#Requires -Version 5.1
<#
.SYNOPSIS
  Stops local PostgreSQL 16 and Redis 7 containers without deleting persistent volumes.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

Write-Host "Stopping local PostgreSQL 16 and Redis 7 containers (preserving volumes)..." -ForegroundColor Cyan
docker compose -f docker-compose.local.yml stop
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to stop local Docker services."
    exit 1
}
Write-Host "[OK] Local services stopped. Persistent volumes (pressure_out_local_pgdata, pressure_out_local_redisdata) are preserved." -ForegroundColor Green
exit 0
