import hashlib
import hmac
import secrets

from cryptography.fernet import Fernet

from app.core.config import get_settings


def _fernet() -> Fernet:
    key = get_settings().encryption_key
    if not key:
        raise RuntimeError("ENCRYPTION_KEY must be configured before storing account credentials")
    return Fernet(key.encode())


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode()).decode()


def hash_api_key(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_api_key(value: str, digest: str) -> bool:
    return hmac.compare_digest(hash_api_key(value), digest)


def new_api_key() -> str:
    return "sk-m2a-" + secrets.token_urlsafe(32)


def mask_secret(value: str) -> str:
    return value[:9] + "••••••••" + value[-4:]
