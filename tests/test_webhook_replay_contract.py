from pathlib import Path


def test_replay_protection_has_unique_provider_event_key():
    migration_files = list(Path('database/migrations').glob('*.sql'))
    text = '\n'.join(path.read_text() for path in migration_files).lower()
    assert 'webhook_events' in text
    assert 'unique (provider, event_id)' in text or 'unique(provider, event_id)' in text
