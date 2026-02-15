"""
Ollama generative LLM service.

First generative LLM integration — uses Ollama's /api/generate endpoint
for signal detection and other text generation tasks.
Singleton pattern matching embeddings.py.
"""

from typing import Any

import httpx
import structlog

from .config import get_settings

logger = structlog.get_logger()


class LLMError(Exception):
    """Raised when LLM generation fails."""

    pass


class OllamaLLM:
    """Generate text via Ollama."""

    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(
            timeout=self.settings.signal_detection_timeout
        )

    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
        format_json: bool = False,
    ) -> str:
        """
        Generate text from Ollama.

        Args:
            prompt: The prompt to send
            model: Model name (defaults to signal_detection_model)
            temperature: Sampling temperature
            format_json: If True, request JSON output from Ollama

        Returns:
            Generated text response
        """
        model = model or self.settings.signal_detection_model

        body: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }
        if format_json:
            body["format"] = "json"
        # Disable thinking for qwen3 models to get clean JSON output
        if "qwen3" in model:
            body["options"]["num_ctx"] = 8192
            body["think"] = False

        try:
            response = await self.client.post(
                f"{self.settings.ollama_host}/api/generate",
                json=body,
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("response", "")

            logger.error(
                "llm_request_failed",
                status=response.status_code,
                model=model,
            )
            raise LLMError(f"Ollama returned status {response.status_code}")

        except httpx.TimeoutException as e:
            logger.error("llm_timeout", model=model, timeout=self.settings.signal_detection_timeout)
            raise LLMError(f"Ollama timed out after {self.settings.signal_detection_timeout}s")
        except httpx.RequestError as e:
            logger.error("llm_request_error", error=repr(e), error_type=type(e).__name__)
            raise LLMError(f"Failed to connect to Ollama: {type(e).__name__}: {e}")

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# Singleton instance
_llm: OllamaLLM | None = None


async def get_llm() -> OllamaLLM:
    """Get or create the LLM singleton."""
    global _llm
    if _llm is None:
        _llm = OllamaLLM()
    return _llm
