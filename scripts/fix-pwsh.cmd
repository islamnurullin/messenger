@echo off
REM Устанавливает PowerShell 7 — без него DeepSeek Harness не может запускать команды.
REM Двойной клик. UAC спросит подтверждение — это нормально.

setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix-pwsh.ps1" %*
echo.
pause
exit /b %ERRORLEVEL%
