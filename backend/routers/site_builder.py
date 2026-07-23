"""One-time access tokens for the Premium site builder."""
import hashlib, secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from supabase import create_client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth

router = APIRouter(prefix="/site-builder", tags=["site-builder"])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _expiry(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

@router.post("/access")
async def create_builder_access(current_user: AuthUser = Depends(require_auth)):
    profile = supabase.table("profiles").select("plan_type").eq("user_id", current_user.user_id).maybe_single().execute()
    if (profile.data or {}).get("plan_type") != "premium":
        raise HTTPException(403, "The site builder is available only on PREMIUM")
    raw = secrets.token_urlsafe(36)
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    result = supabase.table("site_builder_tokens").insert({"user_id": current_user.user_id, "token_hash": _hash(raw), "expires_at": expires.isoformat(), "used_at": None}).execute()
    if not result.data:
        raise HTTPException(500, "Could not create builder access")
    return {"token": raw, "expires_at": expires.isoformat(), "url": f"/site-builder?token={raw}"}

@router.get("/verify/{token}")
async def verify_builder_access(token: str):
    result = supabase.table("site_builder_tokens").select("id,user_id,expires_at,used_at").eq("token_hash", _hash(token)).maybe_single().execute()
    if not result.data or result.data.get("used_at"):
        raise HTTPException(401, "Invalid or already used builder token")
    if _expiry(result.data["expires_at"]) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Builder token expired")
    profile = supabase.table("profiles").select("plan_type").eq("user_id", result.data["user_id"]).maybe_single().execute()
    if (profile.data or {}).get("plan_type") != "premium":
        raise HTTPException(403, "The site builder is available only on PREMIUM")
    return {"valid": True, "user_id": result.data["user_id"]}

@router.post("/consume/{token}")
async def consume_builder_access(token: str):
    token_hash = _hash(token)
    now = datetime.now(timezone.utc).isoformat()
    result = supabase.table("site_builder_tokens").update({"used_at": now}).eq("token_hash", token_hash).is_("used_at", "null").execute()
    if not result.data:
        raise HTTPException(401, "Invalid, expired, or already used builder token")
    row = result.data[0]
    if _expiry(row["expires_at"]) <= datetime.now(timezone.utc):
        supabase.table("site_builder_tokens").update({"used_at": None}).eq("id", row["id"]).execute()
        raise HTTPException(401, "Builder token expired")
    profile = supabase.table("profiles").select("plan_type").eq("user_id", row["user_id"]).maybe_single().execute()
    if (profile.data or {}).get("plan_type") != "premium":
        raise HTTPException(403, "The site builder is available only on PREMIUM")
    return {"valid": True, "user_id": row["user_id"]}
