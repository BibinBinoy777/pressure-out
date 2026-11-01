#Requires -Version 5.1
<#
.SYNOPSIS
  Starts local PostgreSQL 16 and Redis 7 containers via docker-compose.local.yml
  and ensures all local directories and caches reside inside the repository on D:.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

# Ensure D: drive cache and data directories exist inside the repo
$dirs = @(
    ".local-data\postgres",
    ".local-data\redis",
    ".local-data\media",
    ".local-data\backups",
    ".cache\python",
    ".cache\npm",
    ".cache\playwright",
    ".cache\tmp"
)
foreach ($rel in $dirs) {
    $full = Join-Path $RepoRoot $rel
    if (-not (Test-Path $full)) {
        New-Item -ItemType Directory -Path $full -Force | Out-Null
    }
}

# Initialize .env.local from .env.local.example if not already present (never overwrite!)
$envLocal = Join-Path $RepoRoot ".env.local"
if (-not (Test-Path $envLocal)) {
    Copy-Item (Join-Path $RepoRoot ".env.local.example") $envLocal
    Write-Host "[INFO] Created .env.local from .env.local.example (existing files are never overwritten)." -ForegroundColor Yellow
}

Write-Host "Starting local PostgreSQL 16 and Redis 7 containers..." -ForegroundColor Cyan
docker compose -f docker-compose.local.yml --env-file .env.local up -d
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to start local Docker services. Verify Docker Desktop is running."
    exit 1
}

Write-Host "Waiting for PostgreSQL 16 and Redis 7 health checks..." -ForegroundColor Cyan
$maxAttempts = 30
for ($i = 1; $i -le $maxAttempts; $i++) {
    $pgHealth = docker inspect --format "{{.State.Health.Status}}" pressure-out-local-postgres 2>$null
    $redisHealth = docker inspect --format "{{.State.Health.Status}}" pressure-out-local-redis 2>$null
    if ($pgHealth -eq "healthy" -and $redisHealth -eq "healthy") {
        Write-Host "[OK] pressure-out-local-postgres (healthy) & pressure-out-local-redis (healthy)" -ForegroundColor Green
        docker compose -f docker-compose.local.yml ps
        exit 0
    }
    Start-Sleep -Seconds 2
}

Write-Error "Timed out waiting for PostgreSQL 16 or Redis 7 to become healthy."
exit 1
