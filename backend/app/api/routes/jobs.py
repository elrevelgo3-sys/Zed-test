"""
Job management API endpoints.

Handles job status tracking, listing, and cancellation.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    ErrorResponse,
    JobResponse,
    JobStatistics,
    JobStatus,
)
from app.services.job_manager import job_manager

router = APIRouter()


@router.get(
    "/jobs/{job_id}",
    response_model=JobResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
    },
)
async def get_job_status(job_id: str):
    """
    Get the status of a conversion job.

    Returns detailed information about the job including:
    - Current status (pending, processing, completed, failed)
    - Progress percentage
    - Number of pages processed
    - Download URL (when completed)
    - Processing time
    """
    job = await job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found")

    return job


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    status: Optional[JobStatus] = Query(None, description="Filter by job status"),
    limit: int = Query(
        20, ge=1, le=100, description="Maximum number of jobs to return"
    ),
    offset: int = Query(0, ge=0, description="Number of jobs to skip"),
):
    """
    List all jobs with optional filtering.

    Returns a paginated list of jobs, optionally filtered by status.
    Jobs are sorted by creation time (newest first).
    """
    jobs = await job_manager.list_jobs(status=status, limit=limit, offset=offset)

    return jobs


@router.delete(
    "/jobs/{job_id}",
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        409: {
            "model": ErrorResponse,
            "description": "Cannot cancel job in current state",
        },
    },
)
async def cancel_job(job_id: str):
    """
    Cancel a pending or processing job.

    Only jobs in 'pending' or 'processing' status can be cancelled.
    Completed or failed jobs cannot be cancelled.
    """
    job = await job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found")

    if job.status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
        raise HTTPException(
            status_code=409, detail=f"Cannot cancel job in '{job.status}' state"
        )

    success = await job_manager.cancel_job(job_id)

    if success:
        return {
            "job_id": job_id,
            "status": "cancelled",
            "message": "Job has been cancelled",
        }

    raise HTTPException(status_code=500, detail="Failed to cancel job")


@router.get(
    "/jobs/{job_id}/statistics",
    response_model=JobStatistics,
    responses={
        404: {"model": ErrorResponse, "description": "Job not found"},
        400: {"model": ErrorResponse, "description": "Job not completed"},
    },
)
async def get_job_statistics(job_id: str):
    """
    Get detailed statistics for a completed job.

    Returns processing metrics including:
    - Total pages processed
    - Number of pages requiring OCR
    - Elements extracted (paragraphs, headings, etc.)
    - Tables and images found
    - Processing time breakdown
    """
    job = await job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400, detail="Statistics are only available for completed jobs"
        )

    stats = await job_manager.get_job_statistics(job_id)

    if not stats:
        raise HTTPException(status_code=404, detail="Statistics not found for this job")

    return stats


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    """
    Retry a failed job.

    Creates a new job with the same file and settings as the original.
    Only failed jobs can be retried.
    """
    job = await job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found")

    if job.status != JobStatus.FAILED:
        raise HTTPException(status_code=400, detail="Only failed jobs can be retried")

    new_job = await job_manager.retry_job(job_id)

    if not new_job:
        raise HTTPException(status_code=500, detail="Failed to create retry job")

    return {
        "original_job_id": job_id,
        "new_job_id": new_job.job_id,
        "status": new_job.status,
        "message": "Job has been requeued for processing",
    }


@router.delete("/jobs")
async def delete_completed_jobs(
    older_than_hours: int = Query(
        24, ge=1, le=720, description="Delete jobs older than this many hours"
    ),
):
    """
    Delete completed and failed jobs older than specified hours.

    This endpoint is useful for cleanup and freeing storage space.
    Only completed and failed jobs are deleted; pending and processing jobs are preserved.
    """
    deleted_count = await job_manager.cleanup_old_jobs(
        older_than_hours=older_than_hours
    )

    return {
        "deleted_count": deleted_count,
        "message": f"Deleted {deleted_count} jobs older than {older_than_hours} hours",
    }
