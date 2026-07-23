"""Authentication and authorization helpers for Supabase-backed users."""
from datetime import datetime, timezone
from typing import Optional
import logging
from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from backend.config import settings
logger=logging.getLogger(__name__); security=HTTPBearer()
supabase_client:Client=create_client(settings.SUPABASE_URL,settings.SUPABASE_ANON_KEY); supabase_service:Client=create_client(settings.SUPABASE_URL,settings.SUPABASE_SERVICE_ROLE_KEY)
class AuthUser:
    def __init__(self,user_id:str,email:str): self.user_id,self.email=user_id,email
    def __repr__(self): return f"AuthUser(user_id={self.user_id}, email={self.email})"
async def get_current_user(request:Request,credentials:HTTPAuthorizationCredentials=Depends(security))->AuthUser:
    try:
        response=supabase_service.auth.get_user(credentials.credentials)
        if not response or not response.user: raise HTTPException(401,"Invalid token")
        return AuthUser(response.user.id,response.user.email or "")
    except HTTPException: raise
    except Exception as exc: logger.warning("JWT validation error: %s",exc); raise HTTPException(401,"Could not validate credentials")
async def get_current_user_optional(request:Request)->Optional[AuthUser]:
    auth=request.headers.get("Authorization","")
    if not auth.startswith("Bearer "): return None
    try:
        response=supabase_client.auth.get_user(auth.split(" ",1)[1]); return AuthUser(response.user.id,response.user.email or "") if response and response.user else None
    except Exception: return None
def require_auth(user:AuthUser=Depends(get_current_user))->AuthUser: return user
class RoleChecker:
    def __init__(self,allowed_roles:list[str]): self.allowed_roles=allowed_roles
    def __call__(self,user:AuthUser=Depends(get_current_user))->AuthUser:
        try:
            profile=supabase_service.table("profiles").select("role").eq("user_id",user.user_id).execute()
            if not profile.data or profile.data[0].get("role","user") not in self.allowed_roles: raise HTTPException(403,"Insufficient permissions")
            return user
        except HTTPException: raise
        except Exception as exc: logger.error("Role check error: %s",exc,exc_info=True); raise HTTPException(500,"Failed to verify role")
def active_plan(row:dict)->str:
    plan=str(row.get("plan_type") or "free").strip().lower(); plan={"professional":"pro","pro_monthly":"pro","premium_monthly":"premium","paid":"pro"}.get(plan,plan)
    if plan not in {"free","pro","premium"}: return "free"
    if plan!="free" and row.get("subscription_expires_at"):
        try:
            exp=datetime.fromisoformat(str(row["subscription_expires_at"]).replace("Z","+00:00")); exp=exp if exp.tzinfo else exp.replace(tzinfo=timezone.utc)
            if exp<=datetime.now(timezone.utc): return "free"
        except ValueError: return "free"
    return plan
def is_pro_user(user_id:str)->bool:
    try:
        result=supabase_service.table("profiles").select("plan_type,subscription_expires_at").eq("user_id",user_id).maybe_single().execute(); return active_plan(result.data or {}) in {"pro","premium"}
    except Exception as exc: logger.error("Plan check error: %s",exc); return False
def require_business_owner_for_business_id(business_id:str,current_user:AuthUser)->str:
    result=supabase_service.table("businesses").select("id").eq("id",business_id).eq("owner_id",current_user.user_id).execute()
    if not result.data: raise HTTPException(403,"Unauthorized access to this business resources")
    return str(result.data[0]["id"])
require_admin=RoleChecker(["admin","super_admin"]); require_business_owner=RoleChecker(["admin","super_admin","business_owner"])
