"""
Tests for /health and /stats endpoints.
"""

from tests.integration.conftest import API_BASE


class TestHealth:
    """Health check endpoint tests."""

    async def test_health_returns_healthy(self, api_client):
        r = await api_client.get(f"{API_BASE}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] in ("healthy", "degraded")
        assert "timestamp" in data

    async def test_health_includes_service_checks(self, api_client):
        r = await api_client.get(f"{API_BASE}/health")
        data = r.json()
        checks = data["checks"]
        assert "api" in checks
        assert "qdrant" in checks
        assert "neo4j" in checks
        assert "redis" in checks
        # Each check should start with "ok" when healthy
        for service, status in checks.items():
            assert "ok" in str(status), f"{service} check not ok: {status}"

    async def test_stats_returns_counts(self, api_client):
        r = await api_client.get(f"{API_BASE}/stats")
        assert r.status_code == 200
        data = r.json()

        assert "memories" in data
        assert "total" in data["memories"]
        assert "graph_nodes" in data["memories"]
        assert "relationships" in data["memories"]
        assert isinstance(data["memories"]["total"], int)

        assert "sessions" in data
        assert "active" in data["sessions"]

        assert "timestamp" in data
