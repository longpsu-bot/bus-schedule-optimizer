# Current-State Gap Analysis

**Audit date:** 2026-07-26

**Audited merged main:** `bb9b4837edac5303e754225ca04cbde900cdcd1c`

**Governing direction:** [Project Direction Reset](PROJECT_DIRECTION_RESET.md)

This audit describes the actual merged main branch. It replaces the 22 July baseline audit and
does not treat unmerged Phase B commit `bc391e1967957fd530b51755331ce92da0bfdea8` as repository
state.

## Executive finding

The repository is a dual stack:

- the Streamlit application still runs the legacy MVP pipeline; and
- `contracts_v1` is a substantial, separately tested target domain and solver boundary.

The two paths are not integrated. The legacy heuristic has a Contract V1 compatibility adapter,
but the application service, UI, charts, and exporters do not call that boundary. No OR-Tools
dependency, CP-SAT model, or CP-SAT adapter exists.

The next work is integration and hard-feasibility solving, not another internal authorization or
workflow-contract layer.

## Actual runtime paths

### Legacy application runtime

The executable application path is:

```text
streamlit_app.py
-> app_pages/
-> importer.py
-> service.py::run_analysis()
-> validator.py / demand.py / fleet.py / comparator.py
-> generator.py / c_generator.py
-> diagram.py
-> excel_exporter.py / comparison_exporter.py
```

`service.py::run_analysis()` validates and evaluates B, derives an active fleet value, invokes the
legacy deterministic generator, evaluates returned scenarios, asserts B immutability and B-to-C
locks, and returns an `AnalysisBundle`.

No non-Contract V1 runtime module imports `contracts_v1`. Therefore Contract V1 does not power the
current Streamlit UI or its exports.

### Contract V1 target path

The separately tested target path is:

```text
contracts_v1/adapters.py
-> normalized models and validation
-> authoritative B evaluation and demand coverage
-> ScheduleProblemV1
-> ScheduleSolver
-> heuristic compatibility adapter
-> raw candidate
-> independent solution validator
-> ScheduleGenerationOutcomeV1 / ScheduleSolutionV1
```

The active public pre-problem path in `contracts_v1/public_api.py` is:

```text
normalized bundle
-> evaluate_scenario_b_v1()
-> build_service_adjustment_evaluation_context_v1()
-> evaluate_service_adjustment_need_v1()
```

This Phase A quantitative separation is useful. It has no application-runtime caller on main.

## Useful completed work on main

The following work is reusable and should not be rebuilt:

- normalized Scenario A, Scenario B, observed-demand, source-metadata, fleet-limit, and exact
  timetable models;
- legacy workbook-to-Contract V1 normalization adapters;
- schema, serialization, and validation coverage for the current Contract V1 shapes;
- native/adaptive/manual demand-resolution primitives;
- authoritative B evaluation and one-sided load-factor/block-supply rules;
- temporal and directional demand-coverage authority;
- exact source-trip runtime and arrival-terminal turnaround hardening;
- terminal-aware fleet assessment and continuous-stock validation;
- canonical `ScheduleProblemV1`, operating locks, problem serialization, fingerprints, and
  independent problem validation;
- solver-neutral `ScheduleSolver`, raw candidate, solution, outcome, and native-status contracts;
- a legacy-heuristic compatibility context and adapter;
- independent candidate validation before accepted-solution construction;
- quantitative service-adjustment decisions and Phase A pre-problem evaluation context;
- legacy B immutability, B-to-C one-to-one traceability, deterministic ordering, and workbook
  no-overwrite behavior; and
- substantial synthetic regression coverage for both the legacy MVP and Contract V1 boundary.

## Unintegrated components

These components exist but are not wired into the running application:

- normalized Contract V1 inputs and authoritative B evaluation;
- the Phase A adjustment-need evaluator;
- `ScheduleProblemV1` construction;
- the Contract V1 heuristic adapter;
- raw-candidate and independent-solution validation;
- Contract V1 generation outcomes and accepted solutions; and
- Contract V1 serializers and target workbook/visualization semantics.

The current `build_heuristic_schedule_request_v1()` remains a library/test composition helper. It
constructs the compatibility context and canonical problem, but `service.py::run_analysis()` does
not call it.

## No OR-Tools implementation

`pyproject.toml` contains no OR-Tools dependency. Repository searches find no `cp_model` import,
CP-SAT model builder, solver adapter, or CP-SAT tests. References to an OR-Tools adapter occur only
in documentation, schemas, examples, and schema-test placeholder strings.

The legacy heuristic reports only candidate-search behavior. It cannot prove global optimality or
infeasibility.

## Current conflicts and gaps

### Scoring

`comparator.py` rewards closeness to `target_load_factor` with
`abs(load_factor - target_load_factor)`. This symmetrically penalizes low load and conflicts with
Contract V1's one-sided capacity objective. The comparator also collapses demand, headway, fleet
utilization, and coverage into a weighted scalar, while the target comparison must expose an
ordered objective vector and preserve hard-feasibility precedence.

This scoring remains legacy runtime behavior and must not become the authoritative Contract V1
solver objective.

### Fleet semantics

The legacy application derives `available_fleet_b` as the maximum of B's calculated minimum fleet
and the count of declared vehicle IDs. It then records that derived value as an exact active fleet,
copies active IDs from B to C, and asserts equal active-vehicle count.

The Contract V1 target instead requires:

- an explicit `available_fleet_limit` upper bound;
- independently calculated `minimum_required_fleet`;
- solver-determined initial terminal positioning by default; and
- no requirement that every available or approved vehicle operate.

The two semantics must be reconciled in the unified application service. The legacy exact-active
fleet behavior must not be copied into CP-SAT.

### Combined demand

The legacy evaluator correctly warns that combined demand cannot support a directional conclusion.
However, legacy generation falls back to combined records for each direction, and the older
variable-trip path allocates combined demand using Scenario B's directional trip share as an
assumption.

Contract V1 correctly preserves combined demand as aggregate evidence and requires directional
support for demand-guided directional optimization. The unified service must enforce that
authority before invoking either solver.

### Supply planning and objectives

The legacy heuristic generates exact times and then derives/evaluates supply. It does not make the
Contract V1 `BlockSupplyPlan` the canonical planning input to exact-time optimization. It uses a
bounded deterministic candidate search rather than a proof-oriented hard-feasibility model.

The initial CP-SAT milestone should therefore implement the exact fixed-resource technical problem
first. Demand/headway objectives should follow only after the problem, candidate, and validator
boundary is proven.

### Export and presentation

The legacy runtime produces a general result workbook and a separate B-C comparison workbook with
legacy sheet names and shapes. Presentation/export helpers calculate or re-grid some summaries.
They do not consume a complete Contract V1 accepted solution or generation outcome.

The target is one authoritative domain result consumed by charts and editable XLSX without
re-running allocation, validation, or optimization. UI/XLSX cutover must wait until heuristic and
CP-SAT results reconcile through the same service and solution fingerprint.

### Adjustment/orchestration direction

Phase A on merged main successfully separates quantitative adjustment assessment from the solver
problem. V1-D2 Phases B-E would add capability routing, authorization profiles, legacy
projections, authorized requests, orchestration envelopes, and a long internal fingerprint chain.
That direction is cancelled by the project reset and is not an implementation dependency.

## Test and fixture gaps

Main has broad synthetic unit and integration coverage, including Contract V1 normalization,
evaluation, demand coverage, service adjustment, canonical problems, solver orchestration, and
independent validation. Important gaps remain:

- no CP-SAT tiny feasibility proofs;
- no exhaustive-enumeration oracle for CP-SAT fixtures;
- no heuristic-versus-CP-SAT differential suite;
- no side-by-side application-service integration test;
- no anonymized real-route corpus;
- no difficult real-route fixtures for terminal imbalance, tight fleet, asymmetric runtime or
  turnaround, endpoint locks, and irregular headways;
- no Route 61-8 or Route 61-4 fixture;
- no production-sized CP-SAT benchmark tiers;
- no Contract V1-driven Streamlit upload/download test; and
- no authoritative accepted-solution-to-chart/XLSX reconciliation test.

Route 61-8 and Route 61-4 should be added only when anonymized source data is available and its
provenance, operating day, exact runtimes, turnaround, fleet limit, and demand grain can be
documented.

## Exact recommended next steps

1. Keep this documentation reset on a documentation-only branch and do not merge Phase B commit
   `bc391e1967957fd530b51755331ce92da0bfdea8`.
2. Define one unified application-service API over normalization, B evaluation, Phase A adjustment
   assessment, canonical problem construction, solver selection, independent validation,
   comparison, and presentation outputs.
3. Add a characterization test proving current legacy behavior before changing `service.py`.
4. Route the existing heuristic through `ScheduleProblemV1`, raw candidate, and the independent
   validator; keep its algorithm and legacy UI behavior unchanged during this milestone.
5. Define a transparent comparison vector covering hard feasibility, no-service blocks, overload
   above 90%, overload above 85%, service gaps, regularity, shifted trips/minutes, and fleet as a
   late tie-breaker. Do not reuse the legacy weighted scalar as authority.
6. Implement an OR-Tools CP-SAT adapter for fixed total/directional trips, exact source runtimes,
   terminal-specific turnaround, endpoint locks, available-fleet upper bound, solver-determined
   initial positioning, continuous terminal stock, and independent validation. Include no demand
   objective in the first feasibility pull request.
7. Add 4-12-trip proof fixtures and heuristic/CP-SAT differential tests, then add anonymized
   difficult route fixtures, including 61-8 and 61-4 when their source data is available.
8. Add fixed-resource demand/headway objectives only after the hard-feasibility suite is green.
9. Cut the UI, charts, and XLSX over to the unified authoritative result with side-by-side
   validation and no presentation-layer recalculation.
10. Consider variable-trip-count and V1-A1 structural demand-response work only as later optional
    milestones.
