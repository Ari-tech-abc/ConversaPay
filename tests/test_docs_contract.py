from pathlib import Path


def test_customer_docs_and_onboarding_exist():
    assert Path('docs/API.md').exists()
    assert Path('docs/ONBOARDING.md').exists()
    assert 'sandbox' in Path('docs/ONBOARDING.md').read_text().lower()
