import time

from rest_framework.response import Response


def envelope(data, status=200):
    return Response({"success": True, "source": "live", "fetchedAt": int(time.time() * 1000), "data": data}, status=status)


def page_params(request, sorts, default="id"):
    try:
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))
    except ValueError as exc:
        raise ValueError("Invalid pagination") from exc
    if not 1 <= limit <= 200 or offset < 0:
        raise ValueError("limit must be 1..200 and offset must be nonnegative")
    sort = request.query_params.get("sort", default)
    order = request.query_params.get("order", "desc")
    if sort not in sorts or order not in ("asc", "desc"):
        raise ValueError("Invalid sort or order")
    return limit, offset, sort, order
