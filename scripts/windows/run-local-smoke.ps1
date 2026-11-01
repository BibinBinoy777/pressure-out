#Requires -Version 5.1
<#
.SYNOPSIS
  Executes the 35-step end-to-end local application smoke test (`scripts/run_local_smoke_35.py`).
#>
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BackendDir = Join-Path $RepoRoot "backend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$PythonCmd = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

$env:PYTHONPATH = $BackendDir
$env:TEMP = Join-Path $RepoRoot ".cache\tmp"
$env:TMP = Join-Path $RepoRoot ".cache\tmp"

Set-Location $RepoRoot
Write-Host "Executing 35-Step Local End-to-End Smoke Verification..." -ForegroundColor Cyan
& $PythonCmd scripts/run_local_smoke_35.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "35-Step Local Smoke Verification failed."
    exit 1
}
Write-Host "[OK] All 35 local end-to-end smoke steps passed." -ForegroundColor Green
exit 0
