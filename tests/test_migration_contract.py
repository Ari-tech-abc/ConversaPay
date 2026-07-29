from pathlib import Path

from backend.services.migration_runner import discover_migrations


def test_migrations_are_deterministically_ordered():
    migrations = discover_migrations()
    names = [migration.name for migration in migrations]
    assert names == sorted(names)
    assert names == [path.name for path in sorted(Path("database/migrations").glob("*.sql"))]


def test_migrations_are_idempotent_by_contract():
    for migration in discover_migrations():
        sql = migration.sql.lower()
        assert "if not exists" in sql or "create or replace function" in sql or "drop policy if exists" in sql, migration.name


def test_runner_uses_transaction_and_advisory_lock():
    source = Path("backend/services/migration_runner.py").read_text()
    assert "connection.transaction" in source
    assert "pg_advisory_xact_lock" in source
    assert "schema_migrations" in source
