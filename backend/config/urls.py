from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.dashboard.urls import public_health
from apps.gateway.proxy import gateway_patterns

urlpatterns = [
    path("health", public_health),
    path("health/", public_health),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.checkin.urls")),
    path("api/v1/", include("apps.credits.urls")),
    path("api/v1/", include("apps.api_keys.urls")),
    path("api/v1/", include("apps.models_manager.urls")),
    path("api/v1/", include("apps.request_logs.urls")),
    path("api/v1/", include("apps.system_settings.urls")),
    path("api/v1/", include("apps.gateway.urls")),
    path("api/v1/", include("apps.dashboard.urls")),
    *gateway_patterns,
]
