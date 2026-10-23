"""Проверка живости сервиса и его зависимостей.

Это не «/api/health возвращает ok» — цель в том, чтобы нагрузочный стенд и CI
могли отличить «Django поднялся» от «Django поднялся, но Postgres недоступен».
Поэтому каждый компонент проверяется отдельно и с коротким таймаутом.
"""

from __future__ import annotations

import logging
import time

from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)

# Короткий таймаут: health-check не должен висеть, если зависимость «почти жива».
CHECK_TIMEOUT_SECONDS = 2


def _check_database() -> dict:
    started = time.perf_counter()
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "ok", "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
    except OperationalError as exc:
        return {"status": "error", "error": str(exc)}


def _check_redis() -> dict:
    started = time.perf_counter()
    try:
        import redis

        client = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=CHECK_TIMEOUT_SECONDS,
            socket_timeout=CHECK_TIMEOUT_SECONDS,
        )
        client.ping()
        return {"status": "ok", "latency_ms": round((time.perf_counter() - started) * 1000, 2)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _check_centrifugo() -> dict:
    """Проверка через HTTP API Centrifugo, а не через /health.

    В Centrifugo v6 эндпоинта GET /health нет (он был в первых версиях) — запрос
    к нему всегда даёт 404, и health-check вечно показывал «degraded». Настоящий
    признак жизни — успешный ответ на POST /api с методом ``info``: он требует
    валидный API-ключ и реально ходит в движок (Redis).
    """
    started = time.perf_counter()
    try:
        import httpx

        response = httpx.post(
            f"{settings.CENTRIFUGO_HTTP_URL.rstrip('/')}/api",
            json={"method": "info"},
            headers={"X-API-Key": settings.CENTRIFUGO_API_KEY},
            timeout=CHECK_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    latency = round((time.perf_counter() - started) * 1000, 2)
    if response.status_code != 200:
        return {"status": "error", "http_status": response.status_code}

    # 200 с телом {"error": ...} — ключ не принят или запрос отвергнут.
    payload = response.json()
    if "error" in payload:
        return {"status": "error", "error": payload["error"].get("message", "unknown")}

    nodes = payload.get("result", {}).get("nodes", [])
    return {
        "status": "ok",
        "latency_ms": latency,
        "nodes": len(nodes),
        "version": nodes[0].get("version") if nodes else None,
    }


def _check_elasticsearch() -> dict:
    if not settings.ELASTICSEARCH_ENABLED:
        return {"status": "disabled"}
    started = time.perf_counter()
    try:
        import httpx

        response = httpx.get(
            f"{settings.ELASTICSEARCH_URL.rstrip('/')}/_cluster/health",
            timeout=CHECK_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "cluster": response.json().get("status"),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    """GET /api/health — сводка по зависимостям.

    Код ответа: 200, если обязательные зависимости (БД, Redis) живы, иначе 503.
    Centrifugo/Elasticsearch влияют на ``status``, но не на код: без поиска
    приложение работоспособно, а его отсутствие — деградация, не отказ.
    """
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
        "centrifugo": _check_centrifugo(),
        "elasticsearch": _check_elasticsearch(),
    }

    critical_ok = checks["database"]["status"] == "ok" and checks["redis"]["status"] == "ok"
    degraded = any(checks[name]["status"] == "error" for name in ("centrifugo", "elasticsearch"))

    if not critical_ok:
        overall = "unavailable"
    elif degraded:
        overall = "degraded"
    else:
        overall = "ok"

    logger.info("health check: %s", overall)

    return Response(
        {"status": overall, "checks": checks},
        status=status.HTTP_200_OK if critical_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
