"""
Orders router for managing orders.
Requires authentication - users can only access their own business orders.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query, Body
from typing import List, Optional
import logging
from datetime import datetime

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth, require_business_owner_for_business_id
from backend.models.schemas import OrderCreate, OrderUpdate, OrderResponse, OrderStatus, PaymentInfo
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["orders"])

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


# Public order summary endpoint (no auth - customer facing)
@router.get("/{order_id}/summary", response_model=dict)
async def get_order_summary_public(order_id: str):
    """
    Public endpoint to get order summary for checkout page.
    Returns only basic, non-sensitive order details.
    No authentication required - this is called by customers.
    """
    try:
        # Get order details
        order = supabase.table("orders")\
            .select("*, businesses!inner(business_name)")\
            .eq("id", order_id)\
            .execute()
        
        if not order.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        order_data = order.data[0]
        
        # Get business name from joined data
        business_name = order_data.get('businesses', {}).get('business_name', 'Unknown Business')
        
        # Return only safe, non-sensitive information
        return {
            "order_id": order_data['id'],
            "order_number": order_data['order_number'],
            "business_id": order_data['business_id'],
            "business_name": business_name,
            "items": order_data.get('items', []),
            "total": order_data['total'],
            "currency": order_data['currency'],
            "status": order_data['status']
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order summary: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch order summary"
        )


# Public order status endpoint (no auth - customer facing)
@router.get("/{order_id}/status", response_model=dict)
async def get_order_status_public(order_id: str):
    """
    Public endpoint to get order status for polling.
    Returns only the status field for real-time updates.
    No authentication required - this is called by customers.
    """
    try:
        # Get order status
        order = supabase.table("orders")\
            .select("status")\
            .eq("id", order_id)\
            .execute()
        
        if not order.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        order_data = order.data[0]
        
        # Return only the status
        return {
            "status": order_data['status']
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order status: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch order status"
        )


# Public order from pay page (no auth - customer facing)
@router.post("/pay", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order_public(request: OrderCreate):
    """
    Public endpoint to create an order from the payment page.
    No authentication required - this is called by customers.
    """
    try:
        # Look up business by business_id (string slug)
        business = supabase.table("businesses")\
            .select("id")\
            .eq("business_id", request.business_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        business_uuid = business.data[0]['id']
        
        # Generate order number
        order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{datetime.utcnow().strftime('%H%M%S')}"
        
        # Create order
        order_data = {
            "business_id": business_uuid,
            "customer_id": request.customer_id,
            "conversation_id": request.conversation_id,
            "order_number": order_number,
            "status": OrderStatus.PAID.value,
            "subtotal": request.subtotal,
            "tax": request.tax,
            "total": request.total,
            "currency": request.currency,
            "items": [item.model_dump() for item in request.items] if request.items else [],
            "customer_info": request.customer_info,
            "shipping_address": request.shipping_address,
            "notes": request.notes,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("orders")\
            .insert(order_data)\
            .execute()
        
        if result.data:
            order = result.data[0]
            logger.info(f"Public order created: {order_number} for business {request.business_id}")
            return OrderResponse(**order)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create order"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating public order: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create order"
        )


# Mark order as paid (public - for payment page callback - SIMULATOR ONLY)
@router.post("/{order_id}/mark-paid", response_model=dict)
async def mark_order_paid(
    order_id: str,
    payment_info: PaymentInfo = Body(...),
):
    """
    Public endpoint called after simulated payment to mark order as paid.
    DISABLED IN PRODUCTION - only for local development/testing.
    In production, order payment status must only be updated via verified Stripe webhooks.
    """
    # SECURITY: Disable in production
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
            logger.info(f"Order {order_id} marked as paid (SIMULATOR)")
            return {
                "status": "success",
                "message": "Order marked as paid",
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
        logger.error(f"Error marking order as paid: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process payment"
        )


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: OrderCreate,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Create a new order.
    User must be the owner of the business.
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
        
        # Generate order number
        order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{datetime.utcnow().strftime('%H%M%S')}"
        
        # Create order
        order_data = {
            "business_id": business_uuid,
            "customer_id": request.customer_id,
            "conversation_id": request.conversation_id,
            "order_number": order_number,
            "status": OrderStatus.PENDING.value,
            "subtotal": request.subtotal,
            "tax": request.tax,
            "total": request.total,
            "currency": request.currency,
            "items": [item.model_dump() for item in request.items],
            "customer_info": request.customer_info,
            "shipping_address": request.shipping_address,
            "notes": request.notes,
            "created_at": datetime.utcnow().isoformat()
        }
        
        result = supabase.table("orders")\
            .insert(order_data)\
            .execute()
        
        if result.data:
            order = result.data[0]
            logger.info(f"Order created: {order_number} for business {request.business_id}")
            
            # Update customer stats if customer_id provided
            if request.customer_id:
                try:
                    supabase.table("customers")\
                        .update({
                            "total_purchases": supabase.rpc("increment", {"field": "total_purchases", "value": request.total}),
                            "purchase_count": supabase.rpc("increment", {"field": "purchase_count", "value": 1}),
                            "last_purchase_at": datetime.utcnow().isoformat()
                        })\
                        .eq("id", request.customer_id)\
                        .execute()
                except Exception as e:
                    logger.warning(f"Could not update customer stats: {str(e)}")
            
            return OrderResponse(**order)
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create order"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating order: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create order"
        )


@router.get("", response_model=List[OrderResponse])
async def get_orders(
    business_id: str = Query(..., description="Business identifier"),
    status_filter: Optional[OrderStatus] = Query(None, description="Filter by order status"),
    limit: int = Query(50, ge=1, le=100),
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get all orders for a business.
    User must be the owner of the business.
    """
    try:
        # Verify business ownership
        business_uuid = require_business_owner_for_business_id(business_id, current_user)

        # Get orders
        
        # Get orders
        query = supabase.table("orders")\
            .select("*")\
            .eq("business_id", business_uuid)\
            .order("created_at", desc=True)\
            .limit(limit)
        
        if status_filter:
            query = query.eq("status", status_filter.value)
        
        result = query.execute()
        
        return [OrderResponse(**order) for order in result.data] if result.data else []
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching orders: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch orders"
        )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get a specific order by ID.
    User must be the owner of the business that owns the order.
    """
    try:
        # Get order
        result = supabase.table("orders")\
            .select("*")\
            .eq("id", order_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        order = result.data[0]
        
        # Verify ownership
        require_business_owner_for_business_id(order['business_id'], current_user)
        return OrderResponse(**order)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch order"
        )


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: str,
    request: OrderUpdate,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Update an order (e.g., change status).
    User must be the owner of the business that owns the order.
    """
    try:
        # Get order
        order_result = supabase.table("orders")\
            .select("business_id")\
            .eq("id", order_id)\
            .execute()
        
        if not order_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        business_uuid = order_result.data[0]['business_id']
        
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
        
        # Update order
        result = supabase.table("orders")\
            .update(update_data)\
            .eq("id", order_id)\
            .execute()
        
        if result.data:
            logger.info(f"Order updated: {order_id}")
            return OrderResponse(**result.data[0])
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update order"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating order: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update order"
        )


@router.get("/number/{order_number}", response_model=OrderResponse)
async def get_order_by_number(
    order_number: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get an order by order number.
    User must be the owner of the business that owns the order.
    """
    try:
        # Get order
        result = supabase.table("orders")\
            .select("*")\
            .eq("order_number", order_number)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        order = result.data[0]
        
        # Verify ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", order['business_id'])\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return OrderResponse(**order)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch order"
        )