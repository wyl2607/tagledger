$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

function Test-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command 'git')) {
    throw 'Git was not found. Install Git for Windows: https://git-scm.com/download/win'
}

function Get-PythonVersion {
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Args = @()
    )

    try {
        $Output = & $Exe @Args -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ($LASTEXITCODE -eq 0 -and $Output) {
            return [version]$Output
        }
    }
    catch {
    }
    return $null
}

$PythonExe = $null
$PythonArgs = @()
$Candidates = @()
if (Test-Command 'py') {
    $Candidates += ,@('py', '-3.12')
}
if (Test-Command 'python') {
    $Candidates += ,@('python')
}

foreach ($Candidate in $Candidates) {
    $CandidateExe = $Candidate[0]
    $CandidateArgs = @()
    if ($Candidate.Length -gt 1) {
        $CandidateArgs = $Candidate[1..($Candidate.Length - 1)]
    }
    $Version = Get-PythonVersion -Exe $CandidateExe -Args $CandidateArgs
    if ($null -ne $Version -and $Version -ge [version]'3.12') {
        $PythonExe = $CandidateExe
        $PythonArgs = $CandidateArgs
        break
    }
}

if ($null -eq $PythonExe) {
    throw 'Python 3.12+ was not found. Install Python 3.12+ from Microsoft Store or python.org.'
}

if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & $PythonExe @PythonArgs -m venv .venv
}

$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
& $Python -m pip install --upgrade pip
& $Python -m pip install -e ".[barcode,ocr]"

Write-Host ''
Write-Host 'Windows install completed.'
Write-Host 'Next: install Tesseract for Windows from: https://github.com/UB-Mannheim/tesseract/wiki'
Write-Host 'Add the Tesseract install directory to PATH, usually: C:\Program Files\Tesseract-OCR'
Write-Host 'Verify it in a new PowerShell window with: tesseract --version'
Write-Host ''
Write-Host 'Barcode note: pyzbar on Windows usually includes the zbar DLL, so no separate zbar install is normally needed.'
Write-Host 'Start the API with: .\scripts\run_dev.ps1'
