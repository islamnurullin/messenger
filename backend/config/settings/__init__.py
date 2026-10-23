"""
Django settings package.

Выбор модуля — через DJANGO_SETTINGS_MODULE (по умолчанию config.settings.dev
в manage.py). Здесь ничего не импортируется специально: держим пакет тонким,
чтобы `django-admin` не тянул лишнего.
"""

__all__ = ["base", "dev", "prod"]
