import os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from dotenv import load_dotenv
from starlette.middleware.base import BaseHTTPMiddleware
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
from backend.config import settings
from backend.routers import auth, businesses, products, chat, orders, payments, logs, webhooks, analytics, widget, admin, dashboard, api_keys, site_builder, profile
from backend.routers.admin_password import router as admin_password_router
from backend.routers.stripe_webhook import router as stripe_webhook_router
from backend.routers.whatsapp import router as whatsapp_webhook_router
from backend.services.monitoring_service import monitoring_service

@asynccontextmanager
async def lifespan(app):
    monitoring_service.initialize()
    yield

app = FastAPI(title="ConversaPay API", version="2.2.0", lifespan=lifespan, docs_url=None if settings.is_production else "/docs", redoc_url=None if settings.is_production else "/redoc")

class DualCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")
        path = request.url.path
        public = any(path.startswith(x) for x in (f"{settings.API_PREFIX}/chat", f"{settings.API_PREFIX}/widget", f"{settings.API_PREFIX}/webhooks/", f"{settings.API_PREFIX}/orders/", f"{settings.API_PREFIX}/site-builder/verify"))
        if request.method == "OPTIONS":
            response = Response()
            response.headers["Access-Control-Allow-Origin"] = "*" if public else (origin if origin in settings.cors_origins_list else "")
            response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,X-Builder-Token,X-Widget-Key"
            response.headers["Vary"] = "Origin"
            return response
        response = await call_next(request)
        if public:
            response.headers["Access-Control-Allow-Origin"] = "*"
        elif origin in settings.cors_origins_list:
            response.headers.update({"Access-Control-Allow-Origin": origin, "Access-Control-Allow-Credentials": "true"})
        response.headers["Vary"] = "Origin"
        return response

app.add_middleware(DualCORSMiddleware)

@app.get("/health")
async def health(): return {"status": "healthy", "version": "2.2.0", "environment": settings.ENVIRONMENT}

@app.get(f"{settings.API_PREFIX}/config/public")
async def public_config(): return {"supabase_url": settings.SUPABASE_URL, "supabase_anon_key": settings.SUPABASE_ANON_KEY}

prefix = settings.API_PREFIX
for router, route_prefix, tag in [
    (auth.router, f"{prefix}/auth", "authentication"), (profile.router, f"{prefix}/profile", "profile"), (businesses.router, prefix, "businesses"), (products.router, prefix, "products"), (chat.router, prefix, "chat"), (orders.router, prefix, "orders"), (payments.router, prefix, "payments"), (logs.router, prefix, "logs"), (webhooks.router, prefix, "webhooks"), (analytics.router, prefix, "analytics"), (widget.router, prefix, "widget"), (dashboard.router, prefix, "dashboard"), (admin.router, prefix, "admin"), (admin_password_router, prefix, "admin-security"), (api_keys.router, prefix, "api-keys"), (site_builder.router, prefix, "site-builder"), (stripe_webhook_router, prefix, "stripe-webhook"), (whatsapp_webhook_router, prefix, "whatsapp-webhook")
]: app.include_router(router, prefix=route_prefix, tags=[tag])
if not settings.is_production:
    from backend.routers.dev_simulator import router as dev_simulator_router
    app.include_router(dev_simulator_router, prefix=prefix, tags=["dev-simulator"])

current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "backend", "static")
frontend_dir = os.path.join(current_dir, "frontend")
html_dir = os.path.join(frontend_dir, "html")
site_builder_dir = os.path.join(current_dir, "conversapay-site-builder", "frontend")
def _html(name): return os.path.join(html_dir, name)

_admin_secret = settings.ADMIN_SECRET_PATH.strip()

@app.get("/admin-{secret_path}", response_class=HTMLResponse)
@app.get("/admin-{secret_path}/dashboard", response_class=HTMLResponse)
async def serve_admin_dashboard(secret_path: str):
    if not _admin_secret or secret_path != _admin_secret: raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(_html("admin-dashboard.html"))

@app.get("/admin-{secret_path}/login", response_class=HTMLResponse)
async def serve_admin_login(secret_path: str):
    if not _admin_secret or secret_path != _admin_secret: raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(_html("admin-login.html"))

@app.get("/admin-{secret_path}/change-password", response_class=HTMLResponse)
async def serve_admin_change_password(secret_path: str):
    if not _admin_secret or secret_path != _admin_secret: raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(_html("admin-change-password.html"))

app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

@app.get("/conversapay-ui.css")
async def conversapay_ui_stylesheet(): return FileResponse(_html("conversapay-ui.css"), media_type="text/css")
@app.get("/")
async def root(): return FileResponse(_html("home.html"))
@app.get("/dashboard")
@app.get("/dashboard.html")
async def dashboard_page():
    with open(_html("dashboard.html"), "r", encoding="utf-8") as dashboard_file: page = dashboard_file.read()
    wordpress_link = '<a class="nav-pill" href="/wordpress" aria-label="פתיחת מסך תפעול WordPress">WordPress</a>'
    if wordpress_link not in page and "</nav>" in page: page = page.replace("</nav>", f"{wordpress_link}</nav>", 1)
    style_link = '<link rel="stylesheet" href="/frontend/html/saas-overrides.css">'
    if style_link not in page: page = page.replace('</head>', f'{style_link}</head>', 1)
    return HTMLResponse(page)
@app.get("/wordpress")
@app.get("/wordpress.html")
async def wordpress_operations_page(): return FileResponse(_html("wordpress.html"))
@app.get("/login")
@app.get("/login.html")
async def login_page(): return FileResponse(_html("login.html"))
@app.get("/register")
@app.get("/register.html")
async def register_page(): return FileResponse(_html("register.html"))
@app.get("/forgot-password")
@app.get("/forgot-password.html")
async def forgot_password_page(): return FileResponse(_html("forgot-password.html"))
@app.get("/terms")
@app.get("/terms.html")
async def terms_page(): return FileResponse(_html("terms.html"))
@app.get("/privacy")
@app.get("/privacy.html")
async def privacy_page(): return FileResponse(_html("privacy.html"))
@app.get("/404")
@app.get("/404.html")
async def not_found_page(): return FileResponse(_html("404.html"), status_code=404)
@app.get("/pay")
@app.get("/pay.html")
async def pay_page(): return FileResponse(_html("pay.html"))
@app.get("/payment/success")
@app.get("/payment-success.html")
@app.get("/success")
@app.get("/success.html")
async def payment_success_page(): return FileResponse(_html("success.html"))
@app.get("/payment/canceled")
@app.get("/payment-canceled.html")
@app.get("/canceled")
@app.get("/canceled.html")
async def payment_canceled_page(): return FileResponse(_html("canceled.html"))
@app.get("/upgrade")
@app.get("/upgrade.html")
async def upgrade_page(): return FileResponse(_html("upgrade.html"))
@app.get("/profile")
@app.get("/profile.html")
async def profile_page(): return FileResponse(_html("profile.html"))
@app.get("/settings")
@app.get("/settings.html")
async def settings_page(): return FileResponse(_html("settings.html"))

if _admin_secret:
    @app.get("/admin")
    @app.get("/admin.html")
    async def admin_page_hidden(): raise HTTPException(status_code=404, detail="Not found")
    @app.get("/admin/login")
    @app.get("/admin-login.html")
    async def admin_login_page_hidden(): raise HTTPException(status_code=404, detail="Not found")
    @app.get("/admin/change-password")
    @app.get("/admin-change-password.html")
    async def admin_change_password_page_hidden(): raise HTTPException(status_code=404, detail="Not found")
    @app.get("/admin/{path:path}")
    async def admin_catchall_hidden(path: str): raise HTTPException(status_code=404, detail="Not found")
else:
    @app.get("/admin")
    @app.get("/admin.html")
    async def admin_page(): return FileResponse(_html("admin-dashboard.html"))
    @app.get("/admin/login")
    @app.get("/admin-login.html")
    async def admin_login_page(): return FileResponse(_html("admin-login.html"))
    @app.get("/admin/change-password")
    @app.get("/admin-change-password.html")
    async def admin_change_password_page(): return FileResponse(_html("admin-change-password.html"))
@app.get("/setup-guide")
@app.get("/setup-guide.html")
async def setup_guide_page(): return FileResponse(_html("setup-guide.html"))
@app.get("/widget-demo")
@app.get("/widget-demo.html")
async def widget_demo_page(): return FileResponse(_html("widget-demo.html"))
@app.get("/auth/callback")
async def auth_callback_page(): return FileResponse(_html("auth-callback.html"))
@app.get("/site-builder")
@app.get("/site-builder.html")
async def site_builder_page(): return FileResponse(os.path.join(site_builder_dir, "index.html"))
@app.get("/robots.txt")
async def robots(): return FileResponse(os.path.join(static_dir, "robots.txt"), media_type="text/plain")
@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap(): return FileResponse(os.path.join(static_dir, "sitemap.xml"), media_type="application/xml")

@app.exception_handler(404)
async def not_found(request: Request, exc):
    if "text/html" in request.headers.get("accept", ""):
        return FileResponse(_html("404.html"), status_code=404)
    return JSONResponse(status_code=404, content={"error":"Not found","detail":str(exc.detail) if hasattr(exc,'detail') else "Not found"})

@app.exception_handler(500)
async def internal_error(request, exc): return JSONResponse(status_code=500, content={"error":"Internal server error","detail":"An unexpected error occurred"})
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT",8000)), reload=settings.DEBUG)
