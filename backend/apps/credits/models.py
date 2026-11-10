from django.db import models

from apps.accounts.models import Account
from common.utils import utcnow


class CreditEntry(models.Model):
    KINDS = ("checkin", "api_usage", "adjustment", "credit_sync")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="ledger")
    region = models.CharField(max_length=10)
    kind = models.CharField(max_length=40)
    delta = models.DecimalField(max_digits=24, decimal_places=6)
    balance_before = models.DecimalField(max_digits=24, decimal_places=6)
    balance_after = models.DecimalField(max_digits=24, decimal_places=6)
    upstream_id = models.CharField(max_length=255, unique=True)
    request_id = models.CharField(max_length=64, blank=True, default="")
    checkin_id = models.BigIntegerField(null=True, blank=True)
    note = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(default=utcnow)

    class Meta:
        db_table = "credits_creditentry"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(balance_after=models.F("balance_before") + models.F("delta")),
                name="ledger_balances",
            )
        ]
        indexes = [models.Index(fields=["region", "created_at"])]


class BalanceSnapshot(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="snapshots")
    amount = models.DecimalField(max_digits=24, decimal_places=6)
    unit = models.CharField(max_length=80)
    provider_field = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=utcnow)

    class Meta:
        db_table = "credits_balancesnapshot"
        indexes = [models.Index(fields=["account", "created_at"])]
