"""
Widget Router - Public API for embedded chat widget
Handles widget configuration with domain-based security and Pro tier enforcement
"""
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import JSONResponse
import logging
from datetime import datetime

from supabase import create_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["widget"])


async def get_business_plan_info(business_id: str, supabase_client) -> dict:
    """
    Get the business owner's subscription plan info.
    Returns dict with plan_type, is_active, and expires_at.
    """
    try:
        # Get the business record to find the owner
        biz_result = supabase_client.table('businesses')\
            .select('owner_id')\
            .eq('id', business_id)\
            .single()\
            .execute()
        
        if not biz_result.data:
            logger.warning(f"Business not found for plan check: {business_id}")
            return {'plan_type': 'free', 'is_active': True}
        
        user_id = biz_result.data.get('owner_id')
        if not user_id:
            logger.warning(f"Business {business_id} has no owner_id")
            return {'plan_type': 'free', 'is_active': True}
        
        # Check the user's profile for subscription plan
        profile_result = supabase_client.table('profiles')\
            .select('plan_type, is_pro, subscription_expires_at')\
            .eq('user_id', user_id)\
            .single()\
            .execute()
        
        if not profile_result.data:
            logger.warning(f"No profile found for user {user_id}")
            return {'plan_type': 'free', 'is_active': True}
        
        profile = profile_result.data
        plan_type = profile.get('plan_type', 'free')
        is_pro = plan_type in ('pro', 'premium')
        expires_at = profile.get('subscription_expires_at')
        
        # Free tier is always active (no expiry) - Widget works for everyone
        if plan_type == 'free':
            return {'plan_type': 'free', 'is_active': True, 'is_pro': False}
        
        # Check if paid subscription has expired
        is_active = True
        if expires_at:
            try:
                # Fix: handle timezone-aware datetime
                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                expires_dt = expires_dt.replace(tzinfo=None)  # Make naive
                now = datetime.utcnow()
                if expires_dt < now:
                    is_active = False
            except Exception as e:
                logger.warning(f"Error parsing subscription expiry for user {user_id}: {e}")
                pass
        
        logger.info(f"User {user_id} plan: {plan_type}, active: {is_active} (business {business_id})")
        return {
            'plan_type': plan_type, 
            'is_active': is_active,
            'is_pro': plan_type in ('pro', 'premium') or is_pro
        }
        
    except Exception as e:
        logger.error(f"Error checking plan for business {business_id}: {str(e)}", exc_info=True)
        return {'plan_type': 'free', 'is_active': True, 'is_pro': False}


@router.get("/config/{business_id}")
async def get_widget_config(business_id: str, request: Request):
    """
    Get public widget configuration for a business.
    """
    try:
        # Get the origin/referer from request headers
        origin = request.headers.get('Origin', '')
        referer = request.headers.get('Referer', '')
        host = request.headers.get('Host', '')
        
        # Determine the requesting domain
        requesting_domain = origin or referer or host
        if requesting_domain.startswith('http'):
            requesting_domain = requesting_domain.split('/')[2]
        
        logger.info(f"Widget config request for business {business_id} from domain: {requesting_domain}")
        
        # Handle the system demo bot slug "conversapay"
        is_demo_bot = (business_id == 'conversapay')
        
        from backend.config import settings as app_settings
        supabase = create_client(
            app_settings.SUPABASE_URL,
            app_settings.SUPABASE_SERVICE_ROLE_KEY
        )
        
        if is_demo_bot:
            result = supabase.table('businesses')\
                .select('id, settings, bot_name, greeting_message, theme_colors')\
                .eq('business_id', business_id)\
                .single()\
                .execute()
        else:
            result = supabase.table('businesses')\
                .select('settings, bot_name, greeting_message, theme_colors')\
                .eq('id', business_id)\
                .single()\
                .execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Business not found")
        
        business = result.data
        biz_settings = business.get('settings', {})
        allowed_domains = biz_settings.get('allowed_domains', [])
        
        bot_name = business.get('bot_name', 'AI Assistant')
        greeting_message = business.get('greeting_message', 'Hello! How can I help you today?')
        theme_colors = business.get('theme_colors', {})
        
        # Determine plan info
        plan_info = await get_business_plan_info(business_id, supabase)
        plan_type = plan_info.get('plan_type', 'free')
        is_plan_active = plan_info.get('is_active', False)
        
        # Determine if this is the conversapay.org internal domain
        own_domain = app_settings.BASE_URL.split('://')[-1].split('/')[0] if '://' in app_settings.BASE_URL else app_settings.BASE_URL
        is_conversapay_domain = (
            'localhost' in requesting_domain or
            '127.0.0.1' in requesting_domain or
            'conversapay' in requesting_domain or
            own_domain in requesting_domain or
            requesting_domain.endswith('conversapay.org')
        )
        
        # 3-Tier Access Control - Widget works for everyone on internal domain
        if is_conversapay_domain:
            pass  # Always allowed
        elif plan_type == 'free':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Widget available only on conversapay.org for Free plan. Upgrade to Pro."
            )
        elif not is_plan_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your {plan_type.capitalize()} subscription has expired."
            )
        
        # Build response
        config = {
            "business_id": business_id,
            "bot_name": bot_name,
            "greeting_message": greeting_message,
            "avatar_url": None,
            "theme_colors": theme_colors or {
                "primary": "#A855F7",
                "secondary": "#00D9FF",
                "background": "#0B0F19"
            },
            "features": {
                "checkout": plan_type in ('pro', 'premium'),
                "product_catalog": True,
                "plan_type": plan_type,
                "is_pro": plan_type in ('pro', 'premium')
            }
        }
        
        return JSONResponse(content=config)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching widget config: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load widget configuration"
        )


@router.get("/health")
async def widget_health():
    """Health check for widget service."""
    return {
        "status": "healthy",
        "service": "conversapay-widget",
        "version": "2.0.0"
    }