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

function Get-PythonCommand {
    $directPython = Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"
    if (Test-Path $directPython) {
        return $directPython
    }

    foreach ($candidate in @("py", "python", "python3")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            return $candidate
        }
    }
    return $null
}

if (-not (Test-Server)) {
    Write-Host "Starting backend server..."
    $pythonCmd = Get-PythonCommand
    if (-not $pythonCmd) {
        throw "Python executable not found. Install Python and try again."
    }

    if ($pythonCmd -eq "py") {
        Start-Process $pythonCmd -ArgumentList "-3", "backend\server.py" -WorkingDirectory $projectRoot | Out-Null
    } else {
        Start-Process $pythonCmd -ArgumentList "backend\server.py" -WorkingDirectory $projectRoot | Out-Null
    }

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
    $chromeCmd = Get-Command "chrome" -ErrorAction SilentlyContinue
    if ($chromeCmd) {
        Start-Process chrome $appUrl
        Write-Host "Opened Chrome: $appUrl"
    } else {
        Start-Process $appUrl
        Write-Host "Chrome not found in PATH. Opened default browser: $appUrl"
    }
}
