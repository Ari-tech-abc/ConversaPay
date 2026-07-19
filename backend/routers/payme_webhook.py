"""
PayMe Webhook Router
Handles Instant Payment Notifications (IPN) from PayMe payment gateway.
"""
from fastapi import APIRouter, HTTPException, status, Request
import logging
from datetime import datetime
from typing import Optional

from supabase import create_client, Client
from backend.config import settings
from backend.services.payme_service import payme_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks/payme", tags=["payme-webhook"])

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


# ============================================
# PayMe Webhook Endpoint
# ============================================

@router.post("", response_model=dict)
async def handle_payme_webhook(request: Request):
    """
    Handle PayMe Instant Payment Notifications (IPN).
    
    PayMe sends payment status updates to this endpoint.
    We process successful payments to activate subscriptions,
    and handle failures/cancellations to deactivate them.
    """
    try:
        # Parse the incoming payload
        payload = await request.json()
        
        logger.info(f"Received PayMe webhook: {payload}")
        
        # Extract key fields
        sale_id = payload.get("sale_id")
        payme_status = payload.get("status")  # "success" or other status codes
        amount = payload.get("amount")  # Amount in Agora
        card_token = payload.get("card_token")  # For recurring billing
        buyer_key = payload.get("buyer_key")  # Alternative token field
        user_id = payload.get("extra1")  # Our user_id stored during initialization
        plan_type = payload.get("extra2")  # Our plan type stored during initialization
        
        if not sale_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing sale_id in webhook payload"
            )
        
        # Check if this is a successful payment
        is_success = payme_status == "success" or str(payme_status) == "0"
        
        if is_success:
            # Successful payment - activate subscription
            await _activate_subscription(user_id, plan_type, card_token or buyer_key, sale_id)
        else:
            # Failed/cancelled payment - deactivate subscription
            await _deactivate_subscription(user_id, sale_id)
        
        return {"status": "success", "processed": True}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing PayMe webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook"
        )


# ============================================
# Helper Functions
# ============================================

async def _activate_subscription(
    user_id: Optional[str],
    plan_type: Optional[str],
    card_token: Optional[str],
    sale_id: str
):
    """
    Activate a user\'s subscription after successful PayMe payment.
    """
    if not user_id:
        logger.warning(f"No user_id in successful PayMe payment: {sale_id}")
        return
    
    try:
        # Update user profile with subscription details
        # Note: The profiles table stores is_pro and subscription info
        profile_data = {
            "is_pro": True,
            "plan_type": plan_type or "pro",
            "payme_card_token": card_token,  # Store for recurring billing
            "payme_sale_id": sale_id,
            "subscription_activated_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Check if profile exists
        existing = supabase.table("profiles")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()
        
        if existing.data:
            # Update existing profile
            supabase.table("profiles")\
                .update(profile_data)\
                .eq("user_id", user_id)\
                .execute()
        else:
            # Create new profile
            profile_data["user_id"] = user_id
            supabase.table("profiles")\
                .insert(profile_data)\
                .execute()
        
        logger.info(f"Activated {plan_type} subscription for user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to activate subscription: {str(e)}", exc_info=True)


async def _deactivate_subscription(user_id: Optional[str], sale_id: str):
    """
    Deactivate a user\'s subscription after failed/cancelled payment.
    """
    if not user_id:
        logger.warning(f"No user_id in failed PayMe payment: {sale_id}")
        return
    
    try:
        # Update user profile to deactivate subscription
        supabase.table("profiles")\
            .update({
                "is_pro": False,
                "plan_type": None,
                "payme_card_token": None,
                "subscription_cancelled_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            })\
            .eq("user_id", user_id)\
            .execute()
        
        logger.info(f"Deactivated subscription for user {user_id}")
        
    except Exception as e:
        logger.error(f"Failed to deactivate subscription: {str(e)}", exc_info=True)