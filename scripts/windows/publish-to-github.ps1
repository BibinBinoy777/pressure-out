#Requires -Version 5.1

$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$RemoteUrl = "https://github.com/BibinBinoy777/pressure-out.git"

function Assert-GitSuccess {
    param([string]$Operation)

    if ($LASTEXITCODE -ne 0) {
        throw "Git operation failed: $Operation"
    }
}

Write-Host "`n1. Checking Git installation..." -ForegroundColor Cyan

git --version
Assert-GitSuccess "git version"

Write-Host "`n2. Initializing local repository..." -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $RepoRoot ".git"))) {
    git init -b main
    Assert-GitSuccess "git init"
}

$branch = git branch --show-current
Assert-GitSuccess "branch inspection"

if ($branch -ne "main") {
    git branch -M main
    Assert-GitSuccess "branch rename"
}

Write-Host "`n3. Configuring GitHub remote..." -ForegroundColor Cyan

$existingRemotes = @(git remote)
Assert-GitSuccess "remote inspection"

if ($existingRemotes -contains "origin") {
    git remote set-url origin $RemoteUrl
} else {
    git remote add origin $RemoteUrl
}

Assert-GitSuccess "remote configuration"

git remote -v

Write-Host "`n4. Checking remote repository before publication..." -ForegroundColor Cyan

$remoteRefs = @(git ls-remote --heads origin)
Assert-GitSuccess "remote inspection"

if ($remoteRefs.Count -gt 0) {
    throw "Remote repository already contains branches. Aborting to protect existing history."
}

Write-Host "[OK] Remote has no existing branches." -ForegroundColor Green

Write-Host "`n5. Staging project files..." -ForegroundColor Cyan

git add -A
Assert-GitSuccess "git add"

$stagedFiles = @(git diff --cached --name-only)
Assert-GitSuccess "staged file inspection"

if ($stagedFiles.Count -eq 0) {
    throw "No files are staged. Nothing to publish."
}

Write-Host "`n6. Running filename security audit..." -ForegroundColor Cyan

$forbiddenPatterns = @(
    '(^|/)\.env($|\.(?!example$|local\.example$))',
    '(^|/)node_modules(/|$)',
    '(^|/)\.venv(/|$)',
    '(^|/)\.next(/|$)',
    '(^|/)\.cache(/|$)',
    '(^|/)\.local-data(/|$)',
    '(^|/)(backups|backup|dumps|dump)(/|$)',
    '(^|/)[^/]+\.(sqlite3?|db|dump|rdb|pem|key|p12|pfx)$',
    '(^|/)(id_rsa|id_ed25519)$'
)

foreach ($file in $stagedFiles) {
    foreach ($pattern in $forbiddenPatterns) {
        if ($file -match $pattern) {
            throw "SECURITY AUDIT FAILED: Forbidden file detected: $file"
        }
    }
}

Write-Host "[OK] Filename security audit passed." -ForegroundColor Green

git diff --cached --check
if ($LASTEXITCODE -ne 0) { Write-Warning "Whitespace warnings detected. Review separately; source files have not been modified." }

Write-Host "`n7. Creating initial commit..." -ForegroundColor Cyan

git commit -m "Initial release: Pressure Out Phases 1-12.3"
Assert-GitSuccess "initial commit"

$localSha = (git rev-parse HEAD).Trim()
Assert-GitSuccess "local commit verification"

Write-Host "`n8. Publishing to GitHub..." -ForegroundColor Cyan

git push -u origin main
Assert-GitSuccess "GitHub push"

Write-Host "`n9. Verifying GitHub publication..." -ForegroundColor Cyan

$remoteRef = git ls-remote origin refs/heads/main
Assert-GitSuccess "remote verification"

if (-not $remoteRef -or -not $remoteRef.StartsWith($localSha)) {
    throw "Remote verification failed. The GitHub commit does not match local HEAD."
}

Write-Host "`n[SUCCESS] Pressure Out published successfully." -ForegroundColor Green
Write-Host "Commit: $localSha"
Write-Host "Repository: $RemoteUrl"


