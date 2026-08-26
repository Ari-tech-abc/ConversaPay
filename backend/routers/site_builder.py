"""Premium site builder access, persistence and tenant-scoped lead APIs."""
from __future__ import annotations
import hashlib, json, logging, re, secrets
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from google import genai
from pydantic import BaseModel, Field, field_validator
from supabase import Client, create_client
from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth
from backend.middleware.tenant_guard import verify_resource_owner, verify_tenant_ownership
try:
    from google.genai import errors as genai_errors
except ImportError:
    genai_errors = None
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/site-builder", tags=["site-builder"])
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
MODEL_NAME = "gemini-2.5-flash"
client = genai.Client(api_key=settings.GEMINI_API_KEY) if settings.GEMINI_API_KEY else None

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=1000)
    business_name: str = Field(..., min_length=2, max_length=100)
    industry: str = Field(..., min_length=2, max_length=50)
    business_id: Optional[str] = Field(None, min_length=8, max_length=64)
    vibe: str = Field("modern", pattern="^(minimalist|cyber|luxury|playful|modern)$")
    sections: List[str] = Field(default_factory=lambda: ["hero", "features", "stats", "products", "faq", "contact"])

    @field_validator("sections")
    @classmethod
    def validate_sections(cls, v: List[str]) -> List[str]:
        allowed = {"hero", "features", "stats", "products", "faq", "contact"}
        for item in v:
            if item not in allowed:
                raise ValueError(f"Invalid section: {item!r}")
        return v

    @field_validator("business_name", "industry", "prompt")
    @classmethod
    def no_html_tags(cls, v: str) -> str:
        if re.search(r"[<>]", v):
            raise ValueError("Field must not contain HTML characters")
        return v
class SaveRequest(BaseModel):
    project_name: str = Field("ConversaPay site", min_length=2, max_length=120)
    html: str = Field(..., min_length=200, max_length=500_000)
class LeadSubmission(BaseModel):
    business_id: str = Field(..., min_length=8, max_length=64)
    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=320)
    message: str = Field(..., min_length=2, max_length=4000)
    company: Optional[str] = Field(None, max_length=160)
    source: str = Field("site-builder", min_length=2, max_length=80)
    page_url: Optional[str] = Field(None, max_length=2048)
    website: Optional[str] = Field(None, max_length=200)
class LeadStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(new|contacted|qualified|converted|archived)$")
class GenerateResponse(BaseModel):
    success: bool
    config: Optional[Dict[str, Any]] = None
    html: Optional[str] = None
    error: Optional[str] = None
    fallback: bool = False

def _hash(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()
def _expiry(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")); return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
def _ensure_premium(user_id: str) -> None:
    profile = supabase.table("profiles").select("plan_type").eq("user_id", user_id).maybe_single().execute()
    if (profile.data or {}).get("plan_type") != "premium": raise HTTPException(403, "The site builder is available only on PREMIUM")
def _get_business_for_user(user_id: str, business_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query = supabase.table("businesses").select("id,business_name,is_active,settings,owner_id").eq("owner_id", user_id)
    if business_id: query = query.eq("id", business_id)
    result = query.limit(1).execute(); return (result.data or [None])[0]
def _get_token_record(token: str, user_id: str | None = None) -> Dict[str, Any]:
    result = supabase.table("site_builder_tokens").select("id,user_id,expires_at,used_at").eq("token_hash", _hash(token)).maybe_single().execute(); record = result.data or {}
    if not record: raise HTTPException(401, "Invalid builder token")
    if user_id and record.get("user_id") != user_id: raise HTTPException(404, "Resource not found")
    if record.get("used_at"): raise HTTPException(401, "Builder token already used")
    try:
        if _expiry(record["expires_at"]) <= datetime.now(timezone.utc): raise HTTPException(401, "Builder token expired")
    except (KeyError, TypeError, ValueError) as exc: raise HTTPException(401, "Invalid builder token") from exc
    _ensure_premium(record["user_id"]); return record
def _mark_token_used(token_id: str) -> None:
    result = supabase.table("site_builder_tokens").update({"used_at": datetime.now(timezone.utc).isoformat()}).eq("id", token_id).is_("used_at", "null").execute()
    if not result.data: raise HTTPException(409, "Builder token already used")
def _origin_allowed(origin: Optional[str], business: Dict[str, Any]) -> bool:
    if not origin: return False
    parsed = urlparse(origin.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname: return False
    normalized = f"{parsed.scheme}://{parsed.hostname.lower().rstrip('.')}{f':{parsed.port}' if parsed.port else ''}"
    configured = {str(item).rstrip('/') for item in settings.cors_origins_list}
    custom = ((business.get("settings") or {}).get("custom_domains") or [])
    return normalized in configured or normalized in {str(item).rstrip('/') if "://" in str(item) else f"https://{str(item).rstrip('/')}" for item in custom}
def _rate_limit_key(business_id: str, ip_address: str) -> str: return hashlib.sha256(f"{settings.SECRET_KEY}:site-lead:{business_id}:{ip_address}".encode()).hexdigest()
def _consume_rate_limit(business_id: str, ip_address: str) -> None:
    result = supabase.rpc("consume_site_lead_rate_limit", {"p_key": _rate_limit_key(business_id, ip_address), "p_limit": 5, "p_window_seconds": 3600}).execute()
    raw = result.data[0] if isinstance(result.data, list) and result.data else result.data
    if raw is not True and str(raw).lower() != "true": raise HTTPException(429, "Too many leads", headers={"Retry-After": "3600"})

def _clean_json(text: str) -> str:
    cleaned = re.sub(r"```(?:json)?", "", text or "", flags=re.I).strip(); match = re.search(r"\{.*\}", cleaned, re.S); return match.group(0) if match else cleaned
def _fallback_config(request: GenerateRequest) -> Dict[str, Any]: return {"hero": {"badge": request.business_name, "headline": request.business_name, "subheadline": request.industry, "primaryCTA": {"text": "Contact", "link": "#contact"}}, "features": [], "proofStats": [], "products": [], "faq": [], "contact": {"title": "Contact", "description": "Leave details"}, "theme": {"primaryColor": "#635bff"}, "seo": {"title": request.business_name}}
def _build_prompt(request: GenerateRequest) -> str: return f"Create JSON only for {request.business_name} in {request.industry}. Context: {request.prompt}. Do not include raw HTML."
def _safe_link(value: Any, default: str = "#contact") -> str:
    value = str(value or "").strip(); parsed = urlparse(value); return value if value in {"#contact", "#products"} or (parsed.scheme == "https" and parsed.netloc) else default
def _render(data: Dict[str, Any], business_id: str) -> str:
    seo = data.get("seo") or {}
    hero = data.get("hero") or {}
    title = escape(str(seo.get("title") or "Your site"))
    headline = escape(str(hero.get("headline") or title))
    raw_sub = str(hero.get("subheadline") or "").strip()
    subheadline = escape(raw_sub) if raw_sub else ""
    cta = hero.get("primaryCTA") or {}
    cta_text = escape(str(cta.get("text") or "Contact"))
    cta_link = escape(_safe_link(cta.get("link"), "#contact"), quote=True)
    safe_biz_id = escape(str(business_id), quote=True)
    sub_html = f"<p>{subheadline}</p>" if subheadline else ""
    return (
        f"<!doctype html><html lang='he'><head>"
        f"<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title></head><body><main>"
        f"<h1>{headline}</h1>"
        f"{sub_html}"
        f"<a href='{cta_link}'>{cta_text}</a>"
        f"<p data-business-id='{safe_biz_id}'></p>"
        f"</main></body></html>"
    )

@router.post("/access")
async def create_builder_access(current_user: AuthUser = Depends(require_auth)):
    _ensure_premium(current_user.user_id); business = _get_business_for_user(current_user.user_id)
    if not business: raise HTTPException(422, "Create a business before opening the site builder")
    raw = secrets.token_urlsafe(36); expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    result = supabase.table("site_builder_tokens").insert({"user_id": current_user.user_id, "token_hash": _hash(raw), "expires_at": expires.isoformat(), "used_at": None}).execute()
    if not result.data: raise HTTPException(500, "Could not create builder token")
    return {"token": raw, "expires_at": expires.isoformat(), "business_id": business["id"], "url": f"/site-builder?token={raw}"}

@router.get("/verify/{token}")
async def verify_builder_access(token: str, current_user: AuthUser = Depends(require_auth)):
    record = _get_token_record(token, current_user.user_id); business = verify_tenant_ownership(supabase=supabase, user_id=current_user.user_id, business_id=_get_business_for_user(current_user.user_id)["id"])
    return {"valid": True, "user_id": current_user.user_id, "business_id": business["id"]}

@router.post("/consume/{token}")
async def consume_builder_access(token: str, current_user: AuthUser = Depends(require_auth)):
    record = _get_token_record(token, current_user.user_id); _mark_token_used(record["id"]); business = _get_business_for_user(current_user.user_id)
    return {"valid": True, "user_id": current_user.user_id, "business_id": business["id"] if business else None}

@router.post("/generate", response_model=GenerateResponse)
async def generate_builder_site(request: GenerateRequest, x_builder_token: Optional[str] = Header(None), current_user: AuthUser = Depends(require_auth)):
    if not x_builder_token: raise HTTPException(401, "Premium builder token required")
    record = _get_token_record(x_builder_token, current_user.user_id); business = verify_tenant_ownership(supabase=supabase, user_id=current_user.user_id, business_id=request.business_id or _get_business_for_user(current_user.user_id)["id"])
    try:
        data = _fallback_config(request)
        if client:
            response = client.models.generate_content(model=MODEL_NAME, contents=_build_prompt(request), config={"temperature": 0.7, "max_output_tokens": 5000}); data = json.loads(_clean_json(getattr(response, "text", "") or ""))
        html = _render(data, business["id"]); _mark_token_used(record["id"]); return GenerateResponse(success=True, config=data, html=html, fallback=not bool(client))
    except HTTPException: raise
    except Exception as exc: logger.exception("Site rendering failed"); raise HTTPException(500, "Failed to render site") from exc

@router.post("/leads", status_code=status.HTTP_201_CREATED)
async def create_site_lead(payload: LeadSubmission, request: Request):
    if payload.website and payload.website.strip(): return {"accepted": True, "message": "Thank you"}
    business = supabase.table("businesses").select("id,business_name,is_active,settings").eq("id", payload.business_id).maybe_single().execute()
    if not business.data or business.data.get("is_active") is False: raise HTTPException(404, "Business not found")
    if not _origin_allowed(request.headers.get("origin"), business.data): raise HTTPException(403, "Domain not allowed")
    _consume_rate_limit(payload.business_id, request.client.host if request.client else "unknown")
    result = supabase.table("lead_submissions").insert({"business_id": payload.business_id, "name": payload.name.strip(), "email": payload.email.strip().lower(), "message": payload.message.strip(), "company": (payload.company or "").strip() or None, "source": payload.source.strip()[:80], "page_url": (payload.page_url or "").strip()[:2048] or None, "ip_address": request.client.host if request.client else None, "user_agent": request.headers.get("user-agent", "")[:500] or None}).execute()
    if not result.data: raise HTTPException(503, "Could not save lead")
    return {"accepted": True, "message": "Thank you", "lead_id": result.data[0].get("id")}

@router.get("/leads")
async def list_site_leads(current_user: AuthUser = Depends(require_auth)):
    business = _get_business_for_user(current_user.user_id)
    if not business: return {"items": [], "total": 0}
    result = supabase.table("lead_submissions").select("id,name,email,company,message,source,page_url,status,created_at,updated_at").eq("business_id", business["id"]).execute(); return {"items": result.data or [], "total": len(result.data or []), "business_id": business["id"]}

@router.patch("/leads/{lead_id}")
async def update_site_lead(lead_id: str, payload: LeadStatusUpdate, current_user: AuthUser = Depends(require_auth)):
    business = _get_business_for_user(current_user.user_id)
    if not business: raise HTTPException(404, "Business not found")
    verify_resource_owner(supabase=supabase, table="lead_submissions", resource_id=lead_id, user_id=current_user.user_id, owner_column="business_id")
    result = supabase.table("lead_submissions").update({"status": payload.status}).eq("id", lead_id).eq("business_id", business["id"]).execute()
    if not result.data: raise HTTPException(404, "Lead not found")
    return result.data[0]

@router.get("/inbox", response_class=HTMLResponse, include_in_schema=False)
async def lead_inbox_page(current_user: AuthUser = Depends(require_auth)):
    _ensure_premium(current_user.user_id); path = Path(__file__).resolve().parents[2] / "frontend" / "html" / "leads.html"; return HTMLResponse(path.read_text(encoding="utf-8"))

@router.post("/save")
async def save_builder_site(request: SaveRequest, x_builder_token: Optional[str] = Header(None), current_user: AuthUser = Depends(require_auth)):
    if not x_builder_token: raise HTTPException(401, "Premium builder token required")
    record = _get_token_record(x_builder_token, current_user.user_id)
    if "<html" not in request.html.lower() or "</html>" not in request.html.lower(): raise HTTPException(422, "Edited site must be a complete HTML document")
    result = supabase.table("site_builder_projects").insert({"user_id": current_user.user_id, "token_id": record["id"], "project_name": request.project_name.strip(), "html": request.html}).execute()
    if not result.data: raise HTTPException(500, "Could not save site")
    _mark_token_used(record["id"]); return {"saved": True, "project_id": result.data[0].get("id"), "updated_at": result.data[0].get("updated_at")}
