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


def _lookup_user_by_stripe_customer(customer_id: str) -> str | None:
    """Find user_id by looking up the Stripe customer in profiles or by email."""
    if not customer_id:
        return None
    try:
        # First try: direct lookup by stripe_customer_id field in profiles
        result = (
            supabase.table("profiles")
            .select("user_id")
            .eq("stripe_customer_id", customer_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["user_id"]
    except Exception:
        pass  # Field might not exist, fall through to email lookup

    try:
        # Second try: look up customer email in Stripe, match to profiles
        stripe_service._ensure_configured()
        customer = stripe.Customer.retrieve(customer_id)
        email = customer.get("email")
        if not email:
            return None
        result = (
            supabase.table("profiles")
            .select("user_id")
            .eq("email", email)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["user_id"]
        # Third try: case-insensitive email match
        result = (
            supabase.table("profiles")
            .select("user_id")
            .ilike("email", email)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["user_id"]
    except Exception as exc:
        logger.warning("Fallback customer lookup failed for %s: %s", customer_id, exc)
    return None


def _store_stripe_customer_id(user_id: str, customer_id: str) -> None:
    """Persist stripe_customer_id on the user profile for future webhook lookups."""
    if not user_id or not customer_id:
        return
    try:
        supabase.table("profiles").update(
            {"stripe_customer_id": customer_id, "updated_at": _utc_now_iso()}
        ).eq("user_id", user_id).execute()
    except Exception as exc:
        logger.warning(
            "Failed to store stripe_customer_id %s for user %s: %s",
            customer_id,
            user_id,
            exc,
        )


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
            "subscription_status": subscription_status,
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
        "customer": subscription.get("customer"),
        "cancel_at_period_end": subscription.get("cancel_at_period_end", False),
        "canceled_at": subscription.get("canceled_at"),
    }


def _apply_subscription_state(
    *,
    user_id: str | None,
    plan_type: str | None,
    subscription_status: str | None,
    subscription_expires_at: str | None,
    customer_id: str | None = None,
    cancel_at_period_end: bool = False,
) -> None:
    if not user_id and customer_id:
        user_id = _lookup_user_by_stripe_customer(customer_id)

    if not user_id:
        logger.warning(
            "Cannot apply subscription state: no user_id found (customer=%s)",
            customer_id,
        )
        return

    effective_plan = (plan_type or "pro").lower()
    effective_status = subscription_status or "active"
    effective_expiry = subscription_expires_at

    # Downgrade immediately if subscription is canceled or scheduled for cancellation
    if effective_status in {"canceled", "unpaid", "incomplete_expired"} or cancel_at_period_end:
        effective_plan = "free"
        effective_expiry = None
        if cancel_at_period_end and effective_status == "active":
            effective_status = "canceled"

    logger.info(
        "Applying subscription state for user %s: plan=%s status=%s",
        user_id,
        effective_plan,
        effective_status,
    )

    _update_profile_and_business(
        user_id,
        plan_type=effective_plan,
        subscription_expires_at=effective_expiry,
        subscription_status=effective_status,
    )


def _handle_charge_refunded(obj: dict[str, Any]) -> None:
    """When a charge is refunded, check if it belongs to a subscription and downgrade."""
    invoice_id = obj.get("invoice")
    customer_id = obj.get("customer")

    if invoice_id:
        try:
            stripe_service._ensure_configured()
            invoice = stripe.Invoice.retrieve(invoice_id)
            subscription_id = invoice.get("subscription")
            if subscription_id:
                sub_context = _subscription_context(subscription_id)
                sub_metadata = sub_context.get("metadata") or {}
                user_id = sub_metadata.get("user_id")
                if not user_id and customer_id:
                    user_id = _lookup_user_by_stripe_customer(customer_id)
                if user_id:
                    logger.info(
                        "Downgrading user %s to free due to refund on subscription %s",
                        user_id,
                        subscription_id,
                    )
                    _update_profile_and_business(
                        user_id,
                        plan_type="free",
                        subscription_expires_at=None,
                        subscription_status="canceled",
                    )
                    try:
                        stripe.Subscription.cancel(subscription_id)
                    except Exception as exc:
                        logger.warning(
                            "Auto-cancel subscription %s after refund failed: %s",
                            subscription_id,
                            exc,
                        )
                return
        except Exception as exc:
            logger.warning("Error processing refund invoice lookup: %s", exc)

    # Fallback: find user by customer and downgrade
    if customer_id:
        user_id = _lookup_user_by_stripe_customer(customer_id)
        if user_id:
            logger.info(
                "Downgrading user %s to free due to refund (customer=%s)",
                user_id,
                customer_id,
            )
            _update_profile_and_business(
                user_id,
                plan_type="free",
                subscription_expires_at=None,
                subscription_status="canceled",
            )


def _handle_payment_intent_canceled(obj: dict[str, Any]) -> None:
    """When a payment_intent is canceled, downgrade if tied to a subscription."""
    metadata = dict(obj.get("metadata") or {})
    customer_id = obj.get("customer")
    user_id = metadata.get("user_id")

    if not user_id and customer_id:
        user_id = _lookup_user_by_stripe_customer(customer_id)

    if not user_id:
        return

    # Check if this payment intent is linked to an invoice/subscription
    invoice_id = obj.get("invoice")
    if invoice_id:
        try:
            stripe_service._ensure_configured()
            invoice = stripe.Invoice.retrieve(invoice_id)
            subscription_id = invoice.get("subscription")
            if subscription_id:
                logger.info(
                    "Payment intent canceled for subscription %s, downgrading user %s",
                    subscription_id,
                    user_id,
                )
                _update_profile_and_business(
                    user_id,
                    plan_type="free",
                    subscription_expires_at=None,
                    subscription_status="canceled",
                )
                return
        except Exception as exc:
            logger.warning("Error looking up invoice for canceled payment_intent: %s", exc)

    # If metadata indicates this was a subscription payment, downgrade
    if metadata.get("plan_type") or metadata.get("subscription"):
        logger.info(
            "Payment intent canceled with plan metadata, downgrading user %s",
            user_id,
        )
        _update_profile_and_business(
            user_id,
            plan_type="free",
            subscription_expires_at=None,
            subscription_status="canceled",
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

    logger.info("Processing Stripe event: %s (id=%s)", event_type, event_id)

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
            # Store stripe_customer_id for future webhook lookups
            checkout_user_id = metadata.get("user_id")
            checkout_customer_id = obj.get("customer")
            if checkout_user_id and checkout_customer_id:
                _store_stripe_customer_id(checkout_user_id, checkout_customer_id)

            if checkout_user_id:
                _apply_subscription_state(
                    user_id=checkout_user_id,
                    plan_type=metadata.get("plan_type"),
                    subscription_status="active",
                    subscription_expires_at=None,
                    customer_id=checkout_customer_id,
                )

            subscription_context = _subscription_context(obj.get("subscription"))
            subscription_metadata = subscription_context.get("metadata") or {}
            _apply_subscription_state(
                user_id=subscription_metadata.get("user_id") or checkout_user_id,
                plan_type=subscription_metadata.get("plan_type") or metadata.get("plan_type"),
                subscription_status=subscription_context.get("status") or "active",
                subscription_expires_at=subscription_context.get("current_period_end"),
                customer_id=checkout_customer_id,
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
        customer_id = obj.get("customer")
        cancel_at_period_end = obj.get("cancel_at_period_end", False)
        canceled_at = obj.get("canceled_at")

        # Determine effective status
        raw_status = obj.get("status")
        if event_type == "customer.subscription.deleted":
            effective_status = "canceled"
        elif cancel_at_period_end or canceled_at:
            # User canceled but period hasn't ended yet: treat as canceled immediately
            effective_status = "canceled"
        else:
            effective_status = raw_status

        _apply_subscription_state(
            user_id=subscription_metadata.get("user_id"),
            plan_type=subscription_metadata.get("plan_type"),
            subscription_status=effective_status,
            subscription_expires_at=_period_end_iso(obj.get("current_period_end")),
            customer_id=customer_id,
            cancel_at_period_end=cancel_at_period_end,
        )

    elif event_type in {"charge.refunded", "charge.refund.updated"}:
        _handle_charge_refunded(obj)

    elif event_type == "payment_intent.canceled":
        _handle_payment_intent_canceled(obj)

    elif event_type in {"invoice.payment_failed", "invoice.paid", "invoice.payment_succeeded"}:
        subscription_context = _subscription_context(obj.get("subscription"))
        subscription_metadata = subscription_context.get("metadata") or {}
        subscription_status = subscription_context.get("status")
        customer_id = subscription_context.get("customer") or obj.get("customer")
        cancel_at_period_end = subscription_context.get("cancel_at_period_end", False)

        if event_type in {"invoice.paid", "invoice.payment_succeeded"}:
            _apply_subscription_state(
                user_id=subscription_metadata.get("user_id"),
                plan_type=subscription_metadata.get("plan_type"),
                subscription_status=subscription_status or "active",
                subscription_expires_at=subscription_context.get("current_period_end"),
                customer_id=customer_id,
                cancel_at_period_end=cancel_at_period_end,
            )
        else:
            if subscription_status in {"canceled", "unpaid", "incomplete_expired"} or cancel_at_period_end:
                _apply_subscription_state(
                    user_id=subscription_metadata.get("user_id"),
                    plan_type=subscription_metadata.get("plan_type"),
                    subscription_status=subscription_status or "canceled",
                    subscription_expires_at=None,
                    customer_id=customer_id,
                    cancel_at_period_end=cancel_at_period_end,
                )

    return {"status": "ok", "processed": True, "event_type": event_type}
