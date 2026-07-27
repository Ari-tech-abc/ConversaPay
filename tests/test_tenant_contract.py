from pathlib import Path


def test_rls_migration_is_present_and_fail_closed():
    migration = Path('database/migrations/20260728_multitenancy_rls.sql').read_text()
    assert 'enable row level security' in migration.lower()
    assert 'user_owns_business' in migration
    assert 'revoke all' in migration.lower()
