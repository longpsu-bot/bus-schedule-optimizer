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

## MVP-2: baseline-aware, demand-guided continuation (2026-10-13)

Starting local/remote SHA: `5ac83f1d1f491bbca6434d3c55c9526b09f78eb0`, existing
`feat/mvp-service-plan-compiler`, Draft PR #63. Original checkout edits and all
historical research branches were preserved. The existing worktree was reused;
the app refused to reattach its prior-chat ownership, which was left intact.

### Implementation and decision semantics

`quality.evaluate` now reports every bucket's demand, B/candidate departure
coverage, served/outside mass, exact waiting integral in passenger-minutes,
mean wait/difference/percentage, contribution to combined wait, intersecting
gap, relevant regimes, protection violations and capacity threshold. Times are
whole minutes from midnight; arrivals are modeled uniformly within each supplied
bucket, not actual timestamped passenger observations. Every departure interval
reports modeled boarding exposure separately from physical capacity/onboard load.

Feedback priorities target explicit protected violations, capacity-proxy limits,
material excess wait versus B, and ordinary wait opportunities. Severity uses
actual gap/count deficits, excess modeled boardings, or absolute passenger-minutes;
relative percentage alone cannot dominate high-demand exposure. Fleet feedback
uses exact excess fleet plus a measured runtime/layover concurrency peak to locate
boundary/reallocation opportunities. This peak is not a replacement fleet estimate.

Existing merge/reallocate/shift/split operations are ordered by local nominal
headway reduction over the measured problem interval. All revisions still pass
the unchanged exact compiler and independent vehicle-chain validator. No compiler,
circulation, input-authority, frozen benchmark or SSE/TE gate was rewritten.

The queue holds at most `4 * effective evaluation budget` pending plans (100 at
default 25), reserving a bounded pool per direction. Evaluated plans are never
repeated; evicted unevaluated plans may re-enter. Candidate registration no longer
uses up the evaluation budget. Direction turns alternate when both pools exist;
every third turn explores a less-used operation. Generation and duplicate counters
are distinct from the 25 exact ServicePlan evaluations. Full measured quality,
including rejections, is retained as deterministic feedback. These settings bound
memory by evaluation count and the existing finite neighborhood; no brute-force
budget increase was made.

B is independently checked with its original times and the same authoritative
directional counts, endpoints, runtime, layover, fleet ceiling, stock, protection,
hard proxy and any configured maximum headway transition. It is not converted to
uniform regimes: regime count is `null`, regimes are `[]`. An irregular compliant
B is admissible. A solver limit is incomplete certification, not proof of a hard
failure. Separately proven service/authority failures can still establish that B
is noncompliant even when its minimum fleet is not certified.

Change justification is explicit, without a composite score:

- Replace a baseline with a proven hard failure when a fully certified alternative exists.
- Otherwise require material combined waiting improvement or at least one whole-minute
  protected-gap improvement, with no protected-gap deterioration, directional wait
  outside equivalence, or fleet increase versus B.
- Allow fewer vehicles with combined and directional wait inside the configured
  equivalence band; secondary regime/transition/terminal measures cannot justify
  change by themselves.
- The existing equivalence band is `max(0.10 minutes, 2% of B wait)`. Separate
  provisional materiality is `max(0.05 minutes, 1% of B wait)`; both thresholds
  are configurable and exported. Tiny numerical differences are not improvements.
- Explicit zero demand does not fabricate a mean wait; independently measurable
  protected improvement can still justify change without extra fleet. Missing wait
  evidence is not treated as zero demand.

`status=NO_CHANGE_RECOMMENDED`, `operator_decision=KEEP_BASELINE` and
`selected_source=BASELINE` recommend the actual certified B. `search_status` can
independently remain budget-limited or contain no feasible generated candidate.
An uncertified B plus feasible generated schedules leaves the operator unresolved,
with `BASELINE_COMPARISON_INCOMPLETE`; it never certifies retaining B or automatically
authorizes replacement. Existing statuses remain available. No outcome claims B
is globally optimal or a limited search proves a route infeasible.

All six output names and essential contracts remain. JSON reports include source,
decision, comparisons and alternative rejection reasons; no-change exports B's
actual timetable and exact chains. The original five XLSX sheets remain, plus
`DemandBuckets`, `Alternatives` and `ServiceFeedback`. All timetable/chain row
coverage is verified. CLI prints measured elapsed seconds separately so deterministic
result payloads do not contain wall-clock measurements.

### Independently reproduced real-route comparison

Inputs, SHA256 identities, `STABLE_MAR_JUL_2026`, source runtime/capacity/ceiling
and explicit 5-minute layover are unchanged from MVP-1 above. MVP-1 was also replayed
directly from `5ac83f1` in a local isolated module namespace, without checking out
another branch or modifying frozen evidence; its accepted figures reproduced.

| Metric | Route 6 B | Route 6 MVP-1 | Route 6 MVP-2 | Route 10 B | Route 10 MVP-1 | Route 10 MVP-2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Exact fleet | 20 | 16 | 16 | 12 | 12 | 12 |
| Modeled wait, minutes | 6.1656251053 | 6.1828200591 | 6.1652384347 | 9.5702955186 | 9.7109891162 | 9.5702955186 |
| Maximum headway, minutes | 15 | 21 | 18 | 25 | 22 | 25 |
| ServiceRegimes | Not modeled | 6 (3/3) | 6 (3/3) | Not modeled | 5 (2/3) | Not modeled |
| Terminal wait, vehicle-minutes | 6130 | 956 | 2289 | 2885 | 2154 | 2885 |
| Maximum headway transition jump, minutes | 7 | 11 | 11 | 5 | 4 | 5 |
| Applicable hard validity | PASS | PASS | PASS | PASS | PASS | PASS |
| Decision/source | Benchmark B | Generated | REPLACE / OPTIMIZED | Benchmark B | Generated | KEEP / BASELINE |

Route 6 selected `C010`: four fewer vehicles and wait difference from B
**-0.0003866706 minutes (-0.006271%)**, below materiality; justification is
**FLEET_SAVING_WITH_EQUIVALENT_WAIT**, not a material passenger-wait improvement.
Waiting improves versus MVP-1 by **0.0175816244 minutes** while keeping fleet16.
Directional waits are **6.2081507648 / 6.1250026374** minutes; B is
**6.2110095898 / 6.1230713470**. Terminal wait is higher than MVP-1 but lower than B.
Transitions remain exact meaningful blocks, including a 35-minute/five-gap inbound
peak; its 7→18-minute transition is disclosed, not hidden as a one-gap block.

An alternative `C023` uses fleet15 and wait6.2815705897 but is rejected for
directional deterioration outside equivalence. `C002` uses fleet16 and
wait6.1678185565 and remains justified, but loses generated-candidate tie-breaking.

Route 10 keeps B. Generated `C013` has fleet11, wait9.7857123912; `C011` has fleet12,
wait9.8083099885. Both exceed B's permitted service equivalence. Fewer regimes or
lower terminal waiting cannot force adopting them. Selected directional waits are
**9.5111955570 / 9.6382731735**. Default capacity is evaluation-only: B's maximum
boarding proxy **53.4640522876** exceeds the 0.9 planning limit **45.9**, which is
reported rather than described as an onboard-load certificate.

### Budget efficiency and measured runtime

| Per-route search | R6 MVP-1 | R6 MVP-2 | R10 MVP-1 | R10 MVP-2 |
| --- | ---: | ---: | ---: | ---: |
| Evaluated distinct ServicePlans | 25 | 25 | 25 | 25 |
| Distinct generated plans | 25 | 590 | 25 | 568 |
| Total generated proposals, including repeats | Not recorded | 668 | Not recorded | 631 |
| Compiled two-direction candidates, including duplicate schedules | 25 | 24 | 19 | 24 |
| Feasible distinct generated schedules | 14 | 17 | 3 | 2 |
| Duplicate compiled schedules | 10 | 7 | 5 | 7 |
| Guided / fallback evaluations | Generic / not recorded | 24 / 1 | Generic / not recorded | 24 / 1 |
| Outbound / inbound revisions | 10 / 14 | 12 / 12 | 20 / 4 | 12 / 12 |
| Maximum pending plans | 4 | 100 | 4 | 100 |
| Runtime, seconds (one local measurement) | 0.490 | 0.771 | 0.324 | 0.646 |

Generation counts are proposals, not additional solver evaluations. The small
priority pool improves Route 6 service per evaluation and supplies an explicit
Route 10 no-change decision. It does **not** demonstrate more feasible candidates
or better generated passenger service on every route. Runtime is machine-dependent,
includes baseline certification, and stays below the unchanged 120-second deadline.
All four MVP-2 scenario result payloads reproduced identically on a second run.

### Strict hard 0.8 proxy: accurate certification and remaining violations

Both routes ran independently without relaxing capacity or changing inputs.
Each evaluated25 plans, used24 guided/1 fallback turns, and balanced revisions12/12.
Both still have pending families after the budget and zero feasible generated
alternatives. The search is not exhausted; route infeasibility is not proved.

- **Route 6:** `NO_CHANGE_RECOMMENDED`, sourceBASELINE, search status
  `SEARCH_INCOMPLETE_NO_FEASIBLE_CANDIDATE`. B passes the configured hard proxy:
  max51.5882352941 ≤54.4, fleet20, wait6.1656251053; its timetable and exact chains
  are usable outputs. Closest generated rejection is evaluation3, fleet20, with
  inbound400–412 exposure60.0052287582 versus54.4 (**+5.6052287582**),
  inbound988–1000 **+2.5394335512**, and inbound412–424 **+1.4074074074**.
- **Route 10:** `SEARCH_INCOMPLETE_NO_FEASIBLE_CANDIDATE`, operatorUNRESOLVED.
  B fails the hard proxy (53.4640522876 versus40.8). Closest fleet-admissible
  generated rejection is evaluation11, fleet12; outbound996–1018 exposure
  58.2736383442 versus40.8 (**+17.4736383442**), outbound930–952 **+12.8819172113**,
  outbound390–409 **+9.9908496732**. No timetable is falsely certified.

MVP-1 hard runs also found zero feasible generated schedules. Its closest Route6
proxy was55.0671023965 (**+0.6671023965**); MVP-2 generated search is worse on this
measure, although it now certifies and retains valid B. Route10's best remaining
maximum excess is unchanged at17.4736383442. This limitation is material: nominal
local headway estimates can misrank exact integer settlement and cannot promise
monotonic proxy improvement. No favorable outcome or expected fleet was hard-coded.

Source data contain no real protected windows or initial terminal stock. Both are
tested synthetically; real-route protection is not certified from aggregate ticketing.
The 0.8 check certifies only the configured **boarding planning proxy**, not actual
onboard load factor. Stop-level boardings/alightings/occupancy are unavailable.

### Validation and independent review

```powershell
$env:PYTHONPATH='src'
$env:BUS_MVP_ROUTE6_WORKBOOK='E:\Project\Biểu đồ giờ\New model\Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx'
$env:BUS_MVP_ROUTE10_WORKBOOK='E:\Project\Biểu đồ giờ\New model\Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx'
python -m pytest tests/test_mvp_service_plan.py tests/test_mvp_acceptance.py --basetemp outputs/mvp2_validation/focused-final --tb=short
python -m pytest -s --basetemp outputs/mvp2_validation/full-final --tb=short
python -m ruff check . --exclude .artifact --exclude outputs --exclude .venv
python -m ruff format --check src/bus_schedule_engine/contracts_v1 tests/test_contract*.py
python -m ruff format --check src/bus_schedule_engine/mvp scripts/run_mvp_service_plan.py tests/test_mvp_service_plan.py tests/test_mvp_acceptance.py
```

Focused: **62 passed in9.57seconds**, including explicit synthetic reallocation and
boundary-shift improvements, absolute-versus-relative exposure, protected-before-quality
ordering, exact capacity intervals,12/12 fairness, all baseline policy cases,
uncertified fleet handling, zero-demand protection, deterministic repeats, six-output
contracts, unchanged compiler/chain validation and four independent private-route cases.
Lint and both format scopes pass. Full suite: **1515 passed,4 skipped,4 failed,
2 warnings in143.34seconds**. No MVP failure. The four failures match MVP-1:

- `test_input_template_semantics_are_frozen`: unchanged generated-template fingerprint.
- Two `test_fixture_json_is_structural_and_byte_deterministic` fixtures and
  `test_reviewed_baseline_json_is_byte_deterministic_and_has_review_status`: CRLF/LF bytes.

Separate inherited-only run without MVP collection: **50 passed,4 skipped,4 failed**.
No frozen fingerprint or unrelated expectation was changed. Full log is local
`outputs/mvp2_validation/pytest-full-final.log`; private reports/replay inputs remain
ignored, not committed. Independent reviewer reproduced four important decision
edge cases; RED→GREEN regressions fixed all of them, with no separate Minor findings.

Reproducible product CLI, run separately for each route:

```powershell
python scripts/run_mvp_service_plan.py --input 'E:\Project\Biểu đồ giờ\New model\Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx' --minimum-layover 5 --output-dir outputs/mvp2_validation/route_6
# Strict scenario: add --capacity-policy hard --maximum-load-factor 0.8 and use another output directory.
```

**Smallest next product decision:** authorize a bounded compile lookahead for the
top capacity-targeted neighbors so priority reflects actual settled gap exposure,
then rerun the same25-plan acceptance. First calibrate wait materiality/equivalence
with operators; do not equate the boarding proxy with observed load factor. No
Streamlit redesign, Route53 scale work, forecasting or network research was started.
