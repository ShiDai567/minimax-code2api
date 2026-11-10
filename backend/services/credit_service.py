"""Confirmed ledger only. A reported reward is not a ledger entry."""
from decimal import Decimal

from django.db import IntegrityError, transaction

from adapters import adapter_for
from adapters.base import UpstreamError
from apps.accounts.models import Account
from apps.credits.models import BalanceSnapshot, CreditEntry
from common.problems import ApiProblem
from common.utils import utcnow


def apply_delta(*, account_id, kind, delta, upstream_id, note="", request_id="", checkin_id=None, region=""):
    """Post a confirmed movement. Caller must already know the delta is real."""
    delta = Decimal(delta)
    try:
        with transaction.atomic():
            account = Account.objects.select_for_update().get(id=account_id)
            if account.current_credits is None:
                raise ApiProblem("No confirmed balance to post against", 409, "UNCONFIRMED_BALANCE")
            before = account.current_credits
            after = before + delta
            if after < 0:
                raise ApiProblem("Confirmed balance would become negative", 409, "INSUFFICIENT_CREDITS")
            entry = CreditEntry(
                account=account,
                region=region or account.region,
                kind=kind,
                delta=delta,
                balance_before=before,
                balance_after=after,
                upstream_id=upstream_id,
                request_id=request_id,
                checkin_id=checkin_id,
                note=note[:255],
            )
            entry.save()
            account.current_credits = after
            account.save(update_fields=["current_credits", "updated_at"])
            return entry
    except IntegrityError:
        return CreditEntry.objects.filter(upstream_id=upstream_id).first()


def establish_baseline(account_id, amount, upstream_id, note):
    """First confirmed observation. Delta is zero: history before this point is unknown, not invented."""
    amount = Decimal(amount)
    with transaction.atomic():
        account = Account.objects.select_for_update().get(id=account_id)
        if account.current_credits is not None:
            return None
        entry = CreditEntry(
            account=account,
            region=account.region,
            kind="credit_sync",
            delta=Decimal(0),
            balance_before=amount,
            balance_after=amount,
            upstream_id=upstream_id,
            note=note[:255],
        )
        try:
            entry.save()
        except IntegrityError:
            return CreditEntry.objects.filter(upstream_id=upstream_id).first()
        account.current_credits = amount
        account.credits_synced_at = utcnow()
        account.save(update_fields=["current_credits", "credits_synced_at", "updated_at"])
        return entry


def sync_credits(account):
    if not account.enabled:
        raise ApiProblem("Account is disabled")
    try:
        reported = adapter_for(account).get_credits(account)
    except UpstreamError as exc:
        raise ApiProblem(exc.message, exc.status_code, exc.code) from None
    snapshot = BalanceSnapshot.objects.create(
        account=account,
        amount=reported["amount"],
        unit=reported["unit"],
        provider_field=reported["provider_field"],
    )
    amount = reported["amount"]
    stamp = int(utcnow().timestamp() * 1000)
    if account.current_credits is None:
        establish_baseline(account.id, amount, f"baseline:{account.id}", "First confirmed upstream snapshot; prior history unknown")
    else:
        with transaction.atomic():
            locked = Account.objects.select_for_update().get(id=account.id)
            delta = amount - locked.current_credits
            locked.credits_synced_at = utcnow()
            locked.save(update_fields=["credits_synced_at", "updated_at"])
        if delta != 0:
            apply_delta(
                account_id=account.id,
                kind="credit_sync",
                delta=delta,
                upstream_id=f"sync:{account.id}:{stamp}",
                note="Upstream snapshot difference; not attributed to a single request",
            )
    account.refresh_from_db()
    return account, snapshot


def adjust(account, delta, note):
    if account.current_credits is None:
        raise ApiProblem("Sync a confirmed balance before posting a manual adjustment", 409, "UNCONFIRMED_BALANCE")
    stamp = int(utcnow().timestamp() * 1000)
    return apply_delta(
        account_id=account.id,
        kind="adjustment",
        delta=Decimal(delta),
        upstream_id=f"adjust:{account.id}:{stamp}",
        note=note or "Manual adjustment",
    )


def reconcile_after_request(account_id, request_id):
    """Attribute a balance drop to one request only when this account had no sibling in flight."""
    from django.conf import settings

    if not settings.BALANCE_ADAPTERS:
        return None
    account = Account.objects.filter(id=account_id).first()
    if account is None or account.region not in settings.BALANCE_ADAPTERS:
        return None
    try:
        reported = adapter_for(account).get_credits(account)
    except UpstreamError:
        return None
    with transaction.atomic():
        locked = Account.objects.select_for_update().get(id=account_id)
        if locked.inflight != 0 or locked.current_credits is None:
            locked.credits_synced_at = utcnow()
            locked.save(update_fields=["credits_synced_at", "updated_at"])
            return None
        delta = reported["amount"] - locked.current_credits
    if delta == 0:
        return None
    if delta > 0:
        return apply_delta(
            account_id=account_id,
            kind="credit_sync",
            delta=delta,
            upstream_id=f"sync:{account_id}:{request_id}",
            note="Upstream balance increased during an idle window",
            request_id=request_id,
        )
    return apply_delta(
        account_id=account_id,
        kind="api_usage",
        delta=delta,
        upstream_id=f"request:{request_id}",
        note="Upstream balance difference while this account served a single request",
        request_id=request_id,
    )
