from decimal import Decimal

import pytest

from apps.accounts.models import Account
from apps.credits.models import CreditEntry
from common.encryption import encrypt
from common.problems import ApiProblem
from services.credit_service import apply_delta, establish_baseline


@pytest.mark.django_db
def test_ledger_constraint_rejects_an_unbalanced_entry():
    account = Account.objects.create(region="cn", name="a", identifier="a@example.com", credential_encrypted=encrypt("t"))
    account.current_credits = Decimal("10")
    account.save()
    with pytest.raises(Exception):
        CreditEntry.objects.create(
            account=account, region="cn", kind="adjustment", delta=Decimal("1"),
            balance_before=Decimal("10"), balance_after=Decimal("99"), upstream_id="bad",
        )


@pytest.mark.django_db
def test_first_snapshot_is_a_zero_delta_baseline(account):
    entry = establish_baseline(account.id, Decimal("100"), "baseline:1", "first")
    assert entry.delta == 0
    assert entry.balance_before == entry.balance_after == Decimal("100")
    account.refresh_from_db()
    assert account.current_credits == Decimal("100")
    assert establish_baseline(account.id, Decimal("200"), "baseline:2", "again") is None


@pytest.mark.django_db
def test_posting_without_a_baseline_is_refused(account):
    with pytest.raises(ApiProblem) as caught:
        apply_delta(account_id=account.id, kind="adjustment", delta=Decimal("1"), upstream_id="x")
    assert caught.value.code == "UNCONFIRMED_BALANCE"


@pytest.mark.django_db
def test_duplicate_upstream_id_is_idempotent(account):
    establish_baseline(account.id, Decimal("5"), "baseline:1", "first")
    first = apply_delta(account_id=account.id, kind="adjustment", delta=Decimal("1"), upstream_id="same")
    second = apply_delta(account_id=account.id, kind="adjustment", delta=Decimal("1"), upstream_id="same")
    assert first.id == second.id
    assert CreditEntry.objects.count() == 2
