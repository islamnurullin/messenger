#Requires -Version 5.1
<#
.SYNOPSIS
    Полная настройка окружения разработки с нуля.

.DESCRIPTION
    Идемпотентен: повторный запуск не ломает уже настроенное. Каждый шаг
    проверяет, сделан ли он, и сообщает, что пропущено.

    Шаги:
      1. Проверка инструментов (python, node, docker, git).
      2. venv + pip install для бэкенда.
      3. npm install для веба.
      4. docker compose up для PostgreSQL/Redis/Centrifugo.
      5. Миграции Django.
      6. Health-check.

.PARAMETER SkipInstall
    Пропустить pip/npm install (когда зависимости уже стоят).

.PARAMETER WithSearch
    Поднять Elasticsearch (профиль search, ~1.5 ГБ RAM).

.EXAMPLE
    .\scripts\setup.ps1
    .\scripts\setup.ps1 -WithSearch
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$WithSearch
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Write-Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  [ok] $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  [!]  $text" -ForegroundColor Yellow }
function Write-Err($text)  { Write-Host "  [x]  $text" -ForegroundColor Red }

# --- 1. Инструменты -----------------------------------------------------------

Write-Step 'Проверка инструментов'

$tools = @(
    @{ Name = 'python'; Cmd = { python --version } },
    @{ Name = 'node';   Cmd = { node --version } },
    @{ Name = 'npm';    Cmd = { npm --version } },
    @{ Name = 'docker'; Cmd = { docker --version } },
    @{ Name = 'git';    Cmd = { git --version } }
)

$missing = @()
foreach ($tool in $tools) {
    try {
        $version = (& $tool.Cmd 2>&1) -join ' '
        Write-Ok "$($tool.Name): $version"
    } catch {
        Write-Err "$($tool.Name) не найден в PATH"
        $missing += $tool.Name
    }
}

if ($missing -contains 'python' -or $missing -contains 'node') {
    throw "Не хватает обязательных инструментов: $($missing -join ', '). Установите их и повторите."
}

# --- 2. Бэкенд ----------------------------------------------------------------

Write-Step 'Бэкенд: виртуальное окружение'

$venvPath = Join-Path $root 'backend\.venv'
$pythonExe = Join-Path $venvPath 'Scripts\python.exe'

if (-not (Test-Path $pythonExe)) {
    Write-Host '  Создаю venv...'
    python -m venv $venvPath
    Write-Ok 'venv создан'
} else {
    Write-Ok 'venv уже есть'
}

if (-not $SkipInstall) {
    Write-Host '  Устанавливаю зависимости (это займёт пару минут)...'
    # --no-cache-dir и --progress-bar off: в ограниченных окружениях кеш в %TEMP%
    # недоступен и даёт PermissionError, а прогресс-бар бесконечно висит в логах.
    & $pythonExe -m pip install --no-cache-dir --progress-bar off `
        -r (Join-Path $root 'backend\requirements-dev.txt')
    if ($LASTEXITCODE -ne 0) { throw 'pip install завершился с ошибкой' }
    Write-Ok 'зависимости установлены'
}

# --- 3. Веб -------------------------------------------------------------------

Write-Step 'Веб: зависимости'

$webPath = Join-Path $root 'web'
if (-not $SkipInstall) {
    Push-Location $webPath
    try {
        if (Test-Path 'package-lock.json') {
            npm ci
        } else {
            npm install
        }
        if ($LASTEXITCODE -ne 0) { throw 'npm install завершился с ошибкой' }
        Write-Ok 'node_modules готовы'
    } finally {
        Pop-Location
    }
} else {
    Write-Ok 'пропущено (-SkipInstall)'
}

# --- 4. Инфраструктура --------------------------------------------------------

Write-Step 'Инфраструктура (Docker)'

try {
    docker info 2>&1 | Out-Null
} catch {
    throw 'Docker-демон не запущен. Откройте Docker Desktop и дождитесь статуса "running".'
}

$composeFile = Join-Path $root 'infra\docker-compose.yml'
$composeArgs = @('compose', '-f', $composeFile)
if ($WithSearch) { $composeArgs += @('--profile', 'search') }

& docker @composeArgs up -d
if ($LASTEXITCODE -ne 0) { throw 'docker compose up завершился с ошибкой' }

Write-Host '  Жду готовности PostgreSQL...'
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    $status = (& docker @composeArgs ps --format json 2>$null) -join ''
    if ($status -match '"Health":"healthy"') { $ready = $true; break }
    Start-Sleep -Seconds 2
}
if ($ready) { Write-Ok 'сервисы подняты' } else { Write-Warn 'не дождался healthy — проверьте: docker compose -f infra/docker-compose.yml ps' }

# --- 5. Миграции --------------------------------------------------------------

Write-Step 'Миграции Django'

Push-Location (Join-Path $root 'backend')
try {
    if (-not (Test-Path '.env')) {
        Copy-Item (Join-Path $root '.env.example') '.env'
        Write-Ok 'создан backend/.env из .env.example'
    }
    & $pythonExe manage.py migrate --noinput
    if ($LASTEXITCODE -ne 0) { throw 'migrate завершился с ошибкой' }
    Write-Ok 'миграции применены'
} finally {
    Pop-Location
}

# --- 6. Health-check ----------------------------------------------------------

Write-Step 'Проверка'

Push-Location (Join-Path $root 'backend')
try {
    & $pythonExe -c @'
import json, urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=3) as r:
        print(json.dumps(json.load(r), ensure_ascii=False, indent=2))
except Exception as e:
    print("Сервер не запущен — это нормально, запустите его отдельно:")
    print("  cd backend; .venv\\Scripts\\python.exe manage.py runserver")
'@
} finally {
    Pop-Location
}

Write-Host "`nГотово. Дальше:" -ForegroundColor Cyan
Write-Host '  Терминал 1:  cd backend; .venv\Scripts\Activate.ps1; python manage.py runserver'
Write-Host '  Терминал 2:  cd web;     npm run dev'
Write-Host '  Браузер:     http://localhost:5173'
