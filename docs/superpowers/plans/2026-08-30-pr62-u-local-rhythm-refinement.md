# PR62-U Local Rhythm Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate the historical Route 10 Q timetable through a live bounded post-frontier refinement path while preserving every frozen production authority.

**Architecture:** A focused production module wraps one unchanged coordinator call, performs bounded directional canonicalization for V3-materiality sources, recombines and validates pairs, augments the unchanged Pareto frontier, and repeats only under strict rhythm progress. A repository script performs the single Route 6/10 certification replay and deterministic evidence render.

**Tech Stack:** Python 3.13, frozen dataclasses, pytest, Ruff, existing clean-boundary compiler and coordinator APIs.

**Spec:** `docs/superpowers/specs/2026-08-30-pr62-u-local-rhythm-refinement-design.md`

## Global Constraints

- Do not modify the coordinator, compiler, V1/V2/V3 selector, fleet validator, clean-boundary pilot, canonical XLSX, global budgets, Pareto vector, or terminal occupancy behavior.
- Boundary and transfer radii are exactly 3; the local compiler frontier limit is exactly 256.
- Call `search_route_service_plans_v1` exactly once per integrated route execution.
- Process every V3 phase-robust materiality source at most once and admit only strict lexicographic V3-rhythm descendants.
- Route 6 and Route 10 certification each permit one completed global replay and no automatic recovery replay.
- Use Q evidence only as a regression oracle; never load its candidate payload into production.

---

### Task 1: Rhythm-family and bounded-state primitives

**Files:**
- Create: `src/bus_schedule_engine/local_rhythm_refinement.py`
- Create: `tests/test_local_rhythm_refinement.py`

**Interfaces:**
- Produces: immutable `LocalRhythmFamilyV1`, `LocalRhythmRefinementPolicyV1`, family detection/representative/mapping helpers, bounded state generation, micro-boundary counting, and strict pair-rhythm comparison.

- [ ] Write failing tests for family contiguity, trip-count floor, weighted representative, slice-based mapping, invalid mapping, structural bounds, state authority preservation, directional filtering, and strict rhythm progress.
- [ ] Run `python -m pytest tests/test_local_rhythm_refinement.py -q` and confirm failure because the production module/API is absent.
- [ ] Implement only the primitives required by those tests with radius 3 and no PLAN-ID parsing.
- [ ] Rerun the unit test file until all primitive tests pass.

### Task 2: Local compile, recombination, Pareto augmentation, and closed loop

**Files:**
- Modify: `src/bus_schedule_engine/local_rhythm_refinement.py`
- Modify: `tests/test_local_rhythm_refinement.py`

**Interfaces:**
- Consumes: Task 1 primitives and existing coordinator/compiler/V3 APIs.
- Produces: `LocalRhythmRefinementStatisticsV1`, `LocalRhythmRefinementResultV1`, and `search_route_service_plans_with_local_rhythm_refinement_v1(*, context, seeds, coordinator_budget, refinement_policy)`.

- [ ] Add failing behavioral tests proving complete directional cross-products, existing pair evaluation and Pareto admission, compiler-cap blocker, descendant deduplication, one-time source processing, and same-rhythm termination.
- [ ] Confirm those tests fail for missing orchestration behavior.
- [ ] Implement local compile/protection/tail evaluation, pair recombination, frozen-rhythm filtering, Pareto augmentation, V3 reselection, immutable statistics, and the monotonic work loop.
- [ ] Run the full unit test file and relevant coordinator/V3 tests.

### Task 3: Real-route integration and deterministic evidence

**Files:**
- Create: `scripts/run_pr62_u_local_rhythm_search_integration.py`
- Create: `tests/test_pr62_u_local_rhythm_search_integration.py`
- Create: `docs/engine/evidence/PR62_U_LOCAL_RHYTHM_CANONICALIZATION_SEARCH_INTEGRATION.json`
- Create: `docs/engine/evidence/PR62_U_LOCAL_RHYTHM_CANONICALIZATION_SEARCH_INTEGRATION.md`

**Interfaces:**
- Consumes: Task 2 integrated API.
- Produces: one-replay-per-route certification, exact base-frontier locks, live-Q assertion, Route 6 control, deterministic evidence, and PR-body text.

- [ ] Write integration tests that first fail because the runner/evidence do not exist and that forbid Q payload injection.
- [ ] Implement the runner with explicit replay counters and in-memory result preservation.
- [ ] Run Route 10 exactly once with budget `24/512/4/24/512`, then Route 6 exactly once, stopping rather than replaying if either completed result is lost.
- [ ] Require exact PR62-I base frontiers, Route 10 Q generation/selection, Route 6 stability, zero compiler-cap pruning, and all requested guards.
- [ ] Render JSON and Markdown twice byte-identically and write the evidence.
- [ ] Run both new test files.

### Task 4: Focused regression and immutable verification

**Files:**
- Verify only the files listed by the PR62-U specification.

- [ ] Run all specified focused pytest files once after GREEN.
- [ ] Run Ruff check/format-check and `py_compile` on touched Python.
- [ ] Run `git diff --check` and verify deterministic evidence bytes/hashes.
- [ ] Recompute every immutable authority and XLSX hash, including exact V3 start/end equality.
- [ ] Review statistics and evidence against every readiness/guard requirement; fail closed on any gap.

### Task 5: Commit, push, and Draft PR update

**Files:**
- Stage exact approved paths only.

- [ ] Review `git status --short` and `git diff --check`.
- [ ] Stage each U path explicitly and commit as `Integrate local rhythm canonicalization refinement`.
- [ ] Push `codex/closed-loop-service-plan-coordinator-v1` without merging.
- [ ] Update Draft PR #62 body with the PR62-U section and top-level A-through-U status.
- [ ] Verify local HEAD, origin branch head, and PR head are identical; verify the PR remains Draft and report GitHub checks.
