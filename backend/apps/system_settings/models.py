from django.db import models

from common.utils import utcnow


class Setting(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    value = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "systemsettings_setting"


class AuditLog(models.Model):
    actor = models.CharField(max_length=64, default="admin")
    action = models.CharField(max_length=64)
    target = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(default=utcnow)

    class Meta:
        db_table = "systemsettings_auditlog"
        indexes = [models.Index(fields=["-created_at"])]


class RuntimeLog(models.Model):
    level = models.CharField(max_length=10)
    message = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=utcnow)

    class Meta:
        db_table = "systemsettings_runtimelog"
        indexes = [models.Index(fields=["-created_at"])]
