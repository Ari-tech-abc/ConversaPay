"""
WhatsApp Webhook Router for Premium Tier Integration.
Handles Meta's WhatsApp Cloud API webhook verification and message processing.
"""
import logging
import httpx
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from typing import Optional, Dict, Any

from supabase import create_client, Client
from backend.config import settings
from backend.services.gemini_service import gemini_service
from backend.services.session_service import session_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/whatsapp", tags=["whatsapp-webhook"])

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


async def send_whatsapp_message(to_number: str, text: str, access_token: str, phone_number_id: str) -> bool:
    """
    Send a WhatsApp message via Meta's Graph API.
    
    Args:
        to_number: Recipient's phone number (format: +1234567890)
        text: Message text to send
        access_token: WhatsApp Business access token
        phone_number_id: The phone number ID of the business
        
    Returns:
        True if message sent successfully, False otherwise
    """
    try:
        url = f"https://graph.facebook.com/v20.0/{phone_number_id}/messages"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {
                "body": text
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)
            
        if response.status_code == 200:
            logger.info(f"WhatsApp message sent successfully to {to_number}")
            return True
        else:
            logger.error(f"Failed to send WhatsApp message: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}", exc_info=True)
        return False


@router.get("", response_class=PlainTextResponse)
async def verify_webhook(request: Request):
    """
    Meta's official Webhook Verification handshake.
    
    Query parameters:
    - hub.mode: Should be "subscribe" for verification
    - hub.verify_token: The verify token to match against registered merchant
    - hub.challenge: The challenge string to return if verified
    
    Returns:
    - hub.challenge as plain text if verified (status 200)
    - 403 Forbidden if verification fails
    """
    try:
        hub_mode = request.query_params.get("hub.mode")
        hub_verify_token = request.query_params.get("hub.verify_token")
        hub_challenge = request.query_params.get("hub.challenge")
        
        # Check if mode is "subscribe"
        if hub_mode != "subscribe":
            logger.warning(f"WhatsApp webhook verification failed: mode is '{hub_mode}'")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid mode"
            )
        
        # Query Supabase to find merchant with matching verify token and Premium status
        profile_result = supabase.table("profiles")\
            .select("*")\
            .eq("whatsapp_verify_token", hub_verify_token)\
            .eq("is_pro", True)\
            .eq("plan_type", "premium")\
            .execute()
        
        if not profile_result.data:
            logger.warning(f"WhatsApp webhook verification failed: no Premium merchant with verify token '{hub_verify_token}'")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Verification token not found or not Premium"
            )
        
        # Verification successful - return the challenge
        logger.info(f"WhatsApp webhook verified for user {profile_result.data[0]['user_id']}")
        return PlainTextResponse(content=hub_challenge)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in WhatsApp webhook verification: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Verification failed"
        )


@router.post("", response_class=JSONResponse)
async def handle_whatsapp_webhook(request: Request):
    """
    Handle incoming WhatsApp webhook event payloads from Meta's WhatsApp Cloud API.
    
    Payload structure:
    {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "...",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "phone_number_id": "..."
                    },
                    "messages": [{
                        "from": "CUSTOMER_PHONE_NUMBER",
                        "type": "text",
                        "text": {
                            "body": "MESSAGE_TEXT"
                        }
                    }]
                }
            }]
        }]
    }
    
    Returns:
    - 200 OK to satisfy Meta's retry loop policy (even for non-Premium merchants)
    - Processes message only for Premium merchants
    """
    try:
        payload = await request.json()
        
        # Extract phone_number_id from payload
        entry = payload.get("entry", [])
        if not entry:
            return JSONResponse(content={"status": "ok"})
        
        changes = entry[0].get("changes", [])
        if not changes:
            return JSONResponse(content={"status": "ok"})
        
        value = changes[0].get("value", {})
        phone_number_id = value.get("metadata", {}).get("phone_number_id")
        
        if not phone_number_id:
            return JSONResponse(content={"status": "ok"})
        
        # Look up merchant profile in Supabase using the phone_number_id
        profile_result = supabase.table("profiles")\
            .select("*")\
            .eq("whatsapp_phone_number_id", phone_number_id)\
            .execute()
        
        if not profile_result.data:
            logger.info(f"No merchant found for WhatsApp phone_number_id: {phone_number_id}")
            return JSONResponse(content={"status": "ok"})
        
        profile = profile_result.data[0]
        
        # Strict Premium Gate: Verify plan_type == 'premium' and is_pro == true
        if not profile.get("is_pro") or profile.get("plan_type") != "premium":
            logger.info(f"Non-Premium merchant attempted WhatsApp message: {profile.get('user_id')}")
            return JSONResponse(content={"status": "ok"})
        
        # Extract message from payload
        messages = value.get("messages", [])
        if not messages:
            return JSONResponse(content={"status": "ok"})
        
        message = messages[0]
        if message.get("type") != "text":
            return JSONResponse(content={"status": "ok"})
        
        customer_phone = message.get("from")
        message_text = message.get("text", {}).get("body", "")
        
        if not customer_phone or not message_text:
            return JSONResponse(content={"status": "ok"})
        
        # Get the business for this merchant
        business_result = supabase.table("businesses")\
            .select("*")\
            .eq("owner_id", profile["user_id"])\
            .eq("is_active", True)\
            .execute()
        
        if not business_result.data:
            return JSONResponse(content={"status": "ok"})
        
        business = business_result.data[0]
        
        # Get or create conversation for WhatsApp channel
        conversation = await session_service.get_or_create_conversation(
            business_id=business["id"],
            session_id=f"whatsapp_{customer_phone}",
            channel="whatsapp"
        )
        
        # Get or create customer (using phone as identifier)
        customer = await session_service.get_or_create_customer(
            business_id=business["id"],
            phone=customer_phone,
            name=None,
            email=None
        )
        
        # Get active products
        products_result = supabase.table("products")\
            .select("*")\
            .eq("business_id", business["id"])\
            .eq("is_active", True)\
            .execute()
        
        products = products_result.data if products_result.data else []
        
        # Get conversation history
        history = await session_service.get_conversation_history(
            conversation_id=conversation["id"],
            limit=20
        )
        
        conversation_history = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in history
        ]
        
        # Build customer context
        customer_context = None
        if customer:
            customer_context = {
                "name": customer.get("name"),
                "email": customer.get("email"),
                "phone": customer.get("phone"),
                "purchase_count": customer.get("purchase_count", 0),
                "total_purchases": customer.get("total_purchases", 0),
                "last_purchase_at": customer.get("last_purchase_at"),
                "recent_orders": []
            }
        
        # Save user message
        await session_service.add_message(
            conversation_id=conversation["id"],
            role="user",
            content=message_text
        )
        
        # Route to Gemini AI (same as web chat)
        ai_response = await gemini_service.chat(
            business_id=business["id"],
            session_id=conversation["session_id"],
            message=message_text,
            business_data=business,
            products=products,
            customer_context=customer_context,
            conversation_history=conversation_history
        )
        
        # Save assistant message
        await session_service.add_message(
            conversation_id=conversation["id"],
            role="assistant",
            content=ai_response["response"],
            intent=ai_response["intent"]
        )
        
        # Send response via WhatsApp
        access_token = profile.get("whatsapp_access_token")
        if access_token:
            await send_whatsapp_message(
                to_number=customer_phone,
                text=ai_response["response"],
                access_token=access_token,
                phone_number_id=phone_number_id
            )
        
        return JSONResponse(content={"status": "ok"})
        
    except Exception as e:
        logger.error(f"Error processing WhatsApp webhook: {str(e)}", exc_info=True)
        # Return 200 OK to satisfy Meta's retry loop policy
        return JSONResponse(content={"status": "ok"})