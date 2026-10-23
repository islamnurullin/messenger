@echo off
REM Диагностика окружения в обход политики выполнения PowerShell.

setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0doctor.ps1" %*
pause
exit /b %ERRORLEVEL%
