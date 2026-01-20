"""
OCR Providers Package - Simplified.

Usage:
    from app.services.ocr import get_ocr_provider

    provider = get_ocr_provider("mistral")  # or "deepseek", "auto"
    await provider.initialize()
    result = await provider.process_image(image_bytes)
"""

from app.services.ocr.factory import get_ocr_provider

__all__ = ["get_ocr_provider"]
