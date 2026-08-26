"""WhatsApp Cloud API webhook for PREMIUM accounts."""
from __future__ import annotations

import hashlib
import hmac
import logging

import httpx
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, JSONResponse
from supabase import create_client, Client

from backend.config import settings
from backend.services.gemini_service import gemini_service
from backend.services.session_service import session_service
from backend.services.whatsapp_security import decrypt_secret, encrypt_secret, secret_hash

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp-webhook"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _meta_app_secret() -> str | None:
    return (settings.META_APP_SECRET or settings.WHATSAPP_APP_SECRET or "").strip() or None


def _verify_meta_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Validate Meta's X-Hub-Signature-256 over the exact request bytes."""
    app_secret = _meta_app_secret()
    if not app_secret or not signature_header:
        return False
    scheme, separator, supplied = signature_header.partition("=")
    if scheme.lower() != "sha256" or not separator or not supplied:
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(supplied.strip().lower(), expected)


async def send_whatsapp_message(to_number: str, text: str, access_token: str, phone_number_id: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://graph.facebook.com/v20.0/{phone_number_id}/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"messaging_product": "whatsapp", "to": to_number, "type": "text", "text": {"body": text}},
            )
        return response.is_success
    except Exception:
        # Never include access tokens or provider response bodies in logs.
        logger.exception("WhatsApp send failed")
        return False


def _premium(profile: dict) -> bool:
    return profile.get("plan_type") == "premium"


@router.get("", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    if request.query_params.get("hub.mode") != "subscribe":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    hashed = secret_hash(token)
    result = supabase.table("profiles").select("user_id,plan_type").eq("whatsapp_verify_token_hash", hashed).eq("plan_type", "premium").maybe_single().execute()
    if not result.data:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token not found")
    return PlainTextResponse(content=challenge or "")


@router.post("", response_class=JSONResponse)
async def handle_whatsapp_webhook(request: Request):
    raw_body = await request.body()
    if not _verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Meta webhook signature")
    try:
        payload = await request.json()
        value = ((payload.get("entry") or [{}])[0].get("changes") or [{}])[0].get("value") or {}
        phone_id = (value.get("metadata") or {}).get("phone_number_id")
        message = (value.get("messages") or [{}])[0]
        if not phone_id or message.get("type") != "text":
            return {"status": "ok"}

        profile_result = supabase.table("profiles").select("user_id,plan_type,whatsapp_access_token_encrypted").eq("whatsapp_phone_number_id", phone_id).eq("plan_type", "premium").maybe_single().execute()
        profile = profile_result.data
        if not profile or not _premium(profile):
            return {"status": "ok"}
        access_token = decrypt_secret(profile.get("whatsapp_access_token_encrypted"))
        customer_phone = message.get("from")
        text = (message.get("text") or {}).get("body", "")
        if not customer_phone or not text or not access_token:
            return {"status": "ok"}

        business_result = supabase.table("businesses").select("*").eq("owner_id", profile["user_id"]).eq("is_active", True).limit(1).execute()
        if not business_result.data:
            return {"status": "ok"}
        business = business_result.data[0]
        conversation = await session_service.get_or_create_conversation(business_id=business["id"], session_id=f"whatsapp_{customer_phone}", channel="whatsapp")
        customer = await session_service.get_or_create_customer(business_id=business["id"], phone=customer_phone, name=None, email=None)
        products = supabase.table("products").select("*").eq("business_id", business["id"]).eq("is_active", True).execute().data or []
        history = await session_service.get_conversation_history(conversation_id=conversation["id"], limit=20)
        context = {"name": customer.get("name"), "email": customer.get("email"), "phone": customer.get("phone")} if customer else None
        await session_service.add_message(conversation_id=conversation["id"], role="user", content=text)
        answer = await gemini_service.chat(business_id=business["id"], session_id=conversation["session_id"], message=text, business_data=business, products=products, customer_context=context, conversation_history=[{"role": m["role"], "content": m["content"]} for m in history])
        await session_service.add_message(conversation_id=conversation["id"], role="assistant", content=answer.get("response", ""), intent=answer.get("intent"))
        await send_whatsapp_message(customer_phone, answer.get("response", ""), access_token, phone_id)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("WhatsApp webhook processing failed")
        return {"status": "ok"}
