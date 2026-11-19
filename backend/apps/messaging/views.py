"""Эндпоинты сообщений.

Доступ проверяется тем же ``chats_for(user)``, что и в чатах: не-участник
получает 404 — существование чата не подтверждаем (см. ``apps/chats/views.py``).
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chats.models import Chat, ChatMember
from apps.chats.views import chats_for
from apps.realtime.publisher import publish_new_message

from .models import Message
from .serializers import MessageCreateSerializer, MessageSerializer, build_page_data
from .services import append_message

PAGE_SIZE = settings.MESSAGE_PAGE_SIZE


def page_messages(chat: Chat, before: int | None, limit: int) -> tuple[list[Message], bool]:
    """Страница истории «до курсора».

    Сортировка по ``seq``, а не по ``created_at``: seq непрерывен и уникален
    внутри чата, поэтому границы страниц не разъезжаются при одинаковых
    timestamp. Курсор — seq самого старого показанного сообщения, а не offset:
    offset съезжает, когда в чат приходит новое сообщение во время прокрутки,
    и пользователь видит одну и ту же запись дважды.
    """
    queryset = Message.objects.filter(chat=chat).select_related("sender")
    if before is not None:
        queryset = queryset.filter(seq__lt=before)

    # Берём на одно больше, чтобы понять, есть ли ещё история, и не делать
    # ради этого отдельный COUNT.
    rows = list(queryset.order_by("-seq")[: limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    rows.reverse()
    return rows, has_more


def publish_to_members(chat: Chat, message: Message) -> None:
    """Рассылка события в realtime. Вызывается после коммита транзакции.

    Один пакетный запрос на всех участников: канал чата + личный канал каждого,
    чтобы у тех, кто не открыл чат, обновился счётчик непрочитанных.
    """
    payload = MessageSerializer(message).data
    member_ids = list(ChatMember.objects.filter(chat=chat).values_list("user_id", flat=True))
    publish_new_message(chat.pk, payload, member_ids)


class MessageListCreateView(APIView):
    """GET — история с пагинацией, POST — отправка."""

    permission_classes = (IsAuthenticated,)

    def get(self, request: Request, chat_id: int) -> Response:
        chat = get_object_or_404(chats_for(request.user), pk=chat_id)

        raw_before = request.query_params.get("before")
        before: int | None = None
        if raw_before is not None:
            try:
                before = int(raw_before)
            except ValueError:
                return Response(
                    {"error": {"code": "bad_request", "message": "before должен быть числом"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if before < 0:
                return Response(
                    {"error": {"code": "bad_request", "message": "before не может быть меньше 0"}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        raw_limit = request.query_params.get("limit")
        limit = PAGE_SIZE
        if raw_limit is not None:
            try:
                limit = max(1, min(int(raw_limit), 200))
            except ValueError:
                limit = PAGE_SIZE

        messages, has_more = page_messages(chat, before, limit)
        return Response(build_page_data(messages, has_more))

    def post(self, request: Request, chat_id: int) -> Response:
        chat = get_object_or_404(chats_for(request.user), pk=chat_id)

        serializer = MessageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        message, created = append_message(
            chat=chat,
            sender=request.user,
            body=data["body"],
            client_msg_id=data["client_msg_id"],
        )

        if created:
            # transaction.on_commit — критично: publish уходит в сеть сразу, и
            # если отправить его до коммита, подписчик получит сообщение,
            # которого ещё нет в базе (например, транзакция откатится позже).
            # Тогда при перезагрузке страницы сообщение исчезнет — худший вид
            # бага для мессенджера.
            transaction.on_commit(lambda: publish_to_members(chat, message))

            # Автор прочитал своё сообщение по определению: иначе у него
            # самого висел бы счётчик непрочитанных.
            ChatMember.objects.filter(chat=chat, user=request.user).update(
                last_read_seq=message.seq
            )

        payload = MessageSerializer(message).data
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
