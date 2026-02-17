"""
Phase 15B integration tests — Health dashboard & force profile.

Tests the health dashboard, force profile per-memory endpoint,
and conflict detection system.
"""

import asyncio
import os
import uuid

import pytest

from tests.integration.conftest import request_with_retry

API_BASE = os.environ.get("RECALL_API_URL", "http://localhost:8200")


class TestHealthDashboard:
    """Test the health dashboard endpoint."""

    async def test_dashboard_returns_all_sections(self, api_client):
        """Dashboard should return all expected sections."""
        r = await api_client.get(f"{API_BASE}/admin/health/dashboard")
        assert r.status_code == 200
        data = r.json()

        assert "generated_at" in data
        assert "feedback" in data
        assert "population" in data
        assert "graph" in data
        assert "pins" in data
        assert "importance_distribution" in data
        assert "feedback_similarity" in data

    async def test_dashboard_feedback_structure(self, api_client):
        """Feedback section should have the expected fields."""
        r = await api_client.get(f"{API_BASE}/admin/health/dashboard")
        assert r.status_code == 200
        feedback = r.json()["feedback"]

        assert "positive_rate" in feedback
        assert "total_positive" in feedback
        assert "total_negative" in feedback
        assert "daily" in feedback
        assert isinstance(feedback["daily"], list)

    async def test_dashboard_cached(self, api_client):
        """Dashboard should be cached (same generated_at within 5min)."""
        r1 = await api_client.get(f"{API_BASE}/admin/health/dashboard")
        assert r1.status_code == 200
        ts1 = r1.json()["generated_at"]

        r2 = await api_client.get(f"{API_BASE}/admin/health/dashboard")
        assert r2.status_code == 200
        ts2 = r2.json()["generated_at"]

        # Cached response should have same timestamp
        assert ts1 == ts2

    async def test_pin_ratio_computed(self, api_client):
        """Pin ratio should be computed correctly."""
        r = await api_client.get(f"{API_BASE}/admin/health/dashboard")
        assert r.status_code == 200
        pins = r.json()["pins"]

        assert "pinned" in pins
        assert "total" in pins
        assert "ratio" in pins
        assert "warning" in pins
        assert isinstance(pins["warning"], bool)
        assert pins["total"] >= 0
        assert 0.0 <= pins["ratio"] <= 1.0

    async def test_importance_distribution_has_bands(self, api_client):
        """Importance distribution should have 5 bands."""
        r = await api_client.get(f"{API_BASE}/admin/health/dashboard")
        assert r.status_code == 200
        bands = r.json()["importance_distribution"]

        assert isinstance(bands, list)
        assert len(bands) == 5
        for band in bands:
            assert "range" in band
            assert "count" in band


class TestForceProfile:
    """Test the per-memory force profile endpoint."""

    async def test_force_profile_for_existing_memory(
        self, api_client, stored_memory, cleanup
    ):
        """Force profile should return all forces for a valid memory."""
        mem = await stored_memory(
            f"Force profile test memory {uuid.uuid4().hex[:8]}"
        )
        r = await api_client.get(f"{API_BASE}/memory/{mem['id']}/forces")
        assert r.status_code == 200
        data = r.json()

        assert data["memory_id"] == mem["id"]
        assert "current_importance" in data
        assert "forces" in data
        assert "importance_timeline" in data

        forces = data["forces"]
        assert "decay_pressure" in forces
        assert "retrieval_lift" in forces
        assert "feedback_signal" in forces
        assert "co_retrieval_gravity" in forces
        assert "pin_status" in forces
        assert "durability_shield" in forces

    async def test_pinned_memory_zero_decay(
        self, api_client, stored_memory, cleanup
    ):
        """Pinned memory should have zero decay pressure and pin force 1.0."""
        mem = await stored_memory(
            f"Pinned force test {uuid.uuid4().hex[:8]}",
            importance=0.8,
        )
        await api_client.post(f"{API_BASE}/memory/{mem['id']}/pin")

        r = await api_client.get(f"{API_BASE}/memory/{mem['id']}/forces")
        assert r.status_code == 200
        forces = r.json()["forces"]

        assert forces["decay_pressure"] == 0.0
        assert forces["pin_status"] == 1.0

    async def test_force_profile_nonexistent_404(self, api_client):
        """Force profile for nonexistent memory should 404."""
        r = await api_client.get(
            f"{API_BASE}/memory/00000000-0000-0000-0000-000000000000/forces"
        )
        assert r.status_code == 404


class TestConflicts:
    """Test the conflict detection endpoint."""

    async def test_conflicts_returns_list(self, api_client):
        """Conflicts endpoint should return a list structure."""
        r = await api_client.get(f"{API_BASE}/admin/conflicts")
        assert r.status_code == 200
        data = r.json()

        assert "conflicts" in data
        assert isinstance(data["conflicts"], list)
        for conflict in data["conflicts"]:
            assert "type" in conflict
            assert "severity" in conflict
            assert "memory_id" in conflict
            assert "description" in conflict
