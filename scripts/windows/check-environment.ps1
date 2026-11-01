#Requires -Version 5.1
<#
.SYNOPSIS
  Pressure Out — Local Windows & D: Drive Environment Readiness Check (Phase 12.3)
.DESCRIPTION
  Inspects Windows version, PowerShell version, C: and D: drive free space,
  project location (preferring D:\PressureOut), Docker Desktop WSL disk location,
  and required developer tools (python, node, npm, git, docker) without printing secrets.
#>
$ErrorActionPreference = "Stop"

Write-Host "=== Pressure Out: Local Windows Environment & D: Drive Check ===" -ForegroundColor Cyan

# 1. OS & PowerShell Version
$osInfo = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
if ($osInfo) {
    Write-Host ("Windows Edition : {0} ({1})" -f $osInfo.Caption, $osInfo.Version)
}
Write-Host ("PowerShell Ver  : {0}" -f $PSVersionTable.PSVersion.ToString())

# 2. Project Location Check (Must prioritize D:\PressureOut)
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Write-Host ("Repository Path : {0}" -f $RepoRoot)
if (-not $RepoRoot.StartsWith("D:\", [System.StringComparison]::OrdinalIgnoreCase)) {
    Write-Warning "Repository is currently not on D:\ (recommended: D:\PressureOut). See docs/development/WINDOWS_LOCAL_DEVELOPMENT.md for safe relocation steps."
} else {
    Write-Host "[OK] Repository is located on D: drive." -ForegroundColor Green
}

# 3. Disk Space Check via Get-PSDrive -PSProvider FileSystem
Write-Host "`n--- Filesystem Drive Space ---" -ForegroundColor Cyan
$drives = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Name -in @("C", "D") }
foreach ($d in $drives) {
    $freeGB = [math]::Round($d.Free / 1GB, 2)
    $usedGB = [math]::Round($d.Used / 1GB, 2)
    Write-Host ("Drive {0}: Free = {1} GB | Used = {2} GB" -f $d.Name, $freeGB, $usedGB)
    if ($d.Name -eq "C" -and $freeGB -lt 10) {
        Write-Warning "Drive C: has less than 10 GB free ($freeGB GB). All Pressure Out caches, venv, node_modules, and Docker volumes MUST use D:."
    }
    if ($d.Name -eq "D" -and $freeGB -lt 15) {
        Write-Error "Drive D: has less than 15 GB free ($freeGB GB). At least 15 GB free on D: is recommended."
        exit 1
    }
}

# 4. Docker Desktop WSL Data Location Check
$defaultDockerWsl = Join-Path $env:LOCALAPPDATA "Docker\wsl"
if (Test-Path $defaultDockerWsl) {
    Write-Warning "Docker Desktop WSL data directory detected on C: ($defaultDockerWsl). Open Docker Desktop -> Settings -> Resources -> Advanced -> Disk image location and set it to D:\DockerData."
}

# 5. Tool Availability Checks
Write-Host "`n--- Developer Tooling ---" -ForegroundColor Cyan
$missingTools = @()
foreach ($tool in @("git", "python", "node", "npm", "docker")) {
    $cmd = Get-Command $tool -ErrorAction SilentlyContinue
    if ($null -eq $cmd) {
        Write-Warning ("Missing command: {0}" -f $tool)
        $missingTools += $tool
    } else {
        Write-Host ("[OK] {0} -> {1}" -f $tool, $cmd.Source) -ForegroundColor Green
    }
}

if ($missingTools.Count -gt 0) {
    Write-Error ("Missing required tools: {0}. Please install them before starting local services." -f ($missingTools -join ", "))
    exit 1
}

# 6. Check Docker Compose & Daemon Status
try {
    $dockerInfo = docker info --format "{{.ServerVersion}}" 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $dockerInfo) {
        Write-Warning "Docker Desktop daemon is not currently running. Start Docker Desktop before running start-local-services.ps1."
        exit 2
    }
    Write-Host ("[OK] Docker Daemon Running (Server Version: {0})" -f $dockerInfo) -ForegroundColor Green
} catch {
    Write-Warning "Docker Desktop daemon is not reachable."
    exit 2
}

Write-Host "`n[READY] Windows environment check completed successfully." -ForegroundColor Green
exit 0
