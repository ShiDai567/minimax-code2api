import json
import logging
import time
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import Base, engine, get_db
from app.core.security import decrypt_secret, encrypt_secret, hash_api_key, mask_secret, new_api_key, verify_api_key
from app.models import Account, AccountGroup, ApiKey, CheckinRecord, CreditLedger, RequestLog
from app.providers import PROVIDERS, balance, checkin
from app.schemas import AccountCreate, AccountUpdate, GroupCreate, KeyCreate

APP_VERSION = "0.1.0"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("code2api")
app = FastAPI(title="MiniMax Code2API", version="0.1.0")


def require_admin(authorization: str | None = Header(default=None)):
    expected = get_settings().admin_token
    if not expected:
        raise HTTPException(503, "ADMIN_TOKEN must be configured")
    if not authorization or not authorization.startswith("Bearer ") or not verify_api_key(authorization[7:], hash_api_key(expected)):
        raise HTTPException(401, "Admin authentication required")


def account_json(row: Account):
    cred = decrypt_secret(row.credential_ciphertext)
    return {"id": str(row.id), "region": row.region, "name": row.name, "identifier": row.identifier,
            "realUserId": row.real_user_id,
            "health": row.health, "healthReason": row.health_reason, "enabled": row.enabled,
            "credentialMasked": mask_secret(cred), "groupId": str(row.group_id) if row.group_id else None,
            "balance": row.balance, "balanceSyncedAt": row.balance_synced_at, "createdAt": row.created_at,
            "lastCheckinAt": row.last_checkin_at, "lastActiveAt": row.last_active_at, "note": row.note,
            "dataSource": "live"}


@app.get("/health")
def health():
    return {"status": "ok", "version": app.version, "capabilities": {"accounts": "real", "gateway": "real", "models": "unsupported", "checkin": "unknown", "credits": "unknown"}}


@app.get("/api/v1/capabilities", dependencies=[Depends(require_admin)])
def capabilities():
    return {"data": {"serviceControl": False, "protocolToggle": False, "modelToggle": False,
                      "checkin": False, "credits": False, "multiAccount": True, "runtimeLogs": True,
                      "checkinSource": "unknown", "balanceSource": "unknown"}, "source": "live"}


@app.get("/api/v1/accounts", dependencies=[Depends(require_admin)])
def list_accounts(region: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Account).order_by(Account.id)
    if region:
        if region not in PROVIDERS:
            raise HTTPException(422, "region must be cn or global")
        stmt = stmt.where(Account.region == region)
    total_stmt = select(func.count()).select_from(Account)
    if region:
        total_stmt = total_stmt.where(Account.region == region)
    return {"items": [account_json(x) for x in db.scalars(stmt)], "total": db.scalar(total_stmt), "source": "live"}


@app.post("/api/v1/accounts", dependencies=[Depends(require_admin)], status_code=201)
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    if data.group_id:
        group = db.get(AccountGroup, data.group_id)
        if not group or group.region != data.region:
            raise HTTPException(422, "Group must belong to the same region")
    row = Account(region=data.region, name=data.name, identifier=data.identifier, real_user_id=data.real_user_id,
                  credential_ciphertext=encrypt_secret(data.credential), group_id=data.group_id, note=data.note)
    db.add(row)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(409, "Account identifier already exists in this region") from exc
    db.refresh(row)
    return account_json(row)


@app.patch("/api/v1/accounts/{account_id}", dependencies=[Depends(require_admin)])
def update_account(account_id: int, data: AccountUpdate, db: Session = Depends(get_db)):
    row = db.get(Account, account_id)
    if not row:
        raise HTTPException(404, "Account not found")
    values = data.model_dump(exclude_unset=True)
    if "group_id" in values and values["group_id"] is not None:
        group = db.get(AccountGroup, values["group_id"])
        if not group or group.region != row.region:
            raise HTTPException(422, "Group must belong to the same region")
    if values.get("credential"):
        row.credential_ciphertext = encrypt_secret(values.pop("credential"))
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return account_json(row)


@app.delete("/api/v1/accounts/{account_id}", dependencies=[Depends(require_admin)], status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    row = db.get(Account, account_id)
    if not row:
        raise HTTPException(404, "Account not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@app.post("/api/v1/accounts/bulk-delete", dependencies=[Depends(require_admin)])
def bulk_delete_accounts(ids: list[int], db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Account).where(Account.id.in_(ids))))
    for row in rows:
        db.delete(row)
    db.commit()
    return {"deleted": len(rows)}


@app.get("/api/v1/groups", dependencies=[Depends(require_admin)])
def list_groups(region: str | None = None, db: Session = Depends(get_db)):
    stmt = select(AccountGroup).order_by(AccountGroup.id)
    if region:
        stmt = stmt.where(AccountGroup.region == region)
    rows = list(db.scalars(stmt))
    return {"items": [{"id": str(g.id), "region": g.region, "name": g.name, "description": g.description,
                        "createdAt": g.created_at, "accountCount": len(g.accounts)} for g in rows], "total": len(rows), "source": "live"}


@app.post("/api/v1/groups", dependencies=[Depends(require_admin)], status_code=201)
def create_group(data: GroupCreate, db: Session = Depends(get_db)):
    row = AccountGroup(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "region": row.region, "name": row.name, "description": row.description, "createdAt": row.created_at}


@app.get("/api/v1/keys", dependencies=[Depends(require_admin)])
def list_keys(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(ApiKey).order_by(ApiKey.id)))
    return {"items": [{"id": str(k.id), "name": k.name, "masked": k.key_prefix + "••••••••", "enabled": k.enabled,
                        "createdAt": k.created_at, "lastUsedAt": k.last_used_at, "requestCount": k.request_count,
                        "permissions": json.loads(k.permissions), "note": k.note} for k in rows], "total": len(rows), "source": "live"}


@app.post("/api/v1/keys", dependencies=[Depends(require_admin)], status_code=201)
def create_key(data: KeyCreate, db: Session = Depends(get_db)):
    secret = new_api_key()
    row = ApiKey(name=data.name, note=data.note, permissions=json.dumps(data.permissions), key_hash=hash_api_key(secret), key_prefix=secret[:12])
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"key": {"id": str(row.id), "name": row.name, "masked": mask_secret(secret), "enabled": row.enabled,
                     "createdAt": row.created_at, "lastUsedAt": None, "requestCount": 0, "note": row.note}, "secret": secret}


@app.patch("/api/v1/keys/{key_id}", dependencies=[Depends(require_admin)])
def toggle_key(key_id: int, enabled: bool, db: Session = Depends(get_db)):
    row = db.get(ApiKey, key_id)
    if not row:
        raise HTTPException(404, "API key not found")
    row.enabled = enabled
    db.commit()
    return {"id": str(row.id), "enabled": row.enabled}


@app.delete("/api/v1/keys/{key_id}", dependencies=[Depends(require_admin)], status_code=204)
def delete_key(key_id: int, db: Session = Depends(get_db)):
    row = db.get(ApiKey, key_id)
    if not row:
        raise HTTPException(404, "API key not found")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


def authenticate_gateway(authorization: str | None, db: Session) -> ApiKey:
    secret = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    row = db.scalar(select(ApiKey).where(ApiKey.key_hash == hash_api_key(secret), ApiKey.enabled.is_(True))) if secret else None
    if not row:
        raise HTTPException(401, {"type": "authentication_error", "message": "Invalid or missing API key"})
    return row


@app.get("/v1/models")
def models(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    authenticate_gateway(authorization, db)
    raise HTTPException(501, "Model discovery is unavailable: no verified upstream model-list adapter is configured")


@app.api_route("/v1/messages", methods=["POST"])
@app.api_route("/v1/chat/completions", methods=["POST"])
@app.api_route("/v1/responses", methods=["POST"])
async def gateway(request: Request, authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    key = authenticate_gateway(authorization, db)
    path = request.url.path
    payload = await request.body()
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Request body must be valid JSON")
    client_model = str(parsed.get("model", ""))
    region = request.headers.get("x-minimax-region", "cn")
    if region not in PROVIDERS:
        raise HTTPException(400, "x-minimax-region must be cn or global")
    if path == "/v1/chat/completions" or path == "/v1/responses":
        raise HTTPException(501, "OpenAI protocol adapters are not implemented yet; use /v1/messages")
    excluded: set[int] = set()
    max_attempts = 3
    request_id = "req_" + uuid.uuid4().hex[:16]
    start = time.monotonic()
    response = None
    account = None
    error = None
    for _ in range(max_attempts):
        stmt = select(Account).where(Account.region == region, Account.enabled.is_(True), Account.health == "healthy")
        candidates = [a for a in db.scalars(stmt.order_by(Account.last_active_at.asc().nullsfirst(), Account.id)) if a.id not in excluded]
        if not candidates:
            error = "No healthy account available for requested region"
            break
        account = candidates[0]
        try:
            token = decrypt_secret(account.credential_ciphertext)
            if parsed.get("stream") is True:
                return await stream_gateway_response(request, db, key, account, region, path, token, payload,
                                                     client_model, request_id, start, safe_headers={
                                                         name: ("[REDACTED]" if name.lower() in {"authorization", "x-api-key", "cookie"} else value)
                                                         for name, value in request.headers.items()
                                                         if name.lower() in {"authorization", "x-api-key", "content-type", "anthropic-version", "x-minimax-region"}})
            async with httpx.AsyncClient(timeout=get_settings().upstream_timeout_seconds) as client:
                response = await PROVIDERS[region].request(client, path, token, payload, dict(request.headers))
            if response.status_code == 401:
                account.health = "expired"
                account.health_reason = "Upstream authentication rejected"
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
    safe_headers = {name: ("[REDACTED]" if name.lower() in {"authorization", "x-api-key", "cookie"} else value)
                    for name, value in request.headers.items() if name.lower() in {"authorization", "x-api-key", "content-type", "anthropic-version", "x-minimax-region"}}
    db.add(RequestLog(id=request_id, api_key_id=key.id, account_id=account.id if account else None,
                      region=region, protocol="anthropic" if path.startswith("/v1/messages") else "openai_responses" if path.endswith("/responses") else "openai_chat",
                      endpoint=path, model=client_model, resolved_model=client_model, status="success" if 200 <= status_code < 400 else "error",
                      http_status=status_code, duration_ms=duration, error_message=error if status_code >= 400 else None,
                      safe_headers=json.dumps(safe_headers), client_ip=request.client.host if request.client else "", stream=bool(parsed.get("stream"))))
    key.request_count += 1
    key.last_used_at = datetime.now(timezone.utc)
    if account:
        account.last_active_at = datetime.now(timezone.utc)
    db.commit()
    response_headers = {name: value for name, value in (response.headers.items() if response else [])
                        if name.lower() in {"content-type", "cache-control", "retry-after", "anthropic-version"}}
    response_headers["x-request-id"] = request_id
    return Response(content=body, status_code=status_code, headers=response_headers, media_type=response.headers.get("content-type") if response else "application/json")


async def stream_gateway_response(request: Request, db: Session, key: ApiKey, account: Account, region: str,
                                  path: str, token: str, payload: bytes, model: str, request_id: str,
                                  start: float, safe_headers: dict[str, str]):
    client = httpx.AsyncClient(timeout=get_settings().upstream_timeout_seconds)
    upstream = await PROVIDERS[region].request(client, path, token, payload,
                                               {"Content-Type": "application/json", "Accept": "text/event-stream"}, stream=True)
    if upstream.status_code >= 400:
        content = await upstream.aread()
        await upstream.aclose()
        await client.aclose()
        duration = int((time.monotonic() - start) * 1000)
        db.add(RequestLog(id=request_id, api_key_id=key.id, account_id=account.id, region=region,
                          protocol="anthropic" if path.startswith("/v1/messages") else "openai_responses" if path.endswith("/responses") else "openai_chat",
                          endpoint=path, model=model, resolved_model=model, status="error", http_status=upstream.status_code,
                          duration_ms=duration, error_message="upstream request failed", safe_headers=json.dumps(safe_headers),
                          client_ip=request.client.host if request.client else "", stream=True))
        key.request_count += 1
        key.last_used_at = datetime.now(timezone.utc)
        db.commit()
        return Response(content=content, status_code=upstream.status_code, media_type=upstream.headers.get("content-type", "application/json"), headers={"x-request-id": request_id})

    async def body_iterator():
        first_token_ms = None
        status = "success"
        error_message = None
        try:
            async for chunk in upstream.aiter_raw():
                if await request.is_disconnected():
                    break
                if first_token_ms is None and chunk:
                    first_token_ms = int((time.monotonic() - start) * 1000)
                yield chunk
        except (httpx.HTTPError, OSError) as exc:
            status = "error"
            error_message = str(exc)
            log.warning("stream %s interrupted: %s", request_id, exc)
        finally:
            await upstream.aclose()
            await client.aclose()
            db.add(RequestLog(id=request_id, api_key_id=key.id, account_id=account.id, region=region,
                              protocol="anthropic" if path.startswith("/v1/messages") else "openai_responses" if path.endswith("/responses") else "openai_chat",
                              endpoint=path, model=model, resolved_model=model, status=status, http_status=upstream.status_code,
                              duration_ms=int((time.monotonic() - start) * 1000), first_token_ms=first_token_ms,
                              error_message=error_message, safe_headers=json.dumps(safe_headers),
                              client_ip=request.client.host if request.client else "", stream=True))
            key.request_count += 1
            key.last_used_at = datetime.now(timezone.utc)
            account.last_active_at = datetime.now(timezone.utc)
            db.commit()

    headers = {name: value for name, value in upstream.headers.items()
               if name.lower() in {"content-type", "cache-control", "retry-after", "anthropic-version"}}
    headers["x-request-id"] = request_id
    return StreamingResponse(body_iterator(), status_code=upstream.status_code, headers=headers,
                             media_type=upstream.headers.get("content-type", "text/event-stream"))


@app.get("/api/v1/logs", dependencies=[Depends(require_admin)])
def logs(limit: int = Query(default=50, ge=1, le=500), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(RequestLog).order_by(RequestLog.created_at.desc()).offset(offset).limit(limit)))
    return {"items": [{"id": r.id, "at": r.created_at, "apiKeyId": str(r.api_key_id) if r.api_key_id else None,
                        "protocol": r.protocol, "endpoint": r.endpoint, "model": r.model, "resolvedModel": r.resolved_model,
                        "accountId": str(r.account_id) if r.account_id else None, "region": r.region, "status": r.status,
                        "httpStatus": r.http_status, "latencyMs": r.duration_ms, "firstTokenTime": r.first_token_ms,
                        "estimatedCredits": r.estimated_credits, "actualCredits": r.actual_credits,
                        "inputTokens": r.input_tokens, "outputTokens": r.output_tokens, "errorMessage": r.error_message,
                        "headers": json.loads(r.safe_headers), "clientIp": r.client_ip, "stream": r.stream} for r in rows], "source": "live"}


@app.get("/api/v1/credits", dependencies=[Depends(require_admin)])
def credits(db: Session = Depends(get_db)):
    rows = list(db.scalars(select(CreditLedger).order_by(CreditLedger.created_at.desc()).limit(500)))
    return {"items": [{"id": str(x.id), "accountId": str(x.account_id), "region": x.region, "type": x.kind,
                        "delta": x.delta, "balanceBefore": x.balance_before, "balanceAfter": x.balance_after,
                        "certainty": x.certainty, "requestId": x.request_id, "at": x.created_at, "note": x.note} for x in rows],
            "source": "live", "balanceSource": "unknown"}


@app.post("/api/v1/checkin/run", dependencies=[Depends(require_admin)])
async def run_checkin(account_id: int, db: Session = Depends(get_db)):
    row = db.get(Account, account_id)
    if not row:
        raise HTTPException(404, "Account not found")
    if not row.enabled:
        raise HTTPException(409, "Account is disabled")
    if not row.real_user_id:
        raise HTTPException(422, "Account real_user_id is required for MiniMax Code check-in")
    business_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    existing = db.scalar(select(CheckinRecord).where(CheckinRecord.account_id == row.id,
                                                       CheckinRecord.business_date == business_date))
    if existing and existing.status in {"success", "pending"}:
        return {"accountId": str(row.id), "status": "skipped", "message": "Already attempted for business date", "arrival": existing.arrival}
    record = existing or CheckinRecord(account_id=row.id, region=row.region, business_date=business_date,
                                        status="pending", arrival="unknown")
    record.status = "pending"
    db.add(record)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(409, "Check-in already in progress or recorded") from exc
    try:
        result = await checkin(row.region, decrypt_secret(row.credential_ciphertext), row.real_user_id, APP_VERSION)
        record.status = "success" if result["status"] in {"claimed", "already_claimed"} else "failed"
        record.reward = result.get("reward")
        record.arrival = "pending" if result.get("reward") is not None else "unknown"
        if result["status"] == "claimed" and isinstance(result.get("reward"), (int, float)):
            db.add(CreditLedger(account_id=row.id, region=row.region, kind="checkin_reward", delta=result["reward"],
                                balance_before=None, balance_after=None, certainty="reported", note="Upstream check-in claim reward; balance not reconciled"))
        row.last_checkin_at = datetime.now(timezone.utc) if record.status == "success" else row.last_checkin_at
        record.failure_reason = None if record.status == "success" else "Upstream says check-in is not claimable"
        db.commit()
        return {"accountId": str(row.id), "status": record.status, "reward": record.reward,
                "arrival": record.arrival, "message": record.failure_reason or result["status"]}
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        record.status = "failed"
        record.failure_reason = str(exc)[:1000]
        row.health_reason = record.failure_reason
        db.commit()
        raise HTTPException(502, "Upstream check-in failed; see the account error detail") from exc


@app.post("/api/v1/accounts/{account_id}/balance-sync", dependencies=[Depends(require_admin)])
async def sync_balance(account_id: int, db: Session = Depends(get_db)):
    row = db.get(Account, account_id)
    if not row:
        raise HTTPException(404, "Account not found")
    try:
        result = await balance(row.region, decrypt_secret(row.credential_ciphertext))
    except (httpx.HTTPError, RuntimeError) as exc:
        raise HTTPException(502, "Upstream balance query failed") from exc
    summary = result.get("op_credit_summary") or result.get("data", {}).get("op_credit_summary")
    amount = summary.get("total_remaining_amount") if isinstance(summary, dict) else result.get("opcredit_balance")
    if amount is None:
        raise HTTPException(502, "Upstream response did not contain a verifiable credit balance")
    try:
        amount = float(amount)
    except (TypeError, ValueError) as exc:
        raise HTTPException(502, "Upstream credit balance was not numeric") from exc
    before = row.balance
    row.balance = amount
    row.balance_synced_at = datetime.now(timezone.utc)
    db.add(CreditLedger(account_id=row.id, region=row.region, kind="balance_reconciliation", delta=0,
                        balance_before=before, balance_after=amount, certainty="confirmed",
                        note="Upstream Token Plan balance snapshot; delta is not a usage charge"))
    db.commit()
    return {"accountId": str(row.id), "region": row.region, "balance": amount, "syncedAt": row.balance_synced_at, "source": "real"}


@app.get("/api/v1/dashboard", dependencies=[Depends(require_admin)])
def dashboard(db: Session = Depends(get_db)):
    account_rows = list(db.scalars(select(Account)))
    request_rows = list(db.scalars(select(RequestLog)))
    now = datetime.now(timezone.utc)
    todays = [r for r in request_rows if r.created_at and r.created_at.date() == now.date()]
    total_balance = sum(a.balance for a in account_rows if a.balance is not None)
    activity = [{"id": r.id, "at": r.created_at, "kind": "request_success" if r.status == "success" else "request_failed",
                 "accountId": str(r.account_id) if r.account_id else None, "region": r.region,
                 "title": "API 请求成功" if r.status == "success" else "API 请求失败",
                 "detail": f"{r.protocol} · {r.model} · {r.duration_ms}ms", "read": False}
                for r in sorted(request_rows, key=lambda x: x.created_at or now, reverse=True)[:10]]
    return {"metrics": {"totalAccounts": {"value": len(account_rows), "previous": None},
                         "healthyAccounts": {"value": sum(a.enabled and a.health == "healthy" for a in account_rows), "previous": None},
                         "totalBalance": {"value": total_balance if all(a.balance is not None for a in account_rows) else None, "previous": None},
                         "checkinsToday": {"value": None, "previous": None},
                         "requestsToday": {"value": len(todays), "previous": None},
                         "creditsConsumedToday": {"value": None, "previous": None}},
            "regions": [{"region": region, "total": sum(a.region == region for a in account_rows),
                         "online": sum(a.region == region and a.enabled and a.health == "healthy" for a in account_rows),
                         "abnormal": sum(a.region == region and a.health in {"error", "expired"} for a in account_rows),
                         "disabled": sum(a.region == region and not a.enabled for a in account_rows),
                         "checkedIn": None, "awaitingCheckin": None,
                         "balance": sum(a.balance or 0 for a in account_rows if a.region == region),
                         "unsyncedBalances": sum(a.region == region and a.balance is None for a in account_rows),
                         "consumption7d": []} for region in ("cn", "global")],
            "gateway": {"state": "running", "totalRequests": len(request_rows), "successRate":
                        (sum(r.status == "success" for r in request_rows) / len(request_rows) * 100 if request_rows else None),
                        "avgLatencyMs": (sum(r.duration_ms for r in request_rows) / len(request_rows) if request_rows else None),
                        "inflight": 0, "errors24h": sum(r.status == "error" for r in todays), "startedAt": None},
            "activity": activity, "source": "live"}
