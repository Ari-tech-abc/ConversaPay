from fastapi import APIRouter,HTTPException,status,Depends,Query
from typing import List
import logging
from supabase import create_client,Client
from backend.config import settings
from backend.middleware.auth import AuthUser,require_auth,require_business_owner_for_business_id
from backend.models.schemas import ProductCreate,ProductUpdate,ProductResponse
from backend.services.money import money_db
logger=logging.getLogger(__name__); router=APIRouter(prefix="/products",tags=["products"]); supabase:Client=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)
def _normalized_item_key(value): return value.strip().upper()
def _db_product(data):
    payload=dict(data)
    if "price" in payload: payload["price"]=money_db(payload["price"])
    return payload
@router.post("",response_model=ProductResponse,status_code=201)
async def create_product(request:ProductCreate,current_user:AuthUser=Depends(require_auth)):
    business_uuid=require_business_owner_for_business_id(request.business_id,current_user); item_key=_normalized_item_key(request.item_key)
    if supabase.table("products").select("id").eq("business_id",business_uuid).eq("item_key",item_key).execute().data: raise HTTPException(400,f"Product with item_key '{request.item_key}' already exists")
    result=supabase.table("products").insert({"business_id":business_uuid,"item_key":item_key,"name":request.name.strip(),"description":request.description,"price":money_db(request.price),"currency":request.currency.upper(),"image_url":str(request.image_url) if request.image_url else None,"payment_link":str(request.payment_link) if request.payment_link else None,"is_active":request.is_active,"inventory_count":request.inventory_count,"metadata":request.metadata}).execute()
    if not result.data: raise HTTPException(500,"Failed to create product")
    return ProductResponse(**_db_product(result.data[0]))
@router.get("",response_model=List[ProductResponse])
async def get_products(business_id:str=Query(...),active_only:bool=Query(True),current_user:AuthUser=Depends(require_auth)):
    q=supabase.table("products").select("*").eq("business_id",require_business_owner_for_business_id(business_id,current_user)); q=q.eq("is_active",True) if active_only else q
    return [ProductResponse(**_db_product(x)) for x in (q.order("item_key").execute().data or [])]
@router.get("/{product_id}",response_model=ProductResponse)
async def get_product(product_id:str,current_user:AuthUser=Depends(require_auth)):
    result=supabase.table("products").select("*").eq("id",product_id).execute()
    if not result.data: raise HTTPException(404,"Product not found")
    if not supabase.table("businesses").select("id").eq("id",result.data[0]["business_id"]).eq("owner_id",current_user.user_id).execute().data: raise HTTPException(403,"Access denied")
    return ProductResponse(**_db_product(result.data[0]))
@router.patch("/{product_id}",response_model=ProductResponse)
@router.put("/{product_id}",response_model=ProductResponse)
async def update_product(product_id:str,request:ProductUpdate,current_user:AuthUser=Depends(require_auth)):
    product=supabase.table("products").select("business_id,item_key").eq("id",product_id).execute()
    if not product.data: raise HTTPException(404,"Product not found")
    bid=product.data[0]["business_id"]
    if not supabase.table("businesses").select("id").eq("id",bid).eq("owner_id",current_user.user_id).execute().data: raise HTTPException(403,"Access denied")
    data=request.model_dump(exclude_none=True)
    if "item_key" in data:
        requested_key=_normalized_item_key(data["item_key"])
        existing_key=_normalized_item_key(product.data[0]["item_key"])
        if requested_key != existing_key:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,"item_key cannot be changed after product creation")
        data.pop("item_key")
    if "name" in data:data["name"]=data["name"].strip()
    if "currency" in data:data["currency"]=data["currency"].upper()
    if "price" in data:data["price"]=money_db(data["price"])
    if not data: raise HTTPException(400,"No mutable product fields to update")
    result=supabase.table("products").update(data).eq("id",product_id).execute()
    if not result.data: raise HTTPException(500,"Failed to update product")
    return ProductResponse(**_db_product(result.data[0]))
@router.delete("/{product_id}",status_code=204)
async def delete_product(product_id:str,current_user:AuthUser=Depends(require_auth)):
    result=supabase.table("products").select("business_id").eq("id",product_id).execute()
    if not result.data: raise HTTPException(404,"Product not found")
    if not supabase.table("businesses").select("id").eq("id",result.data[0]["business_id"]).eq("owner_id",current_user.user_id).execute().data: raise HTTPException(403,"Access denied")
    supabase.table("products").delete().eq("id",product_id).execute()
@router.get("/business/{business_id}/public",response_model=List[ProductResponse])
async def get_public_products(business_id:str):
    business=supabase.table("businesses").select("id").eq("business_id",business_id).execute()
    if not business.data: raise HTTPException(404,"Business not found")
    result=supabase.table("products").select("*").eq("business_id",business.data[0]["id"]).eq("is_active",True).order("item_key").execute()
    return [ProductResponse(**_db_product(x)) for x in (result.data or [])]
