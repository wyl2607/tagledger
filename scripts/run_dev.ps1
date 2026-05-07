$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

$ActivateScript = Join-Path $ProjectRoot '.venv\Scripts\Activate.ps1'
if (-not (Test-Path $ActivateScript)) {
    Write-Host 'Missing .venv. Create it with: .\scripts\install_windows.ps1'
    exit 1
}

. $ActivateScript

$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
& $Python -c "import importlib.metadata as m; m.version('tagledger')" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing local package: pip install -e .'
    & $Python -m pip install -e .
}

function Get-LanIPv4 {
    try {
        $Address = Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object {
                $_.IPAddress -notlike '127.*' -and
                $_.IPAddress -notlike '169.254.*' -and
                $_.AddressState -eq 'Preferred'
            } |
            Sort-Object InterfaceMetric |
            Select-Object -First 1 -ExpandProperty IPAddress
        if ($Address) {
            return $Address
        }
    }
    catch {
    }
    return '127.0.0.1'
}

$LanIP = Get-LanIPv4

Write-Host 'Starting TagLedger API'
Write-Host 'Local docs: http://127.0.0.1:8000/docs'
Write-Host "LAN docs:   http://${LanIP}:8000/docs"
Write-Host "LAN app:    http://${LanIP}:8000"
Write-Host "Phone scan: http://${LanIP}:8000/mobile"
Write-Host 'For QR-code LAN startup, run: .\scripts\run_lan.ps1'
& $Python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
