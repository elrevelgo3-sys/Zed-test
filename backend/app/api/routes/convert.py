"""
PDF Conversion API - Simplified.
Sync processing for small files (<20 pages), async for larger.
"""

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import settings
from app.models.schemas import ConvertResponse, JobStatus, OCRProvider
from app.services.job_manager import job_manager

router = APIRouter()

# Threshold for sync vs async processing
SYNC_PAGE_LIMIT = 20


def generate_job_id() -> str:
    return str(uuid.uuid4())[:12]


async def save_file(file: UploadFile, job_id: str) -> tuple[str, bytes]:
    """Save uploaded file and return path + content."""
    upload_dir = os.path.join(settings.storage_path, "uploads", job_id)
    os.makedirs(upload_dir, exist_ok=True)

    filename = file.filename or "document.pdf"
    # Sanitize filename
    filename = filename.replace("/", "_").replace("\\", "_")[:200]
    file_path = os.path.join(upload_dir, filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    return file_path, content


@router.post("/convert", response_model=ConvertResponse)
async def convert_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    ocr_enabled: bool = Form(default=True),
    ocr_provider: str = Form(default="auto"),
    language: str = Form(default="auto"),
):
    """
    Convert PDF to DOCX.

    Small files (<20 pages): processed immediately, DOCX returned in response.
    Large files: queued for background processing.
    """
    # Validate file
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    content = await file.read()

    # Check magic bytes
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "Invalid PDF file")

    # Check file size
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(413, f"File too large. Max: {settings.max_file_size_mb}MB")

    await file.seek(0)

    # Generate job ID and save file
    job_id = generate_job_id()
    file_path, _ = await save_file(file, job_id)

    # Quick page count check
    page_count = await get_page_count(file_path)

    # Create job record
    job = await job_manager.create_job(
        job_id=job_id,
        filename=file.filename,
        file_size=len(content),
        file_path=file_path,
        settings={
            "ocr_enabled": ocr_enabled,
            "ocr_provider": ocr_provider,
            "language": language,
        },
    )

    # Small file: process synchronously
    if page_count <= SYNC_PAGE_LIMIT:
        try:
            result = await process_pdf(job_id)
            if result["success"]:
                return ConvertResponse(
                    job_id=job_id,
                    status=JobStatus.COMPLETED,
                    message=f"Converted {page_count} pages in {result['time_ms']}ms",
                )
        except Exception as e:
            # On error, fall back to showing error
            await job_manager.update_job(
                job_id, status=JobStatus.FAILED, message=str(e)
            )
            raise HTTPException(500, f"Conversion failed: {str(e)}")

    # Large file: background processing
    background_tasks.add_task(process_pdf, job_id)

    return ConvertResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message=f"Processing {page_count} pages in background...",
    )


@router.post("/convert/batch")
async def batch_convert(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    ocr_enabled: bool = Form(default=True),
    language: str = Form(default="auto"),
):
    """
    Batch convert multiple PDFs (max 5).
    All files are processed in background.
    """
    if len(files) > 5:
        raise HTTPException(400, "Maximum 5 files per batch")

    results = []

    for file in files:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            results.append(
                {"filename": file.filename, "success": False, "error": "Not a PDF"}
            )
            continue

        try:
            content = await file.read()
            if not content.startswith(b"%PDF"):
                results.append(
                    {
                        "filename": file.filename,
                        "success": False,
                        "error": "Invalid PDF",
                    }
                )
                continue

            if len(content) > settings.max_file_size_bytes:
                results.append(
                    {"filename": file.filename, "success": False, "error": "Too large"}
                )
                continue

            await file.seek(0)

            job_id = generate_job_id()
            file_path, _ = await save_file(file, job_id)

            await job_manager.create_job(
                job_id=job_id,
                filename=file.filename,
                file_size=len(content),
                file_path=file_path,
                settings={"ocr_enabled": ocr_enabled, "language": language},
            )

            background_tasks.add_task(process_pdf, job_id)
            results.append(
                {"filename": file.filename, "success": True, "job_id": job_id}
            )

        except Exception as e:
            results.append(
                {"filename": file.filename, "success": False, "error": str(e)}
            )

    success_count = sum(1 for r in results if r.get("success"))
    return {
        "message": f"Queued {success_count}/{len(files)} files",
        "results": results,
    }


async def get_page_count(file_path: str) -> int:
    """Quick page count without full analysis."""
    try:
        import fitz

        doc = fitz.open(file_path)
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 999  # Assume large on error


async def process_pdf(job_id: str) -> dict:
    """
    Process a PDF conversion job.
    Returns result dict with success status.
    """
    import time

    from app.services.docx_service import DOCXService
    from app.services.ocr.factory import get_ocr_provider
    from app.services.pdf_service import PDFService

    start = time.time()
    job = job_manager.get_raw_job(job_id)

    if not job:
        return {"success": False, "error": "Job not found"}

    try:
        # Update status
        await job_manager.update_job(
            job_id, status=JobStatus.PROCESSING, message="Analyzing PDF..."
        )

        pdf_service = PDFService()
        docx_service = DOCXService()

        file_path = job["file_path"]
        job_settings = job.get("settings", {})

        # Analyze PDF
        analysis = await pdf_service.analyze(file_path)
        await job_manager.update_job(
            job_id,
            pages_total=analysis.total_pages,
            document_type=analysis.document_type,
            progress=10,
        )

        # Setup OCR if needed
        ocr_provider = None
        if job_settings.get("ocr_enabled", True) and analysis.needs_ocr:
            ocr_provider = get_ocr_provider(job_settings.get("ocr_provider", "auto"))
            await ocr_provider.initialize()
            await job_manager.update_job(
                job_id, message=f"Using {ocr_provider.name} for OCR..."
            )

        # Extract structure
        await job_manager.update_job(
            job_id, message="Extracting content...", progress=20
        )

        def on_progress(progress, page):
            # Scale: 20-80 for extraction
            scaled = 20 + int(progress * 0.6)
            job["progress"] = scaled
            job["pages_processed"] = page

        structure = await pdf_service.extract_structure(
            file_path=file_path,
            ocr_provider=ocr_provider,
            language=job_settings.get("language", "auto"),
            on_progress=on_progress,
        )

        # Generate DOCX
        await job_manager.update_job(job_id, message="Generating DOCX...", progress=85)

        output_dir = os.path.join(settings.storage_path, "output", job_id)
        output_filename = os.path.splitext(job["filename"])[0] + ".docx"

        output_path = await docx_service.generate(
            structure=structure,
            output_dir=output_dir,
            filename=output_filename,
        )

        # Complete
        time_ms = int((time.time() - start) * 1000)
        await job_manager.update_job(
            job_id,
            status=JobStatus.COMPLETED,
            message=f"Completed in {time_ms}ms",
            progress=100,
            download_url=f"/api/v1/download/{job_id}",
            output_path=output_path,
            processing_time_ms=time_ms,
        )

        return {"success": True, "time_ms": time_ms, "output_path": output_path}

    except Exception as e:
        await job_manager.update_job(
            job_id,
            status=JobStatus.FAILED,
            message=f"Error: {str(e)}",
        )
        return {"success": False, "error": str(e)}
