"""
Canonical domain list and normalization.

All memories should use one of CANONICAL_DOMAINS.
Freeform domain strings are normalized via DOMAIN_ALIASES
or fall back to "general".
"""

CANONICAL_DOMAINS: list[str] = [
    "general",
    "infrastructure",
    "development",
    "testing",
    "security",
    "api",
    "database",
    "frontend",
    "devops",
    "networking",
    "ai-ml",
    "tooling",
    "configuration",
    "documentation",
    "sessions",
]

# Map freeform domain names to canonical domains
DOMAIN_ALIASES: dict[str, str] = {
    # infrastructure
    "redis": "infrastructure",
    "docker": "infrastructure",
    "casaos": "infrastructure",
    "proxmox": "infrastructure",
    "homelab": "infrastructure",
    "linux": "infrastructure",
    "ubuntu": "infrastructure",
    "vm": "infrastructure",
    "container": "infrastructure",
    "containers": "infrastructure",
    # database
    "neo4j": "database",
    "qdrant": "database",
    "postgres": "database",
    "postgresql": "database",
    "sql": "database",
    "sqlite": "database",
    "mongodb": "database",
    "db": "database",
    # frontend
    "react": "frontend",
    "dashboard": "frontend",
    "tailwind": "frontend",
    "css": "frontend",
    "ui": "frontend",
    "ui/ux": "frontend",
    "ui/ux design": "frontend",
    "frontend ui": "frontend",
    "frontend ui/ux": "frontend",
    "frontend development": "frontend",
    "frontend/react": "frontend",
    "vite": "frontend",
    "daisyui": "frontend",
    "html": "frontend",
    # development
    "python": "development",
    "typescript": "development",
    "javascript": "development",
    "node": "development",
    "nodejs": "development",
    "node.js": "development",
    "coding": "development",
    "programming": "development",
    "software development": "development",
    "backend": "development",
    "backend development": "development",
    # api
    "fastapi": "api",
    "rest": "api",
    "rest api": "api",
    "api development": "api",
    "endpoints": "api",
    "http": "api",
    # ai-ml
    "ollama": "ai-ml",
    "llm": "ai-ml",
    "embeddings": "ai-ml",
    "ai": "ai-ml",
    "ml": "ai-ml",
    "machine learning": "ai-ml",
    "artificial intelligence": "ai-ml",
    "qwen": "ai-ml",
    "qwen3": "ai-ml",
    # tooling
    "npm": "tooling",
    "bun": "tooling",
    "pip": "tooling",
    "ruff": "tooling",
    "mypy": "tooling",
    "tools": "tooling",
    "dev tools": "tooling",
    # devops
    "git": "devops",
    "ci-cd": "devops",
    "ci/cd": "devops",
    "deployment": "devops",
    "deploy": "devops",
    "ssh": "devops",
    "scp": "devops",
    # networking
    "nginx": "networking",
    "dns": "networking",
    "vpn": "networking",
    "network": "networking",
    "cors": "networking",
    "proxy": "networking",
    # security
    "ssl": "security",
    "tls": "security",
    "auth": "security",
    "authentication": "security",
    "authorization": "security",
    "encryption": "security",
    "api keys": "security",
    # testing
    "pytest": "testing",
    "vitest": "testing",
    "jest": "testing",
    "tests": "testing",
    "test": "testing",
    "unit testing": "testing",
    "integration testing": "testing",
    # configuration
    "config": "configuration",
    "settings": "configuration",
    "env": "configuration",
    "environment": "configuration",
    # documentation
    "docs": "documentation",
    "readme": "documentation",
    "markdown": "documentation",
    # sessions
    "session": "sessions",
    "session-summary": "sessions",
    # recall-specific
    "recall": "development",
    "memory": "development",
    "memory system": "development",
}

_CANONICAL_SET = set(CANONICAL_DOMAINS)


def normalize_domain(raw: str) -> str:
    """Normalize a freeform domain string to a canonical domain.

    Checks aliases first, then falls back to "general" for unknown domains.
    Canonical domain names pass through unchanged.
    """
    cleaned = raw.strip().lower()
    if not cleaned:
        return "general"
    if cleaned in _CANONICAL_SET:
        return cleaned
    return DOMAIN_ALIASES.get(cleaned, "general")
