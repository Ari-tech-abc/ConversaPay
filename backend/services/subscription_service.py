"""Authoritative subscription state transitions, callable only by webhooks."""
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


def apply_subscription_state(*, user_id: str | None, plan_type: str | None, subscription_status: str | None,
                              subscription_expires_at: str | None, customer_id: str | None = None,
                              cancel_at_period_end: bool = False, stripe_subscription_id: str | None = None) -> None:
    """Apply a provider-confirmed state. This is intentionally not imported by payments.py."""
    if not user_id:
        return
    plan = (plan_type or "pro").lower()
    provider_status = (subscription_status or "active").lower()
    expiry = subscription_expires_at
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
        "subscription_start_date": now if plan != "free" else None,
        "subscription_end_date": expiry if plan != "free" else None,
        "subscription_expires_at": expiry if plan != "free" else None,
        "auto_renew": auto_renew if plan != "free" else False,
        "updated_at": now,
    }
    if stripe_subscription_id:
        payload["stripe_subscription_id"] = stripe_subscription_id
    if customer_id:
        payload["stripe_customer_id"] = customer_id
    profile = supabase.table("profiles").update(payload).eq("user_id", user_id).execute()
    if not profile.data:
        raise RuntimeError(f"Profile not found for Stripe user {user_id}")
    supabase.table("businesses").update({"subscription_tier": plan, "subscription_status": provider_status}).eq("owner_id", user_id).execute()


def mark_webhook_processed(event_id: str) -> None:
    supabase.table("webhook_events").update({"status": "processed", "processed_at": datetime.now(timezone.utc).isoformat()}).eq("provider", "stripe").eq("event_id", event_id).execute()


def mark_webhook_failed(event_id: str, error: str) -> None:
    supabase.table("webhook_events").update({"status": "failed", "last_error": error[:1000]}).eq("provider", "stripe").eq("event_id", event_id).execute()
