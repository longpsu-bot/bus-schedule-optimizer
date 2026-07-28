# Milestone 5B1: Streamlit shadow runtime

## 1. Purpose

Milestone 5B1 integrates Contract V1 into the ordinary Streamlit submission flow as
non-authoritative shadow evidence. It does not cut over any visible result page, chart, Scenario C,
or download.

The application runtime is:

```text
uploaded workbook bytes
-> workbook import and existing user overrides
-> legacy analysis and legacy artifacts once
-> authoritative-input readiness assessment
-> unified Contract V1 analysis at most once
-> pure side-by-side report projection
-> unified presentation, figures, and editable XLSX
-> parallel session state
```

## 2. One legacy and one unified execution

`run_parallel_application_pipeline_v1(...)` calls the existing
`run_and_build_artifacts(...)` path exactly once. The returned legacy bundle, overview figure,
XLSX files, HTML, PNG, and Scenario C fingerprint are passed through without replacement.

Before either execution path runs, the application deep-copies the imported workbook into
independent legacy and unified inputs. Mutable trip lists, demand lists, configuration, and nested
trip objects are therefore not shared between the caller, the legacy bundle, and unified
normalization or analysis.

When the workbook is optimization-ready, the runtime calls
`analyze_and_optimize_schedule_v1(...)` exactly once. The public
`build_side_by_side_validation_report_v1(...)` then compares the already computed legacy and
unified results. Presentation, figure, and XLSX builders only project those returned facts and do
not rerun either analysis path.

## 3. Input-not-ready behavior

Readiness is assessed after import and user overrides. If optimization authority is incomplete:

- the successful legacy result and artifacts remain available;
- status is `INPUT_NOT_READY`;
- every missing authority code is retained;
- Contract normalization and unified optimization are not called;
- no unified report, presentation, figure, or XLSX is created; and
- no fleet, operating day, demand confidence, terminal capacity, or other authority is inferred.

This preserves legacy diagnostic analysis for workbooks such as a blank
`available_fleet_limit`, while the unified path fails closed.

Readiness assessment is part of the guarded post-legacy shadow stage. If readiness assessment
itself raises unexpectedly, the runtime returns `UNIFIED_RUNTIME_FAILED`, retains the completed
legacy artifacts, and leaves `input_readiness=None`; it does not invent readiness evidence.

## 4. Parallel session-state evidence

The existing legacy keys remain authoritative:

```text
imported_workbook
analysis_bundle
diagram_figure
download_artifacts
scenario_c_fingerprint
```

Milestone 5B1 adds:

```text
parallel_runtime_status
workbook_input_readiness
unified_optimization_result
side_by_side_validation_report
unified_presentation
unified_demand_supply_figure
unified_departure_figure
unified_download_artifacts
unified_runtime_failure
```

`unified_download_artifacts` is validation evidence only. It contains unified XLSX bytes and the
presentation, normalized-B, and accepted-solution fingerprints. No unified download button is
shown.

When uploaded workbook bytes change, prior legacy and unified result state is cleared before a new
run. Streamlit derives provenance from the exact uploaded bytes as
`streamlit-upload-sha256:<lowercase SHA-256>` and captures one UTC timestamp for the run. The
filename and temporary paths are not authoritative source identity.

## 5. Unified artifact alignment

For `PARALLEL_VALIDATION_COMPLETE`, the application verifies:

```text
presentation fingerprint
= demand/supply figure fingerprint
= departure figure fingerprint
= unified XLSX fingerprint
```

It also verifies the normalized Scenario B fingerprint and accepted-solution fingerprint across
the same artifacts. If unified Scenario C is absent, all accepted-C fingerprints remain `None`,
the presentation has no Scenario C timetable, and the XLSX has no Scenario C timetable sheet.

The unified exporter writes to a new temporary file with `overwrite=False`. The application reads
the exported metadata before retaining the XLSX bytes.

## 6. Failure isolation

Legacy execution remains the ordinary blocking boundary. If it fails, the submission fails as it
did before.

After legacy artifacts succeed, an unexpected readiness, unified, or artifact-integrity exception
returns `UNIFIED_RUNTIME_FAILED` with stable code `UNIFIED_SHADOW_RUNTIME_FAILED` and a concise
message. The exact legacy bundle, figure, and downloads remain available. Readiness is retained
only if its assessment completed successfully; all partial unified objects are discarded, and
Streamlit displays one warning that visible results still use the legacy pipeline.

## 7. No visible results-page cutover

Pages 02–05 are unchanged. Pages 04 and 05 continue to consume `analysis_bundle`,
`diagram_figure`, and `download_artifacts`. Existing legacy chart builders, exporters, filenames,
download buttons, Scenario C display, and fingerprint checks remain in force. Unified figures and
the unified XLSX are not displayed or downloadable.

## 8. Gate to Milestone 5B2

Milestone 5B2 may separately propose a results-page cutover only after the stored side-by-side
discrepancies, presentation evidence, corpus characterizations, and artifact fingerprints are
reviewed. Milestone 5B1 does not authorize that cutover.

## 9. Explicit shadow status

Every unified object created here is validation-only, parallel, and non-authoritative. A complete
shadow run is evidence that the two paths executed and their projected artifacts align; it is not
an approval, production-readiness decision, or automatic-cutover signal.
