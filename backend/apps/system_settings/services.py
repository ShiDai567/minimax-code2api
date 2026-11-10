import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.system_settings.models import RuntimeLog, Setting
from common.problems import ApiProblem

DEFAULTS = {
    "general": {"systemName": "MiniMax Code2API", "timezone": "Asia/Shanghai", "language": "zh-CN"},
    "checkin": {
        "auto": False,
        "time": "09:00",
        "timezone": "Asia/Shanghai",
        "regions": [],
        "retryOnFailure": False,
        "maxRetries": 0,
        "concurrency": 1,
    },
    "api": {
        "host": "127.0.0.1",
        "port": 8045,
        "requireApiKey": True,
        "timeoutSec": 30,
        "defaultModel": "",
        "protocols": {"anthropic": True, "openai_chat": True, "openai_responses": True},
        "gatewayEnabled": True,
    },
    "account": {
        "autoDisableExpired": False,
        "errorThreshold": 5,
        "cooldownMinutes": 10,
        "regionsEnabled": ["cn", "global"],
        "strategy": "round_robin",
    },
    "runtime": {"startedAt": None},
}


def get_settings():
    row = Setting.objects.filter(id=1).first()
    value = row.value if row else {}
    merged = {}
    for key, default in DEFAULTS.items():
        current = value.get(key) if isinstance(value.get(key), dict) else {}
        merged[key] = {**default, **current}
    return merged


def save_settings(patch):
    if not isinstance(patch, dict):
        raise ApiProblem("Expected a JSON object", 400)
    current = get_settings()
    for section in ("general", "checkin", "api", "account"):
        if section not in patch:
            continue
        incoming = patch[section]
        if not isinstance(incoming, dict):
            raise ApiProblem(f"Invalid {section}")
        unknown = set(incoming) - set(DEFAULTS[section])
        if unknown:
            raise ApiProblem("Unknown fields: " + ", ".join(sorted(unknown)))
        current[section].update(incoming)
    _validate(current)
    Setting.objects.update_or_create(id=1, defaults={"value": current})
    return current


def _validate(value):
    checkin = value["checkin"]
    if type(checkin["auto"]) is not bool or type(checkin["retryOnFailure"]) is not bool:
        raise ApiProblem("Boolean settings must be booleans")
    if not isinstance(checkin["time"], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", checkin["time"]):
        raise ApiProblem("Invalid check-in time")
    for zone in (checkin["timezone"], value["general"]["timezone"]):
        try:
            ZoneInfo(zone)
        except (ZoneInfoNotFoundError, TypeError, ValueError):
            raise ApiProblem("Invalid timezone") from None
    for name in ("regions", "regionsEnabled"):
        regions = checkin["regions"] if name == "regions" else value["account"]["regionsEnabled"]
        if not isinstance(regions, list) or any(item not in ("cn", "global") for item in regions) or len(set(regions)) != len(regions):
            raise ApiProblem("Invalid regions")
    if checkin["auto"] and not checkin["regions"]:
        raise ApiProblem("Select at least one region")
    retries = checkin["maxRetries"]
    if type(retries) is not int or not 0 <= retries <= 5:
        raise ApiProblem("maxRetries must be 0..5")
    if value["account"]["strategy"] not in ("round_robin", "most_credits", "recent_active", "least_used"):
        raise ApiProblem("Invalid account strategy")
    timeout = value["api"]["timeoutSec"]
    if type(timeout) is not int or not 5 <= timeout <= 600:
        raise ApiProblem("timeoutSec must be 5..600")
    if value["general"]["language"] != "zh-CN":
        raise ApiProblem("Only zh-CN is supported")


def log_runtime(level, message):
    RuntimeLog.objects.create(level=level, message=message[:500])
    stale = RuntimeLog.objects.order_by("-id").values_list("id", flat=True)[500:]
    if stale:
        RuntimeLog.objects.filter(id__in=list(stale)).delete()


def mark_started():
    from common.utils import utcnow

    current = get_settings()
    current["runtime"]["startedAt"] = utcnow().isoformat()
    Setting.objects.update_or_create(id=1, defaults={"value": current})
