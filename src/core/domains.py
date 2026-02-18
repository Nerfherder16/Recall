"""
Canonical domain list and normalization.

All memories should use one of CANONICAL_DOMAINS.
Freeform domain strings are normalized via multi-level matching:
  1. Exact match on canonical names
  2. Exact match on alias dict
  3. Segment match — split on / and try each segment
  4. Word match — split into words and match against keyword signals
  5. Fall back to "general"
"""

import re

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

# Map freeform domain names to canonical domains (exact match after lowering)
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
    "containerization": "infrastructure",
    "server": "infrastructure",
    # database
    "neo4j": "database",
    "qdrant": "database",
    "postgres": "database",
    "postgresql": "database",
    "sql": "database",
    "sqlite": "database",
    "mongodb": "database",
    "db": "database",
    "database schema": "database",
    "schema": "database",
    # frontend
    "react": "frontend",
    "dashboard": "frontend",
    "tailwind": "frontend",
    "css": "frontend",
    "ui": "frontend",
    "ux": "frontend",
    "ui/ux": "frontend",
    "vite": "frontend",
    "daisyui": "frontend",
    "html": "frontend",
    "component": "frontend",
    "components": "frontend",
    "interaction": "frontend",
    # development
    "python": "development",
    "typescript": "development",
    "javascript": "development",
    "node": "development",
    "nodejs": "development",
    "node.js": "development",
    "coding": "development",
    "programming": "development",
    "backend": "development",
    "code": "development",
    "refactoring": "development",
    "architecture": "development",
    "dependencies": "development",
    "recall": "development",
    "memory system": "development",
    # api
    "fastapi": "api",
    "rest": "api",
    "endpoints": "api",
    "http": "api",
    "api": "api",
    # ai-ml
    "ollama": "ai-ml",
    "llm": "ai-ml",
    "embeddings": "ai-ml",
    "embedding": "ai-ml",
    "ai": "ai-ml",
    "ml": "ai-ml",
    "machine learning": "ai-ml",
    "artificial intelligence": "ai-ml",
    "qwen": "ai-ml",
    "qwen3": "ai-ml",
    "neural": "ai-ml",
    "nlp": "ai-ml",
    "model": "ai-ml",
    # tooling
    "npm": "tooling",
    "bun": "tooling",
    "pip": "tooling",
    "ruff": "tooling",
    "mypy": "tooling",
    "tools": "tooling",
    # devops
    "git": "devops",
    "ci-cd": "devops",
    "ci/cd": "devops",
    "deployment": "devops",
    "deploy": "devops",
    "ssh": "devops",
    "scp": "devops",
    "version control": "devops",
    "build system": "devops",
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
    # testing
    "pytest": "testing",
    "vitest": "testing",
    "jest": "testing",
    "tests": "testing",
    "test": "testing",
    "verification": "testing",
    # configuration
    "config": "configuration",
    "settings": "configuration",
    "env": "configuration",
    "environment": "configuration",
    # documentation
    "docs": "documentation",
    "readme": "documentation",
    # sessions
    "session": "sessions",
    "session-summary": "sessions",
}

_CANONICAL_SET = set(CANONICAL_DOMAINS)

# Priority: lower = wins ties when multiple words match different domains
_DOMAIN_PRIORITY: dict[str, int] = {
    "api": 1,
    "database": 1,
    "security": 1,
    "ai-ml": 1,
    "testing": 2,
    "infrastructure": 2,
    "frontend": 2,
    "networking": 2,
    "devops": 3,
    "tooling": 3,
    "configuration": 3,
    "documentation": 4,
    "sessions": 4,
    "development": 5,  # Most generic — loses to everything
    "general": 99,
}

_SPLIT_RE = re.compile(r"[/\-_,&]+|\s+")


def normalize_domain(raw: str) -> str:
    """Normalize a freeform domain string to a canonical domain.

    Multi-level matching:
      1. Exact match on canonical set
      2. Exact match on alias dict
      3. Split on /, -, _, spaces — try each segment as alias
      4. Try individual words as alias keys
      5. Fall back to "general"

    When multiple segments match different domains, the highest-priority
    (most specific) domain wins.
    """
    cleaned = raw.strip().lower()
    if not cleaned:
        return "general"

    # 1. Already canonical
    if cleaned in _CANONICAL_SET:
        return cleaned

    # 2. Exact alias match
    if cleaned in DOMAIN_ALIASES:
        return DOMAIN_ALIASES[cleaned]

    # 3. Segment matching — split on / - _ spaces, try each segment
    segments = [s.strip() for s in _SPLIT_RE.split(cleaned) if s.strip()]
    candidates: list[str] = []

    for seg in segments:
        if seg in _CANONICAL_SET:
            candidates.append(seg)
        elif seg in DOMAIN_ALIASES:
            candidates.append(DOMAIN_ALIASES[seg])

    if candidates:
        return min(candidates, key=lambda d: _DOMAIN_PRIORITY.get(d, 50))

    return "general"
