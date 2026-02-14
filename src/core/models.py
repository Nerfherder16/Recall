"""
Core domain models for the Recall memory system.

These models represent the fundamental concepts of living memory:
- Memory: The atomic unit of stored knowledge
- Relationship: Connections between memories (graph edges)
- Session: Temporal context for memory formation
- MemoryQuery: Structured retrieval requests
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from ulid import ULID


def generate_id() -> str:
    """Generate a sortable unique ID."""
    return str(ULID())


class MemoryType(str, Enum):
    """Classification of memory by cognitive function."""

    EPISODIC = "episodic"  # Events, experiences (time-bound)
    SEMANTIC = "semantic"  # Facts, knowledge (timeless)
    PROCEDURAL = "procedural"  # Workflows, how-to (action sequences)
    WORKING = "working"  # Temporary session context (volatile)


class MemorySource(str, Enum):
    """Origin of the memory."""

    USER = "user"  # Explicitly from user
    ASSISTANT = "assistant"  # From AI assistant response
    SYSTEM = "system"  # Auto-detected by system
    CONSOLIDATION = "consolidation"  # Created by merging other memories
    PATTERN = "pattern"  # Extracted from recurring patterns


class RelationshipType(str, Enum):
    """Types of relationships between memories."""

    RELATED_TO = "related_to"  # General semantic relationship
    CAUSED_BY = "caused_by"  # Causal relationship
    SOLVED_BY = "solved_by"  # Problem -> Solution
    SUPERSEDES = "supersedes"  # Newer version replaces older
    DERIVED_FROM = "derived_from"  # Created from (consolidation)
    CONTRADICTS = "contradicts"  # Conflicting information
    REQUIRES = "requires"  # Dependency relationship
    PART_OF = "part_of"  # Hierarchical containment


class Memory(BaseModel):
    """
    The atomic unit of the recall system.

    A memory is not just stored text - it's a living entity with:
    - Semantic meaning (embedding)
    - Dynamic importance (decays, reinforces)
    - Relationships to other memories
    - Lineage tracking
    """

    id: str = Field(default_factory=generate_id)

    # Content
    content: str  # The actual information
    content_hash: str = ""  # For deduplication (computed on save)
    summary: str | None = None  # Optional compressed version

    # Classification
    memory_type: MemoryType = MemoryType.SEMANTIC
    source: MemorySource = MemorySource.SYSTEM
    domain: str = "general"  # Topic area: "auth", "infrastructure", etc.
    tags: list[str] = Field(default_factory=list)

    # Dynamics - these change over time
    importance: float = Field(default=0.5, ge=0.0, le=1.0)  # Current relevance
    stability: float = Field(default=0.1, ge=0.0, le=1.0)  # Resistance to decay
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)  # How certain we are
    access_count: int = 0  # Reinforcement counter

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed: datetime = Field(default_factory=datetime.utcnow)

    # Lineage
    parent_ids: list[str] = Field(default_factory=list)  # Source memories
    superseded_by: str | None = None  # If replaced by newer memory
    session_id: str | None = None  # Session where created

    # Metadata for extensibility
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class Relationship(BaseModel):
    """
    An edge in the memory graph.

    Relationships enable traversal and context expansion:
    - Find all solutions to a problem
    - Trace the evolution of a concept
    - Discover related knowledge
    """

    id: str = Field(default_factory=generate_id)
    source_id: str  # From memory
    target_id: str  # To memory
    relationship_type: RelationshipType
    strength: float = Field(default=0.5, ge=0.0, le=1.0)  # Connection strength
    bidirectional: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    """
    A temporal context for memory operations.

    Sessions group related memories and provide:
    - Working memory scope
    - Context for consolidation
    - Activity tracking
    """

    id: str = Field(default_factory=generate_id)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: datetime | None = None

    # Context
    working_directory: str | None = None
    active_files: list[str] = Field(default_factory=list)
    current_task: str | None = None

    # Accumulated context
    working_memory: list[str] = Field(default_factory=list)  # Memory IDs
    topics_discussed: list[str] = Field(default_factory=list)

    # Stats
    memories_created: int = 0
    memories_retrieved: int = 0
    signals_detected: int = 0


class MemoryQuery(BaseModel):
    """
    Structured query for memory retrieval.

    Supports multiple retrieval strategies:
    - Semantic similarity (embedding-based)
    - Graph traversal (relationship-based)
    - Filtered search (metadata-based)
    """

    # Query content (at least one required)
    text: str | None = None  # Natural language query
    embedding: list[float] | None = None  # Pre-computed embedding
    memory_ids: list[str] | None = None  # Specific memories to expand from

    # Filters
    memory_types: list[MemoryType] | None = None
    domains: list[str] | None = None
    tags: list[str] | None = None
    min_importance: float = 0.0
    min_confidence: float = 0.0
    since: datetime | None = None
    until: datetime | None = None

    # Graph options
    expand_relationships: bool = True
    relationship_types: list[RelationshipType] | None = None
    max_depth: int = 2  # How many hops in graph

    # Result options
    limit: int = 10
    include_superseded: bool = False

    # Context for ranking
    session_id: str | None = None
    current_file: str | None = None
    current_task: str | None = None


class RetrievalResult(BaseModel):
    """Result from memory retrieval with scoring."""

    memory: Memory
    score: float  # Combined relevance score
    similarity: float  # Embedding similarity (0-1)
    graph_distance: int  # Hops from query origin
    retrieval_path: list[str] = Field(default_factory=list)  # How we got here


class ConsolidationResult(BaseModel):
    """Result from memory consolidation."""

    merged_memory: Memory
    source_memories: list[str]  # IDs that were merged
    relationships_created: int
    memories_superseded: int


# =============================================================
# SIGNAL DETECTION MODELS
# =============================================================


class SignalType(str, Enum):
    """Types of auto-saveable signals."""

    ERROR_FIX = "error_fix"
    DECISION = "decision"
    PATTERN = "pattern"
    PREFERENCE = "preference"
    FACT = "fact"
    WORKFLOW = "workflow"
    CONTRADICTION = "contradiction"


class DetectedSignal(BaseModel):
    """A signal detected from conversation."""

    signal_type: SignalType
    content: str
    confidence: float
    source: MemorySource
    suggested_domain: str | None = None
    suggested_tags: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


# =============================================================
# NEGATIVE SPACE (ANTI-PATTERNS)
# =============================================================


class AntiPattern(BaseModel):
    """
    Something that should NOT be done.

    Negative space memories help prevent mistakes by:
    - Warning when bad patterns are detected
    - Suggesting better alternatives
    """

    id: str = Field(default_factory=generate_id)
    pattern: str  # What to watch for
    warning: str  # What to tell the user
    alternative: str | None = None  # Better approach
    severity: str = "warning"  # warning, error, info
    domain: str = "general"
    times_triggered: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
