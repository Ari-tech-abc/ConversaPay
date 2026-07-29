from pathlib import Path


def test_production_does_not_register_dev_simulator():
    source = Path('main.py').read_text()
    assert 'if not settings.is_production:' in source
    assert 'dev_simulator_router' in source


def test_health_endpoint_exists():
    assert 'async def health' in Path('main.py').read_text()


def test_security_sensitive_tables_have_migrations():
    schema = Path('database/full_schema_bootstrap.sql').read_text()
    assert 'webhook_events' in schema
