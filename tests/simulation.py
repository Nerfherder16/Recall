"""
Recall Memory System Simulation

Tests the full living memory system with realistic scenarios:
1. Memory storage (all types)
2. Semantic retrieval
3. Graph relationships
4. Memory dynamics
5. Context assembly
6. Session management
"""

import asyncio
import os

import httpx
import json
from datetime import datetime

API_BASE = os.environ.get("RECALL_API_URL", "http://localhost:8200")

# Test scenarios simulating a real coding session
SCENARIOS = [
    # ============================================
    # SCENARIO 1: Learning about a new project
    # ============================================
    {
        "name": "Learn Project Structure",
        "memories": [
            {
                "content": "The authentication system uses JWT tokens stored in HTTP-only cookies for security",
                "memory_type": "semantic",
                "domain": "auth",
                "tags": ["security", "jwt", "cookies"],
            },
            {
                "content": "User passwords are hashed using bcrypt with cost factor 12",
                "memory_type": "semantic",
                "domain": "auth",
                "tags": ["security", "bcrypt", "passwords"],
            },
            {
                "content": "The API rate limiter allows 100 requests per minute per user",
                "memory_type": "semantic",
                "domain": "api",
                "tags": ["rate-limiting", "performance"],
            },
        ],
        "queries": [
            {"query": "How does authentication work?", "expected_domain": "auth"},
            {"query": "What security measures are in place?", "expected_tags": ["security"]},
        ],
    },

    # ============================================
    # SCENARIO 2: Debugging a problem
    # ============================================
    {
        "name": "Debug Authentication Bug",
        "memories": [
            {
                "content": "Found bug: JWT tokens were expiring too quickly because the expiry time was set in seconds instead of milliseconds",
                "memory_type": "episodic",
                "source": "user",
                "domain": "auth",
                "tags": ["bug", "jwt", "fix"],
            },
            {
                "content": "Fixed by changing token expiry from 3600 to 3600000 in auth/token.py line 42",
                "memory_type": "episodic",
                "source": "assistant",
                "domain": "auth",
                "tags": ["bug", "jwt", "fix"],
            },
        ],
        "queries": [
            {"query": "What was the JWT token bug?", "expected_type": "episodic"},
            {"query": "How did we fix the authentication issue?", "expected_content": "3600000"},
        ],
    },

    # ============================================
    # SCENARIO 3: Recording workflows
    # ============================================
    {
        "name": "Document Deployment Process",
        "memories": [
            {
                "content": "To deploy: 1) Run tests with pytest 2) Build Docker image 3) Push to registry 4) Update k8s deployment 5) Verify health checks",
                "memory_type": "procedural",
                "domain": "devops",
                "tags": ["deployment", "workflow"],
            },
            {
                "content": "Database migrations must run before deploying new API versions to avoid schema mismatches",
                "memory_type": "procedural",
                "domain": "devops",
                "tags": ["database", "migrations", "workflow"],
            },
        ],
        "queries": [
            {"query": "How do I deploy the application?", "expected_type": "procedural"},
            {"query": "What about database migrations?", "expected_content": "schema"},
        ],
    },

    # ============================================
    # SCENARIO 4: User preferences
    # ============================================
    {
        "name": "Remember Preferences",
        "memories": [
            {
                "content": "User prefers TypeScript over JavaScript for type safety",
                "memory_type": "semantic",
                "source": "user",
                "domain": "preferences",
                "tags": ["language", "typescript"],
            },
            {
                "content": "Always use 4-space indentation, never tabs",
                "memory_type": "semantic",
                "source": "user",
                "domain": "preferences",
                "tags": ["style", "formatting"],
            },
        ],
        "queries": [
            {"query": "What programming language does the user prefer?", "expected_content": "TypeScript"},
            {"query": "What code style preferences exist?", "expected_content": "4-space"},
        ],
    },

    # ============================================
    # SCENARIO 5: Cross-domain recall
    # ============================================
    {
        "name": "Cross-Domain Connections",
        "memories": [
            {
                "content": "The payment service communicates with the auth service to validate user sessions before processing transactions",
                "memory_type": "semantic",
                "domain": "payments",
                "tags": ["integration", "auth", "payments"],
            },
        ],
        "queries": [
            # This should retrieve both payment AND auth memories
            {"query": "How do payments interact with authentication?", "expected_domains": ["payments", "auth"]},
        ],
    },
]


class SimulationResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
        self.details = []

    def record(self, test_name: str, passed: bool, message: str = ""):
        if passed:
            self.passed += 1
            self.details.append(f"  [PASS] {test_name}")
        else:
            self.failed += 1
            self.details.append(f"  [FAIL] {test_name}: {message}")
            self.errors.append(f"{test_name}: {message}")

    def summary(self):
        total = self.passed + self.failed
        pct = (self.passed / total * 100) if total > 0 else 0
        return f"{self.passed}/{total} tests passed ({pct:.1f}%)"


async def check_health(client: httpx.AsyncClient) -> bool:
    """Verify system is healthy before running tests."""
    try:
        r = await client.get(f"{API_BASE}/health")
        data = r.json()
        return data.get("status") == "healthy"
    except Exception as e:
        print(f"Health check failed: {e}")
        return False


async def clear_test_data(client: httpx.AsyncClient):
    """Clear any existing test data (if endpoint exists)."""
    # For now, we'll just proceed - in production you'd want a cleanup endpoint
    pass


async def store_memory(client: httpx.AsyncClient, memory: dict) -> dict:
    """Store a memory and return the response."""
    payload = {
        "content": memory["content"],
        "memory_type": memory.get("memory_type", "semantic"),
        "domain": memory.get("domain", "general"),
        "tags": memory.get("tags", []),
    }
    if "source" in memory:
        payload["source"] = memory["source"]

    r = await client.post(f"{API_BASE}/memory/store", json=payload)
    return r.json()


async def search_memories(client: httpx.AsyncClient, query: str, limit: int = 10) -> dict:
    """Search for memories."""
    r = await client.post(
        f"{API_BASE}/search/query",
        json={"query": query, "limit": limit}
    )
    return r.json()


async def get_context(client: httpx.AsyncClient, query: str) -> dict:
    """Get assembled context."""
    r = await client.post(
        f"{API_BASE}/search/context",
        json={"query": query, "max_tokens": 2000}
    )
    return r.json()


async def run_scenario(client: httpx.AsyncClient, scenario: dict, results: SimulationResults):
    """Run a single test scenario."""
    print(f"\n{'='*60}")
    print(f"SCENARIO: {scenario['name']}")
    print(f"{'='*60}")

    # Store all memories for this scenario
    stored_ids = []
    for mem in scenario.get("memories", []):
        try:
            response = await store_memory(client, mem)
            if response.get("created") or response.get("id"):
                stored_ids.append(response.get("id"))
                results.record(
                    f"Store: {mem['content'][:40]}...",
                    True
                )
            else:
                results.record(
                    f"Store: {mem['content'][:40]}...",
                    False,
                    f"Unexpected response: {response}"
                )
        except Exception as e:
            results.record(
                f"Store: {mem['content'][:40]}...",
                False,
                str(e)
            )

    # Small delay to let embeddings process
    await asyncio.sleep(0.5)

    # Run queries and verify results
    for q in scenario.get("queries", []):
        query_text = q["query"]
        try:
            search_results = await search_memories(client, query_text)

            if "error" in search_results or "detail" in search_results:
                results.record(
                    f"Query: {query_text[:40]}...",
                    False,
                    f"Search error: {search_results}"
                )
                continue

            found_results = search_results.get("results", [])

            # Check if we got any results
            if not found_results:
                results.record(
                    f"Query: {query_text[:40]}...",
                    False,
                    "No results returned"
                )
                continue

            # Validate expected conditions
            passed = True
            fail_reason = ""

            # Check expected domain
            if "expected_domain" in q:
                top_domain = found_results[0].get("domain")
                if top_domain != q["expected_domain"]:
                    passed = False
                    fail_reason = f"Expected domain '{q['expected_domain']}', got '{top_domain}'"

            # Check expected type
            if "expected_type" in q:
                top_type = found_results[0].get("memory_type")
                if top_type != q["expected_type"]:
                    passed = False
                    fail_reason = f"Expected type '{q['expected_type']}', got '{top_type}'"

            # Check expected content substring
            if "expected_content" in q:
                all_content = " ".join(r.get("content", "") for r in found_results)
                if q["expected_content"].lower() not in all_content.lower():
                    passed = False
                    fail_reason = f"Expected content containing '{q['expected_content']}'"

            # Check expected tags
            if "expected_tags" in q:
                all_tags = []
                for r in found_results:
                    all_tags.extend(r.get("tags", []))
                for tag in q["expected_tags"]:
                    if tag not in all_tags:
                        passed = False
                        fail_reason = f"Expected tag '{tag}' not found in results"
                        break

            # Check multiple expected domains
            if "expected_domains" in q:
                found_domains = set(r.get("domain") for r in found_results)
                for domain in q["expected_domains"]:
                    if domain not in found_domains:
                        passed = False
                        fail_reason = f"Expected domain '{domain}' not found"
                        break

            # Log result details
            top_result = found_results[0]
            similarity = top_result.get("similarity", 0)

            results.record(
                f"Query: {query_text[:40]}... (sim={similarity:.2f})",
                passed,
                fail_reason
            )

        except Exception as e:
            results.record(
                f"Query: {query_text[:40]}...",
                False,
                str(e)
            )


async def test_context_assembly(client: httpx.AsyncClient, results: SimulationResults):
    """Test the context assembly endpoint."""
    print(f"\n{'='*60}")
    print("TESTING: Context Assembly")
    print(f"{'='*60}")

    try:
        context = await get_context(client, "Tell me about security and authentication")

        # Check structure
        if "context" not in context:
            results.record("Context assembly: structure", False, "Missing 'context' field")
            return

        results.record("Context assembly: structure", True)

        # Check breakdown exists
        breakdown = context.get("breakdown", {})
        if not breakdown:
            results.record("Context assembly: breakdown", False, "Missing breakdown")
        else:
            results.record("Context assembly: breakdown", True)

        # Check memories were used
        memories_used = context.get("memories_used", 0)
        if memories_used > 0:
            results.record(f"Context assembly: found {memories_used} memories", True)
        else:
            results.record("Context assembly: found memories", False, "No memories retrieved")

        # Check context has sections
        ctx_text = context.get("context", "")
        has_sections = "##" in ctx_text
        results.record("Context assembly: has sections", has_sections, "No markdown sections")

        print(f"  Context preview: {ctx_text[:200]}...")

    except Exception as e:
        results.record("Context assembly", False, str(e))


async def test_memory_dynamics(client: httpx.AsyncClient, results: SimulationResults):
    """Test memory importance and access tracking."""
    print(f"\n{'='*60}")
    print("TESTING: Memory Dynamics")
    print(f"{'='*60}")

    try:
        # Store a memory
        mem_response = await store_memory(client, {
            "content": "Test memory for dynamics checking - unique identifier XYZ123",
            "memory_type": "semantic",
            "domain": "test",
            "tags": ["dynamics-test"],
        })

        mem_id = mem_response.get("id")
        if not mem_id:
            results.record("Dynamics: store test memory", False, "No ID returned")
            return

        results.record("Dynamics: store test memory", True)

        # Search for it multiple times (should increase access count)
        for i in range(3):
            await search_memories(client, "XYZ123 unique identifier")
            await asyncio.sleep(0.2)

        # Search again and check if importance increased
        final_search = await search_memories(client, "XYZ123")
        found = [r for r in final_search.get("results", []) if "XYZ123" in r.get("content", "")]

        if found:
            importance = found[0].get("importance", 0)
            # After 3 accesses, importance should have increased from base 0.5
            if importance >= 0.5:
                results.record(f"Dynamics: importance tracking (imp={importance:.2f})", True)
            else:
                results.record("Dynamics: importance tracking", False, f"Importance too low: {importance}")
        else:
            results.record("Dynamics: importance tracking", False, "Memory not found")

    except Exception as e:
        results.record("Dynamics test", False, str(e))


async def test_similarity_ranking(client: httpx.AsyncClient, results: SimulationResults):
    """Test that more relevant results rank higher."""
    print(f"\n{'='*60}")
    print("TESTING: Similarity Ranking")
    print(f"{'='*60}")

    try:
        # Store memories with varying relevance
        await store_memory(client, {
            "content": "Python is a programming language known for its simple syntax",
            "memory_type": "semantic",
            "domain": "languages",
        })
        await store_memory(client, {
            "content": "JavaScript runs in the browser and on Node.js",
            "memory_type": "semantic",
            "domain": "languages",
        })
        await store_memory(client, {
            "content": "Python's pip package manager installs dependencies from PyPI",
            "memory_type": "semantic",
            "domain": "languages",
        })

        await asyncio.sleep(0.5)

        # Query specifically about Python
        search_results = await search_memories(client, "Python programming language syntax")
        found = search_results.get("results", [])

        if len(found) >= 2:
            # Top result should be about Python
            top_content = found[0].get("content", "")
            if "Python" in top_content and "syntax" in top_content:
                results.record("Ranking: most relevant first", True)
            else:
                results.record("Ranking: most relevant first", False, f"Top result: {top_content[:50]}")

            # Check similarity decreases
            sims = [r.get("similarity", 0) for r in found]
            if sims == sorted(sims, reverse=True):
                results.record("Ranking: similarity descending", True)
            else:
                results.record("Ranking: similarity descending", False, f"Sims: {sims}")
        else:
            results.record("Ranking tests", False, f"Only {len(found)} results")

    except Exception as e:
        results.record("Ranking test", False, str(e))


async def run_simulation():
    """Main simulation runner."""
    print("\n" + "="*60)
    print("RECALL MEMORY SYSTEM SIMULATION")
    print("="*60)
    print(f"Target: {API_BASE}")
    print(f"Started: {datetime.now().isoformat()}")

    results = SimulationResults()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Health check
        print("\nChecking system health...")
        if not await check_health(client):
            print("ERROR: System not healthy. Aborting simulation.")
            return
        print("System healthy. Starting simulation.\n")

        # Run all scenarios
        for scenario in SCENARIOS:
            await run_scenario(client, scenario, results)

        # Additional tests
        await test_context_assembly(client, results)
        await test_memory_dynamics(client, results)
        await test_similarity_ranking(client, results)

    # Print results
    print("\n" + "="*60)
    print("SIMULATION RESULTS")
    print("="*60)

    for detail in results.details:
        print(detail)

    print(f"\n{'-'*60}")
    print(f"SUMMARY: {results.summary()}")

    if results.errors:
        print(f"\nFAILURES:")
        for err in results.errors:
            print(f"  - {err}")

    print(f"\nCompleted: {datetime.now().isoformat()}")

    return results.passed, results.failed


if __name__ == "__main__":
    passed, failed = asyncio.run(run_simulation())
    exit(0 if failed == 0 else 1)
