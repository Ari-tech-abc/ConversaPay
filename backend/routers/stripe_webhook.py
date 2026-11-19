"""Stripe webhook: event payload is authoritative and processing stays local."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import stripe
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from supabase import Client, create_client

from backend.config import settings
from backend.services.subscription_service import apply_subscription_state, mark_webhook_failed, mark_webhook_processed, period_end_iso, subscription_period_end

from backend.services.payment_validation import checkout_amount
from backend.services.subscription_catalog import subscription_plan, invoice_confirms_subscription

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/stripe", tags=["stripe-webhook"], redirect_slashes=False)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
if settings.STRIPE_SECRET_KEY:
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _claim(event_id: str, event_type: str) -> bool:
    result = supabase.rpc("claim_webhook_event", {"p_provider": "stripe", "p_event_id": event_id, "p_event_type": event_type}).execute()
    value = result.data
    if isinstance(value, list):
        value = value[0] if value else False
    if isinstance(value, dict):
        value = next(iter(value.values()), False)
    return value is True or str(value).lower() == "true"


def _lookup_user(customer_id: str | None = None, subscription_id: str | None = None) -> str | None:
    query = supabase.table("profiles").select("user_id")
    if subscription_id:
        result = query.eq("stripe_subscription_id", subscription_id).limit(1).execute()
    elif customer_id:
        result = query.eq("stripe_customer_id", customer_id).limit(1).execute()
    else:
        return None
    return result.data[0]["user_id"] if result.data else None


def _update_order(order_id: str, *, session: dict, order_status: str, payment_status: str, metadata_updates: dict[str, Any], paid: bool = False) -> None:
    amount, currency = checkout_amount(session)
    session_id = session.get('id')
    if not session_id:
        raise ValueError('Missing provider session ID')
    result = supabase.rpc('update_order_payment_atomic', {
        'p_order_id': order_id, 'p_order_status': order_status, 'p_payment_status': payment_status,
        'p_metadata_updates': metadata_updates, 'p_paid': paid,
        'p_expected_amount': amount, 'p_expected_currency': currency,
        'p_provider_session_id': session_id, 'p_provider': 'stripe',
    }).execute()
    if result.data is not True:
        raise RuntimeError('Atomic order/payment validation or update failed')


def _apply_from_event(*, user_id: str | None, plan_type: str | None, subscription_id: str | None, customer_id: str | None, context: dict[str, Any], stripe_subscription: dict[str, Any] | None = None) -> None:
    try:
        plan = subscription_plan((stripe_subscription or {}).get("metadata", {}).get("plan_type") or plan_type or "")
        paid = invoice_confirms_subscription(stripe_subscription or {}, plan)
    except ValueError:
        paid = False
    apply_subscription_state(
        user_id=user_id or _lookup_user(customer_id, subscription_id),
        plan_type=plan_type,
        subscription_status=context.get("status"),
        subscription_expires_at=context.get("current_period_end"),
        customer_id=customer_id,
        cancel_at_period_end=context.get("cancel_at_period_end", False),
        stripe_subscription_id=subscription_id,
        stripe_subscription=stripe_subscription or context,
        payment_confirmed=paid,
    )


def _subscription_context(obj: dict[str, Any], subscription_id: str | None = None) -> dict[str, Any]:
    return {"id": obj.get("id") or subscription_id, "metadata": dict(obj.get("metadata") or {}), "status": obj.get("status"), "current_period_end": period_end_iso(subscription_period_end(obj)), "customer": obj.get("customer"), "cancel_at_period_end": bool(obj.get("cancel_at_period_end", False))}


def _as_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return dict(obj)


def _retrieve_subscription(subscription_id: str | None) -> dict[str, Any] | None:
    if not subscription_id:
        return None
    try:
        return _as_dict(stripe.Subscription.retrieve(subscription_id, expand=["items.data.price.product", "latest_invoice"]))
    except stripe.error.StripeError:
        logger.warning("Could not retrieve Stripe subscription %s during webhook reconciliation", subscription_id, exc_info=True)
        return None


@router.post("")
@router.post("/")
async def stripe_webhook(request: Request) -> JSONResponse:
    raw = await request.body()
    signature = request.headers.get("stripe-signature")
    signing_secret = settings.STRIPE_CONNECT_WEBHOOK_SECRET if request.url.path.endswith("/connect") else settings.STRIPE_WEBHOOK_SECRET
    if not signature or not signing_secret:
        raise HTTPException(400, "Missing Stripe signature configuration")
    try:
        event = stripe.Webhook.construct_event(raw, signature, signing_secret)
    except ValueError as exc:
        raise HTTPException(400, "Invalid Stripe payload") from exc
    except stripe.error.SignatureVerificationError as exc:
        raise HTTPException(400, "Invalid Stripe signature") from exc

    event_id, event_type = str(event["id"]), str(event["type"])
    claimed = False
    try:
        claimed = await asyncio.to_thread(lambda: _claim(event_id,event_type))
        if not claimed:
            return JSONResponse(status_code=200, content={"status": "ok", "processed": False, "duplicate": True})
        obj = _as_dict(event["data"]["object"])
        metadata = dict(obj.get("metadata") or {})
        account = event.get("account")
        if metadata.get("order_id"):
            matches = (await asyncio.to_thread(lambda: supabase.table("payments").select("metadata").eq("order_id",metadata["order_id"]).eq("metadata->>provider_session_id",obj.get("id")).limit(1).execute())).data or []
            if not matches or (matches[0].get("metadata") or {}).get("stripe_account_id") != account:
                raise ValueError("Merchant payment account mismatch")
        if account and (obj.get("mode")=="subscription" or event_type.startswith(("customer.subscription.","invoice."))):
            await asyncio.to_thread(mark_webhook_processed,event_id)
            return JSONResponse(status_code=200,content={"status":"ok","ignored":True})
        checkout_completed = False
        if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
            order_id = metadata.get("order_id")
            if order_id and obj.get("payment_status") == "paid":
                await asyncio.to_thread(_update_order,order_id, session=obj, order_status="paid", payment_status="succeeded", paid=True, metadata_updates={"provider": "stripe", "provider_session_id": obj.get("id"), "payment_intent": obj.get("payment_intent"), "customer": obj.get("customer")})
                checkout_completed = True
            if obj.get("mode") == "subscription" and obj.get("payment_status") == "paid":
                subscription_id = obj.get("subscription") if isinstance(obj.get("subscription"), str) else None
                subscription = await asyncio.to_thread(_retrieve_subscription, subscription_id)
                if not subscription:
                    raise RuntimeError("Subscription could not be verified")
                expected = subscription_plan((subscription.get("metadata") or {}).get("plan_type") or metadata.get("plan_type") or "")
                if obj.get("payment_status") != "paid" or obj.get("amount_total") != expected.amount_minor or str(obj.get("currency") or "").upper() != expected.currency:
                    raise ValueError("Subscription checkout amount or payment state mismatch")
                source = subscription
                context = _subscription_context(source, subscription_id)
                cm = context.get("metadata") or {}
                _apply_from_event(user_id=cm.get("user_id") or metadata.get("user_id"), plan_type=cm.get("plan_type") or metadata.get("plan_type"), subscription_id=subscription_id or context.get("id"), customer_id=context.get("customer") or obj.get("customer"), context=context, stripe_subscription=subscription)
        elif event_type in {"checkout.session.async_payment_failed","checkout.session.expired"}:
            order_id = metadata.get("order_id")
            if order_id:
                (await asyncio.to_thread(lambda: supabase.rpc("expire_order_checkout",{"p_order_id":order_id,"p_session_id":obj["id"]}).execute()))
        elif event_type.startswith("customer.subscription."):
            subscription = await asyncio.to_thread(_retrieve_subscription, obj.get("id"))
            if not subscription:
                raise RuntimeError("Subscription could not be verified")
            context = _subscription_context(subscription)
            cm = context.get("metadata") or {}
            _apply_from_event(user_id=cm.get("user_id"), plan_type=cm.get("plan_type"), subscription_id=context.get("id"), customer_id=subscription.get("customer"), context=context, stripe_subscription=subscription)
        elif event_type in {"invoice.paid", "invoice.payment_succeeded", "invoice.payment_failed"}:
            subscription_id = obj.get("subscription") or (((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
            if not subscription_id:
                (await asyncio.to_thread(lambda: mark_webhook_processed(event_id)))
                return JSONResponse(status_code=200, content={"status": "ok", "processed": True})
            subscription = await asyncio.to_thread(_retrieve_subscription, subscription_id)
            if not subscription:
                raise RuntimeError("Subscription could not be verified")
            source = subscription
            context = _subscription_context(source, subscription_id)
            cm = context.get("metadata") or {}
            _apply_from_event(user_id=cm.get("user_id"), plan_type=cm.get("plan_type"), subscription_id=subscription_id or context.get("id"), customer_id=context.get("customer") or obj.get("customer"), context=context, stripe_subscription=subscription)
        elif event_type in {"charge.refunded", "charge.refund.updated", "refund.updated"}:
            if account:
                charge = obj
                if event_type != "charge.refunded":
                    charge = await asyncio.to_thread(stripe.Charge.retrieve,obj["charge"],stripe_account=account)
                amount,_ = checkout_amount({"amount_total":charge["amount_refunded"],"currency":charge["currency"]}) if charge["amount_refunded"] else ("0","")
                (await asyncio.to_thread(lambda: supabase.rpc("apply_order_refund",{"p_payment_intent":charge["payment_intent"],"p_account":account,"p_amount":amount}).execute()))
        (await asyncio.to_thread(lambda: mark_webhook_processed(event_id)))
        if checkout_completed:
            return JSONResponse(status_code=200, content={"status": "success"})
        return JSONResponse(status_code=200, content={"status": "ok", "processed": True, "event_type": event_type})
    except Exception as exc:
        try:
            if claimed:
                (await asyncio.to_thread(lambda: mark_webhook_failed(event_id, str(exc))))
        except Exception:
            logger.exception("Failed to mark webhook event failed")
        logger.exception("Stripe webhook processing failed for %s", event_id)
        raise HTTPException(500, "Webhook processing failed") from exc

router.add_api_route("/connect",stripe_webhook,methods=["POST"])
