"""Public widget configuration with API-key enforcement (no Origin/Host trust)."""
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from supabase import create_client

from backend.config import settings
from backend.middleware.auth import active_plan
from backend.middleware.rate_limiter import check_rate_limit, widget_config_rate_limiter
from backend.services.widget_auth import authorize_widget_request

logger = logging.getLogger(__name__)
router = APIRouter(tags=["widget"])

# Singleton client instead of creating a new one per request.
_supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def plan_info(business_id, client):
    business = client.table("businesses").select("owner_id").eq("id", business_id).maybe_single().execute()
    if not business.data:
        return {"plan_type": "free", "active": False}
    profile = client.table("profiles").select("plan_type,subscription_expires_at").eq("user_id", business.data["owner_id"]).maybe_single().execute()
    plan = active_plan(profile.data or {})
    return {"plan_type": plan, "active": True}


@router.get("/config/{business_id}")
async def get_widget_config(business_id: str, request: Request):
    # Scoped to business_id so scraping one tenant doesn't burn another
    # tenant's quota, and so this endpoint can no longer be hit unbounded.
    check_rate_limit(request, limiter=widget_config_rate_limiter, extra_key=business_id)
    try:
        client = _supabase
        demo = business_id == "conversapay"
        query = client.table("businesses").select("id,settings,bot_name,greeting_message,theme_colors")
        result = (query.eq("business_id", business_id) if demo else query.eq("id", business_id)).maybe_single().execute()
        if not result.data:
            # Generic 404 regardless of *why* — avoids leaking which
            # business_ids exist vs. which are just unauthorized.
            raise HTTPException(404, "Business not found")
        business = result.data
        actual_id = business.get("id", business_id)
        plan = plan_info(actual_id, client)

        # Authorization is API-key / demo-only. Origin, Referer, and Host
        # are never consulted — they are attacker-controlled and cannot
        # grant trust. See services/widget_auth.py for rationale.
        await authorize_widget_request(
            requested_business_id=business_id,
            actual_business_id=actual_id,
            plan_type=plan["plan_type"],
            request=request,
            client=client,
        )

        return JSONResponse(content={"business_id": business_id, "bot_name": business.get("bot_name", "AI Assistant"), "greeting_message": business.get("greeting_message", "Hello! How can I help you today?"), "avatar_url": None, "theme_colors": business.get("theme_colors") or {"primary": "#A855F7", "secondary": "#00D9FF", "background": "#0B0F19"}, "features": {"checkout": plan["plan_type"] in ("pro", "premium"), "product_catalog": True, "plan_type": plan["plan_type"]}})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Widget config error: %s", exc, exc_info=True)
        raise HTTPException(500, "Failed to load widget configuration")


@router.get("/health")
async def widget_health():
    return {"status": "healthy", "service": "conversapay-widget", "version": "2.0.0"}