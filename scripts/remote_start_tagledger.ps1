param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [ValidateRange(5, 120)]
    [int]$StartupTimeoutSec = 20,
    [switch]$DetachedTask,
    [string]$OpenPath = ''
)

$ErrorActionPreference = 'Stop'

$AppDir = Split-Path -Parent $PSScriptRoot
Set-Location $AppDir

$OutLog = Join-Path $AppDir 'uvicorn.out.log'
$ErrLog = Join-Path $AppDir 'uvicorn.err.log'
$Py = Join-Path $AppDir '.venv\Scripts\python.exe'

if (-not (Test-Path $Py)) {
    throw "Python not found: $Py"
}

$CommandToken = "backend.app.main:app"
$PortToken = "--port $Port"

$Running = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -ieq 'python.exe' -and
    $_.CommandLine -and
    $_.CommandLine -like "*$CommandToken*" -and
    $_.CommandLine -like "*$PortToken*"
}

foreach ($Proc in $Running) {
    try { Stop-Process -Id $Proc.ProcessId -Force -ErrorAction Stop } catch {}
}

Start-Sleep -Seconds 1

foreach ($Log in @($OutLog, $ErrLog)) {
    if (Test-Path $Log) {
        try { Remove-Item $Log -Force -ErrorAction Stop } catch {}
    }
}

if ($DetachedTask) {
    $TaskName = "TagLedgerService-$Port"
    $CmdPath = Join-Path $AppDir "run-tagledger-$Port.cmd"
    $Cmd = @"
@echo off
cd /d "$AppDir"
"$Py" -m uvicorn backend.app.main:app --host 0.0.0.0 --port $Port > "$OutLog" 2> "$ErrLog"
"@
    Set-Content -LiteralPath $CmdPath -Value $Cmd -Encoding ASCII

    & cmd.exe /c "schtasks /Delete /TN `"$TaskName`" /F >nul 2>nul" | Out-Null
    $StartTime = (Get-Date).AddMinutes(1).ToString('HH:mm')
    $CreateOutput = & schtasks.exe /Create /TN $TaskName /SC ONCE /ST $StartTime /TR "`"$CmdPath`"" /F 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create scheduled task $TaskName. Output:$([Environment]::NewLine)$($CreateOutput -join [Environment]::NewLine)"
    }
    $RunOutput = & schtasks.exe /Run /TN $TaskName 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to run scheduled task $TaskName. Output:$([Environment]::NewLine)$($RunOutput -join [Environment]::NewLine)"
    }
} else {
    $Proc = Start-Process -FilePath $Py `
        -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '0.0.0.0', '--port', "$Port") `
        -WorkingDirectory $AppDir `
        -RedirectStandardOutput $OutLog `
        -RedirectStandardError $ErrLog `
        -PassThru
}

$HealthUri = "http://127.0.0.1:$Port/health"
$Healthy = $false

for ($i = 0; $i -lt $StartupTimeoutSec; $i++) {
    Start-Sleep -Seconds 1

    if (-not $DetachedTask) {
        $Proc.Refresh()
        if ($Proc.HasExited) {
            $Tail = if (Test-Path $ErrLog) {
                (Get-Content $ErrLog -Tail 40 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
            } else {
                ''
            }
            throw "TagLedger exited during startup on port $Port. ExitCode=$($Proc.ExitCode). ErrorLog:$([Environment]::NewLine)$Tail"
        }
    }

    try {
        $StatusCode = (Invoke-WebRequest -UseBasicParsing -Uri $HealthUri -TimeoutSec 2).StatusCode
        if ($StatusCode -eq 200) {
            $Healthy = $true
            break
        }
    } catch {
        # keep waiting until timeout
    }
}

if (-not $Healthy) {
    if (-not $DetachedTask) {
        try { Stop-Process -Id $Proc.Id -Force -ErrorAction Stop } catch {}
    }
    $Tail = if (Test-Path $ErrLog) {
        (Get-Content $ErrLog -Tail 40 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
    } else {
        ''
    }
    throw "TagLedger health check timeout on port $Port after $StartupTimeoutSec seconds. ErrorLog:$([Environment]::NewLine)$Tail"
}

$Started = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -ieq 'python.exe' -and
    $_.CommandLine -and
    $_.CommandLine -like "*$CommandToken*" -and
    $_.CommandLine -like "*$PortToken*"
} | Select-Object -First 1

if ($Started) {
    Write-Output "PID=$($Started.ProcessId)"
} elseif (-not $DetachedTask) {
    Write-Output "PID=$($Proc.Id)"
} else {
    Write-Output 'PID=unknown'
}
Write-Output "PORT=$Port"
Write-Output "HEALTH=$HealthUri"
if ($DetachedTask) { Write-Output "TASK=$TaskName" }
if (Test-Path $OutLog) { Write-Output 'OUT_LOG_READY' }
if (Test-Path $ErrLog) { Write-Output 'ERR_LOG_READY' }

if ($OpenPath) {
    if (-not $OpenPath.StartsWith('/')) {
        $OpenPath = "/$OpenPath"
    }
    $OpenUri = "http://127.0.0.1:$Port$OpenPath"
    Start-Process $OpenUri
    Write-Output "OPENED=$OpenUri"
}
