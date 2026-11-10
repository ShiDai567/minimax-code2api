import platform
from datetime import datetime

from django.conf import settings
from rest_framework.views import APIView

from apps.accounts.models import Account
from apps.checkin.models import CheckinJob
from apps.system_settings.services import get_settings, save_settings
from common.console_token import issue_token, password_matches
from common.pagination import envelope
from common.problems import ApiProblem
from common.utils import epoch_ms, utcnow


class SettingsView(APIView):
    def get(self, request):
        return envelope(get_settings())

    def patch(self, request):
        return envelope(save_settings(request.data))


class LoginView(APIView):
    authentication_required = False

    def post(self, request):
        if not settings.CONSOLE_PASSWORD:
            raise ApiProblem("Console password is not configured", 503, "NOT_CONFIGURED")
        body = request.data if isinstance(request.data, dict) else {}
        if not password_matches(body.get("password", "")):
            raise ApiProblem("Invalid password", 401, "UNAUTHORIZED")
        token, expires_at = issue_token()
        return envelope({"token": token, "expiresAt": expires_at})


class RuntimeView(APIView):
    def get(self, request):
        from django.db import connection

        config = get_settings()
        started = config["runtime"].get("startedAt")
        try:
            connection.ensure_connection()
            database = "operational"
        except Exception:
            database = "down"
        jobs = CheckinJob.objects.filter(status__in=("queued", "running")).count()
        expired = Account.objects.filter(health="expired").count()
        return envelope({
            "version": "1.0.0",
            "pythonVersion": platform.python_version(),
            "platform": platform.platform(),
            "startedAt": epoch_ms(datetime.fromisoformat(started)) if isinstance(started, str) else None,
            "dataSource": "live",
            "database": database,
            "queuedJobs": jobs,
            "expiredAccounts": expired,
            "upstream": {
                "cn": "https://agent.minimax.cn",
                "global": "https://agent.minimax.io",
                "health": "unknown",
            },
            "checkedAt": epoch_ms(utcnow()),
        })


