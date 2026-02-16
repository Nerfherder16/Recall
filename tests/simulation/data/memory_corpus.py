"""
Memory corpora for lifecycle, consolidation, and time-acceleration suites.
"""

# Memories at different importance levels for decay curve testing
LIFECYCLE_MEMORIES = {
    "high": [
        {"content": "Critical production database password rotation must happen every 90 days per compliance policy.", "importance": 0.8},
        {"content": "The RTX 3090 GPU requires vendor-reset workaround when hot-swapping VMs on the Proxmox host.", "importance": 0.8},
        {"content": "FastAPI background tasks that call Ollama need asyncio.Semaphore(1) to prevent GPU saturation.", "importance": 0.85},
        {"content": "OPNsense firewall rules for WireGuard interface need explicit allow rules for tunnel traffic.", "importance": 0.8},
        {"content": "Qdrant collection must be created with vector size 1024 for bge-large embeddings.", "importance": 0.8},
    ],
    "mid": [
        {"content": "Docker Compose on CasaOS should use 'docker compose' (not docker-compose hyphenated).", "importance": 0.5},
        {"content": "Python structlog produces JSON output by default, configure with ConsoleRenderer for dev.", "importance": 0.5},
        {"content": "Redis LPUSH reverses the order when pushing multiple values in one call.", "importance": 0.5},
        {"content": "Pydantic v2 uses model_validate instead of parse_obj for dict-to-model conversion.", "importance": 0.5},
        {"content": "Neo4j APOC plugin must be installed separately and enabled in neo4j.conf.", "importance": 0.5},
    ],
    "low": [
        {"content": "Tim prefers dark mode in all editors and terminal applications.", "importance": 0.3},
        {"content": "The CasaOS web UI default port is 80 but was moved to 8080 to avoid conflicts.", "importance": 0.3},
        {"content": "Cursor IDE uses .cursorrules file for AI coding assistant configuration.", "importance": 0.3},
        {"content": "The Threadripper 1950X has 16 cores and 32 threads at 3.4GHz base clock.", "importance": 0.3},
        {"content": "Jellyfin hardware transcoding works with Intel QSV but not NVIDIA on the current VM.", "importance": 0.3},
    ],
}

# Near-paraphrase memories that consolidation should merge
CONSOLIDATION_CANDIDATES = [
    "Python uses 4-space indentation according to PEP 8 coding style guidelines.",
    "PEP 8 recommends 4 spaces per indentation level in Python code.",
    "The standard Python indentation is 4 spaces as specified by PEP 8.",
    "In Python, the convention is to indent with 4 spaces following PEP 8.",
    "According to PEP 8, Python code should use 4 spaces for each indentation level.",
]

# Memories for time-acceleration suite, organized by domain
TIME_ACCEL_MEMORIES = {
    "infra": [
        {"content": "Proxmox backup schedule runs daily at 2am to local NAS via PBS.", "importance": 0.7},
        {"content": "CasaOS VM allocated 16GB RAM and 8 vCPUs for Docker workloads.", "importance": 0.6},
        {"content": "Gluetun VPN container routes all *arr stack traffic through Mullvad.", "importance": 0.7},
        {"content": "UPS provides 45 minutes of backup power for the homelab rack.", "importance": 0.5},
        {"content": "Proxmox host uses ZFS mirror for boot drives with weekly scrub.", "importance": 0.6},
        {"content": "DNS resolution goes through OPNsense Unbound with DNSSEC enabled.", "importance": 0.5},
        {"content": "Home Assistant runs at 192.168.50.20 with Zigbee2MQTT for device control.", "importance": 0.4},
        {"content": "VPS at Racknerd handles reverse proxy with Nginx + certbot for SSL.", "importance": 0.6},
        {"content": "WireGuard tunnel between OPNsense and VPS provides secure remote access.", "importance": 0.7},
        {"content": "MinIO S3-compatible storage runs on CasaOS for backup and media.", "importance": 0.4},
    ],
    "code-patterns": [
        {"content": "Use structlog for all Python logging with JSON output in production.", "importance": 0.6},
        {"content": "FastAPI route handlers should use Depends() for authentication injection.", "importance": 0.7},
        {"content": "Pydantic models with Field() validators prevent invalid API inputs.", "importance": 0.6},
        {"content": "asyncpg connections should use get_postgres_store() singleton pattern.", "importance": 0.5},
        {"content": "Background tasks in FastAPI should be fire-and-forget with error logging.", "importance": 0.5},
        {"content": "Redis keys follow recall:namespace:id pattern for organized key management.", "importance": 0.4},
        {"content": "All Cypher queries must use $param syntax, never f-string interpolation.", "importance": 0.8},
        {"content": "Embedding service calls need OllamaUnavailableError exception handling.", "importance": 0.6},
        {"content": "Content dedup uses SHA-256 hash stored in both Qdrant and as check.", "importance": 0.5},
        {"content": "Rate limiting uses slowapi with 'request: Request' as first parameter.", "importance": 0.5},
    ],
    "debug-notes": [
        {"content": "When Qdrant returns 'wrong input' error, the ID is not a valid UUID.", "importance": 0.3},
        {"content": "Neo4j connection timeout usually means the container hasn't finished starting.", "importance": 0.4},
        {"content": "Ollama returns empty JSON when think mode conflicts with format: json.", "importance": 0.7},
        {"content": "SSE stream tests hang with httpx unless using client.stream() context.", "importance": 0.5},
        {"content": "Docker logs show 'exec format error' when building ARM image on x86.", "importance": 0.3},
        {"content": "Python output buffering causes missed logs; use line_buffering=True.", "importance": 0.4},
        {"content": "JSONL export endpoint returns newline-delimited JSON, not a JSON array.", "importance": 0.4},
        {"content": "qwen3:14b needs think: false API param to produce clean JSON output.", "importance": 0.6},
        {"content": "Scroll_all() must be used for decay/consolidation instead of search.", "importance": 0.8},
        {"content": "Session current_task can be None; always use (s.get('current_task') or '').", "importance": 0.3},
    ],
}
