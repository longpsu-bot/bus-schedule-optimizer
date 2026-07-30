# Milestone 5C2 unified-first runtime

## 1. Purpose

Milestone 5C2 implements the Option C boundary approved in Milestone 5C1: Contract V1 is the
only ordinary Streamlit analysis runtime. Legacy analysis remains executable only as an offline
regression oracle. This milestone does not delete legacy code or approve an operating timetable.

## 2. Approved 5C1 decision

The governing decision is
[Milestone 5C1 legacy runtime retirement decision](MILESTONE_5C1_LEGACY_RUNTIME_RETIREMENT_DECISION.md).
Optimization-ready submissions run Contract V1 without a legacy prerequisite or fallback.
Incomplete-authority submissions stop at readiness, and unexpected unified failures fail closed.
The default remains `SolverChoice.HEURISTIC`; Streamlit exposes no solver selector.

## 3. New runtime sequence

`run_unified_application_pipeline_v1(...)` performs this ordered sequence:

1. Deep-copy the imported workbook once.
2. Assess authoritative-input readiness.
3. Stop immediately when optimization authority is incomplete.
4. Build strict normalization options.
5. Run `analyze_and_optimize_schedule_v1(...)` once.
6. Build the report-free unified presentation.
7. Verify its semantic fingerprint and source identity.
8. Build the demand/supply figure.
9. Build the departure figure.
10. Export the unified XLSX.
11. Verify figure metadata, XLSX metadata, fingerprints, and source identity.
12. Return one atomic unified result.

No ordinary Streamlit step invokes legacy analysis, side-by-side comparison, legacy charts, or
legacy exporters.

## 4. Unified application result model

`UnifiedApplicationRunV1` is frozen and slotted. It contains the input readiness, unified result,
verified presentation, two figures, exact XLSX bytes, source identity, imported timestamp, and
optional `UnifiedRuntimeFailureV1`. Its terminal statuses are `INPUT_NOT_READY`, `COMPLETE`,
`ARTIFACT_FAILED`, and `FAILED`. It contains no `AnalysisBundle`, legacy figure, legacy artifact
mapping, legacy Scenario C fingerprint, or side-by-side report.

## 5. Readiness-first behavior

`INPUT_NOT_READY` returns the complete `WorkbookInputReadinessV1` and stable status
`WORKBOOK_OPTIMIZATION_NOT_READY`. It returns no analytical result or download. Pages show the
source input facts, every exact missing-authority code, the generated template, and migration
instructions. Missing authority remains missing; no normalization, solver, fleet analysis, chart,
export, legacy runtime, or side-by-side comparison runs.

## 6. Import-invalid behavior

Page 01 reports `WORKBOOK_IMPORT_INVALID`, a bounded import message, and migration guidance.
The generated template remains available. The application does not run the pipeline or expose
result downloads, workbook rows, or workbook bytes.

## 7. Report-free presentation

`build_unified_application_presentation_v1(...)` projects the Contract V1 result without a
`SideBySideValidationReportV1`. It shares the timetable, exact demand-block, outcome, fleet,
headway, and terminal-occupancy projection with the retained offline report-backed builder.
Application presentations remain `VALIDATION_ONLY`, have no discrepancies or cutover blockers,
and assign Scenario C authority only to an independently accepted Contract V1 solution.

## 8. Review-code derivation

Runtime expert-review codes are the sorted, deduplicated union of non-INFO dimension issue codes,
validator rejection codes, and terminal-occupancy issue codes. INFO dimension issue codes remain
informational. If a result has limitations but that expert union is empty,
`UNIFIED_LIMITATIONS_REQUIRE_EXPERT_REVIEW` is added. Free-text limitations are not converted
into fabricated domain codes.

## 9. Failure-stage model

Unexpected failures use the narrow stages `NORMALIZATION`, `EVALUATION`, `HEURISTIC_SOLVER`,
`OR_TOOLS_SOLVER`, `SOLVER_COMPARISON`, `PRESENTATION`, and `ARTIFACTS`. Service-stage wrappers
retain the original exception as the cause. `ContractValidationError` is classified by the stage
where it occurs; it is not globally synonymous with normalization failure. The application maps
`NORMALIZATION` to `CONTRACT_V1_NORMALIZATION_FAILED`, solver stages to
`CONTRACT_V1_SOLVER_FAILED`, and `EVALUATION` or an unknown stage to
`CONTRACT_V1_APPLICATION_ERROR`. Normal no-solver results, returned infeasible/unknown outcomes,
completed no-C results, and validator-rejected candidates are not runtime failures.

## 10. Correlation-ID and logging policy

Failures receive a deterministic `m5c2-...` correlation ID derived from bounded source identity,
import timestamp, stage, exception class, and sanitized message. Logs include the stable code,
stage, target commit when available, solver choice, readiness codes, returned status codes, and
fingerprints that existed before failure. Local paths are removed. Workbook bytes, workbook rows,
and passenger observations are neither logged nor displayed.

## 11. Artifact atomicity

`COMPLETE` exposes both figures and the exact verified XLSX bytes. A chart or export construction
failure after presentation verification returns `ARTIFACT_FAILED`: Pages 02–04 retain the
verified result and presentation, while Page 05 receives no figure or download bundle. A
presentation or cross-artifact semantic mismatch reports
`CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH` and exposes no analytical result. Page 05 independently
reconstructs the canonical departure figure and verifies the actual stored XLSX bytes before
building its all-or-nothing HTML and PNG bundle.

## 12. Visible authority

The single resolver supports `NO_RESULT`, `INPUT_NOT_READY`, `UNIFIED_CONTRACT_V1`,
`UNIFIED_ARTIFACT_FAILED`, and `CONTRACT_V1_FAILED`. Complete authority requires ready input,
verified presentation integrity, aligned source and accepted-C identity, both aligned figures,
and an aligned XLSX sidecar. Corrupted or partial complete state fails closed; legacy is never
selected.

## 13. Session-state migration

Ordinary state retains `input_bytes`, `imported_workbook`, `workbook_input_readiness`,
`unified_runtime_status`, `unified_optimization_result`, `unified_presentation`,
`unified_demand_supply_figure`, `unified_departure_figure`, `unified_download_artifacts`, and
`unified_runtime_failure`. Startup and result clearing remove stale legacy keys with
`pop(..., None)` and never initialize or write them as result state.

## 14. Page behavior

Page 01 invokes only the unified pipeline and displays declared input facts rather than a
pre-readiness computed fleet estimate. Pages 02–04 consume only the unified visible context.
They stop on readiness or runtime failure and render a verified presentation during ordinary
artifact failure. Page 05 has no legacy branch and retains exactly these downloads on complete
runs:

- `Bus_Schedule_Contract_V1_Result.xlsx`
- `Bus_Schedule_Contract_V1_Charts.html`
- `Bus_Schedule_Contract_V1_Overview.png`

## 15. Candidate rejection

An independently rejected candidate remains a completed Contract outcome with status
`CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR`. Scenario B evaluation, the selected action, solver
facts, and validator codes remain visible. Raw candidate timetable facts and Scenario C remain
absent. A semantically valid no-C XLSX/HTML/PNG bundle may still be downloaded.

## 16. Mixed solver behavior

For `SolverChoice.BOTH`, an accepted recommended solution remains the sole visible Scenario C
even when the other candidate is rejected. The rejected outcome remains diagnostic evidence.
The UI does not claim the accepted solution was rejected, and the accepted-C fingerprint must
align across the presentation and every artifact.

## 17. Offline release audit

The retained oracle is explicitly invoked outside Streamlit:

```text
python -m bus_schedule_engine.release_audit --workbook <path> --solver HEURISTIC --output <report.json>
```

The command hashes without modifying the workbook, assesses readiness, invokes the existing
side-by-side adapter only when ready, and writes deterministic bounded JSON. It includes source
hash, solver choice, comparison metadata, blocker/review/informational codes, and available
fingerprints, but omits comparison values, workbook rows, and passenger observations. It exits
zero only when no blocker exists.

## 18. Backward compatibility

Generated authoritative workbooks continue through Contract V1. Historical workbooks that still
import but lack optimization authority receive exact readiness codes and template-based migration
guidance; they receive no legacy diagnostics or downloads. Import-invalid workbooks receive the
stable import status and the same template route. No authority is inferred and no automatic
converter is introduced.

## 19. Rollback boundary

Rollback is a source-control revert of the 5C2 change after reviewing any evidence produced by
the offline audit. There is no runtime feature flag, legacy/unified toggle, or automatic fallback.
The retained legacy modules and parallel adapter provide regression evidence during the
transitional compatibility period without entering ordinary application execution.

## 20. Evidence results

Automated characterization covers readiness and import failure, accepted/no-C/rejected/mixed
outcomes, Alpha and Beta corpus behavior, terminal-occupancy authority variants, staged service
exceptions, semantic mismatch, stored-figure and XLSX mismatch, HTML/PNG atomic failure, unified
page authority, deterministic release-audit output, and retained offline oracle behavior. The
delivery record reports the focused and full-suite counts from the final branch validation.
Protected Contract, schema, corpus, template, solver, and oracle files are verified unchanged.

## 21. Why LEGACY_RUNTIME_RETIRED is implementation-complete but still awaits formal production approval

The implementation gate is satisfied when the validated branch proves zero legacy executions for
both ready and not-ready ordinary submissions, zero per-submission comparisons, a unified run
without `AnalysisBundle`, fail-closed errors, and a working offline audit. Formal production
approval still requires review of that evidence by the Engineering Owner and QA/Release Owner.
Milestone 5 therefore remains incomplete until the approval event occurs.

## 22. Explicit 5C3 exclusions

This milestone does not delete or broadly reorganize legacy modules, rehome heuristic internals,
change Contract V1 or schemas, change the default solver, expose solver selection, add
variable-trip optimization or fleet minimization, implement V1-A1, revive Phase B, approve an
operating timetable, or declare `LEGACY_CODE_DELETED`. Those removals remain a separately
authorized Milestone 5C3 concern.
