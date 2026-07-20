"""
Authentication middleware for Supabase Auth JWT validation.
Extracts and validates user identity from JWT tokens.
"""
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from jose import JWTError, jwt
from supabase import create_client, Client
import logging

from backend.config import settings


logger = logging.getLogger(__name__)

# Security scheme for Swagger UI
security = HTTPBearer()

# Supabase client for token validation
supabase_client: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_ANON_KEY
)


class AuthUser:
    """Represents an authenticated user."""
    
    def __init__(self, user_id: str, email: str):
        self.user_id = user_id
        self.email = email
    
    def __repr__(self):
        return f"AuthUser(user_id={self.user_id}, email={self.email})"


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AuthUser:
    """
    Dependency to get the current authenticated user from JWT token.
    Validates the token using Supabase Auth.
    """
    token = credentials.credentials
    
    try:
        # Verify token with Supabase
        user = supabase_client.auth.get_user(token)
        
        if not user or not user.user:
            raise HTTPException(
                status_code=401,
                detail="Invalid authentication credentials"
            )
        
        return AuthUser(
            user_id=user.user.id,
            email=user.user.email or ""
        )
    
    except JWTError as e:
        logger.warning(f"JWT validation error: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Could not validate credentials"
        )
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Authentication failed"
        )


async def get_current_user_optional(
    request: Request
) -> Optional[AuthUser]:
    """
    Optional authentication - returns None if not authenticated.
    Useful for public endpoints that can return different data based on auth status.
    """
    authorization = request.headers.get("Authorization")
    
    if not authorization or not authorization.startswith("Bearer "):
        return None
    
    token = authorization.split(" ")[1]
    
    try:
        user = supabase_client.auth.get_user(token)
        
        if user and user.user:
            return AuthUser(
                user_id=user.user.id,
                email=user.user.email or ""
            )
    except Exception as e:
        logger.debug(f"Optional auth failed: {str(e)}")
    
    return None


def require_auth(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """
    Dependency that requires authentication.
    Raises 401 if user is not authenticated.
    """
    return user


class RoleChecker:
    """Base class for role-based access control."""
    
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles
    
    def __call__(self, user: AuthUser = Depends(get_current_user)) -> AuthUser:
        # For now, all authenticated users have the same role
        # This can be extended for admin, business_owner, etc.
        return user


# Supabase client for database operations (service role)
supabase_service: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


def is_pro_user(user_id: str) -> bool:
    """
    Check if a user has an active Pro subscription.
    Returns True if is_pro is True and subscription hasn't expired.
    """
    try:
        from datetime import datetime
        
        profile = supabase_service.table("profiles")\
            .select("is_pro, subscription_expires_at")\
            .eq("user_id", user_id)\
            .execute()
        
        if not profile.data:
            return False
        
        is_pro = profile.data[0].get('is_pro', False)
        if not is_pro:
            return False
        
        # Check if subscription is still valid
        expires_at = profile.data[0].get('subscription_expires_at')
        if expires_at:
            expires_datetime = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            if expires_datetime < datetime.utcnow():
                return False
        
        return True
    
    except Exception as e:
        logger.error(f"Error checking Pro status: {str(e)}")
        return False


# Role-based dependencies
require_admin = RoleChecker(["admin"])
require_business_owner = RoleChecker(["business_owner"])


def require_business_owner_for_business_id(
    business_id: str,
    current_user: AuthUser,
) -> str:
    """Verify that the authenticated user owns the business with the given UUID.

    The `business_id` parameter is expected to be the primary key UUID
    of the `businesses` table.

    Raises:
        403: if the authenticated user does not own the business.
    """
    try:
        business = supabase_service.table("businesses") \
            .select("id") \
            .eq("id", business_id) \
            .eq("owner_id", current_user.user_id) \
            .execute()

        if not business.data:
            raise HTTPException(
                status_code=403,
                detail="Unauthorized access to this business resources",
            )

        return str(business.data[0]["id"])

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error verifying business ownership for business_id={business_id}: {str(e)}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to verify business ownership",
        )

