# Диагностика запуска PowerShell для DSH.
#
# Зачем: DeepSeek Harness падает с ошибкой "spawn EPERM" при попытке запустить
# команду. Похоже, он находит в PATH заглушку-алиас
#   C:\Users\<вы>\AppData\Local\Microsoft\WindowsApps\pwsh.exe
# вместо настоящего PowerShell.
#
# Запустите двойным кликом по check-pwsh.cmd и пришлите весь вывод.

Write-Host '=== 1. Что находится по имени pwsh ===' -ForegroundColor Cyan
Get-Command pwsh -All -ErrorAction SilentlyContinue |
    Format-List Name, CommandType, Source, Version
if (-not (Get-Command pwsh -All -ErrorAction SilentlyContinue)) {
    Write-Host '  ничего не найдено' -ForegroundColor Yellow
}

Write-Host "`n=== 2. PowerShell 7 в стандартном месте ===" -ForegroundColor Cyan
$ps7 = 'C:\Program Files\PowerShell\7\pwsh.exe'
if (Test-Path $ps7) {
    Write-Host "  найден: $ps7" -ForegroundColor Green
    & $ps7 -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'
} else {
    Write-Host "  НЕ найден: $ps7" -ForegroundColor Red
}

Write-Host "`n=== 3. Папка C:\Program Files\PowerShell ===" -ForegroundColor Cyan
if (Test-Path 'C:\Program Files\PowerShell') {
    Get-ChildItem 'C:\Program Files\PowerShell' -Recurse -Filter pwsh.exe -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty FullName
} else {
    Write-Host '  папки нет — PowerShell 7 не установлен' -ForegroundColor Yellow
}

Write-Host "`n=== 4. Заглушка из Microsoft Store ===" -ForegroundColor Cyan
$stub = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\pwsh.exe'
if (Test-Path $stub) {
    $item = Get-Item $stub -Force -ErrorAction SilentlyContinue
    if ($item) {
        Write-Host "  путь:  $stub"
        Write-Host "  размер: $($item.Length) байт"
        Write-Host "  версия: $($item.VersionInfo.FileVersion)"
    } else {
        Write-Host '  путь есть, но прочитать не удалось (это и есть симптом)' -ForegroundColor Red
    }
} else {
    Write-Host '  заглушки нет'
}

Write-Host "`n=== 5. Системный Windows PowerShell 5.1 (запасной вариант) ===" -ForegroundColor Cyan
$ps51 = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
if (Test-Path $ps51) {
    Write-Host "  найден: $ps51" -ForegroundColor Green
    & $ps51 -NoLogo -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'
} else {
    Write-Host '  НЕ найден' -ForegroundColor Red
}

Write-Host "`n=== 6. Порядок поиска в PATH ===" -ForegroundColor Cyan
($env:PATH -split ';') | Where-Object { $_ -match 'WindowsApps|PowerShell' } |
    ForEach-Object { Write-Host "  $_" }

Write-Host "`n=== 7. Пробный запуск через заглушку ===" -ForegroundColor Cyan
try {
    $out = & pwsh -NoLogo -NoProfile -Command 'Write-Output probe-ok' 2>&1
    Write-Host "  результат: $out" -ForegroundColor Green
} catch {
    Write-Host "  ОШИБКА: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "`nГотово. Скопируйте весь вывод и пришлите в чат." -ForegroundColor Cyan
