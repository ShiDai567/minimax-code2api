import json
import logging
import time
import uuid
from datetime import datetime, timezone

import httpx
from flask import Blueprint, Response, abort, g, jsonify, request, stream_with_context
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.http import db_session
from app.core.security import decrypt_secret, hash_api_key
from app.models import Account, ApiKey, RequestLog
from app.providers import PROVIDERS

gateway_bp = Blueprint("gateway", __name__)
log = logging.getLogger("code2api")
SAFE_HEADERS = {"authorization", "x-api-key", "content-type", "anthropic-version", "x-minimax-region"}


def authenticate_gateway():
    authorization = request.headers.get("Authorization", "")
    secret = authorization[7:] if authorization.startswith("Bearer ") else ""
    row = db_session().scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(secret), ApiKey.enabled.is_(True))) if secret else None
    if not row:
        return None
    return row


@gateway_bp.get("/v1/models")
def models():
    if not authenticate_gateway():
        return jsonify({"detail": {"type": "authentication_error", "message": "Invalid or missing API key"}}), 401
    return jsonify({"detail": "Model discovery is unavailable: no verified upstream model-list adapter is configured"}), 501


@gateway_bp.post("/v1/messages")
@gateway_bp.post("/v1/chat/completions")
@gateway_bp.post("/v1/responses")
def gateway():
    key = authenticate_gateway()
    if not key:
        return jsonify({"detail": {"type": "authentication_error", "message": "Invalid or missing API key"}}), 401
    path, payload = request.path, request.get_data()
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        abort(400, description="Request body must be valid JSON")
    if not isinstance(parsed, dict):
        abort(400, description="Request body must be a JSON object")
    client_model = str(parsed.get("model", ""))
    region = request.headers.get("x-minimax-region", "cn")
    if region not in PROVIDERS:
        abort(400, description="x-minimax-region must be cn or global")
    if path in {"/v1/chat/completions", "/v1/responses"}:
        abort(501, description="OpenAI protocol adapters are not implemented yet; use /v1/messages")

    db = db_session()
    excluded, request_id, start = set(), "req_" + uuid.uuid4().hex[:16], time.monotonic()
    response = account = None
    error = None
    safe_headers = {name: ("[REDACTED]" if name.lower() in {"authorization", "x-api-key", "cookie"} else value)
                    for name, value in request.headers.items() if name.lower() in SAFE_HEADERS}
    for _ in range(3):
        stmt = select(Account).where(Account.region == region, Account.enabled.is_(True), Account.health == "healthy")
        candidates = [a for a in db.scalars(stmt.order_by(Account.last_active_at.asc().nullsfirst(), Account.id)) if a.id not in excluded]
        if not candidates:
            error = "No healthy account available for requested region"
            break
        account = candidates[0]
        try:
            token = decrypt_secret(account.credential_ciphertext)
            if parsed.get("stream") is True:
                return stream_gateway_response(key.id, account.id, region, path, token, payload,
                                               client_model, request_id, start, safe_headers)
            with httpx.Client(timeout=get_settings().upstream_timeout_seconds) as client:
                response = PROVIDERS[region].request_sync(client, path, token, payload, dict(request.headers))
            if response.status_code == 401:
                account.health, account.health_reason = "expired", "Upstream authentication rejected"
                excluded.add(account.id)
                db.commit()
                error = "Upstream authentication rejected"
                continue
            break
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            excluded.add(account.id)
            error = str(exc)
    duration = int((time.monotonic() - start) * 1000)
    status_code = response.status_code if response else 502
    body = response.content if response else json.dumps({"error": {"type": "upstream_error", "message": error or "No upstream account available"}}).encode()
    db.add(RequestLog(id=request_id, api_key_id=key.id, account_id=account.id if account else None,
                      region=region, protocol="anthropic", endpoint=path, model=client_model,
                      resolved_model=client_model, status="success" if 200 <= status_code < 400 else "error",
                      http_status=status_code, duration_ms=duration,
                      error_message=error if status_code >= 400 else None, safe_headers=json.dumps(safe_headers),
                      client_ip=request.remote_addr or "", stream=False))
    key.request_count += 1
    key.last_used_at = datetime.now(timezone.utc)
    if account:
        account.last_active_at = datetime.now(timezone.utc)
    db.commit()
    headers = {name: value for name, value in (response.headers.items() if response else [])
               if name.lower() in {"content-type", "cache-control", "retry-after", "anthropic-version"}}
    headers["x-request-id"] = request_id
    return Response(body, status=status_code, headers=headers,
                    content_type=response.headers.get("content-type") if response else "application/json")


def stream_gateway_response(key_id, account_id, region, path, token, payload, model, request_id, start, safe_headers):
    client_ip = request.remote_addr or ""
    client = httpx.Client(timeout=get_settings().upstream_timeout_seconds)
    try:
        upstream = PROVIDERS[region].request_sync(client, path, token, payload,
                    {"Content-Type": "application/json", "Accept": "text/event-stream"}, stream=True)
    except Exception:
        client.close()
        raise
    if upstream.status_code >= 400:
        content = upstream.content
        upstream.close()
        client.close()
        db = db_session()
        key, account = db.get(ApiKey, key_id), db.get(Account, account_id)
        db.add(RequestLog(id=request_id, api_key_id=key_id, account_id=account_id, region=region,
                          protocol="anthropic", endpoint=path, model=model, resolved_model=model, status="error",
                          http_status=upstream.status_code, duration_ms=int((time.monotonic() - start) * 1000),
                          error_message="upstream request failed", safe_headers=json.dumps(safe_headers),
                          client_ip=client_ip, stream=True))
        key.request_count += 1
        key.last_used_at = datetime.now(timezone.utc)
        db.commit()
        return Response(content, status=upstream.status_code, content_type=upstream.headers.get("content-type", "application/json"),
                        headers={"x-request-id": request_id})

    @stream_with_context
    def body_iterator():
        first_token_ms, status, error_message = None, "success", None
        try:
            for chunk in upstream.iter_raw():
                if first_token_ms is None and chunk:
                    first_token_ms = int((time.monotonic() - start) * 1000)
                yield chunk
        except (httpx.HTTPError, OSError) as exc:
            status, error_message = "error", str(exc)
            log.warning("stream %s interrupted: %s", request_id, exc)
        finally:
            upstream.close()
            client.close()
            with SessionLocal() as db:
                key, account = db.get(ApiKey, key_id), db.get(Account, account_id)
                db.add(RequestLog(id=request_id, api_key_id=key_id, account_id=account_id, region=region,
                                  protocol="anthropic", endpoint=path, model=model, resolved_model=model,
                                  status=status, http_status=upstream.status_code,
                                  duration_ms=int((time.monotonic() - start) * 1000), first_token_ms=first_token_ms,
                                  error_message=error_message, safe_headers=json.dumps(safe_headers),
                                  client_ip=client_ip, stream=True))
                key.request_count += 1
                key.last_used_at = datetime.now(timezone.utc)
                account.last_active_at = datetime.now(timezone.utc)
                db.commit()

    headers = {name: value for name, value in upstream.headers.items()
               if name.lower() in {"content-type", "cache-control", "retry-after", "anthropic-version"}}
    headers["x-request-id"] = request_id
    return Response(body_iterator(), status=upstream.status_code, headers=headers,
                    content_type=upstream.headers.get("content-type", "text/event-stream"))
