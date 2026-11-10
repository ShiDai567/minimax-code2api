from django.urls import path

from apps.gateway.views import GatewayRestartView, GatewayStartView, GatewayStatusView, GatewayStopView, RuntimeLogView

urlpatterns = [
    path("gateway/status", GatewayStatusView.as_view()),
    path("gateway/status/", GatewayStatusView.as_view()),
    path("gateway/start", GatewayStartView.as_view()),
    path("gateway/start/", GatewayStartView.as_view()),
    path("gateway/stop", GatewayStopView.as_view()),
    path("gateway/stop/", GatewayStopView.as_view()),
    path("gateway/restart", GatewayRestartView.as_view()),
    path("gateway/restart/", GatewayRestartView.as_view()),
    path("gateway/runtime-logs", RuntimeLogView.as_view()),
    path("gateway/runtime-logs/", RuntimeLogView.as_view()),
]
