# Milestone 5A2B unified presentation adapters

## 1. Purpose

Milestone 5A2B adds a parallel, validation-only presentation path for the unified Contract V1
optimization result. It projects one `BusScheduleOptimizationResult` and its Milestone 5A1
`SideBySideValidationReportV1` into one deterministic presentation model, two Plotly figures,
and one editable XLSX workbook.

The adapters are independently callable:

```python
build_unified_presentation_v1(result, validation_report)
build_unified_demand_supply_figure_v1(presentation)
build_unified_departure_figure_v1(presentation)
export_unified_result_workbook_v1(presentation, path, overwrite=False)
read_unified_export_metadata_v1(path)
```

They do not run analysis, normalization, evaluation, recommendation, solving, or legacy
presentation logic.

## 2. Unified presentation authority

The unified result supplies normalized A and B, B evaluation, adjustment and solver outcomes,
accepted C, exact block supply, exact timetables, B-to-C mapping, headway regimes, fleet
assignments, initial positioning, fingerprints, explanations, and limitations. The side-by-side
report supplies legacy-versus-unified comparison records and the blocking, expert-review, and
informational codes.

`build_unified_presentation_v1(...)` verifies that route, terminals, normalized B fingerprint,
accepted-C existence, accepted solution fingerprint, accepted solution source-B fingerprint, and
reported C authority refer to one consistent execution. Internal result/report inconsistency
raises `UnifiedPresentationConsistencyError`. Legacy-versus-unified discrepancies do not.

The adapter never converts unified facts to `AnalysisBundle`, `ScenarioResult`, legacy trips,
legacy block evaluations, or legacy fleet objects.

## 3. Validation-only status

Every presentation is labeled `VALIDATION_ONLY`. It exposes:

- `cutover_blocked`, derived only from the report's blocking discrepancy codes;
- `requires_expert_review`, derived from blocking or expert-review codes;
- the exact blocking and expert-review code tuples.

There is no approval, readiness score, production-readiness, or automatic cutover property.

## 4. Scenario C acceptance gate

Scenario C is projected only when the recommended outcome has
`GenerationResultStatus.SOLUTION_ACCEPTED` and a non-null accepted solution. Only that solution
supplies C timetable, supply, headway, fleet, mapping, and fingerprints.

When the gate is false, there is no C scenario, C chart lane, C supply trace, C fleet assignment,
C headway regime, or C fingerprint. Scenario B is never copied into C. Rejected-candidate codes
remain visible, while the raw candidate timetable and candidate fingerprint remain absent.

## 5. Exact demand-grain rule

`PresentationBlockV1` preserves the exact semantic key:

```text
block_id + direction + block_start + block_end
```

A, B, and accepted-C returned supply plans are reconciled only on that key. A mismatch fails
clearly instead of aggregating, splitting, interpolating, or re-binning. Combined demand remains
combined; it is never apportioned to outbound or inbound demand.

## 6. Allowed display derivations

The presentation path may sort returned records, format times and percentages, convert service
seconds to Excel time values, derive terminal display labels from declared terminals, calculate
chart coordinates, and project exact departures onto a continuous service-day axis.

An adjacent headway calculated only for a future display must be labeled `DISPLAY_DERIVED`. No
display derivation may affect feasibility, adjustment, load-factor, fleet, terminal occupancy,
solver comparison, or C acceptance.

## 7. Chart outputs

`build_unified_demand_supply_figure_v1(...)` shows exact Contract blocks, passenger-demand bars,
returned A/B/C trip counts, and returned 85% and 90% required-trip facts. C appears only when
accepted. Categories retain block ID, interval, and direction.

`build_unified_departure_figure_v1(...)` shows exact A, B, and accepted-C departures on separate
scenario/direction lanes. The service-day axis remains continuous past midnight. C hover evidence
contains source B trip, B and C departures, shift, regime, reason, vehicle, and exact terminals.

Both figures store presentation mode, presentation fingerprint, B fingerprint, accepted-solution
fingerprint, accepted-C state and authority, cutover state, review codes, and exact demand-grain
label in `layout.meta`. Neither figure calls a legacy chart builder.

## 8. XLSX outputs

`export_unified_result_workbook_v1(...)` defaults to `overwrite=False`, refuses an existing target,
and refuses a target that is the declared source workbook. It creates plain `.xlsx` cells without
macros, protection, or business formulas.

The workbook contains `TONG_QUAN`, optional `A_BIEU_DO`, mandatory `B_BIEU_DO`, exact
`CUNG_CAU_BLOCK`, `DANH_GIA_B`, `SOLVER`, `DOI_CHIEU_5A1`, `GIOI_HAN`, and `FINGERPRINTS`.
Accepted C additionally creates `C_BIEU_DO`, `SO_SANH_B_C`, `FLEET_C`, and `HEADWAY_C`. Without
accepted C, `C_TRANG_THAI` replaces all C artifact sheets and states explicitly that no
authoritative C exists.

Objective names and vectors are copied exactly; no weighted total is created. Authoritative trip
counts, required trips, load factors, shortages, shifts, fleet facts, occupancy statuses, solver
vectors, and acceptance facts are values, not formulas.

## 9. Fingerprint alignment

The presentation fingerprint is a semantic SHA-256 over route/source identity, exact A/B/C
timetables, B/C fingerprints, exact block facts, evaluation dimensions, solver/outcome facts,
fleet and headway facts, all side-by-side records, explanations, and limitations.

It excludes output paths, workbook timestamps, Plotly styling and dimensions, solver-duration
telemetry, and temporary paths. Contract fingerprints are not recalculated or modified.
`read_unified_export_metadata_v1(...)` reads the presentation fingerprint, B fingerprint,
accepted-solution fingerprint, source ID, mode, and cutover state from `FINGERPRINTS` to validate
artifact alignment. That reader is not business authority.

## 10. Side-by-side discrepancy visibility

Blocking discrepancies remain renderable review evidence. They appear in chart metadata,
`TONG_QUAN`, and every comparison row in `DOI_CHIEU_5A1`. A blocker sets `cutover_blocked=True`
and implies expert review, but produces no automatic approval or suppression of evidence.

Only inconsistency between the supplied unified result and the supplied report prevents artifact
construction.

## 11. Gate to later Streamlit cutover

A later milestone may consider Streamlit cutover only after the validation artifacts show one
authoritative result consistently across figures and workbook, all blocking discrepancies are
resolved, expert-review items are handled, and that cutover is separately approved.

Milestone 5A2B supplies evidence for that decision; it does not make the decision.

## 12. Explicit non-cutover statement

The current Streamlit pages, session-state keys, download buttons, legacy chart builders, legacy
result XLSX exporters, execution services, solver boundary, Contract schemas, and route corpus
remain unchanged. The current application remains legacy-authoritative.
