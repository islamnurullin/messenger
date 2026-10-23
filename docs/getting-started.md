# Первый запуск — по шагам

Короткая инструкция для этой машины. Подробности — в [troubleshooting](troubleshooting.md).

## Что должно быть установлено

| Инструмент | Проверка | Зачем |
|---|---|---|
| Python 3.12+ | `python --version` | бэкенд |
| Node.js 22+ | `node --version` | веб-клиент |
| Git | `git --version` | сдача работы |
| Docker Desktop | `docker info` | PostgreSQL, Redis, Centrifugo |
| PowerShell 7 | `pwsh --version` | скрипты проекта |

> **PowerShell 7 обязателен именно как `pwsh`.** Windows поставляется с PowerShell 5.1
> (`powershell.exe`), но в `WindowsApps` лежит 0-байтная заглушка `pwsh.exe`, которая
> выдаёт `EACCES` при запуске. Если `pwsh --version` не отвечает — установите
> PowerShell 7: `winget install --id Microsoft.PowerShell -e` либо из Microsoft Store.
> Подробнее — [troubleshooting](troubleshooting.md#ни-одна-команда-не-запускается-spawn-eperm).

## Одноразово

```powershell
# 1. Запустить Docker Desktop и дождаться, пока поднимется демон
Start-Process "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
docker info --format '{{.ServerVersion}}'   # должно вывести версию

# 2. Всё остальное делает скрипт
cd D:\projects\messenger
.\scripts\setup.ps1
```

`setup.ps1` создаст venv, поставит зависимости, поднимет контейнеры, применит миграции
и проверит health-check. Повторный запуск безопасен.

Проверить, что ничего не забыто, можно в любой момент:

```powershell
.\scripts\doctor.ps1     # только читает, ничего не меняет
```

## Каждый день

Нужно три терминала.

```powershell
# Терминал 1 — инфраструктура (если ещё не поднята)
docker compose -f infra/docker-compose.yml up -d

# Терминал 2 — бэкенд
cd backend
.\.venv\Scripts\Activate.ps1
python manage.py runserver

# Терминал 3 — веб
cd web
npm run dev
```

Открыть http://localhost:5173 — на странице «Состояние» видно, что поднялось.

## Порты

| Сервис | Адрес | Примечание |
|---|---|---|
| Django | http://127.0.0.1:8000 | `/api/health`, `/admin/` |
| Веб-клиент | http://localhost:5173 | Vite, горячая перезагрузка |
| Centrifugo | ws://127.0.0.1:8001 | websocket |
| PostgreSQL | 127.0.0.1:**5433** | не 5432 — см. ниже |
| Redis | 127.0.0.1:6379 | |
| Elasticsearch | http://127.0.0.1:9200 | только с `--profile search` |

> **Почему PostgreSQL на 5433.** На этой машине работает нативная служба
> `postgresql-x64-17`, которая занимает 5432. Docker не может опубликовать занятый порт,
> а Django подключается к чужой базе и падает с ошибкой про базу `messenger`. Поэтому
> контейнер публикуется на 5433. Останавливать нативную службу не нужно.

## Остановить

```powershell
docker compose -f infra/docker-compose.yml down
```

Данные сохраняются в томах. Полная очистка (включая БД): добавить `-v`.

## Git

```powershell
.\scripts\git-init.ps1
```

Создаст `main`, первый коммит и ветку `develop`, на которую переключится. Дальше —
`git remote add origin <url>` и `git push -u origin main develop`.

## Что проверить перед сдачей

```powershell
cd backend;  .\.venv\Scripts\ruff.exe check .;  .\.venv\Scripts\python.exe -m pytest -q
cd ..\web;   npm run check;  npm run lint;  npm run build
curl http://127.0.0.1:8000/api/health
```

Ожидаемый ответ health-check — `"status": "ok"` и все проверки в состоянии `ok`
(Elasticsearch — `disabled`, если поиск не поднят).
