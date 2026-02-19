"""
Adaptive Memory Suite — Pinning, Anti-Patterns, and Feedback Loop.

Tests adaptive memory features end-to-end:
A. Pinning: pinned memories survive decay, unpinned decay normally
B. Anti-Patterns: CRUD, retrieval injection, domain filtering
C. Feedback Loop: useful/not-useful importance adjustments
"""

import asyncio
import time

from tests.simulation.report import SuiteReport

from .base import BaseSuite


class AdaptiveSuite(BaseSuite):
    name = "adaptive"

    async def run(self) -> SuiteReport:
        t0 = time.monotonic()
        passed = True

        try:
            # ── Scenario A: Memory Pinning ──
            self.observe("=== Scenario A: Memory Pinning ===")

            # Store a high-importance memory and pin it
            pinned_id = await self._store(
                content="Architecture decision: use event sourcing for the audit log",
                importance=0.8,
                tags=["pinning-test"],
            )
            # Store a control memory (not pinned)
            control_id = await self._store(
                content="Ran npm install on the CI server yesterday afternoon",
                importance=0.5,
                tags=["pinning-test"],
            )
            await asyncio.sleep(1)

            if not pinned_id or not control_id:
                self.error("Failed to store pinning test memories")
                return self._make_report(False, time.monotonic() - t0)

            # Pin the first memory
            pin_result = await self.client.pin_memory(pinned_id)
            if not pin_result:
                self.error("Pin request failed")
                passed = False
            else:
                self.observe(
                    f"Pinned memory {pinned_id[:8]}... → pinned={pin_result.get('pinned')}"
                )

            # Verify pin via GET
            mem = await self.client.get_memory(pinned_id)
            if mem and mem.get("pinned") is True:
                self.observe("GET confirms pinned=true")
            else:
                self.error(f"GET did not confirm pinned=true: {mem}")
                passed = False

            # Get baseline importances
            pinned_before = mem.get("importance", 0) if mem else 0
            control_mem = await self.client.get_memory(control_id)
            control_before = control_mem.get("importance", 0) if control_mem else 0
            self.observe(
                f"Before decay — pinned: {pinned_before:.3f}, control: {control_before:.3f}"
            )

            # Run decay (3 steps x 48h = 144h simulated)
            for step in range(3):
                r = await self.client.decay(simulate_hours=48)
                if r is None:
                    self.error(f"Decay step {step + 1} failed")
                await asyncio.sleep(6)  # Rate limit

            # Check importances after decay
            pinned_after_mem = await self.client.get_memory(pinned_id)
            control_after_mem = await self.client.get_memory(control_id)

            pinned_after = pinned_after_mem.get("importance", 0) if pinned_after_mem else 0
            control_after = control_after_mem.get("importance", 0) if control_after_mem else 0

            self.observe(f"After decay — pinned: {pinned_after:.3f}, control: {control_after:.3f}")

            # Pinned should be unchanged (or very close)
            pinned_drift = abs(pinned_after - pinned_before)
            if pinned_drift > 0.05:
                self.error(
                    f"Pinned memory decayed: {pinned_before:.3f} → "
                    f"{pinned_after:.3f} (drift={pinned_drift:.3f})"
                )
                passed = False
            else:
                self.observe(f"Pinned memory held stable (drift={pinned_drift:.3f})")

            # Control should have decayed
            if control_after < control_before:
                self.observe(
                    f"Control decayed normally: {control_before:.3f} → {control_after:.3f}"
                )
            else:
                self.observe(
                    f"Warning: control didn't decay ({control_before:.3f} → {control_after:.3f})"
                )

            self.metric(
                "pinning",
                {
                    "pinned_before": round(pinned_before, 4),
                    "pinned_after": round(pinned_after, 4),
                    "pinned_drift": round(pinned_drift, 4),
                    "control_before": round(control_before, 4),
                    "control_after": round(control_after, 4),
                    "pinned_survived": pinned_drift <= 0.05,
                    "control_decayed": control_after < control_before,
                },
            )

            # Test unpin
            unpin_result = await self.client.unpin_memory(pinned_id)
            if unpin_result and unpin_result.get("pinned") is False:
                self.observe("Unpin successful")
            else:
                self.error(f"Unpin failed: {unpin_result}")
                passed = False

            await asyncio.sleep(2)

            # ── Scenario B: Anti-Patterns ──
            self.observe("\n=== Scenario B: Anti-Patterns ===")

            # Create anti-patterns
            ap1 = await self.client.create_anti_pattern(
                pattern="Using pickle to deserialize untrusted data",
                warning="Pickle deserialization of untrusted data allows arbitrary code execution",
                alternative="Use JSON or MessagePack for untrusted data serialization",
                severity="error",
                domain=self.domain,
                tags=["security"],
            )
            await asyncio.sleep(0.5)

            ap2 = await self.client.create_anti_pattern(
                pattern="Concatenating user input into SQL queries",
                warning="String concatenation in SQL queries enables SQL injection attacks",
                alternative="Use parameterized queries or ORM methods",
                severity="error",
                domain=self.domain,
                tags=["security"],
            )
            await asyncio.sleep(0.5)

            ap3 = await self.client.create_anti_pattern(
                pattern="Catching bare exceptions with except: pass",
                warning="Bare except catches SystemExit/KeyboardInterrupt and hides real errors",
                alternative="Catch specific exceptions: except ValueError as e:",
                severity="warning",
                domain="python",
                tags=["code-quality"],
            )
            await asyncio.sleep(1)

            created_count = sum(1 for ap in [ap1, ap2, ap3] if ap and ap.get("id"))
            self.observe(f"Created {created_count}/3 anti-patterns")

            if created_count < 2:
                self.error("Too few anti-patterns created")
                passed = False

            # List all anti-patterns
            all_aps = await self.client.list_anti_patterns()
            self.observe(f"Listed {len(all_aps)} total anti-patterns")

            # List with domain filter
            domain_aps = await self.client.list_anti_patterns(domain=self.domain)
            self.observe(f"Listed {len(domain_aps)} anti-patterns for domain={self.domain}")

            # Verify our tagged ones appear
            our_ap_ids = [ap["id"] for ap in [ap1, ap2, ap3] if ap and ap.get("id")]
            found_in_list = sum(1 for ap in all_aps if ap.get("id") in our_ap_ids)

            self.metric(
                "anti_patterns_crud",
                {
                    "created": created_count,
                    "total_listed": len(all_aps),
                    "domain_filtered": len(domain_aps),
                    "found_in_list": found_in_list,
                },
            )

            # Test retrieval integration — search for content matching an anti-pattern
            if ap1 and ap1.get("id"):
                await asyncio.sleep(2)
                browse_results = await self.client.search_browse(
                    "pickle deserialize untrusted data security risk",
                    limit=10,
                    tags=[self.run_tag],
                )
                await asyncio.sleep(2)

                # Check if any result mentions the anti-pattern warning
                warning_found = any(
                    "WARNING" in (r.get("summary", "") or r.get("content", ""))
                    or r.get("metadata", {}).get("is_anti_pattern")
                    for r in browse_results
                )
                self.observe(
                    f"Anti-pattern in browse results: "
                    f"{warning_found} ({len(browse_results)} results)"
                )
                self.metric(
                    "anti_pattern_retrieval",
                    {
                        "browse_results": len(browse_results),
                        "warning_injected": warning_found,
                    },
                )

            # Delete one anti-pattern
            if ap3 and ap3.get("id"):
                del_result = await self.client.delete_anti_pattern(ap3["id"])
                if del_result:
                    self.observe(f"Deleted anti-pattern {ap3['id'][:8]}...")
                else:
                    self.error("Failed to delete anti-pattern")

            # Clean up remaining anti-patterns
            for ap in [ap1, ap2]:
                if ap and ap.get("id"):
                    await self.client.delete_anti_pattern(ap["id"])
                    await asyncio.sleep(0.3)

            await asyncio.sleep(2)

            # ── Scenario C: Feedback Loop ──
            self.observe("\n=== Scenario C: Feedback Loop ===")

            # Store memories for feedback testing
            fb_useful = await self._store(
                content=(
                    "FastAPI uses Pydantic models for automatic "
                    "request validation and serialization"
                ),
                importance=0.5,
                tags=["feedback-test"],
            )
            fb_notuseful = await self._store(
                content=(
                    "Recipe for chocolate cake: mix flour, sugar, cocoa powder, eggs, and butter"
                ),
                importance=0.5,
                tags=["feedback-test"],
            )
            await asyncio.sleep(2)

            if not fb_useful or not fb_notuseful:
                self.error("Failed to store feedback test memories")
                return self._make_report(passed, time.monotonic() - t0)

            # Submit "useful" feedback — assistant text highly related to the memory
            useful_result = await self.client.submit_feedback(
                injected_ids=[fb_useful],
                assistant_text=(
                    "I used FastAPI with Pydantic models to validate the request body. "
                    "The Pydantic BaseModel provides automatic serialization and validation "
                    "for all incoming data, which is exactly what we need for this endpoint. "
                    "FastAPI integrates with Pydantic to generate OpenAPI schemas automatically."
                ),
            )
            await asyncio.sleep(1)

            if useful_result:
                self.observe(
                    f"Useful feedback: processed={useful_result.get('processed')}, "
                    f"useful={useful_result.get('useful')}, "
                    f"not_useful={useful_result.get('not_useful')}"
                )
            else:
                self.error("Useful feedback request failed")
                passed = False

            # Submit "not useful" feedback — completely unrelated assistant text
            notuseful_result = await self.client.submit_feedback(
                injected_ids=[fb_notuseful],
                assistant_text=(
                    "The quantum mechanics of superconducting circuits involves Cooper pairs "
                    "tunneling through Josephson junctions. The critical temperature depends on "
                    "the material's electron-phonon coupling constant and the density of states "
                    "at the Fermi level. BCS theory provides the theoretical framework."
                ),
            )
            await asyncio.sleep(1)

            if notuseful_result:
                self.observe(
                    f"Not-useful feedback: processed={notuseful_result.get('processed')}, "
                    f"useful={notuseful_result.get('useful')}, "
                    f"not_useful={notuseful_result.get('not_useful')}"
                )
            else:
                self.error("Not-useful feedback request failed")
                passed = False

            # Check importance changes
            useful_after = await self.client.get_memory(fb_useful)
            notuseful_after = await self.client.get_memory(fb_notuseful)

            useful_imp = useful_after.get("importance", 0) if useful_after else 0
            notuseful_imp = notuseful_after.get("importance", 0) if notuseful_after else 0

            self.observe(
                f"After feedback — useful: {useful_imp:.3f} (was 0.5), "
                f"not_useful: {notuseful_imp:.3f} (was 0.5)"
            )

            # Useful feedback should have increased importance (or at least maintained)
            useful_direction = (
                "up" if useful_imp > 0.5 else ("same" if useful_imp == 0.5 else "down")
            )
            notuseful_direction = (
                "down" if notuseful_imp < 0.5 else ("same" if notuseful_imp == 0.5 else "up")
            )

            self.metric(
                "feedback",
                {
                    "useful_importance_after": round(useful_imp, 4),
                    "useful_direction": useful_direction,
                    "notuseful_importance_after": round(notuseful_imp, 4),
                    "notuseful_direction": notuseful_direction,
                    "useful_response": useful_result,
                    "notuseful_response": notuseful_result,
                },
            )

            if useful_result and useful_result.get("useful", 0) > 0:
                self.observe("Feedback correctly identified useful memory")
            elif useful_result and useful_result.get("not_useful", 0) > 0:
                self.observe(
                    "Warning: useful memory classified as not_useful "
                    "(cosine threshold may be tight)"
                )

            if notuseful_result and notuseful_result.get("not_useful", 0) > 0:
                self.observe("Feedback correctly identified not-useful memory")
            elif notuseful_result and notuseful_result.get("useful", 0) > 0:
                self.observe("Warning: not-useful memory classified as useful (unexpected)")

            # Batch feedback test
            self.observe("Testing batch feedback...")
            batch_ids = [fb_useful, fb_notuseful]
            batch_result = await self.client.submit_feedback(
                injected_ids=batch_ids,
                assistant_text=(
                    "I set up the FastAPI endpoint with Pydantic validation. "
                    "The request body is automatically validated against the model schema. "
                    "I also baked a chocolate cake for the team celebration after the deploy."
                ),
            )

            if batch_result:
                self.observe(
                    f"Batch feedback: processed={batch_result.get('processed')}, "
                    f"useful={batch_result.get('useful')}, "
                    f"not_useful={batch_result.get('not_useful')}"
                )
                if batch_result.get("processed", 0) == 2:
                    self.observe("Batch processed all 2 memories")
                else:
                    self.observe(
                        f"Warning: expected 2 processed, got {batch_result.get('processed')}"
                    )
            else:
                self.error("Batch feedback request failed")

            # Test feedback for nonexistent memory
            ghost_result = await self.client.submit_feedback(
                injected_ids=["00000000-0000-0000-0000-000000000000"],
                assistant_text=(
                    "This is a long enough assistant text to meet the minimum length requirement "
                    "for the feedback endpoint validation and test the not_found counter."
                ),
            )
            if ghost_result and ghost_result.get("not_found", 0) == 1:
                self.observe("Nonexistent memory correctly counted as not_found")
            else:
                self.observe(f"Warning: ghost feedback response unexpected: {ghost_result}")

            self.metric(
                "feedback_batch",
                {
                    "batch_response": batch_result,
                    "ghost_response": ghost_result,
                },
            )

        except Exception as e:
            self.error(f"Phase 14 suite exception: {e}")
            passed = False

        return self._make_report(passed, time.monotonic() - t0)
