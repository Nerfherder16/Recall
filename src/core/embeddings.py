"""
Embedding generation for semantic memory.

Uses Ollama with Qwen3-Embedding-0.6B for high-quality local embeddings.
Qwen3-Embedding produces 1024-dimensional vectors with MTEB ~68-70.
"""

import hashlib
import struct
import time
from collections import OrderedDict

import httpx
import numpy as np
import structlog

from .config import get_settings
from .metrics import get_metrics

logger = structlog.get_logger()

# --- Embedding LRU cache ---
_embed_cache: OrderedDict[str, tuple[list[float], float]] = OrderedDict()
_EMBED_CACHE_MAX = 200
_EMBED_CACHE_TTL = 300  # seconds


def clear_embed_cache() -> None:
    """Clear the embedding LRU cache."""
    _embed_cache.clear()


class EmbeddingService:
    """
    Generate embeddings via Ollama.

    Qwen3-Embedding-0.6B characteristics:
    - 1024 dimensions
    - MTEB ~68-70 (superior to BGE-large ~64)
    - 639MB VRAM (smaller than BGE-large 1.3GB)
    - Supports instruction-based query prefixing
    - Native batch embedding via /api/embed
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
            response = await self.client.get(f"{self.settings.ollama_host}/api/tags")
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
                   Qwen3-Embedding uses instruction prefix for queries

        Returns:
            1024-dimensional embedding vector
        """
        # Check LRU cache
        cache_key = hashlib.md5((prefix + ":" + text).encode()).hexdigest()
        cached = _embed_cache.get(cache_key)
        if cached is not None:
            vec, ts = cached
            if time.time() - ts < _EMBED_CACHE_TTL:
                _embed_cache.move_to_end(cache_key)
                return vec
            else:
                del _embed_cache[cache_key]

        # Qwen3-Embedding uses instruction prefix for queries
        if prefix == "query":
            prefixed_text = (
                "Instruct: Given a web search query, retrieve relevant "
                "passages that answer the query\n"
                f"Query:{text}"
            )
        else:
            prefixed_text = text

        metrics = get_metrics()
        start = time.time()
        try:
            response = await self.client.post(
                f"{self.settings.ollama_host}/api/embed",
                json={
                    "model": self.settings.embedding_model,
                    "input": prefixed_text,
                },
            )

            if response.status_code == 200:
                data = response.json()
                embeddings = data.get("embeddings", [])
                if not embeddings:
                    raise EmbeddingError("Ollama returned empty embeddings array")
                embedding = embeddings[0]

                if len(embedding) != self.settings.embedding_dimensions:
                    logger.warning(
                        "unexpected_embedding_dimensions",
                        expected=self.settings.embedding_dimensions,
                        actual=len(embedding),
                    )

                # Store in LRU cache
                _embed_cache[cache_key] = (embedding, time.time())
                if len(_embed_cache) > _EMBED_CACHE_MAX:
                    _embed_cache.popitem(last=False)

                metrics.increment(
                    "recall_embedding_requests_total",
                    {"status": "success"},
                )
                return embedding

            logger.error("embedding_request_failed", status=response.status_code)
            metrics.increment("recall_embedding_requests_total", {"status": "error"})
            raise EmbeddingError(f"Ollama returned status {response.status_code}")

        except httpx.RequestError as e:
            logger.error("embedding_request_error", error=str(e))
            metrics.increment("recall_embedding_requests_total", {"status": "error"})
            raise OllamaUnavailableError(f"Failed to connect to Ollama: {e}")
        finally:
            metrics.observe(
                "recall_embedding_latency_seconds",
                value=time.time() - start,
            )

    async def embed_batch(self, texts: list[str], prefix: str = "passage") -> list[list[float]]:
        """
        Generate embeddings for multiple texts using native batch API.

        Sends all texts in a single /api/embed request.
        Falls back to sequential on error.
        """
        if not texts:
            return []

        # Apply query prefix if needed
        if prefix == "query":
            processed = [
                "Instruct: Given a web search query, retrieve relevant "
                "passages that answer the query\n"
                f"Query:{t}"
                for t in texts
            ]
        else:
            processed = texts

        try:
            response = await self.client.post(
                f"{self.settings.ollama_host}/api/embed",
                json={
                    "model": self.settings.embedding_model,
                    "input": processed,
                },
            )

            if response.status_code == 200:
                data = response.json()
                embeddings = data.get("embeddings", [])
                if len(embeddings) == len(texts):
                    return embeddings

                logger.warning(
                    "batch_embedding_count_mismatch",
                    expected=len(texts),
                    actual=len(embeddings),
                )

        except Exception as e:
            logger.warning("batch_embedding_failed_falling_back", error=str(e))

        # Fallback: sequential
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
