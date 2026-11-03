# Starts RouteX at http://localhost:8000. Press Ctrl+C to stop.
$ErrorActionPreference = 'Stop'
Set-Location "$PSScriptRoot\backend"
Start-Job { Start-Sleep 2; Start-Process 'http://localhost:8000' } | Out-Null
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
