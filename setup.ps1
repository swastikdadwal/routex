# One-time setup: Python environment, database, and the built frontend.
# Needs Python 3.11+, Node.js and PostgreSQL 17 already installed.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$nodeDir = Join-Path $env:ProgramFiles 'nodejs'
if (Test-Path $nodeDir) { $env:Path = "$nodeDir;$env:Path" }

Write-Host 'Setting up the Python backend...'
if (-not (Test-Path 'backend\.venv')) { python -m venv backend\.venv }
& backend\.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check -r backend\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Installing Python packages failed.' }

Write-Host 'Setting up the database...'
& backend\.venv\Scripts\python.exe backend\scripts\init_db.py
if ($LASTEXITCODE -ne 0) { throw 'Database setup failed. Check that PostgreSQL is running.' }

Write-Host 'Building the React frontend...'
Push-Location frontend
# npm reports progress on stderr, so its exit codes decide success here, not PowerShell.
$ErrorActionPreference = 'Continue'
try {
  npm ci --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) { throw 'Installing frontend packages failed.' }
  npm run build
  if ($LASTEXITCODE -ne 0) { throw 'Building the frontend failed.' }
} finally {
  $ErrorActionPreference = 'Stop'
  Pop-Location
}

Write-Host 'Setup complete. Start RouteX with: .\start.ps1'
