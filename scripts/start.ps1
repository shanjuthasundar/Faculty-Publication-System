param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$healthUrl = "http://127.0.0.1:8000/api/health"
$appUrl = "http://127.0.0.1:8000/login.html"

function Test-Server {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec 2
        return ($response.StatusCode -eq 200)
    } catch {
        return $false
    }
}

if (-not (Test-Server)) {
    Write-Host "Starting backend server..."
    Start-Process py -ArgumentList "-3", "backend\server.py" -WorkingDirectory $projectRoot | Out-Null

    $started = $false
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 500
        if (Test-Server) {
            $started = $true
            break
        }
    }

    if (-not $started) {
        throw "Backend failed to start at $healthUrl"
    }
    Write-Host "Backend started."
} else {
    Write-Host "Backend already running."
}

if (-not $NoBrowser) {
    Start-Process chrome $appUrl
    Write-Host "Opened Chrome: $appUrl"
}
