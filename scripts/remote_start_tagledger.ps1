$ErrorActionPreference = 'Stop'

Set-Location 'C:\Users\vitec\tagledger'

$OutLog = 'C:\Users\vitec\tagledger\uvicorn.out.log'
$ErrLog = 'C:\Users\vitec\tagledger\uvicorn.err.log'

if (Test-Path $OutLog) { Remove-Item $OutLog -Force }
if (Test-Path $ErrLog) { Remove-Item $ErrLog -Force }

$Py = 'C:\Users\vitec\tagledger\.venv\Scripts\python.exe'
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
    -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '0.0.0.0', '--port', '8000') `
    -WorkingDirectory 'C:\Users\vitec\tagledger' `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

Start-Sleep -Seconds 3

Write-Output "PID=$($Proc.Id)"
if (Test-Path $OutLog) { Write-Output 'OUT_LOG_READY' }
if (Test-Path $ErrLog) { Write-Output 'ERR_LOG_READY' }
