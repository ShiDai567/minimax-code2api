from datetime import timedelta

from django.conf import settings as django_settings
from django.db.models import Avg, Count, Max, Q
from django.utils import timezone
from rest_framework.views import APIView

from apps.request_logs.models import RequestLog
from apps.system_settings.models import RuntimeLog
from apps.system_settings.services import get_settings, log_runtime, save_settings
from common.pagination import envelope
from common.utils import epoch_ms


class GatewayStatusView(APIView):
    def get(self, request):
        return envelope(_status())


class GatewayStartView(APIView):
    def post(self, request):
        _set_enabled(True)
        log_runtime("info", "Gateway enabled")
        return envelope(_status())


class GatewayStopView(APIView):
    def post(self, request):
        _set_enabled(False)
        log_runtime("warn", "Gateway disabled")
        return envelope(_status())


class GatewayRestartView(APIView):
    def post(self, request):
        _set_enabled(True)
        log_runtime("info", "Gateway restart requested; process keeps running, new requests are accepted")
        return envelope(_status())


class RuntimeLogView(APIView):
    def get(self, request):
        rows = RuntimeLog.objects.order_by("-id")[:200]
        return envelope({
            "items": [
                {"id": str(row.id), "at": epoch_ms(row.created_at), "level": row.level, "message": row.message}
                for row in rows
            ]
        })


def _set_enabled(enabled):
    current = get_settings()
    current["api"]["gatewayEnabled"] = enabled
    save_settings({"api": {"gatewayEnabled": enabled}})


def _status():
    config = get_settings()
    since = timezone.now() - timedelta(hours=24)
    logs = RequestLog.objects.all()
    day = logs.filter(created_at__gte=since)
    total = logs.count()
    success = logs.filter(http_status__gte=200, http_status__lt=300).count()
    protocols = []
    catalog = [
        ("anthropic", "Anthropic Messages API", "/v1/messages"),
        ("openai_chat", "OpenAI Chat Completions", "/v1/chat/completions"),
        ("openai_responses", "OpenAI Responses", "/v1/responses"),
    ]
    for key, name, endpoint in catalog:
        subset = logs.filter(protocol=key)
        last = subset.aggregate(last=Max("created_at"))["last"]
        protocols.append({
            "protocol": key,
            "name": name,
            "method": "POST",
            "endpoint": endpoint,
            "enabled": config["api"]["protocols"].get(key, True) and config["api"]["gatewayEnabled"],
            "requests": subset.count(),
            "lastCalledAt": epoch_ms(last),
        })
    started = config["runtime"].get("startedAt")
    started_ms = None
    if isinstance(started, str):
        from datetime import datetime

        try:
            started_ms = epoch_ms(datetime.fromisoformat(started))
        except ValueError:
            started_ms = None
    return {
        "state": "running" if config["api"]["gatewayEnabled"] else "stopped",
        "host": django_settings.GATEWAY_HOST,
        "port": django_settings.GATEWAY_PORT,
        "startedAt": started_ms,
        "inflight": 0,
        "totalRequests": total,
        "successRate": round(success / total * 100, 1) if total else None,
        "avgLatencyMs": round(day.aggregate(value=Avg("latency_ms"))["value"] or 0) if day.exists() else None,
        "errors24h": day.filter(http_status__gte=400).count(),
        "version": "1.0.0",
        "protocols": protocols,
        "auxEndpoints": [
            {"method": "POST", "path": "/v1/messages/count_tokens", "description": "Anthropic token 计数透传"},
            {"method": "GET", "path": "/v1/models", "description": "仅在配置了已核实的模型发现 URL 时可用"},
            {"method": "GET", "path": "/health", "description": "健康检查"},
        ],
    }
