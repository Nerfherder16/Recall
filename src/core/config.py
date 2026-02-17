"""
Configuration for the Recall memory system.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_prefix="RECALL_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    env: str = "development"
    debug: bool = True

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Qdrant (Vector Store)
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "recall_memories"

    # Neo4j (Graph Store)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "recallmemory"

    # PostgreSQL (Metadata Store)
    postgres_dsn: str = "postgresql+asyncpg://recall:recallmemory@localhost:5433/recall"

    # Redis (Cache + Events)
    redis_url: str = "redis://localhost:6380"

    # Ollama (Embeddings)
    ollama_host: str = "http://localhost:11434"
    embedding_model: str = "qwen3-embedding:0.6b"
    embedding_dimensions: int = 1024  # Qwen3-Embedding-0.6B uses 1024 dims

    # Memory Settings
    default_importance: float = 0.5
    importance_decay_rate: float = 0.01  # Per hour
    consolidation_threshold: float = 0.85  # Similarity for merge
    min_importance_for_retrieval: float = 0.05

    # Session Settings
    session_ttl_hours: int = 24
    working_memory_limit: int = 20

    # Signal Detection
    signal_confidence_auto_store: float = 0.75
    signal_confidence_pending: float = 0.4
    signal_context_window: int = 10
    signal_max_turns_stored: int = 50
    signal_detection_model: str = "qwen3:14b"
    signal_detection_timeout: float = 180.0

    # Security
    api_key: str = ""  # Empty = auth disabled (dev mode)
    allowed_origins: str = "*"  # Comma-separated origins, or "*" for all
    max_content_length: int = 50000  # Max chars for memory content / turn content
    max_turns_per_request: int = 50  # Max turns per ingest request

    # Rate Limiting
    rate_limit_default: str = "60/minute"
    rate_limit_search: str = "30/minute"
    rate_limit_ingest: str = "20/minute"
    rate_limit_admin: str = "10/minute"

    # Operations
    export_include_embeddings_default: bool = False
    metrics_enabled: bool = True

    # Background Jobs
    consolidation_interval_hours: int = 1
    decay_interval_minutes: int = 30
    pattern_extraction_interval_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
