# Contract V1 Canonical Schedule Problem Boundary

**Status:** Approved implementation design for completing the existing Contract `1.0.0` Stage 3 problem boundary

**Design ID:** `V1-H4`

**Base:** `main@31f098302b9d367b03007cba3b0342b5cba1ed3b`

**Applies to:** typed Schedule Problem models, problem construction, authoritative generation context, heuristic compatibility context, problem serialization/schema validation, solver protocol inputs, orchestration, independent validation, fingerprints, examples, and regression tests

**Does not implement:** V1-A1 / Contract `1.1.0`, OR-Tools, a technical-feasibility-only solver mode, production runtime cutover, Streamlit, diagrams, XLSX, workbook formats, demand forecasting, elasticity, or new fleet/headway algorithms

This design resolves the remaining Stage 3 type/schema mismatch. The current typed `ScheduleProblemV1` is an internal heuristic migration shell containing legacy `ScenarioParameters`, `Trip`, `DemandRecord`, and `ScenarioCConfig` objects. The machine-readable `schedule_problem.schema.json` instead describes a solver-independent, serializable problem.

V1-H4 makes the serialized problem canonical while preserving the existing H1/H2/H3 integrity rules and keeping legacy inputs inside an explicitly adapter-owned compatibility context.

## 1. Governing principles

### 1.1 The canonical problem is a contract object

`ScheduleProblemV1` MUST be:

- immutable;
- composed only of Contract V1 domain models and primitive/configuration values;
- serializable without access to legacy workbook classes;
- independently validatable;
- suitable as the only problem argument passed to any `ScheduleSolver` implementation;
- free of `ScenarioParameters`, legacy `Trip`, legacy `DemandRecord`, and `ScenarioCConfig` objects.

A solver-neutral shape does not mean every run has identical identity across adapters. The selected solver adapter and an opaque fingerprint of its approved execution context are part of the exact reviewed request presented to a solver. Adapter-owned Python objects themselves are not part of the problem.

### 1.2 Evaluation authority and solver facts are separate

The canonical problem contains the facts and constraints a solver may use. The complete authoritative Scenario B evaluation remains in an internal `ScheduleGenerationContextV1` used by orchestration and independent validation.

The problem MUST carry the authoritative evaluation fingerprint. It MUST NOT embed an unversioned copy of the full evaluation object in the external problem payload.

### 1.3 Legacy compatibility is adapter-owned

The heuristic adapter may still require legacy parameters, trips, demand rows, and `ScenarioCConfig`. Those values belong to `HeuristicCompatibilityContextV1`, not `ScheduleProblemV1`.

The canonical problem contains only:

- `solver_adapter`;
- `adapter_context_fingerprint`;
- generic solver policy;
- authoritative problem facts and locks.

The heuristic adapter MUST prove that the compatibility context it holds matches the problem's adapter-context fingerprint before search begins.

### 1.4 No solver invocation from hidden data

A concrete adapter MUST NOT use legacy or mutable values that are absent from the adapter-context fingerprint. A change to any adapter input capable of changing candidate generation MUST change `adapter_context_fingerprint`, and therefore the problem fingerprint.

## 2. Authority layers

V1-H4 defines three explicit layers.

### 2.1 `ScheduleProblemV1`

The canonical, serializable request passed to `ScheduleSolver.solve()`.

It contains normalized Scenario A/B references, authoritative demand blocks and requirements when available, operating locks, supported modes, generic solver policy, adapter identity, and fingerprints.

### 2.2 `ScheduleGenerationContextV1`

An internal authoritative aggregate used by orchestration and the independent validator. It contains:

- `problem: ScheduleProblemV1`;
- `normalized_inputs: NormalizedInputBundleV1`;
- `b_evaluation: ScenarioBEvaluationBundleV1`;
- `evaluation_policy: ScenarioBEvaluationPolicyV1`.

The context is not the external problem schema. It exists so H1 evaluation provenance, H3 coverage support, and no-run disposition decisions remain independently checkable.

The context MUST validate that:

- problem scenarios and source fingerprints match `normalized_inputs`;
- problem `evaluation_fingerprint` matches the authoritative evaluation and policy;
- demand blocks and block requirements match the evaluation bundle;
- operating locks match Scenario B;
- problem identity recomputes exactly.

### 2.3 `HeuristicCompatibilityContextV1`

An adapter-owned internal object containing the current heuristic's legacy inputs:

- reconciled legacy `ScenarioParameters` compatibility view;
- exact legacy Scenario B trips;
- legacy demand rows;
- `ScenarioCConfig`;
- H2 turnaround bridge mode/value;
- source B and observed-demand fingerprints;
- deterministic `context_fingerprint`.

It MUST NOT be included in problem serialization, solution serialization, outcome serialization, or external schemas.

## 3. Canonical `ScheduleProblemV1` fields

The typed model and corrected machine-readable schema MUST represent this stable top-level shape.

### 3.1 Identity and provenance

Required fields:

- `contract_version`;
- `problem_id`;
- `problem_fingerprint`;
- `evaluation_fingerprint`;
- `source_a_fingerprint` — nullable;
- `source_b_fingerprint` — required;
- `observed_demand_fingerprint` — nullable;
- `solver_adapter`;
- `adapter_context_fingerprint`.

`problem_id` is a display/reference identifier. `problem_fingerprint` is the full canonical identity.

### 3.2 Normalized scenarios

Required fields with nullable A:

- `scenario_a: ScenarioAInput | null`;
- `scenario_b: ScenarioBInput`.

The scenario objects remain complete Contract V1 normalized objects. Their embedded source metadata is retained for audit and presentation.

The domain validator MUST independently verify:

- `scenario_a_fingerprint == scenario_fingerprint(scenario_a)` when A exists;
- both A fields are null together when A is absent;
- `source_b_fingerprint == scenario_fingerprint(scenario_b)`;
- A/B route and terminal identity consistency;
- all existing normalized input invariants.

### 3.3 Demand and block evidence

Required stable-shape fields:

- `demand_response_mode` — nullable when observed demand is absent;
- `demand_resolution` — nullable;
- `analysis_blocks` — array, possibly empty;
- `block_requirements` — array, possibly empty.

Rules:

1. No observed demand:
   - `observed_demand_fingerprint = null`;
   - `demand_response_mode = null`;
   - `demand_resolution = null`;
   - `analysis_blocks = []`;
   - `block_requirements = []`.

2. Daily-total-only demand:
   - demand fingerprint and response mode are present;
   - demand resolution is present;
   - intraday `analysis_blocks` and `block_requirements` are empty;
   - H3 continues to block demand-guided C generation.

3. Supported intraday demand:
   - demand fingerprint, response mode, and resolution are present;
   - analysis blocks equal the authoritative evaluation blocks;
   - block requirements equal authoritative Scenario B supply rows for those blocks;
   - block IDs are unique and reconcile one-to-one.

4. Coverage gaps remain diagnostics inside authoritative evaluation/context evidence. They MUST NOT create synthetic analysis blocks.

### 3.4 Operating locks and modes

Required fields:

- `operating_parameter_locks`;
- `direction_trip_lock_mode`;
- `direction_redistribution_authorization` — nullable;
- `fleet_constraint_mode`;
- `initial_fleet_positioning_mode`;
- `fixed_initial_fleet` — nullable;
- `bounded_initial_fleet` — nullable;
- `planning_load_factor_ceiling`;
- `critical_load_factor_ceiling`;
- `boundary_convention`.

Current supported runtime modes remain:

- `direction_trip_lock_mode = fixed_by_direction`;
- `fleet_constraint_mode = available_upper_bound`;
- `initial_fleet_positioning_mode = solver_determined`.

The schema may retain already-documented future enum values, but the current builder MUST reject unsupported execution modes rather than silently treating them as supported.

`boundary_convention` emitted by V1-H4 is:

`half_open`

This means all analytical membership uses:

`start <= event_time < end`.

The former draft schema values `half_open_with_final_sentinel` and `half_open_with_documented_final_inclusive` may remain accepted for backward validation during this draft phase, but the V1-H4 builder MUST emit only `half_open`. No final-boundary inclusion may be inferred; H3 uncovered-departure rules remain authoritative.

### 3.5 Solver policy

`solver_policy` is generic execution policy, not heuristic algorithm configuration.

Required fields:

- `time_limit_seconds: number | null`;
- `worker_count: integer | null`;
- `random_seed: integer | null`;
- `require_independent_validation = true`.

For the current heuristic adapter, the first three values are null because the heuristic does not implement those controls.

For a future solver, non-null values must be positive/non-negative as applicable and must be included in problem identity.

`ScenarioCConfig` fields are not solver policy and MUST NOT be serialized into the canonical problem. They are bound through `adapter_context_fingerprint`.

## 4. Problem identity

### 4.1 Canonical fingerprint profile

The problem fingerprint profile becomes:

`contract_v1_h4_problem`

### 4.2 Fingerprint payload

The fingerprint payload MUST include:

- fingerprint profile;
- contract version;
- source A/B/demand fingerprints;
- stable scenario source identities (`source_type` and `source_id`, excluding `imported_at` and notes);
- authoritative evaluation fingerprint;
- demand response mode;
- canonical demand-resolution contract;
- canonical analysis blocks;
- canonical operating locks;
- direction/fleet/initial-position modes and any authorizations/bounds;
- planning and critical ceilings;
- canonical block requirements;
- boundary convention;
- solver adapter ID;
- adapter-context fingerprint;
- canonical generic solver policy.

It MUST exclude:

- `problem_id`;
- `problem_fingerprint`;
- solve duration;
- generated timestamps;
- source `imported_at` values;
- free-text source notes;
- raw legacy objects;
- un-fingerprinted adapter configuration.

Nested scenarios are serialized in the external problem payload, but the fingerprint binds their domain facts through their independently validated scenario fingerprints and stable source identities rather than by hashing volatile import timestamps.

### 4.3 Problem ID

After computing the full fingerprint:

`problem_id = "PROBLEM-" + uppercase(problem_fingerprint[0:16])`

The problem ID is deterministic but is not a substitute for the 64-character fingerprint.

A mismatch returns:

`PROBLEM_ID_FINGERPRINT_MISMATCH`.

### 4.4 Identity consequences

The following changes MUST change `problem_fingerprint`:

- any authoritative A/B timetable fact;
- demand dataset identity or authoritative blocks;
- B evaluation evidence or policy;
- coverage support that changes authoritative evaluation evidence;
- operating locks or supported modes;
- load-factor ceilings;
- generic solver policy;
- solver adapter ID;
- adapter-context fingerprint;
- H2 runtime/turnaround/bridge evidence bound through locks/context.

Changing only `imported_at` or free-text notes MUST NOT change problem identity.

Changing stable source ID/type MUST change problem identity.

## 5. Evaluation binding

### 5.1 Required evaluation fingerprint

`evaluation_fingerprint` is required even when no demand exists. It identifies the complete authoritative Scenario B evaluation under the effective evaluation policy.

The `ScheduleGenerationContextV1` constructor/builder MUST recompute it using the H1/H3 evaluation-fingerprint service and require exact equality.

Stable error:

`PROBLEM_EVALUATION_FINGERPRINT_MISMATCH`.

### 5.2 No evaluation object inside the problem schema

The external problem contains derived analysis blocks, block requirements, policies, and fingerprints, but not the full `ScheduleEvaluationResultV1` object.

Orchestration and independent validation use `ScheduleGenerationContextV1.b_evaluation` and verify its fingerprint before using any disposition or coverage result.

A solver MUST NOT receive or trust caller-supplied disposition outside the validated generation context.

## 6. Operating-lock authority

### 6.1 Build once

Operating locks MUST be derived once during canonical problem construction by a pure lock builder.

The accepted solution MUST reuse the exact immutable problem lock tuple. The independent validator MUST NOT rebuild a potentially different lock set after candidate acceptance.

### 6.2 Required lock coverage

The V1-H4 lock set includes all H1/H2 authoritative values, including at least:

- route and terminal identity;
- route type;
- total daily trips;
- trips by direction;
- first and last departures;
- vehicle capacity;
- available fleet limit;
- approved active fleet when present;
- operating-day type;
- scenario default/fallback runtime;
- `runtime_lock_mode = fixed_by_source_trip`;
- deterministic source B per-trip runtime mapping;
- terminal-specific turnaround values;
- `turnaround_application_mode = arrival_terminal_specific`;
- fleet and initial-positioning modes;
- direction-trip lock mode.

For a heuristic-specific problem, H2 bridge evidence remains represented in lock/evidence entries and is also bound by the adapter-context fingerprint.

### 6.3 Lock validation

The lock validator MUST reject:

- duplicate lock field names;
- missing mandatory fields;
- unlocked mandatory entries;
- wrong source fingerprint;
- values inconsistent with Scenario B;
- unsupported authorized exceptions.

Stable codes:

- `PROBLEM_LOCK_SET_INCOMPLETE`;
- `PROBLEM_LOCK_DUPLICATE_FIELD`;
- `PROBLEM_LOCK_SOURCE_MISMATCH`;
- `PROBLEM_LOCK_VALUE_MISMATCH`.

## 7. Heuristic compatibility context

### 7.1 Context fingerprint profile

`contract_v1_h4_heuristic_context`

### 7.2 Fingerprint payload

The compatibility-context fingerprint MUST include every legacy/heuristic value capable of changing generated candidates:

- source B fingerprint;
- observed-demand fingerprint;
- canonical reconciled legacy parameter values;
- canonical legacy B trip facts and B trace IDs;
- canonical legacy demand rows;
- complete `ScenarioCConfig`;
- H2 turnaround bridge mode and scalar bridge value;
- compatibility-context profile.

It excludes mutable object identity, timestamps, list insertion order, and unrecognized configuration keys.

### 7.3 Adapter construction and verification

`HeuristicScheduleSolverAdapter` is constructed with one immutable `HeuristicCompatibilityContextV1`.

Before search, it MUST verify:

- `problem.solver_adapter == adapter.adapter_id`;
- `problem.adapter_context_fingerprint == context.context_fingerprint`;
- context source B fingerprint equals problem source B fingerprint;
- context demand fingerprint equals problem demand fingerprint;
- context legacy facts still reconcile with the canonical problem.

A mismatch produces a completed sanitized model-invalid run, not route infeasibility.

Stable codes:

- `PROBLEM_ADAPTER_CONTEXT_MISMATCH`;
- `HEURISTIC_CONTEXT_SOURCE_MISMATCH`;
- `HEURISTIC_CONTEXT_DEMAND_MISMATCH`.

The raw legacy context is never copied into candidate, solution, or outcome payloads.

### 7.4 Empty adapter context

A solver requiring no adapter-specific inputs uses the deterministic fingerprint of:

`{"fingerprint_profile": "contract_v1_h4_empty_adapter_context"}`

Therefore `adapter_context_fingerprint` remains a required fingerprint rather than nullable.

## 8. Builder workflow

The implementation SHOULD expose clear pure builders.

### 8.1 Authoritative problem builder

A generic builder receives:

- normalized inputs;
- freshly recomputed authoritative B evaluation;
- effective evaluation policy;
- solver adapter ID;
- adapter-context fingerprint;
- generic solver policy;
- supported mode selections.

It then:

1. validates normalized inputs;
2. validates/recomputes evaluation fingerprint;
3. derives authoritative blocks and B block requirements;
4. derives the complete operating-lock tuple;
5. builds the canonical problem without IDs/fingerprint;
6. calculates problem fingerprint;
7. derives problem ID;
8. runs the independent problem validator;
9. returns immutable `ScheduleProblemV1`.

### 8.2 Generation-context builder

A context builder returns `ScheduleGenerationContextV1` containing the canonical problem and authoritative evaluation references.

It MUST fail closed if problem/evaluation/normalized inputs do not reconcile.

### 8.3 Heuristic request helper

A heuristic-specific helper may:

1. validate legacy inputs against normalized facts;
2. construct `HeuristicCompatibilityContextV1`;
3. compute its context fingerprint;
4. construct the canonical problem with heuristic adapter identity/context fingerprint;
5. construct `ScheduleGenerationContextV1`;
6. return the context plus a `HeuristicScheduleSolverAdapter` initialized with the compatibility context.

The legacy values are never stored in `ScheduleProblemV1`.

## 9. Solver, orchestration, and validation signatures

### 9.1 Solver protocol

The protocol remains conceptually:

`ScheduleSolver.solve(problem: ScheduleProblemV1) -> SolverRunResultV1`

A solver receives only the canonical typed problem.

### 9.2 Orchestration

`run_schedule_solver_v1()` receives:

- `ScheduleGenerationContextV1`;
- `ScheduleSolver`.

It uses validated evaluation/disposition/coverage from the generation context for no-run decisions, then passes only `context.problem` to the solver.

The solver MUST NOT be invoked when H3 coverage or existing disposition rules prohibit generation.

### 9.3 Independent validation

`validate_and_build_solution_v1()` receives:

- `ScheduleGenerationContextV1`;
- raw candidate.

It derives source locks, runtime, turnaround, fleet, blocks, headways, and coverage backstops from the canonical problem and validated evaluation context.

The accepted solution:

- uses `context.problem.operating_parameter_locks` unchanged;
- binds `context.problem.problem_fingerprint`;
- never reads legacy context directly.

## 10. Problem serialization

### 10.1 Required serializer

Add:

`schedule_problem_to_contract_dict(problem: ScheduleProblemV1) -> dict[str, object]`

It MUST use existing authoritative serializers for nested scenarios, demand resolution, analysis blocks, locks, and block requirements.

It MUST emit deterministic array order:

- analysis blocks by direction/start/end/block ID;
- locks by field;
- block requirements by direction/start/end/block ID.

### 10.2 Machine-readable schema corrections

`contracts/v1/schedule_problem.schema.json` is still a draft validation artifact and has never been emitted by the runtime. V1-H4 completes it before formal approval.

Required corrections:

- add required `problem_fingerprint`;
- add required `evaluation_fingerprint`;
- add required `solver_adapter`;
- add required `adapter_context_fingerprint`;
- allow `source_a_fingerprint` and `scenario_a` to be null together;
- allow `observed_demand_fingerprint`, `demand_response_mode`, and `demand_resolution` to be null when demand is absent;
- allow empty `analysis_blocks` and `block_requirements`;
- allow nullable generic solver-policy resource controls;
- accept `half_open` boundary convention while retaining prior draft values for backward validation;
- preserve `additionalProperties: false`;
- preserve Contract version `1.0.0`.

This is schema completion for a previously unimplemented boundary. It does not authorize changing Scenario, Solution, or Outcome object shapes.

### 10.3 Examples

Update the existing full-demand example to include the completed identity/adapter fields and full directional evidence.

Add at least one B-only/no-demand example proving nullable/empty semantics.

All examples MUST validate through the schema registry.

## 11. Cross-field problem validation

A pure `validate_schedule_problem_v1()` MUST check beyond JSON Schema:

- problem ID/fingerprint relationship;
- recomputed problem fingerprint;
- nested scenario fingerprints;
- A nullability covariance;
- demand nullability covariance;
- resolution/block/requirement covariance;
- unique block IDs;
- analysis-block versus B-requirement reconciliation;
- lock completeness and value reconciliation;
- mode-specific constraints;
- initial-position bounds and fixed values;
- solver policy validity;
- adapter ID/context fingerprint presence;
- evaluation fingerprint equality with generation context;
- boundary convention supported by the current implementation.

The validator returns structured stable issues and a passed flag. Builders raise `ScheduleProblemError` only after collecting deterministic errors.

## 12. Stable issue codes

Use stable codes as applicable:

- `PROBLEM_ID_FINGERPRINT_MISMATCH`;
- `PROBLEM_FINGERPRINT_MISMATCH`;
- `PROBLEM_SCENARIO_A_FINGERPRINT_MISMATCH`;
- `PROBLEM_SCENARIO_B_FINGERPRINT_MISMATCH`;
- `PROBLEM_DEMAND_FINGERPRINT_MISMATCH`;
- `PROBLEM_EVALUATION_FINGERPRINT_MISMATCH`;
- `PROBLEM_DEMAND_NULLABILITY_MISMATCH`;
- `PROBLEM_SCENARIO_A_NULLABILITY_MISMATCH`;
- `PROBLEM_BLOCK_RECONCILIATION_MISMATCH`;
- `PROBLEM_DUPLICATE_BLOCK_ID`;
- `PROBLEM_LOCK_SET_INCOMPLETE`;
- `PROBLEM_LOCK_DUPLICATE_FIELD`;
- `PROBLEM_LOCK_SOURCE_MISMATCH`;
- `PROBLEM_LOCK_VALUE_MISMATCH`;
- `PROBLEM_POLICY_INVALID`;
- `UNSUPPORTED_PROBLEM_MODE`;
- `PROBLEM_ADAPTER_CONTEXT_MISMATCH`;
- `HEURISTIC_CONTEXT_SOURCE_MISMATCH`;
- `HEURISTIC_CONTEXT_DEMAND_MISMATCH`.

These identify contract/integration defects. They are not demand, fleet, timetable, or infeasibility conclusions.

## 13. Fingerprint propagation

H1 candidate, solution, and outcome fingerprints continue to bind `problem_fingerprint`.

V1-H4 does not add new serialized candidate/solution/outcome fields. Their fingerprint values change naturally because the canonical problem fingerprint now includes the completed problem and adapter-context identity.

The following remain excluded from solution/outcome fingerprints:

- solve duration;
- mutable logs;
- raw exception text.

## 14. Compatibility and versioning

V1-H4 remains Contract `1.0.0` because:

- the canonical problem boundary was not previously emitted or consumed by production;
- the existing problem schema is explicitly a draft artifact;
- the refactor does not alter Scenario A/B, observed demand, solution, or outcome external shapes;
- no existing production runtime path is cut over;
- no solver proof capability is added.

V1-H4 does change the internal additive Stage 3 API and completes `schedule_problem.schema.json`. All Contract V1 tests and examples must migrate in the same PR.

The old typed migration shell MUST NOT remain exported under the name `ScheduleProblemV1` after V1-H4. If temporarily retained for implementation migration, it must be private and deleted before merge.

## 15. Implementation boundary for Codex

### 15.1 Expected files

Implementation should remain concentrated in:

- `src/bus_schedule_engine/contracts_v1/solver_models.py`;
- `src/bus_schedule_engine/contracts_v1/solver_problem.py`;
- new small modules such as `problem_serialization.py`, `problem_validation.py`, or `heuristic_context.py`;
- `src/bus_schedule_engine/contracts_v1/heuristic_solver.py`;
- `src/bus_schedule_engine/contracts_v1/solver_orchestration.py`;
- `src/bus_schedule_engine/contracts_v1/solver_validation.py`;
- `src/bus_schedule_engine/contracts_v1/solver_fingerprints.py` only as required for the H4 problem profile;
- `src/bus_schedule_engine/contracts_v1/solver_adapter.py` and `__init__.py` for the public additive API;
- `contracts/v1/schedule_problem.schema.json`;
- `examples/contracts/v1/schedule_problem.example.json` and a B-only example;
- Contract V1 problem/solver/schema tests.

### 15.2 Prohibited areas

Codex MUST NOT modify:

- legacy `c_generator.py`, `fleet.py`, or `demand.py` algorithms;
- V1-H2 runtime/turnaround/fleet semantics;
- V1-H3 demand-coverage semantics;
- Streamlit/application runtime;
- diagrams or XLSX exporters;
- workbook templates;
- OR-Tools;
- V1-A1 / Contract `1.1.0` models or statuses;
- Scenario, Solution, or Outcome schemas except a separately reported unavoidable contradiction.

### 15.3 Required implementation sequence

1. Add canonical problem/supporting typed models.
2. Add pure operating-lock construction and problem validation.
3. Correct the draft schedule-problem schema and examples.
4. Add canonical problem serialization.
5. Add heuristic compatibility context and fingerprint.
6. Refactor heuristic adapter to hold compatibility context and accept only canonical problem.
7. Add generation context and refactor orchestration/validator signatures.
8. Remove legacy objects from typed `ScheduleProblemV1`.
9. Preserve all H1/H2/H3 gates and accepted-solution behavior.
10. Add adversarial regressions and run full validation.

## 16. Mandatory adversarial regression suite

At minimum, tests MUST prove:

1. typed `ScheduleProblemV1` contains no legacy model or `ScenarioCConfig` fields;
2. `ScheduleSolver.solve()` receives only canonical `ScheduleProblemV1`;
3. a full directional-demand problem serializes and validates against the corrected schema;
4. a B-only/no-demand problem serializes with null demand/A fields and empty arrays as applicable;
5. daily-total demand permits resolution with empty intraday blocks/requirements;
6. Scenario A object/fingerprint must be null together;
7. observed-demand fingerprint/mode/resolution/blocks must reconcile;
8. nested Scenario B tampering is rejected even when the declared source fingerprint is unchanged;
9. nested Scenario A tampering is rejected;
10. evaluation fingerprint mismatch is rejected;
11. problem fingerprint tampering is rejected;
12. problem ID tampering is rejected;
13. problem ID is deterministically derived from the fingerprint;
14. duplicate analysis block IDs are rejected;
15. block requirements with missing, extra, or mismatched block IDs are rejected;
16. mandatory operating locks are complete, unique, locked, and source-bound;
17. accepted solution operating locks exactly equal problem operating locks;
18. unsupported direction/fleet/initial-position modes fail closed;
19. heuristic legacy objects do not appear anywhere in problem serialization;
20. changing `ScenarioCConfig` changes heuristic context and problem fingerprints;
21. changing H2 bridge value changes heuristic context and problem fingerprints;
22. changing one legacy demand row changes heuristic context fingerprint;
23. adapter rejects a context belonging to another B problem;
24. adapter rejects a demand-context mismatch;
25. identical facts/configuration produce deterministic context and problem fingerprints;
26. changing generic solver policy changes problem fingerprint;
27. changing only `imported_at` or notes does not change problem fingerprint;
28. changing stable source ID/type changes problem fingerprint;
29. the heuristic adapter retains equal-turnaround/direct-generator timetable parity;
30. H1 candidate tamper, H2 runtime/turnaround, and H3 coverage gates remain green;
31. no-run B-suitable and insufficient-demand outcomes still have valid problem-bound fingerprints;
32. accepted solution and outcome continue to validate existing schemas;
33. full Pytest passes;
34. Ruff lint passes;
35. Contract V1 Ruff-format gate passes;
36. JSON Schema registry validation passes;
37. final diff contains no prohibited production/OR-Tools/V1-A1 scope drift.

## 17. Acceptance gate

V1-H4 is complete only when:

- `ScheduleProblemV1` is canonical, typed, serializable, and free of legacy classes;
- problem schema and typed model match;
- B-only/no-demand and full-demand shapes are both valid;
- evaluation and source provenance are independently bound;
- operating locks are built once and reused by accepted solutions;
- heuristic context is adapter-owned and fingerprint-bound;
- solvers receive only canonical problem objects;
- orchestration and validation retain H1/H2/H3 behavior;
- candidate/solution/outcome identities remain problem-bound;
- no production runtime cutover occurs;
- all mandatory tests and validation gates pass.

## 18. Explicitly deferred work

The following remain separate tasks:

- V1-A1 structural-change `1.1.0` implementation;
- a demand-independent technical-feasibility solver capability;
- OR-Tools hard-feasibility implementation;
- demand allocation and timetable regularity optimization;
- formal approval/promotion of all remaining draft schemas;
- production UI/export cutover;
- public deserialization of untrusted remote problem payloads.
