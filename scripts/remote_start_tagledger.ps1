param(
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'

$AppDir = Split-Path -Parent $PSScriptRoot
Set-Location $AppDir

$OutLog = Join-Path $AppDir 'uvicorn.out.log'
$ErrLog = Join-Path $AppDir 'uvicorn.err.log'

if (Test-Path $OutLog) { Remove-Item $OutLog -Force }
if (Test-Path $ErrLog) { Remove-Item $ErrLog -Force }

$Py = Join-Path $AppDir '.venv\Scripts\python.exe'
if (-not (Test-Path $Py)) {
    throw "Python not found: $Py"
}

$Running = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -ieq 'python.exe' -and
    $_.CommandLine -like '*backend.app.main:app*'
}
foreach ($Proc in $Running) {
    try { Stop-Process -Id $Proc.ProcessId -Force -ErrorAction Stop } catch {}
}

$Proc = Start-Process -FilePath $Py `
    -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '0.0.0.0', '--port', "$Port") `
    -WorkingDirectory $AppDir `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Start-Sleep -Seconds 3

Write-Output "PID=$($Proc.Id)"
Write-Output "PORT=$Port"
if (Test-Path $OutLog) { Write-Output 'OUT_LOG_READY' }
if (Test-Path $ErrLog) { Write-Output 'ERR_LOG_READY' }
