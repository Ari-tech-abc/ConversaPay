"""Stripe-backed payment routes. Subscription state is confirmed here on demand and by webhook."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any
import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from supabase import Client, create_client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import PaymentResponse, ProfileResponse, SubscriptionCreate, SubscriptionResponse
from backend.services.stripe_service import PLACEHOLDER_SECRET_KEY_PREFIX, STRIPE_KEY_MISSING_MESSAGE, StripeServiceError, describe_stripe_error, stripe_service
from backend.services.subscription_service import apply_subscription_state, period_end_iso

logger = logging.getLogger(__name__)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
router = APIRouter(prefix="/payments", tags=["payments"])
PLAN_PRICES = {"pro": 200, "premium": 350}
PLAN_PRICE_IDS = {"pro": settings.STRIPE_PRO_PRICE_ID, "premium": settings.STRIPE_PREMIUM_PRICE_ID}


def _require_stripe_secret_key() -> None:
    """Fail fast when STRIPE_SECRET_KEY is missing, before any Stripe call is attempted.

    The key value is never logged or returned: only the fact that it is unusable.
    """
    secret_key = (settings.STRIPE_SECRET_KEY or "").strip()
    if not secret_key or secret_key.startswith(PLACEHOLDER_SECRET_KEY_PREFIX):
        logger.error("Checkout session aborted: STRIPE_SECRET_KEY is missing or still a placeholder (value not logged).")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, STRIPE_KEY_MISSING_MESSAGE)


def _stripe_service_error_status(exc: StripeServiceError) -> int:
    """Configuration problems are ours (500); everything else is an upstream failure (502)."""
    message = str(exc).lower()
    if "not configured" in message or "secret key is missing" in message:
        return status.HTTP_500_INTERNAL_SERVER_ERROR
    return status.HTTP_502_BAD_GATEWAY


@router.post("/create-checkout-session", response_model=SubscriptionResponse)
async def create_subscription_checkout_session(request: SubscriptionCreate, current_user: AuthUser = Depends(require_auth)) -> SubscriptionResponse:
    if request.user_id != current_user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User ID mismatch")
    plan = (request.plan_type or "").lower()
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


def _extract_subscription_fields(session: dict[str, Any]) -> tuple[str | None, str | None, str | None, bool]:
    """Pull subscription id/status/expiry/cancel-flag out of an (expanded) Checkout Session dict.

    The `subscription` field is either an expanded object (dict) or a bare id (str), depending on
    whether Stripe had it ready to expand at retrieval time; handle both.
    """
    subscription = session.get("subscription")
    if isinstance(subscription, dict):
        return (
            subscription.get("id"),
            subscription.get("status"),
            period_end_iso(subscription.get("current_period_end")),
            bool(subscription.get("cancel_at_period_end", False)),
        )
    if isinstance(subscription, str):
        return subscription, None, None, False
    return None, None, None, False


@router.get("/confirm-session", response_model=dict)
async def confirm_checkout_session(session_id: str = Query(..., min_length=1), current_user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    """Verify a Checkout Session against Stripe and, for subscriptions, reconcile the profile now.

    success.html calls this immediately on load instead of waiting for the webhook. Once Stripe
    confirms payment_status == 'paid' for a subscription-mode session, we update
    profiles.plan_type right here so the UI never has to sit on "sync pending". This is safe to
    call more than once (e.g. the webhook firing afterwards): both paths converge on the same
    Stripe-confirmed state.
    """
    try:
        session = stripe_service.retrieve_checkout_session(session_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except StripeServiceError as exc:
        raise HTTPException(_stripe_service_error_status(exc), str(exc)) from exc
    metadata = dict(session.get("metadata") or {})
    if metadata.get("user_id") and metadata["user_id"] != current_user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Session does not belong to the current user")

    payment_status = session.get("payment_status")
    mode = session.get("mode")
    response: dict[str, Any] = {"session_id": session.get("id"), "mode": mode, "status": "pending", "payment_status": payment_status, "confirmed": False, "subscription_state_source": "stripe_webhook"}

    if payment_status != "paid":
        return response

    if mode != "subscription":
        # One-off order payments are reconciled by the webhook via update_order_payment_atomic;
        # there is no profile plan to sync here, just acknowledge Stripe already confirmed it.
        response.update({"confirmed": True, "status": "confirmed"})
        return response

    plan_type = (metadata.get("plan_type") or "pro").lower()
    subscription_id, subscription_status, subscription_expires_at, cancel_at_period_end = _extract_subscription_fields(session)
    try:
        apply_subscription_state(
            user_id=current_user.user_id,
            plan_type=plan_type,
            subscription_status=subscription_status,
            subscription_expires_at=subscription_expires_at,
            customer_id=session.get("customer"),
            cancel_at_period_end=cancel_at_period_end,
            stripe_subscription_id=subscription_id,
        )
    except Exception as exc:
        logger.error("Immediate plan reconciliation failed (user_id=%s session_id=%s plan_type=%s): %s", current_user.user_id, session_id, plan_type, exc, exc_info=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Stripe confirmed the payment but syncing the profile failed. Please retry in a moment.") from exc

    logger.info("Subscription reconciled immediately via confirm-session: user_id=%s plan_type=%s session_id=%s (triggered by success.html, ahead of webhook)", current_user.user_id, plan_type, session_id)
    response.update({"confirmed": True, "status": "confirmed", "plan_type": plan_type, "subscription_status": subscription_status or "active", "subscription_expires_at": subscription_expires_at})
    return response


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(current_user: AuthUser = Depends(require_auth)) -> ProfileResponse:
    fields = "id,user_id,email,full_name,plan_type,subscription_expires_at,created_at,updated_at"
    result = supabase.table("profiles").select(fields).eq("user_id", current_user.user_id).execute()
    if not result.data:
        result = supabase.table("profiles").insert({"user_id": current_user.user_id, "email": current_user.email, "plan_type": "free"}).execute()
    return ProfileResponse(**result.data[0])


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
    _require_stripe_secret_key()
    data = order.data[0]; metadata = {"order_id": order_id, "business_id": business.data[0]["id"], "owner_id": current_user.user_id}
    try:
        session = stripe_service.create_checkout_session(amount=data["total"], product_name=f"ConversaPay order {data.get('order_number', order_id)}", currency=data.get("currency", "ILS"), mode="payment", customer_email=request.get("customer_email") or current_user.email, metadata=metadata)
    except ValueError as exc:
        logger.error("Invalid order checkout session request (order_id=%s): %s", order_id, exc)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except StripeServiceError as exc:
        logger.error("Order checkout session creation failed (order_id=%s): %s", order_id, exc)
        raise HTTPException(_stripe_service_error_status(exc), str(exc)) from exc
    payment = supabase.table("payments").insert({"business_id": business.data[0]["id"], "order_id": order_id, "amount": data["total"], "currency": data.get("currency", "ILS"), "status": "pending", "customer_email": request.get("customer_email") or current_user.email, "customer_name": request.get("customer_name"), "metadata": {"provider": "stripe", "session_id": session["session_id"], "mode": session["mode"]}}).execute()
    return {**session, "provider": "stripe", "payment_id": payment.data[0]["id"] if payment.data else None}


@router.get("/success")
async def payment_success(session_id: str | None = None) -> dict[str, Any]:
    return {"status": "pending_confirmation", "provider": "stripe", "session_id": session_id}

@router.get("/canceled")
async def payment_canceled() -> dict[str, str]:
    return {"status": "canceled", "provider": "stripe"}

@router.get("", response_model=list[PaymentResponse])
async def get_payments(business_id: str, current_user: AuthUser = Depends(require_auth)) -> list[PaymentResponse]:
    business = supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()
    if not business.data: raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    result = supabase.table("payments").select("*").eq("business_id", business.data[0]["id"]).order("created_at", desc=True).execute()
    return [PaymentResponse(**item) for item in (result.data or [])]

@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str, current_user: AuthUser = Depends(require_auth)) -> PaymentResponse:
    result = supabase.table("payments").select("*").eq("id", payment_id).execute()
    if not result.data: raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    item = result.data[0]
    if not supabase.table("businesses").select("id").eq("id", item["business_id"]).eq("owner_id", current_user.user_id).execute().data: raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    return PaymentResponse(**item)

@router.get("/wordpress-plugin/{business_id}")
async def get_wordpress_plugin(business_id: str, current_user: AuthUser = Depends(require_auth)) -> Response:
    business = supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()
    if not business.data: raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    path = Path(__file__).parent.parent / "templates" / "conversapay-chat.php"
    if not path.exists(): raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Plugin file not found")
    content = path.read_text(encoding="utf-8").replace("{{BUSINESS_ID}}", business_id).replace("{{FRONTEND_URL}}", settings.FRONTEND_URL)
    return Response(content=content.encode(), media_type="application/x-httpd-php", headers={"Content-Disposition": f"attachment; filename=conversapay-chat-{business_id}.php"})
