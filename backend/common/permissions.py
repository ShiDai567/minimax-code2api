import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission

from common.console_token import token_valid


def _bearer(request) -> str:
    header = request.headers.get("Authorization", "")
    return header[7:] if header.startswith("Bearer ") else ""


class AdminTokenPermission(BasePermission):
    message = "Authentication required"

    def has_permission(self, request, view):
        if getattr(view, "authentication_required", True) is False:
            return True
        expected = settings.ADMIN_TOKEN
        supplied = _bearer(request)
        if not expected or not supplied or len(supplied) != len(expected):
            return False
        return hmac.compare_digest(supplied.encode(), expected.encode())


class SessionPermission(AdminTokenPermission):
    """Admin token, or a signed token issued after the console password check. Never an API key."""

    def has_permission(self, request, view):
        if super().has_permission(request, view):
            return True
        if getattr(view, "authentication_required", True) is False:
            return False
        return token_valid(_bearer(request))
