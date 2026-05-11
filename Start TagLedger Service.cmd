@echo off
setlocal
set "APP_DIR=%~dp0"
for %%I in ("%APP_DIR%.") do set "APP_DIR=%%~fI"
if not exist "%APP_DIR%\scripts\remote_start_tagledger.ps1" (
  set "APP_DIR=%USERPROFILE%\tagledger-git"
)
if not exist "%APP_DIR%\scripts\remote_start_tagledger.ps1" (
  echo TagLedger startup script not found:
  echo %APP_DIR%\scripts\remote_start_tagledger.ps1
  pause
  exit /b 1
)
cd /d "%APP_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%\scripts\remote_start_tagledger.ps1"
if errorlevel 1 (
  echo.
  echo TagLedger service failed to start.
  pause
  exit /b 1
)
echo.
echo TagLedger service started. Press any key to close this window.
pause >nul
