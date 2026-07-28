"""Premium site builder access, generation, visual-save persistence, and lead intake."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from google import genai
from pydantic import BaseModel, Field
from supabase import Client, create_client

from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth

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


class GenerateResponse(BaseModel):
    success: bool
    config: Optional[Dict[str, Any]] = None
    html: Optional[str] = None
    error: Optional[str] = None
    fallback: bool = False


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _expiry(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _ensure_premium(user_id: str) -> None:
    profile = supabase.table("profiles").select("plan_type").eq("user_id", user_id).maybe_single().execute()
    if (profile.data or {}).get("plan_type") != "premium":
        raise HTTPException(403, "The site builder is available only on PREMIUM")


def _get_business_for_user(user_id: str, business_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query = supabase.table("businesses").select("id,business_name,is_active").eq("owner_id", user_id)
    if business_id:
        query = query.eq("id", business_id)
    result = query.limit(1).execute()
    return (result.data or [None])[0]


def _get_token_record(token: str, allow_used: bool = True) -> Dict[str, Any]:
    """Validate the hash and expiry, but keep a token usable for its 30-minute session."""
    result = supabase.table("site_builder_tokens").select("id,user_id,expires_at,used_at").eq("token_hash", _hash(token)).maybe_single().execute()
    record = result.data or {}
    if not record:
        raise HTTPException(401, "Invalid builder token")
    try:
        expired = _expiry(record["expires_at"]) <= datetime.now(timezone.utc)
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Malformed site builder token expiry: %s", exc)
        raise HTTPException(401, "Invalid builder token") from exc
    if expired:
        raise HTTPException(401, "Builder token expired")
    _ensure_premium(record["user_id"])
    return record


def _mark_token_used(token_id: str) -> None:
    supabase.table("site_builder_tokens").update({"used_at": datetime.now(timezone.utc).isoformat()}).eq("id", token_id).execute()


def _clean_json(text: str) -> str:
    cleaned = re.sub(r"```(?:json)?", "", text or "", flags=re.I).strip()
    match = re.search(r"\{.*\}", cleaned, re.S)
    return match.group(0) if match else cleaned


def _build_prompt(request: GenerateRequest) -> str:
    return f"""אתה מעצב אתרים בכיר, מומחה CRO וקופירייטר שיווקי מקצועי בעברית.
צור JSON בלבד, ללא markdown וללא הסברים. אל תעתיק את הפרומפט כטקסט גולמי. פרש את ההקשר והפוך אותו למסר שיווקי חד, אמין ומניע לפעולה.
עסק: {request.business_name}
תחום: {request.industry}
הקשר עסקי: {request.prompt}
סגנון: {request.vibe}
החזר hero, features, proofStats, products, faq, contact, seo ו-theme. כל קישור חייב להיות #contact, #products או כתובת https:// פעילה. אין להשתמש ב-placeholder כמו lorem ipsum."""


def _fallback_config(request: GenerateRequest) -> Dict[str, Any]:
    return {
        "hero": {"badge": request.business_name, "headline": f"{request.business_name}, הדרך הברורה לבחור נכון", "subheadline": f"פתרון מקצועי בתחום {request.industry}, עם חוויה פשוטה שמובילה את הלקוח לפעולה.", "primaryCTA": {"text": "בואו נדבר", "link": "#contact"}, "secondaryCTA": {"text": "מה מקבלים", "link": "#products"}, "imageUrl": ""},
        "features": [{"title": "מסר חד", "description": "כל מה שהלקוח צריך לדעת, בלי רעש מיותר.", "benefit": "הבנה מהירה"}, {"title": "חוויה נעימה", "description": "מבנה רגוע, ברור ונוח בכל מסך.", "benefit": "יותר ביטחון"}, {"title": "פעולה ברורה", "description": "כל שלב מוביל בעדינות לצעד הבא.", "benefit": "יותר פניות"}],
        "proofStats": [{"value": "24/7", "label": "זמינים כשצריך"}, {"value": "3 צעדים", "label": "מתחילים מהר"}, {"value": "100%", "label": "מותאם למובייל"}],
        "products": [{"title": "שיחת התאמה", "pricePlaceholder": "מתחילים בשיחה", "description": "נבין מה חשוב לכם ונבנה את הצעד הבא.", "ctaText": "דברו איתנו", "ctaLink": "#contact"}],
        "faq": [{"question": "איך מתחילים?", "answer": "משאירים פרטים, ואנחנו חוזרים עם תשובה ממוקדת."}],
        "contact": {"title": "מוכנים להתקדם?", "description": "השאירו פרטים, ונחזור אליכם.", "whatsappNumber": ""},
        "theme": {"primaryColor": "#635bff", "accentColor": "#22c55e", "backgroundColor": "#111827", "textColor": "#f8fafc", "secondaryColor": "#cbd5e1", "surfaceColor": "#1f2937"},
        "seo": {"title": request.business_name, "description": request.prompt},
    }


def _is_location_error(error: Exception) -> bool:
    client_error = getattr(genai_errors, "ClientError", None) if genai_errors else None
    message = str(error).lower()
    markers = ("user location is not supported", "location is not supported", "region is not supported", "not available in your country", "geographic restriction", "unsupported location")
    return bool(client_error and isinstance(error, client_error) and any(marker in message for marker in markers)) or any(marker in message for marker in markers)


def _safe_link(value: Any, default: str = "#contact") -> str:
    link = str(value or "").strip()
    if link in {"#contact", "#products"}:
        return link
    parsed = urlparse(link)
    return link if parsed.scheme == "https" and parsed.netloc else default


def _render(data: Dict[str, Any], business_id: str) -> str:
    hero = data.get("hero") or {}
    theme = data.get("theme") or {}
    seo = data.get("seo") or {}
    features = data.get("features") or []
    stats = data.get("proofStats") or data.get("stats") or []
    products = data.get("products") or []
    faqs = data.get("faq") or []
    contact = data.get("contact") or {}
    values = {
        "TITLE": escape(seo.get("title") or hero.get("headline") or "האתר שלך"),
        "DESCRIPTION": escape(seo.get("description") or hero.get("subheadline") or ""),
        "PRIMARY": escape(theme.get("primaryColor", "#635bff")),
        "ACCENT": escape(theme.get("accentColor", "#22c55e")),
        "BACKGROUND": escape(theme.get("backgroundColor", "#111827")),
        "TEXT": escape(theme.get("textColor", "#f8fafc")),
        "MUTED": escape(theme.get("secondaryColor", "#cbd5e1")),
        "SURFACE": escape(theme.get("surfaceColor", "#1f2937")),
        "BADGE": escape(hero.get("badge") or "ConversaPay"),
        "HEADLINE": escape(hero.get("headline") or "בונים אמון, מניעים פעולה"),
        "SUBHEADLINE": escape(hero.get("subheadline") or "עמוד ברור ומקצועי לעסק שלך."),
        "PRIMARY_LINK": escape(_safe_link((hero.get("primaryCTA") or {}).get("link")), quote=True),
        "PRIMARY_TEXT": escape((hero.get("primaryCTA") or {}).get("text") or "בואו נדבר"),
        "SECONDARY_LINK": escape(_safe_link((hero.get("secondaryCTA") or {}).get("link"), "#products"), quote=True),
        "SECONDARY_TEXT": escape((hero.get("secondaryCTA") or {}).get("text") or "לגלות עוד"),
        "BUSINESS_ID": escape(business_id, quote=True),
    }
    image_url = str(hero.get("imageUrl") or "").strip()
    values["IMAGE_MARKUP"] = f"<img class='hero-image' data-editable-image src='{escape(image_url, quote=True)}' alt='תמונה של {values['BADGE']}'>" if image_url and urlparse(image_url).scheme in {"http", "https"} else "<div class='hero-orb' aria-hidden='true'></div>"
    values["FEATURES"] = "".join(f"<article class='feature-card' data-editable-block><h3 data-editable>{escape(item.get('title') or '')}</h3><p data-editable>{escape(item.get('description') or '')}</p><strong data-editable>{escape(item.get('benefit') or '')}</strong></article>" for item in features)
    values["STATS"] = "".join(f"<div class='stat' data-editable-block><strong data-editable>{escape(item.get('value') or '')}</strong><span data-editable>{escape(item.get('label') or '')}</span></div>" for item in stats)
    values["PRODUCTS"] = "".join(f"<article class='product-card' data-editable-block><h3 data-editable>{escape(item.get('title') or '')}</h3><strong data-editable>{escape(item.get('pricePlaceholder') or '')}</strong><p data-editable>{escape(item.get('description') or '')}</p><a class='cta secondary' data-editable href='{escape(_safe_link(item.get('ctaLink')), quote=True)}'>{escape(item.get('ctaText') or 'קבלו פרטים')}</a></article>" for item in products)
    values["FAQ"] = "".join(f"<details data-editable-block><summary data-editable>{escape(item.get('question') or '')}</summary><p data-editable>{escape(item.get('answer') or '')}</p></details>" for item in faqs)
    values["CONTACT_TITLE"] = escape(contact.get("title") or "מוכנים להתקדם?")
    values["CONTACT_DESCRIPTION"] = escape(contact.get("description") or "השאירו פרטים ונחזור אליכם.")
    phone = str(contact.get("whatsappNumber") or "").replace("+", "").replace(" ", "").replace("-", "")
    values["WHATSAPP_LINK"] = escape(f"https://wa.me/{phone}" if phone.isdigit() and len(phone) >= 8 else "#contact", quote=True)

    template = """<!doctype html><html lang='he' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>__TITLE__</title><meta name='description' content='__DESCRIPTION__'><style>:root{--primary:__PRIMARY__;--accent:__ACCENT__;--bg:__BACKGROUND__;--text:__TEXT__;--muted:__MUTED__;--surface:__SURFACE__}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font:500 16px/1.7 system-ui,-apple-system,'Segoe UI',sans-serif}main{width:min(1160px,calc(100% - 40px));margin:auto}header{display:flex;justify-content:space-between;align-items:center;padding:24px 0;gap:16px}.brand{font-weight:800}.cta{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 17px;border-radius:12px;text-decoration:none;font-weight:800;background:var(--primary);color:#f8fafc;border:0;cursor:pointer}.cta.secondary{background:var(--surface);color:var(--text);border:1px solid color-mix(in srgb,var(--text) 16%,transparent)}.hero{display:grid;grid-template-columns:1.1fr .9fr;gap:48px;align-items:center;padding:72px 0 92px}.hero-copy{display:grid;gap:20px}.eyebrow{color:var(--primary);font-size:.75rem;font-weight:900;letter-spacing:.12em;text-transform:uppercase}h1,h2,h3{margin:0;line-height:1.1;letter-spacing:-.045em}h1{font-size:clamp(2.8rem,7vw,6rem);max-width:11ch}h2{font-size:clamp(2rem,4vw,3rem)}p{color:var(--muted);max-width:68ch}.actions{display:flex;gap:10px;flex-wrap:wrap}.hero-visual{min-height:360px;display:grid;place-items:center;border:1px solid color-mix(in srgb,var(--text) 14%,transparent);border-radius:32px;background:var(--surface)}.hero-orb{width:220px;height:220px;border-radius:50%;background:var(--primary)}.hero-image{max-width:88%;max-height:320px;border-radius:24px;object-fit:cover}section{padding:72px 0;border-top:1px solid color-mix(in srgb,var(--text) 14%,transparent)}.feature-grid,.product-grid,.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}.feature-card,.product-card,.stat,details,.contact-card{padding:22px;border:1px solid color-mix(in srgb,var(--text) 14%,transparent);border-radius:20px;background:var(--surface)}.feature-card{display:grid;gap:10px}.feature-card strong{color:var(--accent)}.stat{display:grid;gap:4px}.stat strong{font-size:2.4rem;color:var(--primary)}.product-card{display:grid;gap:12px}.faq-list{display:grid;gap:10px;max-width:820px}.contact-card{display:grid;gap:14px;max-width:760px}.contact-form{display:grid;gap:12px}.contact-form label{font-weight:700;color:var(--text)}.sr-only{position:absolute!important;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.contact-form input,.contact-form textarea{width:100%;padding:12px 14px;border-radius:12px;border:1px solid color-mix(in srgb,var(--text) 18%,transparent);background:var(--bg);color:var(--text);font:inherit}.contact-form textarea{min-height:120px}.contact-form .form-status{min-height:24px;color:var(--accent);font-weight:700}footer{padding:34px 0 64px;color:var(--muted)}[contenteditable=true]{outline:2px dashed transparent;outline-offset:4px}[contenteditable=true]:focus{outline-color:var(--primary)}@media(max-width:760px){main{width:min(100% - 24px,1160px)}.hero{grid-template-columns:1fr;padding:46px 0 64px}.actions,.nav{display:grid;grid-template-columns:1fr}.cta{width:100%}section{padding:48px 0}}</style></head><body><main><header><div class='brand' data-editable>__BADGE__</div><nav class='nav'><a class='cta secondary' href='#products'>שירותים</a><a class='cta' href='#contact' data-editable>דברו איתנו</a></nav></header><section class='hero'><div class='hero-copy'><span class='eyebrow' data-editable>__BADGE__</span><h1 data-editable>__HEADLINE__</h1><p data-editable>__SUBHEADLINE__</p><div class='actions'><a class='cta' data-editable href='__PRIMARY_LINK__'>__PRIMARY_TEXT__</a><a class='cta secondary' data-editable href='__SECONDARY_LINK__'>__SECONDARY_TEXT__</a></div></div><div class='hero-visual'>__IMAGE_MARKUP__</div></section><section id='features'><h2 data-editable>מה הופך את הבחירה לפשוטה</h2><div class='feature-grid'>__FEATURES__</div></section><section id='proof'><div class='stats-grid'>__STATS__</div></section><section id='products'><h2 data-editable>הצעד הבא שלכם</h2><p data-editable>בחרו את הדרך שמתאימה לכם, או השאירו פרטים ונכוון אתכם.</p><div class='product-grid'>__PRODUCTS__</div></section><section id='faq'><h2 data-editable>שאלות נפוצות</h2><div class='faq-list'>__FAQ__</div></section><section id='contact'><div class='contact-card'><h2 data-editable>__CONTACT_TITLE__</h2><p data-editable>__CONTACT_DESCRIPTION__</p><form class='contact-form' id='contactForm' data-business-id='__BUSINESS_ID__' novalidate><label for='leadName'>שם מלא</label><input id='leadName' name='name' autocomplete='name' required minlength='2' maxlength='120' placeholder='שם מלא'><label for='leadEmail'>כתובת אימייל</label><input id='leadEmail' name='email' type='email' autocomplete='email' required maxlength='320' placeholder='אימייל'><label for='leadMessage'>איך אפשר לעזור?</label><textarea id='leadMessage' name='message' required minlength='2' maxlength='4000' placeholder='איך אפשר לעזור?'></textarea><label class='sr-only' for='leadCompany'>חברה</label><input id='leadCompany' name='company' tabindex='-1' autocomplete='off' aria-hidden='true' style='position:absolute;left:-10000px;width:1px;height:1px;opacity:0'><button class='cta' type='submit'>שלחו פנייה</button><div id='formStatus' class='form-status' role='status' aria-live='polite'></div></form><a class='cta secondary' href='__WHATSAPP_LINK__' target='_blank' rel='noopener'>WhatsApp</a></div></section><footer data-editable>נבנה עם ConversaPay Site Builder</footer></main><script>(function(){var api='/api/v1/site-builder/leads',form=document.getElementById('contactForm'),status=document.getElementById('formStatus');form&&form.addEventListener('submit',async function(event){event.preventDefault();status.textContent='שולחים...';var button=form.querySelector('button[type=submit]');button.disabled=true;try{var response=await fetch(api,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({business_id:form.dataset.businessId,name:form.name.value.trim(),email:form.email.value.trim(),message:form.message.value.trim(),company:form.company.value.trim(),source:'site-builder',page_url:location.href,website:form.company.value.trim()})});var data=await response.json().catch(function(){return{};});if(!response.ok)throw new Error(data.detail||'לא ניתן לשלוח את הפנייה כרגע.');status.textContent=data.message||'תודה, קיבלנו את הפרטים ונחזור אליכם בהקדם.';form.reset()}catch(error){status.textContent=error.message||'לא ניתן לשלוח את הפנייה כרגע.'}finally{button.disabled=false}})})();</script></body></html>"""
    for key, value in values.items():
        template = template.replace(f"__{key}__", value)
    return template


@router.post("/access")
async def create_builder_access(current_user: AuthUser = Depends(require_auth)):
    _ensure_premium(current_user.user_id)
    business = _get_business_for_user(current_user.user_id)
    if not business:
        raise HTTPException(422, "Create a business before opening the site builder")
    raw = secrets.token_urlsafe(36)
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    result = supabase.table("site_builder_tokens").insert({"user_id": current_user.user_id, "token_hash": _hash(raw), "expires_at": expires.isoformat(), "used_at": None}).execute()
    if not result.data:
        raise HTTPException(500, "Could not create builder token")
    return {"token": raw, "expires_at": expires.isoformat(), "business_id": business["id"], "url": f"/site-builder?token={raw}"}


@router.get("/verify/{token}")
async def verify_builder_access(token: str):
    record = _get_token_record(token, allow_used=True)
    business = _get_business_for_user(record["user_id"])
    return {"valid": True, "user_id": record["user_id"], "business_id": (business or {}).get("id")}


@router.post("/consume/{token}")
async def consume_builder_access(token: str):
    record = _get_token_record(token, allow_used=True)
    _mark_token_used(record["id"])
    business = _get_business_for_user(record["user_id"])
    return {"valid": True, "user_id": record["user_id"], "business_id": (business or {}).get("id")}


@router.post("/generate", response_model=GenerateResponse)
async def generate_builder_site(request: GenerateRequest, x_builder_token: Optional[str] = Header(None)):
    if not x_builder_token:
        raise HTTPException(401, "Premium builder token required")
    record = _get_token_record(x_builder_token, allow_used=True)
    business = _get_business_for_user(record["user_id"], request.business_id)
    if not business:
        raise HTTPException(422, "Business not found for this builder session")
    business_id = business["id"]
    fallback = False
    fallback_message = None
    try:
        if not client:
            raise RuntimeError("Gemini client is not configured")
        response = client.models.generate_content(model=MODEL_NAME, contents=_build_prompt(request), config={"temperature": 0.7, "max_output_tokens": 5000})
        data = json.loads(_clean_json(getattr(response, "text", "") or ""))
        if not isinstance(data, dict):
            raise ValueError("Gemini returned an invalid site configuration")
    except Exception as exc:
        fallback = True
        fallback_message = "AI generation is unavailable in this region, so a polished starter site was created instead." if _is_location_error(exc) else "AI generation is temporarily unavailable, so a polished starter site was created instead."
        logger.warning("Site generation provider failed, using fallback: %s", exc, exc_info=not _is_location_error(exc))
        data = _fallback_config(request)
    try:
        html = _render(data, business_id)
        _mark_token_used(record["id"])
        return GenerateResponse(success=True, config=data, html=html, error=fallback_message, fallback=fallback)
    except Exception as exc:
        logger.exception("Site template rendering failed")
        raise HTTPException(500, "Failed to render site template") from exc


@router.post("/leads", status_code=status.HTTP_201_CREATED)
async def create_site_lead(payload: LeadSubmission, request: Request):
    """Receive a public builder form submission while keeping it tenant-scoped."""
    if payload.website and payload.website.strip():
        return {"accepted": True, "message": "תודה, קיבלנו את הפרטים ונחזור אליכם בהקדם."}
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", payload.email.strip()):
        raise HTTPException(422, "כתובת אימייל אינה תקינה")
    business = supabase.table("businesses").select("id,is_active").eq("id", payload.business_id).maybe_single().execute()
    if not business.data or business.data.get("is_active") is False:
        raise HTTPException(404, "Business not found")
    row = {
        "business_id": payload.business_id,
        "name": payload.name.strip(),
        "email": payload.email.strip().lower(),
        "message": payload.message.strip(),
        "company": (payload.company or "").strip() or None,
        "source": payload.source.strip()[:80],
        "page_url": (payload.page_url or "").strip()[:2048] or None,
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:500] or None,
    }
    try:
        result = supabase.table("lead_submissions").insert(row).execute()
    except Exception as exc:
        logger.exception("Lead submission failed")
        raise HTTPException(503, "לא ניתן לשמור את הפנייה כרגע") from exc
    if not result.data:
        raise HTTPException(503, "לא ניתן לשמור את הפנייה כרגע")
    return {"accepted": True, "message": "תודה, קיבלנו את הפרטים ונחזור אליכם בהקדם.", "lead_id": result.data[0].get("id")}


@router.post("/save")
async def save_builder_site(request: SaveRequest, x_builder_token: Optional[str] = Header(None)):
    if not x_builder_token:
        raise HTTPException(401, "Premium builder token required")
    record = _get_token_record(x_builder_token, allow_used=True)
    if "<html" not in request.html.lower() or "</html>" not in request.html.lower():
        raise HTTPException(422, "Edited site must be a complete HTML document")
    try:
        result = supabase.table("site_builder_projects").insert({"user_id": record["user_id"], "token_id": record["id"], "project_name": request.project_name.strip(), "html": request.html}).execute()
        if not result.data:
            raise HTTPException(500, "Could not save site")
        return {"saved": True, "project_id": result.data[0].get("id"), "updated_at": result.data[0].get("updated_at")}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Site project save failed")
        raise HTTPException(503, "Site saving is not available until the site builder migration is applied") from exc
