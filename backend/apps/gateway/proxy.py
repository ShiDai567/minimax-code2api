"""Public gateway. Streams SSE without buffering the body. Admin auth does not apply."""
import hashlib
import json
import time
import uuid

from django.db.models import F
from django.urls import path
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

from adapters import adapter_for
from adapters.base import UpstreamError
from apps.accounts.models import Account
from apps.api_keys.models import ApiKey
from apps.request_logs.models import RequestLog
from apps.system_settings.services import get_settings, log_runtime
from common.utils import utcnow
from services.account_pool import acquire, release, select_account
from services.account_service import note_upstream_failure
from services.credit_service import reconcile_after_request
from services.gateway_service import anthropic_sse_to_openai, from_anthropic, to_anthropic
from services.model_router import observe, resolve

PROTOCOL_BY_PATH = {
    "/v1/messages": "anthropic",
    "/v1/messages/count_tokens": "anthropic",
    "/v1/chat/completions": "openai_chat",
    "/v1/responses": "openai_responses",
}


def _problem(detail, status, code):
    return JsonResponse({"detail": detail, "error": {"code": code, "type": code.lower()}}, status=status)


def _authenticate(request):
    header = request.headers.get("Authorization", "")
    secret = header[7:] if header.startswith("Bearer ") else request.headers.get("x-api-key", "")
    if not secret:
        return None
    digest = hashlib.sha256(secret.encode()).hexdigest()
    key = ApiKey.objects.filter(key_hash=digest, enabled=True).first()
    if key is None:
        return None
    if key.expires_at and key.expires_at <= utcnow():
        return None
    return key


def _region(request):
    region = request.headers.get("x-minimax-region", "cn")
    if region not in ("cn", "global"):
        raise ValueError("region")
    return region


def _safe_headers(request, forwarded):
    safe = {name: "[REDACTED]" for name in forwarded}
    if request.headers.get("Authorization"):
        safe["Authorization"] = "[REDACTED]"
    if request.headers.get("x-api-key"):
        safe["x-api-key"] = "[REDACTED]"
    return safe


def _write_log(**kwargs):
    RequestLog.objects.create(**kwargs)
    if kwargs.get("api_key_id"):
        ApiKey.objects.filter(id=kwargs["api_key_id"]).update(
            last_used_at=utcnow(), request_count=F("request_count") + 1
        )


@csrf_exempt
def gateway_entry(request, suffix=""):
    path = request.path.rstrip("/") or request.path
    if request.method == "GET" and path == "/v1/models":
        return models_view(request)
    if request.method != "POST" or path not in PROTOCOL_BY_PATH:
        return _problem("Not found", 404, "NOT_FOUND")
    return forward(request, path)


def models_view(request):
    key = _authenticate(request)
    if key is None:
        return _problem("API key required", 401, "UNAUTHORIZED")
    try:
        region = _region(request)
    except ValueError:
        return _problem("Invalid x-minimax-region", 400, "INVALID_INPUT")
    try:
        account = select_account(region)
        data = adapter_for(account).list_models(account)
    except UpstreamError as exc:
        return _problem(exc.message, exc.status_code, exc.code)
    except Exception as exc:
        from common.problems import ApiProblem

        if isinstance(exc, ApiProblem):
            return _problem(exc.detail, exc.status_code, exc.code)
        raise
    models = []
    for row in data:
        if isinstance(row, dict) and isinstance(row.get("id"), str) and 0 < len(row["id"]) <= 255:
            observe(region, row["id"])
            models.append({"id": row["id"], "object": "model", "owned_by": "minimax"})
    return JsonResponse({"object": "list", "data": models})


def forward(request, path):
    from common.problems import ApiProblem

    key = _authenticate(request)
    if key is None:
        return _problem("API key required", 401, "UNAUTHORIZED")
    config = get_settings()
    if not config["api"].get("gatewayEnabled", True):
        return _problem("Gateway is stopped", 503, "GATEWAY_STOPPED")
    protocol = PROTOCOL_BY_PATH[path]
    if not config["api"]["protocols"].get(protocol, True):
        return _problem("Protocol is disabled", 403, "PROTOCOL_DISABLED")
    try:
        body = json.loads(request.body or b"null")
    except ValueError:
        return _problem("A JSON object is required", 400, "INVALID_INPUT")
    if not isinstance(body, dict) or not isinstance(body.get("model"), str):
        return _problem("A JSON object with a model is required", 400, "INVALID_INPUT")
    if "stream" in body and type(body["stream"]) is not bool:
        return _problem("stream must be a boolean", 400, "INVALID_INPUT")
    try:
        region = _region(request)
        resolved = resolve(region, body["model"])
        upstream_body = to_anthropic({**body, "model": resolved}, protocol)
        account = select_account(region)
    except (ApiProblem, UpstreamError) as exc:
        status = getattr(exc, "status_code", 400)
        code = getattr(exc, "code", "INVALID_INPUT")
        detail = getattr(exc, "detail", None) or getattr(exc, "message", "Request failed")
        return _problem(detail, status, code)
    if path.endswith("count_tokens") and body.get("stream"):
        return _problem("count_tokens does not support streaming", 400, "INVALID_INPUT")

    forwarded = {}
    for header in ("anthropic-version", "anthropic-beta"):
        value = request.headers.get(header)
        if value and len(value) <= 512:
            forwarded[header] = value
    stream = bool(body.get("stream"))
    suffix = "messages/count_tokens" if path.endswith("count_tokens") else "messages"
    if stream and protocol != "anthropic":
        upstream_body["stream"] = True
    log_id = str(uuid.uuid4())
    started = time.monotonic()
    client_ip = request.META.get("REMOTE_ADDR", "")[:64]
    acquire(account.id)
    try:
        response, client = adapter_for(account).generate(account, upstream_body, forwarded, suffix)
    except UpstreamError as exc:
        release(account.id)
        if exc.code != "UPSTREAM_TIMEOUT":
            note_upstream_failure(account.id, exc.permanent)
        _write_log(
            id=log_id, account_id=account.id, api_key_id=key.id, region=region, protocol=protocol,
            endpoint=path, model=body["model"], resolved_model=resolved, http_status=exc.status_code,
            latency_ms=int((time.monotonic() - started) * 1000), stream=stream, error_message=exc.message[:255],
            headers=_safe_headers(request, forwarded), client_ip=client_ip,
        )
        return _problem(exc.message, exc.status_code, exc.code)

    status = response.status_code
    if status in (401, 403):
        note_upstream_failure(account.id, True)
    elif status >= 500:
        note_upstream_failure(account.id, False)

    def finish(http_status, error="", usage=None, credits=None, ledger_id=None):
        usage = usage if isinstance(usage, dict) else {}
        _write_log(
            id=log_id, account_id=account.id, api_key_id=key.id, region=region, protocol=protocol,
            endpoint=path, model=body["model"], resolved_model=resolved, http_status=http_status,
            latency_ms=int((time.monotonic() - started) * 1000), stream=stream,
            input_tokens=usage.get("input_tokens") if type(usage.get("input_tokens")) is int else None,
            output_tokens=usage.get("output_tokens") if type(usage.get("output_tokens")) is int else None,
            consumed_credits=credits, ledger_id=ledger_id, error_message=(error or "")[:255],
            headers=_safe_headers(request, forwarded), client_ip=client_ip,
        )
        Account.objects.filter(id=account.id).update(last_active_at=utcnow())

    if stream and 200 <= status < 300:
        content_type = response.headers.get("content-type", "text/event-stream")

        def generate():
            error = ""
            state = {}
            try:
                for chunk in response.iter_bytes():
                    if protocol == "anthropic":
                        yield chunk
                    else:
                        try:
                            for frame in anthropic_sse_to_openai(chunk, protocol, state):
                                yield frame
                        except ApiProblem as exc:
                            error = exc.detail
                            yield f"data: {json.dumps({'error': {'message': exc.detail}})}\n\n".encode()
                            break
            except Exception:
                error = "Stream interrupted"
            finally:
                response.close()
                client.close()
                release(account.id)
                entry = reconcile_after_request(account.id, log_id) if not error else None
                credits = abs(entry.delta) if entry and entry.delta < 0 else None
                finish(502 if error else status, error, credits=credits, ledger_id=entry.id if entry else None)
                if error:
                    log_runtime("error", f"{log_id} stream interrupted")

        streaming = StreamingHttpResponse(generate(), status=status, content_type=content_type)
        streaming["Cache-Control"] = "no-cache"
        streaming["X-Accel-Buffering"] = "no"
        return streaming

    try:
        raw = response.read()
    except Exception:
        response.close()
        client.close()
        release(account.id)
        finish(502, "Upstream response interrupted")
        return _problem("Upstream response interrupted", 502, "UPSTREAM_ERROR")
    response.close()
    client.close()
    release(account.id)
    if not 200 <= status < 300:
        finish(status, f"Upstream returned HTTP {status}")
        mapped = 504 if status == 504 else status if status >= 400 else 502
        return _problem(f"Upstream returned HTTP {status}", mapped, "UPSTREAM_ERROR")
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise TypeError
        if protocol == "anthropic":
            converted = parsed
        else:
            converted = from_anthropic(parsed, protocol)
    except (ValueError, TypeError, ApiProblem):
        finish(502, "Invalid or unsupported upstream response")
        return _problem("Invalid or unsupported upstream response", 502, "UPSTREAM_ERROR")
    model_name = parsed.get("model") if isinstance(parsed.get("model"), str) else resolved
    observe(region, model_name)
    entry = reconcile_after_request(account.id, log_id)
    credits = abs(entry.delta) if entry and entry.delta < 0 else None
    finish(status, usage=parsed.get("usage"), credits=credits, ledger_id=entry.id if entry else None)
    return JsonResponse(converted, status=status)


gateway_patterns = [
    path("v1/models", models_view),
    path("v1/models/", models_view),
    path("v1/messages", gateway_entry),
    path("v1/messages/", gateway_entry),
    path("v1/messages/count_tokens", gateway_entry),
    path("v1/messages/count_tokens/", gateway_entry),
    path("v1/chat/completions", gateway_entry),
    path("v1/chat/completions/", gateway_entry),
    path("v1/responses", gateway_entry),
    path("v1/responses/", gateway_entry),
]
