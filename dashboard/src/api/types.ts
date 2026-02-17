export interface HealthCheck {
  status: "healthy" | "degraded";
  timestamp: string;
  checks: Record<string, string>;
}

export interface Stats {
  memories: { total: number; graph_nodes: number; relationships: number };
  sessions: { active: number };
  timestamp: string;
}

export interface DomainStat {
  domain: string;
  count: number;
  avg_importance: number;
}

export interface BrowseResult {
  id: string;
  summary: string;
  memory_type: string;
  domain: string;
  similarity: number;
  importance: number;
  created_at: string;
  tags: string[];
  stored_by: string | null;
  pinned: boolean;
  access_count: number;
}

export interface MemoryDetail {
  id: string;
  content: string;
  memory_type: string;
  source: string;
  domain: string;
  tags: string[];
  importance: number;
  stability: number;
  confidence: number;
  access_count: number;
  created_at: string;
  last_accessed: string;
  stored_by: string | null;
  pinned: boolean;
}

export interface AntiPattern {
  id: string;
  pattern: string;
  warning: string;
  alternative: string | null;
  severity: string;
  domain: string;
  tags: string[];
  times_triggered: number;
  created_at: string;
}

export interface UserInfo {
  id: number;
  username: string;
  display_name: string | null;
  is_admin: boolean;
  created_at: string;
  last_active_at: string | null;
}

export interface CreateUserResponse extends UserInfo {
  api_key: string;
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  action: string;
  memory_id: string;
  actor: string;
  session_id: string | null;
  details: Record<string, unknown>;
}

export interface SessionEntry {
  session_id: string;
  started_at: string;
  ended_at: string | null;
  current_task: string | null;
  memories_created: number;
  signals_detected: number;
  turns_count: number;
}

export interface SSEHealth {
  memory_count?: number;
  fact_count?: number;
  graph_nodes?: number;
  relationships?: number;
  active_sessions?: number;
  audit_count?: number;
  qdrant?: string;
  neo4j?: string;
  redis?: string;
  postgres?: string;
}

// Phase 10 additions

export interface MemoryPreview {
  id: string;
  summary: string;
  memory_type: string;
  domain: string;
  importance: number;
  created_at: string;
  tags: string[];
}

export interface Turn {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
}

export interface WorkingMemory {
  session_id: string;
  current_task: string | null;
  active_context: string[];
  turns: Turn[];
}
