"""Alembic asynchronous migration environment for Pressure Out."""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from app.config import get_settings
from app.database.base import Base

try:
    from alembic import context
    from sqlalchemy import pool
    from sqlalchemy.engine import Connection
    from sqlalchemy.ext.asyncio import async_engine_from_config
except ImportError:  # pragma: no cover
    context = None  # type: ignore[assignment]


def get_migration_database_url() -> str:
    """Return the configured database URL for migrations."""
    settings = get_settings()
    return settings.database_url


def do_run_migrations(connection: "Connection") -> None:
    """Configure context and run migrations inside a synchronous connection callback."""
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async SQLAlchemy engine and run Alembic migrations."""
    configuration = context.config.get_section(context.config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_migration_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_migration_database_url()
    context.configure(
        url=url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context is not None:  # pragma: no cover
    if context.config.config_file_name is not None:
        fileConfig(context.config.config_file_name)

    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
