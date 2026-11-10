import re
from datetime import UTC, datetime


def utcnow():
    return datetime.now(UTC)


def epoch_ms(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1000)


def region_required(value):
    from common.problems import ApiProblem

    if value not in ("cn", "global"):
        raise ApiProblem("region must be cn or global")
    return value


def text(value, name, limit, required=True):
    from common.problems import ApiProblem

    if not isinstance(value, str) or len(value.strip()) > limit or (required and not value.strip()):
        raise ApiProblem(f"Invalid {name}")
    return value.strip()


TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
