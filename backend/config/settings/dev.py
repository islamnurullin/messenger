from .base import *

DEBUG = True

# В dev разрешаем всё локальное: Vite на 5173, Django на 8000, Centrifugo на 8001.
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True

INTERNAL_IPS = ["127.0.0.1"]

# Письма в консоль вместо SMTP.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
