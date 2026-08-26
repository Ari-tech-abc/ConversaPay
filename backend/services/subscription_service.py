"""Authoritative subscription state transitions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import logging

from supabase import Client, create_client

from backend.config import settings

logger = logging.getLogger(__name__)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
TERMINAL = {"canceled", "unpaid", "incomplete_expired"}


def period_end_iso(value: Any) -> str | None:
    if not value:
        return None
    return datetime.fromtimestamp(int(value), timezone.utc).isoformat()


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
    # Preserve the legacy default for old Stripe objects that predate metadata.
    return "pro"


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
) -> None:
    """Apply Stripe-confirmed state through the service-role Supabase client."""
    subscription = _as_dict(stripe_subscription)
    metadata = _as_dict(subscription.get("metadata"))
    user_id = user_id or metadata.get("user_id")
    if not user_id:
        return

    plan = _resolve_plan_type(plan_type, stripe_subscription)
    provider_status = str(subscription_status or subscription.get("status") or "active").lower()
    expiry = subscription_expires_at or period_end_iso(subscription.get("current_period_end"))
    stripe_subscription_id = stripe_subscription_id or subscription.get("id")
    customer_id = customer_id or subscription.get("customer")
    auto_renew = not cancel_at_period_end

    if provider_status in TERMINAL:
        plan, expiry, auto_renew = "free", None, False
    elif cancel_at_period_end and plan in {"pro", "premium"}:
        provider_status = "pending_cancellation"
    if plan in {"pro", "premium"} and not expiry:
        expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    now = datetime.now(timezone.utc).isoformat()
    payload: dict[str, Any] = {
        "plan_type": plan,
        "subscription_status": provider_status,
        "stripe_customer_id": customer_id,
        "stripe_subscription_id": stripe_subscription_id,
        "subscription_expires_at": expiry if plan != "free" else None,
        "subscription_start_date": now if plan != "free" else None,
        "subscription_end_date": expiry if plan != "free" else None,
        "auto_renew": auto_renew if plan != "free" else False,
        "updated_at": now,
    }
    profile = supabase.table("profiles").update(payload).eq("user_id", user_id).execute()
    if not profile.data:
        raise RuntimeError(f"Profile not found for Stripe user {user_id}")
    supabase.table("businesses").update({"subscription_tier": plan, "subscription_status": provider_status}).eq("owner_id", user_id).execute()
    logger.info("Successfully updated user %s to plan %s with status %s", user_id, plan, provider_status)


def mark_webhook_processed(event_id: str) -> None:
    supabase.table("webhook_events").update({"status": "processed", "processed_at": datetime.now(timezone.utc).isoformat()}).eq("provider", "stripe").eq("event_id", event_id).execute()


def mark_webhook_failed(event_id: str, error: str) -> None:
    supabase.table("webhook_events").update({"status": "failed", "last_error": error[:1000]}).eq("provider", "stripe").eq("event_id", event_id).execute()
