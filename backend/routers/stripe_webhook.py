"""Stripe webhook: event payload is authoritative and processing stays local."""
from __future__ import annotations
import logging
from typing import Any
import stripe
from fastapi import APIRouter, HTTPException, Request
from supabase import Client, create_client
from backend.config import settings
from backend.services.subscription_service import apply_subscription_state, mark_webhook_failed, mark_webhook_processed, period_end_iso
logger=logging.getLogger(__name__); router=APIRouter(prefix="/webhooks/stripe",tags=["stripe-webhook"]); supabase:Client=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)
if settings.STRIPE_SECRET_KEY: stripe.api_key=settings.STRIPE_SECRET_KEY

def _claim(event_id,event_type):
    result=supabase.rpc("claim_webhook_event",{"p_provider":"stripe","p_event_id":event_id,"p_event_type":event_type}).execute(); value=result.data
    if isinstance(value,list): value=value[0] if value else False
    if isinstance(value,dict): value=next(iter(value.values()),False)
    return value is True or str(value).lower()=="true"

def _lookup_user(customer_id):
    if not customer_id:return None
    result=supabase.table("profiles").select("user_id").eq("stripe_customer_id",customer_id).limit(1).execute()
    return result.data[0]["user_id"] if result.data else None

def _update_order(order_id:str,*,order_status:str,payment_status:str,metadata_updates:dict[str,Any],paid:bool=False)->None:
    result=supabase.rpc("update_order_payment_atomic",{"p_order_id":order_id,"p_order_status":order_status,"p_payment_status":payment_status,"p_metadata_updates":metadata_updates,"p_paid":paid}).execute()
    if result.data is not True and str(result.data).lower() not in {"true","[true]"}: raise RuntimeError("Atomic order/payment update was not confirmed")

def _apply_from_event(*,user_id,plan_type,subscription_id,customer_id,context):
    apply_subscription_state(user_id=user_id or _lookup_user(customer_id),plan_type=plan_type,subscription_status=context.get("status"),subscription_expires_at=context.get("current_period_end"),customer_id=customer_id,cancel_at_period_end=context.get("cancel_at_period_end",False),stripe_subscription_id=subscription_id)

def _subscription_context(obj:dict,subscription_id:str|None=None)->dict:
    return {"id":obj.get("id") or subscription_id,"metadata":dict(obj.get("metadata") or {}),"status":obj.get("status"),"current_period_end":period_end_iso(obj.get("current_period_end")),"customer":obj.get("customer"),"cancel_at_period_end":bool(obj.get("cancel_at_period_end",False))}

@router.post("")
async def stripe_webhook(request:Request)->dict[str,Any]:
    raw=await request.body(); signature=request.headers.get("stripe-signature")
    if not signature or not settings.STRIPE_WEBHOOK_SECRET: raise HTTPException(400,"Missing Stripe signature configuration")
    try: event=stripe.Webhook.construct_event(raw,signature,settings.STRIPE_WEBHOOK_SECRET)
    except ValueError as exc: raise HTTPException(400,"Invalid Stripe payload") from exc
    except stripe.error.SignatureVerificationError as exc: raise HTTPException(400,"Invalid Stripe signature") from exc
    event_id,event_type=str(event["id"]),str(event["type"])
    try:
        if not _claim(event_id,event_type): return {"status":"ok","processed":False,"duplicate":True}
        obj=stripe.util.convert_to_stripe_object(event["data"]["object"]) if isinstance(event["data"]["object"],dict) else event["data"]["object"]
        obj=stripe_service_obj(obj); metadata=dict(obj.get("metadata") or {})
        if event_type in {"checkout.session.completed","checkout.session.async_payment_succeeded"}:
            order_id=metadata.get("order_id")
            if order_id: _update_order(order_id,order_status="paid",payment_status="succeeded",paid=True,metadata_updates={"provider":"stripe","session_id":obj.get("id"),"payment_intent":obj.get("payment_intent"),"customer":obj.get("customer")})
            if obj.get("mode")=="subscription":
                subscription_id=obj.get("subscription") if isinstance(obj.get("subscription"),str) else None; context=_subscription_context(obj,subscription_id); cm=context.get("metadata") or {}
                _apply_from_event(user_id=cm.get("user_id") or metadata.get("user_id"),plan_type=cm.get("plan_type") or metadata.get("plan_type"),subscription_id=subscription_id,customer_id=obj.get("customer"),context=context)
        elif event_type=="checkout.session.async_payment_failed":
            order_id=metadata.get("order_id")
            if order_id:_update_order(order_id,order_status="pending",payment_status="failed",metadata_updates={"provider":"stripe","session_id":obj.get("id")})
        elif event_type.startswith("customer.subscription."):
            context=_subscription_context(obj); context["status"]="canceled" if event_type=="customer.subscription.deleted" else context.get("status"); cm=context.get("metadata") or {}
            _apply_from_event(user_id=cm.get("user_id"),plan_type=cm.get("plan_type"),subscription_id=context.get("id"),customer_id=obj.get("customer"),context=context)
        elif event_type in {"invoice.paid","invoice.payment_succeeded","invoice.payment_failed"}:
            context=_subscription_context(obj,obj.get("subscription")); cm=context.get("metadata") or {}
            if event_type!="invoice.payment_failed" or context.get("status") in {"canceled","unpaid","incomplete_expired"}:
                _apply_from_event(user_id=cm.get("user_id"),plan_type=cm.get("plan_type"),subscription_id=context.get("id"),customer_id=context.get("customer") or obj.get("customer"),context=context)
        elif event_type in {"charge.refunded","charge.refund.updated"}:
            user_id=_lookup_user(obj.get("customer"))
            if user_id: apply_subscription_state(user_id=user_id,plan_type="free",subscription_status="canceled",subscription_expires_at=None,customer_id=obj.get("customer"),cancel_at_period_end=False)
        mark_webhook_processed(event_id); return {"status":"ok","processed":True,"event_type":event_type}
    except Exception as exc:
        try: mark_webhook_failed(event_id,str(exc))
        except Exception: logger.exception("Failed to mark webhook event failed")
        logger.exception("Stripe webhook processing failed for %s",event_id); raise HTTPException(500,"Webhook processing failed") from exc

def stripe_service_obj(obj):
    if isinstance(obj,dict): return obj
    if hasattr(obj,"to_dict_recursive"): return obj.to_dict_recursive()
    if hasattr(obj,"to_dict"): return obj.to_dict()
    return obj
