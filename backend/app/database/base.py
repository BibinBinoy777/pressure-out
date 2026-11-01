"""Declarative metadata registry for SQLAlchemy 2.x models and Alembic migrations."""
from __future__ import annotations

try:
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        """SQLAlchemy 2.x DeclarativeBase for Pressure Out models."""
        pass

except ImportError:  # pragma: no cover

    class _FallbackMeta:
        tables: dict[str, object] = {}

    class Base:  # type: ignore[no-redef]
        """Fallback declarative placeholder when SQLAlchemy is not installed in the sandbox VM."""
        metadata = _FallbackMeta()
