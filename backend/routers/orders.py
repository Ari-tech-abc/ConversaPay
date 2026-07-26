"""Order routes with server-side catalog pricing and ownership checks."""
import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, status, Depends, Query
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth, require_business_owner_for_business_id
from backend.middleware.rate_limiter import check_rate_limit
from backend.models.schemas import OrderCreate, OrderResponse, OrderStatus
from fastapi import Request

router = APIRouter(prefix="/orders", tags=["orders"])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _order_number():
    return f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"


def _catalog_order(request, business_uuid):
    if not request.items:
        raise HTTPException(400, "An order must contain at least one item")
    keys = list({x.item_key.strip().upper() for x in request.items})
    result = supabase.table("products").select("id,item_key,name,price,currency").eq("business_id", business_uuid).eq("is_active", True).in_("item_key", keys).execute()
    products = {x["item_key"].upper(): x for x in (result.data or [])}
    if len(products) != len(keys):
        raise HTTPException(400, "One or more products are unavailable")
    currency = None
    items = []
    subtotal = 0.0
    for requested in request.items:
        key = requested.item_key.strip().upper()
        product = products[key]
        product_currency = str(product.get("currency") or "ILS").upper()
        if currency is None:
            currency = product_currency
        if product_currency != currency:
            raise HTTPException(400, "All products in an order must use the same currency")
        quantity = int(requested.quantity)
        if quantity < 1 or quantity > 100:
            raise HTTPException(400, "Quantity must be between 1 and 100")
        price = float(product["price"])
        subtotal += price * quantity
        items.append({"product_id": product["id"], "item_key": product["item_key"], "name": product["name"], "quantity": quantity, "price": price})
    return items, round(subtotal, 2), currency or "ILS"


def _order_payload(request, business_uuid):
    items, subtotal, currency = _catalog_order(request, business_uuid)
    return {
        "business_id": business_uuid,
        "customer_id": request.customer_id,
        "conversation_id": request.conversation_id,
        "order_number": _order_number(),
        "status": OrderStatus.PENDING.value,
        "payment_status": "pending",
        "subtotal": subtotal,
        "tax": 0,
        "total": subtotal,
        "currency": currency,
        "items": items,
        "customer_info": request.customer_info,
        "shipping_address": request.shipping_address,
        "notes": request.notes,
        "created_at": datetime.utcnow().isoformat(),
    }


@router.post("/pay", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order_public(request: OrderCreate, request_obj: Request):
    check_rate_limit(request_obj)
    business = supabase.table("businesses").select("id").eq("business_id", request.business_id).eq("is_active", True).execute()
    if not business.data:
        raise HTTPException(404, "Business not found")
    result = supabase.table("orders").insert(_order_payload(request, business.data[0]["id"])).execute()
    if not result.data:
        raise HTTPException(500, "Failed to create order")
    return OrderResponse(**result.data[0])


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(request: OrderCreate, current_user: AuthUser = Depends(require_auth)):
    business_uuid = require_business_owner_for_business_id(request.business_id, current_user)
    result = supabase.table("orders").insert(_order_payload(request, business_uuid)).execute()
    if not result.data:
        raise HTTPException(500, "Failed to create order")
    return OrderResponse(**result.data[0])


@router.get("", response_model=List[OrderResponse])
async def list_orders(
    business_id: str = Query(...),
    limit: int = Query(50, ge=1, le=100),
    status_filter: str | None = Query(None),
    current_user: AuthUser = Depends(require_auth),
):
    """List the authenticated owner's orders for the legacy dashboard controller."""
    business_uuid = require_business_owner_for_business_id(business_id, current_user)
    query = supabase.table("orders").select("*").eq("business_id", business_uuid).order("created_at", desc=True).limit(limit)
    if status_filter:
        query = query.eq("status", status_filter)
    result = query.execute()
    return [OrderResponse(**row) for row in (result.data or [])]


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, current_user: AuthUser = Depends(require_auth)):
    """Read one order after verifying that its business belongs to the caller."""
    result = supabase.table("orders").select("*").eq("id", order_id).maybe_single().execute()
    if not result.data:
        raise HTTPException(404, "Order not found")
    order = result.data
    owner = supabase.table("businesses").select("id").eq("id", order["business_id"]).eq("owner_id", current_user.user_id).maybe_single().execute()
    if not owner.data:
        raise HTTPException(403, "Access denied")
    return OrderResponse(**order)
