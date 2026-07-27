from pathlib import Path


def test_correlation_middleware_and_safe_sentry_bootstrap_exist():
    assert Path('backend/middleware/correlation.py').exists()
    text = Path('backend/services/observability.py').read_text()
    assert 'send_default_pii=False' in text
