from pathlib import Path


def test_webhook_claim_and_completion_are_explicit():
    source = Path("backend/routers/stripe_webhook.py").read_text()
    assert "claim_webhook_event" in source
    assert "mark_webhook_processed" in source
    assert "mark_webhook_failed" in source
    assert "stripe-signature" in source
