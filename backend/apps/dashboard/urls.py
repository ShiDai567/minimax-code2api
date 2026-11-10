from django.http import JsonResponse
from django.urls import path

from apps.dashboard.views import CapabilitiesView, DashboardView, HealthView

urlpatterns = [
    path("dashboard", DashboardView.as_view()),
    path("dashboard/", DashboardView.as_view()),
    path("dashboard/overview", DashboardView.as_view()),
    path("dashboard/overview/", DashboardView.as_view()),
    path("capabilities", CapabilitiesView.as_view()),
    path("capabilities/", CapabilitiesView.as_view()),
    path("health", HealthView.as_view()),
    path("health/", HealthView.as_view()),
]


def public_health(_request):
    return JsonResponse({"status": "ok", "version": "1.0.0"})
