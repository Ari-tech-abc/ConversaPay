"""Dashboard APIs with explicit three-tier feature gates."""
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

PLANS = {
    "free": {"products": True, "analytics": True, "profile": True, "domains": False, "orders": False, "sales": False, "wordpress": False, "html_embed": False, "whatsapp": False, "site_builder": False, "api_key_limit": 0, "domain_limit": 0},
    "pro": {"products": True, "analytics": True, "profile": True, "domains": True, "orders": True, "sales": True, "wordpress": True, "html_embed": True, "whatsapp": False, "site_builder": False, "api_key_limit": 3, "domain_limit": 3},
    "premium": {"products": True, "analytics": True, "profile": True, "domains": True, "orders": True, "sales": True, "wordpress": True, "html_embed": True, "whatsapp": True, "site_builder": True, "api_key_limit": 10, "domain_limit": 10},
}

def get_user_plan(user_id: str) -> Dict[str, Any]:
    result = supabase.table("profiles").select("plan_type,email_verified,subscription_expires_at,payme_id,whatsapp_phone_number_id").eq("user_id", user_id).maybe_single().execute()
    row = result.data or {}
    plan = row.get("plan_type", "free") if row.get("plan_type", "free") in PLANS else "free"
    return {**row, "plan_type": plan}

def require_verified(user: AuthUser) -> Dict[str, Any]:
    plan = get_user_plan(user.user_id)
    if not plan.get("email_verified", False): raise HTTPException(403, "email_not_verified")
    return plan

def gate(plan: str, feature: str):
    if not PLANS[plan].get(feature): raise HTTPException(403, f"{feature} is unavailable on the {plan.upper()} plan")

@router.get("/profile")
async def profile(current_user: AuthUser = Depends(require_auth)):
    p = require_verified(current_user)
    return {"user_id":current_user.user_id,"email":current_user.email,"plan_type":p["plan_type"],"email_verified":p.get("email_verified",False),"subscription_expires_at":p.get("subscription_expires_at")}

@router.get("/features")
async def features(current_user: AuthUser = Depends(require_auth)):
    p = require_verified(current_user); plan=p["plan_type"]
    return {"plan_type":plan, **PLANS[plan], "upgrade_url":"/upgrade.html" if plan != "premium" else ""}

@router.get("/limits")
async def limits(current_user: AuthUser = Depends(require_auth)):
    p=require_verified(current_user); plan=p["plan_type"]
    return {"plan_type":plan,"domain_limit":PLANS[plan]["domain_limit"],"api_key_limit":PLANS[plan]["api_key_limit"],"features":PLANS[plan]}

@router.get("/analytics")
async def analytics(current_user: AuthUser = Depends(require_auth)):
    p=require_verified(current_user)
    businesses=supabase.table("businesses").select("id,business_name").eq("owner_id",current_user.user_id).execute()
    if not businesses.data: return {"business_id":None,"business_name":"","total_revenue":0,"closed_deals":0,"conversion_rate":0,"average_order_value":0,"total_conversations":0,"charts_data":[]}
    bid=businesses.data[0]["id"]
    paid=supabase.table("orders").select("total").eq("business_id",bid).in_("status",["paid","shipped","delivered"]).execute().data or []
    conversations=supabase.table("conversations").select("session_id").eq("business_id",bid).execute().data or []
    revenue=sum(float(x.get("total",0)) for x in paid); deals=len(paid); sessions=len({x.get("session_id") for x in conversations if x.get("session_id")})
    return {"business_id":bid,"business_name":businesses.data[0]["business_name"],"total_revenue":round(revenue,2),"closed_deals":deals,"conversion_rate":round(deals/sessions*100,2) if sessions else 0,"average_order_value":round(revenue/deals,2) if deals else 0,"total_conversations":sessions,"charts_data":[]}

@router.get("/products")
async def products(current_user: AuthUser = Depends(require_auth)):
    require_verified(current_user); businesses=supabase.table("businesses").select("id").eq("owner_id",current_user.user_id).execute()
    if not businesses.data:return {"products":[],"total":0}
    rows=supabase.table("products").select("id,name,price,inventory_count,metadata").eq("business_id",businesses.data[0]["id"]).execute().data or []
    return {"products":[{"id":x.get("id"),"name":x.get("name"),"price":x.get("price",0),"stock":x.get("inventory_count",-1),"category":(x.get("metadata") or {}).get("category","")} for x in rows],"total":len(rows)}

@router.get("/orders")
async def orders(current_user: AuthUser = Depends(require_auth)):
    p=require_verified(current_user); plan=p["plan_type"]; businesses=supabase.table("businesses").select("id").eq("owner_id",current_user.user_id).execute()
    if not businesses.data:return {"orders":[],"total_count":0,"locked":False}
    rows=supabase.table("orders").select("id,order_number,status,total,customer_info,created_at").eq("business_id",businesses.data[0]["id"]).order("created_at",desc=True).limit(50).execute().data or []
    if not PLANS[plan]["orders"]: return {"orders":rows[:5],"total_count":len(rows[:5]),"locked":True,"lock_message":"ניהול הזמנות ומכירות זמין במסלולי PRO ו-PREMIUM.","upgrade_url":"/upgrade.html"}
    return {"orders":rows,"total_count":len(rows),"locked":False}

@router.get("/upgrade-options")
async def upgrade_options(current_user: AuthUser = Depends(require_auth)):
    p=require_verified(current_user); current=p["plan_type"]; plans=[]
    if current=="free": plans.append({"plan_name":"PRO","price":200,"currency":"ILS","features":["ניהול דומיינים","ניהול הזמנות ומכירות","ווידג׳ט","עד 3 API keys"],"upgrade_url":"/pay?plan=pro"})
    if current in ("free","pro"): plans.append({"plan_name":"PREMIUM","price":350,"currency":"ILS","features":["כל תכונות PRO","WhatsApp","בונה אתרים חד-פעמי","עד 10 API keys"],"upgrade_url":"/pay?plan=premium"})
    return {"plans":plans,"current_tier":current}

@router.get("/builder-access")
async def builder_access(current_user: AuthUser = Depends(require_auth)):
    p=require_verified(current_user); gate(p["plan_type"],"site_builder")
    return {"available":True,"start_url":"/api/v1/site-builder/access"}

@router.get("/settings")
async def settings_page(current_user: AuthUser = Depends(require_auth)):
    p=require_verified(current_user); return {"plan_type":p["plan_type"],"payme_id":p.get("payme_id"),"whatsapp_phone":p.get("whatsapp_phone_number_id"),"domain_limit":PLANS[p["plan_type"]]["domain_limit"],"api_key_limit":PLANS[p["plan_type"]]["api_key_limit"]}
