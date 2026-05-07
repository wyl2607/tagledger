@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_lan.ps1" %*
echo.
echo TagLedger stopped. Press any key to close this window.
pause >nul
