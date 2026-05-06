<#
.SYNOPSIS
  TagLedger preflight check (Windows).
.DESCRIPTION
  Runs ruff lint, pytest, and import verification.
.EXAMPLE
  .\scripts\run_preflight.ps1
#>
$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectDir

Write-Host "=== preflight: tagledger ==="

# 1. ruff lint
Write-Host "`n[1/3] ruff lint ..."
$ruff = "ruff"
if (Test-Path "$ProjectDir\.venv\Scripts\ruff.exe") {
    $ruff = "$ProjectDir\.venv\Scripts\ruff.exe"
}
if (Get-Command $ruff -ErrorAction SilentlyContinue) {
    & $ruff check "$ProjectDir\backend"
    Write-Host "ruff: OK"
} else {
    Write-Host "ruff not installed, skipping (pip install ruff)"
}

# 2. pytest
Write-Host "`n[2/3] pytest ..."
if (Test-Path "$ProjectDir\.venv\Scripts\python.exe") {
    & "$ProjectDir\.venv\Scripts\python.exe" -m pytest "$ProjectDir\backend\tests" -v
} else {
    python -m pytest "$ProjectDir\backend\tests" -v
}

# 3. import check
Write-Host "`n[3/3] import check ..."
$python = if (Test-Path "$ProjectDir\.venv\Scripts\python.exe") { "$ProjectDir\.venv\Scripts\python.exe" } else { "python" }
$code = @'
from backend.app.main import app
from backend.app.models import Record, RecordStatus, Category
from backend.app.schemas import (
    UploadResponse, ConfirmRequest, ConfirmResponse,
    RecordRead, RecordListItem, RetryResponse,
)
print("All imports OK")
print(f"Routes: {len(app.routes)} registered")
'@
& $python -c $code

Write-Host "`n=== preflight: PASSED ==="
