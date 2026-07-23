"""Admin authentication and protected management endpoints."""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import hashlib, secrets
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from supabase import create_client
from backend.config import settings

router = APIRouter(prefix="/admin", tags=["admin"])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

class AdminLogin(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=256)
class AdminLoginResponse(BaseModel):
    access_token: str; token_type: str; admin_id: str; email: str; role: str
class DomainRestrictionCreate(BaseModel):
    business_id: str; domain: str; max_domains_allowed: int = Field(1, ge=1); monthly_api_calls_limit: int = Field(100000, ge=0)
class DomainRestrictionUpdate(BaseModel):
    status: Optional[str] = None; reason_for_status: Optional[str] = None; max_domains_allowed: Optional[int] = Field(None, ge=1); monthly_api_calls_limit: Optional[int] = Field(None, ge=0)
class AbuseReportCreate(BaseModel):
    business_id: str; domain: Optional[str] = None; report_type: str; severity: str = "medium"; description: str; evidence: Optional[Dict[str, Any]] = None


def hash_password(password: str) -> str:
    salt = secrets.token_hex(32); digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"{salt}${digest.hex()}"
def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1); candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
        return secrets.compare_digest(candidate, digest)
    except (ValueError, TypeError): return False
def create_admin_token(admin_id: str, email: str) -> str:
    import jwt
    return jwt.encode({"admin_id": admin_id, "email": email, "type": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=24)}, settings.SECRET_KEY, algorithm="HS256")
def verify_admin_token(token: str):
    import jwt
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload if payload.get("type") == "admin" else None
    except Exception: return None
async def require_admin(request: Request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "): raise HTTPException(401, "Missing or invalid authorization header")
    payload = verify_admin_token(header.split(" ", 1)[1])
    if not payload: raise HTTPException(401, "Invalid or expired token")
    return payload

def _find_admin(identifier: str):
    result = supabase.table("admin_users").select("*").eq("username", identifier).execute()
    if result.data: return result.data[0]
    result = supabase.table("admin_users").select("*").eq("email", identifier).execute()
    return result.data[0] if result.data else None
def _audit(admin_id, action, request, resource_type=None, resource_id=None, business_id=None, details=None):
    supabase.table("admin_audit_logs").insert({"admin_id": admin_id, "action": action, "resource_type": resource_type, "resource_id": resource_id, "business_id": business_id, "details": details or {}, "ip_address": request.client.host if request.client else None, "user_agent": request.headers.get("user-agent")}).execute()

@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(credentials: AdminLogin, request: Request):
    admin = _find_admin(credentials.identifier.strip())
    if not admin: raise HTTPException(401, "Invalid credentials")
    if admin.get("locked_until"):
        locked = datetime.fromisoformat(str(admin["locked_until"]).replace("Z", "+00:00")); locked = locked if locked.tzinfo else locked.replace(tzinfo=timezone.utc)
        if locked > datetime.now(timezone.utc): raise HTTPException(429, "Account is temporarily locked")
    if admin.get("status") != "active": raise HTTPException(403, "Account is not active")
    if not verify_password(credentials.password, admin["password_hash"]):
        attempts = (admin.get("login_attempts") or 0) + 1; lock = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat() if attempts >= 5 else None
        supabase.table("admin_users").update({"login_attempts": attempts, "locked_until": lock}).eq("id", admin["id"]).execute()
        raise HTTPException(401, "Invalid credentials")
    supabase.table("admin_users").update({"login_attempts": 0, "locked_until": None, "last_login": datetime.now(timezone.utc).isoformat()}).eq("id", admin["id"]).execute()
    token = create_admin_token(admin["id"], admin["email"]); _audit(admin["id"], "admin_login", request)
    return {"access_token": token, "token_type": "bearer", "admin_id": admin["id"], "email": admin["email"], "role": admin["role"]}

@router.get("/dashboard")
async def admin_dashboard(admin: dict = Depends(require_admin)):
    def count(table, column=None, value=None):
        q = supabase.table(table).select("id", count="exact")
        if column: q = q.eq(column, value)
        r = q.execute(); return r.count if r.count is not None else len(r.data or [])
    return {"total_businesses": count("businesses"), "flagged_domains": count("domain_restrictions", "status", "flagged"), "open_abuse_reports": count("abuse_reports", "status", "open"), "today_api_calls": count("usage_logs"), "admin_role": admin.get("role")}

@router.get("/domain-restrictions")
async def list_domain_restrictions(business_id: Optional[str] = None, status: Optional[str] = None, admin: dict = Depends(require_admin)):
    q = supabase.table("domain_restrictions").select("*")
    if business_id: q = q.eq("business_id", business_id)
    if status: q = q.eq("status", status)
    r = q.order("created_at", desc=True).execute(); return r.data or []
@router.post("/domain-restrictions")
async def create_domain_restriction(data: DomainRestrictionCreate, request: Request, admin: dict = Depends(require_admin)):
    r = supabase.table("domain_restrictions").insert({**data.model_dump(), "monthly_reset_date": datetime.now(timezone.utc).date().isoformat()}).execute()
    if not r.data: raise HTTPException(500, "Failed to create domain restriction")
    _audit(admin["admin_id"], "domain_restriction_created", request, "domain_restriction", r.data[0]["id"], data.business_id, {"domain": data.domain}); return r.data[0]
@router.put("/domain-restrictions/{restriction_id}")
async def update_domain_restriction(restriction_id: str, data: DomainRestrictionUpdate, request: Request, admin: dict = Depends(require_admin)):
    current = supabase.table("domain_restrictions").select("*").eq("id", restriction_id).execute()
    if not current.data: raise HTTPException(404, "Domain restriction not found")
    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if updates.get("status") == "blocked": updates.update({"blocked_at": datetime.now(timezone.utc).isoformat(), "blocked_by_admin_id": admin["admin_id"]})
    r = supabase.table("domain_restrictions").update(updates).eq("id", restriction_id).execute()
    _audit(admin["admin_id"], "domain_restriction_updated", request, "domain_restriction", restriction_id, current.data[0]["business_id"], updates); return r.data[0]
@router.delete("/domain-restrictions/{restriction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_domain_restriction(restriction_id: str, request: Request, admin: dict = Depends(require_admin)):
    current = supabase.table("domain_restrictions").select("id,business_id,domain").eq("id", restriction_id).execute()
    if not current.data: raise HTTPException(404, "Domain restriction not found")
    row = current.data[0]; supabase.table("domain_restrictions").delete().eq("id", restriction_id).execute(); _audit(admin["admin_id"], "domain_restriction_deleted", request, "domain_restriction", restriction_id, row.get("business_id"), {"domain": row.get("domain")})

@router.get("/abuse-reports")
async def list_abuse_reports(status: Optional[str] = None, severity: Optional[str] = None, admin: dict = Depends(require_admin)):
    q = supabase.table("abuse_reports").select("*")
    if status: q = q.eq("status", status)
    if severity: q = q.eq("severity", severity)
    r = q.order("created_at", desc=True).execute(); return r.data or []
@router.post("/abuse-reports")
async def create_abuse_report(data: AbuseReportCreate, request: Request, admin: dict = Depends(require_admin)):
    r = supabase.table("abuse_reports").insert({**data.model_dump(exclude_none=True), "evidence": data.evidence or {}, "assigned_to_admin_id": admin["admin_id"]}).execute()
    if not r.data: raise HTTPException(500, "Failed to create abuse report")
    _audit(admin["admin_id"], "abuse_report_created", request, "abuse_report", r.data[0]["id"], data.business_id); return r.data[0]
