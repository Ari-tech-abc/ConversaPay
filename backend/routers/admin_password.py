"""Authenticated admin password rotation endpoint."""
import hashlib
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from supabase import create_client
from backend.config import settings
from backend.routers.admin import require_admin, supabase

router = APIRouter(prefix="/admin", tags=["admin-security"])

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=12, max_length=256)


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
        return secrets.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    admin: dict = Depends(require_admin),
):
    """Change the authenticated admin's password; never accepts an admin id from the client."""
    if payload.current_password == payload.new_password:
        raise HTTPException(400, "New password must be different")
    result = supabase.table("admin_users").select("id,password_hash").eq("id", admin["admin_id"]).maybe_single().execute()
    if not result.data or not _verify_password(payload.current_password, result.data["password_hash"]):
        raise HTTPException(401, "Current password is incorrect")
    supabase.table("admin_users").update({
        "password_hash": _hash_password(payload.new_password),
        "login_attempts": 0,
        "locked_until": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", admin["admin_id"]).execute()
    supabase.table("admin_audit_logs").insert({
        "admin_id": admin["admin_id"],
        "action": "admin_password_changed",
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }).execute()
    return None
