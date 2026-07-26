"""Premium site builder access, CRO generation, visual-save persistence, and fallbacks."""
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

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from supabase import Client, create_client
from google import genai

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
    vibe: str = Field("modern", pattern="^(minimalist|cyber|luxury|playful|modern)$")
    sections: List[str] = Field(default_factory=lambda: ["hero", "features", "stats", "products", "faq", "contact"])


class SaveRequest(BaseModel):
    project_name: str = Field("ConversaPay site", min_length=2, max_length=120)
    html: str = Field(..., min_length=200, max_length=500_000)


class GenerateResponse(BaseModel):
    success: bool
    config: Optional[Dict[str, Any]] = None
    html: Optional[str] = None
    error: Optional[str] = None
    fallback: bool = False


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _expiry(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _ensure_premium(user_id: str) -> None:
    profile = supabase.table("profiles").select("plan_type").eq("user_id", user_id).maybe_single().execute()
    if (profile.data or {}).get("plan_type") != "premium":
        raise HTTPException(403, "The site builder is available only on PREMIUM")


def _get_token_record(token: str, allow_used: bool = False) -> Dict[str, Any]:
    result = supabase.table("site_builder_tokens").select("id,user_id,expires_at,used_at").eq("token_hash", _hash(token)).maybe_single().execute()
    record = result.data or {}
    if not record:
        raise HTTPException(401, "Invalid builder token")
    if record.get("used_at") and not allow_used:
        raise HTTPException(401, "Builder token already used")
    if _expiry(record["expires_at"]) <= datetime.now(timezone.utc):
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
החזר את המבנה המדויק הבא, עם תוכן בעברית טבעית:
hero {{ badge, headline, subheadline, primaryCTA {{ text, link }}, secondaryCTA {{ text, link }}, imageUrl }}
features: 3-4 אובייקטים {{ title, description, benefit }}
proofStats: 3 אובייקטים {{ value, label }}
products: 2-3 אובייקטים {{ title, pricePlaceholder, description, ctaText, ctaLink }}
faq: 3-5 אובייקטים {{ question, answer }}
contact {{ title, description, whatsappNumber }}
seo {{ title, description }}
theme {{ primaryColor, accentColor, backgroundColor, textColor, secondaryColor, surfaceColor }}
כל קישור חייב להיות #contact, #products או כתובת https:// פעילה. CTA ראשי צריך להוביל ל-#contact או ל-#products. אין להשתמש ב-placeholder כמו lorem ipsum."""


def _fallback_config(request: GenerateRequest) -> Dict[str, Any]:
    return {
        "hero": {"badge": request.business_name, "headline": f"{request.business_name}, הדרך הברורה לבחור נכון", "subheadline": f"פתרון מקצועי בתחום {request.industry}, עם חוויה פשוטה שמובילה את הלקוח מהשאלה הראשונה לפעולה.", "primaryCTA": {"text": "בואו נדבר", "link": "#contact"}, "secondaryCTA": {"text": "מה מקבלים", "link": "#products"}, "imageUrl": ""},
        "features": [{"title": "מסר חד", "description": "כל מה שהלקוח צריך לדעת, בלי רעש מיותר.", "benefit": "הבנה מהירה"}, {"title": "חוויה נעימה", "description": "מבנה רגוע, ברור ונוח בכל מסך.", "benefit": "יותר ביטחון"}, {"title": "פעולה ברורה", "description": "כל שלב מוביל בעדינות לצעד הבא.", "benefit": "יותר פניות"}],
        "proofStats": [{"value": "24/7", "label": "זמינים כשצריך"}, {"value": "3 צעדים", "label": "מתחילים מהר"}, {"value": "100%", "label": "מותאם למובייל"}],
        "products": [{"title": "שיחת התאמה", "pricePlaceholder": "מתחילים בשיחה", "description": "נבין מה חשוב לכם ונבנה את הצעד הבא.", "ctaText": "דברו איתנו", "ctaLink": "#contact"}, {"title": "הפתרון המלא", "pricePlaceholder": "לפי התאמה", "description": "מסלול מסודר שמחבר בין צורך, ערך ותוצאה.", "ctaText": "קבלו פרטים", "ctaLink": "#contact"}],
        "faq": [{"question": "למי זה מתאים?", "answer": f"לעסקים וללקוחות שמחפשים פתרון ברור בתחום {request.industry}."}, {"question": "איך מתחילים?", "answer": "משאירים פרטים, ואנחנו חוזרים עם תשובה ממוקדת."}, {"question": "מה קורה אחרי הפנייה?", "answer": "נבין את הצורך, נציג אפשרויות ונמליץ על הצעד הנכון."}],
        "contact": {"title": "מוכנים להתקדם?", "description": "השאירו פרטים, ונחזור אליכם עם תשובה עניינית.", "whatsappNumber": ""},
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
    if parsed.scheme == "https" and parsed.netloc:
        return link
    return default


def _render(data: Dict[str, Any]) -> str:
    hero = data.get("hero") or {}; theme = data.get("theme") or {}; seo = data.get("seo") or {}
    features = data.get("features") or []; stats = data.get("proofStats") or data.get("stats") or []; products = data.get("products") or []; faqs = data.get("faq") or []; contact = data.get("contact") or {}
    primary = escape(theme.get("primaryColor", "#635bff")); accent = escape(theme.get("accentColor", "#22c55e")); background = escape(theme.get("backgroundColor", "#111827")); text = escape(theme.get("textColor", "#f8fafc")); muted = escape(theme.get("secondaryColor", "#cbd5e1")); surface = escape(theme.get("surfaceColor", "#1f2937"))
    title = escape(seo.get("title") or hero.get("headline") or "האתר שלך"); description = escape(seo.get("description") or hero.get("subheadline") or ""); badge = escape(hero.get("badge") or "ConversaPay"); headline = escape(hero.get("headline") or "בונים אמון, מניעים פעולה"); subheadline = escape(hero.get("subheadline") or "עמוד ברור ומקצועי לעסק שלך."); primary_text = escape((hero.get("primaryCTA") or {}).get("text") or "בואו נדבר"); primary_link = escape(_safe_link((hero.get("primaryCTA") or {}).get("link"))); secondary_text = escape((hero.get("secondaryCTA") or {}).get("text") or "לגלות עוד"); secondary_link = escape(_safe_link((hero.get("secondaryCTA") or {}).get("link"), "#products")); image_url = str(hero.get("imageUrl") or "").strip()
    image_markup = f"<img class='hero-image' data-editable-image src='{escape(image_url, quote=True)}' alt='תמונה של {badge}'>" if image_url and urlparse(image_url).scheme in {"http", "https"} else "<div class='hero-orb' aria-hidden='true'></div>"
    feature_html = ''.join(f"<article class='feature-card' data-editable-block><span class='eyebrow'>BENEFIT</span><h3 data-editable>{escape(item.get('title') or '')}</h3><p data-editable>{escape(item.get('description') or '')}</p><strong data-editable>{escape(item.get('benefit') or '')}</strong></article>" for item in features)
    stats_html = ''.join(f"<div class='stat' data-editable-block><strong data-editable>{escape(item.get('value') or '')}</strong><span data-editable>{escape(item.get('label') or '')}</span></div>" for item in stats)
    product_html = ''.join(f"<article class='product-card' data-editable-block><span class='eyebrow'>SERVICE</span><h3 data-editable>{escape(item.get('title') or '')}</h3><strong class='price' data-editable>{escape(item.get('pricePlaceholder') or '')}</strong><p data-editable>{escape(item.get('description') or '')}</p><a class='cta secondary' data-editable href='{escape(_safe_link(item.get('ctaLink')), quote=True)}'>{escape(item.get('ctaText') or 'קבלו פרטים')}</a></article>" for item in products)
    faq_html = ''.join(f"<details data-editable-block><summary data-editable>{escape(item.get('question') or '')}</summary><p data-editable>{escape(item.get('answer') or '')}</p></details>" for item in faqs)
    whatsapp = str(contact.get("whatsappNumber") or "").replace("+", "").replace(" ", "").replace("-", "")
    whatsapp_link = f"https://wa.me/{escape(whatsapp)}" if whatsapp.isdigit() and len(whatsapp) >= 8 else "#contact"
    return f"""<!doctype html><html lang='he' dir='rtl'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title><meta name='description' content='{description}'><style>
:root{{--primary:{primary};--accent:{accent};--bg:{background};--text:{text};--muted:{muted};--surface:{surface};--line:color-mix(in srgb,var(--text) 14%,transparent);--shadow:0 24px 80px color-mix(in srgb,var(--bg) 70%,transparent)}}*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--bg);color:var(--text);font:500 16px/1.7 system-ui,-apple-system,'Segoe UI',sans-serif}}body::before{{content:'';position:fixed;inset:0;pointer-events:none;background:radial-gradient(circle at 85% 5%,color-mix(in srgb,var(--primary) 20%,transparent),transparent 35%),radial-gradient(circle at 15% 55%,color-mix(in srgb,var(--accent) 12%,transparent),transparent 28%);z-index:-1}}main{{width:min(1160px,calc(100% - 40px));margin:auto}}header{{display:flex;justify-content:space-between;align-items:center;padding:24px 0;gap:16px}}.brand{{font-weight:800;letter-spacing:-.04em}}.nav-link,.cta{{display:inline-flex;align-items:center;justify-content:center;min-height:44px;padding:10px 17px;border-radius:12px;text-decoration:none;font-weight:800;transition:transform .2s cubic-bezier(.16,1,.3,1),filter .2s ease}}.nav-link{{color:var(--muted)}}.cta{{background:var(--primary);color:#f8fafc;box-shadow:0 12px 26px color-mix(in srgb,var(--primary) 30%,transparent)}}.cta.secondary{{background:color-mix(in srgb,var(--surface) 80%,transparent);border:1px solid var(--line);color:var(--text);box-shadow:none}}.cta:hover,.nav-link:hover{{transform:translateY(-2px);filter:brightness(1.08)}}.hero{{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(260px,.9fr);gap:48px;align-items:center;padding:72px 0 92px}}.eyebrow{{color:var(--primary);font-size:.75rem;font-weight:900;letter-spacing:.12em;text-transform:uppercase}}h1,h2,h3{{margin:0;text-wrap:balance;line-height:1.1;letter-spacing:-.045em}}h1{{font-size:clamp(2.8rem,7vw,6rem);max-width:11ch}}h2{{font-size:clamp(2rem,4vw,3rem)}}h3{{font-size:1.25rem}}p{{color:var(--muted);max-width:68ch}}.hero-copy{{display:grid;gap:20px}}.hero-copy p{{font-size:1.15rem;max-width:55ch}}.actions{{display:flex;gap:10px;flex-wrap:wrap}}.hero-visual{{min-height:360px;position:relative;display:grid;place-items:center;border:1px solid var(--line);border-radius:32px;background:color-mix(in srgb,var(--surface) 75%,transparent);box-shadow:var(--shadow);backdrop-filter:blur(14px);overflow:hidden}}.hero-orb{{width:220px;height:220px;border-radius:50%;background:radial-gradient(circle at 35% 30%,color-mix(in srgb,var(--accent) 82%,white),var(--primary) 42%,color-mix(in srgb,var(--primary) 30%,var(--bg)));box-shadow:0 30px 90px color-mix(in srgb,var(--primary) 35%,transparent)}}.hero-image{{max-width:88%;max-height:320px;border-radius:24px;object-fit:cover;box-shadow:var(--shadow)}}section{{padding:72px 0;border-top:1px solid var(--line)}}.section-head{{display:grid;gap:10px;margin-bottom:28px}}.feature-grid,.product-grid,.stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}.feature-card,.product-card,.stat,details,.contact-card{{padding:22px;border:1px solid var(--line);border-radius:20px;background:color-mix(in srgb,var(--surface) 72%,transparent);box-shadow:0 16px 48px color-mix(in srgb,var(--bg) 35%,transparent);backdrop-filter:blur(10px)}}.feature-card{{display:grid;gap:10px}}.feature-card strong{{color:var(--accent)}}.stat{{display:grid;gap:4px}}.stat strong{{font-size:2.4rem;color:var(--primary);letter-spacing:-.06em}}.product-card{{display:grid;gap:12px}}.price{{font-size:1.6rem}}.faq-list{{display:grid;gap:10px;max-width:820px}}details summary{{cursor:pointer;font-weight:800}}details p{{margin-bottom:0}}.contact-card{{display:grid;gap:14px;max-width:760px}}.contact-form{{display:grid;gap:12px}}.contact-form input,.contact-form textarea{{width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--line);background:color-mix(in srgb,var(--bg) 70%,transparent);color:var(--text);font:inherit}}.contact-form textarea{{min-height:120px;resize:vertical}}.form-status{{min-height:24px;color:var(--accent)}}footer{{padding:34px 0 64px;color:var(--muted)}}[contenteditable=true]{{outline:2px dashed transparent;outline-offset:4px}}[contenteditable=true]:focus{{outline-color:var(--primary)}}.edit-highlight{{outline:2px dashed var(--primary)!important;outline-offset:4px}}@media(max-width:760px){{main{{width:min(100% - 24px,1160px)}}header{{padding:16px 0;align-items:flex-start}}.hero{{grid-template-columns:1fr;padding:46px 0 64px;gap:26px}}.hero-visual{{min-height:260px}}h1{{font-size:clamp(2.5rem,15vw,4.2rem)}}.actions,.nav{{display:grid;grid-template-columns:1fr}}.cta,.nav-link{{width:100%}}section{{padding:48px 0}}}}
</style></head><body><main><header><div class='brand' data-editable>{badge}</div><nav class='nav'><a class='nav-link' href='#products'>שירותים</a><a class='cta' href='#contact' data-editable>דברו איתנו</a></nav></header><section class='hero'><div class='hero-copy'><span class='eyebrow' data-editable>{badge}</span><h1 data-editable>{headline}</h1><p data-editable>{subheadline}</p><div class='actions'><a class='cta' data-editable href='{primary_link}'>{primary_text}</a><a class='cta secondary' data-editable href='{secondary_link}'>{secondary_text}</a></div></div><div class='hero-visual'>{image_markup}</div></section><section id='features'><div class='section-head'><span class='eyebrow'>WHY US</span><h2 data-editable>מה הופך את הבחירה לפשוטה</h2></div><div class='feature-grid'>{feature_html}</div></section><section id='proof'><div class='stats-grid'>{stats_html}</div></section><section id='products'><div class='section-head'><span class='eyebrow'>SERVICES</span><h2 data-editable>הצעד הבא שלכם</h2><p data-editable>בחרו את הדרך שמתאימה לכם, או השאירו פרטים ונכוון אתכם.</p></div><div class='product-grid'>{product_html}</div></section><section id='faq'><div class='section-head'><span class='eyebrow'>FAQ</span><h2 data-editable>שאלות נפוצות</h2></div><div class='faq-list'>{faq_html}</div></section><section id='contact'><div class='contact-card'><span class='eyebrow'>CONTACT</span><h2 data-editable>{escape(contact.get('title') or 'מוכנים להתקדם?')}</h2><p data-editable>{escape(contact.get('description') or 'השאירו פרטים ונחזור אליכם.')}</p><form class='contact-form' id='contactForm'><input name='name' required placeholder='שם מלא' aria-label='שם מלא'><input name='email' type='email' required placeholder='אימייל' aria-label='אימייל'><textarea name='message' required placeholder='איך אפשר לעזור?' aria-label='איך אפשר לעזור?'></textarea><button class='cta' type='submit'>שלחו פנייה</button><div class='form-status' id='formStatus' role='status' aria-live='polite'></div></form><a class='cta secondary' href='{escape(whatsapp_link, quote=True)}' target='_blank' rel='noopener'>WhatsApp</a></div></section><footer data-editable>נבנה עם ConversaPay Site Builder</footer></main><script>document.querySelectorAll('a[href^="#"]').forEach(a=>a.addEventListener('click',e=>{const target=document.querySelector(a.getAttribute('href'));if(target){e.preventDefault();target.scrollIntoView({behavior:'smooth',block:'start'})}}));document.getElementById('contactForm')?.addEventListener('submit',e=>{e.preventDefault();const status=document.getElementById('formStatus');status.textContent='תודה, קיבלנו את הפרטים ונחזור אליכם בהקדם.';e.currentTarget.reset()});</script></body></html>"""


@router.post("/access")
async def create_builder_access(current_user: AuthUser = Depends(require_auth)):
    _ensure_premium(current_user.user_id)
    raw = secrets.token_urlsafe(36); expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    result = supabase.table("site_builder_tokens").insert({"user_id": current_user.user_id, "token_hash": _hash(raw), "expires_at": expires.isoformat(), "used_at": None}).execute()
    if not result.data: raise HTTPException(500, "Could not create builder access")
    return {"token": raw, "expires_at": expires.isoformat(), "url": f"/site-builder?token={raw}"}


@router.get("/verify/{token}")
async def verify_builder_access(token: str):
    record = _get_token_record(token, allow_used=False); return {"valid": True, "user_id": record["user_id"]}


@router.post("/consume/{token}")
async def consume_builder_access(token: str):
    record = _get_token_record(token, allow_used=False); _mark_token_used(record["id"]); return {"valid": True, "user_id": record["user_id"]}


@router.post("/generate", response_model=GenerateResponse)
async def generate_builder_site(request: GenerateRequest, x_builder_token: Optional[str] = Header(None)):
    if not x_builder_token: raise HTTPException(401, "Premium builder token required")
    record = _get_token_record(x_builder_token, allow_used=False); fallback = False; fallback_message = None
    try:
        if not client: raise RuntimeError("Gemini client is not configured")
        response = client.models.generate_content(model=MODEL_NAME, contents=_build_prompt(request), config={"temperature": 0.7, "max_output_tokens": 5000})
        data = json.loads(_clean_json(getattr(response, "text", "") or ""))
        if not isinstance(data, dict): raise ValueError("Gemini returned an invalid site configuration")
    except Exception as exc:
        fallback = True
        fallback_message = "AI generation is unavailable in this region, so a polished starter site was created instead." if _is_location_error(exc) else "AI generation is temporarily unavailable, so a polished starter site was created instead."
        logger.warning("Site generation provider failed, using fallback: %s", exc, exc_info=not _is_location_error(exc))
        data = _fallback_config(request)
    try:
        html = _render(data); _mark_token_used(record["id"]); return GenerateResponse(success=True, config=data, html=html, error=fallback_message, fallback=fallback)
    except Exception as exc:
        logger.exception("Site template rendering failed"); raise HTTPException(500, "Failed to render site template") from exc


@router.post("/save")
async def save_builder_site(request: SaveRequest, x_builder_token: Optional[str] = Header(None)):
    if not x_builder_token: raise HTTPException(401, "Premium builder token required")
    record = _get_token_record(x_builder_token, allow_used=True)
    if "<html" not in request.html.lower() or "</html>" not in request.html.lower():
        raise HTTPException(422, "Edited site must be a complete HTML document")
    try:
        result = supabase.table("site_builder_projects").insert({"user_id": record["user_id"], "token_id": record["id"], "project_name": request.project_name.strip(), "html": request.html}).execute()
        if not result.data: raise HTTPException(500, "Could not save site")
        return {"saved": True, "project_id": result.data[0].get("id"), "updated_at": result.data[0].get("updated_at")}
    except HTTPException: raise
    except Exception as exc:
        logger.exception("Site project save failed")
        raise HTTPException(503, "Site saving is not available until the site builder migration is applied") from exc
