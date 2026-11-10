import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

from common.utils import epoch_ms, utcnow

SALT = "console-login"
MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def _fingerprint() -> str:
    return hashlib.sha256(settings.CONSOLE_PASSWORD.encode()).hexdigest()


def password_matches(supplied: str) -> bool:
    expected = settings.CONSOLE_PASSWORD
    if not expected or not isinstance(supplied, str) or not supplied:
        return False
    return hmac.compare_digest(
        hashlib.sha256(supplied.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )


def issue_token() -> tuple[str, int]:
    token = TimestampSigner(salt=SALT).sign(_fingerprint())
    return token, epoch_ms(utcnow() + timedelta(seconds=MAX_AGE_SECONDS))


def token_valid(token: str) -> bool:
    if not settings.CONSOLE_PASSWORD or not token:
        return False
    try:
        value = TimestampSigner(salt=SALT).unsign(token, max_age=MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return hmac.compare_digest(value, _fingerprint())
