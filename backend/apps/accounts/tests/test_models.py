from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_create_user_sets_password_hash(user):
    assert user.pk is not None
    assert user.check_password("test-pass-12345")
    assert user.password != "test-pass-12345"


def test_username_is_required():
    with pytest.raises(ValueError):
        User.objects.create_user(username="", password="x")


def test_username_is_unique(user):
    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        User.objects.create_user(username=user.username, password="other-pass-123")


def test_display_name_falls_back_to_username(user):
    """В списках чатов должно быть что показать, даже если имя не задано."""
    user.display_name = ""
    assert user.name == user.username


def test_superuser_flags():
    admin = User.objects.create_superuser(username="root", password="root-pass-123")
    assert admin.is_staff is True
    assert admin.is_superuser is True
