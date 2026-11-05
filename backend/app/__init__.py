import logging

from flask import Flask, jsonify
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api.admin import admin_bp
from app.api.gateway import gateway_bp
from app.api.operations import operations_bp
from app.core.http import register_request_hooks


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(JSON_SORT_KEYS=False)
    if test_config:
        app.config.update(test_config)

    logging.basicConfig(level=logging.INFO)
    app.register_blueprint(admin_bp)
    app.register_blueprint(operations_bp)
    app.register_blueprint(gateway_bp)
    register_request_hooks(app)

    @app.errorhandler(ValidationError)
    def validation_error(error):
        return jsonify({"detail": error.errors(include_input=False, include_url=False)}), 422

    @app.errorhandler(IntegrityError)
    def integrity_error(_error):
        return jsonify({"detail": "Resource conflicts with an existing record"}), 409

    @app.get("/health")
    def health():
        return {"status": "ok", "version": app.config.get("APP_VERSION", "0.1.0"),
                "capabilities": {"accounts": "real", "gateway": "real", "models": "unsupported",
                                 "checkin": "unknown", "credits": "unknown"}}

    return app
