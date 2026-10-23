"""Единый формат ошибок API.

DRF по умолчанию отдаёт разные формы для ValidationError и для прочих исключений,
из-за чего клиенту (а их три) приходится писать три разных парсера. Приводим всё
к виду ``{"error": {"code": "...", "message": "...", "details": {...}}}``.
"""

from __future__ import annotations

from typing import Any

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _code_for(response_status: int) -> str:
    return {
        status.HTTP_400_BAD_REQUEST: "bad_request",
        status.HTTP_401_UNAUTHORIZED: "unauthorized",
        status.HTTP_403_FORBIDDEN: "forbidden",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_429_TOO_MANY_REQUESTS: "throttled",
    }.get(response_status, "server_error")


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = drf_exception_handler(exc, context)

    if response is None:
        # Не-DRF исключение: DRF вернёт None, Django отдаст 500 HTML.
        # Превращаем в JSON, чтобы клиенты не пытались парсить HTML.
        return Response(
            {"error": {"code": "server_error", "message": "Внутренняя ошибка сервера"}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    detail = response.data
    if isinstance(exc, APIException) and isinstance(detail, list | dict):
        message = str(getattr(exc, "detail", "Ошибка запроса"))
        details = detail
    else:
        message = "Ошибка запроса"
        details = detail

    response.data = {
        "error": {
            "code": _code_for(response.status_code),
            "message": message,
            "details": details,
        }
    }
    return response
