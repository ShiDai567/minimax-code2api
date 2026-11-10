from rest_framework.views import exception_handler as drf_handler

from common.problems import ApiProblem


def exception_handler(exc, context):
    if isinstance(exc, ApiProblem):
        from rest_framework.response import Response

        return Response({"detail": exc.detail, "error": {"code": exc.code}}, status=exc.status_code)
    response = drf_handler(exc, context)
    if response is not None:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        if detail is None and isinstance(response.data, dict):
            detail = "; ".join(f"{key}: {value}" for key, value in response.data.items())
        response.data = {"detail": str(detail or "Request failed"), "error": {"code": "INVALID_INPUT"}}
    return response
