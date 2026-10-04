"""Authenticated SaaS profile, security, preferences, billing and privacy APIs."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from supabase import create_client
from backend.config import settings
from backend.dependencies import create_auth_client
from backend.services.billing_reconciliation import active_plan_from_row
from backend.middleware.auth import AuthUser, get_current_user
from backend.routers.auth import get_user_profile

logger = logging.getLogger(__name__)
router = APIRouter(tags=["profile"])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
PROFILE_UPDATE_FIELDS = frozenset({"full_name", "company_name", "phone", "timezone", "avatar_url"})

class ProfileUpdatePayload(BaseModel):
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

def _now(): return datetime.now(timezone.utc).isoformat()

def _settings_profile(user_id: str) -> dict:
    # Unlike the legacy helper, a storage failure must not become a free plan.
    try:
        result = supabase.table("profiles").select("*").eq("user_id", user_id).limit(1).execute()
    except Exception as exc:
        logger.exception("Settings profile load failed for %s", user_id)
        raise HTTPException(503, {"code": "settings_unavailable", "message": "Account settings are temporarily unavailable."}) from exc
    if not result.data:
        raise HTTPException(404, {"code": "profile_not_found", "message": "Account profile was not found."})
    return result.data[0]

def _profile_update_error(user_id: str, exc: Exception) -> None:
    error_code = str(getattr(exc, "code", "") or "").upper()
    error_message = str(getattr(exc, "message", "") or exc)
    normalized = error_message.lower()
    schema_error = error_code == "PGRST204" or "schema cache" in normalized or "could not find column" in normalized or ("column" in normalized and "does not exist" in normalized)
    logger.error("Profile update failed for %s (%s): %s", user_id, error_code or "database_error", error_message, exc_info=True)
    if schema_error:
        raise HTTPException(503, {"code":"profile_schema_unavailable", "message":"Profile storage is missing a required field. Apply the latest profile schema migration."}) from exc
    raise HTTPException(502, {"code":"profile_update_failed", "message":"The profile could not be saved right now."}) from exc

def _safe_update(user_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    try:
        result = supabase.table("profiles").update(changes).eq("user_id", user_id).execute()
    except Exception as exc:
        _profile_update_error(user_id, exc)
    if getattr(result, "data", None): return result.data[0]
    profile = get_user_profile(user_id)
    if profile is not None: return profile
    raise HTTPException(404, {"code":"profile_not_found", "message":"Profile not found."})

def _profile_view(row: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    end_date = row.get("subscription_end_date") or row.get("subscription_expires_at")
    return {
        "full_name": row.get("full_name") or "", "company_name": row.get("company_name") or "", "phone": row.get("phone") or "", "timezone": row.get("timezone") or "UTC", "avatar_url": row.get("avatar_url") or "", "notification_preferences": row.get("notification_preferences") or {"payment_success": True, "weekly_digest": True, "security_alerts": True, "product_updates": False}, "two_factor_enabled": False, "two_factor_available": False, "plan_type": row.get("plan_type") or "free", "subscription_status": row.get("subscription_status") or "active", "subscription_start_date": row.get("subscription_start_date"), "subscription_end_date": end_date, "subscription_expires_at": end_date, "auto_renew": bool(row.get("auto_renew", True)), "stripe_subscription_id": row.get("stripe_subscription_id"), "subscription_remaining_days": _remaining_days(end_date), "subscription_active": str(row.get("plan_type") or "free").lower() == "free" or active_plan_from_row(row) != "free", "subscription_expires_at": end_date,
    }

def _remaining_days(value: Any) -> int:
    try:
        end = datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
        if end and end.tzinfo is None: end = end.replace(tzinfo=timezone.utc)
        return max(0, (end.date() - datetime.now(timezone.utc).date()).days) if end else 0
    except (TypeError, ValueError): return 0

def _subscription_active(plan: Any, end_date: Any) -> bool:
    return str(plan or "free").lower() == "free" or _remaining_days(end_date) > 0

@router.get("")
async def get_profile(current_user: AuthUser = Depends(get_current_user)):
    return {"user_id": current_user.user_id, "email": current_user.email, "profile": _profile_view(get_user_profile(current_user.user_id))}

@router.patch("")
async def update_profile(payload: ProfileUpdatePayload, current_user: AuthUser = Depends(get_current_user)):
    changes = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if key in PROFILE_UPDATE_FIELDS}
    if not changes: raise HTTPException(400, {"code":"no_profile_fields", "message":"Provide at least one profile field to update."})
    changes = {key: value.strip() if isinstance(value, str) else value for key, value in changes.items()}
    if "timezone" in changes and not changes["timezone"]: changes["timezone"] = "UTC"
    return {"profile": _profile_view(_safe_update(current_user.user_id, changes))}

@router.post("/password")
async def change_password(payload: PasswordPayload, current_user: AuthUser = Depends(get_current_user)):
    try:
        auth_check = create_auth_client().auth.sign_in_with_password({"email": current_user.email, "password": payload.current_password})
        if not auth_check or not auth_check.user: raise HTTPException(400, "Current password is incorrect")
        supabase.auth.admin.update_user_by_id(current_user.user_id, {"password": payload.new_password})
        return {"message":"Password updated"}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(400, "Current password is incorrect or password update failed") from exc

@router.get("/security")
async def security_status(current_user: AuthUser = Depends(get_current_user)):
    return {"two_factor_enabled": False, "two_factor_available": False, "sessions_available": False, "sessions":[{"id":"current","device":"Current browser","ip":"Hidden by provider","last_active":_now(),"current":True}]}

@router.post("/2fa/toggle")
async def toggle_2fa(current_user: AuthUser = Depends(get_current_user)):
    raise HTTPException(503, {"code":"mfa_unavailable", "message":"Two-factor authentication is not available yet."})


@router.post("/sessions/revoke-others")
async def revoke_other_sessions(request: Request, current_user: AuthUser = Depends(get_current_user)):
    try:
        result = supabase.auth.admin.sign_out(request.headers["Authorization"].split(" ", 1)[1], "others")
        if getattr(result, "error", None): raise RuntimeError(str(result.error))
    except Exception as exc:
        logger.error("Failed to revoke sessions for %s: %s", current_user.user_id, exc, exc_info=True); raise HTTPException(502,"Unable to revoke other sessions") from exc
    from backend.services.notification_service import enqueue_security_event
    enqueue_security_event(supabase, current_user.user_id, "sessions_revoked")
    return {"message":"Other sessions revoked"}

@router.get("/notifications")
async def get_notifications(current_user: AuthUser = Depends(get_current_user)):
    row = _settings_profile(current_user.user_id)
    preferences = {"payment_success": True, "weekly_digest": True, "security_alerts": True, "product_updates": False}
    preferences.update({key: value for key, value in (row.get("notification_preferences") or {}).items() if key in preferences and isinstance(value, bool)})
    from backend.services.notification_service import delivery_status
    return {"preferences": preferences, "delivery": delivery_status()}

@router.put("/notifications")
async def update_notifications(payload: PreferencesPayload, current_user: AuthUser = Depends(get_current_user)):
    return {"preferences":_profile_view(_safe_update(current_user.user_id,{"notification_preferences":payload.model_dump()})).get("notification_preferences")}

@router.get("/billing")
async def billing_summary(current_user: AuthUser = Depends(get_current_user)):
    row = _settings_profile(current_user.user_id); plan = active_plan_from_row(row); activity = None
    period_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start.replace(year=period_start.year+1, month=1) if period_start.month == 12 else period_start.replace(month=period_start.month+1)
    try:
        activity = supabase.rpc("account_activity", {"p_user_id": current_user.user_id, "p_start": period_start.isoformat(), "p_end": period_end.isoformat()}).execute().data
    except Exception as exc: logger.warning("Usage summary unavailable for %s: %s", current_user.user_id, exc)
    view = _profile_view(row)
    from backend.middleware.rate_limiter import free_dashboard_chat_limiter
    preview_limit = 5 if plan == "free" else None
    return {"plan_type":plan, "subscription_status":view["subscription_status"], "subscription_start_date":view["subscription_start_date"], "subscription_end_date":view["subscription_end_date"], "auto_renew":view["auto_renew"], "remaining_days":view["subscription_remaining_days"], "subscription_expires_at":view["subscription_expires_at"],
        "usage":{"used":activity.get("messages") if isinstance(activity, dict) else None,"available":isinstance(activity, dict),"period_start":period_start.isoformat(),"period_end":period_end.isoformat(),"limit":None,"metric":"customer_messages","activity":activity},
        "preview":{"limit":preview_limit,"remaining":free_dashboard_chat_limiter.remaining(str(current_user.user_id)) if preview_limit else None,"window_seconds":3600},
        "manage_url":"/upgrade","invoices_url":"/upgrade#invoices"}

@router.get("/export")
async def export_account(current_user: AuthUser = Depends(get_current_user)):
    return {"exported_at":_now(),"user":{"id":current_user.user_id,"email":current_user.email},"profile":_profile_view(get_user_profile(current_user.user_id))}

@router.delete("")
async def delete_account(request: Request, confirm: str = "", current_user: AuthUser = Depends(get_current_user)):
    if confirm != "DELETE MY ACCOUNT": raise HTTPException(400,"Confirmation phrase required")
    try: supabase.auth.admin.delete_user(current_user.user_id)
    except Exception as exc: raise HTTPException(500,"Account deletion failed") from exc
    return {"message":"Account deletion requested"}
