from decimal import Decimal
from fastapi import APIRouter,Depends,Query
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser,require_auth,require_business_owner_for_business_id
from backend.models.schemas import AnalyticsOverviewResponse
from backend.services.sales_analytics import business_metrics
router=APIRouter(prefix="/analytics",tags=["analytics"])
supabase=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)

@router.get("/overview",response_model=AnalyticsOverviewResponse)
def get_analytics_overview(current_user:AuthUser=Depends(require_auth)):
    ids=supabase.table("businesses").select("id").eq("owner_id",current_user.user_id).execute().data or []
    metrics=[business_metrics(supabase,row["id"],None) for row in ids]
    revenue=sum((Decimal(row["total_revenue"]) for row in metrics),Decimal(0))
    deals=sum(row["closed_deals"] for row in metrics)
    return AnalyticsOverviewResponse(total_revenue=revenue,closed_deals_count=deals,average_order_value=revenue/deals if deals else 0,total_conversations=sum(row["total_conversations"] for row in metrics))

@router.get("/businesses/{business_id}/analytics")
def get_business_analytics(business_id:str,current_user:AuthUser=Depends(require_auth)):
    bid=require_business_owner_for_business_id(business_id,current_user)
    return business_metrics(supabase,bid,30)

@router.get("/businesses/{business_id}/revenue")
def get_revenue_analytics(business_id:str,days:int=Query(30,ge=1,le=3650),current_user:AuthUser=Depends(require_auth)):
    return business_metrics(supabase,require_business_owner_for_business_id(business_id,current_user),days)

@router.get("/businesses/{business_id}/orders")
def get_order_analytics(business_id:str,days:int=Query(30,ge=1,le=3650),current_user:AuthUser=Depends(require_auth)):
    return business_metrics(supabase,require_business_owner_for_business_id(business_id,current_user),days)
