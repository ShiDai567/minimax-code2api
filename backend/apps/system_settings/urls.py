from django.urls import path

from apps.system_settings.views import LoginView, RuntimeView, SettingsView

urlpatterns = [
    path("settings", SettingsView.as_view()),
    path("settings/", SettingsView.as_view()),
    path("auth/login", LoginView.as_view()),
    path("auth/login/", LoginView.as_view()),
    path("runtime", RuntimeView.as_view()),
    path("runtime/", RuntimeView.as_view()),
]
