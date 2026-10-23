# Messenger

Учебный мессенджер: личные сообщения, группы и каналы. Веб на SvelteKit, десктоп на
Electron, мобильное приложение на Flutter. Бэкенд — Django + PostgreSQL, доставка в
реальном времени — Centrifugo, полнотекстовый поиск — Elasticsearch.

> **Статус: неделя 1 из 12 — выполнена.** Каркас монорепо, инфраструктура и health-check
> работают и проверены. Переписки пока нет: это неделя 2 «Аккаунты».

## Что уже работает

- Инфраструктура поднимается одной командой (PostgreSQL, Redis, Centrifugo).
- `GET /api/health` проверяет каждую зависимость отдельно и отдаёт `ok` / `degraded` /
  `unavailable` — по нему видно, что именно отвалилось.
- Веб-интерфейс показывает состояние системы на странице `/status`.
- Кастомная модель пользователя с входом по логину и паролю (без телефона).

## Требования

| Инструмент | Версия | Зачем |
|---|---|---|
| Python | 3.12+ | бэкенд |
| Node.js | 22+ | веб и десктоп |
| Docker Desktop | 4.x+ | PostgreSQL, Redis, Centrifugo, Elasticsearch |
| Git | 2.40+ | версии |
| PowerShell | 7+ | скрипты `scripts/*.ps1` |

Flutter и Android SDK понадобятся только с недели 8 — сейчас их можно не ставить.

> **PowerShell 7 нужен именно как `pwsh`.** В Windows есть 5.1 (`powershell.exe`), но в
> `%LOCALAPPDATA%\Microsoft\WindowsApps` может лежать 0-байтная заглушка `pwsh.exe`,
> которая не запускается. Установка: `winget install --id Microsoft.PowerShell -e`.

## Быстрый старт

```bash
git clone <url> messenger
cd messenger
cp .env.example .env
```

> Первый запуск на Windows одной командой: `.\scripts\setup.ps1`. Скрипт создаёт venv,
> ставит зависимости, поднимает Docker и применяет миграции. Пошагово —
> [docs/getting-started.md](docs/getting-started.md). Если что-то не запускается —
> [docs/troubleshooting.md](docs/troubleshooting.md).

### 1. Инфраструктура

```bash
docker compose -f infra/docker-compose.yml up -d
```

Поднимаются три сервиса: PostgreSQL (`5433` на хосте), Redis (`6379`), Centrifugo (`8001`).
Elasticsearch вынесен в отдельный профиль, потому что ест ~1.5 ГБ RAM:

```bash
docker compose -f infra/docker-compose.yml --profile search up -d
```

> **Почему PostgreSQL на 5433, а не на 5432.** На Windows часто уже работает нативная
> служба `postgresql-x64-*` (ставится вместе с pgAdmin или другими курсовыми), и она
> занимает 5432. Docker тогда не может опубликовать порт, а Django подключается к чужой
> базе и падает с невнятной ошибкой. Если 5432 свободен, можно вернуть стандартный порт
> через `POSTGRES_HOST_PORT=5432` и `POSTGRES_PORT=5432` в `.env`.

### 2. Бэкенд

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # Windows (PowerShell: .venv\Scripts\Activate.ps1)
# source .venv/bin/activate        # macOS / Linux
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

API — http://127.0.0.1:8000, админка — http://127.0.0.1:8000/admin/.

### 3. Веб

```bash
cd web
npm install
npm run dev
```

Интерфейс — http://localhost:5173.

### Проверка, что всё сошлось

```bash
curl http://127.0.0.1:8000/api/health
```

```json
{
  "status": "ok",
  "checks": {
    "database": { "status": "ok", "latency_ms": 45.5 },
    "redis": { "status": "ok", "latency_ms": 281.4 },
    "centrifugo": { "status": "ok", "latency_ms": 1194.18, "nodes": 1, "version": "6.10.2 OSS" },
    "elasticsearch": { "status": "disabled" }
  }
}
```

Если `status` — `degraded`, значит живы БД и Redis, но не отвечает Centrifugo или поиск:
приложение работает, доставка в реальном времени — нет. `unavailable` и код 503 означают,
что лежит БД или Redis.

> Centrifugo проверяется через `POST /api` с методом `info`, а не через `GET /health`:
> в Centrifugo v6 такого эндпоинта нет, и запрос к нему всегда возвращает 404. Подробнее —
> [docs/troubleshooting.md](docs/troubleshooting.md#особый-случай-centrifugo-живой-но-проверка-даёт-404).

## Структура репозитория

```
backend/          Django: REST API, модели, Celery-задачи
  apps/
    accounts/     пользователи, аутентификация
    chats/        чаты и участники
    messaging/    сообщения
    realtime/     выдача токенов и публикация в Centrifugo
    search/       индексация в Elasticsearch
    common/       health-check, общий формат ошибок
  config/         настройки, urls, celery, asgi
web/              SvelteKit: веб-клиент
infra/            docker-compose и конфиг Centrifugo
docs/adr/         архитектурные решения
PLAN.md           план на 12 недель
SPEC.md           техническое задание
```

## Разработка

### Ветки

- `main` — то, что сдаётся. Только через merge из `develop`.
- `develop` — интеграционная ветка.
- `feature/<тема>` — задачи. Ветвится от `develop`, вливается обратно через PR.

Коммиты — в формате [Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.

### Тесты и линтеры

```bash
# бэкенд
cd backend
pytest
ruff check .
ruff format --check .

# веб
cd web
npm run check
npm run lint
```

## Архитектурные решения

Ключевые решения и причины, по которым они приняты, — в [`docs/adr/`](docs/adr/):

- [0001 — выбор стека](docs/adr/0001-stack.md)
- [0002 — монотонный `seq` вместо сортировки по времени](docs/adr/0002-monotonic-seq.md)
- [0003 — порядок записи и публикации сообщения](docs/adr/0003-write-then-publish.md)

## Лицензия

Учебный проект, лицензия не задана.
