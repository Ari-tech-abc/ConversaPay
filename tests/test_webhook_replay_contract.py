from pathlib import Path


def test_replay_protection_has_unique_provider_event_key():
    text = Path('database/migrations/20260728_security_webhook_hardening.sql').read_text().lower()
    assert 'unique(provider, event_id)' in text
