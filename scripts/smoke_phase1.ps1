$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    py -3.12 -m venv .venv
    $Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
}

& $Python -m pip install -e ".[dev]"
& $Python --version

$Tesseract = Get-Command tesseract -ErrorAction SilentlyContinue
if ($null -eq $Tesseract) {
    Write-Host 'Tesseract not found on PATH.'
    Write-Host 'Install Tesseract for Windows: https://github.com/UB-Mannheim/tesseract/wiki'
    Write-Host 'Then add the install directory, for example C:\Program Files\Tesseract-OCR, to PATH.'
}
else {
    Write-Host "Tesseract found: $($Tesseract.Source)"
}

& $Python -c "import pyzbar" | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host 'pyzbar import passed.'
}
else {
    Write-Host 'pyzbar import failed.'
    Write-Host 'Install barcode extras with: .\.venv\Scripts\python.exe -m pip install -e ".[barcode]"'
    Write-Host 'On Windows, the pyzbar wheel usually includes the required zbar DLL.'
}

& $Python -m pytest
Write-Host 'Phase 1 smoke passed. Start with: .\scripts\run_dev.ps1'
