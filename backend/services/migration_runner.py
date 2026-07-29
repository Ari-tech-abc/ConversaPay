"""Ordered, atomic SQL migration runner for the repository's Supabase schema."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import asyncpg

from backend.config import settings

logger = logging.getLogger(__name__)
LOCK_KEY = 7_214_026


@dataclass(frozen=True)
class Migration:
    name: str
    sql: str
    checksum: str


def discover_migrations(directory: Path | None = None) -> list[Migration]:
    root = directory or settings.migrations_dir
    files = sorted(root.glob("*.sql"), key=lambda path: path.name)
    migrations: list[Migration] = []
    for path in files:
        sql = path.read_text(encoding="utf-8")
        migrations.append(Migration(path.name, sql, hashlib.sha256(sql.encode()).hexdigest()))
    return migrations


async def apply_migrations() -> int:
    """Apply all pending migrations in one transaction under a DB advisory lock.

    If DATABASE_URL is absent, no connection is attempted. Production should set
    it when MIGRATIONS_AUTO_APPLY is enabled; this keeps local UI-only runs safe.
    """
    if not settings.MIGRATIONS_AUTO_APPLY or not settings.DATABASE_URL:
        logger.warning("Database migrations skipped: DATABASE_URL or MIGRATIONS_AUTO_APPLY is not configured")
        return 0

    migrations = discover_migrations()
    if not migrations:
        return 0

    connection = await asyncpg.connect(settings.DATABASE_URL)
    try:
        async with connection.transaction():
            await connection.execute("select pg_advisory_xact_lock($1)", LOCK_KEY)
            await connection.execute("""
                create table if not exists public.schema_migrations (
                    name text primary key,
                    checksum text not null,
                    applied_at timestamptz not null default now()
                )
            """)
            applied = {row["name"]: row["checksum"] for row in await connection.fetch("select name, checksum from public.schema_migrations")}
            count = 0
            for migration in migrations:
                previous = applied.get(migration.name)
                if previous == migration.checksum:
                    continue
                if previous and previous != migration.checksum:
                    raise RuntimeError(f"Migration checksum mismatch: {migration.name}")
                await connection.execute(migration.sql)
                await connection.execute("insert into public.schema_migrations(name, checksum) values($1, $2)", migration.name, migration.checksum)
                count += 1
            return count
    finally:
        await connection.close()
