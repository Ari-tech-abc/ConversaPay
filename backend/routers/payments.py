"""Cardcom-backed payment and subscription routes."""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from supabase import Client, create_client

from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import PaymentResponse, ProfileResponse, SubscriptionCreate
from backend.services.cardcom_service import CardcomError, cardcom_service

logger = logging.getLogger(__name__)
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
router = APIRouter(prefix="/payments", tags=["payments"])
PLAN_PRICES = {"pro": 200, "premium": 350}


@router.post("/create-checkout-session", response_model=dict)
async def create_subscription_checkout_session(request: SubscriptionCreate, current_user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    if request.user_id != current_user.user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "User ID mismatch")
    plan = (request.plan_type or "").lower()
    if plan not in PLAN_PRICES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only PRO and PREMIUM can be purchased")
    try:
        url = await cardcom_service.create_payment_page(
            amount=PLAN_PRICES[plan],
            product_name=f"ConversaPay {plan.upper()} subscription",
            currency="ILS",
            return_value=f"subscription:{current_user.user_id}:{plan}",
        )
    except (CardcomError, ValueError) as exc:
        logger.error("Cardcom subscription checkout failed: %s", exc, exc_info=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Unable to create Cardcom checkout") from exc
    return {"session_id": url, "url": url, "provider": "cardcom", "plan_type": plan}


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(current_user: AuthUser = Depends(require_auth)) -> ProfileResponse:
    result = supabase.table("profiles").select("*").eq("user_id", current_user.user_id).execute()
    if not result.data:
        result = supabase.table("profiles").insert({"user_id": current_user.user_id, "email": current_user.email, "plan_type": "free"}).execute()
    return ProfileResponse(**result.data[0])


@router.post("/checkout-session", response_model=dict)
async def create_order_checkout_session(request: dict[str, Any], current_user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    business_id = request.get("business_id")
    order_id = request.get("order_id")
    if not business_id or not order_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing required fields: business_id, order_id")
    business = supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()
    if not business.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Business not found")
    order = supabase.table("orders").select("*").eq("id", order_id).eq("business_id", business.data[0]["id"]).execute()
    if not order.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
    order_data = order.data[0]
    amount = order_data.get("total")
    if amount is None or float(amount) <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Order has no valid total amount")
    try:
        url = await cardcom_service.create_payment_page(amount, f"ConversaPay order {order_data.get('order_number', order_id)}", order_data.get("currency", "ILS"), order_id)
    except (CardcomError, ValueError) as exc:
        logger.error("Cardcom order checkout failed: %s", exc, exc_info=True)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Unable to create Cardcom checkout") from exc
    payment = supabase.table("payments").insert({"business_id": business.data[0]["id"], "order_id": order_id, "amount": amount, "currency": order_data.get("currency", "ILS"), "status": "pending", "customer_email": request.get("customer_email"), "customer_name": request.get("customer_name"), "metadata": {"provider": "cardcom"}}).execute()
    return {"session_id": url, "url": url, "provider": "cardcom", "payment_id": payment.data[0]["id"] if payment.data else None}


@router.get("/success")
async def payment_success(low_profile_code: str | None = None, LowProfileCode: str | None = None) -> dict[str, Any]:
    return {"status": "pending_confirmation", "provider": "cardcom", "low_profile_code": low_profile_code or LowProfileCode}


@router.get("/canceled")
async def payment_canceled() -> dict[str, str]:
    return {"status": "canceled", "provider": "cardcom"}


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
