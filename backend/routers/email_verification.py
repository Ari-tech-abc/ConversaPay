"""Email verification routes that sit in front of the legacy auth routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client, create_client
import logging

from backend.config import settings
from backend.middleware.auth import AuthUser, get_current_user
from backend.models.schemas import UserRegister
from backend.routers.auth import create_user_profile, generate_verification_token, email_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["authentication"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


class MessageResponse(BaseModel):
    message: str


EMAIL_REDIRECT_TO = f"{settings.FRONTEND_URL.rstrip('/')}/auth/callback"


@router.post("/signup", response_model=dict, status_code=status.HTTP_201_CREATED)
async def signup(request: UserRegister):
    try:
        auth_response = supabase.auth.sign_up({
            "email": str(request.email),
            "password": request.password,
            "options": {
                "email_redirect_to": EMAIL_REDIRECT_TO,
                "data": {"full_name": request.full_name, "business_name": request.business_name},
            },
        })
        if not auth_response.user:
            raise HTTPException(status_code=400, detail="Registration failed")

        user = auth_response.user
        token = generate_verification_token()
        profile = create_user_profile(
            user.id,
            str(request.email),
            request.full_name,
            token,
            "2099-01-01T00:00:00+00:00",
        )
        if not profile:
            raise HTTPException(status_code=500, detail="server_error")

        email_service.send_verification_email(to_email=str(request.email), token=token, user_name=request.full_name)
        logger.info("User registered; verification required: %s", user.email)
        return {"message": "Confirmation email sent. Please check your inbox.", "email_verification_required": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Registration error: %s", exc, exc_info=True)
        text = str(exc).lower()
        if "already" in text or "duplicate" in text:
            raise HTTPException(status_code=400, detail="User already registered")
        raise HTTPException(status_code=400, detail="Registration failed")


@router.post("/resend-verification", response_model=MessageResponse)
async def resend_verification(current_user: AuthUser = Depends(get_current_user)):
    if current_user.email_verified:
        return MessageResponse(message="Email is already verified")
    try:
        supabase.auth.resend({
            "type": "signup",
            "email": current_user.email,
            "options": {"email_redirect_to": EMAIL_REDIRECT_TO},
        })
        logger.info("Verification email resent: user_id=%s", current_user.user_id)
        return MessageResponse(message="Verification email sent. Please check your inbox.")
    except Exception as exc:
        logger.error("Verification resend failed for user_id=%s: %s", current_user.user_id, exc, exc_info=True)
        raise HTTPException(status_code=502, detail="Unable to resend verification email") from exc
