from django.db.models import Count
from datetime import timedelta

from django.utils import timezone
from rest_framework.views import APIView

from adapters import adapter_for
from adapters.base import UpstreamError
from apps.models_manager.models import UpstreamModel
from apps.request_logs.models import RequestLog
from common.pagination import envelope
from common.problems import ApiProblem
from common.utils import epoch_ms, region_required
from services.account_pool import select_account
from services.model_router import observe


class ModelListView(APIView):
    def get(self, request):
        region = request.query_params.get("region")
        query = UpstreamModel.objects.order_by("region", "model_id")
        if region:
            query = query.filter(region=region_required(region))
        since = timezone.now() - timedelta(hours=24)
        items = []
        for row in query:
            items.append({
                "id": str(row.id),
                "modelId": row.model_id,
                "displayName": row.display_name,
                "regions": [row.region],
                "protocols": row.protocols,
                "enabled": row.enabled,
                "source": row.source,
                "lastUsedAt": epoch_ms(row.last_used_at),
                "requests24h": RequestLog.objects.filter(region=row.region, resolved_model=row.model_id, created_at__gte=since).count(),
            })
        return envelope({"items": items, "total": len(items), "note": "Only models discovered or observed from upstream. No catalog is hardcoded."})


class ModelDetailView(APIView):
    def patch(self, request, model_id):
        row = UpstreamModel.objects.filter(id=model_id).first()
        if row is None:
            raise ApiProblem("Resource not found", 404, "NOT_FOUND")
        enabled = (request.data or {}).get("enabled")
        if type(enabled) is not bool:
            raise ApiProblem("enabled must be a boolean")
        row.enabled = enabled
        row.save(update_fields=["enabled", "updated_at"])
        return envelope({"id": str(row.id), "enabled": row.enabled})


class ModelDiscoverView(APIView):
    def post(self, request):
        region = region_required((request.data or {}).get("region"))
        try:
            account = select_account(region)
            data = adapter_for(account).list_models(account)
        except UpstreamError as exc:
            raise ApiProblem(exc.message, exc.status_code, exc.code) from None
        found = 0
        for row in data:
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                observe(region, row["id"])
                UpstreamModel.objects.filter(region=region, model_id=row["id"]).update(source="discovery")
                found += 1
        return envelope({"discovered": found})
