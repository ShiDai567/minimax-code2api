from django.apps import AppConfig


class ModelsManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.models_manager"
    label = "models_manager"
    verbose_name = "Models"
