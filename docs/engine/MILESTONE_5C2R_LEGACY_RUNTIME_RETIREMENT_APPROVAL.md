# Milestone 5C2R: Legacy runtime retirement approval evidence

## 1. Decision boundary

Milestone 5C2R prepares deterministic repository evidence for the human production decision
required by Milestones 5C1 and 5C2. It does not make that decision.

The three governing states remain separate:

1. `CUTOVER_COMPLETE`: Contract V1 is the only ordinary Streamlit result authority.
2. `LEGACY_RUNTIME_RETIRED`: the implementation gate has passed and the required owners have
   formally approved production retirement.
3. `LEGACY_CODE_DELETED`: an authorized later Milestone 5C3 change has removed eligible code.

This audit concludes `READY_FOR_FORMAL_APPROVAL` when every repository implementation check
passes. Production approval remains `PENDING`. No 5C3 deletion is performed or authorized by
this document.

## 2. Governing sources and commits

The authoritative implementation baseline is
`f4971c0d6255d69f5ee3135f083b5637e85ffd86`, the merged Milestone 6A2D commit. It contains the
merged 5C1 and 5C2 runtime decisions plus Milestones 6A1 through 6A2D.

The audited target is the exact draft-PR head supplied to
`python -m bus_schedule_engine.legacy_retirement_audit --target-commit ...`. The audit records
that full commit in `audited_target_commit` and fails with `M5C2R_TARGET_COMMIT_MISMATCH` unless
it equals the inspected checkout's `HEAD`. This avoids a self-referential commit SHA inside the
commit that creates this document while still binding every generated approval package to an
exact target.

The governing documents are:

- `docs/engine/MILESTONE_5C1_LEGACY_RUNTIME_RETIREMENT_DECISION.md`;
- `docs/engine/MILESTONE_5C2_UNIFIED_FIRST_RUNTIME.md`;
- `docs/engine/MILESTONE_6A1_TRIP_RIDERSHIP_ANALYSIS.md`;
- `docs/engine/MILESTONE_6A2A_PROTECTED_SERVICE_FLOOR_AUTHORITY.md`;
- `docs/engine/MILESTONE_6A2B_PROTECTED_SERVICE_FLOOR_ACCEPTANCE_ENFORCEMENT.md`;
- `docs/engine/MILESTONE_6A2C_PROTECTED_SERVICE_FLOOR_HEURISTIC_SEARCH.md`; and
- `docs/engine/MILESTONE_6A2D_PROTECTED_SERVICE_FLOOR_ORTOOLS_CONSTRAINTS.md`.

## 3. Deterministic approval package

The frozen, slotted evidence model uses profile
`m5c2r_legacy_runtime_retirement_approval_evidence_v1`. Its canonical fingerprint payload has no
wall-clock time. JSON keys, blocker codes, warning codes, inventory entries, candidates, shared
dependencies, runtime roots, and evidence references are deterministically ordered. The report
fingerprint is SHA-256 over the compact canonical JSON with only `report_fingerprint` omitted.

Generate the package from the repository root:

```powershell
python -m bus_schedule_engine.legacy_retirement_audit `
  --target-commit <exact-current-HEAD> `
  --output legacy-runtime-retirement-evidence.json
```

The command reads only repository source, documentation, test names, and local Git metadata. It
does not start Streamlit, run either analysis implementation, read a production workbook, use the
network, or change application files. It returns zero only for
`READY_FOR_FORMAL_APPROVAL`; any collected blocker returns nonzero. The requested JSON output is
the command's only write.

The report also binds a deterministic source-tree fingerprint covering the audited Python,
Streamlit, test, README, and governing-document inputs. A dirty tree is recorded as a warning so
that the final review package can require a clean committed target without making focused tests
depend on repository staging state.

## 4. Implementation-gate evidence

| Gate | Evidence and conclusion |
| --- | --- |
| Ordinary runtime | AST inspection of `streamlit_app.py` and Pages 01–05 finds one analysis entry point: `run_unified_application_pipeline_v1`. No ordinary import or reachable call uses legacy analysis, the parallel adapter, side-by-side comparison, legacy chart/export builders, or `AnalysisBundle` result authority. |
| Readiness and import failure | The unified pipeline assesses readiness before normalization or analysis. Existing behavioral tests prove import-invalid input never enters the pipeline and not-ready input returns readiness facts only. |
| Fail-closed behavior | Normalization, evaluation, solver, presentation, semantic-integrity, and artifact failures retain Contract V1 failure semantics. The reachable unified call closure contains no legacy fallback entry point. |
| Completed outcomes | Candidate rejection remains a completed no-authoritative-C result. `SolverChoice.BOTH` retains one accepted authoritative C when another candidate is rejected. |
| Visible authority | `VisibleResultModeV1` contains only `NO_RESULT`, `INPUT_NOT_READY`, `UNIFIED_CONTRACT_V1`, `UNIFIED_ARTIFACT_FAILED`, and `CONTRACT_V1_FAILED`; Pages 02–05 reference no legacy mode. |
| Page 05 | Only `Bus_Schedule_Contract_V1_Result.xlsx`, `Bus_Schedule_Contract_V1_Charts.html`, and `Bus_Schedule_Contract_V1_Overview.png` are exposed. |
| Session state | Ordinary code neither reads nor writes retired result keys. Startup and result clearing may remove stale values with `pop(..., None)`. |
| Offline oracle | `release_audit` alone imports the side-by-side adapter. Its fixed source-identity time, sorted JSON, bounded comparison fields, prohibited-content exclusion, and nonzero blocker exit remain characterized. |
| Post-5C2 regressions | The ordinary pipeline derives 6A1 evidence, builds 6A2A assessment and 6A2B authority, then passes that authority through the unified heuristic or OR-Tools boundary. 6A2C filtering and 6A2D constraints remain native Contract V1 search behavior with common validation final. |
| Characterization | The audit checks for the required runtime, UI, authority, Page 05, release-oracle, mixed-solver, route, and protected-floor test nodes before allowing a ready conclusion. |

The draft PR must include the final CLI output and validation results. A zero exit and no blocker
means only that the implementation is ready to be reviewed for formal approval.

## 5. Stable blocker codes

The audit collects every applicable blocker and sorts the codes; it never stops after the first
finding.

| Code | Definition |
| --- | --- |
| `M5C2R_ORDINARY_RUNTIME_LEGACY_ANALYSIS_REACHABLE` | An ordinary root imports or calls legacy analysis or the parallel application entry point. |
| `M5C2R_ORDINARY_RUNTIME_LEGACY_ARTIFACT_REACHABLE` | An ordinary root can build a legacy chart, image, HTML file, or workbook result artifact. |
| `M5C2R_ORDINARY_RUNTIME_SIDE_BY_SIDE_REACHABLE` | Per-submission side-by-side comparison is reachable. |
| `M5C2R_LEGACY_FALLBACK_REACHABLE` | A visible authority or page retains a legacy fallback mode. |
| `M5C2R_LEGACY_RESULT_STATE_AUTHORITATIVE` | A retired result key or `AnalysisBundle` is read, written, or treated as visible authority. |
| `M5C2R_PAGE05_LEGACY_DOWNLOAD_REACHABLE` | Page 05 exposes anything outside the three approved Contract V1 files or calls a legacy artifact builder. |
| `M5C2R_RELEASE_AUDIT_REACHABLE_FROM_ORDINARY_RUNTIME` | The offline release audit enters the ordinary import graph. |
| `M5C2R_OFFLINE_EVIDENCE_NONDETERMINISTIC` | Fixed identity time, sorted serialization, bounded fields, blocker exit, or network isolation is not proven. |
| `M5C2R_OFFLINE_EVIDENCE_PROHIBITED_DATA` | A prohibited source-content field is present in offline output. |
| `M5C2R_SHARED_DEPENDENCY_MARKED_FOR_DELETION` | A current production dependency is absent from the must-remain classification. |
| `M5C2R_RUNTIME_FAILURE_LEGACY_FALLBACK` | A Contract V1 failure can substitute a legacy result. |
| `M5C2R_INCOMPLETE_READINESS_RUNS_ANALYSIS` | Analysis can occur before the not-ready return. |
| `M5C2R_REQUIRED_CHARACTERIZATION_COVERAGE_MISSING` | A required behavioral or protected-floor characterization test is missing. |
| `M5C2R_TARGET_COMMIT_MISMATCH` | The supplied target is not a full SHA equal to inspected `HEAD`. |
| `M5C2R_GOVERNING_DOCUMENT_MISSING` | An authoritative 5C or 6A document is absent. |
| `M5C2R_DEPENDENCY_INVENTORY_STALE` | An inventoried retained target no longer exists at the audited checkout. |

## 6. Warning codes

Warnings do not change the implementation conclusion, but must be resolved or explicitly
accepted during the human event.

| Code | Definition |
| --- | --- |
| `M5C2R_APPROVER_IDENTITIES_PENDING` | No approver names were supplied; the audit does not invent them. |
| `M5C2R_PRODUCTION_APPROVAL_PENDING` | The implementation report cannot approve production retirement. |
| `M5C2R_ROLLBACK_REHEARSAL_CONFIRMATION_PENDING` | QA/Release review must confirm deployable rollback and rehearsal evidence. |
| `M5C2R_WORKTREE_HAS_UNCOMMITTED_CHANGES` | The inspected source tree differs from committed `HEAD`; regenerate the final package after committing. |

## 7. Offline-oracle boundary

The retained oracle remains available only through explicit offline or test workflows:

- `python -m bus_schedule_engine.release_audit`;
- `side_by_side_validation.run_side_by_side_validation_v1`;
- legacy service regression tests; and
- anonymized route-corpus and deterministic regression fixtures.

The release report contains hashes, solver choice, readiness, classifications, stable codes, and
available fingerprints. It excludes source records, binary workbook content, sensitive
individual-level evidence, comparison values, and machine-local absolute locations. A blocker
returns nonzero. Nothing in this boundary is a feature flag, hidden Streamlit route, or product
fallback.

## 8. Retained shared dependencies

The following current production dependencies must remain. They may be rehomed only through a
separately reviewed change that preserves Contract V1 behavior:

- `c_config.py::ScenarioCConfig`;
- `c_generator.py` as a module, including `generate_scenario_c`, `_balanced_values`,
  `_material_boundaries`, `_regime_drafts`,
  `build_heuristic_protected_floor_search_projection_v1`, and
  `validate_heuristic_protected_floor_search_projection_v1`;
- `demand.py` and `demand.py::evaluate_scenario`;
- `fleet.py::assign_fleet`;
- `validator.py::validate_schedule`;
- `models.py::Trip`, `models.py::ScenarioParameters`, and
  `models.py::ProtectedServiceFloorEnforcementAuthorityV1`; and
- the 6A2B enforcement and 6A2D protected-floor modules used by the unified solvers.

The whole `models.py`, `ui_utils.py`, and `excel_exporter.py` files are blocked from deletion
because each contains current production dependencies. In particular,
`excel_exporter.py::create_input_template` and the Page 01 input helpers remain required.

## 9. Exact proposed Milestone 5C3 deletion scope

If and only if production retirement is formally approved, a separate 5C3 change may propose
deleting these audited legacy-only targets and updating their tests and exports:

- `scripts/build_sample_artifacts.py`;
- `application_pipeline.py::ParallelApplicationRunV1`;
- `application_pipeline.py::ParallelRuntimeStatusV1`;
- `application_pipeline.py::_failed_shadow_run`;
- `application_pipeline.py::build_side_by_side_validation_report_v1` (the compatibility
  wrapper, not the offline implementation);
- `application_pipeline.py::run_and_build_artifacts`;
- `application_pipeline.py::run_parallel_application_pipeline_v1`;
- `block_supply.py`;
- `comparison_exporter.py`;
- `diagram.py`;
- `excel_exporter.py::export_results` only, while retaining template creation;
- `ui_utils.py::run_and_build_artifacts`;
- `ui_utils.py::validation_frame`;
- `ui_utils.py::block_frame`;
- `ui_utils.py::scenario_frame`;
- `ui_utils.py::supply_summary_frame`; and
- `ui_utils.py::regime_frame`.

This is a proposed symbol/file scope for a later reviewed change, not a deletion performed here.
The release-audit CLI, side-by-side adapter, `service.py::run_analysis`, legacy comparison result
models, and their required oracle dependencies remain outside this proposed scope while the
offline oracle is required.

## 10. Rollback boundary

Rollback remains a deployment of the last known-good complete pre-retirement application
release, with evidence from the offline audit reviewed before rollback. There is no runtime
legacy/unified toggle, feature flag, within-request legacy retry, or partial artifact fallback.

Before approving retirement, the QA/Release Owner must confirm the rollback artifact is
deployable, session/input compatibility is understood, the rehearsal evidence is retained, and
the rollback does not mix authorities within one request.

## 11. Required human sign-offs

| Role | Required decision | Status |
| --- | --- | --- |
| Engineering Owner | Approve production legacy-runtime retirement | PENDING |
| QA/Release Owner | Approve evidence and rollback readiness | PENDING |

No names or decisions were supplied. This document records no approval on behalf of either role.
Production approval is explicitly `PENDING`, even when the implementation conclusion is
`READY_FOR_FORMAL_APPROVAL`.

