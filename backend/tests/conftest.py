import json

import httpx
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Account
from common.encryption import encrypt, reset_cipher


TOKEN = "a" * 32


@pytest.fixture(autouse=True)
def _fresh_cipher():
    reset_cipher()
    yield
    reset_cipher()


@pytest.fixture
def client():
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {TOKEN}")
    return api


@pytest.fixture
def account(db):
    return Account.objects.create(
        region="cn",
        name="测试账号",
        identifier="tester@example.com",
        credential_encrypted=encrypt("upstream-token"),
        real_user_id="42",
        health="healthy",
    )


def panel(today_status=2, claimable=True):
    days = []
    for number in range(1, 8):
        days.append({
            "day_no": number,
            "points": 10,
            "is_today": number == 1,
            "status": today_status if number == 1 else (2 if claimable else 1),
        })
    return {"scene": 1, "days": days}


@pytest.fixture
def transport(settings):
    """Route every upstream call through one handler the test can replace."""
    holder = {"handler": lambda request: httpx.Response(404, json={"detail": "unhandled"})}

    def dispatch(request: httpx.Request) -> httpx.Response:
        return holder["handler"](request)

    settings.HTTP_TRANSPORT = httpx.MockTransport(dispatch)
    return holder


def json_response(body, status=200):
    return httpx.Response(status, json=body)


def sse(events):
    body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})
