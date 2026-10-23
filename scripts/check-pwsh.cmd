@echo off
REM Диагностика PowerShell: почему DSH не может запустить команду.
REM Двойной клик по этому файлу.

setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0check-pwsh.ps1"
echo.
pause
