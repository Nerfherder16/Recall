"""
Admin endpoints for triggering maintenance operations on-demand.

- POST /admin/consolidate  — merge similar memories
- POST /admin/decay        — apply importance decay
- GET  /admin/ollama       — proxy Ollama model/status info
- POST /admin/users        — create user
- GET  /admin/users        — list users
- DELETE /admin/users/{id}  — delete user
"""

import re
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.api.rate_limit import limiter
from src.core.config import get_settings
from src.core.models import User

from src.core.consolidation import MemoryConsolidator
from src.core.domains import normalize_domain
from src.core.embeddings import get_embedding_service
from src.core.models import MemoryType
from src.storage import get_neo4j_store, get_postgres_store, get_qdrant_store, get_redis_store
from src.workers.decay import DecayWorker

logger = structlog.get_logger()
router = APIRouter()


# =============================================================
# REQUEST / RESPONSE MODELS
# =============================================================


class ConsolidateRequest(BaseModel):
    domain: str | None = None
    memory_type: str | None = None
    min_cluster_size: int = Field(default=2, ge=2)
    dry_run: bool = False


class ConsolidateResponse(BaseModel):
    clusters_merged: int
    memories_merged: int
    results: list[dict[str, Any]]


class DecayRequest(BaseModel):
    simulate_hours: float = Field(default=0.0, ge=0.0)


class DecayResponse(BaseModel):
    processed: int
    decayed: int
    archived: int
    stable: int


# =============================================================
# ROUTES
# =============================================================


@router.post("/consolidate", response_model=ConsolidateResponse)
@limiter.limit("10/minute")
async def trigger_consolidation(request: Request, body: ConsolidateRequest):
    """Trigger memory consolidation on-demand."""
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        embeddings = await get_embedding_service()

        consolidator = MemoryConsolidator(qdrant, neo4j, embeddings)

        memory_type = MemoryType(body.memory_type) if body.memory_type else None

        results = await consolidator.consolidate(
            memory_type=memory_type,
            domain=body.domain,
            min_cluster_size=body.min_cluster_size,
            dry_run=body.dry_run,
        )

        formatted = []
        memories_merged = 0
        for r in results:
            memories_merged += len(r.source_memories)
            formatted.append({
                "merged_id": r.merged_memory.id,
                "source_ids": r.source_memories,
                "content_preview": r.merged_memory.content[:100],
                "relationships_created": r.relationships_created,
                "memories_superseded": r.memories_superseded,
            })

        return ConsolidateResponse(
            clusters_merged=len(results),
            memories_merged=memories_merged,
            results=formatted,
        )

    except Exception as e:
        logger.error("consolidation_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/decay", response_model=DecayResponse)
@limiter.limit("10/minute")
async def trigger_decay(request: Request, body: DecayRequest):
    """Trigger importance decay on-demand, optionally simulating time passage."""
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        worker = DecayWorker(qdrant, neo4j)
        stats = await worker.run(hours_offset=body.simulate_hours)

        return DecayResponse(**stats)

    except Exception as e:
        logger.error("decay_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/ollama")
async def ollama_info(request: Request):
    """Proxy Ollama model info, running models, and version."""
    settings = get_settings()
    host = settings.ollama_host
    result: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(f"{host}/api/version")
            result["version"] = r.json().get("version", "unknown") if r.status_code == 200 else "error"
        except Exception:
            result["version"] = "unreachable"

        try:
            r = await client.get(f"{host}/api/tags")
            if r.status_code == 200:
                result["models"] = [
                    {
                        "name": m.get("name"),
                        "parameter_size": m.get("details", {}).get("parameter_size"),
                        "quantization": m.get("details", {}).get("quantization_level"),
                        "family": m.get("details", {}).get("family"),
                        "size_bytes": m.get("size", 0),
                    }
                    for m in r.json().get("models", [])
                ]
            else:
                result["models"] = []
        except Exception:
            result["models"] = []

        try:
            r = await client.get(f"{host}/api/ps")
            if r.status_code == 200:
                result["running"] = [
                    {
                        "name": m.get("name"),
                        "size_bytes": m.get("size", 0),
                        "size_vram": m.get("size_vram", 0),
                        "context_length": m.get("context_length", 0),
                        "expires_at": m.get("expires_at"),
                    }
                    for m in r.json().get("models", [])
                ]
            else:
                result["running"] = []
        except Exception:
            result["running"] = []

    return result


# =============================================================
# USER MANAGEMENT
# =============================================================


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str | None = Field(default=None, max_length=100)
    is_admin: bool = False


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str | None
    is_admin: bool
    created_at: str
    last_active_at: str | None


class CreateUserResponse(UserResponse):
    api_key: str  # Only returned once on creation


@router.post("/users", response_model=CreateUserResponse)
async def create_user(body: CreateUserRequest, request: Request):
    """Create a new user with a generated API key. The key is shown only once."""
    try:
        pg = await get_postgres_store()
        user_data = await pg.create_user(
            username=body.username,
            display_name=body.display_name,
            is_admin=body.is_admin,
        )
        logger.info("user_created", username=body.username, user_id=user_data["id"])
        return CreateUserResponse(**user_data)
    except Exception as e:
        err = str(e).lower()
        if "unique" in err or "duplicate" in err:
            raise HTTPException(status_code=409, detail=f"Username '{body.username}' already exists")
        logger.error("create_user_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/users", response_model=list[UserResponse])
async def list_users(request: Request):
    """List all users (API keys are never returned)."""
    try:
        pg = await get_postgres_store()
        users = await pg.list_users()
        return [UserResponse(**u) for u in users]
    except Exception as e:
        logger.error("list_users_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, request: Request):
    """Delete a user. Their memories remain attributed to them."""
    try:
        pg = await get_postgres_store()
        deleted = await pg.delete_user(user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")
        logger.info("user_deleted", user_id=user_id)
        return {"deleted": True, "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_user_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# DURABILITY MIGRATION
# =============================================================

# Regex patterns that indicate permanent-worthy content
_PERMANENT_PATTERNS = [
    re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),  # IPv4
    re.compile(r"\b[\w.-]+:\d{2,5}\b"),  # host:port
    re.compile(r"https?://\S+"),  # URLs
    re.compile(r"(?:/[\w.-]+){2,}"),  # Unix paths
    re.compile(r"[A-Z]:\\[\w.\\-]+"),  # Windows paths
    re.compile(r"\b(?:RTX|GTX|RX|Xeon|Ryzen|i[3579]|A100|H100)\s*\w+", re.IGNORECASE),  # GPU/CPU
]

# Signal tags → durability mapping
_DURABLE_SIGNAL_TAGS = {"signal:fact", "signal:decision", "signal:pattern",
                        "signal:workflow", "signal:preference", "signal:warning"}
_EPHEMERAL_SIGNAL_TAGS = {"signal:error_fix", "signal:contradiction"}


def classify_durability(payload: dict[str, Any]) -> tuple[str, str]:
    """
    Classify a memory payload into a durability tier.

    Returns (tier, reason) where tier is "ephemeral"/"durable"/"permanent".
    Priority waterfall: signal tags → regex permanent → memory type → durable fallback.
    """
    tags = set(payload.get("tags") or [])
    content = payload.get("content") or ""
    memory_type = payload.get("memory_type") or ""
    importance = payload.get("importance") or 0.0

    # Step 1: Signal tags
    if tags & _DURABLE_SIGNAL_TAGS:
        matched = tags & _DURABLE_SIGNAL_TAGS
        return "durable", f"signal tag: {sorted(matched)[0]}"
    if tags & _EPHEMERAL_SIGNAL_TAGS:
        matched = tags & _EPHEMERAL_SIGNAL_TAGS
        return "ephemeral", f"signal tag: {sorted(matched)[0]}"

    # Step 2: Permanent regex detection (needs importance >= 0.4)
    if importance >= 0.4:
        regex_hits = sum(1 for p in _PERMANENT_PATTERNS if p.search(content))
        if regex_hits >= 2:
            return "permanent", f"{regex_hits} infrastructure patterns detected"
        if regex_hits == 1 and memory_type == "semantic":
            return "permanent", "infrastructure pattern + semantic type"

    # Step 3: Memory type
    if memory_type in ("procedural", "semantic"):
        return "durable", f"memory_type={memory_type}"
    if memory_type in ("episodic", "working"):
        return "ephemeral", f"memory_type={memory_type}"

    # Step 4: Fallback
    return "durable", "default fallback"


class MigrateDurabilityRequest(BaseModel):
    dry_run: bool = True


class MigrationSampleEntry(BaseModel):
    id: str
    content_preview: str
    assigned_tier: str
    reason: str


class MigrateDurabilityResponse(BaseModel):
    total_null: int
    classified: int
    errors: int
    per_tier: dict[str, int]
    sample: list[MigrationSampleEntry]


@router.post("/migrate/durability", response_model=MigrateDurabilityResponse)
@limiter.limit("10/minute")
async def migrate_durability(request: Request, body: MigrateDurabilityRequest):
    """
    Classify and backfill durability for pre-v2.2 memories (null durability).

    Naturally idempotent — only targets memories with null durability.
    Default dry_run=true for safety.
    """
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        pg = await get_postgres_store()

        null_memories = await qdrant.scroll_null_durability()
        total_null = len(null_memories)

        per_tier: dict[str, int] = {"ephemeral": 0, "durable": 0, "permanent": 0}
        sample: list[MigrationSampleEntry] = []
        errors = 0
        classified = 0

        for memory_id, payload in null_memories:
            try:
                tier, reason = classify_durability(payload)
                per_tier[tier] += 1
                classified += 1

                if len(sample) < 20:
                    content = (payload.get("content") or "")[:120]
                    sample.append(MigrationSampleEntry(
                        id=memory_id,
                        content_preview=content,
                        assigned_tier=tier,
                        reason=reason,
                    ))

                if not body.dry_run:
                    await qdrant.update_durability(memory_id, tier)
                    await neo4j.update_durability(memory_id, tier)
                    await pg.log_audit(
                        action="durability_migration",
                        memory_id=memory_id,
                        actor="system",
                        details={"tier": tier, "reason": reason},
                    )
            except Exception as e:
                errors += 1
                logger.warning("migration_classify_error", memory_id=memory_id, error=str(e))

        logger.info(
            "durability_migration_complete",
            dry_run=body.dry_run,
            total_null=total_null,
            classified=classified,
            errors=errors,
            per_tier=per_tier,
        )

        return MigrateDurabilityResponse(
            total_null=total_null,
            classified=classified,
            errors=errors,
            per_tier=per_tier,
            sample=sample,
        )

    except Exception as e:
        logger.error("durability_migration_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# DOMAIN NORMALIZATION MIGRATION
# =============================================================


class NormalizeDomainsResponse(BaseModel):
    processed: int
    updated: int
    domain_mapping: dict[str, str]


@router.post("/domains/normalize", response_model=NormalizeDomainsResponse)
@limiter.limit("5/minute")
async def normalize_domains(request: Request):
    """
    One-time migration: normalize all memory domains to canonical list.

    Scrolls all memories, applies normalize_domain(), updates any that changed.
    Idempotent — safe to run multiple times.
    """
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        memories = await qdrant.scroll_all()

        processed = 0
        updated = 0
        domain_mapping: dict[str, str] = {}

        for memory_id, payload in memories:
            processed += 1
            current_domain = payload.get("domain", "general")
            normalized = normalize_domain(current_domain)

            if normalized != current_domain:
                domain_mapping[current_domain] = normalized

                # Update Qdrant payload
                await qdrant.client.set_payload(
                    collection_name=qdrant.collection,
                    payload={"domain": normalized},
                    points=[memory_id],
                )

                # Update Neo4j node
                async with neo4j.driver.session() as session:
                    await session.run(
                        "MATCH (m:Memory {id: $id}) SET m.domain = $domain",
                        id=memory_id, domain=normalized,
                    )

                updated += 1

        logger.info(
            "domain_normalization_complete",
            processed=processed,
            updated=updated,
            unique_mappings=len(domain_mapping),
        )

        return NormalizeDomainsResponse(
            processed=processed,
            updated=updated,
            domain_mapping=domain_mapping,
        )

    except Exception as e:
        logger.error("domain_normalization_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# DOMAIN RECLASSIFICATION (LLM-based)
# =============================================================


class ReclassifyDomainsResponse(BaseModel):
    scanned: int
    reclassified: int
    domain_changes: dict[str, int]
    errors: int


@router.post("/domains/reclassify", response_model=ReclassifyDomainsResponse)
@limiter.limit("2/minute")
async def reclassify_domains(request: Request):
    """
    LLM-based reclassification of memories stuck in the 'general' domain.

    Sends each general-domain memory's content to the LLM to classify
    into a canonical domain. Processes sequentially with delays to avoid
    overwhelming Ollama.
    """
    import asyncio
    import json

    from src.core.domains import CANONICAL_DOMAINS
    from src.core.llm import get_llm
    from qdrant_client.models import FieldCondition, MatchValue, Filter

    canonical_list = ", ".join(d for d in CANONICAL_DOMAINS if d != "general")
    prompt_template = (
        "Classify this memory into exactly one domain.\n"
        "Domains: {domains}\n\n"
        "Memory content:\n{content}\n\n"
        'Respond with JSON: {{"domain": "chosen_domain"}}\n'
        "If unsure, use the most specific domain that applies. "
        "Only use 'general' if absolutely nothing else fits."
    )

    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()
        llm = await get_llm()

        # Scroll only "general" domain memories
        all_points = []
        offset = None
        while True:
            points, next_offset = await qdrant.client.scroll(
                collection_name=qdrant.collection,
                scroll_filter=Filter(must=[
                    FieldCondition(
                        key="domain",
                        match=MatchValue(value="general"),
                    ),
                ]),
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                all_points.append((str(point.id), point.payload or {}))
            if next_offset is None:
                break
            offset = next_offset

        scanned = len(all_points)
        reclassified = 0
        errors = 0
        domain_changes: dict[str, int] = {}

        for i, (memory_id, payload) in enumerate(all_points):
            content = payload.get("content", "")
            if not content or len(content) < 10:
                continue

            # Truncate long content to avoid blowing context
            truncated = content[:500]

            prompt = prompt_template.format(
                domains=canonical_list,
                content=truncated,
            )

            try:
                raw = await llm.generate(prompt, temperature=0.1, format_json=True)
                parsed = json.loads(raw)
                new_domain = parsed.get("domain", "general").strip().lower()

                if new_domain == "general" or new_domain not in set(CANONICAL_DOMAINS):
                    continue

                # Update Qdrant
                await qdrant.client.set_payload(
                    collection_name=qdrant.collection,
                    payload={"domain": new_domain},
                    points=[memory_id],
                )

                # Update Neo4j
                async with neo4j.driver.session() as session:
                    await session.run(
                        "MATCH (m:Memory {id: $id}) SET m.domain = $domain",
                        id=memory_id, domain=new_domain,
                    )

                reclassified += 1
                domain_changes[new_domain] = domain_changes.get(new_domain, 0) + 1

            except Exception as e:
                logger.debug("reclassify_error", memory_id=memory_id, error=str(e))
                errors += 1

            # Rate limit: 1 LLM call per second
            if (i + 1) % 5 == 0:
                await asyncio.sleep(2)

        logger.info(
            "domain_reclassification_complete",
            scanned=scanned,
            reclassified=reclassified,
            errors=errors,
        )

        return ReclassifyDomainsResponse(
            scanned=scanned,
            reclassified=reclassified,
            domain_changes=domain_changes,
            errors=errors,
        )

    except Exception as e:
        logger.error("domain_reclassification_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# GRAPH BOOTSTRAP
# =============================================================


class BootstrapGraphResponse(BaseModel):
    processed: int
    edges_created: int


@router.post("/graph/bootstrap", response_model=BootstrapGraphResponse)
@limiter.limit("2/minute")
async def bootstrap_graph(request: Request):
    """
    One-time bootstrap: create RELATED_TO edges for all existing memories.

    For each memory, searches for top-3 similar (>0.5) and creates edges.
    Processes in batches of 20 with 1s delay to avoid overwhelming Neo4j.
    Idempotent — strengthen_relationship uses MERGE.
    """
    import asyncio

    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        memories = await qdrant.scroll_all(with_vectors=True)

        processed = 0
        edges_created = 0
        batch_size = 20

        for i, (memory_id, payload, embedding) in enumerate(memories):
            if not embedding:
                continue

            # Search for similar memories
            similar = await qdrant.search(
                query_vector=embedding,
                limit=4,  # Extra for self-exclusion
            )

            for candidate_id, similarity, _ in similar:
                if candidate_id == memory_id:
                    continue
                if similarity < 0.5:
                    continue

                await neo4j.strengthen_relationship(
                    source_id=memory_id,
                    target_id=candidate_id,
                    increment=similarity * 0.5,
                )
                edges_created += 1

            processed += 1

            # Batch delay to avoid overwhelming Neo4j
            if (i + 1) % batch_size == 0:
                await asyncio.sleep(1.0)

        logger.info(
            "graph_bootstrap_complete",
            processed=processed,
            edges_created=edges_created,
        )

        return BootstrapGraphResponse(
            processed=processed,
            edges_created=edges_created,
        )

    except Exception as e:
        logger.error("graph_bootstrap_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# IMPORTANCE REHABILITATION
# =============================================================


class RehabilitateResponse(BaseModel):
    processed: int
    rehabilitated: int


@router.post("/importance/rehabilitate", response_model=RehabilitateResponse)
@limiter.limit("5/minute")
async def rehabilitate_importance(request: Request):
    """
    Rehabilitate floor-level memories that were over-decayed.

    Boosts importance for memories where:
    - access_count >= 3 or pinned: boost to max(importance, initial_importance * 0.5, 0.3)
    - durability is "durable" or "permanent": boost to max(importance, 0.2)

    Only targets memories with importance < 0.05.
    Idempotent — safe to run multiple times.
    """
    try:
        qdrant = await get_qdrant_store()
        neo4j = await get_neo4j_store()

        memories = await qdrant.scroll_all()

        processed = 0
        rehabilitated = 0

        for memory_id, payload in memories:
            importance = payload.get("importance", 0.5)

            # Only rehabilitate floor-level memories
            if importance >= 0.05:
                continue

            processed += 1
            new_importance = importance

            access_count = payload.get("access_count", 0)
            pinned = payload.get("pinned") == "true"
            durability = payload.get("durability")
            initial_importance = payload.get("initial_importance")

            # High-access or pinned memories deserve rehabilitation
            if access_count >= 3 or pinned:
                base = (initial_importance or 0.5) * 0.5
                new_importance = max(new_importance, base, 0.3)

            # Durable/permanent memories should not be at floor level
            if durability in ("durable", "permanent"):
                new_importance = max(new_importance, 0.2)

            if new_importance > importance:
                await qdrant.update_importance(memory_id, new_importance)
                await neo4j.update_importance(memory_id, new_importance)
                rehabilitated += 1

        logger.info(
            "importance_rehabilitation_complete",
            processed=processed,
            rehabilitated=rehabilitated,
        )

        return RehabilitateResponse(
            processed=processed,
            rehabilitated=rehabilitated,
        )

    except Exception as e:
        logger.error("importance_rehabilitation_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================
# ML RERANKER
# =============================================================


@router.post("/ml/retrain-ranker")
@limiter.limit("1/minute")
async def retrain_ranker(request: Request):
    """Train or retrain the retrieval reranker from feedback data."""
    try:
        from src.core.reranker_trainer import train_reranker

        pg = await get_postgres_store()
        qdrant = await get_qdrant_store()
        redis = await get_redis_store()

        result = await train_reranker(pg, qdrant, redis)
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="sklearn not installed — required for training",
        )
    except Exception as e:
        logger.error("retrain_ranker_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/ml/reranker-status")
async def reranker_status(request: Request):
    """Get current reranker model status."""
    import json
    from src.core.reranker import REDIS_KEY

    try:
        redis = await get_redis_store()
        raw = await redis.client.get(REDIS_KEY)

        if not raw:
            return {"status": "not_trained"}

        data = json.loads(raw)
        return {
            "status": "trained",
            "trained_at": data.get("trained_at"),
            "n_samples": data.get("n_samples"),
            "cv_score": data.get("cv_score"),
            "features": data.get("features"),
            "class_distribution": data.get("class_distribution"),
        }

    except Exception as e:
        logger.error("reranker_status_error", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
