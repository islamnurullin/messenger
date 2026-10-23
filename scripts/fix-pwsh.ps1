#Requires -Version 5.1
<#
.SYNOPSIS
    Устанавливает PowerShell 7 и проверяет, что DSH теперь сможет запускать команды.

.DESCRIPTION
    Причина сбоя "spawn EPERM": DSH ищет pwsh в порядке
      1) C:\Program Files\PowerShell\7\pwsh.exe
      2) PATH (там оказывается заглушка Microsoft Store размером 0 байт)
      3) Windows PowerShell 5.1
    PowerShell 7 не установлен, поэтому срабатывает пункт 2, а заглушку
    запустить нельзя. Скрипт ставит PowerShell 7 в стандартное место —
    пункт 1 начинает срабатывать, и заглушка больше не используется.

    Требуются права администратора (UAC спросит подтверждение).

.EXAMPLE
    .\scripts\fix-pwsh.ps1
#>
[CmdletBinding()]
param(
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'

function Write-Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  [ok] $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  [!]  $text" -ForegroundColor Yellow }
function Write-Err($text)  { Write-Host "  [x]  $text" -ForegroundColor Red }

$ps7 = 'C:\Program Files\PowerShell\7\pwsh.exe'

Write-Host 'Проверка PowerShell для DeepSeek Harness' -ForegroundColor Gray

# --- 1. Текущее состояние -----------------------------------------------------

Write-Step '1. Что сейчас есть'

if (Test-Path $ps7) {
    Write-Ok "PowerShell 7 уже установлен: $ps7"
    & $ps7 -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString()' |
        ForEach-Object { Write-Ok "версия: $_" }
    $alreadyInstalled = $true
} else {
    Write-Err "PowerShell 7 НЕ установлен ($ps7 отсутствует)"
    $alreadyInstalled = $false
}

$stub = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\pwsh.exe'
if (Test-Path $stub) {
    Write-Warn "в WindowsApps лежит заглушка: $stub"
}

if ($CheckOnly) {
    Write-Host "`nРежим -CheckOnly: ничего не меняю." -ForegroundColor Cyan
    exit 0
}

if ($alreadyInstalled) {
    Write-Host "`nУстановка не нужна. Перезапустите DSH полностью." -ForegroundColor Cyan
    exit 0
}

# --- 2. winget -----------------------------------------------------------------

Write-Step '2. Установка через winget'

$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) {
    Write-Err 'winget не найден'
    Write-Host "`nУстановите PowerShell 7 вручную:" -ForegroundColor Yellow
    Write-Host '  https://aka.ms/powershell-release?tag=stable'
    Write-Host 'Скачайте MSI для Windows x64 и запустите.'
    exit 1
}

Write-Ok "winget: $($winget.Source)"
Write-Host '  Запускаю установку (может занять пару минут)...'

& winget install --id Microsoft.PowerShell --source winget `
    --accept-source-agreements --accept-package-agreements `
    --silent

$exitCode = $LASTEXITCODE

# winget возвращает 0x8A150061 (-1978335135), если пакет уже установлен
if ($exitCode -eq 0 -or $exitCode -eq -1978335135) {
    Write-Ok 'winget завершился успешно'
} else {
    Write-Warn "winget вернул код $exitCode — проверю результат по файлу"
}

# --- 3. Проверка результата ---------------------------------------------------

Write-Step '3. Проверка'

if (Test-Path $ps7) {
    Write-Ok "PowerShell 7 установлен: $ps7"
    & $ps7 -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString()' |
        ForEach-Object { Write-Ok "версия: $_" }

    Write-Host ''
    try {
        $out = & $ps7 -NoLogo -NoProfile -NonInteractive -Command 'Write-Output probe-ok' 2>&1
        if ($out -match 'probe-ok') {
            Write-Ok 'пробный запуск неинтерактивной команды прошёл'
        } else {
            Write-Warn "пробный запуск вернул: $out"
        }
    } catch {
        Write-Err "пробный запуск упал: $($_.Exception.Message)"
    }

    Write-Host "`nГотово. Теперь:" -ForegroundColor Cyan
    Write-Host '  1. Полностью закройте DeepSeek Harness (не просто окно — завершите процесс).'
    Write-Host '  2. Откройте DSH снова и продолжите сессию.'
    Write-Host '  3. Проверка: в чате попросите выполнить echo test'
} else {
    Write-Err "PowerShell 7 всё ещё не установлен: $ps7"
    Write-Host "`nПопробуйте вручную:" -ForegroundColor Yellow
    Write-Host '  winget install --id Microsoft.PowerShell --source winget'
    Write-Host 'или скачайте MSI: https://aka.ms/powershell-release?tag=stable'
    exit 1
}
