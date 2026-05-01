param(
    [switch]$BackendOnly,
    [switch]$SkipE2E
)

$ErrorActionPreference = "Stop"
$repo = Resolve-Path (Join-Path $PSScriptRoot "..")

function Invoke-Gate {
    param(
        [string]$Name,
        [string]$Command,
        [string]$WorkingDirectory = $repo
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    Push-Location $WorkingDirectory
    try {
        powershell -NoProfile -ExecutionPolicy Bypass -Command $Command
        if ($LASTEXITCODE -ne 0) {
            throw "$Name failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

Invoke-Gate `
    -Name "Python premium/report contract tests" `
    -Command "pytest tests\test_premium_artifact_qa.py tests\test_premium_document.py tests\test_enterprise_structured_source.py tests\test_v4_endpoints.py -q"

Invoke-Gate `
    -Name "Python symbol lint for touched quality surfaces" `
    -Command "ruff check smart_report\api\v4_endpoints.py smart_report\exporters\premium\artifact_qa.py scripts\premium_artifact_qa.py tests\test_premium_artifact_qa.py tests\test_v4_endpoints.py --select F401,F821"

if (-not $BackendOnly) {
    Invoke-Gate `
        -Name "Frontend production build" `
        -Command "npm run build" `
        -WorkingDirectory (Join-Path $repo "frontend")

    if (-not $SkipE2E) {
        Invoke-Gate `
            -Name "Structured report editor browser flow" `
            -Command "npm run test:e2e -- --grep 'structured report'" `
            -WorkingDirectory (Join-Path $repo "frontend")
    }
}

Write-Host ""
Write-Host "Enterprise quality gates passed." -ForegroundColor Green
