"""
Pydantic models for API requests and responses.
Simplified version - focusing on what matters.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job status - only what user needs to see."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OCRProvider(str, Enum):
    """Available OCR providers."""

    MISTRAL = "mistral"
    DEEPSEEK = "deepseek"
    SURYA = "surya"
    AUTO = "auto"


class DocumentType(str, Enum):
    """Detected document type."""

    NATIVE = "native"
    SCANNED = "scanned"
    MIXED = "mixed"


# Request Models


class ConvertRequest(BaseModel):
    """Conversion settings."""

    ocr_enabled: bool = True
    ocr_provider: OCRProvider = OCRProvider.AUTO
    language: str = "auto"
    preserve_layout: bool = True


# Response Models


class JobResponse(BaseModel):
    """Job status response."""

    job_id: str
    status: JobStatus
    progress: int = Field(default=0, ge=0, le=100)
    message: str = ""
    filename: str
    file_size: int
    pages_total: Optional[int] = None
    pages_processed: int = 0
    document_type: Optional[DocumentType] = None
    download_url: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    processing_time_ms: Optional[int] = None


class ConvertResponse(BaseModel):
    """Response after upload."""

    job_id: str
    status: JobStatus = JobStatus.PENDING
    message: str = "Processing started"


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str
    ocr_available: bool


# Document Structure (for internal use)


class BoundingBox(BaseModel):
    """Bounding box in 0-1000 coordinates."""

    x_min: int = 0
    y_min: int = 0
    x_max: int = 1000
    y_max: int = 1000


class TextStyle(BaseModel):
    """Text styling."""

    font_size: float = 11.0
    bold: bool = False
    italic: bool = False
    color: str = "#000000"


class DocumentElement(BaseModel):
    """Single document element."""

    type: str  # paragraph, heading, table, image, list
    content: str = ""
    bbox: list[int] = [0, 0, 1000, 1000]
    style: Optional[TextStyle] = None
    table_data: Optional[list[list[str]]] = None
    confidence: float = 1.0
    page: int = 1


class PageStructure(BaseModel):
    """Single page structure."""

    page_number: int
    width: float
    height: float
    elements: list[DocumentElement] = []


class DocumentStructure(BaseModel):
    """Complete document."""

    pages: list[PageStructure] = []
    total_pages: int
    document_type: DocumentType = DocumentType.NATIVE
    language: Optional[str] = None


class JobStatistics(BaseModel):
    """Job statistics for completed jobs."""

    job_id: str
    pages_total: int
    pages_with_ocr: int = 0
    elements_extracted: int = 0
    tables_found: int = 0
    images_found: int = 0
    processing_time_ms: int = 0
