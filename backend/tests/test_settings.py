import pytest


@pytest.mark.django_db
def test_settings_roundtrip_and_validation(client):
    saved = client.patch("/api/v1/settings", {"checkin": {"auto": True, "regions": ["cn"], "time": "08:30"}}, format="json")
    assert saved.status_code == 200
    assert saved.json()["data"]["checkin"]["time"] == "08:30"
    assert saved.json()["source"] == "live"

    bad = client.patch("/api/v1/settings", {"checkin": {"time": "25:00"}}, format="json")
    assert bad.status_code == 422

    read = client.get("/api/v1/settings")
    assert read.json()["data"]["checkin"]["time"] == "08:30"


@pytest.mark.django_db
def test_login_accepts_only_the_env_password(client, settings):
    settings.CONSOLE_PASSWORD = "correct-horse"
    anonymous = client.__class__()
    refused = anonymous.post("/api/v1/auth/login", {"password": "wrong"}, format="json")
    assert refused.status_code == 401
    logged_in = anonymous.post("/api/v1/auth/login", {"password": "correct-horse"}, format="json")
    assert logged_in.status_code == 200
    token = logged_in.json()["data"]["token"]
    anonymous.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert anonymous.get("/api/v1/settings").status_code == 200

    settings.CONSOLE_PASSWORD = "rotated"
    assert anonymous.get("/api/v1/settings").status_code == 403
    anonymous.credentials()
    assert anonymous.post("/api/v1/auth/login", {"password": "correct-horse"}, format="json").status_code == 401


@pytest.mark.django_db
def test_login_requires_a_configured_password(client, settings):
    settings.CONSOLE_PASSWORD = ""
    anonymous = client.__class__()
    missing = anonymous.post("/api/v1/auth/login", {"password": "anything"}, format="json")
    assert missing.status_code == 503


@pytest.mark.django_db
def test_health_is_public(client):
    anonymous = client.__class__()
    assert anonymous.get("/api/v1/health/").status_code == 200
    assert anonymous.get("/health").status_code == 200
