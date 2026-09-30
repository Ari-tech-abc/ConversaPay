"""Pure billing-state helpers used by reconciliation jobs and webhook handlers."""
from __future__ import annotations
from datetime import datetime, timezone

ACTIVE_STATUSES = {'active', 'trialing', 'past_due', 'pending_cancellation'}
TERMINAL_STATUSES = {'canceled', 'unpaid', 'incomplete_expired'}


def normalize_provider_status(status: str | None) -> str:
    return str(status or 'unknown').strip().lower()


def effective_plan(plan_type: str | None, provider_status: str | None, expires_at: datetime | None) -> str:
    plan = str(plan_type or 'free').lower()
    status = normalize_provider_status(provider_status)
    if plan == 'free' or status in TERMINAL_STATUSES:
        return 'free'
    if expires_at is None:
        return 'free'
    expires_at = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= datetime.now(timezone.utc):
        return 'free'
    return plan if plan in {'pro', 'premium'} and status in ACTIVE_STATUSES else 'free'


def should_retry_invoice(attempt_number: int, next_attempt_at: datetime | None) -> bool:
    if attempt_number >= 4:
        return False
    return next_attempt_at is None or next_attempt_at <= datetime.now(timezone.utc)


def active_plan_from_row(row: dict) -> str:
    plan = str(row.get('plan_type') or 'free').strip().lower()
    plan = {'professional':'pro','pro_monthly':'pro','premium_monthly':'premium','paid':'pro'}.get(plan, plan)
    raw = row.get('subscription_expires_at') or row.get('subscription_end_date')
    try:
        expiry = datetime.fromisoformat(str(raw).replace('Z', '+00:00')) if raw else None
    except (ValueError, TypeError):
        return 'free'
    return effective_plan(plan, row.get('subscription_status'), expiry)
