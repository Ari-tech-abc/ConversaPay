"""Auth compatibility routes that add onboarding state without changing legacy auth handlers."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from supabase import Client, create_client

from backend.config import settings
from backend.middleware.auth import AuthUser, get_current_user
from backend.routers.auth import (
    create_business_for_user,
    create_user_profile,
    generate_verification_token,
    get_user_profile,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

_DEFAULT_BUSINESS_NAMES = {
    "my business",
    "העסק שלי",
    "business",
}


def is_default_business_name(value: Any) -> bool:
    name = str(value or "").strip().lower()
    return not name or name in _DEFAULT_BUSINESS_NAMES or name.startswith("העסק של ")


def _owned_businesses(user_id: str) -> list[dict[str, Any]]:
    result = supabase.table("businesses").select("*").eq("owner_id", user_id).order("created_at", desc=True).execute()
    return result.data or []


def _onboarding_required(user_id: str, businesses: list[dict[str, Any]] | None = None) -> bool:
    rows = businesses if businesses is not None else _owned_businesses(user_id)
    return not any(not is_default_business_name(row.get("business_name")) for row in rows)


def _auth_view(current_user: AuthUser) -> dict[str, Any]:
    profile = get_user_profile(current_user.user_id)
    businesses = _owned_businesses(current_user.user_id)
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "profile": profile,
        "requires_business_onboarding": _onboarding_required(current_user.user_id, businesses),
    }


@router.get("/me")
async def get_current_user_with_onboarding(current_user: AuthUser = Depends(get_current_user)):
    """Return the legacy auth payload plus a non-breaking onboarding flag."""
    return _auth_view(current_user)


@router.post("/oauth/session")
async def complete_oauth_session_with_onboarding(current_user: AuthUser = Depends(get_current_user)):
    """Provision an OAuth profile without inventing a fake business name."""
    try:
        full_name = ""
        business_name = ""
        try:
            user_lookup = supabase.auth.admin.get_user_by_id(current_user.user_id)
            metadata = (user_lookup.user.user_metadata or {}) if user_lookup and user_lookup.user else {}
            full_name = metadata.get("full_name") or metadata.get("name") or ""
            candidate = str(metadata.get("business_name") or "").strip()
            business_name = candidate if candidate and not is_default_business_name(candidate) else ""
        except Exception as exc:
            logger.warning("Could not fetch OAuth user metadata: %s", exc)

        profile = get_user_profile(current_user.user_id)
        if not profile:
            token = generate_verification_token()
            profile = create_user_profile(
                current_user.user_id,
                current_user.email,
                full_name,
                token,
                "2099-01-01T00:00:00+00:00",
            )
            if not profile:
                raise HTTPException(500, "Failed to create OAuth profile")

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
