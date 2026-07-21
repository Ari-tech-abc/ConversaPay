"""
Business router for managing business profiles.
Requires authentication - users can only access their own businesses.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
import logging

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, get_current_user, require_auth
from backend.models.schemas import BusinessCreate, BusinessUpdate, BusinessResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/businesses", tags=["businesses"])

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


@router.post("", response_model=BusinessResponse, status_code=status.HTTP_201_CREATED)
async def create_business(
    request: BusinessCreate,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Create a new business for the authenticated user.
    Only Pro users (is_pro == true) can create businesses.
    """
    try:
        # Check if business_id already exists
        existing = supabase.table("businesses")\
            .select("id")\
            .eq("business_id", request.business_id)\
            .execute()
        
        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Business ID already exists"
            )
        
        # Pro Subscription Gate: Check if user has Pro or Premium status
        profile = supabase.table("profiles")\
            .select("plan_type, subscription_expires_at")\
            .eq("user_id", current_user.user_id)\
            .execute()
        
        is_pro = False
        if profile.data:
            plan_type = profile.data[0].get('plan_type', 'free')
            is_pro = plan_type in ['pro', 'premium']
            # Check if subscription is still valid
            expires_at = profile.data[0].get('subscription_expires_at')
            if expires_at:
                from datetime import datetime
                expires_datetime = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if expires_datetime < datetime.utcnow():
                    is_pro = False
        
        if not is_pro:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Pro subscription required. Please upgrade to Pro Plan to create a business."
            )
        
        # Create business
        business_data = {
            "business_id": request.business_id,
            "business_name": request.business_name,
            "description": request.description,
            "owner_id": current_user.user_id,
            "subscription_tier": "pro",
            "subscription_status": "active",
            "is_active": True
        }
        
        result = supabase.table("businesses")\
            .insert(business_data)\
            .execute()
        
        if result.data:
            logger.info(f"Business created: {request.business_id} by user {current_user.email}")
            return BusinessResponse(**result.data[0])
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create business"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating business: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create business"
        )


@router.get("", response_model=List[BusinessResponse])
async def get_businesses(
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get all businesses for the authenticated user.
    """
    try:
        result = supabase.table("businesses")\
            .select("*")\
            .eq("owner_id", current_user.user_id)\
            .order("created_at", desc=True)\
            .execute()
        
        return [BusinessResponse(**business) for business in result.data] if result.data else []
    
    except Exception as e:
        logger.error(f"Error fetching businesses: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch businesses"
        )


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(
    business_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get a specific business by ID.
    User must be the owner of the business.
    """
    try:
        result = supabase.table("businesses")\
            .select("*")\
            .eq("id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        return BusinessResponse(**result.data[0])
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching business: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch business"
        )


@router.patch("/{business_id}", response_model=BusinessResponse)
async def update_business(
    business_id: str,
    request: BusinessUpdate,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Update a business.
    User must be the owner of the business.
    """
    try:
        # Verify ownership
        existing = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        # Build update data
        update_data = request.model_dump(exclude_none=True)
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data to update"
            )
        
        # Update business
        result = supabase.table("businesses")\
            .update(update_data)\
            .eq("id", business_id)\
            .execute()
        
        if result.data:
            logger.info(f"Business updated: {business_id}")
            return BusinessResponse(**result.data[0])
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update business"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating business: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update business"
        )


@router.delete("/{business_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_business(
    business_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Delete a business.
    User must be the owner of the business.
    """
    try:
        # Verify ownership
        existing = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not existing.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        # Delete business (cascade will handle related records)
        supabase.table("businesses")\
            .delete()\
            .eq("id", business_id)\
            .execute()
        
        logger.info(f"Business deleted: {business_id}")
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting business: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete business"
        )


@router.get("/{business_id}/stats", response_model=dict)
async def get_business_stats(
    business_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """
    Get statistics for a business.
    """
    try:
        # Verify ownership
        business = supabase.table("businesses")\
            .select("id")\
            .eq("id", business_id)\
            .eq("owner_id", current_user.user_id)\
            .execute()
        
        if not business.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business not found"
            )
        
        business_uuid = business.data[0]['id']
        
        # Get stats
        from datetime import datetime, timedelta
        
        # Conversations count
        conversations = supabase.table("conversations")\
            .select("id", count="exact")\
            .eq("business_id", business_uuid)\
            .execute()
        
        # Orders count and revenue
        orders = supabase.table("orders")\
            .select("total, status", count="exact")\
            .eq("business_id", business_uuid)\
            .execute()
        
        # Customers count
        customers = supabase.table("customers")\
            .select("id", count="exact")\
            .eq("business_id", business_uuid)\
            .execute()
        
        # Calculate stats
        total_orders = orders.count if hasattr(orders, 'count') else len(orders.data)
        total_revenue = sum(order['total'] for order in orders.data) if orders.data else 0
        total_customers = customers.count if hasattr(customers, 'count') else len(customers.data)
        total_conversations = conversations.count if hasattr(conversations, 'count') else len(conversations.data)
        
        # Calculate conversion rate (orders / conversations)
        conversion_rate = (total_orders / total_conversations * 100) if total_conversations > 0 else 0
        
        return {
            "business_id": business_id,
            "total_conversations": total_conversations,
            "total_orders": total_orders,
            "total_revenue": round(total_revenue, 2),
            "total_customers": total_customers,
            "conversion_rate": round(conversion_rate, 2)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching business stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch business stats"
        )