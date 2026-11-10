"""Shared result types only. HTTP details stay in each region adapter."""
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class CheckinOutcome:
    status: str
    message: str
    reward: Decimal | None = None
    claim_id: str = ""


@dataclass
class AccountInfo:
    identifier: str = ""
    name: str = ""
    raw: dict = field(default_factory=dict)


class UpstreamError(Exception):
    def __init__(self, message, status_code=502, code="UPSTREAM_ERROR", permanent=False):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.permanent = permanent


class BaseMiniMaxAdapter:
    region = ""
    gateway_origin = ""
    public_origin = ""
    language = "en"

    def authenticate(self, credentials: dict) -> dict:
        token = credentials.get("credential") or credentials.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise UpstreamError("credential is required", 422, "INVALID_INPUT")
        return {"access_token": token.strip(), "real_user_id": (credentials.get("real_user_id") or "").strip()}

    def refresh_token(self, account):
        raise UpstreamError("Upstream token refresh is not implemented; no verified refresh endpoint", 501, "UNSUPPORTED")

    def get_account_info(self, account) -> AccountInfo:
        return AccountInfo(identifier=account.identifier, name=account.name)

    def checkin(self, account) -> CheckinOutcome:
        raise NotImplementedError

    def get_credits(self, account):
        raise NotImplementedError

    def generate(self, account, body, headers=None, suffix="messages"):
        raise NotImplementedError

    def count_tokens(self, account, body):
        return self.generate(account, body, suffix="messages/count_tokens")

    def list_models(self, account):
        raise NotImplementedError
