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
    
    3-Tier Model:
    - free:  Dashboard access + AI agent ONLY on conversapay.org
    - pro:   Full features + widget on 1 custom external domain
    - premium: Full features + widget on multiple custom external domains
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
            return {'plan_type': 'free', 'is_active': True}  # Widget always works
        
        user_id = biz_result.data.get('owner_id')
        if not user_id:
            logger.warning(f"Business {business_id} has no owner_id")
            return {'plan_type': 'free', 'is_active': True}
        
        # Use service role client to bypass RLS on profiles table
        from backend.config import settings as app_settings
        service_role_client = create_client(
            app_settings.SUPABASE_URL,
            app_settings.SUPABASE_SERVICE_ROLE_KEY
        )
        
        # Check the user's profile for subscription plan
        profile_result = service_role_client.table('profiles')\
            .select('plan_type, is_pro, subscription_expires_at')\
            .eq('user_id', user_id)\
            .single()\
            .execute()
        
        if not profile_result.data:
            logger.warning(f"No profile found for user {user_id}")
            return {'plan_type': 'free', 'is_active': True}
        
        profile = profile_result.data
        plan_type = profile.get('plan_type', 'free')
        is_pro = profile.get('is_pro', False)
        expires_at = profile.get('subscription_expires_at')
        
        # Free tier is always active (no expiry) - Widget works for everyone
        if plan_type == 'free':
            return {'plan_type': 'free', 'is_active': True, 'is_pro': False}
        
        # Check if paid subscription has expired
        is_active = True
        if expires_at:
            try:
                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if expires_dt < datetime.utcnow():
                    logger.warning(f"Paid subscription expired for user {user_id} at {expires_at}")
                    is_active = False
            except (ValueError, AttributeError) as e:
                logger.warning(f"Error parsing subscription expiry for user {user_id}: {e}")
                pass
        
        logger.info(f"User {user_id} plan: {plan_type}, active: {is_active} (business {business_id})")
        return {
            'plan_type': plan_type, 
            'is_active': is_active,
            'is_pro': True
        }
        
    except Exception as e:
        logger.error(f"Error checking plan for business {business_id}: {str(e)}", exc_info=True)
        return {'plan_type': 'free', 'is_active': True, 'is_pro': False}


@router.get("/config/{business_id}")
async def get_widget_config(business_id: str, request: Request):
    """
    Get public widget configuration for a business.
    
    Security:
    - Validates the requesting domain against allowed_domains whitelist
    - Returns 403 if domain is not authorized
    - For non-Pro users, widget is strictly blocked on external domains
    - Only returns public, non-sensitive data
    
    Pro Enforcement:
    - Free/Starter users: widget only works on localhost/internal dashboard preview
    - Pro users: widget works on all their configured allowed_domains
    """
    try:
        # Get the origin/referer from request headers
        origin = request.headers.get('Origin', '')
        referer = request.headers.get('Referer', '')
        host = request.headers.get('Host', '')
        
        # Determine the requesting domain
        requesting_domain = origin or referer or host
        
        # Extract just the domain from URL if needed
        if requesting_domain.startswith('http'):
            requesting_domain = requesting_domain.split('/')[2]
        
        logger.info(f"Widget config request for business {business_id} from domain: {requesting_domain}")
        
        # Handle the system demo bot slug "conversapay" — resolve by slug column instead of UUID
        is_demo_bot = (business_id == 'conversapay')
        
        # Database lookup for business and allowed_domains
        from backend.config import settings as app_settings
        from supabase import create_client
        
        try:
            supabase = create_client(
                app_settings.SUPABASE_URL,
                app_settings.SUPABASE_ANON_KEY
            )
            
            if is_demo_bot:
                # Demo bot: look up by business_id (slug) column instead of id (UUID)
                result = supabase.table('businesses')\
                    .select('id, settings, bot_name, greeting_message, theme_colors')\
                    .eq('business_id', business_id)\
                    .single()\
                    .execute()
            else:
                # All other businesses: query by UUID primary key
                result = supabase.table('businesses')\
                    .select('settings, bot_name, greeting_message, theme_colors')\
                    .eq('id', business_id)\
                    .single()\
                    .execute()
            
            if not result.data:
                raise HTTPException(status_code=404, detail="Business not found")
            
            business = result.data
            
            # Extract allowed_domains from settings JSONB
            biz_settings = business.get('settings', {})
            allowed_domains = biz_settings.get('allowed_domains', [])
            
            bot_name = business.get('bot_name', 'AI Assistant')
            greeting_message = business.get('greeting_message', 'Hello! How can I help you today?')
            theme_colors = business.get('theme_colors', {})
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Database error: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to load widget configuration"
            )
        
        # Determine plan info for the business owner
        plan_info = await get_business_plan_info(business_id, supabase)
        plan_type = plan_info.get('plan_type', 'free')
        is_plan_active = plan_info.get('is_active', False)
        
        # Determine if this is the conversapay.org internal domain (always allowed for all tiers)
        own_domain = app_settings.BASE_URL.split('://')[-1].split('/')[0] if '://' in app_settings.BASE_URL else app_settings.BASE_URL
        is_conversapay_domain = (
            'localhost' in requesting_domain or
            '127.0.0.1' in requesting_domain or
            'conversapay' in requesting_domain or
            own_domain in requesting_domain or
            requesting_domain.endswith('conversapay.org')
        )
        
        logger.info(f"Widget config - domain: {requesting_domain}, is_own_domain: {is_conversapay_domain}, plan: {plan_type}, plan_active: {is_plan_active}, allowed_domains: {allowed_domains}")
        
        # 3-Tier Access Control:
        # Tier 1 - conversapay.org (internal): ALL tiers allowed (Free users get AI agent here)
        # Tier 2 - External domain, Free tier: BLOCKED
        # Tier 3 - External domain, Pro tier: ALLOWED if no allowed_domains configured (uses default 1), or domain is in list
        # Tier 4 - External domain, Premium tier: ALLOWED if domain is in allowed_domains list (supports multiple)
        if is_conversapay_domain:
            # conversapay.org is always allowed for all tiers (Free users get AI agent here)
            logger.info(f"Allowing widget access on conversapay.org domain for plan: {plan_type}")
            pass
            
        elif plan_type == 'free':
            # Free tier on external domain - blocked
            logger.warning(f"BLOCKED: Free tier widget access attempt from external domain {requesting_domain} for business {business_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Widget available only on conversapay.org for Free plan. Upgrade to Pro to enable on external sites."
            )
            
        elif not is_plan_active:
            # Paid subscription expired
            logger.warning(f"BLOCKED: Expired {plan_type} subscription for business {business_id} from {requesting_domain}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your {plan_type.capitalize()} subscription has expired. Renew to continue using the widget."
            )
            
        elif plan_type in ('pro', 'premium'):
            # Pro/Premium tier on external domain
            if allowed_domains and requesting_domain not in allowed_domains:
                plan_name = plan_type.capitalize()
                logger.warning(f"BLOCKED: {plan_name} widget access from unauthorized domain {requesting_domain} for business {business_id}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Domain not authorized for your {plan_name} plan. Configure your allowed domain in settings."
                )
            # If no allowed_domains configured, Pro/Premium gets one free domain slot
            if not allowed_domains:
                logger.info(f"{plan_type.capitalize()} plan: No allowed_domains configured, defaulting to allow {requesting_domain}")
        
        # Build response with plan info and actual data from database
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