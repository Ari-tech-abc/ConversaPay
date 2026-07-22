"""Order routes. Public checkout prices are always calculated from the catalog."""
import uuid
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth, require_business_owner_for_business_id
from backend.models.schemas import OrderCreate, OrderUpdate, OrderResponse, OrderStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/orders', tags=['orders'])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

def _order_number() -> str:
    return f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

def _catalog_order(request: OrderCreate, business_uuid: str) -> tuple[list, float, str]:
    """Build an order using only active products and their server-side prices."""
    if not request.items:
        raise HTTPException(400, 'An order must contain at least one item')
    keys = list({item.item_key for item in request.items})
    result = supabase.table('products').select('id,item_key,name,price,currency').eq('business_id', business_uuid).eq('is_active', True).in_('item_key', keys).execute()
    products = {row['item_key']: row for row in (result.data or [])}
    if len(products) != len(keys):
        raise HTTPException(400, 'One or more products are unavailable')
    currency = None
    items, subtotal = [], 0.0
    for requested in request.items:
        product = products[requested.item_key]
        if currency is None: currency = product.get('currency', 'ILS')
        if product.get('currency', 'ILS') != currency:
            raise HTTPException(400, 'All products in an order must use the same currency')
        price = float(product['price'])
        subtotal += price * requested.quantity
        items.append({'product_id': product['id'], 'item_key': product['item_key'], 'name': product['name'], 'quantity': requested.quantity, 'price': price})
    return items, round(subtotal, 2), currency or 'ILS'

@router.get('/{order_id}/public')
async def get_order_public(order_id: str):
    result = supabase.table('orders').select('*, businesses!inner(business_name)').eq('id', order_id).execute()
    if not result.data: raise HTTPException(404, 'Order not found')
    row = result.data[0]
    return {key: row.get(key) for key in ('order_number', 'items', 'total', 'currency', 'status')}

@router.get('/{order_id}/summary')
async def get_order_summary_public(order_id: str):
    result = supabase.table('orders').select('*, businesses!inner(business_name)').eq('id', order_id).execute()
    if not result.data: raise HTTPException(404, 'Order not found')
    row = result.data[0]
    return {'order_id': row['id'], 'order_number': row['order_number'], 'business_name': row.get('businesses', {}).get('business_name', 'Unknown Business'), 'items': row.get('items', []), 'total': row['total'], 'currency': row['currency'], 'status': row['status']}

@router.get('/{order_id}/status')
async def get_order_status_public(order_id: str):
    result = supabase.table('orders').select('status').eq('id', order_id).execute()
    if not result.data: raise HTTPException(404, 'Order not found')
    return {'status': result.data[0]['status']}

@router.post('/pay', response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order_public(request: OrderCreate):
    business = supabase.table('businesses').select('id').eq('business_id', request.business_id).execute()
    if not business.data: raise HTTPException(404, 'Business not found')
    business_uuid = business.data[0]['id']
    # Do not trust client-supplied price, subtotal, tax, total, name or currency.
    items, subtotal, currency = _catalog_order(request, business_uuid)
    data = {'business_id': business_uuid, 'customer_id': request.customer_id, 'conversation_id': request.conversation_id, 'order_number': _order_number(), 'status': OrderStatus.PENDING.value, 'subtotal': subtotal, 'tax': 0, 'total': subtotal, 'currency': currency, 'items': items, 'customer_info': request.customer_info, 'shipping_address': request.shipping_address, 'notes': request.notes, 'created_at': datetime.utcnow().isoformat()}
    result = supabase.table('orders').insert(data).execute()
    if not result.data: raise HTTPException(500, 'Failed to create order')
    return OrderResponse(**result.data[0])

@router.post('', response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(request: OrderCreate, current_user: AuthUser = Depends(require_auth)):
    business = supabase.table('businesses').select('id').eq('business_id', request.business_id).eq('owner_id', current_user.user_id).execute()
    if not business.data: raise HTTPException(404, 'Business not found')
    result = supabase.table('orders').insert({'business_id': business.data[0]['id'], 'customer_id': request.customer_id, 'conversation_id': request.conversation_id, 'order_number': _order_number(), 'status': OrderStatus.PENDING.value, 'subtotal': request.subtotal, 'tax': request.tax, 'total': request.total, 'currency': request.currency, 'items': [item.model_dump() for item in request.items], 'customer_info': request.customer_info, 'shipping_address': request.shipping_address, 'notes': request.notes, 'created_at': datetime.utcnow().isoformat()}).execute()
    if not result.data: raise HTTPException(500, 'Failed to create order')
    return OrderResponse(**result.data[0])

@router.get('', response_model=List[OrderResponse])
async def get_orders(business_id: str = Query(...), status_filter: Optional[OrderStatus] = Query(None), limit: int = Query(50, ge=1, le=100), current_user: AuthUser = Depends(require_auth)):
    business_uuid = require_business_owner_for_business_id(business_id, current_user)
    query = supabase.table('orders').select('*').eq('business_id', business_uuid).order('created_at', desc=True).limit(limit)
    if status_filter: query = query.eq('status', status_filter.value)
    return [OrderResponse(**row) for row in (query.execute().data or [])]

@router.get('/number/{order_number}', response_model=OrderResponse)
async def get_order_by_number(order_number: str, current_user: AuthUser = Depends(require_auth)):
    result = supabase.table('orders').select('*').eq('order_number', order_number).execute()
    if not result.data: raise HTTPException(404, 'Order not found')
    row = result.data[0]; require_business_owner_for_business_id(row['business_id'], current_user)
    return OrderResponse(**row)

@router.get('/{order_id}', response_model=OrderResponse)
async def get_order(order_id: str, current_user: AuthUser = Depends(require_auth)):
    result = supabase.table('orders').select('*').eq('id', order_id).execute()
    if not result.data: raise HTTPException(404, 'Order not found')
    row = result.data[0]; require_business_owner_for_business_id(row['business_id'], current_user)
    return OrderResponse(**row)

@router.patch('/{order_id}', response_model=OrderResponse)
async def update_order(order_id: str, request: OrderUpdate, current_user: AuthUser = Depends(require_auth)):
    found = supabase.table('orders').select('business_id,status').eq('id', order_id).execute()
    if not found.data: raise HTTPException(404, 'Order not found')
    row = found.data[0]; require_business_owner_for_business_id(row['business_id'], current_user)
    updates = request.model_dump(exclude_none=True)
    if not updates: raise HTTPException(400, 'No data to update')
    if request.status:
        transitions = {'pending': ['processing','canceled'], 'processing': ['paid','failed','canceled'], 'paid': ['shipped','refunded'], 'shipped': ['delivered','refunded'], 'delivered': ['refunded'], 'canceled': [], 'refunded': []}
        if request.status.value not in transitions.get(row['status'], []): raise HTTPException(400, f"Invalid status transition from {row['status']} to {request.status.value}")
    result = supabase.table('orders').update(updates).eq('id', order_id).execute()
    if not result.data: raise HTTPException(500, 'Failed to update order')
    return OrderResponse(**result.data[0])
