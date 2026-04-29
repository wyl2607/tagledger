<#
.SYNOPSIS
  Clean up old uploaded images and screenshots.
.DESCRIPTION
  Removes uploaded images and screenshots older than N days.
  Safe to run while the service is running.
.PARAMETER Days
  Remove files older than this many days. Default 30.
.PARAMETER DryRun
  List files that would be deleted without actually deleting them.
#>
param(
    [int]$Days = 30,
    [switch]$DryRun
)

$ProjectDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ScreenshotDir = Join-Path $ProjectDir "data\screenshots"
$UploadDir = Join-Path $ProjectDir "data\uploads"
$Cutoff = (Get-Date).AddDays(-$Days)

Write-Host "Cleaning files older than $Days days (before $Cutoff)..."

foreach ($Dir in @($ScreenshotDir, $UploadDir)) {
    if (-not (Test-Path $Dir)) { continue }
    $Files = Get-ChildItem -Path $Dir -File -Recurse |
        Where-Object { $_.Name -ne ".gitkeep" -and $_.LastWriteTime -lt $Cutoff }
    foreach ($File in $Files) {
        if ($DryRun) {
            Write-Host "  [DRY RUN] Would remove: $($File.FullName)"
        } else {
            Remove-Item $File.FullName -Force
            Write-Host "  Removed: $($File.Name)"
        }
    }
}

if ($DryRun) {
    Write-Host "Dry run complete. Run without -DryRun to actually delete."
} else {
    Write-Host "Cleanup complete."
}
