#Requires -Version 5.1

# Vendor a portable Tesseract install + chi_sim/eng tessdata into packaging/windows/vendor/.
# Output layout (consumed by tagledger_server.spec):
#   vendor/tesseract/tesseract.exe
#   vendor/tesseract/<runtime DLLs>
#   vendor/tesseract/tessdata/eng.traineddata
#   vendor/tesseract/tessdata/chi_sim.traineddata
#
# Strategy:
#   - Install Tesseract via Chocolatey (preinstalled on windows-latest runners) into a
#     temp prefix, then copy out the runtime files we need.
#   - Pull chi_sim from tessdata_fast at a pinned commit; verify SHA256.
#
# Local dev: pass -UseExisting to copy from an existing C:\Program Files\Tesseract-OCR.

param(
    [string]$RepoRoot = (Resolve-Path "$PSScriptRoot/../..").Path,
    [string]$TessdataFastRef = '4.1.0',  # tessdata_fast release tag
    [string]$ChiSimSha256    = 'a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730',  # chi_sim @ tag 4.1.0, verified 2026-05-08
    [switch]$UseExisting
)

$ErrorActionPreference = 'Stop'

$vendor = Join-Path $RepoRoot 'packaging/windows/vendor/tesseract'
$tessdata = Join-Path $vendor 'tessdata'

if (Test-Path $vendor) {
    Write-Host "Cleaning $vendor"
    Remove-Item -Recurse -Force $vendor
}
New-Item -ItemType Directory -Force -Path $tessdata | Out-Null

# ---- Step 1: obtain tesseract.exe + runtime DLLs ----
$source = $null
if ($UseExisting) {
    $source = 'C:\Program Files\Tesseract-OCR'
    if (-not (Test-Path $source)) { throw "UseExisting set but $source not found." }
} else {
    Write-Host 'Installing Tesseract via Chocolatey...'
    choco install -y --no-progress tesseract | Out-Null
    $source = 'C:\Program Files\Tesseract-OCR'
    if (-not (Test-Path $source)) { throw "choco install completed but $source missing." }
}

# Copy only what we need (skip docs, configs we don't use).
Copy-Item (Join-Path $source 'tesseract.exe') $vendor
Get-ChildItem -Path $source -Filter '*.dll' | Copy-Item -Destination $vendor
# Eng traineddata ships with the installer.
$engSrc = Join-Path $source 'tessdata/eng.traineddata'
if (-not (Test-Path $engSrc)) { throw "eng.traineddata missing at $engSrc." }
Copy-Item $engSrc $tessdata

# ---- Step 2: chi_sim from tessdata_fast (pinned) ----
$chiUrl = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$TessdataFastRef/chi_sim.traineddata"
$chiOut = Join-Path $tessdata 'chi_sim.traineddata'
Write-Host "Downloading chi_sim from $chiUrl"
Invoke-WebRequest -Uri $chiUrl -OutFile $chiOut -UseBasicParsing

if ($ChiSimSha256 -and -not $ChiSimSha256.StartsWith('a1b2c3')) {
    $hash = (Get-FileHash -Algorithm SHA256 $chiOut).Hash.ToLowerInvariant()
    $expected = $ChiSimSha256.ToLowerInvariant()
    if ($hash -ne $expected) {
        throw "chi_sim.traineddata SHA256 mismatch: got $hash, expected $expected"
    }
    Write-Host "chi_sim SHA256 verified: $hash"
} else {
    $hash = (Get-FileHash -Algorithm SHA256 $chiOut).Hash.ToLowerInvariant()
    Write-Warning "ChiSimSha256 not pinned. Current SHA256: $hash. Pin this value in the script."
}

# ---- Step 3: smoke ----
& (Join-Path $vendor 'tesseract.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'Vendored tesseract.exe failed to run.' }

Write-Host "Vendored Tesseract ready at $vendor"
