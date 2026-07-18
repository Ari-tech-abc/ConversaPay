"""
Widget Router - Public API for embedded chat widget
Handles widget configuration with domain-based security
"""
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import JSONResponse
import logging
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(tags=["widget"])


@router.get("/config/{business_id}")
async def get_widget_config(business_id: str, request: Request):
    """
    Get public widget configuration for a business.
    
    Security:
    - Validates the requesting domain against allowed_domains whitelist
    - Returns 403 if domain is not authorized
    - Only returns public, non-sensitive data
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
        # allowed_domains is stored in the settings JSONB column
        from backend.config import settings as app_settings
        from supabase import create_client
        
        try:
            supabase = create_client(
                app_settings.SUPABASE_URL,
                app_settings.SUPABASE_ANON_KEY
            )
            
            result = supabase.table('businesses')\
                .select('settings, bot_name, greeting_message, theme_colors')\
                .eq('business_id', business_id)\
                .single()\
                .execute()
            
            if not result.data:
                raise HTTPException(status_code=404, detail="Business not found")
            
            business = result.data
            
            # Extract allowed_domains from settings JSONB
            settings = business.get('settings', {})
            allowed_domains = settings.get('allowed_domains', [])
            
            # If no allowed_domains configured, deny access (secure by default)
            if not allowed_domains:
                logger.warning(f"No allowed_domains configured for business {business_id}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Widget not configured for this domain"
                )
            
            bot_name = business.get('bot_name', 'AI Assistant')
            greeting_message = business.get('greeting_message', 'Hello! How can I help you today?')
            theme_colors = business.get('theme_colors', {})
            
        except Exception as e:
            logger.error(f"Database error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to load widget configuration"
            )
        
        # Security check: validate domain
        if requesting_domain not in allowed_domains:
            logger.warning(f"Unauthorized widget access attempt from {requesting_domain} for business {business_id}")
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
                "product_catalog": True
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
        "version": "1.0.0"
    }