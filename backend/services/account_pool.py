"""Account selection. A local balance never proves the upstream call will succeed."""
from django.db.models import F

from apps.accounts.models import Account
from apps.system_settings.services import get_settings
from common.problems import ApiProblem
from common.utils import utcnow


def select_account(region, strategy=None):
    config = get_settings()
    strategy = strategy or config["account"].get("strategy", "round_robin")
    queryset = Account.objects.filter(region=region, enabled=True, health="healthy")
    if strategy == "most_credits":
        queryset = queryset.filter(current_credits__isnull=False).order_by("-current_credits", "id")
    elif strategy == "recent_active":
        queryset = queryset.order_by(F("last_active_at").desc(nulls_last=True), "id")
    elif strategy == "least_used":
        queryset = queryset.order_by(F("last_active_at").asc(nulls_first=True), "id")
    else:
        queryset = queryset.order_by(F("last_active_at").asc(nulls_first=True), "id")
    account = queryset.first()
    if account is None and strategy == "most_credits":
        account = Account.objects.filter(region=region, enabled=True, health="healthy").order_by("id").first()
    if account is None:
        raise ApiProblem("No verified, enabled account in the selected region", 503, "NO_ACCOUNT")
    Account.objects.filter(id=account.id).update(last_active_at=utcnow())
    return account


def acquire(account_id):
    Account.objects.filter(id=account_id).update(inflight=F("inflight") + 1)


def release(account_id):
    Account.objects.filter(id=account_id, inflight__gt=0).update(inflight=F("inflight") - 1)
