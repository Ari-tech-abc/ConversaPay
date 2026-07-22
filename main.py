import os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from dotenv import load_dotenv
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
from backend.config import settings
from backend.routers import auth, businesses, products, chat, orders, payments, logs, webhooks, analytics, widget, admin, dashboard, api_keys, site_builder
from backend.routers.payme_webhook import router as payme_webhook_router
from backend.routers.whatsapp import router as whatsapp_webhook_router
from backend.services.monitoring_service import monitoring_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ConversaPay")
    monitoring_service.initialize()
    yield
    logger.info("Stopping ConversaPay")

app = FastAPI(title="ConversaPay API", version="2.0.0", lifespan=lifespan, docs_url="/docs", redoc_url="/redoc")

class DualCORSMiddleware(CORSMiddleware):
    pass

app.add_middleware(DualCORSMiddleware, allow_origins=settings.cors_origins_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
async def health(): return {"status":"healthy","version":"2.0.0","environment":settings.ENVIRONMENT}

@app.get(f"{settings.API_PREFIX}/config/public")
async def public_config(): return {"supabase_url":settings.SUPABASE_URL,"supabase_anon_key":settings.SUPABASE_ANON_KEY}

prefix = settings.API_PREFIX
app.include_router(auth.router, prefix=f"{prefix}/auth", tags=["authentication"])
app.include_router(businesses.router, prefix=prefix, tags=["businesses"])
app.include_router(products.router, prefix=prefix, tags=["products"])
app.include_router(chat.router, prefix=prefix, tags=["chat"])
app.include_router(orders.router, prefix=prefix, tags=["orders"])
app.include_router(payments.router, prefix=prefix, tags=["payments"])
app.include_router(logs.router, prefix=prefix, tags=["logs"])
app.include_router(webhooks.router, prefix=prefix, tags=["webhooks"])
app.include_router(analytics.router, prefix=prefix, tags=["analytics"])
app.include_router(widget.router, prefix=f"{prefix}/widget", tags=["widget"])
app.include_router(dashboard.router, prefix=f"{prefix}/dashboard", tags=["dashboard"])
app.include_router(admin.router, prefix=f"{prefix}/admin", tags=["admin"])
app.include_router(api_keys.router, prefix=prefix, tags=["api-keys"])
app.include_router(site_builder.router, prefix=prefix, tags=["site-builder"])
app.include_router(payme_webhook_router, prefix=prefix, tags=["payme-webhook"])
app.include_router(whatsapp_webhook_router, prefix=prefix, tags=["whatsapp-webhook"])

if not settings.is_production:
    from backend.routers.dev_simulator import router as dev_simulator_router
    app.include_router(dev_simulator_router, prefix=prefix, tags=["dev-simulator"])

current_dir = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(current_dir, "backend", "static")
frontend_dir = os.path.join(current_dir, "frontend")
html_dir = os.path.join(frontend_dir, "html")
site_builder_dir = os.path.join(current_dir, "conversapay-site-builder", "frontend")

def _html(name): return os.path.join(html_dir, name)
app.mount("/static", StaticFiles(directory=static_dir), name="static")
app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

@app.get("/")
async def root(): return FileResponse(_html("home.html"))
@app.get("/dashboard")
@app.get("/dashboard.html")
async def dashboard_page(): return FileResponse(_html("dashboard.html"))
@app.get("/login")
@app.get("/login.html")
async def login_page(): return FileResponse(_html("login.html"))
@app.get("/register")
@app.get("/register.html")
async def register_page(): return FileResponse(_html("register.html"))
@app.get("/demo")
@app.get("/demo.html")
async def demo_page(): return FileResponse(_html("demo.html"))
@app.get("/pay")
@app.get("/pay.html")
async def pay_page(): return FileResponse(_html("pay.html"))
@app.get("/admin")
@app.get("/admin.html")
async def admin_page(): return FileResponse(_html("admin-dashboard.html"))
@app.get("/admin/login")
@app.get("/admin-login.html")
async def admin_login_page(): return FileResponse(_html("admin-login.html"))
@app.get("/setup-guide")
@app.get("/setup-guide.html")
async def setup_guide_page(): return FileResponse(_html("setup-guide.html"))
@app.get("/auth/callback")
async def auth_callback_page(): return FileResponse(_html("auth-callback.html"))
@app.get("/site-builder")
async def site_builder_page():
    return FileResponse(os.path.join(site_builder_dir, "index.html"))

@app.get("/robots.txt")
async def robots(): return FileResponse(os.path.join(static_dir, "robots.txt"), media_type="text/plain")
@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap(): return FileResponse(os.path.join(static_dir, "sitemap.xml"), media_type="application/xml")

@app.exception_handler(404)
async def not_found(request: Request, exc): return JSONResponse(status_code=404, content={"error":"Not found","detail":str(exc.detail)})
@app.exception_handler(500)
async def internal_error(request: Request, exc):
    logger.error("Internal server error", exc_info=True)
    return JSONResponse(status_code=500, content={"error":"Internal server error","detail":"An unexpected error occurred"})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT",8000)), reload=settings.DEBUG)
