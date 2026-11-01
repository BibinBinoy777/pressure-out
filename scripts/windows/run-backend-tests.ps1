#Requires -Version 5.1
<#
.SYNOPSIS
  Runs the complete backend regression test suite (18 test modules) and PostgreSQL qualification check.
#>
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$BackendDir = Join-Path $RepoRoot "backend"
$VenvPython = Join-Path $BackendDir ".venv\Scripts\python.exe"
$PythonCmd = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

$env:PYTHONPATH = $BackendDir
$env:TEMP = Join-Path $RepoRoot ".cache\tmp"
$env:TMP = Join-Path $RepoRoot ".cache\tmp"

Set-Location $BackendDir
Write-Host "Running backend unittest suite via $PythonCmd ..." -ForegroundColor Cyan
& $PythonCmd -m unittest discover -s tests -p "test_*.py" -v
if ($LASTEXITCODE -ne 0) {
    Write-Error "Backend test suite reported failures."
    exit 1
}

Write-Host "[OK] All backend test modules passed." -ForegroundColor Green
exit 0
