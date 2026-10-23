#Requires -Version 5.1
<#
.SYNOPSIS
    Проверка окружения без установки чего-либо.

.DESCRIPTION
    Ничего не меняет: только читает версии и состояние сервисов.
    Нужен, чтобы понять, на каком шаге настройка застряла.

.EXAMPLE
    .\scripts\doctor.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot

function Write-Section($text) { Write-Host "`n--- $text ---" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  [ok]   $text" -ForegroundColor Green }
function Write-Bad($text)  { Write-Host "  [fail] $text" -ForegroundColor Red }
function Write-Warn($text) { Write-Host "  [warn] $text" -ForegroundColor Yellow }

Write-Host 'Диагностика окружения. Ничего не устанавливает и не меняет.' -ForegroundColor Gray

# --- Инструменты --------------------------------------------------------------

Write-Section 'Инструменты'

$checks = @(
    @{ Name = 'python'; Cmd = 'python --version' },
    @{ Name = 'node';   Cmd = 'node --version' },
    @{ Name = 'npm';    Cmd = 'npm --version' },
    @{ Name = 'docker'; Cmd = 'docker --version' },
    @{ Name = 'git';    Cmd = 'git --version' }
)

foreach ($c in $checks) {
    try {
        $out = Invoke-Expression $c.Cmd 2>&1
        if ($LASTEXITCODE -eq 0) { Write-Ok "$($c.Name): $out" } else { Write-Bad "$($c.Name): $out" }
    } catch {
        Write-Bad "$($c.Name) не найден"
    }
}

# --- Docker демон --------------------------------------------------------------

Write-Section 'Docker демон'

try {
    $info = docker info --format '{{.ServerVersion}}' 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "демон работает, версия $info"
    } else {
        Write-Bad "демон не запущен: $info"
        Write-Warn 'Откройте Docker Desktop и дождитесь статуса running'
    }
} catch {
    Write-Bad 'docker не отвечает'
}

# --- venv ----------------------------------------------------------------------

Write-Section 'Виртуальное окружение'

$pythonExe = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (Test-Path $pythonExe) {
    Write-Ok "venv существует: $pythonExe"
    # `pip list` в этом окружении может висеть минутами, поэтому спрашиваем
    # метаданные напрямую через importlib — это мгновенно и без сети.
    $probe = @'
import importlib.metadata as m
import sys
for name in ("Django", "djangorestframework", "psycopg", "celery", "pytest", "ruff"):
    try:
        print(f"{name}=={m.version(name)}")
    except m.PackageNotFoundError:
        print(f"{name}==MISSING")
'@
    $probeFile = Join-Path $env:TEMP 'dsh-doctor-probe.py'
    Set-Content -Path $probeFile -Value $probe -Encoding UTF8
    $pkgs = & $pythonExe $probeFile 2>$null
    Remove-Item $probeFile -ErrorAction SilentlyContinue

    $missing = $pkgs | Where-Object { $_ -match '==MISSING$' }
    if ($missing) {
        Write-Bad "не установлено: $(($missing -replace '==MISSING$', '') -join ', ')"
        Write-Warn 'Нужен pip install -r requirements-dev.txt'
    } else {
        $django = $pkgs | Where-Object { $_ -match '^Django==' }
        Write-Ok "зависимости на месте, $django"
    }
} else {
    Write-Bad 'venv отсутствует — нужен python -m venv backend\.venv'
}

# --- node_modules --------------------------------------------------------------

Write-Section 'Веб-зависимости'

$nodeModules = Join-Path $root 'web\node_modules'
if (Test-Path $nodeModules) {
    Write-Ok 'node_modules существует'
} else {
    Write-Bad 'node_modules отсутствует — нужен npm install'
}

# --- Сервисы -------------------------------------------------------------------

Write-Section 'Сервисы'

$ports = @(
    @{ Port = 5433; Name = 'PostgreSQL (Docker)' },
    @{ Port = 6379; Name = 'Redis' },
    @{ Port = 8001; Name = 'Centrifugo' },
    @{ Port = 9200; Name = 'Elasticsearch (опционально)' },
    @{ Port = 8000; Name = 'Django' },
    @{ Port = 5173; Name = 'Vite' }
)

foreach ($p in $ports) {
    # Test-NetConnection на каждый порт тратит по несколько секунд (он ещё и
    # резолвит имя), поэтому используем TCP-клиент с таймаутом в миллисекундах.
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync('127.0.0.1', $p.Port)
        $open = $task.Wait(700) -and $client.Connected
    } catch {
        $open = $false
    } finally {
        $client.Dispose()
    }
    if ($open) { Write-Ok "$($p.Name) слушает порт $($p.Port)" } else { Write-Warn "$($p.Name) не слушает порт $($p.Port)" }
}

# Нативный PostgreSQL на 5432 — частая причина «миграции ушли не в ту базу».
$native = Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue
if ($native) {
    Write-Warn "Найдена нативная служба $($native.Name -join ', ') — она может занимать 5432."
    Write-Warn 'Наш контейнер слушает 5433, поэтому конфликта быть не должно. Останавливать службу не нужно.'
}

# --- TLS до PyPI ---------------------------------------------------------------

Write-Section 'HTTPS до PyPI (причина зависания pip)'

try {
    $r = Invoke-WebRequest -Uri 'https://pypi.org/simple/django/' -UseBasicParsing -TimeoutSec 10
    Write-Ok "TLS работает, HTTP $($r.StatusCode)"
} catch {
    Write-Bad "TLS не работает: $($_.Exception.Message)"
    Write-Warn 'См. docs/troubleshooting.md, раздел про SEC_E_NO_CREDENTIALS'
}

Write-Host "`nГотово." -ForegroundColor Cyan
