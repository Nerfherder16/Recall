"""
Ground-truth memories for IR metrics evaluation.

Each entry has:
- content: The memory text to store
- memory_type: semantic | episodic | procedural
- importance: float 0-1
- positive_queries: queries that SHOULD match this memory
- negative_queries: queries that should NOT match this memory
"""

GROUND_TRUTH_MEMORIES = [
    {
        "content": "Python uses 4-space indentation as its standard coding style per PEP 8. Tabs should not be mixed with spaces.",
        "memory_type": "semantic",
        "importance": 0.7,
        "positive_queries": [
            "What is the Python indentation standard?",
            "PEP 8 formatting rules",
        ],
        "negative_queries": [
            "How to configure Docker networking",
            "Kubernetes pod scheduling",
        ],
    },
    {
        "content": "Docker containers communicate on the same network via service names as hostnames. Use docker-compose networks for isolation between stacks.",
        "memory_type": "semantic",
        "importance": 0.7,
        "positive_queries": [
            "How do Docker containers talk to each other?",
            "Docker networking between services",
        ],
        "negative_queries": [
            "Python indentation style",
            "React component lifecycle",
        ],
    },
    {
        "content": "Kubernetes uses etcd as its backing store for all cluster data. The control plane components include kube-apiserver, kube-scheduler, and kube-controller-manager.",
        "memory_type": "semantic",
        "importance": 0.8,
        "positive_queries": [
            "What database does Kubernetes use internally?",
            "Kubernetes control plane components",
        ],
        "negative_queries": [
            "PostgreSQL table partitioning",
            "Git branching strategies",
        ],
    },
    {
        "content": "TCP uses a three-way handshake: SYN, SYN-ACK, ACK. This establishes a reliable connection before data transfer begins.",
        "memory_type": "semantic",
        "importance": 0.6,
        "positive_queries": [
            "How does TCP establish a connection?",
            "TCP three-way handshake",
        ],
        "negative_queries": [
            "Docker volume mounting",
            "Python async await patterns",
        ],
    },
    {
        "content": "The homelab Proxmox server uses an RTX 3090 with GPU passthrough to the Ollama VM for LLM inference.",
        "memory_type": "episodic",
        "importance": 0.8,
        "positive_queries": [
            "What GPU is in the homelab?",
            "Ollama server GPU setup",
        ],
        "negative_queries": [
            "React state management",
            "SQL join optimization",
        ],
    },
    {
        "content": "SQL injection can be prevented by using parameterized queries or prepared statements. Never concatenate user input directly into SQL strings.",
        "memory_type": "semantic",
        "importance": 0.9,
        "positive_queries": [
            "How to prevent SQL injection?",
            "Database security best practices",
        ],
        "negative_queries": [
            "Docker compose file format",
            "Git rebase vs merge",
        ],
    },
    {
        "content": "PostgreSQL VACUUM reclaims storage occupied by dead tuples. VACUUM FULL rewrites the entire table but requires an exclusive lock.",
        "memory_type": "semantic",
        "importance": 0.6,
        "positive_queries": [
            "PostgreSQL maintenance commands",
            "How does VACUUM work in Postgres?",
        ],
        "negative_queries": [
            "Kubernetes ingress controller",
            "Python decorator patterns",
        ],
    },
    {
        "content": "Git rebase replays commits on top of another branch, creating a linear history. Interactive rebase allows squashing, reordering, and editing commits.",
        "memory_type": "semantic",
        "importance": 0.6,
        "positive_queries": [
            "How does git rebase work?",
            "Git interactive rebase",
        ],
        "negative_queries": [
            "Docker container resource limits",
            "TCP congestion control",
        ],
    },
    {
        "content": "pytest fixtures use dependency injection: a test function declares fixtures as parameters, and pytest automatically provides them. Fixtures can have session, module, class, or function scope.",
        "memory_type": "semantic",
        "importance": 0.7,
        "positive_queries": [
            "How do pytest fixtures work?",
            "pytest dependency injection",
        ],
        "negative_queries": [
            "Kubernetes service mesh",
            "Docker image layers",
        ],
    },
    {
        "content": "React useEffect runs after render and can return a cleanup function. Dependencies array controls when it re-runs: empty array means mount-only, no array means every render.",
        "memory_type": "semantic",
        "importance": 0.7,
        "positive_queries": [
            "React useEffect behavior",
            "How does useEffect cleanup work?",
        ],
        "negative_queries": [
            "PostgreSQL indexing strategies",
            "TCP vs UDP comparison",
        ],
    },
    {
        "content": "Fixed a bug where FastAPI background tasks were saturating the Ollama GPU. Solution: asyncio.Semaphore(1) with a 2-second delay before acquiring.",
        "memory_type": "episodic",
        "importance": 0.8,
        "positive_queries": [
            "Ollama GPU saturation bug",
            "FastAPI background task throttling",
        ],
        "negative_queries": [
            "React component rendering",
            "Git merge conflicts",
        ],
    },
    {
        "content": "Redis LPUSH adds elements to the head of a list, RPUSH to the tail. LRANGE retrieves a range. Watch out for ordering: LPUSH reverses the order of multiple values.",
        "memory_type": "semantic",
        "importance": 0.5,
        "positive_queries": [
            "Redis list operations",
            "LPUSH vs RPUSH ordering",
        ],
        "negative_queries": [
            "Kubernetes deployment strategies",
            "Python type annotations",
        ],
    },
    {
        "content": "OPNsense WireGuard VPN: newer versions use 'Instances' and 'Peers' tabs instead of the old 'Local' and 'Endpoints' terminology.",
        "memory_type": "episodic",
        "importance": 0.6,
        "positive_queries": [
            "OPNsense WireGuard configuration",
            "VPN setup on OPNsense",
        ],
        "negative_queries": [
            "Python list comprehensions",
            "Docker Compose volumes",
        ],
    },
    {
        "content": "CORS (Cross-Origin Resource Sharing) uses preflight OPTIONS requests to check if a cross-origin request is allowed. Configure allowed origins, methods, and headers on the server.",
        "memory_type": "semantic",
        "importance": 0.7,
        "positive_queries": [
            "How does CORS work?",
            "CORS preflight requests",
        ],
        "negative_queries": [
            "Redis pub/sub channels",
            "Git stash operations",
        ],
    },
    {
        "content": "Neo4j Cypher uses MATCH patterns to find graph data. Parameters should use $param syntax, never f-string interpolation, to prevent injection.",
        "memory_type": "semantic",
        "importance": 0.7,
        "positive_queries": [
            "Neo4j Cypher query syntax",
            "Graph database query language",
        ],
        "negative_queries": [
            "Docker health checks",
            "React hooks rules",
        ],
    },
    {
        "content": "asyncio.gather runs coroutines concurrently and returns results in order. Use return_exceptions=True to prevent one failure from canceling the rest.",
        "memory_type": "semantic",
        "importance": 0.6,
        "positive_queries": [
            "Python asyncio concurrent execution",
            "asyncio.gather behavior",
        ],
        "negative_queries": [
            "Kubernetes namespace isolation",
            "PostgreSQL connection pooling",
        ],
    },
    {
        "content": "Qdrant vector search uses HNSW index by default. FieldCondition.range accepts Union[Range, DatetimeRange] — do not use datetime_range parameter.",
        "memory_type": "semantic",
        "importance": 0.7,
        "positive_queries": [
            "Qdrant vector search configuration",
            "Qdrant date range filtering",
        ],
        "negative_queries": [
            "Git cherry-pick workflow",
            "React context API",
        ],
    },
    {
        "content": "JWT tokens should have short expiry times (15 minutes for access tokens). Refresh tokens can be longer-lived but must be stored securely and revocable.",
        "memory_type": "semantic",
        "importance": 0.8,
        "positive_queries": [
            "JWT token best practices",
            "Authentication token expiry strategy",
        ],
        "negative_queries": [
            "Docker container orchestration",
            "Python metaclasses",
        ],
    },
    {
        "content": "Prometheus uses a pull-based model: it scrapes metrics endpoints at configured intervals. Metrics types: counter, gauge, histogram, summary.",
        "memory_type": "semantic",
        "importance": 0.6,
        "positive_queries": [
            "How does Prometheus collect metrics?",
            "Prometheus metric types",
        ],
        "negative_queries": [
            "Python generator functions",
            "Git submodule management",
        ],
    },
    {
        "content": "The Recall memory system uses a 3-layer search: browse returns 120-char summaries, query returns full content with scores, and timeline returns chronological entries.",
        "memory_type": "procedural",
        "importance": 0.8,
        "positive_queries": [
            "How does Recall search work?",
            "Recall 3-layer search architecture",
        ],
        "negative_queries": [
            "Docker image optimization",
            "TCP window scaling",
        ],
    },
]
