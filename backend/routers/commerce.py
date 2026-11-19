"""Explicit fulfillment settings; no invented shipping defaults."""
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser,require_auth,require_business_owner_for_business_id
from backend.services.money import money_db

router=APIRouter(prefix="/businesses",tags=["commerce"])
supabase=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)

class FulfillmentSettings(BaseModel):
    pickup_ils:Decimal|None=Field(default=None,ge=0,le=100000,max_digits=10,decimal_places=2)
    shipping_ils:Decimal|None=Field(default=None,ge=0,le=100000,max_digits=10,decimal_places=2)
    shipping_business_days:list[int]=Field(default_factory=list,max_length=2)

@router.get("/{business_id}/commerce")
def get_commerce(business_id:UUID,user:AuthUser=Depends(require_auth)):
    bid=require_business_owner_for_business_id(str(business_id),user)
    rows=supabase.table("businesses").select("settings").eq("id",bid).execute().data or []
    data=(rows[0].get("settings") or {}) if rows else {}
    return {key:data.get(key) for key in ("pickup_ils","shipping_ils","shipping_business_days")}

@router.put("/{business_id}/commerce")
def save_commerce(business_id:UUID,payload:FulfillmentSettings,user:AuthUser=Depends(require_auth)):
    bid=require_business_owner_for_business_id(str(business_id),user)
    days=payload.shipping_business_days
    if days and (len(days)!=2 or not 0<=days[0]<=days[1]<=365):raise HTTPException(422,"Invalid delivery range")
    changes={"pickup_ils":money_db(payload.pickup_ils) if payload.pickup_ils is not None else None,"shipping_ils":money_db(payload.shipping_ils) if payload.shipping_ils is not None else None,"shipping_business_days":days}
    supabase.rpc("save_commerce_settings",{"p_business_id":bid,"p_user_id":user.user_id,"p_settings":changes}).execute()
    return changes
