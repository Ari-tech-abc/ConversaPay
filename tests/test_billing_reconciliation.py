from datetime import datetime, timedelta, timezone
from backend.services.billing_reconciliation import effective_plan, should_retry_invoice


def test_terminal_provider_state_downgrades_plan():
    assert effective_plan('pro', 'canceled', None) == 'free'


def test_expired_paid_plan_is_free():
    expired = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert effective_plan('premium', 'active', expired) == 'free'


def test_dunning_stops_after_four_attempts():
    assert not should_retry_invoice(4, None)
