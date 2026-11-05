import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from flask import Blueprint, abort
from sqlalchemy import select

from app.core.config import get_settings
from app.core.http import db_session, require_admin
from app.core.security import decrypt_secret
from app.models import Account, CheckinRecord, CreditLedger
from app.providers import balance, checkin

operations_bp = Blueprint("operations", __name__, url_prefix="/api/v1")
APP_VERSION = "0.1.0"


@operations_bp.post("/checkin/run")
@require_admin
async def run_checkin():
    from flask import request
    db = db_session()
    account_id = request.args.get("account_id", type=int)
    if account_id is None:
        abort(422, description="account_id is required")
    row = db.get(Account, account_id)
    if not row:
        abort(404, description="Account not found")
    if not row.enabled:
        abort(409, description="Account is disabled")
    if not row.real_user_id:
        abort(422, description="Account real_user_id is required for MiniMax Code check-in")
    business_date = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    existing = db.scalar(select(CheckinRecord).where(CheckinRecord.account_id == row.id,
                                                      CheckinRecord.business_date == business_date))
    if existing and existing.status in {"success", "pending"}:
        return {"accountId": str(row.id), "status": "skipped", "message": "Already attempted for business date",
                "arrival": existing.arrival}
    record = existing or CheckinRecord(account_id=row.id, region=row.region, business_date=business_date,
                                       status="pending", arrival="unknown")
    record.status = "pending"
    db.add(record)
    try:
        db.commit()
    except Exception:
        db.rollback()
        abort(409, description="Check-in already in progress or recorded")
    try:
        result = await checkin(row.region, decrypt_secret(row.credential_ciphertext), row.real_user_id, APP_VERSION)
        record.status = "success" if result["status"] in {"claimed", "already_claimed"} else "failed"
        record.reward = result.get("reward")
        record.arrival = "pending" if record.reward is not None else "unknown"
        if result["status"] == "claimed" and isinstance(record.reward, (int, float)):
            db.add(CreditLedger(account_id=row.id, region=row.region, kind="checkin_reward", delta=record.reward,
                                balance_before=None, balance_after=None, certainty="reported",
                                note="Upstream check-in claim reward; balance not reconciled"))
        if record.status == "success":
            row.last_checkin_at = datetime.now(timezone.utc)
        record.failure_reason = None if record.status == "success" else "Upstream says check-in is not claimable"
        db.commit()
        return {"accountId": str(row.id), "status": record.status, "reward": record.reward,
                "arrival": record.arrival, "message": record.failure_reason or result["status"]}
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        record.status, record.failure_reason = "failed", str(exc)[:1000]
        row.health_reason = record.failure_reason
        db.commit()
        abort(502, description="Upstream check-in failed; see the account error detail")


@operations_bp.post("/accounts/<int:account_id>/balance-sync")
@require_admin
async def sync_balance(account_id):
    db = db_session()
    row = db.get(Account, account_id)
    if not row:
        abort(404, description="Account not found")
    try:
        result = await balance(row.region, decrypt_secret(row.credential_ciphertext))
    except (httpx.HTTPError, RuntimeError):
        abort(502, description="Upstream balance query failed")
    summary = result.get("op_credit_summary") or result.get("data", {}).get("op_credit_summary")
    amount = summary.get("total_remaining_amount") if isinstance(summary, dict) else result.get("opcredit_balance")
    if amount is None:
        abort(502, description="Upstream response did not contain a verifiable credit balance")
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        abort(502, description="Upstream credit balance was not numeric")
    before = row.balance
    row.balance = amount
    row.balance_synced_at = datetime.now(timezone.utc)
    db.add(CreditLedger(account_id=row.id, region=row.region, kind="balance_reconciliation", delta=0,
                        balance_before=before, balance_after=amount, certainty="confirmed",
                        note="Upstream Token Plan balance snapshot; delta is not a usage charge"))
    db.commit()
    return {"accountId": str(row.id), "region": row.region, "balance": amount,
            "syncedAt": row.balance_synced_at, "source": "real"}
