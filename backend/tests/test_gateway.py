import json

import httpx
import pytest

from apps.accounts.models import Account
from apps.api_keys.models import ApiKey
from apps.request_logs.models import RequestLog
from common.encryption import encrypt
from tests.conftest import json_response, sse


SECRET = "sk-m2a-testsecret"


@pytest.fixture
def gateway(db, client):
    import hashlib

    ApiKey.objects.create(name="k", prefix=SECRET[:12], key_hash=hashlib.sha256(SECRET.encode()).hexdigest())
    Account.objects.create(
        region="cn", name="c", identifier="c@example.com",
        credential_encrypted=encrypt("upstream-token"), health="healthy",
    )
    return client


def call(path, body, headers=None, method="post"):
    from django.test import Client

    raw = Client()
    return getattr(raw, method)(
        path,
        data=json.dumps(body) if body is not None else None,
        content_type="application/json",
        headers=headers or {},
    )


def authed(path, body, extra=None):
    headers = {"Authorization": f"Bearer {SECRET}", **(extra or {})}
    return call(path, body, headers)


@pytest.mark.django_db
def test_missing_key_is_401_and_admin_token_is_not_an_api_key(gateway):
    assert call("/v1/messages", {"model": "m"}).status_code == 401
    admin = call("/v1/messages", {"model": "m"}, {"Authorization": "Bearer " + "a" * 32})
    assert admin.status_code == 401


@pytest.mark.django_db
def test_no_healthy_account_is_503(db):
    import hashlib

    ApiKey.objects.create(name="k", prefix="x", key_hash=hashlib.sha256(SECRET.encode()).hexdigest())
    response = authed("/v1/messages", {"model": "m", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "NO_ACCOUNT"


@pytest.mark.django_db
def test_anthropic_passthrough_and_log(gateway, transport):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return json_response({"id": "msg_1", "model": "m", "content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 3, "output_tokens": 1}})

    transport["handler"] = handler
    response = authed("/v1/messages", {"model": "m", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 8})
    assert response.status_code == 200
    assert response.json()["content"][0]["text"] == "ok"
    assert seen["url"].startswith("https://agent.minimax.cn/mavis/api/v1/llm/v1/messages")
    assert seen["auth"] == "Bearer upstream-token"
    log = RequestLog.objects.get()
    assert log.protocol == "anthropic" and log.http_status == 200
    assert log.headers["Authorization"] == "[REDACTED]"
    assert SECRET not in str(log.headers)


@pytest.mark.django_db
def test_openai_chat_conversion_and_unsupported_field(gateway, transport):
    transport["handler"] = lambda request: json_response({
        "id": "msg_1", "model": "m", "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "hello"}],
        "usage": {"input_tokens": 2, "output_tokens": 1},
    })
    response = authed("/v1/chat/completions", {"model": "m", "messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "hello"
    assert body["usage"]["total_tokens"] == 3

    rejected = authed("/v1/chat/completions", {"model": "m", "messages": [{"role": "user", "content": "hi"}], "tools": []})
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "UNSUPPORTED"


@pytest.mark.django_db
def test_openai_streaming_conversion(gateway, transport):
    transport["handler"] = lambda request: sse([
        ("message_start", {"message": {"id": "msg_1", "model": "m"}}),
        ("content_block_delta", {"delta": {"text": "hi"}}),
        ("message_delta", {"delta": {"stop_reason": "end_turn"}}),
    ])
    response = authed("/v1/chat/completions", {"model": "m", "messages": [{"role": "user", "content": "hi"}], "stream": True})
    assert response.status_code == 200
    text = b"".join(response.streaming_content).decode()
    assert "chat.completion.chunk" in text
    assert '"content": "hi"' in text
    assert "data: [DONE]" in text
    assert RequestLog.objects.get().stream is True


@pytest.mark.django_db
def test_stopped_gateway_refuses_requests(gateway, client):
    assert client.post("/api/v1/gateway/stop").status_code == 200
    response = authed("/v1/messages", {"model": "m"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "GATEWAY_STOPPED"


@pytest.mark.django_db
def test_api_key_cannot_reach_the_admin_api(db):
    import hashlib

    ApiKey.objects.create(name="k", prefix="x", key_hash=hashlib.sha256(SECRET.encode()).hexdigest())
    from django.test import Client

    response = Client().get("/api/v1/accounts?region=cn", headers={"Authorization": f"Bearer {SECRET}"})
    assert response.status_code == 403
