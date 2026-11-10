from datetime import timedelta

from django.db.models import Q, Sum
from django.db.models.functions import TruncDate, TruncHour
from django.utils import timezone
from rest_framework.views import APIView

from apps.accounts.models import Account
from apps.checkin.models import CheckinJob, CheckinRecord
from apps.credits.models import CreditEntry
from apps.request_logs.models import RequestLog
from apps.system_settings.models import AuditLog
from common.pagination import envelope
from common.utils import epoch_ms
from apps.gateway.views import _status


class DashboardView(APIView):
    def get(self, request):
        span = request.query_params.get("range", "24h")
        if span not in ("24h", "7d", "30d"):
            span = "24h"
        now = timezone.now()
        start = now - timedelta(hours=24 if span == "24h" else 24 * (7 if span == "7d" else 30))
        previous_start = start - (now - start)
        return envelope({
            "metrics": _metrics(now, start, previous_start),
            "regions": [_region(region, start) for region in ("cn", "global")],
            "gateway": _gateway(),
            "activity": _activity(),
            "trend": _trend(span, start),
        })


def _metric(current, previous):
    return {"value": current, "previous": previous}


def _metrics(now, start, previous_start):
    today = now.date()
    accounts = Account.objects.count()
    healthy = Account.objects.filter(enabled=True, health="healthy").count()
    confirmed = Account.objects.filter(current_credits__isnull=False)
    balance = confirmed.aggregate(total=Sum("current_credits"))["total"]
    checkins = CheckinRecord.objects.filter(day=today, status="success").count()
    requests = RequestLog.objects.filter(created_at__date=today).count()
    consumed = CreditEntry.objects.filter(created_at__date=today, kind="api_usage").aggregate(total=Sum("delta"))["total"]
    return {
        "totalAccounts": _metric(accounts, None),
        "healthyAccounts": _metric(healthy, None),
        "totalBalance": _metric(float(balance) if balance is not None else None, None),
        "checkinsToday": _metric(checkins, CheckinRecord.objects.filter(day=today - timedelta(days=1), status="success").count()),
        "requestsToday": _metric(requests, RequestLog.objects.filter(created_at__date=today - timedelta(days=1)).count()),
        "creditsConsumedToday": _metric(abs(float(consumed)) if consumed is not None else None, None),
    }


def _region(region, start):
    rows = Account.objects.filter(region=region)
    today = timezone.now().date()
    balance = rows.filter(current_credits__isnull=False).aggregate(total=Sum("current_credits"))["total"]
    points = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        consumed = CreditEntry.objects.filter(region=region, kind="api_usage", created_at__date=day).aggregate(total=Sum("delta"))["total"]
        points.append({"label": day.isoformat()[5:], "value": abs(float(consumed or 0))})
    return {
        "region": region,
        "total": rows.count(),
        "online": rows.filter(enabled=True, health="healthy").count(),
        "abnormal": rows.exclude(health="healthy").exclude(health="unknown").count(),
        "disabled": rows.filter(enabled=False).count(),
        "checkedIn": CheckinRecord.objects.filter(region=region, day=today, status="success").count(),
        "awaitingCheckin": rows.filter(enabled=True).exclude(id__in=CheckinRecord.objects.filter(day=today).values("account_id")).count(),
        "balance": float(balance) if balance is not None else 0,
        "balanceKnown": balance is not None,
        "unsyncedBalances": rows.filter(current_credits__isnull=True).count(),
        "consumption7d": points,
    }


def _gateway():
    status = _status()
    return {key: status[key] for key in ("state", "totalRequests", "successRate", "avgLatencyMs", "inflight", "errors24h", "startedAt")}


def _activity():
    events = []
    for row in CheckinRecord.objects.order_by("-id")[:8]:
        events.append({
            "id": f"checkin-{row.id}",
            "at": epoch_ms(row.updated_at),
            "kind": "checkin_success" if row.status == "success" else "checkin_failed",
            "accountId": str(row.account_id),
            "region": row.region,
            "title": "签到成功" if row.status == "success" else "签到未完成",
            "detail": row.message,
            "read": False,
        })
    for row in RequestLog.objects.order_by("-created_at")[:8]:
        events.append({
            "id": row.id,
            "at": epoch_ms(row.created_at),
            "kind": "request_success" if row.http_status < 400 else "request_failed",
            "accountId": str(row.account_id) if row.account_id else None,
            "region": row.region,
            "title": "API 请求成功" if row.http_status < 400 else "API 请求失败",
            "detail": f"{row.protocol} · {row.model} · {row.http_status}",
            "read": False,
        })
    events.sort(key=lambda item: item["at"] or 0, reverse=True)
    return events[:12]


def _trend(span, start):
    trunc = TruncHour if span == "24h" else TruncDate
    rows = (
        CreditEntry.objects.filter(created_at__gte=start)
        .annotate(bucket=trunc("created_at"))
        .values("bucket")
        .annotate(earned=Sum("delta", filter=Q(delta__gt=0)), consumed=Sum("delta", filter=Q(delta__lt=0)))
        .order_by("bucket")
    )
    return [
        {
            "t": epoch_ms(row["bucket"]),
            "label": row["bucket"].isoformat() if row["bucket"] else "",
            "earned": float(row["earned"] or 0),
            "consumed": abs(float(row["consumed"] or 0)),
        }
        for row in rows
    ]


class CapabilitiesView(APIView):
    authentication_required = False

    def get(self, request):
        from django.conf import settings

        return envelope({
            "serviceControl": True,
            "protocolToggle": True,
            "modelToggle": True,
            "checkin": True,
            "credits": bool(settings.BALANCE_ADAPTERS),
            "multiAccount": True,
            "runtimeLogs": True,
            "modelDiscovery": bool(settings.MODEL_DISCOVERY_URLS),
            "tokenRefresh": False,
        })


class HealthView(APIView):
    authentication_required = False

    def get(self, request):
        from django.db import connection

        try:
            connection.ensure_connection()
            database = "ok"
        except Exception:
            database = "down"
        return envelope({"status": "ok" if database == "ok" else "degraded", "version": "1.0.0", "database": database})
