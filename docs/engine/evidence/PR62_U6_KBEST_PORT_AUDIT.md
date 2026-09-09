# PR62-U6 U5 production port audit

## Decision and authority

Only the exact layered-DAG algorithmic behavior identified below may be re-expressed
in U6. No experiment module is imported. The sole admitted post-59b local behavior
is fixed-endpoint half-open-regime preflight. Checkpoint/recovery, local continuation
deltas, CP-SAT objects, historical-Q certification and U0 selector optimization are excluded.

Authority: `docs/superpowers/specs/2026-09-08-pr62-u6-kbest-dag-shadow-integration-design.md`.
Exact audited range:
`59b892d3b367182b20734ad4e4405e264ba14024..0b51d07735a767eb1c7cba2fad899f007a6543cc`.
U5 design: `fc779e61186f38dc40066668ea20d2437687a6ac`.
U5 evidence: `f689111357b2cf465e1d96e093a5ad9e0c3f61b3`.
All are read-only authorities; the U5 evidence commit is outside this implementation diff.

This audit accounts for all **214 paths and 290 zero-context hunks** in the full
diff, including paths outside the focused U5/dependency/production source command.
There are 210 additions and four modified files, no deletes, renames or binary-only
changes. Each literal `(path, complete Git hunk header)` has one row.
H001-H290 follow Git full-diff order and are stable for this frozen range.

Frozen classifications:

- `A. K_BEST_DAG_CORE`: admit specified algorithmic behavior through production equivalents.
- `B. EXPERIMENT_ONLY`: reject experiment infrastructure and CP-SAT objects.
- `C. TEST_OR_EVIDENCE_ONLY`: tests, fixtures, manifests, artifacts and pure evidence renderers.
- `D. DEPENDS_ON_POST_59B_LOCAL_CHANGES`: reject later local/authority dependencies except the narrow endpoint invariant.

Mixed new-file hunks cannot be split into invented Git hunks. The single hunk class
is its admission class, constrained by included/excluded symbols in its row.
U2 solver and U3 shell are B admission units; their graph/decoding semantics are A
behavioral references for re-expression, not second hunk classifications. U5 kbest
is A only with experiment dataclasses, imports, callback and result fields excluded.
Pure evidence renderers are C; experiment report orchestration/classification is B.
The task controller explicitly confirmed this mixed-hunk convention.

## Allowed behavior and exact production equivalents

Experiment line references below are at `0b51d077`; production references are at
`59b892d3`. These are port decisions, not claims that U6 modules already exist.

| Behavior | Algorithmic source | Production equivalent and boundary |
|---|---|---|
| A partial-path scoring | U5 kbest PartialPath.key 21-40, _candidate_q 66-70, _first_path 73-82, _extend 85-94, _infer_scale 137-144 | Private immutable slotted U6 path. Preserve exact scaled quantization, actual regime count, phase imbalance, headway vector, departure vector. Infer denominator LCM; fail closed on non-unit denominator. No float ranking; experiment dataclass definitions are not production contracts. |
| A deterministic merge and per-node K | U5 kbest _merge_sorted_sources 97-134, _enumerate_domain 147-198 | Private U6 k-way heap merge with canonical key then explicit source/item indices; exact departure deduplication, sorted unique predecessors, at most K distinct prefixes per node. No Python-object tie comparison or diversity pruning. |
| A terminal merge and exhaustion | U5 kbest extract_k_best 245-322, enumerate_kbest 325-332 | compile_service_plan_family_kbest_v1 sorts input states by service_plan_fingerprint_v1, validates family identities, and retains global top K (1..256). Exhaustion requires no node or terminal truncation. Exclude callback argument/call 250/288-289 and experiment result/termination records. |
| A layered-domain construction | U5 authority build_domains_timed 72-123; U2 solver build_domain 104-137 | Private U6 domain with 59b _regimes_from_state, _phase_candidates, _candidate_path and _bounded_phase_candidates (inherited bound 4096). Bounded-phase authority precedes reachability-only trim. No U2 Domain, checkpoint loader or launch machinery. |
| A graph compatibility and reachability | U2 solver graph_domain 66-101, corroborated by 59b _candidate_path 263-334 | Re-express edge union: right.first = left.last + left.headway OR right.first - right.headway = left.last. Preserve left-owned, right-owned and equal-headway semantics. Intersect forward/backward reachable sets, retain sorted original node order, remap edges. No objective pruning; U6 owns super-source/sink statistics. |
| A decoding and exact reconstruction | U5 kbest _decode 201-242; U3 shell _path/_objective/_decode 140-173; U2 benchmark exact_objective 48-59 | Reconstruct Fraction objective from phases/demand slices; use 59b _FrontierPath, _compilation_from_path, clean_compilation_fingerprint_v1 and structural validator. Exclude U2 Solution, benchmark import and synthetic no-state hash fallback 231-234. Production inputs are validated states. |
| Canonical-record dependency | U3 shell canonical_record 176-199, U5 import 294 | Explicit KBestDagCandidateV1/KBestDagFrontierV1 fields; no U3 import. A test-only serializer may reproduce U5 semantic evidence fields. U6 hashes use approved compact encoding without timings; U2 benchmark canonical_bytes uses indented JSON and is not interchangeable byte authority. |
| Result/telemetry dependency | U5 KBestResult 44-56 and node/merge metadata | New frozen slotted KBestDagGraphStatisticsV1, KBestDagTelemetryV1 and KBestDagFrontierV1. No solver status, Q observation, artifact path, subprocess or checkpoint field. |
| Sole narrow D endpoint behavior | Later _local_state_matches_compiler_endpoint_contract_v1 431-445; ordinary generated-state call 508 | Pure preflight before DAG building: first.start <= fixed_first_departure < first.end AND final.start <= fixed_last_departure < final.end. Reject checkpoint call 443-444. Preserve 59b no-external-side generation behavior. RED-to-GREEN tests precede implementation admission. |

U5 kbest imports at 15/218/294 are excluded. Its experiment dataclasses at 20-63
are re-expressed with the approved immutable slotted U6 contracts and private domain,
partial-path and merge types. Generation callback at 250/288-289 is excluded.
Compilation decoding uses existing compiler builders directly, never through U2.

U5 authority source_authority (41-69) and prepare (204-269) bind checkpoint/U4/launch
authority and are excluded. graph_manifests (126-201) is C evidence behavior.
U5 evaluation imports the post-59b U0 selector at 8-11 and U3 path at 12; its
structural (57-77), validate_raw (80-90), select (93-110), downstream (117-188)
and classify (191-222) are not copied as orchestration. U6 uses unchanged 59b
structural validation, endpoints/trip totals, translated protection,
evaluate_actual_service_v1 and metrics.tail_ordering.eligible before aggregate
directional diversity. Pair/fleet, strict rhythm, Pareto and V3 retain 59b authority.
The U5 worker's selection-before-downstream sequence is excluded. U5 subprocess,
watchdog, write-once, run/worker report orchestration and posthoc Q are B; its pure
evidence report renderer is C.

Read-only dependency closure: U5 -> U2 solver/benchmark and U3 shell/inputs -> U2
corpus and U3 execution. U2 load_object/load_corpus and U3 load_family read
post-59b checkpoint/digest objects; none is a U6 runtime equivalent. The later
fixture task derives only frozen states, endpoint authority and semantic expectations.
This audit neither executes experiment code nor reads private checkpoint artifacts.

## Frozen 59b production authority

| Path | 59b Git blob | 59b content SHA-256 | U5 Git blob |
|---|---|---|---|
| src/bus_schedule_engine/contracts_v1/clean_boundary_compiler.py | 8026c250f5b5187a80bb8f2575682ecd90838928 | e882cc8285ab7907b16862e55f23334c680606deb8b59735ec08ccae657970b5 | 8026c250f5b5187a80bb8f2575682ecd90838928 |
| src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py | d5e53416dd45a45453ffbf9d0e8d88b7c67bffd2 | 58272cf3d3cb17e560629a556461e9fa6f794e195f82e2f778e7cd60fc35d3bc | 0c09a022c8707d73b2abdf1a515e3066cadb4060 |
| src/bus_schedule_engine/local_rhythm_refinement.py | f2be8376f6e89b948a8ed169b8e8175a1f28f33a | 98373bfc816bfb15e7efeb91fabe05b630d5690b345076ef7b2a6846e2159c90 | 1ec7d5da579b4d30a7e7d2e1a7e635ceec0e2738 |
| src/bus_schedule_engine/contracts_v1/service_plan_state.py | 021fb54470c1195c82169f9365aa0b77287f2c18 | c917301a9985c03f95980f08897f0e90b2fe7caa19f9352f2aa0966dcb519dd1 | 021fb54470c1195c82169f9365aa0b77287f2c18 |
| src/bus_schedule_engine/service_plan_coordinator.py | cf0a45cd6e58617ac02ca039e3e4d59510291043 | 0bc6b98fcbc6218539fcb11280904695f2e588dad33e2fbeedff4482c5ceb772 | cf0a45cd6e58617ac02ca039e3e4d59510291043 |

Exact 59b symbols available read-only:

- clean_boundary_compiler: _PhaseCandidate 141-147, _phase_candidates 206-260,
  _candidate_path 263-334, _build_service_regimes 368-412,
  _boundary_diagnostics 415-442, validate_clean_boundary_compilation_v1 550-593.
- clean_compile_frontier: _FrontierPath 55-79, clean_compilation_fingerprint_v1
  82-90, _deduplicate_paths 93-101, _departure_distance 104-105,
  _select_diverse_paths 108-176, _bounded_phase_candidates 264-335,
  _regimes_from_state 338-348, _compilation_from_path 351-393.
- service_plan_state: service_plan_fingerprint_v1 116-123.
- local_rhythm_refinement: detect_local_rhythm_families_v1 243-289,
  map_actual_family_to_planning_indices_v1 292-312, enumerate_local_rhythm_states_v1
  347-414, retain_strict_directional_canonicalizations_v1 424-433,
  pair_rhythm_tuple_v1 436-443, strict_pair_rhythm_progress_v1 446-447.

clean_boundary_compiler is byte-identical across the range. Only
_select_diverse_paths changed in clean_compile_frontier; its other listed symbol
source texts are unchanged. Neither compiler may be edited to publish wrappers.
Use the 59b selector unchanged; if actual aggregate performance is inadequate,
stop and report. No U0 caching, aggregate pre-diversity cap or post-59b continuation
API is admitted. The new shadow worklist/parent-child evidence is separately
specified U6 behavior, not an imported D continuation implementation.

## Changed-path inventory by category

A and M in this inventory are Git statuses, not admission classes.
Every path is listed once here and has its exact hunk rows below.

| Category | Paths | Hunks |
|---|---:|---:|
| Repository evidence byte policy | 1 | 1 |
| U0 transition manifest | 1 | 1 |
| Historical evidence and artifacts | 140 | 140 |
| Historical design and plans | 8 | 8 |
| Experiment modules and READMEs | 33 | 33 |
| Historical runners and recovery | 5 | 5 |
| Post-59b production changes | 2 | 68 |
| Tests and oracles | 24 | 34 |
| Total | 214 | 290 |

### Repository evidence byte policy

```text
M .gitattributes (1 hunk)
```

### U0 transition manifest

```text
A config/pr62_u0_clean_compile_frontier_authority_transition.json (1 hunk)
```

### Historical evidence and artifacts

```text
A docs/engine/evidence/PR62_U0_EXACT_COMPILER_SELECTION_PERFORMANCE_EQUIVALENCE.json (1 hunk)
A docs/engine/evidence/PR62_U0_EXACT_COMPILER_SELECTION_PERFORMANCE_EQUIVALENCE.md (1 hunk)
A docs/engine/evidence/PR62_U0_PRE_ADJUDICATION_SELECTOR_PROOF.json (1 hunk)
A docs/engine/evidence/PR62_U0_PRE_ADJUDICATION_SELECTOR_PROOF.md (1 hunk)
A docs/engine/evidence/PR62_U2_SOLVER_BASED_LOCAL_TIMETABLE_REALIZATION_POC.json (1 hunk)
A docs/engine/evidence/PR62_U2_SOLVER_BASED_LOCAL_TIMETABLE_REALIZATION_POC.md (1 hunk)
A docs/engine/evidence/PR62_U3_CP_SAT_DETERMINISTIC_FRONTIER_EXTRACTION_POC.json (1 hunk)
A docs/engine/evidence/PR62_U3_CP_SAT_DETERMINISTIC_FRONTIER_EXTRACTION_POC.md (1 hunk)
A docs/engine/evidence/PR62_U4_CP_SAT_LEXICOGRAPHIC_QUALITY_TIER_FRONTIER_POC.json (1 hunk)
A docs/engine/evidence/PR62_U4_CP_SAT_LEXICOGRAPHIC_QUALITY_TIER_FRONTIER_POC.md (1 hunk)
A docs/engine/evidence/PR62_U_LOCAL_RHYTHM_CANONICALIZATION_SEARCH_INTEGRATION.json (1 hunk)
A docs/engine/evidence/PR62_U_LOCAL_RHYTHM_CANONICALIZATION_SEARCH_INTEGRATION.md (1 hunk)
A docs/engine/evidence/pr62_u2/.gitattributes (1 hunk)
A docs/engine/evidence/pr62_u2/corpus.json (1 hunk)
A docs/engine/evidence/pr62_u2/frozen_outputs.json (1 hunk)
A docs/engine/evidence/pr62_u2/initial_run/corpus.json (1 hunk)
A docs/engine/evidence/pr62_u2/initial_run/frozen_outputs.json (1 hunk)
A docs/engine/evidence/pr62_u2/initial_run/raw.json (1 hunk)
A docs/engine/evidence/pr62_u2/initial_run/result.json (1 hunk)
A docs/engine/evidence/pr62_u2/raw.json (1 hunk)
A docs/engine/evidence/pr62_u2/result.json (1 hunk)
A docs/engine/evidence/pr62_u2/supplemental_outputs.json (1 hunk)
A docs/engine/evidence/pr62_u2/verification.json (1 hunk)
A docs/engine/evidence/pr62_u3/.gitattributes (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/manifest.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/pre_observation_result.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/result.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/domains.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/downstream.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/input.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/optimum.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/phase.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/process.log (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/process_result.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/raw.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/run.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/selected.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_a/shell.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/domains.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/downstream.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/input.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/optimum.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/phase.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/process.log (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/process_result.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/raw.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/run.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/selected.json (1 hunk)
A docs/engine/evidence/pr62_u3/canonical/run_b/shell.json (1 hunk)
A docs/engine/evidence/pr62_u3/fleet_smoke.json (1 hunk)
A docs/engine/evidence/pr62_u3/tests.xml (1 hunk)
A docs/engine/evidence/pr62_u3/verification.json (1 hunk)
A docs/engine/evidence/pr62_u4/.gitattributes (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/pre_observation_result.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/result.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/completed_tiers.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/launch.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/launch/base_model.pbtxt (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/launch/benchmark_manifest.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/launch/domains.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/launch/objective_expressions.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/launch/solver_parameters.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/launch/source_authority.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/launch/state_order.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/launch/variable_order.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/partial_raw.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/phase.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/process.log (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/process_result.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/summary.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/optimization.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/optimization_partial.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/optimization_stage_0_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/optimization_stage_1_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/optimization_stage_2_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/partial_raw.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/raw.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/shell.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/shell.pbtxt (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/tier.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/optimization.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/optimization_partial.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/optimization_stage_0_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/optimization_stage_1_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/optimization_stage_2_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/partial_raw.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/raw.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/shell.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/shell.pbtxt (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/tier.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/optimization.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/optimization_partial.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/optimization_stage_0_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/optimization_stage_1_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/optimization_stage_2_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/partial_raw.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/raw.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/shell.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/shell.pbtxt (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/tier.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/03/optimization_partial.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/03/optimization_stage_0_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_a/tiers/03/optimization_stage_1_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/completed_tiers.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/launch.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/launch/base_model.pbtxt (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/launch/benchmark_manifest.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/launch/domains.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/launch/objective_expressions.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/launch/solver_parameters.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/launch/source_authority.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/launch/state_order.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/launch/variable_order.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/partial_raw.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/phase.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/phase.json.tmp (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/process.log (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/process_result.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/run.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/summary.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/optimization.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/optimization_partial.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/optimization_stage_0_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/optimization_stage_1_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/optimization_stage_2_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/partial_raw.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/raw.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/shell.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/shell.pbtxt (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/tier.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/optimization.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/optimization_partial.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/optimization_stage_0_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/optimization_stage_1_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/optimization_stage_2_delta.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/shell.json (1 hunk)
A docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/shell.pbtxt (1 hunk)
A docs/engine/evidence/pr62_u4/derived_runtime_summary.json (1 hunk)
A docs/engine/evidence/pr62_u4/tests.xml (1 hunk)
A docs/engine/evidence/pr62_u4/verification.json (1 hunk)
```

### Historical design and plans

```text
A docs/superpowers/plans/2026-09-04-pr62-u2-cpsat-local-realization.md (1 hunk)
A docs/superpowers/plans/2026-09-04-pr62-u3-cpsat-frontier-extraction.md (1 hunk)
A docs/superpowers/plans/2026-09-04-pr62-u4-cpsat-quality-tier-frontier.md (1 hunk)
A docs/superpowers/plans/2026-09-04-pr62-u5-kbest-dag-frontier.md (1 hunk)
A docs/superpowers/specs/2026-09-04-pr62-u2-cpsat-local-realization-design.md (1 hunk)
A docs/superpowers/specs/2026-09-04-pr62-u3-cpsat-frontier-extraction-design.md (1 hunk)
A docs/superpowers/specs/2026-09-04-pr62-u4-cpsat-quality-tier-frontier-design.md (1 hunk)
A docs/superpowers/specs/2026-09-04-pr62-u5-kbest-dag-frontier-design.md (1 hunk)
```

### Experiment modules and READMEs

```text
A experiments/pr62_u2_cpsat_local_realization/README.md (1 hunk)
A experiments/pr62_u2_cpsat_local_realization/benchmark.py (1 hunk)
A experiments/pr62_u2_cpsat_local_realization/corpus.py (1 hunk)
A experiments/pr62_u2_cpsat_local_realization/report.py (1 hunk)
A experiments/pr62_u2_cpsat_local_realization/solver.py (1 hunk)
A experiments/pr62_u2_cpsat_local_realization/supplement.py (1 hunk)
A experiments/pr62_u3_cpsat_frontier_extraction/README.md (1 hunk)
A experiments/pr62_u3_cpsat_frontier_extraction/execution.py (1 hunk)
A experiments/pr62_u3_cpsat_frontier_extraction/inputs.py (1 hunk)
A experiments/pr62_u3_cpsat_frontier_extraction/posthoc.py (1 hunk)
A experiments/pr62_u3_cpsat_frontier_extraction/report.py (1 hunk)
A experiments/pr62_u3_cpsat_frontier_extraction/run.py (1 hunk)
A experiments/pr62_u3_cpsat_frontier_extraction/shell.py (1 hunk)
A experiments/pr62_u3_cpsat_frontier_extraction/smoke.py (1 hunk)
A experiments/pr62_u3_cpsat_frontier_extraction/worker.py (1 hunk)
A experiments/pr62_u4_cpsat_quality_tier_frontier/README.md (1 hunk)
A experiments/pr62_u4_cpsat_quality_tier_frontier/authority.py (1 hunk)
A experiments/pr62_u4_cpsat_quality_tier_frontier/evaluation.py (1 hunk)
A experiments/pr62_u4_cpsat_quality_tier_frontier/execution.py (1 hunk)
A experiments/pr62_u4_cpsat_quality_tier_frontier/posthoc.py (1 hunk)
A experiments/pr62_u4_cpsat_quality_tier_frontier/report.py (1 hunk)
A experiments/pr62_u4_cpsat_quality_tier_frontier/run.py (1 hunk)
A experiments/pr62_u4_cpsat_quality_tier_frontier/tiers.py (1 hunk)
A experiments/pr62_u4_cpsat_quality_tier_frontier/worker.py (1 hunk)
A experiments/pr62_u5_kbest_dag_frontier/README.md (1 hunk)
A experiments/pr62_u5_kbest_dag_frontier/authority.py (1 hunk)
A experiments/pr62_u5_kbest_dag_frontier/evaluation.py (1 hunk)
A experiments/pr62_u5_kbest_dag_frontier/execution.py (1 hunk)
A experiments/pr62_u5_kbest_dag_frontier/kbest.py (1 hunk)
A experiments/pr62_u5_kbest_dag_frontier/posthoc.py (1 hunk)
A experiments/pr62_u5_kbest_dag_frontier/report.py (1 hunk)
A experiments/pr62_u5_kbest_dag_frontier/run.py (1 hunk)
A experiments/pr62_u5_kbest_dag_frontier/worker.py (1 hunk)
```

### Historical runners and recovery

```text
A scripts/pr62_u0_compiler_authority.py (1 hunk)
A scripts/pr62_u_local_recovery.py (1 hunk)
A scripts/run_pr62_u0_exact_compiler_selection_performance_equivalence.py (1 hunk)
A scripts/run_pr62_u_local_recovery.py (1 hunk)
A scripts/run_pr62_u_local_rhythm_search_integration.py (1 hunk)
```

### Post-59b production changes

```text
M src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py (9 hunks)
M src/bus_schedule_engine/local_rhythm_refinement.py (59 hunks)
```

### Tests and oracles

```text
A tests/experiments/test_pr62_u2_benchmark.py (1 hunk)
A tests/experiments/test_pr62_u2_corpus.py (1 hunk)
A tests/experiments/test_pr62_u2_report.py (1 hunk)
A tests/experiments/test_pr62_u2_solver.py (1 hunk)
A tests/experiments/test_pr62_u2_supplement.py (1 hunk)
A tests/experiments/test_pr62_u3_execution.py (1 hunk)
A tests/experiments/test_pr62_u3_report.py (1 hunk)
A tests/experiments/test_pr62_u3_shell.py (1 hunk)
A tests/experiments/test_pr62_u4_evaluation.py (1 hunk)
A tests/experiments/test_pr62_u4_execution.py (1 hunk)
A tests/experiments/test_pr62_u4_report.py (1 hunk)
A tests/experiments/test_pr62_u4_tiers.py (1 hunk)
A tests/experiments/test_pr62_u5_authority.py (1 hunk)
A tests/experiments/test_pr62_u5_evaluation.py (1 hunk)
A tests/experiments/test_pr62_u5_execution.py (1 hunk)
A tests/experiments/test_pr62_u5_kbest.py (1 hunk)
A tests/experiments/test_pr62_u5_report.py (1 hunk)
A tests/pr62_u0_selection_oracle.py (1 hunk)
A tests/test_clean_compile_frontier_selection_equivalence.py (1 hunk)
A tests/test_local_recovery.py (1 hunk)
M tests/test_local_rhythm_refinement.py (11 hunks)
A tests/test_pr62_u0_compiler_authority_transition.py (1 hunk)
A tests/test_pr62_u_local_recovery_runner.py (1 hunk)
A tests/test_pr62_u_local_rhythm_search_integration.py (1 hunk)
```

## Exact zero-context hunk decisions

Admission totals: A = 1, B = 19, C = 192, D = 78.
Single-add C evidence files have one file-level decision; every modified/mixed
file retains one row per literal Git hunk. Symbol boundaries do not add hunk keys.

| Hunk | Path | Git hunk | Class | Dependency | U6 decision |
|---|---|---|---|---|---|
| H001 | .gitattributes | @@ -1,0 +2,2 @@ docs/engine/evidence/*.json -text | C. TEST_OR_EVIDENCE_ONLY | Evidence byte-preservation rules only | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H002 | config/pr62_u0_clean_compile_frontier_authority_transition.json | @@ -0,0 +1,24 @@ | C. TEST_OR_EVIDENCE_ONLY | Manifest documenting D U0 compiler-authority transition | Evidence only; reject U0 authority transition and preserve 59b compiler bytes. |
| H003 | docs/engine/evidence/PR62_U0_EXACT_COMPILER_SELECTION_PERFORMANCE_EQUIVALENCE.json | @@ -0,0 +1,3391 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H004 | docs/engine/evidence/PR62_U0_EXACT_COMPILER_SELECTION_PERFORMANCE_EQUIVALENCE.md | @@ -0,0 +1,160 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H005 | docs/engine/evidence/PR62_U0_PRE_ADJUDICATION_SELECTOR_PROOF.json | @@ -0,0 +1,1391 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H006 | docs/engine/evidence/PR62_U0_PRE_ADJUDICATION_SELECTOR_PROOF.md | @@ -0,0 +1,87 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H007 | docs/engine/evidence/PR62_U2_SOLVER_BASED_LOCAL_TIMETABLE_REALIZATION_POC.json | @@ -0,0 +1,1642 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H008 | docs/engine/evidence/PR62_U2_SOLVER_BASED_LOCAL_TIMETABLE_REALIZATION_POC.md | @@ -0,0 +1,81 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H009 | docs/engine/evidence/PR62_U3_CP_SAT_DETERMINISTIC_FRONTIER_EXTRACTION_POC.json | @@ -0,0 +1,831 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H010 | docs/engine/evidence/PR62_U3_CP_SAT_DETERMINISTIC_FRONTIER_EXTRACTION_POC.md | @@ -0,0 +1,91 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H011 | docs/engine/evidence/PR62_U4_CP_SAT_LEXICOGRAPHIC_QUALITY_TIER_FRONTIER_POC.json | @@ -0,0 +1,2414 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H012 | docs/engine/evidence/PR62_U4_CP_SAT_LEXICOGRAPHIC_QUALITY_TIER_FRONTIER_POC.md | @@ -0,0 +1,125 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H013 | docs/engine/evidence/PR62_U_LOCAL_RHYTHM_CANONICALIZATION_SEARCH_INTEGRATION.json | @@ -0,0 +1,2295 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H014 | docs/engine/evidence/PR62_U_LOCAL_RHYTHM_CANONICALIZATION_SEARCH_INTEGRATION.md | @@ -0,0 +1,20 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H015 | docs/engine/evidence/pr62_u2/.gitattributes | @@ -0,0 +1 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H016 | docs/engine/evidence/pr62_u2/corpus.json | @@ -0,0 +1,9088 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H017 | docs/engine/evidence/pr62_u2/frozen_outputs.json | @@ -0,0 +1,15656 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H018 | docs/engine/evidence/pr62_u2/initial_run/corpus.json | @@ -0,0 +1,9038 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H019 | docs/engine/evidence/pr62_u2/initial_run/frozen_outputs.json | @@ -0,0 +1,14890 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H020 | docs/engine/evidence/pr62_u2/initial_run/raw.json | @@ -0,0 +1,3985 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H021 | docs/engine/evidence/pr62_u2/initial_run/result.json | @@ -0,0 +1,13103 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H022 | docs/engine/evidence/pr62_u2/raw.json | @@ -0,0 +1,4284 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H023 | docs/engine/evidence/pr62_u2/result.json | @@ -0,0 +1,13461 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H024 | docs/engine/evidence/pr62_u2/supplemental_outputs.json | @@ -0,0 +1,1010 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H025 | docs/engine/evidence/pr62_u2/verification.json | @@ -0,0 +1,34 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H026 | docs/engine/evidence/pr62_u3/.gitattributes | @@ -0,0 +1,2 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H027 | docs/engine/evidence/pr62_u3/canonical/manifest.json | @@ -0,0 +1,234 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H028 | docs/engine/evidence/pr62_u3/canonical/pre_observation_result.json | @@ -0,0 +1,304776 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H029 | docs/engine/evidence/pr62_u3/canonical/result.json | @@ -0,0 +1,304814 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H030 | docs/engine/evidence/pr62_u3/canonical/run_a/domains.json | @@ -0,0 +1,430885 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H031 | docs/engine/evidence/pr62_u3/canonical/run_a/downstream.json | @@ -0,0 +1,719 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H032 | docs/engine/evidence/pr62_u3/canonical/run_a/input.json | @@ -0,0 +1,234 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H033 | docs/engine/evidence/pr62_u3/canonical/run_a/optimum.json | @@ -0,0 +1,139 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H034 | docs/engine/evidence/pr62_u3/canonical/run_a/phase.json | @@ -0,0 +1,4 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H035 | docs/engine/evidence/pr62_u3/canonical/run_a/process.log | @@ -0,0 +1 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H036 | docs/engine/evidence/pr62_u3/canonical/run_a/process_result.json | @@ -0,0 +1,152259 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H037 | docs/engine/evidence/pr62_u3/canonical/run_a/raw.json | @@ -0,0 +1,93 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H038 | docs/engine/evidence/pr62_u3/canonical/run_a/run.json | @@ -0,0 +1,152254 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H039 | docs/engine/evidence/pr62_u3/canonical/run_a/selected.json | @@ -0,0 +1,93 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H040 | docs/engine/evidence/pr62_u3/canonical/run_a/shell.json | @@ -0,0 +1,152062 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H041 | docs/engine/evidence/pr62_u3/canonical/run_b/domains.json | @@ -0,0 +1,430885 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H042 | docs/engine/evidence/pr62_u3/canonical/run_b/downstream.json | @@ -0,0 +1,719 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H043 | docs/engine/evidence/pr62_u3/canonical/run_b/input.json | @@ -0,0 +1,234 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H044 | docs/engine/evidence/pr62_u3/canonical/run_b/optimum.json | @@ -0,0 +1,139 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H045 | docs/engine/evidence/pr62_u3/canonical/run_b/phase.json | @@ -0,0 +1,4 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H046 | docs/engine/evidence/pr62_u3/canonical/run_b/process.log | @@ -0,0 +1 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H047 | docs/engine/evidence/pr62_u3/canonical/run_b/process_result.json | @@ -0,0 +1,152259 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H048 | docs/engine/evidence/pr62_u3/canonical/run_b/raw.json | @@ -0,0 +1,93 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H049 | docs/engine/evidence/pr62_u3/canonical/run_b/run.json | @@ -0,0 +1,152254 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H050 | docs/engine/evidence/pr62_u3/canonical/run_b/selected.json | @@ -0,0 +1,93 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H051 | docs/engine/evidence/pr62_u3/canonical/run_b/shell.json | @@ -0,0 +1,152062 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H052 | docs/engine/evidence/pr62_u3/fleet_smoke.json | @@ -0,0 +1,47 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H053 | docs/engine/evidence/pr62_u3/tests.xml | @@ -0,0 +1 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H054 | docs/engine/evidence/pr62_u3/verification.json | @@ -0,0 +1,58 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H055 | docs/engine/evidence/pr62_u4/.gitattributes | @@ -0,0 +1,4 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H056 | docs/engine/evidence/pr62_u4/canonical/pre_observation_result.json | @@ -0,0 +1,2117 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H057 | docs/engine/evidence/pr62_u4/canonical/result.json | @@ -0,0 +1,2208 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H058 | docs/engine/evidence/pr62_u4/canonical/run_a/completed_tiers.json | @@ -0,0 +1,187 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H059 | docs/engine/evidence/pr62_u4/canonical/run_a/launch.json | @@ -0,0 +1,614 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H060 | docs/engine/evidence/pr62_u4/canonical/run_a/launch/base_model.pbtxt | @@ -0,0 +1,793224 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H061 | docs/engine/evidence/pr62_u4/canonical/run_a/launch/benchmark_manifest.json | @@ -0,0 +1,234 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H062 | docs/engine/evidence/pr62_u4/canonical/run_a/launch/domains.json | @@ -0,0 +1,430885 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H063 | docs/engine/evidence/pr62_u4/canonical/run_a/launch/objective_expressions.json | @@ -0,0 +1,152050 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H064 | docs/engine/evidence/pr62_u4/canonical/run_a/launch/solver_parameters.json | @@ -0,0 +1,21 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H065 | docs/engine/evidence/pr62_u4/canonical/run_a/launch/source_authority.json | @@ -0,0 +1,507 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H066 | docs/engine/evidence/pr62_u4/canonical/run_a/launch/state_order.json | @@ -0,0 +1,51 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H067 | docs/engine/evidence/pr62_u4/canonical/run_a/launch/variable_order.json | @@ -0,0 +1,263914 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H068 | docs/engine/evidence/pr62_u4/canonical/run_a/partial_raw.json | @@ -0,0 +1,341 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H069 | docs/engine/evidence/pr62_u4/canonical/run_a/phase.json | @@ -0,0 +1,5 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H070 | docs/engine/evidence/pr62_u4/canonical/run_a/process.log | @@ -0,0 +1,3 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H071 | docs/engine/evidence/pr62_u4/canonical/run_a/process_result.json | @@ -0,0 +1,13 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H072 | docs/engine/evidence/pr62_u4/canonical/run_a/summary.json | @@ -0,0 +1,1187 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H073 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/optimization.json | @@ -0,0 +1,44 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H074 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/optimization_partial.json | @@ -0,0 +1,29 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H075 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/optimization_stage_0_delta.json | @@ -0,0 +1,10 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H076 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/optimization_stage_1_delta.json | @@ -0,0 +1,12 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H077 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/optimization_stage_2_delta.json | @@ -0,0 +1,13 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H078 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/partial_raw.json | @@ -0,0 +1,109 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H079 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/raw.json | @@ -0,0 +1,109 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H080 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/shell.json | @@ -0,0 +1,14 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H081 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/shell.pbtxt | @@ -0,0 +1,1209182 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H082 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/00/tier.json | @@ -0,0 +1,59 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H083 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/optimization.json | @@ -0,0 +1,52 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H084 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/optimization_partial.json | @@ -0,0 +1,29 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H085 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/optimization_stage_0_delta.json | @@ -0,0 +1,14 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H086 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/optimization_stage_1_delta.json | @@ -0,0 +1,16 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H087 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/optimization_stage_2_delta.json | @@ -0,0 +1,17 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H088 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/partial_raw.json | @@ -0,0 +1,109 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H089 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/raw.json | @@ -0,0 +1,109 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H090 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/shell.json | @@ -0,0 +1,14 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H091 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/shell.pbtxt | @@ -0,0 +1,1209182 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H092 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/01/tier.json | @@ -0,0 +1,63 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H093 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/optimization.json | @@ -0,0 +1,52 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H094 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/optimization_partial.json | @@ -0,0 +1,29 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H095 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/optimization_stage_0_delta.json | @@ -0,0 +1,14 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H096 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/optimization_stage_1_delta.json | @@ -0,0 +1,16 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H097 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/optimization_stage_2_delta.json | @@ -0,0 +1,17 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H098 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/partial_raw.json | @@ -0,0 +1,109 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H099 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/raw.json | @@ -0,0 +1,109 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H100 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/shell.json | @@ -0,0 +1,14 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H101 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/shell.pbtxt | @@ -0,0 +1,1209182 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H102 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/02/tier.json | @@ -0,0 +1,63 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H103 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/03/optimization_partial.json | @@ -0,0 +1,11 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H104 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/03/optimization_stage_0_delta.json | @@ -0,0 +1,14 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H105 | docs/engine/evidence/pr62_u4/canonical/run_a/tiers/03/optimization_stage_1_delta.json | @@ -0,0 +1,16 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H106 | docs/engine/evidence/pr62_u4/canonical/run_b/completed_tiers.json | @@ -0,0 +1,61 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H107 | docs/engine/evidence/pr62_u4/canonical/run_b/launch.json | @@ -0,0 +1,614 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H108 | docs/engine/evidence/pr62_u4/canonical/run_b/launch/base_model.pbtxt | @@ -0,0 +1,793224 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H109 | docs/engine/evidence/pr62_u4/canonical/run_b/launch/benchmark_manifest.json | @@ -0,0 +1,234 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H110 | docs/engine/evidence/pr62_u4/canonical/run_b/launch/domains.json | @@ -0,0 +1,430885 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H111 | docs/engine/evidence/pr62_u4/canonical/run_b/launch/objective_expressions.json | @@ -0,0 +1,152050 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H112 | docs/engine/evidence/pr62_u4/canonical/run_b/launch/solver_parameters.json | @@ -0,0 +1,21 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H113 | docs/engine/evidence/pr62_u4/canonical/run_b/launch/source_authority.json | @@ -0,0 +1,507 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H114 | docs/engine/evidence/pr62_u4/canonical/run_b/launch/state_order.json | @@ -0,0 +1,51 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H115 | docs/engine/evidence/pr62_u4/canonical/run_b/launch/variable_order.json | @@ -0,0 +1,263914 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H116 | docs/engine/evidence/pr62_u4/canonical/run_b/partial_raw.json | @@ -0,0 +1,115 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H117 | docs/engine/evidence/pr62_u4/canonical/run_b/phase.json | @@ -0,0 +1,5 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H118 | docs/engine/evidence/pr62_u4/canonical/run_b/phase.json.tmp | @@ -0,0 +1,5 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H119 | docs/engine/evidence/pr62_u4/canonical/run_b/process.log | @@ -0,0 +1,24 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H120 | docs/engine/evidence/pr62_u4/canonical/run_b/process_result.json | @@ -0,0 +1,16 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H121 | docs/engine/evidence/pr62_u4/canonical/run_b/run.json | @@ -0,0 +1,6 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H122 | docs/engine/evidence/pr62_u4/canonical/run_b/summary.json | @@ -0,0 +1,912 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H123 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/optimization.json | @@ -0,0 +1,44 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H124 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/optimization_partial.json | @@ -0,0 +1,29 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H125 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/optimization_stage_0_delta.json | @@ -0,0 +1,10 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H126 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/optimization_stage_1_delta.json | @@ -0,0 +1,12 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H127 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/optimization_stage_2_delta.json | @@ -0,0 +1,13 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H128 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/partial_raw.json | @@ -0,0 +1,109 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H129 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/raw.json | @@ -0,0 +1,109 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H130 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/shell.json | @@ -0,0 +1,14 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H131 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/shell.pbtxt | @@ -0,0 +1,1209182 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H132 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/00/tier.json | @@ -0,0 +1,59 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H133 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/optimization.json | @@ -0,0 +1,52 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H134 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/optimization_partial.json | @@ -0,0 +1,29 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H135 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/optimization_stage_0_delta.json | @@ -0,0 +1,14 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H136 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/optimization_stage_1_delta.json | @@ -0,0 +1,16 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H137 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/optimization_stage_2_delta.json | @@ -0,0 +1,17 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H138 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/shell.json | @@ -0,0 +1,14 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H139 | docs/engine/evidence/pr62_u4/canonical/run_b/tiers/01/shell.pbtxt | @@ -0,0 +1,1209182 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H140 | docs/engine/evidence/pr62_u4/derived_runtime_summary.json | @@ -0,0 +1,143 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H141 | docs/engine/evidence/pr62_u4/tests.xml | @@ -0,0 +1 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H142 | docs/engine/evidence/pr62_u4/verification.json | @@ -0,0 +1,203 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H143 | docs/superpowers/plans/2026-09-04-pr62-u2-cpsat-local-realization.md | @@ -0,0 +1,55 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H144 | docs/superpowers/plans/2026-09-04-pr62-u3-cpsat-frontier-extraction.md | @@ -0,0 +1,62 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H145 | docs/superpowers/plans/2026-09-04-pr62-u4-cpsat-quality-tier-frontier.md | @@ -0,0 +1,59 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H146 | docs/superpowers/plans/2026-09-04-pr62-u5-kbest-dag-frontier.md | @@ -0,0 +1,41 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H147 | docs/superpowers/specs/2026-09-04-pr62-u2-cpsat-local-realization-design.md | @@ -0,0 +1,37 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H148 | docs/superpowers/specs/2026-09-04-pr62-u3-cpsat-frontier-extraction-design.md | @@ -0,0 +1,41 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H149 | docs/superpowers/specs/2026-09-04-pr62-u4-cpsat-quality-tier-frontier-design.md | @@ -0,0 +1,52 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H150 | docs/superpowers/specs/2026-09-04-pr62-u5-kbest-dag-frontier-design.md | @@ -0,0 +1,23 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H151 | experiments/pr62_u2_cpsat_local_realization/README.md | @@ -0,0 +1,27 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H152 | experiments/pr62_u2_cpsat_local_realization/benchmark.py | @@ -0,0 +1,403 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H153 | experiments/pr62_u2_cpsat_local_realization/corpus.py | @@ -0,0 +1,290 @@ | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Post-59b checkpoint/pickle/digest loaders and local-family regeneration authority | Reject production import and checkpoint reads/resume; future parity fixture contains only frozen states, endpoint authority and semantic expectations; U6 runtime accepts caller-owned ServicePlanStateV1 values. |
| H154 | experiments/pr62_u2_cpsat_local_realization/report.py | @@ -0,0 +1,274 @@ | C. TEST_OR_EVIDENCE_ONLY | Evidence-only assemble/render/write functions; no algorithmic runtime authority | Do not import or port renderer to production; retain as read-only evidence. New U6 evidence rendering is separately specified. |
| H155 | experiments/pr62_u2_cpsat_local_realization/solver.py | @@ -0,0 +1,331 @@ | B. EXPERIMENT_ONLY | Mixed single add hunk: CP-SAT imports 13-14, objects 30-63, scaling 140-191, solve_pool 194-331; graph_domain 66-101/build_domain 104-137 are algorithmic reference only | Reject whole module and CP-SAT objects. Re-express A graph compatibility/reachability/domain behavior in private U6 dataclasses using 59b _phase_candidates, _candidate_path, _bounded_phase_candidates, _regimes_from_state; decode through 59b _FrontierPath/_compilation_from_path. See A behavior boundary. |
| H156 | experiments/pr62_u2_cpsat_local_realization/supplement.py | @@ -0,0 +1,221 @@ | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Post-59b checkpoint/pickle/digest loaders and local-family regeneration authority | Reject production import and checkpoint reads/resume; future parity fixture contains only frozen states, endpoint authority and semantic expectations; U6 runtime accepts caller-owned ServicePlanStateV1 values. |
| H157 | experiments/pr62_u3_cpsat_frontier_extraction/README.md | @@ -0,0 +1,40 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H158 | experiments/pr62_u3_cpsat_frontier_extraction/execution.py | @@ -0,0 +1,116 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H159 | experiments/pr62_u3_cpsat_frontier_extraction/inputs.py | @@ -0,0 +1,112 @@ | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Post-59b checkpoint/pickle/digest loaders and local-family regeneration authority | Reject production import and checkpoint reads/resume; future parity fixture contains only frozen states, endpoint authority and semantic expectations; U6 runtime accepts caller-owned ServicePlanStateV1 values. |
| H160 | experiments/pr62_u3_cpsat_frontier_extraction/posthoc.py | @@ -0,0 +1,35 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H161 | experiments/pr62_u3_cpsat_frontier_extraction/report.py | @@ -0,0 +1,172 @@ | C. TEST_OR_EVIDENCE_ONLY | Evidence-only assemble/render/write functions; no algorithmic runtime authority | Do not import or port renderer to production; retain as read-only evidence. New U6 evidence rendering is separately specified. |
| H162 | experiments/pr62_u3_cpsat_frontier_extraction/run.py | @@ -0,0 +1,108 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H163 | experiments/pr62_u3_cpsat_frontier_extraction/shell.py | @@ -0,0 +1,332 @@ | B. EXPERIMENT_ONLY | Mixed single add hunk: CP-SAT import/capture/optimum/shell/enumeration; U2 object dependency; _path/_objective/_decode/canonical_record 140-199 | Reject exact-shell module/objects and U3 selection. Re-express A path decoding with 59b _FrontierPath/_compilation_from_path; replace canonical_record by explicit U6 semantic candidate fields and a test-only U5 parity serializer; unchanged 59b selector after U6 hard eligibility. |
| H164 | experiments/pr62_u3_cpsat_frontier_extraction/smoke.py | @@ -0,0 +1,67 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H165 | experiments/pr62_u3_cpsat_frontier_extraction/worker.py | @@ -0,0 +1,174 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H166 | experiments/pr62_u4_cpsat_quality_tier_frontier/README.md | @@ -0,0 +1,18 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H167 | experiments/pr62_u4_cpsat_quality_tier_frontier/authority.py | @@ -0,0 +1,155 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H168 | experiments/pr62_u4_cpsat_quality_tier_frontier/evaluation.py | @@ -0,0 +1,184 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H169 | experiments/pr62_u4_cpsat_quality_tier_frontier/execution.py | @@ -0,0 +1,84 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H170 | experiments/pr62_u4_cpsat_quality_tier_frontier/posthoc.py | @@ -0,0 +1,50 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H171 | experiments/pr62_u4_cpsat_quality_tier_frontier/report.py | @@ -0,0 +1,185 @@ | C. TEST_OR_EVIDENCE_ONLY | Evidence-only assemble/render/write functions; no algorithmic runtime authority | Do not import or port renderer to production; retain as read-only evidence. New U6 evidence rendering is separately specified. |
| H172 | experiments/pr62_u4_cpsat_quality_tier_frontier/run.py | @@ -0,0 +1,155 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H173 | experiments/pr62_u4_cpsat_quality_tier_frontier/tiers.py | @@ -0,0 +1,199 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H174 | experiments/pr62_u4_cpsat_quality_tier_frontier/worker.py | @@ -0,0 +1,314 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H175 | experiments/pr62_u5_kbest_dag_frontier/README.md | @@ -0,0 +1,4 @@ | C. TEST_OR_EVIDENCE_ONLY | Single-add historical evidence, artifact, manifest, README, design or plan; no runtime dependency | Read-only evidence; no production import, cherry-pick, historical reclassification or artifact modification. |
| H176 | experiments/pr62_u5_kbest_dag_frontier/authority.py | @@ -0,0 +1,269 @@ | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Imports U2 and U3 inputs 12-14, whose load_family reads post-59b checkpoints; source_authority/prepare bind recovery and U4 authorities | Reject imports and launch/file authority code 25-69/204-269. Re-express A build_domains_timed graph behavior 72-123 with private U6 domain and 59b builders; graph_manifests 126-201 is C evidence behavior, not runtime authority. |
| H177 | experiments/pr62_u5_kbest_dag_frontier/evaluation.py | @@ -0,0 +1,222 @@ | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Imports post-59b U0 selector 8-11 and U3 _path 12; selection 93-110 occurs before downstream 117-188 in worker; parity/rendering gates are evidence | Reject inherited orchestration/imports and U0 selector. Use 59b structural/protection/metrics/tail authorities before aggregate diversity, then 59b exact pair/fleet evaluation. Parity/tier assertions 17-54 are test-only; classification 191-222 is experiment-only. |
| H178 | experiments/pr62_u5_kbest_dag_frontier/execution.py | @@ -0,0 +1,110 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H179 | experiments/pr62_u5_kbest_dag_frontier/kbest.py | @@ -0,0 +1,332 @@ | A. K_BEST_DAG_CORE | D dependency: U2 Domain/Solution, U3 canonical_record and benchmark.exact_objective; exclude imports line 15/218/294, experiment dataclasses lines 20-63, and generation callback lines 250/288-289 (see symbol boundary below) | Re-express scoring/merge/retention/terminal/decode behavior with U6 frozen slotted candidate, frontier, statistics and telemetry dataclasses plus a private U6 partial path/domain. Production equivalent: 59b _FrontierPath, _compilation_from_path and fingerprint/validation builders. No experiment imports, callback, synthetic-domain hash fallback, or experiment result fields. |
| H180 | experiments/pr62_u5_kbest_dag_frontier/posthoc.py | @@ -0,0 +1,44 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H181 | experiments/pr62_u5_kbest_dag_frontier/report.py | @@ -0,0 +1,121 @@ | C. TEST_OR_EVIDENCE_ONLY | Evidence-only assemble/render/write functions; no algorithmic runtime authority | Do not import or port renderer to production; retain as read-only evidence. New U6 evidence rendering is separately specified. |
| H182 | experiments/pr62_u5_kbest_dag_frontier/run.py | @@ -0,0 +1,135 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H183 | experiments/pr62_u5_kbest_dag_frontier/worker.py | @@ -0,0 +1,163 @@ | B. EXPERIMENT_ONLY | Experiment harness: solver/tier extraction, subprocess/watchdog, write-once, orchestration, posthoc-Q or benchmark reporting | Reject runtime import and all harness/CP-SAT/Q behavior; use only separately documented 59b production authorities and A semantic equivalents. |
| H184 | scripts/pr62_u0_compiler_authority.py | @@ -0,0 +1,107 @@ | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Post-59b U0 authority transition, recovery/checkpoint or local continuation runner | Reject whole historical runner/helper; no recovery, global rerun, certification/Q authority or U0 transition enters U6 runtime. |
| H185 | scripts/pr62_u_local_recovery.py | @@ -0,0 +1,400 @@ | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Post-59b U0 authority transition, recovery/checkpoint or local continuation runner | Reject whole historical runner/helper; no recovery, global rerun, certification/Q authority or U0 transition enters U6 runtime. |
| H186 | scripts/run_pr62_u0_exact_compiler_selection_performance_equivalence.py | @@ -0,0 +1,461 @@ | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | U0 selector optimization proof runner and post-59b selector imports | Reject U0 optimization/proof runner in production; historical performance evidence remains read-only. |
| H187 | scripts/run_pr62_u_local_recovery.py | @@ -0,0 +1,356 @@ | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Post-59b U0 authority transition, recovery/checkpoint or local continuation runner | Reject whole historical runner/helper; no recovery, global rerun, certification/Q authority or U0 transition enters U6 runtime. |
| H188 | scripts/run_pr62_u_local_rhythm_search_integration.py | @@ -0,0 +1,1518 @@ | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Post-59b U0 authority transition, recovery/checkpoint or local continuation runner | Reject whole historical runner/helper; no recovery, global rerun, certification/Q authority or U0 transition enters U6 runtime. |
| H189 | src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py | @@ -119,0 +120,7 @@ def _select_diverse_paths( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | U0 _select_diverse_paths cached projections/incremental nearest-distance optimization | Reject every U0 optimization hunk; production equivalent is unchanged 59b _select_diverse_paths (lines 108-176); measure actual eligible aggregate and stop if inadequate. |
| H190 | src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py | @@ -124 +131 @@ def _select_diverse_paths( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | U0 _select_diverse_paths cached projections/incremental nearest-distance optimization | Reject every U0 optimization hunk; production equivalent is unchanged 59b _select_diverse_paths (lines 108-176); measure actual eligible aggregate and stop if inadequate. |
| H191 | src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py | @@ -127 +134,31 @@ def _select_diverse_paths( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | U0 _select_diverse_paths cached projections/incremental nearest-distance optimization | Reject every U0 optimization hunk; production equivalent is unchanged 59b _select_diverse_paths (lines 108-176); measure actual eligible aggregate and stop if inadequate. |
| H192 | src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py | @@ -132 +169 @@ def _select_diverse_paths( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | U0 _select_diverse_paths cached projections/incremental nearest-distance optimization | Reject every U0 optimization hunk; production equivalent is unchanged 59b _select_diverse_paths (lines 108-176); measure actual eligible aggregate and stop if inadequate. |
| H193 | src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py | @@ -143 +180 @@ def _select_diverse_paths( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | U0 _select_diverse_paths cached projections/incremental nearest-distance optimization | Reject every U0 optimization hunk; production equivalent is unchanged 59b _select_diverse_paths (lines 108-176); measure actual eligible aggregate and stop if inadequate. |
| H194 | src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py | @@ -147 +184 @@ def _select_diverse_paths( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | U0 _select_diverse_paths cached projections/incremental nearest-distance optimization | Reject every U0 optimization hunk; production equivalent is unchanged 59b _select_diverse_paths (lines 108-176); measure actual eligible aggregate and stop if inadequate. |
| H195 | src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py | @@ -149,11 +186 @@ def _select_diverse_paths( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | U0 _select_diverse_paths cached projections/incremental nearest-distance optimization | Reject every U0 optimization hunk; production equivalent is unchanged 59b _select_diverse_paths (lines 108-176); measure actual eligible aggregate and stop if inadequate. |
| H196 | src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py | @@ -163 +190 @@ def _select_diverse_paths( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | U0 _select_diverse_paths cached projections/incremental nearest-distance optimization | Reject every U0 optimization hunk; production equivalent is unchanged 59b _select_diverse_paths (lines 108-176); measure actual eligible aggregate and stop if inadequate. |
| H197 | src/bus_schedule_engine/contracts_v1/clean_compile_frontier.py | @@ -165,11 +192 @@ def _select_diverse_paths( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | U0 _select_diverse_paths cached projections/incremental nearest-distance optimization | Reject every U0 optimization hunk; production equivalent is unchanged 59b _select_diverse_paths (lines 108-176); measure actual eligible aggregate and stop if inadequate. |
| H198 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -6,0 +7 @@ from collections.abc import Sequence | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | ContextVar recovery import | Reject recovery hook infrastructure; keep 59b imports. |
| H199 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -37,0 +39 @@ LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING = "LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_B | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Later compile-failure classification | Reject classification change; no legacy entry-point rewrite. |
| H200 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -43,0 +46,41 @@ LOCAL_RHYTHM_REFINEMENT_COMPLETE = "LOCAL_RHYTHM_REFINEMENT_COMPLETE" | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Recovery hook and checkpoint_* functions, lines 46-85 | Reject all checkpoint/recovery behavior; no production equivalent required. |
| H201 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -93,0 +137,12 @@ DEFAULT_LOCAL_RHYTHM_REFINEMENT_POLICY_V1 = LocalRhythmRefinementPolicyV1() | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | LocalCompilerCallTelemetryV1 | Reject inherited telemetry dataclass; U6 owns its specified DAG/shadow telemetry. |
| H202 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -104,0 +160,3 @@ class DirectionalLocalCompileResultV1: | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Later directional compile telemetry fields | Reject changes to legacy result contract. |
| H203 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -115,0 +174,3 @@ class PairCrossProductResultV1: | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Later accepted-descendant witness result field | Reject inherited result change; U6 shadow records its own parent/child evidence from the approved specification. |
| H204 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -143,0 +205,7 @@ class SourcePairRefinementV1: | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Later source telemetry and descendant fields | Reject inherited result changes; keep 59b source contract. |
| H205 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -203,0 +272,7 @@ class LocalRhythmRefinementStatisticsV1: | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Later aggregate compiler telemetry fields | Reject legacy statistics expansion. |
| H206 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -216,0 +292,2 @@ class LocalRhythmRefinementResultV1: | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Later result source/telemetry fields | Reject legacy result expansion. |
| H207 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -246 +323 @@ def detect_local_rhythm_families_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Overlapping-family detector docstring change | Reject; preserve 59b non-overlapping detector semantics. |
| H208 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -265 +342 @@ def detect_local_rhythm_families_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Overlapping maximal-family guard | Reject; use 59b detect_local_rhythm_families_v1. |
| H209 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -288 +365 @@ def detect_local_rhythm_families_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Overlapping-family scan increment | Reject; preserve 59b index = end behavior. |
| H210 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -298,0 +376,4 @@ def map_actual_family_to_planning_indices_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Later demand-ID lookup mapping | Reject; use 59b map_actual_family_to_planning_indices_v1. |
| H211 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -300 +381,3 @@ def map_actual_family_to_planning_indices_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Later mapping lookup comprehension | Reject; preserve 59b ordered demand-slice enumeration. |
| H212 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -304,0 +388 @@ def map_actual_family_to_planning_indices_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Later duplicate-demand-ID mapping guard | Reject unrelated mapping-contract change. |
| H213 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -346,0 +431,17 @@ def _merged_family_state_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Endpoint preflight plus checkpoint_endpoint_rejection side effect, lines 431-445 | SOLE NARROW D BEHAVIOR: re-express first.start <= fixed_first_departure < first.end and final.start <= fixed_last_departure < final.end as a pure U6 preflight before DAG construction; RED-to-GREEN tests in the implementation task; reject checkpoint call at lines 443-444. |
| H214 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -362,0 +464,7 @@ def enumerate_local_rhythm_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | No-external-side validation plus endpoint predicate | Reject new no-side generation behavior; only the same pure endpoint predicate is admitted for U6 preflight, not merged-state admission. |
| H215 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -364,2 +472,2 @@ def enumerate_local_rhythm_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | No-external-side merged-state admission and revised statistics | Reject; retain 59b empty no-side state set and statistics. |
| H216 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -400 +508 @@ def enumerate_local_rhythm_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Endpoint eligibility call in ordinary generated-state loop | Re-express only the same sole endpoint invariant before DAG construction; no checkpoint or compiler-failure semantics. |
| H217 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -418,3 +526,10 @@ def actual_micro_rhythm_boundary_count_v1(compilation: Any) -> int: | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Overlapping-family boundary deduplication | Reject; preserve 59b actual_micro_rhythm_boundary_count_v1. |
| H218 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -458,0 +574 @@ def compile_local_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Compiler pruning/rejection counters | Reject later legacy compiler telemetry. |
| H219 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -461 +577,2 @@ def compile_local_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Indexed compiler loop and telemetry collection | Reject runner-cursor/telemetry additions. |
| H220 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -463 +580,3 @@ def compile_local_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | checkpoint_scope and checkpoint_compile wrapper | Reject hooks; U6 invokes its explicit DAG API. |
| H221 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -468,0 +588,3 @@ def compile_local_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Compiler internal pruning and call candidates | Reject later compiler accounting. |
| H222 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -502,0 +625,29 @@ def compile_local_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Per-call lineage, strict filtering observation, checkpoint_after_call | Reject historical compiler-call telemetry and checkpoint; use unchanged strict directional predicate only as specified by U6. |
| H223 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -520,0 +672,2 @@ def compile_local_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Return internal pruning/reject counters | Reject legacy result contract additions. |
| H224 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -523,0 +677 @@ def compile_local_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Return per-call telemetry tuple | Reject historical call telemetry. |
| H225 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -525,2 +679,2 @@ def compile_local_states_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Compile failure replaces cap-binding classification | Reject legacy failure/cap authority change. |
| H226 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -550,0 +705 @@ def evaluate_directional_cross_product_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Witness accumulator | Reject continuation delta; U6 records evidence in its own shadow driver. |
| H227 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -554 +709,3 @@ def evaluate_directional_cross_product_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | checkpoint_pair wrapper | Reject; use 59b evaluate_operating_pair_v1 directly. |
| H228 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -558,0 +716,5 @@ def evaluate_directional_cross_product_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Strict-progress check moved before global deduplication | Reject inherited continuation/control-flow delta; U6 follows its approved source-once worklist and unchanged strict_pair_rhythm_progress_v1. |
| H229 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -564,3 +725,0 @@ def evaluate_directional_cross_product_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Removal of original strict-progress check position | Reject historical control-flow rewrite. |
| H230 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -570,0 +730,9 @@ def evaluate_directional_cross_product_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Accepted-descendant witness append | Reject imported continuation implementation; U6 supplies specified parent/child evidence. |
| H231 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -579,0 +748 @@ def evaluate_directional_cross_product_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Return accepted descendant witnesses | Reject legacy contract change. |
| H232 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -608,0 +778 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Source-level extra counters | Reject inherited local telemetry. |
| H233 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -612,0 +783 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Source compiler-call telemetry accumulator | Reject inherited local telemetry. |
| H234 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -624 +795 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Indexed family loop for recovery cursor | Reject recovery-oriented loop change. |
| H235 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -633,0 +805 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Mapping rejection counter | Reject legacy telemetry change. |
| H236 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -634,0 +807 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Source checkpoint before generation | Reject checkpoint hook. |
| H237 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -643,0 +817 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Source checkpoint before compilation | Reject checkpoint hook. |
| H238 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -648,0 +823,2 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | checkpoint_family and call telemetry extension | Reject checkpoint and inherited telemetry. |
| H239 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -651,0 +828,2 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Accumulate later compiler counters | Reject inherited telemetry. |
| H240 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -657,2 +834,0 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Remove compiler cap-binding stop propagation | Reject change to legacy classification. |
| H241 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -687,0 +864,3 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Additional source result counters | Reject inherited result contract. |
| H242 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -698,0 +878,2 @@ def refine_source_pair_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Source telemetry and descendant witness result fields | Reject legacy result changes; U6 owns its shadow result. |
| H243 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -711,0 +893,22 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | New refine_local_rhythm_frontier_v1 completed-result entry and global-call wrapper | Reject post-59b local continuation entry point; implement only the separately approved U6 run_kbest_dag_shadow_from_completed_result_v1, with zero global calls. |
| H244 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -732,0 +936,3 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Continuation aggregate counters | Reject historical continuation/telemetry delta. |
| H245 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -753,0 +960,2 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Continuation source and call telemetry lists | Reject inherited continuation state. |
| H246 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -765 +973 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Indexed source loop for recovery cursor | Reject runner-owned source cursor. |
| H247 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -770,0 +979 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Frontier checkpoint hook | Reject checkpoint hook. |
| H248 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -777,0 +987,2 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Continuation source/call telemetry accumulation | Reject inherited continuation state. |
| H249 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -792,0 +1004,3 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Continuation extra aggregate field names | Reject legacy statistics delta. |
| H250 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -804,2 +1017,0 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Remove continuation cap-binding propagation | Reject legacy cap classification change. |
| H251 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -820 +1032 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Legacy continuation reports zero global executions | Reject post-59b entry-point change; U6 zero-global telemetry derives from its new explicit completed-result API. |
| H252 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -833,0 +1046,3 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Continuation statistics extra counters | Reject inherited statistics delta. |
| H253 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -848,0 +1064,15 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Compiler pruning telemetry aggregation | Reject historical call accounting; U6 records DAG-specific counts. |
| H254 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -850 +1080 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Assign result before checkpoint finish | Reject recovery-oriented return rewrite. |
| H255 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -859,0 +1090,2 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | Continuation result source/telemetry fields | Reject legacy result contract change. |
| H256 | src/bus_schedule_engine/local_rhythm_refinement.py | @@ -860,0 +1093 @@ def search_route_service_plans_with_local_rhythm_refinement_v1( | D. DEPENDS_ON_POST_59B_LOCAL_CHANGES | checkpoint_finish return wrapper | Reject checkpoint hook and recovery resume. |
| H257 | tests/experiments/test_pr62_u2_benchmark.py | @@ -0,0 +1,123 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H258 | tests/experiments/test_pr62_u2_corpus.py | @@ -0,0 +1,97 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H259 | tests/experiments/test_pr62_u2_report.py | @@ -0,0 +1,104 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H260 | tests/experiments/test_pr62_u2_solver.py | @@ -0,0 +1,139 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H261 | tests/experiments/test_pr62_u2_supplement.py | @@ -0,0 +1,28 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H262 | tests/experiments/test_pr62_u3_execution.py | @@ -0,0 +1,112 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H263 | tests/experiments/test_pr62_u3_report.py | @@ -0,0 +1,19 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H264 | tests/experiments/test_pr62_u3_shell.py | @@ -0,0 +1,176 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H265 | tests/experiments/test_pr62_u4_evaluation.py | @@ -0,0 +1,157 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H266 | tests/experiments/test_pr62_u4_execution.py | @@ -0,0 +1,92 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H267 | tests/experiments/test_pr62_u4_report.py | @@ -0,0 +1,27 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H268 | tests/experiments/test_pr62_u4_tiers.py | @@ -0,0 +1,169 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H269 | tests/experiments/test_pr62_u5_authority.py | @@ -0,0 +1,71 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H270 | tests/experiments/test_pr62_u5_evaluation.py | @@ -0,0 +1,115 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H271 | tests/experiments/test_pr62_u5_execution.py | @@ -0,0 +1,115 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H272 | tests/experiments/test_pr62_u5_kbest.py | @@ -0,0 +1,355 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H273 | tests/experiments/test_pr62_u5_report.py | @@ -0,0 +1,41 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H274 | tests/pr62_u0_selection_oracle.py | @@ -0,0 +1,91 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H275 | tests/test_clean_compile_frontier_selection_equivalence.py | @@ -0,0 +1,156 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H276 | tests/test_local_recovery.py | @@ -0,0 +1,321 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H277 | tests/test_local_rhythm_refinement.py | @@ -2,0 +3 @@ from __future__ import annotations | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H278 | tests/test_local_rhythm_refinement.py | @@ -9,0 +11,2 @@ from bus_schedule_engine.contracts_v1.service_plan_state import ( | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H279 | tests/test_local_rhythm_refinement.py | @@ -12 +14,0 @@ from bus_schedule_engine.local_rhythm_refinement import ( | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H280 | tests/test_local_rhythm_refinement.py | @@ -60,0 +63,99 @@ def _compilation(service_ids: tuple[str, ...]): | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H281 | tests/test_local_rhythm_refinement.py | @@ -316,0 +418 @@ def test_every_cross_product_pair_uses_existing_pareto_updater(monkeypatch) -> N | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H282 | tests/test_local_rhythm_refinement.py | @@ -345 +447 @@ def test_duplicate_pair_descendants_are_suppressed_before_admission(monkeypatch) | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H283 | tests/test_local_rhythm_refinement.py | @@ -351 +453,3 @@ def test_compiler_cap_binding_is_an_explicit_blocker(monkeypatch) -> None: | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H284 | tests/test_local_rhythm_refinement.py | @@ -364 +468,244 @@ def test_compiler_cap_binding_is_an_explicit_blocker(monkeypatch) -> None: | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H285 | tests/test_local_rhythm_refinement.py | @@ -402,0 +750,8 @@ def test_integrated_entry_calls_global_coordinator_once_and_processes_source_onc | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H286 | tests/test_local_rhythm_refinement.py | @@ -413,0 +769,17 @@ def test_integrated_entry_calls_global_coordinator_once_and_processes_source_onc | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H287 | tests/test_local_rhythm_refinement.py | @@ -464,0 +837,87 @@ def test_v3_source_remains_exact_start_bytes() -> None: | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H288 | tests/test_pr62_u0_compiler_authority_transition.py | @@ -0,0 +1,98 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H289 | tests/test_pr62_u_local_recovery_runner.py | @@ -0,0 +1,74 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |
| H290 | tests/test_pr62_u_local_rhythm_search_integration.py | @@ -0,0 +1,699 @@ | C. TEST_OR_EVIDENCE_ONLY | Test/fixture/oracle evidence; may exercise excluded post-59b behavior | Do not port tests as runtime code or treat historical expectations as U6 authority; author focused U6 tests from approved spec. |

## Verification and Task 1 boundary

The temporary Python check parses the complete git diff --unified=0 range,
checks exact hunk-key set equality, one row per key, sequential unique IDs,
exactly one full classification per row, production equivalents for every
A-with-D row, path/category accounting and the single-add C evidence condition.
Its command and actual result are recorded in the separate task report.

Task 1 clean baseline is `c37358654528a3f6bc81bc9df4b7f956a38d3e83`.
The literal comparison to `4a3893765f97e8b31ed5e5b0373d6e0ae21462f2` also includes
the already-approved U6 plan added by c373586. The controller confirmed that this
pre-existing delta must be reported and preserved. Only this audit is added by
Task 1; the separate ignored task report is not a repository change.

Historical classifications are unchanged: production
ROUTE10_LOCAL_REFINEMENT_OPERATIONALLY_INTRACTABLE (Route 10 global executions 1,
Route 6 global executions 0; all four production-Q stages UNADJUDICATED);
U2 CP_SAT_LOCAL_REALIZATION_POC_NO_GO; U3 U3_EXACT_SHELL_EXHAUSTED_TOO_NARROW;
U4 U4_IMPLEMENTATION_ERROR; U5 U5_EXACT_KBEST_DAG_FRONTIER_VALIDATED.

This inventory does not claim U6 implementation, parity, route validation or
production readiness. No production module, tests, private artifacts, SDD ledger,
other worktrees or historical commits are modified. No push, merge or PR #62
update is performed by this task.
