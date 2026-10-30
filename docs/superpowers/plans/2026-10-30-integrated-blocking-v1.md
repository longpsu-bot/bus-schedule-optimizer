# Fixed-timetable integrated blocking V1 implementation plan

> Execute inline with `superpowers:executing-plans`; obtain independent technical reviews before implementation and before pushing. User approval is the conditional implementation request, not an additional approval gate.

**Goal:** Independently executable fixed-team vehicle blocks for the 102 frozen P0 trips, with honest global proof bounds.

**Architecture:** A separate strict request/witness validator reconstructs all intervals without importing the solver. A complete trip-DAG CP-SAT model propagates duty, driving and protected-rest/meal coverage. Additive JSON/XLSX reporting and a thin Route 10 CLI leave all existing recommendation/compiler/scoring modules unchanged.

**Tech stack:** Installed Python, OR-Tools 9.15.6755, openpyxl (explicitly requested by the approved specification); no new dependency.

**Spec:** `docs/engine/INTEGRATED_VEHICLE_CREW_BLOCKING_V1.md`, as corrected by the PO request dated 30 October 2026.

## Global constraints

- q=h=p=5; q only internally, final tasks h only.
- One unique synchronized driver/attendant pair and vehicle per block; no reuse/relief/depot/deadheading.
- Sustained meal eligibility D>=360 and overlap>=60; lunch 660–840 and dinner 1020–1200, 30 continuous minutes each.
- Independently require 30 continuous protected minutes when D>=360; one physical union can satisfy several rules.
- Duty 480/600 separately; continuous driving 240 and protected reset 30; total driving <=H is only a redundant experimental rule.
- Exactly four primary p50/p75 × 480/600 experiments; no inherited 14 ceiling.
- Preserve all three source/departure hashes, frozen input bytes and old contracts; never operate on PR #63.
- Fixed seed, one worker, bounded search, retain strongest independently validated incumbent. UNKNOWN never proves infeasibility.

## Task 1: Correct and independently review the specification

Files: modify the specification above; this plan records progress and decisions.

- [x] Correct final duty to arrival+h and bound to ceil((W+1530)/(H+5)).
- [x] Add general-rest requirement, sharing and experimental authority.
- [x] Read independent review; corrected validator/report/general-rest fixture coverage and frozen-policy wording before implementation.
- [x] Existing focused baseline: 94 passed / 1 private-input skip (95 collected); outputs/integrated_v1_baseline.log.

## Task 2: Strict input and independent witness validator FIRST

Files: create `src/bus_schedule_engine/mvp/integrated_blocking_validation.py` and `tests/test_integrated_blocking_validation.py`.

Interface: `validate_request(request)->dict`; `validate_assignment(request, blocks)->dict` raises ValueError for invalid input/witness and returns independently reconstructed block metrics, physical assignment and inventory.

- [x] Write hand-built valid witnesses and mutations: endpoint q exclusion, duties/recovery/rest disjointness, meals/general/reset sharing, duplicate/missing trips and reused identities, same-direction/late edges, false arrivals, stock and explicit policy fields.
- [x] Run `python -m pytest tests/test_integrated_blocking_validation.py` and inspect expected missing-feature failure.
- [x] Implement strict versioned contract and independent reconstruction, runtime half-open lookup via existing input module, exact physical validation via existing circulation module.
- [x] Re-run validator tests successfully BEFORE writing solver code.

## Task 3: Complete compact solver and proof retention

Files: create `src/bus_schedule_engine/mvp/integrated_blocking.py`, `tests/test_integrated_blocking.py`.

Interface: `solve_integrated(request, *, incumbent=None, checkpoint=None, cancelled=None)->dict`; source request remains unchanged; incumbents always independently validated.

- [x] Write synthetic T1–T16 regressions and small exhaustive path/partition oracle with independent literal interval arithmetic. Include forced-cutoff incumbent and global-bound checks.
- [x] Observe failures, implement full DAG flow, reified duty/exposure/meal/rest states, stock/cap checks and max-flow/matching relaxation certificate.
- [x] Deterministic bounded CP-SAT, callback validation, monotone incumbent, atomic request-keyed checkpoint and conservative bounds/statuses. Record model/response digests and versions.
- [x] Run both new suites; compare exact tiny answers and crew-disabled matching independently.

## Task 4: Add reports, pinned source adapter and CLI

Files: create `src/bus_schedule_engine/mvp/integrated_blocking_report.py`, `scripts/run_route10_integrated_blocking.py`, `tests/test_integrated_blocking_report.py`.

Interfaces: `route10_requests(workbook, evidence)->list[dict]`; `export_report(request, result, output_dir)->dict`; CLI accepts private input/evidence/output paths.

- [x] Test report round-trip three tables, frozen identity/hash rejection, source/output collision and blank assignments for no incumbent.
- [x] Implement three native Excel tables with linked block/connection/rest detail rows and typed numeric values, inspectable JSON and exact physical assignment.
- [x] Revalidate original workbook-derived runtime profiles against SHA-locked frozen evidence without timetable search. Keep evidence and generated files ignored.
- [x] Run exactly four primary scenarios under predeclared budgets; independently validate each retained witness and archive exact assignments, proof certificates and elapsed work.

## Task 5: Review, regression and publication to pilot branch

- [x] Independent fresh-context code review; address material findings with reproducing tests.
- [x] Run focused new and existing regression groups with private source variables; lint, format, source hash and unchanged-module checks.
- [x] Verify saved workbook values and legibility; repeat deterministic solver verification on synthetic cases (real primary cases run once each).
- [x] Write concise four-case evidence report, include assumptions of old 14/16 models and unresolved operator authority.
- [x] Prepare validated changes for the authorized pilot-branch commit/push; the final chat records the resulting remote HEAD and clean-worktree verification. Do not open a PR.

## Execution ledger

- Initial worktree clean at `449e3f45928449682a23f7cf06ce835ecf9b5afe`; unrelated original workspace left untouched.
- PO request fully supplies design approval and experimental policies; proceed inline without repeated permission.
- Specification review dispatched before implementation. Existing baseline runs in ignored outputs.

- Task 2 complete: 33 initial hand-built validator tests passed before solver code; expanded to 39 later. First failure exposed Counter(mapping) semantics; fixed coverage to Counter(mapping.keys()).
- Task 3 complete: full-DAG solver, exact small independent enumeration, cutoff/checkpoint tests passed. Combined new suites before primary runs: 64 passed, 1 private adapter skip; adapter separately passed with private inputs.
- Ruling: explicitly protect each entire connection free interval — independently reviewed dominance proof in spec §6.6; selected protected minutes/work-exposure proxy differ, duty and feasible path set unchanged. No residual-recovery secondary objective.
- Task 4 primary experiments started once each in outputs/integrated_v1_primary under 10 deterministic / 60 wall seconds per case, 300 global wall seconds. Independent implementation review in progress.

- Task 4 complete: exactly four primary solves, bounds/validated counts 26–41,21–36,27–44,22–36; primary pipeline88.658 seconds. All saved witnesses revalidated under final code; hashes unchanged; all three workbook sheets rendered and values checked.
- Task 5 verification: focused suite186passed/4older-private-input skips in379.31s; final fresh new suites73passed in8.32s. Ruff lint/format and diff whitespace pass.
- Final review: fresh independent reviewer found no mathematical issue after500 randomized small exact oracle comparisons and four independent saved-witness checks. Boundary findings (staging paths including alias/hardlink resolution, oversized integers, malformed checkpoint/witness) fixed with RED→GREEN regressions. Additional checkpoint I/O retention regression passed. Windows file-symlink creation unavailable; resolver-boundary reproduction plus actual hardlink/direct-path tests passed. No material findings remain.
- No secondary optimization or feedback planning added; protected whole free intervals are a declared scheduling commitment. Actual operator/legal authority remains unverified. Final verdict FEASIBLE_BUT_UNPROVED.
