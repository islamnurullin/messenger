# локальные проблемы и как их читать

Документ про то, что ломается **на этой машине** и почему. Общие инструкции — в
[README](../README.md).

## `pip install` не качает пакеты: SEC_E_NO_CREDENTIALS

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

То есть «интернет есть, но HTTPS не работает» — это не про сеть.

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
Test-Path 'C:\Program Files\PowerShell\7\pwsh.exe'   # должно стать True
```

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
