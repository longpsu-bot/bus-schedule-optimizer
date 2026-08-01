# Bus Schedule Optimization Engine

This repository is a local, deterministic decision-support tool for validating and improving a
one-route, two-terminal bus timetable. It imports timetable workbooks, checks operating
constraints, evaluates demand and service, generates heuristic alternatives, renders charts, and
exports editable XLSX workbooks.

The active product direction is defined in
[Project Direction Reset](docs/engine/PROJECT_DIRECTION_RESET.md).

## Current implementation state

The repository contains one ordinary application runtime and one retained offline regression
oracle.

### Contract V1 ordinary application runtime

Milestone 5C2 is merged and implements the unified-only ordinary Streamlit path. It:

- assesses authoritative-input readiness before analysis;
- runs Contract V1 once for optimization-ready input;
- builds a report-free, fingerprinted unified presentation;
- fails closed on runtime or semantic-integrity failure;
- renders unified Plotly charts and the three Contract V1 downloads; and
- never runs legacy analysis or per-submission side-by-side comparison.

### Supplemental trip-level ridership analysis

Milestone 6A1 adds optional `THONG_TIN_SAN_LUONG_CHUYEN` and
`SAN_LUONG_CHUYEN` workbook sheets. The application deterministically matches those observations
to Scenario B, excludes ambiguous, collided, unmatched, and invalid records, and reports
per-trip descriptive passenger/load statistics plus explicit route and direction coverage.
This evidence is supplemental only: `SAN_LUONG` remains the sole Contract V1 demand authority,
trip records never enter `ObservedDemandInput`, solver requests and Scenario C are unchanged, and
ordinary Streamlit remains Contract V1-only.

Milestone 6A2A derives current direction-separated Scenario B regimes and classifies which
ones have regular short headways plus sufficient repeated P85 trip evidence for a future
protected service floor. Its assessment remains review-only and its previews retain
`NOT_ENFORCED_IN_6A2A`. Milestone 6A2B promotes only a current 6A2A assessment into a separate,
fingerprinted enforcement authority and rejects violating solver candidates at the common
independent validator. Milestone 6A2C now filters the legacy-compatible heuristic's direction
plans against that exact authority before candidate combination; the common validator remains
final. Milestone 6A2D adds the same bound authority as hard constraints to the canonical OR-Tools
service-quality model while retaining independent validation as final. See
[Milestone 6A1 trip-level ridership analysis](docs/engine/MILESTONE_6A1_TRIP_RIDERSHIP_ANALYSIS.md)
and
[Milestone 6A2A protected service-floor authority](docs/engine/MILESTONE_6A2A_PROTECTED_SERVICE_FLOOR_AUTHORITY.md)
and
[Milestone 6A2B protected service-floor acceptance enforcement](docs/engine/MILESTONE_6A2B_PROTECTED_SERVICE_FLOOR_ACCEPTANCE_ENFORCEMENT.md)
and
[Milestone 6A2C protected service-floor-aware heuristic search](docs/engine/MILESTONE_6A2C_PROTECTED_SERVICE_FLOOR_HEURISTIC_SEARCH.md)
and
[Milestone 6A2D protected service-floor OR-Tools constraints](docs/engine/MILESTONE_6A2D_PROTECTED_SERVICE_FLOOR_ORTOOLS_CONSTRAINTS.md).

### Offline legacy regression oracle

Legacy analysis, chart/export code, and the side-by-side adapter remain available for tests and
the explicit `python -m bus_schedule_engine.release_audit` command. They are not imported or
executed by ordinary Streamlit. Broad legacy deletion has not started.

### Contract V1 domain and solver boundary

`src/bus_schedule_engine/contracts_v1/` is a separately tested target boundary. It provides:

- normalized Scenario A, Scenario B, and observed-demand models and adapters;
- authoritative demand resolution, coverage, and Scenario B evaluation;
- the canonical `ScheduleProblemV1`;
- the solver-neutral `ScheduleSolver` interface;
- raw candidate, independent validator, accepted solution, and generation-outcome contracts;
- a compatibility adapter for the existing heuristic; and
- the quantitative pre-problem service-adjustment evaluator from V1-D2 Phase A.

Milestone 5A1 now runs the two result-producing paths through a deterministic side-by-side
validation adapter. This creates review evidence used by the later visible-result authority gate.

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

Milestone 5B1 introduced the shadow runtime. Milestone 5B2A cut over visible diagnostic and
recommendation Pages 02–04, and Milestone 5B2B cut over Page 05 to exact-direction unified charts
and three validated Contract V1 downloads. See
[Milestone 5B1 Streamlit shadow runtime](docs/engine/MILESTONE_5B1_STREAMLIT_SHADOW_RUNTIME.md)
and
[Milestone 5B2A unified result pages](docs/engine/MILESTONE_5B2A_UNIFIED_RESULT_PAGES.md), and
[Milestone 5B2B unified Page 05 artifacts](docs/engine/MILESTONE_5B2B_UNIFIED_PAGE5_ARTIFACTS.md).
Milestone 5C1 is merged and selects Option C. Milestone 5C2 now implements the unified-only
ordinary runtime: Streamlit performs no legacy analysis or per-submission comparison, while
legacy remains an offline oracle. `LEGACY_RUNTIME_RETIRED` and Milestone 5 still await formal
production approval, and `LEGACY_CODE_DELETED` is not claimed. See
[Milestone 5C1 legacy runtime retirement decision](docs/engine/MILESTONE_5C1_LEGACY_RUNTIME_RETIREMENT_DECISION.md)
and
[Milestone 5C2 unified-first runtime](docs/engine/MILESTONE_5C2_UNIFIED_FIRST_RUNTIME.md).

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
- Optional supplemental trip-level ridership import, deterministic Scenario B matching, and
  coverage-aware descriptive analysis that does not affect optimization.
- Deterministic current-B service regimes and supplemental high-demand service-floor
  classification with review-only, explicitly non-enforced previews.
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
  service regimes, with solver-determined transition headways between regimes and conditional
  hard constraints for the exact bound protected-floor authority.
- Unified fixed-resource solver selection with heuristic-only continuity by default, explicit
  15-stage OR-Tools service-quality solving, and transparent `BOTH` comparison of independently
  validated accepted solutions.
- Unified-only ordinary runtime with readiness-first execution and fail-closed errors.
- Unified demand/supply and exact-departure figures plus an editable formula-free XLSX workbook,
  all aligned by one semantic presentation fingerprint.
- Unified Page 05 exact-direction charts plus validated XLSX, deterministic offline HTML, and
  selected-overview PNG downloads.
- Explicit deterministic offline release-audit JSON backed by the retained legacy oracle.

## Not supported yet

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
- Formal production approval of the implemented `LEGACY_RUNTIME_RETIRED` gate.
- Broad deletion or rehoming of the retained legacy regression-oracle code.

## Target pipeline

```text
Workbook/UI
-> import
-> assess authoritative-input readiness
-> strict Contract V1 normalization
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
5B1 Streamlit shadow execution, Milestone 5B2A unified result Pages 02–04, and Milestone 5B2B
unified Page 05 artifacts are implemented and merged. Milestone 5C1 is merged and Milestone 5C2
is merged. Milestone 6A1 supplemental trip-level ridership analysis, Milestone 6A2A
protected service-floor authority, Milestone 6A2B acceptance enforcement, and Milestone 6A2C
heuristic search awareness, and Milestone 6A2D OR-Tools hard constraints are implemented**, but
Milestone 5 and `LEGACY_RUNTIME_RETIRED` still require formal approval.

1. Milestone 5A1: compare deterministic legacy and unified result snapshots.
2. Milestone 5A2A: stabilize authoritative workbook input and readiness.
3. Milestone 5A2B: validate parallel unified presentation adapters for charts and XLSX
   (implemented; no Streamlit cutover).
4. Milestone 5B1: run Contract V1 once in Streamlit and store non-authoritative shadow evidence
   (implemented; visible pages and downloads remain legacy).
5. Milestone 5B2A: cut over Pages 02–04 through the explicit visible-result authority gate
   (implemented).
6. Milestone 5B2B: cut over Page 05 charts and downloads through the same gate while retaining
   the complete legacy fallback (implemented; legacy retirement remains separate).
7. Milestone 5C1: define and approve the Option C legacy-runtime retirement gate (merged).
8. Milestone 5C2: make Contract V1 the only ordinary Streamlit runtime and move side-by-side
   validation to an explicit offline release audit (implemented; formal approval pending).
9. Milestone 5C3: separately remove authorized legacy code after approval (not started).
10. Milestone 6A1: add supplemental, coverage-aware trip-level ridership analysis without
    changing optimization authority.
11. Milestone 6A2A: define deterministic protected high-demand service-floor authority and
    non-enforced previews (implemented).
12. Milestone 6A2B: enforce reviewed service floors at independent candidate acceptance while
    deferring solver-native protected-floor search (implemented).
13. Milestone 6A2C: filter bounded legacy-compatible heuristic direction plans against the exact
    6A2B authority while keeping common validation final (implemented).
14. Milestone 6A2D: encode the exact bound 6A2B authority in the canonical OR-Tools
    service-quality model while keeping common validation final (implemented).

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
for detailed historical evidence. Pages 02–05 now display only aligned unified Contract V1 facts
and artifacts. The corpus remains diagnostic evidence and does not approve an operating
timetable. The prior reviewed baseline recorded that “The Streamlit UI, charts, and XLSX exports have not yet migrated”;
Milestone 5C2 supersedes that historical runtime statement without changing the corpus facts or
approval boundary.

Variable-trip-count optimization and structural demand-response scenarios are optional later
stages. See [Migration Roadmap to OR-Tools](docs/engine/MIGRATION_ROADMAP_TO_OR_TOOLS.md).

## Install

Python 3.11 or later is required. On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Run the unified application

```powershell
.\.venv\Scripts\streamlit.exe run streamlit_app.py
```

The five Vietnamese UI pages cover input, technical checks, demand evaluation,
recommendations, and chart/XLSX export.

Run the retained legacy comparison only as an explicit offline release audit:

```powershell
.\.venv\Scripts\python.exe -m bus_schedule_engine.release_audit `
  --workbook "Schedule template.xlsx" `
  --solver HEURISTIC `
  --output "outputs/release-audit.json"
```

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
- `THONG_TIN_SAN_LUONG_CHUYEN`;
- `SAN_LUONG_CHUYEN`;
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
Optional `protected_service_floor_*` entries in `CAU_HINH` declare the 6A2A policy. They are
supplemental planning settings and do not change Contract V1 or Scenario C.

The current exporters create new workbooks and do not overwrite `Schedule template.xlsx`.
