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


async def check_business_pro_status(business_id: str, supabase_client) -> bool:
    """
    Check if the business owner has an active Pro or Premium subscription.
    This is used to enforce widget rendering restrictions for free users.
    Uses service role client to bypass RLS for the profiles table.
    """
    try:
        # Get the business record to find the owner - query by UUID primary key
        biz_result = supabase_client.table('businesses')\
            .select('owner_id')\
            .eq('id', business_id)\
            .single()\
            .execute()
        
        if not biz_result.data:
            logger.warning(f"Business not found for pro status check: {business_id}")
            return False
        
        user_id = biz_result.data.get('owner_id')
        if not user_id:
            logger.warning(f"Business {business_id} has no owner_id")
            return False
        
        # Use service role client to bypass RLS on profiles table
        from backend.config import settings as app_settings
        service_role_client = create_client(
            app_settings.SUPABASE_URL,
            app_settings.SUPABASE_SERVICE_ROLE_KEY
        )
        
        # Check the user's profile for pro/premium status
        profile_result = service_role_client.table('profiles')\
            .select('is_pro, subscription_expires_at')\
            .eq('user_id', user_id)\
            .single()\
            .execute()
        
        if not profile_result.data:
            logger.warning(f"No profile found for user {user_id}")
            return False
        
        is_pro = profile_result.data.get('is_pro', False)
        expires_at = profile_result.data.get('subscription_expires_at')
        
        # Check if user has an active paid subscription (Pro or Premium)
        has_paid_tier = is_pro
        
        if not has_paid_tier:
            logger.info(f"User {user_id} is not on a paid tier")
            return False
        
        # Check if subscription has expired
        if expires_at:
            try:
                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                if expires_dt < datetime.utcnow():
                    logger.warning(f"Paid subscription expired for user {user_id} at {expires_at}")
                    return False
            except (ValueError, AttributeError) as e:
                logger.warning(f"Error parsing subscription expiry for user {user_id}: {e}")
                pass
        
        logger.info(f"User {user_id} has active paid subscription (business {business_id})")
        return True
        
    except Exception as e:
        logger.error(f"Error checking Pro status for business {business_id}: {str(e)}", exc_info=True)
        return False


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
        
        # Database lookup for business and allowed_domains
        from backend.config import settings as app_settings
        from supabase import create_client
        
        try:
            supabase = create_client(
                app_settings.SUPABASE_URL,
                app_settings.SUPABASE_ANON_KEY
            )
            
            # Query by UUID primary key, not by business_id slug
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
        
        # Pro status enforcement:
        # 1. Check if the business owner has an active Pro or Premium subscription
        is_pro = await check_business_pro_status(business_id, supabase)
        
        # Determine if this is a development/internal domain (always allowed)
        own_domain = app_settings.BASE_URL.split('://')[-1].split('/')[0] if '://' in app_settings.BASE_URL else app_settings.BASE_URL
        is_development = (
            'localhost' in requesting_domain or
            '127.0.0.1' in requesting_domain or
            'conversapay' in requesting_domain or
            own_domain in requesting_domain or
            requesting_domain.endswith('conversapay.org')
        )
        
        logger.info(f"Access check - domain: {requesting_domain}, is_development: {is_development}, is_pro: {is_pro}, allowed_domains: {allowed_domains}")
        
        # 2. Access control logic:
        #    - Development/internal domains are always allowed (localhost, conversapay.org, etc.)
        #    - Pro users: allowed on any domain (with or without allowed_domains configured)
        #    - Non-Pro users: require allowed_domains to be configured and domain must be in list
        if is_development:
            # Always allow internal/development domains
            logger.info(f"Allowing access for development domain: {requesting_domain}")
            pass
        elif not is_pro:
            # Non-Pro user on external domain
            if not allowed_domains:
                logger.warning(f"No allowed_domains configured for non-Pro business {business_id}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Widget not configured for this domain. Upgrade to Pro to enable widget on external sites."
                )
            elif requesting_domain not in allowed_domains:
                logger.warning(f"BLOCKED: Non-Pro widget access attempt from {requesting_domain} for business {business_id}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Domain not authorized. Upgrade to Pro to embed this widget on external sites."
                )
        else:
            # Pro user on external domain - always allowed, even without allowed_domains
            # If allowed_domains is configured, still check it for Pro users
            if allowed_domains and requesting_domain not in allowed_domains:
                logger.warning(f"Unauthorized widget access attempt from {requesting_domain} for Pro business {business_id}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Domain not authorized to embed this widget"
                )
        
        # Build response with actual data from database
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
                "checkout": True,
                "product_catalog": True,
                "is_pro": is_pro
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