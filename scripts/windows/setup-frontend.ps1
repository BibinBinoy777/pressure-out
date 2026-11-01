#Requires -Version 5.1
<#
.SYNOPSIS
  Installs frontend dependencies into D:\PressureOut\frontend\node_modules
  with npm cache and temporary directories pinned to D:\PressureOut\.cache.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$FrontendDir = Join-Path $RepoRoot "frontend"
$CacheRoot = Join-Path $RepoRoot ".cache"

$env:NPM_CONFIG_CACHE = Join-Path $CacheRoot "npm"
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $CacheRoot "playwright"
$env:NEXT_TELEMETRY_DISABLED = "1"
$env:TEMP = Join-Path $CacheRoot "tmp"
$env:TMP = Join-Path $CacheRoot "tmp"

foreach ($p in @($env:NPM_CONFIG_CACHE, $env:PLAYWRIGHT_BROWSERS_PATH, $env:TEMP)) {
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null }
}

Set-Location $FrontendDir
Write-Host "Installing frontend dependencies in $FrontendDir (npm cache at $env:NPM_CONFIG_CACHE)..." -ForegroundColor Cyan
if (Test-Path (Join-Path $FrontendDir "package-lock.json")) {
    npm ci
} else {
    npm install
}
if ($LASTEXITCODE -ne 0) {
    Write-Error "Frontend dependency installation failed."
    exit 1
}

Write-Host "[OK] Frontend dependencies installed on D: drive." -ForegroundColor Green
exit 0
