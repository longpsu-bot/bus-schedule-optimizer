# Project Direction Reset

**Status:** Active implementation authority

**Baseline:** `main@bb9b4837edac5303e754225ca04cbde900cdcd1c`

**Effective date:** 2026-07-26

This document governs the practical implementation direction of the repository. Where an
implementation plan in another document conflicts with this reset, this document controls the
roadmap. Existing Contract V1 scheduling rules remain authoritative unless this document
explicitly defers an implementation stage.

## Product purpose

The repository is a one-route bus-schedule validation and optimization engine. It exists to:

1. import and normalize current and proposed timetable data;
2. validate the submitted timetable and its operating parameters;
3. quantitatively determine whether adjustment is needed;
4. generate feasible alternatives through a deterministic heuristic and OR-Tools CP-SAT;
5. independently validate every generated candidate;
6. compare accepted alternatives through transparent objective vectors; and
7. export decision-support charts and editable XLSX schedules.

The engine supports expert decisions. It does not automatically publish or operate a timetable.

The repository is not a distributed system, authorization framework, API platform, generic
workflow engine, or internal-contract provenance system.

## Simplified target pipeline

```text
Workbook/UI input
-> import and normalize
-> validate inputs and evaluate Scenario B
-> quantify whether adjustment is needed
-> build one canonical ScheduleProblemV1 when solving is appropriate
-> run the heuristic solver and/or OR-Tools CP-SAT
-> independently validate every raw candidate
-> accept only conforming solutions
-> compare transparent objective vectors
-> render charts and export editable XLSX
```

One unified application service will own this sequence. Solver selection is ordinary application
configuration. It does not require an authorization protocol between internal Python functions.

## Retained hard constraints

The implementation MUST retain the scheduling and validation rules already established by
Contract V1, including:

- one route with two terminals and directional departures;
- exact source-trip runtime;
- terminal-specific minimum turnaround at the arrival terminal;
- locked total trip count and, for the first target, locked directional trip counts;
- locked first and last departures;
- chronological trip order and one-to-one B-to-C traceability;
- an available-fleet upper bound;
- solver-determined initial terminal positioning by default;
- non-negative terminal stock on the continuous event timeline;
- no deadhead, teleportation, shortened runtime, or shortened turnaround;
- authoritative demand grain and no fabricated directional or finer-grained demand;
- one-sided load-factor and demand-shortage treatment;
- headway continuity across demand-block boundaries;
- independent validation after every solver run; and
- no authoritative Scenario C unless the candidate passes that validator.

Runtime, turnaround, fleet, demand-coverage, load-factor, headway, and validation rules are not
weakened by this reset.

## Retained core contracts

The following remain active domain and solver authority:

- normalized Scenario A, Scenario B, and observed-demand inputs;
- authoritative Scenario B evaluation;
- demand resolution, coverage, and block-supply calculations;
- exact runtime and terminal-turnaround authority;
- `ScheduleProblemV1`;
- the `ScheduleSolver` interface;
- raw solver candidates;
- the independent domain validator;
- accepted `ScheduleSolutionV1`;
- `ScheduleGenerationOutcomeV1`; and
- the quantitative service-adjustment evaluator.

The existing schemas remain unchanged by this documentation reset.

## Permitted fingerprints

Fingerprints are permitted where stable identity is useful for persistence, caching,
reconciliation, or reproducibility. Appropriate subjects are:

- normalized persisted inputs;
- canonical solver problems;
- raw candidates;
- accepted solutions; and
- generation outcomes.

Fingerprints prove identity, not correctness. They are not authorization tokens between ordinary
Python functions. The engine does not need a fingerprint chain that grants internal execution
authority from evaluator to router to request to orchestrator.

## Prohibited internal architecture

Do not implement:

- authorization profiles for ordinary solver calls;
- capability-routing contracts or routing policies;
- authorized-problem request objects;
- legacy assessment projections;
- orchestration envelopes;
- internal bearer-token semantics;
- a phase-by-phase authorization fingerprint chain; or
- parallel public entry points whose only purpose is to model an internal workflow protocol.

No authorization profile, legacy projection, routing policy, or orchestration envelope should be
implemented.

`V1-D2` Phases B through E are cancelled. Commit
`bc391e1967957fd530b51755331ce92da0bfdea8` MUST NOT be merged, cherry-picked, or copied into the
active implementation.

Phase A may remain temporarily as a quantitative pre-problem evaluator. Its useful separation is:
evaluate the need for adjustment before building a solver problem. It must not grow into the
cancelled capability-routing or authorization architecture.

## Solver roles

### Heuristic solver

The deterministic heuristic remains a useful baseline, fast fallback, regression oracle, and
possible CP-SAT hint source. It must cross the canonical problem/candidate/validator boundary
before the application treats its result as an accepted solution. It does not prove optimality or
global infeasibility.

### OR-Tools CP-SAT solver

CP-SAT is the target proof-oriented solver. Its first implementation is hard feasibility for one
route, two terminals, fixed total and directional trips, exact runtimes, terminal-specific
turnaround, locked endpoints, the available-fleet upper bound, and solver-determined initial
positioning. Demand objectives are not part of the first feasibility pull request.

### Independent validator

The validator, not either solver, is the acceptance authority. It reconstructs and verifies
runtime, turnaround, terminal stock, fleet, locks, trip traceability, block reconciliation, and
other domain invariants. Only a candidate that passes validation becomes `ScheduleSolutionV1`.

## Current dual-stack state

At the governing baseline the repository has two separate paths:

1. The application runtime is the legacy MVP under `streamlit_app.py`, `app_pages/`, and the
   non-`contracts_v1` modules in `src/bus_schedule_engine/`. It imports workbooks, validates and
   evaluates B, runs the legacy heuristic, renders Plotly charts, and exports XLSX.
2. `src/bus_schedule_engine/contracts_v1/` is a separately tested target domain and solver
   boundary. It includes normalization, B evaluation, demand authority, `ScheduleProblemV1`, a
   solver protocol, a legacy-heuristic adapter, raw-candidate handling, independent validation,
   result envelopes, and the Phase A quantitative evaluator.

These paths are not integrated. The Streamlit application does not call the Contract V1 public
boundary. OR-Tools is not a dependency and no CP-SAT adapter or model exists.

## Implementation milestones

1. **Documentation reset and unified application service.** Establish this direction and create
   one service boundary that can run Contract V1 normalization, evaluation, adjustment assessment,
   problem construction, solver selection, validation, comparison, and presentation adapters.
2. **Heuristic integration.** Route the existing deterministic heuristic through the canonical
   `ScheduleProblemV1` -> raw candidate -> independent validator flow without changing its
   algorithm.
3. **OR-Tools hard feasibility.** Add CP-SAT for the fixed-resource one-route target and prove the
   complete hard-constraint set on tiny fixtures.
4. **Fixed-resource demand/headway optimization and route corpus.** Add lexicographic demand,
   service-gap, regularity, and shift objectives only after feasibility is proven; validate both
   solvers on anonymized real-route fixtures.
5. **UI/XLSX cutover and side-by-side validation.** Make the unified service authoritative for the
   UI and exports, compare legacy/heuristic/CP-SAT results during cutover, and remove duplicated
   calculations from presentation code.

Variable-trip-count optimization and structural demand-response scenarios are later optional
work. They do not block fixed-resource hard feasibility.

## Acceptance criteria

The active direction is implemented when:

- the application uses one Contract V1-based service path;
- legacy heuristic output crosses the canonical problem and independent-validator boundary;
- CP-SAT can find or prove hard feasibility for the defined fixed-resource scope;
- both solvers are compared using the same transparent objective vector and validation result;
- tiny proof cases and anonymized real-route fixtures cover difficult headway, turnaround, and
  fleet cases;
- no candidate is presented or exported as Scenario C before independent validation;
- charts and XLSX consume authoritative domain results without recalculating optimization facts;
- source workbooks are never overwritten;
- OR-Tools capabilities and solver statuses are stated honestly; and
- no cancelled authorization/routing/orchestration architecture is introduced.

## Document disposition

### Active

- `ENGINE_CONTRACT_V1.md` for scheduling, solver, validation, and output rules;
- `RESULT_ENVELOPE_CONTRACT_V1.md`;
- normalized input, B evaluation, demand resolution/coverage, runtime/turnaround,
  `ScheduleProblemV1`, solver boundary, and validator documents;
- `SERVICE_ADJUSTMENT_NEED_EVALUATOR_V1.md`, limited to its quantitative pre-problem evaluator;
- this direction reset, the current-state audit, migration roadmap, CP-SAT target design, and test
  strategy as amended by this reset.

### Superseded for implementation

- `ADJUSTMENT_DECISION_ORCHESTRATION_BOUNDARY_V1.md`, except for the Phase A separation of
  quantitative pre-problem evaluation.

### Deferred

- `EXTREME_SERVICE_CHANGE_AND_DEMAND_SCENARIO_AMENDMENT_V1.md` (`V1-A1`);
- variable-trip-count increase/reduction solvers;
- structural demand-response scenario selection and monitoring;
- mixed fleet, multi-route, deadhead, driver duties, depot, and maintenance optimization.
