from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import md5
import uuid
from urllib.parse import quote
from urllib.parse import urlencode

import httpx


@dataclass(frozen=True)
class RegionProvider:
    region: str
    origin: str

    async def request(self, client: httpx.AsyncClient, path: str, token: str, body: bytes,
                      headers: dict[str, str], stream: bool = False):
        url = f"{self.origin}/mavis/api/v1/llm{path}"
        forwarded = {k: v for k, v in headers.items() if k.lower() in {"content-type", "accept", "anthropic-version", "anthropic-beta"}}
        forwarded["Authorization"] = f"Bearer {token}"
        forwarded["User-Agent"] = "MiniMaxAgent"
        forwarded["X-Mavis-Session-Id"] = str(uuid.uuid4())
        forwarded["X-Mavis-Agent-Id"] = "main"
        forwarded["X-Mavis-Timezone-Offset"] = "0"
        request = client.build_request("POST", url, content=body, headers=forwarded)
        return await client.send(request, stream=stream)


PROVIDERS = {
    "cn": RegionProvider("cn", "https://agent.minimax.cn"),
    "global": RegionProvider("global", "https://agent.minimax.io"),
}


class UnsupportedUpstreamCapability(RuntimeError):
    pass


def _mcode_signed_request(origin: str, path: str, token: str, real_user_id: str, app_version: str,
                          method: str, body: str = "", now_ms: int | None = None):
    now_ms = now_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    second = now_ms // 1000
    language = "zh" if origin.endswith("minimaxi.com") else "en"
    query = urlencode({"device_platform": "web", "biz_id": "3", "app_id": "3001", "version_code": "22201",
                       "is_desktop": "1", "desktop_version": app_version, "unix": str(now_ms),
                       "timezone_offset": "0", "sys_language": language, "lang": language, "device_id": "0",
                       "os_name": "linux", "browser_name": "mcode", "user_id": real_user_id, "client": "mcode"})
    target = f"{origin}{path}?{query}"
    path_with_search = f"{path}?{query}"
    yy_body = body or "{}"
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "MiniMaxCode",
               "Authorization": f"Bearer {token}",
               "yy": md5(f"{quote(path_with_search, safe='/')}_{yy_body}{md5(str(now_ms).encode()).hexdigest()}ooui".encode()).hexdigest(),
               "x-timestamp": str(second),
               "x-signature": md5(f"{second}I*7Cf%WZ#S&%1RlZJ&C2{body}".encode()).hexdigest()}
    return target, headers, body if method == "POST" else None


async def checkin(region: str, token: str, real_user_id: str, app_version: str):
    origin = "https://agent.minimaxi.com" if region == "cn" else "https://agent.minimax.io"
    async with httpx.AsyncClient(timeout=30) as client:
        status_url, status_headers, _ = _mcode_signed_request(origin, "/minimax-cloud/api/v1/signin/status", token, real_user_id, app_version, "GET")
        status_response = await client.get(status_url, headers=status_headers)
        status_response.raise_for_status()
        panel_body = status_response.json()
        if panel_body.get("base_resp", {}).get("status_code", 0) != 0:
            raise RuntimeError(panel_body.get("base_resp", {}).get("status_msg", "Check-in status failed"))
        panel = panel_body.get("data")
        if not isinstance(panel, dict):
            raise RuntimeError("Check-in status response was missing data")
        days = panel.get("days", [])
        today = next((day for day in days if isinstance(day, dict) and day.get("is_today") is True), None)
        if today and today.get("status") == 3:
            return {"status": "already_claimed", "panel": panel, "reward": None}
        if not today or today.get("status") != 2:
            return {"status": "unavailable", "panel": panel, "reward": None}
        body = "{}"
        claim_url, claim_headers, claim_body = _mcode_signed_request(origin, "/minimax-cloud/api/v1/signin/claim", token, real_user_id, app_version, "POST", body)
        claim_response = await client.post(claim_url, headers=claim_headers, content=claim_body)
        claim_response.raise_for_status()
        result = claim_response.json()
        if result.get("base_resp", {}).get("status_code", 0) != 0:
            raise RuntimeError(result.get("base_resp", {}).get("status_msg", "Check-in claim failed"))
        data = result.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("Check-in claim response was missing data")
        if not isinstance(data.get("claim_id"), str) or not isinstance(data.get("points"), (int, float)):
            raise RuntimeError("Check-in claim response is missing verified claim fields")
        return {"status": "already_claimed" if data.get("claim_result") == 2 else "claimed",
                "panel": data.get("panel", panel), "reward": data.get("points"),
                "day_no": data.get("day_no"), "claim_id": data.get("claim_id")}


async def balance(region: str, token: str):
    origin = "https://www.minimaxi.com" if region == "cn" else "https://platform.minimax.io"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{origin}/v1/api/openplatform/coding_plan/remains",
                                    headers={"Accept": "application/json", "Authorization": f"Bearer {token}"})
    response.raise_for_status()
    data = response.json()
    if data.get("base_resp", {}).get("status_code", 0) != 0:
        raise RuntimeError(data.get("base_resp", {}).get("status_msg", "Balance query failed"))
    return data
