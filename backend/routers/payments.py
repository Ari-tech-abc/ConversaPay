"""Stripe-backed payment and subscription routes."""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from supabase import Client, create_client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import PaymentResponse, ProfileResponse, SubscriptionCreate, SubscriptionResponse
from backend.services.stripe_service import StripeServiceError, stripe_service

logger = logging.getLogger(__name__)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
router = APIRouter(prefix="/payments", tags=["payments"])
PLAN_PRICES = {"pro": 200, "premium": 350}
PLAN_PRICE_IDS = {"pro": settings.STRIPE_PRO_PRICE_ID, "premium": settings.STRIPE_PREMIUM_PRICE_ID}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _period_end_iso(timestamp: Any) -> str | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(int(timestamp), timezone.utc).isoformat()


def _update_profile_plan(
    user_id: str,
    *,
    plan_type: str,
    subscription_expires_at: str | None,
    subscription_id: str | None = None,
) -> None:
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    end_date = subscription_expires_at or (now_dt + timedelta(days=30)).isoformat()
    payload: dict[str, Any] = {
        "plan_type": plan_type,
        "subscription_status": "active",
        "subscription_start_date": now,
        "subscription_end_date": end_date,
        "subscription_expires_at": end_date,
        "auto_renew": True,
        "updated_at": now,
    }
    if subscription_id:
        payload["stripe_subscription_id"] = subscription_id
    supabase.table("profiles").update(payload).eq("user_id", user_id).execute()
    try:
        supabase.table("businesses").update({"subscription_tier": plan_type, "subscription_status": "active"}).eq("owner_id", user_id).execute()
    except Exception as exc:
        logger.warning("Profile was upgraded but business tier sync failed for user %s: %s", user_id, exc)


def _mark_order_as_paid(order_id: str, *, payment_status: str, metadata_updates: dict[str, Any] | None = None, paid: bool = False) -> None:
    now = _utc_now_iso()
    order_status = "paid" if paid else "pending"
    order_payment_status = "paid" if paid else payment_status
    supabase.table("orders").update({"status": order_status, "payment_status": order_payment_status, "updated_at": now}).eq("id", order_id).execute()
    payment_result = supabase.table("payments").select("id, metadata").eq("order_id", order_id).order("created_at", desc=True).limit(1).execute()
    if not payment_result.data:
        return
    payment_row = payment_result.data[0]
    metadata = dict(payment_row.get("metadata") or {})
    metadata.update(metadata_updates or {})
    update_payload: dict[str, Any] = {"status": payment_status, "metadata": metadata, "updated_at": now}
    if paid:
        update_payload["paid_at"] = now
    supabase.table("payments").update(update_payload).eq("id", payment_row["id"]).execute()


@router.post("/create-checkout-session", response_model=SubscriptionResponse)
async def create_subscription_checkout_session(request: SubscriptionCreate, current_user: AuthUser = Depends(require_auth)) -> SubscriptionResponse:
    if request.user_id != current_user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User ID mismatch")
    plan = (request.plan_type or "").lower()
    if plan not in PLAN_PRICES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PRO and PREMIUM can be purchased")
    metadata = {"user_id": current_user.user_id, "plan_type": plan}
    try:
        price_id = PLAN_PRICE_IDS.get(plan)
        if price_id:
            session = stripe_service.create_checkout_session_with_price(price_id=price_id, mode="subscription", customer_email=current_user.email, metadata=metadata)
        else:
            logger.warning("Stripe price ID for plan '%s' is not configured. Falling back to inline recurring price data.", plan)
            session = stripe_service.create_checkout_session(amount=PLAN_PRICES[plan], product_name=f"ConversaPay {plan.upper()} subscription", currency="ILS", mode="subscription", customer_email=current_user.email, metadata=metadata)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except StripeServiceError as exc:
        detail = str(exc); code = status.HTTP_500_INTERNAL_SERVER_ERROR if "not configured" in detail.lower() else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(code, detail) from exc
    return SubscriptionResponse(session_id=session["session_id"], url=session["url"], payme_sale_id=None)


@router.get("/confirm-session", response_model=dict)
async def confirm_checkout_session(session_id: str = Query(..., min_length=1), current_user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    try:
        session = stripe_service.retrieve_checkout_session(session_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except StripeServiceError as exc:
        detail = str(exc); code = status.HTTP_500_INTERNAL_SERVER_ERROR if "not configured" in detail.lower() else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(code, detail) from exc
    metadata = dict(session.get("metadata") or {})
    session_user_id = metadata.get("user_id")
    if session_user_id and session_user_id != current_user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Session does not belong to the current user")
    response: dict[str, Any] = {"session_id": session.get("id"), "mode": session.get("mode"), "status": session.get("status"), "payment_status": session.get("payment_status"), "confirmed": False}
    if session.get("mode") == "subscription":
        plan = (metadata.get("plan_type") or "pro").lower(); plan = plan if plan in PLAN_PRICES else "pro"
        subscription_obj = session.get("subscription"); subscription_status = None; subscription_expires_at = None; subscription_id = None
        try:
            if isinstance(subscription_obj, str):
                subscription_id = subscription_obj
                subscription_obj = stripe_service.retrieve_subscription(subscription_obj)
            if subscription_obj:
                subscription_id = subscription_obj.get("id") or subscription_id
                subscription_status = subscription_obj.get("status"); subscription_expires_at = _period_end_iso(subscription_obj.get("current_period_end"))
        except (StripeServiceError, ValueError, AttributeError) as exc:
            logger.warning("Unable to load Stripe subscription details for session %s: %s", session_id, exc)
        if session.get("payment_status") in {"paid", "no_payment_required"} or session.get("status") == "complete" or subscription_status in {"active", "trialing"}:
            try:
                _update_profile_plan(current_user.user_id, plan_type=plan, subscription_expires_at=subscription_expires_at, subscription_id=subscription_id)
            except Exception as exc:
                logger.error("Failed to sync upgraded plan for user %s from session %s: %s", current_user.user_id, session_id, exc, exc_info=True)
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to sync upgraded plan to the user profile") from exc
            response.update({"confirmed": True, "plan_type": plan, "subscription_status": subscription_status or "active", "subscription_expires_at": subscription_expires_at or (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()})
        else:
            response.update({"plan_type": plan, "subscription_status": subscription_status, "subscription_expires_at": subscription_expires_at})
    elif session.get("mode") == "payment":
        order_id = metadata.get("order_id")
        if order_id and session.get("payment_status") == "paid":
            _mark_order_as_paid(order_id, payment_status="succeeded", metadata_updates={"provider": "stripe", "session_id": session.get("id"), "payment_intent": session.get("payment_intent"), "customer": session.get("customer")}, paid=True)
            response["confirmed"] = True
    return response


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(current_user: AuthUser = Depends(require_auth)) -> ProfileResponse:
    safe_fields = "id,user_id,email,full_name,plan_type,subscription_expires_at,created_at,updated_at"
    result = supabase.table("profiles").select(safe_fields).eq("user_id", current_user.user_id).execute()
    if not result.data:
        result = supabase.table("profiles").insert({"user_id": current_user.user_id, "email": current_user.email, "plan_type": "free"}).execute()
    return ProfileResponse(**result.data[0])


@router.post("/checkout-session", response_model=dict)
async def create_order_checkout_session(request: dict[str, Any], current_user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    business_id = request.get("business_id"); order_id = request.get("order_id")
    if not business_id or not order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing required fields: business_id, order_id")
    business = supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()
    if not business.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    order = supabase.table("orders").select("*").eq("id", order_id).eq("business_id", business.data[0]["id"]).execute()
    if not order.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    data = order.data[0]
    metadata = {"order_id": order_id, "business_id": business.data[0]["id"], "owner_id": current_user.user_id}
    try:
        session = stripe_service.create_checkout_session(amount=data["total"], product_name=f"ConversaPay order {data.get('order_number', order_id)}", currency=data.get("currency", "ILS"), mode="payment", customer_email=request.get("customer_email") or current_user.email, metadata=metadata)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except StripeServiceError as exc:
        detail = str(exc); code = status.HTTP_500_INTERNAL_SERVER_ERROR if "not configured" in detail.lower() else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(code, detail) from exc
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
    owner = supabase.table("businesses").select("id").eq("id", item["business_id"]).eq("owner_id", current_user.user_id).execute()
    if not owner.data:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    return PaymentResponse(**item)


@router.get("/wordpress-plugin/{business_id}")
async def get_wordpress_plugin(business_id: str, current_user: AuthUser = Depends(require_auth)) -> Response:
    business = supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()
    if not business.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    plugin_path = Path(__file__).parent.parent / "templates" / "conversapay-chat.php"
    if not plugin_path.exists():
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Plugin file not found")
    content = plugin_path.read_text(encoding="utf-8").replace("{{BUSINESS_ID}}", business_id).replace("{{FRONTEND_URL}}", settings.FRONTEND_URL)
    return Response(content=content.encode(), media_type="application/x-httpd-php", headers={"Content-Disposition": f"attachment; filename=conversapay-chat-{business_id}.php"})
