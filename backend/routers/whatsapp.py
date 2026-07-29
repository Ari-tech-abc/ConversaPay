"""WhatsApp Cloud API webhook for PREMIUM accounts."""
import logging
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from supabase import create_client, Client
from backend.config import settings
from backend.services.gemini_service import gemini_service
from backend.services.session_service import session_service
from backend.services.whatsapp_security import decrypt_secret, encrypt_secret, secret_hash
logger=logging.getLogger(__name__); router=APIRouter(prefix="/webhooks/whatsapp",tags=["whatsapp-webhook"]); supabase:Client=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)
async def send_whatsapp_message(to_number:str,text:str,access_token:str,phone_number_id:str)->bool:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response=await client.post(f"https://graph.facebook.com/v20.0/{phone_number_id}/messages",headers={"Authorization":f"Bearer {access_token}"},json={"messaging_product":"whatsapp","to":to_number,"type":"text","text":{"body":text}})
        return response.is_success
    except Exception: logger.exception("WhatsApp send failed"); return False
def _premium(profile:dict)->bool: return profile.get("plan_type")=="premium"
@router.get("",response_class=PlainTextResponse)
async def verify_webhook(request:Request):
    if request.query_params.get("hub.mode")!="subscribe": raise HTTPException(status_code=403,detail="Invalid mode")
    token=request.query_params.get("hub.verify_token"); challenge=request.query_params.get("hub.challenge")
    hashed=secret_hash(token)
    result=supabase.table("profiles").select("user_id,plan_type").eq("whatsapp_verify_token_hash",hashed).eq("plan_type","premium").maybe_single().execute()
    if not result.data:
        result=supabase.table("profiles").select("user_id,plan_type").eq("whatsapp_verify_token",token).eq("plan_type","premium").maybe_single().execute()
        if result.data:
            supabase.table("profiles").update({"whatsapp_verify_token_encrypted":encrypt_secret(token),"whatsapp_verify_token_hash":hashed,"whatsapp_verify_token":None}).eq("user_id",result.data["user_id"]).execute()
    if not result.data or not _premium(result.data): raise HTTPException(status_code=403,detail="Verification token not found")
    return PlainTextResponse(content=challenge or "")
@router.post("",response_class=JSONResponse)
async def handle_whatsapp_webhook(request:Request):
    try:
        payload=await request.json(); value=((payload.get("entry") or [{}])[0].get("changes") or [{}])[0].get("value") or {}; phone_id=(value.get("metadata") or {}).get("phone_number_id"); message=(value.get("messages") or [{}])[0]
        if not phone_id or message.get("type")!="text": return {"status":"ok"}
        profile_result=supabase.table("profiles").select("user_id,plan_type,whatsapp_access_token_encrypted,whatsapp_access_token").eq("whatsapp_phone_number_id",phone_id).eq("plan_type","premium").maybe_single().execute(); profile=profile_result.data
        if not profile or not _premium(profile): return {"status":"ok"}
        access_token=decrypt_secret(profile.get("whatsapp_access_token_encrypted"))
        if not access_token and profile.get("whatsapp_access_token"):
            access_token=profile["whatsapp_access_token"]; supabase.table("profiles").update({"whatsapp_access_token_encrypted":encrypt_secret(access_token),"whatsapp_access_token":None}).eq("user_id",profile["user_id"]).execute()
        customer_phone=message.get("from"); text=(message.get("text") or {}).get("body","")
        if not customer_phone or not text or not access_token: return {"status":"ok"}
        business_result=supabase.table("businesses").select("*").eq("owner_id",profile["user_id"]).eq("is_active",True).limit(1).execute()
        if not business_result.data:return {"status":"ok"}
        business=business_result.data[0]; conversation=await session_service.get_or_create_conversation(business_id=business["id"],session_id=f"whatsapp_{customer_phone}",channel="whatsapp"); customer=await session_service.get_or_create_customer(business_id=business["id"],phone=customer_phone,name=None,email=None); products=supabase.table("products").select("*").eq("business_id",business["id"]).eq("is_active",True).execute().data or []; history=await session_service.get_conversation_history(conversation_id=conversation["id"],limit=20); context={"name":customer.get("name"),"email":customer.get("email"),"phone":customer.get("phone")} if customer else None
        await session_service.add_message(conversation_id=conversation["id"],role="user",content=text); answer=await gemini_service.chat(business_id=business["id"],session_id=conversation["session_id"],message=text,business_data=business,products=products,customer_context=context,conversation_history=[{"role":m["role"],"content":m["content"]} for m in history]); await session_service.add_message(conversation_id=conversation["id"],role="assistant",content=answer.get("response",""),intent=answer.get("intent")); await send_whatsapp_message(customer_phone,answer.get("response",""),access_token,phone_id); return {"status":"ok"}
    except Exception: logger.exception("WhatsApp webhook processing failed"); return {"status":"ok"}
