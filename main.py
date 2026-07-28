import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

from backend.config import settings
from backend.middleware.correlation import CorrelationIdMiddleware
from backend.routers import (
    admin,
    analytics,
    api_keys,
    auth,
    businesses,
    chat,
    dashboard,
    logs,
    onboarding,
    orders,
    payments,
    products,
    profile,
    site_builder,
    subscription,
    webhooks,
    widget,
)
from backend.routers.admin_password import router as admin_password_router
from backend.routers.stripe_webhook import router as stripe_webhook_router
from backend.routers.whatsapp import router as whatsapp_webhook_router
from backend.services.monitoring_service import monitoring_service
from backend.services.observability import initialize_error_tracking


@asynccontextmanager
async def lifespan(_: FastAPI):
    monitoring_service.initialize()
    initialize_error_tracking()
    yield


app = FastAPI(title="Talk2Pay API", version="2.3.0", lifespan=lifespan, docs_url=None if settings.is_production else "/docs", redoc_url=None if settings.is_production else "/redoc")


class DualCORSMiddleware(BaseHTTPMiddleware):
    PUBLIC_PREFIXES = (f"{settings.API_PREFIX}/chat", f"{settings.API_PREFIX}/widget", f"{settings.API_PREFIX}/webhooks/", f"{settings.API_PREFIX}/orders/", f"{settings.API_PREFIX}/site-builder/")
    ALLOWED_METHODS = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    ALLOWED_HEADERS = "Content-Type,Authorization,X-Builder-Token,X-Widget-Key,X-Webhook-Signature,X-Correlation-ID"

    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        is_public = request.url.path.startswith(self.PUBLIC_PREFIXES)
        is_allowed_origin = bool(origin and origin in settings.cors_origins_list)
        if request.method == "OPTIONS":
            if not is_public and not is_allowed_origin:
                return Response(status_code=403)
            response = Response(status_code=204)
        else:
            response = await call_next(request)
        if is_public:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif is_allowed_origin:
            response.headers.update({"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true"})
        if request.method == "OPTIONS":
            response.headers.update({"Access-Control-Allow-Methods": self.ALLOWED_METHODS, "Access-Control-Allow-Headers": self.ALLOWED_HEADERS, "Access-Control-Max-Age": "600"})
        response.headers.append("Vary", "Origin")
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    CSP = "; ".join(("default-src 'self'", "base-uri 'self'", "object-src 'none'", "frame-ancestors 'self'", "form-action 'self'", "img-src 'self' data: https:", "font-src 'self' data: https://fonts.gstatic.com", "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com", "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net", "connect-src 'self' https://*.supabase.co wss://*.supabase.co", "upgrade-insecure-requests"))

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", self.CSP)
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        content_type = response.headers.get("content-type", "").lower()
        path = request.url.path
        if path.startswith(settings.API_PREFIX) or "text/html" in content_type:
            response.headers.setdefault("Cache-Control", "no-store")
        elif path.startswith(("/frontend/", "/images/", "/static/")):
            response.headers.setdefault("Cache-Control", "public, max-age=86400, stale-while-revalidate=604800")
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(DualCORSMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "healthy", "version": "2.3.0", "environment": settings.ENVIRONMENT}


@app.get("/ready", include_in_schema=False)
async def readiness():
    return {"status": "ready", "environment": settings.ENVIRONMENT}


@app.get(f"{settings.API_PREFIX}/config/public", include_in_schema=False)
async def public_config():
    return {"supabase_url": settings.SUPABASE_URL, "supabase_anon_key": settings.SUPABASE_ANON_KEY}


prefix = settings.API_PREFIX
for router, route_prefix, tag in ((onboarding.router, prefix, "authentication-onboarding"), (auth.router, f"{prefix}/auth", "authentication"), (profile.router, f"{prefix}/profile", "profile"), (subscription.router, prefix, "subscription"), (businesses.router, prefix, "businesses"), (products.router, prefix, "products"), (chat.router, prefix, "chat"), (orders.router, prefix, "orders"), (payments.router, prefix, "payments"), (logs.router, prefix, "logs"), (webhooks.router, prefix, "webhooks"), (analytics.router, prefix, "analytics"), (widget.router, prefix, "widget"), (dashboard.router, prefix, "dashboard"), (admin.router, prefix, "admin"), (admin_password_router, prefix, "admin-security"), (api_keys.router, prefix, "api-keys"), (site_builder.router, prefix, "site-builder"), (stripe_webhook_router, prefix, "stripe-webhook"), (whatsapp_webhook_router, prefix, "whatsapp-webhook")):
    app.include_router(router, prefix=route_prefix, tags=[tag])
if not settings.is_production:
    from backend.routers.dev_simulator import router as dev_simulator_router
    app.include_router(dev_simulator_router, prefix=prefix, tags=["dev-simulator"])

ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "backend" / "static"
FRONTEND_DIR = ROOT_DIR / "frontend"
HTML_DIR = FRONTEND_DIR / "html"
IMAGES_DIR = FRONTEND_DIR / "images"
SITE_BUILDER_DIR = ROOT_DIR / "conversapay-site-builder" / "frontend"
ADMIN_SECRET = settings.ADMIN_SECRET_PATH.strip()
BRAND_LOGO_SRC = "/frontend/images/conversapay_logo_whitebg.png"
FAVICON_SRC = "/frontend/images/favicon-32x32.png"
DESIGN_SYSTEM_LINK = '<link rel="stylesheet" href="/frontend/html/design-system.css">'
LANDING_FIXES_LINK = '<link rel="stylesheet" href="/frontend/html/landing-fixes.css">'
APPLE_POLISH_LINK = '<link rel="stylesheet" href="/frontend/html/apple-ready-polish.css">'
BRANDING_STYLE = '<style id="talk2pay-branding">.cp-brand,.brand,.legal-header>a{display:inline-flex;align-items:center;min-height:38px}.cp-brand-logo,.brand-logo,.legal-header .cp-brand-logo{display:block;width:auto;height:38px;max-width:min(220px,55vw);object-fit:contain}@media(max-width:760px){.cp-brand-logo,.brand-logo,.legal-header .cp-brand-logo{height:32px;max-width:180px}}</style>'

COPY_REPLACEMENTS = (
    ("ConversaPay", "Talk2Pay"),
    ("LIVE CANVAS", "קנבס חי"),
    ("Production checklist", "רשימת בדיקות לפרודקשן"),
    ("Developer tools", "כלי פיתוח"),
    ("Admin session", "סשן מנהל"),
    ("Session protected", "הסשן מוגן"),
    ("Requires action", "נדרשת פעולה"),
    ("Moderate risk", "סיכון בינוני"),
    ("High risk", "סיכון גבוה"),
    ("Critical reports", "דוחות קריטיים"),
    ("Blocked present", "קיימים חסומים"),
    ("Under control", "בשליטה"),
    ("Protected", "מוגן"),
    ("Stable", "יציב"),
    ("Checking", "בודק"),
    ("Calculating", "מחשב"),
    ("Ready", "מוכן"),
    ("Clear", "נקי"),
    ("Role:", "תפקיד:"),
    ("Traffic", "תעבורה"),
    ("Businesses", "עסקים"),
    ("Flagged", "מסומנים"),
    ("Reports", "דוחות"),
    ("Dashboard", "לוח בקרה"),
    ("DASHBOARD", "לוח בקרה"),
    ("Billing", "חיוב"),
    ("Security", "אבטחה"),
    ("Tier", "מסלול"),
    ("Custom HTML", "HTML מותאם אישית"),
    ("Minimal", "מינימלי"),
    ("Luxury", "יוקרתי"),
    ("Playful", "משחקי"),
)


def normalize_copy(page: str) -> str:
    """Apply the canonical Talk2Pay product vocabulary at the delivery boundary."""
    for source, target in COPY_REPLACEMENTS:
        page = page.replace(source, target)
    return page


def html_path(name: str) -> Path:
    path = (HTML_DIR / name).resolve()
    if path.parent != HTML_DIR.resolve():
        raise ValueError("Invalid HTML path")
    return path


def brand_markup(page: str) -> str:
    page = normalize_copy(page)

    def replace_cp_brand(match: re.Match) -> str:
        tag = match.group(0)
        href_match = re.search(r'href=["\']([^"\']+)', tag, re.IGNORECASE)
        href = href_match.group(1) if href_match else "/"
        return f'<a class="cp-brand" href="{href}"><img class="cp-brand-logo" src="{BRAND_LOGO_SRC}" alt="Talk2Pay" width="220" height="38"></a>'

    page = re.sub(r'<a\b[^>]*class=["\'][^>]*\bcp-brand\b[^>]*["\'][^>]*>.*?</a>', replace_cp_brand, page, flags=re.IGNORECASE | re.DOTALL)
    page = re.sub(r'<a\b(?P<attrs>[^>]*class=["\'][^>]*\bbrand\b[^>]*["\'][^>]*)>\s*Talk2Pay\s*</a>', lambda match: f'<a{match.group("attrs")}><img class="brand-logo" src="{BRAND_LOGO_SRC}" alt="Talk2Pay" width="220" height="38"></a>', page, flags=re.IGNORECASE | re.DOTALL)
    page = re.sub(r'(<header\b[^>]*class=["\'][^>]*\blegal-header\b[^>]*["\'][^>]*>\s*)<a\s+href=["\']/["\']>\s*Talk2Pay\s*</a>', lambda match: f'{match.group(1)}<a href="/"><img class="cp-brand-logo" src="{BRAND_LOGO_SRC}" alt="Talk2Pay" width="220" height="38"></a>', page, flags=re.IGNORECASE | re.DOTALL)
    if 'rel="icon"' not in page.lower():
        page = page.replace("</head>", f'<link rel="icon" type="image/png" href="{FAVICON_SRC}">\n</head>', 1)
    for link in (DESIGN_SYSTEM_LINK, APPLE_POLISH_LINK):
        if link not in page:
            page = page.replace("</head>", f"{link}</head>", 1)
    if 'class="home-page"' in page and LANDING_FIXES_LINK not in page:
        page = page.replace("</head>", f"{LANDING_FIXES_LINK}</head>", 1)
    if 'id="talk2pay-branding"' not in page:
        page = page.replace("</head>", f"{BRANDING_STYLE}</head>", 1)
    return page


def branded_file(path: Path, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(brand_markup(path.read_text(encoding="utf-8")), status_code=status_code, headers={"X-ConversaPay-Release": "apple-ready-polish"})


@app.get("/admin-{secret_path}", response_class=HTMLResponse)
@app.get("/admin-{secret_path}/dashboard", response_class=HTMLResponse)
async def serve_admin_dashboard(secret_path: str):
    if not ADMIN_SECRET or not secrets_match(secret_path, ADMIN_SECRET):
        raise HTTPException(status_code=404, detail="Not found")
    page = html_path("admin-dashboard.html").read_text(encoding="utf-8").replace('href="/admin-change-password.html"', 'href="change-password"')
    return HTMLResponse(brand_markup(page), headers={"X-ConversaPay-Release": "apple-ready-polish"})


def secrets_match(candidate: str, expected: str) -> bool:
    import hmac
    return hmac.compare_digest(candidate.encode(), expected.encode())


@app.get("/admin-{secret_path}/login", response_class=HTMLResponse)
async def serve_admin_login(secret_path: str):
    if not ADMIN_SECRET or not secrets_match(secret_path, ADMIN_SECRET):
        raise HTTPException(status_code=404, detail="Not found")
    return branded_file(html_path("admin-login.html"))


@app.get("/admin-{secret_path}/change-password", response_class=HTMLResponse)
async def serve_admin_change_password(secret_path: str):
    if not ADMIN_SECRET or not secrets_match(secret_path, ADMIN_SECRET):
        raise HTTPException(status_code=404, detail="Not found")
    return branded_file(html_path("admin-change-password.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")
app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@app.get("/conversapay-ui.css", include_in_schema=False)
async def conversapay_ui_stylesheet():
    return FileResponse(html_path("conversapay-ui.css"), media_type="text/css")


@app.get("/")
async def root():
    return branded_file(html_path("home.html"))


@app.get("/dashboard")
@app.get("/dashboard.html")
async def dashboard_page():
    page = html_path("dashboard.html").read_text(encoding="utf-8")
    navigation_links = (
        '<a class="nav-pill" href="/wordpress" aria-label="פתיחת מסך תפעול WordPress">WordPress</a>',
        '<a class="nav-pill" href="/leads" aria-label="פתיחת תיבת הפניות">פניות</a>',
    )
    for link in navigation_links:
        if link not in page and "</nav>" in page:
            page = page.replace("</nav>", f"{link}</nav>", 1)
    additions = (DESIGN_SYSTEM_LINK, APPLE_POLISH_LINK, '<script src="/frontend/js/business-onboarding.js" defer></script>', '<script src="/frontend/js/premium-builder-link.js" defer></script>')
    for addition in additions:
        if addition not in page:
            page = page.replace("</head>", f"{addition}</head>", 1)
    return HTMLResponse(brand_markup(page), headers={"X-ConversaPay-Release": "apple-ready-polish"})


PAGE_ROUTES = {"/wordpress": "wordpress.html", "/wordpress.html": "wordpress.html", "/login": "login.html", "/login.html": "login.html", "/register": "register.html", "/register.html": "register.html", "/forgot-password": "forgot-password.html", "/forgot-password.html": "forgot-password.html", "/terms": "terms.html", "/terms.html": "terms.html", "/privacy": "privacy.html", "/privacy.html": "privacy.html", "/pay": "pay.html", "/pay.html": "pay.html", "/payment/success": "success.html", "/payment-success.html": "success.html", "/success": "success.html", "/success.html": "success.html", "/payment/canceled": "canceled.html", "/payment-canceled.html": "canceled.html", "/canceled": "canceled.html", "/canceled.html": "canceled.html", "/upgrade": "upgrade.html", "/upgrade.html": "upgrade.html", "/profile": "profile.html", "/profile.html": "profile.html", "/settings": "settings.html", "/settings.html": "settings.html", "/setup-guide": "setup-guide.html", "/setup-guide.html": "setup-guide.html", "/widget-demo": "widget-demo.html", "/widget-demo.html": "widget-demo.html", "/leads": "leads.html", "/leads.html": "leads.html", "/auth/callback": "auth-callback.html"}


def make_page_handler(filename: str):
    async def page_handler():
        return branded_file(html_path(filename))
    return page_handler


for route, filename in PAGE_ROUTES.items():
    app.add_api_route(route, make_page_handler(filename), methods=["GET"], include_in_schema=False)


@app.get("/404")
@app.get("/404.html")
async def not_found_page():
    return branded_file(html_path("404.html"), status_code=404)


if ADMIN_SECRET:
    @app.get("/admin")
    @app.get("/admin.html")
    @app.get("/admin/login")
    @app.get("/admin-login.html")
    @app.get("/admin/change-password")
    @app.get("/admin-change-password.html")
    async def admin_hidden():
        raise HTTPException(status_code=404, detail="Not found")

    @app.get("/admin/{path:path}")
    async def admin_catchall_hidden(path: str):
        raise HTTPException(status_code=404, detail="Not found")
else:
    @app.get("/admin")
    @app.get("/admin.html")
    async def admin_page():
        return branded_file(html_path("admin-dashboard.html"))

    @app.get("/admin/login")
    @app.get("/admin-login.html")
    async def admin_login_page():
        return branded_file(html_path("admin-login.html"))

    @app.get("/admin/change-password")
    @app.get("/admin-change-password.html")
    async def admin_change_password_page():
        return branded_file(html_path("admin-change-password.html"))


@app.get("/site-builder")
@app.get("/site-builder.html")
async def site_builder_page():
    return branded_file(SITE_BUILDER_DIR / "index.html")


@app.get("/robots.txt", include_in_schema=False)
async def robots():
    return FileResponse(STATIC_DIR / "robots.txt", media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap():
    return FileResponse(STATIC_DIR / "sitemap.xml", media_type="application/xml")


@app.exception_handler(404)
async def not_found(request: Request, exc: HTTPException):
    if "text/html" in request.headers.get("accept", ""):
        return branded_file(html_path("404.html"), status_code=404)
    return JSONResponse(status_code=404, content={"error": "Not found", "detail": "Not found"})


@app.exception_handler(500)
async def internal_error(_: Request, exc: Exception):
    logger.exception("Unhandled error", exc_info=exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": "An unexpected error occurred"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", "8000")), reload=settings.DEBUG)
