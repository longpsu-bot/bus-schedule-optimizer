# MVP Service Plan Compiler reset

## Verified recovery (2026-10-13)

Baseline: `main@ae5cab1598b22639224628f7c2bbb7915ad29b7b`. Product branch:
`feat/mvp-service-plan-compiler`, isolated managed worktree. Existing checkout
`d497748e8141195eb97c7a3dc6ad026ad689ce3b` has local edits to the coordinator and
frontier; those edits and its untracked private inputs remain untouched.
PRs 57/58/60/61/62 are OPEN/Draft; PR62 remote HEAD is `59b892d3`.
U6/U7 remain at their separate historical refs; no merging or evidence edits.

U6 evidence (`PR62_U6_KBEST_DAG_SHADOW_PRODUCTION_INTEGRATION.md`, U6
`185dbee3`) reports 123 frontier candidates and `DEMAND_FIT_ANCHOR_CONFLICT`.
U7 (`326e7b02`) compares plausible demand authorities. This is a selection
gate, not proof of operational infeasibility. The new product path never
requires SSE and TE to choose the same candidate.

## Focused reuse audit

| Component / actual source | Decision | Reason |
| --- | --- | --- |
| `v3_workbook.import_v3_multi_period_workbook_v1`, `importer._trips/_parameters` | REUSE_DIRECTLY | Validated Scenario B and native multi-period workbook inputs. |
| `multi_period_demand.derive_demand_profile_v1` | REUSE_DIRECTLY | Explicit day-weighted normalization and profile fingerprints. |
| research `demand_regimes.detect_demand_regimes_v1` | ADAPT | Use sustained demand changes, but avoid importing statistical authority stack. |
| research `demand_regime_trip_allocator` | ADAPT | Square-root rate allocation; bounded, revisable trip allocation. |
| `two_stage_allocator`, V3 `v3_global_regularity`, V4 branch | DEFER | Their frozen allocation/product authority and large dependency graph exceed this slice. |
| research `clean_boundary_compiler.compile_clean_boundary_timetable_v1` | ADAPT | Preserve integer rhythms and legal boundary ownership; a small CP-SAT regime compiler permits revisable shared pivots and time limits. |
| research `end_tail_settlement` | ADAPT | Protect last departure; explicitly model the tail as a meaningful rhythm, without frozen fingerprint dependencies. |
| research `clean_boundary_pilot._maximum_matching` (`69c8e9e`) | ADAPT | Exact DAG minimum path cover; extend to departure-specific runtimes/terminal layovers. |
| main `fleet_assignment.assign_contract_v1_fleet` | DEFER | Source-trip runtime anchoring and unconstrained initial distribution do not cover this input contract. |
| `protected_service_floor.assess_protected_service_floors_v1` | DEFER | Requires matched trip-level evidence; do not manufacture that evidence from aggregate demand. |
| research coordinator's exact wait integration | ADAPT | Integrate actual next departures under explicit uniform bucket arrivals; report out-of-window demand separately. |
| main `ortools_solver`, `ortools_quality_solver` | ADAPT | Reuse installed deterministic single-worker CP-SAT; solve regime integers rather than huge exact departure frontiers. |
| research `service_plan_coordinator`, refinement operators | REPLACE | Small bounded feedback queue, retain verified candidates, no concordance gate. |
| main `excel_exporter`, `v3_result_exporter` | ADAPT | Existing openpyxl export convention, new five-sheet result contract. |
| existing Streamlit pages | DEFER | CLI first; no UI changes. |

## Execution boundaries and implementation plan

1. `mvp/input.py`: normalized minute-based bundle, strict data/constraint validation,
   V3 adapter with source hashes and explicit layover/capacity policy.
2. `mvp/planning.py`: sustained demand segmentation and square-root allocation,
   bounded merge/split/boundary/count/tail neighbors; exact integer regime compiler.
3. `mvp/circulation.py`: exact minimum path cover, constrained initial terminal
   availability when supplied, independent full-chain validation.
4. `mvp/quality.py`: exact modeled wait, protection, diagnostics, deterministic
   hierarchical selection. No aggregate score across service metrics.
5. `mvp/runner.py` and CLI: bounded feedback, outcomes and six requested exports.

Tests first: hand-verifiable synthetic route, invalid authorities, exact endpoints,
whole-minute/internal uniformity, legal pivots, layover/path-cover, initial stock,
protection/capacity, wait integration, metric disagreement, budgets, determinism,
independent inputs and JSON/XLSX agreement. Run existing pytest/Ruff/format CI
commands as well. Windows pytest requires a dedicated `--basetemp` here (baseline
importer tests pass with it; default temp creation failed).

## MVP contracts and risks

Fixed directional counts from B are the smallest supported allocation contract;
directional count ranges/network optimization are deferred. Regimes own consecutive
gaps; neighboring regimes share a pivot, emitted once. Each has at least two gaps
(configurable) and a configurable minimum duration. Exported departure counts use
left-closed/right-open membership, with the final endpoint owned by the tail.
No one-gap transition or unowned inter-regime gap is allowed.

Candidate generation, not global optimization, is bounded (default 25 evaluations,
24 revisions). Single-worker CP-SAT has explicit per-call seconds and deterministic
work limits; timeout is incomplete, not infeasible. Regime-family infeasibility
is not route infeasibility. Only simple authoritative contradictions prove route
infeasibility. Always retain and return the best verified schedule.

Protection windows are explicit contracts: maximum intersecting consecutive gap
and optional minimum departure count. No inferred protection from aggregate
ticket sales. Capacity is optional, with explicit `evaluation_only` or `hard`
planning policy and configurable load factor (including 0.8). This measures
modeled boarding exposure, not observed onboard occupancy.

Demand outside fixed first/last departures is disclosed as unserved modeled
exposure. No next-day departure is invented. Historical boardings are an arrival
proxy only under the stated uniform-arrival assumption. A workbook with no explicit
layover requires a CLI operational input; route name/type never supplies it.
Workbook-specific terminal occupancy constraints must be rejected if unsupported.

Selection: feasible only; smallest worst protected gap; smallest exact modeled
waiting; within `max(0.10 minutes, 2% of best wait)` choose smallest fleet; then
regime count, transition jump, unnecessary terminal wait, tail gap, stable departure
tuple. These waiting tolerances are provisional configurable product calibration.
Directional and combined wait are reported; SSE/TE/exposure disagreements are
diagnostics only. Expert/Human Final schedules are comparisons, never authorities.

Real Route 6/10 acceptance runs independently with available original local V3
workbooks. Private workbooks and generated detailed outputs are not committed.
Commands, hashes, compact numerical results and missing-check reasons belong here.

## Executed acceptance evidence

Original Route 6/10 V3 inputs were available locally. Their SHA256 identities:

- Route 6: `4a5030da74d809b8a8bb40364bdc54f625c12469850d1d6ba1385622ab8d8f11`.
- Route 10: `876c5c709dfb6fee21ade63150302704f6c09589bf8a927bad279fbc88ff2b94`.

Both use `STABLE_MAR_JUL_2026`, explicit **5-minute terminal layover** supplied
as an operational acceptance setting, source runtimes 70/80 minutes respectively,
and fleet ceilings 20/13. This layover is not silently inferred from route type.
All runs are independent. Capacity is **evaluation_only** at the workbook's 0.9
maximum load factor in the default route run; it is not a hard capacity certificate.

| Actual result | Route 6 | Route 10 |
| --- | ---: | ---: |
| Outcome | FEASIBLE_BUDGET_LIMITED | FEASIBLE_BUDGET_LIMITED |
| Outbound / inbound trips | 78 / 78 | 51 / 51 |
| Outbound / inbound regimes | 3 / 3 | 2 / 3 |
| Exact required fleet / ceiling | 16 / 20 | 12 / 13 |
| Modeled combined waiting (minutes) | 6.1828200591 | 9.7109891162 |
| Outbound / inbound waiting (minutes) | 6.2444835640 / 6.1250026374 | 9.6492859752 / 9.7819609868 |
| B combined waiting (minutes) | 6.1656251053 | 9.5702955186 |
| B exact required fleet | 20 | 12 |
| Tail maximum headway (minutes) | 18 | 22 |
| Unnecessary terminal waiting (total vehicle-minutes) | 956 | 2154 |
| B unnecessary terminal waiting (total vehicle-minutes) | 6130 | 2885 |
| Hard timetable/fleet checks | PASS | PASS |
| Plan evaluations / generated plans | 25 / 25 | 25 / 25 |
| Feasible distinct schedules retained | 14 | 3 |
| SSE/TE diagnostic anchors disagree | YES (C022 / C008) | NO in this run |
| Max modeled boardings / capacity planning limit | 60.0732 / 61.2 | 58.2736 / 45.9 |

**Waiting is slightly worse than B:** +0.017195 minutes on Route 6 and +0.140694
minutes on Route 10. No claim of passenger-wait improvement is made. Route 6 uses
four fewer vehicles; Route 10 uses the same fleet with fewer rhythms and less
terminal waiting. Selection is relative to the generated feasible candidate set,
not a promise of dominance over B. Two alternatives and their quality measures
are included in each quality report.

No explicit protected windows/initial terminal stock were supplied by these V3
inputs. Maximum protected-window gap is therefore **not measured** (the neutral
ranking value is zero), not a real-route protection certificate. Exact first/last
departures are preserved. Synthetic tests exercise explicit protected-window
limits and stock. Matched trip-level protection authority is a missing input for
these acceptance runs; no historical research protections were changed.

Demand outside the fixed service endpoints: Route 6 outbound/inbound
15.7026 / 14.4880 modeled passengers; Route 10 13.3529 / 28.8301. These are reported
separately; no service beyond the last departure is fabricated. They are ticketing
proxy exposure, not measured passengers left behind.

The Route 6 Human Final reference was recovered from frozen
`PR62_C1_ROUTE6_GLOBAL_CLEAN_RHYTHM_DESIGN.json` at research commit `d497748e`.
Its archived exact timestamps were independently evaluated using this route's
normalized demand and operational inputs: 78/78 trips, minimum fleet **19**,
combined modeled wait **6.1509633746** minutes. Original expert workbook identity
in that evidence is `c2038b31c5a3f6a3ee2377ce2067542cc718a7d1907722efa3ab45a536bdd14a`.
This is a recovered benchmark comparison, not a fresh import of the expert
workbook and never a generation/selection authority. No analogous Route 10 Human
Final input was located.

Separate strict capacity runs with `--capacity-policy hard --maximum-load-factor
0.8` returned **SEARCH_INCOMPLETE_NO_FEASIBLE_CANDIDATE** on each route, after the
bounded search. No operational infeasibility is proved and no constraint is relaxed.
Both runs export empty recommendations and actionable rejection evidence.

Reproducible CLI (run once per route, changing `6` to `10`):

```powershell
python scripts/run_mvp_service_plan.py --input 'E:\Project\Biểu đồ giờ\New model\Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx' --minimum-layover 5 --output-dir 'E:\Project\Biểu đồ giờ\New model\outputs\mvp_service_plan\route_6'
```

Each route output directory contains the six requested JSON/XLSX artifacts.
All timestamp, regime-count and vehicle rows were compared between exported XLSX
and the selected result by the real-route acceptance tests. Repeat runs produced
identical result payloads. The committed synthetic fixture independently gives
two 20-minute rhythms, eight departures, two vehicles, 10-minute expected wait.

## Validation and remaining issues

Focused command (private paths supplied via `BUS_MVP_ROUTE6_WORKBOOK` and
`BUS_MVP_ROUTE10_WORKBOOK`; routes are separate parametrized tests):

```powershell
$env:PYTHONPATH='src'
New-Item -ItemType Directory -Force outputs/mvp_validation | Out-Null
python -m pytest tests/test_mvp_service_plan.py tests/test_mvp_acceptance.py --basetemp outputs/mvp_validation/acceptance-final2 --tb=short
python -m ruff check . --exclude .artifact --exclude outputs --exclude .venv
python -m ruff format --check src/bus_schedule_engine/contracts_v1 tests/test_contract*.py
python -m ruff format --check src/bus_schedule_engine/mvp scripts/run_mvp_service_plan.py tests/test_mvp_service_plan.py tests/test_mvp_acceptance.py
```

Focused: **33 passed**, including 29 unit regressions, synthetic export integration,
blank-capacity workbook integration, and two independent private-route tests.
Ruff lint and both formatting scopes pass. Reviewer findings about missing hard
capacity, nested unknown constraints, malformed settings and unbudgeted baseline
work were reproduced and fixed with tests, including the workbook caller.

Initial full pytest: 1466 passed, 4 skipped, 6 failures. Separate rerun without MVP
test collection reproduced four baseline failures: frozen template semantic
fingerprint with installed runtime/libraries; three canonical-byte JSON checks
against Windows CRLF checkout. Two subprocess tests passed with `-s`; captured
stdin had produced WinError 6. No frozen fingerprint/test was changed to hide
these failures. Final full run:

```powershell
python -m pytest -s --basetemp outputs/mvp_validation/full-final --tb=short
```

**1486 passed, 4 skipped, 4 failed, 2 warnings in 118.37 seconds**. The same
four baseline failures remain; no MVP test fails. Log:
`outputs/mvp_validation/pytest-full-final.log` (local, not committed). The exact
cause of the baseline generated-template fingerprint difference has not been
diagnosed. The three JSON byte differences are confirmed CRLF versus LF.

Input limitations: missing real protected-window/initial-stock authority and
original expert workbook. Search limitations: small candidate neighborhood,
capacity 0.8 schedules not found, no proven global optimum. Deferred scope:
directional count ranges, cross-direction reallocation, network routing, terminal
occupancy (blocked when supplied), Streamlit redesign and Route 53 load testing.
No known unfixed defect is asserted to be operational infeasibility.

**Smallest next product milestone:** use rejected capacity/protected-window bucket
evidence to target bounded trip reallocation and boundary revisions, so the same
25-plan budget finds better passenger service and can satisfy hard load factor
0.8 when feasible. Keep exact compiler/fleet validation and baseline comparisons.
