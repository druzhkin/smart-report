param(
    [string]$HealthUrl = "https://smart-report-production.up.railway.app/health",
    [string]$Service = "smart-report",
    [string]$Environment = "production",
    [int]$TimeoutMinutes = 10,
    [switch]$Push
)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $repo
try {
    if (-not $env:RAILWAY_TOKEN) {
        $envPath = Join-Path $repo ".env.local"
        if (Test-Path -LiteralPath $envPath) {
            $line = Get-Content -LiteralPath $envPath |
                Where-Object { $_ -match "^RAILWAY_TOKEN=" } |
                Select-Object -First 1
            if ($line) {
                $env:RAILWAY_TOKEN = $line.Substring("RAILWAY_TOKEN=".Length)
            }
        }
    }
    if (-not $env:RAILWAY_TOKEN) {
        throw "RAILWAY_TOKEN is not set and was not found in .env.local"
    }

    if ($Push) {
        git push origin v4.5
    }

    $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
    do {
        $status = railway service status --all
        Write-Host $status
        if ($status -match "$Service\s+\|.*\| SUCCESS") {
            break
        }
        if ($status -match "$Service\s+\|.*\| (FAILED|CRASHED|REMOVED)") {
            throw "Railway service $Service entered a failed state."
        }
        Start-Sleep -Seconds 20
    } while ((Get-Date) -lt $deadline)

    if ((Get-Date) -ge $deadline) {
        throw "Timed out waiting for Railway service $Service to reach SUCCESS."
    }

    $health = Invoke-WebRequest -UseBasicParsing $HealthUrl
    if ($health.StatusCode -ne 200) {
        throw "Health check failed: HTTP $($health.StatusCode)"
    }
    Write-Host "Health check passed: $($health.StatusCode) $($health.Content)"

    $logs = railway logs --service $Service --environment $Environment --http --status ">=400" --since 10m --lines 50
    if ($logs) {
        Write-Host $logs
        throw "Fresh HTTP >=400 logs found after deploy."
    }
    Write-Host "No fresh HTTP >=400 logs found."
}
finally {
    Pop-Location
}
