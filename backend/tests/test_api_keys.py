import hashlib

import pytest

from apps.api_keys.models import ApiKey


@pytest.mark.django_db
def test_secret_is_shown_once_and_only_its_hash_is_stored(client):
    created = client.post("/api/v1/keys", {"name": "生产"}, format="json")
    assert created.status_code == 201
    secret = created.json()["data"]["secret"]
    assert secret.startswith("sk-m2a-")
    stored = ApiKey.objects.get()
    assert secret not in str(stored.key_hash)
    assert stored.key_hash == hashlib.sha256(secret.encode()).hexdigest()

    listed = client.get("/api/v1/keys")
    body = listed.json()["data"]["items"][0]
    assert secret not in str(body)
    assert body["masked"].endswith("••••••••")
