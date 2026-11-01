#Requires -Version 5.1
<#
.SYNOPSIS
  Creates backend\.venv on D:, sets project-scoped PIP_CACHE_DIR/TEMP/TMP on D:,
  installs Python dependencies, and runs Alembic migrations to head (0010_phase11_workplace).
#>
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BackendDir = Join-Path $RepoRoot "backend"
$VenvDir = Join-Path $BackendDir ".venv"
$CacheRoot = Join-Path $RepoRoot ".cache"

$env:PIP_CACHE_DIR = Join-Path $CacheRoot "python"
$env:TEMP = Join-Path $CacheRoot "tmp"
$env:TMP = Join-Path $CacheRoot "tmp"

foreach ($p in @($env:PIP_CACHE_DIR, $env:TEMP)) {
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
}

if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating Python virtual environment at $VenvDir ..." -ForegroundColor Cyan
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Write-Error "Failed to create virtual environment."; exit 1 }
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment Python executable not found at $VenvPython"
    exit 1
}

Set-Location $BackendDir
Write-Host "Installing backend dependencies into $VenvDir (cache on D:)..." -ForegroundColor Cyan
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { Write-Error "pip install failed."; exit 1 }

Write-Host "Applying Alembic migrations up to head (0010_phase11_workplace)..." -ForegroundColor Cyan
& $VenvPython -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Warning "alembic upgrade head did not succeed. Verify PostgreSQL 16 is running via scripts\windows\start-local-services.ps1."
    exit 1
}

Write-Host "[OK] Backend virtual environment and database migrations are ready." -ForegroundColor Green
exit 0
