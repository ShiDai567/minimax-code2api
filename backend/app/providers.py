"""Region-specific MiniMax wire adapters. No model catalog or prices are invented."""
import hashlib
import math
import sys
import time
from decimal import Decimal
from urllib.parse import quote, urlencode

import httpx
from flask import current_app

from .http import ApiProblem

GATEWAY_ORIGINS = {"cn": "https://agent.minimax.cn", "global": "https://agent.minimax.io"}
PUBLIC_ORIGINS = {"cn": "https://agent.minimaxi.com", "global": "https://agent.minimax.io"}


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value < 10**18


class MiniMaxProvider:
    def __init__(self, region, credential, real_user_id=None, session_id=None):
        self.region, self.credential = region, credential
        self.real_user_id, self.session_id = real_user_id, session_id

    def client(self):
        return httpx.Client(timeout=httpx.Timeout(current_app.config["UPSTREAM_TIMEOUT_SECONDS"], connect=10),
                            follow_redirects=False, trust_env=False,
                            transport=current_app.config.get("HTTP_TRANSPORT"))

    def messages(self, body, headers=None, suffix="messages"):
        origin = current_app.config["GATEWAY_ORIGINS"][self.region]
        client = self.client()
        request_headers = {
            "Authorization": f"Bearer {self.credential}", "User-Agent": "MiniMaxAgent",
            "X-Mavis-Session-Id": self.session_id, "X-Mavis-Agent-Id": "main",
            "X-Mavis-Timezone-Offset": "0", "anthropic-version": "2023-06-01",
        }
        request_headers.update(headers or {})
        try:
            response = client.send(client.build_request("POST", f"{origin}/mavis/api/v1/llm/v1/{suffix}",
                                                        json=body, headers=request_headers), stream=True)
            return response, client
        except httpx.HTTPError:
            client.close()
            raise ApiProblem("Upstream connection failed", 502, "UPSTREAM_UNAVAILABLE") from None

    def public(self, path, method):
        if not self.real_user_id:
            raise ApiProblem("real_user_id is required for check-in")
        now = int(time.time() * 1000)
        language = "zh" if self.region == "cn" else "en"
        params = {
            "device_platform": "web", "biz_id": "3", "app_id": "3001", "version_code": "22201",
            "is_desktop": "1", "desktop_version": current_app.config["MCODE_APP_VERSION"],
            "unix": str(now), "timezone_offset": "0", "sys_language": language, "lang": language,
            "device_id": "0", "os_name": sys.platform, "browser_name": "mcode",
            "user_id": self.real_user_id, "client": "mcode",
        }
        # URLSearchParams uses form encoding but escapes '~' and preserves '*'.
        query = urlencode(params, safe="*").replace("~", "%7E")
        path_search = path + "?" + query
        body = "{}" if method == "POST" else ""

        def md5(value):
            return hashlib.md5(value.encode(), usedforsecurity=False).hexdigest()

        headers = {
            "Authorization": f"Bearer {self.credential}", "User-Agent": "MiniMaxCode",
            "Accept": "application/json", "Content-Type": "application/json",
            "yy": md5(f"{quote(path_search, safe='~()*!.\u0027-')}_{{}}{md5(str(now))}ooui"),
            "x-timestamp": str(now // 1000),
            "x-signature": md5(f"{now // 1000}I*7Cf%WZ#S&%1RlZJ&C2{body}"),
        }
        return self.json_request(method, current_app.config["PUBLIC_ORIGINS"][self.region] + path_search,
                                 headers=headers, content=body.encode() if body else None)

    def json_request(self, method, url, **kwargs):
        try:
            with self.client() as client:
                response = client.request(method, url, **kwargs)
                if response.status_code in (401, 403):
                    raise ApiProblem("Upstream credential rejected", 502, "UPSTREAM_AUTH_FAILED")
                if not response.is_success:
                    raise ApiProblem(f"Upstream returned HTTP {response.status_code}", 502, "UPSTREAM_ERROR")
                body = response.json()
                if not isinstance(body, dict):
                    raise TypeError
                base = body.get("base_resp", {})
                if not isinstance(base, dict) or base.get("status_code", 0) != 0:
                    raise ValueError
                return body
        except (httpx.HTTPError, ValueError, TypeError):
            raise ApiProblem("Upstream returned an invalid response or could not be reached", 502, "UPSTREAM_ERROR") from None

    def checkin(self):
        panel = self.public("/minimax-cloud/api/v1/signin/status", "GET").get("data")
        validate_panel(panel)
        if any(day["is_today"] and day["status"] == 3 for day in panel["days"]):
            return {"status": "skipped", "message": "Already claimed upstream"}
        if not any(day["status"] == 2 for day in panel["days"]):
            return {"status": "skipped", "message": "No claimable sign-in reward"}
        claim = self.public("/minimax-cloud/api/v1/signin/claim", "POST").get("data")
        if (not isinstance(claim, dict) or not isinstance(claim.get("claim_id"), str)
                or not 0 < len(claim["claim_id"]) <= 255 or type(claim.get("claim_result")) is not int
                or claim["claim_result"] not in (1, 2) or not numeric(claim.get("points"))
                or type(claim.get("day_no")) is not int or not 1 <= claim["day_no"] <= 7
                or not numeric(claim.get("expire_at_ms"))):
            raise ApiProblem("Invalid upstream sign-in claim", 502, "UPSTREAM_ERROR")
        validate_panel(claim.get("panel"))
        if claim["claim_result"] == 2:
            return {"status": "skipped", "message": "Already claimed upstream"}
        return {"status": "success", "reward": Decimal(str(claim["points"])), "claim_id": claim["claim_id"],
                "message": "Reward reported by upstream; credit arrival remains unconfirmed"}

    def balances(self):
        # Explicit operator-configured adapter: do not assume a generic wallet endpoint.
        adapter = current_app.config["BALANCE_ADAPTERS"].get(self.region)
        if not adapter:
            raise ApiProblem("No verified balance adapter configured for this region", 501, "UNSUPPORTED")
        body = self.json_request("GET", adapter["url"], headers={"Authorization": f"Bearer {self.credential}"})
        value = body
        for part in adapter["field"].split("."):
            value = value.get(part) if isinstance(value, dict) else None
        if not numeric(value):
            raise ApiProblem("Configured balance field is missing or invalid", 502, "UPSTREAM_ERROR")
        return [{"amount": Decimal(str(value)), "unit": adapter["unit"], "provider_field": adapter["field"]}]

    def models(self):
        url = current_app.config["MODEL_DISCOVERY_URLS"].get(self.region)
        if not url:
            raise ApiProblem("Model discovery is not configured for this region", 501, "UNSUPPORTED")
        body = self.json_request("GET", url, headers={"Authorization": f"Bearer {self.credential}"})
        data = body.get("data")
        if not isinstance(data, list) or any(not isinstance(row, dict) or not isinstance(row.get("id"), str)
                                            or not 0 < len(row["id"]) <= 255 for row in data):
            raise ApiProblem("Invalid upstream model catalog", 502, "UPSTREAM_ERROR")
        return [{"id": row["id"], "object": "model", "owned_by": "minimax"} for row in data]


def validate_panel(panel):
    valid = isinstance(panel, dict) and type(panel.get("scene")) is int and panel["scene"] in range(5)
    days = panel.get("days") if valid else None
    valid = valid and isinstance(days, list) and len(days) == 7
    if valid:
        valid = all(isinstance(day, dict) and type(day.get("day_no")) is int and 1 <= day["day_no"] <= 7
                    and numeric(day.get("points")) and type(day.get("is_today")) is bool
                    and type(day.get("status")) is int and day["status"] in (1, 2, 3, 4)
                    and ("bonus_points" not in day or numeric(day["bonus_points"])) for day in days)
    if valid:
        valid = (len({day["day_no"] for day in days}) == 7 and sum(day["is_today"] for day in days) <= 1
                 and sum(day["status"] == 2 for day in days) <= 1)
    if not valid:
        raise ApiProblem("Invalid upstream sign-in panel", 502, "UPSTREAM_ERROR")


def provider_for(account):
    cipher = current_app.extensions["credential_cipher"]
    from cryptography.fernet import InvalidToken
    try:
        credential = cipher.decrypt(account.credential_encrypted).decode()
    except (InvalidToken, UnicodeDecodeError):
        raise ApiProblem("Stored credential cannot be decrypted; check the encryption key", 503, "CREDENTIAL_UNAVAILABLE") from None
    factory = current_app.config.get("PROVIDER_FACTORY", MiniMaxProvider)
    return factory(account.region, credential, account.real_user_id, account.session_id)
