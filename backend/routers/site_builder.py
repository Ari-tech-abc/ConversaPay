"""Premium site builder access and generation endpoints."""
import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Dict, List, Optional

import google.generativeai as genai
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from supabase import create_client

from backend.config import settings
from backend.middleware.auth import AuthUser, require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/site-builder", tags=["site-builder"])
supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
model = None

if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.5-flash")


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=10, max_length=1000)
    business_name: str = Field(..., min_length=2, max_length=100)
    industry: str = Field(..., min_length=2, max_length=50)
    vibe: str = Field("modern", pattern="^(minimalist|cyber|luxury|playful|modern)$")
    sections: List[str] = Field(default_factory=lambda: ["hero", "features", "products", "testimonials"])


class GenerateResponse(BaseModel):
    success: bool
    config: Optional[Dict[str, Any]] = None
    html: Optional[str] = None
    error: Optional[str] = None


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
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.I).strip()
    match = re.search(r"\{.*\}", cleaned, re.S)
    return match.group(0) if match else cleaned


def _build_prompt(request: GenerateRequest) -> str:
    return (
        "Return only valid JSON for a premium landing page. "
        f"Language: same as the user prompt. Business: {request.business_name}. "
        f"Industry: {request.industry}. Vibe: {request.vibe}. "
        f"Description: {request.prompt}. Sections: {', '.join(request.sections)}. "
        "Include hero, features, products, testimonials, theme and seo. "
        "Make the tone persuasive and production-ready."
    )


def _render(data: Dict[str, Any]) -> str:
    hero = data.get("hero") or {}
    theme = data.get("theme") or {}
    seo = data.get("seo") or {}
    features = data.get("features") or []
    products = data.get("products") or []
    testimonials = data.get("testimonials") or []

    primary = escape(theme.get("primaryColor", "#635bff"))
    background = escape(theme.get("backgroundColor", "#07111f"))
    text = escape(theme.get("textColor", "#f8fafc"))
    muted = escape(theme.get("secondaryColor", "#cbd5e1"))
    surface = escape(theme.get("surfaceColor", "rgba(255,255,255,0.06)"))
    title = escape(seo.get("title") or hero.get("headline") or "Generated site")
    description = escape(seo.get("description") or hero.get("subheadline") or "")
    badge = escape(hero.get("badge") or "ConversaPay")
    headline = escape(hero.get("headline") or "Build trust and convert faster")
    subheadline = escape(hero.get("subheadline") or "A clear premium landing page for your business.")
    cta_text = escape((hero.get("primaryCTA") or {}).get("text") or "Get started")
    cta_link = escape((hero.get("primaryCTA") or {}).get("link") or "#contact")

    def render_feature_cards(items: List[Dict[str, Any]]) -> str:
        cards = []
        for item in items:
            cards.append(
                f"<article class='tile'><span class='mini-badge'>FEATURE</span><h3>{escape(item.get('title') or '')}</h3><p>{escape(item.get('description') or '')}</p></article>"
            )
        return "".join(cards)

    def render_product_cards(items: List[Dict[str, Any]]) -> str:
        cards = []
        for item in items:
            cards.append(
                f"<article class='tile'><h3>{escape(item.get('title') or '')}</h3><strong>{escape(item.get('pricePlaceholder') or '')}</strong><p>{escape(item.get('description') or '')}</p></article>"
            )
        return "".join(cards)

    def render_testimonials(items: List[Dict[str, Any]]) -> str:
        cards = []
        for item in items:
            cards.append(
                f"<figure class='quote'><blockquote>“{escape(item.get('quote') or '')}”</blockquote><figcaption>{escape(item.get('author') or '')} · {escape(item.get('role') or '')}</figcaption></figure>"
            )
        return "".join(cards)

    sections = []
    if features:
        sections.append(f"<section><h2>What makes this different</h2><div class='grid'>{render_feature_cards(features)}</div></section>")
    if products:
        sections.append(f"<section><h2>What you offer</h2><div class='grid'>{render_product_cards(products)}</div></section>")
    if testimonials:
        sections.append(f"<section><h2>What people say</h2><div class='grid'>{render_testimonials(testimonials)}</div></section>")

    return f"""<!doctype html>
<html lang='en'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width,initial-scale=1'>
  <title>{title}</title>
  <meta name='description' content='{description}'>
  <style>
    :root {{ --primary:{primary}; --bg:{background}; --text:{text}; --muted:{muted}; --surface:{surface}; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font:16px/1.7 Inter,system-ui,sans-serif; background:var(--bg); color:var(--text); }}
    main {{ max-width:1180px; margin:auto; padding:32px 20px 80px; }}
    .hero {{ padding:88px 0 72px; max-width:780px; }}
    .badge,.mini-badge {{ display:inline-flex; padding:8px 12px; border-radius:999px; background:color-mix(in srgb,var(--primary) 16%, transparent); color:var(--text); font-size:.78rem; letter-spacing:.14em; text-transform:uppercase; }}
    h1 {{ font-size:clamp(2.8rem,7vw,5.8rem); line-height:1.02; margin:16px 0 22px; letter-spacing:-.06em; }}
    h2 {{ font-size:2rem; margin:0 0 18px; letter-spacing:-.04em; }}
    h3 {{ margin:0; font-size:1.15rem; }}
    p {{ color:var(--muted); max-width:68ch; }}
    .cta {{ display:inline-flex; align-items:center; justify-content:center; margin-top:18px; padding:14px 22px; border-radius:999px; background:var(--primary); color:white; text-decoration:none; font-weight:700; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:18px; }}
    .tile,.quote {{ padding:24px; border-radius:24px; background:var(--surface); border:1px solid color-mix(in srgb,var(--text) 10%, transparent); backdrop-filter: blur(8px); }}
    .quote {{ margin:0; }}
    blockquote {{ margin:0 0 14px; font-size:1.1rem; color:var(--text); }}
    section {{ margin-top:48px; }}
    footer {{ padding-top:36px; color:var(--muted); }}
    @media (max-width:640px) {{ .hero {{ padding-top:48px; }} main {{ padding-top:20px; }} }}
  </style>
</head>
<body>
  <main>
    <section class='hero'>
      <span class='badge'>{badge}</span>
      <h1>{headline}</h1>
      <p>{subheadline}</p>
      <a class='cta' href='{cta_link}'>{cta_text}</a>
    </section>
    {''.join(sections)}
    <footer>Built with ConversaPay Site Builder</footer>
  </main>
</body>
</html>"""


@router.post("/access")
async def create_builder_access(current_user: AuthUser = Depends(require_auth)):
    _ensure_premium(current_user.user_id)
    raw = secrets.token_urlsafe(36)
    expires = datetime.now(timezone.utc) + timedelta(minutes=30)
    result = supabase.table("site_builder_tokens").insert(
        {
            "user_id": current_user.user_id,
            "token_hash": _hash(raw),
            "expires_at": expires.isoformat(),
            "used_at": None,
        }
    ).execute()
    if not result.data:
        raise HTTPException(500, "Could not create builder access")
    return {"token": raw, "expires_at": expires.isoformat(), "url": f"/site-builder?token={raw}"}


@router.get("/verify/{token}")
async def verify_builder_access(token: str):
    record = _get_token_record(token, allow_used=False)
    return {"valid": True, "user_id": record["user_id"]}


@router.post("/consume/{token}")
async def consume_builder_access(token: str):
    record = _get_token_record(token, allow_used=False)
    _mark_token_used(record["id"])
    return {"valid": True, "user_id": record["user_id"]}


@router.post("/generate", response_model=GenerateResponse)
async def generate_builder_site(request: GenerateRequest, x_builder_token: Optional[str] = Header(None)):
    if not x_builder_token:
        raise HTTPException(401, "Premium builder token required")
    if not model:
        raise HTTPException(503, "AI service not configured")

    record = _get_token_record(x_builder_token, allow_used=False)

    try:
        response = model.generate_content(
            _build_prompt(request),
            generation_config={"temperature": 0.7, "max_output_tokens": 3000},
        )
        data = json.loads(_clean_json(response.text))
        html = _render(data)
        _mark_token_used(record["id"])
        return GenerateResponse(success=True, config=data, html=html)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Site generation failed")
        raise HTTPException(500, "Failed to generate site")
