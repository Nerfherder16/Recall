"""
Test conversations for signal detection quality evaluation.

Each conversation has:
- description: what the conversation is about
- expected_signals: list of expected signal types
- turns: list of (role, content) tuples
"""

TEST_CONVERSATIONS = [
    {
        "description": "Debugging a Docker networking issue and finding the fix",
        "expected_signals": ["error_fix"],
        "turns": [
            ("user", "The API container can't connect to the Redis container. I'm getting Connection refused on port 6379."),
            ("assistant", "Let me check the Docker network configuration. The containers need to be on the same network to communicate."),
            ("user", "They're both in the docker-compose.yml but Redis shows as 'exited' in docker ps."),
            ("assistant", "I see the issue. Redis is crashing on startup because the data volume has corrupted RDB files. Let me fix this by clearing the Redis data directory and restarting."),
            ("user", "That worked! Redis is running now and the API can connect. The connection refused error is gone."),
            ("assistant", "The fix was to clear the corrupted Redis RDB dump file at /data/dump.rdb. The container was crash-looping because it couldn't load the corrupted snapshot on startup. I've added a health check to the docker-compose.yml so we'll detect this earlier next time."),
        ],
    },
    {
        "description": "Making an architectural decision about authentication",
        "expected_signals": ["decision"],
        "turns": [
            ("user", "We need to decide on the authentication strategy for the new API. What are our options?"),
            ("assistant", "The main options are: JWT tokens with refresh rotation, session-based auth with Redis store, or API keys for service-to-service. Each has trade-offs in terms of security, complexity, and scalability."),
            ("user", "We need both user auth and service auth. What would you recommend?"),
            ("assistant", "I recommend a hybrid approach: JWT for user authentication with 15-minute expiry and refresh tokens stored in httpOnly cookies, plus API keys with the rc_ prefix for service-to-service calls. The API keys get stored in PostgreSQL with bcrypt hashing."),
            ("user", "Let's go with that. JWT for users, API keys for services. Can you outline the implementation plan?"),
            ("assistant", "Decision made: hybrid auth with JWT for users and API keys for services. Implementation plan: 1) Create auth middleware that checks Bearer token type, 2) JWT tokens via /auth/login endpoint, 3) API keys created via /admin/users endpoint, 4) Rate limiting per auth type. The middleware resolves both to a User object for downstream handlers."),
        ],
    },
    {
        "description": "Establishing a coding workflow pattern",
        "expected_signals": ["workflow"],
        "turns": [
            ("user", "How should we handle deploying changes to the production server?"),
            ("assistant", "Here's the deployment workflow I recommend for our setup:"),
            ("user", "Walk me through the steps."),
            ("assistant", "Step 1: Make changes locally and test with pytest. Step 2: SCP the changed files to the CasaOS VM. Step 3: docker compose restart api worker to pick up changes (volume-mounted). Step 4: Check docker logs for any startup errors. Step 5: Run a quick health check against the live API. This works because src/ is volume-mounted so we don't need to rebuild the image."),
            ("user", "What if we need to add a new Python dependency?"),
            ("assistant", "For new dependencies: add to pyproject.toml, then docker compose down && docker compose build api && docker compose up -d. The rebuild is needed because pip install happens during image build, not at runtime. Always test the full build locally first with docker compose build --no-cache to catch any issues."),
        ],
    },
    {
        "description": "Learning a new technical fact",
        "expected_signals": ["fact"],
        "turns": [
            ("user", "What embedding model are we using and what are its dimensions?"),
            ("assistant", "We're using bge-large from Ollama for embeddings. It produces 1024-dimensional vectors, which is why the Qdrant collection needs to be created with size=1024. The model runs on the GPU VM."),
            ("user", "How does it compare to nomic-embed-text?"),
            ("assistant", "bge-large produces 1024-dim vectors while nomic-embed-text produces 768-dim vectors. bge-large generally scores higher on retrieval benchmarks like MTEB, especially for technical content. The trade-off is slightly higher memory usage and inference time, but on the RTX 3090 the difference is negligible — about 15ms vs 12ms per embedding."),
        ],
    },
    {
        "description": "Expressing a tool preference",
        "expected_signals": ["preference"],
        "turns": [
            ("user", "I've been going back and forth between vim and VS Code for editing files on the server."),
            ("assistant", "Both are solid choices. Vim is faster for quick edits over SSH since it's always available. VS Code with Remote SSH gives you a full IDE experience. What's your preference?"),
            ("user", "I prefer VS Code with Remote SSH for longer editing sessions, but vim for quick config changes. For Claude Code sessions, I want you to always use the Edit tool rather than generating patches."),
            ("assistant", "Noted. Your preferences: VS Code Remote SSH for extended work, vim for quick server edits, and the Edit tool for Claude Code changes. I'll always use the Edit tool for file modifications in our sessions rather than outputting diff patches."),
        ],
    },
    {
        "description": "Discovering a recurring code pattern",
        "expected_signals": ["pattern"],
        "turns": [
            ("user", "I keep seeing the same bug in our Cypher queries. What's going on?"),
            ("assistant", "I've noticed a pattern: multiple Cypher queries have been using f-strings for parameter interpolation instead of Neo4j's $param syntax. This has happened in find_path, find_related, and now in the pattern extractor."),
            ("user", "So it's a recurring issue? How do we prevent it?"),
            ("assistant", "Yes, it's a recurring pattern — this is the third time we've hit f-string injection in Cypher queries. The fix is always the same: replace {variable} in the query string with $variable and pass the value via the params dict. We should add this to the code review checklist and consider a linting rule that flags f-strings containing MATCH or MERGE keywords."),
        ],
    },
    {
        "description": "Casual greeting — should produce NO signals",
        "expected_signals": [],
        "turns": [
            ("user", "Hey, how's it going?"),
            ("assistant", "Hey! I'm ready to help. What are you working on today?"),
            ("user", "Nothing specific yet, just checking in."),
            ("assistant", "No problem! I'm here whenever you need me. Let me know if anything comes up."),
        ],
    },
    {
        "description": "Quick factual Q&A with tool preference",
        "expected_signals": ["fact", "preference"],
        "turns": [
            ("user", "What port does our Recall API run on?"),
            ("assistant", "The Recall API runs on port 8200 at http://localhost:8200. The Docker container maps port 8200 on the host to 8000 inside the container where uvicorn listens."),
            ("user", "And the dashboard?"),
            ("assistant", "The dashboard is served as static files from the same API server on port 8200, mounted at /dashboard. It's a React SPA built with Vite+Tailwind+DaisyUI that builds to src/api/static/dashboard/."),
            ("user", "I always want to use the dark theme for the dashboard by default."),
            ("assistant", "I'll remember that. Your preference is dark theme as the default for the Recall dashboard. The theme is controlled by the data-theme attribute on the HTML element and persisted to localStorage."),
        ],
    },
]
