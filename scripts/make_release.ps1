$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

$AppName = 'machine-label-ocr'
$Version = if ($env:VERSION) { $env:VERSION } else { Get-Date -Format 'yyyyMMdd-HHmmss' }
$BuildDir = Join-Path $ProjectRoot 'dist\release'
$PackageDir = Join-Path $BuildDir "$AppName-$Version"
$ZipPath = Join-Path $BuildDir "$AppName-$Version.zip"

if (Test-Path $PackageDir) { Remove-Item -Recurse -Force $PackageDir }
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null

$ExcludeDirs = @(
    '.git', '.omx', '.pytest_cache', '.ruff_cache', '.venv',
    'build', 'dist', 'logs', 'machine_label_ocr.egg-info', '__pycache__'
)
$ExcludeFiles = @('.env', '.DS_Store')

Get-ChildItem -Force $ProjectRoot | ForEach-Object {
    if ($_.Name -like '.env.*') { return }
    if ($ExcludeDirs -contains $_.Name -or $ExcludeFiles -contains $_.Name) { return }
    Copy-Item -Recurse -Force $_.FullName (Join-Path $PackageDir $_.Name)
}

$SensitivePaths = @(
    'data\app.db',
    'data\storage_state.json',
    'data\outbound',
    'data\ocr-scratch'
)
foreach ($Path in $SensitivePaths) {
    $Target = Join-Path $PackageDir $Path
    if (Test-Path $Target) { Remove-Item -Recurse -Force $Target }
}

$DataDir = Join-Path $PackageDir 'data'
if (Test-Path $DataDir) {
    Get-ChildItem -Force $DataDir -Filter '*.xlsx' | Remove-Item -Force
    Get-ChildItem -Force $DataDir -Filter '~$*.xlsx' | Remove-Item -Force
}

Get-ChildItem -Force -Recurse $PackageDir -Filter '.env*' | Remove-Item -Force

foreach ($Dir in @('data\uploads', 'data\screenshots', 'logs')) {
    $TargetDir = Join-Path $PackageDir $Dir
    if (Test-Path $TargetDir) {
        Get-ChildItem -Force $TargetDir | Remove-Item -Recurse -Force
    }
    else {
        New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
    }
    New-Item -ItemType File -Force -Path (Join-Path $TargetDir '.gitkeep') | Out-Null
}

@'
# Machine Label OCR Release Package

This is a sanitized source release. It does not include local databases, uploaded photos, screenshots, logs, `.env` files, virtual environments, or git/OMX metadata.

## Windows Quick Start

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\install_windows.ps1
.\scripts\run_dev.ps1
```

Open:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/mobile
http://127.0.0.1:8000/history
http://127.0.0.1:8000/dashboard
```

## macOS Quick Start

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev,barcode,ocr]"
PORT=8001 ./scripts/run_mobile_test.sh
```

Install Tesseract separately:

- macOS: `brew install tesseract`
- Windows: https://github.com/UB-Mannheim/tesseract/wiki
'@ | Set-Content -Encoding UTF8 (Join-Path $PackageDir 'README_RELEASE.md')

Compress-Archive -Force -Path $PackageDir -DestinationPath $ZipPath

$ForbiddenEntries = @()
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    foreach ($Entry in $Archive.Entries) {
        $Name = $Entry.FullName -replace '\\', '/'
        $Lower = $Name.ToLowerInvariant()
        if (
            $Lower -match '(^|/)\.git/' -or
            $Lower -match '(^|/)\.omx/' -or
            $Lower -match '(^|/)data/app\.db$' -or
            $Lower -match '(^|/)data/storage_state\.json$' -or
            $Lower -match '(^|/)data/[^/]+\.xlsx$' -or
            $Lower -match '(^|/)data/outbound/' -or
            $Lower -match '(^|/)data/ocr-scratch/' -or
            $Lower -match '(^|/)data/uploads/.+\.(jpg|jpeg|png|webp)$' -or
            $Lower -match '(^|/)data/screenshots/.+\.(png|jpg|jpeg|txt)$' -or
            $Lower -match '(^|/)logs/.+\.log$' -or
            $Lower -match '(^|/)\.env($|\.)'
        ) {
            $ForbiddenEntries += $Name
        }
    }
}
finally {
    $Archive.Dispose()
}

if ($ForbiddenEntries.Count -gt 0) {
    Write-Error ("Release package contains forbidden entries:`n" + ($ForbiddenEntries -join "`n"))
}

Write-Host "Release package created:"
Write-Host $ZipPath
Write-Host ''
Write-Host 'Sanity check passed. Sanitized package excludes data\app.db, data\uploads, data\screenshots, logs, .env, .git and .omx.'
