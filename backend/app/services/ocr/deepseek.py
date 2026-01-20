"""
DeepSeek VL2 OCR Provider - Simplified.
Cost-effective alternative to Mistral.
"""

import base64
import json
import time
from typing import Optional

import httpx

from app.config import settings

SYSTEM_PROMPT = """Extract all text and structure from document images.

Output JSON format:
{
  "elements": [
    {"type": "heading", "content": "Document Title", "bbox": [50, 20, 950, 80]},
    {"type": "paragraph", "content": "Text content here...", "bbox": [50, 100, 950, 200]},
    {"type": "table", "content": "[TABLE]", "bbox": [50, 220, 950, 400], "rows": [["A", "B"], ["1", "2"]]},
    {"type": "list", "content": "• Item one\\n• Item two", "bbox": [50, 420, 950, 500]}
  ],
  "language": "en"
}

bbox format: [y_min, x_min, y_max, x_max] in 0-1000 coordinates."""


class DeepSeekOCR:
    """DeepSeek VL2 OCR - cost-effective and reliable."""

    API_URL = "https://api.deepseek.com/v1/chat/completions"
    MODEL = "deepseek-chat"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.deepseek_api_key
        self.client: Optional[httpx.AsyncClient] = None

    @property
    def name(self) -> str:
        return "DeepSeek VL2"

    async def initialize(self):
        if not self.api_key:
            raise ValueError("DeepSeek API key required")
        self.client = httpx.AsyncClient(
            timeout=120.0,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )

    async def process_image(self, image_bytes: bytes, language: str = "auto") -> dict:
        """Process single image, return structured content."""
        if not self.client:
            await self.initialize()

        start = time.time()
        image_b64 = base64.b64encode(image_bytes).decode()

        # Detect image type
        mime = "image/jpeg"
        if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"

        prompt = "Extract all text and structure from this document."
        if language != "auto":
            prompt += f" Document language: {language}."

        response = await self.client.post(
            self.API_URL,
            json={
                "model": self.MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                            },
                        ],
                    },
                ],
                "max_tokens": 8192,
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        parsed = self._parse(content)
        parsed["processing_time_ms"] = int((time.time() - start) * 1000)
        parsed["provider"] = self.name

        return parsed

    async def process_batch(
        self, images: list[bytes], language: str = "auto"
    ) -> list[dict]:
        """Process multiple images."""
        results = []
        for img in images:
            result = await self.process_image(img, language)
            results.append(result)
        return results

    def _parse(self, content: str) -> dict:
        """Parse JSON response."""
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return {"elements": [], "language": None, "error": "Parse error"}

        return {
            "elements": data.get("elements", []),
            "language": data.get("language"),
            "raw_text": " ".join(
                e.get("content", "") for e in data.get("elements", [])
            ),
        }

    async def close(self):
        if self.client:
            await self.client.aclose()
