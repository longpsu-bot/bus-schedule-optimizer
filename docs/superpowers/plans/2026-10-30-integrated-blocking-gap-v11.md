# Integrated blocking V1.1 controlled experiment

> Execute inline. The PO's detailed conditional implementation request authorizes this plan; request one independent technical review before pushing.

**Goal:** Distinguish weak feasible-assignment construction from weak lower-bound proofs on the frozen P0 timetable.

**Architecture:** Preserve the legacy greedy seed and its existing objective cutoff. Add one bounded rest-aware seed, independently validate it, and use it only as a hint and retained upper bound. Observe the original CP-SAT callbacks without changing the model, objective, parameters or independent validator.

**Tech stack:** Existing Python, OR-Tools 9.15.6755, pytest and Ruff. No dependencies.

**Spec:** Product Owner's “INTEGRATED BLOCKING V1.1: OPTIMALITY GAP REVIEW” request in this chat, and `docs/engine/INTEGRATED_VEHICLE_CREW_BLOCKING_V1.md` for unchanged operational semantics.

## Frozen scope

- Start `98427b194d63a077f3e3ca7ac6e3d73cf98cf93f`, pilot branch only; no new PR, no merge, preserve Draft PR #63.
- Preserve all 102 departures, source/runtime/policy hashes and four original validated assignments under `outputs/integrated_v1_primary`.
- One worker, seed 0, ten deterministic seconds, sixty wall seconds, 1024 MB and complete DAG unchanged.
- Production constraints, duty/meal/reset rules, objective, solver interfaces and timetable optimizer unchanged.
- Explicitly label relaxed requests; never promote their bounds as production upper bounds.

## Task 1: Reproduce and instrument the gap

Files: `scripts/review_integrated_blocking_gap.py`; ignored experiment artifacts under `outputs/integrated_gap_v11/`.

- [x] Check clean pilot worktree, SHA, existing witnesses and Draft PR.
- [x] Baseline integrated tests: 72 passed, one private-input skip.
- [x] Trace `_greedy`: cumulative driving cutoff and unconditional 360-minute duty cutoff confirmed by inspection.
- [x] Observe fresh p50/600 and p75/600 runs of the original source. Record initial greedy, first native incumbent, all independently validated rank/fleet improvements and final bound/work.
- [x] Independently revalidate and hash frozen evidence; retain exact intermediate witnesses privately.

## Task 2: One bounded seed correction, test first

Files: modify only `src/bus_schedule_engine/mvp/integrated_blocking.py`; extend `tests/test_integrated_blocking.py` and experiment tests.

- [x] RED: synthetic two-trip duty 480–885 with 180+180 driving and protected 670–700 break must use one seed block versus two legacy blocks. Check literal exact-partition oracle and independent validator.
- [x] Add chronological rest-aware candidate extensions using every compatible DAG edge, continuous resets, elapsed/total limits, general rest and own-window meal eligibility. Deterministically bound to the existing trip/chain scan; no retries, extra search or edge pruning.
- [x] Validate complete proposed seed through `retain`; preserve legacy seed/cutoff, supply best validated seed only as hints.
- [x] GREEN: exact-oracle, meal/reset/threshold, invalid-seed fallback and unchanged constraint-fingerprint regressions.

## Task 3: Controlled measurements and constraint analysis

Files: experiment runner above, `docs/engine/INTEGRATED_BLOCKING_V11_GAP_REVIEW.md`, compact evidence JSON.

- [x] Fresh same-budget p50/600 and p75/600 after correction; compare exact constraint fingerprints with baseline.
- [x] Explicit relaxed staircase: technical only; terminal tasks; elapsed duty (total driving cap retained, redundant); continuous driving/reset; general rest; lunch; dinner/full. Also leave-one-out checks of general/lunch/dinner and driving, with exact witnesses validated under each labeled request.
- [x] Compare known relaxed optima or nonoverlapping certified bounds only; otherwise report effect unresolved. Revalidate relaxed assignments against full policy to identify witness-specific failures without claiming a fleet minimum.
- [x] Only if the 600-minute results improve or clarify search, run original/corrected p50/480 and p75/480 at the same budgets.
- [x] Report requested before/after metrics, full fleet-incumbent sequences, proof limitations and one PO verdict. No extra heuristic or budget increase.

## Task 4: Review, verify, deliver and stop

- [x] Exact-oracle tests, all integrated tests with private inputs, relevant pilot/crew/circulation/optimizer regressions, Ruff lint/format and `git diff --check`.
- [x] Fresh independent technical review of code, trace validity, mathematical claims, fixed constraints and frozen evidence.
- [x] Resolve material findings with reproducing tests; rerun affected checks. No actionable findings.
- [ ] Commit only validated code/tests/compact documentation and push to the existing pilot branch; verify remote and Draft PR state. Stop.

## Decisions

- Preserve the original greedy bound in the model rather than tightening it with the new heuristic. This keeps the constraint system identical across the controlled before/after pair; only hints and independently retained witnesses change.
- Private inputs and complete witness traces remain ignored. Publish compact numeric evidence, hashes and reproducible commands without source workbook contents.
- The independent reset-workload certificate strengthens necessary bounds without changing native solver bounds or adding model constraints. General-rest redundancy is proved only for these frozen runtimes/tasks/reserves and whole-interval protection.

## Verification ledger

- Main seed regressions: five expected RED failures before implementation, then five GREEN passes.
- Before/after requests and no-hint constraint SHA-256 values match in all four pairs.
- Relevant regressions: 202 passed / 4 documented older private-acceptance skips, 419.61 seconds.
- Final integrated suites after diagnostic certificate: 83 passed / 0 skips, 8.44 seconds.
- Repository lint, changed-file and Contract V1 format, diff whitespace checks passed.
- Independent reviewer: 35 synthetic tests; 28 results / 203 event witnesses / 10 frozen file hashes checked; no actionable findings; approved to commit and push.
