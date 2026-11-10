from django.urls import path

from apps.models_manager.views import ModelDetailView, ModelDiscoverView, ModelListView

urlpatterns = [
    path("models", ModelListView.as_view()),
    path("models/", ModelListView.as_view()),
    path("models/discover", ModelDiscoverView.as_view()),
    path("models/discover/", ModelDiscoverView.as_view()),
    path("models/<int:model_id>", ModelDetailView.as_view()),
    path("models/<int:model_id>/", ModelDetailView.as_view()),
]
