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

The two paths are not yet integrated. The Streamlit application does not call the Contract V1
public boundary, and Contract V1 does not yet power the UI, charts, or XLSX exports.

Contract V1 includes separate OR-Tools v9.15 CP-SAT adapters for one-route, fixed-resource hard
feasibility, directional demand-priority optimization, and service-quality optimization. The
feasibility adapter remains an objective-free satisfaction model. Demand protection remains the
highest optimization priority. The service-quality adapter then protects positive-demand service
gaps, aligns fixed directional trips with passenger demand, and balances adjacent headways inside
sustained service regimes; different legitimate demand regimes may use different headway levels.
All three adapters use canonical request builders and the independent validator. The unified
application service now supports explicit `SolverChoice.HEURISTIC`, `OR_TOOLS`, and `BOTH` for
fixed-resource actions, while the default remains `HEURISTIC`. `OR_TOOLS` selects the 15-stage
service-quality adapter. `BOTH` independently validates both outcomes, recomputes the same
transparent lexicographic objective vector for accepted solutions, and recommends one outcome
without a weighted score. Streamlit does not yet expose this selection.

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
- Separate OR-Tools fixed-resource demand-priority solving for authoritative directional demand,
  covering no-service and overload protection before provisional B-preservation shift tie-breaks.
- Separate OR-Tools fixed-resource service-quality solving for positive-demand gaps, proportional
  directional-demand alignment, and regular headways within derived sustained service regimes.
- Unified fixed-resource solver selection with heuristic-only continuity by default, explicit
  15-stage OR-Tools service-quality solving, and transparent `BOTH` comparison of independently
  validated accepted solutions.

## Not supported yet

- Contract V1 execution through the Streamlit application.
- Solver selection through Streamlit.
- OR-Tools fleet-minimization objectives.
- A globally optimal timetable or a proof of infeasibility from the legacy heuristic.
- Approval of the draft anonymized real-route corpus as a permanent regression baseline.
- Variable-trip-count optimization.
- Production implementation of the deferred V1-A1 structural demand-response workflow.
- Mixed fleets, multi-route interlining, deadhead, driver duties, depot pull-in/out, maintenance,
  or mature cross-midnight optimization.
- Charts and XLSX do not yet consume unified Contract V1 optimization results.

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

1. Obtain expert approval for the draft anonymized real-route corpus characterization.
2. Run side-by-side UI, chart, and XLSX validation against unified results.
3. Cut the UI and XLSX over only after that validation is approved.

## Draft anonymized route corpus

Milestone 4C1 now includes two versioned, anonymized, real-route-derived fixtures under
`tests/fixtures/route_corpus/v1/`. The private source workbooks remain external and uncommitted.
Overlapping raw trip-observation evidence is preserved separately from a LOW-confidence,
departure-hour sensitivity proxy. Proxy values retain their exact 15-day
`total_observation_period` classification, and Contract V1 derives daily demand using the
15-day observation count. Coverage gaps or unsupported normalized precision prevent the
diagnostic solvers from running.

The corpus and solver characterization are drafts, not approved operational timetables or frozen
solver regression expectations. UI, chart, and XLSX cutover remains blocked on corpus review and
approval.

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
- `SAN_LUONG`;
- `CAU_HINH`.

`total_daily_trips` is the total across both directions.
`vehicle_capacity_passengers` is required. Times use `HH:mm`; dates use `dd/mm/yyyy`.
`allowed_trip_runtime_minutes` accepts an inclusive integer range such as `55,65` or `55;65`.
Combined demand remains combined and must not be fabricated into directional demand.

The current exporters create new workbooks and do not overwrite `Schedule template.xlsx`.
