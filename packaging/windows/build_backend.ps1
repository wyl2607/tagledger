#Requires -Version 5.1

# End-to-end M2 build: vendor Tesseract, install runtime deps, run PyInstaller, smoke test.
# Usage:
#   pwsh -File packaging/windows/build_backend.ps1
#   pwsh -File packaging/windows/build_backend.ps1 -SkipVendor   # reuse existing vendor/tesseract
#   pwsh -File packaging/windows/build_backend.ps1 -SkipSmoke

param(
    [switch]$SkipVendor,
    [switch]$SkipSmoke,
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path "$PSScriptRoot/../..").Path
Set-Location $RepoRoot
Write-Host "Repo: $RepoRoot"

# ---- Step 1: Tesseract vendor ----
if (-not $SkipVendor) {
    & "$PSScriptRoot/vendor_tesseract.ps1"
} else {
    if (-not (Test-Path "$RepoRoot/packaging/windows/vendor/tesseract/tesseract.exe")) {
        throw 'SkipVendor set but vendor/tesseract is missing. Run without -SkipVendor first.'
    }
}

# ---- Step 2: virtualenv + runtime deps ----
$venv = Join-Path $RepoRoot '.venv-build'
if (-not (Test-Path $venv)) {
    Write-Host 'Creating build venv...'
    & $Python -m venv $venv
}
$pip = Join-Path $venv 'Scripts/pip.exe'
$venvPython = Join-Path $venv 'Scripts/python.exe'
& $pip install --upgrade pip wheel | Out-Null
& $pip install -r (Join-Path $RepoRoot 'requirements-runtime.txt')
& $pip install 'pyinstaller>=6.10,<7'

# ---- Step 3: PyInstaller ----
Push-Location $RepoRoot
try {
    & $venvPython -m PyInstaller `
        packaging/windows/tagledger_server.spec `
        --noconfirm `
        --clean
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
} finally {
    Pop-Location
}

$dist = Join-Path $RepoRoot 'dist/tagledger-server'
if (-not (Test-Path "$dist/tagledger_server.exe")) {
    throw "Expected $dist/tagledger_server.exe missing after build."
}
Write-Host "Built: $dist/tagledger_server.exe"

# ---- Step 4: smoke ----
if ($SkipSmoke) { return }

$smokeData = Join-Path $env:TEMP "tagledger-smoke-$([Guid]::NewGuid().ToString('N'))"
$smokeLogs = Join-Path $smokeData 'logs'
New-Item -ItemType Directory -Force -Path $smokeLogs | Out-Null

Write-Host "Smoke run: data=$smokeData"
$proc = Start-Process -FilePath "$dist/tagledger_server.exe" `
    -ArgumentList @('--host','127.0.0.1','--port','0','--data-dir',$smokeData,'--log-dir',$smokeLogs) `
    -PassThru -WindowStyle Hidden

try {
    # Wait for runtime/port file (sidecar writes it after binding).
    $portFile = Join-Path $smokeData 'runtime/port'
    $deadline = (Get-Date).AddSeconds(20)
    while (-not (Test-Path $portFile) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 200 }
    if (-not (Test-Path $portFile)) { throw 'Sidecar did not write runtime/port within 20s.' }

    $port = (Get-Content $portFile -Raw).Trim()
    Write-Host "Sidecar will listen on 127.0.0.1:$port (waiting for uvicorn bind)"

    # The port file is written before uvicorn finishes binding, so poll /health
    # with backoff instead of single-shotting it.
    $healthOk = $false
    $deadline = (Get-Date).AddSeconds(20)
    while (-not $healthOk -and (Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$port/health" `
                -UseBasicParsing -TimeoutSec 3
            if ($resp.StatusCode -eq 200) { $healthOk = $true; break }
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $healthOk) { throw "Health check did not return 200 within 20s." }
    Write-Host '/health OK'

    # Host header attack should be 421. Use HttpWebRequest instead of
    # Invoke-WebRequest here because Windows PowerShell 5 and PowerShell 7 wrap
    # non-2xx responses differently.
    $badHostCode = $null
    $request = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$port/health")
    $request.Host = 'evil.com'
    $request.Timeout = 5000
    try {
        $badHostResponse = $request.GetResponse()
        $badHostCode = [int]$badHostResponse.StatusCode
        $badHostResponse.Close()
        throw 'Host-header attack was not rejected.'
    } catch [System.Net.WebException] {
        $resp = $_.Exception.Response
        if ($null -ne $resp) {
            $badHostCode = [int]$resp.StatusCode
            $resp.Close()
        }
    }
    if ($badHostCode -ne 421) { throw "Expected 421 for bad Host, got $badHostCode" }
    Write-Host 'Bad Host -> 421 OK'
} finally {
    if (-not $proc.HasExited) {
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -Recurse -Force $smokeData -ErrorAction SilentlyContinue
}

Write-Host 'M2 build + smoke complete.'
