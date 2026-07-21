"""
Authentication router for user registration, login, logout, and password reset.
Uses Supabase Auth for authentication.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Request, Query
from fastapi.security import HTTPBearer
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import logging
import secrets

from supabase import create_client, Client
from supabase_auth.errors import AuthApiError
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
from backend.services.payme_service import payme_service

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


def create_user_profile(user_id: str, email: str, full_name: str) -> dict:
    """Create user profile in database."""
    try:
        result = supabase.table("profiles").insert({
            "user_id": user_id,
            "email": email,
            "full_name": full_name,
            "is_pro": False,
            "plan_type": "free",
            "email_verified": False,
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
        profile = create_user_profile(user_id, email, full_name)
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
    
    # Note: PayMe checkout is NOT created during login/initialization
    # It will only be created when user explicitly clicks "Upgrade" button
    
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
        
        result = supabase.table("profiles")\
            .update({
                "email_verification_token": token,
                "email_verification_expires_at": expires_at.isoformat(),
                "email_verified": False
            })\
            .eq("user_id", user_id)\
            .execute()
        
        return bool(result.data)
    except Exception as e:
        logger.error(f"Error saving verification token: {str(e)}")
        return False


# ============================================
# Routes
# ============================================

@router.post("/signup", response_model=dict, status_code=status.HTTP_201_CREATED)
async def signup(request: UserRegister):
    """
    Register a new user with email and password.
    Only performs Supabase Auth sign_up - does NOT create profile or business yet.
    Profile and business will be created on first login after email confirmation.
    
    Returns a success response indicating that a confirmation email has been sent.
    """
    try:
        # Register user with Supabase Auth (with email confirmation enabled)
        auth_response = supabase.auth.sign_up({
            "email": request.email,
            "password": request.password,
            "options": {
                "data": {
                    "full_name": request.full_name,
                    "business_name": request.business_name  # Store for later use
                }
            }
        })
        
        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration failed"
            )
        
        user = auth_response.user
        
        logger.info(f"User registered successfully: {user.email}")
        
        # Return response indicating email verification is required
        return {
            "message": "Confirmation email sent. Please check your inbox."
        }
    
    except HTTPException:
        raise
    except AuthApiError as e:
        error_message = str(e)
        logger.error(f"Registration error (AuthApiError): {error_message}")
        
        # Handle duplicate user registration
        if "already registered" in error_message.lower() or "already exists" in error_message.lower() or "duplicate" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User already registered"
            )
        
        # Handle other auth API errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        error_message = str(e)
        logger.error(f"Registration error: {error_message}", exc_info=True)
        
        # Handle specific errors with friendly error codes
        if "already exists" in error_message.lower() or "duplicate" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="email_exists"
            )
        
        # Handle rate limiting
        if "rate limit" in error_message.lower() or "429" in error_message:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="rate_limit"
            )
        
        # Generic error
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="server_error"
        )


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
        
        # Initialize user workspace on first login (if not already done)
        # Get user metadata to retrieve business_name if available
        business_name = user.user_metadata.get("business_name", "My Business") if user.user_metadata else "My Business"
        full_name = user.user_metadata.get("full_name", "") if user.user_metadata else ""
        
        # Initialize user workspace (profile + business) on first login
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
    except AuthApiError as e:
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
            # Return error HTML page
            return HTMLResponse(content="""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Verification Failed - ConversaPay</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                        text-align: center;
                    }
                    .container {
                        background: #f9f9f9;
                        padding: 40px;
                        border-radius: 10px;
                        margin-top: 50px;
                    }
                    .error-icon {
                        font-size: 60px;
                        color: #dc3545;
                        margin-bottom: 20px;
                    }
                    .button {
                        display: inline-block;
                        padding: 15px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 20px 10px;
                        font-weight: bold;
                    }
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
                        body {
                            font-family: Arial, sans-serif;
                            line-height: 1.6;
                            color: #333;
                            max-width: 600px;
                            margin: 0 auto;
                            padding: 20px;
                            text-align: center;
                        }
                        .container {
                            background: #f9f9f9;
                            padding: 40px;
                            border-radius: 10px;
                            margin-top: 50px;
                        }
                        .warning-icon {
                            font-size: 60px;
                            color: #ffc107;
                            margin-bottom: 20px;
                        }
                        .button {
                            display: inline-block;
                            padding: 15px 30px;
                            background: #667eea;
                            color: white;
                            text-decoration: none;
                            border-radius: 5px;
                            margin: 20px 10px;
                            font-weight: bold;
                        }
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
                    body {
                        font-family: Arial, sans-serif;
                        line-height: 1.6;
                        color: #333;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                        text-align: center;
                    }
                    .container {
                        background: #f9f9f9;
                        padding: 40px;
                        border-radius: 10px;
                        margin-top: 50px;
                    }
                    .info-icon {
                        font-size: 60px;
                        color: #17a2b8;
                        margin-bottom: 20px;
                    }
                    .button {
                        display: inline-block;
                        padding: 15px 30px;
                        background: #667eea;
                        color: white;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 20px 10px;
                        font-weight: bold;
                    }
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
        
        # Mark email as verified
        supabase.table("profiles")\
            .update({
                "email_verified": True,
                "email_verification_token": None,
                "email_verification_expires_at": None
            })\
            .eq("id", profile["id"])\
            .execute()
        
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
                body {
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    text-align: center;
                }
                .container {
                    background: #f9f9f9;
                    padding: 40px;
                    border-radius: 10px;
                    margin-top: 50px;
                }
                .success-icon {
                    font-size: 60px;
                    color: #28a745;
                    margin-bottom: 20px;
                }
                .button {
                    display: inline-block;
                    padding: 15px 30px;
                    background: #667eea;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 10px;
                    font-weight: bold;
                }
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
    Logout current user by invalidating the session.
    """
    try:
        # Extract the access token from the Authorization header
        authorization: str = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid authorization header"
            )
        
        access_token = authorization.split(" ")[1]
        
        # Create a Supabase client with the user's access token
        user_supabase = create_client(
            settings.SUPABASE_URL,
            access_token
        )
        
        # Sign out the user
        user_supabase.auth.sign_out()
        
        logger.info(f"User logged out: {current_user.email}")
        return MessageResponse(message="Logged out successfully")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Logout failed"
        )


@router.post("/password-reset/request", response_model=MessageResponse)
async def request_password_reset(request: PasswordResetRequest):
    """
    Request a password reset email.
    Supabase will send a password reset email to the user.
    """
    try:
        supabase.auth.reset_password_for_email(str(request.email))
        logger.info(f"Password reset requested for: {request.email}")
        return MessageResponse(
            message="If an account exists with this email, you will receive a password reset link."
        )
    
    except Exception as e:
        logger.error(f"Password reset request error: {str(e)}")
        # Don't reveal if email exists or not
        return MessageResponse(
            message="If an account exists with this email, you will receive a password reset link."
        )


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def confirm_password_reset(request: PasswordReset):
    """
    Confirm password reset with token and new password.
    """
    try:
        supabase.auth.update_user({
            "password": request.new_password
        }, request.token)
        
        logger.info("Password reset successful")
        return MessageResponse(message="Password reset successfully")
    
    except Exception as e:
        logger.error(f"Password reset confirm error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
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
        
        result = supabase.table("profiles").update(update_data).eq("user_id", current_user.user_id).execute()
        
        if result.data:
            return {
                "message": "Profile updated successfully",
                "profile": result.data[0]
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