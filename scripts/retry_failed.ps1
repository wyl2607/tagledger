<#
.SYNOPSIS
  Retry all submission_failed records via /jobs/retry API.
.DESCRIPTION
  Sends a POST to /jobs/retry to re-enqueue all submission_failed records
  for SaaS submission. Defaults to http://127.0.0.1:8000.
.PARAMETER BaseUrl
  API base URL. Defaults to http://127.0.0.1:8000.
#>
param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$retryUrl = "$BaseUrl/jobs/retry"
Write-Host "Retrying all submission_failed records via $retryUrl ..."

try {
    $response = Invoke-RestMethod -Uri $retryUrl -Method Post
    $response | ForEach-Object {
        Write-Host "  re-enqueued #$($_.id) status=$($_.status)"
    }
    Write-Host "Done."
} catch {
    Write-Error "Retry failed: $_"
    exit 1
}
