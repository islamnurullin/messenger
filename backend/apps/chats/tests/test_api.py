"""Тесты API чатов.

Проверяем не «эндпоинт отвечает 200», а вещи, которые ломаются при росте:
идемпотентность личного чата, отсутствие утечки чужих чатов, стоимость списка.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.chats.models import Chat, ChatMember

User = get_user_model()


@pytest.fixture
def api(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _direct(user, peer) -> Chat:
    return Chat.objects.create(
        type=Chat.Type.DIRECT, direct_key=Chat.build_direct_key(user.pk, peer.pk)
    )


@pytest.mark.django_db
def test_create_direct_chat_returns_201(api, user, other_user):
    response = api.post("/api/chats", {"type": "direct", "username": other_user.username})
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "direct"
    assert body["peer"]["username"] == other_user.username
    assert ChatMember.objects.filter(chat_id=body["id"]).count() == 2


@pytest.mark.django_db
def test_create_direct_chat_is_idempotent(api, user, other_user):
    first = api.post("/api/chats", {"type": "direct", "username": other_user.username})
    second = api.post("/api/chats", {"type": "direct", "username": other_user.username})

    assert first.status_code == 201
    # Повторная попытка открыть диалог — обычное дело, и это не создание.
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert Chat.objects.filter(type=Chat.Type.DIRECT).count() == 1


@pytest.mark.django_db
def test_direct_chat_idempotent_from_both_sides(api, user, other_user):
    """Оба участника начинают диалог — чат должен остаться один."""
    first = api.post("/api/chats", {"type": "direct", "username": other_user.username})

    peer_client = APIClient()
    peer_client.force_authenticate(user=other_user)
    second = peer_client.post("/api/chats", {"type": "direct", "username": user.username})

    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.django_db
def test_cannot_create_direct_chat_with_self(api, user):
    response = api.post("/api/chats", {"type": "direct", "username": user.username})
    assert response.status_code == 400
    # message должен быть готовой строкой для показа, а не repr словаря DRF.
    assert response.json()["error"]["message"] == "Нельзя создать чат с собой."


@pytest.mark.django_db
def test_direct_chat_with_unknown_user_is_rejected(api):
    response = api.post("/api/chats", {"type": "direct", "username": "no-such-user"})
    assert response.status_code == 400


@pytest.mark.django_db
def test_create_group_with_members(api, user, other_user):
    response = api.post(
        "/api/chats",
        {"type": "group", "title": "Учёба", "usernames": [other_user.username]},
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Учёба"
    assert body["member_count"] == 2
    roles = dict(ChatMember.objects.filter(chat_id=body["id"]).values_list("user_id", "role"))
    assert roles[user.pk] == ChatMember.Role.OWNER


@pytest.mark.django_db
def test_group_requires_title(api, other_user):
    response = api.post(
        "/api/chats", {"type": "group", "usernames": [other_user.username]}, format="json"
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_group_with_unknown_member_is_rejected(api):
    response = api.post(
        "/api/chats", {"type": "group", "title": "X", "usernames": ["ghost"]}, format="json"
    )
    assert response.status_code == 400
    assert "ghost" in str(response.json())


@pytest.mark.django_db
def test_group_member_lookup_ignores_case(api, other_user):
    """Логин регистронезависим при входе — значит и в группе должен находиться."""
    response = api.post(
        "/api/chats",
        {"type": "group", "title": "X", "usernames": [other_user.username.upper()]},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["member_count"] == 2


@pytest.mark.django_db
def test_list_returns_only_own_chats(api, user, other_user):
    own = _direct(user, other_user)
    ChatMember.objects.create(chat=own, user=user)

    alien_user = User.objects.create_user(username="stranger", password="x" * 12)
    alien_chat = Chat.objects.create(type=Chat.Type.GROUP, title="Чужое")
    ChatMember.objects.create(chat=alien_chat, user=alien_user)

    response = api.get("/api/chats")
    assert response.status_code == 200
    ids = [c["id"] for c in response.json()]
    assert own.pk in ids
    assert alien_chat.pk not in ids


@pytest.mark.django_db
def test_non_member_gets_404_not_403(api, other_user):
    """403 подтвердил бы существование чата — перебором можно узнать о переписках."""
    alien = User.objects.create_user(username="alien2", password="x" * 12)
    chat = Chat.objects.create(type=Chat.Type.GROUP, title="Секрет")
    ChatMember.objects.create(chat=chat, user=alien)

    assert api.get(f"/api/chats/{chat.pk}").status_code == 404
    assert (
        api.post(f"/api/chats/{chat.pk}/members", {"username": other_user.username}).status_code
        == 404
    )
    assert api.post(f"/api/chats/{chat.pk}/read", {"last_read_seq": 1}).status_code == 404


@pytest.mark.django_db
def test_unread_counts_from_last_seq(api, user, other_user):
    chat = _direct(user, other_user)
    ChatMember.objects.create(chat=chat, user=user, last_read_seq=3)
    ChatMember.objects.create(chat=chat, user=other_user)
    Chat.objects.filter(pk=chat.pk).update(last_seq=10)

    body = api.get("/api/chats").json()
    assert body[0]["unread"] == 7
    assert body[0]["last_read_seq"] == 3


@pytest.mark.django_db
def test_mark_read_is_monotonic(api, user, other_user):
    chat = _direct(user, other_user)
    ChatMember.objects.create(chat=chat, user=user)
    ChatMember.objects.create(chat=chat, user=other_user)
    Chat.objects.filter(pk=chat.pk).update(last_seq=10)

    first = api.post(f"/api/chats/{chat.pk}/read", {"last_read_seq": 8})
    assert first.status_code == 200
    assert first.json()["last_read_seq"] == 8

    # Назад откатывать нельзя: клиент мог отправить устаревшее значение.
    second = api.post(f"/api/chats/{chat.pk}/read", {"last_read_seq": 2})
    assert second.json()["last_read_seq"] == 8


@pytest.mark.django_db
def test_mark_read_cannot_exceed_last_seq(api, user, other_user):
    chat = _direct(user, other_user)
    ChatMember.objects.create(chat=chat, user=user)
    ChatMember.objects.create(chat=chat, user=other_user)
    Chat.objects.filter(pk=chat.pk).update(last_seq=5)

    response = api.post(f"/api/chats/{chat.pk}/read", {"last_read_seq": 999})
    assert response.json()["last_read_seq"] == 5
    assert response.json()["unread"] == 0


@pytest.mark.django_db
def test_add_member_to_group(api, user, other_user):
    chat = Chat.objects.create(type=Chat.Type.GROUP, title="X")
    ChatMember.objects.create(chat=chat, user=user, role=ChatMember.Role.OWNER)

    response = api.post(f"/api/chats/{chat.pk}/members", {"username": other_user.username})
    assert response.status_code == 201
    assert response.json()["user"]["username"] == other_user.username


@pytest.mark.django_db
def test_add_member_twice_conflicts(api, user, other_user):
    chat = Chat.objects.create(type=Chat.Type.GROUP, title="X")
    ChatMember.objects.create(chat=chat, user=user)
    ChatMember.objects.create(chat=chat, user=other_user)

    response = api.post(f"/api/chats/{chat.pk}/members", {"username": other_user.username})
    assert response.status_code == 409


@pytest.mark.django_db
def test_cannot_add_member_to_direct_chat(api, user, other_user):
    chat = _direct(user, other_user)
    ChatMember.objects.create(chat=chat, user=user)
    ChatMember.objects.create(chat=chat, user=other_user)

    third = User.objects.create_user(username="third", password="x" * 12)
    response = api.post(f"/api/chats/{chat.pk}/members", {"username": third.username})
    assert response.status_code == 400
    assert not ChatMember.objects.filter(chat=chat, user=third).exists()


@pytest.mark.django_db
def test_chats_require_authentication():
    assert APIClient().get("/api/chats").status_code == 401


@pytest.mark.django_db
def test_list_does_not_grow_queries_with_chat_count(api, user):
    """Список чатов должен стоить одинаково при 1 и при 20 чатах.

    Без предзагрузки membership/peers/counts каждый чат добавлял бы по 2-3
    запроса — на 50 диалогах это заметно даже на локальной машине.
    """

    def make_chats(start: int, count: int) -> None:
        for i in range(start, start + count):
            peer = User.objects.create_user(username=f"peer{i}", password="x" * 12)
            chat = Chat.objects.create(
                type=Chat.Type.DIRECT, direct_key=Chat.build_direct_key(user.pk, peer.pk)
            )
            ChatMember.objects.create(chat=chat, user=user)
            ChatMember.objects.create(chat=chat, user=peer)

    make_chats(0, 1)
    with CaptureQueriesContext(connection) as few:
        api.get("/api/chats")
    few_count = len(few.captured_queries)

    make_chats(1, 19)
    with CaptureQueriesContext(connection) as many:
        api.get("/api/chats")
    many_count = len(many.captured_queries)

    assert (
        many_count <= few_count + 2
    ), f"запросов стало больше при росте списка: {few_count} -> {many_count}"
