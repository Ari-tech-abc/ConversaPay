"""
Admin management router.
Only for ConversaPay administrators.
Separate authentication from regular users.
"""
from fastapi import APIRouter, HTTPException, status, Depends, Request
from typing import List, Dict, Any, Optional
import logging
from datetime import datetime, timedelta
import secrets
import hashlib
from pydantic import BaseModel

from supabase import create_client, Client
from backend.config import settings
from backend.middleware.auth import AuthUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Supabase client
supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY
)


# ============================================
# Schemas
# ============================================

class AdminLogin(BaseModel):
    """Schema for admin login. ``identifier`` accepts a username OR an email."""
    identifier: str
    password: str


class AdminLoginResponse(BaseModel):
    """Schema for admin login response."""
    access_token: str
    token_type: str
    admin_id: str
    email: str
    role: str


class DomainRestrictionCreate(BaseModel):
    """Schema for creating domain restriction."""
    business_id: str
    domain: str
    max_domains_allowed: int = 1
    monthly_api_calls_limit: int = 100000


class DomainRestrictionUpdate(BaseModel):
    """Schema for updating domain restriction."""
    status: Optional[str] = None
    reason_for_status: Optional[str] = None
    max_domains_allowed: Optional[int] = None
    monthly_api_calls_limit: Optional[int] = None


class DomainRestrictionResponse(BaseModel):
    """Schema for domain restriction response."""
    id: str
    business_id: str
    domain: str
    status: str
    max_domains_allowed: int
    current_domain_count: int
    monthly_api_calls_limit: int
    current_monthly_api_calls: int
    created_at: datetime


class AbuseReportCreate(BaseModel):
    """Schema for creating abuse report."""
    business_id: str
    domain: Optional[str] = None
    report_type: str
    severity: str = "medium"
    description: str
    evidence: Optional[Dict[str, Any]] = None


class AbuseReportResponse(BaseModel):
    """Schema for abuse report response."""
    id: str
    business_id: str
    domain: Optional[str]
    report_type: str
    severity: str
    status: str
    description: str
    created_at: datetime


# ============================================
# Admin Authentication
# ============================================

def hash_password(password: str) -> str:
    """Hash password with salt."""
    salt = secrets.token_hex(32)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${pwd_hash.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    try:
        salt, pwd_hash = password_hash.split('$')
        new_hash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
        return secrets.compare_digest(new_hash.hex(), pwd_hash)
    except Exception:
        return False


def create_admin_token(admin_id: str, email: str) -> str:
    """Create JWT token for admin."""
    import jwt
    payload = {
        'admin_id': admin_id,
        'email': email,
        'type': 'admin',
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


def verify_admin_token(token: str) -> Dict[str, Any]:
    """Verify admin JWT token."""
    import jwt
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        if payload.get('type') != 'admin':
            return None
        return payload
    except Exception:
        return None


async def require_admin(request: Request) -> Dict[str, Any]:
    """Dependency to require admin authentication."""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header"
        )

    token = auth_header.split(' ')[1]
    payload = verify_admin_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return payload


def _find_admin(identifier: str):
    """Look up an admin by username first, then by email. Returns row or None."""
    result = supabase.table("admin_users").select("*").eq("username", identifier).execute()
    if result.data:
        return result.data[0]
    result = supabase.table("admin_users").select("*").eq("email", identifier).execute()
    if result.data:
        return result.data[0]
    return None


# ============================================
# POST /admin/login - Admin Login
# ============================================

@router.post(
    "/login",
    response_model=AdminLoginResponse,
    summary="Admin login",
    description="Authenticate as ConversaPay administrator (username or email)"
)
async def admin_login(
    credentials: AdminLogin,
    request: Request
):
    """
    Admin login endpoint.
    Only for ConversaPay administrators.
    """
    try:
        ident = credentials.identifier.strip()

        admin_user = _find_admin(ident)

        if not admin_user:
            logger.warning(f"Failed login attempt for non-existent admin: {ident}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Check if account is locked
        if admin_user.get("locked_until"):
            locked_until = datetime.fromisoformat(admin_user["locked_until"].replace('Z', '+00:00'))
            if locked_until > datetime.utcnow():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Account is temporarily locked. Try again later."
                )

        # Check if account is active
        if admin_user.get("status") != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is not active"
            )

        # Verify password
        if not verify_password(credentials.password, admin_user["password_hash"]):
            # Increment login attempts
            login_attempts = (admin_user.get("login_attempts") or 0) + 1
            locked_until = None

            if login_attempts >= 5:
                locked_until = (datetime.utcnow() + timedelta(hours=1)).isoformat()

            supabase.table("admin_users")\
                .update({
                    "login_attempts": login_attempts,
                    "locked_until": locked_until
                })\
                .eq("id", admin_user["id"])\
                .execute()

            logger.warning(f"Failed login attempt for admin: {ident}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Reset login attempts and update last login
        supabase.table("admin_users")\
            .update({
                "login_attempts": 0,
                "locked_until": None,
                "last_login": datetime.utcnow().isoformat()
            })\
            .eq("id", admin_user["id"])\
            .execute()

        # Create token
        token = create_admin_token(admin_user["id"], admin_user["email"])

        # Log successful login
        supabase.table("admin_audit_logs")\
            .insert({
                "admin_id": admin_user["id"],
                "action": "admin_login",
                "ip_address": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent")
            })\
            .execute()

        return {
            "access_token": token,
            "token_type": "bearer",
            "admin_id": admin_user["id"],
            "email": admin_user["email"],
            "role": admin_user["role"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during admin login: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


# ============================================
# GET /admin/dashboard - Admin Dashboard Stats
# ============================================

@router.get(
    "/dashboard",
    summary="Admin dashboard statistics",
    description="Get overall statistics for admin dashboard"
)
async def admin_dashboard(
    admin: Dict[str, Any] = Depends(require_admin)
):
    """
    Get admin dashboard statistics.
    """
    try:
        # Get total businesses
        businesses = supabase.table("businesses")\
            .select("id", count="exact")\
            .execute()

        total_businesses = businesses.count if hasattr(businesses, 'count') else len(businesses.data or [])

        # Get flagged domains
        flagged = supabase.table("domain_restrictions")\
            .select("id", count="exact")\
            .eq("status", "flagged")\
            .execute()

        flagged_count = flagged.count if hasattr(flagged, 'count') else len(flagged.data or [])

        # Get open abuse reports
        reports = supabase.table("abuse_reports")\
            .select("id", count="exact")\
            .eq("status", "open")\
            .execute()

        open_reports = reports.count if hasattr(reports, 'count') else len(reports.data or [])

        # Get today's API calls
        today = datetime.utcnow().date().isoformat()
        today_calls = supabase.table("usage_logs")\
            .select("id", count="exact")\
            .gte("created_at", f"{today}T00:00:00")\
            .execute()

        today_api_calls = today_calls.count if hasattr(today_calls, 'count') else len(today_calls.data or [])

        return {
            "total_businesses": total_businesses,
            "flagged_domains": flagged_count,
            "open_abuse_reports": open_reports,
            "today_api_calls": today_api_calls,
            "admin_role": admin.get("role")
        }

    except Exception as e:
        logger.error(f"Error getting admin dashboard: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get dashboard statistics"
        )


# ============================================
# Domain Restrictions Management
# ============================================

@router.post(
    "/domain-restrictions",
    response_model=DomainRestrictionResponse,
    summary="Create domain restriction",
    description="Set domain restrictions for a business"
)
async def create_domain_restriction(
    data: DomainRestrictionCreate,
    admin: Dict[str, Any] = Depends(require_admin),
    request: Request = None
):
    """
    Create domain restriction for a business.
    """
    try:
        # Create restriction
        restriction = supabase.table("domain_restrictions")\
            .insert({
                "business_id": data.business_id,
                "domain": data.domain,
                "max_domains_allowed": data.max_domains_allowed,
                "monthly_api_calls_limit": data.monthly_api_calls_limit,
                "monthly_reset_date": datetime.utcnow().date().isoformat()
            })\
            .execute()

        if not restriction.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create domain restriction"
            )

        # Log action
        supabase.table("admin_audit_logs")\
            .insert({
                "admin_id": admin["admin_id"],
                "action": "domain_restriction_created",
                "resource_type": "domain_restriction",
                "resource_id": restriction.data[0]["id"],
                "business_id": data.business_id,
                "details": {
                    "domain": data.domain,
                    "max_domains": data.max_domains_allowed
                },
                "ip_address": request.client.host if request else None,
                "user_agent": request.headers.get("user-agent") if request else None
            })\
            .execute()

        return restriction.data[0]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating domain restriction: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create domain restriction"
        )


@router.get(
    "/domain-restrictions",
    response_model=List[DomainRestrictionResponse],
    summary="List domain restrictions",
    description="Get all domain restrictions"
)
async def list_domain_restrictions(
    business_id: Optional[str] = None,
    status: Optional[str] = None,
    admin: Dict[str, Any] = Depends(require_admin)
):
    """
    List domain restrictions.
    """
    try:
        query = supabase.table("domain_restrictions").select("*")

        if business_id:
            query = query.eq("business_id", business_id)

        if status:
            query = query.eq("status", status)

        restrictions = query.order("created_at", desc=True).execute()

        return restrictions.data or []

    except Exception as e:
        logger.error(f"Error listing domain restrictions: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list domain restrictions"
        )


@router.put(
    "/domain-restrictions/{restriction_id}",
    response_model=DomainRestrictionResponse,
    summary="Update domain restriction",
    description="Update domain restriction status or limits"
)
async def update_domain_restriction(
    restriction_id: str,
    data: DomainRestrictionUpdate,
    admin: Dict[str, Any] = Depends(require_admin),
    request: Request = None
):
    """
    Update domain restriction.
    """
    try:
        # Get current restriction
        current = supabase.table("domain_restrictions")\
            .select("*")\
            .eq("id", restriction_id)\
            .execute()

        if not current.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain restriction not found"
            )

        # Update restriction
        update_data = {}
        if data.status:
            update_data["status"] = data.status
            if data.status == "blocked":
                update_data["blocked_at"] = datetime.utcnow().isoformat()
                update_data["blocked_by_admin_id"] = admin["admin_id"]

        if data.reason_for_status:
            update_data["reason_for_status"] = data.reason_for_status

        if data.max_domains_allowed:
            update_data["max_domains_allowed"] = data.max_domains_allowed

        if data.monthly_api_calls_limit:
            update_data["monthly_api_calls_limit"] = data.monthly_api_calls_limit

        updated = supabase.table("domain_restrictions")\
            .update(update_data)\
            .eq("id", restriction_id)\
            .execute()

        if not updated.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update domain restriction"
            )

        # Log action
        supabase.table("admin_audit_logs")\
            .insert({
                "admin_id": admin["admin_id"],
                "action": "domain_restriction_updated",
                "resource_type": "domain_restriction",
                "resource_id": restriction_id,
                "business_id": current.data[0]["business_id"],
                "details": update_data,
                "ip_address": request.client.host if request else None,
                "user_agent": request.headers.get("user-agent") if request else None
            })\
            .execute()

        return updated.data[0]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating domain restriction: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update domain restriction"
        )


@router.delete(
    "/domain-restrictions/{restriction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete domain restriction",
    description="Permanently remove a domain restriction"
)
async def delete_domain_restriction(
    restriction_id: str,
    admin: Dict[str, Any] = Depends(require_admin),
    request: Request = None
):
    """
    Delete a domain restriction. Admin-only.
    """
    try:
        current = supabase.table("domain_restrictions")\
            .select("id, business_id, domain")\
            .eq("id", restriction_id)\
            .execute()

        if not current.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Domain restriction not found"
            )

        supabase.table("domain_restrictions")\
            .delete()\
            .eq("id", restriction_id)\
            .execute()

        # Log action
        supabase.table("admin_audit_logs")\
            .insert({
                "admin_id": admin["admin_id"],
                "action": "domain_restriction_deleted",
                "resource_type": "domain_restriction",
                "resource_id": restriction_id,
                "business_id": current.data[0].get("business_id"),
                "details": {"domain": current.data[0].get("domain")},
                "ip_address": request.client.host if request else None,
                "user_agent": request.headers.get("user-agent") if request else None
            })\
            .execute()

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting domain restriction: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete domain restriction"
        )


# ============================================
# Abuse Reports
# ============================================

@router.post(
    "/abuse-reports",
    response_model=AbuseReportResponse,
    summary="Create abuse report",
    description="Report abuse or violations"
)
async def create_abuse_report(
    data: AbuseReportCreate,
    admin: Dict[str, Any] = Depends(require_admin),
    request: Request = None
):
    """
    Create abuse report.
    """
    try:
        report = supabase.table("abuse_reports")\
            .insert({
                "business_id": data.business_id,
                "domain": data.domain,
                "report_type": data.report_type,
                "severity": data.severity,
                "description": data.description,
                "evidence": data.evidence or {},
                "assigned_to_admin_id": admin["admin_id"]
            })\
            .execute()

        if not report.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create abuse report"
            )

        # Log action
        supabase.table("admin_audit_logs")\
            .insert({
                "admin_id": admin["admin_id"],
                "action": "abuse_report_created",
                "resource_type": "abuse_report",
                "resource_id": report.data[0]["id"],
                "business_id": data.business_id,
                "details": {
                    "report_type": data.report_type,
                    "severity": data.severity
                },
                "ip_address": request.client.host if request else None,
                "user_agent": request.headers.get("user-agent") if request else None
            })\
            .execute()

        return report.data[0]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating abuse report: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create abuse report"
        )


@router.get(
    "/abuse-reports",
    response_model=List[AbuseReportResponse],
    summary="List abuse reports",
    description="Get all abuse reports"
)
async def list_abuse_reports(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    admin: Dict[str, Any] = Depends(require_admin)
):
    """
    List abuse reports.
    """
    try:
        query = supabase.table("abuse_reports").select("*")

        if status:
            query = query.eq("status", status)

        if severity:
            query = query.eq("severity", severity)

        reports = query.order("created_at", desc=True).execute()

        return reports.data or []

    except Exception as e:
        logger.error(f"Error listing abuse reports: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list abuse reports"
        )
