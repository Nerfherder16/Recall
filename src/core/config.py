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
    embedding_model: str = "bge-large-en-v1.5"
    embedding_dimensions: int = 1024  # BGE-large uses 1024 dims

    # Memory Settings
    default_importance: float = 0.5
    importance_decay_rate: float = 0.01  # Per hour
    consolidation_threshold: float = 0.85  # Similarity for merge
    min_importance_for_retrieval: float = 0.05

    # Session Settings
    session_ttl_hours: int = 24
    working_memory_limit: int = 20

    # Background Jobs
    consolidation_interval_hours: int = 1
    decay_interval_minutes: int = 30
    pattern_extraction_interval_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
