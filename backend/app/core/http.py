from functools import wraps
from inspect import iscoroutinefunction

from flask import g, jsonify, request
from werkzeug.exceptions import HTTPException

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security import hash_api_key, verify_api_key


def register_request_hooks(app):
    @app.before_request
    def open_session():
        g.db = SessionLocal()

    @app.teardown_request
    def close_session(_error=None):
        db = g.pop("db", None)
        if db is not None:
            if _error is not None:
                db.rollback()
            db.close()

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify({"detail": error.description}), error.code


def db_session():
    return g.db


def require_admin(fn):
    def authorized():
        expected = get_settings().admin_token
        authorization = request.headers.get("Authorization", "")
        if not expected:
            return jsonify({"detail": "ADMIN_TOKEN must be configured"}), 503
        if not authorization.startswith("Bearer ") or not verify_api_key(authorization[7:], hash_api_key(expected)):
            return jsonify({"detail": "Admin authentication required"}), 401
        return None

    if iscoroutinefunction(fn):
        @wraps(fn)
        async def async_wrapped(*args, **kwargs):
            denied = authorized()
            return denied if denied else await fn(*args, **kwargs)
        return async_wrapped

    @wraps(fn)
    def wrapped(*args, **kwargs):
        denied = authorized()
        return denied if denied else fn(*args, **kwargs)
    return wrapped


def parse_model(schema):
    return schema.model_validate(request.get_json(silent=True) or {})
