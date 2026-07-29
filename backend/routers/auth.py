"""
Authentication router for user registration, login, logout, and password reset.
Uses Supabase Auth for authentication.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Request, Query
from fastapi.security import HTTPBearer
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, ValidationError
from typing import Optional
from datetime import datetime, timedelta
import logging
import secrets

from supabase import create_client, Client
from supabase_auth.errors import AuthApiError as SupabaseAuthApiError
from postgrest.exceptions import APIError as PostgrestAPIError
from backend.config import settings
from backend.middleware.auth import AuthUser, get_current_user
from backend.models.schemas import (
    UserRegister,
    UserLogin,
    TokenResponse,
    PasswordResetRequest,
    PasswordReset
)
from backend.services.email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["authentication"])

# Supabase client for auth operations
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


# ============================================
# Response Models
# ============================================

class MessageResponse(BaseModel):
    """Simple message response."""
    message: str


class UserInfoResponse(BaseModel):
    """Current user information response."""
    user_id: str
    email: str
    profile: Optional[dict] = None


# ============================================
# Helper Functions
# ============================================

def get_user_profile(user_id: str) -> Optional[dict]:
    """Get user profile from database."""
    try:
        result = supabase.table("profiles").select("*").eq("user_id", user_id).execute()
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"Error fetching user profile: {str(e)}")
    return None


def update_profile_row(user_id: str, changes: dict, select_fields: str = "*") -> Optional[dict]:
    """
    Update a profile row and reliably return the resulting row.

    The Supabase Python client returns the updated representation from an UPDATE
    by default, so we read result.data directly. (Chaining .select() onto an
    update builder is not supported and raises, which previously broke email
    verification.) If the payload comes back empty for any reason, we fall back
    to reloading the profile.

    select_fields is accepted for call-site compatibility but is not applied to
    the update itself.
    """
    try:
        result = supabase.table("profiles")\
            .update(changes)\
            .eq("user_id", user_id)\
            .execute()

        if result.data:
            return result.data[0]

        return get_user_profile(user_id)
    except Exception as e:
        logger.error(f"Error updating user profile for {user_id}: {str(e)}", exc_info=True)
        return None


def create_user_profile(user_id: str, email: str, full_name: str, token: str, expires_at: str) -> dict:
    """Create user profile with verification token in one insert."""
    try:
        result = supabase.table("profiles").insert({
            "user_id": user_id,
            "email": email,
            "full_name": full_name,
            "plan_type": "free",
            "email_verified": False,
            "email_verification_token": token,
            "email_verification_expires_at": expires_at,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        
        if result.data:
            return result.data[0]
    except Exception as e:
        logger.error(f"Error creating user profile: {str(e)}")
    
    return {}


def create_business_for_user(user_id: str, business_name: str) -> Optional[str]:
    """Create business for user and return business_id."""
    try:
        # Generate business_id from business name (lowercase, no spaces)
        business_id = business_name.lower().replace(' ', '_').replace('-', '_')
        business_id = ''.join(c for c in business_id if c.isalnum() or c == '_')
        
        # Ensure uniqueness by appending user ID if needed
        existing = supabase.table("businesses")\
            .select("id")\
            .eq("business_id", business_id)\
            .execute()
        
        if existing.data:
            # Append user ID to make it unique
            business_id = f"{business_id}_{user_id[:8]}"
        
        business_data = {
            "business_id": business_id,
            "business_name": business_name,
            "description": f"עסק של {business_name}",
            "owner_id": user_id,
            "subscription_tier": "free",
            "subscription_status": "active",
            "is_active": True
        }
        
        business_result = supabase.table("businesses")\
            .insert(business_data)\
            .execute()
        
        if business_result.data:
            logger.info(f"Business created: {business_id} for user {user_id}")
            return business_result.data[0]['id']  # Return the UUID
        
    except Exception as e:
        logger.error(f"Failed to create business: {str(e)}")
    
    return None


async def initialize_user_workspace(user_id: str, email: str, full_name: str, business_name: str) -> dict:
    """
    Initialize user workspace (profile + business) on first login.
    This should be called after email confirmation.
    """
    result = {
        "profile_created": False,
        "business_created": False,
        "business_id": None
    }
    
    # Step 1: Create profile if it doesn't exist
    profile = get_user_profile(user_id)
    if not profile:
        token = generate_verification_token()
        expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        profile = create_user_profile(user_id, email, full_name, token, expires_at)
        if profile:
            result["profile_created"] = True
            logger.info(f"User profile created for: {email}")
    
    # Step 2: Create business if it doesn't exist
    if profile:
        # Check if user already has a business
        existing_business = supabase.table("businesses")\
            .select("id")\
            .eq("owner_id", user_id)\
            .execute()
        
        if not existing_business.data:
            business_uuid = create_business_for_user(user_id, business_name)
            if business_uuid:
                result["business_created"] = True
                result["business_id"] = business_uuid
    
    return result


def generate_verification_token() -> str:
    """Generate a secure random verification token."""
    return secrets.token_urlsafe(32)


def save_verification_token(user_id: str, token: str) -> bool:
    """
    Save verification token to user profile.
    
    Args:
        user_id: User ID
        token: Verification token
        
    Returns:
        bool: True if saved successfully
    """
    try:
        expires_at = datetime.utcnow() + timedelta(hours=24)
        updated_profile = update_profile_row(
            user_id,
            {
                "email_verification_token": token,
                "email_verification_expires_at": expires_at.isoformat(),
                "email_verified": False
            },
            "user_id,email_verification_token,email_verified"
        )
        return bool(updated_profile and updated_profile.get("email_verification_token") == token)
    except Exception as e:
        logger.error(f"Error saving verification token: {str(e)}")
        return False


def _auth_error_status_code(error: Exception) -> int:
    """Map a Supabase Auth failure to a client-safe HTTP status."""
    raw_status = getattr(error, "status_code", None) or getattr(error, "status", None)
    try:
        upstream_status = int(raw_status)
    except (TypeError, ValueError):
        upstream_status = 0

    return status.HTTP_400_BAD_REQUEST if 400 <= upstream_status < 500 else status.HTTP_502_BAD_GATEWAY


def _is_database_permission_error(error: Exception) -> bool:
    """Detect Postgres privilege/RLS failures returned by PostgREST."""
    error_text = str(error).lower()
    error_code = str(getattr(error, "code", "")).lower()
    return (
        error_code == "42501"
        or "42501" in error_text
        or "permission denied" in error_text
        or "row-level security" in error_text
        or "rls policy" in error_text
    )


# ============================================
# Routes
# ============================================

@router.post("/signup", response_model=dict, status_code=status.HTTP_201_CREATED)
async def signup(request: UserRegister):
    """
    Register a new user with email and password.
    Creates profile and sends verification email via Resend.
    """
    try:
        # Register user with Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "options": {
                "data": {
                    "full_name": request.full_name,
                    "business_name": request.business_name
                }
            }
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration failed"
            )
        
        user = auth_response.user
        
        # Generate token first
        token = generate_verification_token()
        expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
        
        # Create profile + token in one insert (avoids RLS blocking a separate UPDATE)
        profile = create_user_profile(user.id, request.email, request.full_name, token, expires_at)
        if not profile:
            logger.error(f"Failed to create profile for {request.email}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="server_error")
        
        # Send verification email via Resend
        email_sent = email_service.send_verification_email(
            to_email=request.email,
            token=token,
            user_name=request.full_name
        )
        
        if not email_sent:
            logger.error(f"Failed to send verification email to {request.email}")
        
        logger.info(f"User registered: {user.email}")
        return {"message": "Confirmation email sent. Please check your inbox."}
    
    except HTTPException:
        raise
    except SupabaseAuthApiError as e:
        error_message = str(e)
        logger.error(f"Registration error (AuthApiError): {error_message}")
        if "already registered" in error_message.lower() or "already exists" in error_message.lower() or "duplicate" in error_message.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already registered")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        error_message = str(e)
        logger.error(f"Registration error: {error_message}", exc_info=True)
        if "already exists" in error_message.lower() or "duplicate" in error_message.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email_exists")
        if "rate limit" in error_message.lower() or "429" in error_message:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limit")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="server_error")


# Keep the old /register endpoint for backward compatibility
@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
async def register_legacy(request: UserRegister):
    """
    Legacy registration endpoint - redirects to /signup.
    """
    return await signup(request)


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLogin):
    """
    Login with email and password.
    Returns JWT access token.
    Also initializes user workspace (profile + business) on first login.
    """
    try:
        # Authenticate with Supabase
        auth_response = supabase.auth.sign_in_with_password({
            "email": request.email,
            "password": request.password
        })
        
        if not auth_response.user or not auth_response.session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )
        
        user = auth_response.user
        session = auth_response.session
        
        # Check email verification status
        profile = get_user_profile(user.id)
        if profile and not profile.get("email_verified", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="email_not_verified"
            )
        
        # Initialize user workspace on first login
        business_name = user.user_metadata.get("business_name", "My Business") if user.user_metadata else "My Business"
        full_name = user.user_metadata.get("full_name", "") if user.user_metadata else ""
        
        workspace_result = await initialize_user_workspace(
            user_id=user.id,
            email=user.email or request.email,
            full_name=full_name,
            business_name=business_name
        )
        
        if workspace_result.get("profile_created") or workspace_result.get("business_created"):
            logger.info(f"Workspace initialized for user: {user.email}")
        
        logger.info(f"User logged in: {user.email}")
        
        return TokenResponse(
            access_token=session.access_token,
            token_type="bearer",
            user_id=user.id,
            email=user.email or ""
        )
    
    except HTTPException:
        raise
    except SupabaseAuthApiError as e:
        logger.error(f"Login error (AuthApiError): {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )


@router.get("/verify", response_class=HTMLResponse)
async def verify_email(token: str = Query(..., description="Email verification token")):
    """
    Verify user email address using verification token.
    Returns a user-friendly HTML confirmation page.
    """
    try:
        # Find user by verification token
        result = supabase.table("profiles")\
            .select("*")\
            .eq("email_verification_token", token)\
            .execute()
        
        if not result.data:
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Verification Failed - ConversaPay</title>
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; text-align: center; }
                    .container { background: #f9f9f9; padding: 40px; border-radius: 10px; margin-top: 50px; }
                    .error-icon { font-size: 60px; color: #dc3545; margin-bottom: 20px; }
                    .button { display: inline-block; padding: 15px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 10px; font-weight: bold; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="error-icon">❌</div>
                    <h1>Verification Failed</h1>
                    <p>The verification link is invalid or has expired.</p>
                    <p>Please try registering again or contact support if you continue to have issues.</p>
                    <a href="/" class="button">Go to Homepage</a>
                </div>
            </body>
            </html>
            """, status_code=400)
        
        profile = result.data[0]
        
        # Check if token has expired
        if profile.get("email_verification_expires_at"):
            expires_at = datetime.fromisoformat(profile["email_verification_expires_at"].replace("Z", "+00:00"))
            if datetime.utcnow().replace(tzinfo=expires_at.tzinfo) > expires_at:
                return HTMLResponse(content="""
                <!DOCTYPE html>
                <html>
                <head>
                    <meta charset="utf-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>Link Expired - ConversaPay</title>
                    <style>
                        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; text-align: center; }
                        .container { background: #f9f9f9; padding: 40px; border-radius: 10px; margin-top: 50px; }
                        .warning-icon { font-size: 60px; color: #ffc107; margin-bottom: 20px; }
                        .button { display: inline-block; padding: 15px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 10px; font-weight: bold; }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="warning-icon">⏰</div>
                        <h1>Link Expired</h1>
                        <p>This verification link has expired. Verification links are valid for 24 hours.</p>
                        <p>Please request a new verification email or try registering again.</p>
                        <a href="/register.html" class="button">Register Again</a>
                        <a href="/" class="button">Go to Homepage</a>
                    </div>
                </body>
                </html>
                """, status_code=400)
        
        # Check if already verified
        if profile.get("email_verified"):
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Already Verified - ConversaPay</title>
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; text-align: center; }
                    .container { background: #f9f9f9; padding: 40px; border-radius: 10px; margin-top: 50px; }
                    .info-icon { font-size: 60px; color: #17a2b8; margin-bottom: 20px; }
                    .button { display: inline-block; padding: 15px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 10px; font-weight: bold; }
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="info-icon">ℹ️</div>
                    <h1>Already Verified</h1>
                    <p>Your email has already been verified. You can log in to your account.</p>
                    <a href="/login.html" class="button">Login</a>
                    <a href="/" class="button">Go to Homepage</a>
                </div>
            </body>
            </html>
            """)
        
        # Mark email as verified via a SECURITY DEFINER RPC.
        verify_result = supabase.rpc(
            "mark_email_verified", {"p_user_id": profile["user_id"]}
        ).execute()

        if not verify_result.data:
            logger.error(f"Failed to mark email as verified for user_id: {profile['user_id']}")
            raise HTTPException(status_code=500, detail="Failed to verify email")

        logger.info(f"Email verified for user: {profile['email']}")
        
        # Return success HTML page
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Email Verified - ConversaPay</title>
            <style>
                body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; text-align: center; }
                .container { background: #f9f9f9; padding: 40px; border-radius: 10px; margin-top: 50px; }
                .success-icon { font-size: 60px; color: #28a745; margin-bottom: 20px; }
                .button { display: inline-block; padding: 15px 30px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; margin: 20px 10px; font-weight: bold; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✅</div>
                <h1>Email Verified Successfully!</h1>
                <p>Thank you for verifying your email address. Your account is now active.</p>
                <p>You can now log in and start using ConversaPay!</p>
                <a href="/login.html" class="button">Login to Your Account</a>
                <a href="/" class="button">Go to Homepage</a>
            </div>
        </body>
        </html>
        """)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email verification error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during email verification"
        )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Logout current user by revoking their session server-side.

    FIX: The previous implementation incorrectly passed the user's JWT as
    the Supabase project API key to create_client(). The second argument
    must be the project anon_key or service_role_key, not a user token.
    """
    try:
        authorization = request.headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            access_token = authorization.split(" ", 1)[1]
            try:
                # Use a properly-initialized client (anon key as the project
                # API key) and sign out via the user's access token.
                user_client = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_ANON_KEY
                )
                user_client.auth.sign_out(access_token)
            except (AttributeError, TypeError):
                # Fallback for gotrue-py versions without token param.
                # Supabase JWTs are short-lived; client discards the token.
                logger.debug("sign_out(token) not supported; client-side logout only")
            except Exception as sign_out_err:
                logger.debug(f"Server-side sign_out non-fatal: {sign_out_err}")

        logger.info(f"User logged out: {current_user.email}")
        return MessageResponse(message="Logged out successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Logout error (non-fatal): {str(e)}")
        # Always return success. The client must discard its local token
        # regardless of server-side revocation outcome.
        return MessageResponse(message="Logged out successfully")


@router.post("/password-reset/request", response_model=MessageResponse)
async def request_password_reset(request: Request, request_data: PasswordResetRequest):
    """
    Request a password reset email with enhanced security.
    """
    try:
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        logger.info(
            f"Password reset requested - Email: {request_data.email}, "
            f"IP: {client_ip}, User-Agent: {user_agent[:100]}"
        )
        
        supabase.auth.reset_password_for_email(
            str(request_data.email),
            {
                "redirect_to": f"{settings.BASE_URL}/forgot-password.html"
            }
        )
        
        logger.info(f"Password reset email sent to: {request_data.email}")
        return MessageResponse(
            message="If an account exists with this email, you will receive a password reset link."
        )
    
    except HTTPException:
        raise
    except SupabaseAuthApiError as e:
        error_message = str(e)
        response_status = _auth_error_status_code(e)
        logger.error(
            f"Password reset request AuthApiError: {error_message}; "
            f"returning HTTP {response_status}",
            exc_info=True
        )
        if response_status == status.HTTP_400_BAD_REQUEST:
            detail = "Password reset request was rejected. Check the email address and try again."
        else:
            detail = "Password reset service is temporarily unavailable. Please try again later."
        raise HTTPException(status_code=response_status, detail=detail)
    except Exception as e:
        logger.error(f"Password reset request error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Password reset service is temporarily unavailable. Please try again later."
        )


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def confirm_password_reset(request: Request):
    """
    Confirm password reset with token and new password.

    The body is validated here instead of by FastAPI's parameter validation so
    missing, malformed, or invalid values return an actionable 400 response
    rather than an opaque 422 validation payload.
    """
    try:
        try:
            payload = await request.json()
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request body must be valid JSON with a reset token and new password."
            )

        if not isinstance(payload, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request body must be an object with a reset token and new password."
            )

        if not isinstance(payload.get("token"), str) or not payload.get("token", "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A valid reset token is required."
            )

        if not isinstance(payload.get("new_password"), str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A new password is required and must be at least 8 characters long."
            )

        try:
            request_data = PasswordReset(**payload)
        except ValidationError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A new password is required and must be at least 8 characters long."
            )

        if len(request_data.new_password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long."
            )
        
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        
        supabase.auth.update_user({
            "password": request_data.new_password
        }, request_data.token.strip())
        
        logger.info(
            f"Password reset successful - IP: {client_ip}, "
            f"User-Agent: {user_agent[:100]}"
        )
        
        try:
            user_response = supabase.auth.get_user(request_data.token.strip())
            if user_response and user_response.user:
                user_id = user_response.user.id
                
                supabase.table("audit_logs").insert({
                    "user_id": user_id,
                    "action": "password_reset",
                    "ip_address": client_ip,
                    "user_agent": user_agent[:255],
                    "timestamp": datetime.utcnow().isoformat(),
                    "details": {
                        "method": "email_reset",
                        "success": True
                    }
                }).execute()
                
                logger.info(f"Password reset audit log created for user: {user_id}")
        except Exception as audit_error:
            logger.warning(f"Failed to create audit log: {str(audit_error)}")
        
        return MessageResponse(message="Password reset successfully")
    
    except HTTPException:
        raise
    except SupabaseAuthApiError as e:
        logger.error(f"Password reset confirm error (AuthApiError): {str(e)}", exc_info=True)
        error_message = str(e)
        if "expired" in error_message.lower() or "invalid" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired reset token. Request a new password reset link."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset failed. Check the reset token and try again."
        )
    except Exception as e:
        logger.error(f"Password reset confirm error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token. Request a new password reset link."
        )


@router.get("/password-reset/verify-identity", response_model=dict)
async def verify_identity_for_reset(
    request: Request,
    email: str = Query(..., description="User email address")
):
    """
    Verify user identity before allowing password reset.
    """
    try:
        client_ip = request.client.host if request.client else "unknown"
        
        try:
            user_lookup = supabase.auth.admin.get_user_by_email(email)
            if user_lookup and user_lookup.user:
                user_id = user_lookup.user.id
                
                verification_token = generate_verification_token()
                expires_at = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
                
                update_profile_row(
                    user_id,
                    {
                        "email_verification_token": verification_token,
                        "email_verification_expires_at": expires_at
                    }
                )
                
                email_sent = email_service.send_verification_email(
                    to_email=email,
                    token=verification_token,
                    user_name=user_lookup.user.user_metadata.get("full_name", "משתמש")
                )
                
                logger.info(
                    f"Identity verification initiated for: {email}, "
                    f"IP: {client_ip}, Email sent: {email_sent}"
                )
                
                return {
                    "message": "Verification code sent to your email",
                    "email": email,
                    "expires_in_minutes": 10
                }
        except SupabaseAuthApiError:
            pass
        
        logger.info(f"Identity verification requested for: {email}, IP: {client_ip}")
        return {
            "message": "If an account exists with this email, a verification code has been sent",
            "email": email,
            "expires_in_minutes": 10
        }
    
    except Exception as e:
        logger.error(f"Identity verification error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during identity verification"
        )


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(current_user: AuthUser = Depends(get_current_user)):
    """
    Get current user information.
    Requires authentication.
    """
    profile = get_user_profile(current_user.user_id)
    
    return UserInfoResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        profile=profile
    )


@router.put("/whatsapp-settings", response_model=dict)
async def update_whatsapp_settings(
    request: Request,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Update WhatsApp Business API settings for Premium users.
    """
    body = await request.json()
    profile = get_user_profile(current_user.user_id)
    if not profile or profile.get("plan_type") != "premium":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="premium_required")

    result = update_profile_row(
        current_user.user_id,
        {
            "whatsapp_phone_number_id": body.get("whatsapp_phone_number_id"),
            "whatsapp_access_token": body.get("whatsapp_access_token"),
            "whatsapp_verify_token": body.get("whatsapp_verify_token")
        },
        "user_id,whatsapp_phone_number_id,whatsapp_access_token,whatsapp_verify_token"
    )

    if not result:
        raise HTTPException(status_code=500, detail="Failed to update WhatsApp settings")

    return {"message": "WhatsApp settings updated"}


@router.put("/me", response_model=dict)
async def update_current_user(
    full_name: Optional[str] = None,
    current_user: AuthUser = Depends(get_current_user)
):
    """
    Update current user profile.
    """
    try:
        update_data = {}
        if full_name:
            update_data["full_name"] = full_name
        
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No data to update"
            )
        
        result = update_profile_row(current_user.user_id, update_data)
        
        if result:
            return {
                "message": "Profile updated successfully",
                "profile": result
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to update profile"
        )


# ============================================
# Google OAuth
# ============================================

@router.post("/oauth/session", response_model=dict)
async def complete_oauth_session(current_user: AuthUser = Depends(get_current_user)):
    """
    Finalize a Supabase OAuth (e.g. Google) sign-in.

    Called by the frontend right after it establishes a Supabase session
    client-side. Ensures a `profiles` row and a starter `business` exist
    for the user, same as first-time email/password login does.
    """
    try:
        full_name = ""
        business_name = "העסק שלי"
        try:
            user_lookup = supabase.auth.admin.get_user_by_id(current_user.user_id)
            metadata = (user_lookup.user.user_metadata or {}) if user_lookup and user_lookup.user else {}
            full_name = metadata.get("full_name") or metadata.get("name") or ""
            business_name = metadata.get("business_name") or (
                f"העסק של {full_name}" if full_name else "העסק שלי"
            )
        except Exception as e:
            logger.warning(f"Could not fetch OAuth user metadata: {str(e)}")

        # Do not use get_user_profile here: it intentionally swallows database
        # errors, which would make a missing profiles SELECT privilege look like
        # a missing row and lead to a misleading insert attempt.
        try:
            profile_result = supabase.table("profiles") \
                .select("*") \
                .eq("user_id", current_user.user_id) \
                .execute()
            profile = profile_result.data[0] if profile_result.data else None
        except PostgrestAPIError as e:
            if _is_database_permission_error(e):
                logger.error(
                    "SQL PERMISSION WARNING: OAuth session cannot SELECT from "
                    "public.profiles for user %s. Missing SQL privileges or an "
                    "RLS policy is blocking the query. Grant SELECT on profiles "
                    "and verify the Supabase service-role/RLS configuration. "
                    "Database error: %s",
                    current_user.user_id,
                    str(e),
                    exc_info=True,
                )
            else:
                logger.error(
                    "OAuth session profiles query failed for user %s: %s",
                    current_user.user_id,
                    str(e),
                    exc_info=True,
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to load your profile. Please try again later."
            )
        except Exception as e:
            if _is_database_permission_error(e):
                logger.error(
                    "SQL PERMISSION WARNING: OAuth session cannot SELECT from "
                    "public.profiles for user %s. Missing SQL privileges or an "
                    "RLS policy is blocking the query. Grant SELECT on profiles "
                    "and verify the Supabase service-role/RLS configuration. "
                    "Database error: %s",
                    current_user.user_id,
                    str(e),
                    exc_info=True,
                )
            else:
                logger.error(
                    "Unexpected OAuth session profiles lookup error for user %s: %s",
                    current_user.user_id,
                    str(e),
                    exc_info=True,
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Unable to load your profile. Please try again later."
            )

        if not profile:
            token = generate_verification_token()
            expires_at = (datetime.utcnow() + timedelta(hours=24)).isoformat()
            profile = create_user_profile(
                current_user.user_id, current_user.email, full_name, token, expires_at
            )
            if profile:
                # Google already verified this email address for us.
                supabase.rpc("mark_email_verified", {"p_user_id": current_user.user_id}).execute()
                logger.info(f"Profile created for OAuth user: {current_user.email}")

        existing_business = supabase.table("businesses") \
            .select("id") \
            .eq("owner_id", current_user.user_id) \
            .execute()

        if not existing_business.data:
            create_business_for_user(current_user.user_id, business_name)
            logger.info(f"Business created for OAuth user: {current_user.email}")

        return {
            "user_id": current_user.user_id,
            "email": current_user.email,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth session finalize error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to finalize sign-in"
        )
