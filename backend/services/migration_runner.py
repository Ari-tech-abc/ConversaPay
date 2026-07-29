"""Apply repository SQL migrations safely under a database advisory lock."""
from __future__ import annotations
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
import asyncpg
from backend.config import settings
logger=logging.getLogger(__name__)
LOCK_KEY=7_214_026
_migration_status="pending"

@dataclass(frozen=True)
class Migration:
    name:str
    sql:str
    checksum:str

def get_migration_status()->str:
    return _migration_status

def _set_migration_status(value:str)->None:
    global _migration_status
    _migration_status=value

def discover_migrations(directory:Path|None=None)->list[Migration]:
    root=directory or settings.migrations_dir
    bootstrap=settings.base_dir/"database"/"full_schema_bootstrap.sql"
    paths=[bootstrap] if bootstrap.exists() else []
    if root.exists(): paths.extend(sorted(root.glob("*.sql")))
    result=[]
    for path in paths:
        sql=path.read_text(encoding="utf-8")
        result.append(Migration(path.name,sql,hashlib.sha256(sql.encode()).hexdigest()))
    return result

async def apply_migrations()->int:
    _set_migration_status("in_progress")
    try:
        if not settings.MIGRATIONS_AUTO_APPLY or not settings.DATABASE_URL:
            logger.warning("Database migrations skipped: configuration is incomplete")
            _set_migration_status("skipped")
            return 0
        migrations=discover_migrations()
        if not migrations:
            logger.warning("No database migrations found")
            _set_migration_status("completed")
            return 0
        connection=await asyncpg.connect(settings.DATABASE_URL)
        try:
            async with connection.transaction():
                await connection.execute("select pg_advisory_xact_lock($1)",LOCK_KEY)
                await connection.execute("create table if not exists public.schema_migrations (name text primary key, checksum text not null, applied_at timestamptz not null default now())")
                applied={row["name"]:row["checksum"] for row in await connection.fetch("select name, checksum from public.schema_migrations")}
                count=0
                for migration in migrations:
                    previous=applied.get(migration.name)
                    if previous==migration.checksum: continue
                    if previous and previous!=migration.checksum: raise RuntimeError(f"Migration checksum mismatch: {migration.name}")
                    await connection.execute(migration.sql)
                    await connection.execute("insert into public.schema_migrations(name, checksum) values($1, $2)",migration.name,migration.checksum)
                    count+=1
                _set_migration_status("completed")
                return count
        finally: await connection.close()
    except Exception:
        _set_migration_status("failed")
        raise
