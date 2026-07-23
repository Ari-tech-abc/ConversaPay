"""Order routes with server-side catalog pricing and ownership checks."""
import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth, require_business_owner_for_business_id
from backend.models.schemas import OrderCreate, OrderUpdate, OrderResponse, OrderStatus
router=APIRouter(prefix="/orders",tags=["orders"]); supabase=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)
def _order_number(): return f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"
def _catalog_order(request,business_uuid):
    if not request.items: raise HTTPException(400,"An order must contain at least one item")
    keys=list({x.item_key for x in request.items}); result=supabase.table("products").select("id,item_key,name,price,currency").eq("business_id",business_uuid).eq("is_active",True).in_("item_key",keys).execute(); products={x["item_key"]:x for x in (result.data or [])}
    if len(products)!=len(keys): raise HTTPException(400,"One or more products are unavailable")
    currency=None; items=[]; subtotal=0.0
    for requested in request.items:
        p=products[requested.item_key]; pc=p.get("currency","ILS")
        if currency is None: currency=pc
        if pc!=currency: raise HTTPException(400,"All products in an order must use the same currency")
        qty=int(requested.quantity)
        if qty<1 or qty>100: raise HTTPException(400,"Quantity must be between 1 and 100")
        price=float(p["price"]); subtotal+=price*qty; items.append({"product_id":p["id"],"item_key":p["item_key"],"name":p["name"],"quantity":qty,"price":price})
    return items,round(subtotal,2),currency or "ILS"
@router.post("/pay",response_model=OrderResponse,status_code=status.HTTP_201_CREATED)
async def create_order_public(request:OrderCreate):
    business=supabase.table("businesses").select("id").eq("business_id",request.business_id).execute()
    if not business.data:raise HTTPException(404,"Business not found")
    bid=business.data[0]["id"]; items,subtotal,currency=_catalog_order(request,bid); data={"business_id":bid,"customer_id":request.customer_id,"conversation_id":request.conversation_id,"order_number":_order_number(),"status":OrderStatus.PENDING.value,"subtotal":subtotal,"tax":0,"total":subtotal,"currency":currency,"items":items,"customer_info":request.customer_info,"shipping_address":request.shipping_address,"notes":request.notes,"created_at":datetime.utcnow().isoformat()}; result=supabase.table("orders").insert(data).execute()
    if not result.data:raise HTTPException(500,"Failed to create order")
    return OrderResponse(**result.data[0])
@router.post("",response_model=OrderResponse,status_code=status.HTTP_201_CREATED)
async def create_order(request:OrderCreate,current_user:AuthUser=Depends(require_auth)):
    business=supabase.table("businesses").select("id").eq("business_id",request.business_id).eq("owner_id",current_user.user_id).execute()
    if not business.data:raise HTTPException(404,"Business not found")
    bid=business.data[0]["id"]; items,subtotal,currency=_catalog_order(request,bid); result=supabase.table("orders").insert({"business_id":bid,"customer_id":request.customer_id,"conversation_id":request.conversation_id,"order_number":_order_number(),"status":OrderStatus.PENDING.value,"subtotal":subtotal,"tax":0,"total":subtotal,"currency":currency,"items":items,"customer_info":request.customer_info,"shipping_address":request.shipping_address,"notes":request.notes,"created_at":datetime.utcnow().isoformat()}).execute()
    if not result.data:raise HTTPException(500,"Failed to create order")
    return OrderResponse(**result.data[0])
