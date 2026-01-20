from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()


class ServiceStatus(BaseModel):
    name: str
    healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = Field(description="healthy | degraded | unhealthy")
    version: str
    environment: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: dict[str, bool] = Field(default_factory=dict)
    details: list[ServiceStatus] = Field(default_factory=list)


@router.get("/health/live")
async def liveness_probe():
    """
    MUST be lightweight and ALWAYS return 200 if the process is running.

    This endpoint is intended for Railway/K8s liveness checks.
    Do not perform external checks here (Redis/S3/DB/API), because they can
    cause deploy healthchecks to fail even when the app is fine.
    """
    return {"status": "alive"}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Detailed health endpoint.
    This can include best-effort checks and may return degraded/unhealthy.
    """
    details: list[ServiceStatus] = []

    # Storage check (local path)
    details.append(_check_local_storage())

    # OCR config check (only checks key presence, does not call external API)
    details.append(_check_ocr_config())

    services = {s.name: s.healthy for s in details}

    # Determine overall status
    all_healthy = all(s.healthy for s in details)
    if all_healthy:
        overall = "healthy"
    else:
        # If storage is broken, treat as unhealthy; OCR key missing => degraded
        storage_ok = services.get("storage", False)
        overall = "degraded" if storage_ok else "unhealthy"

    return HealthResponse(
        status=overall,
        version=settings.app_version,
        environment=settings.app_env,
        services=services,
        details=details,
    )


@router.get("/health/ready")
async def readiness_probe():
    """
    Readiness probe.
    Should return 200 only when the app is ready to serve requests.

    We keep it simple: storage must be writable and at least one OCR option is configured.
    """
    storage = _check_local_storage()
    ocr = _check_ocr_config()

    if storage.healthy and ocr.healthy:
        return {"status": "ready"}

    return {
        "status": "not_ready",
        "details": {
            "storage": storage.model_dump(),
            "ocr": ocr.model_dump(),
        },
    }


def _check_local_storage() -> ServiceStatus:
    start = time.time()
    try:
        storage_path = settings.storage_path
        os.makedirs(storage_path, exist_ok=True)

        test_file = os.path.join(storage_path, ".health_check")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(test_file)

        latency = (time.time() - start) * 1000
        return ServiceStatus(name="storage", healthy=True, latency_ms=round(latency, 2))
    except Exception as e:
        latency = (time.time() - start) * 1000
        return ServiceStatus(
            name="storage",
            healthy=False,
            latency_ms=round(latency, 2),
            error=str(e),
        )


def _check_ocr_config() -> ServiceStatus:
    # We only check config presence here; do NOT call external OCR providers.
    has_mistral = bool(settings.mistral_api_key)
    has_deepseek = bool(settings.deepseek_api_key)

    if has_mistral or has_deepseek:
        return ServiceStatus(name="ocr", healthy=True)

    return ServiceStatus(
        name="ocr",
        healthy=False,
        error="No OCR API key configured (set MISTRAL_API_KEY or DEEPSEEK_API_KEY).",
    )
