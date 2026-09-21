"""Registration verification and business onboarding routes."""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from supabase import Client, create_client
from supabase_auth.errors import AuthApiError as SupabaseAuthApiError

from backend.config import settings
from backend.middleware.auth import AuthUser, get_current_user
from backend.middleware.rate_limiter import check_rate_limit
from backend.routers.auth import create_business_for_user, create_user_profile, get_user_profile, update_profile_row
from backend.services.email_service import email_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


class SignupCodeRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    business_name: str = Field(..., min_length=1, max_length=255)


class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str = Field(..., pattern=r"^\d{6}$")


class ResendCodeRequest(BaseModel):
    email: EmailStr


class OnboardingRequest(BaseModel):
    business_category: str = Field(..., min_length=2, max_length=80)
    custom_ai_instructions: str = Field(default="", max_length=4000)


def _code_hash(email: str, code: str) -> str:
    payload = f"{email.strip().lower()}:{code}:{settings.SECRET_KEY}".encode("utf-8")
    return "code:" + hashlib.sha256(payload).hexdigest()


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _owned_businesses(user_id: str) -> list[dict[str, Any]]:
    result = supabase.table("businesses").select("*").eq("owner_id", user_id).order("created_at", desc=True).execute()
    return result.data or []


def _settings_for(row: dict[str, Any] | None) -> dict[str, Any]:
    return dict((row or {}).get("settings") or {})


def _onboarding_required(user_id: str, businesses: list[dict[str, Any]] | None = None) -> bool:
    rows = businesses if businesses is not None else _owned_businesses(user_id)
    if not rows:
        return True
    return not bool(_settings_for(rows[0]).get("onboarding_completed"))


def _auth_view(current_user: AuthUser) -> dict[str, Any]:
    profile = get_user_profile(current_user.user_id)
    businesses = _owned_businesses(current_user.user_id)
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "profile": profile,
        "requires_business_onboarding": _onboarding_required(current_user.user_id, businesses),
    }


@router.post("/signup-code", status_code=status.HTTP_201_CREATED)
async def signup_with_code(request: SignupCodeRequest, request_obj: Request):
    """Create an unconfirmed Supabase Auth user without sending Supabase's link email."""
    check_rate_limit(request_obj, extra_key=f"signup:{request.email.lower()}")
    try:
        existing_profile = supabase.table("profiles").select("user_id,email_verified").eq("email", request.email).maybe_single().execute().data
        if existing_profile:
            raise HTTPException(400, "email_exists")

        auth_response = supabase.auth.admin.create_user({
            "email": request.email,
            "password": request.password,
            "email_confirm": False,
            "user_metadata": {"full_name": request.full_name, "business_name": request.business_name},
        })
        if not auth_response or not auth_response.user:
            raise HTTPException(400, "registration_failed")

        user_id = auth_response.user.id
        code = _new_code()
        expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        profile = create_user_profile(
            user_id,
            request.email,
            request.full_name,
            _code_hash(request.email, code),
            expires_at,
        )
        if not profile:
            try:
                supabase.auth.admin.delete_user(user_id)
            except Exception:
                logger.exception("Could not roll back orphan auth user %s", user_id)
            raise HTTPException(500, "server_error")
        if not email_service.send_verification_code(request.email, code, request.full_name):
            raise HTTPException(502, "verification_email_failed")
        return {"message": "verification_code_sent", "email": request.email, "expires_in_minutes": 15}
    except HTTPException:
        raise
    except SupabaseAuthApiError as exc:
        text = str(exc).lower()
        if "already" in text or "exists" in text or "registered" in text or "duplicate" in text:
            raise HTTPException(400, "email_exists") from exc
        logger.error("Supabase admin registration error: %s", exc)
        raise HTTPException(400, "registration_failed") from exc
    except Exception as exc:
        logger.error("signup-code failed: %s", exc, exc_info=True)
        text = str(exc).lower()
        if "duplicate" in text or "already" in text or "exists" in text:
            raise HTTPException(400, "email_exists") from exc
        raise HTTPException(500, "server_error") from exc


@router.post("/verify-code")
async def verify_email_code(request: VerifyCodeRequest, request_obj: Request):
    check_rate_limit(request_obj, extra_key=f"verify:{request.email.lower()}")
    result = supabase.table("profiles").select("*").eq("email", request.email).maybe_single().execute()
    profile = result.data or {}
    if not profile:
        raise HTTPException(404, "verification_not_found")
    if profile.get("email_verified"):
        # Repair Auth state for accounts whose profile was verified by an older flow.
        try:
            supabase.auth.admin.update_user_by_id(profile["user_id"], {"email_confirm": True})
        except Exception as exc:
            logger.warning("Could not repair Supabase Auth verification state: %s", exc)
        return {"verified": True}

    expires_raw = profile.get("email_verification_expires_at")
    if not expires_raw:
        raise HTTPException(400, "verification_code_expired")
    expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(400, "verification_code_expired")

    expected = str(profile.get("email_verification_token") or "")
    if not secrets.compare_digest(expected, _code_hash(request.email, request.code)):
        raise HTTPException(400, "verification_code_invalid")

    # Both sources of truth must become verified: Supabase Auth protects API access,
    # while profiles.email_verified is retained for the product's own state/UI.
    try:
        supabase.auth.admin.update_user_by_id(profile["user_id"], {"email_confirm": True})
    except Exception as exc:
        logger.error("Failed to confirm Supabase Auth email for %s: %s", profile["user_id"], exc, exc_info=True)
        raise HTTPException(500, "verification_failed") from exc
    verified = supabase.rpc("mark_email_verified", {"p_user_id": profile["user_id"]}).execute()
    if not verified.data:
        raise HTTPException(500, "verification_failed")
    return {"verified": True}


@router.post("/resend-code")
async def resend_code(request: ResendCodeRequest, request_obj: Request):
    check_rate_limit(request_obj, extra_key=f"resend:{request.email.lower()}")
    result = supabase.table("profiles").select("*").eq("email", request.email).maybe_single().execute()
    profile = result.data or {}
    # Deliberately return a neutral result for unknown addresses to avoid account enumeration.
    if not profile:
        return {"message": "verification_code_sent"}
    if profile.get("email_verified"):
        return {"message": "already_verified"}

    code = _new_code()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
    updated = update_profile_row(profile["user_id"], {
        "email_verification_token": _code_hash(request.email, code),
        "email_verification_expires_at": expires_at,
        "email_verified": False,
    })
    if not updated:
        raise HTTPException(500, "server_error")
    if not email_service.send_verification_code(request.email, code, profile.get("full_name") or ""):
        raise HTTPException(502, "verification_email_failed")
    return {"message": "verification_code_sent", "expires_in_minutes": 15}


@router.get("/me")
async def get_current_user_with_onboarding(current_user: AuthUser = Depends(get_current_user)):
    return _auth_view(current_user)


@router.get("/onboarding")
async def get_onboarding(current_user: AuthUser = Depends(get_current_user)):
    if not current_user.email_verified:
        raise HTTPException(403, "EMAIL_NOT_VERIFIED")
    businesses = _owned_businesses(current_user.user_id)
    business = businesses[0] if businesses else None
    metadata: dict[str, Any] = {}
    try:
        lookup = supabase.auth.admin.get_user_by_id(current_user.user_id)
        metadata = (lookup.user.user_metadata or {}) if lookup and lookup.user else {}
    except Exception as exc:
        logger.warning("Could not read onboarding metadata: %s", exc)
    business_settings = _settings_for(business)
    return {
        "business_name": (business or {}).get("business_name") or metadata.get("business_name") or "",
        "business_category": business_settings.get("business_category", ""),
        "custom_ai_instructions": business_settings.get("custom_ai_instructions", ""),
        "completed": bool(business_settings.get("onboarding_completed")),
    }


@router.post("/onboarding")
async def save_onboarding(request: OnboardingRequest, current_user: AuthUser = Depends(get_current_user)):
    if not current_user.email_verified:
        raise HTTPException(403, "EMAIL_NOT_VERIFIED")
    category = request.business_category.strip()
    custom = request.custom_ai_instructions.strip()
    businesses = _owned_businesses(current_user.user_id)
    business = businesses[0] if businesses else None

    if not business:
        business_name = "My Business"
        try:
            lookup = supabase.auth.admin.get_user_by_id(current_user.user_id)
            metadata = (lookup.user.user_metadata or {}) if lookup and lookup.user else {}
            business_name = str(metadata.get("business_name") or business_name).strip() or business_name
        except Exception as exc:
            logger.warning("Could not read business name during onboarding: %s", exc)
        business_id = create_business_for_user(current_user.user_id, business_name)
        if not business_id:
            raise HTTPException(500, "business_creation_failed")
        businesses = _owned_businesses(current_user.user_id)
        business = businesses[0] if businesses else None
    if not business:
        raise HTTPException(500, "business_not_found")

    merged = _settings_for(business)
    merged.update({
        "business_category": category,
        "custom_ai_instructions": custom,
        "onboarding_completed": True,
        "onboarding_completed_at": datetime.now(timezone.utc).isoformat(),
    })
    updated = supabase.table("businesses").update({"settings": merged}).eq("id", business["id"]).eq("owner_id", current_user.user_id).execute()
    if not updated.data:
        raise HTTPException(500, "onboarding_save_failed")
    return {"completed": True, "business_id": updated.data[0]["id"]}


@router.post("/oauth/session")
async def complete_oauth_session_with_onboarding(current_user: AuthUser = Depends(get_current_user)):
    try:
        full_name = ""
        business_name = ""
        try:
            user_lookup = supabase.auth.admin.get_user_by_id(current_user.user_id)
            metadata = (user_lookup.user.user_metadata or {}) if user_lookup and user_lookup.user else {}
            full_name = metadata.get("full_name") or metadata.get("name") or ""
            business_name = str(metadata.get("business_name") or "").strip()
        except Exception as exc:
            logger.warning("Could not fetch OAuth user metadata: %s", exc)

        profile = get_user_profile(current_user.user_id)
        if not profile:
            profile = create_user_profile(current_user.user_id, current_user.email, full_name, "oauth", "2099-01-01T00:00:00+00:00")
            if not profile:
                raise HTTPException(500, "profile_creation_failed")
        if not profile.get("email_verified", False):
            supabase.rpc("mark_email_verified", {"p_user_id": current_user.user_id}).execute()

        businesses = _owned_businesses(current_user.user_id)
        if not businesses and business_name:
            create_business_for_user(current_user.user_id, business_name)
            businesses = _owned_businesses(current_user.user_id)
        return {
            "user_id": current_user.user_id,
            "email": current_user.email,
            "requires_business_onboarding": _onboarding_required(current_user.user_id, businesses),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("OAuth onboarding finalize failed: %s", exc, exc_info=True)
        raise HTTPException(500, "Failed to finalize sign-in") from exc
