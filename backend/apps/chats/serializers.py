"""Сериализаторы чатов.

Ключевое решение: наружу чат отдаётся вместе с unread и с собеседником (для
личного) — иначе клиенту пришлось бы на каждый чат в списке делать отдельный
запрос за пользователем. Это N+1, который виден на глаз при 50 чатах.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.db.models.functions import Lower
from rest_framework import serializers

from apps.accounts.serializers import UserPublicSerializer

from .models import Chat, ChatMember

User = get_user_model()


class ChatMemberSerializer(serializers.ModelSerializer):
    user = UserPublicSerializer(read_only=True)

    class Meta:
        model = ChatMember
        fields = ("user", "role", "last_read_seq", "joined_at")
        read_only_fields = fields


class ChatSerializer(serializers.ModelSerializer):
    """Чат глазами участника: unread и собеседник уже внутри."""

    unread = serializers.SerializerMethodField()
    last_read_seq = serializers.SerializerMethodField()
    peer = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = (
            "id",
            "type",
            "title",
            "last_seq",
            "unread",
            "last_read_seq",
            "peer",
            "member_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def _member(self, chat: Chat) -> ChatMember | None:
        # Вьюха кладёт сюда membership вручную (через .annotate/.prefetch),
        # чтобы не ходить в БД на каждый чат списка.
        cached = self.context.get("memberships", {}).get(chat.pk)
        return cached

    def get_unread(self, chat: Chat) -> int:
        member = self._member(chat)
        if member is None:
            return 0
        return max(0, chat.last_seq - member.last_read_seq)

    def get_last_read_seq(self, chat: Chat) -> int:
        member = self._member(chat)
        return member.last_read_seq if member else 0

    def get_member_count(self, chat: Chat) -> int:
        counts = self.context.get("member_counts")
        if counts is not None:
            return counts.get(chat.pk, 0)
        return chat.members.count()

    def get_peer(self, chat: Chat) -> dict[str, Any] | None:
        """Собеседник личного чата — чтобы список чатов рисовался без доп. запросов."""
        if chat.type != Chat.Type.DIRECT:
            return None
        peers = self.context.get("peers", {})
        if chat.pk in peers:
            user = peers[chat.pk]
            return UserPublicSerializer(user).data if user is not None else None
        return None


class ChatCreateSerializer(serializers.Serializer):
    """Создание личного чата или группы.

    ``type=direct`` требует ровно одного ``username`` собеседника;
    ``group``/``channel`` — ``title`` и, для группы, список участников.
    Набор полей проверяется в ``validate``, потому что он зависит от типа.
    """

    type = serializers.ChoiceField(choices=Chat.Type.choices, default=Chat.Type.DIRECT)
    title = serializers.CharField(max_length=128, required=False, allow_blank=True)
    username = serializers.CharField(max_length=32, required=False, allow_blank=True)
    usernames = serializers.ListField(
        child=serializers.CharField(max_length=32), required=False, allow_empty=True
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        chat_type = attrs["type"]
        request = self.context["request"]

        if chat_type == Chat.Type.DIRECT:
            username = (attrs.get("username") or "").strip()
            if not username:
                raise serializers.ValidationError({"username": ["Укажите собеседника."]})
            try:
                peer = User.objects.get(username__iexact=username)
            except User.DoesNotExist:
                # Тот же текст, что и для «нельзя создать чат с собой»: иначе
                # перебором логинов можно узнать, кто зарегистрирован.
                raise serializers.ValidationError(
                    {"username": ["Пользователь не найден."]}
                ) from None
            if peer.pk == request.user.pk:
                raise serializers.ValidationError({"username": ["Нельзя создать чат с собой."]})
            attrs["peer"] = peer
            attrs["title"] = ""
            return attrs

        title = (attrs.get("title") or "").strip()
        if not title:
            raise serializers.ValidationError({"title": ["Укажите название."]})

        usernames = [u.strip() for u in attrs.get("usernames") or [] if u.strip()]
        if len(set(usernames)) != len(usernames):
            raise serializers.ValidationError({"usernames": ["Имена повторяются."]})
        if len(usernames) > 200:
            raise serializers.ValidationError({"usernames": ["Слишком много участников."]})

        users = list(
            User.objects.annotate(username_lower=Lower("username")).filter(
                username_lower__in=[u.lower() for u in usernames]
            )
        )
        # Одним запросом по lower(username): иначе «Alice» и «alice» разошлись бы —
        # username__in в Postgres чувствителен к регистру, а вход по логину нет
        # (см. LoginSerializer), и группа молча не нашла бы участника.
        found = {u.username.lower() for u in users}
        lowered = [u.lower() for u in usernames]
        missing = [name for name in lowered if name not in found]
        if missing:
            raise serializers.ValidationError(
                {"usernames": [f"Не найдены: {', '.join(sorted(set(missing)))}"]}
            )
        attrs["title"] = title
        attrs["members"] = [u for u in users if u.pk != request.user.pk]
        return attrs


class AddMemberSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=32)

    def validate_username(self, value: str) -> str:
        value = value.strip()
        try:
            user = User.objects.get(username__iexact=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("Пользователь не найден.") from None
        self.context["user"] = user
        return user.username


class MarkReadSerializer(serializers.Serializer):
    last_read_seq = serializers.IntegerField(min_value=0)
