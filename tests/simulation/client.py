"""
TimedRecallClient — Enhanced Recall API client with per-request latency tracking
and run-ID-based isolation for testbed suites.
"""

import asyncio
import time
from collections import defaultdict

import httpx


class TimedRecallClient:
    """Recall API client that tracks latencies and tags everything with a run ID."""

    def __init__(self, base_url: str, api_key: str, run_id: str, timeout: float = 120.0):
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.run_id = run_id
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

        # Per-operation latency tracking: "POST /memory/store" -> [0.045, 0.052, ...]
        self.latencies: dict[str, list[float]] = defaultdict(list)
        # Tracked memory IDs for cleanup
        self.tracked_ids: list[str] = []
        # Tracked session IDs for cleanup
        self.tracked_sessions: list[str] = []
        # Tracked document IDs for cleanup
        self.tracked_documents: list[str] = []
        # 429 count
        self.rate_limited: int = 0

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout, headers=self.headers)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, method: str, path: str, body=None) -> dict | list | None:
        """Make a timed API request. Returns parsed JSON on success, None on error."""
        client = await self._get_client()
        op_key = f"{method} {path.split('?')[0]}"
        t0 = time.monotonic()

        try:
            if method == "GET":
                r = await client.get(f"{self.base}{path}")
            elif method == "POST":
                r = await client.post(f"{self.base}{path}", json=body)
            elif method == "DELETE":
                r = await client.delete(f"{self.base}{path}")
            else:
                return None

            elapsed = time.monotonic() - t0
            self.latencies[op_key].append(elapsed)

            if r.status_code == 429:
                self.rate_limited += 1
                return None
            if r.status_code >= 400:
                return None

            return r.json() if r.text else {}

        except Exception:
            elapsed = time.monotonic() - t0
            self.latencies[op_key].append(elapsed)
            return None

    def latency_stats(self, operation: str | None = None) -> dict:
        """Get latency stats for a specific operation or all operations."""
        if operation:
            values = self.latencies.get(operation, [])
            return self._compute_stats(values)

        # All operations
        all_stats = {}
        for op, values in sorted(self.latencies.items()):
            all_stats[op] = self._compute_stats(values)
        return all_stats

    @staticmethod
    def _compute_stats(values: list[float]) -> dict:
        if not values:
            return {"count": 0}
        s = sorted(values)
        n = len(s)
        return {
            "count": n,
            "mean": round(sum(s) / n, 4),
            "min": round(s[0], 4),
            "max": round(s[-1], 4),
            "p50": round(s[n // 2], 4),
            "p95": round(s[int(n * 0.95)], 4),
            "p99": round(s[int(n * 0.99)], 4),
        }

    # ── Domain/tag helpers ──

    def suite_domain(self, suite_name: str) -> str:
        return f"testbed-{suite_name}-{self.run_id}"

    def run_tag(self) -> str:
        return f"testbed:{self.run_id}"

    # ── Session management ──

    async def create_session(self, task: str = "") -> str | None:
        r = await self._request("POST", "/session/start", {
            "current_task": task or None,
        })
        if r and "session_id" in r:
            self.tracked_sessions.append(r["session_id"])
            return r["session_id"]
        return None

    async def get_session_status(self, sid: str) -> dict | None:
        return await self._request("GET", f"/session/{sid}")

    async def end_session(self, sid: str):
        return await self._request("POST", "/session/end", {
            "session_id": sid,
            "trigger_consolidation": False,
        })

    async def ingest_turns(self, sid: str, turns: list[dict]):
        return await self._request("POST", "/ingest/turns", {
            "session_id": sid,
            "turns": turns,
        })

    async def get_signals(self, sid: str) -> list[dict]:
        r = await self._request("GET", f"/ingest/{sid}/signals")
        if isinstance(r, list):
            return r
        if isinstance(r, dict):
            return r.get("signals", [])
        return []

    async def approve_signal(self, sid: str, index: int = 0) -> dict | None:
        return await self._request("POST", f"/ingest/{sid}/signals/approve", {
            "index": index,
        })

    # ── Memory operations ──

    async def store_memory(
        self,
        content: str,
        domain: str,
        memory_type: str = "semantic",
        tags: list[str] | None = None,
        importance: float = 0.5,
        session_id: str | None = None,
        durability: str | None = None,
    ) -> dict | None:
        """Store a memory tagged with the run ID. Returns full response dict."""
        all_tags = [self.run_tag()] + (tags or [])
        body = {
            "content": content,
            "memory_type": memory_type,
            "domain": domain,
            "tags": all_tags,
            "importance": importance,
            "session_id": session_id,
        }
        if durability:
            body["durability"] = durability
        r = await self._request("POST", "/memory/store", body)
        if r and r.get("id"):
            self.tracked_ids.append(r["id"])
        return r

    async def get_memory(self, memory_id: str) -> dict | None:
        return await self._request("GET", f"/memory/{memory_id}")

    async def delete_memory(self, memory_id: str) -> dict | None:
        return await self._request("DELETE", f"/memory/{memory_id}")

    async def batch_store(self, items: list[dict]) -> dict | None:
        """Batch store memories. Each item should have content, domain, etc.
        Adds run_tag to each item's tags automatically."""
        for item in items:
            item.setdefault("tags", [])
            if self.run_tag() not in item["tags"]:
                item["tags"].append(self.run_tag())
        r = await self._request("POST", "/memory/batch/store", {"memories": items})
        if r and "results" in r:
            for res in r["results"]:
                if res.get("created") and res.get("id"):
                    self.tracked_ids.append(res["id"])
        return r

    async def batch_delete(self, ids: list[str]) -> dict | None:
        return await self._request("POST", "/memory/batch/delete", {"ids": ids})

    # ── Pinning ──

    async def pin_memory(self, memory_id: str) -> dict | None:
        return await self._request("POST", f"/memory/{memory_id}/pin")

    async def unpin_memory(self, memory_id: str) -> dict | None:
        return await self._request("DELETE", f"/memory/{memory_id}/pin")

    # ── Anti-patterns ──

    async def create_anti_pattern(
        self,
        pattern: str,
        warning: str,
        alternative: str | None = None,
        severity: str = "warning",
        domain: str = "general",
        tags: list[str] | None = None,
    ) -> dict | None:
        body = {
            "pattern": pattern,
            "warning": warning,
            "severity": severity,
            "domain": domain,
            "tags": (tags or []) + [self.run_tag()],
        }
        if alternative:
            body["alternative"] = alternative
        return await self._request("POST", "/memory/anti-pattern", body)

    async def list_anti_patterns(self, domain: str | None = None) -> list[dict]:
        path = "/memory/anti-patterns"
        if domain:
            path += f"?domain={domain}"
        r = await self._request("GET", path)
        if isinstance(r, dict):
            return r.get("anti_patterns", [])
        if isinstance(r, list):
            return r
        return []

    async def delete_anti_pattern(self, ap_id: str) -> dict | None:
        return await self._request("DELETE", f"/memory/anti-pattern/{ap_id}")

    # ── Feedback ──

    async def submit_feedback(
        self,
        injected_ids: list[str],
        assistant_text: str,
    ) -> dict | None:
        return await self._request("POST", "/memory/feedback", {
            "injected_ids": injected_ids,
            "assistant_text": assistant_text,
        })

    # ── Relationships ──

    async def create_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        strength: float = 0.5,
        bidirectional: bool = False,
    ) -> dict | None:
        return await self._request("POST", "/memory/relationship", {
            "source_id": source_id,
            "target_id": target_id,
            "relationship_type": relationship_type,
            "strength": strength,
            "bidirectional": bidirectional,
        })

    # ── Search ──

    async def search_query(
        self,
        query: str,
        limit: int = 10,
        domains: list[str] | None = None,
        expand_relationships: bool = True,
        user: str | None = None,
    ) -> list[dict]:
        r = await self._request("POST", "/search/query", {
            "query": query,
            "limit": limit,
            "domains": domains,
            "expand_relationships": expand_relationships,
            "user": user,
        })
        if r and "results" in r:
            return r["results"]
        return []

    async def search_browse(
        self,
        query: str,
        limit: int = 10,
        domains: list[str] | None = None,
        session_id: str | None = None,
    ) -> list[dict]:
        body: dict = {
            "query": query,
            "limit": limit,
            "domains": domains,
        }
        if session_id:
            body["session_id"] = session_id
        r = await self._request("POST", "/search/browse", body)
        if r and "results" in r:
            return r["results"]
        return []

    async def search_timeline(
        self,
        limit: int = 20,
        domain: str | None = None,
    ) -> list[dict]:
        r = await self._request("POST", "/search/timeline", {
            "limit": limit,
            "domain": domain,
        })
        if r and "entries" in r:
            return r["entries"]
        return []

    # ── Admin / maintenance ──

    async def health(self) -> dict | None:
        return await self._request("GET", "/health")

    async def stats(self) -> dict | None:
        return await self._request("GET", "/stats")

    async def decay(self, simulate_hours: float = 0.0) -> dict | None:
        return await self._request("POST", "/admin/decay", {
            "simulate_hours": simulate_hours,
        })

    async def consolidate(
        self,
        domain: str | None = None,
        dry_run: bool = False,
        min_cluster_size: int = 2,
    ) -> dict | None:
        return await self._request("POST", "/admin/consolidate", {
            "domain": domain,
            "dry_run": dry_run,
            "min_cluster_size": min_cluster_size,
        })

    async def reconcile(self, repair: bool = False) -> dict | None:
        return await self._request("POST", f"/admin/reconcile?repair={'true' if repair else 'false'}")

    async def ollama_info(self) -> dict | None:
        return await self._request("GET", "/admin/ollama")

    # ── Durability ──

    async def put_durability(self, memory_id: str, durability: str) -> dict | None:
        """Set durability tier on a memory."""
        client = await self._get_client()
        op_key = "PUT /memory/{id}/durability"
        t0 = time.monotonic()
        try:
            r = await client.put(
                f"{self.base}/memory/{memory_id}/durability",
                json={"durability": durability},
            )
            self.latencies[op_key].append(time.monotonic() - t0)
            if r.status_code == 429:
                self.rate_limited += 1
                return None
            if r.status_code >= 400:
                return None
            return r.json() if r.text else {}
        except Exception:
            self.latencies[op_key].append(time.monotonic() - t0)
            return None

    # ── Documents ──

    async def ingest_document(
        self,
        content: bytes,
        filename: str,
        domain: str,
        file_type: str = "text",
        durability: str | None = None,
    ) -> dict | None:
        """Upload a file for document ingestion (multipart).
        Uses a separate client without Content-Type header so httpx can
        set multipart/form-data with boundary automatically."""
        op_key = "POST /document/ingest"
        t0 = time.monotonic()
        try:
            files = {"file": (filename, content, "text/plain")}
            data = {"domain": domain, "file_type": file_type}
            if durability:
                data["durability"] = durability
            # Must NOT include Content-Type — httpx sets it for multipart
            upload_headers = {"Authorization": f"Bearer {self.api_key}"}
            async with httpx.AsyncClient(timeout=self._timeout) as upload_client:
                r = await upload_client.post(
                    f"{self.base}/document/ingest",
                    files=files,
                    data=data,
                    headers=upload_headers,
                )
            self.latencies[op_key].append(time.monotonic() - t0)
            if r.status_code == 429:
                self.rate_limited += 1
                return None
            if r.status_code >= 400:
                return None
            result = r.json()
            # Track document and child IDs for cleanup
            if result and result.get("document", {}).get("id"):
                self.tracked_documents.append(result["document"]["id"])
            if result and result.get("child_ids"):
                self.tracked_ids.extend(result["child_ids"])
            return result
        except Exception:
            self.latencies[op_key].append(time.monotonic() - t0)
            return None

    async def list_documents(self, domain: str | None = None) -> list[dict]:
        path = "/document/"
        if domain:
            path += f"?domain={domain}"
        r = await self._request("GET", path)
        return r if isinstance(r, list) else []

    async def get_document(self, doc_id: str) -> dict | None:
        return await self._request("GET", f"/document/{doc_id}")

    async def delete_document(self, doc_id: str) -> dict | None:
        return await self._request("DELETE", f"/document/{doc_id}")

    async def pin_document(self, doc_id: str) -> dict | None:
        return await self._request("POST", f"/document/{doc_id}/pin")

    async def unpin_document(self, doc_id: str) -> dict | None:
        return await self._request("DELETE", f"/document/{doc_id}/pin")

    async def update_document(self, doc_id: str, **fields) -> dict | None:
        """PATCH document (domain, durability)."""
        client = await self._get_client()
        op_key = "PATCH /document/{id}"
        t0 = time.monotonic()
        try:
            r = await client.patch(
                f"{self.base}/document/{doc_id}",
                json=fields,
            )
            self.latencies[op_key].append(time.monotonic() - t0)
            if r.status_code == 429:
                self.rate_limited += 1
                return None
            if r.status_code >= 400:
                return None
            return r.json() if r.text else {}
        except Exception:
            self.latencies[op_key].append(time.monotonic() - t0)
            return None

    # ── Cleanup ──

    async def cleanup(self):
        """Delete all tracked documents, memories, and end all tracked sessions."""
        # Delete documents first (cascade deletes children)
        for doc_id in self.tracked_documents:
            try:
                await self.delete_document(doc_id)
                await asyncio.sleep(0.3)
            except Exception:
                pass

        # End open sessions
        for sid in self.tracked_sessions:
            try:
                await self.end_session(sid)
            except Exception:
                pass

        # Batch delete tracked memories (100 per request)
        remaining = list(set(self.tracked_ids))
        while remaining:
            batch = remaining[:100]
            remaining = remaining[100:]
            try:
                await self.batch_delete(batch)
            except Exception:
                pass
            if remaining:
                await asyncio.sleep(0.5)
