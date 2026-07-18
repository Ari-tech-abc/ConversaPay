"""
ConversaPay Site Builder - AI-Powered Website Generator
Main FastAPI application with CORS configuration.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

from backend.config import settings
from backend.routers import generator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="ConversaPay Site Builder",
    description="AI-powered website builder using Gemini API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ============================================
# CORS Configuration
# ============================================
# Allow requests from:
# - Main ConversaPay app (production)
# - Local development (localhost)
# - Site builder frontend

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        # Production domains
        "https://conversapay.org",
        "https://www.conversapay.org",
        "https://app.conversapay.org",
        "https://builder.conversapay.org",
        
        # Local development
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:8080",
        "http://localhost:8081",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8080",
        
        # File:// protocol for local testing
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
    expose_headers=["*"],  # Expose all headers
)


# ============================================
# Health Check
# ============================================

@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "conversapay-site-builder",
        "version": "1.0.0"
    }


@app.get("/", tags=["root"])
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to ConversaPay Site Builder API",
        "docs": "/docs",
        "health": "/health"
    }


# ============================================
# Error Handlers
# ============================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "detail": "The requested resource was not found",
            "path": str(request.url.path)
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later."
        }
    )


# ============================================
# Include Routers
# ============================================

app.include_router(
    generator.router,
    prefix="/api/v1/builder",
    tags=["website-builder"]
)


# ============================================
# Startup & Shutdown Events
# ============================================

@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("🚀 ConversaPay Site Builder starting up...")
    logger.info(f"📝 Docs available at: /docs")
    logger.info(f"🔍 Health check at: /health")
    
    # Check if Gemini API is configured
    if settings.GEMINI_API_KEY:
        logger.info("✅ Gemini API configured")
    else:
        logger.warning("⚠️  GEMINI_API_KEY not configured - AI generation will be disabled")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("👋 ConversaPay Site Builder shutting down...")


# ============================================
# Run Application
# ============================================

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8001,  # Different port from main ConversaPay app
        reload=True,
        log_level="info"
    )