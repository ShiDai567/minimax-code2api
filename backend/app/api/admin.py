import json

from flask import Blueprint, abort, request
from sqlalchemy import func, select

from app.core.http import db_session, parse_model, require_admin
from app.core.security import decrypt_secret, encrypt_secret, hash_api_key, mask_secret, new_api_key
from app.models import Account, AccountGroup, ApiKey, CreditLedger, RequestLog
from app.providers import PROVIDERS
from app.schemas import AccountCreate, AccountUpdate, GroupCreate, KeyCreate

admin_bp = Blueprint("admin", __name__, url_prefix="/api/v1")


def account_json(row):
    return {"id": str(row.id), "region": row.region, "name": row.name, "identifier": row.identifier,
            "realUserId": row.real_user_id, "health": row.health, "healthReason": row.health_reason,
            "enabled": row.enabled, "credentialMasked": mask_secret(decrypt_secret(row.credential_ciphertext)),
            "groupId": str(row.group_id) if row.group_id else None, "balance": row.balance,
            "balanceSyncedAt": row.balance_synced_at, "createdAt": row.created_at,
            "lastCheckinAt": row.last_checkin_at, "lastActiveAt": row.last_active_at,
            "note": row.note, "dataSource": "live"}


@admin_bp.get("/capabilities")
@require_admin
def capabilities():
    return {"data": {"serviceControl": False, "protocolToggle": False, "modelToggle": False,
                      "checkin": False, "credits": False, "multiAccount": True, "runtimeLogs": True,
                      "checkinSource": "unknown", "balanceSource": "unknown"}, "source": "live"}


@admin_bp.get("/accounts")
@require_admin
def list_accounts():
    db = db_session()
    region = request.args.get("region")
    stmt = select(Account).order_by(Account.id)
    total = select(func.count()).select_from(Account)
    if region:
        if region not in PROVIDERS:
            abort(422, description="region must be cn or global")
        stmt, total = stmt.where(Account.region == region), total.where(Account.region == region)
    return {"items": [account_json(row) for row in db.scalars(stmt)], "total": db.scalar(total), "source": "live"}


@admin_bp.post("/accounts")
@require_admin
def create_account():
    db, data = db_session(), parse_model(AccountCreate)
    if data.group_id:
        group = db.get(AccountGroup, data.group_id)
        if not group or group.region != data.region:
            abort(422, description="Group must belong to the same region")
    row = Account(region=data.region, name=data.name, identifier=data.identifier, real_user_id=data.real_user_id,
                  credential_ciphertext=encrypt_secret(data.credential), group_id=data.group_id, note=data.note)
    db.add(row)
    try:
        db.commit()
    except Exception:
        db.rollback()
        abort(409, description="Account identifier already exists in this region")
    db.refresh(row)
    return account_json(row), 201


@admin_bp.patch("/accounts/<int:account_id>")
@require_admin
def update_account(account_id):
    db, row = db_session(), db_session().get(Account, account_id)
    if not row:
        abort(404, description="Account not found")
    values = parse_model(AccountUpdate).model_dump(exclude_unset=True)
    if values.get("group_id") is not None:
        group = db.get(AccountGroup, values["group_id"])
        if not group or group.region != row.region:
            abort(422, description="Group must belong to the same region")
    if values.get("credential"):
        row.credential_ciphertext = encrypt_secret(values.pop("credential"))
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return account_json(row)


@admin_bp.delete("/accounts/<int:account_id>")
@require_admin
def delete_account(account_id):
    db, row = db_session(), db_session().get(Account, account_id)
    if not row:
        abort(404, description="Account not found")
    db.delete(row)
    db.commit()
    return "", 204


@admin_bp.post("/accounts/bulk-delete")
@require_admin
def bulk_delete_accounts():
    ids = request.get_json(silent=True)
    if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
        abort(422, description="Request body must be an array of account IDs")
    db = db_session()
    rows = list(db.scalars(select(Account).where(Account.id.in_(ids))))
    for row in rows:
        db.delete(row)
    db.commit()
    return {"deleted": len(rows)}


@admin_bp.get("/groups")
@require_admin
def list_groups():
    stmt = select(AccountGroup).order_by(AccountGroup.id)
    if region := request.args.get("region"):
        stmt = stmt.where(AccountGroup.region == region)
    rows = list(db_session().scalars(stmt))
    items = [{"id": str(g.id), "region": g.region, "name": g.name, "description": g.description,
              "createdAt": g.created_at, "accountCount": len(g.accounts)} for g in rows]
    return {"items": items, "total": len(items), "source": "live"}


@admin_bp.post("/groups")
@require_admin
def create_group():
    db, data = db_session(), parse_model(GroupCreate)
    row = AccountGroup(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id), "region": row.region, "name": row.name,
            "description": row.description, "createdAt": row.created_at}, 201


@admin_bp.get("/keys")
@require_admin
def list_keys():
    rows = db_session().scalars(select(ApiKey).order_by(ApiKey.id))
    items = [{"id": str(k.id), "name": k.name, "masked": k.key_prefix + "••••••••", "enabled": k.enabled,
              "createdAt": k.created_at, "lastUsedAt": k.last_used_at, "requestCount": k.request_count,
              "permissions": json.loads(k.permissions), "note": k.note} for k in rows]
    return {"items": items, "total": len(items), "source": "live"}


@admin_bp.post("/keys")
@require_admin
def create_key():
    db, data = db_session(), parse_model(KeyCreate)
    secret = new_api_key()
    row = ApiKey(name=data.name, note=data.note, permissions=json.dumps(data.permissions),
                 key_hash=hash_api_key(secret), key_prefix=secret[:12])
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"key": {"id": str(row.id), "name": row.name, "masked": mask_secret(secret), "enabled": row.enabled,
                     "createdAt": row.created_at, "lastUsedAt": None, "requestCount": 0, "note": row.note},
            "secret": secret}, 201


@admin_bp.patch("/keys/<int:key_id>")
@require_admin
def toggle_key(key_id):
    row = db_session().get(ApiKey, key_id)
    if not row:
        abort(404, description="API key not found")
    enabled = request.args.get("enabled", type=lambda x: x.lower() == "true")
    if enabled is None:
        abort(422, description="enabled query parameter is required")
    row.enabled = enabled
    db_session().commit()
    return {"id": str(row.id), "enabled": row.enabled}


@admin_bp.delete("/keys/<int:key_id>")
@require_admin
def delete_key(key_id):
    db, row = db_session(), db_session().get(ApiKey, key_id)
    if not row:
        abort(404, description="API key not found")
    db.delete(row)
    db.commit()
    return "", 204


@admin_bp.get("/logs")
@require_admin
def logs():
    limit = request.args.get("limit", default=50, type=int)
    offset = request.args.get("offset", default=0, type=int)
    if not 1 <= limit <= 500 or offset < 0:
        abort(422, description="limit must be 1..500 and offset must be non-negative")
    rows = db_session().scalars(select(RequestLog).order_by(RequestLog.created_at.desc()).offset(offset).limit(limit))
    items = [{"id": r.id, "at": r.created_at, "apiKeyId": str(r.api_key_id) if r.api_key_id else None,
              "protocol": r.protocol, "endpoint": r.endpoint, "model": r.model, "resolvedModel": r.resolved_model,
              "accountId": str(r.account_id) if r.account_id else None, "region": r.region, "status": r.status,
              "httpStatus": r.http_status, "latencyMs": r.duration_ms, "firstTokenTime": r.first_token_ms,
              "estimatedCredits": r.estimated_credits, "actualCredits": r.actual_credits, "inputTokens": r.input_tokens,
              "outputTokens": r.output_tokens, "errorMessage": r.error_message, "headers": json.loads(r.safe_headers),
              "clientIp": r.client_ip, "stream": r.stream} for r in rows]
    return {"items": items, "source": "live"}


@admin_bp.get("/credits")
@require_admin
def credits():
    rows = db_session().scalars(select(CreditLedger).order_by(CreditLedger.created_at.desc()).limit(500))
    return {"items": [{"id": str(x.id), "accountId": str(x.account_id), "region": x.region, "type": x.kind,
                       "delta": x.delta, "balanceBefore": x.balance_before, "balanceAfter": x.balance_after,
                       "certainty": x.certainty, "requestId": x.request_id, "at": x.created_at, "note": x.note}
                      for x in rows], "source": "live", "balanceSource": "unknown"}


@admin_bp.get("/dashboard")
@require_admin
def dashboard():
    from datetime import datetime, timezone
    db = db_session()
    account_rows, request_rows = list(db.scalars(select(Account))), list(db.scalars(select(RequestLog)))
    now = datetime.now(timezone.utc)
    todays = [r for r in request_rows if r.created_at and r.created_at.date() == now.date()]
    activity = [{"id": r.id, "at": r.created_at, "kind": "request_success" if r.status == "success" else "request_failed",
                 "accountId": str(r.account_id) if r.account_id else None, "region": r.region,
                 "title": "API 请求成功" if r.status == "success" else "API 请求失败",
                 "detail": f"{r.protocol} · {r.model} · {r.duration_ms}ms", "read": False}
                for r in sorted(request_rows, key=lambda x: x.created_at or now, reverse=True)[:10]]
    return {"metrics": {"totalAccounts": {"value": len(account_rows), "previous": None},
                         "healthyAccounts": {"value": sum(a.enabled and a.health == "healthy" for a in account_rows), "previous": None},
                         "totalBalance": {"value": sum(a.balance for a in account_rows) if all(a.balance is not None for a in account_rows) else None, "previous": None},
                         "checkinsToday": {"value": None, "previous": None}, "requestsToday": {"value": len(todays), "previous": None},
                         "creditsConsumedToday": {"value": None, "previous": None}},
            "regions": [{"region": region, "total": sum(a.region == region for a in account_rows),
                         "online": sum(a.region == region and a.enabled and a.health == "healthy" for a in account_rows),
                         "abnormal": sum(a.region == region and a.health in {"error", "expired"} for a in account_rows),
                         "disabled": sum(a.region == region and not a.enabled for a in account_rows), "checkedIn": None,
                         "awaitingCheckin": None, "balance": sum(a.balance or 0 for a in account_rows if a.region == region),
                         "unsyncedBalances": sum(a.region == region and a.balance is None for a in account_rows),
                         "consumption7d": []} for region in ("cn", "global")],
            "gateway": {"state": "running", "totalRequests": len(request_rows),
                        "successRate": sum(r.status == "success" for r in request_rows) / len(request_rows) * 100 if request_rows else None,
                        "avgLatencyMs": sum(r.duration_ms for r in request_rows) / len(request_rows) if request_rows else None,
                        "inflight": 0, "errors24h": sum(r.status == "error" for r in todays), "startedAt": None},
            "activity": activity, "source": "live"}
