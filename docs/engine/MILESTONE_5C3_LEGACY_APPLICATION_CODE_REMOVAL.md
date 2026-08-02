# Milestone 5C3: Retired legacy application code removal

## 1. Authorization and completion semantics

On 2 August 2026, the user explicitly instructed: **“Proceed and remove the legacy.”** This is
the authorization that commenced the bounded Milestone 5C3 removal. No approver names were
provided, none are invented here, and no rollback rehearsal is claimed.

The honest post-change state is:

`RETIRED_LEGACY_APPLICATION_CODE_REMOVED`

This is not an unrestricted `LEGACY_CODE_DELETED` claim. The explicit offline regression oracle,
legacy comparison models, and legacy-originated code that remains a shared Contract V1 production
dependency are intentionally retained.

## 2. Baseline and preserved pre-deletion evidence

The source boundary is the merged `main` commit
`45b49791b1be734b89271e5700e8eeeb64deb2d4` (`Milestone 5C2R: Prepare legacy runtime retirement
approval evidence`). Before source deletion, the 5C2R CLI was run at that exact clean checkout:

```text
python -m bus_schedule_engine.legacy_retirement_audit \
  --target-commit 45b49791b1be734b89271e5700e8eeeb64deb2d4 \
  --output legacy-runtime-retirement-evidence.json
```

It exited zero with `READY_FOR_FORMAL_APPROVAL`, recorded the exact target commit, retained
historical production approval as `PENDING`, and retained the pending approver-identity and
rollback-rehearsal warnings. The exact bytes are archived at
[`evidence/M5C2R_LEGACY_RUNTIME_RETIREMENT_EVIDENCE_45B49791.json`](evidence/M5C2R_LEGACY_RUNTIME_RETIREMENT_EVIDENCE_45B49791.json).

- Report fingerprint: `2ab6efe216bfd7c3e6341fb29a1b459d739ac72a9e84e42816887e86bcbd417b`
- Archived-file SHA-256: `fe972418873dc8b141561b9fe0719b549efc087b977c61395bcb65570f475045`
- Fingerprint verification: passed before deletion and is exercised against the archived file
  after deletion.

The archive describes the pre-deletion approval baseline. The original 5C2R CLI is not made to
reinterpret the post-deletion checkout as if its authorized candidates still existed.

## 3. Exact removal scope

Complete files removed:

- `scripts/build_sample_artifacts.py`
- `src/bus_schedule_engine/block_supply.py`
- `src/bus_schedule_engine/comparison_exporter.py`
- `src/bus_schedule_engine/diagram.py`

Symbols removed from `application_pipeline.py`:

- `ParallelRuntimeStatusV1`
- `ParallelApplicationRunV1`
- `run_and_build_artifacts`
- the compatibility wrapper `build_side_by_side_validation_report_v1`
- `_failed_shadow_run`
- `run_parallel_application_pipeline_v1`
- `UNIFIED_SHADOW_RUNTIME_FAILURE`

Only imports used by that compatibility surface were removed: `AnalysisBundle`, the
`SideBySideValidationReportV1` type-checking alias, legacy-only `TYPE_CHECKING` logic,
`analyze_and_optimize_schedule_v1`, and `build_unified_presentation_v1`. The unified application
models, pipeline, readiness-first sequence, failure handling, protected-floor flow,
presentation, figures, XLSX, and Page 05 behavior were not changed.

Symbols removed from `ui_utils.py`:

- `run_and_build_artifacts`
- `validation_frame`
- `block_frame`
- `scenario_frame`
- `supply_summary_frame`
- `regime_frame`

`workbook_sheet_names`, `preview_sheet`, `apply_overrides`, and `template_bytes` remain.

Symbols and exclusive result-formatting code removed from `excel_exporter.py`:

- `export_results`
- `_peak_and_offpeak_headway`
- `_write_result_schedule_sheet`
- the legacy result-workbook sheets, formulas, conditional formatting, scoring-config reads, and
  result-only imports owned exclusively by `export_results`

`create_input_template` and every helper, label, example, formula, validation, sheet, and style it
uses remain in place.

## 4. Package boundary

Direct package imports and `__all__` entries were removed for:

- `ParallelApplicationRunV1`
- `ParallelRuntimeStatusV1`
- `run_parallel_application_pipeline_v1`
- `UNIFIED_SHADOW_RUNTIME_FAILURE`

The package does not silently replace those names; normal attribute import fails. The lazy
offline exports remain intact, including `run_side_by_side_validation_v1`, the real
`build_side_by_side_validation_report_v1`, `SideBySideValidationReportV1`, and
`LegacyPathSnapshotV1`. `AnalysisBundle` also remains exported for the oracle.

## 5. Retained offline regression oracle

The retained explicit offline boundary is:

- `src/bus_schedule_engine/release_audit.py`
- `src/bus_schedule_engine/side_by_side_validation.py`
- `src/bus_schedule_engine/service.py::run_analysis`
- `src/bus_schedule_engine/models.py` comparison result models, including `AnalysisBundle`
- `src/bus_schedule_engine/generator.py`
- `src/bus_schedule_engine/comparator.py`
- `src/bus_schedule_engine/fingerprint.py` where required by retained snapshots
- the anonymized route corpus and its characterization tests

The release-audit CLI and side-by-side adapter continue to execute legacy analysis explicitly,
but do not depend on the deleted chart, PNG, HTML, application artifact, comparison-XLSX, or
legacy result-XLSX code. No ordinary Streamlit module imports or invokes this boundary.

## 6. Retained shared production dependencies

The following remain without semantic change because Contract V1 or the input path still uses
them:

- `c_config.py::ScenarioCConfig`
- `c_generator.py`, including `generate_scenario_c`, `_balanced_values`,
  `_material_boundaries`, `_regime_drafts`, and the 6A2C protected-floor projection functions
- `demand.py` and `demand.evaluate_scenario`
- `fleet.assign_fleet`
- `validator.validate_schedule`
- `models.py::Trip`, `models.py::ScenarioParameters`, and protected-service-floor authority models
- the 6A2B enforcement code
- the 6A2D OR-Tools protected-floor code
- `ui_utils.py` for Page 01 preparation and preview
- `excel_exporter.py::create_input_template`

Baseline-bound aggregate SHA-256 manifests protect the shared heuristic sources, both protected
solver paths, all Contract schema/example files, and all route-corpus files. They are also covered
by their existing behavioral regression suites.

## 7. Input-template preservation

Before deletion, the existing exporter/import/readiness semantic suites passed **44 tests**. A
normalized workbook-content fingerprint was also recorded over every ZIP member, excluding only
volatile created/modified timestamps in `docProps/core.xml`:

`8b1617679d5755e5fc0aae511f9e5eddc1b5ce4e9016f31222ca0cc6f38b82c2`

The post-deletion focused removal suite regenerates the template and requires the same fingerprint.
The existing exporter, importer, input-authority, Page 01, and normalization suites provide the
semantic proof for sheets, validations, formulas, examples, field names, labels, formatting, and
authoritative-input readiness.

## 8. Test cleanup and replacement

The pre-deletion suite contained 1,304 collected nodes (1,300 passed and four expected skips).
Exactly **72 obsolete test nodes** were removed:

- 20 chart/block-supply nodes from deleting `test_diagram.py` and `test_block_supply.py`;
- 18 parallel application compatibility nodes from `test_application_pipeline.py`;
- two Scenario C chart/comparison-export nodes;
- one side-by-side artifact-monkeypatch node;
- one unified-chart legacy-builder monkeypatch node;
- one unified-XLSX legacy-exporter monkeypatch node; and
- 29 current-checkout 5C2R candidate/graph nodes whose lifecycle ended with the archived
  pre-deletion package.

Ten focused post-deletion nodes were added in `test_legacy_code_removal.py`, and six archived
evidence lifecycle nodes replace the prior current-checkout 5C2R test module. The net collection
is 1,242 nodes, a reduction of 62. Mixed integration and Scenario C tests were rewritten only to
remove artifact expectations; offline `run_analysis`, heuristic behavior, demand evaluation,
fleet assignment, and validation assertions remain.

## 9. Verification layer

The post-deletion checks prove that removed files, modules, definitions, imports, and exports are
absent; package import succeeds; Streamlit is unified-only; stale result keys are clear-only;
Page 05 still exposes exactly three Contract V1 files; the template fingerprint is unchanged;
the release audit and side-by-side adapter work; the service entry point is offline/test-only;
shared heuristic, protected-solver, schema, and corpus manifests are unchanged; and the archived
5C2R fingerprint still verifies.

Final validation results:

- focused removal plus archived-evidence lifecycle: 16 passed;
- application, runtime-cutover, template/import/readiness, integration, release-audit,
  side-by-side, and Scenario C: 131 passed;
- Pages 01–05, visible-result authority, unified presentation, charts, XLSX, and Page 05: 149
  passed;
- heuristic, OR-Tools, protected-floor, schema, and route-corpus regression: 551 passed and four
  expected skips;
- complete suite: 1,238 passed and four expected skips (1,242 collected);
- Ruff repository lint: passed;
- Ruff repository formatting check: 164 files already formatted;
- `git diff --check`: passed; and
- protected shared sources, Contract schemas/examples, and route-corpus paths have no diff from
  `45b49791b1be734b89271e5700e8eeeb64deb2d4`.

The two complete-suite warnings are existing Kaleido `setDaemon()` deprecations from the real PNG
render tests; they do not change results.

## 10. Documentation state

The 5C1, 5C2, and 5C2R documents contain concise status links to this milestone. Historical text
remains historical. The active README now states that retired legacy application/artifact code is
removed, ordinary Streamlit remains Contract V1-only, and the explicit offline oracle remains
intentionally.

## 11. Rollback boundary

The last complete pre-deletion source boundary is:

`45b49791b1be734b89271e5700e8eeeb64deb2d4`

For an unmerged branch, abandon the 5C3 branch and deploy that exact commit. After integration,
create a rollback branch and either revert the 5C3 commit or restore the exact baseline tree for
review:

```powershell
git switch -c rollback/m5c3 45b49791b1be734b89271e5700e8eeeb64deb2d4
```

When history requires a non-destructive inverse commit, use `git revert <5C3-commit-sha>` and
validate the restored application before deployment. No runtime toggle, hidden fallback, or
mixed-authority compatibility path is introduced.

## 12. Remaining legacy-originated code

The retained offline oracle still needs `service.py`, `side_by_side_validation.py`,
`generator.py`, `comparator.py`, legacy comparison models, and their analytical dependencies.
The ordinary Contract V1 heuristic still directly depends on `c_generator.py`, while Contract
headway code uses its balancing/regime helpers; `demand.py`, `fleet.py`, and `validator.py` also
remain shared production dependencies. Removing or rehoming those responsibilities requires a
separate reviewed milestone with solver, schema, corpus, and protected-floor parity evidence.

Therefore the completion statement remains `RETIRED_LEGACY_APPLICATION_CODE_REMOVED`.
