# MVP-5A: Route 10 engine optimization pilot

The engine independently generates an exact, explainable C using 14 vehicles in the primary report-derived p50 scenario. It has marginally lower modeled waiting than B and lower waiting than X. This is a **conditional experimental result requiring service review**, not unqualified operator acceptance: nine interval review exceptions remain, including a 4.167-minute local waiting increase. The p75 sensitivity is **SEARCH_INCOMPLETE** at 14 vehicles. No route-infeasibility proof or operational approval is claimed.

## Reproduce and preserve

Baseline: draft PR #63, `e9fe4eb92c785748d939d44c6386c005d5d9cd3c`. The isolated branch is `feat/mvp5-route10-engine-pilot`. PR #63, its worktree, unrelated local changes, historical research and original workbooks are untouched. No new PR is opened.

```powershell
$env:PYTHONPATH='src'
python scripts/run_route10_pilot.py --input 'C:\Users\HOME\Downloads\Bus10_MienTay_DHQG_A.xlsx' --output-dir outputs/mvp5_route10
```

The command requires SHA-256 `8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b`; missing or different input fails before output creation. It uses the existing MVP-4 importer and demand normalization, never V3 demand. Both B and X have 51 outbound/51 inbound trips, first departures 04:45/05:00, last departures 21:00/21:00, and a reported 14 vehicles. Independently reproduced source modeled waits are B 9.442026146574122 and X 10.36687674771821 minutes; maximum headways are B 25/25 and X 42/45 minutes.

Detailed private outputs stay ignored:

- `source_evidence.json`: normalized imported source with cell provenance, demand and excluded observations.
- `recorded_X_chains.json`: original recorded X trips, arrivals, vehicle summaries and source chain validation. These are separate from every common-runtime circulation.
- `unchanged_external_benchmark.json`: unmodified MVP-4 metrics; no benchmark metric or frozen expectation changed.
- `pilot_report.json`: scenario definitions, normalized bundles, before/after feedback, independently re-evaluated B/X/C, full vehicle chains, every interval and primary-C sensitivities.
- `comparison_report.md`: comparison, exact C departures/regimes and review warnings.
- Scenario subdirectories: existing timetable XLSX, JSON, regime, fleet, quality, diagnostics and offline operational-review HTML exports. For p75 the recommended timetable is empty; the rejected trial's exact evidence remains in the pilot report.

## Common hypothetical operating scenarios

The departure/arrival pairs are recorded for X only. The following direction-specific windows were declared after inspecting their broad duration patterns. They do not establish B's historical running time. Each row gives nearest-rank empirical p50/p75, rounded upward to whole minutes for the operating model. Observed durations already have whole-minute precision.

| Direction | Departure window | n | p50 | p75 |
|---|---|---:|---:|---:|
| Outbound | 04:45–06:00 | 5 | 92 | 92 |
| Outbound | 06:00–09:00 | 10 | 111 | 115 |
| Outbound | 09:00–15:30 | 19 | 108 | 113 |
| Outbound | 15:30–18:15 | 6 | 141 | 146 |
| Outbound | 18:15–21:01 | 11 | 97 | 106 |
| Inbound | 05:00–06:30 | 6 | 97 | 98 |
| Inbound | 06:30–09:00 | 9 | 111 | 112 |
| Inbound | 09:00–16:00 | 17 | 104 | 107 |
| Inbound | 16:00–18:30 | 9 | 126 | 130 |
| Inbound | 18:30–21:01 | 10 | 88 | 89 |

Windows are half-open; 21:01 includes the final 21:00 departure. Every B/X/C departure gets the same time-dependent rule and an explicit five-minute layover at its destination. Every arrival and minimum DAG path cover is recomputed, then independently chain-validated. Source X arrival times are never transplanted onto B.

The five- and six-observation periods are sparse. Five observations is a declared minimum for this descriptive experiment, not a statistical adequacy theorem; fewer observations block the scenario. p75 is a sensitivity assumption, not a guaranteed reliability percentile. The source does not establish independent samples, dates/day types, population coverage or day-to-day variability. Window choice, X's departure choices and report construction may bias results, especially where long-running trips receive a single departure-window runtime. The final window extension and step changes are model conventions, not measurements.

Reported fleet 14 is not an exact common-scenario fleet certificate. Initial terminal stock, drivers, actual onboard load and legal operating requirements remain unverified. Demand is historical boarding/chart exposure with uniform within-half-hour arrivals. The same 38.2 passengers outside service are disclosed and excluded for B/X/C; no next-day trips are invented.

## Measured control and targeted change

The unchanged MVP-2 coordinator/compiler was executed before modifying the algorithm. In p50 it generated 643 distinct plans, evaluated 25, compiled 22, and produced three duplicate schedules. All 19 unique evaluated timetables failed exact fleet feasibility; three directional compilations were family-infeasible. The initial C required 15 vehicles and waited 9.550209 minutes. B/X independently required 17/16 vehicles. This established runtime-induced fleet pressure and poor integer-settlement prioritization, not route infeasibility.

The compiler previously minimized only boundary deviation. Enumerating the same initial regime allocation exposed a different legal integer settlement yielding 14 vehicles and 9.441295 minutes waiting. The integrated improvement retains the original valid boundary incumbent and previews at most 256 additional legal settlements per direction/plan, bounded by existing solver time/work limits. It ranks explicit protection violations, exact demand waiting and boundary fit. The final exact fleet/quality checks, feedback revisions and selection remain in the existing coordinator.

This is opt-in using `compilation_lookahead=256`; default `0` reproduces boundary fitting and existing Route 6/10 MVP regressions. All runs retain 25 plan evaluations. Settlement previews are separately disclosed; they do not run hidden exact fleet evaluations. No one-gap transition regimes, larger search budget, new dependency or second optimization architecture was added. Previously verified feasible candidates remain retained by the coordinator.

| p50 statistic | Control | Improved |
|---|---:|---:|
| Distinct plans generated | 643 | 658 |
| Total proposals | 703 | 743 |
| Plan evaluations | 25 | 25 |
| Fully compiled plans | 22 | 24 |
| Duplicate timetables | 3 | 13 |
| Unique exact fleet/quality evaluations | 19 | 11 |
| Feasible generated candidates | 0 | 1 |
| Directional settlement previews | 47 | 6,637 |
| Incomplete settlement enumerations | 0 | 0 |
| Runtime, first recorded Windows run | 0.658 s | 8.903 s |

The extra previews cost runtime and reveal many duplicate timetables; both are visible limitations, not hidden budget increases. The search is bounded and global optimality is not proved. p75's improved run evaluated 25 plans and 12 unique timetables, with zero feasible candidates, 13 duplicates and four incomplete directional enumerations (7,222 previews, 11.042 s in that run). Original and new statistics are saved in full for every scenario, and elapsed time is expected to vary by machine.

## Independently evaluated B / X / C

Each table uses one normalized demand, runtime and layover context. C in the primary and guardrail scenarios is engine-generated C001. p75's strongest trial is the same departure pattern but fails its separately recomputed 14-vehicle ceiling. No fleet counts are borrowed across scenarios.

| Primary p50 criterion | B | X | C |
|---|---:|---:|---:|
| Outbound/inbound trips | 51/51 | 51/51 | 51/51 |
| Exact required fleet | 17 | 16 | 14 |
| Modeled wait, minutes | 9.442026 | 10.366877 | 9.441295 |
| Maximum directional headways | 25/25 | 42/45 | 23/21 |
| Positive interval deterioration vs B, passenger-minutes | 0 | 6,593.907 | 3,301.567 |
| Explicit protected-rule violations | 0 | 0 | 0 |
| Uniform runs outbound/inbound | 8/7 | 31/28 | 4/3 |
| Singleton runs outbound/inbound | 0/0 | 22/18 | 0/0 |
| Operational constraints within scenario | fail fleet | fail fleet | pass conditionally |

Zero explicit-rule violations does not establish peak-service protection: none was supplied. Positive deterioration sums only worsening intervals; it does not offset them against improvements. Overall C improvement vs B is only 0.000731 minutes (0.007742%), too small to claim a meaningful passenger benefit. Replacement is justified under the current policy because B fails the declared common-scenario fleet ceiling. C improves waiting vs X by approximately 0.925582 minutes (8.93%).

| p75 criterion | B | X | Strongest C trial |
|---|---:|---:|---:|
| Trips | 51/51 | 51/51 | 51/51 |
| Exact fleet | 18 | 16 | 15 |
| Wait, minutes | 9.442026 | 10.366877 | 9.441295 |
| Maximum headways | 25/25 | 42/45 | 23/21 |
| Positive deterioration, passenger-minutes | 0 | 6,593.907 | 3,301.567 |
| Explicit protected-rule violations | 0 | 0 | 0 |
| Operational constraints | fail fleet | fail fleet | fail fleet; SEARCH_INCOMPLETE |

The separately declared p50 **B-derived 25-minute full-horizon guardrail** gives B/X/C fleet 17/16/14, unchanged waits and headways, and 0/2/0 experimental guardrail violations. C001 remains feasible. This experiment does not invent a regulatory gap limit or protect inferred school/worker peaks.

## Service trade-offs and acceptance

All hard numerical timetable and exact circulation gates pass for primary C: 51/51 whole-minute departures, preserved endpoints, 14 vehicles, lower waiting than X and marginally no worse than B, no 42–45-minute gaps, and seven internally uniform regimes without one-gap blocks. The final outbound/inbound gaps are 23/20 minutes. Starting stock requirements are eight outbound/six inbound; actual stock availability is unconfirmed.

Interval quality is **REVIEW_REQUIRED**, not an automatic pass. Existing MVP-3 review thresholds are unchanged; they are review policy rather than hard service authority. C has nine review exceptions. High-demand warnings are:

- Outbound 11:00–11:30: fewer departures counted within the half-hour, although modeled wait improves 1.967 minutes. This is an alignment/count warning, not demonstrated waiting harm.
- Outbound 16:00–16:30 and inbound 16:30–17:00: intersecting gaps rise from 15 to 20 minutes and local modeled wait rises 0.833 minutes. The smoothed service relieves exact fleet pressure, but those intervals lose frequency.

Material local deterioration also occurs outside the default high-demand classification: inbound 17:00–17:30 worsens 4.167 minutes (470.833 passenger-minutes); outbound 14:30–15:00, 15:30–16:00 and 16:30–17:00 worsen 3.467, 3.367 and 3.333 minutes. These are unresolved service trade-offs requiring operator review. Aggregate wait equivalence does not settle them, and the current engine does not prove them unavoidable.

The next justified engine improvement is **joint settlement ranking using exact circulation and interval-deterioration evidence within the same 25-evaluation budget**, retaining the current verified C as incumbent. Directional minimum-wait settlement alone misses circulation-compatible alternatives in p75 and does not prioritize severe local deterioration before aggregate wait. This pilot makes that limitation measurable; it does not claim p75 infeasibility or completed operational certification.

## Exact primary C

Outbound: 04:45, 05:00, 05:15, 05:30, 05:45, 06:00, 06:15, 06:30, 06:45, 07:04, 07:23, 07:42, 08:01, 08:20, 08:39, 08:58, 09:17, 09:36, 09:55, 10:14, 10:33, 10:52, 11:11, 11:30, 11:50, 12:10, 12:30, 12:50, 13:10, 13:30, 13:50, 14:10, 14:30, 14:50, 15:10, 15:30, 15:50, 16:10, 16:30, 16:50, 17:10, 17:33, 17:56, 18:19, 18:42, 19:05, 19:28, 19:51, 20:14, 20:37, 21:00.

Inbound: 05:00, 05:17, 05:34, 05:51, 06:08, 06:25, 06:42, 06:59, 07:16, 07:33, 07:50, 08:07, 08:24, 08:41, 08:58, 09:15, 09:32, 09:53, 10:14, 10:35, 10:56, 11:17, 11:38, 11:59, 12:20, 12:40, 13:00, 13:20, 13:40, 14:00, 14:20, 14:40, 15:00, 15:20, 15:40, 16:00, 16:20, 16:40, 17:00, 17:20, 17:40, 18:00, 18:20, 18:40, 19:00, 19:20, 19:40, 20:00, 20:20, 20:40, 21:00.

| Direction | Shared pivot interval | Headway | Gaps |
|---|---|---:|---:|
| Outbound | 04:45–06:45 | 15 | 8 |
| Outbound | 06:45–11:30 | 19 | 15 |
| Outbound | 11:30–17:10 | 20 | 17 |
| Outbound | 17:10–21:00 | 23 | 10 |
| Inbound | 05:00–09:32 | 17 | 16 |
| Inbound | 09:32–12:20 | 21 | 8 |
| Inbound | 12:20–21:00 | 20 | 26 |

The generated vehicle-chain JSON lists all 102 trip IDs, assigned vehicles, recomputed arrivals, ready times and 14 alternating-terminal chains. The independent validator checks identity coverage, uniqueness, endpoints, direction changes and destination layovers. Unit tests cover runtime-window boundaries, source coverage, nearest-rank summaries, sparse evidence, protection, transition limits, demand response, boundedness and determinism. Private acceptance tests independently regenerate and evaluate the result when `BUS_MVP5_ROUTE10_WORKBOOK` is configured. Route 6/10 MVP-1/2/3 private regressions use their separate existing environment variables; they never provide demand to this pilot.

## Final verification

- Linux Python 3.11, canonical LF checkout of the staged source: **1,621 passed, four skipped**, with both private V3 route regressions and the actual SHA-verified pilot workbook enabled. Whole-repository Ruff lint passed; CI Contract V1 format scope passed (59 files); all six changed Python files passed formatting. Two inherited Kaleido deprecation warnings remain. This is a local execution of the existing CI checks; no GitHub Actions run or new PR was created.
- Windows full suite before the final two review regressions: 1,615 passed, four skipped, four inherited frozen template/CRLF fingerprint failures. Frozen fixtures and expectations were not edited. Final focused new checks: 15 passed, one private-input skip.
- Two complete final actual-workbook Windows runs reproduce every non-timing pilot field exactly. Windows/Linux independently agree on all three scenarios' B/X/C departures and exact vehicle chains; numerical quality evidence agrees within 1e-9. Improved-run non-timing statistics also agree. The unchanged p75 control follows different tied boundary settlements across platforms (Windows 23 compiled/20 fleet rejections; Linux 25 compiled/21 fleet rejections), with no feasible C in either. Same-environment repeatability is verified; cross-platform bitwise equality of the inherited control search is not claimed.
- Independent reviewer verified the input hash and all scenario metrics. Two findings were fixed with RED-to-GREEN regressions: share deterministic solver work between boundary solve/lookahead, and independently evaluate retained measured rejected-trial times instead of rerunning a bounded solve. Final verdict: no remaining critical/important findings; ship as a conditional experiment.
