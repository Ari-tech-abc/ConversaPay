from decimal import Decimal
from fastapi import APIRouter,HTTPException,status,Depends
from typing import Dict,Any
from datetime import datetime,timedelta
from supabase import create_client,Client
from backend.config import settings
from backend.middleware.auth import AuthUser,require_auth
from backend.models.schemas import AnalyticsOverviewResponse
from backend.services.money import money,money_db
router=APIRouter(prefix="/analytics",tags=["analytics"]); supabase:Client=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)
def _sum(rows): return sum((money(x.get("total")) for x in rows),Decimal("0.00"))
@router.get("/overview",response_model=AnalyticsOverviewResponse)
async def get_analytics_overview(current_user:AuthUser=Depends(require_auth)):
    try:
        try:
            data=supabase.rpc("get_user_analytics_overview",{"p_user_id":current_user.user_id}).execute().data
            if isinstance(data,list):data=data[0] if data else {}
            if not data: raise ValueError("Empty RPC response")
            revenue=money(data.get("total_revenue")); deals=int(data.get("closed_deals_count",0)); conversations=int(data.get("total_conversations",0))
        except Exception:
            businesses=supabase.table("businesses").select("id").eq("owner_id",current_user.user_id).execute().data or []; ids=[b["id"] for b in businesses]
            if not ids:return AnalyticsOverviewResponse()
            rows=supabase.table("orders").select("total").in_("business_id",ids).eq("status","paid").execute().data or []; revenue=_sum(rows); deals=len(rows); conversations=supabase.table("conversations").select("id",count="exact").in_("business_id",ids).execute().count or 0
        return AnalyticsOverviewResponse(total_revenue=revenue,closed_deals_count=deals,average_order_value=(revenue/Decimal(deals)).quantize(Decimal("0.01")) if deals else Decimal("0.00"),total_conversations=conversations)
    except Exception as exc: raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,"Failed to fetch analytics overview") from exc
@router.get("/businesses/{business_id}/analytics",response_model=Dict[str,Any])
async def get_business_analytics(business_id:str,current_user:AuthUser=Depends(require_auth)):
    business=supabase.table("businesses").select("id").eq("id",business_id).eq("owner_id",current_user.user_id).execute()
    if not business.data: raise HTTPException(404,"Business not found")
    paid=supabase.table("orders").select("total,items").eq("business_id",business_id).eq("status","paid").execute().data or []; all_orders=supabase.table("orders").select("id",count="exact").eq("business_id",business_id).execute(); conv=supabase.table("conversations").select("session_id").eq("business_id",business_id).execute().data or []; total_orders=all_orders.count or len(all_orders.data or []); sessions=len({x['session_id'] for x in conv}); revenue=_sum(paid); products={}
    for order in paid:
        for item in order.get('items') or []:
            key=item.get('item_key');
            if key: products.setdefault(key,{"item_key":key,"name":item.get('name','Unknown Product'),"total_quantity":0,"order_count":0}); products[key]["total_quantity"]+=int(item.get('quantity',1)); products[key]["order_count"]+=1
    customers=supabase.table("customers").select("id",count="exact").eq("business_id",business_id).execute(); return {"business_id":business_id,"period_days":30,"generated_at":datetime.utcnow().isoformat(),"total_revenue":money_db(revenue),"total_orders":total_orders,"total_customers":customers.count or len(customers.data or []),"conversion_rate":round(len(paid)/sessions*100,2) if sessions else 0,"average_order_value":money_db(revenue/Decimal(total_orders)) if total_orders else "0.00","orders_by_status":{},"top_selling_products":sorted(products.values(),key=lambda x:x['total_quantity'],reverse=True)[:10],"unique_chat_sessions":sessions,"paid_orders_count":len(paid)}
@router.get("/businesses/{business_id}/revenue",response_model=Dict[str,Any])
async def get_revenue_analytics(business_id:str,days:int=30,current_user:AuthUser=Depends(require_auth)):
    business=supabase.table("businesses").select("id").eq("id",business_id).eq("owner_id",current_user.user_id).execute()
    if not business.data: raise HTTPException(404,"Business not found")
    end=datetime.utcnow(); start=end-timedelta(days=days); rows=supabase.table("orders").select("total,created_at").eq("business_id",business_id).eq("status","paid").gte("created_at",start.isoformat()).lte("created_at",end.isoformat()).order("created_at").execute().data or []; daily={}
    for row in rows: daily[row['created_at'][:10]]=daily.get(row['created_at'][:10],Decimal('0'))+money(row['total'])
    series=[]; current=start
    while current<=end: key=current.strftime('%Y-%m-%d'); series.append({"date":key,"revenue":money_db(daily.get(key,0))}); current+=timedelta(days=1)
    return {"business_id":business_id,"period_days":days,"start_date":start.isoformat(),"end_date":end.isoformat(),"total_revenue":money_db(sum((money(x['revenue']) for x in series),Decimal('0'))),"revenue_by_day":series}
@router.get("/businesses/{business_id}/orders",response_model=Dict[str,Any])
async def get_order_analytics(business_id:str,days:int=30,current_user:AuthUser=Depends(require_auth)):
    business=supabase.table("businesses").select("id").eq("id",business_id).eq("owner_id",current_user.user_id).execute()
    if not business.data: raise HTTPException(404,"Business not found")
    end=datetime.utcnow(); start=end-timedelta(days=days); rows=supabase.table("orders").select("status,created_at").eq("business_id",business_id).gte("created_at",start.isoformat()).lte("created_at",end.isoformat()).execute().data or []; by_day={}; counts={}
    for row in rows: key=row['created_at'][:10]; status=row['status']; counts[status]=counts.get(status,0)+1; by_day.setdefault(key,{}); by_day[key][status]=by_day[key].get(status,0)+1
    series=[]; current=start
    while current<=end: key=current.strftime('%Y-%m-%d'); data=by_day.get(key,{}); series.append({"date":key,"total":sum(data.values()),"by_status":data}); current+=timedelta(days=1)
    return {"business_id":business_id,"period_days":days,"start_date":start.isoformat(),"end_date":end.isoformat(),"total_orders":len(rows),"orders_by_status":counts,"orders_by_day":series}
