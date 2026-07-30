"""Talk2Pay API composition root. Delivery lives in backend.routers.frontend."""
from contextlib import asynccontextmanager
import asyncio, logging, asyncpg
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from backend.config import settings
from backend.middleware.correlation import CorrelationIdMiddleware
from backend.middleware.auth_rate_limit import AuthRateLimitMiddleware
from backend.routers import admin, analytics, api_keys, auth, businesses, chat, dashboard, logs, onboarding, orders, payments, products, profile, site_builder, subscription, webhooks, widget, reconciliation
from backend.routers.email_verification import router as email_verification_router
from backend.routers.safe_auth import router as safe_auth_router
from backend.routers.admin_password import router as admin_password_router
from backend.routers.frontend import router as frontend_router
from backend.routers.stripe_webhook import router as stripe_webhook_router
from backend.routers.whatsapp import router as whatsapp_webhook_router
from backend.services.migration_runner import apply_migrations, get_migration_status
from backend.services.monitoring_service import monitoring_service
from backend.services.observability import initialize_error_tracking
from backend.services.whatsapp_security import secure_get_user_profile, secure_update_profile_row

auth_get_user_profile=auth.get_user_profile; auth_update_profile_row=auth.update_profile_row
auth.get_user_profile=lambda user_id: secure_get_user_profile(auth_get_user_profile,auth_update_profile_row,user_id)
auth.update_profile_row=lambda user_id,changes,select_fields="*": secure_update_profile_row(auth_update_profile_row,user_id,changes,select_fields)
logger=logging.getLogger(__name__)
@asynccontextmanager
async def lifespan(_:FastAPI):
    monitoring_service.initialize(); initialize_error_tracking(); asyncio.create_task(_run_migrations_background()); yield
async def _run_migrations_background():
    try: await apply_migrations()
    except Exception: logger.exception("Background database migrations failed")
app=FastAPI(title="Talk2Pay API",version="2.5.0",lifespan=lifespan,docs_url=None if settings.is_production else "/docs",redoc_url=None if settings.is_production else "/redoc")
class DualCORSMiddleware(BaseHTTPMiddleware):
    PUBLIC_PREFIXES=(f"{settings.API_PREFIX}/chat",f"{settings.API_PREFIX}/widget",f"{settings.API_PREFIX}/webhooks/",f"{settings.API_PREFIX}/orders/",f"{settings.API_PREFIX}/site-builder/")
    ALLOWED_METHODS="GET,POST,PUT,PATCH,DELETE,OPTIONS"; ALLOWED_HEADERS="Content-Type,Authorization,X-Builder-Token,X-Widget-Key,X-Webhook-Signature,X-Correlation-ID"
    async def dispatch(self,request:Request,call_next):
        origin=request.headers.get("origin"); public=request.url.path.startswith(self.PUBLIC_PREFIXES); allowed=bool(origin and origin in settings.cors_origins_list)
        if request.method=="OPTIONS":
            if not public and not allowed:return Response(status_code=403)
            response=Response(status_code=204)
        else: response=await call_next(request)
        if public:response.headers["Access-Control-Allow-Origin"]="*"
        elif allowed:response.headers.update({"Access-Control-Allow-Origin":origin,"Access-Control-Allow-Credentials":"true"})
        if request.method=="OPTIONS":response.headers.update({"Access-Control-Allow-Methods":self.ALLOWED_METHODS,"Access-Control-Allow-Headers":self.ALLOWED_HEADERS,"Access-Control-Max-Age":"600"})
        response.headers.append("Vary","Origin"); return response
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    CSP="; ".join(("default-src 'self'","base-uri 'self'","object-src 'none'","frame-ancestors 'self'","form-action 'self'","img-src 'self' data: https:","font-src 'self' data: https://fonts.gstatic.com","style-src 'self' 'unsafe-inline' https://fonts.googleapis.com","script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net","connect-src 'self' https://*.supabase.co wss://*.supabase.co","upgrade-insecure-requests"))
    async def dispatch(self,request:Request,call_next):
        response=await call_next(request)
        for key,value in (("Content-Security-Policy",self.CSP),("Cross-Origin-Opener-Policy","same-origin"),("Permissions-Policy","camera=(), microphone=(), geolocation=(), payment=()"),("Referrer-Policy","strict-origin-when-cross-origin"),("X-Content-Type-Options","nosniff"),("X-Frame-Options","SAMEORIGIN")):response.headers.setdefault(key,value)
        if settings.is_production:response.headers.setdefault("Strict-Transport-Security","max-age=31536000; includeSubDomains")
        return response
app.add_middleware(CorrelationIdMiddleware); app.add_middleware(AuthRateLimitMiddleware); app.add_middleware(DualCORSMiddleware); app.add_middleware(SecurityHeadersMiddleware)
@app.get("/health",include_in_schema=False)
async def health():
    status=get_migration_status()
    if status in {"pending","in_progress","failed"}: return JSONResponse(status_code=503,content={"status":"not_ready","version":"2.5.0","environment":settings.ENVIRONMENT,"checks":{"migrations":status}})
    return {"status":"healthy","version":"2.5.0","environment":settings.ENVIRONMENT,"checks":{"migrations":status}}
async def _check_database():
    if not settings.DATABASE_URL: raise RuntimeError("DATABASE_URL is not configured")
    connection=await asyncpg.connect(settings.DATABASE_URL,timeout=3)
    try: await connection.execute("SELECT 1")
    finally: await connection.close()
async def _check_redis():
    if not settings.REDIS_URL:return
    import redis.asyncio as redis_async
    client=redis_async.from_url(settings.REDIS_URL,socket_connect_timeout=2,socket_timeout=2)
    try: await asyncio.wait_for(client.ping(),timeout=3)
    finally: await client.aclose()
@app.get("/ready",include_in_schema=False)
async def readiness():
    migration_status=get_migration_status(); checks={"database":"ok","redis":"skipped" if not settings.REDIS_URL else "ok","migrations":migration_status}; failures={}
    if migration_status in {"pending","in_progress","failed"}: failures["migrations"]=migration_status
    try: await _check_database()
    except Exception as exc: checks["database"]="failed"; failures["database"]=str(exc); logger.error("Readiness database check failed: %s",exc)
    if settings.REDIS_URL:
        try: await _check_redis()
        except Exception as exc: checks["redis"]="failed"; failures["redis"]=str(exc); logger.error("Readiness Redis check failed: %s",exc)
    if failures:return JSONResponse(status_code=503,content={"status":"not_ready","environment":settings.ENVIRONMENT,"checks":checks,"failures":failures})
    return {"status":"ready","environment":settings.ENVIRONMENT,"checks":checks}
@app.get(f"{settings.API_PREFIX}/config/public",include_in_schema=False)
async def public_config(): return {"supabase_url":settings.SUPABASE_URL,"supabase_anon_key":settings.SUPABASE_ANON_KEY}
prefix=settings.API_PREFIX
for selected_router,route_prefix,tag in ((onboarding.router,prefix,"authentication-onboarding"),(safe_auth_router,prefix,"authentication"),(email_verification_router,f"{prefix}/auth","authentication"),(auth.router,f"{prefix}/auth","authentication"),(profile.router,f"{prefix}/profile","profile"),(subscription.router,prefix,"subscription"),(businesses.router,prefix,"businesses"),(products.router,prefix,"products"),(chat.router,prefix,"chat"),(orders.router,prefix,"orders"),(payments.router,prefix,"payments"),(reconciliation.router,prefix,"reconciliation"),(logs.router,prefix,"logs"),(webhooks.router,prefix,"webhooks"),(analytics.router,prefix,"analytics"),(widget.router,prefix,"widget"),(dashboard.router,prefix,"dashboard"),(admin.router,prefix,"admin"),(admin_password_router,prefix,"admin-security"),(api_keys.router,prefix,"api-keys"),(site_builder.router,prefix,"site-builder"),(stripe_webhook_router,prefix,"stripe-webhook"),(whatsapp_webhook_router,prefix,"whatsapp-webhook")): app.include_router(selected_router,prefix=route_prefix,tags=[tag])
if not settings.is_production:
    from backend.routers.dev_simulator import router as dev_simulator_router
    app.include_router(dev_simulator_router,prefix=prefix,tags=["dev-simulator"])
app.include_router(frontend_router)
@app.exception_handler(404)
async def api_not_found(_:Request,__): return JSONResponse(status_code=404,content={"error":"Not found","detail":"Not found"})
@app.exception_handler(500)
async def internal_error(_:Request,__): return JSONResponse(status_code=500,content={"error":"Internal server error","detail":"An unexpected error occurred"})
