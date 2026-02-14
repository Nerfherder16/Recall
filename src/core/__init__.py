"""Core domain models and services."""

from .config import Settings, get_settings
from .embeddings import EmbeddingService, get_embedding_service
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
)

__all__ = [
    # Config
    "Settings",
    "get_settings",
    # Embeddings
    "EmbeddingService",
    "get_embedding_service",
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
]
