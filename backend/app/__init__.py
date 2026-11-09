import hmac
import json
import os
import sqlite3
from datetime import UTC, datetime
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from flask import Flask, g, jsonify, request
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

db = SQLAlchemy()
migrate = Migrate()


def validate_adapters(config):
    def validate_url(value):
        if not isinstance(value, str):
            raise TypeError("Adapter URLs must be HTTPS URLs")
        try:
            parts = urlsplit(value)
            valid = (parts.scheme == "https" and bool(parts.hostname) and parts.username is None
                     and parts.password is None and not parts.fragment and parts.port != 0)
        except ValueError:
            valid = False
        if not valid:
            raise RuntimeError("Adapter URLs must be HTTPS URLs without credentials or fragments")

    balances = config["BALANCE_ADAPTERS"]
    models = config["MODEL_DISCOVERY_URLS"]
    if not isinstance(balances, dict) or not isinstance(models, dict):
        raise TypeError("Adapter configuration must be JSON objects")
    if any(region not in ("cn", "global") for region in (*balances, *models)):
        raise RuntimeError("Invalid adapter region")
    for adapter in balances.values():
        if not isinstance(adapter, dict) or set(adapter) != {"url", "field", "unit"}:
            raise RuntimeError("Balance adapter requires url, field and unit")
        validate_url(adapter["url"])
        if (not isinstance(adapter["field"], str) or not 0 < len(adapter["field"]) <= 255
                or any(not part for part in adapter["field"].split("."))
                or not isinstance(adapter["unit"], str) or not 0 < len(adapter["unit"]) <= 80):
            raise RuntimeError("Invalid balance adapter field or unit")
    for url in models.values():
        validate_url(url)


@event.listens_for(Engine, "connect")
def sqlite_configure(connection, _record):
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///code2api.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=1024 * 1024,
        ADMIN_TOKEN=os.environ.get("ADMIN_TOKEN"),
        ENCRYPTION_KEY=os.environ.get("ENCRYPTION_KEY"),
        UPSTREAM_TIMEOUT_SECONDS=30,
        MCODE_APP_VERSION=os.environ.get("MCODE_APP_VERSION", "0.1.0"),
        BALANCE_ADAPTERS=json.loads(os.environ.get("BALANCE_ADAPTERS", "{}")),
        MODEL_DISCOVERY_URLS=json.loads(os.environ.get("MODEL_DISCOVERY_URLS", "{}")),
    )
    if config:
        app.config.update(config)
    validate_adapters(app.config)
    token = app.config["ADMIN_TOKEN"]
    key = app.config["ENCRYPTION_KEY"]
    if not isinstance(token, str) or len(token) < 32 or not key:
        raise RuntimeError("Set ADMIN_TOKEN (at least 32 characters) and ENCRYPTION_KEY")
    app.extensions["credential_cipher"] = Fernet(key.encode() if isinstance(key, str) else key)
    db.init_app(app)
    migrate.init_app(app, db)

    from . import models  # noqa: F401
    from .providers import GATEWAY_ORIGINS, PUBLIC_ORIGINS
    app.config.setdefault("GATEWAY_ORIGINS", GATEWAY_ORIGINS)
    app.config.setdefault("PUBLIC_ORIGINS", PUBLIC_ORIGINS)
    from .gateway import gateway
    from .http import ApiProblem
    from .jobs import register_worker
    from .routes import api
    app.register_blueprint(api)
    app.register_blueprint(gateway)
    register_worker(app)
    app.extensions["started_at"] = datetime.now(UTC).isoformat()

    def capabilities():
        return {"multiAccount": True, "checkin": True, "batchCheckin": True, "scheduler": True,
                "credits": False, "balanceSync": bool(app.config["BALANCE_ADAPTERS"]),
                "models": bool(app.config["MODEL_DISCOVERY_URLS"]), "anthropic": True,
                "openaiChat": "text_nonstream_only", "openaiResponses": "text_nonstream_only",
                "serviceControl": False, "protocolToggle": False, "modelToggle": False,
                "runtimeLogs": False}

    app.extensions["capabilities"] = capabilities

    @app.errorhandler(ApiProblem)
    def problem(exc):
        return jsonify(success=False, message=exc.detail, detail=exc.detail, error={"code": exc.code}), exc.status

    @app.errorhandler(IntegrityError)
    def conflict(_exc):
        db.session.rollback()
        return jsonify(success=False, message="Resource conflict or resource in use", detail="Resource conflict or resource in use",
                       error={"code": "CONFLICT"}), 409

    @app.after_request
    def prevent_caching(response):
        if request.path.startswith("/api/v1/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.before_request
    def authenticate_admin():
        if not request.path.startswith("/api/v1/"):
            return None
        auth = request.headers.get("Authorization", "")
        supplied = auth[7:] if auth.startswith("Bearer ") else ""
        if not hmac.compare_digest(supplied.encode(), token.encode()):
            return jsonify(success=False, message="Authentication required", detail="Authentication required", error={"code": "UNAUTHORIZED"}, timestamp=datetime.now(UTC).isoformat()), 401
        g.admin = True
        return None

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.2.0", "capabilities": capabilities()}

    return app
