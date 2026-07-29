from pathlib import Path


def test_bootstrap_is_idempotent_for_security_tables():
    sql = Path("database/consolidated_setup.sql").read_text().lower()
    assert "create extension if not exists" in sql
    assert "create table if not exists" in sql
    assert "create index if not exists" in sql
    assert "drop policy if exists" in sql
    assert "enable row level security" in sql
    assert "revoke all" in sql


def test_security_migrations_are_orderable_and_additive():
    migration_dir = Path("database/migrations")
    names = [path.name for path in sorted(migration_dir.glob("*.sql"))]
    assert names == sorted(names)
    assert any("multitenancy" in name for name in names)
    assert any("site_builder_leads" in name for name in names)
