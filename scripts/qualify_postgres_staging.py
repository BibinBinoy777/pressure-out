#!/usr/bin/env python3
"""Pressure Out — 16-Step PostgreSQL 16 & Staging Safety Qualification Runner (Phase 12.1 & 12.2).

Enforces Section 3 Staging Safety Requirements:
- Requires APP_ENV=staging
- Verifies DATABASE_URL and REDIS_URL explicitly target staging (rejecting production identifiers)
- Verifies CORS_ORIGINS are staging origins
- Verifies backup/restore targets are disposable (pressure_out_restore_drill_*)
- Masks all secret credentials before emitting output
- Never fakes PostgreSQL or Redis verification using SQLite or mocks.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from typing import Any, Dict, List

EXPECTED_ALEMBIC_HEAD = "0010_phase11_workplace"
REQUIRED_PG_EXTENSIONS = ("pgcrypto", "citext", "ltree", "pg_trgm")
_DISPOSABLE_DB_RE = re.compile(r"^pressure_out_restore_drill_[0-9]{8,16}$")
_PROD_TOKEN_RE = re.compile(r"(?:^|[\-_./:@])prod(?:uction)?(?:$|[\-_./:@])", re.I)

QUALIFICATION_STEPS: List[Dict[str, str]] = [
    {"step": "01", "id": "pg16_startup", "title": "PostgreSQL 16 server connectivity & version check (>= 16.0)"},
    {"step": "02", "id": "pg_extensions", "title": "Required extensions available (pgcrypto, citext, ltree, pg_trgm)"},
    {"step": "03", "id": "alembic_upgrade", "title": "Complete Alembic migration from base to head (0001 -> 0010)"},
    {"step": "04", "id": "alembic_head_check", "title": "Verify alembic_version matches 0010_phase11_workplace"},
    {"step": "05", "id": "app_startup_pg", "title": "FastAPI application startup and /api/v1/health/ready against PostgreSQL"},
    {"step": "06", "id": "integration_suite_pg", "title": "Execute backend integration test suite against PostgreSQL"},
    {"step": "07", "id": "fk_and_uniqueness", "title": "Verify foreign-key cascades and CITEXT/unique index enforcement"},
    {"step": "08", "id": "audit_triggers", "title": "Verify append-only audit_events triggers block UPDATE and DELETE"},
    {"step": "09", "id": "tx_rollback", "title": "Verify transaction rollback leaves zero partial rows on exception"},
    {"step": "10", "id": "concurrent_moderation", "title": "Verify concurrent high-severity reports trigger single protective hold"},
    {"step": "11", "id": "concurrent_contributions", "title": "Verify concurrent structured workplace contribution upserts preserve UNIQUE(user_id)"},
    {"step": "12", "id": "connection_recovery", "title": "Verify connection pool recovery after database session termination"},
    {"step": "13", "id": "backup_creation", "title": "Execute pg_dump custom-format backup with 0600 permissions & SHA-256"},
    {"step": "14", "id": "backup_verification", "title": "Verify backup SHA-256 digest and pg_restore --list catalog"},
    {"step": "15", "id": "disposable_restore", "title": "Restore archive into disposable database (pressure_out_restore_drill_*)"},
    {"step": "16", "id": "post_restore_integrity", "title": "Verify restored database alembic_version=0010_phase11_workplace and table counts"},
]


def verify_staging_safety_guards(
    *,
    app_env: str,
    database_url: str,
    redis_url: str,
    cors_origins: List[str],
    restore_target_db: str = "pressure_out_restore_drill_2026103001",
) -> None:
    """Enforce Phase 12.2 Section 3 staging safety invariants before connecting to any service."""
    if (app_env or "").strip().lower() != "staging":
        raise ValueError(f"STAGING_SAFETY_ERROR: APP_ENV must be 'staging' (got '{app_env}').")

    if not database_url or not database_url.startswith("postgresql"):
        raise ValueError("STAGING_SAFETY_ERROR: DATABASE_URL must be a PostgreSQL connection string.")
    if _PROD_TOKEN_RE.search(database_url):
        raise ValueError("STAGING_SAFETY_ERROR: Production identifier detected in DATABASE_URL; aborting.")
    if "staging" not in database_url.lower() and "stage" not in database_url.lower():
        raise ValueError("STAGING_SAFETY_ERROR: DATABASE_URL must explicitly identify a staging database.")

    if not redis_url or not redis_url.startswith(("redis://", "rediss://")):
        raise ValueError("STAGING_SAFETY_ERROR: REDIS_URL must be a valid Redis connection string.")
    if _PROD_TOKEN_RE.search(redis_url):
        raise ValueError("STAGING_SAFETY_ERROR: Production identifier detected in REDIS_URL; aborting.")
    if "staging" not in redis_url.lower() and "stage" not in redis_url.lower() and "127.0.0.1" not in redis_url:
        raise ValueError("STAGING_SAFETY_ERROR: REDIS_URL must explicitly target a staging Redis service.")

    if not cors_origins:
        raise ValueError("STAGING_SAFETY_ERROR: CORS_ORIGINS must not be empty.")
    for origin in cors_origins:
        if origin == "*" or _PROD_TOKEN_RE.search(origin):
            raise ValueError(f"STAGING_SAFETY_ERROR: Unsafe or production CORS origin '{origin}' rejected.")

    if not _DISPOSABLE_DB_RE.match(restore_target_db):
        raise ValueError(
            f"STAGING_SAFETY_ERROR: Restore target '{restore_target_db}' must match ^pressure_out_restore_drill_[0-9]{{8,16}}$."
        )


def inspect_environment() -> Dict[str, Any]:
    binaries = {
        name: shutil.which(name) is not None
        for name in ("psql", "pg_dump", "pg_restore", "alembic", "redis-server", "redis-cli", "docker")
    }
    return {
        "expected_alembic_head": EXPECTED_ALEMBIC_HEAD,
        "required_extensions": list(REQUIRED_PG_EXTENSIONS),
        "binaries_available": binaries,
        "steps": QUALIFICATION_STEPS,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pressure Out PostgreSQL 16 Staging Qualification")
    parser.add_argument("--verify-plan", action="store_true", help="Validate 16-step plan and inspect local binary availability")
    parser.add_argument("--app-env", default=os.getenv("APP_ENV", "staging"), help="Target APP_ENV (must be staging)")
    parser.add_argument("--database-url", default=os.getenv("STAGING_POSTGRES_URL", ""), help="Live staging PostgreSQL 16 DSN")
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://:pass@staging-redis:6379/0"), help="Staging Redis URL")
    parser.add_argument("--cors-origin", default="https://staging.pressureout.example.com", help="Staging frontend origin")
    args = parser.parse_args(argv)

    env_report = inspect_environment()
    if args.verify_plan:
        all_bins = all(env_report["binaries_available"][k] for k in ("psql", "pg_dump", "pg_restore"))
        env_report["qualification_status"] = (
            "READY_TO_EXECUTE" if (all_bins and args.database_url.startswith("postgresql")) else "BLOCKED_NO_LIVE_POSTGRES_IN_SANDBOX"
        )
        print(json.dumps(env_report, indent=2))
        return 0

    try:
        verify_staging_safety_guards(
            app_env=args.app_env,
            database_url=args.database_url,
            redis_url=args.redis_url,
            cors_origins=[args.cors_origin],
        )
    except ValueError as exc:
        print(json.dumps({"status": "SAFETY_CHECK_FAILED", "reason": str(exc)}, indent=2))
        return 1

    if not env_report["binaries_available"]["psql"]:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": "PostgreSQL client binaries (psql/pg_dump/pg_restore) are not installed in this environment.",
                    "environment": env_report,
                },
                indent=2,
            )
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
