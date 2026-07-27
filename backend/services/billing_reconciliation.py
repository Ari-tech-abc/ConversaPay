"""Pure billing-state helpers used by reconciliation jobs and webhook handlers."""
from __future__ import annotations
from datetime import datetime, timezone

ACTIVE_STATUSES = {'active', 'trialing', 'past_due'}
TERMINAL_STATUSES = {'canceled', 'unpaid', 'incomplete_expired'}


def normalize_provider_status(status: str | None) -> str:
    return str(status or 'unknown').strip().lower()


def effective_plan(plan_type: str | None, provider_status: str | None, expires_at: datetime | None) -> str:
    plan = str(plan_type or 'free').lower()
    status = normalize_provider_status(provider_status)
    if plan == 'free' or status in TERMINAL_STATUSES:
        return 'free'
    if expires_at and expires_at <= datetime.now(timezone.utc):
        return 'free'
    return plan if status in ACTIVE_STATUSES else 'free'


def should_retry_invoice(attempt_number: int, next_attempt_at: datetime | None) -> bool:
    if attempt_number >= 4:
        return False
    return next_attempt_at is None or next_attempt_at <= datetime.now(timezone.utc)
