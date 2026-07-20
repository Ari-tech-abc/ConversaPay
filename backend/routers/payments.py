"""
Payments router for managing payments and PayMe integration.
Handles payment sessions, subscription checkout, and webhooks.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import JSONResponse
from typing import Optional, List
from datetime import datetime
import logging
import httpx

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import (
    PaymentCreate, PaymentResponse, PaymentStatus,
    SubscriptionCreate, SubscriptionResponse,
    ProfileResponse
)
from backend.services.payme_service import payme_service

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


# ============================================
# Subscription Checkout Session (PayMe Integration)
# ============================================

@router.post("/create-checkout-session", response_model=SubscriptionResponse)
async def create_subscription_checkout_session(
    request: SubscriptionCreate,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Create a PayMe checkout session for Pro Plan subscription (200 ₪/month).
    User must be authenticated.
    
    This endpoint:
    - Step 1: Calls PayMe's generate-sale endpoint with seller_id, amount (200), currency (ILS)
    - Step 2: Returns the payment URL and payme_sale_id for frontend redirect
    """
    try:
        # Verify the user is the owner of the request
        if request.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User ID mismatch"
            )
        
        # Build success and cancel URLs for redirect after payment
        success_url = f"{settings.FRONTEND_URL}/pay?status=success&sale_id={{sale_id}}"
        cancel_url = f"{settings.FRONTEND_URL}/pay?status=canceled"
        
        # Step 1: Call PayMe's generate-sale endpoint
        # Pro tier price is exactly 200 NIS (no decimals)
        try:
            payme_result = await payme_service.create_hosted_setup_session(
                user_id=request.user_id,
                plan_type="pro",
                success_url=success_url,
                cancel_url=cancel_url
            )
            
            # Extract the returned values
            payme_sale_id = payme_result.get("payme_sale_id")
            payment_url = payme_result.get("sale_url")
            
            if not payme_sale_id or not payment_url:
                logger.error(f"PayMe API returned unexpected structure: {payme_result}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="PayMe API returned invalid response structure"
                )
            
            logger.info(f"PayMe sale created: {payme_sale_id} for user {request.user_id}")
            
        except httpx.HTTPError as e:
            logger.error(f"PayMe API HTTP error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to PayMe API"
            )
        except Exception as e:
            logger.error(f"PayMe API error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create PayMe payment session"
            )
        
        # Step 2: Prepare transaction details for database sync
        # Log the transaction details to be ready for webhook confirmation
        transaction_data = {
            "user_id": request.user_id,
            "payme_sale_id": payme_sale_id,
            "amount": 200,  # 200 NIS for Pro tier
            "currency": "ILS",
            "plan_type": "pro",
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Log transaction for debugging and database sync preparation
        logger.info(f"Transaction prepared for PayMe sync: {transaction_data}")
        
        # Return the payment URL and sale_id for frontend redirect
        return {
            "session_id": payme_sale_id,
            "url": payment_url,
            "payme_sale_id": payme_sale_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating subscription checkout session: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subscription checkout session"
        )


# ============================================
# Profile Management
# ============================================

@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get the current user's profile with subscription status.
    """
    try:
        result = supabase.table("profiles")\
            .select("*")\
            .eq("user_id", current_user.user_id)\
            .execute()
        
        if not result.data:
            # Create profile if it doesn't exist
            profile_data = {
                "user_id": current_user.user_id,
                "email": current_user.email,
                "is_pro": False
            }
            result = supabase.table("profiles")\
                .insert(profile_data)\
                .execute()
        
        return ProfileResponse(**result.data[0]) if result.data else None
    
    except Exception as e:
        logger.error(f"Error fetching profile: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch profile"
        )


# ============================================
# Order Checkout Session (PayMe Integration)
# ============================================

@router.post("/checkout-session", response_model=dict)
async def create_checkout_session(
    request: dict,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Create a PayMe Checkout session for an order.
    User must be the owner of the business.
    SECURITY: Amount is fetched from database, not trusted from client request.
    """
    try:
        business_id = request.get('business_id')
        order_id = request.get('order_id')
        customer_email = request.get('customer_email')
        customer_name = request.get('customer_name')
        
        if not business_id or not order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: business_id, order_id"
            )
        
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
        
        # Verify order exists and belongs to business
        order = supabase.table("orders")\
            .select("*")\
            .eq("id", order_id)\
            .eq("business_id", business.data[0]['id'])\
            .execute()
        
        if not order.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # SECURITY: Use amount from database, not from client request
        order_data = order.data[0]
        amount = order_data.get('total')
        currency = order_data.get('currency', 'ILS')
        
        if not amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Order has no total amount"
            )
        
        # Build success and cancel URLs
        success_url = f"{settings.FRONTEND_URL}/pay?status=success&order_id={order_id}"
        cancel_url = f"{settings.FRONTEND_URL}/pay?status=canceled"
        
        # Create PayMe payment session
        try:
            # Convert amount to integer NIS (PayMe expects NIS, not agorot)
            amount_nis = int(float(amount))
            
            # Build payload for PayMe API
            payload = {
                "pay_key": settings.PAYME_PAY_KEY,
                "seller_key": settings.PAYME_SELLER_KEY,
                "amount": amount_nis,
                "currency": "ILS",
                "description": f"Order #{order_id}",
                "extra1": business_id,
                "extra2": order_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.PAYME_API_URL}/generate-sale",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30.0
                )
                
                response.raise_for_status()
                data = response.json()
                
                sale_url = data.get("sale_url")
                sale_id = data.get("sale_id")
                
                if not sale_url or not sale_id:
                    logger.error(f"PayMe API returned unexpected structure: {data}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="PayMe API returned invalid response structure"
                    )
                
                logger.info(f"PayMe checkout session created: {sale_id} for order {order_id}")
                
        except httpx.HTTPError as e:
            logger.error(f"PayMe API HTTP error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to PayMe API"
            )
        except Exception as e:
            logger.error(f"PayMe API error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create PayMe payment session"
            )
        
        # Create payment record
        payment_data = {
            "business_id": business.data[0]['id'],
            "order_id": order_id,
            "payme_sale_id": sale_id,
            "amount": amount,
            "currency": currency,
            "status": PaymentStatus.PENDING.value,
            "customer_email": customer_email,
            "customer_name": customer_name,
            "metadata": {"payme_sale_id": sale_id}
        }
        
        payment_result = supabase.table("payments")\
            .insert(payment_data)\
            .execute()
        
        logger.info(f"Checkout session created for order {order_id}")
        
        return {
            "session_id": sale_id,
            "url": sale_url,
            "payment_id": payment_result.data[0]['id'] if payment_result.data else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )


@router.get("/success")
async def payment_success(sale_id: str):
    """
    Payment success page.
    Verifies the payment and updates order status.
    """
    try:
        # Get payment record from database
        payment = supabase.table("payments")\
            .select("*")\
            .eq("payme_sale_id", sale_id)\
            .execute()
        
        if payment.data:
            payment_id = payment.data[0]['id']
            order_id = payment.data[0]['order_id']
            business_id = payment.data[0]['business_id']
            
            # Update payment
            supabase.table("payments")\
                .update({
                    "status": PaymentStatus.SUCCEEDED.value,
                    "paid_at": datetime.utcnow().isoformat(),
                    "metadata": {
                        **payment.data[0].get('metadata', {}),
                        "payme_status": "success"
                    }
                })\
                .eq("id", payment_id)\
                .execute()
            
            # Update order status
            supabase.table("orders")\
                .update({"status": "paid"})\
                .eq("id", order_id)\
                .execute()
            
            logger.info(f"Payment succeeded for sale {sale_id}")
        
        return {"status": "success", "message": "Payment completed successfully"}
    
    except Exception as e:
        logger.error(f"Error processing payment success: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process payment"
        )


@router.get("/canceled")
async def payment_canceled():
    """
    Payment canceled page.
    """
    return {"status": "canceled", "message": "Payment was canceled"}


# ============================================
# PayMe Webhook Handler
# ============================================

@router.post("/webhook")
async def payme_webhook(request: Request):
    """
    PayMe webhook endpoint.
    Handles payment events from PayMe payment gateway.
    Listens for:
    - sale.completed (for successful payments)
    - sale.failed (for failed payments)
    - sale.canceled (for canceled payments)
    """
    try:
        # Get raw body
        payload = await request.json()
        
        logger.info(f"Received PayMe webhook: {payload}")
        
        # Extract key fields
        sale_id = payload.get("sale_id")
        status_value = payload.get("status")
        amount = payload.get("amount")
        user_id = payload.get("extra1")
        plan_type = payload.get("extra2")
        
        if not sale_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing sale_id in webhook payload"
            )
        
        # Check if this is a successful payment
        is_success = status_value == "success" or str(status_value) == "0"
        
        if is_success:
            # Successful payment - activate subscription
            await _handle_subscription_activated(user_id, plan_type, sale_id)
        else:
            # Failed/cancelled payment - deactivate subscription
            await _handle_subscription_deactivated(user_id, sale_id)
        
        return {"status": "success", "processed": True}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook processing failed"
        )


async def _handle_subscription_activated(
    user_id: Optional[str],
    plan_type: Optional[str],
    sale_id: str
) -> dict:
    """
    Handle successful subscription payment.
    Updates user profile with Pro status.
    """
    try:
        if not user_id:
            logger.warning(f"No user_id in successful PayMe payment: {sale_id}")
            return {"status": "error", "message": "No user_id in metadata"}
        
        # Update or create profile
        existing_profile = supabase.table("profiles")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()
        
        profile_data = {
            "is_pro": True,
            "plan_type": plan_type or "pro",
            "payme_sale_id": sale_id,
            "subscription_activated_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if existing_profile.data:
            supabase.table("profiles")\
                .update(profile_data)\
                .eq("user_id", user_id)\
                .execute()
            logger.info(f"Updated profile for user {user_id} to Pro status")
        else:
            profile_data["user_id"] = user_id
            supabase.table("profiles")\
                .insert(profile_data)\
                .execute()
            logger.info(f"Created Pro profile for user {user_id}")
        
        return {"status": "success", "event": "subscription_activated", "processed": True}
    
    except Exception as e:
        logger.error(f"Error processing subscription activation: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e), "event": "subscription_activated"}


async def _handle_subscription_deactivated(user_id: Optional[str], sale_id: str) -> dict:
    """
    Handle failed/cancelled subscription payment.
    Revokes Pro status from user.
    """
    try:
        if not user_id:
            logger.warning(f"No user_id in failed PayMe payment: {sale_id}")
            return {"status": "error", "message": "No user_id in metadata"}
        
        # Update user profile to deactivate subscription
        supabase.table("profiles")\
            .update({
                "is_pro": False,
                "plan_type": None,
                "payme_sale_id": None,
                "subscription_cancelled_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            })\
            .eq("user_id", user_id)\
            .execute()
        
        logger.info(f"Deactivated subscription for user {user_id}")
        
        return {"status": "success", "event": "subscription_deactivated", "processed": True}
    
    except Exception as e:
        logger.error(f"Error processing subscription deactivation: {str(e)}", exc_info=True)
        return {"status": "error", "message": str(e), "event": "subscription_deactivated"}


# ============================================
# Payment List/Detail
# ============================================

@router.get("", response_model=List[PaymentResponse])
async def get_payments(
    business_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get all payments for a business.
    User must be the owner of the business.
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
        
        # Get payments
        result = supabase.table("payments")\
            .select("*")\
            .eq("business_id", business_uuid)\
            .order("created_at", desc=True)\
            .execute()
        
        return [PaymentResponse(**payment) for payment in result.data] if result.data else []
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching payments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch payments"
        )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get a specific payment by ID.
    User must be the owner of the business that owns the payment.
    """
    try:
        # Get payment
        result = supabase.table("payments")\
            .select("*")\
            .eq("id", payment_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        
        payment = result.data[0]
        
        # Verify ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", payment['business_id'])\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return PaymentResponse(**payment)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching payment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch payment"
        )


# ============================================
# WordPress Plugin Generator
# ============================================

@router.get("/wordpress-plugin/{business_id}")
async def get_wordpress_plugin(
    business_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Serve the static WordPress plugin file.
    User must be the owner of the business.
    """
    try:
        # Verify business ownership
        business = supabase.table("businesses")\
            .select("id, business_id, business_name")\
            .eq("business_id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        # Read the template plugin file
        from pathlib import Path
        plugin_file_path = Path(__file__).parent.parent / "templates" / "conversapay-chat.php"
        
        if not plugin_file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Plugin file not found"
            )
        
        # Read the plugin content
        plugin_content = plugin_file_path.read_text(encoding='utf-8')
        
        # Replace placeholders with actual values
        plugin_content = plugin_content.replace('{{BUSINESS_ID}}', business_id)
        plugin_content = plugin_content.replace('{{FRONTEND_URL}}', settings.FRONTEND_URL)
        
        # Return as downloadable PHP file
        from fastapi.responses import Response
        
        return Response(
            content=plugin_content.encode('utf-8'),
            media_type='application/x-httpd-php',
            headers={
                'Content-Disposition': f'attachment; filename=conversapay-chat-{business_id}.php'
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving WordPress plugin: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to serve WordPress plugin"
        )