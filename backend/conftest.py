"""Общие фикстуры pytest."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model


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
