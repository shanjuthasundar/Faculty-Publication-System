$ErrorActionPreference = "SilentlyContinue"

$processes = Get-CimInstance Win32_Process | Where-Object {
    $_.Name -like "python*.exe" -and $_.CommandLine -match "backend\\server.py"
}

if (-not $processes) {
    Write-Host "No backend server process found."
    exit 0
}

foreach ($proc in $processes) {
    Stop-Process -Id $proc.ProcessId -Force
}

Write-Host "Stopped backend server process(es)."
