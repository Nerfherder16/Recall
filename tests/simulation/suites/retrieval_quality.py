"""
Retrieval Quality Suite — Precision, recall, MRR, graph expansion, and inhibition.
"""

import asyncio
import time

from tests.simulation.data.ground_truth import GROUND_TRUTH_MEMORIES
from tests.simulation.report import SuiteReport

from .base import BaseSuite

TOP_K = 10


class RetrievalQualitySuite(BaseSuite):
    name = "retrieval"

    async def run(self) -> SuiteReport:
        t0 = time.monotonic()
        passed = True

        try:
            # ── Setup: Store ground truth memories ──
            self.observe("Storing 20 ground-truth memories...")
            id_map: dict[int, str] = {}  # index -> memory_id

            for i, gt in enumerate(GROUND_TRUTH_MEMORIES):
                mid = await self._store(
                    content=gt["content"],
                    importance=gt["importance"],
                    memory_type=gt["memory_type"],
                    tags=[f"gt:{i}"],
                )
                if mid:
                    id_map[i] = mid
                await asyncio.sleep(0.5)

            self.observe(f"Stored {len(id_map)}/{len(GROUND_TRUTH_MEMORIES)} ground-truth memories")

            if len(id_map) < 15:
                self.error("Too few ground-truth memories stored")
                return self._make_report(False, time.monotonic() - t0)

            # Allow indexing to settle
            await asyncio.sleep(3)

            # ── Scenario A: Precision / Recall / MRR ──
            self.observe("Running precision/recall/MRR evaluation...")
            per_query_results = []
            total_reciprocal_rank = 0.0
            total_precision = 0.0
            total_recall = 0.0
            query_count = 0

            for i, gt in enumerate(GROUND_TRUTH_MEMORIES):
                if i not in id_map:
                    continue
                expected_id = id_map[i]

                for query in gt["positive_queries"]:
                    results = await self.client.search_query(
                        query,
                        limit=TOP_K,
                        tags=[self.run_tag],
                    )
                    await asyncio.sleep(2)  # Rate limit: 30/min

                    result_ids = [r["id"] for r in results]
                    found = expected_id in result_ids

                    precision = 1.0 / TOP_K if found else 0.0
                    recall = 1.0 if found else 0.0

                    # MRR: 1/rank if found
                    if found:
                        rank = result_ids.index(expected_id) + 1
                        reciprocal_rank = 1.0 / rank
                    else:
                        rank = -1
                        reciprocal_rank = 0.0

                    per_query_results.append(
                        {
                            "query": query,
                            "expected_index": i,
                            "found": found,
                            "rank": rank,
                            "precision": round(precision, 4),
                            "recall": round(recall, 4),
                            "reciprocal_rank": round(reciprocal_rank, 4),
                            "result_count": len(results),
                        }
                    )

                    total_precision += precision
                    total_recall += recall
                    total_reciprocal_rank += reciprocal_rank
                    query_count += 1

            if query_count > 0:
                avg_precision = total_precision / query_count
                avg_recall = total_recall / query_count
                mrr = total_reciprocal_rank / query_count
            else:
                avg_precision = avg_recall = mrr = 0.0

            self.metric(
                "precision_recall_mrr",
                {
                    "avg_precision_at_k": round(avg_precision, 4),
                    "avg_recall": round(avg_recall, 4),
                    "mrr": round(mrr, 4),
                    "total_queries": query_count,
                    "K": TOP_K,
                },
            )
            self.observe(
                f"P@{TOP_K}={avg_precision:.3f}, "
                f"R={avg_recall:.3f}, "
                f"MRR={mrr:.3f} over {query_count} queries"
            )

            if avg_recall < 0.3:
                self.error(f"Recall too low: {avg_recall:.3f} (expected > 0.3)")
                passed = False

            # ── Scenario B: Negative Precision ──
            self.observe("Running negative precision evaluation...")
            neg_correct = 0
            neg_total = 0

            for i, gt in enumerate(GROUND_TRUTH_MEMORIES):
                if i not in id_map:
                    continue
                wrong_id = id_map[i]

                for query in gt["negative_queries"]:
                    results = await self.client.search_query(
                        query,
                        limit=5,
                        tags=[self.run_tag],
                    )
                    await asyncio.sleep(2)

                    top_ids = [r["id"] for r in results[:5]]
                    if wrong_id not in top_ids:
                        neg_correct += 1
                    neg_total += 1

            neg_precision = neg_correct / neg_total if neg_total > 0 else 0.0
            self.metric("negative_precision", round(neg_precision, 4))
            self.observe(f"Negative precision: {neg_precision:.3f} ({neg_correct}/{neg_total})")

            # ── Scenario C: Graph Expansion ──
            self.observe("Running graph expansion test...")

            # Store 3 connected memories: A -> B -> C
            mid_a = await self._store(
                "Alpha protocol: initial handshake uses TLS 1.3 with certificate pinning.",
                tags=["chain-a"],
            )
            await asyncio.sleep(0.5)
            mid_b = await self._store(
                "Beta validation: after Alpha handshake, mutual auth verifies both endpoints.",
                tags=["chain-b"],
            )
            await asyncio.sleep(0.5)
            mid_c = await self._store(
                "Gamma completion: once Beta validation passes, the secure channel is established.",
                tags=["chain-c"],
            )
            await asyncio.sleep(0.5)

            if mid_a and mid_b and mid_c:
                # Create relationships: A -> B -> C
                await self.client.create_relationship(
                    mid_a,
                    mid_b,
                    "related_to",
                    strength=0.8,
                )
                await asyncio.sleep(0.5)
                await self.client.create_relationship(
                    mid_b,
                    mid_c,
                    "related_to",
                    strength=0.8,
                )
                await asyncio.sleep(3)

                # Search with expansion: should find C via 2-hop
                results_expanded = await self.client.search_query(
                    "Alpha protocol TLS handshake",
                    limit=10,
                    tags=[self.run_tag],
                    expand_relationships=True,
                )
                await asyncio.sleep(2)

                expanded_ids = [r["id"] for r in results_expanded]
                chain_found = mid_c in expanded_ids

                # Search without expansion: C should NOT appear
                results_flat = await self.client.search_query(
                    "Alpha protocol TLS handshake",
                    limit=10,
                    tags=[self.run_tag],
                    expand_relationships=False,
                )
                await asyncio.sleep(2)

                flat_ids = [r["id"] for r in results_flat]
                chain_isolated = mid_c not in flat_ids

                self.metric(
                    "graph_expansion",
                    {
                        "chain_traversal": chain_found,
                        "chain_isolation": chain_isolated,
                    },
                )
                self.observe(f"Graph expansion: found={chain_found}, isolated={chain_isolated}")

                if not chain_found:
                    self.observe("Warning: graph expansion didn't reach 2-hop neighbor")
            else:
                self.error("Could not store chain memories for graph test")

            # ── Scenario D: Contradiction Inhibition ──
            self.observe("Running contradiction inhibition test...")

            mid_pos = await self._store(
                "PostgreSQL is the best choice for our vector storage needs due to pgvector.",
                importance=0.7,
                tags=["contradiction-test"],
            )
            await asyncio.sleep(0.5)
            mid_neg = await self._store(
                "PostgreSQL is NOT suitable for vector storage; "
                "use a dedicated vector DB like Qdrant.",
                importance=0.7,
                tags=["contradiction-test"],
            )
            await asyncio.sleep(0.5)

            if mid_pos and mid_neg:
                # Create CONTRADICTS relationship
                await self.client.create_relationship(
                    mid_pos,
                    mid_neg,
                    "contradicts",
                    strength=0.9,
                    bidirectional=True,
                )
                await asyncio.sleep(3)

                # Search for their shared topic
                results = await self.client.search_query(
                    "PostgreSQL vector storage database choice",
                    limit=10,
                    tags=[self.run_tag],
                    expand_relationships=True,
                )
                await asyncio.sleep(2)

                # Check if one is scored lower due to inhibition
                scores = {}
                for r in results:
                    if r["id"] == mid_pos:
                        scores["positive"] = r["score"]
                    elif r["id"] == mid_neg:
                        scores["negative"] = r["score"]

                if "positive" in scores and "negative" in scores:
                    ratio = (
                        min(scores.values()) / max(scores.values())
                        if max(scores.values()) > 0
                        else 1.0
                    )
                    inhibition_detected = ratio < 0.95
                    self.metric(
                        "inhibition",
                        {
                            "detected": inhibition_detected,
                            "score_ratio": round(ratio, 4),
                            "scores": scores,
                        },
                    )
                    self.observe(f"Inhibition: ratio={ratio:.3f}, detected={inhibition_detected}")
                else:
                    self.observe("Warning: could not find both contradicting memories in results")
                    self.metric(
                        "inhibition",
                        {
                            "detected": False,
                            "note": "memories not found in results",
                        },
                    )
            else:
                self.error("Could not store contradiction memories")

            # ── Scenario E: Parameter Variation ──
            self.observe("Running parameter variation test...")
            test_query = "How to prevent SQL injection in database queries"
            param_results = {}

            for limit in [5, 20]:
                for expand in [True, False]:
                    results = await self.client.search_query(
                        test_query,
                        limit=limit,
                        tags=[self.run_tag],
                        expand_relationships=expand,
                    )
                    await asyncio.sleep(2)

                    key = f"limit={limit}_expand={expand}"
                    if 5 in id_map:
                        found = id_map[5] in [r["id"] for r in results]
                    else:
                        found = False
                    param_results[key] = {
                        "result_count": len(results),
                        "target_found": found,
                    }

            self.metric("parameter_variation", param_results)
            self.observe(f"Parameter variation: {len(param_results)} combos tested")

        except Exception as e:
            self.error(f"Retrieval suite exception: {e}")
            passed = False

        return self._make_report(passed, time.monotonic() - t0)
