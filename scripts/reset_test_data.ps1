$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ProjectRoot

if ($args.Count -eq 0 -or $args[0] -ne '--yes') {
    Write-Host 'Dry run only.'
    Write-Host ''
    Write-Host 'This removes local test data:'
    Write-Host '- data\app.db'
    Write-Host '- data\uploads\* except .gitkeep'
    Write-Host '- data\screenshots\* except .gitkeep'
    Write-Host '- logs\playwright.log'
    Write-Host ''
    Write-Host 'Run:'
    Write-Host '  .\scripts\reset_test_data.ps1 --yes'
    exit 0
}

Remove-Item -Force -ErrorAction SilentlyContinue data\app.db, data\app.db-shm, data\app.db-wal, logs\playwright.log
Get-ChildItem data\uploads -Force | Where-Object { $_.Name -ne '.gitkeep' } | Remove-Item -Force -Recurse
Get-ChildItem data\screenshots -Force | Where-Object { $_.Name -ne '.gitkeep' } | Remove-Item -Force -Recurse

Write-Host 'Local test data reset.'
