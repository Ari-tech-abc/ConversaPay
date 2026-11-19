"""Stripe-backed subscription routes and provider-neutral order checkout."""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from supabase import Client, create_client

from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import PaymentResponse, ProfileResponse, SubscriptionCreate, SubscriptionResponse
from backend.services.payment_adapters import CheckoutOrder, PaymentAdapterError, get_checkout_adapter
from backend.services.stripe_service import PLACEHOLDER_SECRET_KEY_PREFIX, STRIPE_KEY_MISSING_MESSAGE, StripeServiceError, describe_stripe_error, stripe_service
from backend.services.subscription_service import apply_subscription_state, normalize_plan_type, period_end_iso, subscription_period_end

logger = logging.getLogger(__name__)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
router = APIRouter(prefix="/payments", tags=["payments"])
from backend.services.subscription_checkout import create_subscription_checkout, BillingConflict, BillingStorageUnavailable
from backend.services.subscription_gateway import SubscriptionGatewayUnavailable
from backend.services.subscription_catalog import PLANS, invoice_confirms_subscription, paid_subscription_period
PLAN_PRICES = {key: plan.amount for key, plan in PLANS.items()}
PLAN_PRICE_IDS = {"pro": settings.STRIPE_PRO_PRICE_ID, "premium": settings.STRIPE_PREMIUM_PRICE_ID}
CONFIRMED_PAYMENT_STATUSES = {"paid", "no_payment_required"}
ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}


def _require_stripe_secret_key() -> None:
    secret_key = (settings.STRIPE_SECRET_KEY or "").strip()
    if not secret_key or secret_key.startswith(PLACEHOLDER_SECRET_KEY_PREFIX):
        logger.error("Checkout session aborted: STRIPE_SECRET_KEY is missing or still a placeholder (value not logged).")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, STRIPE_KEY_MISSING_MESSAGE)


def _stripe_service_error_status(exc: StripeServiceError) -> int:
    message = str(exc).lower()
    if "not configured" in message or "secret key is missing" in message:
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    return status.HTTP_502_BAD_GATEWAY


@router.post("/create-checkout-session", response_model=SubscriptionResponse)
async def create_subscription_checkout_session(request: SubscriptionCreate, current_user: AuthUser = Depends(require_auth)) -> SubscriptionResponse:
    if request.user_id != current_user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User ID mismatch")
    plan = normalize_plan_type(request.plan_type)
    if plan not in PLAN_PRICES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PRO and PREMIUM can be purchased")
    try:
        session = await asyncio.to_thread(create_subscription_checkout, supabase, user_id=current_user.user_id, email=current_user.email, plan_type=plan)
    except BillingConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except (SubscriptionGatewayUnavailable, BillingStorageUnavailable) as exc:
        raise HTTPException(503, str(exc)) from None
    except Exception:
        logger.exception("Subscription checkout could not be completed for user %s", current_user.user_id)
        raise HTTPException(502, "billing_checkout_unavailable") from None
    return SubscriptionResponse(session_id=session["session_id"], url=session["url"], payme_sale_id=None)



def _extract_subscription_fields(session: dict[str, Any]) -> tuple[str | None, str | None, str | None, bool, dict[str, Any] | None]:
    subscription = session.get("subscription")
    if isinstance(subscription, dict):
        return (subscription.get("id"), subscription.get("status"), period_end_iso(subscription_period_end(subscription)), bool(subscription.get("cancel_at_period_end", False)), subscription)
    if isinstance(subscription, str):
        return subscription, None, None, False, None
    return None, None, None, False, None


def _subscription_plan_from_stripe(session: dict[str, Any], subscription: dict[str, Any] | None) -> str:
    candidates: list[Any] = []
    for source in (subscription, session):
        if not isinstance(source, dict):
            continue
        metadata = source.get("metadata") or {}
        candidates.extend([metadata.get("plan_type"), metadata.get("plan")])
        items = source.get("items") or {}
        item_values = items.get("data", []) if isinstance(items, dict) else []
        for item in item_values:
            price = item.get("price") or {}
            price_metadata = price.get("metadata") or {}
            candidates.extend([price_metadata.get("plan_type"), price_metadata.get("plan"), price.get("lookup_key"), price.get("nickname"), price.get("id")])
            product = price.get("product") or {}
            if isinstance(product, dict):
                product_metadata = product.get("metadata") or {}
                candidates.extend([product_metadata.get("plan_type"), product_metadata.get("plan"), product.get("name")])
    for candidate in candidates:
        plan = normalize_plan_type(candidate)
        if plan in {"pro", "premium"}:
            return plan
    raise HTTPException(400, "Subscription has no recognized plan")


@router.get("/confirm-session", response_model=dict)
async def confirm_checkout_session(session_id: str = Query(..., min_length=1), current_user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    """Verify Stripe and reconcile a completed subscription before success.html advances."""
    try:
        session = await asyncio.to_thread(stripe_service.retrieve_checkout_session, session_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except StripeServiceError as exc:
        raise HTTPException(_stripe_service_error_status(exc), str(exc)) from exc

    metadata = dict(session.get("metadata") or {})
    if metadata.get("user_id") and metadata["user_id"] != current_user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Session does not belong to the current user")

    payment_status = str(session.get("payment_status") or "").lower()
    session_status = str(session.get("status") or "").lower()
    mode = session.get("mode")
    response: dict[str, Any] = {"session_id": session.get("id") or session_id, "mode": mode, "status": "pending", "payment_status": payment_status or None, "session_status": session_status or None, "confirmed": False, "subscription_state_source": "stripe_confirmed"}

    if mode == "subscription" and metadata.get("user_id") != current_user.user_id:
        raise HTTPException(403, "Session ownership metadata is required")

    if mode != "subscription":
        if payment_status in CONFIRMED_PAYMENT_STATUSES and session_status in {"complete", ""}:
            response.update({"confirmed": True, "status": "confirmed"})
        return response

    subscription_id, subscription_status, subscription_expires_at, cancel_at_period_end, subscription = _extract_subscription_fields(session)
    if subscription_id:
        try:
            subscription = await asyncio.to_thread(stripe_service.retrieve_subscription, subscription_id)
        except StripeServiceError as exc:
            raise HTTPException(_stripe_service_error_status(exc), str(exc)) from exc
        subscription_id = subscription.get("id") or subscription_id
        subscription_status = subscription.get("status")
        subscription_expires_at = period_end_iso(subscription_period_end(subscription))
        cancel_at_period_end = bool(subscription.get("cancel_at_period_end", False))

    subscription_metadata = dict((subscription or {}).get("metadata") or {})
    subscription_user_id = subscription_metadata.get("user_id")
    if subscription_user_id and subscription_user_id != current_user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Subscription does not belong to the current user")

    normalized_subscription_status = str(subscription_status or "").lower()
    paid_or_active = session_status == "complete" and normalized_subscription_status in ACTIVE_SUBSCRIPTION_STATUSES and bool(subscription_expires_at) and payment_status in CONFIRMED_PAYMENT_STATUSES
    if not paid_or_active:
        response.update({"subscription_status": normalized_subscription_status or None, "status": "pending"})
        logger.info("Stripe checkout still pending (session_id=%s session_status=%s payment_status=%s subscription_status=%s)", session_id, session_status or "unknown", payment_status or "unknown", normalized_subscription_status or "unknown")
        return response

    plan_type = _subscription_plan_from_stripe(session, subscription)
    expected = PLANS[plan_type]
    if payment_status != "paid" or session.get("amount_total") != expected.amount_minor or str(session.get("currency") or "").upper() != expected.currency:
        raise HTTPException(409, "billing_payment_mismatch")
    if not invoice_confirms_subscription(subscription or {}, expected):
        response["status"] = "pending"
        return response
    subscription_expires_at = period_end_iso(paid_subscription_period(subscription, expected)[1])
    try:
        applied = await asyncio.to_thread(apply_subscription_state, user_id=current_user.user_id, plan_type=plan_type, subscription_status=subscription_status, subscription_expires_at=subscription_expires_at, customer_id=(subscription or {}).get("customer") or session.get("customer"), cancel_at_period_end=cancel_at_period_end, stripe_subscription_id=subscription_id, stripe_subscription=subscription or session.get("subscription"), payment_confirmed=True)
        if applied is False:
            raise ValueError("Subscription state conflict")
    except Exception as exc:
        logger.error("Immediate plan reconciliation failed (user_id=%s session_id=%s plan_type=%s): %s", current_user.user_id, session_id, plan_type, exc, exc_info=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Stripe confirmed the payment but syncing the profile failed. Please retry in a moment.") from exc

    logger.info("Subscription reconciled immediately via confirm-session: user_id=%s plan_type=%s session_id=%s", current_user.user_id, plan_type, session_id)
    response.update({"confirmed": True, "status": "confirmed", "plan_type": plan_type, "subscription_status": normalized_subscription_status or "active", "subscription_expires_at": subscription_expires_at})
    return response


def _checkout_order_from_row(order: dict[str, Any], request: dict[str, Any]) -> CheckoutOrder:
    customer_info = order.get("customer_info") or {}
    return CheckoutOrder(order_id=str(order["id"]), order_number=str(order.get("order_number") or order["id"]), amount=Decimal(str(order.get("total") or "0")), currency=str(order.get("currency") or "ILS").upper(), items=list(order.get("items") or []), customer_email=request.get("customer_email") or customer_info.get("email"), customer_name=request.get("customer_name") or customer_info.get("name"), success_url=settings.PAYME_SUCCESS_URL if settings.PAYMENT_PROVIDER.lower() == "payme" else None, cancel_url=settings.PAYME_CANCEL_URL if settings.PAYMENT_PROVIDER.lower() == "payme" else None, callback_url=settings.PAYME_CALLBACK_URL if settings.PAYMENT_PROVIDER.lower() == "payme" else None, metadata={"business_id": str(order.get("business_id") or "")})


@router.post("/checkout-session", response_model=dict)
async def create_order_checkout_session(request: dict[str, Any], current_user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    business_id, order_id = request.get("business_id"), request.get("order_id")
    if not business_id or not order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing required fields: business_id, order_id")
    business = (await asyncio.to_thread(lambda: supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()))
    if not business.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    order = (await asyncio.to_thread(lambda: supabase.table("orders").select("*").eq("id", order_id).eq("business_id", business.data[0]["id"]).execute()))
    if not order.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")

    row = order.data[0]
    if row.get("status") in {"paid","shipped","delivered","canceled","refunded"}:
        raise HTTPException(409,"Order cannot create a new checkout")
    from backend.routers.chat import _create_order_checkout
    try:
        url, session_id, payment = await _create_order_checkout(row,row.get("customer_info") or {})
    except (PaymentAdapterError,ValueError) as exc:
        raise HTTPException(503,str(exc)) from None
    return {"session_id":session_id,"url":url,"checkout_url":url,"provider":"stripe","payment_id":payment.get("id")}



@router.get("/profile", response_model=ProfileResponse)
async def get_profile(current_user: AuthUser = Depends(require_auth)) -> ProfileResponse:
    fields = "id,user_id,email,full_name,plan_type,subscription_expires_at,created_at,updated_at"
    result = (await asyncio.to_thread(lambda: supabase.table("profiles").select(fields).eq("user_id", current_user.user_id).execute()))
    if not result.data:
        result = (await asyncio.to_thread(lambda: supabase.table("profiles").insert({"user_id": current_user.user_id, "email": current_user.email, "plan_type": "free"}).execute()))
    return ProfileResponse(**result.data[0])


@router.get("/success")
async def payment_success(session_id: str | None = None, provider: str | None = None, order_id: str | None = None) -> dict[str, Any]:
    return {"status": "pending_confirmation", "provider": provider or settings.PAYMENT_PROVIDER, "session_id": session_id, "order_id": order_id}


@router.get("/canceled")
async def payment_canceled(provider: str | None = None, order_id: str | None = None) -> dict[str, Any]:
    return {"status": "canceled", "provider": provider or settings.PAYMENT_PROVIDER, "order_id": order_id}


@router.get("", response_model=list[PaymentResponse])
async def get_payments(business_id: str, current_user: AuthUser = Depends(require_auth)) -> list[PaymentResponse]:
    business = (await asyncio.to_thread(lambda: supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()))
    if not business.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    result = (await asyncio.to_thread(lambda: supabase.table("payments").select("*").eq("business_id", business.data[0]["id"]).order("created_at", desc=True).execute()))
    return [PaymentResponse(**item) for item in (result.data or [])]


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str, current_user: AuthUser = Depends(require_auth)) -> PaymentResponse:
    result = (await asyncio.to_thread(lambda: supabase.table("payments").select("*").eq("id", payment_id).execute()))
    if not result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    item = result.data[0]
    if not (await asyncio.to_thread(lambda: supabase.table("businesses").select("id").eq("id", item["business_id"]).eq("owner_id", current_user.user_id).execute())).data:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    return PaymentResponse(**item)


@router.get("/wordpress-plugin/{business_id}")
async def get_wordpress_plugin(business_id: str, current_user: AuthUser = Depends(require_auth)) -> Response:
    from uuid import UUID
    try:
        UUID(business_id); field="id"
    except ValueError:
        field="business_id"
    business = (await asyncio.to_thread(lambda: supabase.table("businesses").select("id").eq(field, business_id).eq("owner_id", current_user.user_id).execute()))
    if not business.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    path = settings.base_dir / "wordpress-plugin" / "conversapay-chat.php"
    if not path.exists():
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Plugin file not found")
    import io, zipfile
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in ("conversapay-chat.php", "admin.css", "README.md"):
            bundle.write(path.parent / name, "conversapay-chat/" + name)
    return Response(content=archive.getvalue(), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=conversapay-chat.zip"})
