"""
PDF Service - Handles PDF analysis and content extraction.

This service is responsible for:
- Analyzing PDF documents to determine their type (native, scanned, mixed)
- Extracting text from native PDFs
- Converting PDF pages to images for OCR
- Detecting tables, images, and other elements
"""

import io
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import fitz  # PyMuPDF


class DocumentType(str, Enum):
    """Type of PDF document based on content analysis."""

    NATIVE = "native"  # Contains extractable text
    SCANNED = "scanned"  # Image-based, requires OCR
    MIXED = "mixed"  # Contains both text and image pages


@dataclass
class PageInfo:
    """Information about a single PDF page."""

    page_number: int
    width: float
    height: float
    has_text: bool
    text_content: str
    char_count: int
    image_count: int
    needs_ocr: bool
    rotation: int = 0


@dataclass
class PDFAnalysis:
    """Results of PDF document analysis."""

    total_pages: int
    document_type: DocumentType
    needs_ocr: bool
    pages_with_text: int
    pages_needing_ocr: int
    total_images: int
    file_size_bytes: int
    metadata: dict = field(default_factory=dict)
    pages: list[PageInfo] = field(default_factory=list)

    @property
    def ocr_ratio(self) -> float:
        """Ratio of pages needing OCR (0.0 - 1.0)."""
        if self.total_pages == 0:
            return 0.0
        return self.pages_needing_ocr / self.total_pages


@dataclass
class ExtractedElement:
    """A single extracted element from a PDF page."""

    id: str
    type: str  # paragraph, heading, table, image, list_item, etc.
    content: str
    bbox: tuple[int, int, int, int]  # (x_min, y_min, x_max, y_max) normalized 0-1000
    page_number: int
    confidence: float = 1.0
    style: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class PageStructure:
    """Structured content of a single page."""

    page_number: int
    width: float
    height: float
    elements: list[ExtractedElement] = field(default_factory=list)
    raw_text: str = ""
    image_base64: Optional[str] = None


@dataclass
class DocumentStructure:
    """Complete document structure with all pages."""

    pages: list[PageStructure]
    total_pages: int
    document_type: DocumentType
    detected_language: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class PDFService:
    """
    Service for PDF document analysis and content extraction.

    Uses PyMuPDF (fitz) for PDF operations which is fast and
    supports a wide range of PDF features.
    """

    # Minimum characters per page to consider it as having text
    MIN_CHARS_FOR_TEXT_PAGE = 50

    # DPI for rendering pages to images (for OCR)
    DEFAULT_IMAGE_DPI = 200
    HIGH_QUALITY_DPI = 300

    def __init__(self):
        """Initialize PDF service."""
        pass

    async def analyze(self, file_path: str) -> PDFAnalysis:
        """
        Analyze a PDF document to determine its characteristics.

        Args:
            file_path: Path to the PDF file

        Returns:
            PDFAnalysis with document information
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        file_size = os.path.getsize(file_path)

        # Open PDF with PyMuPDF
        doc = fitz.open(file_path)

        try:
            pages_info: list[PageInfo] = []
            pages_with_text = 0
            pages_needing_ocr = 0
            total_images = 0

            for page_num in range(len(doc)):
                page = doc[page_num]

                # Extract text
                text = page.get_text("text").strip()
                char_count = len(text)

                # Count images on the page
                image_list = page.get_images(full=True)
                image_count = len(image_list)
                total_images += image_count

                # Determine if page has extractable text
                has_text = char_count >= self.MIN_CHARS_FOR_TEXT_PAGE

                # Page needs OCR if it has images but little/no text
                # or if it appears to be a scanned page
                needs_ocr = not has_text and (
                    image_count > 0 or self._is_scanned_page(page)
                )

                if has_text:
                    pages_with_text += 1
                if needs_ocr:
                    pages_needing_ocr += 1

                page_info = PageInfo(
                    page_number=page_num + 1,
                    width=page.rect.width,
                    height=page.rect.height,
                    has_text=has_text,
                    text_content=text if has_text else "",
                    char_count=char_count,
                    image_count=image_count,
                    needs_ocr=needs_ocr,
                    rotation=page.rotation,
                )
                pages_info.append(page_info)

            # Determine document type
            total_pages = len(doc)
            if pages_needing_ocr == 0:
                doc_type = DocumentType.NATIVE
            elif pages_needing_ocr == total_pages:
                doc_type = DocumentType.SCANNED
            else:
                doc_type = DocumentType.MIXED

            # Extract metadata
            metadata = dict(doc.metadata) if doc.metadata else {}

            return PDFAnalysis(
                total_pages=total_pages,
                document_type=doc_type,
                needs_ocr=pages_needing_ocr > 0,
                pages_with_text=pages_with_text,
                pages_needing_ocr=pages_needing_ocr,
                total_images=total_images,
                file_size_bytes=file_size,
                metadata=metadata,
                pages=pages_info,
            )

        finally:
            doc.close()

    def _is_scanned_page(self, page: fitz.Page) -> bool:
        """
        Detect if a page appears to be a scanned document.

        Scanned pages typically have one large image covering most of the page.
        """
        images = page.get_images(full=True)
        if not images:
            return False

        # Check if there's a large image covering most of the page
        page_area = page.rect.width * page.rect.height

        for img in images:
            try:
                # Get image bbox
                img_rects = page.get_image_rects(img[0])
                for rect in img_rects:
                    img_area = rect.width * rect.height
                    # If image covers more than 80% of the page, it's likely a scan
                    if img_area / page_area > 0.8:
                        return True
            except Exception:
                pass

        return False

    async def extract_structure(
        self,
        file_path: str,
        ocr_provider=None,
        language: str = "auto",
        extract_tables: bool = True,
        extract_images: bool = True,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> DocumentStructure:
        """
        Extract complete document structure from a PDF.

        Args:
            file_path: Path to the PDF file
            ocr_provider: OCR provider instance for scanned pages
            language: Document language for OCR
            extract_tables: Whether to detect and extract tables
            extract_images: Whether to extract images
            on_progress: Callback for progress updates (progress_percent, current_page)

        Returns:
            DocumentStructure with all pages and elements
        """
        # First analyze the document
        analysis = await self.analyze(file_path)

        doc = fitz.open(file_path)
        pages_structure: list[PageStructure] = []

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                page_info = analysis.pages[page_num]

                # Report progress
                if on_progress:
                    progress = int((page_num / len(doc)) * 100)
                    on_progress(progress, page_num + 1)

                if page_info.needs_ocr and ocr_provider:
                    # Convert page to image and run OCR
                    page_structure = await self._extract_with_ocr(
                        page, page_num + 1, ocr_provider, language
                    )
                else:
                    # Extract text directly from PDF
                    page_structure = self._extract_native(
                        page, page_num + 1, extract_tables, extract_images
                    )

                pages_structure.append(page_structure)

            # Final progress update
            if on_progress:
                on_progress(100, len(doc))

            # Detect language from extracted text if needed
            detected_language = None
            if language == "auto":
                all_text = " ".join(p.raw_text for p in pages_structure if p.raw_text)
                detected_language = self._detect_language(all_text)
            else:
                detected_language = language

            return DocumentStructure(
                pages=pages_structure,
                total_pages=len(doc),
                document_type=analysis.document_type,
                detected_language=detected_language,
                metadata=analysis.metadata,
            )

        finally:
            doc.close()

    def _extract_native(
        self,
        page: fitz.Page,
        page_number: int,
        extract_tables: bool = True,
        extract_images: bool = True,
    ) -> PageStructure:
        """
        Extract content from a native (text-based) PDF page.
        """
        elements: list[ExtractedElement] = []
        page_width = page.rect.width
        page_height = page.rect.height

        # Get text blocks with positions
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        element_id = 0
        for block in blocks:
            if block["type"] == 0:  # Text block
                for line in block.get("lines", []):
                    text = ""
                    font_size = 11
                    is_bold = False
                    is_italic = False

                    for span in line.get("spans", []):
                        text += span.get("text", "")
                        font_size = span.get("size", 11)
                        font_name = span.get("font", "").lower()
                        is_bold = "bold" in font_name or span.get("flags", 0) & 2**4
                        is_italic = "italic" in font_name or span.get("flags", 0) & 2**1

                    text = text.strip()
                    if not text:
                        continue

                    # Determine element type based on font size and style
                    element_type = self._classify_text_element(text, font_size, is_bold)

                    # Get bounding box and normalize to 0-1000
                    bbox = line.get("bbox", block.get("bbox", (0, 0, 0, 0)))
                    normalized_bbox = self._normalize_bbox(
                        bbox, page_width, page_height
                    )

                    element = ExtractedElement(
                        id=f"p{page_number}_e{element_id}",
                        type=element_type,
                        content=text,
                        bbox=normalized_bbox,
                        page_number=page_number,
                        confidence=1.0,
                        style={
                            "font_size": font_size,
                            "bold": is_bold,
                            "italic": is_italic,
                        },
                    )
                    elements.append(element)
                    element_id += 1

            elif block["type"] == 1 and extract_images:  # Image block
                bbox = block.get("bbox", (0, 0, 0, 0))
                normalized_bbox = self._normalize_bbox(bbox, page_width, page_height)

                element = ExtractedElement(
                    id=f"p{page_number}_e{element_id}",
                    type="image",
                    content="[IMAGE]",
                    bbox=normalized_bbox,
                    page_number=page_number,
                    metadata={"image_index": block.get("number", 0)},
                )
                elements.append(element)
                element_id += 1

        # Extract tables if requested
        if extract_tables:
            tables = self._extract_tables_from_page(
                page, page_number, page_width, page_height
            )
            for table_element in tables:
                table_element.id = f"p{page_number}_e{element_id}"
                elements.append(table_element)
                element_id += 1

        # Sort elements by vertical position (top to bottom)
        elements.sort(key=lambda e: (e.bbox[1], e.bbox[0]))

        return PageStructure(
            page_number=page_number,
            width=page_width,
            height=page_height,
            elements=elements,
            raw_text=page.get_text("text"),
        )

    async def _extract_with_ocr(
        self,
        page: fitz.Page,
        page_number: int,
        ocr_provider,
        language: str,
    ) -> PageStructure:
        """
        Extract content from a scanned page using OCR.
        """
        # Render page to image
        image_bytes = self._page_to_image(page, dpi=self.DEFAULT_IMAGE_DPI)

        # Run OCR
        ocr_result = await ocr_provider.process_image(
            image_bytes=image_bytes,
            language=language,
        )

        # Convert OCR results to elements
        elements: list[ExtractedElement] = []
        for idx, item in enumerate(ocr_result.elements):
            element = ExtractedElement(
                id=f"p{page_number}_e{idx}",
                type=item.get("type", "paragraph"),
                content=item.get("content", ""),
                bbox=tuple(item.get("bbox", [0, 0, 0, 0])),
                page_number=page_number,
                confidence=item.get("confidence", 0.9),
                style=item.get("style", {}),
            )
            elements.append(element)

        # Sort elements by position
        elements.sort(key=lambda e: (e.bbox[1], e.bbox[0]))

        return PageStructure(
            page_number=page_number,
            width=page.rect.width,
            height=page.rect.height,
            elements=elements,
            raw_text=" ".join(e.content for e in elements),
        )

    def _page_to_image(self, page: fitz.Page, dpi: int = 200) -> bytes:
        """Convert a PDF page to a JPEG image."""
        zoom = dpi / 72  # 72 is the default PDF DPI
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)

        # Convert to JPEG bytes
        img_bytes = pix.tobytes("jpeg", 95)
        return img_bytes

    def _normalize_bbox(
        self,
        bbox: tuple,
        page_width: float,
        page_height: float,
    ) -> tuple[int, int, int, int]:
        """Normalize bounding box to 0-1000 coordinate space."""
        x_min, y_min, x_max, y_max = bbox
        return (
            int((x_min / page_width) * 1000),
            int((y_min / page_height) * 1000),
            int((x_max / page_width) * 1000),
            int((y_max / page_height) * 1000),
        )

    def _classify_text_element(
        self,
        text: str,
        font_size: float,
        is_bold: bool,
    ) -> str:
        """Classify a text element based on its properties."""
        # Simple heuristic-based classification
        if font_size >= 18 and is_bold:
            return "heading_1"
        elif font_size >= 14 and is_bold:
            return "heading_2"
        elif font_size >= 12 and is_bold:
            return "heading_3"
        elif text.strip().startswith(("•", "-", "*", "–", "◦")):
            return "list_item"
        elif text.strip()[0:3].replace(".", "").replace(")", "").isdigit():
            return "list_item"
        else:
            return "paragraph"

    def _extract_tables_from_page(
        self,
        page: fitz.Page,
        page_number: int,
        page_width: float,
        page_height: float,
    ) -> list[ExtractedElement]:
        """
        Extract tables from a PDF page.

        Uses PyMuPDF's table detection capabilities.
        """
        tables_elements: list[ExtractedElement] = []

        try:
            # PyMuPDF 1.23+ has built-in table detection
            tables = page.find_tables()

            for idx, table in enumerate(tables):
                # Get table data
                table_data = table.extract()

                if not table_data:
                    continue

                # Convert to rows format
                rows = []
                for row in table_data:
                    rows.append([cell if cell else "" for cell in row])

                # Get bounding box
                bbox = table.bbox
                normalized_bbox = self._normalize_bbox(bbox, page_width, page_height)

                element = ExtractedElement(
                    id=f"table_{idx}",
                    type="table",
                    content="[TABLE]",
                    bbox=normalized_bbox,
                    page_number=page_number,
                    metadata={
                        "rows": rows,
                        "row_count": len(rows),
                        "col_count": len(rows[0]) if rows else 0,
                    },
                )
                tables_elements.append(element)

        except Exception as e:
            # Table detection might not be available in older PyMuPDF versions
            print(f"Table extraction error: {e}")

        return tables_elements

    def _detect_language(self, text: str) -> str:
        """
        Detect the language of text.

        Simple heuristic-based detection.
        In production, use a proper library like langdetect.
        """
        if not text or len(text) < 20:
            return "en"

        # Simple detection based on character ranges
        sample = text[:1000].lower()

        # Count Cyrillic characters (Russian, Ukrainian, etc.)
        cyrillic_count = sum(1 for c in sample if "\u0400" <= c <= "\u04ff")

        # Count CJK characters (Chinese, Japanese, Korean)
        cjk_count = sum(1 for c in sample if "\u4e00" <= c <= "\u9fff")

        # Count Arabic characters
        arabic_count = sum(1 for c in sample if "\u0600" <= c <= "\u06ff")

        total_chars = len(sample)

        if cyrillic_count / total_chars > 0.3:
            return "ru"
        elif cjk_count / total_chars > 0.3:
            return "zh"
        elif arabic_count / total_chars > 0.3:
            return "ar"
        else:
            return "en"

    def get_page_image(
        self,
        file_path: str,
        page_number: int,
        dpi: int = 150,
    ) -> bytes:
        """
        Get a specific page as an image.

        Args:
            file_path: Path to the PDF file
            page_number: Page number (1-based)
            dpi: Image resolution

        Returns:
            JPEG image bytes
        """
        doc = fitz.open(file_path)
        try:
            if page_number < 1 or page_number > len(doc):
                raise ValueError(f"Invalid page number: {page_number}")

            page = doc[page_number - 1]
            return self._page_to_image(page, dpi)
        finally:
            doc.close()

    def get_all_pages_as_images(
        self,
        file_path: str,
        dpi: int = 150,
        max_pages: Optional[int] = None,
    ) -> list[bytes]:
        """
        Convert all PDF pages to images.

        Args:
            file_path: Path to the PDF file
            dpi: Image resolution
            max_pages: Maximum number of pages to convert

        Returns:
            List of JPEG image bytes for each page
        """
        doc = fitz.open(file_path)
        images = []

        try:
            num_pages = min(len(doc), max_pages) if max_pages else len(doc)

            for page_num in range(num_pages):
                page = doc[page_num]
                img_bytes = self._page_to_image(page, dpi)
                images.append(img_bytes)

            return images
        finally:
            doc.close()
