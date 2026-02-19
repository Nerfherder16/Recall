"""
Observer worker — extracts facts from file changes and stores them as memories.

Called as a BackgroundTask from the /observe/file-change endpoint.
"""

import json

import structlog

from src.core import Memory, MemorySource, MemoryType, get_embedding_service
from src.core.domains import normalize_domain
from src.core.embeddings import OllamaUnavailableError, content_hash
from src.core.llm import get_llm
from src.core.models import Durability
from src.storage import get_neo4j_store, get_postgres_store, get_qdrant_store

logger = structlog.get_logger()

OBSERVER_PROMPT = """Analyze this code change and extract facts worth remembering long-term.

File: {file_path}
Change type: {tool_name}
{change_description}

Extract ONLY concrete, reusable facts:
- Configuration values (ports, URLs, paths, credential patterns)
- Architectural decisions visible in the code
- API endpoints being created/modified
- Bug fixes and what caused them
- Dependencies and their usage patterns

Skip: variable names, obvious code, temporary debug changes, formatting-only changes.

Domain must be one of: general, infrastructure, development, testing, security, api,
database, frontend, devops, networking, ai-ml, tooling, configuration, documentation, sessions

Return JSON array: [{{"fact": "...", "domain": "...", "tags": ["..."]}}]
Return [] if nothing worth remembering."""


async def extract_and_store_observations(observation: dict):
    """
    Extract facts from a file change observation and store as memories.

    Wrapped in top-level try/except so BackgroundTask failures
    are always logged.
    """
    try:
        await _run_extraction(observation)
    except Exception as e:
        logger.error(
            "observer_extraction_failed",
            file=observation.get("file_path"),
            error=str(e),
            error_type=type(e).__name__,
        )


async def _run_extraction(observation: dict):
    """Inner implementation of observation extraction."""
    file_path = observation.get("file_path", "")
    tool_name = observation.get("tool_name", "Write")

    # Build change description
    if tool_name == "Edit" and observation.get("old_string") and observation.get("new_string"):
        old = observation["old_string"][:2000]
        new = observation["new_string"][:2000]
        change_desc = f"Replaced:\n```\n{old}\n```\nWith:\n```\n{new}\n```"
    elif observation.get("content"):
        change_desc = f"File content (truncated):\n```\n{observation['content'][:3000]}\n```"
    else:
        logger.debug("observer_no_content", file=file_path)
        return

    prompt = OBSERVER_PROMPT.format(
        file_path=file_path,
        tool_name=tool_name,
        change_description=change_desc,
    )

    # Call LLM
    llm = await get_llm()
    try:
        response = await llm.generate(prompt, format_json=True, temperature=0.2)
    except Exception as e:
        logger.warning("observer_llm_error", error=str(e))
        return

    # Parse response
    facts = _parse_facts(response)
    if not facts:
        logger.debug("observer_no_facts", file=file_path)
        return

    # Store each fact as a memory
    stored = 0
    for fact_data in facts[:5]:  # Cap at 5 facts per observation
        fact_text = fact_data.get("fact", "")
        if not fact_text or len(fact_text) < 10:
            continue

        domain = normalize_domain(fact_data.get("domain", "general"))
        tags = fact_data.get("tags", [])

        chash = content_hash(fact_text)

        qdrant = await get_qdrant_store()
        existing = await qdrant.find_by_content_hash(chash)
        if existing:
            continue  # Dedup

        memory = Memory(
            content=fact_text,
            content_hash=chash,
            memory_type=MemoryType.SEMANTIC,
            source=MemorySource.SYSTEM,
            domain=domain,
            tags=["observer"] + tags,
            importance=0.4,
            confidence=0.6,
            metadata={"observer": True, "source_file": file_path},
            durability=Durability.DURABLE,
            initial_importance=0.4,
        )

        try:
            embedding_service = await get_embedding_service()
            embedding = await embedding_service.embed(fact_text)
        except OllamaUnavailableError:
            logger.warning("observer_embedding_unavailable")
            return

        await qdrant.store(memory, embedding)

        try:
            neo4j = await get_neo4j_store()
            await neo4j.create_memory_node(memory)
        except Exception as neo4j_err:
            logger.error("observer_neo4j_failed", id=memory.id, error=str(neo4j_err))
            await qdrant.delete(memory.id)
            continue

        # Audit (fire-and-forget)
        try:
            pg = await get_postgres_store()
            await pg.log_audit(
                "create",
                memory.id,
                actor="observer",
                details={"source_file": file_path, "tool": tool_name},
            )
        except Exception as audit_err:
            logger.warning("observer_audit_failed", error=str(audit_err))

        # Auto-link to similar memories
        try:
            from src.core.auto_linker import auto_link_memory

            await auto_link_memory(memory.id, embedding, domain)
        except Exception as link_err:
            logger.debug("observer_auto_link_skipped", error=str(link_err))

        # Trigger fact extraction for sub-embeddings
        try:
            from src.workers.fact_extractor import extract_facts_for_memory

            await extract_facts_for_memory(memory.id, fact_text, domain)
        except Exception as e:
            logger.debug("observer_fact_extraction_skipped", error=str(e))

        stored += 1

    if stored:
        logger.info("observer_stored", file=file_path, facts=stored)


async def save_session_snapshot(session_id: str, summary: str | None):
    """Save a session snapshot as a memory on Stop hook."""
    try:
        from src.storage import get_redis_store

        redis = await get_redis_store()
        session = await redis.get_session(session_id)
        if not session:
            logger.debug("snapshot_no_session", session_id=session_id)
            return

        task = session.get("current_task", "unknown task")
        memories_created = session.get("memories_created", 0)
        signals_detected = session.get("signals_detected", 0)

        snapshot_text = summary or (
            f"Session worked on: {task}. "
            f"Created {memories_created} memories, "
            f"detected {signals_detected} signals."
        )

        chash = content_hash(snapshot_text)
        qdrant = await get_qdrant_store()
        if await qdrant.find_by_content_hash(chash):
            return

        memory = Memory(
            content=snapshot_text,
            content_hash=chash,
            memory_type=MemoryType.EPISODIC,
            source=MemorySource.SYSTEM,
            domain="sessions",
            tags=["session-snapshot"],
            importance=0.3,
            confidence=0.9,
            session_id=session_id,
            metadata={"snapshot": True},
            durability=Durability.EPHEMERAL,
            initial_importance=0.3,
        )

        embedding_service = await get_embedding_service()
        embedding = await embedding_service.embed(snapshot_text)
        await qdrant.store(memory, embedding)

        try:
            neo4j = await get_neo4j_store()
            await neo4j.create_memory_node(memory)
        except Exception as neo4j_err:
            logger.error(
                "snapshot_neo4j_failed_compensating",
                id=memory.id,
                error=str(neo4j_err),
            )
            await qdrant.delete(memory.id)
            raise

        try:
            pg = await get_postgres_store()
            await pg.log_audit(
                "create",
                memory.id,
                actor="observer",
                session_id=session_id,
            )
        except Exception as audit_err:
            logger.warning("snapshot_audit_failed", error=str(audit_err))

        logger.info("session_snapshot_saved", session_id=session_id, memory_id=memory.id)

    except Exception as e:
        logger.error("session_snapshot_error", session_id=session_id, error=str(e))


def _parse_facts(response: str) -> list[dict]:
    """Parse LLM response into list of fact dicts."""
    try:
        data = json.loads(response)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # LLM might return {"facts": [...]}
            if "facts" in data:
                return data["facts"]
            # Single fact
            if "fact" in data:
                return [data]
        return []
    except json.JSONDecodeError:
        return []
