"""Сериализаторы сообщений."""

from __future__ import annotations

import uuid
from typing import Any

from rest_framework import serializers

from apps.accounts.serializers import UserPublicSerializer

from .models import Message
from .services import MAX_BODY_LENGTH


class MessageSerializer(serializers.ModelSerializer):
    """Сообщение в ленте.

    Отправитель отдаётся вложенным объектом, а не id: клиенту нужно показать
    имя и аватар у каждого сообщения. В списке это N+1, поэтому вьюха делает
    ``select_related("sender")`` — тогда дополнительных запросов нет.
    """

    sender = UserPublicSerializer(read_only=True)

    class Meta:
        model = Message
        fields = ("id", "seq", "sender", "body", "created_at")
        read_only_fields = fields


class MessageCreateSerializer(serializers.Serializer):
    """Отправка сообщения.

    ``client_msg_id`` обязателен: без него повторная отправка после обрыва
    связи создаёт дубль. UUID проверяется здесь, чтобы кривой идентификатор
    давал 400, а не 500 от базы.
    """

    body = serializers.CharField(
        max_length=MAX_BODY_LENGTH,
        allow_blank=False,
        trim_whitespace=True,
        error_messages={
            "blank": "Сообщение не может быть пустым.",
            "max_length": f"Сообщение длиннее {MAX_BODY_LENGTH} символов.",
        },
    )
    client_msg_id = serializers.UUIDField()

    def validate_client_msg_id(self, value: uuid.UUID) -> uuid.UUID:
        return value


class MessagesPageSerializer(serializers.Serializer):
    """Страница истории: сообщения по возрастанию seq плюс курсоры.

    ``has_more`` считается по факту наличия более раннего сообщения, а не по
    длине страницы: иначе на ровно 50 сообщениях клиент решил бы, что история
    кончилась, и не показал бы «загрузить ещё».
    """

    messages = MessageSerializer(many=True)
    has_more = serializers.BooleanField()
    oldest_seq = serializers.IntegerField(allow_null=True)
    newest_seq = serializers.IntegerField(allow_null=True)


def build_page_data(messages: list[Message], has_more: bool) -> dict[str, Any]:
    return {
        "messages": MessageSerializer(messages, many=True).data,
        "has_more": has_more,
        "oldest_seq": messages[0].seq if messages else None,
        "newest_seq": messages[-1].seq if messages else None,
    }
