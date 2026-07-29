# Bus Schedule Optimization Engine

This repository is a local, deterministic decision-support tool for validating and improving a
one-route, two-terminal bus timetable. It imports timetable workbooks, checks operating
constraints, evaluates demand and service, generates heuristic alternatives, renders charts, and
exports editable XLSX workbooks.

The active product direction is defined in
[Project Direction Reset](docs/engine/PROJECT_DIRECTION_RESET.md).

## Current implementation state

The repository currently contains two separate paths.

### Legacy MVP application runtime

`streamlit_app.py`, `app_pages/`, and the non-`contracts_v1` modules under
`src/bus_schedule_engine/` are the application that runs today. This path:

- imports the legacy workbook format;
- validates Scenario B with the legacy validator;
- evaluates demand at the legacy block grain;
- generates deterministic fixed-resource Scenario C candidates;
- assigns fleet with the legacy greedy two-terminal algorithm;
- compares scenarios with the legacy scoring configuration;
- renders Plotly charts; and
- exports the existing XLSX reports.

### Contract V1 target domain and solver boundary

`src/bus_schedule_engine/contracts_v1/` is a separately tested target boundary. It provides:

- normalized Scenario A, Scenario B, and observed-demand models and adapters;
- authoritative demand resolution, coverage, and Scenario B evaluation;
- the canonical `ScheduleProblemV1`;
- the solver-neutral `ScheduleSolver` interface;
- raw candidate, independent validator, accepted solution, and generation-outcome contracts;
- a compatibility adapter for the existing heuristic; and
- the quantitative pre-problem service-adjustment evaluator from V1-D2 Phase A.

Milestone 5A1 now runs the two result-producing paths through a deterministic side-by-side
validation adapter. This creates review evidence without changing application behavior. The
Streamlit application, charts, and XLSX exports still use the legacy path and do not yet consume
unified Contract V1 results.

Milestone 5A2A adds a separate authoritative-input readiness gate. Generated workbooks label
fields as required, required for optimization, or optional. A blank optimization-only authority
field still imports, but `normalization_options_from_workbook_v1(...)` fails closed with stable
codes before Contract V1 normalization. See
[Milestone 5A2A authoritative input template](docs/engine/MILESTONE_5A2A_AUTHORITATIVE_INPUT_TEMPLATE.md).

Milestone 5A2B adds parallel validation-only unified chart and editable-XLSX adapters. Both chart
types and the workbook consume one deterministic unified presentation fingerprint built from the
Contract V1 result and the Milestone 5A1 report. This does not cut over Streamlit: the current UI,
session state, charts, and downloads remain legacy-authoritative. See
[Milestone 5A2B unified presentation adapters](docs/engine/MILESTONE_5A2B_UNIFIED_PRESENTATION_ADAPTERS.md).

Milestone 5B1 completes the shadow runtime: unified Contract V1 runs once in the real Streamlit
submission flow when authoritative input is ready and stores aligned validation evidence in
parallel session state. Milestone 5B2A now cuts over visible diagnostic and recommendation Pages
02–04 through one explicit authority resolver; missing, failed, blocked, or inconsistent shadow
evidence retains a prominently labeled legacy fallback. Page 05 charts and downloads remain
entirely legacy-authoritative, and Milestone 5B2B remains pending. See
[Milestone 5B1 Streamlit shadow runtime](docs/engine/MILESTONE_5B1_STREAMLIT_SHADOW_RUNTIME.md)
and
[Milestone 5B2A unified result pages](docs/engine/MILESTONE_5B2A_UNIFIED_RESULT_PAGES.md).

Contract V1 includes separate OR-Tools v9.15 CP-SAT adapters for one-route, fixed-resource hard
feasibility, directional demand-priority optimization, and service-quality optimization. The
feasibility adapter remains an objective-free satisfaction model. Demand protection remains the
highest optimization priority. The service-quality adapter then protects positive-demand service
gaps, aligns fixed directional trips with exact rational passenger demand, and enforces exactly
uniform headways inside each demand-derived sustained service regime. Headway remains adaptive
between regimes; no route-wide fixed headway is imposed.
All three adapters use canonical request builders and the independent validator. The unified
application service now supports explicit `SolverChoice.HEURISTIC`, `OR_TOOLS`, and `BOTH` for
fixed-resource actions, while the default remains `HEURISTIC`. `OR_TOOLS` selects the 15-stage
service-quality adapter. `BOTH` independently validates both outcomes, recomputes the same
transparent lexicographic objective vector for accepted solutions, and recommends one outcome
without a weighted score. Streamlit does not yet expose this selection.

Contract V1 keeps three independent quantities:

- **available fleet** is the hard upper bound on active route vehicles;
- **ready stock** changes at `arrival + terminal turnaround` and controls whether a vehicle can
  serve another departure; and
- **physical terminal occupancy** changes at arrival and departure and includes positioned,
  unloading, turnaround, ready, waiting, boarding, and departing route vehicles.

Therefore, available fleet != ready stock != physical terminal occupancy. Scenario B may
optionally supply `terminal_occupancy_limits` for either or both terminals. Scenario B evaluation,
all three canonical OR-Tools adapters, and independent candidate validation then enforce each
supplied value as a hard physical-capacity constraint. Arrivals count before departures at the
same minute. When neither value is supplied, the result retains
`TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED`; a limit is never inferred from fleet, approved fleet,
or the timetable. See
[Contract V1 terminal physical occupancy](docs/engine/TERMINAL_OCCUPANCY_CAPACITY_V1.md) for the
event equation, CP-SAT model size, and independent reconstruction boundary.

## Supported today

- One route, two terminals, and two timetable directions.
- Workbook import with Scenario B required and Scenario A/demand/configuration optional.
- Legacy technical validation for totals, endpoints, runtime, turnaround, and declared vehicle
  chains.
- Multi-day demand normalization and legacy load-factor/headway evaluation.
- Deterministic fixed-total, fixed-direction heuristic re-spacing/redistribution.
- B-to-C trip traceability and timetable fingerprints in the legacy runtime.
- Plotly diagnostics and editable XLSX output.
- Separately tested Contract V1 normalization, B evaluation, demand authority, canonical problem,
  heuristic adapter, raw-candidate validation, solution/outcome, and quantitative adjustment
  assessment.
- OR-Tools v9.15 hard-feasibility solving through the Contract V1 adapter and independent
  validator.
- Optional authoritative per-terminal physical vehicle-occupancy capacities, reconstructed from
  grouped arrival/departure events and enforced by every canonical OR-Tools hard model.
- Separate OR-Tools fixed-resource demand-priority solving for authoritative directional demand,
  covering no-service and overload protection before provisional B-preservation shift tie-breaks.
- Separate OR-Tools fixed-resource service-quality solving for positive-demand gaps, exact
  rational directional-demand alignment, and hard uniform headways within derived sustained
  service regimes, with solver-determined transition headways between regimes.
- Unified fixed-resource solver selection with heuristic-only continuity by default, explicit
  15-stage OR-Tools service-quality solving, and transparent `BOTH` comparison of independently
  validated accepted solutions.
- Parallel validation-only unified demand/supply and exact-departure figures plus an editable
  formula-free XLSX workbook, all aligned by one semantic presentation fingerprint.

## Not supported yet

- Contract V1 authority for Page 05 charts, PNG/HTML generation, or downloads through the
  Streamlit application.
- Solver selection through Streamlit.
- OR-Tools fleet-minimization objectives.
- A globally optimal timetable or a proof of infeasibility from the legacy heuristic.
- Operational-timetable, ridership-forecast, or solver-quality approval of the anonymized
  real-route corpus.
- Variable-trip-count optimization.
- Accepted zero-trip or one-trip headway regimes under the current public Contract V1 shape;
  supporting those cases requires a separately authorized future Contract revision.
- Production implementation of the deferred V1-A1 structural demand-response workflow.
- Mixed fleets, multi-route interlining, deadhead, driver duties, depot pull-in/out, maintenance,
  or mature cross-midnight optimization.
- The current Streamlit charts and downloads do not yet consume unified Contract V1 optimization
  results; the Milestone 5B1 runtime stores them as parallel validation artifacts only.

## Target pipeline

```text
Workbook/UI
-> import and normalize
-> validate and evaluate B
-> quantify whether adjustment is needed
-> build ScheduleProblemV1
-> heuristic and/or OR-Tools CP-SAT
-> independent domain validator
-> accepted solution and transparent objective vector
-> charts and editable XLSX
```

Only an independently validated candidate may be presented as authoritative Scenario C.

## Near-term roadmap

Milestone 4C2C is complete. **Milestone 5A1 side-by-side result validation, Milestone 5A2A
authoritative input readiness, Milestone 5A2B validation-only presentation adapters, Milestone
5B1 Streamlit shadow execution, and Milestone 5B2A unified result Pages 02–04 are implemented**,
but Milestone 5 is not complete.

1. Milestone 5A1: compare deterministic legacy and unified result snapshots.
2. Milestone 5A2A: stabilize authoritative workbook input and readiness.
3. Milestone 5A2B: validate parallel unified presentation adapters for charts and XLSX
   (implemented; no Streamlit cutover).
4. Milestone 5B1: run Contract V1 once in Streamlit and store non-authoritative shadow evidence
   (implemented; visible pages and downloads remain legacy).
5. Milestone 5B2A: cut over Pages 02–04 through the explicit visible-result authority gate
   (implemented; Page 05 remains legacy).
6. Milestone 5B2B: separately cut over charts and downloads (pending).

See
[Milestone 5A1 side-by-side validation](docs/engine/MILESTONE_5A1_SIDE_BY_SIDE_VALIDATION.md)
for comparison and Scenario C authority rules.

## Reviewed anonymized route corpus

Milestone 4C2C approves the versioned, anonymized, real-route-derived fixtures under
`tests/fixtures/route_corpus/v1/`. The private source workbooks remain external and uncommitted.
Overlapping raw trip-observation evidence is preserved separately from a LOW-confidence,
departure-hour sensitivity proxy. Proxy values retain their exact 15-day
`total_observation_period` classification, and Contract V1 derives daily demand using the
15-day observation count without rounding or truncation. Alpha now reaches real-route-derived
LOW-confidence sensitivity characterization when the exact canonical request is constructible;
Beta remains solver-free because its evidence has an unobserved interior hour.

The corpus status is **REVIEWED DIAGNOSTIC BASELINE**. It protects source facts, anonymization,
normalization, proxy construction, coverage handling, exact demand authority, request
eligibility, honest solver-status interpretation, and the rule against fabricated operational
facts. It is not an approved operational timetable, ridership forecast, optimal schedule,
solver-performance benchmark, solver-quality baseline, or terminal-capacity-feasibility
baseline. Current solver outcomes and timings remain non-frozen diagnostic observations.

See
[Route Corpus Reviewed Baseline V1](docs/engine/ROUTE_CORPUS_REVIEWED_BASELINE_V1.md) for the
approved policy boundary and
[Route Corpus Characterization Draft V1](docs/engine/ROUTE_CORPUS_CHARACTERIZATION_DRAFT_V1.md)
for detailed historical evidence. The Streamlit UI, charts, and XLSX exports have not yet migrated
in full to unified Contract V1 results. Pages 02–04 may now display aligned unified facts through
the 5B2A authority gate, while Page 05 charts and XLSX/PNG/HTML exports remain
legacy-authoritative.

Variable-trip-count optimization and structural demand-response scenarios are optional later
stages. See [Migration Roadmap to OR-Tools](docs/engine/MIGRATION_ROADMAP_TO_OR_TOOLS.md).

## Install

Python 3.11 or later is required. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Run the current legacy application

```powershell
.\.venv\Scripts\streamlit.exe run streamlit_app.py
```

The five Vietnamese UI pages cover input, technical checks, demand evaluation,
recommendations, and chart/XLSX export.

## Validate the repository

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check . --exclude .artifact --exclude outputs --exclude .venv
.\.venv\Scripts\python.exe -m ruff format --check src/bus_schedule_engine/contracts_v1 tests/test_contract*.py
git diff --check
```

## Current workbook conventions

The legacy runtime requires:

- `THONG_SO_B`;
- `BIEU_DO_B`.

Optional sheets are:

- `HUONG_DAN`;
- `THONG_SO_A` and `BIEU_DO_A`;
- `THONG_TIN_DU_LIEU`;
- `SAN_LUONG`;
- `CAU_HINH`.

`total_daily_trips` is the total across both directions.
`vehicle_capacity_passengers` is required. Times use `HH:mm`; dates use `dd/mm/yyyy`.
`allowed_trip_runtime_minutes` accepts an inclusive integer range such as `55,65` or `55;65`.
Blank `available_fleet_limit` or `operating_day_type` permits import but blocks authoritative
fixed-resource optimization. Demand source type, confidence, and response mode become required
for optimization only when `SAN_LUONG` has observations.
`THONG_SO_B` may optionally include `terminal_1_max_occupancy_vehicles` and
`terminal_2_max_occupancy_vehicles`; each supplied value must be an integer of at least one.
Either key may be omitted, and no current workbook is required to contain either key.
Combined demand remains combined and must not be fabricated into directional demand.

The current exporters create new workbooks and do not overwrite `Schedule template.xlsx`.
