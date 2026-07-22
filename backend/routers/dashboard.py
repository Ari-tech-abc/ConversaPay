"""
Dashboard router for user dashboard analytics, widget management, and tier-based features.
Provides comprehensive dashboard functionality with tier-based access controls.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timedelta
from supabase import create_client, Client

from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.models.schemas import (
    ProfileResponse,
    OrderResponse,
    ProductResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


def get_user_plan(user_id: str) -> Dict[str, Any]:
    """Fetch user profile and return plan info."""
    try:
        result = supabase.table("profiles").select("*").eq("user_id", user_id).execute()
        if result.data:
            row = result.data[0]
            return {
                "plan_type": row.get("plan_type", "free"),
                "email_verified": row.get("email_verified", False),
                "subscription_expires_at": row.get("subscription_expires_at"),
                "domain_limit": row.get("domain_limit", 1),
                "payme_id": row.get("payme_id"),
            }
    except Exception as e:
        logger.error(f"Error fetching user plan: {str(e)}")
    return {"plan_type": "free", "email_verified": False, "domain_limit": 1}


def require_verified_email(user: AuthUser) -> None:
    """Raise 403 if email is not verified."""
    plan = get_user_plan(user.user_id)
    if not plan.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email_not_verified"
        )


# ============================================
# Profile & Tier
# ============================================

@router.get("/profile", response_model=Dict[str, Any])
async def get_dashboard_profile(current_user: AuthUser = Depends(require_auth)):
    """Get current user's dashboard profile with tier information."""
    require_verified_email(current_user)
    profile = get_user_plan(current_user.user_id)
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        **profile
    }


@router.get("/features")
async def get_dashboard_features(current_user: AuthUser = Depends(require_auth)):
    """Return available features based on user's tier."""
    require_verified_email(current_user)
    plan = get_user_plan(current_user.user_id)
    plan_type = plan.get("plan_type", "free")

    features = {
        "free": {
            "analytics": True,
            "product_management": True,
            "order_management": False,
            "sales": False,
            "widget_embed": False,
            "wordpress_plugin": False,
            "html_embed": False,
            "whatsapp_integration": False,
            "domain_limit": 1,
            "overlay": True,
        },
        "pro": {
            "analytics": True,
            "product_management": True,
            "order_management": True,
            "sales": True,
            "widget_embed": True,
            "wordpress_plugin": True,
            "html_embed": True,
            "whatsapp_integration": False,
            "domain_limit": plan.get("domain_limit", 3),
            "overlay": False,
        },
        "premium": {
            "analytics": True,
            "product_management": True,
            "order_management": True,
            "sales": True,
            "widget_embed": True,
            "wordpress_plugin": True,
            "html_embed": True,
            "whatsapp_integration": True,
            "domain_limit": plan.get("domain_limit", 10),
            "overlay": False,
        },
    }

    return features.get(plan_type, features["free"])


# ============================================
# Analytics
# ============================================

@router.get("/analytics")
async def get_analytics(current_user: AuthUser = Depends(require_auth)):
    """Get aggregated business dashboard metrics."""
    require_verified_email(current_user)
    try:
        businesses = supabase.table("businesses").select("id, business_name").eq("owner_id", current_user.user_id).execute()
        if not businesses.data:
            return {
                "business_id": None,
                "business_name": "",
                "total_revenue": 0.0,
                "closed_deals": 0,
                "conversion_rate": 0.0,
                "average_order_value": 0.0,
                "total_conversations": 0,
                "cdr_trend": "",
                "charts_data": []
            }

        business_id = businesses.data[0]["id"]
        business_name = businesses.data[0]["business_name"]

        paid_orders = supabase.table("orders").select("total, status, created_at").eq("business_id", business_id).eq("status", "paid").execute()
        total_revenue = sum(o.get("total", 0) for o in (paid_orders.data or []))
        closed_deals = len(paid_orders.data) if paid_orders.data else 0
        average_order_value = round(total_revenue / closed_deals, 2) if closed_deals > 0 else 0.0

        conversations = supabase.table("conversations").select("session_id").eq("business_id", business_id).execute()
        unique_sessions = len(set(c.get("session_id") for c in (conversations.data or []))) if conversations.data else 0
        conversion_rate = round((closed_deals / unique_sessions) * 100, 2) if unique_sessions > 0 else 0.0

        return {
            "business_id": business_id,
            "business_name": business_name,
            "total_revenue": round(total_revenue, 2),
            "closed_deals": closed_deals,
            "conversion_rate": conversion_rate,
            "average_order_value": average_order_value,
            "total_conversations": unique_sessions,
            "cdr_trend": "improving" if conversion_rate > 10 else "stable" if conversion_rate > 5 else "declining",
            "charts_data": []
        }
    except Exception as e:
        logger.error(f"Analytics error: {str(e)}")
        raise HTTPException(status_code=500, detail="Analytics calculation failed")


# ============================================
# Products
# ============================================

@router.get("/products")
async def get_dashboard_products(current_user: AuthUser = Depends(require_auth)):
    """Get product summary for the user's business."""
    require_verified_email(current_user)
    try:
        businesses = supabase.table("businesses").select("id").eq("owner_id", current_user.user_id).execute()
        if not businesses.data:
            return {"products": [], "total": 0}

        business_id = businesses.data[0]["id"]
        products = supabase.table("products").select("id, name, price, stock_quantity, category").eq("business_id", business_id).execute()

        product_list = []
        for p in (products.data or []):
            product_list.append({
                "id": p.get("id"),
                "name": p.get("name"),
                "price": p.get("price", 0.0),
                "stock": p.get("stock_quantity", 0),
                "category": p.get("category", "")
            })

        return {"products": product_list, "total": len(product_list)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Products fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch products")


# ============================================
# Orders (Tier-gated)
# ============================================

@router.get("/orders")
async def get_dashboard_orders(current_user: AuthUser = Depends(require_auth)):
    """Get order summary - FREE tier returns locked response."""
    require_verified_email(current_user)
    try:
        plan = get_user_plan(current_user.user_id)
        tier = plan.get("plan_type", "free")

        businesses = supabase.table("businesses").select("id").eq("owner_id", current_user.user_id).execute()
        if not businesses.data:
            raise HTTPException(status_code=404, detail="No business found")

        business_id = businesses.data[0]["id"]

        if tier == "free":
            orders = supabase.table("orders").select("id, status, total, created_at").eq("business_id", business_id).order("created_at", desc=True).limit(5).execute()
            return {
                "orders": orders.data or [],
                "total_count": len(orders.data or []),
                "locked": True,
                "lock_message": "Order management is locked for FREE tier. Upgrade to PRO or PREMIUM to unlock full order management.",
                "upgrade_url": "/pay?plan=pro"
            }

        orders = supabase.table("orders").select("id, status, total, customer_name, created_at").eq("business_id", business_id).order("created_at", desc=True).limit(50).execute()
        return {"orders": orders.data or [], "total_count": len(orders.data or [])}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Orders fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch orders")


# ============================================
# Widget Domain Management
# ============================================

@router.get("/widget/{business_id}")
async def get_widget_data(
    business_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """Get widget data with tier-based overlay controls."""
    require_verified_email(current_user)
    try:
        ownership = supabase.table("businesses").select("id").eq("id", business_id).eq("owner_id", current_user.user_id).execute()
        if not ownership.data:
            raise HTTPException(status_code=403, detail="Unauthorized access")

        widget = supabase.table("widgets").select("*").eq("business_id", business_id).execute()
        profile = get_user_plan(current_user.user_id)
        tier = profile.get("plan_type", "free")
        widget_data = widget.data[0] if widget.data else {}

        if tier == "free":
            return {
                "data": widget_data,
                "has_limitations": True,
                "overlay_active": True,
                "overlay_text": "Order management is locked for FREE tier. Upgrade to unlock full features.",
                "upgrade_url": "/pay?plan=pro"
            }

        return {
            "data": widget_data,
            "has_limitations": False,
            "overlay_active": False,
            "overlay_text": "",
            "upgrade_url": ""
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Widget fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get widget data")


# ============================================
# Upgrade Options
# ============================================

@router.get("/upgrade-options")
async def get_upgrade_options(current_user: AuthUser = Depends(require_auth)):
    """Get available tier upgrade options."""
    require_verified_email(current_user)
    try:
        profile = get_user_plan(current_user.user_id)
        current_tier = profile.get("plan_type", "free")

        plans = []
        if current_tier == "free":
            plans.append({
                "plan_name": "PRO",
                "price": 19.99,
                "currency": "USD",
                "features": ["Full order management", "Unlimited widgets", "Analytics dashboard"],
                "payment_gateway": "bit",
                "upgrade_url": "/pay?plan=pro"
            })
            plans.append({
                "plan_name": "PREMIUM",
                "price": 49.99,
                "currency": "USD",
                "features": ["All PRO features", "WhatsApp integration", "Advanced analytics"],
                "payment_gateway": "payme",
                "upgrade_url": "/pay?plan=premium"
            })

        return {"plans": plans, "current_tier": current_tier}
    except Exception as e:
        logger.error(f"Upgrade options error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load upgrade options")


# ============================================
# WhatsApp (PREMIUM only)
# ============================================

@router.get("/whatsapp")
async def get_whatsapp_status(current_user: AuthUser = Depends(require_auth)):
    """Get WhatsApp connection status - PREMIUM tier only."""
    require_verified_email(current_user)
    try:
        profile = get_user_plan(current_user.user_id)
        plan_type = profile.get("plan_type", "free")

        if plan_type != "premium":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="WhatsApp features are only available for PREMIUM tier"
            )

        result = supabase.table("profiles").select("whatsapp_phone_number_id, whatsapp_access_token, whatsapp_verify_token").eq("user_id", current_user.user_id).execute()
        data = result.data[0] if result.data else {}

        return {
            "connected": bool(data.get("whatsapp_phone_number_id")),
            "phone_number": data.get("whatsapp_phone_number_id", ""),
            "plan_type": plan_type
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WhatsApp status error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get WhatsApp status")


# ============================================
# Settings
# ============================================

@router.get("/settings")
async def get_settings(current_user: AuthUser = Depends(require_auth)):
    """Get user settings including PayMe configuration."""
    require_verified_email(current_user)
    try:
        profile = get_user_plan(current_user.user_id)
        return {
            "payme_id": profile.get("payme_id"),
            "payme_merchant_id": profile.get("payme_id"),
            "whatsapp_phone": profile.get("whatsapp_phone_number_id"),
            "whatsapp_token": profile.get("whatsapp_access_token"),
            "domain_limit": profile.get("domain_limit", 1)
        }
    except Exception as e:
        logger.error(f"Settings fetch error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load settings")


@router.put("/settings/payme/{payme_id}")
async def update_payme_settings(
    payme_id: str,
    current_user: AuthUser = Depends(require_auth)
):
    """Update PayMe merchant ID for PREMIUM tier users."""
    require_verified_email(current_user)
    try:
        profile = get_user_plan(current_user.user_id)
        plan_type = profile.get("plan_type", "free")

        if plan_type != "premium":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="PayMe settings are only available for PREMIUM tier"
            )

        result = supabase.table("profiles").update({"payme_id": payme_id, "payme_merchant_id": payme_id}).eq("user_id", current_user.user_id).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to update PayMe settings")

        return {"message": "PayMe settings updated successfully", "payme_id": payme_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PayMe update error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update PayMe settings")