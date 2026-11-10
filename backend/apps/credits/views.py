import csv

from django.db.models import Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.views import APIView

from apps.accounts.models import Account
from apps.credits.models import CreditEntry
from common.pagination import envelope
from common.utils import epoch_ms, region_required


class CreditListView(APIView):
    def get(self, request):
        query = _query(request)
        kind = request.query_params.get("type")
        if kind in ("checkin", "api_usage", "adjustment", "credit_sync"):
            query = query.filter(kind=kind)
        total = query.count()
        items = [_entry(row) for row in query.order_by("-id")[:200]]
        return envelope({"items": items, "total": total})


class CreditSummaryView(APIView):
    def get(self, request):
        query = _query(request)
        today = timezone.now().date()
        balance = Account.objects.filter(current_credits__isnull=False)
        region = request.query_params.get("region")
        if region:
            balance = balance.filter(region=region)
        return envelope({
            "totalBalance": _sum(balance, "current_credits"),
            "unconfirmedAccounts": Account.objects.filter(current_credits__isnull=True).count(),
            "earnedToday": _sum(query.filter(created_at__date=today, delta__gt=0), "delta"),
            "consumedToday": abs(_sum(query.filter(created_at__date=today, delta__lt=0), "delta")),
            "earnedAllTime": _sum(query.filter(delta__gt=0), "delta"),
            "consumedAllTime": abs(_sum(query.filter(delta__lt=0), "delta")),
            "certainty": "confirmed",
        })


class CreditExportView(APIView):
    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="credits.csv"'
        writer = csv.writer(response)
        writer.writerow(["id", "account_id", "region", "type", "delta", "balance_before", "balance_after", "note", "created_at"])
        for row in _query(request).order_by("-id")[:5000]:
            writer.writerow([row.id, row.account_id, row.region, row.kind, row.delta, row.balance_before, row.balance_after, row.note, row.created_at.isoformat()])
        return response


def _query(request):
    query = CreditEntry.objects.all()
    region = request.query_params.get("region")
    if region:
        query = query.filter(region=region_required(region))
    return query


def _sum(query, field):
    value = query.aggregate(total=Sum(field))["total"]
    return float(value) if value is not None else 0


def _entry(row):
    return {
        "id": str(row.id),
        "accountId": str(row.account_id),
        "region": row.region,
        "at": epoch_ms(row.created_at),
        "type": row.kind if row.kind != "credit_sync" else "adjustment",
        "kind": row.kind,
        "delta": float(row.delta),
        "balanceBefore": float(row.balance_before),
        "balanceAfter": float(row.balance_after),
        "requestId": row.request_id or None,
        "checkinId": str(row.checkin_id) if row.checkin_id else None,
        "note": row.note,
        "certainty": "confirmed",
    }
