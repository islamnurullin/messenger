"""Пользователь и его профиль.

Телефон сознательно не используется: вход по username+паролю (решение заказчика),
SMS-провайдера в проекте нет. Если когда-нибудь понадобится вход по номеру —
добавляется отдельное поле ``phone`` с ``UNIQUE``, а не замена username.
"""

from __future__ import annotations

from typing import ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(self, username: str, password: str | None = None, **extra: object) -> User:
        if not username:
            raise ValueError("username обязателен")
        user = self.model(username=username, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username: str, password: str | None = None, **extra: object) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if extra.get("is_staff") is not True:
            raise ValueError("superuser должен иметь is_staff=True")
        return self.create_user(username, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    username = models.CharField(
        "имя пользователя",
        max_length=32,
        unique=True,
        db_index=True,
        help_text="Латиница, цифры и подчёркивание. Используется для входа.",
    )
    display_name = models.CharField("отображаемое имя", max_length=64, blank=True)
    bio = models.CharField("о себе", max_length=255, blank=True)
    avatar = models.ImageField("аватар", upload_to="avatars/", blank=True, null=True)

    is_active = models.BooleanField("активен", default=True)
    is_staff = models.BooleanField("персонал", default=False)

    # Денормализованное «был(а) в сети»: presence в Centrifugo эфемерно и теряется
    # при рестарте, а клиенту нужен осмысленный last seen.
    last_seen_at = models.DateTimeField("последняя активность", null=True, blank=True)
    created_at = models.DateTimeField("создан", default=timezone.now, editable=False)
    updated_at = models.DateTimeField("обновлён", auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        verbose_name = "пользователь"
        verbose_name_plural = "пользователи"
        ordering = ("username",)

    def __str__(self) -> str:
        return self.username

    @property
    def name(self) -> str:
        return self.display_name or self.username

    def touch_last_seen(self) -> None:
        User.objects.filter(pk=self.pk).update(last_seen_at=timezone.now())
