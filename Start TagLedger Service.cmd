@echo off
setlocal

set "PORT=%TAGLEDGER_PORT%"
if "%PORT%"=="" set "PORT=8000"

set "APP_DIR=%~dp0"
for %%I in ("%APP_DIR%.") do set "APP_DIR=%%~fI"

if not exist "%APP_DIR%\scripts\remote_start_tagledger.ps1" (
  set "APP_DIR=%USERPROFILE%\tagledger"
)
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
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%\scripts\remote_start_tagledger.ps1" -Port %PORT%
if errorlevel 1 (
  echo.
  echo TagLedger service failed to start on port %PORT%.
  if exist "%APP_DIR%\uvicorn.err.log" (
    echo Last error log lines:
    powershell -NoProfile -Command "Get-Content -LiteralPath '%APP_DIR%\uvicorn.err.log' -Tail 20"
  )
  pause
  exit /b 1
)

echo.
echo TagLedger service started on port %PORT%.
echo Mobile URL: http://127.0.0.1:%PORT%/mobile
echo Press any key to close this window.
pause >nul
