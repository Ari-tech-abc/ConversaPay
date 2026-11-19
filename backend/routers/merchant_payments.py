"""Authenticated OAuth connection to the merchant's existing Stripe account."""
import asyncio
import hashlib
import secrets
from datetime import datetime,timedelta,timezone
from uuid import UUID
import stripe
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import RedirectResponse
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser,require_auth,require_business_owner_for_business_id
from backend.services.stripe_service import stripe_service

router=APIRouter(prefix="/merchant-payments",tags=["merchant-payments"])
supabase=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)

@router.get("/status")
def status(business_id:UUID,user:AuthUser=Depends(require_auth)):
    bid=require_business_owner_for_business_id(str(business_id),user)
    rows=supabase.table("payment_accounts").select("stripe_account_id,status").eq("business_id",bid).eq("provider","stripe").neq("status","revoked").limit(1).execute().data or []
    ready=False
    if rows:
        try:
            stripe_service._ensure_configured()
            account=stripe.Account.retrieve(rows[0]["stripe_account_id"])
            ready=account.get("charges_enabled") is True and account.get("payouts_enabled") is True
        except Exception:
            raise HTTPException(503,"merchant_status_unavailable") from None
    return {"connected":bool(rows),"ready":ready,"provider":"stripe","connection_available":bool(settings.STRIPE_CONNECT_CLIENT_ID and settings.STRIPE_CONNECT_WEBHOOK_SECRET)}

@router.post("/connect")
def connect(business_id:UUID,user:AuthUser=Depends(require_auth)):
    bid=require_business_owner_for_business_id(str(business_id),user)
    if not settings.STRIPE_CONNECT_CLIENT_ID or not settings.STRIPE_CONNECT_WEBHOOK_SECRET:
        raise HTTPException(503,"merchant_connect_not_configured")
    state=secrets.token_urlsafe(32)
    supabase.table("merchant_connect_states").insert({"token_hash":hashlib.sha256(state.encode()).hexdigest(),"business_id":bid,"user_id":user.user_id,"expires_at":(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}).execute()
    url=stripe.OAuth.authorize_url(client_id=settings.STRIPE_CONNECT_CLIENT_ID,scope="read_write",state=state,redirect_uri=settings.BASE_URL.rstrip('/')+settings.API_PREFIX+"/merchant-payments/callback")
    return {"url":url}

@router.get("/callback",include_in_schema=False)
def callback(state:str=Query(...,max_length=128),code:str=Query(...,max_length=1024)):
    rows=supabase.rpc("consume_merchant_connect_state",{"p_hash":hashlib.sha256(state.encode()).hexdigest()}).execute().data or []
    if not rows:raise HTTPException(400,"merchant_connection_expired")
    entry=rows[0]
    business=supabase.table("businesses").select("id").eq("id",entry["business_id"]).eq("owner_id",entry["user_id"]).eq("is_active",True).execute().data
    if not business:raise HTTPException(403,"merchant_business_unavailable")
    try:
        stripe_service._ensure_configured()
        response=stripe.OAuth.token(grant_type="authorization_code",code=code)
        account=stripe.Account.retrieve(response["stripe_user_id"])
        if account.get("id")!=response["stripe_user_id"]:raise ValueError()
        active=account.get("charges_enabled") is True and account.get("payouts_enabled") is True
        supabase.rpc("bind_merchant_account",{"p_business_id":entry["business_id"],"p_user_id":entry["user_id"],"p_account":account["id"],"p_ready":active}).execute()
    except Exception:
        raise HTTPException(502,"merchant_connection_failed") from None
    return RedirectResponse("/settings?merchant=connected",status_code=303)
