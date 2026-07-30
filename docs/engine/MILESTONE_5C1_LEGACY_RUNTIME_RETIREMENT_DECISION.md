# Milestone 5C1: Legacy Runtime Retirement Decision

## 1. Executive decision

**Decision:** adopt **Option C — unified-only application runtime** as the target for Milestone 5.

Milestone 5C2 will make Contract V1 the only ordinary Streamlit analysis path. An
optimization-ready submission will not run `run_analysis(...)`, construct an `AnalysisBundle`,
build legacy figures or exports, or create a per-submission side-by-side report. A workbook that
is not optimization-ready will receive readiness facts and migration instructions, not legacy
analytical conclusions. A Contract V1 failure will fail closed; it will not silently substitute a
legacy result.

This decision approves the target and the gates, not their implementation. The runtime remains
parallel at baseline `ba80a4955ed47802f11d7f63a227567da12990f2`. `CUTOVER_COMPLETE`,
`LEGACY_RUNTIME_RETIRED`, and `LEGACY_CODE_DELETED` are distinct states. Milestone 5 remains
incomplete.

The current default Contract V1 solver remains `HEURISTIC`. This audit found that its adapter
directly imports `c_generator.generate_scenario_c(...)`, while Contract headway code imports
`_balanced_values(...)`, `_material_boundaries(...)`, and `_regime_drafts(...)`. Therefore
retiring the duplicate application runtime does not authorize deleting those shared
dependencies. Full `LEGACY_CODE_DELETED` cannot be claimed until those production imports are
removed or the code is formally rehomed behind Contract V1 without changing the approved solver
contract.

### Decision status

- Target option: **Option C, approved as the Milestone 5C1 recommendation**.
- Implementation authority: limited to a future Milestone 5C2 change.
- Runtime retirement: not yet achieved or approved for production.
- Code deletion: not yet achieved or approved.
- Formal repository approval event: review and merge of the future PR titled
  `Milestone 5C1: Define legacy runtime retirement gate`.

## 2. Current state

The required main baseline is
`ba80a4955ed47802f11d7f63a227567da12990f2` (`Milestone 5B2B: Cut over unified charts and
downloads`). It contains:

- Milestone 5B1 unified shadow execution;
- Milestone 5B2A unified Pages 02–04;
- Milestone 5B2B unified Page 05 charts and downloads;
- canonical departure-figure reconstruction and exact stored-figure comparison;
- complete, labeled legacy fallbacks; and
- no open pull request identified during the 5C1 baseline audit.

Visible cutover is conditional. Pages 02–05 display Contract V1 only after
`resolve_visible_result_context_v1(...)` accepts complete, aligned shadow evidence. The ordinary
submission pipeline still runs the full legacy path first, including all legacy presentation
artifacts. It checks readiness only afterward. Legacy execution is therefore both a prerequisite
for the current unified display gate and the source of every fallback.

The current ready-input path has two business evaluations, two Scenario C generation paths, two
sets of presentation projections, two XLSX families, and per-submission cross-path comparison.
That is intentional 5B validation architecture, not the governing end state.

## 3. Governing target

The governing target is one Contract V1-based application path:

```text
workbook import
-> authoritative-input readiness
-> Contract V1 normalization and Scenario B evaluation
-> adjustment decision
-> selected Contract V1 solver boundary
-> independent candidate validation
-> accepted solution, or an explicit no-accepted-C outcome
-> unified presentation, charts, and downloads
```

The normal path must not depend on legacy analytical success, an `AnalysisBundle`, legacy charts,
legacy exporters, legacy weighted scoring, or a per-submission legacy comparison. Missing
authority must remain missing. A rejected candidate must not become Scenario C. A failed unified
path must not be replaced by conclusions from a less authoritative path.

Release characterization may still execute legacy code outside ordinary Streamlit. That evidence
does not make legacy a product fallback.

## 4. Runtime sequence

The exact ordinary submission sequence at the required baseline is:

| # | Current operation | Exact implementation | Work classification |
|---:|---|---|---|
| 1 | Import uploaded workbook bytes. Import-invalid data raises before analysis. | `app_pages/01_nhap_du_lieu.py` -> `import_workbook(content)` | Authoritative input boundary |
| 2 | Apply submitted runtime parameters to a new imported object. | `apply_overrides(...)` | Authoritative input preparation |
| 3 | Deep-copy the updated input for legacy execution. | `run_parallel_application_pipeline_v1(...)`: `legacy_input = deepcopy(imported)` | Compatibility isolation; duplicated input state |
| 4 | Deep-copy the updated input for unified execution. | `unified_input = deepcopy(imported)` | Authoritative-path isolation |
| 5 | Run legacy validation, demand evaluation, greedy fleet assignment, weighted scoring, and legacy Scenario C generation. | `run_and_build_artifacts(...)` -> `run_analysis(...)` | Compatibility execution; duplicated business work |
| 6 | Build the legacy comparison figure, result XLSX, B/C comparison XLSX, HTML, PNG, and C fingerprint. | `build_comparison_diagram(...)`, `export_results(...)`, `export_bc_comparison(...)`, `diagram_png_bytes(...)` | Presentation-only, fallback-only output; duplicated work |
| 7 | Assess authoritative-input readiness after legacy succeeds. | `assess_workbook_input_readiness_v1(unified_input)` | Authoritative business gate, but ordered too late |
| 8 | Build strict options and normalize the workbook to Contract V1. | `normalization_options_from_workbook_v1(...)`; then `normalize_imported_workbook_v1(...)` inside `analyze_and_optimize_schedule_v1(...)` | Authoritative business execution |
| 9 | Evaluate B, decide adjustment, run the selected solver boundary when allowed, and independently validate any candidate. | `analyze_and_optimize_schedule_v1(...)` | Authoritative business execution |
| 10 | Project legacy and unified results into deterministic snapshots and compare them. | `build_side_by_side_validation_report_v1(...)` | Validation evidence; depends on duplicated execution |
| 11 | Build one unified presentation DTO. | `build_unified_presentation_v1(...)` | Presentation-only projection from authoritative facts plus validation evidence |
| 12 | Build stored unified figures and unified XLSX, then verify cross-artifact fingerprints. | unified diagram builders, `export_unified_result_workbook_v1(...)`, `_verify_unified_artifact_alignment_v1(...)` | Presentation-only work |
| 13 | Store legacy and unified objects, then resolve one visible authority. | Page 01 session assignments; `resolve_visible_result_context_v1(...)` | Authority/validation evidence |
| 14 | Render Pages 02–05. Page 05 reconstructs the canonical departure figure, compares its complete Plotly JSON with the stored figure, validates actual XLSX bytes, then creates HTML and PNG. | `app_pages/02_kiem_tra.py` through `05_xuat_file.py`; `build_unified_page5_artifacts_v1(...)` | Presentation-only work; Page 05 adds render-time integrity work |
| 15 | On input-not-ready, unified failure, cutover blocker, incomplete shadow state, or Page 05 artifact failure, render labeled legacy results; Page 05 may also build a legacy departure-detail figure at render time. | visible-result resolver and `_render_legacy_page5(...)` | Fallback-only work |

### Current duplication

The duplicated work is not limited to two solver calls. Legacy validation, demand evaluation,
fleet assignment, Scenario C generation, scoring, chart construction, XLSX creation, HTML/PNG
creation, state retention, and comparison are all paid before a ready submission can display
Contract V1. The two input deep copies and parallel result graph also increase memory use.

## 5. Legacy dependency inventory

### Classification rules

The status is the approved target role, not a claim that the current code already has that role:

- `REQUIRED_RUNTIME`: required by the target Contract V1 application path.
- `FALLBACK_ONLY`: currently exists only to render or support a legacy fallback.
- `REGRESSION_ORACLE`: legacy computation retained outside the application during transition.
- `OFFLINE_VALIDATION`: release, corpus, or developer comparison evidence.
- `TEST_SUPPORT`: retained only for automated characterization.
- `RETIREMENT_CANDIDATE`: has no approved target consumer after migration.
- `MUST_REMAIN`: shared input or solver dependency that cannot be removed as “legacy” without a
  separately proven replacement.

“Ready?” means the current ordinary optimization-ready path needs the object, even if only
because the 5B gate was designed around it. “Old?” means the current old-workbook fallback needs
it. “Tests?” means current tests directly depend on it.

### Runtime orchestration

| Status | Exact path or symbol | Current consumer and purpose | Ready? | Old? | Tests? | Retirement prerequisite | Final disposition |
|---|---|---|:---:|:---:|:---:|---|---|
| `RETIREMENT_CANDIDATE` | `src/bus_schedule_engine/application_pipeline.py::run_parallel_application_pipeline_v1` | Page 01; runs legacy first and unified second | Yes | Yes | Yes | 5C2 unified-first orchestrator and failure contract | Replace in 5C2; delete/rename parallel entry point in 5C3 |
| `FALLBACK_ONLY` | `src/bus_schedule_engine/ui_utils.py::run_and_build_artifacts` | Parallel pipeline; builds the complete legacy bundle and artifact set | Yes | Yes | Yes | No application legacy fallback; offline oracle has its own entry point | Remove from application in 5C2; delete in 5C3 |
| `REGRESSION_ORACLE` | `src/bus_schedule_engine/service.py::run_analysis` | Legacy artifact path, side-by-side convenience runner, scripts, tests | Yes | Yes | Yes | Offline characterization covers approved cases | Retain outside application through compatibility window; then test-only or delete |
| `REQUIRED_RUNTIME` | `src/bus_schedule_engine/optimization_service.py::analyze_and_optimize_schedule_v1` | Parallel pipeline and tests; owns Contract V1 application result | Yes | No | Yes | None for runtime retirement | Becomes the only ordinary analysis service |
| `OFFLINE_VALIDATION` | `src/bus_schedule_engine/side_by_side_validation.py::build_side_by_side_validation_report_v1` | Parallel pipeline, presentation builder input, tests | Yes | No | Yes | Presentation and authority resolver no longer require per-request report | Move to CI/release audit; remove from session and ordinary runtime |
| `OFFLINE_VALIDATION` | `src/bus_schedule_engine/side_by_side_validation.py::run_side_by_side_validation_v1` | Tests/developer callers; independently runs both paths | No | No | Yes | Stable CLI or CI wrapper and retained evidence format | Use only in explicit offline characterization |
| `RETIREMENT_CANDIDATE` | `src/bus_schedule_engine/application_pipeline.py::ParallelApplicationRunV1` | Page 01 pipeline return and tests; requires legacy fields | Yes | Yes | Yes | Unified-only return type with granular failure state | Replace in 5C2; remove in 5C3 |
| `RETIREMENT_CANDIDATE` | `src/bus_schedule_engine/application_pipeline.py::ParallelRuntimeStatusV1` | Session state, authority resolver, pages, tests | Yes | Yes | Yes | Stable unified-only statuses implemented | Replace; remove stale “parallel/shadow” naming in 5C3 |

### Legacy result objects

| Status | Exact path or symbol | Current consumer and purpose | Ready? | Old? | Tests? | Retirement prerequisite | Final disposition |
|---|---|---|:---:|:---:|:---:|---|---|
| `REGRESSION_ORACLE` | `src/bus_schedule_engine/models.py::AnalysisBundle` | Legacy pages, figures, exporters, side-by-side snapshot | Yes | Yes | Yes | Unified app completes without this type | Remove from production/session; retain only with oracle |
| `REGRESSION_ORACLE` | `src/bus_schedule_engine/models.py::ScenarioResult` | Legacy B/C facts, frames, charts, exports, comparison | Yes | Yes | Yes | Offline snapshots preserve required evidence | Remove from product result path; retain only with oracle |
| `REGRESSION_ORACLE` | `AnalysisBundle.get("C")` legacy Scenario C | Legacy Pages 04–05, exports, comparison evidence | Yes | Yes | Yes | Accepted-C authority is exclusively Contract V1 | Comparison-only during transition; never user authority |
| `FALLBACK_ONLY` | `ParallelApplicationRunV1.legacy_figure` from `build_comparison_diagram(...)` | `diagram_figure` and legacy Page 05 | Yes | Yes | Yes | Unified Page 05 characterization passes | Stop constructing in 5C2; remove in 5C3 |
| `FALLBACK_ONLY` | `ParallelApplicationRunV1.legacy_artifacts` mapping | Page 01/session and four legacy Page 05 downloads | Yes | Yes | Yes | Old-workbook and failure policies approved | No ordinary access after 5C2; delete builders in 5C3 |
| `RETIREMENT_CANDIDATE` | `legacy_artifacts["c_fingerprint"]` / legacy C fingerprint | Page 01 session parity checks and tests | Yes | Yes | Yes | Unified fingerprints cover product integrity | Preserve only inside offline oracle evidence |

### Session state

| Status | Exact key | Current consumer and purpose | Ready? | Old? | Tests? | Retirement prerequisite | Final disposition |
|---|---|---|:---:|:---:|:---:|---|---|
| `MUST_REMAIN` | `imported_workbook` | Submission and input context | Yes | Yes | Yes | None | Keep, or rename only through a separate state migration |
| `RETIREMENT_CANDIDATE` | `analysis_bundle` | All legacy pages and current resolver existence gate | Yes | Yes | Yes | Resolver accepts a unified run without `AnalysisBundle` | Stop writing in 5C2; remove in 5C3 |
| `FALLBACK_ONLY` | `diagram_figure` | Legacy Page 05 overview | Yes | Yes | Yes | Legacy Page 05 removed | Stop writing in 5C2; remove in 5C3 |
| `FALLBACK_ONLY` | `download_artifacts` | Legacy Page 05 four-download bundle | Yes | Yes | Yes | Legacy downloads removed | Stop writing in 5C2; remove in 5C3 |
| `RETIREMENT_CANDIDATE` | `scenario_c_fingerprint` | Legacy Page 05/test integrity evidence | Yes | Yes | Yes | Unified accepted-solution fingerprint is sole product authority | Remove from product state |
| `RETIREMENT_CANDIDATE` | `parallel_runtime_status` | Resolver selects unified or one legacy mode | Yes | Yes | Yes | Unified status model implemented | Replace with unified-only status |
| `REQUIRED_RUNTIME` | `workbook_input_readiness` | Authority gate and readiness display | Yes | Yes | Yes | None | Keep as a first-class pre-analysis result |
| `REQUIRED_RUNTIME` | `unified_optimization_result` | Unified presentation and Pages 02–04 | Yes | No | Yes | None | Keep; naming may be simplified after 5C3 |
| `OFFLINE_VALIDATION` | `side_by_side_validation_report` | Current presentation/gate discrepancy evidence | Yes | No | Yes | Offline blocker policy and report retention | Remove from session in 5C2 |
| `REQUIRED_RUNTIME` | `unified_presentation` | Pages 02–05 and integrity verification | Yes | No | Yes | Presentation builder can consume unified-only evidence | Keep |
| `REQUIRED_RUNTIME` | `unified_demand_supply_figure` | Resolver and Page 05 | Yes | No | Yes | None | Keep or rebuild from immutable presentation |
| `REQUIRED_RUNTIME` | `unified_departure_figure` | Resolver and canonical stored-figure comparison | Yes | No | Yes | None | Keep while stored-figure integrity is required |
| `REQUIRED_RUNTIME` | `unified_download_artifacts` | Resolver and Page 05 actual-byte checks | Yes | No | Yes | None | Keep as an atomic unified bundle |
| `RETIREMENT_CANDIDATE` | `unified_runtime_failure` | Current single shadow-failure fallback | No on success | No | Yes | Granular stable unified failure model | Replace in 5C2; do not keep “shadow failure” semantics |

### UI branches

| Status | Exact branch | Current consumer and purpose | Ready? | Old? | Tests? | Retirement prerequisite | Final disposition |
|---|---|---|:---:|:---:|:---:|---|---|
| `FALLBACK_ONLY` | `app_pages/02_kiem_tra.py` non-unified branch | Legacy technical validation frame | On fallback | Yes | Yes | Unified failure/readiness policy implemented | Remove in 5C3 |
| `FALLBACK_ONLY` | `app_pages/03_nhu_cau.py` non-unified branch | Legacy demand evaluation frame | On fallback | Yes | Yes | Unified failure/readiness policy implemented | Remove in 5C3 |
| `FALLBACK_ONLY` | `app_pages/04_khuyen_nghi.py` non-unified branch | Legacy score, recommendation, and legacy C | On fallback | Yes | Yes | Unified no-C and error UX approved | Remove in 5C3 |
| `FALLBACK_ONLY` | `app_pages/05_xuat_file.py::_render_legacy_page5` | Complete legacy charts and four downloads | On fallback | Yes | Yes | Atomic unified artifact policy and migration policy approved | Remove in 5C3 |
| `FALLBACK_ONLY` | `VisibleResultModeV1.LEGACY_INPUT_NOT_READY` | Shows legacy diagnostics with readiness codes | No | Yes | Yes | Readiness-only migration UX | Replace with no-analysis readiness state |
| `FALLBACK_ONLY` | `VisibleResultModeV1.LEGACY_UNIFIED_FAILED` | Substitutes legacy after Contract V1 exception | On failure | No | Yes | Fail-closed unified error UX and logging | Remove; never invoke legacy on failure |
| `FALLBACK_ONLY` | `VisibleResultModeV1.LEGACY_CUTOVER_BLOCKED` | Substitutes legacy on per-submission discrepancy blocker | On blocker | No | Yes | Blockers move to release evidence; product fails closed | Remove |
| `FALLBACK_ONLY` | `VisibleResultModeV1.LEGACY_INCOMPLETE_SHADOW_STATE` | Substitutes legacy on missing/stale parallel state | On failure | No | Yes | Unified state is atomic and independently checked | Replace with unified integrity error |
| `FALLBACK_ONLY` | `app_pages/05_xuat_file.py::UNIFIED_PAGE5_ARTIFACT_FAILED` branch | Suppresses partial unified artifacts and shows full legacy Page 05 | On failure | No | Yes | Unified artifact failure policy | Keep atomic suppression; remove legacy substitution |

### Legacy and shared modules

| Status | Exact path or symbol | Current consumer and purpose | Ready? | Old? | Tests? | Retirement prerequisite | Final disposition |
|---|---|---|:---:|:---:|:---:|---|---|
| `MUST_REMAIN` | `src/bus_schedule_engine/validator.py::validate_schedule` | `service.py` and `c_generator.py`; validates heuristic candidates | Yes, through default Contract heuristic | Yes | Yes | Contract-native replacement proven without solver change | Do not delete merely with legacy runtime |
| `MUST_REMAIN` | `src/bus_schedule_engine/demand.py::evaluate_scenario` | `service.py` and `c_generator.py`; legacy/heuristic evaluation | Yes, through default Contract heuristic | Yes | Yes | Contract-native heuristic evaluation proven | Retain or rehome behind Contract boundary |
| `REGRESSION_ORACLE` | `src/bus_schedule_engine/demand.py::blocks_needing_more_trips` | `run_analysis(...)` generation report | Yes, only through legacy run | Yes | Yes | Oracle report no longer requires it | Test-only or delete after oracle retirement |
| `MUST_REMAIN` | `src/bus_schedule_engine/c_generator.py::generate_scenario_c` | Legacy generator and `contracts_v1/heuristic_solver.py` | Yes, direct production import | Yes | Yes | Contract-native heuristic implementation with equivalent validator evidence | Retain until separately replaced |
| `MUST_REMAIN` | `c_generator.py::_balanced_values`, `_material_boundaries`, `_regime_drafts` | `contracts_v1/headway_regimes.py` | Yes, direct production imports | Yes | Yes | Move to Contract-owned module with parity tests | Retain until rehomed |
| `REGRESSION_ORACLE` | `src/bus_schedule_engine/generator.py::generate_recommendations` | `service.run_analysis(...)`; wraps legacy C generation | Yes, through legacy run | Yes | Yes | Oracle entry point isolated from production | Retain through transition, then test-only/delete |
| `MUST_REMAIN` | `src/bus_schedule_engine/fleet.py::assign_fleet` | Page 01 preview, legacy service/generator, `c_generator.py` | Yes, including default Contract heuristic | Yes | Yes | Preview and heuristic use Contract-owned equivalent | Retain or rehome; not a 5C2 deletion |
| `REGRESSION_ORACLE` | `src/bus_schedule_engine/comparator.py::load_scoring_config` and `score_scenario` | Legacy service and legacy result XLSX | Yes, only through legacy run/export | Yes | Yes | Weighted score removed from product and oracle snapshot preserved | Test-only or delete after oracle retirement |
| `FALLBACK_ONLY` | `src/bus_schedule_engine/diagram.py::build_comparison_diagram` | Legacy artifact builder and Page 05 direction changes | Yes, generated eagerly | Yes | Yes | Unified chart characterization passes | Remove from application in 5C2; delete in 5C3 |
| `FALLBACK_ONLY` | `src/bus_schedule_engine/diagram.py::build_departure_detail_diagram` | Legacy Page 05 render-time detail chart | On fallback | Yes | Yes | Unified canonical departure coverage passes | Delete in 5C3 |
| `FALLBACK_ONLY` | `src/bus_schedule_engine/diagram.py::diagram_png_bytes` | Legacy PNG download | Yes, generated eagerly | Yes | Yes | Unified PNG evidence passes | Delete with legacy chart export |
| `FALLBACK_ONLY` | `src/bus_schedule_engine/excel_exporter.py::export_results` | Legacy result workbook | Yes, generated eagerly | Yes | Yes | No product legacy download; evidence archived | Delete result-export portion in 5C3 |
| `MUST_REMAIN` | `src/bus_schedule_engine/excel_exporter.py::create_input_template` | Page 01 template, scripts, import/readiness tests | Yes | Yes | Yes | Separate template module exists if exporter is split | Keep; split from legacy result exporter before file deletion |
| `FALLBACK_ONLY` | `src/bus_schedule_engine/comparison_exporter.py::export_bc_comparison` | Legacy B/C comparison download | Yes, generated eagerly | Yes | Yes | No product legacy downloads | Delete in 5C3; it is not cross-path 5A1 evidence |
| `FALLBACK_ONLY` | `src/bus_schedule_engine/comparison_exporter.py::exported_c_fingerprint` | Verifies legacy B/C workbook | Yes | Yes | Yes | Legacy comparison export removed | Delete with comparison exporter |
| `FALLBACK_ONLY` | `ui_utils.py::validation_frame`, `block_frame`, `scenario_frame`, `supply_summary_frame`, `regime_frame` | Legacy Pages 02–05 | On fallback | Yes | Yes | Legacy page branches removed | Delete in 5C3 |
| `MUST_REMAIN` | `ui_utils.py::workbook_sheet_names`, `preview_sheet`, `apply_overrides`, `template_bytes` | Page 01 import/preview/input behavior | Yes | Yes | Yes | Only optional module split | Keep as input UI helpers |
| `FALLBACK_ONLY` | `src/bus_schedule_engine/block_supply.py::scenario_supply_summary` and `available_supply_directions` | Legacy Page 05 and legacy diagram | On fallback | Yes | Yes | Legacy Page 05/chart removal | Delete if no oracle needs them |
| `OFFLINE_VALIDATION` | `scripts/build_sample_artifacts.py` | Developer sample legacy artifacts | No | No | No | Explicit developer-only command and no production import | Keep only if release evidence requires it; otherwise delete in 5C3 |
| `TEST_SUPPORT` | `tests/test_application_pipeline.py`, `tests/test_side_by_side_validation.py`, and legacy-fallback cases in `tests/test_ui.py` | Current parallel/fallback characterization | No | No | Yes | 5C2 target tests added and historic evidence retained | Rewrite around unified runtime; retain offline comparisons |
| `TEST_SUPPORT` | `tests/test_integration.py`, `tests/test_scenario_c.py`, `tests/test_fleet_and_generator.py` | Legacy oracle and heuristic behavior | No | No | Yes | Decide which behavior protects Contract heuristic | Keep required oracle/shared-dependency tests |

### Inventory totals

The inventory contains **58 classified entries**:

| Classification | Count |
|---|---:|
| `REQUIRED_RUNTIME` | 7 |
| `FALLBACK_ONLY` | 22 |
| `REGRESSION_ORACLE` | 7 |
| `OFFLINE_VALIDATION` | 4 |
| `TEST_SUPPORT` | 2 |
| `RETIREMENT_CANDIDATE` | 8 |
| `MUST_REMAIN` | 8 |

The totals count each table row, including grouped symbols that share one consumer and
disposition.

## 6. Runtime fallback matrix

This matrix contrasts the current baseline with the approved target:

| Condition | Current baseline | Option C target | Legacy executes in target? |
|---|---|---|:---:|
| Import-invalid | Import error; no pipeline | Show `WORKBOOK_IMPORT_INVALID`; no analysis or result downloads | No |
| Import-ready, optimization-not-ready | Legacy runs first; Pages 02–05 show legacy diagnostics | Show exact readiness codes and migration guidance only | No |
| Optimization-ready, unified succeeds | Legacy and unified both run; unified may display | Unified-only facts and artifacts | No |
| Normalization fails unexpectedly | Legacy fallback | Fail closed with `CONTRACT_V1_NORMALIZATION_FAILED` | No |
| Solver infrastructure fails | Legacy fallback | Fail closed with `CONTRACT_V1_SOLVER_FAILED` | No |
| Candidate is independently rejected | Unified no-C result if aligned; otherwise legacy fallback | Show B/outcome/rejection facts; never show candidate or legacy C | No |
| Per-submission comparison blocker | Legacy fallback | Comparison is not in the request path; release blocker prevents deployment | No |
| Unified state is incomplete or semantically inconsistent | Legacy fallback | Fail closed with semantic-integrity status | No |
| Page 05 artifact build fails | Complete legacy Page 05 | Keep aligned diagnostic facts; disable the entire download/chart artifact bundle | No |
| Emergency rollback | Not applicable | Deploy the previous complete application release; never switch within a request | Previous release only |

## 7. Options evaluated

| Criterion | Option A — permanent parallel | Option B — unified-first, lazy legacy | Option C — unified-only |
|---|---|---|---|
| Correctness | Strong discrepancy visibility but two authorities remain live | Unified is normal, but fallback can still contradict Contract authority | One explicit authority; failure and no-C states remain honest |
| Compatibility | Highest short-term compatibility | Selective old-workbook compatibility | Old workbooks require migration; no fabricated authority |
| Runtime cost | Highest: duplicate analysis and artifact work every ready run | Lower normally; spikes on fallback | Lowest ordinary cost; one business/presentation path |
| Memory cost | Highest: two deep copies and two result/artifact graphs | Usually one graph; two on fallback | One input/result/artifact graph plus bounded diagnostics |
| Maintenance | Maintains both paths indefinitely | Maintains two production paths and fallback triggers | One production path; legacy retained only as temporary oracle |
| Operator clarity | Lowest; a visible result can change authority by discrepancy state | Better, but fallback authority remains conditional | Highest; Contract V1 or a clear failure/readiness state |
| Discrepancy detection | Per submission | Usually offline, sometimes on fallback | Offline CI/release characterization |
| Failure resilience | Legacy masks unified failures | Legacy may mask failures unless tightly restricted | Fails closed; release rollback handles incidents |
| Technical debt | Permanent parallel architecture | Long-lived conditional legacy path | Aligns with governing target and permits deletion |
| Backward compatibility risk | Lowest | Medium | Highest initially; addressed with explicit migration window |
| Long-term operational risk | High ambiguity and cost | Medium ambiguity | Lower authority ambiguity; requires strong pre-release evidence |

### Option B questions

The only plausible lazy-legacy triggers are an old workbook, an unexpected Contract V1 failure,
a cutover discrepancy, or an artifact failure. None justifies user-facing legacy analysis:

- old workbooks lack declared authority, so legacy conclusions can look more authoritative than
  the input permits;
- running legacy after a unified failure is technically isolated only if mutation boundaries and
  exception state are proven, but it still hides a product defect;
- a cutover discrepancy is a release-quality problem, not a reason to choose a different answer
  for one user; and
- an artifact failure should suppress artifacts, not change analytical authority.

Option B could provide legacy diagnostics and release comparison, but it would preserve the exact
two-authority ambiguity 5C is intended to retire. It is not selected.

### Selected option

**Option C is the sole target.** Options A and B are rejected as production end states.

## 8. Recommended target

The approved answers are:

1. **Workbook imports but is not optimization-ready:** show import facts, every sorted readiness
   code, the generated-template link, and migration instructions. Do not analyze.
2. **Legacy diagnostic results for that workbook:** do not show them.
3. **Unexpected Contract V1 runtime error:** retain safe provenance/readiness facts, show a stable
   error code plus correlation ID, and log the exception.
4. **Fail closed or run legacy:** fail closed.
5. **Legacy on ordinary ready input:** no.
6. **Per-submission side-by-side validation:** no.
7. **Side-by-side after retirement:** CI characterization plus an explicit release-candidate
   audit command over the anonymized corpus and synthetic cases.
8. **Legacy downloads accessible:** none in ordinary Streamlit after 5C2. Offline evidence is not
   a user download. A whole-release rollback may temporarily restore the prior UI.
9. **Legacy session keys:** no `analysis_bundle`, `diagram_figure`, `download_artifacts`, or
   `scenario_c_fingerprint` after 5C2. `parallel_runtime_status` and the session
   `side_by_side_validation_report` also leave the product path. `imported_workbook` remains.
10. **Legacy modules retained for regression:** initially `service.py`, legacy result model
    projections, `generator.py`, scoring, and the side-by-side adapter. `c_generator.py`,
    `validator.py`, `demand.py`, and `fleet.py` additionally remain production dependencies of the
    default Contract heuristic until separately rehomed or replaced.
11. **Rollback:** deploy the last known-good pre-5C2 application release. No feature flag,
    legacy/unified toggle, or within-request retry into legacy is approved.
12. **Transitional compatibility period:** two consecutive production release cycles and at
    least 90 calendar days after the 5C2 release, whichever is longer. The period provides
    migration documentation and support, not legacy analytical results.
13. **Evidence to advance:** every case in Section 13 passes on the target commit; no release
    blocker exists; artifact fingerprints align; rollback is rehearsed; and the evidence package
    is retained.
14. **Final retirement approval:** joint written approval by the Product Owner, Engineering
    Owner, and QA/Release Owner named in the approval record.

## 9. Backward-compatibility policy

### Import-invalid

The workbook cannot be parsed safely or violates import-required shape/types.

- Stable status: `WORKBOOK_IMPORT_INVALID`.
- Display: sanitized import error, affected sheet/field when safe, generated-template link, and
  migration documentation.
- Analysis: none.
- Downloads: no result downloads. The unmodified source remains with the user; the application
  does not rewrite it.
- Legacy: never runs.

### Import-ready but optimization-not-ready

The workbook imports but lacks authoritative optimization fields.

- Stable status: `WORKBOOK_OPTIMIZATION_NOT_READY`.
- Display: source identity, route/terminal names and imported counts as input facts; every exact
  `missing_optimization_authority_codes` value; optional terminal-capacity limitations; and an
  upgrade checklist.
- Technical diagnostic: no schedule-feasibility, demand-sufficiency, fleet, score,
  recommendation, or Scenario C conclusion. Readiness facts are not an analytical result.
- Legacy analysis: prohibited.
- Downloads: no result XLSX, chart, HTML, or PNG. The generated blank/sample template remains
  available as an input resource.
- Upgrade: copy only declared facts into the current template and obtain missing authority from
  an accountable source. Never infer fleet, operating day, demand source, confidence, or response
  mode.
- Readiness codes include, as applicable:
  `AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION`,
  `OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION`,
  `SCENARIO_A_AVAILABLE_FLEET_LIMIT_REQUIRED_FOR_OPTIMIZATION`,
  `SCENARIO_A_OPERATING_DAY_TYPE_REQUIRED_FOR_OPTIMIZATION`,
  `DEMAND_SOURCE_TYPE_REQUIRED_FOR_OPTIMIZATION`,
  `DEMAND_CONFIDENCE_REQUIRED_FOR_OPTIMIZATION`, and
  `DEMAND_RESPONSE_MODE_REQUIRED_FOR_OPTIMIZATION`.

### Optimization-ready

Readiness is assessed before any analysis. Contract V1 normalizes once, evaluates once, runs the
selected solver boundary at most once per selected solver, validates candidates independently,
and builds an atomic unified presentation/artifact set. Legacy does not execute. Failure follows
Section 10.

### Historical legacy workbook

The approved compatibility route is a **documentation-only migration process** using the current
generated template. There is no legacy-results route and no automatic converter in 5C2. During
the compatibility period, support may explain missing fields and source requirements, but may not
invent or prefill authority. A future converter would require separate approval and must preserve
missing values as missing.

After the compatibility period, the same readiness behavior remains; only the elevated migration
support commitment ends.

## 10. Unified failure policy

All user-visible messages include a stable status and a correlation ID. Logs include source
identity/hash, target commit, stage, exception class, sanitized message, readiness codes, solver
choice, result-status codes, and artifact fingerprints that existed before failure. Logs must not
contain workbook secrets or raw passenger rows unless separately approved.

| Case | Stable status | Visible unified facts | Legacy? | Downloads | Retry | Required evidence |
|---|---|---|:---:|---|---|---|
| Readiness failure | `WORKBOOK_OPTIMIZATION_NOT_READY` plus exact readiness codes | Import/readiness facts only | No | No result downloads | After workbook upgrade | Missing-code tuple and source hash |
| Normalization failure after readiness | `CONTRACT_V1_NORMALIZATION_FAILED` | Readiness/provenance only; no analysis conclusion | No | None | After input correction or software fix | Normalization stage, exception, source hash |
| Solver infrastructure/runtime failure | `CONTRACT_V1_SOLVER_FAILED` | Aligned B evaluation may remain only if captured as an immutable verified result; no C | No | None unless a separately complete B-only artifact contract is approved | Yes for transient failure | Solver choice, request/problem fingerprints, termination/error |
| Candidate rejection | `CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR` and exact validator codes | B, adjustment, solver, and rejection facts; no raw rejected timetable and no C | No | Atomic unified no-C downloads may remain | After input/policy change; not an exception retry | Candidate identity permitted only in protected logs; validator codes retained |
| Artifact construction failure | `CONTRACT_V1_ARTIFACT_FAILED` | Verified presentation facts may remain on Pages 02–04 | No | Disable all Page 05 charts/downloads; never mix partial artifacts | Yes | Failing artifact stage and all available fingerprints |
| Semantic-integrity mismatch | `CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH` | No result is authoritative; show status only | No | None | After software/state reset | Expected/actual fingerprints and mismatch location |
| Unexpected application exception | `CONTRACT_V1_APPLICATION_ERROR` | Provenance/readiness facts only | No | None | Yes after incident assessment | Correlation ID, stage, exception, commit, source hash |

An independently rejected candidate is a completed Contract V1 outcome, not a runtime failure.
The application may still produce a no-C unified report if every artifact is semantically aligned.

## 11. Side-by-side validation disposition

Per-submission side-by-side validation is removed from ordinary Streamlit in 5C2.

### Approved destinations

1. **CI characterization suite:** deterministic synthetic cases and the generated authoritative
   template run both paths while the oracle is retained.
2. **Anonymized route corpus:** Alpha and Beta protect source facts, demand grain, coverage gaps,
   and no-fabrication behavior.
3. **Release-candidate audit command:** explicitly executes the legacy oracle and Contract V1,
   emits machine-readable comparisons, and exits nonzero on blockers.
4. **Developer-only comparison CLI:** may wrap the release command for local diagnosis. It is not
   imported or exposed by ordinary Streamlit.

An optional diagnostic mode inside ordinary Streamlit is rejected. A local mode is acceptable
only as an explicit external CLI invocation, not a feature flag, toggle, or hidden request path.

### Required comparisons

- exact Scenario B source facts and timetable locks;
- exact demand grain and no fabricated directional/combined demand;
- validation and fleet conclusions as characterized evidence;
- terminal-occupancy authority and limitation codes;
- candidate acceptance/rejection and absence of rejected-C presentation;
- accepted-C source mapping, trip counts, endpoints, runtimes, fleet, and headway facts where
  comparison is semantically valid;
- deterministic presentation and download fingerprints; and
- expected status, visible authority, download authority, and legacy-execution count for every
  Section 13 case.

### Blockers

The following block a release:

- any current `MUST_MATCH` / `BLOCKS_CUTOVER` discrepancy;
- a semantic-integrity or fingerprint mismatch;
- a rejected candidate exposed as C;
- altered demand grain or fabricated authority;
- unexpected legacy execution in the target application path;
- a missing expected failure/readiness code;
- nondeterministic result or artifact fingerprints; or
- an unreviewed change to a characterized expected difference.

Legacy-only C, unified-only accepted C, and non-comparable weighted-score/vector facts are not
automatically blockers. They must retain their explicit classification and review record.

### Retained evidence and adapter retirement

Each release package retains the target commit, environment and dependency versions, fixture
hashes, solver choice, machine-readable comparison rows, blocker/review codes, fingerprints, and
the approving review record. Legacy Scenario C remains comparison-only.

The side-by-side adapter may be retired only after:

- `LEGACY_RUNTIME_RETIRED` is approved;
- the compatibility period is closed;
- two consecutive release-candidate audits pass without unapproved discrepancies;
- required oracle snapshots are stored independently of executable legacy modules; and
- Product, Engineering, and QA/Release owners approve removal.

## 12. Milestone 5 completion gate

### `CUTOVER_COMPLETE`

Required:

- Pages 02–05 use Contract V1 facts and artifacts when the authority gate passes;
- no rejected candidate is presented as Scenario C;
- exact demand grain is preserved without splitting, combining, or inference;
- visible facts, figures, and downloads share aligned semantic fingerprints;
- canonical departure reconstruction matches stored figure evidence;
- fallback behavior is explicit and never mixes authorities; and
- expert-review and blocking discrepancy codes remain visible.

**Baseline status:** conditionally achieved by 5B2A/5B2B. This state alone does not complete
Milestone 5.

### `LEGACY_RUNTIME_RETIRED`

Required:

- readiness executes before analysis;
- ordinary optimization-ready submissions do not call legacy analysis;
- no per-submission legacy chart, HTML, PNG, or exporter work occurs;
- the application completes a unified run without an `AnalysisBundle`;
- unified failure behavior is granular, stable, logged, and fail-closed;
- import-invalid, not-ready, and historical-workbook handling is approved;
- per-submission side-by-side comparison is removed and its offline disposition works;
- legacy result downloads and session keys are absent from ordinary Streamlit;
- every Section 13 end-to-end characterization passes; and
- rollback deployment is rehearsed and documented.

**Baseline status:** not achieved. This is the Milestone 5C2 implementation gate.

### `LEGACY_CODE_DELETED`

Required:

- no production import references a legacy runtime module;
- approved regression evidence is preserved without requiring production imports;
- legacy session-state keys and UI branches are removed;
- legacy result exporters and chart builders are removed or explicitly isolated as test-only;
- stale “shadow” and “parallel” application naming is removed;
- documentation and application labels describe one Contract V1 runtime;
- the generated input template remains supported after any `excel_exporter.py` split;
- `contracts_v1/heuristic_solver.py` no longer imports `c_generator.generate_scenario_c`, and
  `contracts_v1/headway_regimes.py` no longer imports private `c_generator` helpers, unless those
  symbols have been formally rehomed as Contract-owned code with equivalent tests; and
- full regression and release characterization passes.

**Baseline status:** not achieved. Runtime retirement must be proven before broad deletion.

The three states must be recorded separately. A 5C2 implementation may achieve
`LEGACY_RUNTIME_RETIRED` without achieving `LEGACY_CODE_DELETED`.

## 13. End-to-end evidence requirements

The table describes the post-5C2 target:

| Case | Expected runtime path | Visible authority | Download authority | Legacy executes? | Expected stable status |
|---|---|---|---|:---:|---|
| Generated authoritative template | Import -> ready -> normalize -> evaluate/solve -> unified artifacts | Contract V1 | Complete atomic unified bundle | No | `SOLUTION_ACCEPTED` or explicit completed no-C outcome |
| Import-ready, optimization-not-ready workbook | Import -> readiness -> stop | Readiness facts only | None | No | `WORKBOOK_OPTIMIZATION_NOT_READY` plus exact missing codes |
| Alpha corpus | Offline/app Contract characterization; LOW-confidence assessment, no solver | Contract V1 diagnostic facts; no C | Unified no-C evidence when artifact contract passes | No in app; yes only in offline audit | `B_INSUFFICIENT_DATA` |
| Beta corpus | Contract characterization preserves outbound 17:00–18:00 gap; no solver | Contract V1 diagnostic facts; no C | Unified no-C evidence when artifact contract passes | No in app; yes only in offline audit | `B_INSUFFICIENT_DATA` with coverage limitation |
| Accepted synthetic C | Ready -> solver -> independent validation -> accepted C | Contract V1 accepted C | Unified XLSX/HTML/PNG with accepted fingerprint | No | `SOLUTION_ACCEPTED` |
| Rejected candidate | Ready -> solver -> independent rejection -> no C | Contract V1 B/outcome/rejection facts | Unified no-C bundle only if complete | No | `CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR` plus validator codes |
| Mixed `BOTH` result | Run both; one rejected and recommended outcome accepted | Accepted recommended Contract V1 C; other rejection remains diagnostic | Unified bundle for accepted recommendation | No | `SOLUTION_ACCEPTED` plus non-recommended rejection codes |
| Combined demand | Preserve combined blocks; no directional inference | Contract V1 exact combined grain; C only if supported and accepted | Unified exact-grain bundle | No | Completed result with directional-solving limitation when applicable |
| Directional demand | Preserve exact outbound/inbound blocks and run eligible solver path | Contract V1 exact direction facts | Unified exact-direction bundle | No | Solver result status returned by Contract V1 |
| Terminal occupancy not evaluated | Normal unified run with neither limit inferred | Contract V1 plus limitation | Unified bundle retains limitation | No | `TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED` |
| Partial terminal occupancy authority | Normal unified run with supplied terminal enforced only | Contract V1, `PARTIALLY_EVALUATED` | Unified bundle retains supplied limit and missing-side code | No | `TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED` or terminal 2 equivalent |
| Unified runtime exception | Stop at failing stage | Error/readiness facts only | None | No | Stage-specific failure or `CONTRACT_V1_APPLICATION_ERROR` |
| Artifact integrity failure | Analysis/presentation may complete; atomic artifact exposure fails | Verified Pages 02–04 facts only, unless semantic mismatch invalidates all | None | No | `CONTRACT_V1_ARTIFACT_FAILED` or `CONTRACT_V1_SEMANTIC_INTEGRITY_MISMATCH` |
| Old workbook migration | Import -> readiness -> stop -> documented migration | Readiness facts only | Current generated input template, not a result download | No | `WORKBOOK_OPTIMIZATION_NOT_READY` |

For each case, tests must additionally assert call counts, session keys, source identity, exact
reason/limitation codes, absence of mixed legacy/unified output, and deterministic fingerprints
where artifacts exist.

## 14. Milestone 5C2 boundary

Milestone 5C2 implements unified-first runtime only:

- assess readiness before any legacy execution;
- make the ready path complete without an `AnalysisBundle`;
- remove mandatory legacy execution for ready input;
- implement the approved old-workbook and failure policies;
- move side-by-side comparison out of ordinary Streamlit;
- stop constructing legacy figures and downloads per submission;
- stop writing legacy result session keys;
- retain legacy code as an offline regression oracle;
- preserve the default solver and Contract V1;
- add end-to-end characterization for Section 13; and
- avoid broad module deletion or unrelated renaming.

5C2 does not delete the legacy oracle, redesign solvers, change schemas/templates, expose solver
selection, or implement V1-A1.

## 15. Milestone 5C3 boundary

After `LEGACY_RUNTIME_RETIRED` is approved, Milestone 5C3 may:

- remove approved legacy UI fallback branches and retired state fields;
- remove legacy chart and result-export execution;
- remove retired legacy service/generator/scoring modules when no shared dependency remains;
- isolate only explicitly approved regression support;
- split input-template creation from legacy result export before deleting mixed modules;
- remove stale “shadow” and “parallel” runtime naming;
- update documentation and application labels; and
- prove full regression, offline characterization, and production-import closure.

5C3 must not silently change the default solver. If eliminating direct Contract imports from
`c_generator.py`, `demand.py`, `fleet.py`, or `validator.py` requires a behavior change, that work
needs its own reviewed design and evidence. 5C2 and 5C3 remain separate.

## 16. Explicit exclusions

This decision does not:

- modify runtime or Streamlit behavior;
- stop legacy execution today;
- change readiness order today;
- remove a fallback, session key, branch, module, test, fixture, or workbook;
- add a feature flag or legacy/unified toggle;
- expose solver selection or change the default solver;
- change Contract V1, schemas, template fields, route corpus, or solver behavior;
- declare Milestone 5 complete;
- begin Milestone 5C2, 5C3, or V1-A1;
- revive cancelled Phase B architecture; or
- approve an operating timetable, ridership forecast, solver quality, or deployment.

## 17. Assumptions

- The future 5C1 PR is the formal review vehicle; this branch commit alone is not a merge or
  production approval.
- “Two production release cycles” uses the repository's normal release cadence. If no formal
  cadence exists, the 90-day minimum controls.
- Source workbooks remain user-controlled and are not uploaded into offline corpus evidence.
- A deployable previous release artifact and database/session compatibility are available for
  rollback; 5C2 must verify this before retirement approval.
- The default `HEURISTIC` adapter remains approved during runtime retirement even though it uses
  shared legacy-origin implementation code.
- The current generated template remains the canonical migration destination.

## 18. Unresolved product questions

These questions do not change the selected target, but named answers are required before final
retirement approval:

1. Who are the named Product Owner, Engineering Owner, and QA/Release Owner?
2. What release identifier and date start the 90-day compatibility clock?
3. Where will user-facing migration instructions be published and supported?
4. Is a B-only download desirable after a solver infrastructure failure, or should all downloads
   remain disabled as recommended?
5. What storage location and retention period will hold release comparison packages?
6. Must the legacy oracle remain executable after two clean release audits, or are immutable
   snapshots sufficient?
7. Will the default heuristic internals be rehomed into Contract-owned modules in 5C3 or a later
   separately authorized milestone?
8. What operational thresholds, if any, supplement the deterministic release blockers without
   turning non-comparable legacy facts into authority?

## 19. Approval record

| Decision | Required approver | Status | Evidence/event |
|---|---|---|---|
| Select Option C target | Product Owner and Engineering Owner | Pending formal review | Merge of future `Milestone 5C1: Define legacy runtime retirement gate` PR |
| Accept offline side-by-side disposition | Engineering Owner and QA/Release Owner | Pending formal review | Reviewed CI/release audit design |
| Begin 5C2 implementation | Engineering Owner | Not started | Approved 5C1 PR |
| Declare `LEGACY_RUNTIME_RETIRED` | Product, Engineering, and QA/Release owners | Not approved | Section 13 package, rollback rehearsal, no blockers |
| Begin broad 5C3 deletion | Engineering Owner | Not approved | `LEGACY_RUNTIME_RETIRED` recorded |
| Declare `LEGACY_CODE_DELETED` | Product, Engineering, and QA/Release owners | Not approved | Production-import audit and full regression evidence |

No approver names were available in the repository or task brief. They must be added during
review; this document does not fabricate approval identities.
