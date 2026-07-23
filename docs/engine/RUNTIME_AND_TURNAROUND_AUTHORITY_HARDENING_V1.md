# Contract V1 Runtime and Turnaround Authority Hardening

**Status:** Approved implementation design for hardening existing Contract `1.0.0` runtime and terminal-turnaround semantics

**Design ID:** `V1-H2`

**Base:** `main@646387285d88798b436663a70a33383d358c3f4e`

**Applies to:** normalized Contract V1 inputs, legacy normalization, Scenario B fleet assessment, the heuristic compatibility bridge, independent candidate validation, fleet assignment, operating locks, fingerprints, and regression tests

**Does not implement:** V1-A1 / Contract `1.1.0`, OR-Tools, demand-coverage hardening, `ScheduleProblemV1` schema migration, production runtime cutover, Streamlit, diagrams, XLSX, or source-workbook format changes

This design resolves two ambiguities in the current Stage 3 boundary:

1. `ScenarioInputV1.trip_runtime_minutes` and `ExactTimetableTrip.runtime_minutes` can both exist, but their authority has not been stated precisely.
2. normalized Contract V1 supports different turnaround values at the two terminals, while the legacy heuristic path has only one layover value.

The goal is fail-closed correctness without widening the external Contract `1.0.0` object shapes.

## 1. Governing principles

Runtime and turnaround are hard technical facts. They MUST NOT be selected merely because a legacy helper, scalar parameter, or solver adapter happens to support them.

The authoritative technical chronology of a trip is:

`departure_time -> per-trip runtime -> arrival terminal -> turnaround at that arrival terminal -> ready_time`.

For every trip:

`arrival_time = departure_time + authoritative_trip_runtime_minutes * 60`.

`ready_time = arrival_time + authoritative_turnaround_minutes_at_arrival_terminal * 60`.

A solver, adapter, validator, UI, or exporter MUST NOT shorten runtime or turnaround to make a timetable feasible.

## 2. Runtime authority model

### 2.1 Scenario-level runtime

Within Contract `1.0.0`, `ScenarioInputV1.trip_runtime_minutes` is the declared default or fallback contract runtime for the scenario.

It is used only when the source trip does not provide an explicit, valid arrival/runtime fact.

It is **not** an invariant that every exact trip must equal the scenario-level value.

The scalar field therefore has these semantics:

- default runtime for missing trip-level evidence;
- compatibility metadata for legacy inputs;
- a locked fallback value inherited from B to C;
- not a replacement for exact per-trip runtimes already present in the timetable.

### 2.2 Exact per-trip runtime

For every normalized timetable row, `ExactTimetableTrip.runtime_minutes` is the authoritative runtime of that exact trip.

If `arrival_time` is present:

`runtime_minutes = (arrival_time - departure_time) / 60`.

The duration MUST be a positive whole number of minutes and MUST reconcile exactly with the stored `runtime_minutes`.

If source arrival time is absent, the adapter uses the scenario default/fallback runtime and records the resulting exact trip runtime.

After normalization, downstream evaluation and validation MUST use `ExactTimetableTrip.runtime_minutes` or `resolved_arrival_time`. They MUST NOT overwrite it with the scenario default.

### 2.3 Legacy allowed-runtime range

`ScenarioParameters.allowed_trip_runtime_minutes` is a legacy input-validation range, not a new Contract V1 output field.

For legacy workbook normalization:

- an explicit trip arrival/runtime MUST fall within the configured allowed range;
- an explicit value outside the range is a blocking normalization error;
- when arrival is absent, the existing conservative fallback remains the maximum configured runtime;
- the adapter MUST NOT clamp an explicit runtime into the range;
- the adapter MUST NOT silently replace an out-of-range runtime with the fallback.

Required stable error code:

`TRIP_RUNTIME_OUTSIDE_ALLOWED_RANGE`.

The error is an input/source inconsistency, not a fleet or parameter-infeasibility conclusion.

### 2.4 C runtime lock

Contract V1 default C generation uses one-to-one B-to-C trip mapping. Each C trip MUST inherit the runtime of its source B trip:

`C.runtime_minutes(source_b_trip_id) = B.runtime_minutes(source_b_trip_id)`.

Moving a departure changes arrival and ready timestamps, but it does not change trip runtime.

A runtime change would require a separately authorized contract and is outside V1-H2.

The independent validator MUST derive:

`expected_c_arrival = c_departure_time + source_b_runtime_minutes * 60`.

Candidate claims that disagree are rejected with stable codes:

- `SOURCE_RUNTIME_LOCK_VIOLATION` when the candidate runtime differs from its source B trip;
- `CANDIDATE_ARRIVAL_RUNTIME_MISMATCH` when candidate arrival does not equal C departure plus the locked source runtime.

The accepted fleet assignment MUST use validator-derived arrival values.

## 3. Turnaround authority model

### 3.1 Arrival-terminal rule

`turnaround_minutes.terminal_1` applies to a vehicle after it arrives at terminal 1.

`turnaround_minutes.terminal_2` applies to a vehicle after it arrives at terminal 2.

For an outbound trip from terminal 1 to terminal 2:

`ready_time = arrival_time + turnaround_minutes.terminal_2 * 60`.

For an inbound trip from terminal 2 to terminal 1:

`ready_time = arrival_time + turnaround_minutes.terminal_1 * 60`.

Using the departure-terminal value is incorrect.

### 3.2 Regulatory minimum

The regulatory minimum applies separately to both terminals:

- intra-provincial route: at least 5 minutes at each terminal;
- inter-provincial route: at least 15 minutes at each terminal.

A larger configured value at either terminal is a hard constraint for that terminal.

The authoritative evaluator and independent validator MUST NOT use:

- `min(terminal_1, terminal_2)`;
- a simple average;
- the value of the departure terminal;
- a scalar legacy layover in place of the normalized terminal-specific values.

### 3.3 Equal turnaround is not a Contract V1 restriction

A valid normalized scenario may declare, for example:

- terminal 1 turnaround: 5 minutes;
- terminal 2 turnaround: 20 minutes.

The normalized evaluator, problem identity, candidate validation, accepted solution fleet assignment, and terminal stock profiles MUST preserve and apply `5/20` exactly.

The fact that the legacy generator accepts only one layover value is an adapter limitation, not a domain rule.

## 4. Authoritative fleet assignment

### 4.1 Separation from legacy `assign_fleet`

The accepted Contract V1 solution MUST NOT depend on the legacy scalar-layover fleet helper when terminal turnaround values differ.

V1-H2 should add a pure Contract V1 fleet-assignment service inside `contracts_v1`, or equivalently strengthen an existing Contract V1 service, with these inputs:

- exact candidate timetable;
- source B per-trip runtime locks;
- terminal identities;
- terminal-specific turnaround values;
- available fleet limit.

It MUST produce deterministic assignments and independently reconcile with the continuous terminal-stock assessment.

### 4.2 Deterministic assignment rule

Trips are processed in deterministic order:

`(departure_time, c_trip_id)`.

A vehicle is eligible only when:

- it is located at the trip's departure terminal; and
- `vehicle.ready_time <= trip.departure_time`.

When multiple vehicles are eligible, select deterministically by:

1. latest ready time;
2. vehicle ID as tie-breaker.

When none is eligible, create a new initial vehicle at that terminal.

Ready events at an identical timestamp are available before departures at that timestamp.

No deadhead, teleportation, runtime shortening, turnaround shortening, or simultaneous use of one vehicle is permitted.

### 4.3 Reconciliation requirements

The independent assignment MUST reconcile with the authoritative stock assessment:

- assignment vehicle count equals `minimum_required_fleet`;
- recommended initial vehicles by terminal reconcile with the stock calculation;
- every assignment arrival uses exact locked per-trip runtime;
- every ready time uses turnaround at the arrival terminal;
- all terminal stock values remain non-negative;
- `minimum_required_fleet <= available_fleet_limit` for acceptance.

Required rejection codes as applicable:

- `FLEET_ASSIGNMENT_RECONCILIATION_MISMATCH`;
- `INITIAL_TERMINAL_STOCK_MISMATCH`;
- `ARRIVAL_TERMINAL_TURNAROUND_MISMATCH`;
- `AVAILABLE_FLEET_LIMIT_EXCEEDED`.

## 5. Heuristic compatibility bridge

### 5.1 Trust boundary

`ScheduleProblemV1.legacy_parameters` is an internal compatibility view for the current heuristic adapter. It is not the authority for normalized runtime or turnaround facts.

The problem builder MUST derive the compatibility view from the authoritative normalized B scenario and the reconciled legacy inputs. Caller-supplied scalar layover MUST NOT override normalized terminal values.

### 5.2 Conservative asymmetric-turnaround bridge

The first V1-H2 implementation MAY continue using the unchanged legacy generator by setting its internal scalar compatibility layover to:

`max(turnaround_terminal_1, turnaround_terminal_2)`.

This mode is named:

`conservative_max_terminal_turnaround`.

This value is used only during heuristic search. It is not used by authoritative evaluation or final candidate validation.

The bridge is safe because it never shortens either terminal turnaround. It may miss a feasible candidate that requires the shorter terminal value. Therefore:

- heuristic exhaustion under this bridge maps to `UNKNOWN`, never `INFEASIBLE`;
- the outcome limitation MUST disclose the conservative bridge;
- a missed candidate is not proof that B's locked parameters are infeasible;
- every returned candidate is independently validated with the exact terminal-specific values.

The problem fingerprint MUST include:

- exact terminal 1 turnaround;
- exact terminal 2 turnaround;
- compatibility bridge mode;
- scalar compatibility layover used by the heuristic.

### 5.3 Equal-turnaround parity

When terminal turnaround values are equal, the compatibility bridge value equals the authoritative value. Existing direct-generator versus adapter timetable parity MUST remain green.

## 6. Operating-lock semantics

The existing generic `operating_parameter_locks` array can express the required authority without adding a new external JSON field.

V1-H2 accepted solutions MUST include locks for at least:

- `trip_runtime_minutes` — retained for compatibility, explicitly meaning the scenario default/fallback runtime;
- `runtime_lock_mode = fixed_by_source_trip`;
- `exact_trip_runtime_minutes_by_source_b_trip_id` — deterministic mapping sorted by source B trip ID;
- `turnaround_minutes` — object containing terminal 1 and terminal 2 values;
- `turnaround_application_mode = arrival_terminal_specific`;
- `heuristic_turnaround_bridge_mode` and bridge value when the heuristic adapter was used.

All lock entries use the authoritative source B fingerprint.

The solution explanation/limitations MUST distinguish:

- authoritative per-trip runtime and terminal turnaround;
- internal conservative heuristic approximation, when present.

## 7. Fingerprint identity

V1-H1 already binds problem, candidate, solution, and outcome identity. V1-H2 clarifies that the hashed authoritative problem and solution evidence MUST include:

- scenario default/fallback runtime;
- complete exact B per-trip runtime mapping;
- exact terminal-specific turnaround values;
- turnaround application mode;
- heuristic compatibility bridge mode/value;
- validator-derived C arrival and ready timestamps;
- authoritative fleet assignments and stock evidence.

Two problems that differ only in one trip runtime or one terminal turnaround MUST have different problem fingerprints.

Two accepted solutions that produce different arrival/ready evidence MUST have different solution fingerprints.

## 8. Versioning and compatibility

V1-H2 remains Contract `1.0.0` hardening.

It does not add or remove top-level JSON properties or enum values.

The following are permitted within existing shapes:

- stronger domain validation;
- additional entries in the generic operating-lock array;
- different fingerprint values due to more complete identity payloads;
- additional explanations and limitations;
- an internal Contract V1 fleet-assignment helper.

V1-H2 MUST NOT:

- rename serialized fields;
- add runtime or arrival fields to `SolutionTripV1` schema;
- add separate terminal turnaround fields to the legacy workbook;
- modify production Streamlit or workbook templates;
- claim heuristic global infeasibility under the conservative bridge;
- change demand logic or implement V1-A1.

A future contract version may expose per-trip runtime directly in accepted C timetable rows. Until then, authority is carried by source traceability, operating locks, fleet assignment arrival/ready evidence, and solution fingerprints.

## 9. Implementation boundary for Codex

### 9.1 Expected files

Implementation should remain concentrated in:

- `src/bus_schedule_engine/contracts_v1/adapters.py`;
- `src/bus_schedule_engine/contracts_v1/solver_problem.py`;
- `src/bus_schedule_engine/contracts_v1/heuristic_solver.py`;
- `src/bus_schedule_engine/contracts_v1/solver_validation.py`;
- a small pure Contract V1 fleet-assignment module if needed;
- `tests/test_contract_v1_inputs.py` or the existing normalization test file;
- `tests/test_contract_v1_solver.py`.

`evaluation.py` may be changed only when necessary to share a pure terminal-specific chronology helper without changing disposition semantics.

### 9.2 Prohibited files and areas

Codex MUST NOT modify:

- `src/bus_schedule_engine/c_generator.py`;
- legacy `src/bus_schedule_engine/fleet.py` unless a separately approved design amendment proves unavoidable;
- Streamlit/application files;
- diagram or XLSX code;
- workbook templates;
- V1-A1 / `1.1.0` contracts;
- OR-Tools code;
- demand-resolution behavior.

### 9.3 Required implementation sequence

1. Add normalization validation for explicit legacy runtimes against the configured range.
2. Establish and test scenario-default versus exact-trip runtime semantics.
3. Remove equal-turnaround as a domain requirement from the heuristic problem bridge.
4. Derive the conservative heuristic compatibility layover from normalized B.
5. Bind exact runtime/turnaround and bridge evidence into problem identity.
6. Add Contract V1-native deterministic fleet assignment using exact runtimes and arrival-terminal turnaround.
7. Reconcile candidate runtime and arrival claims independently.
8. Construct fleet assignments, arrival/ready evidence, stock profiles, and locks from validator-derived facts.
9. Add adversarial tests and run the full validation suite.

## 10. Mandatory adversarial regression suite

At minimum, tests MUST prove:

1. scenario default runtime 60 with exact B trip runtimes 55 and 65 is valid when source evidence permits that range;
2. downstream fleet assessment uses each exact trip runtime, not scalar 60 or fallback 65 for all trips;
3. explicit legacy runtime outside the allowed range fails with `TRIP_RUNTIME_OUTSIDE_ALLOWED_RANGE`;
4. a trip without arrival uses the maximum configured fallback runtime;
5. candidate runtime differing from source B is rejected;
6. candidate arrival inconsistent with locked runtime is rejected;
7. accepted solution arrival timestamps are derived from source B per-trip runtimes;
8. turnaround `5/20` applies 20 minutes to arrivals at terminal 2 and 5 minutes to arrivals at terminal 1;
9. problem construction accepts a valid normalized `5/20` scenario instead of requiring equality;
10. heuristic compatibility uses scalar 20 under `conservative_max_terminal_turnaround`;
11. heuristic exhaustion under that bridge remains `UNKNOWN`, not `INFEASIBLE`;
12. accepted candidate validation uses exact `5/20`, not scalar 20 at both terminals;
13. exact turnaround feasibility may accept a candidate even though the conservative bridge is stricter;
14. a candidate violating the 20-minute terminal turnaround is rejected;
15. ready-at-same-timestamp is available before departure;
16. simultaneous trips require separate vehicle stock;
17. deterministic fleet assignment count reconciles with authoritative minimum fleet;
18. operating locks include fallback runtime, exact source-trip runtime map, terminal turnaround, and arrival-terminal mode;
19. problem fingerprint changes when one exact trip runtime changes;
20. problem fingerprint changes when only terminal 1 or terminal 2 turnaround changes;
21. solution fingerprint changes when authoritative arrival/ready evidence changes;
22. equal-turnaround direct heuristic and adapter parity remains unchanged;
23. accepted solution and outcome continue validating existing Contract `1.0.0` schemas;
24. full Pytest, Ruff lint, Ruff format, and existing schema checks remain green.

## 11. Acceptance gate

V1-H2 is complete only when:

- per-trip runtime is the authoritative operational runtime;
- scenario runtime is used only as documented fallback/default metadata;
- explicit legacy runtime evidence is validated against the configured range;
- C runtime is locked one-to-one to source B trips;
- terminal turnaround is applied at the arrival terminal;
- asymmetric turnaround is accepted at the normalized and solver-boundary layers;
- the heuristic bridge is conservative, disclosed, and never used as proof of infeasibility;
- accepted fleet assignment and stock evidence are independent of legacy scalar-layover authority;
- fingerprints distinguish runtime and turnaround changes;
- no external Contract `1.0.0` shape or enum changes;
- no prohibited scope drift;
- the full validation suite is green.

## 12. Explicitly deferred work

The following remain separate tasks:

- uncovered gaps in demand-observation coverage;
- full machine-readable `ScheduleProblemV1` alignment;
- direct normalized UI/API inputs for separate terminal turnaround values;
- legacy workbook columns for separate terminal turnarounds;
- production runtime cutover;
- V1-A1 structural demand-response implementation;
- OR-Tools feasibility and optimization.