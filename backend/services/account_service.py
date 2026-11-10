"""Account lifecycle. Views stay thin; credential handling lives here."""
import json
import uuid

from django.db import IntegrityError, transaction

from adapters import adapter_for
from adapters.base import UpstreamError
from apps.accounts.models import Account, AccountGroup
from apps.system_settings.models import AuditLog
from common.encryption import encrypt
from common.problems import ApiProblem
from common.utils import text, utcnow


def audit(action, target=""):
    AuditLog.objects.create(action=action, target=str(target)[:120])


def validate_group(group_id, region):
    if group_id in (None, ""):
        return None
    if type(group_id) is not int:
        raise ApiProblem("Invalid group_id")
    group = AccountGroup.objects.filter(id=group_id).first()
    if group is None:
        raise ApiProblem("Resource not found", 404, "NOT_FOUND")
    if group.region != region:
        raise ApiProblem("Accounts and groups must belong to the same region")
    return group


def create_account(body, verify_model=""):
    region = body.get("region")
    if region not in ("cn", "global"):
        raise ApiProblem("region must be cn or global")
    credential = text(body.get("credential", ""), "credential", 16384)
    account = Account(
        region=region,
        name=text(body.get("name", ""), "name", 120),
        identifier=text(body.get("identifier", ""), "identifier", 255),
        credential_encrypted=encrypt(credential),
        real_user_id=text(body.get("real_user_id", ""), "real_user_id", 255, required=False),
        note=text(body.get("note", ""), "note", 4000, required=False),
        group=validate_group(body.get("group_id"), region),
        session_id=str(uuid.uuid4()),
        health="unknown",
    )
    try:
        account.save()
    except IntegrityError:
        raise ApiProblem("An account with this identifier already exists in the region", 409, "CONFLICT") from None
    audit("account.create", account.id)
    if verify_model:
        verify_account(account, verify_model)
        account.refresh_from_db()
    return account


def update_account(account, body):
    if "name" in body:
        account.name = text(body.get("name", ""), "name", 120)
    if "identifier" in body:
        account.identifier = text(body.get("identifier", ""), "identifier", 255)
    if "note" in body:
        account.note = text(body.get("note", ""), "note", 4000, required=False)
    if "real_user_id" in body:
        account.real_user_id = text(body.get("real_user_id", ""), "real_user_id", 255, required=False)
    if "group_id" in body:
        account.group = validate_group(body.get("group_id"), account.region)
    if "enabled" in body:
        if type(body["enabled"]) is not bool:
            raise ApiProblem("enabled must be a boolean")
        account.enabled = body["enabled"]
    if "credential" in body:
        credential = text(body.get("credential", ""), "credential", 16384)
        account.credential_encrypted = encrypt(credential)
        account.health = "unknown"
        account.health_reason = ""
        account.verified_at = None
        account.session_id = str(uuid.uuid4())
        account.error_count = 0
    try:
        account.save()
    except IntegrityError:
        raise ApiProblem("An account with this identifier already exists in the region", 409, "CONFLICT") from None
    audit("account.update", account.id)
    return account


def delete_account(account):
    from apps.checkin.models import CheckinRecord
    from apps.credits.models import CreditEntry

    if CheckinRecord.objects.filter(account=account).exists() or CreditEntry.objects.filter(account=account).exists():
        raise ApiProblem("Account has history; disable it instead", 409, "RESOURCE_IN_USE")
    account_id = account.id
    account.delete()
    audit("account.delete", account_id)


def import_accounts(region, rows):
    if region not in ("cn", "global"):
        raise ApiProblem("region must be cn or global")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ApiProblem("accounts must contain 1..200 objects")
    created, failed = [], []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            failed.append({"index": index, "detail": "Expected an object"})
            continue
        try:
            created.append(create_account({**row, "region": region}, row.get("model") or ""))
        except ApiProblem as exc:
            failed.append({"index": index, "detail": exc.detail})
    return created, failed


def verify_account(account, model):
    if not account.enabled:
        raise ApiProblem("Account is disabled")
    model = text(model, "model", 255)
    verified_credential = bytes(account.credential_encrypted)
    try:
        response, client = adapter_for(account).count_tokens(account, {"model": model, "messages": [{"role": "user", "content": "test"}]})
    except UpstreamError as exc:
        _mark(account, verified_credential, "error", exc.message[:255], None)
        raise ApiProblem(exc.message, exc.status_code, exc.code) from None
    try:
        raw = response.read()
        if response.status_code in (401, 403):
            _mark(account, verified_credential, "expired", "Upstream rejected credential", None)
        elif 200 <= response.status_code < 300:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or type(parsed.get("input_tokens")) is not int:
                raise ApiProblem("Unexpected verification response", 502, "UPSTREAM_ERROR")
            _mark(account, verified_credential, "healthy", "", utcnow())
        else:
            raise ApiProblem(f"Upstream returned HTTP {response.status_code}", 502, "UPSTREAM_ERROR")
    except (ValueError, UnicodeDecodeError):
        raise ApiProblem("Unexpected verification response", 502, "UPSTREAM_ERROR") from None
    finally:
        response.close()
        client.close()
    account.refresh_from_db()
    return account


def _mark(account, credential, health, reason, verified_at):
    changed = Account.objects.filter(id=account.id, credential_encrypted=credential, enabled=True).update(
        health=health,
        health_reason=reason,
        verified_at=verified_at,
        error_count=0 if health == "healthy" else account.error_count,
        updated_at=utcnow(),
    )
    if changed != 1:
        raise ApiProblem("Account changed during verification; retry", 409, "ACCOUNT_CHANGED")


def set_enabled(account, enabled):
    account.enabled = enabled
    account.save(update_fields=["enabled", "updated_at"])
    audit("account.enable" if enabled else "account.disable", account.id)
    return account


def note_upstream_failure(account_id, permanent):
    """Network timeouts must not permanently invalidate an account."""
    from apps.system_settings.services import get_settings

    threshold = get_settings()["account"]["errorThreshold"]
    with transaction.atomic():
        account = Account.objects.select_for_update().get(id=account_id)
        if permanent:
            account.health = "expired"
            account.health_reason = "Upstream rejected credential"
            account.last_error = account.health_reason
        else:
            account.error_count += 1
            account.last_error = "Upstream request failed"
            if account.error_count >= threshold and get_settings()["account"]["autoDisableExpired"]:
                account.health = "error"
                account.health_reason = "Repeated upstream failures"
        account.save()
