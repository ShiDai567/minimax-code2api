import hashlib
import json
import time
import uuid

import httpx
from flask import (
    Blueprint,
    Response,
    g,
    jsonify,
    request,
    stream_with_context,
)
from sqlalchemy import update

from . import db
from .http import ApiProblem, get_or_404, json_body, result
from .models import Account, ApiKey, RequestLog, utcnow
from .providers import provider_for
from .routes import api, serialize_account

gateway = Blueprint("gateway", __name__, url_prefix="/v1")


@gateway.before_request
def authenticate_key():
    auth = request.headers.get("Authorization", "")
    secret = auth[7:] if auth.startswith("Bearer ") else request.headers.get("x-api-key", "")
    digest = hashlib.sha256(secret.encode()).hexdigest()
    key = db.session.scalar(db.select(ApiKey).where(ApiKey.key_hash == digest, ApiKey.enabled.is_(True)))
    if key is None:
        raise ApiProblem("API key required", 401, "UNAUTHORIZED")
    g.key_id = key.id


def selected_region():
    region = request.headers.get("x-minimax-region", "cn")
    if region not in ("cn", "global"):
        raise ApiProblem("Invalid x-minimax-region", 400)
    return region


def select_account(region):
    account = db.session.scalar(db.select(Account).where(Account.region == region, Account.enabled.is_(True),
        Account.health == "healthy").order_by(Account.last_active_at.asc().nulls_first(), Account.id).limit(1))
    if not account:
        raise ApiProblem("No verified, enabled account in the selected region", 503, "NO_ACCOUNT")
    return account


@api.post("/accounts/<int:account_id>/verify-model")
def verify_model(account_id):
    account = get_or_404(Account, account_id)
    if not account.enabled:
        raise ApiProblem("Account is disabled")
    body = json_body({"model"})
    model = body.get("model")
    if not isinstance(model, str) or not 0 < len(model.strip()) <= 255:
        raise ApiProblem("A known model is required")
    verified_credential = account.credential_encrypted
    response, client = provider_for(account).messages({"model": model.strip(), "messages": [{"role": "user", "content": "test"}]}, suffix="messages/count_tokens")
    try:
        raw = response.read()
        if response.status_code in (401, 403):
            health, reason, verified_at = "expired", "Upstream rejected credential", None
        elif response.is_success:
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict) or type(parsed.get("input_tokens")) is not int:
                    raise ValueError
            except (ValueError, UnicodeDecodeError):
                raise ApiProblem("Unexpected verification response", 502, "UPSTREAM_ERROR") from None
            health, reason, verified_at = "healthy", None, utcnow()
        else:
            raise ApiProblem(f"Upstream returned HTTP {response.status_code}", 502, "UPSTREAM_ERROR")
        changed = db.session.execute(update(Account).where(
            Account.id == account_id, Account.credential_encrypted == verified_credential,
            Account.enabled.is_(True)).values(health=health, health_reason=reason, verified_at=verified_at))
        if changed.rowcount != 1:
            db.session.rollback()
            raise ApiProblem("Account changed during verification; retry", 409, "ACCOUNT_CHANGED")
        db.session.commit()
        db.session.refresh(account)
        return result(serialize_account(account))
    except httpx.HTTPError:
        raise ApiProblem("Upstream verification response interrupted", 502, "UPSTREAM_ERROR") from None
    finally:
        response.close()
        client.close()


@gateway.get("/models")
def models():
    account = select_account(selected_region())
    return {"object": "list", "data": provider_for(account).models()}


def convert_request(body, protocol):
    if protocol == "anthropic":
        return body
    allowed = {"model", "messages", "max_tokens", "max_completion_tokens", "temperature", "top_p", "stream", "stop"}
    if protocol == "openai_responses":
        allowed = {"model", "input", "instructions", "max_output_tokens", "temperature", "top_p", "stream"}
    unsupported = set(body) - allowed
    if unsupported:
        raise ApiProblem("Unsupported fields: " + ", ".join(sorted(unsupported)), 400, "UNSUPPORTED")
    if body.get("stream", False):
        raise ApiProblem("OpenAI streaming conversion is not implemented", 501, "UNSUPPORTED")
    if protocol == "openai_chat":
        messages = body.get("messages")
    else:
        inp = body.get("input")
        messages = [{"role": "user", "content": inp}] if isinstance(inp, str) else inp
        if body.get("instructions") is not None:
            messages = [{"role": "system", "content": body["instructions"]}] + (messages if isinstance(messages, list) else [])
    if not isinstance(messages, list) or not messages:
        raise ApiProblem("A non-empty message list is required", 400)
    converted, system = [], []
    for item in messages:
        if not isinstance(item, dict) or set(item) != {"role", "content"} or not isinstance(item["content"], str):
            raise ApiProblem("Only plain-text messages are supported", 400, "UNSUPPORTED")
        if item["role"] in ("system", "developer"):
            system.append(item["content"])
        elif item["role"] in ("user", "assistant"):
            converted.append({"role": item["role"], "content": item["content"]})
        else:
            raise ApiProblem("Unsupported message role", 400, "UNSUPPORTED")
    if not converted:
        raise ApiProblem("A user or assistant message is required", 400)
    maximum = body.get("max_tokens", body.get("max_completion_tokens", body.get("max_output_tokens", 4096)))
    if type(maximum) is not int or maximum < 1:
        raise ApiProblem("Invalid maximum output tokens", 400)
    result_body = {"model": body.get("model"), "messages": converted, "max_tokens": maximum}
    if system:
        result_body["system"] = "\n\n".join(system)
    for field in ("temperature", "top_p"):
        if field in body:
            result_body[field] = body[field]
    if "stop" in body:
        stop = body["stop"]
        if isinstance(stop, str):
            stop = [stop]
        if not isinstance(stop, list) or not all(isinstance(s, str) for s in stop):
            raise ApiProblem("Invalid stop sequences", 400)
        result_body["stop_sequences"] = stop
    return result_body


def convert_response(body, protocol):
    if not isinstance(body, dict) or not isinstance(body.get("content"), list):
        raise ApiProblem("Invalid upstream message", 502, "UPSTREAM_ERROR")
    if any(not isinstance(block, dict) or block.get("type") != "text" or not isinstance(block.get("text"), str)
           for block in body["content"]):
        raise ApiProblem("Upstream returned unsupported content", 502, "UNSUPPORTED")
    content = "".join(block["text"] for block in body["content"])
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    inp, out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    if type(inp) is not int or type(out) is not int or inp < 0 or out < 0:
        raise ApiProblem("Invalid upstream usage", 502, "UPSTREAM_ERROR")
    if body.get("stop_reason") not in ("end_turn", "stop_sequence", "max_tokens"):
        raise ApiProblem("Unsupported upstream stop reason", 502, "UNSUPPORTED")
    identifier, model, created = body.get("id", "msg_" + uuid.uuid4().hex), body.get("model"), int(time.time())
    if protocol == "openai_chat":
        return {"id": identifier, "object": "chat.completion", "created": created, "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                             "finish_reason": "length" if body.get("stop_reason") == "max_tokens" else "stop"}],
                "usage": {"prompt_tokens": inp, "completion_tokens": out, "total_tokens": inp + out}}
    response_status = "incomplete" if body.get("stop_reason") == "max_tokens" else "completed"
    return {"id": identifier, "object": "response", "created_at": created, "status": response_status, "model": model,
            "incomplete_details": {"reason": "max_output_tokens"} if response_status == "incomplete" else None,
            "output": [{"id": "msg_" + uuid.uuid4().hex, "type": "message", "status": "completed", "role": "assistant",
                        "content": [{"type": "output_text", "text": content, "annotations": []}]}],
            "usage": {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}}


@gateway.post("/messages")
@gateway.post("/messages/count_tokens")
@gateway.post("/chat/completions")
@gateway.post("/responses")
def forward():
    path = request.path
    protocol = "openai_chat" if path.endswith("chat/completions") else "openai_responses" if path.endswith("responses") else "anthropic"
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("model"), str) or not 0 < len(body["model"]) <= 255:
        raise ApiProblem("A JSON object with a model is required", 400)
    if "stream" in body and type(body["stream"]) is not bool:
        raise ApiProblem("stream must be a boolean", 400)
    upstream_body = convert_request(body, protocol)
    region = selected_region()
    account = select_account(region)
    key_id, account_id = g.key_id, account.id
    stream = body.get("stream", False)
    if path.endswith("count_tokens") and stream:
        raise ApiProblem("count_tokens does not support streaming", 400)
    headers = {}
    for header in ("anthropic-version", "anthropic-beta"):
        value = request.headers.get(header)
        if value and len(value) <= 512:
            headers[header] = value
    safe_headers = {k: "[REDACTED]" for k in headers}
    if request.headers.get("Authorization"):
        safe_headers["Authorization"] = "[REDACTED]"
    if request.headers.get("x-api-key"):
        safe_headers["x-api-key"] = "[REDACTED]"
    started = time.monotonic()
    log_id = str(uuid.uuid4())
    endpoint = path
    suffix = "messages/count_tokens" if path.endswith("count_tokens") else "messages"

    def log(status, error=None, usage=None):
        usage = usage if isinstance(usage, dict) else {}
        db.session.add(RequestLog(id=log_id, account_id=account_id, api_key_id=key_id, region=region,
            protocol=protocol, endpoint=endpoint, model=body["model"], http_status=status,
            latency_ms=int((time.monotonic() - started) * 1000), stream=stream,
            input_tokens=usage.get("input_tokens") if type(usage.get("input_tokens")) is int else None,
            output_tokens=usage.get("output_tokens") if type(usage.get("output_tokens")) is int else None,
            error_message=error, headers=safe_headers))
        db.session.execute(update(ApiKey).where(ApiKey.id == key_id).values(
            last_used_at=utcnow(), request_count=ApiKey.request_count + 1))
        db.session.execute(update(Account).where(Account.id == account_id).values(last_active_at=utcnow()))
        db.session.commit()

    try:
        response, client = provider_for(account).messages(upstream_body, headers, suffix)
    except ApiProblem:
        log(502, "Upstream connection failed")
        raise
    status = response.status_code
    if stream and 200 <= status < 300:
        def generate():
            error = None
            try:
                yield from response.iter_bytes()
            except (httpx.HTTPError, GeneratorExit):
                error = "Stream interrupted"
                raise
            finally:
                response.close()
                client.close()
                log(502 if error else status, error)
        return Response(stream_with_context(generate()), status=status, content_type=response.headers.get("content-type", "text/event-stream"),
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    try:
        raw = response.read()
        if not 200 <= status < 300:
            log(status, f"Upstream returned HTTP {status}")
            # Upstream error bodies may contain sensitive context; do not relay them.
            return jsonify(error={"type": "upstream_error", "message": f"Upstream returned HTTP {status}"}), status if status >= 400 else 502
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise TypeError
            converted = convert_response(parsed, protocol) if protocol != "anthropic" else parsed
        except (ValueError, TypeError, UnicodeDecodeError, ApiProblem):
            log(502, "Invalid or unsupported upstream response")
            raise ApiProblem("Invalid or unsupported upstream response", 502, "UPSTREAM_ERROR") from None
        log(status, usage=parsed.get("usage"))
        return jsonify(converted), status
    except httpx.HTTPError:
        log(502, "Upstream response interrupted")
        raise ApiProblem("Upstream response interrupted", 502, "UPSTREAM_ERROR") from None
    finally:
        response.close()
        client.close()
