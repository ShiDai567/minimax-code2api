import pytest
from cryptography.fernet import Fernet

from common.encryption import decrypt, encrypt, reset_cipher
from common.problems import ApiProblem


@pytest.mark.django_db
def test_roundtrip():
    assert decrypt(encrypt("lease-token-值")) == "lease-token-值"


@pytest.mark.django_db
def test_wrong_key_is_reported_not_swallowed(settings):
    stored = encrypt("secret")
    settings.ENCRYPTION_KEY = Fernet.generate_key().decode()
    reset_cipher()
    with pytest.raises(ApiProblem) as caught:
        decrypt(stored)
    assert caught.value.code == "CREDENTIAL_UNAVAILABLE"
