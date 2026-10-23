# syntax=docker/dockerfile:1

# Образ для dev/CI: собран с wheel-кэшем, чтобы пересборка после правки кода
# была быстрой. Для продакшена нужен отдельный multi-stage — он появится на
# этапе деплоя (неделя 10).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# psycopg[binary] тянет готовые колёса, компилятор не нужен.
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
