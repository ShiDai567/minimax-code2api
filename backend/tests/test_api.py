import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["ADMIN_TOKEN"] = "test-admin-token"
os.environ["ENCRYPTION_KEY"] = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app.core.database import Base
from app import create_app
from app.core import http

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base.metadata.create_all(engine)
http.SessionLocal = TestingSession
app = create_app({"TESTING": True})
client = app.test_client()
ADMIN = {"Authorization": "Bearer test-admin-token"}


def test_admin_guard():
    assert client.get("/api/v1/accounts").status_code == 401
    assert client.get("/api/v1/accounts", headers=ADMIN).status_code == 200


def test_health_and_pydantic_validation():
    assert client.get("/health").json["status"] == "ok"
    invalid = client.post("/api/v1/accounts", headers=ADMIN, json={"region": "planet", "name": "", "identifier": "x"})
    assert invalid.status_code == 422
    assert "detail" in invalid.json


def test_credentials_are_encrypted_and_regions_are_isolated():
    response = client.post("/api/v1/accounts", headers=ADMIN, json={"region": "cn", "name": "CN", "identifier": "a@example.test", "credential": "secret-token"})
    assert response.status_code == 201
    assert response.json["credentialMasked"] != "secret-token"
    assert response.json["realUserId"] is None
    assert len(client.get("/api/v1/accounts?region=global", headers=ADMIN).json["items"]) == 0
    assert len(client.get("/api/v1/accounts?region=cn", headers=ADMIN).json["items"]) == 1


def test_api_key_is_only_returned_once():
    created = client.post("/api/v1/keys", headers=ADMIN, json={"name": "local"})
    assert created.status_code == 201
    secret = created.json["secret"]
    assert secret.startswith("sk-m2a-")
    listed = client.get("/api/v1/keys", headers=ADMIN).json["items"][0]
    assert secret not in str(listed)
    models = client.get("/v1/models", headers={"Authorization": f"Bearer {secret}"})
    assert models.status_code == 501
    assert "no verified upstream model-list adapter" in models.json["detail"]


def test_unknown_checkin_does_not_report_success():
    created = client.post("/api/v1/accounts", headers=ADMIN, json={"region": "global", "name": "IO", "identifier": "b@example.test", "credential": "other-token", "real_user_id": "user-2"})
    response = client.post(f"/api/v1/checkin/run?account_id={created.json['id']}", headers=ADMIN)
    assert response.status_code == 502
    assert "Upstream check-in failed" in response.json["detail"]


def test_api_key_auth_and_openai_protocol_boundary():
    created = client.post("/api/v1/keys", headers=ADMIN, json={"name": "gateway"}).json
    response = client.post("/v1/chat/completions", headers={"Authorization": f"Bearer {created['secret']}"}, json={"model": "anything", "messages": []})
    assert response.status_code == 501
    assert "protocol adapters" in response.json["detail"]


def test_region_group_mismatch_rejected():
    group = client.post("/api/v1/groups", headers=ADMIN, json={"region": "cn", "name": "CN pool"}).json
    response = client.post("/api/v1/accounts", headers=ADMIN, json={"region": "global", "name": "bad", "identifier": "wrong@example.test", "credential": "secret", "group_id": int(group["id"])})
    assert response.status_code == 422
