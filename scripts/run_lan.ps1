<#
.SYNOPSIS
  Start TagLedger for LAN/mobile use on Windows.
.DESCRIPTION
  Creates/uses .venv, installs the app when needed, finds a LAN IPv4 address,
  prints a phone QR code for /mobile, and starts uvicorn on 0.0.0.0.
.EXAMPLE
  .\scripts\run_lan.ps1
.EXAMPLE
  .\scripts\run_lan.ps1 -Port 8010 -OpenBrowser
#>
param(
    [switch]$Help,
    [int]$Port = 8000,
    [string]$Page = 'mobile',
    [switch]$Reload,
    [switch]$OpenBrowser,
    [switch]$AddFirewallRule,
    [switch]$SkipInstall,
    [int]$MaxPortSearch = 20
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

function Show-HelpText {
    Write-Host 'TagLedger LAN startup'
    Write-Host ''
    Write-Host 'Usage:'
    Write-Host '  .\scripts\run_lan.ps1 [-Port 8000] [-Page mobile] [-Reload] [-OpenBrowser] [-AddFirewallRule] [-SkipInstall]'
    Write-Host ''
    Write-Host 'Examples:'
    Write-Host '  .\scripts\run_lan.ps1'
    Write-Host '  .\scripts\run_lan.ps1 -Port 8010 -OpenBrowser'
    Write-Host '  .\scripts\run_lan.ps1 -AddFirewallRule'
    Write-Host ''
    Write-Host 'Starts uvicorn on 0.0.0.0 and prints a LAN /mobile QR code for phones on the same Wi-Fi.'
}

if ($Help) {
    Show-HelpText
    exit 0
}

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Resolve-PythonLauncher {
    if (Test-Path (Join-Path $ProjectRoot '.venv\Scripts\python.exe')) {
        return @{ Exe = (Join-Path $ProjectRoot '.venv\Scripts\python.exe'); Args = @() }
    }
    if (Test-Command 'py') {
        return @{ Exe = 'py'; Args = @('-3.12') }
    }
    if (Test-Command 'python') {
        return @{ Exe = 'python'; Args = @() }
    }
    throw 'Python 3.12+ was not found. Install Python 3.12+ first.'
}

function Get-LanIPv4 {
    try {
        $Address = Get-NetIPAddress -AddressFamily IPv4 |
            Where-Object {
                $_.IPAddress -notlike '127.*' -and
                $_.IPAddress -notlike '169.254.*' -and
                $_.IPAddress -notlike '100.*' -and
                $_.AddressState -eq 'Preferred'
            } |
            Sort-Object InterfaceMetric |
            Select-Object -First 1 -ExpandProperty IPAddress
        if ($Address) { return $Address }
    }
    catch {
    }
    return '127.0.0.1'
}

function Test-PortBusy {
    param([int]$CandidatePort)
    $Client = New-Object System.Net.Sockets.TcpClient
    try {
        $Async = $Client.BeginConnect('127.0.0.1', $CandidatePort, $null, $null)
        $Connected = $Async.AsyncWaitHandle.WaitOne(200, $false)
        if ($Connected -and $Client.Connected) { return $true }
        return $false
    }
    finally {
        $Client.Close()
    }
}

function Get-HttpStatus {
    param([string]$Url)
    try {
        return [int](Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2).StatusCode
    }
    catch {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode.value__
        }
        return 0
    }
}

function Test-CurrentTagLedger {
    param([int]$CandidatePort)
    $HealthCode = Get-HttpStatus "http://127.0.0.1:$CandidatePort/health"
    $OutboundCode = Get-HttpStatus "http://127.0.0.1:$CandidatePort/api/outbound/summary"
    return ($HealthCode -eq 200 -and $OutboundCode -ne 404 -and $OutboundCode -ne 0)
}

function Select-LaunchPort {
    param([int]$PreferredPort)
    for ($Offset = 0; $Offset -le $MaxPortSearch; $Offset++) {
        $Candidate = $PreferredPort + $Offset
        if (-not (Test-PortBusy $Candidate)) { return @{ Port = $Candidate; AlreadyRunning = $false } }
        if (Test-CurrentTagLedger $Candidate) { return @{ Port = $Candidate; AlreadyRunning = $true } }
    }
    throw "No available port found from $PreferredPort to $($PreferredPort + $MaxPortSearch)."
}

function Show-LaunchInfo {
    param([string]$LanIP, [int]$SelectedPort)
    $MobileUrl = "http://${LanIP}:$SelectedPort/$Page"
    $LocalUrl = "http://127.0.0.1:$SelectedPort/$Page"
    $DocsUrl = "http://${LanIP}:$SelectedPort/docs"
    Write-Host ''
    Write-Host 'TagLedger LAN server'
    Write-Host "Phone / scanner: $MobileUrl"
    Write-Host "Local fallback:   $LocalUrl"
    Write-Host "API docs:         $DocsUrl"
    Write-Host ''
    & $Python (Join-Path $ProjectRoot 'scripts\print_lan_qr.py') $MobileUrl 'Scan with phone camera'
}

$Launcher = Resolve-PythonLauncher
if (-not (Test-Path (Join-Path $ProjectRoot '.venv\Scripts\python.exe'))) {
    & $Launcher.Exe @($Launcher.Args + @('-m', 'venv', '.venv'))
}

$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
if (-not $SkipInstall) {
    & $Python -c "import importlib.metadata as m; m.version('tagledger')" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing TagLedger package...'
        & $Python -m pip install -e ".[barcode,ocr]"
    }
    & $Python -c "import qrcode" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Installing QR helper...'
        & $Python -m pip install "qrcode[pil]>=8.0"
    }
}

$LanIP = Get-LanIPv4
$Launch = Select-LaunchPort -PreferredPort $Port
$Port = [int]$Launch.Port

if ($AddFirewallRule) {
    try {
        New-NetFirewallRule -DisplayName "TagLedger LAN $Port" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -ErrorAction Stop | Out-Null
        Write-Host "Windows Firewall rule added for TCP $Port."
    }
    catch {
        Write-Warning "Could not add firewall rule. Run PowerShell as Administrator or allow TCP $Port manually."
    }
}

Show-LaunchInfo -LanIP $LanIP -SelectedPort $Port

if ($Launch.AlreadyRunning) {
    Write-Host "Port $Port is already running the current TagLedger service."
    if ($OpenBrowser) { Start-Process "http://127.0.0.1:$Port/$Page" }
    exit 0
}

if ($OpenBrowser) {
    Start-Process "http://127.0.0.1:$Port/$Page"
}

Write-Host "Starting uvicorn on 0.0.0.0:$Port ..."
$UvicornArgs = @('-m', 'uvicorn', 'backend.app.main:app', '--host', '0.0.0.0', '--port', "$Port")
if ($Reload) { $UvicornArgs += '--reload' }
& $Python @UvicornArgs
