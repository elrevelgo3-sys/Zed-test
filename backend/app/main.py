"""
PDF to DOCX Converter - Main Application
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import convert, download, health, jobs
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print(f"🚀 Starting PDF to DOCX Converter API")
    print(f"📁 Storage type: {settings.storage_type}")
    print(f"🔧 Environment: {settings.app_env}")

    yield

    # Shutdown
    print("👋 Shutting down...")


app = FastAPI(
    title="PDF to DOCX Converter API",
    description="AI-powered PDF to DOCX converter with OCR support",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(convert.router, prefix="/api/v1", tags=["Convert"])
app.include_router(jobs.router, prefix="/api/v1", tags=["Jobs"])
app.include_router(download.router, prefix="/api/v1", tags=["Download"])


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc)
            if settings.app_debug
            else "An unexpected error occurred",
        },
    )


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "PDF to DOCX Converter API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
