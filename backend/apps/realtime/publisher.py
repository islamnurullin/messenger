"""Связь с Centrifugo: токены подписки и публикация событий.

Centrifugo сам ничего не знает о наших чатах — он только передаёт сообщения
подписчикам канала. Поэтому права проверяет Django: даёт клиенту JWT на
конкретные каналы (``connection``-токен и ``subscription``-токен) и публикует
события через свой HTTP API.

Каналы:
- ``chat:<id>`` — лента сообщений конкретного чата;
- ``user:<id>`` — личный канал пользователя: уведомления о новых чатах,
  приглашениях, отметках о прочтении.

Про стоимость публикации: HTTP-запрос к localhost здесь стоит ~1.4 с, если
каждый раз открывать новое TCP-соединение (на Windows так и происходит —
новый сокет на каждый вызов httpx.post). Поэтому соединение переиспользуется
через общий Client, а рассылка по участникам уходит **одним** пакетным
запросом в ``/api/batch``, а не N запросами по числу участников. На группе из
20 человек это разница между 28 секундами и 3 миллисекундами.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import httpx
from django.conf import settings

# trust_env=False: httpx по умолчанию берёт прокси из переменных окружения и
# реестра Windows, а Centrifugo живёт на localhost. Через корпоративный прокси
# запрос к 127.0.0.1 уходит наружу и возвращается 502 — эта ошибка уже ловилась
# на health-check (см. docs/troubleshooting.md).
_TIMEOUT = httpx.Timeout(5.0)

# Сколько живёт токен подписки. Должен быть не меньше времени, которое клиент
# проводит в чате без переподключения; Centrifugo обновляет токен сам.
SUBSCRIPTION_TTL_SECONDS = 3600

_client_lock = threading.Lock()
_client: httpx.Client | None = None


def _http() -> httpx.Client:
    """Общий клиент на процесс.

    httpx.Client держит пул соединений: второй и последующие запросы к тому же
    хосту не платят за TCP-handshake. Без этого каждое сообщение в чате стоило
    больше секунды только на установку соединения.
    """
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = httpx.Client(trust_env=False, timeout=_TIMEOUT)
    return _client


def chat_channel(chat_id: int) -> str:
    return f"chat:{chat_id}"


def user_channel(user_id: int) -> str:
    return f"user:{user_id}"


def _api_url() -> str:
    return f"{settings.CENTRIFUGO_HTTP_URL.rstrip('/')}/api"


def _headers() -> dict[str, str]:
    return {"X-API-Key": settings.CENTRIFUGO_API_KEY}


def _ok(response: httpx.Response) -> bool:
    if response.status_code != 200:
        return False
    # Centrifugo отвечает 200 и на ошибку — признак в теле.
    return "error" not in response.json()


def publish(channel: str, data: dict[str, Any]) -> bool:
    """Публикует одно событие. Ошибки не пробрасываются — см. publish_many."""
    return publish_many([(channel, data)])


def publish_many(events: list[tuple[str, dict[str, Any]]]) -> bool:
    """Публикует пачку событий одним запросом (``/api/batch``).

    Ошибки публикации намеренно не пробрасываются: сообщение уже лежит в
    Postgres, и падение realtime не должно превращать успешную отправку в
    ошибку 500. Клиент догонит пропущенное через обычный GET при следующем
    открытии чата.
    """
    if not events:
        return True

    if len(events) == 1:
        channel, data = events[0]
        payload: dict[str, Any] = {
            "method": "publish",
            "params": {"channel": channel, "data": data},
        }
        url = _api_url()
    else:
        payload = {
            "commands": [
                {"method": "publish", "params": {"channel": channel, "data": data}}
                for channel, data in events
            ]
        }
        url = f"{settings.CENTRIFUGO_HTTP_URL.rstrip('/')}/api/batch"

    try:
        return _ok(_http().post(url, json=payload, headers=_headers()))
    except Exception:
        return False


def publish_message(chat_id: int, message_data: dict[str, Any]) -> bool:
    return publish(chat_channel(chat_id), {"type": "message", "message": message_data})


def publish_to_user(user_id: int, event: dict[str, Any]) -> bool:
    return publish(user_channel(user_id), event)


def publish_new_message(chat_id: int, message_data: dict[str, Any], member_ids: list[int]) -> bool:
    """Рассылка нового сообщения: в канал чата и в личные каналы участников.

    Всё — одним пакетным запросом. Отдельный запрос на каждого участника был бы
    «честнее» по смыслу, но на группе из 20 человек это 20 сетевых вызовов на
    каждое сообщение.
    """
    events: list[tuple[str, dict[str, Any]]] = [
        (chat_channel(chat_id), {"type": "message", "message": message_data}),
    ]
    events += [
        (
            user_channel(user_id),
            {
                "type": "chat.message",
                "chat_id": chat_id,
                "message": {
                    "seq": message_data.get("seq"),
                    "body": message_data.get("body", "")[:120],
                },
            },
        )
        for user_id in member_ids
    ]
    return publish_many(events)


def make_connection_token(user_id: int, ttl_seconds: int = 3600) -> str:
    """JWT для подключения к Centrifugo.

    ``sub`` — идентификатор пользователя в терминах Centrifugo. По нему
    Centrifugo строит presence и понимает, кому адресован канал ``user:<id>``.
    """
    import jwt  # PyJWT ставится вместе с djangorestframework-simplejwt

    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, settings.CENTRIFUGO_TOKEN_HMAC_SECRET, algorithm="HS256")


def make_subscription_token(
    user_id: int, channel: str, ttl_seconds: int = SUBSCRIPTION_TTL_SECONDS
) -> str:
    """JWT на подписку к одному каналу.

    В конфиге Centrifugo стоит ``allow_subscribe_for_client: false``: без этого
    токена подписка отклоняется. Права проверяет Django — вызывающий код обязан
    сначала убедиться, что пользователь действительно участник чата.
    """
    import jwt

    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "channel": channel,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, settings.CENTRIFUGO_TOKEN_HMAC_SECRET, algorithm="HS256")
