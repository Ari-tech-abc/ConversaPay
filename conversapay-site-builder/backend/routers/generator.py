"""Safe AI website generation endpoint."""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import html, json, logging, re
import google.generativeai as genai
from backend.config import settings

logger=logging.getLogger(__name__); router=APIRouter(tags=["website-builder"])
model=None
if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY); model=genai.GenerativeModel("gemini-2.5-flash")

class GenerateRequest(BaseModel):
    prompt:str=Field(...,min_length=10,max_length=1000)
    business_name:str=Field(...,min_length=2,max_length=100)
    industry:str=Field(...,min_length=2,max_length=50)
    vibe:str=Field("modern",pattern="^(minimalist|cyber|luxury|playful|modern)$")
    sections:List[str]=Field(default_factory=lambda:["hero","features","testimonials"])
    business_id:Optional[str]=Field(None,max_length=80)

class GenerateResponse(BaseModel): success:bool; config:Optional[Dict[str,Any]]=None; html:Optional[str]=None; error:Optional[str]=None

def clean_json(text:str)->str:
    text=re.sub(r"```(?:json)?", "", text, flags=re.I).strip(); match=re.search(r"\{.*\}",text,re.S); return match.group(0) if match else text

def esc(value:Any)->str: return html.escape(str(value or ""), quote=True)

def build_prompt(r:GenerateRequest)->str:
    return f"""Return only valid JSON for a landing page. Language: same as prompt. Business: {r.business_name}. Industry: {r.industry}. Vibe: {r.vibe}. Description: {r.prompt}. Sections: {', '.join(r.sections)}. Schema: {{hero:{{headline,subheadline,primaryCTA:{{text,link,style}},secondaryCTA:{{text,link,style}}}},features:[{{title,description}}],products:[{{title,pricePlaceholder,description,features}}],testimonials:[{{quote,author,role}}],theme:{{primaryColor,backgroundColor,fontStack,textColor,secondaryColor}},seo:{{title,description}}}}}"""

def render(data:Dict[str,Any])->str:
    hero=data.get("hero") or {}; theme=data.get("theme") or {}; primary=esc(theme.get("primaryColor","#635bff")); bg=esc(theme.get("backgroundColor","#f7f7f2")); text=esc(theme.get("textColor","#1d2433")); muted=esc(theme.get("secondaryColor","#64748b")); title=esc((data.get("seo") or {}).get("title") or hero.get("headline") or "Generated site")
    features=data.get("features") or []; products=data.get("products") or []; testimonials=data.get("testimonials") or []
    def cards(items, kind):
        out=[]
        for x in items:
            if kind=="feature": out.append(f"<article class='tile'><span class='kicker'>FEATURE</span><h3>{esc(x.get('title'))}</h3><p>{esc(x.get('description'))}</p></article>")
            elif kind=="product": out.append(f"<article class='tile'><h3>{esc(x.get('title'))}</h3><strong>{esc(x.get('pricePlaceholder'))}</strong><p>{esc(x.get('description'))}</p></article>")
            else: out.append(f"<figure class='quote'><blockquote>“{esc(x.get('quote'))}”</blockquote><figcaption>{esc(x.get('author'))}, {esc(x.get('role'))}</figcaption></figure>")
        return ''.join(out)
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>{title}</title><meta name='description' content='{esc((data.get('seo') or {}).get('description'))}'><style>:root{{--p:{primary};--bg:{bg};--t:{text};--m:{muted}}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--t);font:16px system-ui;line-height:1.6}}main{{max-width:1120px;margin:auto;padding:64px 20px}}.hero{{padding:72px 0 84px;max-width:760px}}h1{{font-size:clamp(2.6rem,7vw,5.7rem);line-height:1.02;letter-spacing:-.06em;margin:12px 0 24px}}h2{{font-size:2rem;margin-top:72px}}p{{color:var(--m);max-width:65ch}}.cta{{display:inline-block;background:var(--p);color:white;padding:14px 20px;border-radius:999px;text-decoration:none;font-weight:700;margin-top:18px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px}}.tile,.quote{{padding:24px;border:1px solid color-mix(in srgb,var(--t) 14%,transparent);border-radius:20px;background:color-mix(in srgb,var(--bg) 88%,var(--p))}}.kicker{{font-size:.72rem;letter-spacing:.12em;color:var(--p)}}.quote{{margin:0}}footer{{padding:48px 20px;border-top:1px solid #0002;color:var(--m)}}@media(max-width:600px){{main{{padding-top:32px}}.hero{{padding:40px 0}}}}</style></head><body><main><section class='hero'><span class='kicker'>{esc(hero.get('badge') or 'WELCOME')}</span><h1>{esc(hero.get('headline') or 'A better way to move forward')}</h1><p>{esc(hero.get('subheadline'))}</p><a class='cta' href='{esc((hero.get('primaryCTA') or {}).get('link') or '#contact')}'>{esc((hero.get('primaryCTA') or {}).get('text') or 'Get started')}</a></section>{'<section><h2>What we do</h2><div class="grid">'+cards(features,'feature')+'</div></section>' if features else ''}{'<section><h2>Offerings</h2><div class="grid">'+cards(products,'product')+'</div></section>' if products else ''}{'<section><h2>From our clients</h2><div class="grid">'+cards(testimonials,'quote')+'</div></section>' if testimonials else ''}</main><footer>Built with ConversaPay Site Builder</footer></body></html>"

@router.post("/generate",response_model=GenerateResponse)
async def generate_site(request:GenerateRequest):
    if not model: raise HTTPException(status_code=503,detail="AI service not configured")
    try:
        raw=model.generate_content(build_prompt(request),generation_config={"temperature":0.7,"max_output_tokens":3000})
        data=json.loads(clean_json(raw.text)); return GenerateResponse(success=True,config=data,html=render(data))
    except HTTPException: raise
    except Exception as exc:
        logger.exception("Site generation failed"); raise HTTPException(status_code=500,detail="Failed to generate site")

@router.get("/health")
async def health(): return {"status":"healthy","service":"conversapay-site-builder","ai_enabled":model is not None}
