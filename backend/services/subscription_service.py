"""Authoritative subscription state transitions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import logging
from uuid import UUID
from backend.services.subscription_checkout import billing_rpc
from backend.services.subscription_catalog import PLANS, paid_subscription_period

from supabase import Client, create_client

from backend.config import settings
from backend.services.billing_reconciliation import ACTIVE_STATUSES

logger = logging.getLogger(__name__)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
TERMINAL = {"canceled", "unpaid", "incomplete_expired"}


def period_end_iso(value: Any) -> str | None:
    if not value:
        return None
    return datetime.fromtimestamp(int(value), timezone.utc).isoformat()


def subscription_period_end(subscription: dict) -> int | None:
    direct = subscription.get('current_period_end')
    if direct:
        return direct
    items = (subscription.get('items') or {}).get('data') or []
    periods = [item.get('current_period_end') for item in items if item.get('current_period_end')]
    return min(periods) if periods else None


def subscription_period_start(subscription: dict) -> int | None:
    direct = subscription.get('current_period_start') or subscription.get('start_date')
    if direct:
        return direct
    periods = [item.get('current_period_start') for item in (subscription.get('items') or {}).get('data', []) if item.get('current_period_start')]
    return max(periods) if periods else None


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict_recursive"):
        return value.to_dict_recursive()
    if hasattr(value, "to_dict"):
        return value.to_dict()
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def normalize_plan_type(value: Any) -> str | None:
    """Normalize Stripe/catalog plan labels to the two profile plan values."""
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return None
    if normalized == "free":
        return "free"
    # Check premium first because its label contains the pro substring.
    if "premium" in normalized:
        return "premium"
    if normalized == "pro" or normalized.startswith("pro_") or "_pro_" in f"_{normalized}_" or "professional" in normalized:
        return "pro"
    return None


def _subscription_plan_candidates(subscription: Any) -> list[Any]:
    sub = _as_dict(subscription)
    candidates: list[Any] = []
    metadata = _as_dict(sub.get("metadata"))
    candidates.extend([metadata.get("plan_type"), metadata.get("plan"), sub.get("plan_type"), sub.get("plan")])
    items = _as_dict(sub.get("items"))
    for item in items.get("data") or []:
        item_dict = _as_dict(item)
        item_metadata = _as_dict(item_dict.get("metadata"))
        candidates.extend([item_metadata.get("plan_type"), item_metadata.get("plan")])
        price = _as_dict(item_dict.get("price"))
        price_metadata = _as_dict(price.get("metadata"))
        candidates.extend([
            price_metadata.get("plan_type"),
            price_metadata.get("plan"),
            price.get("lookup_key"),
            price.get("nickname"),
            price.get("id"),
        ])
        product = _as_dict(price.get("product"))
        product_metadata = _as_dict(product.get("metadata"))
        candidates.extend([product_metadata.get("plan_type"), product_metadata.get("plan"), product.get("name")])
    return candidates


def _resolve_plan_type(plan_type: Any, stripe_subscription: Any) -> str:
    for candidate in [plan_type, *_subscription_plan_candidates(stripe_subscription)]:
        normalized = normalize_plan_type(candidate)
        if normalized in {"pro", "premium", "free"}:
            return normalized
    # Missing plan identity never grants a paid tier.
    return "free"


def apply_subscription_state(
    *,
    user_id: str | None,
    plan_type: str | None,
    subscription_status: str | None,
    subscription_expires_at: str | None,
    customer_id: str | None = None,
    cancel_at_period_end: bool = False,
    stripe_subscription_id: str | None = None,
    stripe_subscription: Any | None = None,
    payment_confirmed: bool = False,
    db=None,
) -> bool:
    """Apply Stripe-confirmed state through the service-role Supabase client."""
    subscription = _as_dict(stripe_subscription)
    metadata = _as_dict(subscription.get("metadata"))
    user_id = user_id or metadata.get("user_id")
    if not user_id:
        raise ValueError("Subscription owner could not be resolved")

    plan = _resolve_plan_type(plan_type, stripe_subscription)
    provider_status = str(subscription_status or subscription.get("status") or "unknown").lower()
    expiry = subscription_expires_at or period_end_iso(subscription_period_end(subscription))
    stripe_subscription_id = stripe_subscription_id or subscription.get("id")
    customer_id = customer_id or subscription.get("customer")

    if provider_status not in ACTIVE_STATUSES:
        plan = "free"
    elif cancel_at_period_end and plan in {"pro", "premium"}:
        provider_status = "pending_cancellation"
    if provider_status in ACTIVE_STATUSES and plan not in {"pro", "premium"}:
        raise ValueError("Subscription plan could not be verified")

    if not stripe_subscription_id:
        raise ValueError("A verified subscription ID is required")
    attempt_id = metadata.get("checkout_attempt_id")
    if attempt_id:
        attempt_id = str(UUID(attempt_id))
    start = period_end_iso(subscription_period_start(subscription))
    if payment_confirmed:
        paid_plan = PLANS.get(_resolve_plan_type(plan_type, stripe_subscription))
        paid_period = paid_subscription_period(subscription, paid_plan) if paid_plan else None
        if paid_period is None:
            payment_confirmed = False
        else:
            start = period_end_iso(paid_period[0])
            paid_end = period_end_iso(paid_period[1])
            expiry = min(expiry, paid_end) if expiry else paid_end
    result = billing_rpc(db if db is not None else supabase, "apply_subscription_snapshot", {
        "p_user_id": user_id, "p_provider": "stripe", "p_subscription_id": stripe_subscription_id,
        "p_customer_id": customer_id, "p_plan": plan, "p_status": provider_status,
        "p_period_start": start, "p_period_end": expiry,
        "p_cancel_at_period_end": cancel_at_period_end, "p_attempt_id": attempt_id,
        "p_payment_confirmed": payment_confirmed,
    })
    return result.get("applied") is True



def mark_webhook_processed(event_id: str) -> None:
    supabase.rpc("mark_webhook_processed", {"p_provider": "stripe", "p_event_id": event_id}).execute()


def mark_webhook_failed(event_id: str, error: str) -> None:
    supabase.rpc("mark_webhook_failed", {"p_provider": "stripe", "p_event_id": event_id, "p_error_message": error[:2000]}).execute()
