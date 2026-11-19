"""Выдача номеров и запись сообщений.

Главное здесь — как получается ``seq``. Наивный вариант «прочитать last_seq,
прибавить единицу, записать» ломается на первом же параллельном запросе: два
потока читают одно и то же значение, оба пишут ``N+1``, а уникальный индекс
``(chat_id, seq)`` отбивает второй. Поэтому номер выдаёт сама база одной
командой ``UPDATE ... RETURNING`` — строка чата блокируется на время
транзакции, и два отправителя гарантированно получат разные номера.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.db import IntegrityError, connection, transaction

from apps.chats.models import Chat

from .models import Message

# Сколько символов максимум в тексте сообщения. Вложения — следующий этап,
# поэтому здесь только текст, и хранить килобайты в TextField незачем.
MAX_BODY_LENGTH = 4096


def allocate_seq(chat_id: int) -> int:
    """Резервирует следующий seq для чата. Вызывать только внутри транзакции.

    ``UPDATE ... RETURNING`` за одну команду: Postgres блокирует строку чата до
    конца транзакции, поэтому второй отправитель ждёт и получает следующий
    номер, а не тот же самый. Отдельные SELECT и UPDATE такой гарантии не дают
    даже с уровнем изоляции SERIALIZABLE — там пришлось бы ловить откаты.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE chats_chat
               SET last_seq = last_seq + 1,
                   updated_at = NOW()
             WHERE id = %s
         RETURNING last_seq
            """,
            [chat_id],
        )
        row = cursor.fetchone()
    if row is None:
        raise ValueError(f"Чата {chat_id} не существует")
    return int(row[0])


def find_by_client_id(chat_id: int, client_msg_id: uuid.UUID | None) -> Message | None:
    if client_msg_id is None:
        return None
    return Message.objects.filter(chat_id=chat_id, client_msg_id=client_msg_id).first()


def append_message(
    chat: Chat,
    sender: Any,
    body: str,
    client_msg_id: uuid.UUID | None = None,
) -> tuple[Message, bool]:
    """Записывает сообщение. Возвращает (сообщение, создано_ли).

    Второй элемент False означает повтор: клиент прислал тот же
    ``client_msg_id``, и вместо дубля ему отдаётся уже сохранённое сообщение.
    Это не роскошь — без такой проверки двойной клик или ретрай после обрыва
    связи оставляют в переписке два одинаковых сообщения.
    """
    existing = find_by_client_id(chat.pk, client_msg_id)
    if existing is not None:
        return existing, False

    try:
        with transaction.atomic():
            seq = allocate_seq(chat.pk)
            message = Message.objects.create(
                chat_id=chat.pk,
                seq=seq,
                sender=sender,
                body=body,
                client_msg_id=client_msg_id,
            )
    except IntegrityError:
        # Гонка: два запроса с одним client_msg_id пришли одновременно. Оба
        # прошли проверку выше, но уникальный индекс пропустил только первый.
        # Его транзакция откатилась вместе с инкрементом seq, поэтому дыры в
        # нумерации не остаётся — забираем сохранённое сообщение.
        existing = find_by_client_id(chat.pk, client_msg_id)
        if existing is None:
            raise
        return existing, False

    # last_seq обновился в базе, но объект чата в памяти об этом не знает.
    chat.last_seq = message.seq
    return message, True


def check_body(body: str) -> str | None:
    """Возвращает текст ошибки или None. Пустые сообщения не отправляем."""
    text = body.strip()
    if not text:
        return "Сообщение не может быть пустым."
    if len(text) > MAX_BODY_LENGTH:
        return f"Сообщение длиннее {MAX_BODY_LENGTH} символов."
    return None
