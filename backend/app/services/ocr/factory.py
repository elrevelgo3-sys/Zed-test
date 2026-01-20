"""OCR Provider Factory - simplified."""

from app.config import settings


def get_ocr_provider(provider_type: str = "auto"):
    """Get OCR provider by type. Simple and direct."""

    # Auto-select based on available API keys
    if provider_type == "auto":
        if settings.mistral_api_key:
            provider_type = "mistral"
        elif settings.deepseek_api_key:
            provider_type = "deepseek"
        else:
            provider_type = "surya"

    # Import and return the right provider
    if provider_type == "mistral":
        from app.services.ocr.mistral import MistralOCR

        return MistralOCR()
    elif provider_type == "deepseek":
        from app.services.ocr.deepseek import DeepSeekOCR

        return DeepSeekOCR()
    else:
        from app.services.ocr.surya import SuryaOCR

        return SuryaOCR()
