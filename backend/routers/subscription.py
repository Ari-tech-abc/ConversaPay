"""Subscription status and cancellation APIs with user-scoped profile access."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import create_client
from backend.config import settings
from backend.services.billing_reconciliation import active_plan_from_row
from backend.middleware.auth import AuthUser, require_auth
from backend.services.subscription_gateway import get_subscription_gateway, SubscriptionGatewayUnavailable
from backend.services.subscription_checkout import billing_rpc, BillingConflict, BillingStorageUnavailable
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/subscription", tags=["subscription"])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
class CancellationRequest(BaseModel): reason: str = Field(..., min_length=3, max_length=4000); request_refund: bool = True
class PlanChangeRequest(BaseModel):
    plan_type: str = Field(..., pattern='^(pro|premium)$')
def _parse_datetime(value: Any) -> datetime | None:
    if not value: return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")); return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError): return None
def _status_payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        get_subscription_gateway().ensure_ready()
        checkout_available = True
    except SubscriptionGatewayUnavailable:
        checkout_available = False
    now = datetime.now(timezone.utc); plan = str(row.get("plan_type") or "free").lower(); end_date = _parse_datetime(row.get("subscription_end_date") or row.get("subscription_expires_at")); start_date = _parse_datetime(row.get("subscription_start_date")); expired = bool(end_date and end_date <= now and plan != "free"); effective_plan = active_plan_from_row(row)
    return {"plan_type": effective_plan, "stored_plan_type": plan, "subscription_status": "expired" if expired else (row.get("subscription_status") or "active"), "subscription_start_date": start_date.isoformat() if start_date else None, "subscription_end_date": end_date.isoformat() if end_date else None, "subscription_expires_at": end_date.isoformat() if end_date else None, "auto_renew": bool(row.get("auto_renew", True)), "remaining_days": max(0, (end_date.date() - now.date()).days) if end_date else 0, "is_paid": effective_plan in {"pro", "premium"}, "stripe_subscription_id": row.get("stripe_subscription_id"), "subscription_provider": row.get("subscription_provider") or settings.SUBSCRIPTION_PROVIDER, "provider_subscription_id": row.get("provider_subscription_id") or row.get("stripe_subscription_id"), "plan_change_supported": False, "checkout_available": checkout_available, "can_cancel": bool(row.get("provider_subscription_id") or row.get("stripe_subscription_id")) and bool(row.get("auto_renew", True)) and row.get("subscription_status") not in {"canceled", "incomplete_expired"}}
def _load_profile(user_id: str) -> dict[str, Any]:
    try:
        result = supabase.table("profiles").select("user_id,email,full_name,plan_type,subscription_status,subscription_start_date,subscription_end_date,subscription_expires_at,auto_renew,stripe_subscription_id,subscription_provider,provider_subscription_id,provider_customer_id").eq("user_id", user_id).limit(1).execute()
    except Exception:
        logger.warning("Billing profile storage is unavailable")
        raise HTTPException(503, "billing_storage_unavailable") from None
    if not result.data: raise HTTPException(404, "Profile not found")
    return result.data[0]
@router.get("/status")
async def subscription_status(current_user: AuthUser = Depends(require_auth)):
    row = await asyncio.to_thread(_load_profile, current_user.user_id)
    payload = _status_payload(row)
    payload['next_billing_at'] = payload['subscription_end_date'] if payload['auto_renew'] and row.get('subscription_status') in {'active', 'trialing'} and payload['is_paid'] else None
    payload['payment_action_required'] = row.get('subscription_status') in {'past_due', 'unpaid', 'incomplete'}
    payload['plan_change_request_available'] = payload['is_paid'] and payload['auto_renew'] and row.get('subscription_status') in {'active', 'trialing'} and bool(payload['provider_subscription_id'])
    return payload

def _management_rows(user_id):
    try:
        invoices = supabase.table('subscription_invoices').select('id,status,amount_minor,currency,period_start,period_end,occurred_at').eq('user_id', user_id).order('occurred_at', desc=True).order('id').limit(50).execute().data or []
        requests = supabase.table('subscription_plan_requests').select('id,current_plan,requested_plan,status,created_at').eq('user_id', user_id).eq('status', 'requested').limit(1).execute().data or []
        cancellations = supabase.table('subscription_cancellations').select('id,status,created_at,confirmed_at,request_refund,provider_subscription_id').eq('user_id', user_id).order('created_at', desc=True).limit(1).execute().data or []
        return {'invoices': invoices, 'plan_change_request': next(iter(requests), None), 'cancellation': next(iter(cancellations), None)}
    except Exception:
        raise HTTPException(503, 'billing_storage_unavailable') from None

@router.get('/history')
async def subscription_history(current_user: AuthUser = Depends(require_auth)):
    return await asyncio.to_thread(_management_rows, current_user.user_id)

@router.post('/plan-change')
async def request_plan_change(payload: PlanChangeRequest, current_user: AuthUser = Depends(require_auth)):
    try:
        request = await asyncio.to_thread(billing_rpc, supabase, 'request_subscription_plan_change', {'p_user_id': current_user.user_id, 'p_plan': payload.plan_type})
        if request.get('error'):
            raise HTTPException(409, request['error'])
        return {'request': request, 'provider_confirmed': False, 'effective_at': None, 'charge_created': False}
    except BillingStorageUnavailable:
        raise HTTPException(503, 'billing_storage_unavailable') from None

@router.delete('/plan-change/{request_id}')
async def withdraw_plan_change(request_id: str, current_user: AuthUser = Depends(require_auth)):
    from uuid import UUID
    try:
        request_id = str(UUID(request_id))
    except ValueError:
        raise HTTPException(422, 'Invalid request ID') from None
    try:
        result = await asyncio.to_thread(lambda: supabase.table('subscription_plan_requests').update({'status': 'withdrawn', 'updated_at': datetime.now(timezone.utc).isoformat()}).eq('id', request_id).eq('user_id', current_user.user_id).eq('status', 'requested').execute())
    except Exception:
        raise HTTPException(503, 'billing_storage_unavailable') from None
    if not result.data:
        raise HTTPException(404, 'Request not found')
    return {'withdrawn': True}
@router.post("/cancel")
async def cancel_subscription(payload: CancellationRequest, current_user: AuthUser = Depends(require_auth)):
    row = await asyncio.to_thread(_load_profile, current_user.user_id)
    subscription_id = row.get("provider_subscription_id") or row.get("stripe_subscription_id")
    if not subscription_id:
        raise HTTPException(409, "billing_subscription_missing")
    provider = row.get("subscription_provider") or "stripe"
    try:
        gateway = get_subscription_gateway(provider)
        gateway.ensure_ready()
        cancellation = await asyncio.to_thread(billing_rpc, supabase, "request_subscription_cancellation", {
            "p_user_id": current_user.user_id, "p_provider": provider, "p_subscription_id": subscription_id,
            "p_reason": payload.reason.strip(), "p_refund": payload.request_refund,
        })
        if cancellation.get("error"):
            raise BillingConflict(cancellation["error"])
        if cancellation.get("status") != "confirmed":
            await asyncio.to_thread(gateway.cancel_renewal, subscription_id, cancellation["id"])
        confirmed = await asyncio.to_thread(billing_rpc, supabase, "confirm_subscription_cancellation", {
            "p_id": cancellation["id"], "p_user_id": current_user.user_id, "p_subscription_id": subscription_id,
        })
        if confirmed.get("error"):
            raise BillingConflict(confirmed["error"])
    except BillingConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except (SubscriptionGatewayUnavailable, BillingStorageUnavailable) as exc:
        raise HTTPException(503, str(exc)) from None
    except Exception:
        logger.exception("Subscription cancellation is not yet confirmed for user %s", current_user.user_id)
        raise HTTPException(502, "billing_cancellation_unconfirmed") from None
    update = {"auto_renew": False, "subscription_status": "pending_cancellation"}
    return {**_status_payload({**row, **update}), "message": "Renewal cancellation confirmed", "cancellation_confirmed": True,
            "stripe_synced": provider == "stripe", "refund_requested": bool(confirmed.get("refund_request_id")), "refund_completed": False}
