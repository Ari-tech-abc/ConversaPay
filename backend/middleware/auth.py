"""
Authentication middleware for Supabase Auth JWT validation.

SECURITY FIXES:
  H3 - RoleChecker now reads the user's role from the profiles table and
       raises 403 when the role is not in the allowed list.
  H4 - is_pro_user uses timezone-aware datetime comparison to prevent the
       TypeError that previously caused the check to always return False.
"""
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from jose import JWTError
from supabase import create_client, Client
import logging
from datetime import datetime, timezone

from backend.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()

# Anon client — used only for token validation (no elevated privileges).
supabase_client: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_ANON_KEY
)

# Service-role client — used for privileged DB reads (profiles, businesses).
supabase_service: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
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
    """Validate the JWT token via Supabase Auth and return the caller."""
    token = credentials.credentials
    try:
        user = supabase_client.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return AuthUser(user_id=user.user.id, email=user.user.email or "")
    except JWTError as e:
        logger.warning(f"JWT validation error: {str(e)}")
        raise HTTPException(status_code=401, detail="Could not validate credentials")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(status_code=401, detail="Authentication failed")


async def get_current_user_optional(request: Request) -> Optional[AuthUser]:
    """Optional authentication — returns None if not authenticated."""
    authorization = request.headers.get("Authorization")
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1]
    try:
        user = supabase_client.auth.get_user(token)
        if user and user.user:
            return AuthUser(user_id=user.user.id, email=user.user.email or "")
    except Exception as e:
        logger.debug(f"Optional auth failed: {str(e)}")
    return None


def require_auth(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    """Dependency that requires authentication."""
    return user


class RoleChecker:
    """
    Role-based access control dependency.

    FIX H2: Previously this was a no-op that never checked the actual role.
    Now it reads the 'role' column from the profiles table and raises 403
    when the authenticated user's role is not in allowed_roles.
    """

    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: AuthUser = Depends(get_current_user)) -> AuthUser:
        try:
            profile = supabase_service.table("profiles") \
                .select("role") \
                .eq("user_id", user.user_id) \
                .execute()

            if not profile.data:
                raise HTTPException(status_code=403, detail="Profile not found")

            user_role = profile.data[0].get("role", "user")
            if user_role not in self.allowed_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required: {self.allowed_roles}"
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Role check error: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to verify role")

        return user


def is_pro_user(user_id: str) -> bool:
    """
    Check if a user has an active Pro or Premium subscription.

    FIX H3: Previous code compared a naive datetime.utcnow() against a
    timezone-aware expires_datetime, raising TypeError and always returning
    False (locking out valid Pro users).  Now both sides are timezone-aware.
    """
    try:
        profile = supabase_service.table("profiles") \
            .select("is_pro, plan_type, subscription_expires_at") \
            .eq("user_id", user_id) \
            .execute()

        if not profile.data:
            return False

        row = profile.data[0]
        is_pro = row.get("is_pro", False)
        plan_type = row.get("plan_type", "free")

        if not is_pro or plan_type not in ("pro", "premium"):
            return False

        expires_at = row.get("subscription_expires_at")
        if expires_at:
            # FIX H3: parse to timezone-aware datetime, compare against UTC now.
            expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            now_utc = datetime.now(tz=timezone.utc)
            if expires_dt < now_utc:
                return False

        return True

    except Exception as e:
        logger.error(f"Error checking Pro/Premium status: {str(e)}")
        return False


def require_business_owner_for_business_id(
    business_id: str,
    current_user: AuthUser,
) -> str:
    """
    Verify that the authenticated user owns the business with the given UUID.
    Raises 403 if they do not.
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
        raise HTTPException(status_code=500, detail="Failed to verify business ownership")


# Convenience role-based dependencies
require_admin = RoleChecker(["admin"])
require_business_owner = RoleChecker(["admin", "business_owner"])
