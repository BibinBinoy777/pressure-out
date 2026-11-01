"""Phase 12.3 Local Windows Setup, D: Drive Configuration & 35-Step Full-System Validation Suite."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_smoke_spec = importlib.util.spec_from_file_location(
    "run_local_smoke_35", REPO_ROOT / "scripts" / "run_local_smoke_35.py"
)
assert _smoke_spec and _smoke_spec.loader
_smoke_mod = importlib.util.module_from_spec(_smoke_spec)
_smoke_spec.loader.exec_module(_smoke_mod)
run_local_smoke_35 = _smoke_mod.run_local_smoke_35


class Phase123WindowsLocalValidationTests(unittest.TestCase):
    def test_01_docker_compose_local_and_env_local_example_d_drive_invariants(self) -> None:
        """Verifies docker-compose.local.yml loopback bindings, noeviction Redis, and .env.local.example D: drive paths."""
        local_compose = (REPO_ROOT / "docker-compose.local.yml").read_text()
        self.assertIn("image: postgres:16-alpine", local_compose)
        self.assertIn("image: redis:7-alpine", local_compose)
        self.assertIn("127.0.0.1:${LOCAL_POSTGRES_PORT:-54329}:5432", local_compose)
        self.assertIn("127.0.0.1:${LOCAL_REDIS_PORT:-63799}:6379", local_compose)
        self.assertIn("--maxmemory-policy noeviction", local_compose)
        self.assertIn("pressure_out_local_pgdata", local_compose)
        self.assertIn("pressure_out_local_redisdata", local_compose)

        env_local = (REPO_ROOT / ".env.local.example").read_text()
        self.assertIn("LOCAL_PROJECT_ROOT=D:/PressureOut", env_local)
        self.assertIn("PIP_CACHE_DIR=D:/PressureOut/.cache/python", env_local)
        self.assertIn("NPM_CONFIG_CACHE=D:/PressureOut/.cache/npm", env_local)
        self.assertIn("LOCAL_STORAGE_PATH=D:/PressureOut/.local-data/media", env_local)
        self.assertIn("RATE_LIMIT_BACKEND=redis", env_local)
        self.assertIn("RATE_LIMIT_FAIL_CLOSED=true", env_local)

        gitignore = (REPO_ROOT / ".gitignore").read_text()
        self.assertIn("!.env.local.example", gitignore)
        self.assertIn(".local-data/", gitignore)
        self.assertIn(".cache/", gitignore)

    def test_02_windows_powershell_scripts_and_documentation_completeness(self) -> None:
        """Verifies all 8 PowerShell scripts in scripts/windows/ and docs/development/WINDOWS_LOCAL_DEVELOPMENT.md."""
        expected_scripts = [
            "check-environment.ps1",
            "start-local-services.ps1",
            "stop-local-services.ps1",
            "setup-backend.ps1",
            "setup-frontend.ps1",
            "run-backend-tests.ps1",
            "run-frontend-checks.ps1",
            "run-local-smoke.ps1",
        ]
        win_dir = REPO_ROOT / "scripts" / "windows"
        for name in expected_scripts:
            p = win_dir / name
            self.assertTrue(p.is_file(), f"Missing PowerShell script: {name}")
            content = p.read_text()
            self.assertIn("$ErrorActionPreference = \"Stop\"", content)
            # Ensure no script runs destructive docker compose down -v
            self.assertNotIn("down -v", content)

        check_env_txt = (win_dir / "check-environment.ps1").read_text()
        self.assertIn("Get-PSDrive -PSProvider FileSystem", check_env_txt)

        guide_path = REPO_ROOT / "docs" / "development" / "WINDOWS_LOCAL_DEVELOPMENT.md"
        self.assertTrue(guide_path.is_file())
        guide_txt = guide_path.read_text()
        self.assertIn("D:\\PressureOut", guide_txt)
        self.assertIn("D:\\DockerData", guide_txt)
        self.assertIn("Get-PSDrive -PSProvider FileSystem", guide_txt)

    def test_03_complete_35_step_local_smoke_verification(self) -> None:
        """Executes the full 35-step local end-to-end smoke flow and confirms 35/35 steps pass."""
        report = run_local_smoke_35()
        self.assertTrue(report["all_passed"])
        self.assertEqual(report["total_steps"], 35)
        self.assertEqual(report["passed_steps"], 35)


if __name__ == "__main__":
    unittest.main()
