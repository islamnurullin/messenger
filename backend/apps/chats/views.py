"""Эндпоинты чатов.

Правило доступа одно на все ручки: **не-участник получает 404, а не 403**.
403 подтверждает существование чата — по нему можно перебором выяснить, какие
id заняты, и косвенно узнать о переписках, в которых человек не состоит.
Спрятать существование важнее, чем дать точный код ошибки.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListCreateAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Chat, ChatMember
from .serializers import (
    AddMemberSerializer,
    ChatCreateSerializer,
    ChatMemberSerializer,
    ChatSerializer,
    MarkReadSerializer,
)

User = get_user_model()


def chats_for(user: Any) -> QuerySet[Chat]:
    """Чаты, где пользователь состоит. Единственный источник правды о доступе."""
    return Chat.objects.filter(members__user=user)


def build_context(user: Any, chats: list[Chat]) -> dict[str, Any]:
    """Собирает membership/peers/counts одним пакетом запросов.

    Без этого список из 50 чатов генерирует ~150 запросов: по одному на
    membership, на собеседника и на количество участников.
    """
    chat_ids = [c.pk for c in chats]
    memberships = {m.chat_id: m for m in ChatMember.objects.filter(user=user, chat_id__in=chat_ids)}
    counts = {
        row["chat_id"]: row["total"]
        for row in ChatMember.objects.filter(chat_id__in=chat_ids)
        .values("chat_id")
        .annotate(total=Count("id"))
    }

    # Собеседники личных чатов: один запрос на все диалоги.
    direct_ids = [c.pk for c in chats if c.type == Chat.Type.DIRECT]
    peers: dict[int, Any] = {}
    if direct_ids:
        for row in (
            ChatMember.objects.filter(chat_id__in=direct_ids)
            .exclude(user=user)
            .select_related("user")
        ):
            peers[row.chat_id] = row.user

    return {"memberships": memberships, "member_counts": counts, "peers": peers}


class ChatListCreateView(ListCreateAPIView):
    permission_classes = (IsAuthenticated,)

    def get_queryset(self) -> QuerySet[Chat]:
        return chats_for(self.request.user).distinct()

    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        chats = list(self.get_queryset())
        serializer = ChatSerializer(chats, many=True, context=build_context(request.user, chats))
        return Response(serializer.data)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = ChatCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["type"] == Chat.Type.DIRECT:
            chat, created = self._get_or_create_direct(request.user, data["peer"])
        else:
            chat, created = self._create_group(request.user, data)

        payload = ChatSerializer(chat, context=build_context(request.user, [chat])).data
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @staticmethod
    def _get_or_create_direct(user: Any, peer: Any) -> tuple[Chat, bool]:
        key = Chat.build_direct_key(user.pk, peer.pk)
        # Сначала ищем существующий: повторное открытие диалога — обычное дело,
        # и оно не должно ни создавать чат, ни падать на уникальном индексе.
        existing = Chat.objects.filter(direct_key=key).first()
        if existing is not None:
            return existing, False

        try:
            with transaction.atomic():
                chat = Chat.objects.create(type=Chat.Type.DIRECT, direct_key=key, created_by=user)
                ChatMember.objects.bulk_create(
                    [
                        ChatMember(chat=chat, user=user, role=ChatMember.Role.MEMBER),
                        ChatMember(chat=chat, user=peer, role=ChatMember.Role.MEMBER),
                    ]
                )
        except IntegrityError:
            # Гонка: собеседник успел создать тот же чат между нашим SELECT и INSERT.
            # Индекс сработал — забираем победивший чат.
            return Chat.objects.get(direct_key=key), False
        return chat, True

    @staticmethod
    def _create_group(user: Any, data: dict[str, Any]) -> tuple[Chat, bool]:
        with transaction.atomic():
            chat = Chat.objects.create(type=data["type"], title=data["title"], created_by=user)
            ChatMember.objects.bulk_create(
                [ChatMember(chat=chat, user=user, role=ChatMember.Role.OWNER)]
                + [
                    ChatMember(chat=chat, user=member, role=ChatMember.Role.MEMBER)
                    for member in data["members"]
                ]
            )
        return chat, True


class ChatDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request, chat_id: int) -> Response:
        chat = self._get_chat(request.user, chat_id)
        return Response(ChatSerializer(chat, context=build_context(request.user, [chat])).data)

    @staticmethod
    def _get_chat(user: Any, chat_id: int) -> Chat:
        return get_object_or_404(chats_for(user), pk=chat_id)


class ChatMembersView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request, chat_id: int) -> Response:
        chat = get_object_or_404(chats_for(request.user), pk=chat_id)
        members = chat.members.select_related("user").order_by("joined_at", "id")
        return Response(ChatMemberSerializer(members, many=True).data)

    def post(self, request: Request, chat_id: int) -> Response:
        chat = get_object_or_404(chats_for(request.user), pk=chat_id)
        if chat.type == Chat.Type.DIRECT:
            return Response(
                {
                    "error": {
                        "code": "bad_request",
                        "message": "В личный чат нельзя добавлять людей",
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AddMemberSerializer(data=request.data, context={})
        serializer.is_valid(raise_exception=True)
        new_user = serializer.context["user"]

        if ChatMember.objects.filter(chat=chat, user=new_user).exists():
            return Response(
                {"error": {"code": "conflict", "message": "Пользователь уже в чате"}},
                status=status.HTTP_409_CONFLICT,
            )

        member = ChatMember.objects.create(chat=chat, user=new_user)
        return Response(ChatMemberSerializer(member).data, status=status.HTTP_201_CREATED)


class MarkReadView(APIView):
    """Отметка «дочитал до seq». Монотонна: назад не откатывается."""

    permission_classes = (IsAuthenticated,)

    def post(self, request: Request, chat_id: int) -> Response:
        chat = get_object_or_404(chats_for(request.user), pk=chat_id)
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        target = min(serializer.validated_data["last_read_seq"], chat.last_seq)
        updated = ChatMember.objects.filter(
            chat=chat, user=request.user, last_read_seq__lt=target
        ).update(last_read_seq=target)

        member = ChatMember.objects.get(chat=chat, user=request.user)
        return Response(
            {
                "last_read_seq": member.last_read_seq,
                "unread": max(0, chat.last_seq - member.last_read_seq),
                "updated": bool(updated),
            }
        )
