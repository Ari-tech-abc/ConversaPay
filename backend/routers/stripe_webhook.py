"""Stripe webhook with official signature verification and idempotency."""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
import stripe
from fastapi import APIRouter, HTTPException, Request
from supabase import Client, create_client
from backend.config import settings
from backend.services.stripe_service import StripeServiceError, stripe_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/stripe", tags=["stripe-webhook"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
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
        supabase.table("webhook_events").insert({"provider":"stripe","event_id":event_id,"status":event_type,"received_at":_utc_now_iso()}).execute()
        return True
    except Exception as exc:
        if any(marker in str(exc).lower() for marker in ("duplicate", "unique", "23505", "conflict", "already exists")):
            return False
        raise


def _lookup_user_by_stripe_customer(customer_id: str) -> str | None:
    if not customer_id:
        return None
    try:
        result = supabase.table("profiles").select("user_id").eq("stripe_customer_id", customer_id).limit(1).execute()
        if result.data:
            return result.data[0]["user_id"]
    except Exception:
        pass
    try:
        stripe_service._ensure_configured()
        customer = stripe.Customer.retrieve(customer_id)
        email = customer.get("email")
        if not email:
            return None
        result = supabase.table("profiles").select("user_id").eq("email", email).limit(1).execute()
        if result.data:
            return result.data[0]["user_id"]
        result = supabase.table("profiles").select("user_id").ilike("email", email).limit(1).execute()
        if result.data:
            return result.data[0]["user_id"]
    except Exception as exc:
        logger.warning("Fallback customer lookup failed for %s: %s", customer_id, exc)
    return None


def _store_stripe_customer_id(user_id: str, customer_id: str) -> None:
    if not user_id or not customer_id:
        return
    try:
        supabase.table("profiles").update({"stripe_customer_id":customer_id,"updated_at":_utc_now_iso()}).eq("user_id",user_id).execute()
    except Exception as exc:
        logger.warning("Failed to store stripe_customer_id %s for user %s: %s", customer_id, user_id, exc)


def _update_profile_and_business(
    user_id: str,
    *,
    plan_type: str,
    subscription_expires_at: str | None,
    subscription_status: str,
    subscription_start_date: str | None = None,
    auto_renew: bool = True,
    stripe_subscription_id: str | None = None,
) -> None:
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    end_date = subscription_expires_at
    if plan_type in {"pro", "premium"} and not end_date:
        end_date = (now_dt + timedelta(days=30)).isoformat()
    payload: dict[str, Any] = {
        "plan_type": plan_type,
        "subscription_status": subscription_status,
        "subscription_start_date": subscription_start_date or (now if plan_type != "free" else None),
        "subscription_end_date": end_date if plan_type != "free" else None,
        "subscription_expires_at": end_date if plan_type != "free" else None,
        "auto_renew": bool(auto_renew) if plan_type != "free" else False,
        "updated_at": now,
    }
    if stripe_subscription_id:
        payload["stripe_subscription_id"] = stripe_subscription_id
    supabase.table("profiles").update(payload).eq("user_id", user_id).execute()
    try:
        supabase.table("businesses").update({"subscription_tier":plan_type,"subscription_status":subscription_status}).eq("owner_id", user_id).execute()
    except Exception as exc:
        logger.warning("Profile was synced from Stripe but business sync failed for user %s: %s", user_id, exc)


def _update_order_and_payment(order_id: str, *, order_status: str, order_payment_status: str, payment_status: str, metadata_updates: dict[str, Any] | None = None, paid: bool = False) -> None:
    now = _utc_now_iso()
    supabase.table("orders").update({"status":order_status,"payment_status":order_payment_status,"updated_at":now}).eq("id",order_id).execute()
    payment_result = supabase.table("payments").select("id, metadata").eq("order_id",order_id).order("created_at",desc=True).limit(1).execute()
    if not payment_result.data:
        return
    payment_row = payment_result.data[0]
    metadata = dict(payment_row.get("metadata") or {}); metadata.update(metadata_updates or {})
    update_payload: dict[str, Any] = {"status":payment_status,"metadata":metadata,"updated_at":now}
    if paid: update_payload["paid_at"] = now
    supabase.table("payments").update(update_payload).eq("id",payment_row["id"]).execute()


def _subscription_context(subscription_id: str | None) -> dict[str, Any]:
    if not subscription_id:
        return {}
    try:
        subscription = stripe_service.retrieve_subscription(subscription_id)
    except (StripeServiceError, ValueError) as exc:
        logger.warning("Unable to retrieve Stripe subscription %s: %s", subscription_id, exc)
        return {}
    return {"id":subscription.get("id") or subscription_id,"metadata":dict(subscription.get("metadata") or {}),"status":subscription.get("status"),"current_period_end":_period_end_iso(subscription.get("current_period_end")),"customer":subscription.get("customer"),"cancel_at_period_end":subscription.get("cancel_at_period_end",False),"canceled_at":subscription.get("canceled_at")}


def _apply_subscription_state(*, user_id: str | None, plan_type: str | None, subscription_status: str | None, subscription_expires_at: str | None, customer_id: str | None = None, cancel_at_period_end: bool = False, stripe_subscription_id: str | None = None) -> None:
    if not user_id and customer_id:
        user_id = _lookup_user_by_stripe_customer(customer_id)
    if not user_id:
        logger.warning("Cannot apply subscription state: no user_id found (customer=%s)", customer_id)
        return
    effective_plan = (plan_type or "pro").lower()
    effective_status = (subscription_status or "active").lower()
    effective_expiry = subscription_expires_at
    auto_renew = not cancel_at_period_end
    if cancel_at_period_end and effective_plan in {"pro", "premium"}:
        effective_status = "pending_cancellation"
    elif effective_status in {"canceled", "unpaid", "incomplete_expired"}:
        effective_plan = "free"
        effective_expiry = None
        auto_renew = False
    _update_profile_and_business(user_id, plan_type=effective_plan, subscription_expires_at=effective_expiry, subscription_status=effective_status, auto_renew=auto_renew, stripe_subscription_id=stripe_subscription_id)


def _handle_charge_refunded(obj: dict[str, Any]) -> None:
    invoice_id = obj.get("invoice"); customer_id = obj.get("customer")
    if invoice_id:
        try:
            stripe_service._ensure_configured()
            invoice = stripe.Invoice.retrieve(invoice_id); subscription_id = invoice.get("subscription")
            if subscription_id:
                context = _subscription_context(subscription_id); metadata = context.get("metadata") or {}; user_id = metadata.get("user_id") or _lookup_user_by_stripe_customer(customer_id or "")
                if user_id:
                    _update_profile_and_business(user_id, plan_type="free", subscription_expires_at=None, subscription_status="canceled", auto_renew=False, stripe_subscription_id=subscription_id)
                    try: stripe.Subscription.cancel(subscription_id)
                    except Exception as exc: logger.warning("Auto-cancel subscription %s after refund failed: %s", subscription_id, exc)
                return
        except Exception as exc:
            logger.warning("Error processing refund invoice lookup: %s", exc)
    if customer_id:
        user_id = _lookup_user_by_stripe_customer(customer_id)
        if user_id: _update_profile_and_business(user_id, plan_type="free", subscription_expires_at=None, subscription_status="canceled", auto_renew=False)


@router.post("")
async def stripe_webhook(request: Request) -> dict[str, Any]:
    raw = await request.body(); signature = request.headers.get("stripe-signature")
    if not signature or not settings.STRIPE_WEBHOOK_SECRET: raise HTTPException(400, "Missing Stripe signature configuration")
    try: event = stripe.Webhook.construct_event(raw, signature, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError as exc: raise HTTPException(400, "Invalid Stripe payload") from exc
    except stripe.error.SignatureVerificationError as exc: raise HTTPException(400, "Invalid Stripe signature") from exc
    event_id = str(event["id"]); event_type = str(event["type"])
    if not _claim(event_id, event_type): return {"status":"ok","processed":False}
    obj = stripe_service.serialize_stripe_object(event["data"]["object"]); metadata = dict(obj.get("metadata") or {})
    logger.info("Processing Stripe event: %s (id=%s)", event_type, event_id)

    if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
        order_id = metadata.get("order_id")
        if order_id: _update_order_and_payment(order_id, order_status="paid", order_payment_status="paid", payment_status="succeeded", metadata_updates={"provider":"stripe","session_id":obj.get("id"),"payment_intent":obj.get("payment_intent"),"customer":obj.get("customer")}, paid=True)
        if obj.get("mode") == "subscription":
            checkout_user_id = metadata.get("user_id"); customer_id = obj.get("customer"); subscription_id = obj.get("subscription") if isinstance(obj.get("subscription"), str) else None
            if checkout_user_id and customer_id: _store_stripe_customer_id(checkout_user_id, customer_id)
            context = _subscription_context(subscription_id); context_metadata = context.get("metadata") or {}
            _apply_subscription_state(user_id=context_metadata.get("user_id") or checkout_user_id, plan_type=context_metadata.get("plan_type") or metadata.get("plan_type"), subscription_status=context.get("status") or "active", subscription_expires_at=context.get("current_period_end"), customer_id=customer_id, cancel_at_period_end=context.get("cancel_at_period_end",False), stripe_subscription_id=context.get("id") or subscription_id)

    elif event_type == "checkout.session.async_payment_failed":
        order_id = metadata.get("order_id")
        if order_id: _update_order_and_payment(order_id, order_status="pending", order_payment_status="failed", payment_status="failed", metadata_updates={"provider":"stripe","session_id":obj.get("id"),"payment_intent":obj.get("payment_intent"),"customer":obj.get("customer")})

    elif event_type.startswith("customer.subscription."):
        subscription_id = obj.get("id"); context_metadata = dict(obj.get("metadata") or {}); cancel_at_period_end = bool(obj.get("cancel_at_period_end",False)); raw_status = obj.get("status"); effective_status = "canceled" if event_type == "customer.subscription.deleted" else raw_status
        _apply_subscription_state(user_id=context_metadata.get("user_id"), plan_type=context_metadata.get("plan_type"), subscription_status=effective_status, subscription_expires_at=_period_end_iso(obj.get("current_period_end")), customer_id=obj.get("customer"), cancel_at_period_end=cancel_at_period_end, stripe_subscription_id=subscription_id)

    elif event_type in {"charge.refunded", "charge.refund.updated"}:
        _handle_charge_refunded(obj)

    elif event_type in {"invoice.payment_failed", "invoice.paid", "invoice.payment_succeeded"}:
        context = _subscription_context(obj.get("subscription")); context_metadata = context.get("metadata") or {}; customer_id = context.get("customer") or obj.get("customer"); cancel_at_period_end = bool(context.get("cancel_at_period_end",False))
        if event_type in {"invoice.paid", "invoice.payment_succeeded"}:
            _apply_subscription_state(user_id=context_metadata.get("user_id"), plan_type=context_metadata.get("plan_type"), subscription_status=context.get("status") or "active", subscription_expires_at=context.get("current_period_end"), customer_id=customer_id, cancel_at_period_end=cancel_at_period_end, stripe_subscription_id=context.get("id"))
        elif context.get("status") in {"canceled", "unpaid", "incomplete_expired"} and not cancel_at_period_end:
            _apply_subscription_state(user_id=context_metadata.get("user_id"), plan_type=context_metadata.get("plan_type"), subscription_status=context.get("status"), subscription_expires_at=None, customer_id=customer_id, cancel_at_period_end=False, stripe_subscription_id=context.get("id"))

    return {"status":"ok","processed":True,"event_type":event_type}
