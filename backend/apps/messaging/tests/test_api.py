"""Тесты API сообщений и токенов realtime."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.chats.models import Chat, ChatMember
from apps.messaging.models import Message
from apps.messaging.services import append_message

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def chat(user, other_user) -> Chat:
    chat = Chat.objects.create(
        type=Chat.Type.DIRECT, direct_key=Chat.build_direct_key(user.pk, other_user.pk)
    )
    ChatMember.objects.create(chat=chat, user=user)
    ChatMember.objects.create(chat=chat, user=other_user)
    return chat


@pytest.fixture
def api(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def send(api, chat, body="привет", client_msg_id=None):
    return api.post(
        f"/api/chats/{chat.pk}/messages",
        {"body": body, "client_msg_id": str(client_msg_id or uuid.uuid4())},
        format="json",
    )


# --- отправка ---------------------------------------------------------------


def test_send_message_returns_201_with_seq(api, chat):
    response = send(api, chat, "первое")

    assert response.status_code == 201
    body = response.json()
    assert body["seq"] == 1
    assert body["body"] == "первое"
    assert body["sender"]["username"] == "islam"


def test_seq_grows_monotonically(api, chat):
    seqs = [send(api, chat, f"сообщение {i}").json()["seq"] for i in range(5)]
    assert seqs == [1, 2, 3, 4, 5]


def test_send_updates_sender_last_read(api, chat, user):
    """Автор прочитал своё сообщение: иначе у него самого висел бы счётчик."""
    send(api, chat, "моё")
    member = ChatMember.objects.get(chat=chat, user=user)
    assert member.last_read_seq == 1


def test_repeat_with_same_client_id_returns_200_and_same_message(api, chat):
    client_id = uuid.uuid4()
    first = send(api, chat, "привет", client_id)
    second = send(api, chat, "привет", client_id)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert Message.objects.filter(chat=chat).count() == 1


def test_repeat_does_not_advance_last_seq(api, chat):
    client_id = uuid.uuid4()
    send(api, chat, "один", client_id)
    send(api, chat, "один", client_id)
    chat.refresh_from_db()
    assert chat.last_seq == 1


def test_empty_body_rejected(api, chat):
    response = send(api, chat, "   ")
    assert response.status_code == 400
    assert "пустым" in response.json()["error"]["message"]


def test_missing_client_msg_id_rejected(api, chat):
    response = api.post(f"/api/chats/{chat.pk}/messages", {"body": "привет"}, format="json")
    assert response.status_code == 400


def test_bad_client_msg_id_rejected(api, chat):
    response = api.post(
        f"/api/chats/{chat.pk}/messages",
        {"body": "привет", "client_msg_id": "не-uuid"},
        format="json",
    )
    assert response.status_code == 400


def test_too_long_body_rejected(api, chat):
    response = send(api, chat, "а" * 5000)
    assert response.status_code == 400


def test_non_member_gets_404_on_send(user, other_user, chat):
    stranger = User.objects.create_user(username="stranger", password="bolshoy-parol-2026")
    client = APIClient()
    client.force_authenticate(user=stranger)

    response = send(client, chat, "подглядываю")
    assert response.status_code == 404
    assert Message.objects.filter(chat=chat).count() == 0


def test_non_member_gets_404_on_history(user, other_user, chat):
    stranger = User.objects.create_user(username="stranger", password="bolshoy-parol-2026")
    client = APIClient()
    client.force_authenticate(user=stranger)

    assert client.get(f"/api/chats/{chat.pk}/messages").status_code == 404


def test_requires_auth(chat):
    assert APIClient().get(f"/api/chats/{chat.pk}/messages").status_code == 401


# --- публикация в realtime --------------------------------------------------


def test_publish_happens_after_commit(chat, django_capture_on_commit_callbacks):
    """Публикация уходит только после коммита — иначе подписчик увидит
    сообщение, которого нет в базе, и оно исчезнет при перезагрузке."""
    from django.db import transaction

    client = APIClient()
    client.force_authenticate(user=chat.members.first().user)

    with patch("apps.messaging.views.publish_new_message") as publish:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            response = client.post(
                f"/api/chats/{chat.pk}/messages",
                {"body": "в эфир", "client_msg_id": str(uuid.uuid4())},
                format="json",
            )
        assert response.status_code == 201
        # До коммита публикации ещё нет — это и есть проверяемое свойство.
        assert publish.call_count == 0
        assert len(callbacks) == 1

        with transaction.atomic():
            for callback in callbacks:
                callback()

    assert publish.call_count == 1
    chat_id, payload, member_ids = publish.call_args.args
    assert chat_id == chat.pk
    assert payload["seq"] == 1
    # Рассылка уходит всем участникам одним вызовом, а не по одному на человека.
    assert set(member_ids) == set(chat.members.values_list("user_id", flat=True))


def test_repeat_does_not_publish_twice(chat, django_capture_on_commit_callbacks):
    """Повтор с тем же client_msg_id не должен рассылать событие второй раз."""
    from django.db import transaction

    client = APIClient()
    client.force_authenticate(user=chat.members.first().user)
    client_id = str(uuid.uuid4())

    with patch("apps.messaging.views.publish_new_message") as publish:
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            client.post(
                f"/api/chats/{chat.pk}/messages",
                {"body": "один", "client_msg_id": client_id},
                format="json",
            )
            client.post(
                f"/api/chats/{chat.pk}/messages",
                {"body": "один", "client_msg_id": client_id},
                format="json",
            )

        with transaction.atomic():
            for callback in callbacks:
                callback()

    assert publish.call_count == 1


# --- история ----------------------------------------------------------------


def test_history_returns_messages_ascending(api, chat, user):
    for i in range(3):
        append_message(chat, user, f"текст {i}")

    body = api.get(f"/api/chats/{chat.pk}/messages").json()
    assert [m["body"] for m in body["messages"]] == ["текст 0", "текст 1", "текст 2"]


def test_history_before_cursor_excludes_it(api, chat, user):
    """Курсор — эксклюзивный: before=N отдаёт строго более ранние."""
    for i in range(5):
        append_message(chat, user, f"текст {i}")

    body = api.get(f"/api/chats/{chat.pk}/messages?before=3").json()
    assert [m["seq"] for m in body["messages"]] == [1, 2]


def test_pagination_has_no_gaps_or_duplicates(api, chat, user):
    """Главный тест пагинации: пролистывая назад, видим каждое сообщение ровно раз."""
    total = 12
    for i in range(total):
        append_message(chat, user, f"текст {i}")

    seen: list[int] = []
    before = None
    while True:
        url = f"/api/chats/{chat.pk}/messages?limit=5"
        if before is not None:
            url += f"&before={before}"
        body = api.get(url).json()
        page = [m["seq"] for m in body["messages"]]
        seen = page + seen
        if not body["has_more"]:
            break
        before = page[0]

    assert seen == list(range(1, total + 1))


def test_has_more_false_when_exactly_page_size(api, chat, user):
    """Ровно 5 сообщений при limit=5 — истории больше нет, но клиенту нужен
    верный ответ, иначе он покажет «загрузить ещё» и получит пустую страницу."""
    for i in range(5):
        append_message(chat, user, f"текст {i}")

    body = api.get(f"/api/chats/{chat.pk}/messages?limit=5").json()
    assert len(body["messages"]) == 5
    assert body["has_more"] is False


def test_has_more_true_when_more_exists(api, chat, user):
    for i in range(6):
        append_message(chat, user, f"текст {i}")

    body = api.get(f"/api/chats/{chat.pk}/messages?limit=5").json()
    assert len(body["messages"]) == 5
    assert body["has_more"] is True
    # Отдаются самые свежие, а не самые старые.
    assert [m["seq"] for m in body["messages"]] == [2, 3, 4, 5, 6]


def test_page_cursors_are_reported(api, chat, user):
    for i in range(3):
        append_message(chat, user, f"текст {i}")

    body = api.get(f"/api/chats/{chat.pk}/messages").json()
    assert body["oldest_seq"] == 1
    assert body["newest_seq"] == 3


def test_empty_chat_returns_empty_page(api, chat):
    body = api.get(f"/api/chats/{chat.pk}/messages").json()
    assert body["messages"] == []
    assert body["has_more"] is False
    assert body["oldest_seq"] is None


def test_bad_before_rejected(api, chat):
    assert api.get(f"/api/chats/{chat.pk}/messages?before=abc").status_code == 400
    assert api.get(f"/api/chats/{chat.pk}/messages?before=-1").status_code == 400


def test_limit_is_clamped(api, chat, user):
    for i in range(3):
        append_message(chat, user, f"текст {i}")

    # Ноль и отрицательное не должны отдавать пустоту молча — минимум один.
    assert len(api.get(f"/api/chats/{chat.pk}/messages?limit=0").json()["messages"]) == 1


# --- токены Centrifugo ------------------------------------------------------


def test_connection_token_issued(api):
    response = api.post("/api/realtime/token")
    assert response.status_code == 200
    assert response.json()["token"]
    assert response.json()["ws_url"].startswith("ws://")


def test_subscription_token_for_own_chat(api, chat):
    response = api.post("/api/realtime/subscribe", {"channel": f"chat:{chat.pk}"}, format="json")
    assert response.status_code == 200
    assert response.json()["token"]


def test_subscription_token_denied_for_foreign_chat(api, user, other_user, chat):
    """Без этой проверки любой авторизованный подписался бы на чужой чат."""
    foreign = Chat.objects.create(type=Chat.Type.GROUP, title="Чужая группа")
    ChatMember.objects.create(chat=foreign, user=other_user)

    response = api.post("/api/realtime/subscribe", {"channel": f"chat:{foreign.pk}"}, format="json")
    assert response.status_code == 403


def test_subscription_token_for_own_user_channel(api, user):
    response = api.post("/api/realtime/subscribe", {"channel": f"user:{user.pk}"}, format="json")
    assert response.status_code == 200


def test_subscription_token_denied_for_foreign_user_channel(api, other_user):
    response = api.post(
        "/api/realtime/subscribe", {"channel": f"user:{other_user.pk}"}, format="json"
    )
    assert response.status_code == 403


def test_subscription_rejects_unknown_channel(api):
    response = api.post("/api/realtime/subscribe", {"channel": "свалка:1"}, format="json")
    assert response.status_code == 403
