"""Чаты: личные, группы и каналы.

Три типа в одной таблице, а не три модели: у них совпадает всё, кроме правил
доступа и наличия заголовка. Три отдельные таблицы дали бы три набора
сериализаторов, три эндпоинта списка и вечное «а как это показать в одном
списке чатов» на клиенте.

Про ``last_seq``: это счётчик сообщений внутри чата. Он же курсор пагинации, он
же источник unread-счётчика (``last_seq - last_read_seq``), он же версия для
websocket-событий. Поэтому живёт на чате, а не вычисляется из сообщений: подсчёт
``COUNT(*)`` на каждый запрос списка чатов — это ровно то, что не выдержит
нагрузку «1000+ сообщений в потоке».
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone


class Chat(models.Model):
    class Type(models.TextChoices):
        DIRECT = "direct", "Личный"
        GROUP = "group", "Группа"
        CHANNEL = "channel", "Канал"

    type = models.CharField("тип", max_length=16, choices=Type.choices)
    title = models.CharField("название", max_length=128, blank=True)

    # Ключ идемпотентности личного чата: "меньший_id:больший_id".
    # Уникальный индекс не даёт создать два личных чата между одними и теми же
    # людьми даже при одновременных запросах с обеих сторон. У групп и каналов
    # здесь NULL — NULL в Postgres не конфликтует сам с собой, поэтому уникальность
    # работает только для личных.
    direct_key = models.CharField(max_length=64, unique=True, null=True, blank=True, default=None)

    last_seq = models.BigIntegerField("последний seq", default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="создатель",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_chats",
    )
    created_at = models.DateTimeField("создан", default=timezone.now, editable=False)
    updated_at = models.DateTimeField("обновлён", auto_now=True)

    class Meta:
        verbose_name = "чат"
        verbose_name_plural = "чаты"
        ordering = ("-updated_at", "-id")
        # Индекса по updated_at здесь сознательно нет. Сортировать десяток-сотню
        # чатов пользователя Postgres умеет в памяти, а вот обновлять этот индекс
        # пришлось бы на каждое новое сообщение — то есть ровно на том горячем
        # пути, ради которого всё и затевается. Выборка списка идёт через
        # member_user_idx, а не через сортировку по чатам.

    def __str__(self) -> str:
        return self.title or f"{self.get_type_display()} #{self.pk}"

    @staticmethod
    def build_direct_key(first_id: int, second_id: int) -> str:
        low, high = sorted((first_id, second_id))
        return f"{low}:{high}"

    @property
    def is_direct(self) -> bool:
        return self.type == self.Type.DIRECT


class ChatMember(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Владелец"
        ADMIN = "admin", "Администратор"
        MEMBER = "member", "Участник"

    chat = models.ForeignKey(
        Chat, verbose_name="чат", on_delete=models.CASCADE, related_name="members"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="пользователь",
        on_delete=models.CASCADE,
        related_name="chat_memberships",
    )
    role = models.CharField("роль", max_length=16, choices=Role.choices, default=Role.MEMBER)

    # До какого seq пользователь дочитал. Разница с chat.last_seq и есть unread.
    last_read_seq = models.BigIntegerField("прочитано до seq", default=0)

    joined_at = models.DateTimeField("вступил", default=timezone.now, editable=False)

    class Meta:
        verbose_name = "участник чата"
        verbose_name_plural = "участники чатов"
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=("chat", "user"), name="uniq_chat_member"),
        ]
        indexes: ClassVar[list[models.Index]] = [
            # Основной запрос: «все чаты пользователя, свежие сверху».
            models.Index(fields=("user", "-joined_at"), name="member_user_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.user} в {self.chat}"

    @property
    def unread_count(self) -> int:
        # max(0, ...) — страховка от рассинхрона: если seq чата когда-нибудь
        # откатится (восстановление из бэкапа), счётчик не уйдёт в минус.
        return max(0, self.chat.last_seq - self.last_read_seq)
