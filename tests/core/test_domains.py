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
    assert normalize_domain("") == "general"


def test_normalize_domain_compound_slash():
    """Compound domains with / are split and matched."""
    from src.core.domains import normalize_domain

    assert normalize_domain("Docker/Containerization") == "infrastructure"
    assert normalize_domain("Frontend/React") == "frontend"
    assert normalize_domain("Machine Learning / NLP") == "ai-ml"
    assert normalize_domain("Machine Learning / Embeddings") == "ai-ml"
    assert normalize_domain("Machine Learning / Embedding Models") == "ai-ml"
    assert normalize_domain("Infrastructure/Configuration") == "infrastructure"
    assert normalize_domain("Testing/Dependencies") == "testing"


def test_normalize_domain_compound_spaces():
    """Multi-word domains are split and matched by word."""
    from src.core.domains import normalize_domain

    assert normalize_domain("API Design") == "api"
    assert normalize_domain("API Behavior") == "api"
    assert normalize_domain("API Architecture") == "api"
    assert normalize_domain("API Endpoints") == "api"
    assert normalize_domain("API Integration") == "api"
    assert normalize_domain("Database Schema") == "database"
    assert normalize_domain("Code Quality") == "development"
    assert normalize_domain("Code Refactoring") == "development"
    assert normalize_domain("Code Architecture") == "development"
    assert normalize_domain("System Architecture") == "development"
    assert normalize_domain("Frontend State Management") == "frontend"
    assert normalize_domain("UI Component Design") == "frontend"
    assert normalize_domain("Deployment Configuration") == "devops"


def test_normalize_domain_priority():
    """When multiple words match, the more specific domain wins."""
    from src.core.domains import normalize_domain

    # "API" (priority 1) beats "Development" (priority 5)
    assert normalize_domain("API Development") == "api"
    # "Database" (priority 1) beats "Configuration" (priority 3)
    assert normalize_domain("Database Configuration") == "database"
    # "Security" (priority 1) beats "Testing" (priority 2)
    assert normalize_domain("Security Testing") == "security"


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
