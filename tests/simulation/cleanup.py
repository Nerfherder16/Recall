"""
Cleanup utility — delete all testbed data for a given run ID.

Usable standalone or imported by the testbed orchestrator.
"""

import asyncio
import os
import sys

import httpx


async def cleanup_run(api_url: str, api_key: str, run_id: str, verbose: bool = False):
    """
    Clean up all memories tagged with a testbed run ID.

    Strategy:
    1. Search by tag testbed:{run_id} via browse
    2. Collect all matching IDs
    3. Batch delete in groups of 100
    """
    base = api_url.rstrip("/")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    tag = f"testbed:{run_id}"

    async with httpx.AsyncClient(timeout=60.0, headers=headers) as client:
        # Search for tagged memories across multiple queries
        all_ids: set[str] = set()

        # Use browse search with tag filter
        for query_text in ["testbed", "test", "simulation", "stress"]:
            try:
                r = await client.post(f"{base}/search/browse", json={
                    "query": query_text,
                    "tags": [tag],
                    "limit": 100,
                })
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    for res in results:
                        all_ids.add(res["id"])
            except Exception:
                pass
            await asyncio.sleep(2)  # Rate limit

        # Also search by domain prefix
        for suite in ["lifecycle", "retrieval", "stress", "signals", "time_accel"]:
            domain = f"testbed-{suite}-{run_id}"
            try:
                r = await client.post(f"{base}/search/timeline", json={
                    "domain": domain,
                    "limit": 100,
                })
                if r.status_code == 200:
                    entries = r.json().get("entries", [])
                    for entry in entries:
                        all_ids.add(entry["id"])
            except Exception:
                pass
            await asyncio.sleep(2)

        if verbose:
            print(f"Found {len(all_ids)} memories to clean up for run {run_id}")

        if not all_ids:
            if verbose:
                print("Nothing to clean up.")
            return 0

        # Batch delete
        id_list = list(all_ids)
        deleted_total = 0
        while id_list:
            batch = id_list[:100]
            id_list = id_list[100:]
            try:
                r = await client.post(f"{base}/memory/batch/delete", json={"ids": batch})
                if r.status_code == 200:
                    result = r.json()
                    deleted_total += result.get("deleted", 0)
            except Exception as e:
                if verbose:
                    print(f"Batch delete error: {e}")
            if id_list:
                await asyncio.sleep(1)

        if verbose:
            print(f"Deleted {deleted_total} memories for run {run_id}")

        return deleted_total


def main():
    """CLI entry point for standalone cleanup."""
    if len(sys.argv) < 2:
        print("Usage: python -m tests.simulation.cleanup <run_id> [--api URL] [--api-key KEY]")
        sys.exit(1)

    run_id = sys.argv[1]
    api_url = os.environ.get("RECALL_API_URL", "http://localhost:8200")
    api_key = "test"

    for i, arg in enumerate(sys.argv):
        if arg == "--api" and i + 1 < len(sys.argv):
            api_url = sys.argv[i + 1]
        if arg == "--api-key" and i + 1 < len(sys.argv):
            api_key = sys.argv[i + 1]

    print(f"Cleaning up run {run_id} on {api_url}...")
    deleted = asyncio.run(cleanup_run(api_url, api_key, run_id, verbose=True))
    print(f"Done. Deleted {deleted} memories.")


if __name__ == "__main__":
    main()
