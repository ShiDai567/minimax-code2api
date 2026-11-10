"""Check-in. A pending row is never replayed: the upstream claim may already have landed."""
import uuid
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Q

from adapters import adapter_for
from adapters.base import UpstreamError
from apps.accounts.models import Account
from apps.checkin.models import CheckinJob, CheckinRecord, CheckinTask
from apps.system_settings.services import get_settings
from common.problems import ApiProblem
from common.utils import utcnow


def checkin(account, trigger, allow_retry=True):
    if not account.enabled:
        raise ApiProblem("Account is disabled")
    if not account.real_user_id:
        raise ApiProblem("real_user_id is required for check-in")
    today = utcnow().date()
    record = CheckinRecord.objects.filter(account=account, day=today).first()
    if record and record.status in ("success", "skipped"):
        return record
    if record and record.status == "pending":
        raise ApiProblem("A check-in is pending or its outcome is unknown", 409, "CHECKIN_PENDING")
    if record and record.status == "failed":
        if not allow_retry:
            return record
        updated = CheckinRecord.objects.filter(id=record.id, status="failed").update(
            status="pending", trigger=trigger, message="Checking upstream status", updated_at=utcnow()
        )
        if updated != 1:
            raise ApiProblem("A check-in is already running", 409, "CHECKIN_PENDING")
        record.refresh_from_db()
    if record is None:
        try:
            record = CheckinRecord.objects.create(
                account=account,
                region=account.region,
                day=today,
                status="pending",
                trigger=trigger,
                message="Checking upstream status",
            )
        except IntegrityError:
            raise ApiProblem("A check-in is already running", 409, "CHECKIN_PENDING") from None
    try:
        outcome = adapter_for(account).checkin(account)
        record.status = outcome.status
        record.reward = outcome.reward
        record.claim_id = outcome.claim_id
        record.arrival = "pending" if outcome.status == "success" else ""
        record.message = outcome.message[:255]
        if outcome.status == "success":
            account.last_checkin_at = utcnow()
            account.save(update_fields=["last_checkin_at", "updated_at"])
    except UpstreamError as exc:
        record.status = "failed"
        record.message = exc.message[:255]
        if exc.permanent:
            account.health = "expired"
            account.health_reason = exc.message[:255]
            account.save(update_fields=["health", "health_reason", "updated_at"])
    record.save()
    if record.status == "success":
        _try_confirm_arrival(account, record)
    return record


def _try_confirm_arrival(account, record):
    """A reported reward is not arrival. Confirm only when the synced delta matches, and do not post twice."""
    from apps.credits.models import CreditEntry
    from services.credit_service import sync_credits

    before = account.current_credits
    try:
        sync_credits(account)
    except ApiProblem:
        return
    account.refresh_from_db()
    if before is None or account.current_credits is None or record.reward is None:
        return
    if account.current_credits - before != record.reward:
        record.arrival = "unknown"
        record.save(update_fields=["arrival", "updated_at"])
        return
    entry = CreditEntry.objects.filter(account=account, kind="credit_sync").order_by("-id").first()
    record.arrival = "credited"
    record.ledger_id = entry.id if entry else None
    record.save(update_fields=["arrival", "ledger_id", "updated_at"])


def enqueue(region, account_ids, trigger="batch", schedule_key=None):
    if not isinstance(account_ids, list) or not 1 <= len(account_ids) <= 500:
        raise ApiProblem("account_ids must contain 1..500 integers")
    accounts = list(Account.objects.filter(id__in=account_ids, region=region))
    if len(accounts) != len(set(account_ids)):
        raise ApiProblem("All accounts must exist in the selected region")
    job = CheckinJob(id=str(uuid.uuid4()), region=region, trigger=trigger, schedule_key=schedule_key, total=len(accounts))
    try:
        with transaction.atomic():
            job.save()
            CheckinTask.objects.bulk_create([CheckinTask(job=job, account=account) for account in accounts])
    except IntegrityError:
        raise ApiProblem("A scheduled check-in for this day already exists", 409, "CONFLICT") from None
    return job


def run_one():
    now = utcnow()
    job = (
        CheckinJob.objects.filter(Q(status="queued") | Q(status="running", lease_until__lt=now))
        .order_by("created_at")
        .first()
    )
    if job is None:
        return False
    token = str(uuid.uuid4())
    claimed = CheckinJob.objects.filter(id=job.id).filter(Q(status="queued") | Q(status="running", lease_until__lt=now)).update(
        status="running", lease_token=token, lease_until=now + timedelta(minutes=5)
    )
    if claimed != 1:
        return True
    settings_value = get_settings()
    retries = settings_value["checkin"]["maxRetries"] if settings_value["checkin"]["retryOnFailure"] else 0
    tasks = list(CheckinTask.objects.filter(job_id=job.id, status="queued").select_related("account").order_by("id"))
    for task in tasks:
        renewed = CheckinJob.objects.filter(id=job.id, lease_token=token).update(lease_until=utcnow() + timedelta(minutes=5))
        if renewed != 1:
            return True
        try:
            record = checkin(task.account, job.trigger, allow_retry=True)
            status, message = record.status, record.message
        except ApiProblem as exc:
            status, message = "failed", exc.detail[:255]
        if status == "failed" and task.attempts < retries:
            CheckinTask.objects.filter(id=task.id).update(attempts=task.attempts + 1, message=message)
            continue
        updated = CheckinTask.objects.filter(id=task.id, job__lease_token=token).update(status=status, message=message)
        if updated != 1:
            return True
    _finish(job.id, token)
    return True


def _finish(job_id, token):
    tasks = CheckinTask.objects.filter(job_id=job_id)
    if tasks.filter(status="queued").exists():
        return
    counts = {"success": 0, "failed": 0, "skipped": 0}
    for status in counts:
        counts[status] = tasks.filter(status=status).count()
    CheckinJob.objects.filter(id=job_id, lease_token=token).update(
        status="completed",
        finished_at=utcnow(),
        lease_until=None,
        success_count=counts["success"],
        failure_count=counts["failed"],
        skipped_count=counts["skipped"],
    )


def schedule_due(now=None):
    from zoneinfo import ZoneInfo

    now = now or utcnow()
    config = get_settings()["checkin"]
    if not config["auto"] or not config["regions"]:
        return
    local = now.astimezone(ZoneInfo(config["timezone"]))
    if local.strftime("%H:%M") < config["time"]:
        return
    for region in config["regions"]:
        key = f"{config['timezone']}:{local.date().isoformat()}:{region}"
        if CheckinJob.objects.filter(schedule_key=key).exists():
            continue
        ids = list(Account.objects.filter(region=region, enabled=True).values_list("id", flat=True))
        if not ids:
            continue
        try:
            enqueue(region, ids, "schedule", key)
        except ApiProblem:
            continue
