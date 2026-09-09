# PR62-U6 V3 Anchor Conflict Evidence Review Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:systematic-debugging and superpowers:verification-before-completion. Execute this plan inline because it is a single forensic chain with shared evidence authority.

**Goal:** Reconstruct and independently explain the Route 10 `SSE_BEST != TE_BEST` conflict at the exact reviewed U6 head without changing any production policy or executing Route 6.

**Architecture:** A review-only Python script reads the already-committed U6 evidence and the hash-pinned saved Route 10 base fixture, reprojects saved U6 candidate history without running the global coordinator, and independently recomputes discrete and continuous demand-fit metrics from exact departures and frozen demand buckets. It emits only compact evidence and a decision document; full per-candidate and per-bucket working data stays in ignored scratch storage.

**Tech Stack:** Python 3.11+, repository `bus_schedule_engine` modules, JSON, pytest, Ruff, Git.

**Spec:** User-supplied PR62-U6 Route 10 evidence/root-cause review request dated 2026-09-09; canonical authority is `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json` at semantic SHA `46cd605e4ffb0a9aa00bb9376002b2001ada60760d460e1cbf38ba69aa549d99`.

## Global Constraints

- Base the isolated review branch on exact commit `185dbee3b86a7ec838723c4e9d50bc2e88bf373b`.
- Keep Route 6 global execution count exactly zero.
- Do not change V1, V2, or V3 selection policies, U6 generation/refinement, coordinator, fleet validation, Pareto logic, or final XLSX files.
- Do not rerun the Route 10 global coordinator or regenerate timetables.
- Treat the common-anchor invalidation as a hypothesis until every metric and gate is independently verified.
- Keep committed review JSON below 5 MiB, targeting below 1 MiB.
- Do not implement or select a replacement policy or timetable.

---

### Task 1: Establish immutable review authority and baseline

**Files:**
- Inspect: `src/bus_schedule_engine/contracts_v1/operational_selection_policy.py`
- Inspect: `src/bus_schedule_engine/contracts_v1/operational_selection_policy_v2.py`
- Inspect: `src/bus_schedule_engine/contracts_v1/operational_selection_policy_v3.py`
- Inspect: `docs/engine/evidence/PR62_{M,M1,N,O,R,S,T,U6}_*.{json,md}`

**Interfaces:**
- Consumes: reviewed U6 commit, canonical evidence, saved Route 10 fixture.
- Produces: recorded source hashes and verified metric definitions used by every later task.

- [ ] Verify branch, base SHA, worktree isolation, canonical evidence hashes, saved fixture hash, and clean baseline.
- [ ] Read the three selector implementations completely and trace SSE, TE, continuous exposure, hard feasibility, access, tail, protection, and fleet projections to their source definitions.
- [ ] Review PR62-M/M1/N/O/R/S/T evidence and record the candidate universes and exact historical claims.
- [ ] Run focused selector/U6 tests that cannot invoke Route 6 and record baseline results.

### Task 2: Build a fail-closed evidence-only analyzer

**Files:**
- Create: `scripts/run_pr62_u6_v3_anchor_conflict_review.py`

**Interfaces:**
- Consumes: canonical U6 JSON, hash-pinned Route 10 pickle, frozen U6 projection helpers, exact departures, demand buckets.
- Produces: a deterministic compact Python mapping containing hashes, candidate/gate summaries, independent bucket recomputations, ranks, lineage, batch transition, cap stability, materiality, classifications, and decision matrix.

- [ ] Add authority checks that reject the wrong Git/base/evidence semantic SHA or Route 10 fixture and monkeypatch the global coordinator to fail before any execution.
- [ ] Reconstruct the canonical 123 Pareto / 83 access-safe snapshots and independently recompute directional bucket counts, shares, residuals, SSE, TE, and continuous exposure from exact departures.
- [ ] Fail closed unless recomputed metrics reproduce V3 within numerical epsilon and both anchors pass every upstream gate.
- [ ] Compute directional/pair ranks, changed bucket/departure/boundary audit, Kendall concordance, top overlaps, materiality deltas, cap 16/32/64 identities, and first saved U6 source-batch transition.
- [ ] Keep exhaustive working rows in a temporary ignored directory only; retain only differing anchor buckets and compact rank summaries in committed evidence.

### Task 3: Add focused regression tests for the analyzer

**Files:**
- Create: `tests/test_pr62_u6_v3_anchor_conflict_review.py`

**Interfaces:**
- Consumes: pure functions from `scripts/run_pr62_u6_v3_anchor_conflict_review.py`.
- Produces: deterministic tests for independent norms, tie-safe ranks, boundary crossings, and fail-closed authority validation.

- [ ] Write tests with small synthetic schedules/demand buckets that prove SSE and TE can reverse ordering.
- [ ] Write tests for rank ties, compact differing-bucket selection, and boundary-crossing counts.
- [ ] Run the focused test file and confirm all assertions pass without loading or executing Route 6.

### Task 4: Generate compact evidence and decision document

**Files:**
- Create: `docs/engine/evidence/PR62_U6_V3_ANCHOR_CONFLICT_REVIEW.json`
- Create: `docs/engine/evidence/PR62_U6_V3_ANCHOR_CONFLICT_REVIEW.md`

**Interfaces:**
- Consumes: validated analyzer output.
- Produces: the requested exact conflict, root cause, history, stability, materiality, A/B/C/D policy comparison, one primary classification, and exactly one smallest next experiment.

- [ ] Render deterministic JSON with only materially differing bucket rows and confirm size below 5 MiB.
- [ ] Render the human-readable decision document with no selector recommendation disguised as an implementation.
- [ ] State selection-cap binding separately from anchor-conflict stability.
- [ ] State Route 6 global execution count as zero and include a single next policy experiment.

### Task 5: Verify, review, commit, and push

**Files:**
- Verify: all files created by Tasks 2-4 and this plan.

**Interfaces:**
- Consumes: completed review artifacts.
- Produces: clean pushed review head with reproducible verification evidence.

- [ ] Run Ruff on the review script/test, the focused test file, evidence regeneration into a temporary directory, deterministic byte comparison, JSON validation, hash checks, and Git diff checks proving no prohibited file changed.
- [ ] Use `superpowers:requesting-code-review` for an independent requirements and correctness review; resolve only evidence defects.
- [ ] Use `superpowers:verification-before-completion`, commit the reviewed artifacts, push `review/pr62-u6-v3-anchor-conflict`, and verify local/remote SHA equality and clean status.
