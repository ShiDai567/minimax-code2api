from django.urls import path

from apps.request_logs.views import LogDetailView, LogListView

urlpatterns = [
    path("logs", LogListView.as_view()),
    path("logs/", LogListView.as_view()),
    path("logs/<str:log_id>", LogDetailView.as_view()),
    path("logs/<str:log_id>/", LogDetailView.as_view()),
]
