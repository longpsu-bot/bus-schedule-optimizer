# Contract V1 Solver Boundary Integrity Hardening

**Status:** Approved implementation design for hardening the existing Contract `1.0.0` solver boundary

**Design ID:** `V1-H1`

**Applies to:** the additive Contract V1 solver interface, heuristic adapter, independent validator, fingerprints, and generation outcome boundary already implemented under `src/bus_schedule_engine/contracts_v1/`

**Does not implement:** V1-A1 / Contract `1.1.0`, OR-Tools, production runtime cutover, Streamlit, diagrams, XLSX, or source-workbook behavior

This document clarifies existing Contract V1 integrity requirements. It does not add a new external enum, change the `1.0.0` JSON shapes, or authorize a production runtime cutover. It exists because the current Stage 3 boundary has the correct architectural layers but still trusts several caller- or solver-supplied claims that must be independently bound or recomputed.

## 1. Governing principle

The solver boundary is a trust boundary.

The following inputs are not authoritative merely because they are typed or fingerprinted:

- a `ScenarioBEvaluationBundleV1` supplied by a caller;
- a raw candidate's `shift_minutes`;
- a raw candidate's previous-headway fields;
- raw headway-regime trip counts, windows, or headway sequences;
- a solver adapter's claim that its result belongs to the current problem;
- an exception message emitted by solver-specific code.

An authoritative `ScheduleProblemV1`, `ScheduleSolutionV1`, or `ScheduleGenerationOutcomeV1` may be produced only after the domain layer has independently bound those claims to the current normalized inputs, policy, exact timetable, and problem identity.

A fingerprint proves identity of the payload that was hashed. It does not prove semantic correctness. Independent recomputation remains mandatory.

## 2. Compatibility and versioning decision

V1-H1 is a hardening clarification within Contract `1.0.0`.

The implementation MUST preserve the current external JSON schemas and enum sets. In particular, V1-H1 MUST NOT:

- emit V1-A1 `1.1.0` fields or statuses;
- add undeclared properties to strict `1.0.0` serialization;
- require Streamlit, diagram, XLSX, or production callers to consume a new shape;
- reinterpret `FEASIBLE` as `OPTIMAL`;
- fabricate Scenario C for no-run, invalid, infeasible, or rejected cases.

Fingerprint values are expected to change after hardening because the identity payload becomes complete. To make that change explicit and collision-resistant, every hardened fingerprint payload SHOULD include a stable internal profile identifier:

- `contract_v1_h1_evaluation`;
- `contract_v1_h1_problem`;
- `contract_v1_h1_candidate`;
- `contract_v1_h1_solution`;
- `contract_v1_h1_outcome`.

These profile identifiers participate in hashing but are not new serialized Contract `1.0.0` fields.

## 3. Authoritative evaluation binding

### 3.1 Semantic rule

A caller-supplied `ScenarioBEvaluationBundleV1` is a cache candidate, not an authority.

`build_schedule_problem_v1()` MUST establish the authoritative Scenario B evaluation from:

- the exact `NormalizedInputBundleV1` passed to the builder; and
- the effective `ScenarioBEvaluationPolicyV1` passed to or selected by the builder.

The preferred and required first implementation is:

1. recompute Scenario B evaluation inside `build_schedule_problem_v1()` using the public authoritative evaluator;
2. compute its deterministic evaluation fingerprint;
3. when the caller also supplied an evaluation, compute the supplied evaluation fingerprint and require exact equality;
4. fail closed on any mismatch;
5. store only the freshly computed or exactly reconciled evaluation in `ScheduleProblemV1`.

A stale evaluation, an evaluation from another bundle, or an evaluation produced under another policy MUST NOT control run/no-run behavior.

### 3.2 Evaluation fingerprint payload

The evaluation fingerprint MUST identify all facts that can change Scenario B disposition or downstream block evidence:

- fingerprint profile `contract_v1_h1_evaluation`;
- `contract_version`;
- `scenario_a_fingerprint` when A exists;
- `scenario_b_fingerprint`;
- `observed_demand_fingerprint` when demand exists;
- canonical effective evaluation policy;
- authoritative demand-resolution contract and limitations;
- authoritative demand-analysis blocks;
- authoritative A block-supply rows;
- authoritative B block-supply rows;
- fleet assessment, including initial terminal stocks and stock-event evidence;
- complete `ScheduleEvaluationResultV1`, including all dimensions, issues, evidence, disposition, warnings, limitations, and confidence.

Generated timestamps and execution durations MUST NOT participate.

### 3.3 Required failure

When a supplied evaluation does not match the recomputed evaluation, the problem builder MUST raise `ScheduleProblemError` and expose the stable code:

`B_EVALUATION_PROVENANCE_MISMATCH`

The error is a caller/integration defect. It is not a route, demand, timetable, or locked-parameter conclusion.

### 3.4 Required adversarial proof

The regression suite MUST prove that:

- a low-demand `B_TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE` evaluation cannot be paired with a high-demand bundle;
- an evaluation produced under policy X cannot be paired with the same bundle under policy Y;
- a supplied evaluation with altered block rows, fleet evidence, or disposition cannot pass because its top-level disposition happens to match;
- the resulting problem always stores the authoritative current evaluation.

## 4. Problem identity

### 4.1 Semantic rule

`problem_fingerprint` identifies the exact reviewed problem presented to a solver. It MUST cover every input that can alter:

- the run/no-run decision;
- candidate construction;
- candidate validation;
- feasibility interpretation;
- demand/block interpretation;
- output identity.

### 4.2 Minimum problem fingerprint payload

The payload MUST contain:

- fingerprint profile `contract_v1_h1_problem`;
- `contract_version`;
- Scenario A, Scenario B, and observed-demand fingerprints as applicable;
- the authoritative evaluation fingerprint;
- the canonical effective evaluation policy;
- canonical heuristic/solver-adapter configuration used to construct the problem;
- supported operating modes and locks used by the current implementation;
- the boundary convention used for analytical block membership;
- any other solver policy value that can alter search or validation.

Hashing only the B disposition is prohibited.

The authoritative evaluation embedded in the problem MUST reconcile with the evaluation fingerprint included in the problem payload.

## 5. Raw candidate trust model

### 5.1 General rule

A `RawScheduleCandidateV1` is solver output, not an authoritative solution.

The independent validator MUST derive all facts that can be calculated from exact A/B/C timetables. Solver-supplied duplicates of those facts are claims that must either reconcile exactly or cause rejection.

The validator MUST NOT copy a disputed claim into `ScheduleSolutionV1` and then use it to calculate authoritative metrics.

### 5.2 Deterministic directional ordering

For all previous-headway and regime reconciliation, trips are ordered independently by direction using:

`(departure_time, trip_id)`

The trip ID is a deterministic tie-breaker for simultaneous departures. A zero-minute headway is therefore representable and MUST NOT be silently changed.

### 5.3 Shift reconciliation

For every C trip:

`expected_shift_minutes = (c_departure_time - b_departure_time) / 60`

The first implementation MUST compare the candidate claim with the exact derived value using an implementation-level numeric tolerance no greater than `1e-9` minutes. This tolerance handles floating representation only; it is not an operational tolerance.

A mismatch rejects the candidate with:

`SHIFT_MINUTES_MISMATCH`

The authoritative `SolutionTripV1.shift_minutes` MUST be the independently derived value.

The following solution metrics MUST be calculated only from independently derived shift values:

- `shifted_trip_count`;
- `total_shift_minutes`;
- `maximum_shift_minutes`.

### 5.4 Previous-headway reconciliation

For each direction, the first trip's previous headway MUST be `null`. For every later trip:

`expected_previous_headway = (current_departure - previous_directional_departure) / 60`

The validator MUST derive this sequence separately for B and C.

Candidate claims must reconcile with the derived values within the same numeric tolerance. Mismatches reject the candidate with:

- `PREVIOUS_B_HEADWAY_MISMATCH`;
- `PREVIOUS_C_HEADWAY_MISMATCH`.

Authoritative `SolutionTripV1.previous_b_headway` and `previous_c_headway` MUST be derived by the validator rather than copied from the solver.

## 6. Headway-regime reconciliation

### 6.1 Membership authority

In the current raw-candidate shape, each trip's `headway_regime_id` defines the claimed regime membership. The independent validator MUST group exact C trips by this field and reconcile every raw regime against those members.

The following invariants are mandatory:

- regime IDs are unique;
- every C trip references exactly one existing regime ID;
- every raw regime has at least one member trip;
- all members have the same direction as the regime;
- member trips are ordered by `(c_departure_time, c_trip_id)`;
- `regime.trip_count` equals the number of member trips;
- `regime.actual_headway_sequence` equals the consecutive member-departure gaps in minutes;
- the sequence length equals `max(trip_count - 1, 0)`;
- `regime.start_time` equals the first member departure;
- `regime.end_time` equals the last member departure.

For V1-H1, regime start/end are descriptive inclusive endpoints of member departures. They are not demand-block boundaries and do not use the half-open demand-block convention.

### 6.2 Target versus actual headway

`target_headway` is a solver/planner target. It may differ from the actual balanced sequence, but it MUST be positive and finite.

The validator derives:

`target_service_rate = 60 / target_headway`

The actual sequence, trip count, endpoints, and regularity status are authoritative only after independent reconciliation.

### 6.3 First-cut regularity derivation

Until explicit transition-headway evidence is added to the raw-candidate contract, the independent validator derives:

- `REGULAR` when there are no gaps or all actual gaps are equal;
- `BALANCED_ROUNDING` when actual gaps differ by no more than one minute;
- `EXCEPTIONAL` otherwise.

`TRANSITION` MUST NOT be emitted merely because the solver labeled a regime as transitional. It requires a future explicit evidence contract.

For the current first cut:

- `transition_headways = ()`;
- `exceptional_headways` is the actual sequence only for `EXCEPTIONAL`, otherwise empty.

### 6.4 Required rejection codes

The validator MUST expose stable codes as applicable:

- `DUPLICATE_HEADWAY_REGIME_ID`;
- `UNKNOWN_HEADWAY_REGIME_REFERENCE`;
- `ORPHAN_HEADWAY_REGIME`;
- `HEADWAY_REGIME_DIRECTION_MISMATCH`;
- `HEADWAY_REGIME_START_MISMATCH`;
- `HEADWAY_REGIME_END_MISMATCH`;
- `HEADWAY_REGIME_TRIP_COUNT_MISMATCH`;
- `HEADWAY_REGIME_SEQUENCE_MISMATCH`;
- `INVALID_HEADWAY_REGIME_TARGET`.

A candidate with a valid recomputed candidate fingerprint but fabricated regime facts MUST still be rejected. Fingerprint validity never substitutes for regime validation.

## 7. Candidate, solution, and outcome fingerprint binding

### 7.1 Candidate fingerprint

The hardened candidate fingerprint MUST include:

- fingerprint profile `contract_v1_h1_candidate`;
- `problem_fingerprint`;
- solver adapter ID;
- exact raw C timetable and B trace fields;
- raw regime payload.

Using only `source_b_fingerprint` is insufficient because the same B may be evaluated under different demand, policy, locks, or solver configuration.

The validator MUST recompute the expected candidate fingerprint using the current problem fingerprint.

### 7.2 Solution fingerprint

The hardened solution fingerprint MUST include:

- fingerprint profile `contract_v1_h1_solution`;
- `problem_fingerprint`;
- source B fingerprint;
- solver status and adapter;
- operating locks;
- independently derived trip traces and shift metrics;
- independently reconciled regimes;
- block-supply plan and evaluation;
- fleet assignment and stock evidence;
- relevant configuration already bound by the problem fingerprint.

Solve duration is excluded.

### 7.3 Outcome fingerprint

The hardened outcome fingerprint MUST include:

- fingerprint profile `contract_v1_h1_outcome`;
- `problem_fingerprint`;
- source B fingerprint;
- result status;
- execution status;
- native solver status and adapter when applicable;
- accepted solution fingerprint when applicable;
- diagnostic-candidate metadata when applicable;
- explanations and limitations.

Solve duration is excluded.

The serialized Contract `1.0.0` outcome shape remains unchanged. `problem_fingerprint` participates in the hash input even though it is not added as a new serialized field in V1-H1.

Two problem instances with different authoritative evaluation, policy, or solver configuration MUST NOT produce the same outcome fingerprint merely because their visible result statuses match.

This rule is especially important for:

- `NO_FEASIBLE_C_WITH_B_PARAMETERS`;
- `C_NOT_FOUND_WITHIN_SOLVE_LIMIT`;
- `C_NOT_GENERATED_MODEL_INVALID`;
- no-run outcomes.

## 8. Solver exception envelope

### 8.1 Semantic rule

A solver-specific exception MUST NOT escape the public Contract V1 orchestration boundary.

`run_schedule_solver_v1()` MUST place an exception boundary around `solver.solve(problem)`.

When the solver raises before returning a valid `SolverRunResultV1`, the engine returns:

- `result_status = C_NOT_GENERATED_MODEL_INVALID`;
- `execution_status = COMPLETED`;
- `solver_status = MODEL_INVALID`;
- `solver_adapter = solver.adapter_id`;
- non-negative elapsed `solve_duration_seconds` measured by orchestration;
- `solution = null`;
- `diagnostic_candidate = null`.

This means a solver invocation was attempted and ended in an implementation/adapter failure. It is not a timetable, route, fleet, or parameter infeasibility conclusion.

### 8.2 Safe explanation

The authoritative result envelope MUST use a sanitized explanation such as:

`Solver adapter raised an exception before returning a valid result.`

The stable issue/explanation code is:

`SOLVER_ADAPTER_EXCEPTION`

Raw exception text, stack traces, file paths, workbook values, secrets, or personal data MUST NOT be copied into the authoritative result envelope. Detailed exception diagnostics may be retained only in internal logs outside the contract payload.

## 9. Independent validation output rule

When all checks pass, `ScheduleSolutionV1` is constructed from validator-derived values wherever derivation is possible.

The validator may preserve solver-supplied fields only when they represent genuine solver decisions rather than independently calculable facts and when they pass all applicable structural checks. Examples include a positive target headway and a human-readable change reason.

The following fields are explicitly validator-derived in V1-H1:

- shift minutes;
- previous B headway;
- previous C headway;
- regime member count;
- regime actual headway sequence;
- regime start/end member endpoints;
- regime regularity status;
- target service rate;
- shift summary metrics;
- all existing fleet and block values already independently calculated by the validator.

## 10. Implementation boundary for Codex

### 10.1 Expected files

The implementation should remain concentrated in:

- `src/bus_schedule_engine/contracts_v1/solver_problem.py`;
- `src/bus_schedule_engine/contracts_v1/solver_fingerprints.py`;
- `src/bus_schedule_engine/contracts_v1/solver_validation.py`;
- `src/bus_schedule_engine/contracts_v1/solver_orchestration.py`;
- `tests/test_contract_v1_solver.py`.

A small pure helper module such as `evaluation_fingerprints.py` MAY be added when it improves responsibility separation.

`solver_models.py` and external schemas SHOULD remain unchanged unless implementation proves an unavoidable internal need. No new serialized Contract `1.0.0` field is approved by V1-H1.

### 10.2 Required implementation sequence

1. Implement canonical evaluation serialization/fingerprint using existing authoritative serializers where possible.
2. Recompute and bind evaluation in `build_schedule_problem_v1()`.
3. Strengthen `problem_fingerprint`.
4. Bind candidate fingerprint to `problem_fingerprint`.
5. Add independent trip-trace derivation and mismatch checks.
6. Add independent regime reconciliation and construct solution regimes from derived values.
7. Bind solution and outcome fingerprints to `problem_fingerprint`.
8. Add the orchestration exception boundary.
9. Add adversarial regression tests.
10. Run full validation and inspect the final diff for scope drift.

## 11. Mandatory adversarial regression suite

At minimum, tests MUST cover:

1. low-demand evaluation supplied with high-demand bundle;
2. evaluation supplied under a different policy;
3. evaluation with altered block/fleet evidence but unchanged disposition;
4. actual shift `-4` minutes while candidate claims `0`;
5. incorrect previous B headway;
6. incorrect previous C headway;
7. duplicate regime IDs;
8. unknown regime reference;
9. orphan regime;
10. regime direction mismatch;
11. fabricated `trip_count = 105`;
12. fabricated `actual_headway_sequence = [999]` with a valid recomputed candidate fingerprint;
13. raw regime start/end that do not match member endpoints;
14. same B and visible outcome status under different evaluation/solver configurations producing different outcome fingerprints;
15. accepted solution fingerprints changing when the bound problem identity changes;
16. solver adapter raising `RuntimeError` and returning a valid `MODEL_INVALID` envelope rather than crashing;
17. accepted solution and outcome continuing to validate the existing JSON schemas;
18. heuristic direct generation and adapter generation continuing to produce the same exact candidate timetable;
19. Scenario B input remaining immutable;
20. full existing regression suite remaining green.

## 12. Acceptance gate

V1-H1 is complete only when:

- stale or cross-bundle evaluation cannot control orchestration;
- problem identity includes authoritative evaluation and configuration;
- raw candidate shift/headway claims are independently checked;
- authoritative solution shift/headway values are validator-derived;
- fabricated regime facts are rejected even with a valid candidate fingerprint;
- candidate, solution, and outcome identity are bound to the current problem;
- solver exceptions always return a valid sanitized result envelope;
- no new external `1.0.0` field or enum is emitted;
- full Pytest passes;
- Ruff lint passes;
- Ruff format passes;
- JSON Schema validation passes;
- no Streamlit, diagram, XLSX, source-workbook, heuristic-generator, or production-runtime path is changed.

## 13. Explicitly deferred hardening

The following valid concerns are not part of V1-H1 and should be handled in a later, separately reviewed hardening task:

- scenario-level runtime versus per-trip runtime semantics;
- uncovered gaps in demand-observation coverage;
- equal-turnaround limitation of the legacy heuristic compatibility adapter;
- full alignment between the typed migration-shell `ScheduleProblemV1` and the larger machine-readable target schema;
- V1-A1 structural-change implementation and Contract `1.1.0` migration;
- OR-Tools feasibility or demand allocation.

Codex MUST NOT use V1-H1 as authorization to modify these deferred areas.