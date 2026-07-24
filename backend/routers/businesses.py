"""Business router for managing authenticated users' own businesses."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
import logging
import re
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import BusinessCreate, BusinessUpdate, BusinessResponse
from backend.routers.dashboard import normalize_plan, subscription_active
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/businesses", tags=["businesses"])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _response_business(data: dict) -> BusinessResponse:
    """Build a response even for legacy IDs containing non-ASCII characters."""
    payload = dict(data)
    business_id = str(payload.get("business_id") or "")
    if not re.fullmatch(r"[a-z0-9_]+", business_id):
        # The database row ID is stable and is what authenticated dashboard
        # calls use. Expose it as the compatibility slug for old rows.
        payload["business_id"] = f"business_{str(payload.get('id', 'legacy')).replace('-', '_')}"
    return BusinessResponse(**payload)


@router.post("", response_model=BusinessResponse, status_code=status.HTTP_201_CREATED)
async def create_business(request: BusinessCreate, current_user: AuthUser = Depends(require_auth)):
    try:
        if supabase.table("businesses").select("id").eq("business_id", request.business_id).execute().data: raise HTTPException(400, "Business ID already exists")
        profile = supabase.table("profiles").select("plan_type,subscription_expires_at").eq("user_id", current_user.user_id).maybe_single().execute().data or {}
        plan = normalize_plan(profile.get("plan_type")) if subscription_active(profile) else "free"
        if plan == "free": raise HTTPException(403, "Pro subscription required")
        data = {"business_id": request.business_id, "business_name": request.business_name, "description": request.description, "owner_id": current_user.user_id, "subscription_tier": plan, "subscription_status": "active", "is_active": True}
        result = supabase.table("businesses").insert(data).execute()
        if not result.data: raise HTTPException(500, "Failed to create business")
        return _response_business(result.data[0])
    except HTTPException: raise
    except Exception as exc:
        logger.error("Error creating business: %s", exc, exc_info=True); raise HTTPException(500, "Failed to create business")


@router.get("", response_model=List[BusinessResponse])
async def get_businesses(current_user: AuthUser = Depends(require_auth)):
    result = supabase.table("businesses").select("*").eq("owner_id", current_user.user_id).order("created_at", desc=True).execute()
    return [_response_business(item) for item in (result.data or [])]


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_business(business_id: str, current_user: AuthUser = Depends(require_auth)):
    result = supabase.table("businesses").select("*").eq("id", business_id).eq("owner_id", current_user.user_id).execute()
    if not result.data: raise HTTPException(404, "Business not found")
    return _response_business(result.data[0])


@router.patch("/{business_id}", response_model=BusinessResponse)
async def update_business(business_id: str, request: BusinessUpdate, current_user: AuthUser = Depends(require_auth)):
    if not supabase.table("businesses").select("id").eq("id", business_id).eq("owner_id", current_user.user_id).execute().data: raise HTTPException(404, "Business not found")
    data=request.model_dump(exclude_none=True)
    if not data: raise HTTPException(400, "No data to update")
    result=supabase.table("businesses").update(data).eq("id",business_id).execute()
    if not result.data: raise HTTPException(500,"Failed to update business")
    return _response_business(result.data[0])


@router.delete("/{business_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_business(business_id: str, current_user: AuthUser = Depends(require_auth)):
    if not supabase.table("businesses").select("id").eq("id",business_id).eq("owner_id",current_user.user_id).execute().data: raise HTTPException(404,"Business not found")
    supabase.table("businesses").delete().eq("id",business_id).execute()


@router.get("/{business_id}/stats", response_model=dict)
async def get_business_stats(business_id: str, current_user: AuthUser = Depends(require_auth)):
    if not supabase.table("businesses").select("id").eq("id",business_id).eq("owner_id",current_user.user_id).execute().data: raise HTTPException(404,"Business not found")
    conv=supabase.table("conversations").select("id",count="exact").eq("business_id",business_id).execute(); orders=supabase.table("orders").select("total,status").eq("business_id",business_id).execute(); customers=supabase.table("customers").select("id",count="exact").eq("business_id",business_id).execute()
    total_orders=len(orders.data or []); revenue=sum(float(x.get("total") or 0) for x in (orders.data or [])); total_conv=conv.count if conv.count is not None else len(conv.data or [])
    return {"business_id":business_id,"total_conversations":total_conv,"total_orders":total_orders,"total_revenue":round(revenue,2),"total_customers":customers.count if customers.count is not None else len(customers.data or []),"conversion_rate":round(total_orders/total_conv*100,2) if total_conv else 0}
