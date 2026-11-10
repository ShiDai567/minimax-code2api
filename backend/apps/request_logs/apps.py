from django.apps import AppConfig


class RequestLogsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.request_logs"
    label = "request_logs"
    verbose_name = "Request logs"
