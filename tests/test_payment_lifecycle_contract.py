from pathlib import Path


def test_confirm_session_is_read_only():
    source = Path("backend/routers/payments.py").read_text()
    function = source.split("async def confirm_checkout_session", 1)[1].split("@router.get(\"/profile\"", 1)[0]
    assert ".update(" not in function
    assert ".insert(" not in function
    assert "subscription_state_source" in function


def test_subscription_writes_are_webhook_owned():
    payments = Path("backend/routers/payments.py").read_text()
    webhook = Path("backend/routers/stripe_webhook.py").read_text()
    assert "apply_subscription_state" not in payments
    assert "subscription_service" in webhook
    assert "apply_subscription_state" in webhook


def test_atomic_claim_contract_exists():
    migration = Path("database/migrations/20260729_atomic_webhook_claim.sql").read_text().lower()
    assert "on conflict" in migration
    assert "claim_webhook_event" in migration
    assert "security definer" in migration
