$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$Python = Join-Path $RootDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
  throw "Missing .venv\Scripts\python.exe. Create virtualenv first."
}

& $Python (Join-Path $RootDir "scripts\export_sustainability_snapshot.py") $args
