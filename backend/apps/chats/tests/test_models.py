"""Тесты моделей чатов."""

from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from apps.chats.models import Chat, ChatMember


@pytest.mark.django_db
def test_direct_key_is_order_independent(user, other_user):
    first = Chat.build_direct_key(user.pk, other_user.pk)
    second = Chat.build_direct_key(other_user.pk, user.pk)
    assert first == second
    assert first == f"{min(user.pk, other_user.pk)}:{max(user.pk, other_user.pk)}"


@pytest.mark.django_db
def test_direct_key_unique_rejects_second_direct_chat(user, other_user):
    key = Chat.build_direct_key(user.pk, other_user.pk)
    Chat.objects.create(type=Chat.Type.DIRECT, direct_key=key)
    with pytest.raises(IntegrityError), transaction.atomic():
        Chat.objects.create(type=Chat.Type.DIRECT, direct_key=key)


@pytest.mark.django_db
def test_group_chats_are_not_limited_by_direct_key(user):
    # direct_key = None: NULL в Postgres не конфликтует сам с собой, поэтому
    # сколько угодно групп может иметь пустой ключ.
    for i in range(3):
        Chat.objects.create(type=Chat.Type.GROUP, title=f"Группа {i}")
    assert Chat.objects.filter(type=Chat.Type.GROUP).count() == 3


@pytest.mark.django_db
def test_member_cannot_join_same_chat_twice(user):
    chat = Chat.objects.create(type=Chat.Type.GROUP, title="Друзья")
    ChatMember.objects.create(chat=chat, user=user)
    with pytest.raises(IntegrityError), transaction.atomic():
        ChatMember.objects.create(chat=chat, user=user)


@pytest.mark.django_db
def test_unread_count_is_difference(user):
    chat = Chat.objects.create(type=Chat.Type.GROUP, title="Работа", last_seq=42)
    member = ChatMember.objects.create(chat=chat, user=user, last_read_seq=10)
    assert member.unread_count == 32


@pytest.mark.django_db
def test_unread_count_never_negative(user):
    # Рассинхрон после восстановления из бэкапа не должен давать «-5 непрочитанных».
    chat = Chat.objects.create(type=Chat.Type.GROUP, title="Работа", last_seq=5)
    member = ChatMember.objects.create(chat=chat, user=user, last_read_seq=10)
    assert member.unread_count == 0


@pytest.mark.django_db
def test_chat_str_falls_back_to_type_and_pk(user):
    chat = Chat.objects.create(type=Chat.Type.DIRECT, direct_key="1:2")
    assert str(chat) == f"Личный #{chat.pk}"
    chat.title = "Проект"
    assert str(chat) == "Проект"
