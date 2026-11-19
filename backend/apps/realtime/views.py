"""Выдача токенов Centrifugo.

Клиент не может подписаться на произвольный канал: в конфиге Centrifugo стоит
``allow_subscribe_for_client: false``. Токен на подписку выдаёт Django, и только
после проверки, что канал этому пользователю действительно доступен. Иначе
любой авторизованный мог бы подписаться на ``chat:<чужой_id>`` и читать чужую
переписку в реальном времени.
"""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chats.views import chats_for

from .publisher import make_connection_token, make_subscription_token

CHAT_CHANNEL_RE = re.compile(r"^chat:(\d+)$")
USER_CHANNEL_RE = re.compile(r"^user:(\d+)$")


class ConnectionTokenView(APIView):
    """POST /api/realtime/token — JWT для подключения к websocket."""

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> Response:
        return Response(
            {
                "token": make_connection_token(request.user.pk),
                "ws_url": settings.CENTRIFUGO_WS_URL,
            }
        )


class SubscriptionTokenView(APIView):
    """POST /api/realtime/subscribe — JWT на конкретный канал."""

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request) -> Response:
        channel = str(request.data.get("channel") or "").strip()
        if not channel:
            return _error("Укажите channel")

        if not self._allowed(request.user, channel):
            # 403 здесь уместен: клиент уже знает имя канала, которое сам
            # запросил, поэтому скрывать существование нечего.
            return _error("Нет доступа к этому каналу", status.HTTP_403_FORBIDDEN)

        return Response({"token": make_subscription_token(request.user.pk, channel)})

    @staticmethod
    def _allowed(user: Any, channel: str) -> bool:
        if match := CHAT_CHANNEL_RE.match(channel):
            # Тот же источник правды о доступе, что и в REST: пользователь
            # должен состоять в чате.
            return chats_for(user).filter(pk=int(match.group(1))).exists()
        if match := USER_CHANNEL_RE.match(channel):
            # Свой личный канал — можно, чужой — нельзя.
            return int(match.group(1)) == user.pk
        return False


def _error(message: str, code: int = status.HTTP_400_BAD_REQUEST) -> Response:
    return Response({"error": {"code": "bad_request", "message": message}}, status=code)
