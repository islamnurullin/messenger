"""Сообщения.

Два числа определяют порядок в чате:

- ``seq`` — монотонный номер внутри чата. Он уникален, непрерывен и не зависит
  от часов. Сортировка по ``created_at`` не работает: при массовой вставке
  (нагрузочный тест, импорт) Postgres может выдать одинаковый ``now()``
  нескольким строкам, и «следующее» сообщение окажется то выше, то ниже
  предыдущего. Пагинация по такому полю теряет сообщения на границах.
- ``client_msg_id`` — UUID, который генерирует клиент. Повторная отправка того
  же сообщения (двойной клик, обрыв связи, ретрай) не создаёт дубль.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.chats.models import Chat


class Message(models.Model):
    chat = models.ForeignKey(
        Chat, verbose_name="чат", on_delete=models.CASCADE, related_name="messages"
    )
    seq = models.BigIntegerField("номер в чате")
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="отправитель",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="messages_sent",
    )
    body = models.TextField("text", blank=True, default="")

    # Идемпотентность отправки. NULL для сообщений, которые пришли не от клиента
    # (боты, импорт): NULL в Postgres не конфликтует сам с собой, поэтому
    # уникальный индекс их не блокирует.
    client_msg_id = models.UUIDField("id от клиента", null=True, blank=True)

    created_at = models.DateTimeField("отправлено", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "сообщение"
        verbose_name_plural = "сообщения"
        ordering = ("seq",)
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=("chat", "seq"), name="uniq_message_seq"),
            models.UniqueConstraint(
                fields=("chat", "client_msg_id"), name="uniq_message_client_id"
            ),
        ]
        # Отдельного индекса под пагинацию нет: uniq_message_seq — это btree
        # по (chat_id, seq), и он одинаково хорошо обслуживает и «последние 50»
        # (ORDER BY seq DESC), и «до курсора» (seq < X ORDER BY seq DESC).
        # Второй индекс по тем же колонкам только замедлил бы вставку.

    def __str__(self) -> str:
        preview = self.body[:40] if self.body else "(без текста)"
        return f"#{self.seq} {self.sender}: {preview}"
