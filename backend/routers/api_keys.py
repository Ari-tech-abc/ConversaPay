"""Tier-aware widget API key management.

FREE: no widget keys. PRO: up to 3 active keys. PREMIUM: up to 10.
Secrets are returned only once and only keyed HMAC hashes are stored.

Security note: keys are hashed with HMAC-SHA256 using the server SECRET_KEY
(a keyed hash), which defeats offline rainbow-table attacks against a leaked
database. The stored display prefix keeps only a short, non-sensitive slice.
"""
import hashlib, hmac, secrets
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth

router = APIRouter(prefix="/api-keys", tags=["api-keys"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

class KeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    business_id: str


def _plan(user_id: str) -> str:
    result = supabase.table("profiles").select("plan_type").eq("user_id", user_id).maybe_single().execute()
    return (result.data or {}).get("plan_type", "free")


def _limit(plan: str) -> int:
    return {"free": 0, "pro": 3, "premium": 10}.get(plan, 0)


def _hash(value: str) -> str:
    """Keyed HMAC-SHA256 hash. Must match backend/routers/widget.py."""
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def _owned_business(business_id: str, user_id: str) -> bool:
    result = supabase.table("businesses").select("id").eq("id", business_id).eq("owner_id", user_id).maybe_single().execute()
    return bool(result.data)

@router.get("")
async def list_keys(business_id: str, current_user: AuthUser = Depends(require_auth)) -> Dict[str, Any]:
    if not _owned_business(business_id, current_user.user_id):
        raise HTTPException(404, "Business not found")
    plan = _plan(current_user.user_id)
    result = supabase.table("api_keys").select("id,business_id,name,key_prefix,permissions,expires_at,is_active,last_used_at,created_at").eq("business_id", business_id).eq("is_active", True).order("created_at", desc=True).execute()
    return {"plan_type": plan, "limit": _limit(plan), "keys": result.data or []}

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_key(payload: KeyCreate, current_user: AuthUser = Depends(require_auth)) -> Dict[str, Any]:
    if not _owned_business(payload.business_id, current_user.user_id):
        raise HTTPException(404, "Business not found")
    plan = _plan(current_user.user_id)
    limit = _limit(plan)
    if not limit:
        raise HTTPException(403, "Widget API keys are available in PRO and PREMIUM")
    existing = supabase.table("api_keys").select("id", count="exact").eq("business_id", payload.business_id).eq("is_active", True).execute()
    count = existing.count if existing.count is not None else len(existing.data or [])
    if count >= limit:
        raise HTTPException(409, f"Your {plan.upper()} plan allows up to {limit} active widget keys")
    raw = "cp_live_" + secrets.token_urlsafe(32)
    # Display prefix keeps only the non-secret scheme tag + 4 chars for identification.
    record = {"business_id": payload.business_id, "name": payload.name, "key_prefix": raw[:12], "key_hash": _hash(raw), "permissions": ["widget"], "is_active": True}
    created = supabase.table("api_keys").insert(record).execute()
    if not created.data:
        raise HTTPException(500, "Failed to create API key")
    return {"key": raw, "key_info": {k: created.data[0].get(k) for k in ("id", "business_id", "name", "key_prefix", "permissions", "is_active", "created_at")}, "warning": "Copy this key now. It will not be shown again."}

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(key_id: str, current_user: AuthUser = Depends(require_auth)):
    owned = supabase.table("api_keys").select("id,business_id").eq("id", key_id).maybe_single().execute()
    if not owned.data or not _owned_business(owned.data["business_id"], current_user.user_id):
        raise HTTPException(404, "API key not found")
    supabase.table("api_keys").update({"is_active": False}).eq("id", key_id).execute()
    return None
