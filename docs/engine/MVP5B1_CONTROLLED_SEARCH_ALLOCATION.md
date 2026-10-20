# MVP-5B.1: controlled search allocation decision

**Decision: retain the verified MVP-5A p50 incumbent. Recommend A, ServiceRegime-first optimization, as the next development direction.** Six pairs per plan improves plan coverage and feasible-candidate yield per exact evaluation, but finds no better admissible timetable. Stop K-best/pair-allocation variants here; no next milestone is implemented or authorized by this report.

## Controls and reproduction

Executed locally on 2026-10-20, on `feat/mvp5-route10-engine-pilot`, starting at the required `e0c7b661de1ce60300d1b0596223e9e639508702`. The target worktree was clean. The original checkout has unrelated changes and was left untouched. PR #63 remains separate at `e9fe4eb92c785748d939d44c6386c005d5d9cd3c`.

Both allocations were rerun sequentially in the same Windows / Python 3.14.2 / OR-Tools 9.15.6755 environment. Each invocation reruns the unchanged MVP-5A controls and independently recovers the frozen incumbent. The input is a local copy named `route10.xlsx`, with unchanged SHA-256 `8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b`.

Only `pairs_per_plan` differs. Both use at most 25 plans, 160 distinct exact pair evaluations, four retained directional settlements, 256 previews per directional compilation, two-second / 0.2 deterministic-work solver limits, a 120-second route deadline, one worker and seed zero. Demand, p50/p75 windows, five-minute layovers, 51/51 trips, endpoints, fleet ceiling 14, review thresholds and selection policy are identical. No engine algorithm or frozen fixture changed.

From the pilot worktree, with the SHA-verified private input available:

```powershell
$env:PYTHONPATH='src'
python scripts/run_route10_pilot.py --joint --pairs-per-plan 16 --input outputs/mvp5b_inputs/route10.xlsx --output-dir outputs/mvp5b1_pairs16
python scripts/run_route10_pilot.py --joint --pairs-per-plan 6 --input outputs/mvp5b_inputs/route10.xlsx --output-dir outputs/mvp5b1_pairs6
```

Each command covers p50, p75 and p50 B25. The CLI defaults to 16, restricts this experiment to 6/16, and requires `--joint` for the new flag. Use new output directories for later reproduction to preserve these measurements.

## Primary and sensitivity results

For p50, quality rows describe selected `I001`. For p75, they describe **hard-rejected** `C001_04`, the best near-feasible trial under minimum failures, minimum fleet, then existing local-service order and wait. There is no p75 recommendation. Feasible counts include the separately supplied incumbent when it passes all hard gates; generated counts exclude it. Review exceptions count intervals, rather than individual warnings.

| Metric | p50 / 16 | p50 / 6 | p75 / 16 | p75 / 6 |
|---|---:|---:|---:|---:|
| Plans evaluated | 15 | 25 | 12 | 25 |
| Distinct exact pairs evaluated, including incumbent | 160 | 97 | 160 | 120 |
| Feasible timetables: all / generated | 2 / 1 | 2 / 1 | 0 / 0 | 0 / 0 |
| Minimum exact fleet found | 14 | 14 | 15 | 15 |
| Modeled wait, minutes | 9.441295 | 9.441295 | 9.447497 | 9.447497 |
| Maximum headway outbound/inbound, minutes | 23/21 | 23/21 | 24/21 | 24/21 |
| Maximum local waiting deterioration, minutes | 4.166667 | 4.166667 | 4.166667 | 4.166667 |
| Positive deterioration, passenger-minutes | 3,301.567 | 3,301.567 | 2,890.627 | 2,890.627 |
| Review exceptions / individual warnings | 9 / 11 | 9 / 11 | 8 / 10 | 8 / 10 |
| Runtime, seconds | 9.973 | 8.937 | 8.873 | 8.865 |
| Stop reason | Pair ceiling | Plan ceiling | Pair ceiling | Plan ceiling |
| Directional vectors generated / retained, fresh compilations | 1,518 / 56 | 1,889 / 80 | 1,218 / 48 | 1,511 / 84 |
| Retained directional settlements including cache reuse | 112 | 196 | 96 | 200 |
| Duplicate pairs = exact-pair cache hits | 33 | 48 | 17 | 31 |
| Directional compilation cache hits | 14 | 29 | 12 | 29 |
| Plans still queued | 100 | 100 | 100 | 100 |
| Distinct retained pairs unexamined | 12 | 175 | 12 | 168 |
| Unused exact-pair ceiling | 0 | 63 | 0 | 40 |
| Generated feasible per 100 new exact evaluations | 0.629 | 1.042 | 0 | 0 |
| End-to-end search milliseconds per distinct exact evaluation | 62.33 | 92.14 | 55.46 | 73.87 |

The six-pair allocation uses less exact fleet work, while performing more compilation work. These are **not equal computational-effort runs**. At most 150 generated pair encounters plus the incumbent are possible at six pairs over 25 plans; duplicates, failed compilations and smaller retained sets further reduce new evaluations. The observed counts are 96/119/79 new pairs for p50/p75/B25, plus one incumbent each. Milliseconds per exact evaluation include compilation and review, rather than measuring fleet matching alone; single-run elapsed times are descriptive.

Runtime measures the existing `run_bundle` call, including its baseline check and final review. It excludes MVP-5A control runs, exports and independent acceptance/audit work. The six baseline evaluations (one per scenario/configuration) are outside the pair counters.

Directional generation counts sum distinct vectors within each fresh compilation, including its boundary solution; all happen to equal actual preview totals here. Vectors repeated across different compilations are counted again. Retained counts use the same basis. No fresh directional enumeration was incomplete. Fresh compilation failures were p50: two/one `FAMILY_INFEASIBLE` for 16/6; p75: none. Fixed-family failure is not route infeasibility.

## Separate B-derived 25-minute guardrail

| Metric | B25 / 16 | B25 / 6 |
|---|---:|---:|
| Plans / exact pairs | 19 / 160 | 25 / 80 |
| Feasible timetables: all / generated | 3 / 2 | 2 / 1 |
| Minimum fleet / selected timetable | 14 / I001 | 14 / I001 |
| Selected modeled wait, minutes | 9.441295 | 9.441295 |
| Maximum headway outbound/inbound, minutes | 23/21 | 23/21 |
| Maximum local deterioration, minutes | 4.166667 | 4.166667 |
| Positive deterioration, passenger-minutes | 3,301.567 | 3,301.567 |
| Review exceptions / individual warnings | 9 / 11 | 9 / 11 |
| Runtime, seconds / stop | 10.321 / Pair ceiling | 9.202 / Plan ceiling |
| Directional vectors generated / retained, fresh compilations | 1,596 / 56 | 2,023 / 65 |
| Retained directional settlements including cache reuse | 144 | 173 |
| Duplicate pairs = exact-pair cache hits | 109 | 33 |
| Directional compilation cache hits | 22 | 31 |
| Queued plans / distinct unexamined retained pairs | 100 / 4 | 100 / 124 |
| Unused exact-pair ceiling | 0 | 80 |
| Generated feasible per 100 new exact evaluations | 1.258 | 1.266 |
| Search milliseconds per distinct exact evaluation | 64.50 | 115.03 |

Both retain the protection without violations among evaluated pairs. Fresh compilation failures are one `FAMILY_INFEASIBLE` plus one `NO_LEGAL_SETTLEMENT` at 16, and two `NO_LEGAL_SETTLEMENT` at six. The latter means no legal settlement in the explored directional family; it does not establish route infeasibility. All fresh enumerations completed within their bounds.

## Exact fleet distribution and near-feasible evidence

Counts include the incumbent re-evaluation and exclude duplicate/cache encounters. Every listed fleet count has an independent maximum-flow check.

| Scenario / allocation | Required fleet: number of exact evaluated pairs |
|---|---|
| p50 / 16 | 14:2, 15:24, 16:37, 17:38, 18:27, 19:10, 20:16, 21:4, 22:2 |
| p50 / 6 | 14:2, 15:22, 16:34, 17:21, 18:10, 19:5, 20:2, 21:1 |
| p75 / 16 | 15:11, 16:35, 17:46, 18:37, 19:21, 20:9, 21:1 |
| p75 / 6 | 15:9, 16:19, 17:28, 18:24, 19:24, 20:7, 21:4, 22:5 |
| B25 / 16 | 14:3, 15:25, 16:44, 17:41, 18:36, 19:10, 20:1 |
| B25 / 6 | 14:2, 15:9, 16:26, 17:22, 18:12, 19:1, 20:8 |

The best feasible timetable by aggregate wait and by local-service order is `I001` in every p50/B25 run. There is no feasible p75 timetable. The best hard-rejected near-feasible trial in each run is:

| Scenario / allocation | Candidate | Fleet / shortfall | Wait | Headways O/I | Max local delta | Positive passenger-minutes | Review intervals |
|---|---|---:|---:|---|---:|---:|---:|
| p50 / 16 | C003_04 | 15 / 1 | 9.552323 | 23/21 | 3.466667 | 4,122.040 | 13 |
| p50 / 6 | C004_01 | 15 / 1 | 9.630456 | 22/24 | 3.200000 | 3,113.300 | 9 |
| p75 / 16 | C001_04 | 15 / 1 | 9.447497 | 24/21 | 4.166667 | 2,890.627 | 8 |
| p75 / 6 | C001_04 | 15 / 1 | 9.447497 | 24/21 | 4.166667 | 2,890.627 | 8 |
| B25 / 16 | C010_01 | 15 / 1 | 9.686847 | 23/24 | 3.133333 | 3,331.660 | 11 |
| B25 / 6 | C001_05 | 15 / 1 | 9.447497 | 24/21 | 4.166667 | 2,890.627 | 8 |

## Rejection and selection accounting

**SEARCH_LIMITED:** potentially useful retained pairs remain unevaluated: p50 12/175, p75 12/168, B25 4/124 for 16/6. Each run also leaves 100 queued plans. Total distinct generated plans are respectively 398/651, 323/639 and 499/654; evicted and ungenerated families remain outside the queue counts. Unevaluated candidates have unknown feasibility and quality. The two allocations share only 35 p50, 33 p75 and 49 B25 evaluated vectors; six pairs samples genuinely different candidates without improving the selected result.

**HARD_REJECTED:** exact evaluated timetable counts are p50 158/95, p75 160/120 and B25 157/78. Every one has the authoritative modeled constraint failure `FLEET_CIRCULATION_OR_CEILING`; no policy adjustment can make these timetables fleet-feasible. The p75 hard-rejection totals include the supplied incumbent, which needs 15 vehicles under p75. Compilation failures above are separate and are not exact pair evaluations.

**POLICY_REJECTED:** all feasible generated candidates are listed below. Each passes baseline justification (`REPLACE_NONCOMPLIANT_BASELINE`), then fails both unchanged incumbent non-regression gates: aggregate waiting must be at most 9.44129512129342 (+ numerical tolerance 1e-9), and its hierarchical local-service key must be no worse than the incumbent. No feasible candidate with better overall wait or a better local key was excluded.

| Scenario / allocation: candidate | Fleet | Wait | Wait delta vs I001 | Max local delta | Positive passenger-minutes | Review intervals / warnings | Headways O/I |
|---|---:|---:|---:|---:|---:|---|---|
| Selected incumbent I001 | 14 | 9.441295121 | 0 | 4.166667 | 3,301.566667 | 9 / 11 | 23/21 |
| p50 / 16: C011_04 | 14 | 9.481349629 | +0.040054508 | 4.833333 | 3,716.440000 | 10 / 12 | 25/22 |
| p50 / 6: C012_02 | 14 | 9.582202728 | +0.140907607 | 4.800000 | 4,691.446667 | 14 / 21 | 25/21 |
| B25 / 16: C008_11 | 14 | 9.582202728 | +0.140907607 | 4.800000 | 4,691.446667 | 14 / 21 | 25/21 |
| B25 / 16: C011_02 | 14 | 9.481349629 | +0.040054508 | 4.833333 | 3,716.440000 | 10 / 12 | 25/22 |
| B25 / 6: C011_01 | 14 | 9.520563812 | +0.079268691 | 4.833333 | 3,841.826667 | 11 / 14 | 25/22 |

The full precision comparisons and all six components of the local-service keys are retained in the private audit. The first component alone already rejects each generated feasible alternative: 4.8 or 4.833333 is worse than 4.166667. No baseline-benefit rejection occurs among these candidates.

**SELECTED:** `I001` in both p50 and both B25 runs, with the exact frozen departures and independently rebuilt 14-vehicle chains. None in p75. Selected local deterioration and wait improve by zero.

## Product Owner answers and direction

- **A — p50:** no improvement. Six pairs finds a different 14-vehicle alternative, but it worsens wait by 0.140908 minutes, raises positive deterioration by 1,389.880 passenger-minutes and increases review intervals from nine to 14. Retain `I001`.
- **B — p75:** no fleet-feasible result at 14. Minimum found remains 15, including nine of the six-pair run's 120 exact evaluations. That run explores all 25 allowed plans, leaves 100 queued plans and 168 retained pairs unexamined, and uses 40 fewer exact evaluations than the ceiling. Route infeasibility is not proved.
- **C — local service:** no improvement among feasible candidates. In p50/six, hard-rejected `C005_01` has seven review intervals and 2,709.693 passenger-minutes (591.873 fewer than `I001`), but needs 15 vehicles; its wait is 9.516768 and headways 24/23. `C001_01`, present in both allocations, lowers maximum local deterioration to 2.733333 minutes but needs 16 vehicles, wait 9.748804, 4,041.420 passenger-minutes and 13 review intervals. These are rejected-trial observations, not feasible service improvements. The p75 local improvement to eight intervals / 2,890.627 is also a 15-vehicle rejected trial.
- **D — root cause:** hard fleet feasibility is the strongest direct finding: six-pair p50 rejects 95/97 exact evaluations on fleet, p75 rejects 120/120, and B25 rejects 78/80. Broader plan coverage alone does not resolve it. Insufficient ServiceRegime diversity is a plausible design limitation, not a proved diagnosis; no concrete directional-retention or joint-pairing defect is established, no good feasible candidate is suppressed, and neither runtime deadlines nor incomplete directional enumeration explain these runs. Runtime authority remains conditional but does not invalidate this controlled comparison under the fixed assumptions.

**Recommend exactly A — ServiceRegime-first optimization.** The next authorized design decision should address integer headways and regime boundaries jointly with fleet requirements, rather than spending more trials on the current fixed-family settlements. This recommendation follows the measured fleet bottleneck; it is not an optimality or route-infeasibility claim. Preserve the incumbent and stop pair-count variants. Product Owner authorization is required before developing that milestone.

## Evidence and validation

Private inputs, six complete scenario exports, exact candidate departures/regimes/chains, all evaluated pair feedback and controls remain ignored under `outputs/mvp5b1_pairs16/` and `outputs/mvp5b1_pairs6/`. `outputs/mvp5b1_audit.json` retains comparison metrics, policy comparisons, rejected-trial extrema, vector fingerprints and validation counts; `outputs/mvp5b1_analyze.py` retains the audit procedure. Existing MVP-5A/MVP-5B evidence directories were not overwritten.

The audit independently reconstructs the two-terminal compatibility graph and computes minimum fleet as 102 minus the maximum bipartite matching, using OR-Tools `SimpleMaxFlow` rather than the engine's augmenting-path matcher. All **777** exact evaluations match their exported fleet minimum, and every chain passes independent runtime, terminal-continuity, layover and complete-trip checks. Selected, every feasible alternative and each best near-feasible trial also pass fresh quality/review recomputation. Bundles/settings match across allocations except `pairs_per_plan`; frozen incumbent departures/quality match the preceding evidence. These revalidations recheck existing vectors, do not search new candidates, and are outside the experimental pair budgets. Baseline and MVP-5A control/acceptance work are also outside those budgets.

| Local validation | Actual result |
|---|---|
| Focused public Windows tests | 120 passed, five private-input skips |
| Full Windows / Python 3.14.2, canonical Git LF snapshot, all three private workbooks enabled | 1,648 passed, four skipped, **one inherited XML-writer fingerprint mismatch**, 326.17 seconds |
| Same frozen fingerprint test using the local Linux XML writer | One passed; `OPENPYXL_LXML=False`, matching the Linux environment |
| Full Linux / Python 3.11.17, all three private workbooks enabled, initial Windows-converted archive | 1,646 passed, four skipped, **three inherited CRLF byte-format failures**, 501.66 seconds |
| Linux corpus recheck using canonical Git LF bytes | 53 passed, four skipped; all three byte-format failures pass |
| Whole-repository Ruff / Contract V1 formatting / changed Python formatting | Pass / 59 files pass / three files pass |
| Independent code and report review | No material findings |

The full Windows run is **not reported as fully green**: this host has optional `lxml`, while the local Linux validation environment uses the standard XML writer. The unchanged frozen template fingerprint expects the latter and passes with that writer. No template or fixture was edited. The canonical snapshot is produced with `git -c core.autocrlf=false -c core.eol=lf archive`; the three changed Python files match the tested snapshot byte for byte after canonical LF conversion. All private-workbook acceptance cases, including both pair allocations, pass in both full runs. Two inherited Kaleido deprecation warnings remain. Logs, source/evidence hashes and the audit procedure are retained under ignored `outputs/mvp5b1_*` paths. These are **local checks, not GitHub Actions**; the workflow does not trigger for this feature-branch-only push.

All operational conclusions remain conditional on report-derived runtime windows, boarding-proxy demand with uniform within-bucket arrivals and the experimental five-minute layover. Terminal stock, drivers and onboard-load certification remain unverified.
