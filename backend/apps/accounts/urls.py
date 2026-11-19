"""Маршруты аккаунтов. Подключаются в config/urls.py под префиксом ``api/``."""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginView, MeView, RegisterView

app_name = "accounts"

urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="register"),
    path("auth/login", LoginView.as_view(), name="login"),
    path("auth/refresh", TokenRefreshView.as_view(), name="refresh"),
    path("me", MeView.as_view(), name="me"),
]
