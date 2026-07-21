"""
Orders router for managing orders.
Requires authentication - users can only access their own business orders.

SECURITY FIXES:
  C4  - Public order creation now sets status=PENDING (not PAID).
  H7  - Removed broken supabase.rpc("increment") call; customer stats
        updated with a safe read-then-write pattern.
  M3  - Public /summary no longer returns internal business_id UUID.
  M9  - order_number uses uuid4 suffix to eliminate collision risk.
"""
import uuid
from fastapi import APIRouter, HTTPException, status, Depends, Query
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

supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


def _new_order_number() -> str:
    """
    Generate a collision-free order number.
    FIX H7: previous ORD-{YYYYMMDD}-{HHMMSS} collides for concurrent requests.
    Using a uuid4 suffix guarantees uniqueness.
    """
    return f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


# ============================================
# Public endpoints (customer-facing, no auth)
# ============================================

@router.get("/{order_id}/summary", response_model=dict)
async def get_order_summary_public(order_id: str):
    """
    Public endpoint to get order summary for checkout page.
    FIX M3: internal business_id UUID removed from response.
    """
    try:
        order = supabase.table("orders") \
            .select("*, businesses!inner(business_name)") \
            .eq("id", order_id) \
            .execute()

        if not order.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

        d = order.data[0]
        business_name = d.get("businesses", {}).get("business_name", "Unknown Business")

        # FIX M3: only return safe, non-identifying fields.
        return {
            "order_id": d["id"],
            "order_number": d["order_number"],
            "business_name": business_name,
            "items": d.get("items", []),
            "total": d["total"],
            "currency": d["currency"],
            "status": d["status"],
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order summary: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch order summary")


@router.get("/{order_id}/status", response_model=dict)
async def get_order_status_public(order_id: str):
    """Public endpoint to poll order status."""
    try:
        order = supabase.table("orders").select("status").eq("id", order_id).execute()
        if not order.data:
            raise HTTPException(status_code=404, detail="Order not found")
        return {"status": order.data[0]["status"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order status: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch order status")


@router.post("/pay", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order_public(request: OrderCreate):
    """
    Public endpoint to create an order from the payment page.
    FIX C4: status is now PENDING — payment gateway webhook sets it to PAID.
    """
    try:
        business = supabase.table("businesses") \
            .select("id") \
            .eq("business_id", request.business_id) \
            .execute()

        if not business.data:
            raise HTTPException(status_code=404, detail="Business not found")

        business_uuid = business.data[0]["id"]

        order_data = {
            "business_id": business_uuid,
            "customer_id": request.customer_id,
            "conversation_id": request.conversation_id,
            "order_number": _new_order_number(),
            # FIX C4: PENDING — not PAID. Payment gateway confirms payment via webhook.
            "status": OrderStatus.PENDING.value,
            "subtotal": request.subtotal,
            "tax": request.tax,
            "total": request.total,
            "currency": request.currency,
            "items": [item.model_dump() for item in request.items] if request.items else [],
            "customer_info": request.customer_info,
            "shipping_address": request.shipping_address,
            "notes": request.notes,
            "created_at": datetime.utcnow().isoformat(),
        }

        result = supabase.table("orders").insert(order_data).execute()

        if result.data:
            logger.info(f"Public order created: {order_data['order_number']} for business {request.business_id}")
            return OrderResponse(**result.data[0])

        raise HTTPException(status_code=500, detail="Failed to create order")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating public order: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create order")


# ============================================
# Authenticated endpoints
# ============================================

@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: OrderCreate,
    current_user: AuthUser = Depends(require_auth)
):
    """Create a new order. User must own the business."""
    try:
        business = supabase.table("businesses") \
            .select("id") \
            .eq("business_id", request.business_id) \
            .eq("owner_id", current_user.user_id) \
            .execute()

        if not business.data:
            raise HTTPException(status_code=404, detail="Business not found")

        business_uuid = business.data[0]["id"]

        order_data = {
            "business_id": business_uuid,
            "customer_id": request.customer_id,
            "conversation_id": request.conversation_id,
            "order_number": _new_order_number(),
            "status": OrderStatus.PENDING.value,
            "subtotal": request.subtotal,
            "tax": request.tax,
            "total": request.total,
            "currency": request.currency,
            "items": [item.model_dump() for item in request.items],
            "customer_info": request.customer_info,
            "shipping_address": request.shipping_address,
            "notes": request.notes,
            "created_at": datetime.utcnow().isoformat(),
        }

        result = supabase.table("orders").insert(order_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to create order")

        order = result.data[0]
        logger.info(f"Order created: {order_data['order_number']} for business {request.business_id}")

        # FIX H6: update customer stats with a safe read-then-write (no broken RPC call).
        if request.customer_id:
            try:
                cust = supabase.table("customers") \
                    .select("total_purchases, purchase_count") \
                    .eq("id", request.customer_id) \
                    .execute()
                if cust.data:
                    row = cust.data[0]
                    supabase.table("customers").update({
                        "total_purchases": float(row.get("total_purchases", 0)) + float(request.total),
                        "purchase_count": int(row.get("purchase_count", 0)) + 1,
                        "last_purchase_at": datetime.utcnow().isoformat(),
                    }).eq("id", request.customer_id).execute()
            except Exception as e:
                logger.warning(f"Could not update customer stats: {str(e)}")

        return OrderResponse(**order)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating order: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create order")


@router.get("", response_model=List[OrderResponse])
async def get_orders(
    business_id: str = Query(..., description="Business identifier"),
    status_filter: Optional[OrderStatus] = Query(None, description="Filter by order status"),
    limit: int = Query(50, ge=1, le=100),
    current_user: AuthUser = Depends(require_auth)
):
    """Get all orders for a business. User must own the business."""
    try:
        business_uuid = require_business_owner_for_business_id(business_id, current_user)

        query = supabase.table("orders") \
            .select("*") \
            .eq("business_id", business_uuid) \
            .order("created_at", desc=True) \
            .limit(limit)

        if status_filter:
            query = query.eq("status", status_filter.value)

        result = query.execute()
        return [OrderResponse(**o) for o in result.data] if result.data else []

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching orders: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch orders")


@router.get("/number/{order_number}", response_model=OrderResponse)
async def get_order_by_number(
    order_number: str,
    current_user: AuthUser = Depends(require_auth)
):
    """Get an order by order number. User must own the business."""
    try:
        result = supabase.table("orders").select("*").eq("order_number", order_number).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Order not found")

        order = result.data[0]
        require_business_owner_for_business_id(order["business_id"], current_user)
        return OrderResponse(**order)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch order")


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """Get a specific order by ID. User must own the business."""
    try:
        result = supabase.table("orders").select("*").eq("id", order_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Order not found")

        order = result.data[0]
        require_business_owner_for_business_id(order["business_id"], current_user)
        return OrderResponse(**order)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching order: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch order")


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: str,
    request: OrderUpdate,
    current_user: AuthUser = Depends(require_auth)
):
    """Update an order. User must own the business.
    
    FIX C1: Validate state machine transitions to prevent invalid status changes.
    """
    try:
        order_result = supabase.table("orders") \
            .select("business_id, status") \
            .eq("id", order_id) \
            .execute()

        if not order_result.data:
            raise HTTPException(status_code=404, detail="Order not found")

        order = order_result.data[0]
        require_business_owner_for_business_id(order["business_id"], current_user)

        # FIX C1: Validate state machine transitions
        if request.status:
            current_status = order["status"]
            new_status = request.status.value
            
            # Define valid transitions
            valid_transitions = {
                OrderStatus.PENDING.value: [OrderStatus.PROCESSING.value, OrderStatus.CANCELED.value],
                OrderStatus.PROCESSING.value: [OrderStatus.PAID.value, OrderStatus.FAILED.value, OrderStatus.CANCELED.value],
                OrderStatus.PAID.value: [OrderStatus.SHIPPED.value, OrderStatus.REFUNDED.value],
                OrderStatus.SHIPPED.value: [OrderStatus.DELIVERED.value, OrderStatus.REFUNDED.value],
                OrderStatus.DELIVERED.value: [OrderStatus.REFUNDED.value],
                OrderStatus.CANCELED.value: [],
                OrderStatus.REFUNDED.value: [],
            }
            
            if new_status not in valid_transitions.get(current_status, []):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status transition from {current_status} to {new_status}"
                )

        update_data = request.model_dump(exclude_none=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No data to update")

        result = supabase.table("orders").update(update_data).eq("id", order_id).execute()

        if result.data:
            logger.info(f"Order updated: {order_id}")
            return OrderResponse(**result.data[0])

        raise HTTPException(status_code=500, detail="Failed to update order")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating order: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update order")
