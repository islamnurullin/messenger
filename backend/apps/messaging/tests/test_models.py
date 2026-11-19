"""Тесты моделей и сервисов сообщений."""

from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction

from apps.chats.models import Chat, ChatMember
from apps.messaging.models import Message
from apps.messaging.services import MAX_BODY_LENGTH, allocate_seq, append_message, check_body

pytestmark = pytest.mark.django_db


@pytest.fixture
def chat(user, other_user) -> Chat:
    chat = Chat.objects.create(
        type=Chat.Type.DIRECT, direct_key=Chat.build_direct_key(user.pk, other_user.pk)
    )
    ChatMember.objects.create(chat=chat, user=user)
    ChatMember.objects.create(chat=chat, user=other_user)
    return chat


def test_allocate_seq_starts_at_one(chat):
    assert allocate_seq(chat.pk) == 1
    assert allocate_seq(chat.pk) == 2


def test_allocate_seq_updates_chat_row(chat):
    """last_seq в базе должен двигаться — на нём держатся unread и курсоры."""
    allocate_seq(chat.pk)
    chat.refresh_from_db()
    assert chat.last_seq == 1


def test_unique_seq_per_chat(chat):
    """Уникальный индекс (chat_id, seq) — последний рубеж защиты от дублей."""
    Message.objects.create(chat=chat, seq=1, sender=chat.members.first().user, body="раз")
    with pytest.raises(IntegrityError), transaction.atomic():
        Message.objects.create(chat=chat, seq=1, sender=chat.members.first().user, body="два")


def test_different_chats_can_share_seq(user, other_user, chat):
    """Нумерация своя в каждом чате: seq=1 есть в любом из них."""
    second = Chat.objects.create(type=Chat.Type.GROUP, title="Вторая")
    ChatMember.objects.create(chat=second, user=user)
    ChatMember.objects.create(chat=second, user=other_user)

    append_message(chat, user, "в первом")
    append_message(second, user, "во втором")

    assert list(Message.objects.filter(chat=chat).values_list("seq", flat=True)) == [1]
    assert list(Message.objects.filter(chat=second).values_list("seq", flat=True)) == [1]


def test_append_message_returns_created_flag(chat, user):
    message, created = append_message(chat, user, "привет")
    assert created is True
    assert message.seq == 1


def test_append_message_is_idempotent_by_client_id(chat, user):
    """Повтор с тем же client_msg_id не создаёт дубль и не тратит seq."""
    client_id = uuid.uuid4()
    first, created_first = append_message(chat, user, "привет", client_id)
    second, created_second = append_message(chat, user, "привет", client_id)

    assert created_first is True
    assert created_second is False
    assert first.pk == second.pk
    assert Message.objects.filter(chat=chat).count() == 1
    chat.refresh_from_db()
    # Ключевое: last_seq не должен уехать вперёд из-за повтора.
    assert chat.last_seq == 1


def test_append_message_allows_many_null_client_ids(chat, user):
    """NULL в client_msg_id не конфликтует сам с собой — сообщения без id живут."""
    append_message(chat, user, "раз")
    append_message(chat, user, "два")
    assert Message.objects.filter(chat=chat, client_msg_id__isnull=True).count() == 2


def test_message_deleted_sender_is_kept(chat, user):
    """Удаление пользователя не уносит переписку собеседника."""
    message, _ = append_message(chat, user, "останется")
    user.delete()
    message.refresh_from_db()
    assert message.sender_id is None
    assert message.body == "останется"


def test_check_body_rejects_blank():
    assert check_body("   ") == "Сообщение не может быть пустым."
    assert check_body("") is not None


def test_check_body_rejects_too_long():
    assert check_body("а" * (MAX_BODY_LENGTH + 1)) is not None


def test_check_body_accepts_normal():
    assert check_body("привет") is None


def test_ordering_is_by_seq(chat, user):
    """Порядок ленты задаётся seq, а не временем: одинаковые timestamp его не ломают."""
    for text in ("раз", "два", "три"):
        append_message(chat, user, text)
    # Принудительно ставим одинаковое время всем сообщениям.
    Message.objects.filter(chat=chat).update(created_at="2026-01-01T00:00:00Z")

    bodies = list(Message.objects.filter(chat=chat).values_list("body", flat=True))
    assert bodies == ["раз", "два", "три"]
