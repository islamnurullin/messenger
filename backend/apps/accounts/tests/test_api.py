"""Тесты аккаунтов: регистрация, вход, обновление токена, профиль, аватар."""

from __future__ import annotations

import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

User = get_user_model()

REGISTER_URL = "/api/auth/register"
LOGIN_URL = "/api/auth/login"
REFRESH_URL = "/api/auth/refresh"
ME_URL = "/api/me"


@pytest.fixture
def client_api() -> APIClient:
    return APIClient()


def _image_bytes(size: tuple[int, int] = (300, 200), fmt: str = "PNG") -> bytes:
    image = Image.new("RGB", size, (30, 120, 200))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _register(client_api: APIClient, **overrides: object) -> dict:
    payload = {
        "username": "newuser",
        "password": "strong-pass-98765",
        "display_name": "Новый",
    }
    payload.update(overrides)
    response = client_api.post(REGISTER_URL, payload, format="json")
    return {"status": response.status_code, "data": response.json()}


# --- Регистрация -----------------------------------------------------------


def test_register_returns_tokens_and_profile(client_api):
    result = _register(client_api)
    assert result["status"] == 201
    data = result["data"]
    assert data["access"]
    assert data["refresh"]
    assert data["user"]["username"] == "newuser"
    assert data["user"]["name"] == "Новый"
    # Служебные поля не должны утекать в ответ.
    assert "is_staff" not in data["user"]
    assert "password" not in data["user"]


def test_register_stores_password_hashed(client_api):
    _register(client_api)
    user = User.objects.get(username="newuser")
    assert user.password != "strong-pass-98765"
    assert user.check_password("strong-pass-98765")


def test_register_rejects_duplicate_username_in_other_case(client_api):
    _register(client_api, username="Islam")
    result = _register(client_api, username="islam")
    assert result["status"] == 400
    assert "username" in str(result["data"])


def test_register_rejects_weak_password(client_api):
    result = _register(client_api, password="123")
    assert result["status"] == 400


def test_register_rejects_password_similar_to_username(client_api):
    """Пароль, почти совпадающий с ником, валидатор Django должен ловить.

    Внимание на границу: ``islam12345`` при username ``islam`` валидатор
    **пропускает** — SequenceMatcher даёт 0.67 при пороге 0.7. Проверяем случай,
    который он действительно отсекает, иначе тест проверяет не то, что заявлено.
    """
    result = _register(client_api, username="islamnurullin", password="islamnurullin1")
    assert result["status"] == 400
    assert "password" in str(result["data"])


def test_register_rejects_invalid_username_characters(client_api):
    result = _register(client_api, username="ислам")
    assert result["status"] == 400


# --- Вход ------------------------------------------------------------------


def test_login_returns_tokens(client_api, user):
    response = client_api.post(
        LOGIN_URL, {"username": "islam", "password": "test-pass-12345"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["access"]
    assert response.json()["user"]["username"] == "islam"


def test_login_is_case_insensitive_for_username(client_api, user):
    response = client_api.post(
        LOGIN_URL, {"username": "ISLAM", "password": "test-pass-12345"}, format="json"
    )
    assert response.status_code == 200


def test_login_updates_last_seen(client_api, user):
    assert user.last_seen_at is None
    client_api.post(LOGIN_URL, {"username": "islam", "password": "test-pass-12345"}, format="json")
    user.refresh_from_db()
    assert user.last_seen_at is not None


def test_login_wrong_password_does_not_reveal_user_existence(client_api, user):
    """Одинаковый ответ на «нет такого» и «неверный пароль» — иначе перебор логинов."""
    wrong_pass = client_api.post(
        LOGIN_URL, {"username": "islam", "password": "nope-nope-1"}, format="json"
    )
    no_user = client_api.post(
        LOGIN_URL, {"username": "ghost", "password": "nope-nope-1"}, format="json"
    )
    assert wrong_pass.status_code == no_user.status_code == 400
    assert wrong_pass.json()["error"]["details"] == no_user.json()["error"]["details"]


def test_login_inactive_user_is_rejected(client_api, user):
    user.is_active = False
    user.save(update_fields=["is_active"])
    response = client_api.post(
        LOGIN_URL, {"username": "islam", "password": "test-pass-12345"}, format="json"
    )
    assert response.status_code == 400


# --- Обновление токена -----------------------------------------------------


def test_refresh_returns_new_access(client_api, user):
    tokens = client_api.post(
        LOGIN_URL, {"username": "islam", "password": "test-pass-12345"}, format="json"
    ).json()
    response = client_api.post(REFRESH_URL, {"refresh": tokens["refresh"]}, format="json")
    assert response.status_code == 200
    assert response.json()["access"]


def test_refresh_with_garbage_token_is_rejected(client_api):
    response = client_api.post(REFRESH_URL, {"refresh": "not-a-token"}, format="json")
    assert response.status_code in {400, 401}


# --- Профиль ---------------------------------------------------------------


def test_me_requires_auth(client_api):
    response = client_api.get(ME_URL)
    assert response.status_code == 401


def test_me_returns_own_profile(client_api, user):
    client_api.force_authenticate(user=user)
    response = client_api.get(ME_URL)
    assert response.status_code == 200
    assert response.json()["username"] == "islam"
    assert response.json()["name"] == "Ислам"


def test_patch_me_updates_display_name_and_bio(client_api, user):
    client_api.force_authenticate(user=user)
    response = client_api.patch(
        ME_URL, {"display_name": "Ислам Н.", "bio": "Студент"}, format="json"
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.display_name == "Ислам Н."
    assert user.bio == "Студент"


def test_patch_me_cannot_change_username(client_api, user):
    """username — идентификатор входа, его смена ломает чужое представление о тебе."""
    client_api.force_authenticate(user=user)
    response = client_api.patch(ME_URL, {"username": "hacker"}, format="json")
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.username == "islam"


def test_patch_me_does_not_touch_other_user(client_api, user, other_user):
    """Маршрута с чужим id нет вообще — правится только request.user."""
    client_api.force_authenticate(user=user)
    client_api.patch(ME_URL, {"display_name": "Взлом"}, format="json")
    other_user.refresh_from_db()
    assert other_user.display_name == "Алиса"


# --- Аватар ----------------------------------------------------------------


def test_patch_avatar_stores_square_jpeg(client_api, user):
    client_api.force_authenticate(user=user)
    upload = SimpleUploadedFile("photo.png", _image_bytes((300, 200)), content_type="image/png")
    response = client_api.patch(ME_URL, {"avatar": upload}, format="multipart")
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.avatar
    with Image.open(user.avatar.path) as stored:
        assert stored.format == "JPEG"
        # Квадрат по меньшей стороне, но без апскейла: растягивать 200px до 256
        # значит добавлять размытие, которого в исходнике нет.
        assert stored.size == (200, 200)


def test_patch_avatar_downscales_large_image(client_api, user):
    client_api.force_authenticate(user=user)
    upload = SimpleUploadedFile("big.png", _image_bytes((1200, 800)), content_type="image/png")
    response = client_api.patch(ME_URL, {"avatar": upload}, format="multipart")
    assert response.status_code == 200
    user.refresh_from_db()
    with Image.open(user.avatar.path) as stored:
        assert stored.size == (256, 256)


def test_patch_avatar_rejects_non_image(client_api, user):
    client_api.force_authenticate(user=user)
    upload = SimpleUploadedFile("evil.png", b"not really an image", content_type="image/png")
    response = client_api.patch(ME_URL, {"avatar": upload}, format="multipart")
    assert response.status_code == 400
    user.refresh_from_db()
    assert not user.avatar


def test_patch_avatar_rejects_oversized_file(client_api, user, settings):
    settings.ATTACHMENT_MAX_BYTES = 1024
    client_api.force_authenticate(user=user)
    upload = SimpleUploadedFile("big.png", _image_bytes((800, 800)), content_type="image/png")
    response = client_api.patch(ME_URL, {"avatar": upload}, format="multipart")
    assert response.status_code == 400
