"""Talk2Pay API composition root. Delivery lives in backend.routers.frontend."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import settings
from backend.middleware.correlation import CorrelationIdMiddleware
from backend.routers import admin, analytics, api_keys, auth, businesses, chat, dashboard, logs, onboarding, orders, payments, products, profile, site_builder, subscription, webhooks, widget
from backend.routers.admin_password import router as admin_password_router
from backend.routers.frontend import router as frontend_router
from backend.routers.stripe_webhook import router as stripe_webhook_router
from backend.routers.whatsapp import router as whatsapp_webhook_router
from backend.services.migration_runner import apply_migrations
from backend.services.monitoring_service import monitoring_service
from backend.services.observability import initialize_error_tracking


@asynccontextmanager
async def lifespan(_: FastAPI):
    monitoring_service.initialize()
    initialize_error_tracking()
    await apply_migrations()
    yield


app = FastAPI(title="Talk2Pay API", version="2.5.0", lifespan=lifespan, docs_url=None if settings.is_production else "/docs", redoc_url=None if settings.is_production else "/redoc")


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
        if settings.is_production:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(DualCORSMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


@app.get("/health", include_in_schema=False)
async def health():
    return {"status": "healthy", "version": "2.5.0", "environment": settings.ENVIRONMENT}


@app.get("/ready", include_in_schema=False)
async def readiness():
    return {"status": "ready", "environment": settings.ENVIRONMENT}


@app.get(f"{settings.API_PREFIX}/config/public", include_in_schema=False)
async def public_config():
    return {"supabase_url": settings.SUPABASE_URL, "supabase_anon_key": settings.SUPABASE_ANON_KEY}


prefix = settings.API_PREFIX
for selected_router, route_prefix, tag in ((onboarding.router, prefix, "authentication-onboarding"), (auth.router, f"{prefix}/auth", "authentication"), (profile.router, f"{prefix}/profile", "profile"), (subscription.router, prefix, "subscription"), (businesses.router, prefix, "businesses"), (products.router, prefix, "products"), (chat.router, prefix, "chat"), (orders.router, prefix, "orders"), (payments.router, prefix, "payments"), (logs.router, prefix, "logs"), (webhooks.router, prefix, "webhooks"), (analytics.router, prefix, "analytics"), (widget.router, prefix, "widget"), (dashboard.router, prefix, "dashboard"), (admin.router, prefix, "admin"), (admin_password_router, prefix, "admin-security"), (api_keys.router, prefix, "api-keys"), (site_builder.router, prefix, "site-builder"), (stripe_webhook_router, prefix, "stripe-webhook"), (whatsapp_webhook_router, prefix, "whatsapp-webhook")):
    app.include_router(selected_router, prefix=route_prefix, tags=[tag])
if not settings.is_production:
    from backend.routers.dev_simulator import router as dev_simulator_router
    app.include_router(dev_simulator_router, prefix=prefix, tags=["dev-simulator"])

app.include_router(frontend_router)


@app.exception_handler(404)
async def api_not_found(_: Request, __):
    return JSONResponse(status_code=404, content={"error": "Not found", "detail": "Not found"})


@app.exception_handler(500)
async def internal_error(_: Request, __):
    return JSONResponse(status_code=500, content={"error": "Internal server error", "detail": "An unexpected error occurred"})
