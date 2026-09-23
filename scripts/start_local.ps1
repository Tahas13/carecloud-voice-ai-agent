# Brings the whole demo stack back up after a reboot:
#   1. FastAPI server on port 8123 (SQLite data persists in ./carecloud.db)
#   2. ngrok tunnel exposing it at the static public domain
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts\start_local.ps1

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Stop anything already bound to the port or the ngrok API.
foreach ($port in 8123, 4040) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}
Start-Sleep -Seconds 2

Start-Process -FilePath .\.venv\Scripts\python.exe `
    -ArgumentList '-m','uvicorn','app.main:app','--port','8123' `
    -RedirectStandardOutput server_out.log -RedirectStandardError server_err.log -WindowStyle Hidden

Start-Process -FilePath ngrok -ArgumentList 'http','8123' `
    -RedirectStandardOutput ngrok.log -WindowStyle Hidden

Start-Sleep -Seconds 8
$tunnel = (Invoke-RestMethod http://127.0.0.1:4040/api/tunnels).tunnels[0].public_url
Write-Host "API server:  http://localhost:8123"
Write-Host "Public URL:  $tunnel"
Write-Host "Health:      $((Invoke-WebRequest -UseBasicParsing "$tunnel/health" -Headers @{'ngrok-skip-browser-warning'='1'}).Content)"
