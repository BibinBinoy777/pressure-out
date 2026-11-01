#Requires -Version 5.1
<#
.SYNOPSIS
  Runs frontend VM AST/ESLint verification (`npm run test:vm`), TypeScript check (`npm run typecheck`),
  ESLint (`npm run lint`), and production Next.js build (`npm run build`).
#>
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$FrontendDir = Join-Path $RepoRoot "frontend"
$CacheRoot = Join-Path $RepoRoot ".cache"

$env:NPM_CONFIG_CACHE = Join-Path $CacheRoot "npm"
$env:NEXT_TELEMETRY_DISABLED = "1"
$env:TEMP = Join-Path $CacheRoot "tmp"
$env:TMP = Join-Path $CacheRoot "tmp"

Set-Location $FrontendDir
Write-Host "1. Running offline-capable AST + ESLint + VDOM verification suite (npm run test:vm)..." -ForegroundColor Cyan
npm run test:vm
if ($LASTEXITCODE -ne 0) { Write-Error "npm run test:vm failed."; exit 1 }

if (Test-Path (Join-Path $FrontendDir "node_modules")) {
    Write-Host "2. Running TypeScript compiler check (npm run typecheck)..." -ForegroundColor Cyan
    npm run typecheck
    if ($LASTEXITCODE -ne 0) { Write-Error "npm run typecheck failed."; exit 1 }

    Write-Host "3. Running ESLint (npm run lint)..." -ForegroundColor Cyan
    npm run lint
    if ($LASTEXITCODE -ne 0) { Write-Error "npm run lint failed."; exit 1 }

    Write-Host "4. Building production Next.js bundle (npm run build)..." -ForegroundColor Cyan
    npm run build
    if ($LASTEXITCODE -ne 0) { Write-Error "npm run build failed."; exit 1 }
} else {
    Write-Warning "frontend\node_modules is not installed yet. Run scripts\windows\setup-frontend.ps1 first to execute tsc and next build."
    exit 2
}

Write-Host "[OK] All frontend checks and production build succeeded." -ForegroundColor Green
exit 0
