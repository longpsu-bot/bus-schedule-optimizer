# Peak/off-peak deployment pilot — Phase 1 and Phase 2

**Goal:** Measure terminal-only fleet deployment and fixed-crew meal opportunities without changing frozen P0 or building a new optimizer.

**Spec:** Product Owner's approved Phase 1–2 brief, supplied 28/10/2026.

**Architecture:** Add an event reconstruction module over existing exact vehicle chains; add a private Route 10 experiment runner using `compile_plan`, `assign_fleet`, independent `audit_fleet`, `compare_timetable` and `analyze_chains`. Add a CLI, standalone synthetic tests and reproduction documentation. No existing production caller, fixture, compiler, assignment, selection or expected value changes.

**Constraints:** 102 trips; fixed endpoints; integer uniform meaningful regimes; 14-vehicle primary ceiling; separately labeled 15-vehicle chain-split sensitivity; one crew per full chain; terminal-only stock; unknown parking authority; no relief/depot movement; no operational or legal approval. Keep sources and generated route evidence ignored. Commit/push validated code to existing pilot branch; no PR or merge.

- [x] Inspect branch/worktrees; fast-forward clean pilot branch to expected `8982dca`; verify workbook and frozen MVP-6A hashes and PR #63 state.
- [x] Write synthetic event/meal/recovery tests and observe failure; implement exact half-open state intervals, ordered event audit and duration-weighted 15-minute reporting.
- [x] Verify frozen acceptance locks; author P1/P2 directional plans from demand; compile exactly once per authored direction and disclose family failures. Evaluate unchanged departures under nominal, fixed p75 and exact p75 reassignment.
- [x] Evaluate declared 8/6 stock using existing constrained assignment; assess explicit 15th-vehicle splits with terminal origins and full-chain crew policy.
- [x] Export deterministic JSON/CSV, Vietnamese report and offline utilization/inventory/vehicle timelines. Verify source traceability and repeat hashes.
- [x] Independent review of code and private acceptance evidence; resolve findings and run focused/MVP regressions, Ruff and formatting.
- [x] Record local validation, preserve P0/source hashes and unrelated changes, verify remote base and unchanged PR #63. Integrate only validated pilot files on the existing branch, then stop.

## Validation ledger

Initial workbook SHA-256: `8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b`.

Frozen MVP-6A SHA-256: `1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3`.

Initial PR #63: draft/open, unmerged, head `e9fe4eb92c785748d939d44c6386c005d5d9cd3c`.

- Final focused/private acceptance: **22 passed**, 16.84 seconds. Standalone mode: **21 passed, one private-input skip**. Synthetic cases include equal-minute arrivals before another vehicle's departure, different morning/evening concurrent counts, first preparation versus readiness, true continuous meals, crew-compatible reactivation, no double-counted traffic reserve, actual assigned passenger crossings, zero-demand unknown waits and workbook/evidence/policy output collisions.
- Selected broader MVP/crew/compiler/settlement/joint/fleet-feedback/review/Route10/import/benchmark regression completed without failures; six existing opt-in/private-case skips. The two final collision tests were added afterward and passed in the final focused run. Frozen Route10 input was enabled for the new acceptance.
- Whole-repository Ruff passed. CI Contract V1 source/tests plus all six new Python files passed formatting: **65 files**. No existing engine source, original workbook, timetable, fixture or expected value changed.
- All six main private exports are byte-identical between `outputs/peak_offpeak/` and `outputs/peak_offpeak_repeat/`. All three normalized analysis-code fingerprints match the final files. Authoritative source hashes and full frozen P0 object are unchanged.
- Independent reviewer ran **115 tests** with private inputs, then final boundary/collision checks. A separate arithmetic sweep, without importing pilot calculations, verified source identity, exact matching minima, physical locations, meal/recovery intervals, deployment leads and CSV duration integrals. Detailed private review evidence stays under ignored `outputs/reviewer_peak/`.
- Review-specific fixes cover initial predeparture tasks/readiness, zero-demand missing values, meal-compatible reactivation, actual assigned peak arrivals, configurable policy prose/key ordering, and protection of every source file from export collisions. Relevant regressions demonstrated failure before correction.
- Vietnamese report copy validator: **zero errors and zero warnings**. Offline browser inspection verified utilization, both terminal inventories, vehicle timelines with hour ticks, and explicit rejection labels for over-ceiling plans. All displayed data remains private and local.
- Operational outcome: **PARTIAL_EVIDENCE**, with `NO_OPERATIONALLY_ACCEPTABLE_CANDIDATE_FOUND_WITHIN_PILOT`. This is not global infeasibility, operational approval, or a legal-compliance finding. No Phase 3, general deployment solver or PR was introduced.
- Validation is local. The current Actions workflow triggers only `main` pushes/PRs; no GitHub Actions success is claimed for this pilot branch.
