"""Safe authenticated profile responses with an explicit allow-list."""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from backend.middleware.auth import AuthUser, get_current_user
from backend.routers.auth import get_user_profile

router = APIRouter(prefix="/auth", tags=["authentication"])


class SafeProfileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str
    full_name: Optional[str] = None
    plan_type: str = "free"
    email_verified: bool = False
    subscription_status: Optional[str] = None
    subscription_expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SafeMeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    email: str
    profile: Optional[SafeProfileResponse] = None


@router.get("/me", response_model=SafeMeResponse)
async def safe_current_user_info(current_user: AuthUser = Depends(get_current_user)) -> SafeMeResponse:
    raw = get_user_profile(current_user.user_id) or {}
    allowed = {
        "email", "full_name", "plan_type", "email_verified", "subscription_status",
        "subscription_expires_at", "created_at", "updated_at",
    }
    profile = SafeProfileResponse.model_validate({key: raw[key] for key in allowed if key in raw}) if raw else None
    return SafeMeResponse(user_id=current_user.user_id, email=current_user.email, profile=profile)
