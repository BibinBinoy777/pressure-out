# Pressure Out — Local Windows Setup & D: Drive Development Guide (Phase 12.3)

## 1. Governing Principle: Local Windows First & D: Drive Storage Priority

Pressure Out is configured to run and validate 100% locally on your Windows machine before any external hosting or cloud deployment is considered.

Because the **`C:` drive is nearly full**, all Pressure Out source code, virtual environments, package caches, Docker volumes, media assets, and database backups **must reside on `D:`**:

| Asset / Component | Required `D:` Drive Location | How It Is Configured |
|---|---|---|
| **Main Repository** | `D:\PressureOut` | Cloned or relocated to `D:\PressureOut` |
| **Python Virtual Environment** | `D:\PressureOut\backend\.venv` | Created by `scripts\windows\setup-backend.ps1` |
| **Python `pip` Cache** | `D:\PressureOut\.cache\python` | Project-scoped `PIP_CACHE_DIR` in `.env.local` & PowerShell scripts |
| **Frontend `node_modules` & `.next`** | `D:\PressureOut\frontend\node_modules` & `.next` | Installed by `scripts\windows\setup-frontend.ps1` |
| **Node `npm` Cache** | `D:\PressureOut\.cache\npm` | Project-scoped `NPM_CONFIG_CACHE` in `.env.local` & PowerShell scripts |
| **Playwright Browsers** | `D:\PressureOut\.cache\playwright` | Project-scoped `PLAYWRIGHT_BROWSERS_PATH` |
| **Build / Test Temp Files** | `D:\PressureOut\.cache\tmp` | Project-scoped `TEMP` and `TMP` inside PowerShell scripts |
| **Docker Desktop WSL Disk Image** | `D:\DockerData` | Docker Desktop -> Settings -> Resources -> Advanced -> Disk image location |
| **Local Media Storage** | `D:\PressureOut\.local-data\media` | `LOCAL_STORAGE_PATH` in `.env.local` |
| **Local PostgreSQL Backups** | `D:\PressureOut\.local-data\backups` | `LOCAL_BACKUP_DIR` in `.env.local` |

## 2. Safe Relocation Procedure (If Repository Is Currently on `C:`)

If your working copy is currently on `C:`, **do not delete it until the `D:\PressureOut` copy is verified**:

```powershell
# 1. Check available disk space on C: and D:
Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Name -in @("C", "D") }

# 2. Copy the complete repository (including .git history and untracked files) to D:\PressureOut
New-Item -ItemType Directory -Path "D:\PressureOut" -Force
robocopy "C:\path\to\current\Pressure-Out" "D:\PressureOut" /E /COPYALL /XD ".venv" "node_modules" ".next" ".cache"

# 3. Switch to D:\PressureOut and verify Git status and branch integrity
Set-Location D:\PressureOut
git status
```

## 3. Relocating Docker Desktop Storage to `D:\DockerData`

Before starting PostgreSQL 16 and Redis 7 containers, ensure Docker Desktop stores its WSL2 virtual disk (`ext4.vhdx`) on `D:`:

1. Create `D:\DockerData` in PowerShell:
   ```powershell
   New-Item -ItemType Directory -Path "D:\DockerData" -Force
   ```
2. Open **Docker Desktop** -> **Settings** -> **Resources** -> **Advanced** (or **Virtual disk**).
3. Change **Disk image location** from `C:\Users\<User>\AppData\Local\Docker\wsl` to `D:\DockerData`.
4. Click **Apply & restart**. Docker Desktop will safely migrate existing container/volume layers to `D:\DockerData`.

## 4. Prerequisites & Windows Environment Check

Required tools on Windows 10/11:
* **Windows PowerShell 5.1** or **PowerShell 7+**
* **Python 3.11+** (`python --version`)
* **Node.js 20 LTS+** and **npm 10+** (`node --version`, `npm --version`)
* **Git for Windows** (`git --version`)
* **Docker Desktop for Windows** (with WSL2 backend running)

Run the non-destructive readiness check from `D:\PressureOut`:

```powershell
Set-Location D:\PressureOut
.\scripts\windows\check-environment.ps1
```

## 5. One-Time Local Setup on `D:\PressureOut`

```powershell
Set-Location D:\PressureOut

# 1. Start local PostgreSQL 16 (127.0.0.1:54329) and Redis 7 (127.0.0.1:63799)
.\scripts\windows\start-local-services.ps1

# 2. Create D:\PressureOut\backend\.venv, install Python deps (cached on D:), and run Alembic migrations (0001 -> 0010)
.\scripts\windows\setup-backend.ps1

# 3. Install D:\PressureOut\frontend\node_modules (npm cache pinned to D:)
.\scripts\windows\setup-frontend.ps1
```

## 6. Daily Routine: Starting & Stopping Pressure Out Locally

### 6.1 Starting Pressure Out (4 PowerShell Tabs in Windows Terminal)

* **Tab 1 — Start Local PostgreSQL 16 & Redis 7 Containers:**
  ```powershell
  Set-Location D:\PressureOut
  .\scripts\windows\start-local-services.ps1
  ```
* **Tab 2 — Start the FastAPI Backend (`http://localhost:8000`):**
  ```powershell
  Set-Location D:\PressureOut\backend
  $env:ENV_FILE = "D:\PressureOut\.env.local"
  .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
  ```
* **Tab 3 — Start the Background Meme Worker:**
  ```powershell
  Set-Location D:\PressureOut\backend
  .\.venv\Scripts\python.exe -m app.workers.runner
  ```
* **Tab 4 — Start the Next.js Frontend (`http://localhost:3000`):**
  ```powershell
  Set-Location D:\PressureOut\frontend
  npm run dev
  ```
* Open **`http://localhost:3000`** in your browser (API health check: **`http://localhost:8000/api/v1/health/ready`**).

### 6.2 Stopping Pressure Out (Preserving All Database Volumes)

1. Press `Ctrl+C` in the Frontend, Worker, and Backend PowerShell tabs.
2. Stop the PostgreSQL 16 and Redis 7 containers without deleting their persistent volumes:
   ```powershell
   Set-Location D:\PressureOut
   .\scripts\windows\stop-local-services.ps1
   ```

## 7. Running Automated Verification, Production Build & 35-Step Smoke Tests

```powershell
Set-Location D:\PressureOut

# 1. Run all 18 backend test modules (87 tests)
.\scripts\windows\run-backend-tests.ps1

# 2. Run frontend AST/ESLint/VDOM checks, TypeScript compiler, ESLint, and production `next build`
.\scripts\windows\run-frontend-checks.ps1

# 3. Run the complete 35-step end-to-end local application smoke test
.\scripts\windows\run-local-smoke.ps1

# 4. Run the live 16-step PostgreSQL 16 qualification suite against local Docker PostgreSQL 16
.\backend\.venv\Scripts\python.exe scripts\qualify_postgres_staging.py --app-env staging --database-url "postgresql+asyncpg://po_local_user:po_local_win_pg_pass_change_me@127.0.0.1:54329/pressure_out_local_staging_qual"
```

## 8. Windows-Specific Troubleshooting

* **Docker Desktop not running (`error during connect`):** Start **Docker Desktop** from the Start Menu, wait for the whale icon in the system tray to report *Docker Desktop is running*, and re-run `.\scripts\windows\start-local-services.ps1`.
* **Port already in use (`54329`, `63799`, `8000`, or `3000`):**
  * Inspect which process owns the port: `Get-NetTCPConnection -LocalPort 8000 | Select-Object LocalPort,OwningProcess`
  * `docker-compose.local.yml` intentionally defaults PostgreSQL to `127.0.0.1:54329` and Redis to `127.0.0.1:63799` so it never conflicts with native Windows services on `5432` or `6379`.
* **PowerShell script execution policy error (`cannot be loaded because running scripts is disabled`):**
  * Run for the current process only without altering machine-wide policy:
    ```powershell
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    ```
* **Frontend/Backend CORS or CSRF mismatch:** Ensure you access the frontend via `http://localhost:3000` (matching `CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000` and `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`).
