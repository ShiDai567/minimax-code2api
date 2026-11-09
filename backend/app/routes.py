import hashlib
import secrets
import uuid
from collections import Counter

from flask import Blueprint, current_app, request
from sqlalchemy import func

from . import db
from .http import (
    ApiProblem,
    boolean,
    get_or_404,
    integer,
    iso,
    json_body,
    page,
    region_arg,
    region_value,
    result,
    search,
    text,
)
from .models import (
    Account,
    AccountGroup,
    ApiKey,
    BalanceSnapshot,
    CheckinJob,
    CheckinRecord,
    CreditEntry,
    RequestLog,
    utcnow,
)

api = Blueprint("api", __name__, url_prefix="/api/v1")


def serialize_account(account):
    snapshot = db.session.scalar(db.select(BalanceSnapshot).where(
        BalanceSnapshot.account_id == account.id).order_by(BalanceSnapshot.id.desc()).limit(1))
    return {
        "id": account.id, "region": account.region, "name": account.name,
        "identifier": account.identifier, "enabled": account.enabled, "health": account.health,
        "health_reason": account.health_reason, "credential_masked": "••••••••",
        "real_user_id": account.real_user_id, "group_id": account.group_id, "note": account.note,
        "balance": None, "balance_source": "unknown", "created_at": iso(account.created_at),
        "verified_at": iso(account.verified_at), "last_active_at": iso(account.last_active_at),
        "plan_snapshot": serialize_snapshot(snapshot) if snapshot else None,
    }


def serialize_snapshot(snapshot):
    return {"id": snapshot.id, "account_id": snapshot.account_id, "amount": str(snapshot.amount),
            "unit": snapshot.unit, "provider_field": snapshot.provider_field,
            "created_at": iso(snapshot.created_at), "certainty": "reported", "source": "live"}


def serialize_key(key):
    return {"id": key.id, "name": key.name, "key_prefix": key.prefix, "masked": key.prefix + "••••••••",
            "enabled": key.enabled, "created_at": iso(key.created_at), "note": key.note,
            "last_used_at": iso(key.last_used_at), "request_count": key.request_count}


def serialize_group(group):
    count = db.session.scalar(db.select(func.count()).select_from(Account).where(Account.group_id == group.id))
    return {"id": group.id, "region": group.region, "name": group.name,
            "description": group.description, "created_at": iso(group.created_at), "account_count": count}


def serialize_checkin(record):
    account = db.session.get(Account, record.account_id)
    return {"id": record.id, "account_id": record.account_id, "region": account.region,
            "day": record.day.isoformat(), "status": record.status, "trigger": record.trigger,
            "reward": str(record.reward) if record.reward is not None else None,
            "arrival": record.arrival, "claim_id": record.claim_id, "message": record.message,
            "certainty": "reported" if record.reward is not None else "unknown",
            "created_at": iso(record.created_at), "updated_at": iso(record.updated_at)}


def validate_group(group_id, region):
    if group_id is not None:
        integer(group_id, "group_id")
        group = get_or_404(AccountGroup, group_id)
        if group.region != region:
            raise ApiProblem("Accounts and groups must belong to the same region")
    return group_id


@api.get("/capabilities")
def capabilities():
    return result(current_app.extensions["capabilities"]())


@api.get("/accounts")
def accounts():
    region = region_arg()
    query = search(db.select(Account).where(Account.region == region), Account.name, Account.identifier)
    if "enabled" in request.args:
        value = request.args["enabled"]
        if value not in ("true", "false"):
            raise ApiProblem("Invalid enabled filter")
        query = query.where(Account.enabled == (value == "true"))
    if "health" in request.args:
        value = request.args["health"]
        if value not in ("unknown", "healthy", "error", "expired"):
            raise ApiProblem("Invalid health filter")
        query = query.where(Account.health == value)
    if "group_id" in request.args:
        try:
            group_id = int(request.args["group_id"])
        except ValueError:
            raise ApiProblem("Invalid group_id") from None
        validate_group(group_id, region)
        query = query.where(Account.group_id == group_id)
    return page(query, Account, serialize_account, {"id", "name", "created_at", "last_active_at"})


ACCOUNT_FIELDS = {"region", "name", "identifier", "credential", "real_user_id", "group_id", "note", "enabled"}


@api.post("/accounts")
def create_account():
    body = json_body(ACCOUNT_FIELDS)
    region = region_value(body.get("region"))
    credential = text(body, "credential", 16384)
    account = Account(
        name=text(body, "name", 120), identifier=text(body, "identifier", 255), region=region,
        credential_encrypted=current_app.extensions["credential_cipher"].encrypt(credential.encode()),
        group_id=validate_group(body.get("group_id"), region), note=text(body, "note", 4000, False),
        real_user_id=text(body, "real_user_id", 255, False) or None,
        enabled=boolean(body.get("enabled", True), "enabled"), session_id=str(uuid.uuid4()),
    )
    db.session.add(account)
    db.session.commit()
    return result(serialize_account(account), 201)


@api.get("/accounts/<int:account_id>")
def get_account(account_id):
    return result(serialize_account(get_or_404(Account, account_id)))


@api.patch("/accounts/<int:account_id>")
def update_account(account_id):
    account = get_or_404(Account, account_id)
    body = json_body(ACCOUNT_FIELDS - {"region"})
    for field, limit in (("name", 120), ("identifier", 255), ("note", 4000), ("real_user_id", 255)):
        if field in body:
            setattr(account, field, text(body, field, limit, field in ("name", "identifier")))
    if "group_id" in body:
        account.group_id = validate_group(body["group_id"], account.region)
    if "enabled" in body:
        account.enabled = boolean(body["enabled"], "enabled")
    if "credential" in body:
        credential = text(body, "credential", 16384)
        account.credential_encrypted = current_app.extensions["credential_cipher"].encrypt(credential.encode())
        account.health, account.health_reason, account.verified_at = "unknown", None, None
        account.session_id = str(uuid.uuid4())
    db.session.commit()
    return result(serialize_account(account))


@api.delete("/accounts/<int:account_id>")
def delete_account(account_id):
    db.session.delete(get_or_404(Account, account_id))
    db.session.commit()
    return "", 204


@api.post("/accounts/bulk-delete")
def bulk_delete():
    body = json_body({"region", "account_ids"})
    region = region_value(body.get("region"))
    ids = validate_ids(body.get("account_ids"))
    rows = list(db.session.scalars(db.select(Account).where(Account.id.in_(ids), Account.region == region)))
    if len(rows) != len(ids):
        raise ApiProblem("All accounts must exist in the selected region")
    for account in rows:
        db.session.delete(account)
    db.session.commit()
    return result({"deleted": len(rows)})


def validate_ids(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 500:
        raise ApiProblem("account_ids must contain 1..500 unique integers")
    for item in value:
        integer(item, "account_id")
    if len(set(value)) != len(value):
        raise ApiProblem("Duplicate account IDs")
    return value


@api.get("/groups")
def groups():
    query = search(db.select(AccountGroup).where(AccountGroup.region == region_arg()), AccountGroup.name)
    return page(query, AccountGroup, serialize_group, {"id", "name", "created_at"})


@api.post("/groups")
def create_group():
    body = json_body({"region", "name", "description"})
    group = AccountGroup(region=region_value(body.get("region")), name=text(body, "name", 120),
                         description=text(body, "description", 4000, False))
    db.session.add(group)
    db.session.commit()
    return result(serialize_group(group), 201)


@api.patch("/groups/<int:group_id>")
def update_group(group_id):
    group = get_or_404(AccountGroup, group_id)
    body = json_body({"name", "description"})
    if "name" in body:
        group.name = text(body, "name", 120)
    if "description" in body:
        group.description = text(body, "description", 4000, False)
    db.session.commit()
    return result(serialize_group(group))


@api.delete("/groups/<int:group_id>")
def delete_group(group_id):
    db.session.delete(get_or_404(AccountGroup, group_id))
    db.session.commit()
    return "", 204


@api.get("/keys")
@api.get("/api-keys")
def keys():
    query = search(db.select(ApiKey), ApiKey.name)
    return page(query, ApiKey, serialize_key, {"id", "name", "created_at", "last_used_at", "request_count"})


@api.post("/keys")
@api.post("/api-keys")
def create_key():
    body = json_body({"name", "note"})
    secret = "sk-m2a-" + secrets.token_urlsafe(32)
    key = ApiKey(name=text(body, "name", 120), note=text(body, "note", 4000, False),
                 prefix=secret[:15], key_hash=hashlib.sha256(secret.encode()).hexdigest())
    db.session.add(key)
    db.session.commit()
    return result({"key": serialize_key(key), "secret": secret}, 201)


@api.patch("/keys/<int:key_id>")
@api.patch("/api-keys/<int:key_id>")
def update_key(key_id):
    key = get_or_404(ApiKey, key_id)
    body = json_body({"name", "note", "enabled"})
    if "name" in body:
        key.name = text(body, "name", 120)
    if "note" in body:
        key.note = text(body, "note", 4000, False)
    if "enabled" in body:
        key.enabled = boolean(body["enabled"], "enabled")
    db.session.commit()
    return result(serialize_key(key))


@api.delete("/keys/<int:key_id>")
@api.delete("/api-keys/<int:key_id>")
def delete_key(key_id):
    key = get_or_404(ApiKey, key_id)
    if db.session.scalar(db.select(RequestLog.id).where(RequestLog.api_key_id == key_id).limit(1)):
        raise ApiProblem("Key has request history; disable it instead", 409, "RESOURCE_IN_USE")
    db.session.delete(key)
    db.session.commit()
    return "", 204


@api.post("/accounts/<int:account_id>/balance-sync")
def sync_balance(account_id):
    from .services import sync_balance as sync
    snapshots = sync(get_or_404(Account, account_id))
    return result({"items": [serialize_snapshot(row) for row in snapshots], "balance_source": "unknown"})


@api.post("/checkin/run")
def run_checkin():
    from .services import checkin
    try:
        account_id = int(request.args.get("account_id", ""))
    except ValueError:
        raise ApiProblem("account_id is required") from None
    record = checkin(get_or_404(Account, account_id), "manual")
    return result(serialize_checkin(record), 502 if record.status == "failed" else 200)


@api.get("/checkins")
def checkins():
    query = db.select(CheckinRecord).join(Account).where(Account.region == region_arg())
    if "status" in request.args:
        status = request.args["status"]
        if status not in ("pending", "success", "failed", "skipped"):
            raise ApiProblem("Invalid status")
        query = query.where(CheckinRecord.status == status)
    return page(query, CheckinRecord, serialize_checkin, {"id", "created_at", "updated_at", "day"})


@api.post("/checkin/jobs")
def create_job():
    from .jobs import enqueue, serialize_job
    body = json_body({"region", "account_ids"})
    job = enqueue(region_value(body.get("region")), validate_ids(body.get("account_ids")))
    return result(serialize_job(job), 202)


@api.get("/checkin/jobs")
def jobs():
    from .jobs import serialize_job
    return page(db.select(CheckinJob).where(CheckinJob.region == region_arg()), CheckinJob,
                serialize_job, {"id", "created_at"}, "created_at")


@api.get("/checkin/jobs/<job_id>")
def job_detail(job_id):
    from .jobs import serialize_job
    return result(serialize_job(get_or_404(CheckinJob, job_id)))


def serialize_log(log):
    return {"id": log.id, "account_id": log.account_id, "api_key_id": log.api_key_id,
            "region": log.region, "protocol": log.protocol, "endpoint": log.endpoint,
            "model": log.model, "http_status": log.http_status, "latency_ms": log.latency_ms,
            "status": "success" if 200 <= log.http_status < 300 else "error", "stream": log.stream,
            "input_tokens": log.input_tokens, "output_tokens": log.output_tokens,
            "credits": None, "ledger_id": None, "error_message": log.error_message,
            "headers": log.headers, "created_at": iso(log.created_at)}


@api.get("/logs")
def logs():
    query = db.select(RequestLog).where(RequestLog.region == region_arg())
    query = search(query, RequestLog.model, RequestLog.id)
    if "status" in request.args:
        status = request.args["status"]
        if status not in ("success", "error"):
            raise ApiProblem("Invalid status")
        query = query.where(RequestLog.http_status.between(200, 299) if status == "success" else RequestLog.http_status >= 300)
    if "protocol" in request.args:
        protocol = request.args["protocol"]
        if protocol not in ("anthropic", "openai_chat", "openai_responses"):
            raise ApiProblem("Invalid protocol")
        query = query.where(RequestLog.protocol == protocol)
    return page(query, RequestLog, serialize_log, {"id", "created_at", "latency_ms", "http_status"}, "created_at")


@api.get("/logs/<log_id>")
def log_detail(log_id):
    return result(serialize_log(get_or_404(RequestLog, log_id)))


@api.get("/credits")
def credits():
    query = db.select(CreditEntry).join(Account).where(Account.region == region_arg())

    def serialize(entry):
        return {"id": entry.id, "account_id": entry.account_id, "type": entry.kind,
                "delta": str(entry.delta), "balance_before": str(entry.balance_before),
                "balance_after": str(entry.balance_after), "certainty": "confirmed",
                "created_at": iso(entry.created_at)}

    return page(query, CreditEntry, serialize, {"id", "created_at"})


@api.get("/dashboard")
def dashboard():
    regions = []
    for region in ("cn", "global"):
        counts = dict(db.session.execute(db.select(Account.health, func.count()).where(
            Account.region == region).group_by(Account.health)).all())
        regions.append({"region": region, "total": sum(counts.values()), "health": counts, "balance": None})
    return result({"regions": regions, "total_accounts": sum(row["total"] for row in regions),
                   "total_balance": None, "credits_consumed_today": None,
                   "requests_today": db.session.scalar(db.select(func.count()).select_from(RequestLog).where(
                       RequestLog.created_at >= utcnow().replace(hour=0, minute=0, second=0, microsecond=0))),
                   "balance_source": "unknown"})


@api.get("/settings")
def settings():
    from .jobs import get_settings
    return result(get_settings())


@api.patch("/settings")
def update_settings():
    from .jobs import save_settings
    return result(save_settings(json_body({"checkin"})))


@api.get("/runtime")
def runtime():
    import platform
    return result({"version": "0.2.0", "python_version": platform.python_version(),
                   "started_at": current_app.extensions["started_at"],
                   "capabilities": current_app.extensions["capabilities"](),
                   "database": "operational" if db.session.scalar(db.select(1)) == 1 else "down",
                   "jobs": dict(Counter(db.session.scalars(db.select(CheckinJob.status)))),
                   "worker": "external; run flask worker", "upstream_health": "unknown"})
