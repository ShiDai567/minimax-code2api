import uuid

from django.db import models

from common.utils import utcnow


def new_session_id():
    return str(uuid.uuid4())


class AccountGroup(models.Model):
    STRATEGIES = ("round_robin", "most_credits", "recent_active", "least_used")
    region = models.CharField(max_length=10)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    strategy = models.CharField(max_length=20, default="round_robin")
    created_at = models.DateTimeField(default=utcnow)

    class Meta:
        db_table = "accounts_accountgroup"
        constraints = [
            models.UniqueConstraint(fields=["region", "name"], name="uniq_group_region_name"),
            models.UniqueConstraint(fields=["id", "region"], name="uniq_group_id_region"),
            models.CheckConstraint(condition=models.Q(region__in=["cn", "global"]), name="group_region_valid"),
        ]


class Account(models.Model):
    HEALTH = ("unknown", "healthy", "error", "expired")
    region = models.CharField(max_length=10)
    name = models.CharField(max_length=120)
    identifier = models.CharField(max_length=255)
    credential_encrypted = models.BinaryField()
    real_user_id = models.CharField(max_length=255, blank=True, default="")
    session_id = models.CharField(max_length=36, default=new_session_id)
    group = models.ForeignKey(AccountGroup, null=True, blank=True, on_delete=models.SET_NULL, related_name="accounts")
    enabled = models.BooleanField(default=True)
    health = models.CharField(max_length=20, default="unknown")
    health_reason = models.CharField(max_length=255, blank=True, default="")
    verified_at = models.DateTimeField(null=True, blank=True)
    last_active_at = models.DateTimeField(null=True, blank=True)
    last_checkin_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True, default="")
    note = models.TextField(blank=True, default="")
    current_credits = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    credits_synced_at = models.DateTimeField(null=True, blank=True)
    inflight = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=utcnow)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_account"
        constraints = [
            models.UniqueConstraint(fields=["region", "identifier"], name="uniq_account_region_identifier"),
            models.CheckConstraint(condition=models.Q(region__in=["cn", "global"]), name="account_region_valid"),
            models.CheckConstraint(condition=models.Q(health__in=["unknown", "healthy", "error", "expired"]), name="account_health_valid"),
        ]
        indexes = [models.Index(fields=["region", "enabled", "health"])]

    @property
    def status(self):
        if not self.enabled:
            return "disabled"
        return "error" if self.health == "unknown" else self.health
