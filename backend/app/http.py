from datetime import UTC

from flask import jsonify, request
from sqlalchemy import func

from . import db


class ApiProblem(Exception):
    def __init__(self, detail, status=422, code="INVALID_INPUT"):
        super().__init__(detail)
        self.detail, self.status, self.code = detail, status, code


def result(data=None, status=200):
    # Keep the initial backend's `data` envelope while exposing the client fields.
    body = {"success": True, "data": data, "source": "live"}
    if isinstance(data, dict):
        body.update(data)
    return jsonify(body), status


def iso(value):
    return value.replace(tzinfo=UTC).isoformat() if value else None


def json_body(allowed):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiProblem("Expected a JSON object", 400)
    unknown = set(body) - set(allowed)
    if unknown:
        raise ApiProblem("Unknown fields: " + ", ".join(sorted(unknown)))
    return body


def text(body, name, limit, required=True):
    value = body.get(name, "")
    if not isinstance(value, str) or len(value.strip()) > limit or (required and not value.strip()):
        raise ApiProblem(f"Invalid {name}")
    return value.strip()


def boolean(value, name):
    if type(value) is not bool:
        raise ApiProblem(f"{name} must be a boolean")
    return value


def region_arg(required=True):
    region = request.args.get("region")
    if region not in ("cn", "global") and (required or region is not None):
        raise ApiProblem("region must be cn or global")
    return region


def region_value(value):
    if value not in ("cn", "global"):
        raise ApiProblem("region must be cn or global")
    return value


def integer(value, name, minimum=1, maximum=2**31 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ApiProblem(f"Invalid {name}")
    return value


def get_or_404(model, identifier):
    value = db.session.get(model, identifier)
    if value is None:
        raise ApiProblem("Resource not found", 404, "NOT_FOUND")
    return value


def page(query, model, serializer, sorts, default="id"):
    try:
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        raise ApiProblem("Invalid pagination") from None
    if not 1 <= limit <= 500 or offset < 0:
        raise ApiProblem("limit must be 1..500 and offset must be nonnegative")
    sort = request.args.get("sort", default)
    order = request.args.get("order", "asc")
    if sort not in sorts or order not in ("asc", "desc"):
        raise ApiProblem("Invalid sort or order")
    column = getattr(model, sort)
    total = db.session.scalar(db.select(func.count()).select_from(query.subquery()))
    query = query.order_by(column.desc() if order == "desc" else column.asc(), model.id).limit(limit).offset(offset)
    return result({"items": [serializer(item) for item in db.session.scalars(query)], "total": total})


def search(query, *columns):
    value = request.args.get("search", "").strip()
    if len(value) > 255:
        raise ApiProblem("Search is too long")
    if value:
        query = query.where(db.or_(*(column.icontains(value, autoescape=True) for column in columns)))
    return query
