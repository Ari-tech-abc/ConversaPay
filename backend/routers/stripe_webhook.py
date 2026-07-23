"""Stripe webhook with official signature verification and idempotency."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import stripe
from fastapi import APIRouter, HTTPException, Request
from supabase import Client, create_client
from backend.config import settings
router = APIRouter(prefix="/webhooks/stripe", tags=["stripe-webhook"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
def _claim(event_id: str, event_type: str) -> bool:
    try: supabase.table("webhook_events").insert({"provider":"stripe","event_id":event_id,"status":event_type,"received_at":datetime.now(timezone.utc).isoformat()}).execute(); return True
    except Exception as exc:
        if any(marker in str(exc).lower() for marker in ("duplicate","unique","23505","conflict","already exists")): return False
        raise
@router.post("")
async def stripe_webhook(request: Request) -> dict[str, Any]:
    raw = await request.body(); signature = request.headers.get("stripe-signature")
    if not signature or not settings.STRIPE_WEBHOOK_SECRET: raise HTTPException(400,"Missing Stripe signature configuration")
    try: event = stripe.Webhook.construct_event(raw, signature, settings.STRIPE_WEBHOOK_SECRET)
    except ValueError as exc: raise HTTPException(400,"Invalid Stripe payload") from exc
    except stripe.error.SignatureVerificationError as exc: raise HTTPException(400,"Invalid Stripe signature") from exc
    if not _claim(str(event["id"]), str(event["type"])): return {"status":"ok","processed":False}
    obj = event["data"]["object"]; event_type = str(event["type"]); now = datetime.now(timezone.utc).isoformat()
    if event_type == "checkout.session.completed":
        metadata = dict(obj.get("metadata") or {}); order_id = metadata.get("order_id"); user_id = metadata.get("user_id")
        if order_id: supabase.table("orders").update({"status":"paid","payment_status":"paid","updated_at":now}).eq("id",order_id).execute()
        if user_id and obj.get("mode") == "subscription": supabase.table("profiles").update({"plan_type":metadata.get("plan_type","pro"),"subscription_expires_at":None,"updated_at":now}).eq("user_id",user_id).execute()
    elif event_type in {"customer.subscription.deleted","invoice.payment_failed"}:
        metadata = dict(obj.get("metadata") or {}); user_id = metadata.get("user_id")
        if user_id: supabase.table("profiles").update({"plan_type":"free","subscription_expires_at":None,"updated_at":now}).eq("user_id",user_id).execute()
    return {"status":"ok","processed":True,"event_type":event_type}
