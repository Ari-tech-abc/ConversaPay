"""Authenticated SaaS profile, security, preferences, billing and privacy APIs."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser, get_current_user
from backend.routers.auth import get_user_profile, update_profile_row

logger = logging.getLogger(__name__)
router = APIRouter(tags=["profile"])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


class ProfileUpdatePayload(BaseModel):
    """Allow a safe partial update without requiring unrelated profile fields."""
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=255)
    company_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)
    timezone: str | None = Field(default=None, max_length=80)
    avatar_url: str | None = Field(default=None, max_length=2048)


class PasswordPayload(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class PreferencesPayload(BaseModel):
    payment_success: bool = True
    weekly_digest: bool = True
    security_alerts: bool = True
    product_updates: bool = False


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe_update(user_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    result = update_profile_row(user_id, changes)
    if result is None:
        raise HTTPException(status_code=500, detail="Profile update failed")
    return result


def _profile_view(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    return {
        "full_name": row.get("full_name") or "",
        "company_name": row.get("company_name") or "",
        "phone": row.get("phone") or "",
        "timezone": row.get("timezone") or "UTC",
        "avatar_url": row.get("avatar_url") or "",
        "notification_preferences": row.get("notification_preferences") or {"payment_success": True, "weekly_digest": True, "security_alerts": True, "product_updates": False},
        "two_factor_enabled": bool(row.get("two_factor_enabled", False)),
        "plan_type": row.get("plan_type") or "free",
        "subscription_status": row.get("subscription_status") or "active",
        "subscription_expires_at": row.get("subscription_expires_at"),
    }


@router.get("")
async def get_profile(current_user: AuthUser = Depends(get_current_user)):
    return {"user_id": current_user.user_id, "email": current_user.email, "profile": _profile_view(get_user_profile(current_user.user_id))}


@router.patch("")
async def update_profile(payload: ProfileUpdatePayload, current_user: AuthUser = Depends(get_current_user)):
    # exclude_unset preserves true partial-update semantics and still lets the UI
    # clear nullable values by explicitly sending null.
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No profile fields to update")

    for key, value in changes.items():
        if isinstance(value, str):
            changes[key] = value.strip()

    return {"profile": _profile_view(_safe_update(current_user.user_id, changes))}


@router.post("/password")
async def change_password(payload: PasswordPayload, current_user: AuthUser = Depends(get_current_user)):
    try:
        auth_check = supabase.auth.sign_in_with_password({"email": current_user.email, "password": payload.current_password})
        if not auth_check or not auth_check.user:
            raise HTTPException(400, "Current password is incorrect")
        supabase.auth.admin.update_user_by_id(current_user.user_id, {"password": payload.new_password})
        return {"message": "Password updated"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "Current password is incorrect or password update failed") from exc


@router.get("/security")
async def security_status(current_user: AuthUser = Depends(get_current_user)):
    row = get_user_profile(current_user.user_id) or {}
    return {"two_factor_enabled": bool(row.get("two_factor_enabled", False)), "sessions": [{"id": "current", "device": "Current browser", "ip": "Hidden by provider", "last_active": _now(), "current": True}]}


@router.post("/2fa/toggle")
async def toggle_2fa(current_user: AuthUser = Depends(get_current_user)):
    row = get_user_profile(current_user.user_id) or {}
    enabled = not bool(row.get("two_factor_enabled", False))
    return {"two_factor_enabled": enabled, "profile": _profile_view(_safe_update(current_user.user_id, {"two_factor_enabled": enabled}))}


@router.post("/sessions/revoke-others")
async def revoke_other_sessions(current_user: AuthUser = Depends(get_current_user)):
    try:
        result = supabase.auth.admin.sign_out(current_user.user_id, "others")
        if getattr(result, "error", None):
            raise RuntimeError(str(result.error))
    except Exception as exc:
        logger.error("Failed to revoke sessions for %s: %s", current_user.user_id, exc, exc_info=True)
        raise HTTPException(502, "Unable to revoke other sessions") from exc
    return {"message": "Other sessions revoked"}


@router.get("/notifications")
async def get_notifications(current_user: AuthUser = Depends(get_current_user)):
    return {"preferences": _profile_view(get_user_profile(current_user.user_id)).get("notification_preferences")}


@router.put("/notifications")
async def update_notifications(payload: PreferencesPayload, current_user: AuthUser = Depends(get_current_user)):
    return {"preferences": _profile_view(_safe_update(current_user.user_id, {"notification_preferences": payload.model_dump()})).get("notification_preferences")}


@router.get("/billing")
async def billing_summary(current_user: AuthUser = Depends(get_current_user)):
    row = get_user_profile(current_user.user_id) or {}
    plan = row.get("plan_type") or "free"
    used = 0
    try:
        result = supabase.table("usage_logs").select("id", count="exact").eq("user_id", current_user.user_id).execute()
        used = result.count or 0
    except Exception as exc:
        logger.warning("Usage summary unavailable for %s: %s", current_user.user_id, exc)
    return {"plan_type": plan, "subscription_status": row.get("subscription_status") or "active", "subscription_expires_at": row.get("subscription_expires_at"), "usage": {"used": used, "limit": {"free": 1000, "pro": 25000, "premium": 100000}.get(plan, 1000)}, "manage_url": "/upgrade", "invoices_url": "/upgrade#invoices"}


@router.get("/export")
async def export_account(current_user: AuthUser = Depends(get_current_user)):
    return {"exported_at": _now(), "user": {"id": current_user.user_id, "email": current_user.email}, "profile": _profile_view(get_user_profile(current_user.user_id))}


@router.delete("")
async def delete_account(request: Request, confirm: str = "", current_user: AuthUser = Depends(get_current_user)):
    if confirm != "DELETE MY ACCOUNT":
        raise HTTPException(400, "Confirmation phrase required")
    try:
        supabase.auth.admin.delete_user(current_user.user_id)
    except Exception as exc:
        raise HTTPException(500, "Account deletion failed") from exc
    return {"message": "Account deletion requested"}
