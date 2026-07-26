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

OR-Tools is not installed or implemented. There is no CP-SAT model or solver adapter in the
repository.

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

## Not supported yet

- Contract V1 execution through the Streamlit application.
- OR-Tools CP-SAT feasibility or optimization.
- A globally optimal timetable or a proof of infeasibility from the legacy heuristic.
- A unified comparison of heuristic and CP-SAT objective vectors.
- Variable-trip-count optimization.
- Production implementation of the deferred V1-A1 structural demand-response workflow.
- Mixed fleets, multi-route interlining, deadhead, driver duties, depot pull-in/out, maintenance,
  or mature cross-midnight optimization.
- Contract V1-based charts or the target Contract V1 XLSX workbook.

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

1. Create one unified application service over the Contract V1 boundary.
2. Integrate the legacy heuristic through `ScheduleProblemV1` and the independent validator.
3. Implement one-route, fixed-resource CP-SAT hard feasibility.
4. Add fixed-resource demand/headway objectives and an anonymized real-route regression corpus.
5. Cut the UI and XLSX over after side-by-side validation.

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
