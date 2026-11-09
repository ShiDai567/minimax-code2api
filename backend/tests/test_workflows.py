import json
from datetime import UTC, datetime

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.exc import IntegrityError

from app import create_app, db
from app.jobs import run_one, schedule_due
from app.models import Account, CheckinJob, CheckinRecord, CheckinTask

ADMIN = {"Authorization": "Bearer " + "a" * 32}


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'db.sqlite'}",
                      "ADMIN_TOKEN": "a" * 32, "ENCRYPTION_KEY": Fernet.generate_key()})
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()


def account(client, region="cn", name="user", real_user_id="123"):
    response = client.post("/api/v1/accounts", headers=ADMIN, json={"name": name, "identifier": name,
        "credential": "upstream-secret", "region": region, "real_user_id": real_user_id})
    assert response.status_code == 201
    return response.json["data"]["id"]


def key(client):
    response = client.post("/api/v1/keys", headers=ADMIN, json={"name": "key"})
    return response.json["secret"]


def test_regions_groups_and_crud(client):
    group = client.post("/api/v1/groups", headers=ADMIN, json={"region": "global", "name": "group"}).json["data"]
    cn = account(client)
    assert client.patch(f"/api/v1/accounts/{cn}", headers=ADMIN, json={"group_id": group["id"]}).status_code == 422
    assert client.get("/api/v1/accounts", headers=ADMIN).status_code == 422
    assert client.get("/api/v1/accounts?region=global", headers=ADMIN).json["total"] == 0
    assert client.patch(f"/api/v1/accounts/{cn}", headers=ADMIN, json={"health": "healthy"}).status_code == 422
    assert client.patch(f"/api/v1/accounts/{cn}", headers=ADMIN, json={"credential": "replacement"}).json["health"] == "unknown"
    assert client.post("/api/v1/accounts/bulk-delete", headers=ADMIN,
                       json={"region": "global", "account_ids": [cn]}).status_code == 422
    assert client.delete(f"/api/v1/groups/{group['id']}", headers=ADMIN).status_code == 204


def test_gateway_auth_verification_forwarding_and_redaction(client):
    requests = []
    def upstream(req):
        requests.append(req)
        assert req.headers["authorization"] == "Bearer upstream-secret"
        if req.url.path.endswith("count_tokens"):
            return httpx.Response(200, json={"input_tokens": 3})
        return httpx.Response(200, json={"id": "m1", "model": "model-from-operator",
            "content": [{"type": "text", "text": "hello"}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 3, "output_tokens": 2}})
    client.application.config["HTTP_TRANSPORT"] = httpx.MockTransport(upstream)
    cn, global_id = account(client), account(client, "global", "world")
    secret = key(client)
    headers = {"Authorization": "Bearer " + secret}
    body = {"model": "model-from-operator", "messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/v1/messages", headers=headers, json=body).status_code == 503
    assert client.post(f"/api/v1/accounts/{global_id}/verify-model", headers=ADMIN, json={"model": "m"}).status_code == 200
    assert client.post("/v1/messages", headers=headers, json=body).status_code == 503
    assert client.post(f"/api/v1/accounts/{cn}/verify-model", headers=ADMIN, json={"model": "m"}).json["health"] == "healthy"
    response = client.post("/v1/chat/completions", headers=headers, json=body)
    assert response.status_code == 200
    assert response.json["choices"][0]["message"]["content"] == "hello"
    assert json.loads(requests[-1].content)["max_tokens"] == 4096
    assert requests[-1].url.host == "agent.minimax.cn"
    assert client.post("/v1/chat/completions", headers=headers, json={**body, "stream": True}).status_code == 501
    assert client.post("/v1/chat/completions", headers=headers, json={**body, "tools": []}).status_code == 400
    logs = client.get("/api/v1/logs?region=cn", headers=ADMIN).json
    assert logs["total"] == 1
    assert logs["items"][0]["headers"]["Authorization"] == "[REDACTED]"
    assert secret not in json.dumps(logs)
    assert "upstream-secret" not in json.dumps(logs)
    assert logs["items"][0]["credits"] is None
    assert client.patch(f"/api/v1/accounts/{cn}", headers=ADMIN, json={"credential": "new-secret"}).json["health"] == "unknown"


def test_sse_and_response_conversion(client):
    def upstream(req):
        if req.url.path.endswith("count_tokens"):
            return httpx.Response(200, json={"input_tokens": 1})
        if json.loads(req.content).get("stream"):
            return httpx.Response(200, content=b"event: message_start\ndata: {}\n\nevent: message_stop\ndata: {}\n\n",
                                  headers={"Content-Type": "text/event-stream"})
        return httpx.Response(200, json={"id": "id", "model": "m", "content": [{"type": "text", "text": "ok"}],
                                         "stop_reason": "max_tokens", "usage": {"input_tokens": 1, "output_tokens": 2}})
    client.application.config["HTTP_TRANSPORT"] = httpx.MockTransport(upstream)
    aid = account(client)
    client.post(f"/api/v1/accounts/{aid}/verify-model", headers=ADMIN, json={"model": "m"})
    headers = {"Authorization": "Bearer " + key(client)}
    response = client.post("/v1/messages", headers=headers, json={"model": "m", "messages": [], "stream": True})
    assert b"event: message_stop" in response.data
    response.close()
    response = client.post("/v1/responses", headers=headers, json={"model": "m", "input": "hello"})
    assert response.json["status"] == "incomplete"
    assert response.json["usage"]["total_tokens"] == 3


def test_checkin_status_claim_and_batch_progress(client):
    calls = []
    days = [{"day_no": i, "points": 10, "status": 2 if i == 1 else 1, "is_today": i == 1} for i in range(1, 8)]
    panel = {"scene": 1, "days": days}
    def upstream(req):
        calls.append(req)
        assert req.url.host == "agent.minimaxi.com"
        assert req.url.params["user_id"] == "123"
        assert req.headers["authorization"] == "Bearer upstream-secret"
        if req.method == "GET":
            return httpx.Response(200, json={"data": panel, "base_resp": {"status_code": 0}})
        assert req.content == b"{}"
        return httpx.Response(200, json={"data": {"claim_id": "claim", "claim_result": 1, "day_no": 1,
            "points": 10, "expire_at_ms": 12345, "panel": panel}, "base_resp": {"status_code": 0}})
    client.application.config["HTTP_TRANSPORT"] = httpx.MockTransport(upstream)
    aid = account(client)
    response = client.post(f"/api/v1/checkin/run?account_id={aid}", headers=ADMIN)
    assert response.json["status"] == "success"
    assert response.json["arrival"] == "pending"
    assert client.post(f"/api/v1/checkin/run?account_id={aid}", headers=ADMIN).status_code == 200
    assert len(calls) == 2
    assert client.get("/api/v1/credits?region=cn", headers=ADMIN).json["total"] == 0
    job = client.post("/api/v1/checkin/jobs", headers=ADMIN, json={"region": "cn", "account_ids": [aid]}).json
    assert job["status"] == "queued"
    with client.application.app_context():
        assert run_one()
    job = client.get("/api/v1/checkin/jobs/" + job["id"], headers=ADMIN).json
    assert (job["status"], job["completed"], job["success"]) == ("completed", 1, 1)
    assert len(calls) == 2


def test_pending_checkin_not_repeated_and_scheduler_dedup(client):
    aid = account(client)
    with client.application.app_context():
        db.session.add(CheckinRecord(account_id=aid, day=datetime.now(UTC).date(), status="pending", trigger="manual"))
        db.session.commit()
    assert client.post(f"/api/v1/checkin/run?account_id={aid}", headers=ADMIN).status_code == 409
    assert client.patch("/api/v1/settings", headers=ADMIN, json={"checkin": {"auto": True, "time": "00:00",
        "timezone": "UTC", "regions": ["cn"]}}).status_code == 200
    with client.application.app_context():
        schedule_due()
        schedule_due()
        assert db.session.scalar(db.select(db.func.count()).select_from(CheckinJob)) == 1
        assert run_one()
        task = db.session.scalar(db.select(CheckinTask))
        assert task.status == "failed" and "pending" in task.message


def test_adapters_do_not_conflate_plan_with_balance(client):
    def upstream(req):
        return httpx.Response(200, json={"data": {"remaining": 42}})
    client.application.config["HTTP_TRANSPORT"] = httpx.MockTransport(upstream)
    aid = account(client)
    assert client.post(f"/api/v1/accounts/{aid}/balance-sync", headers=ADMIN).status_code == 501
    client.application.config["BALANCE_ADAPTERS"] = {"cn": {"url": "https://plan.test/remains", "field": "data.remaining", "unit": "tokens"}}
    response = client.post(f"/api/v1/accounts/{aid}/balance-sync", headers=ADMIN)
    assert response.json["items"][0]["amount"] == "42.000000"
    assert client.get(f"/api/v1/accounts/{aid}", headers=ADMIN).json["balance"] is None
    assert client.get("/api/v1/credits?region=cn", headers=ADMIN).json["total"] == 0


def test_cross_region_database_constraint(client):
    group = client.post("/api/v1/groups", headers=ADMIN, json={"region": "global", "name": "group"}).json["data"]
    aid = account(client)
    with client.application.app_context():
        db.session.get(Account, aid).group_id = group["id"]
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_verification_does_not_trust_replaced_credentials(client):
    aid = account(client)
    def upstream(req):
        result = client.patch(f"/api/v1/accounts/{aid}", headers=ADMIN, json={"credential": "replacement"})
        assert result.status_code == 200
        return httpx.Response(200, json={"input_tokens": 1})
    client.application.config["HTTP_TRANSPORT"] = httpx.MockTransport(upstream)
    response = client.post(f"/api/v1/accounts/{aid}/verify-model", headers=ADMIN, json={"model": "m"})
    assert response.status_code == 409
    assert client.get(f"/api/v1/accounts/{aid}", headers=ADMIN).json["health"] == "unknown"


@pytest.mark.parametrize("config", [
    {"MODEL_DISCOVERY_URLS": {"cn": "http://example.test/models"}},
    {"MODEL_DISCOVERY_URLS": {"cn": "https://user:password@example.test/models"}},
    {"MODEL_DISCOVERY_URLS": {"other": "https://example.test/models"}},
    {"BALANCE_ADAPTERS": {"cn": {"url": "https://example.test", "field": "data.x"}}},
])
def test_rejects_invalid_adapter_config(config):
    with pytest.raises(RuntimeError):
        create_app({"ADMIN_TOKEN": "a" * 32, "ENCRYPTION_KEY": Fernet.generate_key(), **config})


def test_gateway_redacts_custom_headers_and_rejects_redirect(client):
    def upstream(req):
        if req.url.path.endswith("count_tokens"):
            return httpx.Response(200, json={"input_tokens": 1})
        return httpx.Response(302, headers={"location": "https://other.test"})
    client.application.config["HTTP_TRANSPORT"] = httpx.MockTransport(upstream)
    aid = account(client)
    client.post(f"/api/v1/accounts/{aid}/verify-model", headers=ADMIN, json={"model": "m"})
    response = client.post("/v1/messages", headers={"Authorization": "Bearer " + key(client),
        "anthropic-beta": "sensitive-value"}, json={"model": "m", "messages": []})
    assert response.status_code == 502
    logs = client.get("/api/v1/logs?region=cn", headers=ADMIN).json
    assert "sensitive-value" not in json.dumps(logs)
