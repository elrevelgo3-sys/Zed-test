"""
Services package for PDF to DOCX Converter.

This package contains the core business logic:
- pdf_service: PDF analysis and text extraction
- ocr: OCR providers (Mistral, DeepSeek, Surya)
- docx_service: DOCX document generation
- storage: File storage (local/S3)
- job_manager: Job lifecycle management
"""

from app.services.docx_service import DOCXService
from app.services.job_manager import job_manager
from app.services.pdf_service import PDFService
from app.services.storage import StorageService

__all__ = [
    "PDFService",
    "DOCXService",
    "StorageService",
    "job_manager",
]
