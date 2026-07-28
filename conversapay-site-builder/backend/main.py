"""Talk2Pay Site Builder API."""
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.config import settings
from backend.routers import generator

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
app = FastAPI(title="Talk2Pay Site Builder", description="Premium AI website builder", version="1.0.0", docs_url="/docs" if settings.DEBUG else None, redoc_url="/redoc" if settings.DEBUG else None)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=False, allow_methods=["POST","GET","OPTIONS"], allow_headers=["Content-Type","X-Builder-Token"], expose_headers=[])
@app.get("/health", tags=["health"])
async def health_check(): return {"status":"healthy","service":"talk2pay-site-builder","version":"1.0.0"}
@app.get("/", tags=["root"])
async def root(): return {"message":"Talk2Pay Site Builder API","health":"/health"}
@app.exception_handler(404)
async def not_found_handler(request, exc): return JSONResponse(status_code=404, content={"error":"Not Found","detail":"The requested resource was not found"})
@app.exception_handler(500)
async def internal_error_handler(request, exc): logger.error("Internal server error: %s", exc, exc_info=True); return JSONResponse(status_code=500, content={"error":"Internal Server Error","detail":"An unexpected error occurred"})
app.include_router(generator.router, prefix="/api/v1/builder", tags=["website-builder"])
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=settings.HOST, port=settings.PORT, reload=settings.RELOAD, log_level=settings.LOG_LEVEL)
