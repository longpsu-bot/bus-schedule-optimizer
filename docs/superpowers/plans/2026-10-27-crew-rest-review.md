# Crew rest and recovery model review

**Goal:** Review frozen Route 10 vehicle chains without changing timetables, optimizer behavior or PR #63.

**Spec:** Product Owner approved brief supplied on 2026-10-27, sections 1–10.

**Architecture:** A read-only analysis module consumes the existing exact fleet structures. A separate Route 10 module and CLI validate the private workbook and frozen MVP-6A JSON, reuses existing runtime/assignment/audit functions, and exports deterministic private JSON and Vietnamese Markdown. No new dependencies or production callers.

**Scope:** Add `mvp/crew_review.py`, `mvp/route10_crew_review.py`, `scripts/review_route10_crew.py`, synthetic tests and a public reproduction/authority note. Existing circulation, compilation, selection, fixtures and exports remain unchanged. Private sources and generated reports stay under ignored `outputs/` or outside Git.

- [x] Verify live branch SHA, dirty checkout ownership, PR #63, private workbook SHA and frozen evidence availability; create a separate managed worktree.
- [x] Establish a clean relevant baseline (87 passed, six private-input skips). Use `PYTHONPATH=src`, `OPENPYXL_LXML=False`, and an ignored explicit pytest base directory to avoid the host's inaccessible default temp root.
- [x] Write failing synthetic tests: technical turnaround versus continuous break, separate waits, explicit tasks/reserve, stress failure versus reassignment, relief without staff proof, unknown assignments, separate roles, invalid/missing policies and deterministic provenance.
- [x] Implement chain metrics, conditional fixed-vehicle and relief opportunities, configurable illustrative policies and strict policy validation. Reserve, technical time, terminal tasks and rest use disjoint modeled intervals. No roster or legal-compliance certificate.
- [x] Validate frozen B/X/C against the SHA-verified workbook and stored chains. Analyze native p50/p75 separately; stress the same p50 departures with both fixed chains and reassignment. Keep recorded X separate.
- [x] Independently reconcile every dwell, exact fleet count and frozen incumbent; verify legal effectiveness and unknown operating date. Export Vietnamese findings A–F plus every-chain/trip annex.
- [x] Obtain independent code/evidence review; fix review-specific findings; run focused/regression tests, Ruff and formatting. Distinguish local checks from Actions.
- [x] Commit only code/tests/public documentation; compare remote SHA before pushing to the existing target branch. Recheck PR #63 unchanged/unmerged. Stop after review.

**Legal verification:** Independently delegated source verification; operating date absent in the source, so distinguish historical and current effective rules.

**Integration:** User explicitly authorizes commit/push on the target branch, no new PR. Work starts detached from `6f8f7644b8ac642f6eabc0ad5e6ba0ca0ef9f56e`; do not move another chat's checked-out branch.

## Validation ledger

- Source workbook SHA and frozen JSON SHA (`1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3`) match before and after review. No pilot/timetable search was rerun; original frozen evidence was reused.
- Final focused/private checks: **28 passed**, 8.66 seconds, Windows/Python 3.12.14/OR-Tools 9.15.6755. Cases include all requested synthetic behaviors, malformed structures, per-file output privacy, conditional relief, fixed-chain stress and reassignment with/without extra fleet, deterministic exports, source reconciliation and incumbent lock.
- Relevant existing MVP/settlement/joint/feedback/review/Route10/import/benchmark regression: **193 passed, six skipped**, 18.77 seconds. Skips are two old private Route6/10 review cases and four old optimizer-pilot acceptance cases. Private new review acceptance was enabled and passed. No optimizer rerun was needed to reuse frozen evidence.
- Whole-repository Ruff passes; Contract V1 formatting **59 files** passes; all four new Python files pass formatting. Both final Vietnamese Markdown outputs pass the Vietnamese copy validator with zero errors/warnings. No whole-repository pytest run is claimed.
- Two independent roles: legal verification of official sources/effectiveness; fresh-context code/math/evidence reviewer. Reviewer independently checked 3,102 native/stressed intervals, exact fleet counts and raw workbook runtime quantiles. Follow-up verified 918 stressed-trip ready/source-arrival values, reserve sensitivities and code fingerprints. No remaining material finding.
- Review-specific fixes demonstrated RED/GREEN: all three export paths must be ignored, explicit mapping/window validation, and stressed ready-time metadata recomputation with original arrival retained. No existing optimizer/circulation/selection file changed.
- Two final standalone review exports are byte-identical for all three files. They remain ignored under `outputs/crew_rest_review/` and `outputs/crew_rest_repeat/`. JSON records input digests and normalized analysis-code hashes.
- Per-scenario fleet, dwell, break, stress and recorded-X findings are retained only in the ignored private exports. The p50 incumbent is unchanged; actual crew feasibility remains unverified.
- Result: **PARTIAL_EVIDENCE**. Recommended Product Owner decision: obtain crew assignments, terminal-task/relief evidence and runtime calibration before implementing operational constraints. No new timetable, scheduler, solver, PR or merge.
- Remote target remained at the verified base before integration. PR #63 remained OPEN at `e9fe4eb92c785748d939d44c6386c005d5d9cd3c`; unrelated dirty tracked files remained untouched. Validation is local; the Python CI workflow triggers only main pushes/main PRs, so no Actions success is inferred from this branch push.
