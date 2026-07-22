"""Public widget configuration with three-tier plan enforcement."""
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging
from supabase import create_client
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["widget"])


def _host(value: str) -> str:
    value = (value or "").strip()
    if "://" in value:
        value = value.split("://", 1)[1]
    return value.split("/", 1)[0].split(":", 1)[0].lower().rstrip(".")


def _plan_info(business_id: str, client) -> dict:
    business = client.table("businesses").select("owner_id").eq("id", business_id).maybe_single().execute()
    if not business.data:
        return {"plan_type": "free", "active": False}
    profile = client.table("profiles").select("plan_type, subscription_expires_at").eq("user_id", business.data["owner_id"]).maybe_single().execute()
    row = profile.data or {}
    plan = row.get("plan_type", "free")
    expiry = row.get("subscription_expires_at")
    active = True
    if plan in ("pro", "premium") and expiry:
        try:
            expires = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            active = expires > datetime.now(timezone.utc)
        except ValueError:
            active = False
    return {"plan_type": plan, "active": active}


@router.get("/config/{business_id}")
async def get_widget_config(business_id: str, request: Request):
    try:
        client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        demo = business_id == "conversapay"
        query = client.table("businesses").select("id, settings, bot_name, greeting_message, theme_colors") if demo else client.table("businesses").select("settings, bot_name, greeting_message, theme_colors")
        result = (query.eq("business_id", business_id) if demo else query.eq("id", business_id)).maybe_single().execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Business not found")
        business = result.data
        plan = _plan_info(business.get("id", business_id), client)
        origin = _host(request.headers.get("origin") or request.headers.get("referer") or request.headers.get("host"))
        own = _host(settings.BASE_URL)
        internal = origin in {"localhost", "127.0.0.1", own} or origin == "conversapay.org" or origin.endswith(".conversapay.org")
        if plan["plan_type"] == "free" and not internal:
            raise HTTPException(status_code=403, detail="Widget is available on the ConversaPay domain for the free plan")
        if plan["plan_type"] in ("pro", "premium") and not plan["active"]:
            raise HTTPException(status_code=403, detail="Subscription has expired")
        return JSONResponse(content={
            "business_id": business_id,
            "bot_name": business.get("bot_name", "AI Assistant"),
            "greeting_message": business.get("greeting_message", "Hello! How can I help you today?"),
            "avatar_url": None,
            "theme_colors": business.get("theme_colors") or {"primary": "#A855F7", "secondary": "#00D9FF", "background": "#0B0F19"},
            "features": {"checkout": plan["plan_type"] in ("pro", "premium"), "product_catalog": True, "plan_type": plan["plan_type"]}
        })
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Widget config error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load widget configuration")


@router.get("/health")
async def widget_health():
    return {"status": "healthy", "service": "conversapay-widget", "version": "2.0.0"}
