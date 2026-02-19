/**
 * Test pairing for api/types.ts.
 * Types are compile-time only — this verifies the StaleMemory types are importable.
 */

import type {
  StaleMemory,
  InvalidationFlag,
  StaleMemoriesResponse,
} from "../types";

// Type-level assertions (compile-time only)
const _flag: InvalidationFlag = {
  reason: "test",
  commit_hash: "abc1234",
  flagged_at: "2026-02-18T00:00:00Z",
};

const _stale: StaleMemory = {
  id: "mem-1",
  content: "test content",
  domain: "infrastructure",
  durability: "permanent",
  invalidation_flag: _flag,
};

const _response: StaleMemoriesResponse = {
  stale_memories: [_stale],
  total: 1,
};

// Suppress unused variable warnings
void _flag;
void _stale;
void _response;

console.log("types.test.ts: StaleMemory types are valid");
