from django.db import models

from common.utils import utcnow


class ApiKey(models.Model):
    name = models.CharField(max_length=120)
    prefix = models.CharField(max_length=24)
    key_hash = models.CharField(max_length=64, unique=True)
    enabled = models.BooleanField(default=True)
    note = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    request_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=utcnow)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "apikeys_apikey"
