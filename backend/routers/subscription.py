"""Subscription status and cancellation/refund request APIs."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import logging
import stripe
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscription", tags=["subscription"])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


class CancellationRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=4000)
    request_refund: bool = True


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _status_payload(row: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    plan = str(row.get("plan_type") or "free").lower()
    end_date = _parse_datetime(row.get("subscription_end_date") or row.get("subscription_expires_at"))
    start_date = _parse_datetime(row.get("subscription_start_date"))
    expired = bool(end_date and end_date <= now and plan != "free")
    effective_plan = "free" if expired else plan
    remaining_days = max(0, (end_date.date() - now.date()).days) if end_date else 0
    return {
        "plan_type": effective_plan,
        "stored_plan_type": plan,
        "subscription_status": "expired" if expired else (row.get("subscription_status") or "active"),
        "subscription_start_date": start_date.isoformat() if start_date else None,
        "subscription_end_date": end_date.isoformat() if end_date else None,
        "subscription_expires_at": end_date.isoformat() if end_date else None,
        "auto_renew": bool(row.get("auto_renew", True)) if not expired else False,
        "remaining_days": remaining_days,
        "is_paid": effective_plan in {"pro", "premium"},
        "stripe_subscription_id": row.get("stripe_subscription_id"),
    }


def _load_profile(user_id: str) -> dict[str, Any]:
    result = supabase.table("profiles").select("*").eq("user_id", user_id).limit(1).execute()
    if not result.data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    return result.data[0]


@router.get("/status")
async def subscription_status(current_user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    return _status_payload(_load_profile(current_user.user_id))


@router.post("/cancel")
async def cancel_subscription(payload: CancellationRequest, current_user: AuthUser = Depends(require_auth)) -> dict[str, Any]:
    row = _load_profile(current_user.user_id)
    current = _status_payload(row)
    if not current["is_paid"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only active paid subscriptions can be cancelled")
    if current["subscription_status"] == "pending_cancellation":
        raise HTTPException(status.HTTP_409_CONFLICT, "Cancellation is already pending")

    stripe_synced = False
    subscription_id = row.get("stripe_subscription_id")
    if subscription_id and settings.STRIPE_SECRET_KEY and not settings.STRIPE_SECRET_KEY.startswith("sk_test_EXAMPLE"):
        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY
            stripe.Subscription.modify(subscription_id, cancel_at_period_end=True)
            stripe_synced = True
        except stripe.error.StripeError as exc:
            logger.error("Stripe cancellation failed for user %s: %s", current_user.user_id, exc, exc_info=True)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Unable to cancel the recurring billing agreement") from exc

    now = datetime.now(timezone.utc).isoformat()
    update = {
        "auto_renew": False,
        "subscription_status": "pending_cancellation",
        "updated_at": now,
    }
    updated = supabase.table("profiles").update(update).eq("user_id", current_user.user_id).execute()

    try:
        supabase.table("refund_requests").insert({
            "user_id": current_user.user_id,
            "request_type": "refund_and_cancellation" if payload.request_refund else "cancellation",
            "reason": payload.reason.strip(),
            "status": "pending",
        }).execute()
    except Exception as exc:
        logger.error("Failed to record cancellation request for user %s: %s", current_user.user_id, exc, exc_info=True)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Cancellation was applied but the review request could not be recorded") from exc

    result_row = updated.data[0] if updated.data else {**row, **update}
    result = _status_payload(result_row)
    return {
        **result,
        "message": "Cancellation request received. Access remains active until the subscription end date.",
        "stripe_synced": stripe_synced,
        "refund_requested": payload.request_refund,
    }
