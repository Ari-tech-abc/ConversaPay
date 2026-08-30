"""Stripe-backed subscription routes and provider-neutral order checkout."""
from __future__ import annotations
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
from backend.services.subscription_service import apply_subscription_state, normalize_plan_type, period_end_iso
logger = logging.getLogger(__name__)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
router = APIRouter(prefix="/payments", tags=["payments"])
PLAN_PRICES = {"pro": 200, "premium": 350}
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
    _require_stripe_secret_key()
    metadata = {"user_id": current_user.user_id, "plan_type": plan}
    price_id = PLAN_PRICE_IDS.get(plan)
    log_context = f"user_id={current_user.user_id} plan={plan} price_id={price_id or 'inline_price_data'}"
    try:
        session = (
            stripe_service.create_checkout_session_with_price(price_id=price_id, mode="subscription", customer_email=current_user.email, metadata=metadata)
            if price_id
            else stripe_service.create_checkout_session(amount=PLAN_PRICES[plan], product_name=f"ConversaPay {plan.upper()} subscription", currency="ILS", mode="subscription", customer_email=current_user.email, metadata=metadata)
        )
    except HTTPException:
        raise
    except ValueError as exc:
        logger.error("Invalid checkout session request (%s): %s", log_context, exc)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except stripe.error.StripeError as exc:
        reason = describe_stripe_error(exc)
        logger.error("Stripe refused the checkout session (%s): %s", log_context, reason, exc_info=True)
        code = status.HTTP_400_BAD_REQUEST if isinstance(exc, stripe.error.InvalidRequestError) else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(code, f"Stripe could not create the checkout session: {reason}") from exc
    except StripeServiceError as exc:
        logger.error("Checkout session creation failed (%s): %s", log_context, exc)
        raise HTTPException(_stripe_service_error_status(exc), str(exc)) from exc
    except Exception as exc:
        logger.error("Unexpected error while creating checkout session (%s): %s: %s", log_context, type(exc).__name__, exc, exc_info=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Unexpected error while creating the Stripe checkout session") from exc
    return SubscriptionResponse(session_id=session["session_id"], url=session["url"], payme_sale_id=None)

def _extract_subscription_fields(session: dict[str, Any]) -> tuple[str | None, str | None, str | None, bool, dict[str, Any] | None]:
    subscription = session.get("subscription")
    if isinstance(subscription, dict):
        return (
            subscription.get("id"),
            subscription.get("status"),
            period_end_iso(subscription.get("current_period_end")),
            bool(subscription.get("cancel_at_period_end", False)),
            subscription,
        )
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
            product_metadata = product.get("metadata") or {}
            candidates.extend([product_metadata.get("plan_type"), product_metadata.get("plan"), product.get("name")])
    for candidate in candidates:
        plan = normalize_plan_type(candidate)
        if plan in {"pro", "premium"}:
            return plan
    return "pro"

@router.get("/confirm-session", response_model=dict)
async def confirm_checkout_session(session_id: str = Query(..., min_length=1), current_user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    """Verify Stripe and reconcile a completed subscription before success.html advances."""
    try:
        session = stripe_service.retrieve_checkout_session(session_id)
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
    if mode != "subscription":
        if payment_status in CONFIRMED_PAYMENT_STATUSES and session_status in {"complete", ""}:
            response.update({"confirmed": True, "status": "confirmed"})
        return response
    subscription_id, subscription_status, subscription_expires_at, cancel_at_period_end, subscription = _extract_subscription_fields(session)
    if isinstance(session.get("subscription"), str):
        try:
            subscription = stripe_service.retrieve_subscription(session["subscription"])
        except StripeServiceError as exc:
            raise HTTPException(_stripe_service_error_status(exc), str(exc)) from exc
        subscription_id = subscription.get("id") or subscription_id
        subscription_status = subscription.get("status")
        subscription_expires_at = period_end_iso(subscription.get("current_period_end"))
        cancel_at_period_end = bool(subscription.get("cancel_at_period_end", False))
    subscription_metadata = dict((subscription or {}).get("metadata") or {})
    subscription_user_id = subscription_metadata.get("user_id")
    if subscription_user_id and subscription_user_id != current_user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Subscription does not belong to the current user")
    normalized_subscription_status = str(subscription_status or "").lower()
    paid_or_active = payment_status in CONFIRMED_PAYMENT_STATUSES or (session_status == "complete" and normalized_subscription_status in ACTIVE_SUBSCRIPTION_STATUSES)
    if not paid_or_active:
        response.update({"subscription_status": normalized_subscription_status or None, "status": "pending"})
        logger.info("Stripe checkout still pending (session_id=%s session_status=%s payment_status=%s subscription_status=%s)", session_id, session_status or "unknown", payment_status or "unknown", normalized_subscription_status or "unknown")
        return response
    plan_type = _subscription_plan_from_stripe(session, subscription)
    try:
        apply_subscription_state(user_id=current_user.user_id, plan_type=plan_type, subscription_status=subscription_status, subscription_expires_at=subscription_expires_at, customer_id=(subscription or {}).get("customer") or session.get("customer"), cancel_at_period_end=cancel_at_period_end, stripe_subscription_id=subscription_id, stripe_subscription=subscription or session.get("subscription"))
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
    business = supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()
    if not business.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    order = supabase.table("orders").select("*").eq("id", order_id).eq("business_id", business.data[0]["id"]).execute()
    if not order.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    provider = (settings.PAYMENT_PROVIDER or "stripe").strip().lower()
    if provider == "stripe":
        _require_stripe_secret_key()
    try:
        checkout = await get_checkout_adapter(provider).create_checkout(_checkout_order_from_row(order.data[0], request))
    except (PaymentAdapterError, ValueError) as exc:
        logger.error("Order checkout creation failed (order_id=%s provider=%s): %s", order_id, provider, exc, exc_info=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    payment = supabase.table("payments").insert({"business_id": business.data[0]["id"], "order_id": order_id, "amount": order.data[0]["total"], "currency": order.data[0].get("currency", "ILS"), "status": "pending", "customer_email": request.get("customer_email") or (order.data[0].get("customer_info") or {}).get("email"), "customer_name": request.get("customer_name") or (order.data[0].get("customer_info") or {}).get("name"), "metadata": {"provider": checkout.provider, "provider_session_id": checkout.provider_session_id, "checkout_url": checkout.checkout_url}}).execute()
    return {"session_id": checkout.provider_session_id, "url": checkout.checkout_url, "checkout_url": checkout.checkout_url, "provider": checkout.provider, "payment_id": payment.data[0]["id"] if payment.data else None}

@router.get("/profile", response_model=ProfileResponse)
async def get_profile(current_user: AuthUser = Depends(require_auth)) -> ProfileResponse:
    fields = "id,user_id,email,full_name,plan_type,subscription_expires_at,created_at,updated_at"
    result = supabase.table("profiles").select(fields).eq("user_id", current_user.user_id).execute()
    if not result.data:
        result = supabase.table("profiles").insert({"user_id": current_user.user_id, "email": current_user.email, "plan_type": "free"}).execute()
    return ProfileResponse(**result.data[0])

@router.get("/success")
async def payment_success(session_id: str | None = None, provider: str | None = None, order_id: str | None = None) -> dict[str, Any]:
    return {"status": "pending_confirmation", "provider": provider or settings.PAYMENT_PROVIDER, "session_id": session_id, "order_id": order_id}

@router.get("/canceled")
async def payment_canceled(provider: str | None = None, order_id: str | None = None) -> dict[str, Any]:
    return {"status": "canceled", "provider": provider or settings.PAYMENT_PROVIDER, "order_id": order_id}

@router.get("", response_model=list[PaymentResponse])
async def get_payments(business_id: str, current_user: AuthUser = Depends(require_auth)) -> list[PaymentResponse]:
    business = supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()
    if not business.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    result = supabase.table("payments").select("*").eq("business_id", business.data[0]["id"]).order("created_at", desc=True).execute()
    return [PaymentResponse(**item) for item in (result.data or [])]

@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str, current_user: AuthUser = Depends(require_auth)) -> PaymentResponse:
    result = supabase.table("payments").select("*").eq("id", payment_id).execute()
    if not result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    item = result.data[0]
    if not supabase.table("businesses").select("id").eq("id", item["business_id"]).eq("owner_id", current_user.user_id).execute().data:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    return PaymentResponse(**item)

@router.get("/wordpress-plugin/{business_id}")
async def get_wordpress_plugin(business_id: str, current_user: AuthUser = Depends(require_auth)) -> Response:
    business = supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()
    if not business.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    path = Path(__file__).parent.parent / "templates" / "conversapay-chat.php"
    if not path.exists():
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Plugin file not found")
    content = path.read_text(encoding="utf-8").replace("{{BUSINESS_ID}}", business_id).replace("{{FRONTEND_URL}}", settings.FRONTEND_URL)
    return Response(content=content.encode(), media_type="application/x-httpd-php", headers={"Content-Disposition": f"attachment; filename=conversapay-chat-{business_id}.php"})
