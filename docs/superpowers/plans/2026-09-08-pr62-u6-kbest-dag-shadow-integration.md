# PR62-U6 K-Best DAG Shadow Production Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean-port the validated U5 exact top-256 layered-DAG compiler into an explicit, non-authoritative production shadow path, then certify Route 10 and the Route 6 control without changing legacy production behavior.

**Architecture:** A focused versioned DAG module converts one local-family state set into an exact compiler-quality top-256 frontier. A separate completed-result shadow orchestrator applies structural/protection/tail eligibility before aggregate deterministic diversity, evaluates exact-fleet pairs through unchanged Pareto and V3 authorities, and runs independent 16/32/64 sensitivity worklists with semantic-only caching.

**Tech Stack:** Python 3.11+, immutable slotted dataclasses, `Fraction` and integer tuple ordering, existing PR62 compiler/protection/fleet/Pareto/V3 authorities, pytest, Ruff, Git worktrees; no U6 OR-Tools or CP-SAT import/call.

**Spec:** `docs/superpowers/specs/2026-09-08-pr62-u6-kbest-dag-shadow-integration-design.md`

## Global Constraints

- Work only in `E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u6` on `feat/pr62-u6-kbest-dag-shadow-integration` based on `59b892d3b367182b20734ad4e4405e264ba14024`.
- Treat U5 design `fc779e61186f38dc40066668ea20d2437687a6ac`, implementation `0b51d07735a767eb1c7cba2fad899f007a6543cc`, and evidence `f689111357b2cf465e1d96e093a5ad9e0c3f61b3` as read-only authorities; do not cherry-pick their ancestry.
- Finish `docs/engine/evidence/PR62_U6_KBEST_PORT_AUDIT.md` before creating either production Python module.
- Do not modify `clean_boundary_compiler.py`, `clean_compile_frontier.py`, demand detection, global coordinator, fleet solver, Pareto updater, V3 selector, Streamlit defaults, or exported production timetables.
- Do not add an OR-Tools dependency and do not import/call OR-Tools, CP-SAT, or any `experiments` package from production U6 code.
- Keep the DAG backend explicit shadow-only; no existing entry point may import or invoke it.
- Freeze raw DAG limit `256`, boundary-step radius `3`, trip-transfer radius `3`, and one-external-side-at-a-time local generation.
- Apply structural, endpoint/trip-total, translated protection, actual-service, and tail eligibility before strict directional progression and technical diversity.
- Apply diversity once to the actual aggregate eligible direction pool; do not assume the aggregate is at most 256 and do not insert a pre-diversity aggregate cap.
- Use technical shadow limits `16`, `32`, and `64` in complete independent runs from the same completed global base. Reuse only content-addressed raw/eligible results for identical semantic source/family keys.
- Use unchanged exact fleet, strict rhythm tuple, 10-D Pareto, and V3. Normalize the cap-32/cap-64 final-frontier union with `update_operating_pair_pareto_v1(..., limit=None)` before union V3 adjudication.
- Route 10 global calls remain `0`; load only the preserved 70,577-byte `route_10_complete_base.pickle` whose SHA-256 is `d2ba609ffd8fa4450e0a0662a0c9255dcdf1d8d2b759e63a8de6cf44fbfb114b`.
- Route 6 consumes exactly one global execution with `CoordinatorSearchBudgetV1(24, 512, 4, 24, 512)` and never reruns it.
- Historical Q `12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5` is `HISTORICAL_REFERENCE_ONLY` and may be observed only after canonical outputs freeze.
- Keep `DAG shadow backend authoritative = false`, `legacy backend removed = false`, `production default changed = false`, `READY_FOR_FINAL_PILOT_USE = false`, and `READY_FOR_PR62_COMPLETION_REVIEW = false` even on success.
- Use isolated pytest base-temp directories. Compare broad U6 failures against a fresh 59b baseline run so no new failure is hidden by CRLF, private-workbook, route-corpus, or Kaleido exclusions.
- Do not merge or update PR #62.

## File Map

- Create `docs/engine/evidence/PR62_U6_KBEST_PORT_AUDIT.md`: exhaustive 59b-to-U5 hunk classification and dependency decisions.
- Create `src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py`: versioned graph contracts, domain construction, exact per-node K retention, terminal merge, compilation decoding, hashes, and telemetry.
- Create `src/bus_schedule_engine/kbest_shadow_refinement.py`: endpoint preflight, eligibility, aggregate diversity, pair/worklist orchestration, semantic caching, cap sensitivity, and versioned shadow result contracts.
- Create `tests/test_kbest_dag_frontier.py`: exact graph, ordering, input, limit, determinism, and no-OR-Tools tests.
- Create `tests/test_kbest_shadow_refinement.py`: eligibility-before-diversity, aggregate, pair, worklist, sensitivity, and authority-preservation tests.
- Create `tests/fixtures/pr62_u6/u5_frozen_family.json`: focused U5 49-state input/endpoint fixture and expected parity authorities.
- Create `scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py`: explicit parity, Route 10, Route 6 one-shot, replay, sensitivity, and evidence-rendering CLI.
- Create `tests/test_pr62_u6_kbest_dag_shadow_integration.py`: saved-result, runner, gate, evidence, determinism, and classification tests.
- Create `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json`: canonical machine evidence.
- Create `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.md`: deterministic human review evidence.
- Leave all scratch pickles, run payloads, ledgers, and timing captures under an explicit untracked `E:/Project/Biểu đồ giờ/pr62-u6-runs/` directory.

---

### Task 1: Complete the U5 Production Port Audit

**Files:**

- Create: `docs/engine/evidence/PR62_U6_KBEST_PORT_AUDIT.md`
- Read: `experiments/pr62_u5_kbest_dag_frontier/*.py` at `0b51d07735a767eb1c7cba2fad899f007a6543cc`
- Read: U2/U3 dependencies referenced by U5 at `0b51d07735a767eb1c7cba2fad899f007a6543cc`
- Read: `src/bus_schedule_engine/local_rhythm_refinement.py` at `59b892d3` and `0b51d077`
- Read: `src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py` at `59b892d3` and `0b51d077`

**Interfaces:**

- Consumes: exact Git diff `59b892d3..0b51d077` and the A/B/C/D definitions in the approved spec.
- Produces: a table with one row for every diff hunk, stable hunk ID, path, hunk header, classification, dependency, port decision, and production equivalent.

- [ ] **Step 1: Inventory every changed path and zero-context diff hunk**

Run:

```powershell
git diff --name-status 59b892d3b367182b20734ad4e4405e264ba14024 0b51d07735a767eb1c7cba2fad899f007a6543cc
git diff --unified=0 59b892d3b367182b20734ad4e4405e264ba14024 0b51d07735a767eb1c7cba2fad899f007a6543cc -- experiments/pr62_u5_kbest_dag_frontier experiments/pr62_u2_cpsat_local_realization/solver.py experiments/pr62_u3_cpsat_frontier_extraction/shell.py src/bus_schedule_engine/local_rhythm_refinement.py src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py
```

Record all 214 changed paths by category and enumerate every `@@` hunk. New evidence/artifact files may share one file-level C decision only when the file is a single add hunk; mixed-code files require one row per hunk.

- [ ] **Step 2: Write the audit with frozen classification rules**

Use this exact table schema:

```markdown
| Hunk | Path | Git hunk | Class | Dependency | U6 decision |
|---|---|---|---|---|---|
| H001 | experiments/pr62_u5_kbest_dag_frontier/kbest.py | @@ ... @@ | A. K_BEST_DAG_CORE | U2 Domain/Solution and U3 canonical record are D | Re-express with U6 dataclasses and existing compiler builders; no experiment import |
```

Classify U5 partial-path scoring, deterministic merge, per-node K retention, terminal merge, graph compatibility, reachability trim, and decoding behavior as A. Classify subprocess/watchdog/write-once/report/posthoc-Q code and CP-SAT objects as B. Classify tests, fixtures, manifests, and evidence renderers as C. Classify imports or behavior relying on post-59b checkpoint hooks, endpoint preflight, local continuation, or U0 selector optimization as D. Record the endpoint preflight as the sole narrow D behavior re-expressed in U6; reject checkpoint/recovery and U0 optimization.

- [ ] **Step 3: Verify the audit has no missing or multiply classified hunk**

Run a temporary Python audit check that parses `git diff --unified=0`, forms keys `(path, hunk_header)`, parses the Markdown table, and asserts set equality plus one row per key. Also assert every row contains exactly one of the four full classification strings and every A-with-D row names a production equivalent.

Expected: `PORT_AUDIT_HUNKS_COMPLETE` with zero unclassified and zero duplicate hunks.

- [ ] **Step 4: Verify no production file changed during audit**

Run:

```powershell
git diff --name-only 4a3893765f97e8b31ed5e5b0373d6e0ae21462f2
git diff --check
```

Expected: only `docs/engine/evidence/PR62_U6_KBEST_PORT_AUDIT.md` is new.

- [ ] **Step 5: Commit the audit**

```powershell
git add -- docs/engine/evidence/PR62_U6_KBEST_PORT_AUDIT.md
git commit -m "Audit U5 k-best DAG production port"
```

### Task 2: Freeze U5 Authority and Write the RED Exact-DAG Contract

**Files:**

- Create: `tests/fixtures/pr62_u6/u5_frozen_family.json`
- Create: `tests/test_kbest_dag_frontier.py`

**Interfaces:**

- Consumes: U5 worktree `E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u5`, preserved source-object root `E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u`, `ServicePlanStateV1`, and `OperationalEndpointAuthorityV1`.
- Produces: a focused production-test fixture containing 49 ServicePlans, endpoint authority, manifest locks, and expected U5 top-1/tier/raw authorities; a failing test contract for the not-yet-created U6 module.

- [ ] **Step 1: Generate and inspect the focused fixture from committed U5 evidence**

First verify the evidence ancestry:

```powershell
git -C 'E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u5' rev-parse HEAD
git -C 'E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u5' merge-base --is-ancestor 0b51d07735a767eb1c7cba2fad899f007a6543cc HEAD
```

Expected: HEAD is `f689111357b2cf465e1d96e093a5ad9e0c3f61b3` or a descendant, and the ancestry command exits `0`.

Run this one-purpose extraction from the U5 worktree; it reads the preserved object authority and emits only reconstructable input data plus frozen expected values:

```powershell
Push-Location 'E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u5'
$env:PYTHONPATH='src;.'
@'
from dataclasses import asdict
import json
from pathlib import Path

from experiments.pr62_u3_cpsat_frontier_extraction.inputs import load_family

manifest, states, endpoint, _, _ = load_family(
    Path(r"E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u")
)
expected_family = "465c0800be66ce991af017ecea6dc87cdd4db7342d8ac9adb30ba1b5678fa905"
assert manifest["family_manifest_sha256"] == expected_family
payload = {
    "profile": "pr62_u6_u5_frozen_family_v1",
    "family_manifest_sha256": expected_family,
    "state_fingerprints": manifest["state_fingerprints"],
    "states": [asdict(state) for state in states],
    "endpoint_authority": asdict(endpoint),
    "expected": {
        "top1_fingerprint": "8e06dbcafc0194e5d338bc96b28569825bff30a79f96eaec8b5eda3c778ca7f6",
        "top_objective": [8214, 7, 74],
        "first_distinct_objective_tiers": [
            [8214, 7, 74],
            [9264, 7, 51],
            [10734, 7, 58],
        ],
        "raw_top256_sha256": "71092c883923e6d5460980a8c528f263a275255986e887bb03c3c1ef16c17601",
    },
}
target = Path(
    r"E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u6/tests/fixtures/pr62_u6/u5_frozen_family.json"
)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(
    json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
    encoding="utf-8",
    newline="\n",
)
'@ | python -
Pop-Location
```

Inspect that the JSON has exactly 49 states and contains no pickle paths, checkpoint objects, context/source pair, U2/U3/U4 artifact bodies, timings, or experiment class names.

- [ ] **Step 2: Write RED input, graph, K-best, parity, and dependency tests**

Import the wished-for production API. Add tests for empty input; bool/non-integer/out-of-range limits; route, direction, endpoint, and trip-total mismatches; exact caller-order canonicalization; and duplicate fingerprint rejection:

```python
def test_caller_state_order_is_canonicalized_and_duplicate_fingerprints_rejected():
    forward = compile_service_plan_family_kbest_v1(
        states=(state_b, state_a), endpoint_authority=authority, raw_limit=2
    )
    reverse = compile_service_plan_family_kbest_v1(
        states=(state_a, state_b), endpoint_authority=authority, raw_limit=2
    )
    assert forward.ordered_fingerprints == reverse.ordered_fingerprints
    with pytest.raises(ValueError, match="duplicate ServicePlan fingerprint"):
        compile_service_plan_family_kbest_v1(
            states=(state_a, state_a), endpoint_authority=authority
        )
```

Use `_PhaseCandidate` fixtures to assert exact one-layer ordering, left-owned and right-owned two-layer edges, equal-headway merging, illegal-boundary exclusion, source/sink counts, and forward/backward reachability trim. Add endpoint preflight cases for `fixed_first_departure < first.end` and `fixed_last_departure < final.end`; equality with either final boundary is invalid.

Use a local exhaustive oracle that materializes every legal small-DAG path and sorts by:

```python
(
    exact_scaled_quantization,
    actual_service_regime_count,
    phase_imbalance,
    headway_vector,
    departure_vector,
)
```

Cover hand-checked top-1/top-2, 40 fixed-seed random DAGs, cross-state terminal merge, exact-departure deduplication, canonical ties, fractional scale, natural exhaustion, node truncation, raw default 256, and byte-identical repeated semantic payloads.

For `test_u5_frozen_family_has_exact_production_port_parity`, reconstruct nested `ServiceRegimeDecisionV1`, `ServicePlanStateV1`, and `OperationalEndpointAuthorityV1` values from the JSON. Call `compile_service_plan_family_kbest_v1(..., raw_limit=256)`. Hash the 256 U5-compatible records with the exact U5 canonical form—`json.dumps(..., indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n"`—and assert count, top fingerprint/objective, first three distinct integer objective tiers, and raw SHA-256.

Add an AST test rejecting production imports rooted at `experiments` or `ortools`, and a child-process import test that sets `sys.modules["ortools"] = None` before importing the U6 module.

- [ ] **Step 3: Run the complete test contract and record the intended RED**

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_dag_frontier.py -vv
```

Expected: collection fails only because `bus_schedule_engine.contracts_v1.kbest_dag_frontier` does not exist. Fix test-data or fixture-generation defects now; do not create the production module until this is the observed failure.

### Task 3: Implement the Exact Versioned K-Best DAG Core and Pass U5 Parity

**Files:**

- Create: `src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py`
- Modify: `tests/test_kbest_dag_frontier.py` only to correct a demonstrated test defect, never to relax frozen authority.

**Interfaces:**

- Consumes: the RED contract from Task 2 and read-only phase/decode/validation symbols from unchanged clean compiler modules.
- Produces: `KBestDagCandidateV1`, `KBestDagGraphStatisticsV1`, `KBestDagTelemetryV1`, `KBestDagFrontierV1`, `service_plan_matches_endpoint_contract_v1`, `kbest_dag_candidate_payload_v1`, and `compile_service_plan_family_kbest_v1` with the approved signatures.

- [ ] **Step 1: Implement immutable contracts, input validation, endpoint preflight, and state-domain construction**

Implement the four public dataclasses exactly as specified, plus private `_PartialPathV1` and `_LayeredDomainV1`. Canonicalize states with:

```python
ordered_states = tuple(sorted(states, key=service_plan_fingerprint_v1))
```

Reject empty input, duplicate fingerprints, route/direction/endpoint/trip-total mismatches, booleans as integer limits, and limits outside `1..256`. Use existing phase generation and compilation helpers read-only. Build adjacency only for:

```python
right.first_minute == left.last_minute + left.headway_minutes
or right.first_minute - right.headway_minutes == left.last_minute
```

Trim nodes only by complete-path reachability and record source, sink, node, edge, and trimmed counts.

- [ ] **Step 2: Run the graph/input slice and observe GREEN with K-best/parity still RED**

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_dag_frontier.py -k "state_order or one_layer or left_owned or right_owned or illegal_boundary or endpoint or limit" -vv
```

Expected: graph/input tests pass. Running the whole file still fails at exact enumeration/parity assertions because per-node retention and terminal merge are not implemented.

- [ ] **Step 3: Implement exact per-node K retention, terminal merge, and compilation decoding**

Implement `_merge_sorted_sources_v1`, `_enumerate_state_domain_v1`, and decoding. Use exact `Fraction`, denominator LCM, explicit heap `(path.key, source_index, item_index, path)` entries, departure-vector deduplication, and no scalar score. Integer scaling is family-local only; terminal merging across states compares the exact `Fraction` compiler objective before regime count, imbalance, headway vector, and departure vector. Validate every decoded compilation, reconstruct its objective independently, and raise on disagreement.

`kbest_dag_candidate_payload_v1` emits the U5-compatible semantic record:

```python
{
    "fingerprint": candidate.compilation_fingerprint,
    "departures_minutes": list(candidate.departure_vector),
    "state_fingerprint": candidate.state_fingerprint,
    "state_index": state_index,
    "phase_indices": list(candidate.phase_indices),
    "headway_shape": list(candidate.headway_vector),
    "objective": [str(value) for value in candidate.compiler_objective],
    "integer_objective": [
        candidate.exact_scaled_quantization,
        *candidate.compiler_objective[1:],
    ],
    "direction": candidate.state.direction,
    "endpoint_checks": {"first": True, "last": True},
}
```

Exclude timing fields from all semantic hashes.

- [ ] **Step 4: Run the full DAG suite and diagnose parity at the first differing semantic record**

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_dag_frontier.py -vv
```

Expected: exact U5 parity and all exhaustive/determinism/dependency tests pass. If parity is RED, classify `U6_PRODUCTION_PORT_DIVERGED_FROM_U5`, compare U6 and U5 domain manifests at the first differing state/layer/node/edge/path, and correct only evidence-backed A-core behavior. Do not import experiment types, loosen hashes, reorder expected records, or add Q handling.

- [ ] **Step 5: Run bounded legacy references, Ruff, and the no-solver import proof**

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_dag_frontier.py tests/test_clean_boundary_compiler.py -vv
python -m ruff check src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py tests/test_kbest_dag_frontier.py
python -m ruff format --check src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py tests/test_kbest_dag_frontier.py
```

Expected: all tests and Ruff checks pass in a process where U6 never imports OR-Tools, CP-SAT, or experiments.

- [ ] **Step 6: Commit the green exact-DAG port and frozen parity gate**

```powershell
git add -- src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py tests/test_kbest_dag_frontier.py tests/fixtures/pr62_u6/u5_frozen_family.json
git commit -m "Port exact k-best DAG realization"
```

### Task 4: Implement Hard Eligibility and Uncapped Aggregate Diversity

**Files:**

- Create: `src/bus_schedule_engine/kbest_shadow_refinement.py`
- Create: `tests/test_kbest_shadow_refinement.py`

**Interfaces:**

- Consumes: `KBestDagCandidateV1`, unchanged structural/protection/actual-service/tail authorities, unchanged `retain_strict_directional_canonicalizations_v1`, and unchanged `_select_diverse_paths` semantics.
- Produces: `KBestDagEligibilityResultV1`, `KBestDagFamilyShadowV1`, `KBestDagDirectionalRetentionV1`, `evaluate_kbest_dag_hard_eligibility_v1`, and `retain_kbest_dag_directional_frontier_v1`.

- [ ] **Step 1: Write RED eligibility-order tests**

Use real minimal compilations where practical and narrow monkeypatches only to make each downstream authority raise if called out of order. Cover structural failure, endpoint mismatch, trip-total mismatch, protection failure, tail failure, actual-service metric retention, and endpoint-invalid generated-state removal before `compile_service_plan_family_kbest_v1`.

Assert rejection counts are separate:

```python
assert result.structural_rejects == 1
assert result.protection_rejects == 1
assert result.tail_rejects == 1
assert result.eligible_fingerprints == expected_eligible
```

- [ ] **Step 2: Run eligibility tests and observe RED**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_shadow_refinement.py -k "eligibility or protection or tail or endpoint" -vv
```

Expected: missing shadow module/API failures.

- [ ] **Step 3: Implement ordered hard eligibility and strict directional progression**

For every raw candidate: validate clean structure, endpoints, total trips, protection, actual-service metrics, then tail. Convert survivors into `DirectionalCompilationCandidateV1` using `CleanCompileVariantV1` values derived from the exact compiler objective. Apply existing strict directional canonicalization only after hard eligibility and count strict-progress rejections separately from hard-ineligible candidates.

- [ ] **Step 4: Run eligibility tests and observe GREEN**

Run the Step 2 command.

Expected: all selected tests pass and raising sentinels prove ineligible candidates never reach diversity.

- [ ] **Step 5: Write RED diversity and greater-than-256 aggregate regressions**

Cover eligible pools at 31, 32, and 33; deterministic repeat; quality anchor; headway-shape retention; exact-departure max-min; and an ineligible best-quality candidate that cannot occupy a retained slot.

Add the required cross-family regression with two family result groups totaling 300 distinct eligible fingerprints. Use monotonically separated exact-departure vectors so the real 59b max-min selector must inspect the high-index tail:

```python
result = retain_kbest_dag_directional_frontier_v1(
    source_directional=source,
    family_results=(family_a_150, family_b_150),
    limit=32,
)
assert result.raw_candidates_before_cross_family_dedupe == 300
assert result.eligible_candidates_before_cross_family_dedupe == 300
assert result.aggregate_eligible_count_after_dedupe == 300
assert result.pre_diversity_truncation_count == 0
assert farthest_fingerprint in result.retained_fingerprints
assert result.selector_seconds >= 0.0
```

This test must fail if any hidden `[:256]`, `min(256, ...)`, or intermediate aggregate cap is inserted.

- [ ] **Step 6: Run diversity tests and observe RED**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_shadow_refinement.py -k "diversity or aggregate or ineligible" -vv
```

Expected: missing aggregate retention behavior.

- [ ] **Step 7: Implement compilation-fingerprint deduplication and unchanged diversity adaptation**

Union all family survivors plus the revalidated source directional candidate. Deduplicate by compilation fingerprint, choosing equal identities deterministically by exact compiler objective/headway/departure ordering. Adapt candidates to the unchanged `_FrontierPath` projection with `Fraction` objective fields and call unchanged `_select_diverse_paths`; map selected departure identities back to directional candidates. Never compare `exact_scaled_quantization` across families.

Record family count, raw-before-dedupe, eligible-before-dedupe, aggregate-after-dedupe, source-added flag, selector seconds, retained count, and a literal zero pre-diversity truncation count.

- [ ] **Step 8: Run all eligibility/diversity tests and measure the real aggregate selector**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_shadow_refinement.py -k "eligibility or diversity or aggregate or ineligible" -vv
```

Expected: tests pass. If the 300-item test or later real Route 10 aggregate demonstrates operational inadequacy, classify and stop before considering U0 code.

- [ ] **Step 9: Commit hard-eligible retention**

```powershell
git add -- src/bus_schedule_engine/kbest_shadow_refinement.py tests/test_kbest_shadow_refinement.py
git commit -m "Integrate hard-eligible DAG shadow retention"
```

### Task 5: Implement Family Generation, Pair Evaluation, and Strict Source-Once Worklists

**Files:**

- Modify: `src/bus_schedule_engine/kbest_shadow_refinement.py`
- Modify: `tests/test_kbest_shadow_refinement.py`

**Interfaces:**

- Consumes: completed `RouteCoordinatorResultV1`, unchanged 59b family detection/planning-index mapping/state generation, retained directional candidates, `evaluate_operating_pair_v1`, `strict_pair_rhythm_progress_v1`, `update_operating_pair_pareto_v1`, and `select_operational_timetable_v3`.
- Produces: `KBestDagSourceRefinementV1`, `KBestDagShadowStatisticsV1`, `KBestDagShadowResultV1`, `refine_kbest_dag_source_pair_v1`, and `run_kbest_dag_shadow_from_completed_result_v1`.

- [ ] **Step 1: Write RED family, pair, and worklist tests**

Cover every family detected by the unchanged 59b authority, actual-family-to-planning-index mapping, boundary-step radius `3`, trip-transfer radius `3`, exactly one external side varied at a time, endpoint-invalid generated-state removal before the DAG call, one multi-state DAG call per detected family, and stable family/state manifests. Also cover only-retained cross-products, maximum `32 * 32`, exact fleet rejection before Pareto, duplicate-pair suppression, strict tuple improvement, equal-tuple rejection, sorted worklist order, one processing per source fingerprint, and parent/child continuation history.

Add a zero-global-call test:

```python
def test_completed_global_result_path_never_invokes_coordinator(monkeypatch):
    monkeypatch.setattr(
        coordinator,
        "search_route_service_plans_v1",
        lambda **kwargs: pytest.fail("global coordinator called from shadow path"),
    )
    result = run_kbest_dag_shadow_from_completed_result_v1(
        base_coordinator_result=completed,
        context=context,
        coordinator_budget=budget,
        directional_frontier_limit=32,
    )
    assert result.statistics.global_coordinator_executions == 0
```

- [ ] **Step 2: Run family/pair/worklist tests and observe RED**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_shadow_refinement.py -k "family or radius or pair or fleet or source or worklist or coordinator" -vv
```

Expected: missing family/pair/worklist APIs.

- [ ] **Step 3: Implement unchanged family discovery with one DAG realization per family**

Reuse the 59b detector, actual-family-to-planning-index mapper, and radius-3 state generator read-only. Preserve the one-external-side-at-a-time rule. Filter endpoint-preflight-invalid states before calling `compile_service_plan_family_kbest_v1`; call the DAG compiler once with the complete internally canonicalized valid state set for each detected family, then apply ordered hard eligibility. Record family identity, planning indices, generated-state fingerprints, invalid-state rejects, graph/raw/eligible hashes, counts, and timings.

- [ ] **Step 4: Implement complete retained cross-products and unchanged Pareto updates**

Cross directions in deterministic compilation-fingerprint order. Call existing exact pair evaluation first; treat `None` as fleet rejection. Deduplicate pair fingerprints, reject non-strict rhythm tuples, then pass strict survivors to unchanged `update_operating_pair_pareto_v1` with the coordinator's `max_pair_frontier`. Record every decision and Pareto before/after hash.

- [ ] **Step 5: Implement the sorted source-once driver**

Seed the queue from sorted base V3 materiality fingerprints. Maintain `processed`, `queued`, generated-pair parent records, and deterministic fingerprint order. After each source, rerun unchanged V3. Enqueue a new V3 materiality fingerprint only when it is a generated Pareto-admitted descendant with a recorded strictly smaller rhythm tuple. Never enqueue equal progress.

The public runner accepts no seeds and contains no call path to `search_route_service_plans_v1`.

- [ ] **Step 6: Run all worklist tests and authority locks**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_shadow_refinement.py tests/test_service_plan_coordinator_v1.py -k "family or radius or pareto or v3 or pair or fleet or source or worklist or coordinator or strict" -vv
```

Expected: all selected tests pass; existing Pareto and coordinator tests remain unchanged.

- [ ] **Step 7: Commit explicit completed-result shadow orchestration**

```powershell
git add -- src/bus_schedule_engine/kbest_shadow_refinement.py tests/test_kbest_shadow_refinement.py
git commit -m "Integrate k-best DAG shadow refinement"
```

### Task 6: Implement Independent Cap Sensitivity and Normalized-Union Binding

**Files:**

- Modify: `src/bus_schedule_engine/kbest_shadow_refinement.py`
- Modify: `tests/test_kbest_shadow_refinement.py`

**Interfaces:**

- Consumes: three independent completed-result shadow runs, immutable semantic cache keys, unchanged Pareto updater with `limit=None`, and unchanged V3.
- Produces: `KBestDagSemanticCacheKeyV1`, `KBestDagSensitivityResultV1`, `run_kbest_dag_cap_sensitivity_v1`, and `adjudicate_kbest_dag_cap_binding_v1`.

- [ ] **Step 1: Write RED independent-worklist and cache-key tests**

Use a fixture where cap 64 discovers a strict descendant source absent from cap 32. Assert the cap-64 source is processed and its DAG compiler is called. Use an identical source/family key in two cases and assert only raw/eligible results are cached; retained fingerprints, worklist histories, Pareto histories, and V3 histories remain distinct objects.

Assert the key binds source fingerprint, direction, family identity, sorted state manifest, endpoint authority, protection/demand/tail context authority, raw limit 256, and implementation authority hash.

- [ ] **Step 2: Run sensitivity/cache tests and observe RED**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_shadow_refinement.py -k "sensitivity or cache or cap_specific" -vv
```

Expected: missing sensitivity/cache behavior.

- [ ] **Step 3: Implement three complete cap runs with semantic-only caching**

Invoke the completed-result shadow runner independently for caps 16, 32, and 64. Share a cache only at the family raw/eligibility boundary and only by the full immutable semantic key. Make fresh-repeat mode allocate an empty cache. Reject cache values containing cap, retained, pair, Pareto, worklist, or V3 state.

- [ ] **Step 4: Write RED normalized-union binding tests, including the required cap-32-present winner case**

Construct nondominated candidates A, B, and X. Cap 32 contains A and B; cap 64 adds X. Give A the unique common SSE/TE anchor, B better rhythm but initially outside the materiality envelope, and X a one-trip-calibration continuous delta that widens the universe-derived envelope enough for B to win:

```python
a = candidate("A", sse=1.0, te=10.0, continuous=20.0, rhythm=(2, 2, 2, 0))
b = candidate("B", sse=2.0, te=12.0, continuous=22.0, rhythm=(1, 2, 2, 0))
x = candidate("X", sse=3.0, te=11.0, continuous=24.0, rhythm=(3, 2, 2, 0))
cap32 = frontier(a, b)
cap64 = frontier(a, b, x)
assert select_v3(cap32).selected_pair_fingerprint == "A"
result = adjudicate_kbest_dag_cap_binding_v1(cap32=cap32, cap64=cap64, context=context)
assert result.normalized_union_selection.selected_pair_fingerprint == "B"
assert result.binding is True
assert result.normalized_union_winner_cap32_present is True
assert result.normalized_union_winner_cap64_only is False
```

Assign tradeoff 10-D Pareto vectors so A, B, and X are mutually nondominated. Add a separate cap-64-exclusive winner case and a same-winner non-binding case.

- [ ] **Step 5: Run binding tests and observe RED**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_shadow_refinement.py -k "binding or normalized_union" -vv
```

Expected: direct-union V3 or exclusivity-based binding fails the required B-winner assertion.

- [ ] **Step 6: Implement deterministic Pareto normalization and outcome-based binding**

Deduplicate `cap32.final_pareto + cap64.final_pareto` by pair fingerprint, iterate candidates in fingerprint order into:

```python
normalized = update_operating_pair_pareto_v1(normalized, candidate, limit=None)
```

Run unchanged V3 only on `normalized`. Set `binding` to selected-fingerprint inequality versus cap-32 final V3. Compute cap-32-present and cap-64-only flags independently for evidence.

- [ ] **Step 7: Run the complete shadow unit suite**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_shadow_refinement.py tests/test_operational_selection_policy_v3.py -vv
python -m ruff check src/bus_schedule_engine/kbest_shadow_refinement.py tests/test_kbest_shadow_refinement.py
python -m ruff format --check src/bus_schedule_engine/kbest_shadow_refinement.py tests/test_kbest_shadow_refinement.py
```

Expected: independent worklist, >256 aggregate, normalized-union, and existing V3 tests all pass.

- [ ] **Step 8: Commit sensitivity behavior**

```powershell
git add -- src/bus_schedule_engine/kbest_shadow_refinement.py tests/test_kbest_shadow_refinement.py
git commit -m "Certify k-best DAG cap sensitivity semantics"
```

### Task 7: Build the Explicit Evidence Runner and Certify Route 10

**Files:**

- Create: `scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py`
- Create: `tests/test_pr62_u6_kbest_dag_shadow_integration.py`
- Create: `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json`
- Create: `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.md`

**Interfaces:**

- Consumes: preserved Route 10 pickle at `E:/Project/Biểu đồ giờ/bus-schedule-optimizer-pr62-u/.pr62-u-local/certification/route_10_complete_base.pickle`, explicit context/input authorities, U5 parity gate, and shadow APIs.
- Produces: CLI stages `parity`, `route10-canonical`, `route10-repeat`, `route10-sensitivity`, `route6-global-once`, `route6-canonical`, `route6-repeat`, `route6-sensitivity`, and `render-evidence`.

- [ ] **Step 1: Write RED saved-result and runner-guard tests**

Test exact SHA/size before unpickle, wrong-hash rejection before unpickle, reconstructed Route 10 Pareto count 11, access-safe count 7, base V3 fingerprint `6dbd9d...3f16`, required materiality source `e76426...cb24`, and global call count zero. Add subprocess tests showing existing production entry points never import the runner or shadow module.

- [ ] **Step 2: Run runner tests and observe RED**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_pr62_u6_kbest_dag_shadow_integration.py -k "saved or route10 or explicit or global" -vv
```

Expected: missing runner and loader APIs.

- [ ] **Step 3: Implement explicit CLI, canonical payloads, and fail-closed gates**

Bind source bytes before deserialization. Emit canonical semantic JSON with UTF-8, sorted keys, compact separators, LF, and no timings inside semantic hashes. Keep timing values in separate payload fields. Reject undefined contract mismatches with `U6_ROUTE10_HARD_ELIGIBILITY_CONTRACT_MISMATCH` or a more precise label.

The runner accepts all input/output paths explicitly; it changes no app default. Write scratch outputs once using exclusive creation. Do not implement a generic checkpoint/recovery framework.

- [ ] **Step 4: Add RED deterministic renderer and Q-isolation tests**

Build a frozen sample payload, render JSON/Markdown twice, and assert byte equality. Assert Q presence/absence cannot change raw, eligible, retained, pair, Pareto, worklist, or V3 hashes; Q observation is computed only after frozen outputs exist.

- [ ] **Step 5: Implement evidence projection and post-freeze Q observation**

Render the requested PORT, ROUTE 10, ROUTE 6, Q, and READINESS sections. Until Route 6 runs, set its state to `NOT_RUN_ROUTE10_GATE_PENDING` and all readiness flags false. Never use Q to classify a run.

- [ ] **Step 6: Run every pre-Route-10 validation gate**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_dag_frontier.py tests/test_kbest_shadow_refinement.py tests/test_pr62_u6_kbest_dag_shadow_integration.py tests/test_local_rhythm_refinement.py tests/test_clean_boundary_compiler.py tests/test_closed_loop_service_protection_v1.py tests/test_end_tail_settlement.py tests/test_fleet_and_generator.py tests/test_service_plan_coordinator_v1.py tests/test_operational_selection_policy_v3.py -vv
python -m ruff check src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py src/bus_schedule_engine/kbest_shadow_refinement.py scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py tests/test_kbest_dag_frontier.py tests/test_kbest_shadow_refinement.py tests/test_pr62_u6_kbest_dag_shadow_integration.py
python -m ruff format --check src/bus_schedule_engine/contracts_v1/kbest_dag_frontier.py src/bus_schedule_engine/kbest_shadow_refinement.py scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py tests/test_kbest_dag_frontier.py tests/test_kbest_shadow_refinement.py tests/test_pr62_u6_kbest_dag_shadow_integration.py
python -m compileall -q src scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py
git diff --check
```

Expected: all commands pass. If U5 parity is not exact, stop as `U6_PRODUCTION_PORT_DIVERGED_FROM_U5`.

- [ ] **Step 7: Run Route 10 canonical and fresh-process repeat with empty caches**

Run the CLI twice in separate processes using the exact saved pickle, distinct output directories, cap 32, and empty cache. Compare processed source order, raw DAG hashes, eligible hashes, retained hashes, pair fingerprints, final Pareto hash, and final V3 fingerprint.

Require zero global calls, every retained candidate protection/tail safe, every Pareto-admitted pair exact-fleet feasible, legitimate source-once termination, each family DAG at most 60 seconds, and canonical Route 10 local total at most 300 seconds. A mismatch or ceiling violation stops under the specified Route 10 classification.

- [ ] **Step 8: Run complete Route 10 16/32/64 sensitivity**

Start all three cases independently from the same saved global result. Allow shared semantic cache hits only within this sensitivity launch. Verify cap-specific descendants build their own DAGs. Normalize the final 32/64 union and require the outcome-based binding detector to be false. Record cap 16 diagnostically.

- [ ] **Step 9: Render and verify Route 10 evidence twice**

Render from the frozen combined payload into two scratch directories. Require byte-identical JSON and Markdown, then place one verified pair at the canonical evidence paths. Evidence must classify `ROUTE10_KBEST_DAG_SHADOW_VALIDATED` before Route 6 can run.

- [ ] **Step 10: Commit Route 10 certification**

```powershell
git add -- scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py tests/test_pr62_u6_kbest_dag_shadow_integration.py docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.md
git commit -m "Certify Route 10 k-best DAG shadow"
```

### Task 8: Consume the Single Route 6 Global Run and Certify the Control

**Files:**

- Modify: `scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py`
- Modify: `tests/test_pr62_u6_kbest_dag_shadow_integration.py`
- Modify: `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json`
- Modify: `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.md`

**Interfaces:**

- Consumes: passed Route 10 evidence, explicit Route 6 workbook and production input hashes, and frozen coordinator budget `24/512/4/24/512`.
- Produces: an untracked write-once Route 6 execution ledger, saved completed global pickle, canonical/repeat/sensitivity payloads, and control evidence.

- [ ] **Step 1: Write RED one-shot ledger and Route 6 control tests**

Test that `route6-global-once` creates an exclusive `STARTED` ledger before calling the coordinator, writes `COMPLETED` plus result hash only after success, refuses any second invocation for both states, and reports one execution. Test base mismatch classification, final-control change classification, and repeat path global count zero.

- [ ] **Step 2: Run Route 6 gate tests and observe RED**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_pr62_u6_kbest_dag_shadow_integration.py -k "route6 or ledger or control" -vv
```

Expected: missing one-shot behavior.

- [ ] **Step 3: Implement the narrow Route 6 one-shot launch path**

Require Route 10 validated evidence before ledger creation. Hash all Route 6 workbook and committed context inputs. Assert the exact budget dataclass fields before calling `search_route_service_plans_v1` once. On process failure after `STARTED`, preserve the consumed ledger and classify `U6_ROUTE6_GLOBAL_EXECUTION_RESULT_UNAVAILABLE`; do not rerun.

After success, pickle the completed result once, record its hash, reconstruct selection, and require base V3 `ad0ebdf...174b` before shadow work.

- [ ] **Step 4: Run the Route 6 global coordinator exactly once**

Invoke `route6-global-once` with explicit workbook path and new scratch ledger/result paths. Confirm execution count `1`, completed-result hash, base Pareto/control authorities, and unchanged input hashes. Never invoke this stage again.

- [ ] **Step 5: Run Route 6 canonical, repeat, and independent cap sensitivity from the saved result**

Run cap-32 canonical A and B in fresh processes with empty caches. Require identical source order, raw/eligible/retained hashes, pair frontier, final Pareto, and V3. Run independent complete cap-32/cap-64 sensitivity with semantic-only cache reuse and no cap-specific state reuse.

Require canonical and normalized-union final V3 to remain `ad0ebdf...174b`. Any change stops as `ROUTE6_CONTROL_CHANGED_UNDER_KBEST_DAG_SHADOW`.

- [ ] **Step 6: Update and render Route 6 evidence twice**

Record canonical input hashes, exactly one global execution, base control, source/family/DAG/eligibility/retention/pair/Pareto counts, sensitivity, final control, determinism, timings, and post-freeze Q observations. Render twice byte-identically and replace the canonical evidence pair only after equality succeeds.

- [ ] **Step 7: Run Route 6 tests and commit control certification**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_pr62_u6_kbest_dag_shadow_integration.py -k "route6 or ledger or control or deterministic" -vv
git diff --check
```

Then commit:

```powershell
git add -- scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py tests/test_pr62_u6_kbest_dag_shadow_integration.py docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.md
git commit -m "Certify Route 6 control shadow"
```

### Task 9: Final Evidence, Authority Audit, and Regression Closeout

**Files:**

- Modify: `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json`
- Modify: `docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.md`
- Modify: `tests/test_pr62_u6_kbest_dag_shadow_integration.py` only for final evidence-schema assertions written RED first.

**Interfaces:**

- Consumes: frozen Route 10 and Route 6 payloads, port audit, production file hashes, and test/lint/diff results.
- Produces: final U6 classification or an evidence-backed fail-closed classification, with all readiness flags false.

- [ ] **Step 1: Write RED final evidence completeness tests**

Assert all requested PORT, ROUTE 10, ROUTE 6, Q, and READINESS keys exist; production hashes match the branch; global counts are 0 and 1; U5 authorities match; both repeats match; cap adjudications are non-binding; Route 6 control is unchanged; Q has no classification effect; and readiness/authority flags remain false.

- [ ] **Step 2: Run final evidence tests and observe RED**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_pr62_u6_kbest_dag_shadow_integration.py -k "evidence or readiness or production_authority" -vv
```

Expected: missing closeout verification fields.

- [ ] **Step 3: Perform the protected production-authority diff audit**

Run exact no-diff checks from `59b892d3` for:

```text
src/bus_schedule_engine/contracts_v1/clean_boundary_compiler.py
src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py
src/bus_schedule_engine/service_plan_coordinator.py
src/bus_schedule_engine/contracts_v1/operational_selection_policy_v3.py
src/bus_schedule_engine/contracts_v1/closed_loop_service_protection.py
src/bus_schedule_engine/contracts_v1/end_tail_settlement.py
src/bus_schedule_engine/contracts_v1/fleet_assignment.py
streamlit_app.py
app_pages/
outputs/final_pilot/
```

AST-scan new production modules for forbidden `ortools`, CP-SAT, `experiments`, coordinator-search, Streamlit, and export imports/calls. Verify `pyproject.toml` is unchanged. Any protected diff classifies `U6_UNEXPECTED_PRODUCTION_AUTHORITY_CHANGE` and stops.

- [ ] **Step 4: Run the complete focused regression and static validation**

Run:

```powershell
$env:PYTHONPATH='src;scripts'
python -m pytest tests/test_kbest_dag_frontier.py tests/test_kbest_shadow_refinement.py tests/test_pr62_u6_kbest_dag_shadow_integration.py tests/test_local_rhythm_refinement.py tests/test_clean_boundary_compiler.py tests/test_closed_loop_service_protection_v1.py tests/test_end_tail_settlement.py tests/test_fleet_and_generator.py tests/test_service_plan_coordinator_v1.py tests/test_operational_selection_policy_v3.py -vv
python -m ruff check src tests scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py
python -m ruff format --check src tests scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py
python -m compileall -q src tests scripts/run_pr62_u6_kbest_dag_shadow_production_integration.py
git diff --check
```

Expected: every command exits zero.

- [ ] **Step 5: Compare broad U6 failures with a fresh untouched 59b baseline**

Run the full suite in the existing detached 59b baseline worktree and the U6 worktree with identical Python, `PYTHONPATH=src;scripts`, isolated base-temp directories, and JUnit XML output. Parse both XML files and assert:

```python
u6_failed_node_ids - baseline_failed_node_ids == set()
u6_error_node_ids - baseline_error_node_ids == set()
```

Record baseline and U6 pass/skip/fail/error counts and the exact pre-existing difference. Do not add a new exclusion to make the comparison pass.

- [ ] **Step 6: Render final evidence twice and verify byte identity**

Render the same frozen final payload into two new scratch directories. Compare SHA-256 and bytes for both JSON and Markdown. Copy the first verified pair to the canonical evidence paths and rerun evidence tests.

- [ ] **Step 7: Set the final classification only after all gates pass**

If every requested condition passes, set:

```text
U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION_VALIDATED
DAG shadow backend authoritative = false
legacy backend removed = false
production default changed = false
READY_FOR_FINAL_PILOT_USE = false
READY_FOR_PR62_COMPLETION_REVIEW = false
```

Otherwise preserve the exact evidence-backed fail-closed classification and do not patch around it.

- [ ] **Step 8: Commit final evidence**

```powershell
git add -- docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.json docs/engine/evidence/PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.md tests/test_pr62_u6_kbest_dag_shadow_integration.py
git commit -m "Record U6 integration evidence"
```

- [ ] **Step 9: Verify final branch state and stop for review**

Run:

```powershell
git status --short --branch
git log --oneline 59b892d3b367182b20734ad4e4405e264ba14024..HEAD
git diff --stat 59b892d3b367182b20734ad4e4405e264ba14024..HEAD
git diff --check 59b892d3b367182b20734ad4e4405e264ba14024..HEAD
```

Report branch, worktree, local commit sequence, origin/PR62 head, PR state, exact ported/excluded files, U5 parity, Route 10 and Route 6 counts/results/timings/determinism, Q observations, final classification, false authority/default/readiness flags, and stop. Do not merge or update PR #62.
