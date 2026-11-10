from django.db import models

from common.utils import utcnow


class UpstreamModel(models.Model):
    region = models.CharField(max_length=10)
    model_id = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    enabled = models.BooleanField(default=True)
    protocols = models.JSONField(default=list)
    source = models.CharField(max_length=20)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=utcnow)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "models_upstreammodel"
        constraints = [models.UniqueConstraint(fields=["region", "model_id"], name="uniq_model_region_id")]
