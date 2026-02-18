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
  durability: string | null;
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
  durability: string | null;
  initial_importance: number | null;
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

// Phase 15B: Health Dashboard types

export interface FeedbackDaily {
  date: string;
  positive: number;
  negative: number;
  total: number;
}

export interface FeedbackMetrics {
  positive_rate: number;
  total_positive: number;
  total_negative: number;
  daily: FeedbackDaily[];
}

export interface PopulationBalance {
  stores: number;
  deletes: number;
  decays: number;
  net_growth: number;
  action_breakdown: Record<string, number>;
}

export interface GraphCohesion {
  avg_edge_strength: number;
  edge_count: number;
}

export interface PinRatio {
  pinned: number;
  total: number;
  ratio: number;
  warning: boolean;
}

export interface ImportanceBand {
  range: string;
  count: number;
}

export interface SimilarityBucket {
  bucket: number;
  range_start: number;
  range_end: number;
  count: number;
}

export interface HealthDashboard {
  generated_at: string;
  feedback: FeedbackMetrics;
  population: PopulationBalance;
  graph: GraphCohesion;
  pins: PinRatio;
  importance_distribution: ImportanceBand[];
  feedback_similarity: SimilarityBucket[];
}

export interface Force {
  decay_pressure: number;
  retrieval_lift: number;
  feedback_signal: number;
  co_retrieval_gravity: number;
  pin_status: number;
  durability_shield: number;
}

export interface ImportanceEvent {
  timestamp: string;
  action: string;
  importance: number | null;
  details: Record<string, unknown>;
}

export interface ForceProfileResponse {
  memory_id: string;
  current_importance: number;
  forces: Force;
  importance_timeline: ImportanceEvent[];
}

export interface Conflict {
  type: string;
  severity: string;
  memory_id: string;
  description: string;
}

// Phase 15C: Document types

export interface DocumentEntry {
  id: string;
  filename: string;
  file_hash: string;
  file_type: string;
  domain: string;
  durability: string | null;
  pinned: boolean;
  memory_count: number;
  created_at: string;
  user_id: number | null;
  username: string | null;
}

export interface DocumentDetail extends DocumentEntry {
  child_memory_ids: string[];
}

export interface IngestResponse {
  document: DocumentEntry;
  memories_created: number;
  child_ids: string[];
}

// v2.7: Stale memory types

export interface InvalidationFlag {
  reason: string;
  commit_hash: string;
  changed_files?: string[];
  matched_values?: string[];
  flagged_at: string;
}

export interface StaleMemory {
  id: string;
  content: string;
  domain: string;
  durability: string | null;
  invalidation_flag: InvalidationFlag;
}

export interface StaleMemoriesResponse {
  stale_memories: StaleMemory[];
  total: number;
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
