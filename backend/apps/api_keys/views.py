import hashlib
import secrets

from rest_framework.views import APIView

from apps.api_keys.models import ApiKey
from apps.request_logs.models import RequestLog
from common.pagination import envelope
from common.problems import ApiProblem
from common.utils import epoch_ms, text, utcnow


class KeyListView(APIView):
    def get(self, request):
        query = ApiKey.objects.order_by("-id")
        search = request.query_params.get("search", "").strip()
        if search:
            query = query.filter(name__icontains=search)
        items = [_key(row) for row in query[:200]]
        return envelope({"items": items, "total": query.count()})

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        secret = "sk-m2a-" + secrets.token_urlsafe(32)
        key = ApiKey.objects.create(
            name=text(body.get("name", ""), "name", 120),
            note=text(body.get("note", ""), "note", 4000, required=False),
            prefix=secret[:12],
            key_hash=hashlib.sha256(secret.encode()).hexdigest(),
        )
        return envelope({"key": _key(key), "secret": secret}, 201)


class KeyDetailView(APIView):
    def patch(self, request, key_id):
        key = _get(key_id)
        body = request.data if isinstance(request.data, dict) else {}
        if "name" in body:
            key.name = text(body.get("name", ""), "name", 120)
        if "note" in body:
            key.note = text(body.get("note", ""), "note", 4000, required=False)
        if "enabled" in body:
            if type(body["enabled"]) is not bool:
                raise ApiProblem("enabled must be a boolean")
            key.enabled = body["enabled"]
        key.save()
        return envelope(_key(key))

    def delete(self, request, key_id):
        key = _get(key_id)
        if RequestLog.objects.filter(api_key=key).exists():
            raise ApiProblem("Key has request history; disable it instead", 409, "RESOURCE_IN_USE")
        key.delete()
        return envelope({"deleted": True})


def _get(key_id):
    key = ApiKey.objects.filter(id=key_id).first()
    if key is None:
        raise ApiProblem("Resource not found", 404, "NOT_FOUND")
    return key


def _key(key):
    expired = bool(key.expires_at and key.expires_at <= utcnow())
    return {
        "id": str(key.id),
        "name": key.name,
        "masked": key.prefix + "••••••••",
        "enabled": key.enabled and not expired,
        "createdAt": epoch_ms(key.created_at),
        "lastUsedAt": epoch_ms(key.last_used_at),
        "requestCount": key.request_count,
        "note": key.note,
        "expiresAt": epoch_ms(key.expires_at),
    }
