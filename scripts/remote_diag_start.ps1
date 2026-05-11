param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
$AppDir = Split-Path -Parent $PSScriptRoot
Set-Location $AppDir

$Py = Resolve-Path '.\.venv\Scripts\python.exe' -ErrorAction Stop
Write-Host 'PWD:' (Get-Location).Path
Write-Host 'PY:' $Py.Path
Write-Host 'PORT:' $Port

& $Py.Path -m uvicorn backend.app.main:app --host 127.0.0.1 --port $Port --log-level debug
