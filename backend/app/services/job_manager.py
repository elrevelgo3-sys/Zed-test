"""
Job Manager - Simplified.
In-memory storage, essential operations only.
"""

import os
import shutil
from datetime import datetime, timedelta
from typing import Optional

from app.config import settings
from app.models.schemas import JobResponse, JobStatistics, JobStatus


class JobManager:
    """Simple job manager with in-memory storage."""

    def __init__(self):
        self._jobs: dict[str, dict] = {}

    async def create_job(
        self,
        job_id: str,
        filename: str,
        file_size: int,
        file_path: str,
        settings_data: dict,
    ) -> JobResponse:
        """Create a new job."""
        now = datetime.utcnow()
        job = {
            "job_id": job_id,
            "status": JobStatus.PENDING,
            "progress": 0,
            "message": "Queued",
            "filename": filename,
            "file_size": file_size,
            "file_path": file_path,
            "pages_total": None,
            "pages_processed": 0,
            "document_type": None,
            "download_url": None,
            "output_path": None,
            "created_at": now,
            "completed_at": None,
            "processing_time_ms": None,
            "settings": settings_data,
        }
        self._jobs[job_id] = job
        return self._to_response(job)

    async def get_job(self, job_id: str) -> Optional[JobResponse]:
        """Get job by ID."""
        job = self._jobs.get(job_id)
        return self._to_response(job) if job else None

    def get_raw_job(self, job_id: str) -> Optional[dict]:
        """Get raw job dict (for internal use)."""
        return self._jobs.get(job_id)

    async def update_job(self, job_id: str, **kwargs) -> Optional[JobResponse]:
        """Update job fields."""
        job = self._jobs.get(job_id)
        if not job:
            return None

        for key, value in kwargs.items():
            if value is not None and key in job:
                job[key] = value

        # Set completed_at for terminal states
        if kwargs.get("status") in [JobStatus.COMPLETED, JobStatus.FAILED]:
            job["completed_at"] = datetime.utcnow()

        return self._to_response(job)

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[JobResponse]:
        """List jobs, newest first."""
        jobs = list(self._jobs.values())

        if status:
            jobs = [j for j in jobs if j["status"] == status]

        jobs.sort(key=lambda j: j["created_at"], reverse=True)
        jobs = jobs[offset : offset + limit]

        return [self._to_response(j) for j in jobs]

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job and its files."""
        if job_id not in self._jobs:
            return False

        # Clean up files
        for folder in ["uploads", "output"]:
            path = os.path.join(settings.storage_path, folder, job_id)
            if os.path.exists(path):
                shutil.rmtree(path, ignore_errors=True)

        del self._jobs[job_id]
        return True

    async def cleanup_old_jobs(self, hours: int = 24) -> int:
        """Delete completed/failed jobs older than X hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        to_delete = []

        for job_id, job in self._jobs.items():
            if job["status"] in [JobStatus.COMPLETED, JobStatus.FAILED]:
                if job["created_at"] < cutoff:
                    to_delete.append(job_id)

        for job_id in to_delete:
            await self.delete_job(job_id)

        return len(to_delete)

    def _to_response(self, job: dict) -> JobResponse:
        """Convert job dict to response model."""
        return JobResponse(
            job_id=job["job_id"],
            status=job["status"],
            progress=job["progress"],
            message=job["message"],
            filename=job["filename"],
            file_size=job["file_size"],
            pages_total=job.get("pages_total"),
            pages_processed=job.get("pages_processed", 0),
            document_type=job.get("document_type"),
            download_url=job.get("download_url"),
            created_at=job["created_at"],
            completed_at=job.get("completed_at"),
            processing_time_ms=job.get("processing_time_ms"),
        )


# Global instance
job_manager = JobManager()
