# Route 10 fixed-timetable integrated blocking V1

**Verdict: `FEASIBLE_BUT_UNPROVED`.** Exactly four primary experiments ran on 30 October 2026, on the unchanged 102-trip P0 timetable. Each retained assignment independently passes physical, fixed-crew, elapsed-duty, total-driving, continuous-driving, meal and general-rest validation. All native results are `FEASIBLE`; none proves the fleet optimum or route infeasibility. These are experimental assignments, not operational or statutory approval.

| Runtime / duty limit | Proven global L | Validated U: vehicles / teams | Initial A / B | Duty spans (min) | Max continuous driving (min) | Lunch / dinner / general required and covered | Solve wall seconds |
|---|---:|---:|---:|---:|---:|---|---:|
| p50 / 480 | 26 | 41 / 41 | 20 / 21 | 242–478 | 234 | 14/14; 7/7; 24/24 | 20.206 |
| p50 / 600 | 21 | 36 / 36 | 20 / 16 | 219–600 | 234 | 20/20; 6/6; 24/24 | 19.304 |
| p75 / 480 | 27 | 44 / 44 | 22 / 22 | 99–479 | 236 | 8/8; 8/8; 20/20 | 14.795 |
| p75 / 600 | 22 | 36 / 36 | 21 / 15 | 269–597 | 235 | 20/20; 9/9; 25/25 | 17.803 |

Coverage entries are covered/required; all required intervals are covered. Each team has one distinct hypothetical driver and attendant, so individual role counts equal U and total people equal 2U. A/B counts are exact requirements of the **selected assignment**, including late starts already stationed initially. Their components are not independently minimized terminal requirements.

Each solve used the complete 1,987-edge p50 or 1,978-edge p75 task/reserve DAG, one worker, seed 0, OR-Tools 9.15.6755, ten deterministic seconds and a sixty-second emergency wall limit. Actual deterministic work was 10.000002 / 10.004335 / 10.000003 / 10.000106 seconds respectively. Total primary pipeline time, including source revalidation and exports, was **88.658 seconds** under the declared 300-second global limit. No additional primary optimization runs were performed. Later checks only revalidated saved witnesses and exercised synthetic models.

The lower bounds combine the task-path relaxation (16 in all cases, matching size 86 equal to independently solved maximum-flow/min-cut capacity 86) with the corrected workload bound. With q=h=p=5, n=102 and K blocks, minimum elapsed workload excluding idle is W+1530−5K, because q is internal only. Therefore K>=ceil((W+1530)/(H+5)), giving 26/21/27/22 for workloads 11,010/11,376 minutes. These are necessary bounds. Absolute gaps U−L are 15/15/17/14; relative gaps are 36.59%/41.67%/38.64%/38.89%. The solver did not close them.

The former **14** vehicle model used p50 runtime and technical five-minute turnaround without fixed-team daily duty and protected-rest obligations. The **16** task-only model includes q+h+p internally but still permits long vehicle paths without the new crew obligations. The p75 technical-only minimum is 15. These weaker-model minima are not competing integrated rosters. The new results establish feasible upper bounds 41/36/44/36 under stronger assumptions; they do not establish those counts as the necessary integrated minimum.

The selected experimental policy is exactly the PO's request: fixed synchronized crew with no reuse/relief; lunch 11:00–14:00 and dinner 17:00–20:00, each thirty continuous minutes, required when D>=360 and window overlap>=60; independently thirty continuous protected minutes for D>=360; continuous driving<=240 with a thirty-minute protected reset; elapsed H=480/600 including waiting/rest; pre/post five minutes each; technical five minutes internally only; explicit zero additional recovery on the selected p50/p75 runtime basis. The redundant total-driving cap H has no statutory daily-driving meaning. Whole free intervals are explicitly selected as protected rest under the dominance argument in specification §6.6. Meal/reset/general labels share that physical union; elapsed rest is never added twice.

## Exact witnesses and reproduction

Generated private artifacts remain ignored under `outputs/integrated_v1_primary/`:

- `integrated_vehicle_crew_v1.json`: all four exact versioned requests, immutable trip tables, ordered vehicle/team/driver/attendant assignments, selected rest and meal intervals/terminals, independently reconstructed activity/inventory ledgers, matching/cut witnesses, bounds, solver/model/response digests and versions.
- `integrated_vehicle_crew_v1.xlsx`: exactly three native tables, **FeasibilityReport**, **Timetable** (408 trip rows), **VehicleCrewDuties** (linked block/trip/connection/activity/rest rows).
- `summary.json` and four atomic incumbent checkpoints retain counts, bounds, elapsed computation and strongest validated assignments. `verification.json` records final independent revalidation and source/code digests. Primary analysis code digests are preserved; later boundary hardening does not change the mathematical model.

From the pilot worktree, with the original private files available:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONUTF8='1'
$env:OPENPYXL_LXML='False'
python scripts/run_route10_integrated_blocking.py --input '<private-workbook.xlsx>' --evidence '<private-fleet_report.json>' --output-dir outputs/integrated_v1_reproduction
```

Use a fresh output directory for an independent reproduction; an existing directory resumes only request-digest-matched, independently validated checkpoints. Reproduction is bounded and may return unproved feasible or incomplete status. The experiment does not change departures, recommendation, scoring, existing exports, ServiceRegime planning or PR #63.

SHA-256 locks remain:

- workbook: `8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b`;
- frozen evidence: `1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3`;
- P0 departures: `d20e26cc05c48a9d4c06c4937b1fc97e835be24d9f7c0f7dda46849c19f257a9`.

## Review and operational uncertainties

The independent specification reviewer accepted corrected endpoint/general-rest accounting and the whole-free-interval dominance proof before implementation. Thirty-three initial hand-built validator tests passed **before solver code was written**. Small exhaustive partition oracles cover the model's exact synthetic claims; a separate reviewer additionally compared 500 randomized tiny instances, including varying task, reserve, meal/reset/general lengths, threshold and disabled-rule settings. The reviewer independently reconstructed all four saved primary assignments. Review findings concerned boundary robustness, not the mathematical model: staging-file aliases, oversized native integers, malformed checkpoint/witness objects and checkpoint I/O retention. Each has a reproducing regression.

Workbook verification imported the saved file into the bundled spreadsheet runtime, checked three native tables, inspected values, rendered all three sheets and found zero formula-error matches. The reports contain fixed computed witnesses, not a recalculating staffing or cost model.

Verification results:

- Focused new/existing regression group: **186 passed, 4 skipped in 379.31 seconds**. Private Route 10 pilot, frozen crew review, peak/off-peak and integrated adapter checks ran. The four skips are only the older `BUS_MVP_ROUTE6_WORKBOOK` / `BUS_MVP_ROUTE10_WORKBOOK` acceptance inputs, which were not configured.
- After all boundary fixes, a fresh run of all new integrated suites with private inputs: **73 passed in 8.32 seconds**.
- Ruff lint, Ruff formatting and `git diff --check` passed. Existing compiler, recommendation, scoring, input, circulation, crew-review and fleet-time-space code and frozen input bytes remain unchanged.
- Independent review findings were fixed with RED→GREEN regressions. Checkpoint I/O failures retain the in-memory validated witness and report an internal incomplete status. Windows denied file-symlink creation; the lexical staging-path alias case was reproduced at the path-resolution boundary, while real NTFS hardlink and direct-path collision checks ran against files.

The focused regression command was:

```text
python -m pytest tests/test_integrated_blocking_validation.py tests/test_integrated_blocking.py tests/test_integrated_blocking_report.py tests/test_crew_review.py tests/test_fleet_timespace.py tests/test_peak_offpeak_pilot.py tests/test_mvp_service_plan.py tests/test_mvp_acceptance.py tests/test_route10_pilot.py --basetemp=outputs/integrated_v1_regression -ra --tb=short
```

It used `PYTHONPATH=src`, `PYTHONUTF8=1`, `OPENPYXL_LXML=False`, and the SHA-locked private files through `BUS_MVP5_ROUTE10_WORKBOOK` / `BUS_CREW_FROZEN_EVIDENCE`. The final new-suite run used the same environment and a distinct basetemp. The new tests added during review were run fresh after the longer regression process had imported its modules.

Operational date, applicable transport/labour/night/overtime rules, actual qualified people and weekly histories, A/B initial stock, parking, measured task/recovery standards, permission to protect whole free intervals and runtime reliability remain unverified. No depot, deadheading, relief, transfer or undocumented repositioning is supplied by the model. Satisfaction of the selected assumptions is not a statutory-compliance claim. Integration with timetable or ServiceRegime planning is outside this milestone.
