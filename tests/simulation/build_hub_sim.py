#!/usr/bin/env python3
"""
Build Hub Simulation — 1-hour autonomous agent team stress test for Recall.

5 agents collaborate on designing "Build Hub", a project database + think tank
platform with LLM-assisted development and video/audio conferencing.

Agents communicate through Recall itself — storing decisions as memories,
searching for each other's work, approving signals, and exercising every endpoint.

Usage:
    python tests/simulation/build_hub_sim.py [--duration 3600] [--api http://localhost:8200]
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime

try:
    import httpx
except ImportError:
    print("ERROR: httpx required. Install with: pip install httpx")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

DEFAULT_API = os.environ.get("RECALL_API_URL", "http://localhost:8200")
DEFAULT_DURATION = 3600  # 1 hour
API_KEY = "test"
DOMAIN = "build-hub"
STATUS_INTERVAL = 120  # Status report every 2 minutes
TURN_DELAY = (15, 22)  # Seconds between conversation pairs (5 agents * 1 req/pair = 20/min max)


# ═══════════════════════════════════════════════════════════════
# STATS TRACKER
# ═══════════════════════════════════════════════════════════════


@dataclass
class Stats:
    sessions_created: int = 0
    sessions_ended: int = 0
    turns_ingested: int = 0
    memories_stored: int = 0
    memories_searched: int = 0
    memories_retrieved: int = 0
    memories_deleted: int = 0
    batch_stores: int = 0
    batch_deletes: int = 0
    signals_loaded: int = 0
    signals_approved: int = 0
    timeline_queries: int = 0
    browse_queries: int = 0
    health_checks: int = 0
    consolidation_runs: int = 0
    decay_runs: int = 0
    reconcile_runs: int = 0
    export_runs: int = 0
    ollama_info_checks: int = 0
    domain_stat_checks: int = 0
    audit_queries: int = 0
    sse_events_received: int = 0
    errors: int = 0
    error_details: list = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 56,
            "  BUILD HUB SIMULATION -- FINAL REPORT",
            "=" * 56,
            "",
            f"  Sessions created:       {self.sessions_created}",
            f"  Sessions ended:         {self.sessions_ended}",
            f"  Turns ingested:         {self.turns_ingested}",
            f"  Memories stored:        {self.memories_stored}",
            f"  Memories searched:      {self.memories_searched}",
            f"  Memories retrieved:     {self.memories_retrieved}",
            f"  Memories deleted:       {self.memories_deleted}",
            f"  Batch store ops:        {self.batch_stores}",
            f"  Batch delete ops:       {self.batch_deletes}",
            f"  Signals loaded:         {self.signals_loaded}",
            f"  Signals approved:       {self.signals_approved}",
            f"  Timeline queries:       {self.timeline_queries}",
            f"  Browse queries:         {self.browse_queries}",
            f"  Health checks:          {self.health_checks}",
            f"  Consolidation runs:     {self.consolidation_runs}",
            f"  Decay runs:             {self.decay_runs}",
            f"  Reconcile runs:         {self.reconcile_runs}",
            f"  Export runs:            {self.export_runs}",
            f"  Ollama info checks:     {self.ollama_info_checks}",
            f"  Domain stat checks:     {self.domain_stat_checks}",
            f"  Audit queries:          {self.audit_queries}",
            f"  SSE events received:    {self.sse_events_received}",
            f"  Errors:                 {self.errors}",
        ]
        if self.error_details:
            lines.append("")
            lines.append("  Last 10 errors:")
            for e in self.error_details[-10:]:
                lines.append(f"    - {e}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# API CLIENT
# ═══════════════════════════════════════════════════════════════


class RecallClient:
    def __init__(self, base_url: str, stats: Stats):
        self.base = base_url.rstrip("/")
        self.stats = stats
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        }
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0, headers=self.headers)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, method: str, path: str, body=None):
        """Make an API request. Returns parsed JSON (dict, list, or {}) on success, None on error."""
        client = await self._get_client()
        try:
            if method == "GET":
                r = await client.get(f"{self.base}{path}")
            elif method == "POST":
                r = await client.post(f"{self.base}{path}", json=body)
            elif method == "DELETE":
                r = await client.delete(f"{self.base}{path}")
            else:
                return None
            if r.status_code >= 400:
                self.stats.errors += 1
                detail = r.text[:120]
                self.stats.error_details.append(f"{method} {path} -> {r.status_code}: {detail}")
                return None
            return r.json() if r.text else {}
        except Exception as e:
            self.stats.errors += 1
            self.stats.error_details.append(f"{method} {path} -> {type(e).__name__}: {str(e)[:80]}")
            return None

    # --- Session management ---
    async def create_session(self, task: str = "") -> str | None:
        r = await self._request("POST", "/session/start", {
            "current_task": task or None,
        })
        if r and "session_id" in r:
            self.stats.sessions_created += 1
            return r["session_id"]
        return None

    async def end_session(self, sid: str):
        r = await self._request("POST", "/session/end", {
            "session_id": sid,
            "trigger_consolidation": False,  # Avoid overloading Ollama
        })
        if r is not None:
            self.stats.sessions_ended += 1

    async def ingest_turn(self, sid: str, role: str, content: str):
        r = await self._request("POST", "/ingest/turns", {
            "session_id": sid,
            "turns": [{"role": role, "content": content}],
        })
        if r is not None:
            self.stats.turns_ingested += 1

    async def ingest_turn_pair(self, sid: str, user_msg: str, asst_msg: str):
        """Ingest both user and assistant turns in one request (saves rate limit)."""
        r = await self._request("POST", "/ingest/turns", {
            "session_id": sid,
            "turns": [
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": asst_msg},
            ],
        })
        if r is not None:
            self.stats.turns_ingested += 2

    # --- Memory operations ---
    async def store_memory(self, content: str, memory_type: str = "semantic",
                           tags: list[str] | None = None,
                           importance: float = 0.5) -> str | None:
        r = await self._request("POST", "/memory/store", {
            "content": content,
            "memory_type": memory_type,
            "domain": DOMAIN,
            "tags": tags or [],
            "importance": importance,
        })
        if r and "id" in r:
            self.stats.memories_stored += 1
            return r["id"]
        return None

    async def get_memory(self, mid: str) -> dict | None:
        r = await self._request("GET", f"/memory/{mid}")
        if r:
            self.stats.memories_retrieved += 1
        return r

    async def delete_memory(self, mid: str) -> bool:
        r = await self._request("DELETE", f"/memory/{mid}")
        if r is not None:
            self.stats.memories_deleted += 1
            return True
        return False

    async def batch_store(self, items: list[dict]) -> dict | None:
        r = await self._request("POST", "/memory/batch/store", {"memories": items})
        if r:
            self.stats.batch_stores += 1
        return r

    async def batch_delete(self, ids: list[str]) -> dict | None:
        r = await self._request("POST", "/memory/batch/delete", {"ids": ids})
        if r:
            self.stats.batch_deletes += 1
        return r

    # --- Search ---
    async def search_browse(self, query: str, limit: int = 10) -> list[dict]:
        r = await self._request("POST", "/search/browse", {
            "query": query, "limit": limit, "domains": [DOMAIN],
        })
        if r:
            self.stats.browse_queries += 1
            return r.get("results", [])
        return []

    async def search_timeline(self, limit: int = 20) -> list[dict]:
        r = await self._request("POST", "/search/timeline", {
            "limit": limit, "domain": DOMAIN,
        })
        if r:
            self.stats.timeline_queries += 1
            return r.get("entries", [])
        return []

    async def search_query(self, query: str, limit: int = 5) -> list[dict]:
        r = await self._request("POST", "/search/query", {
            "query": query, "limit": limit, "domains": [DOMAIN],
        })
        if r:
            self.stats.memories_searched += 1
            return r.get("results", [])
        return []

    # --- Signals ---
    async def get_signals(self, sid: str) -> list[dict]:
        r = await self._request("GET", f"/ingest/{sid}/signals")
        if r is not None:
            self.stats.signals_loaded += 1
            # Response is a list directly (not wrapped in {signals: [...]})
            if isinstance(r, list):
                return r
            return r.get("signals", []) if isinstance(r, dict) else []
        return []

    async def approve_signal(self, sid: str, index: int = 0) -> bool:
        r = await self._request("POST", f"/ingest/{sid}/signals/approve", {
            "index": index,
        })
        if r is not None:
            self.stats.signals_approved += 1
            return True
        return False

    # --- Admin / maintenance ---
    async def health(self) -> dict | None:
        r = await self._request("GET", "/health")
        if r:
            self.stats.health_checks += 1
        return r

    async def stats_endpoint(self) -> dict | None:
        return await self._request("GET", "/stats")

    async def domain_stats(self) -> dict | None:
        r = await self._request("GET", "/stats/domains")
        if r:
            self.stats.domain_stat_checks += 1
        return r

    async def audit(self, limit: int = 20, action: str = "") -> list[dict]:
        params = f"limit={limit}"
        if action:
            params += f"&action={action}"
        r = await self._request("GET", f"/admin/audit?{params}")
        if r:
            self.stats.audit_queries += 1
            return r.get("entries", [])
        return []

    async def sessions_list(self) -> list[dict]:
        r = await self._request("GET", "/admin/sessions")
        if r:
            return r.get("sessions", [])
        return []

    async def ollama_info(self) -> dict | None:
        r = await self._request("GET", "/admin/ollama")
        if r:
            self.stats.ollama_info_checks += 1
        return r

    async def run_consolidation(self, dry_run: bool = False) -> dict | None:
        r = await self._request("POST", "/admin/consolidate", {
            "domain": DOMAIN, "dry_run": dry_run,
        })
        if r is not None:
            self.stats.consolidation_runs += 1
        return r

    async def run_decay(self) -> dict | None:
        r = await self._request("POST", "/admin/decay", {})
        if r is not None:
            self.stats.decay_runs += 1
        return r

    async def run_reconcile(self) -> dict | None:
        r = await self._request("POST", "/admin/reconcile?repair=false")
        if r is not None:
            self.stats.reconcile_runs += 1
        return r

    async def run_export(self) -> dict | None:
        """Export returns JSONL (newline-delimited), so parse first line only."""
        client = await self._get_client()
        try:
            r = await client.get(f"{self.base}/admin/export")
            if r.status_code >= 400:
                self.stats.errors += 1
                self.stats.error_details.append(f"GET /admin/export -> {r.status_code}: {r.text[:80]}")
                return None
            lines = [l for l in r.text.strip().split("\n") if l.strip()]
            self.stats.export_runs += 1
            return {"count": len(lines)}
        except Exception as e:
            self.stats.errors += 1
            self.stats.error_details.append(f"GET /admin/export -> {type(e).__name__}: {str(e)[:80]}")
            return None


# ═══════════════════════════════════════════════════════════════
# CONVERSATION CONTENT — BUILD HUB PROJECT
# ═══════════════════════════════════════════════════════════════
# Rich, realistic technical discussions organized by phase and topic.
# Each entry is (user_message, assistant_message) simulating a dev conversation.

PHASE_1_IDEATION = {
    "alex": [
        (
            "Let's define the core vision for Build Hub. What problem are we solving?",
            "Build Hub is a collaborative platform where development teams can ideate, architect, and scaffold applications together in real-time. The core problem: devs waste hours context-switching between Slack, Figma, GitHub, and docs. Build Hub unifies the entire pre-coding workflow — from brainstorming to deployment-ready architecture — into a single workspace with AI assistance at every step."
        ),
        (
            "What are the main modules we need?",
            "I see six core modules: (1) Project Canvas — a shared whiteboard for architecture diagrams and system design, (2) Idea Vault — searchable database of project concepts with AI-generated feasibility scores, (3) Code Scaffold — LLM-powered code generation from architecture specs, (4) Video Rooms — Zoom-like conferencing with integrated screen sharing and whiteboard overlay, (5) Knowledge Graph — auto-linked documentation that maps relationships between decisions, components, and team members, (6) Deploy Pipeline — one-click infrastructure provisioning from architecture diagrams."
        ),
        (
            "How should we handle the real-time collaboration aspect?",
            "We need a CRDT-based document model for conflict-free real-time editing on the canvas. I'm thinking Yjs or Automerge for the shared state. The video rooms use WebRTC with an SFU (Selective Forwarding Unit) architecture — probably mediasoup or Janus — so we can handle 20+ participants without killing bandwidth. Each room gets a shared canvas layer that overlays on the video grid, rendered via HTML5 Canvas or WebGL for performance."
        ),
        (
            "What about the AI integration strategy?",
            "Three-tier AI: (1) Local LLM (Ollama/llama.cpp) for real-time suggestions and autocomplete — low latency, runs on the user's machine or our servers. (2) Cloud API (Claude/GPT) for complex architecture reviews, code generation, and feasibility analysis — higher latency but much more capable. (3) Specialized models for specific tasks: code analysis (CodeLlama), diagram generation (stable diffusion for wireframes), and voice transcription (Whisper) for meeting notes. The user should be able to configure which tier handles what based on their needs and budget."
        ),
        (
            "What's the tech stack recommendation?",
            "Frontend: React 19 with TypeScript, TanStack Query for data fetching, Zustand for client state, TailwindCSS + shadcn/ui for styling. Backend: Python FastAPI for the main API, Go for the WebRTC signaling server (performance-critical), Redis for pub/sub and ephemeral state, PostgreSQL for persistent data with pgvector for semantic search. Infrastructure: Docker Compose for dev, Kubernetes for prod, S3-compatible storage (MinIO self-hosted) for assets. The canvas uses tldraw as the base drawing engine."
        ),
    ],
    "sam": [
        (
            "Let me think through the database schema for the project system.",
            "Core entities: Project (id, name, description, team_id, created_at, status, ai_feasibility_score), Team (id, name, plan_tier), TeamMember (user_id, team_id, role), Architecture (id, project_id, version, canvas_state_json, generated_code_refs), Decision (id, project_id, title, rationale, decided_by, linked_components), Component (id, project_id, name, type, description, dependencies_json, estimated_complexity). We need a graph structure for the knowledge base — Neo4j or just PostgreSQL with recursive CTEs for the dependency trees."
        ),
        (
            "How should we handle the API design for the project CRUD?",
            "RESTful for CRUD, WebSocket for real-time updates. Endpoints: POST /api/projects (create), GET /api/projects/:id (read with optional ?include=architecture,decisions,components), PATCH /api/projects/:id (update), DELETE /api/projects/:id (soft delete). Batch ops: POST /api/projects/batch for bulk status updates. The architecture canvas gets its own WebSocket channel: ws://api/projects/:id/canvas — all CRDT operations flow through there. We'll use event sourcing for the canvas so we get full undo history for free."
        ),
        (
            "What about the video conferencing backend?",
            "The signaling server needs to be separate from the main API — Go with gorilla/websocket for the WebSocket signaling, mediasoup-go or Pion for the SFU. Architecture: client sends offer/answer/ICE through the signaling server, media flows through the SFU. Recording: each room optionally records to a composite MP4 via FFmpeg, stored in S3. Transcription: audio stream → Whisper → real-time captions + post-meeting searchable transcript. The SFU should auto-scale: 1-4 users use peer-to-peer mesh, 5+ switch to SFU routing."
        ),
        (
            "How do we handle the LLM code generation pipeline?",
            "Three-stage pipeline: (1) Architecture Spec → Structured JSON: Parse the canvas diagram into a formal spec — entities, relationships, API endpoints, data flows. (2) JSON Spec → Code Templates: LLM generates boilerplate for each component — models, routes, services, tests. We use a template library as few-shot examples. (3) Code Review: Second LLM pass reviews generated code for security issues, best practices, and consistency. Output goes into a staging area where the user can accept, modify, or regenerate each file. The whole pipeline is async with progress events via SSE."
        ),
    ],
    "jordan": [
        (
            "Let me plan the frontend architecture for Build Hub.",
            "The app is essentially three workspaces: (1) Dashboard — project list, team activity feed, AI suggestions. (2) Project View — split pane with canvas on the left, chat/decisions panel on the right. (3) Video Room — full-screen video grid with floating toolbar, chat sidebar, and whiteboard overlay. Navigation: top bar with project switcher, left sidebar for workspace selection. State management: Zustand stores for UI state, TanStack Query for server state, Yjs for collaborative state. Code splitting by workspace for fast initial load."
        ),
        (
            "How should the canvas/whiteboard component work?",
            "We'll use tldraw as the base — it gives us shapes, arrows, text, freehand drawing, and multi-user cursors out of the box. Customizations: (1) Architecture-specific shapes — database cylinders, API boxes, queue symbols, service containers. (2) Smart connectors — arrows that snap to ports on shapes and auto-route around obstacles. (3) AI layer — right-click any shape to ask the AI to elaborate, suggest alternatives, or generate code for that component. (4) Component palette — drag-and-drop from a library of pre-built architecture patterns. The canvas state syncs via Yjs + WebSocket to all participants."
        ),
        (
            "What about the video conferencing UI?",
            "The video grid uses a responsive layout: 1 person = full screen, 2 = side-by-side, 3-4 = 2x2 grid, 5-9 = 3x3, 10+ = paginated grid with active speaker detection. Each tile shows: video feed, name label, mute/camera indicators, reaction emoji overlay. Floating toolbar at the bottom: mute, camera, screen share, whiteboard toggle, reactions, chat, participants, leave. The whiteboard overlay is a semi-transparent canvas that sits on top of the video grid — participants can draw and annotate while seeing each other. Screen share replaces the speaker's video tile with their screen content."
        ),
        (
            "How do we handle the Idea Vault UI?",
            "Card-based grid layout, each card shows: project name, brief description, AI feasibility score (color-coded bar), tech stack badges, team members avatars, last activity timestamp. Filters: status (draft/active/archived), tech stack, complexity, team. Sort by: newest, most active, highest AI score. Click a card → full project view. Create new: modal with name, description, optional voice input for description (Whisper transcription). AI auto-suggests similar existing projects to prevent duplication. Search is semantic — powered by pgvector embeddings of project descriptions."
        ),
    ],
    "riley": [
        (
            "Let me outline the testing strategy for Build Hub.",
            "Four layers: (1) Unit tests — Jest for frontend components, pytest for backend endpoints. Target 80% coverage on business logic. (2) Integration tests — test API endpoints with real database, WebSocket connections, CRDT sync. (3) E2E tests — Playwright for critical user flows: create project, add to canvas, start video call, generate code. (4) Load tests — k6 for API performance, custom WebSocket load test for real-time features, WebRTC simulcast test for video rooms. We also need chaos testing for the SFU — what happens when a media server crashes mid-call?"
        ),
        (
            "What are the critical edge cases we need to test?",
            "Video: (1) Participant joins with no camera/mic — should show avatar placeholder. (2) Network degradation — SFU should auto-reduce quality. (3) 20+ participants — pagination must work smoothly. (4) Screen share + whiteboard simultaneously. Canvas: (1) Simultaneous edits to the same shape — CRDT conflict resolution. (2) Offline mode — local changes queue and sync on reconnect. (3) Very large canvases (1000+ shapes) — virtualization needed. AI: (1) LLM timeout — graceful fallback with retry. (2) Generated code with security vulnerabilities — review pass must catch. (3) Rate limiting per team tier."
        ),
    ],
    "casey": [
        (
            "Let me plan the infrastructure for Build Hub.",
            "Three environments: dev (Docker Compose on dev machines), staging (single-node K8s), prod (multi-node K8s on AWS/Hetzner). Services: (1) API server — 2-4 replicas behind load balancer, (2) WebSocket server — sticky sessions via IP hash, (3) SFU media server — dedicated high-bandwidth nodes, auto-scaling group, (4) Worker queue — Redis + ARQ for async tasks (AI generation, recording processing, transcript generation). Database: PostgreSQL with read replicas for analytics, Redis cluster for pub/sub and caching. Storage: MinIO for self-hosted S3, CDN in front for static assets."
        ),
        (
            "How do we handle monitoring and observability?",
            "Prometheus + Grafana for metrics: API latency p50/p95/p99, WebSocket connection count, SFU bandwidth usage, LLM generation time, queue depth. Structured logging with JSON → Loki for aggregation. Distributed tracing with OpenTelemetry — especially important for the multi-service AI pipeline. Alerting: PagerDuty integration for prod, Slack webhooks for staging. Key SLIs: API response time < 200ms p95, WebSocket message latency < 50ms, Video join time < 3 seconds, AI code generation < 30 seconds. Health checks on every service with automatic restart on failure."
        ),
    ],
}

PHASE_2_ARCHITECTURE = {
    "alex": [
        (
            "Let's formalize the Build Hub system architecture. What are the key architectural decisions?",
            "Decision 1: Microservices over monolith — the video/media pipeline has fundamentally different scaling needs than the REST API. Decision 2: Event-driven communication between services via Redis Streams — decouples the AI pipeline from the API layer. Decision 3: CRDT-first for all collaborative data — canvas, chat, decisions list. This eliminates the need for operational transforms and handles offline scenarios naturally. Decision 4: Plugin architecture for AI providers — users can bring their own API keys for Claude, GPT, or use our hosted Ollama instances. Decision 5: Multi-tenant with team isolation at the database level using PostgreSQL Row Level Security."
        ),
        (
            "How should we design the data flow for a typical collaboration session?",
            "Flow: User opens project → API fetches project metadata + latest architecture version → WebSocket connection established to canvas room → Yjs doc loaded from server, existing state applied → User draws on canvas → Yjs CRDT operations broadcast to all participants via WebSocket → Server persists CRDT updates to PostgreSQL every 5 seconds (debounced) → If user requests AI analysis, the canvas state is serialized and sent to the AI pipeline via Redis Stream → AI worker picks up the job, generates analysis/code → Result sent back via SSE to the requesting user → Other participants see the AI-generated components appear on the canvas in real-time."
        ),
        (
            "What about the authentication and authorization model?",
            "OAuth2 with JWT tokens. Providers: GitHub (primary — devs already have accounts), Google, email/password fallback. Authorization: RBAC with four roles per team — Owner (full control), Admin (manage members, settings), Editor (create/modify projects), Viewer (read-only). Project-level permissions inherit from team role but can be overridden. API keys for programmatic access with scoped permissions. The video rooms use short-lived tokens (5 min) that are refreshed automatically — prevents replay attacks on the media server."
        ),
    ],
    "sam": [
        (
            "Let me define the detailed API contracts for the core endpoints.",
            "Project API: POST /api/v1/projects — body: {name, description, template_id?, team_id} → 201 {id, name, ...}. GET /api/v1/projects/:id?include=architecture,decisions,components → 200 with nested objects. Architecture API: POST /api/v1/projects/:id/architectures — creates new version from canvas state. GET /api/v1/projects/:id/architectures/:version — retrieves specific version. POST /api/v1/projects/:id/architectures/:version/generate — triggers AI code generation pipeline, returns job_id. GET /api/v1/jobs/:job_id — poll job status with SSE alternative at /api/v1/jobs/:job_id/stream."
        ),
        (
            "How should the WebRTC signaling protocol work?",
            "Custom signaling over WebSocket. Message types: (1) join_room {room_id, user_id, media_constraints} → server responds with existing_participants list. (2) offer {to_user_id, sdp} → forwarded to target peer. (3) answer {to_user_id, sdp} → forwarded back. (4) ice_candidate {to_user_id, candidate} → forwarded. (5) media_state {audio: bool, video: bool} → broadcast to all. (6) screen_share_start/stop → triggers layout recalculation on all clients. (7) whiteboard_stroke {points, color, width} → broadcast for real-time drawing. The SFU intercepts offer/answer to route media through itself instead of peer-to-peer when participant count > 4."
        ),
        (
            "What's the database migration strategy?",
            "Alembic for Python/PostgreSQL migrations with a strict naming convention: YYYYMMDD_HHMMSS_description.py. Every migration must be reversible (downgrade function required). Schema versioning: the API reports its expected schema version in the health check. Deployment: run migrations before rolling out new API pods — blue/green deployment ensures zero downtime. For the CRDT data, we use a separate documents table with JSONB column — no migrations needed for schema changes in the collaborative state, since CRDTs are schema-agnostic."
        ),
    ],
    "jordan": [
        (
            "Let me design the component architecture for the React frontend.",
            "Top-level layout: AppShell (sidebar + header + main content area). Route structure: / → Dashboard, /projects/:id → ProjectView, /projects/:id/room → VideoRoom, /vault → IdeaVault, /settings → TeamSettings. Shared components: Avatar, Badge, Button, Card, Dialog, Dropdown, Input, Tooltip (all from shadcn/ui, customized). Domain components: ProjectCard, CanvasToolbar, VideoTile, ParticipantList, DecisionCard, ComponentTree. State: useProjectStore (Zustand) for current project, useCanvasStore for tldraw state, useVideoStore for WebRTC connections and media streams."
        ),
        (
            "How should the video room UI handle different screen sizes?",
            "Responsive breakpoints: Mobile (<768px) — single video tile with swipe to switch participants, floating self-view, bottom sheet for controls. Tablet (768-1024px) — 2x2 grid maximum, sidebar for chat. Desktop (1024-1440px) — up to 3x3 grid, right sidebar for chat + participants. Ultra-wide (1440px+) — gallery view with up to 5x5, or theater mode where active speaker takes 70% of the screen. The whiteboard overlay scales proportionally. On mobile, whiteboard gets its own full-screen mode since overlay would be too small to draw on."
        ),
        (
            "What about accessibility requirements?",
            "WCAG 2.1 AA compliance minimum. Keyboard navigation: all interactive elements focusable, canvas supports keyboard shortcuts for shape creation and manipulation. Screen reader: ARIA labels on all controls, live regions for chat messages and participant join/leave announcements. Video: closed captions from Whisper transcription displayed as subtitle overlay, adjustable font size. Color: all status indicators use both color and icon/pattern (not color alone). High contrast mode: alternative theme with stronger borders and backgrounds. Reduced motion: disable animations for prefers-reduced-motion users."
        ),
    ],
    "riley": [
        (
            "Let me define the performance benchmarks for Build Hub.",
            "API: p95 response time < 200ms for CRUD operations, < 500ms for search queries. WebSocket: message round-trip < 100ms for canvas operations. Video: time to first frame < 2 seconds on desktop, < 4 seconds on mobile. AI: code generation < 60 seconds for simple components, < 5 minutes for full project scaffold. Canvas: smooth 60fps with up to 500 shapes visible, acceptable 30fps up to 2000 shapes. Memory: frontend bundle < 500KB gzipped initial load, < 2MB total with all lazy chunks. Database: query time < 50ms for project lookups with joins, < 200ms for semantic search."
        ),
        (
            "What are the security considerations we need to test?",
            "Authentication: brute force protection (rate limiting on login), JWT expiration and refresh flow, OAuth state parameter validation. Authorization: test that viewers cannot modify projects, test cross-team isolation (user A cannot access team B's projects), test API key scope restrictions. Data: SQL injection on all input fields, XSS prevention in chat messages and project descriptions, CSRF protection on state-changing endpoints. Video: SRTP for encrypted media, DTLS for secure data channels, room access tokens cannot be reused. AI: prompt injection prevention — user input to AI must be sandboxed, generated code scanned for known vulnerability patterns."
        ),
    ],
    "casey": [
        (
            "Let me design the CI/CD pipeline for Build Hub.",
            "GitHub Actions with three workflows: (1) PR Check — lint, type check, unit tests, build check, runs in < 5 minutes. (2) Staging Deploy — triggered on merge to main, runs full test suite including integration tests, builds Docker images, pushes to registry, deploys to staging K8s via Helm, runs E2E tests against staging. (3) Production Deploy — manual trigger with approval gate, canary deployment (10% traffic for 15 minutes, auto-rollback on error rate spike), then full rollout. Docker: multi-stage builds for all services, distroless base images for security. Helm charts with values files per environment."
        ),
        (
            "How should we handle the media server scaling?",
            "SFU auto-scaling based on two metrics: active room count and total bandwidth. Each media server handles up to 50 concurrent rooms or 500 Mbps — whichever limit is hit first triggers scale-up. Scale-down after 10 minutes of underutilization (not immediate — avoid thrashing). Room-to-server affinity: once a room is assigned to a server, all participants connect there. If a server fails, rooms are redistributed to remaining servers — clients reconnect automatically with exponential backoff. For recording, dedicated encoding nodes that receive the composite stream from the SFU — separate from the routing nodes to avoid CPU contention."
        ),
    ],
}

PHASE_3_IMPLEMENTATION = {
    "alex": [
        (
            "I've been reviewing Sam's API design and Jordan's component architecture. How do they connect?",
            "The key integration points are: (1) ProjectView component uses TanStack Query to fetch from Sam's GET /api/v1/projects/:id endpoint — the include parameter controls what nested data loads. (2) Canvas sync: Jordan's useCanvasStore connects to the WebSocket at /ws/canvas/:project_id, Yjs handles the CRDT merge, and Sam's server persists snapshots every 5 seconds to the architectures table. (3) AI generation: When Jordan's toolbar triggers code gen, it calls POST /api/v1/projects/:id/architectures/:version/generate, then subscribes to the SSE stream for progress updates. (4) Video rooms: Jordan's useVideoStore manages WebRTC peer connections, Sam's Go signaling server handles the offer/answer exchange."
        ),
        (
            "What patterns should we use for error handling across the stack?",
            "Consistent error envelope: {error: {code: string, message: string, details?: object}}. Frontend: TanStack Query's error boundaries + toast notifications for recoverable errors, full-page error state for fatal errors. Backend: custom exception classes mapped to HTTP status codes via FastAPI exception handlers. WebSocket: error frame type with reconnection logic on the client. AI pipeline: job status includes error field with retry count — auto-retry up to 3 times with exponential backoff, then surface to user with 'Retry' button. Never expose internal error details to the client — log them server-side with correlation IDs."
        ),
    ],
    "sam": [
        (
            "Let me implement the real-time notification system for Build Hub.",
            "Redis pub/sub channels per project: build-hub:project:{id}:events. Event types: member_joined, member_left, decision_created, architecture_updated, ai_job_completed, comment_added. Each event has: {type, timestamp, user_id, payload}. The API server subscribes to relevant channels for connected WebSocket clients and forwards events. For offline users: events are stored in a notifications table and delivered as a batch when they reconnect. Push notifications via Web Push API for critical events (someone @mentions you, AI job completed). Rate limiting: max 10 events per second per channel to prevent spam."
        ),
        (
            "How should we implement the voice transcription pipeline for video rooms?",
            "Architecture: Audio stream from each participant → WebSocket → server-side audio buffer → Whisper model (running on GPU node) → text segments with timestamps → broadcast as caption events. Implementation: The SFU forks each participant's audio track to a transcription worker. The worker accumulates 5-second audio chunks and sends them to Whisper. Whisper returns text with word-level timestamps. We merge overlapping segments and apply speaker diarization (matching audio to participant by their media track ID). Post-meeting: all segments are concatenated into a full transcript, stored in PostgreSQL, and indexed for semantic search."
        ),
    ],
    "jordan": [
        (
            "Let me implement the whiteboard overlay for video rooms.",
            "The overlay is a transparent HTML5 Canvas element positioned absolutely over the video grid container. Drawing tools: pen (freehand), line, rectangle, ellipse, text, arrow, eraser. State synced via the same WebSocket as video signaling — drawing events are broadcast to all participants. Each stroke is a series of points with color, width, and opacity. Undo/redo per user using a command stack. Clear all requires moderator permission. The canvas scales with the video grid — coordinates are stored as percentages (0-1) not pixels, so drawings look correct at any resolution. Performance: batch drawing events into 50ms frames to reduce WebSocket traffic."
        ),
        (
            "How should the AI suggestion panel work in the project canvas?",
            "Floating panel on the right side of the canvas, toggleable. Three modes: (1) Auto-suggest — AI analyzes the current canvas state every 30 seconds and suggests improvements: missing components, potential bottlenecks, security concerns. Suggestions appear as cards that can be dismissed or applied (adds the suggested component to the canvas). (2) Ask AI — text input where users can ask questions about the architecture. Responses reference specific components on the canvas with highlight animation. (3) Generate — select components on canvas, click Generate, and the AI produces implementation code for those specific components. Progress bar shows generation status with cancel button."
        ),
    ],
    "riley": [
        (
            "Let me design the load testing scenario for video conferencing.",
            "Using k6 with the xk6-browser extension for WebRTC load testing. Scenario: simulate 100 concurrent rooms with 5 participants each (500 total video streams). Each virtual participant: sends a 720p video stream (simulated with a static video file), receives 4 streams, sends/receives audio. Metrics to track: time to first frame per participant, packet loss rate, jitter, CPU usage on SFU nodes, bandwidth per node. Ramp-up: 10 rooms per minute over 10 minutes, hold for 20 minutes, ramp down. Success criteria: < 1% packet loss, < 100ms jitter, SFU CPU < 80%, all participants receive video within 3 seconds."
        ),
        (
            "What about testing the CRDT synchronization under conflict?",
            "Dedicated test suite for CRDT edge cases: (1) Simultaneous move — two users move the same shape at the same time to different positions. Expected: one wins deterministically (based on client ID ordering), both clients converge. (2) Delete during edit — user A deletes a shape while user B is editing its text. Expected: delete wins, user B's edit is discarded gracefully. (3) Offline divergence — simulate 30 seconds of offline edits on two clients, then reconnect. Expected: all changes merge without data loss. (4) Large document — 5000 shapes, 10 concurrent editors, verify convergence within 2 seconds. (5) Version rollback — revert to a previous version while others are editing. Expected: all clients snap to the rolled-back state."
        ),
    ],
    "casey": [
        (
            "Let me set up the Kubernetes manifests for Build Hub.",
            "Helm chart structure: charts/build-hub/ with subcharts for each service. API deployment: 3 replicas, 512Mi memory limit, 250m CPU, rolling update strategy with maxSurge=1. WebSocket server: 2 replicas with sticky sessions (annotation: nginx.ingress.kubernetes.io/affinity: cookie), 256Mi memory. SFU nodes: DaemonSet on dedicated media nodes (labeled role=media), hostNetwork=true for optimal UDP performance, 4Gi memory, 2 CPU. Workers: 2 replicas, 1Gi memory for AI tasks. PostgreSQL: StatefulSet with PVC, 10Gi storage, daily backup CronJob to S3. Redis: Sentinel setup with 3 nodes for HA."
        ),
    ],
}

PHASE_4_REVIEW = {
    "riley": [
        (
            "Running the full stress test suite against the Build Hub architecture.",
            "Results summary: API load test (1000 req/s for 5 minutes) — p50: 45ms, p95: 180ms, p99: 350ms, 0 errors. WebSocket test (500 concurrent connections, 100 msg/s each) — message latency p95: 35ms, 0 dropped connections. Canvas CRDT test (50 concurrent editors, 1000 operations each) — convergence time: 800ms average, 2.1s worst case, 0 data inconsistencies. Database test (10000 projects, complex queries) — project lookup with joins: 12ms, semantic search: 95ms, full-text search: 28ms. All benchmarks within target. Identified one concern: memory usage grows linearly with canvas size in the Yjs document — may need to implement shape virtualization for very large projects."
        ),
    ],
    "casey": [
        (
            "Running infrastructure chaos testing.",
            "Tests performed: (1) Kill one API pod — load balancer routes to remaining pods, no dropped requests. (2) Kill the primary PostgreSQL — failover to replica in 8 seconds, 3 failed requests during switchover. (3) Network partition between SFU and signaling — participants experience 5-second freeze then auto-reconnect. (4) Redis sentinel failover — 2-second pub/sub gap, no data loss. (5) Fill disk on worker node — job queue pauses, alert fires, auto-scales to new node. (6) Simulate Ollama crash during code generation — job marked as failed after 30-second timeout, user sees retry button. All scenarios handled gracefully. Recommendation: reduce PostgreSQL failover time with synchronous replication."
        ),
    ],
    "alex": [
        (
            "Let me do a final architecture review before we sign off on the Build Hub design.",
            "Architecture review checklist: Scalability — horizontal scaling for all stateless services, vertical scaling for database and SFU. Reliability — no single point of failure, all services have health checks and auto-restart. Security — end-to-end encryption for video, JWT with short expiry for API, RLS for multi-tenancy, input sanitization everywhere. Performance — sub-200ms API responses, sub-100ms real-time updates, sub-3s video join. Maintainability — clean service boundaries, shared library for common types, comprehensive API documentation via OpenAPI. Cost — estimated $500/month for staging, $2000-5000/month for prod depending on video usage. The architecture is solid. Ready to build."
        ),
    ],
}

# Search queries that agents use to find each other's work
SEARCH_QUERIES = [
    "WebRTC video conferencing architecture",
    "database schema project management",
    "CRDT real-time collaboration",
    "AI code generation pipeline",
    "authentication OAuth JWT",
    "Kubernetes deployment media server",
    "testing strategy load testing",
    "whiteboard canvas drawing overlay",
    "notification system real-time events",
    "voice transcription Whisper pipeline",
    "accessibility WCAG compliance",
    "CI/CD pipeline GitHub Actions",
    "SFU auto-scaling bandwidth",
    "component architecture React frontend",
    "error handling patterns",
    "performance benchmarks latency",
    "security considerations API",
    "microservices event-driven architecture",
    "monitoring observability Prometheus",
    "responsive video grid layout",
]

# Direct memory content for batch operations
BATCH_MEMORIES = [
    {"content": "Build Hub tech stack decision: React 19 + TypeScript frontend, FastAPI + Go backend, PostgreSQL + Redis + Neo4j storage, Kubernetes deployment, mediasoup SFU for video.", "memory_type": "semantic", "tags": ["tech-stack", "decision"], "importance": 0.8},
    {"content": "Build Hub video conferencing uses WebRTC with SFU architecture (mediasoup). Peer-to-peer mesh for 1-4 users, SFU routing for 5+. SRTP encryption, DTLS for data channels.", "memory_type": "semantic", "tags": ["video", "webrtc", "sfu"], "importance": 0.75},
    {"content": "Build Hub whiteboard overlay: transparent HTML5 Canvas over video grid, coordinates stored as 0-1 percentages for resolution independence, strokes batched in 50ms frames.", "memory_type": "semantic", "tags": ["whiteboard", "canvas", "video"], "importance": 0.7},
    {"content": "Build Hub AI integration is three-tier: local Ollama for real-time suggestions, cloud API (Claude/GPT) for complex analysis, specialized models (CodeLlama, Whisper) for specific tasks.", "memory_type": "semantic", "tags": ["ai", "llm", "architecture"], "importance": 0.8},
    {"content": "Build Hub CRDT strategy: Yjs for conflict-free real-time editing on canvas, schema-agnostic JSONB storage in PostgreSQL, 5-second debounced persistence.", "memory_type": "semantic", "tags": ["crdt", "yjs", "real-time"], "importance": 0.75},
    {"content": "Build Hub auth model: OAuth2 + JWT, providers GitHub/Google/email, RBAC with Owner/Admin/Editor/Viewer roles, PostgreSQL Row Level Security for multi-tenancy.", "memory_type": "semantic", "tags": ["auth", "security", "rbac"], "importance": 0.7},
    {"content": "Build Hub performance targets: API p95 < 200ms, WebSocket roundtrip < 100ms, video first frame < 2s desktop / 4s mobile, AI code gen < 60s simple / 5min full scaffold.", "memory_type": "semantic", "tags": ["performance", "benchmarks", "targets"], "importance": 0.65},
    {"content": "How to deploy Build Hub: Docker Compose for dev, single-node K8s for staging, multi-node K8s for prod. SFU on dedicated media nodes with hostNetwork=true for UDP performance.", "memory_type": "procedural", "tags": ["deployment", "kubernetes", "infrastructure"], "importance": 0.7},
    {"content": "How to test Build Hub video: k6 with xk6-browser for WebRTC load testing. Simulate 100 rooms x 5 participants (500 streams). Track time-to-first-frame, packet loss, jitter, SFU CPU.", "memory_type": "procedural", "tags": ["testing", "video", "load-testing"], "importance": 0.65},
    {"content": "Build Hub voice transcription pipeline: participant audio → SFU fork → 5s chunks → Whisper GPU → text with timestamps → speaker diarization → captions + searchable transcript.", "memory_type": "procedural", "tags": ["transcription", "whisper", "voice"], "importance": 0.7},
]


# ═══════════════════════════════════════════════════════════════
# AGENTS
# ═══════════════════════════════════════════════════════════════


class Agent:
    def __init__(self, name: str, role: str, client: RecallClient, stats: Stats):
        self.name = name
        self.role = role
        self.client = client
        self.stats = stats
        self.session_id: str | None = None
        self.stored_ids: list[str] = []

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{self.name}] {msg}")

    async def start_session(self, task: str):
        self.session_id = await self.client.create_session(task)
        if self.session_id:
            self.log(f"Started session: {self.session_id[:12]}... task={task[:50]}")
        else:
            self.log("FAILED to start session")

    async def end_session(self):
        if self.session_id:
            # Wait for background signal detection to complete (Ollama is slow under load)
            await asyncio.sleep(15)
            # Check for signals BEFORE ending (ending clears pending signals)
            signals = await self.client.get_signals(self.session_id)
            if signals:
                self.log(f"Found {len(signals)} signals, approving...")
                for i in range(len(signals)):
                    await self.client.approve_signal(self.session_id, index=0)
                    await asyncio.sleep(4)  # Pace for embedding service
            else:
                self.log("No pending signals (detection may still be running)")
            await self.client.end_session(self.session_id)
            self.log(f"Ended session {self.session_id[:12]}...")
            self.session_id = None

    async def discuss(self, conversations: list[tuple[str, str]], phase_name: str):
        """Ingest a list of (user, assistant) turn pairs into the current session."""
        if not self.session_id:
            await self.start_session(f"Build Hub - {phase_name} - {self.role}")

        for user_msg, asst_msg in conversations:
            # Send both turns in one request to halve rate limit usage
            await self.client.ingest_turn_pair(self.session_id, user_msg, asst_msg)
            self.log(f"Discussed: {user_msg[:60]}...")
            await asyncio.sleep(random.uniform(*TURN_DELAY))

    async def search_and_build(self, query: str):
        """Search for other agents' work and store a synthesis memory."""
        results = await self.client.search_browse(query, limit=5)
        if results:
            summaries = [r.get("summary", "")[:80] for r in results[:3]]
            synthesis = f"[{self.name}] Found {len(results)} related memories about '{query}'. Key findings: {'; '.join(summaries)}. This informs our {self.role.lower()} decisions for Build Hub."
            mid = await self.client.store_memory(
                synthesis,
                memory_type="episodic",
                tags=["synthesis", self.name.lower(), "build-hub"],
                importance=0.6,
            )
            if mid:
                self.stored_ids.append(mid)
                self.log(f"Synthesized from search: {query[:40]}...")
        else:
            self.log(f"No results for: {query[:40]}...")

    async def store_decision(self, content: str, tags: list[str], importance: float = 0.7):
        """Store a direct decision memory."""
        mid = await self.client.store_memory(content, "semantic", tags, importance)
        if mid:
            self.stored_ids.append(mid)
            self.log(f"Stored decision: {content[:50]}...")


class AlexAgent(Agent):
    """System Architect — designs the big picture."""

    async def run_phase_1(self):
        await self.start_session("Build Hub - Phase 1 Ideation - Architecture")
        await self.discuss(PHASE_1_IDEATION["alex"], "Ideation")
        await self.end_session()

    async def run_phase_2(self):
        await self.start_session("Build Hub - Phase 2 Architecture - System Design")
        await self.discuss(PHASE_2_ARCHITECTURE["alex"], "Architecture")
        # Search for Sam's and Jordan's work
        await self.search_and_build("API design database schema")
        await self.search_and_build("frontend component architecture React")
        await self.end_session()

    async def run_phase_3(self):
        await self.start_session("Build Hub - Phase 3 Implementation - Integration")
        await self.discuss(PHASE_3_IMPLEMENTATION["alex"], "Implementation")
        await self.search_and_build("WebRTC signaling protocol")
        await self.search_and_build("CRDT synchronization canvas")
        await self.end_session()

    async def run_phase_4(self):
        await self.start_session("Build Hub - Phase 4 Review - Architecture Review")
        await self.discuss(PHASE_4_REVIEW["alex"], "Review")
        # Final synthesis across all agents
        for q in random.sample(SEARCH_QUERIES, 5):
            await self.search_and_build(q)
        await self.end_session()


class SamAgent(Agent):
    """Backend Developer — designs APIs, databases, business logic."""

    async def run_phase_1(self):
        await self.start_session("Build Hub - Phase 1 Ideation - Backend")
        await self.discuss(PHASE_1_IDEATION["sam"], "Ideation")
        await self.end_session()

    async def run_phase_2(self):
        await self.start_session("Build Hub - Phase 2 Architecture - Backend API")
        await self.discuss(PHASE_2_ARCHITECTURE["sam"], "Architecture")
        await self.search_and_build("system architecture microservices")
        await self.end_session()

    async def run_phase_3(self):
        await self.start_session("Build Hub - Phase 3 Implementation - Backend")
        await self.discuss(PHASE_3_IMPLEMENTATION["sam"], "Implementation")
        await self.search_and_build("video conferencing SFU architecture")
        await self.search_and_build("Kubernetes deployment manifests")
        await self.end_session()

    async def run_phase_4(self):
        # Sam does batch memory operations during review
        self.log("Storing batch of architectural decisions...")
        for batch_item in BATCH_MEMORIES:
            item = {**batch_item, "domain": DOMAIN}
            mid = await self.client.store_memory(
                item["content"], item["memory_type"],
                item.get("tags", []), item.get("importance", 0.5),
            )
            if mid:
                self.stored_ids.append(mid)
            await asyncio.sleep(2)
        self.log(f"Batch stored {len(BATCH_MEMORIES)} architectural decisions")


class JordanAgent(Agent):
    """Frontend Developer — designs UI/UX, React components."""

    async def run_phase_1(self):
        await self.start_session("Build Hub - Phase 1 Ideation - Frontend")
        await self.discuss(PHASE_1_IDEATION["jordan"], "Ideation")
        await self.end_session()

    async def run_phase_2(self):
        await self.start_session("Build Hub - Phase 2 Architecture - Frontend")
        await self.discuss(PHASE_2_ARCHITECTURE["jordan"], "Architecture")
        await self.search_and_build("backend API endpoints REST")
        await self.search_and_build("authentication OAuth JWT model")
        await self.end_session()

    async def run_phase_3(self):
        await self.start_session("Build Hub - Phase 3 Implementation - Frontend")
        await self.discuss(PHASE_3_IMPLEMENTATION["jordan"], "Implementation")
        await self.search_and_build("AI code generation pipeline")
        await self.search_and_build("notification system events")
        await self.end_session()

    async def run_phase_4(self):
        # Jordan does timeline and browse during review
        self.log("Reviewing all build-hub memories via timeline...")
        entries = await self.client.search_timeline(limit=50)
        self.log(f"Timeline returned {len(entries)} entries")

        self.log("Browsing for video conferencing memories...")
        results = await self.client.search_browse("video conferencing whiteboard", 20)
        self.log(f"Browse returned {len(results)} results")

        results = await self.client.search_browse("frontend React components UI", 20)
        self.log(f"Frontend browse returned {len(results)} results")


class RileyAgent(Agent):
    """QA/Stress Tester — exercises edge cases, bulk ops, verifies data integrity."""

    async def run_phase_1(self):
        await self.start_session("Build Hub - Phase 1 Ideation - Testing")
        await self.discuss(PHASE_1_IDEATION["riley"], "Ideation")
        await self.end_session()

    async def run_phase_2(self):
        await self.start_session("Build Hub - Phase 2 Architecture - QA")
        await self.discuss(PHASE_2_ARCHITECTURE["riley"], "Architecture")
        await self.end_session()

    async def run_phase_3(self):
        await self.start_session("Build Hub - Phase 3 Implementation - QA")
        await self.discuss(PHASE_3_IMPLEMENTATION["riley"], "Implementation")
        await self.end_session()

    async def run_phase_4(self):
        """Heavy stress testing phase."""
        self.log("=== STRESS TEST BEGIN ===")

        # Bulk store + delete cycle
        self.log("Batch storing 10 test memories...")
        batch_items = [
            {
                "content": f"Build Hub stress test memory #{i}: Testing batch operations with various content lengths and types to verify Recall handles bulk operations correctly under load.",
                "memory_type": random.choice(["semantic", "episodic", "procedural"]),
                "domain": DOMAIN,
                "tags": ["stress-test", f"batch-{i}"],
                "importance": round(random.uniform(0.3, 0.8), 2),
            }
            for i in range(10)
        ]
        result = await self.client.batch_store(batch_items)
        stored_ids = []
        if result and "ids" in result:
            stored_ids = result["ids"]
            self.log(f"Batch stored {len(stored_ids)} memories")
        elif result and "results" in result:
            stored_ids = [r.get("id") for r in result["results"] if r.get("id")]
            self.log(f"Batch stored {len(stored_ids)} memories")
        else:
            # Fall back to individual stores
            for item in batch_items:
                mid = await self.client.store_memory(
                    item["content"], item["memory_type"],
                    item.get("tags", []), item.get("importance", 0.5),
                )
                if mid:
                    stored_ids.append(mid)
                await asyncio.sleep(1)
            self.log(f"Individually stored {len(stored_ids)} memories")

        await asyncio.sleep(3)

        # Search for stress test memories
        self.log("Searching for stress test memories...")
        results = await self.client.search_browse("stress test batch operations", 15)
        self.log(f"Found {len(results)} stress test results")

        # Retrieve individual memories
        for mid in stored_ids[:3]:
            mem = await self.client.get_memory(mid)
            if mem:
                self.log(f"Retrieved memory {mid[:12]}... type={mem.get('memory_type')}")
            await asyncio.sleep(1)

        # Bulk delete the stress test memories
        if stored_ids:
            self.log(f"Batch deleting {len(stored_ids)} stress test memories...")
            await self.client.batch_delete(stored_ids)
            self.log("Batch delete complete")

        # Timeline stress
        self.log("Timeline query (large limit)...")
        entries = await self.client.search_timeline(limit=100)
        self.log(f"Timeline returned {len(entries)} entries")

        # Multiple rapid searches
        self.log("Rapid search burst (10 queries)...")
        for q in random.sample(SEARCH_QUERIES, 10):
            await self.client.search_browse(q, 5)
            await asyncio.sleep(0.5)
        self.log("Rapid search burst complete")

        # Full-text search queries
        self.log("Full search queries...")
        for q in ["Build Hub", "WebRTC", "Kubernetes", "React", "PostgreSQL"]:
            results = await self.client.search_query(q, 5)
            self.log(f"  query '{q}' → {len(results)} results")
            await asyncio.sleep(1)

        # Audit log queries
        self.log("Querying audit log...")
        for action in ["create", "delete", ""]:
            entries = await self.client.audit(limit=20, action=action)
            self.log(f"  audit action='{action or 'all'}' → {len(entries)} entries")
            await asyncio.sleep(1)

        self.log("=== STRESS TEST COMPLETE ===")


class CaseyAgent(Agent):
    """DevOps — monitors health, runs maintenance, checks infrastructure."""

    async def run_phase_1(self):
        await self.start_session("Build Hub - Phase 1 Ideation - Infrastructure")
        await self.discuss(PHASE_1_IDEATION["casey"], "Ideation")
        await self.end_session()

    async def run_phase_2(self):
        await self.start_session("Build Hub - Phase 2 Architecture - DevOps")
        await self.discuss(PHASE_2_ARCHITECTURE["casey"], "Architecture")
        await self.end_session()

    async def run_phase_3(self):
        await self.start_session("Build Hub - Phase 3 Implementation - DevOps")
        await self.discuss(PHASE_3_IMPLEMENTATION["casey"], "Implementation")
        await self.end_session()

    async def run_phase_4(self):
        """Infrastructure maintenance and monitoring phase."""
        self.log("=== MAINTENANCE OPS BEGIN ===")

        # Health checks
        self.log("Running health checks...")
        h = await self.client.health()
        if h:
            status = h.get("status", "unknown")
            checks = h.get("checks", {})
            self.log(f"Health: {status}")
            for svc, val in checks.items():
                self.log(f"  {svc}: {val}")

        # Stats
        self.log("Fetching system stats...")
        s = await self.client.stats_endpoint()
        if s:
            mems = s.get("memories", {})
            self.log(f"Stats: {mems.get('total', '?')} memories, {mems.get('graph_nodes', '?')} nodes, {mems.get('relationships', '?')} rels")

        # Domain stats
        self.log("Fetching domain stats...")
        d = await self.client.domain_stats()
        if d:
            for dom in d.get("domains", []):
                self.log(f"  {dom['domain']}: {dom['count']} memories, avg_imp={dom['avg_importance']:.3f}")

        # Ollama info
        self.log("Checking Ollama info...")
        o = await self.client.ollama_info()
        if o:
            self.log(f"Ollama v{o.get('version', '?')}: {len(o.get('models', []))} models, {len(o.get('running', []))} running")
            for m in o.get("running", []):
                self.log(f"  Running: {m['name']} — RAM: {m['size_bytes'] / 1e9:.1f}GB, ctx: {m['context_length']}")

        # Sessions list
        self.log("Listing sessions...")
        sessions = await self.client.sessions_list()
        build_hub_sessions = [s for s in sessions if (s.get("current_task") or "").startswith("Build Hub")]
        self.log(f"Total sessions: {len(sessions)}, Build Hub sessions: {len(build_hub_sessions)}")

        await asyncio.sleep(5)

        # Consolidation (dry run)
        self.log("Running consolidation (dry run)...")
        c = await self.client.run_consolidation(dry_run=True)
        if c:
            self.log(f"Consolidation dry run: {c.get('clusters_merged', 0)} clusters, {c.get('memories_merged', 0)} memories")

        await asyncio.sleep(5)

        # Decay
        self.log("Running decay...")
        d = await self.client.run_decay()
        if d:
            self.log(f"Decay: processed={d.get('processed', 0)}, decayed={d.get('decayed', 0)}, archived={d.get('archived', 0)}")

        await asyncio.sleep(5)

        # Reconcile
        self.log("Running reconcile (dry run)...")
        r = await self.client.run_reconcile()
        if r:
            self.log(f"Reconcile: {r}")

        await asyncio.sleep(5)

        # Export
        self.log("Running export...")
        e = await self.client.run_export()
        if e:
            count = e.get("count", e.get("exported", "?"))
            self.log(f"Export: {count} memories exported")

        # Final health check
        self.log("Final health check...")
        h = await self.client.health()
        if h:
            self.log(f"Final status: {h.get('status', 'unknown')}")

        self.log("=== MAINTENANCE OPS COMPLETE ===")


# ═══════════════════════════════════════════════════════════════
# SSE MONITOR (background task)
# ═══════════════════════════════════════════════════════════════


async def sse_monitor(base_url: str, stats: Stats, stop_event: asyncio.Event):
    """Background task that listens to SSE events and counts them."""
    url = f"{base_url}/events/stream?token={API_KEY}"
    while not stop_event.is_set():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url) as response:
                    async for line in response.aiter_lines():
                        if stop_event.is_set():
                            break
                        if line.startswith("data:"):
                            stats.sse_events_received += 1
        except Exception:
            pass
        if not stop_event.is_set():
            await asyncio.sleep(5)


# ═══════════════════════════════════════════════════════════════
# STATUS REPORTER (background task)
# ═══════════════════════════════════════════════════════════════


async def status_reporter(stats: Stats, start_time: float, duration: int, stop_event: asyncio.Event):
    """Print periodic status updates."""
    while not stop_event.is_set():
        await asyncio.sleep(STATUS_INTERVAL)
        if stop_event.is_set():
            break
        elapsed = int(time.time() - start_time)
        remaining = max(0, duration - elapsed)
        mins_elapsed = elapsed // 60
        mins_remaining = remaining // 60
        print(f"\n{'='*60}")
        print(f"STATUS UPDATE — {mins_elapsed}m elapsed, {mins_remaining}m remaining")
        print(f"  Sessions: {stats.sessions_created} created, {stats.sessions_ended} ended")
        print(f"  Turns: {stats.turns_ingested} ingested")
        print(f"  Memories: {stats.memories_stored} stored, {stats.memories_searched} searched")
        print(f"  Signals: {stats.signals_loaded} loaded, {stats.signals_approved} approved")
        print(f"  Queries: {stats.browse_queries} browse, {stats.timeline_queries} timeline")
        print(f"  Maintenance: {stats.consolidation_runs} consolidate, {stats.decay_runs} decay")
        print(f"  SSE events: {stats.sse_events_received}")
        print(f"  Errors: {stats.errors}")
        print(f"{'='*60}\n")


# ═══════════════════════════════════════════════════════════════
# SIMULATION ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════


async def run_simulation(api_base: str, duration: int):
    stats = Stats()
    client = RecallClient(api_base, stats)
    start_time = time.time()
    stop_event = asyncio.Event()

    # Verify connectivity first
    print(f"\nConnecting to Recall at {api_base}...")
    h = await client.health()
    if not h:
        print("ERROR: Cannot connect to Recall API. Aborting.")
        await client.close()
        return
    print(f"Connected! Status: {h.get('status')} — {h.get('checks', {})}")
    print(f"Simulation duration: {duration // 60} minutes")
    print(f"Domain: {DOMAIN}")
    print()

    # Create agents
    alex = AlexAgent("Alex", "System Architect", client, stats)
    sam = SamAgent("Sam", "Backend Developer", client, stats)
    jordan = JordanAgent("Jordan", "Frontend Developer", client, stats)
    riley = RileyAgent("Riley", "QA Engineer", client, stats)
    casey = CaseyAgent("Casey", "DevOps Engineer", client, stats)

    # Start background tasks
    sse_task = asyncio.create_task(sse_monitor(api_base, stats, stop_event))
    status_task = asyncio.create_task(status_reporter(stats, start_time, duration, stop_event))

    def time_remaining() -> int:
        return max(0, duration - int(time.time() - start_time))

    def phase_msg(name: str):
        elapsed = int(time.time() - start_time) // 60
        print(f"\n{'-'*60}")
        print(f"  PHASE: {name} (at {elapsed}m)")
        print(f"{'-'*60}\n")

    # ── PHASE 1: Ideation (first 17% of time) ──
    phase_msg("1 — IDEATION")
    if time_remaining() > 0:
        await asyncio.gather(
            alex.run_phase_1(),
            sam.run_phase_1(),
            jordan.run_phase_1(),
            riley.run_phase_1(),
            casey.run_phase_1(),
        )

    # Brief pause between phases for signal processing
    if time_remaining() > 0:
        print("\n[Orchestrator] Phase 1 complete. Waiting for signal processing...\n")
        await asyncio.sleep(min(15, time_remaining()))

    # ── PHASE 2: Architecture (next 25% of time) ──
    if time_remaining() > 0:
        phase_msg("2 — ARCHITECTURE")
        await asyncio.gather(
            alex.run_phase_2(),
            sam.run_phase_2(),
            jordan.run_phase_2(),
            riley.run_phase_2(),
            casey.run_phase_2(),
        )

    if time_remaining() > 0:
        print("\n[Orchestrator] Phase 2 complete. Waiting for signal processing...\n")
        await asyncio.sleep(min(15, time_remaining()))

    # ── PHASE 3: Implementation (next 25% of time) ──
    if time_remaining() > 0:
        phase_msg("3 — IMPLEMENTATION")
        await asyncio.gather(
            alex.run_phase_3(),
            sam.run_phase_3(),
            jordan.run_phase_3(),
            riley.run_phase_3(),
            casey.run_phase_3(),
        )

    if time_remaining() > 0:
        print("\n[Orchestrator] Phase 3 complete. Waiting for signal processing...\n")
        await asyncio.sleep(min(15, time_remaining()))

    # ── PHASE 4: Review & Stress Test (remaining time) ──
    if time_remaining() > 0:
        phase_msg("4 — REVIEW & STRESS TEST")
        await asyncio.gather(
            alex.run_phase_4(),
            sam.run_phase_4(),
            jordan.run_phase_4(),
            riley.run_phase_4(),
            casey.run_phase_4(),
        )

    # ── PHASE 5: Retrospective (final minutes) ──
    if time_remaining() > 30:
        phase_msg("5 — RETROSPECTIVE")

        # Each agent searches for cross-cutting concerns
        retro_queries = [
            ("alex", "overall architecture decisions Build Hub"),
            ("sam", "backend API implementation details"),
            ("jordan", "frontend UI UX design decisions"),
            ("riley", "testing strategy quality assurance"),
            ("casey", "infrastructure deployment monitoring"),
        ]
        agents_map = {"alex": alex, "sam": sam, "jordan": jordan, "riley": riley, "casey": casey}
        for name, query in retro_queries:
            agent = agents_map[name]
            await agent.search_and_build(query)
            await asyncio.sleep(3)

        # Final health check
        casey.log("Final infrastructure status check...")
        h = await client.health()
        if h:
            casey.log(f"System status: {h.get('status')}")

        # Final audit check
        casey.log("Final audit log check...")
        entries = await client.audit(limit=10)
        casey.log(f"Recent audit entries: {len(entries)}")

    # ── PHASE 6: Continuous Activity (fill remaining time) ──
    cycle = 0
    while time_remaining() > 60:
        cycle += 1
        phase_msg(f"6 — CONTINUOUS OPS (cycle {cycle})")

        # Rotate through agents doing various operations
        agent_list = [alex, sam, jordan, riley, casey]
        active_agent = agent_list[cycle % 5]

        # Start a new session with discussion recap
        task_topic = random.choice([
            "Build Hub sprint review", "Build Hub tech debt assessment",
            "Build Hub feature prioritization", "Build Hub integration testing",
            "Build Hub performance optimization", "Build Hub security audit",
        ])
        await active_agent.start_session(f"{task_topic} cycle {cycle}")

        # Store a new observation memory
        observation = random.choice([
            f"Sprint cycle {cycle}: Build Hub architecture is stabilizing. WebRTC SFU handles 20 participants with <2s first-frame. CRDT sync confirmed stable under concurrent edits.",
            f"Sprint cycle {cycle}: Code scaffold pipeline generates FastAPI boilerplate in <30s. Template library covers 12 common patterns. Review pass catches 94% of issues.",
            f"Sprint cycle {cycle}: Video room UI responsive across desktop/tablet/mobile breakpoints. Canvas overlay renders at 60fps on modern GPUs. Dark mode contrast ratios pass WCAG AA.",
            f"Sprint cycle {cycle}: Load tests show 500 concurrent rooms × 5 users = 2500 streams. SFU CPU at 70% on dedicated media node. Memory stable at 8GB.",
            f"Sprint cycle {cycle}: CI/CD pipeline runs in 4min: lint → test → build → push → staging deploy. Canary releases roll out to 5% of prod traffic first.",
            f"Sprint cycle {cycle}: Knowledge graph links 150+ decisions to components. Auto-generated dependency tree identifies 3 circular dependencies to resolve.",
            f"Sprint cycle {cycle}: Voice transcription latency at 1.2s with GPU Whisper. Speaker diarization accuracy 91% with 4+ participants. Searchable transcripts indexed within 5min post-meeting.",
            f"Sprint cycle {cycle}: Security audit: all API endpoints behind JWT auth, RBAC enforced at middleware level, input sanitization on all user-facing fields, CSP headers configured.",
        ])
        mid = await active_agent.client.store_memory(
            observation, "episodic",
            tags=["sprint", f"cycle-{cycle}", active_agent.name.lower()],
            importance=round(random.uniform(0.4, 0.7), 2),
        )
        if mid:
            active_agent.stored_ids.append(mid)
            active_agent.log(f"Stored sprint observation (cycle {cycle})")

        await asyncio.sleep(5)

        # Search and synthesize
        search_topic = random.choice(SEARCH_QUERIES)
        await active_agent.search_and_build(search_topic)
        await asyncio.sleep(5)

        # Timeline check
        entries = await client.search_timeline(limit=20)
        active_agent.log(f"Timeline: {len(entries)} recent entries")
        await asyncio.sleep(5)

        # Health check every other cycle
        if cycle % 2 == 0:
            h = await client.health()
            if h:
                casey.log(f"Health check (cycle {cycle}): {h.get('status')}")
            await asyncio.sleep(3)

        # Maintenance every 5th cycle
        if cycle % 5 == 0:
            casey.log(f"Maintenance cycle {cycle}...")
            await client.run_consolidation(dry_run=True)
            await asyncio.sleep(5)
            await client.run_decay()
            await asyncio.sleep(5)

        # End session
        await active_agent.end_session()
        await asyncio.sleep(random.uniform(10, 20))

    # ── Shutdown ──
    stop_event.set()
    print("\n\nShutting down...\n")

    # Wait for background tasks
    sse_task.cancel()
    status_task.cancel()
    try:
        await asyncio.gather(sse_task, status_task, return_exceptions=True)
    except Exception:
        pass

    await client.close()

    # Final report
    elapsed = int(time.time() - start_time)
    print(f"\n\nSimulation completed in {elapsed // 60}m {elapsed % 60}s\n")
    print(stats.summary())
    print()


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════


def main():
    # Fix Windows console encoding + enable line buffering for background runs
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

    parser = argparse.ArgumentParser(description="Build Hub Simulation for Recall")
    parser.add_argument("--api", default=DEFAULT_API, help=f"Recall API base URL (default: {DEFAULT_API})")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION, help=f"Duration in seconds (default: {DEFAULT_DURATION})")
    args = parser.parse_args()

    print("=" * 56)
    print("  BUILD HUB SIMULATION -- RECALL STRESS TEST")
    print("=" * 56)
    print(f"  API:      {args.api}")
    print(f"  Duration: {args.duration // 60} minutes")
    print(f"  Domain:   {DOMAIN}")
    print(f"  Agents:   Alex, Sam, Jordan, Riley, Casey")
    print("=" * 56)
    print()

    asyncio.run(run_simulation(args.api, args.duration))


if __name__ == "__main__":
    main()
