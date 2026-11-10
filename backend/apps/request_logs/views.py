from rest_framework.views import APIView

from apps.request_logs.models import RequestLog
from common.pagination import envelope, page_params
from common.problems import ApiProblem
from common.utils import epoch_ms, region_required


class LogListView(APIView):
    def get(self, request):
        query = RequestLog.objects.all()
        region = request.query_params.get("region")
        if region:
            query = query.filter(region=region_required(region))
        search = request.query_params.get("search", "").strip()
        if search:
            query = query.filter(model__icontains=search) | query.filter(id__icontains=search)
            query = RequestLog.objects.filter(id__in=query.values("id"))
        status = request.query_params.get("status")
        if status == "success":
            query = query.filter(http_status__gte=200, http_status__lt=300)
        elif status == "error":
            query = query.filter(http_status__gte=400)
        protocol = request.query_params.get("protocol")
        if protocol:
            if protocol not in ("anthropic", "openai_chat", "openai_responses"):
                raise ApiProblem("Invalid protocol")
            query = query.filter(protocol=protocol)
        try:
            limit, offset, _sort, order = page_params(request, {"id", "created_at", "latency_ms", "http_status"}, "created_at")
        except ValueError as exc:
            raise ApiProblem(str(exc)) from None
        total = query.count()
        column = "-created_at" if order == "desc" else "created_at"
        items = [_log(row) for row in query.order_by(column)[offset : offset + limit]]
        return envelope({"items": items, "total": total})


class LogDetailView(APIView):
    def get(self, request, log_id):
        row = RequestLog.objects.filter(id=log_id).first()
        if row is None:
            raise ApiProblem("Resource not found", 404, "NOT_FOUND")
        return envelope(_log(row))


def _log(row):
    return {
        "id": row.id,
        "at": epoch_ms(row.created_at),
        "apiKeyId": str(row.api_key_id) if row.api_key_id else None,
        "protocol": row.protocol,
        "endpoint": row.endpoint,
        "model": row.model,
        "resolvedModel": row.resolved_model or row.model,
        "accountId": str(row.account_id) if row.account_id else None,
        "region": row.region,
        "status": "success" if 200 <= row.http_status < 300 else "error",
        "httpStatus": row.http_status,
        "latencyMs": row.latency_ms,
        "credits": float(row.consumed_credits) if row.consumed_credits is not None else None,
        "ledgerId": str(row.ledger_id) if row.ledger_id else None,
        "stream": row.stream,
        "inputTokens": row.input_tokens,
        "outputTokens": row.output_tokens,
        "errorMessage": row.error_message or None,
        "headers": row.headers,
        "clientIp": row.client_ip,
    }
