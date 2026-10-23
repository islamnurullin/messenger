@echo off
REM Запуск настройки в обход политики выполнения PowerShell.
REM Нужен, потому что по умолчанию Windows запрещает запуск .ps1-файлов.
REM
REM Использование: двойной клик или из терминала
REM   setup.cmd
REM   setup.cmd -WithSearch

setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE% neq 0 (
    echo [!] Скрипт завершился с ошибкой. Код: %EXITCODE%
) else (
    echo [ok] Готово.
)
pause
exit /b %EXITCODE%
