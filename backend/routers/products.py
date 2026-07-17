"""
Products router for managing product catalogs.
Requires authentication - users can only manage their own business products.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
import logging

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth, require_business_owner_for_business_id
from backend.models.schemas import ProductCreate, ProductUpdate, ProductResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: ProductCreate,
    current_user: AuthUser = Depends(require_auth),
):
    """Create a new product for a business (authenticated owner only)."""
    try:
        business_uuid = require_business_owner_for_business_id(request.business_id, current_user)

        existing = supabase.table("products")\
            .select("id")\
            .eq("business_id", business_uuid)\
            .eq("item_key", request.item_key.upper())\
            .execute()

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with item_key '{request.item_key}' already exists",
            )

        product_data = {
            "business_id": business_uuid,
            "item_key": request.item_key.upper(),
            "name": request.name,
            "description": request.description,
            "price": request.price,
            "currency": request.currency,
            "image_url": request.image_url,
            "is_active": request.is_active,
            "inventory_count": request.inventory_count,
            "metadata": request.metadata,
        }

        result = supabase.table("products")\
            .insert(product_data)\
            .execute()

        if result.data:
            logger.info(
                f"Product created: {request.item_key} for business {request.business_id}"
            )
            return ProductResponse(**result.data[0])

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating product: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create product",
        )


@router.get("", response_model=List[ProductResponse])
async def get_products(
    business_id: str = Query(..., description="Business identifier"),
    active_only: bool = Query(True, description="Return only active products"),
    current_user: AuthUser = Depends(require_auth),
):
    """Get all products for a business (authenticated owner only)."""
    try:
        business_uuid = require_business_owner_for_business_id(business_id, current_user)

        query = supabase.table("products")\
            .select("*")\
            .eq("business_id", business_uuid)

        if active_only:
            query = query.eq("is_active", True)

        result = query.order("item_key", desc=False).execute()

        return [ProductResponse(**product) for product in result.data] if result.data else []

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching products: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products",
        )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str,
    current_user: AuthUser = Depends(require_auth),
):
    """Get a specific product by ID (owner of product's business only)."""
    try:
        result = supabase.table("products")\
            .select("*")\
            .eq("id", product_id)\
            .execute()

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        product = result.data[0]

        # Verify ownership via business
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", product["business_id"])\
            .eq("owner_id", current_user.user_id)\
            .execute()

        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        return ProductResponse(**product)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching product: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch product",
        )


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    request: ProductUpdate,
    current_user: AuthUser = Depends(require_auth),
):
    """Update a product (owner of product's business only)."""
    try:
        product_result = supabase.table("products")\
            .select("business_id")\
            .eq("id", product_id)\
            .execute()

        if not product_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        business_uuid = product_result.data[0]["business_id"]

        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_uuid)\
            .eq("owner_id", current_user.user_id)\
            .execute()

        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        update_data = request.model_dump(exclude_none=True)

        if "item_key" in update_data:
            update_data["item_key"] = update_data["item_key"].upper()

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data to update",
            )

        result = supabase.table("products")\
            .update(update_data)\
            .eq("id", product_id)\
            .execute()

        if result.data:
            logger.info(f"Product updated: {product_id}")
            return ProductResponse(**result.data[0])

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update product",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating product: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update product",
        )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: str,
    current_user: AuthUser = Depends(require_auth),
):
    """Delete a product (owner of product's business only)."""
    try:
        product_result = supabase.table("products")\
            .select("business_id")\
            .eq("id", product_id)\
            .execute()

        if not product_result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found",
            )

        business_uuid = product_result.data[0]["business_id"]

        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_uuid)\
            .eq("owner_id", current_user.user_id)\
            .execute()

        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            )

        supabase.table("products")\
            .delete()\
            .eq("id", product_id)\
            .execute()

        logger.info(f"Product deleted: {product_id}")
        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting product: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete product",
        )


@router.get("/business/{business_id}/public", response_model=List[ProductResponse])
async def get_public_products(business_id: str):
    """Public endpoint for chat widget: returns active products only."""
    try:
        business = supabase.table("businesses")\
            .select("id")\
            .eq("business_id", business_id)\
            .execute()

        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found",
            )

        business_uuid = business.data[0]["id"]

        result = supabase.table("products")\
            .select("*")\
            .eq("business_id", business_uuid)\
            .eq("is_active", True)\
            .order("item_key", desc=False)\
            .execute()

        return [ProductResponse(**product) for product in result.data] if result.data else []

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching public products: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch products",
        )

