from django.test import TestCase

from apps.common.health import health  # noqa: F401  — импорт проверяет, что модуль собирается


class HealthSmokeTests(TestCase):
    """Минимальная проверка через Django test client (без pytest)."""

    def test_endpoint_exists(self):
        response = self.client.get("/api/health")
        self.assertIn(response.status_code, (200, 503))
