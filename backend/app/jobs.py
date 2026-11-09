import re
import uuid
from collections import Counter
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import click
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError

from . import db
from .http import ApiProblem, boolean, iso
from .models import Account, CheckinJob, CheckinTask, Setting, utcnow
from .services import checkin

DEFAULT_SETTINGS = {"checkin": {"auto": False, "time": "09:00", "timezone": "UTC", "regions": []}}


def get_settings():
    row = db.session.get(Setting, 1)
    return row.value if row else DEFAULT_SETTINGS


def save_settings(body):
    value = body.get("checkin")
    if not isinstance(value, dict) or set(value) != {"auto", "time", "timezone", "regions"}:
        raise ApiProblem("checkin requires auto, time, timezone and regions")
    boolean(value["auto"], "auto")
    if not isinstance(value["time"], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value["time"]):
        raise ApiProblem("Invalid check-in time")
    try:
        ZoneInfo(value["timezone"])
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise ApiProblem("Invalid timezone") from None
    regions = value["regions"]
    if not isinstance(regions, list) or any(not isinstance(r, str) or r not in ("cn", "global") for r in regions) or len(set(regions)) != len(regions):
        raise ApiProblem("Invalid regions")
    if value["auto"] and not regions:
        raise ApiProblem("Select at least one region")
    row = db.session.get(Setting, 1)
    if row is None:
        row = Setting(id=1, value={"checkin": value})
        db.session.add(row)
    else:
        row.value = {"checkin": value}
    db.session.commit()
    return row.value


def enqueue(region, ids, trigger="batch", schedule_key=None):
    accounts = list(db.session.scalars(db.select(Account).where(Account.id.in_(ids), Account.region == region)))
    if len(accounts) != len(ids):
        raise ApiProblem("All accounts must exist in the selected region")
    job = CheckinJob(id=str(uuid.uuid4()), region=region, trigger=trigger, schedule_key=schedule_key)
    db.session.add(job)
    db.session.flush()
    db.session.add_all([CheckinTask(job_id=job.id, account_id=account.id) for account in accounts])
    db.session.commit()
    return job


def serialize_job(job):
    tasks = list(db.session.scalars(db.select(CheckinTask).where(CheckinTask.job_id == job.id).order_by(CheckinTask.id)))
    counts = Counter(task.status for task in tasks)
    return {"id": job.id, "region": job.region, "status": job.status, "trigger": job.trigger,
            "total": len(tasks), "completed": sum(counts[k] for k in ("success", "failed", "skipped")),
            "success": counts["success"], "failed": counts["failed"], "skipped": counts["skipped"],
            "created_at": iso(job.created_at), "finished_at": iso(job.finished_at),
            "tasks": [{"account_id": t.account_id, "status": t.status, "message": t.message} for t in tasks]}


def schedule_due(now=None):
    now = now or utcnow()
    settings = get_settings()["checkin"]
    if not settings["auto"]:
        return
    local = now.astimezone(ZoneInfo(settings["timezone"]))
    if local.strftime("%H:%M") < settings["time"]:
        return
    for region in settings["regions"]:
        key = f"{settings['timezone']}:{local.date()}:{region}"
        if db.session.scalar(db.select(CheckinJob.id).where(CheckinJob.schedule_key == key)):
            continue
        ids = list(db.session.scalars(db.select(Account.id).where(Account.region == region, Account.enabled.is_(True))))
        if not ids:
            continue
        try:
            enqueue(region, ids, "schedule", key)
        except IntegrityError:
            db.session.rollback()


def run_one():
    now = utcnow()
    job_id = db.session.scalar(db.select(CheckinJob.id).where(or_(CheckinJob.status == "queued",
        db.and_(CheckinJob.status == "running", CheckinJob.lease_until < now))).order_by(CheckinJob.created_at).limit(1))
    if not job_id:
        return False
    token = str(uuid.uuid4())
    claimed = db.session.execute(update(CheckinJob).where(CheckinJob.id == job_id, or_(CheckinJob.status == "queued",
        db.and_(CheckinJob.status == "running", CheckinJob.lease_until < now))).values(
            status="running", lease_token=token, lease_until=now + timedelta(minutes=5)))
    db.session.commit()
    if claimed.rowcount != 1:
        return True
    job = db.session.get(CheckinJob, job_id)
    tasks = list(db.session.scalars(db.select(CheckinTask).where(CheckinTask.job_id == job_id,
                                                                 CheckinTask.status == "queued").order_by(CheckinTask.id)))
    for task in tasks:
        # Refresh the lease before every network operation.
        renewed = db.session.execute(update(CheckinJob).where(CheckinJob.id == job_id,
            CheckinJob.lease_token == token).values(lease_until=utcnow() + timedelta(minutes=5)))
        db.session.commit()
        if renewed.rowcount != 1:
            return True
        try:
            record = checkin(db.session.get(Account, task.account_id), job.trigger)
            status, message = record.status, record.message
        except ApiProblem as exc:
            status, message = "failed", exc.detail[:255]
        # A slow upstream call can outlive the lease; only the current owner
        # may publish a task result after another worker has reclaimed it.
        updated = db.session.execute(update(CheckinTask).where(
            CheckinTask.id == task.id,
            db.exists(db.select(CheckinJob.id).where(CheckinJob.id == job_id,
                                                      CheckinJob.lease_token == token)),
        ).values(status=status, message=message))
        db.session.commit()
        if updated.rowcount != 1:
            return True
    finished = db.session.execute(update(CheckinJob).where(CheckinJob.id == job_id, CheckinJob.lease_token == token)
                                  .values(status="completed", finished_at=utcnow(), lease_until=None))
    db.session.commit()
    return bool(finished.rowcount)


def register_worker(app):
    @app.cli.command("worker")
    @click.option("--once", is_flag=True, help="Process one job and exit.")
    @click.option("--interval", type=click.IntRange(1, 3600), default=10)
    def worker(once, interval):
        """Run the external check-in scheduler and worker."""
        import time
        while True:
            try:
                schedule_due()
                processed = run_one()
            except Exception:
                db.session.rollback()
                app.logger.exception("Check-in worker failed")
                if once:
                    raise
                processed = False
            if once:
                break
            if not processed:
                time.sleep(interval)
