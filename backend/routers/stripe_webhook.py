"""Stripe webhook with official signature verification and idempotency."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import stripe
from fastapi import APIRouter, HTTPException, Request
from supabase import Client, create_client

from backend.config import settings
from backend.services.stripe_service import StripeServiceError, stripe_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/stripe", tags=["stripe-webhook"])
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)

if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _period_end_iso(timestamp: Any) -> str | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(int(timestamp), timezone.utc).isoformat()


def _claim(event_id: str, event_type: str) -> bool:
    try:
        supabase.table("webhook_events").insert(
            {
                "provider": "stripe",
                "event_id": event_id,
                "status": event_type,
                "received_at": _utc_now_iso(),
            }
        ).execute()
        return True
    except Exception as exc:
        if any(
            marker in str(exc).lower()
            for marker in ("duplicate", "unique", "23505", "conflict", "already exists")
        ):
            return False
        raise


def _update_profile_and_business(
    user_id: str,
    *,
    plan_type: str,
    subscription_expires_at: str | None,
    subscription_status: str,
) -> None:
    now = _utc_now_iso()
    supabase.table("profiles").update(
        {
            "plan_type": plan_type,
            "subscription_expires_at": subscription_expires_at,
            "updated_at": now,
        }
    ).eq("user_id", user_id).execute()

    try:
        supabase.table("businesses").update(
            {
                "subscription_tier": plan_type,
                "subscription_status": subscription_status,
            }
        ).eq("owner_id", user_id).execute()
    except Exception as exc:
        logger.warning(
            "Profile was synced from Stripe but business sync failed for user %s: %s",
            user_id,
            exc,
        )


def _update_order_and_payment(
    order_id: str,
    *,
    order_status: str,
    order_payment_status: str,
    payment_status: str,
    metadata_updates: dict[str, Any] | None = None,
    paid: bool = False,
) -> None:
    now = _utc_now_iso()
    supabase.table("orders").update(
        {
            "status": order_status,
            "payment_status": order_payment_status,
            "updated_at": now,
        }
    ).eq("id", order_id).execute()

    payment_result = (
        supabase.table("payments")
        .select("id, metadata")
        .eq("order_id", order_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not payment_result.data:
        return

    payment_row = payment_result.data[0]
    metadata = dict(payment_row.get("metadata") or {})
    metadata.update(metadata_updates or {})
    update_payload: dict[str, Any] = {
        "status": payment_status,
        "metadata": metadata,
        "updated_at": now,
    }
    if paid:
        update_payload["paid_at"] = now

    supabase.table("payments").update(update_payload).eq("id", payment_row["id"]).execute()


def _subscription_context(subscription_id: str | None) -> dict[str, Any]:
    if not subscription_id:
        return {}
    try:
        subscription = stripe_service.retrieve_subscription(subscription_id)
    except (StripeServiceError, ValueError) as exc:
        logger.warning("Unable to retrieve Stripe subscription %s: %s", subscription_id, exc)
        return {}

    return {
        "metadata": dict(subscription.get("metadata") or {}),
        "status": subscription.get("status"),
        "current_period_end": _period_end_iso(subscription.get("current_period_end")),
    }


def _apply_subscription_state(
    *,
    user_id: str | None,
    plan_type: str | None,
    subscription_status: str | None,
    subscription_expires_at: str | None,
) -> None:
    if not user_id:
        return

    effective_plan = (plan_type or "pro").lower()
    effective_status = subscription_status or "active"
    effective_expiry = subscription_expires_at

    if effective_status in {"canceled", "unpaid", "incomplete_expired"}:
        effective_plan = "free"
        effective_expiry = None

    _update_profile_and_business(
        user_id,
        plan_type=effective_plan,
        subscription_expires_at=effective_expiry,
        subscription_status=effective_status,
    )


@router.post("")
async def stripe_webhook(request: Request) -> dict[str, Any]:
    raw = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature or not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(400, "Missing Stripe signature configuration")

    try:
        event = stripe.Webhook.construct_event(
            raw,
            signature,
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except ValueError as exc:
        raise HTTPException(400, "Invalid Stripe payload") from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(400, "Invalid Stripe signature") from exc

    event_id = str(event["id"])
    event_type = str(event["type"])
    if not _claim(event_id, event_type):
        return {"status": "ok", "processed": False}

    obj = stripe_service.serialize_stripe_object(event["data"]["object"])
    metadata = dict(obj.get("metadata") or {})

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        order_id = metadata.get("order_id")
        if order_id:
            _update_order_and_payment(
                order_id,
                order_status="paid",
                order_payment_status="paid",
                payment_status="succeeded",
                metadata_updates={
                    "provider": "stripe",
                    "session_id": obj.get("id"),
                    "payment_intent": obj.get("payment_intent"),
                    "customer": obj.get("customer"),
                },
                paid=True,
            )

        if obj.get("mode") == "subscription":
            if metadata.get("user_id"):
                _apply_subscription_state(
                    user_id=metadata.get("user_id"),
                    plan_type=metadata.get("plan_type"),
                    subscription_status="active",
                    subscription_expires_at=None,
                )

            subscription_context = _subscription_context(obj.get("subscription"))
            subscription_metadata = subscription_context.get("metadata") or {}
            _apply_subscription_state(
                user_id=subscription_metadata.get("user_id") or metadata.get("user_id"),
                plan_type=subscription_metadata.get("plan_type") or metadata.get("plan_type"),
                subscription_status=subscription_context.get("status") or "active",
                subscription_expires_at=subscription_context.get("current_period_end"),
            )

    elif event_type == "checkout.session.async_payment_failed":
        order_id = metadata.get("order_id")
        if order_id:
            _update_order_and_payment(
                order_id,
                order_status="pending",
                order_payment_status="failed",
                payment_status="failed",
                metadata_updates={
                    "provider": "stripe",
                    "session_id": obj.get("id"),
                    "payment_intent": obj.get("payment_intent"),
                    "customer": obj.get("customer"),
                },
            )

    elif event_type.startswith("customer.subscription."):
        subscription_metadata = dict(obj.get("metadata") or {})
        _apply_subscription_state(
            user_id=subscription_metadata.get("user_id"),
            plan_type=subscription_metadata.get("plan_type"),
            subscription_status=obj.get("status") or (
                "canceled" if event_type == "customer.subscription.deleted" else None
            ),
            subscription_expires_at=_period_end_iso(obj.get("current_period_end")),
        )

    elif event_type in {"invoice.payment_failed", "invoice.paid", "invoice.payment_succeeded"}:
        subscription_context = _subscription_context(obj.get("subscription"))
        subscription_metadata = subscription_context.get("metadata") or {}
        subscription_status = subscription_context.get("status")

        if event_type in {"invoice.paid", "invoice.payment_succeeded"}:
            _apply_subscription_state(
                user_id=subscription_metadata.get("user_id"),
                plan_type=subscription_metadata.get("plan_type"),
                subscription_status=subscription_status or "active",
                subscription_expires_at=subscription_context.get("current_period_end"),
            )
        else:
            if subscription_status in {"canceled", "unpaid", "incomplete_expired"}:
                _apply_subscription_state(
                    user_id=subscription_metadata.get("user_id"),
                    plan_type=subscription_metadata.get("plan_type"),
                    subscription_status=subscription_status,
                    subscription_expires_at=None,
                )

    return {"status": "ok", "processed": True, "event_type": event_type}
