import base64
import hashlib
import hmac
import time
import uuid
from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, status, Depends, Query, Request
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth, require_business_owner_for_business_id
from backend.middleware.rate_limiter import RateLimiter, check_rate_limit
from backend.models.schemas import OrderCreate, OrderResponse, OrderStatus
from backend.services.money import money, money_db, multiply_money

router=APIRouter(prefix="/orders",tags=["orders"])
supabase=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)
public_order_rate_limiter=RateLimiter(requests_per_minute=30,window_seconds=60,name="public-order-read")
PUBLIC_ORDER_TOKEN_TTL_SECONDS=24*60*60

def _order_number(): return f"ORD-{datetime.utcnow():%Y%m%d}-{uuid.uuid4().hex[:8].upper()}"
def _order_guest_token(order_id:str,expires_at:int|None=None)->str:
    expires_at=expires_at or int(time.time())+PUBLIC_ORDER_TOKEN_TTL_SECONDS
    payload=f"{order_id}.{expires_at}".encode("utf-8")
    signature=hmac.new(settings.SECRET_KEY.encode("utf-8"),payload,hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload+b"."+signature).decode("ascii").rstrip("=")
def _verify_order_guest_token(order_id:str,token:str|None)->bool:
    if not token:return False
    try:
        padded=token+"="*((4-len(token)%4)%4)
        decoded=base64.urlsafe_b64decode(padded.encode("ascii"))
        payload,signature=decoded.rsplit(b".",1)
        token_order_id,expires_at=payload.decode("utf-8").rsplit(".",1)
        expected=hmac.new(settings.SECRET_KEY.encode("utf-8"),payload,hashlib.sha256).digest()
        return token_order_id==order_id and int(expires_at)>=int(time.time()) and hmac.compare_digest(signature,expected)
    except (ValueError,TypeError,UnicodeDecodeError):
        return False

def _order_response(row:dict)->OrderResponse:
    return OrderResponse(**row,public_access_token=_order_guest_token(str(row["id"])))
def _catalog_order(request,business_uuid):
    if not request.items: raise HTTPException(400,"An order must contain at least one item")
    keys=list({x.item_key.strip().upper() for x in request.items})
    result=supabase.table("products").select("id,item_key,name,price,currency,payment_link").eq("business_id",business_uuid).eq("is_active",True).in_("item_key",keys).execute()
    products={x["item_key"].upper():x for x in (result.data or [])}
    if len(products)!=len(keys): raise HTTPException(400,"One or more products are unavailable")
    currency=None; items=[]; subtotal=money(0)
    for requested in request.items:
        product=products[requested.item_key.strip().upper()]; product_currency=str(product.get("currency") or "ILS").upper()
        if currency is None: currency=product_currency
        if product_currency!=currency: raise HTTPException(400,"All products in an order must use the same currency")
        quantity=int(requested.quantity)
        if quantity<1 or quantity>100: raise HTTPException(400,"Quantity must be between 1 and 100")
        price=money(product["price"]); subtotal += multiply_money(price,quantity)
        items.append({"product_id":product["id"],"item_key":product["item_key"],"name":product["name"],"quantity":quantity,"price":money_db(price),"payment_link":product.get("payment_link")})
    return items,money_db(subtotal),currency or "ILS"
def _order_payload(request,business_uuid):
    items,subtotal,currency=_catalog_order(request,business_uuid)
    return {"business_id":business_uuid,"customer_id":request.customer_id,"conversation_id":request.conversation_id,"order_number":_order_number(),"status":OrderStatus.PENDING.value,"payment_status":"pending","subtotal":subtotal,"tax":"0.00","total":subtotal,"currency":currency,"items":items,"customer_info":request.customer_info,"shipping_address":request.shipping_address,"notes":request.notes,"created_at":datetime.utcnow().isoformat()}
@router.post("/pay",response_model=OrderResponse,status_code=status.HTTP_201_CREATED)
async def create_order_public(request:OrderCreate,request_obj:Request):
    check_rate_limit(request_obj); business=supabase.table("businesses").select("id").eq("business_id",request.business_id).eq("is_active",True).execute()
    if not business.data: raise HTTPException(404,"Business not found")
    result=supabase.table("orders").insert(_order_payload(request,business.data[0]["id"])).execute()
    if not result.data: raise HTTPException(500,"Failed to create order")
    return _order_response(result.data[0])
@router.post("",response_model=OrderResponse,status_code=status.HTTP_201_CREATED)
async def create_order(request:OrderCreate,current_user:AuthUser=Depends(require_auth)):
    result=supabase.table("orders").insert(_order_payload(request,require_business_owner_for_business_id(request.business_id,current_user))).execute()
    if not result.data: raise HTTPException(500,"Failed to create order")
    return _order_response(result.data[0])
@router.get("",response_model=List[OrderResponse])
async def list_orders(business_id:str=Query(...),limit:int=Query(50,ge=1,le=100),status_filter:str|None=Query(None),current_user:AuthUser=Depends(require_auth)):
    query=supabase.table("orders").select("*").eq("business_id",require_business_owner_for_business_id(business_id,current_user)).order("created_at",desc=True).limit(limit)
    if status_filter: query=query.eq("status",status_filter)
    return [OrderResponse(**row) for row in (query.execute().data or [])]
@router.get("/{order_id}/public")
async def get_public_order(order_id:str,request:Request,guest_token:str|None=Query(None)):
    check_rate_limit(request,public_order_rate_limiter)
    if not _verify_order_guest_token(order_id,guest_token): raise HTTPException(status_code=403,detail="A valid order access token is required")
    result=supabase.table("orders").select("id,order_number,status,total,currency,items,created_at").eq("id",order_id).maybe_single().execute()
    if not result.data: raise HTTPException(404,"Order not found")
    order=result.data; items=order.get("items") or []
    return {"id":order.get("id"),"order_number":order.get("order_number"),"status":order.get("status"),"total":money_db(order.get("total")),"currency":order.get("currency"),"items":items,"payment_link":items[0].get("payment_link") if len(items)==1 and isinstance(items[0],dict) else None,"created_at":order.get("created_at")}
@router.get("/{order_id}",response_model=OrderResponse)
async def get_order(order_id:str,current_user:AuthUser=Depends(require_auth)):
    result=supabase.table("orders").select("*").eq("id",order_id).maybe_single().execute()
    if not result.data: raise HTTPException(404,"Order not found")
    order=result.data
    if not supabase.table("businesses").select("id").eq("id",order["business_id"]).eq("owner_id",current_user.user_id).maybe_single().execute().data: raise HTTPException(403,"Access denied")
    return OrderResponse(**order)
