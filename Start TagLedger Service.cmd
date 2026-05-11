@echo off
setlocal
set "APP_DIR=C:\Users\vitec\tagledger"
if not exist "%APP_DIR%\scripts\remote_start_tagledger.ps1" (
  echo TagLedger startup script not found:
  echo %APP_DIR%\scripts\remote_start_tagledger.ps1
  pause
  exit /b 1
)
cd /d "%APP_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%\scripts\remote_start_tagledger.ps1"
echo.
echo TagLedger service started. Press any key to close this window.
pause >nul
