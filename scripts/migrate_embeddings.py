#!/usr/bin/env python3
"""
Migrate embeddings from BGE-large to Qwen3-Embedding-0.6B.

This script:
1. Verifies Ollama is reachable and qwen3-embedding:0.6b is available
2. Backs up all memories via /admin/export
3. Scrolls all Qdrant points and re-embeds content with the new model
4. Clears the facts sub-embedding collection (auto-regenerates on access)
5. Verifies the migration

Usage:
    python scripts/migrate_embeddings.py                          # Full migration
    python scripts/migrate_embeddings.py --dry-run                # Count only
    python scripts/migrate_embeddings.py --api-url http://host:8200  # Custom API
"""

import argparse
import sys
import time

import httpx

DEFAULT_API_URL = "http://192.168.50.19:8200"
DEFAULT_OLLAMA_URL = "http://192.168.50.62:11434"
MODEL = "qwen3-embedding:0.6b"
BACKUP_FILE = "backup_pre_migration.jsonl"
BATCH_SIZE = 10
PROGRESS_INTERVAL = 50


def log(msg: str):
    print(f"[MIGRATE] {msg}", flush=True)


def error(msg: str):
    print(f"[ERROR] {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def preflight(ollama_url: str, api_url: str, api_key: str | None):
    """Verify Ollama reachable, model available, API reachable."""
    log("Pre-flight checks...")

    # Check Ollama
    try:
        r = httpx.get(f"{ollama_url}/api/tags", timeout=10)
        r.raise_for_status()
        models = [m.get("name", "") for m in r.json().get("models", [])]
        if MODEL not in models and f"{MODEL}:latest" not in models:
            # Check partial match (ollama may report as qwen3-embedding:0.6b)
            found = any("qwen3-embedding" in m for m in models)
            if not found:
                error(
                    f"Model {MODEL} not found in Ollama. "
                    f"Available: {models}. Run: ollama pull {MODEL}"
                )
            log(f"Found qwen3-embedding variant in Ollama models")
        else:
            log(f"Model {MODEL} available in Ollama")
    except httpx.RequestError as e:
        error(f"Cannot reach Ollama at {ollama_url}: {e}")

    # Check API
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        r = httpx.get(f"{api_url}/health", timeout=10)
        r.raise_for_status()
        log(f"Recall API healthy at {api_url}")
    except httpx.RequestError as e:
        error(f"Cannot reach Recall API at {api_url}: {e}")

    # Count memories via stats
    try:
        r = httpx.get(f"{api_url}/stats", headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        count = data.get("memories", {}).get("total", "?")
        log(f"Total memories to re-embed: {count}")
        return count
    except Exception as e:
        log(f"Could not get memory count: {e}")
        return "?"


def backup(api_url: str, api_key: str | None):
    """Export all memories to JSONL backup file."""
    log(f"Backing up to {BACKUP_FILE}...")
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        with httpx.stream(
            "GET",
            f"{api_url}/admin/export?include_embeddings=true",
            headers=headers,
            timeout=300,
        ) as r:
            r.raise_for_status()
            line_count = 0
            with open(BACKUP_FILE, "w", encoding="utf-8") as f:
                for line in r.iter_lines():
                    if line.strip():
                        f.write(line + "\n")
                        line_count += 1
        log(f"Backup complete: {line_count} records to {BACKUP_FILE}")
    except Exception as e:
        error(f"Backup failed: {e}")


def embed_text(ollama_url: str, text: str) -> list[float]:
    """Embed a single text using the new model (passage mode, no prefix)."""
    r = httpx.post(
        f"{ollama_url}/api/embed",
        json={"model": MODEL, "input": text},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    embeddings = data.get("embeddings", [])
    if not embeddings:
        raise ValueError("Empty embeddings response")
    return embeddings[0]


def embed_batch_texts(ollama_url: str, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts using native batch API."""
    r = httpx.post(
        f"{ollama_url}/api/embed",
        json={"model": MODEL, "input": texts},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    embeddings = data.get("embeddings", [])
    if len(embeddings) != len(texts):
        raise ValueError(
            f"Batch mismatch: sent {len(texts)}, got {len(embeddings)}"
        )
    return embeddings


def migrate_qdrant(
    api_url: str,
    ollama_url: str,
    api_key: str | None,
    qdrant_url: str,
    collection: str,
):
    """Scroll all Qdrant points and re-embed with new model."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointVectors

    log(f"Connecting to Qdrant at {qdrant_url}...")
    client = QdrantClient(url=qdrant_url, timeout=60)

    # Get total count
    info = client.get_collection(collection)
    total = info.points_count
    log(f"Collection '{collection}': {total} points to re-embed")

    offset = None
    processed = 0
    errors = 0
    start_time = time.time()

    while True:
        # Scroll batch
        points, next_offset = client.scroll(
            collection_name=collection,
            limit=BATCH_SIZE,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        if not points:
            break

        # Extract content from payloads
        texts = []
        point_ids = []
        for point in points:
            content = point.payload.get("content", "")
            if content:
                texts.append(content)
                point_ids.append(point.id)
            else:
                log(f"  Skipping point {point.id} — no content")

        # Batch embed
        if texts:
            try:
                new_embeddings = embed_batch_texts(ollama_url, texts)

                # Upsert vectors back
                client.update_vectors(
                    collection_name=collection,
                    points=[
                        PointVectors(id=pid, vector=vec)
                        for pid, vec in zip(point_ids, new_embeddings)
                    ],
                )
                processed += len(texts)
            except Exception as e:
                # Fallback: one at a time
                log(f"  Batch failed ({e}), falling back to sequential...")
                for pid, text in zip(point_ids, texts):
                    try:
                        vec = embed_text(ollama_url, text)
                        client.update_vectors(
                            collection_name=collection,
                            points=[PointVectors(id=pid, vector=vec)],
                        )
                        processed += 1
                    except Exception as e2:
                        errors += 1
                        log(f"  Error re-embedding {pid}: {e2}")

        if processed % PROGRESS_INTERVAL == 0 and processed > 0:
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            log(f"  Progress: {processed}/{total} ({rate:.1f}/sec)")

        offset = next_offset
        if offset is None:
            break

    elapsed = time.time() - start_time
    log(
        f"Main collection done: {processed} re-embedded, "
        f"{errors} errors, {elapsed:.1f}s"
    )
    return processed, errors


def clear_facts(qdrant_url: str, collection: str):
    """Delete and recreate the facts sub-embedding collection."""
    from qdrant_client import QdrantClient

    facts_collection = f"{collection}_facts"
    client = QdrantClient(url=qdrant_url, timeout=60)

    collections = [c.name for c in client.get_collections().collections]
    if facts_collection in collections:
        info = client.get_collection(facts_collection)
        count = info.points_count
        log(f"Deleting facts collection '{facts_collection}' ({count} points)...")
        client.delete_collection(facts_collection)
        log("Facts collection deleted — will regenerate on next access")
    else:
        log("No facts collection found — nothing to clear")


def verify(api_url: str, api_key: str | None):
    """Run a test search to verify embeddings work."""
    log("Verifying migration...")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        r = httpx.post(
            f"{api_url}/search/browse",
            headers=headers,
            json={"query": "test migration verification", "limit": 3},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        results = data.get("results", [])
        log(f"Search returned {len(results)} results — embeddings working")
    except Exception as e:
        log(f"Verification search failed: {e}")
        log("This may be expected if the API hasn't restarted with new config yet")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate Recall embeddings from BGE-large to Qwen3-Embedding-0.6B"
    )
    parser.add_argument(
        "--api-url", default=DEFAULT_API_URL, help="Recall API URL"
    )
    parser.add_argument(
        "--ollama-url", default=DEFAULT_OLLAMA_URL, help="Ollama API URL"
    )
    parser.add_argument(
        "--api-key", default=None, help="Recall API key (if auth enabled)"
    )
    parser.add_argument(
        "--qdrant-url",
        default="http://192.168.50.19:6333",
        help="Qdrant URL (direct, not through API)",
    )
    parser.add_argument(
        "--collection", default="recall_memories", help="Qdrant collection name"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count memories without modifying anything",
    )
    parser.add_argument(
        "--skip-backup",
        action="store_true",
        help="Skip JSONL backup (if you already have one)",
    )
    args = parser.parse_args()

    log("=" * 50)
    log("Recall Embedding Migration: BGE-large -> Qwen3-Embedding-0.6B")
    log("=" * 50)
    log(f"API:    {args.api_url}")
    log(f"Ollama: {args.ollama_url}")
    log(f"Qdrant: {args.qdrant_url}")
    log(f"Mode:   {'DRY RUN' if args.dry_run else 'LIVE MIGRATION'}")
    log("")

    # Step 1: Pre-flight
    count = preflight(args.ollama_url, args.api_url, args.api_key)

    if args.dry_run:
        log("")
        log(f"DRY RUN complete. {count} memories would be re-embedded.")
        log("Run without --dry-run to perform migration.")
        return

    # Step 2: Backup
    if not args.skip_backup:
        backup(args.api_url, args.api_key)
    else:
        log("Skipping backup (--skip-backup)")

    # Step 3: Re-embed main collection
    log("")
    log("Re-embedding main collection...")
    processed, errors = migrate_qdrant(
        args.api_url,
        args.ollama_url,
        args.api_key,
        args.qdrant_url,
        args.collection,
    )

    # Step 4: Clear facts collection
    log("")
    clear_facts(args.qdrant_url, args.collection)

    # Step 5: Verify
    log("")
    verify(args.api_url, args.api_key)

    # Summary
    log("")
    log("=" * 50)
    log("Migration complete!")
    log(f"  Re-embedded: {processed}")
    log(f"  Errors:      {errors}")
    log(f"  Backup:      {BACKUP_FILE}")
    log("")
    log("Next steps:")
    log("  1. Deploy updated code (config.py + embeddings.py)")
    log("  2. docker compose restart api worker")
    log("  3. python -m tests.simulation.testbed --suites retrieval")
    log("=" * 50)


if __name__ == "__main__":
    main()
