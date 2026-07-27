# Milestone 5A1 side-by-side validation

## 1. Purpose

Milestone 5A1 adds an application-layer evidence boundary between the legacy MVP analysis and
the unified Contract V1 optimization service. One logical `ImportedWorkbook` is deep-copied for
each path, and the returned results are reduced to deterministic, presentation-oriented
snapshots and semantic fact comparisons.

The report is review evidence. It is not an approval or authorization token.

## 2. Current legacy and unified paths

The legacy execution authority remains:

```text
ImportedWorkbook -> run_analysis(...) -> AnalysisBundle
```

The unified execution authority remains:

```text
ImportedWorkbook -> analyze_and_optimize_schedule_v1(...)
                   -> BusScheduleOptimizationResult
```

The adapter calls neither `run_and_build_artifacts` nor any chart, PNG, HTML, or XLSX builder.
Snapshots consume only the two returned results; they do not rerun demand, fleet, validation,
solver, or headway logic.

## 3. Comparable fact categories

Scenario B source and lock facts must match: route and terminal identities, trip totals and
directional counts, endpoints, source trip IDs, per-trip direction, terminal, departure,
runtime, capacity, turnaround, and supplied terminal occupancy limits.

Validation conclusions, fleet need, demand suitability and authority, headway concerns,
terminal-occupancy conclusions, Scenario C existence, and comparable Scenario C timetable facts
are review evidence. Demand blocks are compared only at identical
`(direction, block_start, block_end)` grain.

## 4. Non-comparable legacy facts

The legacy generator decision contract, generated-trip naming, free-text recommendations, and
weighted score are not Contract V1 quality authority. The legacy weighted score is never
compared with the unified 15-stage objective vector. Unified initial terminal positioning,
solver outcome details, accepted-solution fingerprint, and any existing solver comparison
vector remain unified-only facts.

Legacy and Contract timetable fingerprints use different profiles and are not compared across
paths.

## 5. Difference classifications

- `MUST_MATCH` differences use `BLOCKS_CUTOVER`.
- `REVIEW_IF_DIFFERENT` differences use `EXPERT_REVIEW_REQUIRED`.
- `NOT_COMPARABLE` facts are `EXPECTED_BY_DESIGN` or informational unified-only evidence.
- Matches are informational; they do not authorize a cutover.

No weighted discrepancy or readiness score is produced.

## 6. Scenario C authority rule

A legacy Scenario C is always labeled `LEGACY_DIAGNOSTIC_ONLY`. A unified Scenario C appears
only when `recommended_outcome.result_status == SOLUTION_ACCEPTED` and the recommended outcome
contains an independently validated solution. Rejected or raw candidates are never exposed as
Scenario C, and Scenario B is never substituted for a missing C.

Legacy-only C yields `LEGACY_C_WITHOUT_UNIFIED_AUTHORITY`. Unified-only accepted C yields
`UNIFIED_ACCEPTED_C_WITHOUT_LEGACY_C`. Both require expert review.

## 7. Route corpus interpretation

Under natural LOW-confidence policy, Alpha remains insufficient-data on the unified path, runs
no unified solver, and has no accepted unified C. A legacy C is reported as diagnostic-only.

Beta also remains solver-free and preserves incomplete proxy coverage, including the outbound
17:00-18:00 gap. No demand, vector, solver recommendation, terminal capacity, or Scenario C is
fabricated to align the paths.

The route corpus remains a reviewed diagnostic baseline, not an approved operational timetable.

## 8. Gate to Milestone 5A2

Milestone 5A2 may use this deterministic report to validate unified chart and XLSX presentation
adapters. All blocking source discrepancies and expert-review records must remain visible for
that later review.

## 9. Explicit non-cutover statement

Milestone 5A1 does not change Streamlit, session state, charts, PNG/HTML generation, XLSX
exporters, solver behavior, Contract V1, schemas, route-corpus fixtures, source hashes, or
terminal-capacity policy. Streamlit, charts, and XLSX continue to use the legacy path.
