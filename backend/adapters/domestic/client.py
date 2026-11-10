"""Domestic (cn) wire client. Origins and signing are not shared with the global adapter."""
import hashlib
import math
import sys
import time
from decimal import Decimal
from urllib.parse import quote, urlencode

import httpx
from django.conf import settings

from adapters.base import BaseMiniMaxAdapter, CheckinOutcome, UpstreamError

GATEWAY_ORIGIN = "https://agent.minimax.cn"
PUBLIC_ORIGIN = "https://agent.minimaxi.com"


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value < 10**18


class DomesticClient:
    origin_gateway = GATEWAY_ORIGIN
    origin_public = PUBLIC_ORIGIN
    language = "zh"

    def __init__(self, credential, real_user_id="", session_id=""):
        self.credential = credential
        self.real_user_id = real_user_id
        self.session_id = session_id

    def http(self):
        transport = getattr(settings, "HTTP_TRANSPORT", None)
        kwargs = {
            "timeout": httpx.Timeout(settings.UPSTREAM_TIMEOUT_SECONDS, connect=10),
            "follow_redirects": False,
            "trust_env": False,
        }
        if transport is not None:
            kwargs["transport"] = transport
        return httpx.Client(**kwargs)

    def messages(self, body, headers=None, suffix="messages"):
        request_headers = {
            "Authorization": f"Bearer {self.credential}",
            "User-Agent": "MiniMaxAgent",
            "X-Mavis-Session-Id": self.session_id or "",
            "X-Mavis-Agent-Id": "main",
            "X-Mavis-Timezone-Offset": "0",
            "anthropic-version": "2023-06-01",
        }
        request_headers.update(headers or {})
        client = self.http()
        try:
            response = client.send(
                client.build_request("POST", f"{self.origin_gateway}/mavis/api/v1/llm/v1/{suffix}", json=body, headers=request_headers),
                stream=True,
            )
            return response, client
        except httpx.TimeoutException:
            client.close()
            raise UpstreamError("Upstream timed out", 504, "UPSTREAM_TIMEOUT") from None
        except httpx.HTTPError:
            client.close()
            raise UpstreamError("Upstream connection failed", 502, "UPSTREAM_UNAVAILABLE") from None

    def signed_public(self, path, method):
        if not self.real_user_id:
            raise UpstreamError("real_user_id is required for check-in", 422, "INVALID_INPUT")
        now = int(time.time() * 1000)
        params = {
            "device_platform": "web",
            "biz_id": "3",
            "app_id": "3001",
            "version_code": "22201",
            "is_desktop": "1",
            "desktop_version": settings.MCODE_APP_VERSION,
            "unix": str(now),
            "timezone_offset": "0",
            "sys_language": self.language,
            "lang": self.language,
            "device_id": "0",
            "os_name": sys.platform,
            "browser_name": "mcode",
            "user_id": self.real_user_id,
            "client": "mcode",
        }
        query = urlencode(params, safe="*").replace("~", "%7E")
        path_search = path + "?" + query
        body = "{}" if method == "POST" else ""

        def md5(value):
            return hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()

        quoted = quote(path_search, safe="~()*!.'-")
        headers = {
            "Authorization": f"Bearer {self.credential}",
            "User-Agent": "MiniMaxCode",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "yy": md5(f"{quoted}_{{}}{md5(str(now))}ooui"),
            "x-timestamp": str(now // 1000),
            "x-signature": md5(f"{now // 1000}I*7Cf%WZ#S&%1RlZJ&C2{body}"),
        }
        return self.json_request(method, self.origin_public + path_search, headers=headers, content=body.encode() if body else None)

    def json_request(self, method, url, **kwargs):
        try:
            with self.http() as client:
                response = client.request(method, url, **kwargs)
                if response.status_code in (401, 403):
                    raise UpstreamError("Upstream credential rejected", 502, "UPSTREAM_AUTH_FAILED", permanent=True)
                if not response.is_success:
                    raise UpstreamError(f"Upstream returned HTTP {response.status_code}", 502, "UPSTREAM_ERROR")
                body = response.json()
                if not isinstance(body, dict):
                    raise UpstreamError("Invalid upstream response", 502, "UPSTREAM_ERROR")
                base = body.get("base_resp", {})
                if isinstance(base, dict) and base.get("status_code", 0) not in (0, None):
                    raise UpstreamError("Upstream rejected the request", 502, "UPSTREAM_ERROR")
                return body
        except UpstreamError:
            raise
        except httpx.TimeoutException:
            raise UpstreamError("Upstream timed out", 504, "UPSTREAM_TIMEOUT") from None
        except httpx.HTTPError:
            raise UpstreamError("Upstream connection failed", 502, "UPSTREAM_UNAVAILABLE") from None


def validate_panel(panel):
    days = panel.get("days") if isinstance(panel, dict) else None
    valid = isinstance(panel, dict) and type(panel.get("scene")) is int and panel["scene"] in range(5)
    valid = valid and isinstance(days, list) and len(days) == 7
    if valid:
        valid = all(
            isinstance(day, dict)
            and type(day.get("day_no")) is int
            and 1 <= day["day_no"] <= 7
            and numeric(day.get("points"))
            and type(day.get("is_today")) is bool
            and type(day.get("status")) is int
            and day["status"] in (1, 2, 3, 4)
            for day in days
        )
    if valid:
        valid = len({day["day_no"] for day in days}) == 7 and sum(day["is_today"] for day in days) <= 1
    if not valid:
        raise UpstreamError("Invalid upstream sign-in panel", 502, "UPSTREAM_ERROR")


class DomesticCheckin:
    def __init__(self, client: DomesticClient):
        self.client = client

    def run(self) -> CheckinOutcome:
        panel = self.client.signed_public("/minimax-cloud/api/v1/signin/status", "GET").get("data")
        validate_panel(panel)
        if any(day["is_today"] and day["status"] == 3 for day in panel["days"]):
            return CheckinOutcome("skipped", "Already claimed upstream")
        if not any(day["status"] == 2 for day in panel["days"]):
            return CheckinOutcome("skipped", "No claimable sign-in reward")
        claim = self.client.signed_public("/minimax-cloud/api/v1/signin/claim", "POST").get("data")
        if (
            not isinstance(claim, dict)
            or not isinstance(claim.get("claim_id"), str)
            or not 0 < len(claim["claim_id"]) <= 255
            or type(claim.get("claim_result")) is not int
            or claim["claim_result"] not in (1, 2)
            or not numeric(claim.get("points"))
        ):
            raise UpstreamError("Invalid upstream sign-in claim", 502, "UPSTREAM_ERROR")
        validate_panel(claim.get("panel"))
        if claim["claim_result"] == 2:
            return CheckinOutcome("skipped", "Already claimed upstream")
        return CheckinOutcome(
            "success",
            "Reward reported by upstream; credit arrival remains unconfirmed",
            Decimal(str(claim["points"])),
            claim["claim_id"],
        )


class DomesticCredits:
    def __init__(self, client: DomesticClient):
        self.client = client

    def fetch(self):
        adapter = settings.BALANCE_ADAPTERS.get("cn")
        if not adapter:
            raise UpstreamError("No verified balance adapter configured for cn", 501, "UNSUPPORTED")
        body = self.client.json_request("GET", adapter["url"], headers={"Authorization": f"Bearer {self.client.credential}"})
        value = body
        for part in adapter["field"].split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if not numeric(value):
            raise UpstreamError("Configured balance field is missing or invalid", 502, "UPSTREAM_ERROR")
        return {"amount": Decimal(str(value)), "unit": adapter["unit"], "provider_field": adapter["field"]}


class DomesticAdapter(BaseMiniMaxAdapter):
    region = "cn"
    gateway_origin = GATEWAY_ORIGIN
    public_origin = PUBLIC_ORIGIN
    language = "zh"

    def __init__(self, credential, real_user_id="", session_id=""):
        self.client = DomesticClient(credential, real_user_id, session_id)

    def checkin(self, account):
        return DomesticCheckin(self.client).run()

    def get_credits(self, account):
        return DomesticCredits(self.client).fetch()

    def generate(self, account, body, headers=None, suffix="messages"):
        return self.client.messages(body, headers, suffix)

    def list_models(self, account):
        url = settings.MODEL_DISCOVERY_URLS.get("cn")
        if not url:
            raise UpstreamError("Model discovery is not configured for cn", 501, "UNSUPPORTED")
        body = self.client.json_request("GET", url, headers={"Authorization": f"Bearer {self.client.credential}"})
        data = body.get("data")
        if not isinstance(data, list):
            raise UpstreamError("Invalid upstream model catalog", 502, "UPSTREAM_ERROR")
        return data
