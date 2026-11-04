from urllib.parse import parse_qs, urlparse
import asyncio

import pytest

from app import providers


def test_mcode_signed_request_contains_region_identity_and_signatures():
    url, headers, body = providers._mcode_signed_request(
        "https://agent.minimaxi.com", "/minimax-cloud/api/v1/signin/status",
        "secret", "user-1", "1.2.3", "GET", now_ms=1_700_000_123_456,
    )

    query = parse_qs(urlparse(url).query)
    assert query["user_id"] == ["user-1"]
    assert query["desktop_version"] == ["1.2.3"]
    assert query["sys_language"] == ["zh"]
    assert headers["Authorization"] == "Bearer secret"
    assert len(headers["yy"]) == 32
    assert len(headers["x-signature"]) == 32
    assert headers["x-timestamp"] == "1700000123"
    assert body is None


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    response_payloads = []

    def __init__(self, *args, **kwargs):
        self.responses = iter(self.response_payloads)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, *args, **kwargs):
        return FakeResponse(next(self.responses))

    async def post(self, *args, **kwargs):
        return FakeResponse(next(self.responses))


@pytest.mark.parametrize(
    ("day_status", "expected"),
    [(3, "already_claimed"), (1, "unavailable")],
)
def test_checkin_respects_upstream_day_state(monkeypatch, day_status, expected):
    FakeClient.response_payloads = [{"base_resp": {"status_code": 0}, "data": {
        "days": [{"is_today": True, "status": day_status}],
    }}]
    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(providers.checkin("global", "secret", "user-1", "1.2.3"))

    assert result["status"] == expected
    assert result["reward"] is None


def test_checkin_claim_requires_verified_claim_fields(monkeypatch):
    FakeClient.response_payloads = [
        {"base_resp": {"status_code": 0}, "data": {
            "days": [{"is_today": True, "status": 2}],
        }},
        {"base_resp": {"status_code": 0}, "data": {"claim_id": "claim-1"}},
    ]
    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)

    with pytest.raises(RuntimeError, match="verified claim fields"):
        asyncio.run(providers.checkin("cn", "secret", "user-1", "1.2.3"))
