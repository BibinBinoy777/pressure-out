"""Phase 2 foundation: PostgreSQL extensions with safe ownership tracking.

Revision ID: 0001_phase2_foundation
Revises: None
Create Date: 2026-10-29 00:00:00
"""
from __future__ import annotations

from typing import Any, Sequence, Union

# Revision identifiers used by Alembic and the Phase 2 migration runner.
revision: str = "0001_phase2_foundation"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REQUIRED_EXTENSIONS: tuple[str, ...] = (
    "pgcrypto",
    "citext",
    "ltree",
    "pg_trgm",
)

OWNERSHIP_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS _alembic_extension_ownership (
    extension_name VARCHAR(64) PRIMARY KEY,
    created_by_revision VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);
"""


def _get_connection(bind_or_op: Any = None) -> Any:
    """Resolve an active SQL connection from either Alembic `op` or a direct connection."""
    if bind_or_op is not None:
        return bind_or_op
    from alembic import op  # type: ignore[import-not-found]

    return op.get_bind()


def _is_postgresql(conn: Any) -> bool:
    """Detect whether the underlying connection dialect is PostgreSQL."""
    dialect_name = getattr(getattr(conn, "dialect", None), "name", None)
    if dialect_name:
        return str(dialect_name).startswith("postgresql")
    return False


def _exec_sql(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[Any]:
    """Execute a SQL statement across either SQLAlchemy Connection or DB-API connection."""
    if hasattr(conn, "exec_driver_sql"):
        result = conn.exec_driver_sql(sql, params)
        if result.returns_rows:
            return list(result.fetchall())
        return []
    cursor = conn.cursor()
    cursor.execute(sql, params)
    try:
        rows = cursor.fetchall()
    except Exception:
        rows = []
    return list(rows)


def upgrade(bind: Any = None) -> None:
    """Establish required PostgreSQL extensions while recording which ones were newly created.

    Phase 2 explicitly avoids creating premature business tables. Only the
    baseline database extensions (`pgcrypto`, `citext`, `ltree`, `pg_trgm`)
    and their migration ownership ledger are created here.
    """
    conn = _get_connection(bind)
    _exec_sql(conn, OWNERSHIP_TABLE_DDL)

    is_pg = _is_postgresql(conn)

    for ext_name in REQUIRED_EXTENSIONS:
        if is_pg:
            existing = _exec_sql(
                conn,
                "SELECT 1 FROM pg_extension WHERE extname = %s",
                (ext_name,),
            )
            if not existing:
                _exec_sql(conn, f'CREATE EXTENSION IF NOT EXISTS "{ext_name}"')
                _exec_sql(
                    conn,
                    """
                    INSERT INTO _alembic_extension_ownership (extension_name, created_by_revision)
                    VALUES (%s, %s)
                    ON CONFLICT (extension_name) DO NOTHING
                    """,
                    (ext_name, revision),
                )
        else:
            # Disposable SQLite test harness tracking for offline migration round-trip verification
            existing = _exec_sql(
                conn,
                "SELECT 1 FROM _alembic_preexisting_extensions WHERE extension_name = ?",
                (ext_name,),
            )
            if not existing:
                _exec_sql(
                    conn,
                    """
                    INSERT OR IGNORE INTO _alembic_extension_ownership
                        (extension_name, created_by_revision)
                    VALUES (?, ?)
                    """,
                    (ext_name, revision),
                )


def downgrade(bind: Any = None) -> None:
    """Downgrade baseline extensions safely without dropping pre-existing shared extensions."""
    conn = _get_connection(bind)
    is_pg = _is_postgresql(conn)

    if is_pg:
        owned_rows = _exec_sql(
            conn,
            """
            SELECT extension_name
            FROM _alembic_extension_ownership
            WHERE created_by_revision = %s
            """,
            (revision,),
        )
        for (ext_name,) in owned_rows:
            if ext_name in REQUIRED_EXTENSIONS:
                _exec_sql(conn, f'DROP EXTENSION IF EXISTS "{ext_name}"')
        _exec_sql(conn, "DROP TABLE IF EXISTS _alembic_extension_ownership")
    else:
        _exec_sql(
            conn,
            "DELETE FROM _alembic_extension_ownership WHERE created_by_revision = ?",
            (revision,),
        )
        _exec_sql(conn, "DROP TABLE IF EXISTS _alembic_extension_ownership")
