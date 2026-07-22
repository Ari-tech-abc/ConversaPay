"""One-time access tokens for the Premium site builder."""
import hashlib, secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth

router = APIRouter(prefix="/site-builder", tags=["site-builder"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

@router.post("/access")
async def create_builder_access(current_user: AuthUser = Depends(require_auth)):
    profile = supabase.table("profiles").select("plan_type").eq("user_id", current_user.user_id).maybe_single().execute()
    if (profile.data or {}).get("plan_type") != "premium":
        raise HTTPException(403, "The site builder is available only on PREMIUM")
    raw = secrets.token_urlsafe(36)
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    supabase.table("site_builder_tokens").insert({"user_id": current_user.user_id, "token_hash": hashlib.sha256(raw.encode()).hexdigest(), "expires_at": expires.isoformat(), "used_at": None}).execute()
    return {"token": raw, "expires_at": expires.isoformat(), "url": f"/site-builder?token={raw}"}

@router.get("/verify/{token}")
async def verify_builder_access(token: str):
    result = supabase.table("site_builder_tokens").select("id,user_id,expires_at,used_at").eq("token_hash", hashlib.sha256(token.encode()).hexdigest()).maybe_single().execute()
    if not result.data or result.data.get("used_at"):
        raise HTTPException(401, "Invalid or already used builder token")
    expires = datetime.fromisoformat(str(result.data["expires_at"]).replace("Z", "+00:00"))
    if expires < datetime.now(timezone.utc):
        raise HTTPException(401, "Builder token expired")
    profile = supabase.table("profiles").select("plan_type").eq("user_id", result.data["user_id"]).maybe_single().execute()
    if (profile.data or {}).get("plan_type") != "premium":
        raise HTTPException(403, "The site builder is available only on PREMIUM")
    return {"valid": True, "user_id": result.data["user_id"]}

@router.post("/consume/{token}")
async def consume_builder_access(token: str):
    valid = await verify_builder_access(token)
    supabase.table("site_builder_tokens").update({"used_at": datetime.now(timezone.utc).isoformat()}).eq("token_hash", hashlib.sha256(token.encode()).hexdigest()).execute()
    return {"valid": True, "user_id": valid["user_id"]}
