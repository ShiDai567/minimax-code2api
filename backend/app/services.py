
import httpx
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from . import db
from .http import ApiProblem
from .models import BalanceSnapshot, CheckinRecord, utcnow
from .providers import provider_for


def sync_balance(account):
    if not account.enabled:
        raise ApiProblem("Account is disabled")
    snapshots = [BalanceSnapshot(account_id=account.id, **row) for row in provider_for(account).balances()]
    db.session.add_all(snapshots)
    db.session.commit()
    return snapshots


def checkin(account, trigger):
    if not account.enabled:
        raise ApiProblem("Account is disabled")
    if not account.real_user_id:
        raise ApiProblem("real_user_id is required for check-in")
    today = utcnow().date()
    record = db.session.scalar(db.select(CheckinRecord).where(CheckinRecord.account_id == account.id,
                                                              CheckinRecord.day == today))
    if record:
        if record.status in ("success", "skipped"):
            return record
        # A pending result may have reached the provider even after a crash. Do not repeat automatically.
        if record.status == "pending":
            raise ApiProblem("A check-in is pending or its outcome is unknown", 409, "CHECKIN_PENDING")
        updated = db.session.execute(update(CheckinRecord).where(CheckinRecord.id == record.id,
            CheckinRecord.status == "failed").values(status="pending", updated_at=utcnow(), trigger=trigger,
                                                      message="Checking upstream status"))
        if updated.rowcount != 1:
            db.session.rollback()
            raise ApiProblem("A check-in is already running", 409, "CHECKIN_PENDING")
    else:
        record = CheckinRecord(account_id=account.id, day=today, status="pending", trigger=trigger,
                               message="Checking upstream status")
        db.session.add(record)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise ApiProblem("A check-in is already running", 409, "CHECKIN_PENDING") from None
    try:
        outcome = provider_for(account).checkin()
        record.status = outcome["status"]
        record.reward = outcome.get("reward")
        record.claim_id = outcome.get("claim_id")
        record.arrival = "pending" if record.status == "success" else None
        record.message = outcome["message"]
    except ApiProblem as exc:
        # A failed/invalid response may follow a successful claim; retries always query status first.
        record.status, record.message = "failed", exc.detail[:255]
    except httpx.HTTPError:
        record.status, record.message = "failed", "Upstream connection failed"
    record.updated_at = utcnow()
    db.session.commit()
    return record
