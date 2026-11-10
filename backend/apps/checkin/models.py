from django.db import models

from apps.accounts.models import Account
from common.utils import utcnow


class CheckinRecord(models.Model):
    STATUSES = ("pending", "success", "failed", "skipped")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="checkins")
    region = models.CharField(max_length=10)
    day = models.DateField()
    status = models.CharField(max_length=20, default="pending")
    trigger = models.CharField(max_length=20)
    reward = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    claim_id = models.CharField(max_length=255, blank=True, default="")
    arrival = models.CharField(max_length=20, blank=True, default="")
    message = models.CharField(max_length=255, blank=True, default="")
    ledger_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=utcnow)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "checkin_checkinrecord"
        constraints = [models.UniqueConstraint(fields=["account", "day"], name="uniq_checkin_account_day")]
        indexes = [models.Index(fields=["region", "day"])]


class CheckinJob(models.Model):
    id = models.CharField(max_length=36, primary_key=True)
    region = models.CharField(max_length=10)
    status = models.CharField(max_length=20, default="queued")
    trigger = models.CharField(max_length=20, default="batch")
    schedule_key = models.CharField(max_length=80, null=True, blank=True, unique=True)
    lease_token = models.CharField(max_length=36, blank=True, default="")
    lease_until = models.DateTimeField(null=True, blank=True)
    total = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failure_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=utcnow)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "checkin_checkinjob"
        indexes = [models.Index(fields=["status", "created_at"])]


class CheckinTask(models.Model):
    job = models.ForeignKey(CheckinJob, on_delete=models.CASCADE, related_name="tasks")
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default="queued")
    message = models.CharField(max_length=255, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "checkin_checkintask"
        constraints = [models.UniqueConstraint(fields=["job", "account"], name="uniq_task_job_account")]
