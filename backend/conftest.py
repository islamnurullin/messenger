"""Общие фикстуры pytest."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model


@pytest.fixture(autouse=True)
def _isolated_media_root(tmp_path, settings):
    """Тесты не должны писать файлы в ``backend/media/``.

    Без этого каждый прогон оставляет аватары в рабочей копии: они попадают в
    ``git status``, и через неделю папка media весит мегабайты. ``tmp_path``
    живёт вне репозитория и удаляется pytest сам.
    """
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def user(db):
    """Обычный активный пользователь."""
    return get_user_model().objects.create_user(
        username="islam",
        password="test-pass-12345",
        display_name="Ислам",
    )


@pytest.fixture
def other_user(db):
    """Второй пользователь — для проверок доступа к чужим чатам."""
    return get_user_model().objects.create_user(
        username="alice",
        password="test-pass-12345",
        display_name="Алиса",
    )
