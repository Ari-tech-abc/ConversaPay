import os, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from dotenv import load_dotenv
from starlette.middleware.base import BaseHTTPMiddleware
load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger=logging.getLogger(__name__)
from backend.config import settings
from backend.routers import auth,businesses,products,chat,orders,payments,logs,webhooks,analytics,widget,admin,dashboard,api_keys,site_builder
from backend.routers.payme_webhook import router as payme_webhook_router
from backend.routers.whatsapp import router as whatsapp_webhook_router
from backend.services.monitoring_service import monitoring_service
@asynccontextmanager
async def lifespan(app): monitoring_service.initialize(); yield
app=FastAPI(title="ConversaPay API",version="2.0.0",lifespan=lifespan,docs_url="/docs",redoc_url="/redoc")
class DualCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request,call_next):
        origin=request.headers.get("origin"); path=request.url.path
        public=any(path.startswith(x) for x in (f"{settings.API_PREFIX}/chat",f"{settings.API_PREFIX}/widget",f"{settings.API_PREFIX}/webhooks/",f"{settings.API_PREFIX}/orders/") )
        if request.method=="OPTIONS":
            response=Response(); response.headers["Access-Control-Allow-Origin"]="*" if public else (origin if origin in settings.cors_origins_list else "")
            response.headers["Access-Control-Allow-Methods"]="GET,POST,PUT,PATCH,DELETE,OPTIONS"; response.headers["Access-Control-Allow-Headers"]="Content-Type,Authorization,X-Builder-Token"; response.headers["Vary"]="Origin"; return response
        response=await call_next(request)
        if public: response.headers["Access-Control-Allow-Origin"]="*"
        elif origin in settings.cors_origins_list: response.headers.update({"Access-Control-Allow-Origin":origin,"Access-Control-Allow-Credentials":"true"})
        response.headers["Vary"]="Origin"; return response
app.add_middleware(DualCORSMiddleware)
@app.get("/health")
async def health(): return {"status":"healthy","version":"2.0.0","environment":settings.ENVIRONMENT}
@app.get(f"{settings.API_PREFIX}/config/public")
async def public_config(): return {"supabase_url":settings.SUPABASE_URL,"supabase_anon_key":settings.SUPABASE_ANON_KEY}
prefix=settings.API_PREFIX
for r,p,t in [(auth.router,f"{prefix}/auth","authentication"),(businesses.router,prefix,"businesses"),(products.router,prefix,"products"),(chat.router,prefix,"chat"),(orders.router,prefix,"orders"),(payments.router,prefix,"payments"),(logs.router,prefix,"logs"),(webhooks.router,prefix,"webhooks"),(analytics.router,prefix,"analytics"),(widget.router,f"{prefix}/widget","widget"),(dashboard.router,f"{prefix}/dashboard","dashboard"),(admin.router,f"{prefix}/admin","admin"),(api_keys.router,prefix,"api-keys"),(site_builder.router,prefix,"site-builder"),(payme_webhook_router,prefix,"payme-webhook"),(whatsapp_webhook_router,prefix,"whatsapp-webhook")]: app.include_router(r,prefix=p,tags=[t])
if not settings.is_production:
    from backend.routers.dev_simulator import router as dev_simulator_router
    app.include_router(dev_simulator_router,prefix=prefix,tags=["dev-simulator"])
current_dir=os.path.dirname(os.path.abspath(__file__)); static_dir=os.path.join(current_dir,"backend","static"); frontend_dir=os.path.join(current_dir,"frontend"); html_dir=os.path.join(frontend_dir,"html"); site_builder_dir=os.path.join(current_dir,"conversapay-site-builder","frontend")
def _html(n): return os.path.join(html_dir,n)
app.mount("/static",StaticFiles(directory=static_dir),name="static"); app.mount("/frontend",StaticFiles(directory=frontend_dir),name="frontend")
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
async def site_builder_page(): return FileResponse(os.path.join(site_builder_dir,"index.html"))
@app.get("/robots.txt")
async def robots(): return FileResponse(os.path.join(static_dir,"robots.txt"),media_type="text/plain")
@app.get("/sitemap.xml",include_in_schema=False)
async def sitemap(): return FileResponse(os.path.join(static_dir,"sitemap.xml"),media_type="application/xml")
@app.exception_handler(404)
async def not_found(request,exc): return JSONResponse(status_code=404,content={"error":"Not found","detail":str(exc.detail)})
@app.exception_handler(500)
async def internal_error(request,exc): return JSONResponse(status_code=500,content={"error":"Internal server error","detail":"An unexpected error occurred"})
if __name__=="__main__":
    import uvicorn
    uvicorn.run("main:app",host="0.0.0.0",port=int(os.getenv("PORT",8000)),reload=settings.DEBUG)
