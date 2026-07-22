"""Public widget configuration with domain and API-key enforcement."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import hashlib, logging
from supabase import create_client
from backend.config import settings
logger=logging.getLogger(__name__)
router=APIRouter(tags=["widget"])
def host(value):
    value=(value or "").strip()
    if "://" in value: value=value.split("://",1)[1]
    return value.split("/",1)[0].split(":",1)[0].lower().rstrip(".")
def plan_info(business_id, client):
    b=client.table("businesses").select("owner_id").eq("id",business_id).maybe_single().execute()
    if not b.data:return {"plan_type":"free","active":False}
    p=client.table("profiles").select("plan_type,subscription_expires_at").eq("user_id",b.data["owner_id"]).maybe_single().execute(); row=p.data or {}; plan=row.get("plan_type","free"); active=True
    if plan in ("pro","premium") and row.get("subscription_expires_at"):
        try:
            exp=datetime.fromisoformat(str(row["subscription_expires_at"]).replace("Z","+00:00")); exp=exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc); active=exp>datetime.now(timezone.utc)
        except ValueError: active=False
    return {"plan_type":plan,"active":active}
def valid_key(client,business_id,raw):
    if not raw:return False
    row=client.table("api_keys").select("id").eq("business_id",business_id).eq("key_hash",hashlib.sha256(raw.encode()).hexdigest()).eq("is_active",True).maybe_single().execute()
    if not row.data:return False
    client.table("api_keys").update({"last_used_at":datetime.now(timezone.utc).isoformat()}).eq("id",row.data["id"]).execute(); return True
@router.get("/config/{business_id}")
async def get_widget_config(business_id:str, request:Request):
    try:
        client=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY); demo=business_id=="conversapay"; query=client.table("businesses").select("id,settings,bot_name,greeting_message,theme_colors") if demo else client.table("businesses").select("settings,bot_name,greeting_message,theme_colors"); result=(query.eq("business_id",business_id) if demo else query.eq("id",business_id)).maybe_single().execute()
        if not result.data:raise HTTPException(404,"Business not found")
        business=result.data; actual_id=business.get("id",business_id); plan=plan_info(actual_id,client); origin=host(request.headers.get("origin") or request.headers.get("referer") or request.headers.get("host")); own=host(settings.BASE_URL); internal=origin in {"localhost","127.0.0.1",own,"conversapay.org"} or origin.endswith(".conversapay.org")
        if plan["plan_type"] in ("pro","premium") and not plan["active"]:raise HTTPException(403,"Subscription has expired")
        if not internal and plan["plan_type"]=="free":raise HTTPException(403,"External widget embeds require PRO or PREMIUM")
        if not internal and not valid_key(client,actual_id,request.headers.get("X-Widget-Key")):raise HTTPException(401,"Valid widget API key required")
        return JSONResponse(content={"business_id":business_id,"bot_name":business.get("bot_name","AI Assistant"),"greeting_message":business.get("greeting_message","Hello! How can I help you today?"),"avatar_url":None,"theme_colors":business.get("theme_colors") or {"primary":"#A855F7","secondary":"#00D9FF","background":"#0B0F19"},"features":{"checkout":plan["plan_type"] in ("pro","premium"),"product_catalog":True,"plan_type":plan["plan_type"]}})
    except HTTPException:raise
    except Exception as exc:logger.error("Widget config error: %s",exc,exc_info=True); raise HTTPException(500,"Failed to load widget configuration")
@router.get("/health")
async def widget_health():return {"status":"healthy","service":"conversapay-widget","version":"2.0.0"}
