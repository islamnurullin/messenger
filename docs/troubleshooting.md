# локальные проблемы и как их читать

Документ про то, что ломается **на этой машине** и почему. Общие инструкции — в
[README](../README.md).

## `pip install` не качает пакеты: SEC_E_NO_CREDENTIALS

> Если на машине включён системный прокси, сначала проверьте раздел
> [502 на localhost](#502-bad-gateway-на-http1270018000-системный-прокси): симптом
> выглядит как проблема TLS, но причиной часто оказывается прокси.

> **Чем это закончилось на практике.** Причина оказалась не в сети и не в
> сертификатах, а в том же ограниченном токене, что и `spawn EPERM` (см. ниже):
> процесс не имел доступа к профилю ключей пользователя. После установки настоящего
> PowerShell 7 и перезапуска `pip install` прошёл без единой ошибки, а
> `Invoke-WebRequest https://pypi.org/simple/django/` стал отдавать 200.
> Раздел оставлен как список того, что стоит проверить, если ошибка вернётся.

### Симптом

```
pip install -r requirements.txt      # висит без вывода, потом отваливается
curl.exe https://pypi.org/simple/     # curl: (35) schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030E)
```

При этом `Test-NetConnection pypi.org -Port 443` возвращает `True`.

### Почему это обманчиво

`Test-NetConnection` проверяет только TCP-рукопожатие. Оно проходит. Ломается
следующий шаг — TLS: Windows-провайдер schannel не может получить учётные данные
(`AcquireCredentialsHandle`), поэтому рукопожатие не начинается, и `http=000`.

То есть «интернет есть, но HTTPS не работает» — это не про сеть. И `pip install`
при этом не «медленный»: он висит на попытке установить TLS-соединение.

### Причина

`SEC_E_NO_CREDENTIALS` возникает, когда процесс не имеет доступа к хранилищу ключей
пользователя. Типичные случаи:

- процесс запущен с ограниченным токеном (sandbox, AppContainer, служба);
- профиль `%APPDATA%\Microsoft\Crypto` повреждён или недоступен;
- корпоративный TLS-инспектор подменяет сертификат, а корневой сертификат не установлен.

### Что делать

1. **Запустить установку вне ограниченного окружения.** Обычный терминал
   (PowerShell от своего пользователя) — не из-под песочницы и не от администратора.
2. Если не помогло — проверить, что сертификаты читаются:

   ```powershell
   certutil -store Root | Select-Object -First 5
   ```

   Ошибка доступа здесь подтверждает проблему с профилем ключей.
3. Обходной путь — использовать индекс с HTTP, если сеть доверенная (не рекомендуется):

   ```powershell
   pip install -r requirements.txt --index-url http://pypi.org/simple --trusted-host pypi.org
   ```

4. Если TLS-инспектор: узнать у администратора сети путь к корневому сертификату и
   сослаться на него:

   ```powershell
   pip install -r requirements.txt --cert "C:\path\to\corporate-root.crt"
   setx REQUESTS_CA_BUNDLE "C:\path\to\corporate-root.crt"
   ```

5. **Не запускать несколько `pip install` в один venv одновременно.** Два-три
   параллельных процесса в `.venv` блокируют друг другу файлы, и установка выглядит
   как зависание. Если это уже случилось: убить все python-процессы, удалить `.venv`
   и создать заново.

6. Если `%TEMP%` недоступен на запись (`PermissionError: [WinError 5]`), ставить без
   кеша и без временных каталогов:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt --progress-bar off
   ```

## Ни одна команда не запускается: `spawn EPERM`

### Симптом

```
Error: spawn EPERM
subprocess failed before reporting an outcome: Error: spawn EPERM
```

Ошибка появляется при любой команде — обычной, фоновой, из любой папки, и не
исчезает после перезапуска DSH. Переключение на полный доступ не помогает.

### Причина: заглушка вместо PowerShell

DSH запускает команды через `pwsh.exe`. Функция `candidatePwshPaths` перебирает
варианты в таком порядке:

1. `C:\Program Files\PowerShell\7\pwsh.exe`;
2. всё, что найдётся в `PATH`;
3. `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe` — только если не
   нашлось ничего другого.

Если PowerShell 7 не установлен, срабатывает пункт 2, а в `PATH` лежит
`%LOCALAPPDATA%\Microsoft\WindowsApps\pwsh.exe`. Это **не программа**, а алиас
Microsoft Store: файл-заглушка размером 0 байт. Чтение его напрямую даёт
`EACCES: permission denied`, запуск из фонового процесса — `spawn EPERM`.

Диагностика подтвердила:

```
Get-Command pwsh -All
  Name   : pwsh.exe
  Source : C:\Users\<вы>\AppData\Local\Microsoft\WindowsApps\pwsh.exe

Test-Path 'C:\Program Files\PowerShell\7\pwsh.exe'
  False
```

### Что делать

Установить PowerShell 7 — он встанет в стандартное место и перекроет заглушку:

```powershell
winget install --id Microsoft.PowerShell --source winget
```

Или из Microsoft Store: найти «PowerShell», установить.

После установки **полностью перезапустить DSH** и проверить:

```powershell
Get-Command pwsh -All | Select-Object Source
```

> **Важно:** установка из Microsoft Store кладёт файлы в
> `%LOCALAPPDATA%\Microsoft\WindowsApps\Microsoft.PowerShell_<hash>\pwsh.exe`, а не в
> `C:\Program Files\PowerShell\7\`. Проверять `Test-Path 'C:\Program Files\PowerShell\7\pwsh.exe'`
> в этом случае бессмысленно — он останется `False`, но команды уже работают.
> Надёжный признак: `pwsh --version` отвечает, а `Source` в `Get-Command` указывает
> на путь с `Microsoft.PowerShell_` внутри.

### Запасной вариант

Если PowerShell 7 ставить нельзя, можно явно указать DSH системный
Windows PowerShell 5.1. В `C:\Users\<вы>\.dsh\profiles\desktop\cordis.patch.yml`
добавить в конец:

```yaml
- id: pwsh-sandbox
  config:
    pwshPath: 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
```

и перезапустить DSH. Минус: 5.1 старее, и часть современных конструкций в
`scripts/*.ps1` (например, тернарный оператор `? :`) в нём не работает.

## Другой случай: `CreateProcessAsUserW failed (Win32 5)`

### Симптом

```
sandbox mode "workspace-write" is requested but no sandbox backend is usable on this host
Runner failure: windows-acl-run: CreateProcessAsUserW failed (Win32 5)
```

### Причина

DSH на Windows запускает команды в ограниченном токене и для этого создаёт процесс
через `CreateProcessAsUserW`. Ошибка 5 (`ERROR_ACCESS_DENIED`) означает, что прав на
папку проекта не хватает, чтобы подготовить это окружение.

Это **другая** ошибка, чем `spawn EPERM`: здесь не хватает прав на папку, там —
не запускается сам исполняемый файл.

### Что делать

1. Проверить и починить права на папку проекта и её родителей — есть готовый
   диагностический скрипт (skill `diagnose-windows-sandbox-acl`).
2. Пока не починено — работать с полным доступом к файловой системе
   (в настройках сессии: **full access** / 完全权限).

Команды для ручной проверки прав:

```powershell
icacls "D:\projects\messenger"
icacls "D:\projects"
```

В выводе у вашей учётной записи должно быть `(F)` — полный доступ. Если есть только
`(RX)` или записи нет, нужен ремонт.

## Docker: `npipe:////./pipe/dockerDesktopLinuxEngine` недоступен

Docker CLI установлен, но демон не запущен. Откройте Docker Desktop и дождитесь
статуса **running** (иконка кита перестанет анимироваться), затем:

```powershell
docker info
```

Если `docker info` падает — перезапускать Docker Desktop, а не compose.

## `docker compose up` проходит, а `/api/health` возвращает `degraded`

Это не ошибка: `degraded` означает, что PostgreSQL и Redis живы, а Centrifugo или
Elasticsearch — нет. Проверьте конкретный сервис:

```powershell
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml logs centrifugo --tail 30
```

Если Elasticsearch вообще не запускался — он в профиле `search` и по умолчанию
выключен. Статус `disabled` в ответе — ожидаемый.

### Особый случай: Centrifugo живой, но проверка даёт 404

```
"centrifugo": { "status": "error", "http_status": 404 }
```

**В Centrifugo v6 нет эндпоинта `GET /health`.** Он был в ранних версиях и оттуда
попал в примеры, но в шестой ветке такого маршрута нет — на любой путь, кроме
websocket и `/api`, отвечает `404 page not found`.

Проверять надо не `GET /health`, а HTTP API: `POST /api` с методом `info` и ключом
в заголовке `X-API-Key`. Именно так это сделано в `apps/common/health.py`:

```powershell
curl.exe -X POST http://127.0.0.1:8001/api `
  -H "Content-Type: application/json" `
  -H "X-API-Key: dev-centrifugo-api-key-change-me" `
  -d '{\"method\":\"info\"}'
```

Успех — `200` и `{"result":{"nodes":[...]}}`. Если вернулось `401` — не тот ключ;
если `200` с `{"error":...}` — ключ принят, но запрос отвергнут.

## `502 Bad Gateway` на `http://127.0.0.1:8000`: системный прокси

Сервер точно запущен, `docker compose ps` показывает `healthy`, но любой запрос к
`127.0.0.1` возвращает `502`, а `curl.exe` — код `000`. Причём Python и
`Invoke-RestMethod` падают, а браузер может работать.

**Причина — системный прокси.** На вузовских и корпоративных машинах в реестре
включён прокси без списка исключений:

```powershell
Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' |
  Select-Object ProxyEnable, ProxyServer, ProxyOverride
```

```
ProxyEnable   : 1
ProxyServer   : 10.144.23.8:8080
ProxyOverride :
```

`httpx`, `urllib` и `curl` читают эти настройки автоматически и гоняют через прокси
**даже запросы к localhost** — хотя `netsh winhttp show proxy` при этом честно пишет
«Direct access». Отсюда и `502` от живого сервера, и загадочный
`SEC_E_NO_CREDENTIALS` при установке пакетов: это был не TLS, а прокси.

Проверить гипотезу, обойдя прокси:

```powershell
python -c "import urllib.request; print(urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8000/api/health').status)"
```

Если вернулось `200` — причина подтверждена.

Лечение — три варианта, по возрастанию радикальности:

1. **Добавить исключение** (рекомендуется). Параметры обозревателя → Подключения →
   Настройка сети → Дополнительно → в «Исключения» вписать:

   ```
   localhost;127.0.0.1;::1;*.local
   ```

   То же самое из PowerShell:

   ```powershell
   Set-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' `
     -Name ProxyOverride -Value 'localhost;127.0.0.1;::1;*.local'
   ```

2. **Отключить прокси на время работы** — тот же переключатель «Использовать прокси
   для локальных подключений» снять.

3. **Игнорировать прокси в коде** — так сделано в `apps/common/health.py`:

   ```python
   HTTPX_LOCAL = {"trust_env": False, "timeout": CHECK_TIMEOUT_SECONDS}
   ```

   `trust_env=False` заставляет httpx не читать ни переменные окружения, ни реестр.
   Для проверки локального контейнера это правильно: гонять health-check через
   внешний прокси бессмысленно.

> `curl.exe` на Windows использует schannel и системный прокси; `curl` из Git Bash —
> свой. Поэтому одна и та же команда в разных терминалах может вести себя по-разному.

## Django подключается не к той базе: порт 5432 занят

### Симптом

```
django.db.utils.OperationalError: connection failed: connection to server at
"127.0.0.1", port 5432 failed: ...
```

Сообщение приходит в системной кодировке (cp1251) и выглядит кракозябрами, поэтому
понять его с первого раза трудно. Если добавить `$env:PYTHONIOENCODING='utf-8'`,
текст становится читаемым.

### Причина

На машине работает **нативная** служба PostgreSQL, которая уже слушает 5432:

```powershell
Get-Service postgresql*
```

Docker в такой ситуации не может опубликовать порт 5432 — он молча остаётся за
нативной службой, и Django подключается к чужому серверу, где базы `messenger` нет.

### Что делать

Проект уже настроен на порт **5433**, чтобы конфликта не было (`infra/docker-compose.yml`,
`base.py`, `.env.example`). Проверить:

```powershell
docker compose -f infra/docker-compose.yml ps     # messenger-postgres-1 -> 0.0.0.0:5433->5432
Get-NetTCPConnection -LocalPort 5433 -State Listen
```

Останавливать нативную службу не нужно. Если же 5432 свободен и хочется стандартного
порта — вернуть его через `.env`: `POSTGRES_HOST_PORT=5432` и `POSTGRES_PORT=5432`.

## `manage.py` работает без `.env`

До исправления `backend/.env` создавался скриптом, но **нигде не читался**: настройки
молча брали значения по умолчанию. Теперь `config/settings/base.py` загружает его через
`python-dotenv` с `override=False` — переменные окружения из Docker и CI остаются
главнее файла.

Если настройки «не применяются», проверьте по порядку:

```powershell
# 1. файл есть?
Test-Path backend\.env
# 2. что видит Django на самом деле?
cd backend; .\.venv\Scripts\python.exe -c "import os,django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.dev'); django.setup(); from django.conf import settings; print(settings.DATABASES['default']['PORT'])"
```
