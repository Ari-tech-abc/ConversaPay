"""
Webhooks router for external integrations.
Handles WhatsApp, Telegram, and custom webhook endpoints.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List
import logging
import hmac
import hashlib
from datetime import datetime

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import WebhookCreate, WebhookUpdate, WebhookResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


# ============================================
# Webhook Management (Authenticated)
# ============================================

@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    request: WebhookCreate,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Create a new webhook for a business.
    """
    try:
        # Verify business ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("business_id", request.business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        business_uuid = business.data[0]['id']
        
        # Create webhook
        webhook_data = {
            "business_id": business_uuid,
            "url": str(request.url),
            "events": request.events,
            "secret": request.secret,
            "is_active": request.is_active,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("webhooks")\
            .insert(webhook_data)\
            .execute()
        
        if result.data:
            logger.info(f"Webhook created for business {request.business_id}")
            return WebhookResponse(**result.data[0])
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create webhook"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create webhook"
        )


@router.get("", response_model=List[WebhookResponse])
async def get_webhooks(
    business_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get all webhooks for a business.
    """
    try:
        # Verify business ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("business_id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        business_uuid = business.data[0]['id']
        
        # Get webhooks
        result = supabase.table("webhooks")\
            .select("*")\
            .eq("business_id", business_uuid)\
            .order("created_at", desc=True)\
            .execute()
        
        return [WebhookResponse(**webhook) for webhook in result.data] if result.data else []
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching webhooks: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch webhooks"
        )


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    request: WebhookUpdate,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Update a webhook.
    """
    try:
        # Get webhook
        webhook_result = supabase.table("webhooks")\
            .select("business_id")\
            .eq("id", webhook_id)\
            .execute()
        
        if not webhook_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook not found"
            )
        
        business_uuid = webhook_result.data[0]['business_id']
        
        # Verify ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_uuid)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Build update data
        update_data = request.model_dump(exclude_none=True)
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data to update"
            )
        
        # Update webhook
        result = supabase.table("webhooks")\
            .update(update_data)\
            .eq("id", webhook_id)\
            .execute()
        
        if result.data:
            logger.info(f"Webhook updated: {webhook_id}")
            return WebhookResponse(**result.data[0])
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update webhook"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update webhook"
        )


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Delete a webhook.
    """
    try:
        # Get webhook
        webhook_result = supabase.table("webhooks")\
            .select("business_id")\
            .eq("id", webhook_id)\
            .execute()
        
        if not webhook_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook not found"
            )
        
        business_uuid = webhook_result.data[0]['business_id']
        
        # Verify ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_uuid)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Delete webhook
        supabase.table("webhooks")\
            .delete()\
            .eq("id", webhook_id)\
            .execute()
        
        logger.info(f"Webhook deleted: {webhook_id}")
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete webhook"
        )


# ============================================
# Public Webhook Endpoints (for external integrations)
# ============================================

@router.post("/whatsapp/{business_id}")
async def whatsapp_webhook(
    business_id: str,
    request: Request
):
    """
    WhatsApp webhook endpoint.
    Receives messages from WhatsApp Business API.
    """
    try:
        # Get webhook payload
        payload = await request.json()
        
        logger.info(f"WhatsApp webhook received for business {business_id}")
        
        # TODO: Implement WhatsApp message processing
        # 1. Verify webhook signature
        # 2. Extract message from WhatsApp payload
        # 3. Find or create customer
        # 4. Create conversation
        # 5. Process with AI
        # 6. Send response back via WhatsApp API
        
        return {"status": "received"}
    
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload"
        )


@router.post("/telegram/{business_id}")
async def telegram_webhook(
    business_id: str,
    request: Request
):
    """
    Telegram webhook endpoint.
    Receives messages from Telegram Bot API.
    """
    try:
        # Get webhook payload
        payload = await request.json()
        
        logger.info(f"Telegram webhook received for business {business_id}")
        
        # TODO: Implement Telegram message processing
        # 1. Verify webhook token
        # 2. Extract message from Telegram payload
        # 3. Find or create customer
        # 4. Create conversation
        # 5. Process with AI
        # 6. Send response back via Telegram API
        
        return {"status": "received"}
    
    except Exception as e:
        logger.error(f"Telegram webhook error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload"
        )


@router.post("/custom/{webhook_id}")
async def custom_webhook(
    webhook_id: str,
    request: Request
):
    """
    Custom webhook endpoint for business-specific integrations.
    """
    try:
        # Get webhook
        webhook = supabase.table("webhooks")\
            .select("*")\
            .eq("id", webhook_id)\
            .execute()
        
        if not webhook.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Webhook not found"
            )
        
        webhook_config = webhook.data[0]
        
        # Verify signature if secret is configured
        if webhook_config.get('secret'):
            signature = request.headers.get('X-Webhook-Signature')
            if not signature:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing webhook signature"
                )
            
            # Verify signature
            payload = await request.body()
            expected_signature = hmac.new(
                webhook_config['secret'].encode(),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid webhook signature"
                )
        
        # Get payload
        payload = await request.json()
        
        logger.info(f"Custom webhook triggered: {webhook_id}")
        
        # Update webhook stats
        supabase.table("webhooks")\
            .update({
                "last_triggered_at": datetime.utcnow().isoformat(),
                "failure_count": 0
            })\
            .eq("id", webhook_id)\
            .execute()
        
        # TODO: Process webhook payload based on business configuration
        # This is where custom business logic would be executed
        
        return {"status": "success"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Custom webhook error: {str(e)}", exc_info=True)
        
        # Update failure count
        try:
            supabase.table("webhooks")\
                .update({
                    "failure_count": supabase.rpc("increment", {"field": "failure_count", "value": 1})
                })\
                .eq("id", webhook_id)\
                .execute()
        except Exception:
            pass
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook processing failed"
        )


@router.get("/verify")
async def verify_webhook(request: Request):
    """
    Webhook verification endpoint (for WhatsApp, Telegram, etc.).
    """
    try:
        # Get verification parameters
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')
        
        # TODO: Verify token matches your verification token
        # if token == settings.WEBHOOK_VERIFY_TOKEN:
        #     return JSONResponse(content=int(challenge))
        
        return JSONResponse(content=int(challenge) if challenge else "verified")
    
    except Exception as e:
        logger.error(f"Webhook verification error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification failed"
        )