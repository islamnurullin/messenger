"""Эндпоинты аккаунтов.

Регистрация и вход возвращают сразу пару токенов: клиенту (их три) не нужен
отдельный round-trip за access после успешной регистрации. Обновление токена
отдаёт только access — refresh остаётся прежним, чтобы не разлогинивать
остальные вкладки при каждой ротации.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import LoginSerializer, ProfileSerializer, RegisterSerializer

User = get_user_model()


def _token_pair(user: Any) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class RegisterView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def post(self, request: Request) -> Response:
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {"user": ProfileSerializer(user).data, **_token_pair(user)},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = (AllowAny,)
    authentication_classes = ()

    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.touch_last_seen()
        return Response({"user": ProfileSerializer(user).data, **_token_pair(user)})


class MeView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> Response:
        return Response(ProfileSerializer(request.user).data)

    def patch(self, request: Request) -> Response:
        # request.user, а не id из URL: чужой профиль отредактировать нечем —
        # такого маршрута просто нет.
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
