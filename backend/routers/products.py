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
@router.post("/bulk")
async def create_products_bulk(request: List[ProductCreate], current_user: AuthUser = Depends(require_auth)):
    """Create many products in one authenticated request for dashboard imports."""
    if not request:
        return {"created": 0, "skipped": 0, "errors": [], "created_ids": []}
    if len(request) > 500:
        raise HTTPException(400, "Maximum 500 products per import")
    business_ids = {str(item.business_id) for item in request}
    if len(business_ids) != 1:
        raise HTTPException(400, "All imported products must belong to the same business")
    business_uuid = require_business_owner_for_business_id(str(request[0].business_id), current_user)

    normalized = []
    seen = set()
    errors = []
    for index, item in enumerate(request, start=1):
        key = _normalized_item_key(item.item_key)
        if key in seen:
            errors.append({"row": index, "item_key": key, "reason": "duplicate_in_file"})
            continue
        seen.add(key)
        normalized.append((index, item, key))

    existing = supabase.table("products").select("item_key").eq("business_id", business_uuid).in_("item_key", [x[2] for x in normalized]).execute().data or []
    existing_keys = {_normalized_item_key(x.get("item_key", "")) for x in existing}

    rows = []
    for index, item, key in normalized:
        if key in existing_keys:
            errors.append({"row": index, "item_key": key, "reason": "already_exists"})
            continue
        rows.append({
            "business_id": business_uuid,
            "item_key": key,
            "name": item.name.strip(),
            "description": item.description,
            "price": money_db(item.price),
            "currency": item.currency.upper(),
            "image_url": str(item.image_url) if item.image_url else None,
            "payment_link": str(item.payment_link) if item.payment_link else None,
            "is_active": item.is_active,
            "inventory_count": item.inventory_count,
            "metadata": item.metadata,
        })

    if not rows:
        return {"created": 0, "skipped": len(errors), "errors": errors, "created_ids": []}

    try:
        result = supabase.table("products").insert(rows).execute()
    except Exception as exc:
        logger.exception("Bulk product import failed")
        raise HTTPException(500, "Bulk product import failed") from exc

    created_rows = result.data or []
    return {
        "created": len(created_rows),
        "skipped": len(errors),
        "errors": errors,
        "created_ids": [str(x["id"]) for x in created_rows if x.get("id")],
    }


@router.get("",response_model=List[ProductResponse])
async def get_products(business_id:str=Query(...),active_only:bool=Query(True),current_user:AuthUser=Depends(require_auth)):
    q=supabase.table("products").select("*").eq("business_id",require_business_owner_for_business_id(business_id,current_user)); q=q.eq("is_active",True) if active_only else q
    return [ProductResponse(**_db_product(x)) for x in (q.order("item_key").execute().data or [])]
@router.get("/paged")
async def get_products_paged(
    business_id:str=Query(...),
    active_only:bool=Query(False),
    page:int=Query(1,ge=1),
    page_size:int=Query(50,ge=1,le=100),
    current_user:AuthUser=Depends(require_auth)
):
    business_uuid=require_business_owner_for_business_id(business_id,current_user)
    q=supabase.table("products").select("*",count="exact").eq("business_id",business_uuid)
    if active_only:
        q=q.eq("is_active",True)
    start=(page-1)*page_size
    end=start+page_size-1
    result=q.order("item_key").range(start,end).execute()
    total=int(result.count or 0)
    products=[ProductResponse(**_db_product(x)) for x in (result.data or [])]
    return {
        "products":products,
        "total":total,
        "page":page,
        "page_size":page_size,
        "total_pages":(total+page_size-1)//page_size if total else 0
    }

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
