"""
Embedding generation for semantic memory.

Uses Ollama with BGE-large-en-v1.5 for high-quality local embeddings.
BGE-large produces 1024-dimensional vectors optimized for retrieval.
"""

import hashlib
import struct
import time
from typing import Any

import httpx
import numpy as np
import structlog

from .config import get_settings
from .metrics import get_metrics

logger = structlog.get_logger()


class EmbeddingService:
    """
    Generate embeddings via Ollama.

    BGE-large-en-v1.5 characteristics:
    - 1024 dimensions
    - Excellent for retrieval tasks
    - Supports passage prefixing for better results
    """

    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=120.0)  # Longer timeout for cold starts
        self._model_loaded = False

    async def ensure_model(self) -> bool:
        """Ensure the embedding model is available in Ollama."""
        if self._model_loaded:
            return True

        try:
            # Check if model exists
            response = await self.client.get(
                f"{self.settings.ollama_host}/api/tags"
            )
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]

                # Check for exact match or match with :latest suffix
                target_model = self.settings.embedding_model
                if target_model in model_names or f"{target_model}:latest" in model_names:
                    self._model_loaded = True
                    return True

                # Try to pull the model
                logger.info("pulling_embedding_model", model=self.settings.embedding_model)
                pull_response = await self.client.post(
                    f"{self.settings.ollama_host}/api/pull",
                    json={"name": self.settings.embedding_model},
                    timeout=300.0,  # Model download can take a while
                )
                if pull_response.status_code == 200:
                    self._model_loaded = True
                    return True

        except Exception as e:
            logger.error("embedding_model_check_failed", error=str(e))

        return False

    async def embed(self, text: str, prefix: str = "passage") -> list[float]:
        """
        Generate embedding for text.

        Args:
            text: The text to embed
            prefix: "passage" for stored content, "query" for search queries
                   BGE models benefit from these prefixes

        Returns:
            1024-dimensional embedding vector
        """
        # BGE models work better with prefixes
        if prefix == "query":
            prefixed_text = f"Represent this sentence for searching relevant passages: {text}"
        else:
            prefixed_text = text

        metrics = get_metrics()
        start = time.time()
        try:
            response = await self.client.post(
                f"{self.settings.ollama_host}/api/embeddings",
                json={
                    "model": self.settings.embedding_model,
                    "prompt": prefixed_text,
                },
            )

            if response.status_code == 200:
                data = response.json()
                embedding = data.get("embedding", [])

                if len(embedding) != self.settings.embedding_dimensions:
                    logger.warning(
                        "unexpected_embedding_dimensions",
                        expected=self.settings.embedding_dimensions,
                        actual=len(embedding),
                    )

                metrics.increment("recall_embedding_requests_total", {"status": "success"})
                return embedding

            logger.error("embedding_request_failed", status=response.status_code)
            metrics.increment("recall_embedding_requests_total", {"status": "error"})
            raise EmbeddingError(f"Ollama returned status {response.status_code}")

        except httpx.RequestError as e:
            logger.error("embedding_request_error", error=str(e))
            metrics.increment("recall_embedding_requests_total", {"status": "error"})
            raise OllamaUnavailableError(f"Failed to connect to Ollama: {e}")
        finally:
            metrics.observe("recall_embedding_latency_seconds", value=time.time() - start)

    async def embed_batch(
        self, texts: list[str], prefix: str = "passage"
    ) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Note: Ollama doesn't support batch embedding natively,
        so we process sequentially. Consider parallel processing
        for large batches.
        """
        embeddings = []
        for text in texts:
            embedding = await self.embed(text, prefix)
            embeddings.append(embedding)
        return embeddings

    async def similarity(self, vec1: list[float], vec2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a = np.array(vec1)
        b = np.array(vec2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""

    pass


class OllamaUnavailableError(EmbeddingError):
    """Raised when Ollama is unreachable (connection refused, timeout, etc.)."""

    pass


def content_hash(text: str) -> str:
    """Generate a hash for deduplication."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def compress_embedding(embedding: list[float]) -> bytes:
    """Compress embedding for efficient storage."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def decompress_embedding(data: bytes, dimensions: int = 1024) -> list[float]:
    """Decompress embedding from storage."""
    return list(struct.unpack(f"{dimensions}f", data))


# Singleton instance
_embedding_service: EmbeddingService | None = None


async def get_embedding_service() -> EmbeddingService:
    """Get or create the embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    # Retry ensure_model if it failed on initial creation
    if not _embedding_service._model_loaded:
        await _embedding_service.ensure_model()
    return _embedding_service
