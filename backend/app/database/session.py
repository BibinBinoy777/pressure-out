"""Asynchronous database engine, request-scoped session management, and cleanup."""
from __future__ import annotations

import importlib.util
import sqlite3
import threading
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from app.config import Settings, get_settings

try:
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import (
        AsyncEngine,
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    HAS_SQLALCHEMY = True
except ImportError:  # pragma: no cover
    HAS_SQLALCHEMY = False
    AsyncEngine = Any  # type: ignore[assignment,misc]
    AsyncSession = Any  # type: ignore[assignment,misc]


def _load_migration(filename: str) -> Any:
    mig_path = (
        Path(__file__).resolve().parent.parent.parent
        / "alembic"
        / "versions"
        / filename
    )
    spec = importlib.util.spec_from_file_location(filename.replace(".py", ""), mig_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TransactionalSessionAdapter:
    """Thin async-compatible wrapper around a DB-API connection with explicit cleanup tracking."""

    def __init__(self, raw_conn: sqlite3.Connection, *, close_underlying: bool = True) -> None:
        self._conn = raw_conn
        self._close_underlying = close_underlying
        self.is_closed: bool = False
        self.in_transaction: bool = False

    async def execute(self, statement: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
        if self.is_closed:
            raise RuntimeError("Cannot execute on a closed database session.")
        cursor = self._conn.cursor()
        cursor.execute(statement, params)
        self.in_transaction = self._conn.in_transaction
        try:
            return list(cursor.fetchall())
        except Exception:
            return []

    async def commit(self) -> None:
        if self.is_closed:
            raise RuntimeError("Cannot commit a closed database session.")
        if self._conn.in_transaction:
            self._conn.commit()
        self.in_transaction = self._conn.in_transaction

    async def rollback(self) -> None:
        if not self.is_closed:
            self._conn.rollback()
            self.in_transaction = self._conn.in_transaction

    async def close(self) -> None:
        if not self.is_closed:
            if self._conn.in_transaction:
                self._conn.rollback()
            if self._close_underlying:
                self._conn.close()
            self.is_closed = True
            self.in_transaction = False


class DatabaseManager:
    """Manages engine configuration, session creation, transactions, and deterministic cleanup."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self._engine: Optional[Any] = None
        self._session_factory: Optional[Any] = None
        self._shared_memory_conn: Optional[sqlite3.Connection] = None
        self._sqlite_lock = threading.RLock()
        self.active_sessions_count: int = 0

        if HAS_SQLALCHEMY and self.settings.database_url.startswith("postgresql"):
            self._engine = create_async_engine(
                self.settings.database_url,
                pool_size=self.settings.db_pool_size,
                max_overflow=self.settings.db_max_overflow,
                pool_timeout=self.settings.db_pool_timeout_seconds,
                pool_pre_ping=True,
                echo=False,
            )
            self._session_factory = async_sessionmaker(
                bind=self._engine,
                expire_on_commit=False,
                autoflush=False,
                autocommit=False,
            )
        else:
            path_str = self._resolve_sqlite_path()
            if path_str == ":memory:":
                self._shared_memory_conn = sqlite3.connect(
                    ":memory:", check_same_thread=False
                )
                self._shared_memory_conn.execute("PRAGMA encoding = 'UTF-8'")
                self._shared_memory_conn.execute("PRAGMA foreign_keys = ON")

    @property
    def pool_configuration(self) -> dict[str, int]:
        """Return configured connection pool bounds."""
        return {
            "pool_size": self.settings.db_pool_size,
            "max_overflow": self.settings.db_max_overflow,
            "pool_timeout_seconds": self.settings.db_pool_timeout_seconds,
        }

    def _resolve_sqlite_path(self) -> str:
        url = self.settings.database_url
        if url.startswith("sqlite:///"):
            return url[len("sqlite:///") :]
        return ":memory:"

    def apply_migrations_sync(self) -> None:
        """Apply Phase 2 through Phase 7 migrations idempotently to the local/test database."""
        mig2 = _load_migration("0002_phase3_identity_and_privacy.py")
        mig3 = _load_migration("0003_phase4_core_social_posting.py")
        mig4 = _load_migration("0004_phase5_communities.py")
        mig5 = _load_migration("0005_phase6_comments_engagement_notifications.py")
        mig6 = _load_migration("0006_phase7_feed_search_discovery.py")
        mig7 = _load_migration("0007_phase8_ai_meme_studio.py")
        mig8 = _load_migration("0008_phase9_trust_safety_moderation.py")
        mig9 = _load_migration("0009_phase10_multilingual_translations.py")
        mig10 = _load_migration("0010_phase11_workplace_experiences.py")
        if self._shared_memory_conn is not None:
            mig2.upgrade(self._shared_memory_conn)
            mig3.upgrade(self._shared_memory_conn)
            mig4.upgrade(self._shared_memory_conn)
            mig5.upgrade(self._shared_memory_conn)
            mig6.upgrade(self._shared_memory_conn)
            mig7.upgrade(self._shared_memory_conn)
            mig8.upgrade(self._shared_memory_conn)
            mig9.upgrade(self._shared_memory_conn)
            mig10.upgrade(self._shared_memory_conn)
            self._shared_memory_conn.commit()
        else:
            path_str = self._resolve_sqlite_path()
            conn = sqlite3.connect(path_str, check_same_thread=False)
            try:
                conn.execute("PRAGMA encoding = 'UTF-8'")
                conn.execute("PRAGMA foreign_keys = ON")
                mig2.upgrade(conn)
                mig3.upgrade(conn)
                mig4.upgrade(conn)
                mig5.upgrade(conn)
                mig6.upgrade(conn)
                mig7.upgrade(conn)
                mig8.upgrade(conn)
                mig9.upgrade(conn)
                mig10.upgrade(conn)
                conn.commit()
            finally:
                conn.close()

    @asynccontextmanager
    async def session_scope(self) -> AsyncGenerator[Any, None]:
        """Provide a request-scoped database session with guaranteed rollback/close cleanup."""
        self.active_sessions_count += 1
        if self._session_factory is not None:
            session = self._session_factory()
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
                self.active_sessions_count -= 1
        elif self._shared_memory_conn is not None:
            with self._sqlite_lock:
                adapter = TransactionalSessionAdapter(
                    self._shared_memory_conn, close_underlying=False
                )
                try:
                    yield adapter
                    await adapter.commit()
                except Exception:
                    await adapter.rollback()
                    raise
                finally:
                    await adapter.close()
                    self.active_sessions_count -= 1
        else:
            raw_conn = sqlite3.connect(
                self._resolve_sqlite_path(), check_same_thread=False
            )
            raw_conn.execute("PRAGMA encoding = 'UTF-8'")
            raw_conn.execute("PRAGMA foreign_keys = ON")
            adapter = TransactionalSessionAdapter(raw_conn, close_underlying=True)
            try:
                yield adapter
                await adapter.commit()
            except Exception:
                await adapter.rollback()
                raise
            finally:
                await adapter.close()
                self.active_sessions_count -= 1

    async def verify_connectivity(self) -> bool:
        """Execute a lightweight `SELECT 1` probe to validate database connectivity."""
        async with self.session_scope() as session:
            if HAS_SQLALCHEMY and hasattr(session, "execute") and not isinstance(
                session, TransactionalSessionAdapter
            ):
                res = await session.execute(sa_text("SELECT 1"))
                return res.scalar() == 1
            rows = await session.execute("SELECT 1")
            return rows == [(1,)]

    async def dispose(self) -> None:
        """Dispose of underlying engine connection pools cleanly."""
        if self._engine is not None:
            await self._engine.dispose()
        if self._shared_memory_conn is not None:
            self._shared_memory_conn.close()
            self._shared_memory_conn = None


_default_manager: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = DatabaseManager()
    return _default_manager
