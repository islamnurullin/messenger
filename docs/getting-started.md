# Первый запуск — по шагам

Короткая инструкция для этой машины. Подробности — в [troubleshooting](troubleshooting.md).

## Одноразово

```powershell
# 1. Права на папку проекта (если DSH не может запускать команды)
#    Запустить в обычном PowerShell от своего пользователя:
icacls "D:\projects\messenger" /grant "$($env:USERNAME):(OI)(CI)F" /T

# 2. Всё остальное делает скрипт
cd D:\projects\messenger
.\scripts\setup.ps1
```

`setup.ps1` создаст venv, поставит зависимости, поднимет Docker, применит миграции и
проверит health-check. Повторный запуск безопасен.

Если `pip` не может скачать пакеты (ошибка `SEC_E_NO_CREDENTIALS`) — см.
[troubleshooting](troubleshooting.md#pip-install-не-качает-пакеты-sec_e_no_credentials):
проблема в TLS, а не в сети, и лечится запуском в обычном терминале или указанием
корпоративного сертификата.

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
