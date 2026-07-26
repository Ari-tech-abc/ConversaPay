"""
Products router for managing product catalogs.
Requires authentication - users can only manage their own business products.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List
import logging

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth, require_business_owner_for_business_id
from backend.models.schemas import ProductCreate, ProductUpdate, ProductResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/products", tags=["products"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _normalized_item_key(value: str) -> str:
    return value.strip().upper()


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(request: ProductCreate, current_user: AuthUser = Depends(require_auth)):
    """Create a new product for a business (authenticated owner only)."""
    try:
        business_uuid = require_business_owner_for_business_id(request.business_id, current_user)
        item_key = _normalized_item_key(request.item_key)
        existing = supabase.table("products").select("id").eq("business_id", business_uuid).eq("item_key", item_key).execute()
        if existing.data:
            raise HTTPException(status_code=400, detail=f"Product with item_key '{request.item_key}' already exists")

        product_data = {
            "business_id": business_uuid,
            "item_key": item_key,
            "name": request.name.strip(),
            "description": request.description,
            "price": request.price,
            "currency": request.currency.upper(),
            "image_url": str(request.image_url) if request.image_url else None,
            "payment_link": str(request.payment_link) if request.payment_link else None,
            "is_active": request.is_active,
            "inventory_count": request.inventory_count,
            "metadata": request.metadata,
        }
        result = supabase.table("products").insert(product_data).execute()
        if result.data:
            logger.info("Product created: %s for business %s", item_key, request.business_id)
            return ProductResponse(**result.data[0])
        raise HTTPException(status_code=500, detail="Failed to create product")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error creating product: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create product")


@router.get("", response_model=List[ProductResponse])
async def get_products(
    business_id: str = Query(..., description="Business identifier"),
    active_only: bool = Query(True, description="Return only active products"),
    current_user: AuthUser = Depends(require_auth),
):
    """Get all products for a business (authenticated owner only)."""
    try:
        business_uuid = require_business_owner_for_business_id(business_id, current_user)
        query = supabase.table("products").select("*").eq("business_id", business_uuid)
        if active_only:
            query = query.eq("is_active", True)
        result = query.order("item_key", desc=False).execute()
        return [ProductResponse(**product) for product in (result.data or [])]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching products: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch products")


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: str, current_user: AuthUser = Depends(require_auth)):
    """Get a specific product by ID (owner of product's business only)."""
    try:
        result = supabase.table("products").select("*").eq("id", product_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Product not found")
        product = result.data[0]
        business = supabase.table("businesses").select("id").eq("id", product["business_id"]).eq("owner_id", current_user.user_id).execute()
        if not business.data:
            raise HTTPException(status_code=403, detail="Access denied")
        return ProductResponse(**product)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching product: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch product")


@router.patch("/{product_id}", response_model=ProductResponse)
@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(product_id: str, request: ProductUpdate, current_user: AuthUser = Depends(require_auth)):
    """Update a product; PUT remains supported for existing frontend clients."""
    try:
        product_result = supabase.table("products").select("business_id,item_key").eq("id", product_id).execute()
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Product not found")
        product_row = product_result.data[0]
        business_uuid = product_row["business_id"]
        business = supabase.table("businesses").select("id").eq("id", business_uuid).eq("owner_id", current_user.user_id).execute()
        if not business.data:
            raise HTTPException(status_code=403, detail="Access denied")

        update_data = request.model_dump(exclude_none=True)
        if "item_key" in update_data:
            update_data["item_key"] = _normalized_item_key(update_data["item_key"])
            duplicate = supabase.table("products").select("id").eq("business_id", business_uuid).eq("item_key", update_data["item_key"]).neq("id", product_id).execute()
            if duplicate.data:
                raise HTTPException(status_code=400, detail="A product with this item_key already exists")
        if "name" in update_data:
            update_data["name"] = update_data["name"].strip()
        if "currency" in update_data:
            update_data["currency"] = update_data["currency"].upper()
        for field in ("image_url", "payment_link"):
            if field in update_data and update_data[field] is not None:
                update_data[field] = str(update_data[field])
        if not update_data:
            raise HTTPException(status_code=400, detail="No data to update")

        result = supabase.table("products").update(update_data).eq("id", product_id).execute()
        if result.data:
            logger.info("Product updated: %s", product_id)
            return ProductResponse(**result.data[0])
        raise HTTPException(status_code=500, detail="Failed to update product")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error updating product: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update product")


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: str, current_user: AuthUser = Depends(require_auth)):
    """Delete a product (owner of product's business only)."""
    try:
        product_result = supabase.table("products").select("business_id").eq("id", product_id).execute()
        if not product_result.data:
            raise HTTPException(status_code=404, detail="Product not found")
        business_uuid = product_result.data[0]["business_id"]
        business = supabase.table("businesses").select("id").eq("id", business_uuid).eq("owner_id", current_user.user_id).execute()
        if not business.data:
            raise HTTPException(status_code=403, detail="Access denied")
        supabase.table("products").delete().eq("id", product_id).execute()
        logger.info("Product deleted: %s", product_id)
        return None
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error deleting product: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete product")


@router.get("/business/{business_id}/public", response_model=List[ProductResponse])
async def get_public_products(business_id: str):
    """Public endpoint for chat widget: returns active products only."""
    try:
        business = supabase.table("businesses").select("id").eq("business_id", business_id).execute()
        if not business.data:
            raise HTTPException(status_code=404, detail="Business not found")
        result = supabase.table("products").select("*").eq("business_id", business.data[0]["id"]).eq("is_active", True).order("item_key", desc=False).execute()
        return [ProductResponse(**product) for product in (result.data or [])]
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error fetching public products: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch products")
