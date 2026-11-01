"""Database connectivity, session cleanup, and Alembic migration round-trip tests."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.core.unicode import normalize_unicode_nfc
from app.database.session import DatabaseManager

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent
    / "alembic"
    / "versions"
    / "0001_phase2_foundation_extensions.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("migration_0001", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DatabaseAndMigrationTests(unittest.IsolatedAsyncioTestCase):
    """Verifies async session management, UTF-8 persistence, and migration round-trips."""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_file = os.path.join(self.temp_dir.name, "test_disposable.sqlite3")
        self.settings = Settings(
            app_env="test",
            database_url=f"sqlite:///{self.db_file}",
            db_pool_size=3,
            db_max_overflow=5,
        )
        self.db_manager = DatabaseManager(settings=self.settings)

    async def asyncTearDown(self) -> None:
        await self.db_manager.dispose()
        self.temp_dir.cleanup()

    async def test_database_connectivity_and_session_cleanup(self) -> None:
        self.assertEqual(self.db_manager.active_sessions_count, 0)
        is_connected = await self.db_manager.verify_connectivity()
        self.assertTrue(is_connected)
        self.assertEqual(self.db_manager.active_sessions_count, 0)
        self.assertEqual(
            self.db_manager.pool_configuration,
            {"pool_size": 3, "max_overflow": 5, "pool_timeout_seconds": 30},
        )

    async def test_transaction_rollback_on_error_and_utf8_roundtrip(self) -> None:
        async with self.db_manager.session_scope() as session:
            await session.execute(
                "CREATE TABLE unicode_probe (id INTEGER PRIMARY KEY, sample TEXT NOT NULL)"
            )
            await session.execute(
                "INSERT INTO unicode_probe (sample) VALUES (?)",
                (normalize_unicode_nfc("മലയാളം • हिन्दी • தமிழ் • 🚀"),),
            )

        with self.assertRaises(ValueError):
            async with self.db_manager.session_scope() as session:
                await session.execute(
                    "INSERT INTO unicode_probe (sample) VALUES (?)", ("should_rollback",)
                )
                raise ValueError("Simulated mid-transaction failure")

        self.assertEqual(self.db_manager.active_sessions_count, 0)

        async with self.db_manager.session_scope() as session:
            rows = await session.execute("SELECT sample FROM unicode_probe")
            self.assertEqual(rows, [("മലയാളം • हिन्दी • தமிழ் • 🚀",)])

    async def test_migration_0001_round_trip_and_preexisting_extension_protection(self) -> None:
        """Executes the required 5-step migration verification against a disposable DB:
        1. Upgrade to latest revision (`0001_phase2_foundation`).
        2. Verify expected migration state, required extensions, and zero business tables.
        3. Downgrade to baseline.
        4. Upgrade again.
        5. Verify idempotency and confirm pre-existing extensions are never removed on downgrade.
        """
        migration = _load_migration_module()
        self.assertEqual(migration.revision, "0001_phase2_foundation")
        self.assertIsNone(migration.down_revision)
        self.assertEqual(
            set(migration.REQUIRED_EXTENSIONS),
            {"pgcrypto", "citext", "ltree", "pg_trgm"},
        )

        conn = sqlite3.connect(self.db_file)
        try:
            conn.execute(
                "CREATE TABLE _alembic_preexisting_extensions (extension_name VARCHAR(64) PRIMARY KEY)"
            )
            conn.execute(
                "INSERT INTO _alembic_preexisting_extensions (extension_name) VALUES ('pgcrypto')"
            )
            conn.commit()

            # Step 1: Upgrade to 0001_phase2_foundation
            migration.upgrade(conn)
            conn.commit()

            # Step 2: Verify newly created extensions are tracked, pre-existing 'pgcrypto' is NOT claimed,
            # and no premature business tables (`users`, `posts`, etc.) were created.
            owned = [
                r[0]
                for r in conn.execute(
                    "SELECT extension_name FROM _alembic_extension_ownership ORDER BY extension_name"
                ).fetchall()
            ]
            self.assertEqual(owned, ["citext", "ltree", "pg_trgm"])

            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            for premature_table in ("users", "posts", "comments", "communities", "meme_jobs"):
                self.assertNotIn(premature_table, tables)

            # Verify repeated upgrade is idempotent
            migration.upgrade(conn)
            conn.commit()

            # Step 3: Downgrade to baseline
            migration.downgrade(conn)
            conn.commit()

            preexisting_after_down = [
                r[0]
                for r in conn.execute(
                    "SELECT extension_name FROM _alembic_preexisting_extensions"
                ).fetchall()
            ]
            self.assertEqual(preexisting_after_down, ["pgcrypto"])

            # Step 4 & 5: Upgrade again and confirm consistent state
            migration.upgrade(conn)
            conn.commit()
            owned_second = [
                r[0]
                for r in conn.execute(
                    "SELECT extension_name FROM _alembic_extension_ownership ORDER BY extension_name"
                ).fetchall()
            ]
            self.assertEqual(owned_second, ["citext", "ltree", "pg_trgm"])
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
