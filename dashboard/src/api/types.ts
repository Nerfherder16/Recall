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
  turns_ingested: number;
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
