from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.checkin.models import CheckinRecord
from apps.credits.models import CreditEntry
from common.utils import epoch_ms


def money(value):
    if value is None:
        return None
    number = Decimal(value)
    if number == number.to_integral() and abs(number) < 10**15:
        return int(number)
    return float(number)


def account_payload(account):
    today = timezone.now().date()
    record = CheckinRecord.objects.filter(account=account, day=today).first()
    earned = CreditEntry.objects.filter(account=account, created_at__date=today, delta__gt=0).aggregate(total=Sum("delta"))["total"]
    consumed = CreditEntry.objects.filter(account=account, created_at__date=today, delta__lt=0).aggregate(total=Sum("delta"))["total"]
    from apps.request_logs.models import RequestLog

    requests = RequestLog.objects.filter(account=account, created_at__date=today).count()
    checkin_state = "not_run"
    if record:
        checkin_state = {"success": "success", "failed": "failed", "pending": "pending", "skipped": "success"}.get(record.status, "not_run")
    health = account.health if account.health in ("healthy", "error", "expired") else "error"
    return {
        "id": str(account.id),
        "region": account.region,
        "name": account.name,
        "identifier": account.identifier,
        "health": health,
        "healthReason": account.health_reason or ("尚未用上游验证" if account.health == "unknown" else None),
        "enabled": account.enabled,
        "status": "disabled" if not account.enabled else health,
        "credentialMasked": "lease ••••",
        "groupId": str(account.group_id) if account.group_id else None,
        "balance": money(account.current_credits),
        "balanceSyncedAt": epoch_ms(account.credits_synced_at),
        "createdAt": epoch_ms(account.created_at),
        "lastCheckinAt": epoch_ms(account.last_checkin_at),
        "lastActiveAt": epoch_ms(account.last_active_at),
        "note": account.note,
        "realUserId": account.real_user_id,
        "verifiedAt": epoch_ms(account.verified_at),
        "today": {
            "checkin": checkin_state,
            "earned": money(earned) or 0,
            "consumed": abs(money(consumed) or 0),
            "requests": requests,
        },
    }
