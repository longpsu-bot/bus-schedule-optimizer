# Milestone 5B2A: Unified result pages

## 1. Purpose

Milestone 5B2A cuts over visible diagnostic and recommendation Pages 02–04 to facts already
stored by the Milestone 5B1 Contract V1 shadow runtime. It does not execute analysis again, approve
an operational timetable, or cut over Page 05 charts and downloads.

The cutover is fail-closed. One pure resolver selects either the complete aligned Contract V1
presentation or the existing legacy page behavior. Every page labels the selected authority.

## 2. Visible-result authority gate

`resolve_visible_result_context_v1(...)` consumes only existing session evidence supplied by the
caller:

- the completed legacy `AnalysisBundle`;
- `ParallelRuntimeStatusV1`;
- authoritative-input readiness;
- the unified optimization result;
- the side-by-side validation report;
- the unified presentation;
- both unified figure objects;
- unified XLSX bytes and stored metadata fingerprints; and
- the stable unified runtime failure record.

The resolver is frozen/slotted at its return boundary, does not import Streamlit, does not read
session state, and does not call validation, analysis, diagram construction, export, or solver
paths. It does not rebuild business objects or recompute presentation integrity. It compares the
stored evidence that Milestone 5B1 already produced.

## 3. Unified-mode conditions

`UNIFIED_CONTRACT_V1` is returned only when all of the following are true:

1. a legacy result exists;
2. parallel status is `PARALLEL_VALIDATION_COMPLETE`;
3. readiness exists and `optimization_ready=True`;
4. the unified result, report, presentation, and both unified figures exist;
5. unified XLSX bytes and all three stored metadata fingerprints exist;
6. presentation mode is `VALIDATION_ONLY`;
7. neither report nor presentation contains a blocking discrepancy;
8. report and presentation blocker tuples agree;
9. the presentation fingerprint matches both figure metadata records and XLSX metadata;
10. the normalized-B fingerprint matches the result, report, presentation, figures, and XLSX
    metadata;
11. the accepted-C fingerprint matches the result, report, presentation, figures, and XLSX
    metadata, including `None` everywhere when no accepted C exists;
12. accepted-C presence, timetable, fleet, block fields, and presentation outcome agree;
13. dimension issue vectors have consistent lengths; and
14. the presentation source identity agrees with the unified result.

Passing this gate selects which returned facts Pages 02–04 display. It is not operational approval.

## 4. Legacy fallback modes

The resolver returns one explicit fallback:

- `NO_RESULT`: preserve the existing “run analysis first” warning and stop;
- `LEGACY_INPUT_NOT_READY`: show every returned missing-authority code and retain the current
  legacy page;
- `LEGACY_UNIFIED_FAILED`: show the stable failure code and concise message, discard all partial
  unified objects from the returned context, and retain the current legacy page;
- `LEGACY_CUTOVER_BLOCKED`: show every blocking discrepancy code and retain the current legacy
  page; or
- `LEGACY_INCOMPLETE_SHADOW_STATE`: show the stable
  `UNIFIED_VISIBLE_STATE_INCOMPLETE` code and retain the current legacy page without raising a page
  exception.

Fallback banners begin with `Nguồn kết quả hiển thị: pipeline legacy.` Unified banners begin with
`Nguồn kết quả hiển thị: Contract V1.` No page hides which pipeline supplies visible facts.

## 5. Expert-review behavior

`requires_expert_review=True` does not block unified display when no blocking discrepancy exists.
Pages show every expert-review code. Page 04 also exposes the corresponding discrepancy records,
including deterministic JSON text for legacy and unified values.

Expert review is neither automatic acceptance nor automatic rejection. Blocking discrepancy codes
always force the legacy fallback.

## 6. Page 02 unified projection

Page 02 displays the returned input-validity, parameter-consistency, technical-feasibility,
fleet-feasibility, and headway-quality dimensions. It preserves status, confidence, explanation,
issue code, severity, message, and evidence. It does not collapse `WARNING`,
`INSUFFICIENT_DATA`, or any other status into a fabricated Boolean pass/fail.

The total issue count is a `DISPLAY_DERIVED` count over returned issues.

## 7. Page 03 exact demand grain

Page 03 displays one row per returned `PresentationBlockV1`. It performs no aggregation,
interpolation, splitting, re-binning, combined-demand apportionment, or directional-demand
inference. Direction labels use terminal names for display while the presentation retains its raw
`outbound`, `inbound`, or `combined` value. Combined demand remains `Tổng hợp hai chiều`.

Maximum returned load factors and the explicit demand-gap count are labeled `DISPLAY_DERIVED`.
Scenario A trip counts are informational when returned. Scenario C columns contain values only for
an accepted authoritative C. Otherwise they remain blank; B is never copied into C.

## 8. Page 04 accepted-C authority

Page 04 displays only the unified disposition, adjustment decision, selected action, solver choice
and statuses, validator rejection codes, transparent solver vectors, solver recommendation,
comparison reason, accepted-C authority, explanations, and limitations. It does not display the
legacy weighted score.

When accepted C exists, the page displays returned fleet facts, exact headway-regime facts, and the
accepted solution fingerprint. Counts and maxima over exact returned presentation facts are labeled
`DISPLAY_DERIVED`.

When accepted C does not exist, the page states that no authoritative C exists, displays the
returned decision and diagnostic statuses, and renders no C timetable. Rejected raw candidates are
not present in the presentation and are not exposed.

## 9. Page 05 explicit non-cutover

`app_pages/05_xuat_file.py` remains unchanged and legacy-authoritative. It continues to use the
legacy supply summary, direction selector, overview figure, departure-detail figure, comparison
XLSX, result XLSX, PNG, HTML, and existing filenames. Milestone 5B2A adds no unified download.

Page 01, the submission pipeline, session-state keys, chart builders, exporters, Contract V1,
schemas, solvers, route corpus, and source template are unchanged.

## 10. Gate to Milestone 5B2B

Milestone 5B2B remains pending. It must separately address unified direction-specific chart
behavior, PNG/HTML generation, download filenames, and retirement of the two legacy XLSX products.
Milestone 5B2A supplies no authority for that work.

## 11. No automatic operational approval

Contract V1 result-page visibility supports expert diagnosis and recommendation. Neither a passed
authority gate, an accepted candidate, nor an expert-review state automatically authorizes an
operational timetable or replaces the accountable operating decision.
