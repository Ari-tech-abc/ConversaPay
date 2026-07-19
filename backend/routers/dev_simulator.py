"""
Development Simulator Router
Contains endpoints that are ONLY available in non-production environments
for testing and development purposes. Never included in production builds.
"""
from fastapi import APIRouter, HTTPException, status, Body
import logging
from datetime import datetime

from supabase import create_client, Client
from backend.config import settings
from backend.models.schemas import PaymentInfo, OrderStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["dev-simulator"])

# Supabase client (service role for backend-to-database operations)
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


# ============================================
# Development-only: Mark order as paid
# ============================================

@router.post("/{order_id}/mark-paid", response_model=dict)
async def dev_mark_order_paid(
    order_id: str,
    payment_info: PaymentInfo = Body(...),
):
    """
    DEVELOPMENT ONLY - Simulates payment by marking an order as paid.
    THIS ENDPOINT IS NEVER AVAILABLE IN PRODUCTION.
    Use Stripe webhooks for payment verification in production.
    """
    # SECURITY: Double-check we are NOT in production
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is disabled in production. Use Stripe webhooks for payment verification."
        )

    try:
        # Get order to verify it exists
        order_result = supabase.table("orders")\
            .select("*")\
            .eq("id", order_id)\
            .execute()

        if not order_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )

        order = order_result.data[0]

        # Update order status to paid
        update_data = {
            "status": OrderStatus.PAID.value,
            "payment_status": "paid",
            "customer_info": order.get('customer_info') or {}
        }

        # Merge customer info if provided
        if payment_info.customer_email:
            update_data["customer_info"]["email"] = payment_info.customer_email
        if payment_info.customer_name:
            update_data["customer_info"]["name"] = payment_info.customer_name

        result = supabase.table("orders")\
            .update(update_data)\
            .eq("id", order_id)\
            .execute()

        if result.data:
            logger.info(f"[DEV-SIMULATOR] Order {order_id} marked as paid")
            return {
                "status": "success",
                "message": "Order marked as paid (SIMULATOR)",
                "order_id": order_id,
                "order_number": order.get('order_number', '')
            }

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update order"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[DEV-SIMULATOR] Error marking order as paid: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process payment"
        )