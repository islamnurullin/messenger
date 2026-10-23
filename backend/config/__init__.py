"""Точка входа пакета config: подхватываем Celery, чтобы задачи были доступны."""

from .celery import app as celery_app

__all__ = ("celery_app",)
