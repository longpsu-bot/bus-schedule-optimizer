# Peak/off-peak deployment pilot: Phase 1 and Phase 2

This is a read-only experimental reconstruction and two manually authored ServicePlans. It does not introduce a new time-space optimizer, modify frozen C, change the existing recommendation or certify operational/labor compliance.

## Reproduction

Start from pilot base `8982dca0777435cc86a005c6ef613b05ca4d9f0a`. The CLI checks the private workbook SHA and frozen MVP-6A SHA through the existing crew-review source validation:

- Workbook: `8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b`.
- Frozen `fleet_report.json`: `1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3`.

```powershell
$env:PYTHONPATH='src'
$env:PYTHONUTF8='1'
$env:OPENPYXL_LXML='False'
python scripts/run_peak_offpeak_pilot.py --input '<private-workbook.xlsx>' --evidence '<frozen-fleet_report.json>' --output-dir outputs/peak_offpeak
```

Original inputs remain outside Git or in ignored directories. Every generated output inside this repository must be ignored; the runner checks each destination and prevents source/output collisions. Do not commit the workbook, frozen evidence, generated route JSON, CSV, Markdown, HTML or QA captures.

The six main exports are `peak_offpeak_report_vi.md`, `fleet_timespace.json`, `fleet_utilization.csv`, `deployment_scenarios.json`, `crew_meal_recovery.json` and `fleet_timeline.html`. Recomputed source-review evidence is under `source_revalidation/`. Code fingerprints, source digests, exact departures, regimes, chain identities and rejected operating requirements are included. Repeated runs of these six exports must be byte-identical.

## State and time conventions

- Intervals are half-open, with exact numeric event times. At the same timestamp, initial stock is recorded first, then arrivals, readiness/state events and departures. Inventory columns in the ledger describe each ordered event; snapshots describe the complete post-event state at the timestamp.
- Location is A, B or travelling in one direction. All physical vehicles are at their chain's declared origin at the report horizon start, including vehicles that first depart later. Extra explicitly declared unused stock stays at its initial terminal.
- Vehicle state and crew activity are separate. Technical turnaround, post-arrival tasks, traffic reserve, continuous meal opportunities, waiting/standdown and predeparture tasks use separate intervals. Known preparation, meal and reserve intervals are excluded from terminal-ready counts. Vehicle readiness does not prove crew availability.
- `NOT_YET_DEPLOYED` and `FINISHED_SERVICE` do not remove a vehicle from physical inventory. The physical vehicle total equals both terminal inventories plus both travelling-direction counts at every event boundary.
- Fifteen-minute averages integrate the exact piecewise-constant states. Peaks are maxima during each bucket. Duration totals use the full reported horizon, including stock waiting before/after service; middle-of-chain waiting and standdown are reported separately.
- All movement between terminals is an assigned passenger trip. No depot movement, deadhead or instantaneous transfer is supported. Parking capacity and authority remain unknown, even when conservation passes.

## Crew and recovery assumptions

Defaults are the approved experimental policy `ONE_CREW_PER_FULL_VEHICLE_CHAIN`: lunch 11:00–14:00, dinner 17:00–20:00, each 30 continuous minutes; technical turnaround 5, post-arrival tasks 5, predeparture tasks 5 minutes. These are experimental parameters, not operator rules or legal authority. Override the complete provenance-labelled policy object with `--policy path.json`.

For conservative screening, a meal is required if the modeled full duty span intersects its window, including partial intersection. The report makes this interpretation of “spans” explicit. Duty starts before the first departure by the predeparture task allowance and ends after the final arrival plus technical/post-arrival tasks. Only selected continuous meal opportunities reset modeled continuous-driving exposure; waits are never added together. The eight-hour duty marker is a review prompt, not a legal finding.

At p50, each arriving trip reserves `max(0, p75_runtime(t)-p50_runtime(t))` using its departure time and direction. At p75, that margin is already consumed by the longer arrival time and is not subtracted again. Remaining time is independently assessed for tasks and meals. Shortfalls stay explicit; departures are not delayed or tasks silently dropped.

Existing fixed-chain crew review and exact fleet assignment are reused. The full recovery/task fleet lower bound uses the p75 runtime plus technical/post/pre task connection allowance with unchanged departures. It is not an optimized meal assignment. Fixed-chain p75 failures have no delay propagation; exact p75 reassignment is separately labeled and may require additional vehicles.

## Manual plans and fleet scenarios

P0 is the full frozen C object. P1/P2 contain authored directional boundary targets and gap allocations with a rationale for every choice. The existing compiler is called once per direction and family: at least two gaps and 30 minutes per regime, boundary settlement at most 30 minutes, headway jump at most 10 minutes. Counts and endpoints stay fixed. No search, automatic relaxation or reranking changes P0. Compilation and solver limits are disclosed rather than called infeasibility.

The primary fleet ceiling is 14. Exact unconstrained requirements above 14 are rejected diagnostics, not authorized deployments. The hypothetical 8/6 terminal allocation is separately solved with the existing constrained assignment code at p50, p75 and full recovery/task assumptions. It is not confirmed operator stock.

For a 14-vehicle assignment, the 15-vehicle sensitivity makes exactly one declared split: the longest-duty chain at its departure nearest 12:00. The suffix belongs to a distinct vehicle and crew whose initial terminal is recorded. Both resulting chains are independently validated. This is not a search over all splits; adding one bus may bring no meal/recovery gain. A timetable with a proved minimum above 15 is explicitly rejected for that sensitivity.

Afternoon position diagnostics use independently inspected demand clusters, with distinct directional ends. They reference only actual assigned passenger trips, corresponding arrivals and readiness after recovery, tasks and selected meals. They do not imply that an idle bus can substitute for an arbitrary peak departure.

Hard fleet feasibility, inherited mandatory constraints, explicit service-protection authority, local passenger deterioration and no-relief crew requirements are separate. Missing service/stock/parking authority prevents operational approval. `NO_OPERATIONALLY_ACCEPTABLE_CANDIDATE_FOUND_WITHIN_PILOT` is a bounded experiment outcome, not global timetable infeasibility.

## Validation

Standalone synthetic tests require no private data:

```powershell
python -m pytest tests/test_fleet_timespace.py tests/test_peak_offpeak_pilot.py --basetemp=outputs/peak_tests
```

Set `BUS_MVP5_ROUTE10_WORKBOOK` and `BUS_CREW_FROZEN_EVIDENCE` only for private acceptance. Existing long-running optimizer acceptance has separate opt-in variables; unchanged frozen evidence is sufficient for this pilot's private acceptance. See the implementation plan for the final validation ledger.

Relevant regressions cover crew review, MVP compiler/settlement/joint/fleet feedback, review, Route10, external import and benchmark. Run Ruff over the repository, formatting over changed Python files and the CI Contract V1 scope. An independent reviewer recomputes matching, physical locations, meal/recovery arithmetic, deployment lead times and CSV integrals without importing the pilot's calculations.

Validation is local. The current Python CI workflow triggers for `main` pushes/PRs; a pilot-branch push does not establish an Actions result. PR #63 must remain unchanged and unmerged, with no new PR. Stop after these two phases.
