from django.urls import path

from apps.api_keys.views import KeyDetailView, KeyListView

urlpatterns = [
    path("keys", KeyListView.as_view()),
    path("keys/", KeyListView.as_view()),
    path("api-keys", KeyListView.as_view()),
    path("api-keys/", KeyListView.as_view()),
    path("keys/<int:key_id>", KeyDetailView.as_view()),
    path("keys/<int:key_id>/", KeyDetailView.as_view()),
    path("api-keys/<int:key_id>", KeyDetailView.as_view()),
    path("api-keys/<int:key_id>/", KeyDetailView.as_view()),
]
