"""Сериализаторы аккаунтов: регистрация, вход, профиль.

Два неочевидных решения, которые здесь зашиты:

1. **``username`` уникален без учёта регистра.** Обычный ``unique=True`` в
   PostgreSQL различает ``Islam`` и ``islam``, и в базе появляются два человека,
   которых невозможно различить на глаз. Проверяем через ``__iexact`` и дублируем
   ограничением в БД, чтобы гонка двух одновременных регистраций не проскочила.

2. **Аватар проверяется по содержимому, а не по расширению.** Клиент присылает
   что угодно с именем ``avatar.png``; Pillow открывает поток и говорит реальный
   формат. Заодно отсекаем «изображения», которые на самом деле не картинки.
"""

from __future__ import annotations

import io
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

User = get_user_model()

# Аватар храним квадратом: в списках чатов он всегда круглый, а прямоугольник
# заставляет клиента гадать, как его обрезать. 256 px хватает на retina-аватар
# в списке; исходник при этом не храним — место на диске дороже качества.
AVATAR_SIZE = 256
AVATAR_QUALITY = 85
ALLOWED_AVATAR_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})


def _avatar_error(detail: str) -> serializers.ValidationError:
    return serializers.ValidationError({"avatar": [detail]})


def process_avatar(upload: Any) -> ContentFile:
    """Проверяет загруженный файл и возвращает квадратный JPEG нужного размера."""
    max_bytes = getattr(settings, "ATTACHMENT_MAX_BYTES", 25 * 1024 * 1024)
    if upload.size > max_bytes:
        limit_mb = max_bytes // (1024 * 1024)
        raise _avatar_error(f"Файл больше {limit_mb} МБ")

    try:
        image = Image.open(upload)
        image.verify()
    except (UnidentifiedImageError, OSError):
        raise _avatar_error("Файл не является изображением") from None

    # После verify() поток нужно перечитать: Pillow закрывает его.
    upload.seek(0)
    image = Image.open(upload)
    if image.format not in ALLOWED_AVATAR_FORMATS:
        raise _avatar_error("Поддерживаются только JPEG, PNG и WebP")

    # RGBA/палитра при сохранении в JPEG даёт артефакты или падает, поэтому
    # приводим к RGB на белом фоне (иначе прозрачность станет чёрной).
    if image.mode in {"RGBA", "LA", "P"}:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        image = Image.alpha_composite(background, rgba)
    image = image.convert("RGB")

    # center-crop до квадрата, потом уменьшаем — в таком порядке детали не мылятся.
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side))
    if side > AVATAR_SIZE:
        image = image.resize((AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=AVATAR_QUALITY, optimize=True)
    return ContentFile(buffer.getvalue(), name="avatar.jpg")


class UserPublicSerializer(serializers.ModelSerializer):
    """Профиль, который видят другие: без служебных полей вроде is_staff."""

    name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "display_name", "name", "bio", "avatar", "last_seen_at")
        read_only_fields = fields


class ProfileSerializer(serializers.ModelSerializer):
    """Свой профиль на ``GET/PATCH /api/me``."""

    name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "display_name", "name", "bio", "avatar", "created_at")
        read_only_fields = ("id", "username", "created_at")

    def validate_avatar(self, value: Any) -> Any:
        if value is None:
            return value
        if not hasattr(value, "size"):
            # PATCH без файла: DRF отдаёт либо None, либо уже готовый ContentFile.
            return value
        return process_avatar(value)

    def update(self, instance: User, validated_data: dict[str, Any]) -> User:
        avatar = validated_data.pop("avatar", serializers.empty)
        instance = super().update(instance, validated_data)
        if avatar is not serializers.empty:
            # Удаляем старый файл, иначе media переполнится аватарами-сиротами.
            if avatar is None and instance.avatar:
                instance.avatar.delete(save=False)
            instance.avatar = avatar
            instance.save(update_fields=["avatar", "updated_at"])
        return instance


class RegisterSerializer(serializers.Serializer):
    username = serializers.RegexField(
        r"^[A-Za-z0-9_]{3,32}$",
        error_messages={
            "invalid": _("От 3 до 32 символов: латинские буквы, цифры и подчёркивание."),
        },
        help_text="Используется для входа, менять нельзя.",
    )
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    display_name = serializers.CharField(max_length=64, required=False, allow_blank=True)

    def validate_username(self, value: str) -> str:
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Такое имя уже занято")
        return value

    def validate_password(self, value: str) -> str:
        # Обычные валидаторы Django не знают про username — подсказываем похожесть,
        # чтобы пароль «islam123» не прошёл при username=islam.
        candidate = self.initial_data.get("username", "") or ""
        try:
            password_validation.validate_password(value, user=User(username=candidate))
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from None
        return value

    def create(self, validated_data: dict[str, Any]) -> User:
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=validated_data["username"],
                    password=validated_data["password"],
                    display_name=validated_data.get("display_name", ""),
                )
        except IntegrityError:
            # Ограничение в БД сработало, хотя exists() его не поймал: параллельная
            # регистрация того же имени в другом регистре.
            raise serializers.ValidationError({"username": ["Такое имя уже занято"]}) from None
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        user = User.objects.filter(username__iexact=attrs["username"]).first()
        # Одно сообщение на «нет такого пользователя» и «неверный пароль»:
        # иначе перебором логинов можно узнать, кто зарегистрирован.
        if user is None or not user.check_password(attrs["password"]):
            raise serializers.ValidationError({"detail": ["Неверное имя пользователя или пароль"]})
        if not user.is_active:
            raise serializers.ValidationError({"detail": ["Учётная запись отключена"]})
        attrs["user"] = user
        return attrs
