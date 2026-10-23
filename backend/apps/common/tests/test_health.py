"""Тесты health-check.

Проверяем не «эндпоинт отвечает 200», а то, что он различает состояния:
живая БД при мёртвом Redis — это 503, а не ok.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def _get(client):
    return client.get(reverse("common:health"))


def test_health_ok_when_all_critical_dependencies_alive(client):
    with (
        patch("apps.common.health._check_redis", return_value={"status": "ok"}),
        patch("apps.common.health._check_centrifugo", return_value={"status": "ok"}),
    ):
        response = _get(client)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["checks"]["database"]["status"] == "ok"


def test_health_returns_503_when_database_down(client):
    with (
        patch(
            "apps.common.health._check_database",
            return_value={"status": "error", "error": "connection refused"},
        ),
        patch("apps.common.health._check_redis", return_value={"status": "ok"}),
    ):
        response = _get(client)

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


def test_health_returns_503_when_redis_down(client):
    """Redis обязателен: без него не работают очереди и Centrifugo."""
    with patch(
        "apps.common.health._check_redis",
        return_value={"status": "error", "error": "timed out"},
    ):
        response = _get(client)

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"


def test_health_degraded_when_centrifugo_down(client):
    """Centrifugo не обязателен для записи: сообщения сохранятся, доставка — нет."""
    with (
        patch("apps.common.health._check_redis", return_value={"status": "ok"}),
        patch(
            "apps.common.health._check_centrifugo",
            return_value={"status": "error", "error": "connect failed"},
        ),
    ):
        response = _get(client)

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_health_is_public(client):
    """Health-check не требует токена — иначе им не сможет пользоваться мониторинг."""
    response = _get(client)
    assert response.status_code != 401
    assert response.status_code != 403


def test_elasticsearch_disabled_by_default(client):
    with (
        patch("apps.common.health._check_redis", return_value={"status": "ok"}),
        patch("apps.common.health._check_centrifugo", return_value={"status": "ok"}),
    ):
        response = _get(client)

    assert response.json()["checks"]["elasticsearch"]["status"] == "disabled"


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_centrifugo_check_uses_http_api_not_health_endpoint():
    """Регрессия: в Centrifugo v6 нет GET /health, он отдаёт 404.

    Из-за этого health-check всегда показывал degraded. Правильный признак
    жизни — POST /api с методом info и API-ключом.
    """
    from apps.common.health import _check_centrifugo

    with patch("httpx.post", return_value=_FakeResponse(200, {"result": {"nodes": [{}]}})) as post:
        result = _check_centrifugo()

    assert result["status"] == "ok"
    url = post.call_args.args[0]
    assert url.endswith("/api")
    assert post.call_args.kwargs["json"] == {"method": "info"}


def test_centrifugo_check_reports_error_on_200_with_error_body():
    """200 с телом {"error": ...} — это отказ (неверный ключ), а не успех."""
    from apps.common.health import _check_centrifugo

    body = {"error": {"code": 107, "message": "bad request"}}
    with patch("httpx.post", return_value=_FakeResponse(200, body)):
        result = _check_centrifugo()

    assert result["status"] == "error"
    assert result["error"] == "bad request"
