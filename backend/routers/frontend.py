"""Crash-proof HTML and static asset delivery."""
from __future__ import annotations

import hmac
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from backend.config import settings

router = APIRouter(tags=["frontend"])
settings.ensure_delivery_directories()

# StaticFiles is mounted only after directories are guaranteed to exist.
router.mount("/static", StaticFiles(directory=settings.static_dir), name="static")
router.mount("/frontend", StaticFiles(directory=settings.frontend_dir), name="frontend")
router.mount("/images", StaticFiles(directory=settings.images_dir), name="images")

FALLBACK_HTML = """<!doctype html><html lang=\"he\" dir=\"rtl\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Talk2Pay</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f4f1f8;color:#211b2b;font:16px system-ui,sans-serif}.box{width:min(620px,calc(100% - 40px));padding:40px;border:1px solid #ddd4e8;border-radius:24px;background:#fff;text-align:center}a{color:#6d42c5;font-weight:700}</style></head><body><main class=\"box\"><h1>Talk2Pay</h1><p>העמוד המבוקש אינו זמין כרגע.</p><a href=\"/\">חזרה לדף הבית</a></main></body></html>"""

COPY_REPLACEMENTS = (("ConversaPay", "Talk2Pay"), ("Production checklist", "רשימת בדיקות לפרודקשן"), ("Developer tools", "כלי פיתוח"), ("Dashboard", "לוח בקרה"), ("DASHBOARD", "לוח בקרה"), ("Billing", "חיוב"), ("Security", "אבטחה"))
BRAND_LOGO_SRC = "/frontend/images/conversapay_logo_whitebg.png"
FAVICON_SRC = "/frontend/images/favicon-32x32.png"


def _safe_html_path(filename: str) -> Path:
    candidate = (settings.html_dir / filename).resolve()
    if candidate.parent != settings.html_dir.resolve() or candidate.suffix.lower() != ".html":
        raise HTTPException(status_code=404, detail="Page not found")
    return candidate


def _normalize_copy(page: str) -> str:
    for source, target in COPY_REPLACEMENTS:
        page = page.replace(source, target)
    return page


def _brand_markup(page: str) -> str:
    page = _normalize_copy(page)
    page = re.sub(r'<a\b[^>]*class=["\'][^>]*\bcp-brand\b[^>]*["\'][^>]*>.*?</a>', lambda match: f'<a class="cp-brand" href="/"><img class="cp-brand-logo" src="{BRAND_LOGO_SRC}" alt="Talk2Pay" width="220" height="38"></a>', page, flags=re.I | re.S)
    if 'rel="icon"' not in page.lower():
        page = page.replace("</head>", f'<link rel="icon" type="image/png" href="{FAVICON_SRC}"></head>', 1)
    return page


def _html_response(filename: str, status_code: int = 200) -> HTMLResponse:
    path = _safe_html_path(filename)
    if not path.is_file():
        return HTMLResponse(FALLBACK_HTML if status_code == 200 else "<h1>404</h1>", status_code=404 if status_code == 200 else status_code)
    return HTMLResponse(_brand_markup(path.read_text(encoding="utf-8")), status_code=status_code, headers={"X-Delivery-Release": "safe-frontend-router"})


def _secret_matches(candidate: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(candidate.encode(), expected.encode())


PAGE_ROUTES = {"/": "home.html", "/home": "home.html", "/dashboard": "dashboard.html", "/dashboard.html": "dashboard.html", "/wordpress": "wordpress.html", "/wordpress.html": "wordpress.html", "/login": "login.html", "/login.html": "login.html", "/register": "register.html", "/register.html": "register.html", "/forgot-password": "forgot-password.html", "/forgot-password.html": "forgot-password.html", "/terms": "terms.html", "/terms.html": "terms.html", "/privacy": "privacy.html", "/privacy.html": "privacy.html", "/pay": "pay.html", "/pay.html": "pay.html", "/payment/success": "success.html", "/payment-success.html": "success.html", "/success": "success.html", "/success.html": "success.html", "/payment/canceled": "canceled.html", "/payment-canceled.html": "canceled.html", "/canceled": "canceled.html", "/canceled.html": "canceled.html", "/upgrade": "upgrade.html", "/upgrade.html": "upgrade.html", "/profile": "profile.html", "/profile.html": "profile.html", "/settings": "settings.html", "/settings.html": "settings.html", "/setup-guide": "setup-guide.html", "/setup-guide.html": "setup-guide.html", "/widget-demo": "widget-demo.html", "/widget-demo.html": "widget-demo.html", "/leads": "leads.html", "/leads.html": "leads.html", "/auth/callback": "auth-callback.html"}


for route, filename in PAGE_ROUTES.items():
    router.add_api_route(route, lambda filename=filename: _html_response(filename), methods=["GET"], include_in_schema=False)


@router.get("/404", include_in_schema=False)
@router.get("/404.html", include_in_schema=False)
async def not_found_page():
    return _html_response("404.html", status_code=404)


@router.get("/conversapay-ui.css", include_in_schema=False)
async def ui_stylesheet():
    path = settings.html_dir / "conversapay-ui.css"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stylesheet not found")
    return FileResponse(path, media_type="text/css")


@router.get("/admin-{secret_path}", include_in_schema=False)
@router.get("/admin-{secret_path}/dashboard", include_in_schema=False)
async def hidden_admin_dashboard(secret_path: str):
    if not _secret_matches(secret_path, settings.ADMIN_SECRET_PATH):
        raise HTTPException(status_code=404, detail="Not found")
    return _html_response("admin-dashboard.html")


@router.get("/admin-{secret_path}/login", include_in_schema=False)
async def hidden_admin_login(secret_path: str):
    if not _secret_matches(secret_path, settings.ADMIN_SECRET_PATH):
        raise HTTPException(status_code=404, detail="Not found")
    return _html_response("admin-login.html")


@router.get("/admin-{secret_path}/change-password", include_in_schema=False)
async def hidden_admin_password(secret_path: str):
    if not _secret_matches(secret_path, settings.ADMIN_SECRET_PATH):
        raise HTTPException(status_code=404, detail="Not found")
    return _html_response("admin-change-password.html")


@router.get("/site-builder", include_in_schema=False)
@router.get("/site-builder.html", include_in_schema=False)
async def site_builder_page():
    path = settings.site_builder_dir / "index.html"
    if not path.is_file():
        return HTMLResponse(FALLBACK_HTML, status_code=404)
    return HTMLResponse(_brand_markup(path.read_text(encoding="utf-8")), headers={"X-Delivery-Release": "safe-frontend-router"})


@router.get("/robots.txt", include_in_schema=False)
async def robots():
    path = settings.static_dir / "robots.txt"
    if not path.is_file():
        return HTMLResponse("User-agent: *\nDisallow:", media_type="text/plain")
    return FileResponse(path, media_type="text/plain")


@router.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    path = settings.static_dir / "sitemap.xml"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Sitemap not found")
    return FileResponse(path, media_type="application/xml")


@router.exception_handler(404)
async def frontend_not_found(_: Request, __: HTTPException):
    return HTMLResponse("<h1>404</h1><p>הדף לא נמצא.</p>", status_code=404)
