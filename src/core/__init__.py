"""Core domain models and services."""

from .config import Settings, get_settings
from .embeddings import EmbeddingError, EmbeddingService, OllamaUnavailableError, get_embedding_service
from .llm import LLMError, OllamaLLM, get_llm
from .models import (
    AntiPattern,
    ConsolidationResult,
    DetectedSignal,
    Memory,
    MemoryQuery,
    MemorySource,
    MemoryType,
    Relationship,
    RelationshipType,
    RetrievalResult,
    Session,
    SignalType,
    User,
)

__all__ = [
    # Config
    "Settings",
    "get_settings",
    # Embeddings
    "EmbeddingService",
    "EmbeddingError",
    "OllamaUnavailableError",
    "get_embedding_service",
    # LLM
    "OllamaLLM",
    "LLMError",
    "get_llm",
    # Models
    "Memory",
    "MemoryType",
    "MemorySource",
    "Relationship",
    "RelationshipType",
    "Session",
    "MemoryQuery",
    "RetrievalResult",
    "ConsolidationResult",
    "SignalType",
    "DetectedSignal",
    "AntiPattern",
    "User",
]
