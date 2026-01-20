"""
Health check endpoints for monitoring and readiness probes.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from datetime import datetime

from app.config import settings


router = APIRouter()


class ServiceStatus(BaseModel):
    """Status of a single service."""
    name: str
    healthy: bool
    latency_ms: float | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = Field(description="Overall health status: healthy, degraded, or unhealthy")
    version: str = Field(description="Application version")
    environment: str = Field(description="Current environment")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: dict[str, bool] = Field(default_factory=dict)
    details: list[ServiceStatus] = Field(default_factory=list)


async def check_redis() -> ServiceStatus:
    """Check Redis connectivity."""
    import time
    try:
        import redis.asyncio as redis
        start = time.time()
        client = redis.from_url(settings.redis_url)
        await client.ping()
        await client.close()
        latency = (time.time() - start) * 1000
        return ServiceStatus(name="redis", healthy=True, latency_ms=round(latency, 2))
    except Exception as e:
        return ServiceStatus(name="redis", healthy=False, error=str(e))


async def check_storage() -> ServiceStatus:
    """Check storage availability."""
    import os
    try:
        if settings.storage_type == "local":
            storage_path = settings.storage_path
            if not os.path.exists(storage_path):
                os.makedirs(storage_path, exist_ok=True)
            # Test write permission
            test_file = os.path.join(storage_path, ".health_check")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return ServiceStatus(name="storage", healthy=True)
        else:
            # S3 storage check would go here
            return ServiceStatus(name="storage", healthy=True)
    except Exception as e:
        return ServiceStatus(name="storage", healthy=False, error=str(e))


async def check_ocr_api() -> ServiceStatus:
    """Check OCR API key configuration."""
    try:
        if settings.mistral_api_key:
            return ServiceStatus(name="ocr_api", healthy=True)
        elif settings.deepseek_api_key:
            return ServiceStatus(name="ocr_api", healthy=True)
        else:
            return ServiceStatus(
                name="ocr_api",
                healthy=False,
                error="No OCR API key configured"
            )
    except Exception as e:
        return ServiceStatus(name="ocr_api", healthy=False, error=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns the health status of the application and its dependencies.
    Used for monitoring and container orchestration health probes.
    """
    # Run all health checks
    redis_status = await check_redis()
    storage_status = await check_storage()
    ocr_status = await check_ocr_api()

    details = [redis_status, storage_status, ocr_status]

    # Build services dict for backward compatibility
    services = {s.name: s.healthy for s in details}

    # Determine overall status
    all_healthy = all(s.healthy for s in details)
    critical_healthy = storage_status.healthy and ocr_status.healthy

    if all_healthy:
        status = "healthy"
    elif critical_healthy:
        status = "degraded"
    else:
        status = "unhealthy"

    return HealthResponse(
        status=status,
        version=settings.app_version,
        environment=settings.app_env,
        services=services,
        details=details,
    )


@router.get("/health/live")
async def liveness_probe():
    """
    Kubernetes liveness probe.

    Returns 200 if the application is running.
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_probe():
    """
    Kubernetes readiness probe.

    Returns 200 if the application is ready to accept traffic.
    """
    # Check critical services
    storage_status = await check_storage()
    ocr_status = await check_ocr_api()

    if storage_status.healthy and ocr_status.healthy:
        return {"status": "ready"}

    from fastapi import HTTPException
    raise HTTPException(
        status_code=503,
        detail="Service not ready"
    )
