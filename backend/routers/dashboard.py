"""Dashboard APIs with explicit free, pro and premium entitlements."""
from fastapi import APIRouter, HTTPException, status, Depends
from typing import Dict, Any
import logging
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

PLANS = {
    "free": {"analytics": True, "product_management": True, "order_management": False, "sales": False, "widget_embed": False, "wordpress_plugin": False, "html_embed": False, "domain_management": False, "whatsapp_integration": False, "site_builder": False, "domain_limit": 1},
    "pro": {"analytics": True, "product_management": True, "order_management": True, "sales": True, "widget_embed": True, "wordpress_plugin": True, "html_embed": True, "domain_management": True, "whatsapp_integration": False, "site_builder": False, "domain_limit": 3},
    "premium": {"analytics": True, "product_management": True, "order_management": True, "sales": True, "widget_embed": True, "wordpress_plugin": True, "html_embed": True, "domain_management": True, "whatsapp_integration": True, "site_builder": True, "domain_limit": 10},
}

def get_user_plan(user_id: str) -> Dict[str, Any]:
    try:
        result = supabase.table("profiles").select("plan_type,email_verified,subscription_expires_at,payme_id,whatsapp_phone_number_id").eq("user_id", user_id).maybe_single().execute()
        row = result.data or {}
        plan = row.get("plan_type", "free")
        return {"plan_type": plan if plan in PLANS else "free", "email_verified": bool(row.get("email_verified", False)), "subscription_expires_at": row.get("subscription_expires_at"), "payme_id": row.get("payme_id"), "whatsapp_phone_number_id": row.get("whatsapp_phone_number_id")}
    except Exception:
        logger.exception("Failed to load user plan")
        return {"plan_type": "free", "email_verified": False}

def require_verified(user: AuthUser):
    if not get_user_plan(user.user_id).get("email_verified"):
        raise HTTPException(status_code=403, detail="email_not_verified")

def entitlements(user: AuthUser):
    plan = get_user_plan(user.user_id)
    features = dict(PLANS.get(plan["plan_type"], PLANS["free"]))
    if plan["plan_type"] == "pro": features["domain_limit"] = 3
    if plan["plan_type"] == "premium": features["domain_limit"] = 10
    return plan, features

@router.get("/profile")
async def profile(current_user: AuthUser = Depends(require_auth)):
    require_verified(current_user); plan, features = entitlements(current_user)
    return {"user_id": current_user.user_id, "email": current_user.email, **plan, "features": features}

@router.get("/features")
async def features(current_user: AuthUser = Depends(require_auth)):
    require_verified(current_user); plan, data = entitlements(current_user)
    data["plan_type"] = plan["plan_type"]
    data["site_builder_url"] = "/site-builder.html" if data["site_builder"] else "/upgrade.html?feature=site_builder"
    return data

@router.get("/upgrade-options")
async def upgrade_options(current_user: AuthUser = Depends(require_auth)):
    require_verified(current_user); plan, _ = entitlements(current_user)
    offers = []
    if plan["plan_type"] == "free": offers.append({"plan_name":"PRO","plan_type":"pro","price":200,"currency":"ILS","upgrade_url":"/pay?plan=pro"})
    if plan["plan_type"] in ("free", "pro"): offers.append({"plan_name":"PREMIUM","plan_type":"premium","price":350,"currency":"ILS","upgrade_url":"/pay?plan=premium"})
    return {"current_tier": plan["plan_type"], "plans": offers}

@router.get("/settings")
async def settings_view(current_user: AuthUser = Depends(require_auth)):
    require_verified(current_user); plan, features = entitlements(current_user)
    return {"plan_type": plan["plan_type"], "payme_id": plan.get("payme_id"), "whatsapp_phone": plan.get("whatsapp_phone_number_id"), "domain_limit": features["domain_limit"], "features": features}

@router.get("/products")
async def products(current_user: AuthUser = Depends(require_auth)):
    require_verified(current_user)
    businesses = supabase.table("businesses").select("id").eq("owner_id", current_user.user_id).execute()
    if not businesses.data: return {"products": [], "total": 0}
    rows = supabase.table("products").select("id,name,price,inventory_count,metadata").eq("business_id", businesses.data[0]["id"]).execute().data or []
    items = [{"id":r["id"],"name":r.get("name"),"price":r.get("price",0),"stock":r.get("inventory_count",-1),"category":(r.get("metadata") or {}).get("category","")} for r in rows]
    return {"products": items, "total": len(items)}

@router.get("/orders")
async def orders(current_user: AuthUser = Depends(require_auth)):
    require_verified(current_user); plan, features = entitlements(current_user)
    businesses = supabase.table("businesses").select("id").eq("owner_id", current_user.user_id).execute()
    if not businesses.data: return {"orders": [], "total_count": 0, "locked": not features["order_management"]}
    rows = supabase.table("orders").select("id,order_number,status,total,customer_info,created_at").eq("business_id", businesses.data[0]["id"]).order("created_at", desc=True).limit(50).execute().data or []
    if not features["order_management"]: return {"orders": rows[:5], "total_count": len(rows), "locked": True, "lock_message":"ניהול הזמנות זמין במסלולי PRO ו-PREMIUM", "upgrade_url":"/upgrade.html"}
    return {"orders": rows, "total_count": len(rows), "locked": False}

@router.get("/analytics")
async def analytics(current_user: AuthUser = Depends(require_auth)):
    require_verified(current_user)
    businesses = supabase.table("businesses").select("id,business_name").eq("owner_id", current_user.user_id).execute()
    if not businesses.data: return {"business_id":None,"business_name":"","total_revenue":0,"closed_deals":0,"conversion_rate":0,"average_order_value":0,"total_conversations":0}
    bid = businesses.data[0]["id"]
    paid = supabase.table("orders").select("total").eq("business_id", bid).in_("status", ["paid","shipped","delivered"]).execute().data or []
    conversations = supabase.table("conversations").select("session_id").eq("business_id", bid).execute().data or []
    revenue = round(sum(float(x.get("total",0)) for x in paid),2); deals=len(paid); sessions=len({x.get("session_id") for x in conversations if x.get("session_id")})
    return {"business_id":bid,"business_name":businesses.data[0].get("business_name",""),"total_revenue":revenue,"closed_deals":deals,"conversion_rate":round(deals/sessions*100,2) if sessions else 0,"average_order_value":round(revenue/deals,2) if deals else 0,"total_conversations":sessions,"charts_data":[]}
