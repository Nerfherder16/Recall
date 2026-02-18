/**
 * Test pairing for StaleAuditSection.tsx.
 * Dashboard has no test runner — this is a compile-time type check.
 */

import type { StaleMemory } from "../../api/types";

// Verify the component's expected data shape
const _sample: StaleMemory = {
  id: "mem-flagged-1",
  content: "Ollama runs on 192.168.50.62",
  domain: "infrastructure",
  durability: "permanent",
  invalidation_flag: {
    reason: "Values ['192.168.50.62'] found in commit abc1234",
    commit_hash: "abc1234def5678",
    flagged_at: "2026-02-18T20:00:00Z",
  },
};

void _sample;
console.log("StaleAuditSection.test.ts: types valid");
