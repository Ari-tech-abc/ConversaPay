"""Webhooks router for external integrations."""
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse
from typing import List
import logging
import hmac
from datetime import datetime
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import WebhookCreate, WebhookUpdate, WebhookResponse
from backend.services.webhook_security import require_signed_request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(request: WebhookCreate, current_user: AuthUser = Depends(require_auth)):
    try:
        business = supabase.table("businesses").select("id").eq("business_id", request.business_id).eq("owner_id", current_user.user_id).execute()
        if not business.data:
            raise HTTPException(status_code=404, detail="Business not found")
        data = {"business_id": business.data[0]["id"], "url": str(request.url), "events": request.events, "secret": request.secret, "is_active": request.is_active, "created_at": datetime.utcnow().isoformat()}
        result = supabase.table("webhooks").insert(data).execute()
        if result.data:
            return WebhookResponse(**result.data[0])
        raise HTTPException(status_code=500, detail="Failed to create webhook")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error creating webhook: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create webhook")


@router.get("", response_model=List[WebhookResponse])
async def get_webhooks(business_id: str, current_user: AuthUser = Depends(require_auth)):
    try:
        business = supabase.table("businesses").select("id").eq("business_id", business_id).eq("owner_id", current_user.user_id).execute()
        if not business.data:
            raise HTTPException(status_code=404, detail="Business not found")
        result = supabase.table("webhooks").select("*").eq("business_id", business.data[0]["id"]).order("created_at", desc=True).execute()
        return [WebhookResponse(**webhook) for webhook in (result.data or [])]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching webhooks: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch webhooks")


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(webhook_id: str, request: WebhookUpdate, current_user: AuthUser = Depends(require_auth)):
    try:
        webhook_result = supabase.table("webhooks").select("business_id").eq("id", webhook_id).execute()
        if not webhook_result.data:
            raise HTTPException(status_code=404, detail="Webhook not found")
        business = supabase.table("businesses").select("id").eq("id", webhook_result.data[0]["business_id"]).eq("owner_id", current_user.user_id).execute()
        if not business.data:
            raise HTTPException(status_code=403, detail="Access denied")
        update_data = request.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No data to update")
        result = supabase.table("webhooks").update(update_data).eq("id", webhook_id).execute()
        if result.data:
            return WebhookResponse(**result.data[0])
        raise HTTPException(status_code=500, detail="Failed to update webhook")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error updating webhook: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update webhook")


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(webhook_id: str, current_user: AuthUser = Depends(require_auth)):
    try:
        webhook_result = supabase.table("webhooks").select("business_id").eq("id", webhook_id).execute()
        if not webhook_result.data:
            raise HTTPException(status_code=404, detail="Webhook not found")
        business = supabase.table("businesses").select("id").eq("id", webhook_result.data[0]["business_id"]).eq("owner_id", current_user.user_id).execute()
        if not business.data:
            raise HTTPException(status_code=403, detail="Access denied")
        supabase.table("webhooks").delete().eq("id", webhook_id).execute()
        return None
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error deleting webhook: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete webhook")


@router.post("/whatsapp/{business_id}")
async def whatsapp_webhook(business_id: str, request: Request):
    try:
        payload = await require_signed_request(request)
        logger.info("WhatsApp webhook received for business %s", business_id)
        return {"status": "received", "bytes": len(payload)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("WhatsApp webhook error: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid webhook payload")


@router.post("/telegram/{business_id}")
async def telegram_webhook(business_id: str, request: Request):
    try:
        payload = await require_signed_request(request)
        logger.info("Telegram webhook received for business %s", business_id)
        return {"status": "received", "bytes": len(payload)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Telegram webhook error: %s", exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid webhook payload")


@router.post("/custom/{webhook_id}")
async def custom_webhook(webhook_id: str, request: Request):
    """Public custom webhook; every active endpoint must have a shared secret."""
    try:
        result = supabase.table("webhooks").select("*").eq("id", webhook_id).eq("is_active", True).maybe_single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Webhook not found")
        config = result.data
        secret = str(config.get("secret") or "")
        if not secret:
            raise HTTPException(status_code=503, detail="Webhook secret is not configured")
        payload = await require_signed_request(request, secret=secret)
        try:
            await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid webhook payload") from exc
        supabase.table("webhooks").update({"last_triggered_at": datetime.utcnow().isoformat(), "failure_count": 0}).eq("id", webhook_id).execute()
        return {"status": "success", "bytes": len(payload)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Custom webhook error: %s", exc, exc_info=True)
        try:
            row = supabase.table("webhooks").select("failure_count").eq("id", webhook_id).maybe_single().execute()
            next_count = int((row.data or {}).get("failure_count") or 0) + 1
            supabase.table("webhooks").update({"failure_count": next_count}).eq("id", webhook_id).execute()
        except Exception:
            logger.exception("Failed to update custom webhook failure count")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


@router.get("/verify")
async def verify_webhook(request: Request):
    """Verify a generic provider callback only when a shared token is configured."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode != "subscribe" or not settings.WEBHOOK_VERIFY_TOKEN or not token or not hmac.compare_digest(token, settings.WEBHOOK_VERIFY_TOKEN):
        raise HTTPException(status_code=403, detail="Verification failed")
    if not challenge:
        raise HTTPException(status_code=400, detail="Missing challenge")
    return JSONResponse(content=int(challenge) if challenge.isdigit() else challenge)
