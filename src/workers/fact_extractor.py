"""
Fact extractor — creates granular sub-embeddings for memories.

Each memory gets broken into atomic facts, each with its own embedding
in a separate Qdrant collection. This enables precise search matching.
"""

import asyncio
import json

import structlog

from src.core import get_embedding_service
from src.core.embeddings import OllamaUnavailableError
from src.core.llm import get_llm
from src.storage import get_qdrant_store

logger = structlog.get_logger()

# Limit concurrent fact extractions to prevent overwhelming Ollama.
# Each extraction does LLM generate + N embeddings — allowing too many
# concurrent extractions saturates Ollama and causes main store/search
# embedding calls to timeout.
_extraction_semaphore = asyncio.Semaphore(1)

FACT_PROMPT = """Extract 1-5 atomic, self-contained facts from this text.
Each fact should be a single sentence independently useful for search.
Include specific values (ports, versions, names, paths).
Skip vague or obvious statements.

Text: {content}

Return JSON array of strings only: ["fact 1", "fact 2"]
Return [] if content is too short or vague."""


async def extract_facts_for_memory(
    memory_id: str, content: str, domain: str = "general"
):
    """
    Extract atomic facts from a memory and store as sub-embeddings.

    Called as a BackgroundTask after memory store or by the observer.
    Uses a semaphore to prevent overwhelming Ollama with concurrent requests.
    """
    try:
        # Delay to let main store/search operations complete first.
        # Without this, fact extraction competes for Ollama GPU with
        # the main embedding calls and causes timeouts under load.
        await asyncio.sleep(2)

        async with _extraction_semaphore:
            await _run_fact_extraction(memory_id, content, domain)
    except Exception as e:
        logger.error(
            "fact_extraction_failed",
            memory_id=memory_id,
            error=str(e),
            error_type=type(e).__name__,
        )


async def _run_fact_extraction(memory_id: str, content: str, domain: str):
    """Inner implementation of fact extraction."""
    # Skip very short content
    if len(content) < 30:
        return

    llm = await get_llm()
    prompt = FACT_PROMPT.format(content=content[:3000])

    try:
        response = await llm.generate(prompt, format_json=True, temperature=0.1)
    except Exception as e:
        logger.warning("fact_extractor_llm_error", memory_id=memory_id, error=str(e))
        return

    facts = _parse_facts(response)
    if not facts:
        return

    qdrant = await get_qdrant_store()
    embedding_service = await get_embedding_service()

    stored = 0
    for i, fact_text in enumerate(facts[:5]):
        if not fact_text or len(fact_text) < 10:
            continue

        try:
            embedding = await embedding_service.embed(fact_text)
            await qdrant.store_fact(
                parent_id=memory_id,
                fact_content=fact_text,
                fact_index=i,
                embedding=embedding,
                domain=domain,
            )
            stored += 1
        except OllamaUnavailableError:
            logger.warning("fact_extractor_embedding_unavailable")
            return
        except Exception as e:
            logger.warning("fact_store_error", fact_index=i, error=str(e))

    if stored:
        logger.info("facts_extracted", memory_id=memory_id, facts=stored)


def _parse_facts(response: str) -> list[str]:
    """Parse LLM response into list of fact strings."""
    try:
        data = json.loads(response)
        if isinstance(data, list):
            return [str(f) for f in data if f]
        if isinstance(data, dict) and "facts" in data:
            return [str(f) for f in data["facts"] if f]
        return []
    except json.JSONDecodeError:
        return []
