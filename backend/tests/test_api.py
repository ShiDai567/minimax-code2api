import hashlib

import pytest
from cryptography.fernet import Fernet

from app import create_app, db
from app.models import Account, ApiKey


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
                      "ADMIN_TOKEN": "a" * 32, "ENCRYPTION_KEY": Fernet.generate_key()})
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()


def test_auth_and_region_isolation(client):
    assert client.get('/api/v1/accounts').status_code == 401
    headers = {"Authorization": "Bearer " + "a" * 32}
    for region in ("cn", "global"):
        response = client.post('/api/v1/accounts', headers=headers, json={"region": region, "name": "A", "identifier": "same", "credential": "secret"})
        assert response.status_code == 201
        assert "secret" not in response.get_data(as_text=True)
    assert len(client.get('/api/v1/accounts?region=cn', headers=headers).json['data']['items']) == 1
    assert client.post('/api/v1/accounts', headers=headers, json={"region": "cn", "name": "A", "identifier": "same", "credential": "secret"}).status_code == 409
    with client.application.app_context():
        assert b"secret" not in db.session.scalar(db.select(Account)).credential_encrypted


def test_key_only_returned_once(client):
    headers = {"Authorization": "Bearer " + "a" * 32}
    response = client.post('/api/v1/api-keys', headers=headers, json={"name": "test"})
    secret = response.json['data']['secret']
    assert secret not in client.get('/api/v1/api-keys', headers=headers).get_data(as_text=True)
    assert client.get('/api/v1/accounts', headers={"Authorization": "Bearer " + secret}).status_code == 401
    with client.application.app_context():
        assert db.session.scalar(db.select(ApiKey)).key_hash == hashlib.sha256(secret.encode()).hexdigest()
