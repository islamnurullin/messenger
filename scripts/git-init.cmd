@echo off
REM Инициализация git в обход политики выполнения PowerShell.

setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0git-init.ps1" %*
set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE% neq 0 (
    echo [!] Скрипт завершился с ошибкой. Код: %EXITCODE%
) else (
    echo [ok] Готово.
)
pause
exit /b %EXITCODE%
