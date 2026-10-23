#Requires -Version 5.1
<#
.SYNOPSIS
    Инициализация git-репозитория: main, develop, первый коммит.

.DESCRIPTION
    Идемпотентен: если репозиторий уже есть, ничего не пересоздаёт — только
    сообщает текущее состояние.

.EXAMPLE
    .\scripts\git-init.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

function Write-Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  [ok] $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  [!]  $text" -ForegroundColor Yellow }

try {
    Write-Step 'Проверка репозитория'

    if (Test-Path (Join-Path $root '.git')) {
        Write-Warn 'репозиторий уже инициализирован — пропускаю'
        git status --short --branch
        return
    }

    # user.name / user.email должны быть настроены глобально, иначе коммит упадёт.
    $name = git config --global user.name
    $email = git config --global user.email
    if (-not $name -or -not $email) {
        throw 'Настройте git: git config --global user.name "Имя"; git config --global user.email "you@example.com"'
    }
    Write-Ok "автор коммитов: $name <$email>"

    Write-Step 'Создание репозитория'

    git init --initial-branch=main
    if ($LASTEXITCODE -ne 0) { throw 'git init завершился с ошибкой' }
    Write-Ok 'репозиторий создан, ветка main'

    git add -A
    if ($LASTEXITCODE -ne 0) { throw 'git add завершился с ошибкой' }

    # Не коммитим секреты и локальные данные, даже если .gitignore их пропустил.
    $suspicious = git diff --cached --name-only | Where-Object {
        $_ -match '(^|/)(\.env$|\.env\.(?!example)|.*\.pem$|.*\.key$|id_rsa)'
    }
    if ($suspicious) {
        throw "В индексе оказались секреты: $($suspicious -join ', '). Проверьте .gitignore."
    }

    $staged = (git diff --cached --name-only | Measure-Object).Count
    if ($staged -eq 0) { Write-Warn 'нечего коммитить' ; return }

    git commit -m @'
chore: каркас монорепо и health-check

Этап 1: инфраструктура, скелет Django, SvelteKit, документация.

- Django 5.1 + DRF, кастомная модель User с входом по логину
- PostgreSQL, Redis, Centrifugo в docker compose
- GET /api/health с раздельной проверкой зависимостей
- SvelteKit: страница обзора и страница состояния
- ADR по ключевым решениям, CI, PR-шаблон
'@
    if ($LASTEXITCODE -ne 0) { throw 'git commit завершился с ошибкой' }
    Write-Ok "первый коммит создан ($staged файлов)"

    Write-Step 'Ветка develop'

    git branch develop
    git checkout develop
    Write-Ok 'переключился на develop — дальше работа идёт здесь'

    Write-Host "`nГотово. Текущая ветка:" -ForegroundColor Cyan
    git branch --show-current
    Write-Host '`nЧтобы запушить:' -ForegroundColor Cyan
    Write-Host '  git remote add origin <url-вашего-репозитория>'
    Write-Host '  git push -u origin main'
    Write-Host '  git push -u origin develop'
} finally {
    Pop-Location
}
