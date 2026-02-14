"""
Tests for error handling and validation (422 / 400 responses).
"""

import pytest

from tests.integration.conftest import API_BASE


class TestStoreValidation:
    """POST /memory/store — validation errors."""

    async def test_missing_content_field(self, api_client):
        """content is required."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={"domain": "test"},
        )
        assert r.status_code == 422

    async def test_invalid_memory_type(self, api_client):
        """Invalid enum value for memory_type."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={"content": "test", "memory_type": "nonexistent_type"},
        )
        assert r.status_code == 422

    async def test_invalid_source(self, api_client):
        """Invalid enum value for source."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={"content": "test", "source": "alien"},
        )
        assert r.status_code == 422

    async def test_importance_out_of_range_high(self, api_client):
        """importance > 1.0 should fail validation."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={"content": "test", "importance": 1.5},
        )
        assert r.status_code == 422

    async def test_importance_out_of_range_low(self, api_client):
        """importance < 0.0 should fail validation."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={"content": "test", "importance": -0.1},
        )
        assert r.status_code == 422

    async def test_confidence_out_of_range(self, api_client):
        """confidence > 1.0 should fail validation."""
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            json={"content": "test", "confidence": 2.0},
        )
        assert r.status_code == 422


class TestRelationshipValidation:
    """POST /memory/relationship — validation errors."""

    async def test_invalid_relationship_type(self, api_client):
        r = await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": "a",
                "target_id": "b",
                "relationship_type": "loves",
            },
        )
        assert r.status_code == 422

    async def test_missing_source_id(self, api_client):
        r = await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "target_id": "b",
                "relationship_type": "related_to",
            },
        )
        assert r.status_code == 422

    async def test_missing_target_id(self, api_client):
        r = await api_client.post(
            f"{API_BASE}/memory/relationship",
            json={
                "source_id": "a",
                "relationship_type": "related_to",
            },
        )
        assert r.status_code == 422


class TestSearchValidation:
    """POST /search/query — validation errors."""

    async def test_missing_query_field(self, api_client):
        """query is required."""
        r = await api_client.post(
            f"{API_BASE}/search/query",
            json={"limit": 5},
        )
        assert r.status_code == 422


class TestMalformedPayload:
    """Malformed JSON body."""

    async def test_malformed_json(self, api_client):
        r = await api_client.post(
            f"{API_BASE}/memory/store",
            content=b"this is not json",
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422
