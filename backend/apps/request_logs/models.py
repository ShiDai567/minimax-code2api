import uuid

from django.db import models

from apps.accounts.models import Account
from apps.api_keys.models import ApiKey
from common.utils import utcnow


class RequestLog(models.Model):
    id = models.CharField(max_length=36, primary_key=True, default=uuid.uuid4)
    account = models.ForeignKey(Account, null=True, on_delete=models.SET_NULL)
    api_key = models.ForeignKey(ApiKey, null=True, on_delete=models.SET_NULL)
    region = models.CharField(max_length=10)
    protocol = models.CharField(max_length=30)
    endpoint = models.CharField(max_length=80)
    model = models.CharField(max_length=255)
    resolved_model = models.CharField(max_length=255, blank=True, default="")
    http_status = models.IntegerField()
    latency_ms = models.IntegerField(default=0)
    stream = models.BooleanField(default=False)
    input_tokens = models.IntegerField(null=True, blank=True)
    output_tokens = models.IntegerField(null=True, blank=True)
    consumed_credits = models.DecimalField(max_digits=24, decimal_places=6, null=True, blank=True)
    ledger_id = models.BigIntegerField(null=True, blank=True)
    error_message = models.CharField(max_length=255, blank=True, default="")
    headers = models.JSONField(default=dict)
    client_ip = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(default=utcnow)

    class Meta:
        db_table = "requestlogs_requestlog"
        indexes = [models.Index(fields=["region", "-created_at"]), models.Index(fields=["-created_at"])]
