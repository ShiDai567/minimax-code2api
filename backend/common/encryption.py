from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

from common.problems import ApiProblem

_cipher = None


def cipher():
    global _cipher
    if _cipher is None:
        key = settings.ENCRYPTION_KEY
        if not key:
            raise ApiProblem("ENCRYPTION_KEY is not configured", 503, "CREDENTIAL_UNAVAILABLE")
        _cipher = Fernet(key.encode() if isinstance(key, str) else key)
    return _cipher


def encrypt(value: str) -> bytes:
    return cipher().encrypt(value.encode())


def decrypt(value: bytes) -> str:
    try:
        return cipher().decrypt(value).decode()
    except (InvalidToken, UnicodeDecodeError):
        raise ApiProblem("Stored credential cannot be decrypted", 503, "CREDENTIAL_UNAVAILABLE") from None


def reset_cipher():
    global _cipher
    _cipher = None
