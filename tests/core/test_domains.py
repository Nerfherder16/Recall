"""
v2.3 Unit Tests — Domain normalization.

Pure unit tests that don't need the API.
"""


def test_normalize_domain_alias():
    """Known aliases resolve to canonical domains."""
    from src.core.domains import normalize_domain

    assert normalize_domain("redis") == "infrastructure"
    assert normalize_domain("docker") == "infrastructure"
    assert normalize_domain("casaos") == "infrastructure"
    assert normalize_domain("neo4j") == "database"
    assert normalize_domain("qdrant") == "database"
    assert normalize_domain("postgres") == "database"
    assert normalize_domain("react") == "frontend"
    assert normalize_domain("fastapi") == "api"
    assert normalize_domain("ollama") == "ai-ml"
    assert normalize_domain("npm") == "tooling"
    assert normalize_domain("pytest") == "testing"
    assert normalize_domain("git") == "devops"
    assert normalize_domain("nginx") == "networking"
    assert normalize_domain("ssl") == "security"
    assert normalize_domain("auth") == "security"


def test_normalize_domain_canonical_passthrough():
    """Canonical domain names pass through unchanged."""
    from src.core.domains import normalize_domain

    assert normalize_domain("general") == "general"
    assert normalize_domain("infrastructure") == "infrastructure"
    assert normalize_domain("development") == "development"
    assert normalize_domain("frontend") == "frontend"
    assert normalize_domain("database") == "database"
    assert normalize_domain("sessions") == "sessions"


def test_normalize_domain_unknown_falls_back():
    """Unknown domain strings fall back to 'general'."""
    from src.core.domains import normalize_domain

    assert normalize_domain("xylophone") == "general"
    assert normalize_domain("random-stuff") == "general"
    assert normalize_domain("") == "general"


def test_normalize_domain_case_insensitive():
    """Domain normalization is case-insensitive."""
    from src.core.domains import normalize_domain

    assert normalize_domain("Redis") == "infrastructure"
    assert normalize_domain("DOCKER") == "infrastructure"
    assert normalize_domain("FastAPI") == "api"
    assert normalize_domain("General") == "general"


def test_normalize_domain_whitespace():
    """Domain normalization strips whitespace."""
    from src.core.domains import normalize_domain

    assert normalize_domain("  redis  ") == "infrastructure"
    assert normalize_domain(" general ") == "general"


def test_canonical_domains_list():
    """CANONICAL_DOMAINS contains all expected domains."""
    from src.core.domains import CANONICAL_DOMAINS

    expected = {
        "general", "infrastructure", "development", "testing",
        "security", "api", "database", "frontend", "devops",
        "networking", "ai-ml", "tooling", "configuration",
        "documentation", "sessions",
    }
    assert set(CANONICAL_DOMAINS) == expected
