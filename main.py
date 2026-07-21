"""
ConversaPay - Multi-Tenant SaaS Platform
Main application entry point with modular architecture
"""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Import routers and services
from backend.config import settings
from backend.routers import auth, businesses, products, chat, orders, payments, logs, webhooks, analytics, widget
from backend.routers.payme_webhook import router as payme_webhook_router
from backend.routers.whatsapp import router as whatsapp_webhook_router
from backend.services.monitoring_service import monitoring_service

# Conditionally import the dev simulator router (never in production)
if not settings.is_production:
    from backend.routers.dev_simulator import router as dev_simulator_router
    logger.warning("⚠️  Development simulator router loaded - DO NOT RUN IN PRODUCTION")
else:
    dev_simulator_router = None


# ============================================
# Application Lifecycle
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown events.
    """
    # Startup
    logger.info("🚀 Starting ConversaPay Backend v2.0.0")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    
    # Initialize monitoring
    monitoring_service.initialize()
    
    # Validate critical settings
    if not settings.SUPABASE_URL:
        logger.warning("⚠️  SUPABASE_URL not configured")
    if not settings.GEMINI_API_KEY:
        logger.warning("⚠️  GEMINI_API_KEY not configured")
    if not settings.STRIPE_API_KEY:
        logger.warning("⚠️  STRIPE_API_KEY not configured")
    if not settings.RESEND_API_KEY:
        logger.warning("⚠️  RESEND_API_KEY not configured - email notifications disabled")
    if not settings.PAYME_PAY_KEY or not settings.PAYME_SELLER_KEY:
        logger.warning("⚠️  PayMe API keys not configured - PayMe payments disabled")
    
    logger.info("✅ Application startup complete")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down ConversaPay Backend")


# ============================================
# FastAPI Application
# ============================================

# - Widget/customer API: allow any origin (no credentials) for embedded chat on external sites.
from starlette.middleware.base import BaseHTTPMiddleware

class DualCORSMiddleware(BaseHTTPMiddleware):
    """
    Dual-tier CORS middleware:
    - Widget/public endpoints: Allow any origin (*), no credentials
    - Dashboard/admin endpoints: Restrict to configured origins only, allow credentials
    """
    async def dispatch(self, request: Request, call_next):
        origin = request.headers.get("origin")
        path = request.url.path

        # Widget endpoints (public customer-facing) and webhooks
        is_public_endpoint = (
            path.startswith(f"{settings.API_PREFIX}/chat")
            or path.startswith(f"{settings.API_PREFIX}/orders/pay")
            or path.startswith(f"{settings.API_PREFIX}/orders/") and ("/summary" in path or "/status" in path)
            or path.startswith(f"{settings.API_PREFIX}/payments/checkout-session")
            or path.startswith(f"{settings.API_PREFIX}/payments/webhook")
            or path.startswith(f"{settings.API_PREFIX}/webhooks/payme") # PayMe webhook is public
            or path.startswith(f"{settings.API_PREFIX}/webhooks/whatsapp") # WhatsApp webhook is public
            or path.startswith(f"{settings.API_PREFIX}/widget")
        )

        # Handle preflight requests
        if request.method == "OPTIONS":
            response = Response()
            if is_public_endpoint:
                response.headers["Access-Control-Allow-Origin"] = "*"
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
                response.headers["Vary"] = "Origin"
            else:
                if origin and origin in settings.cors_origins_list:
                    response.headers["Access-Control-Allow-Origin"] = origin
                    response.headers["Access-Control-Allow-Credentials"] = "true"
                    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
                    response.headers["Vary"] = "Origin"
            return response

        # Process request
        response = await call_next(request)

        # Add CORS headers to response
        if is_public_endpoint:
            # Allow any origin for public endpoints, no credentials
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Vary"] = "Origin"
        else:
            # Restrict to configured origins for dashboard endpoints
            if origin and origin in settings.cors_origins_list:
                response.headers["Access-Control-Allow-Origin"] = origin
                response.headers["Access-Control-Allow-Credentials"] = "true"
                response.headers["Vary"] = "Origin"

        return response


# ============================================
# FastAPI Application
# ============================================

app = FastAPI(
    title="ConversaPay API",
    description="Multi-tenant SaaS platform for AI-powered sales and customer service",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add DualCORSMiddleware for dual-tier CORS policy
app.add_middleware(DualCORSMiddleware)


# ============================================
# Health Check
# ============================================

@app.get("/health")
async def health_check():
    """
    Health check endpoint.
    """
    return {
        "status": "healthy",
        "version": "2.0.0",
        "environment": settings.ENVIRONMENT
    }


# ============================================
# API Routes
# ============================================

# Include routers
app.include_router(auth.router, prefix=f"{settings.API_PREFIX}/auth", tags=["authentication"])
app.include_router(businesses.router, prefix=f"{settings.API_PREFIX}", tags=["businesses"])
app.include_router(products.router, prefix=f"{settings.API_PREFIX}", tags=["products"])
app.include_router(chat.router, prefix=f"{settings.API_PREFIX}", tags=["chat"])
app.include_router(orders.router, prefix=f"{settings.API_PREFIX}", tags=["orders"])
app.include_router(payments.router, prefix=f"{settings.API_PREFIX}", tags=["payments"])
app.include_router(logs.router, prefix=f"{settings.API_PREFIX}", tags=["logs"])
app.include_router(webhooks.router, prefix=f"{settings.API_PREFIX}", tags=["webhooks"])
app.include_router(analytics.router, prefix=f"{settings.API_PREFIX}", tags=["analytics"])
app.include_router(widget.router, prefix=f"{settings.API_PREFIX}/widget", tags=["widget"])

# Register PayMe webhook router
app.include_router(payme_webhook_router, prefix=f"{settings.API_PREFIX}", tags=["payme-webhook"])

# Register WhatsApp webhook router
app.include_router(whatsapp_webhook_router, prefix=f"{settings.API_PREFIX}", tags=["whatsapp-webhook"])

# Conditionally include the dev simulator router (never in production)
if not settings.is_production and dev_simulator_router is not None:
    app.include_router(dev_simulator_router, prefix=f"{settings.API_PREFIX}", tags=["dev-simulator"])


# ============================================
# Static Files & Frontend Routes
# ============================================

# Get current directory for static files
current_dir = os.path.dirname(os.path.abspath(__file__))

# ── Directory helpers ────────────────────────────────────────────────────────
static_dir   = os.path.join(current_dir, "backend", "static")
frontend_dir = os.path.join(current_dir, "frontend")
html_dir     = os.path.join(frontend_dir, "html")

def _html(name: str) -> str:
    """Return the absolute path to an HTML file inside frontend/html/."""
    return os.path.join(html_dir, name)

# Mount /static  → backend/static  (widget.js, robots.txt, sitemap.xml)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount /frontend → frontend/  (js/, html/ — lets the browser load JS assets)
app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

# ── HTML page routes ─────────────────────────────────────────────────────────

@app.get("/")
async def root_index():
    """Marketing landing page."""
    return FileResponse(_html("home.html"))

@app.get("/dashboard")
@app.get("/dashboard.html")
async def dashboard():
    """Dashboard page."""
    return FileResponse(_html("dashboard.html"))

@app.get("/login")
@app.get("/login.html")
async def login():
    """Login page."""
    return FileResponse(_html("login.html"))

@app.get("/register")
@app.get("/register.html")
async def register():
    """Register page."""
    return FileResponse(_html("register.html"))


# ============================================
# SEO & Utility Routes
# ============================================

@app.get("/robots.txt")
async def robots_txt():
    return FileResponse(
        os.path.join(static_dir, "robots.txt"), media_type="text/plain"
    )

@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    return FileResponse(
        os.path.join(static_dir, "sitemap.xml"), media_type="application/xml"
    )


# ============================================
# Error Handlers
# ============================================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """
    Handle 404 errors.
    """
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "detail": str(exc.detail)}
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """
    Handle 500 errors.
    """
    logger.error(f"Internal server error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": "An unexpected error occurred"}
    )


# ============================================
# Main Entry Point
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    # Dynamic port binding for Render deployment
    port = int(os.getenv("PORT", 8000))
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.DEBUG,
        log_level="info"
    )
