"""
Download API endpoint for retrieving converted files.

Handles secure file downloads for completed conversion jobs.
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse, StreamingResponse

from app.config import settings
from app.models.schemas import ErrorResponse, JobStatus
from app.services.job_manager import job_manager

router = APIRouter()


@router.get(
    "/download/{job_id}",
    responses={
        200: {
            "description": "File download",
            "content": {
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {}
            },
        },
        404: {"model": ErrorResponse, "description": "Job or file not found"},
        400: {"model": ErrorResponse, "description": "Job not completed"},
    },
    summary="Download converted DOCX file",
    description="Download the converted DOCX file for a completed job.",
)
async def download_file(job_id: str):
    """
    Download the converted DOCX file.

    The job must be in 'completed' status to download the file.
    Returns the file with appropriate headers for download.
    """
    # Get job
    job = await job_manager.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail=f"Job with ID '{job_id}' not found",
        )

    # Check job status
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job is not completed. Current status: {job.status}",
        )

    # Get raw job data to access output_path
    raw_job = job_manager.get_raw_job(job_id)
    if not raw_job:
        raise HTTPException(status_code=404, detail="Job data not found")

    output_path = raw_job.get("output_path")

    if not output_path or not os.path.exists(output_path):
        # Try to find the file in the expected location
        output_dir = os.path.join(settings.storage_path, "output", job_id)
        expected_filename = os.path.splitext(job.filename)[0] + ".docx"
        output_path = os.path.join(output_dir, expected_filename)

        if not os.path.exists(output_path):
            raise HTTPException(
                status_code=404,
                detail="Output file not found. It may have been deleted.",
            )

    # Get filename for download
    download_filename = os.path.basename(output_path)

    # Return file response
    return FileResponse(
        path=output_path,
        filename=download_filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f'attachment; filename="{download_filename}"',
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get(
    "/download/{job_id}/info",
    summary="Get download information",
    description="Get information about the downloadable file without downloading it.",
)
async def get_download_info(job_id: str):
    """
    Get information about the downloadable file.

    Returns file size, name, and a direct download URL.
    """
    # Get job
    job = await job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Status: {job.status}",
        )

    # Get raw job data
    raw_job = job_manager.get_raw_job(job_id)
    output_path = raw_job.get("output_path") if raw_job else None

    if not output_path or not os.path.exists(output_path):
        output_dir = os.path.join(settings.storage_path, "output", job_id)
        expected_filename = os.path.splitext(job.filename)[0] + ".docx"
        output_path = os.path.join(output_dir, expected_filename)

    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output file not found")

    # Get file info
    file_stat = os.stat(output_path)
    filename = os.path.basename(output_path)

    return {
        "job_id": job_id,
        "filename": filename,
        "original_filename": job.filename,
        "file_size": file_stat.st_size,
        "file_size_human": _format_file_size(file_stat.st_size),
        "download_url": f"/api/v1/download/{job_id}",
        "created_at": datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
        "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }


@router.head("/download/{job_id}")
async def download_file_head(job_id: str):
    """
    HEAD request for download - returns file info in headers.

    Useful for checking file availability and size before downloading.
    """
    # Get job
    job = await job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed")

    # Get raw job data
    raw_job = job_manager.get_raw_job(job_id)
    output_path = raw_job.get("output_path") if raw_job else None

    if not output_path or not os.path.exists(output_path):
        output_dir = os.path.join(settings.storage_path, "output", job_id)
        expected_filename = os.path.splitext(job.filename)[0] + ".docx"
        output_path = os.path.join(output_dir, expected_filename)

    if not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="File not found")

    file_stat = os.stat(output_path)
    filename = os.path.basename(output_path)

    return Response(
        headers={
            "Content-Length": str(file_stat.st_size),
            "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Accept-Ranges": "bytes",
        }
    )


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
