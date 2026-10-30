# Integrated blocking V1.1: optimality gap review

**Verdict: `GAP_REDUCED`.** On the unchanged P0 timetable, the validated upper bound improves from **36 to 34** for p50/600 and **44 to 42** for p75/480. The other fleet upper bounds are unchanged. A separate analytical reset-workload certificate raises the certified lower bounds to **23, 23, 28, 29** for p50/600, p75/600, p50/480, p75/480. The native CP-SAT lower bounds do not improve. None of the four full cases is proved optimal.

The weak initial assignment explains part of the search gap. The remaining certified absolute gaps are **11, 13, 13, 13**. This experiment does not establish a single operational constraint as the principal cause of the remaining gap.

## Controlled scope and preserved evidence

Started at `98427b194d63a077f3e3ca7ac6e3d73cf98cf93f` on `feat/mvp5-route10-engine-pilot`. The four original assignments and their artifacts under `outputs/integrated_v1_primary/` remain unchanged and independently valid. All four requests were regenerated from the SHA-locked workbook and frozen MVP-6A evidence and matched the saved requests exactly as JSON values.

- Workbook SHA-256: `8dc42690961b381b78e9f0e6be5f95803290501926d58a78ddaa1a74a9b9060b`.
- Frozen evidence SHA-256: `1029e84dc709a5918e213ba4529b1a133e07f3ad978de9c22cf6053381d22ce3`.
- 102 departures SHA-256: `d20e26cc05c48a9d4c06c4937b1fc97e835be24d9f7c0f7dda46849c19f257a9`.

Every run used OR-Tools 9.15.6755, one worker, seed 0, ten deterministic seconds, sixty emergency wall seconds, 1024 MB and the complete DAG (1,987 p50 / 1,978 p75 production edges). Eight full solves comprise the before/after pairs. Twenty explicitly relaxed diagnostic solves cover the two 600-minute scenarios. The 480-minute pairs were run only after p50/600 improved. There were no restarts, enlarged budgets, second heuristic, timetable changes or optimizer integration.

The original source was extracted from the starting SHA for the before runs. The full request and model constraint fingerprints match exactly in every before/after pair after removing hints. The original validated incumbent cutoff remains fixed at its V1 value; the corrected seed never tightens it. Only the hints and retained validated witness change. All four before runs reproduce the published final fleets, native lower bounds and deterministic work. Wall time varies with machine load.

## Diagnosis and one bounded correction

`_greedy()` has both suspected weaknesses: it sums all driving against the 240-minute continuous limit without processing resets, and rejects any extension with elapsed duty >= min(meal threshold, general-rest threshold), here 360 minutes. The latter applies even when those rules are disabled. This is conservative incumbent construction, not an extra restriction in the CP-SAT resource equations.

The new `_rest_aware_seed()` makes one chronological pass over compatible extensions of the existing complete DAG. It checks actual protected free intervals, continuous resets, elapsed and total driving, general rest and each meal window. It can extend a duty beyond 360 minutes or 240 total driving when a genuine protected reset and required meals make it legal. Every complete proposed seed passes the unchanged independent assignment validator before retention. An invalid seed is discarded. No heuristic decision removes a model edge or legal CP-SAT assignment.

Its deliberate limitation is that each appended prefix must already be legal as an ended duty; it does not search ahead through pending meal obligations or revise earlier assignments. This is a bounded initial assignment, not a new scheduling solver. The synthetic regression uses trips 480–660 and 705–885, a protected 670–700 break and lunch in its own window. The exact partition oracle and independent validator confirm one 415-minute duty with 360 total driving and 180 maximum continuous driving; the legacy seed uses two blocks.

## Before and after

All counts concern hypothetical fixed synchronized teams: one vehicle, duty, driver and attendant per block. Coverage is required-and-covered lunch / dinner / general rest; every required interval is covered. Initial A/B counts describe the selected witness and are not separately minimized terminal requirements.

The first validated fallback is still the legacy seed, because it is preserved to keep the original model cutoff identical. The subsequent corrected seed is the assignment supplied as hints. Both counts are shown so that the improved seed is not mislabeled as the first validation event. “Proven lower bound after” uses the new analytical certificate; the native solver bound is listed separately. The certificate also applies retrospectively to the identical before feasible set.

### p50 / 600

| Metric | Before | After |
|---|---:|---:|
| Proven lower bound | 21 | 23 (analytical) |
| Native CP-SAT lower bound | 21 | 21 |
| First validated feasible fleet (legacy fallback) | 52 | 52 |
| Validated initial assignment used as hints | 52 | 41 |
| First CP-SAT incumbent | 52 | 41 |
| Best validated fleet | 36 | 34 |
| Absolute optimality gap (best certified bound) | 15 | 11 |
| Absolute gap using native solver bound | 15 | 13 |
| Number of duties | 36 | 34 |
| Meal and rest coverage (L / D / G) | 20/20; 6/6; 24/24 | 20/20; 7/7; 23/23 |
| Maximum continuous driving, minutes | 234 | 234 |
| Initial A / B vehicle requirements | 20 / 16 | 21 / 13 |
| Deterministic solver work | 10.004335 | 10.000047 |
| Wall seconds | 41.568 | 24.418 |

### p75 / 600

| Metric | Before | After |
|---|---:|---:|
| Proven lower bound | 22 | 23 (analytical) |
| Native CP-SAT lower bound | 22 | 22 |
| First validated feasible fleet (legacy fallback) | 55 | 55 |
| Validated initial assignment used as hints | 55 | 43 |
| First CP-SAT incumbent | 55 | 43 |
| Best validated fleet | 36 | 36 |
| Absolute optimality gap (best certified bound) | 14 | 13 |
| Absolute gap using native solver bound | 14 | 14 |
| Number of duties | 36 | 36 |
| Meal and rest coverage (L / D / G) | 20/20; 9/9; 25/25 | 17/17; 6/6; 23/23 |
| Maximum continuous driving, minutes | 235 | 236 |
| Initial A / B vehicle requirements | 21 / 15 | 21 / 15 |
| Deterministic solver work | 10.000106 | 10.000103 |
| Wall seconds | 29.791 | 17.363 |

### p50 / 480

| Metric | Before | After |
|---|---:|---:|
| Proven lower bound | 26 | 28 (analytical) |
| Native CP-SAT lower bound | 26 | 26 |
| First validated feasible fleet (legacy fallback) | 52 | 52 |
| Validated initial assignment used as hints | 52 | 43 |
| First CP-SAT incumbent | 52 | 43 |
| Best validated fleet | 41 | 41 |
| Absolute optimality gap (best certified bound) | 15 | 13 |
| Absolute gap using native solver bound | 15 | 15 |
| Number of duties | 41 | 41 |
| Meal and rest coverage (L / D / G) | 14/14; 7/7; 24/24 | 10/10; 11/11; 24/24 |
| Maximum continuous driving, minutes | 234 | 234 |
| Initial A / B vehicle requirements | 20 / 21 | 19 / 22 |
| Deterministic solver work | 10.000002 | 10.000004 |
| Wall seconds | 17.633 | 16.141 |

### p75 / 480

| Metric | Before | After |
|---|---:|---:|
| Proven lower bound | 27 | 29 (analytical) |
| Native CP-SAT lower bound | 27 | 27 |
| First validated feasible fleet (legacy fallback) | 55 | 55 |
| Validated initial assignment used as hints | 55 | 43 |
| First CP-SAT incumbent | 55 | 43 |
| Best validated fleet | 44 | 42 |
| Absolute optimality gap (best certified bound) | 17 | 13 |
| Absolute gap using native solver bound | 17 | 15 |
| Number of duties | 44 | 42 |
| Meal and rest coverage (L / D / G) | 8/8; 8/8; 20/20 | 13/13; 2/2; 18/18 |
| Maximum continuous driving, minutes | 236 | 236 |
| Initial A / B vehicle requirements | 22 / 22 | 25 / 17 |
| Deterministic solver work | 10.000003 | 10.000069 |
| Wall seconds | 15.622 | 17.331 |

## Every validated fleet improvement

Each arrow below is an independently validated strict fleet improvement. The first native incumbent is shown explicitly. The compact evidence JSON retains every accepted rank improvement, total elapsed duty, witness digest and raw callback fields; complete intermediate witnesses remain in the ignored experiment records. There were no omitted improvements at equal fleet in these full runs.

- **p50_600, before:** legacy 52; first CP-SAT 52; native sequence 52 → 51 → 50 → 49 → 48 → 47 → 46 → 45 → 44 → 43 → 42 → 41 → 40 → 39 → 38 → 37 → 36; final 36; native lower 21.
- **p50_600, after:** legacy 52, corrected seed 41; first CP-SAT 41; native sequence 41 → 40 → 39 → 38 → 37 → 36 → 35 → 34; final 34; native lower 21.
- **p75_600, before:** legacy 55; first CP-SAT 55; native sequence 55 → 54 → 53 → 51 → 50 → 49 → 48 → 47 → 46 → 45 → 44 → 43 → 42 → 41 → 40 → 39 → 38 → 37 → 36; final 36; native lower 22.
- **p75_600, after:** legacy 55, corrected seed 43; first CP-SAT 43; native sequence 43 → 42 → 41 → 40 → 39 → 38 → 37 → 36; final 36; native lower 22.
- **p50_480, before:** legacy 52; first CP-SAT 52; native sequence 52 → 51 → 50 → 49 → 48 → 47 → 46 → 45 → 44 → 43 → 42 → 41; final 41; native lower 26.
- **p50_480, after:** legacy 52, corrected seed 43; first CP-SAT 43; native sequence 43 → 42 → 41; final 41; native lower 26.
- **p75_480, before:** legacy 55; first CP-SAT 55; native sequence 55 → 54 → 52 → 51 → 50 → 49 → 46 → 45 → 44; final 44; native lower 27.
- **p75_480, after:** legacy 55, corrected seed 43; first CP-SAT 43; native sequence 43 → 42; final 42; native lower 27.

Callback deterministic-time fields are preserved as reported by OR-Tools and repeat within each run; they are not asserted to be cumulative timestamps for improvements. Work comparisons use the final native response only.

## Independent analytical lower-bound certificate

For these requests every trip takes >=88 minutes (p50) or >=89 (p75), so three trips exceed the 240-minute continuous-driving limit. A continuous driving segment therefore holds at most two trips. Covering 102 trips requires at least 51 segments. With K duties there must be at least 51−K distinct resets, each with thirty continuous protected minutes between trips. These intervals exclude pre/post/technical tasks and cannot be counted twice.

Let W be driving workload (11,010 / 11,376), n=102, q=h=p=5 and H the elapsed-duty limit. Summing elapsed duties, with q only on internal connections, gives:

```text
sum(duty spans) >= W + n(q+h+p) − qK + 30(51−K)
H K >= W + 1530 − 5K + 1530 − 30K
K >= ceil((W+3060)/(H+35))
```

| Case | Numerator / denominator | Certified lower | Native CP-SAT lower | Best U | Certified gap |
|---|---:|---:|---:|---:|---:|
| p50_600 | 14070 / 635 | 23 | 21 | 34 | 11 |
| p75_600 | 14436 / 635 | 23 | 22 | 36 | 13 |
| p50_480 | 14070 / 515 | 28 | 26 | 41 | 13 |
| p75_480 | 14436 / 515 | 29 | 27 | 42 | 13 |

This is a necessary arithmetic certificate over every feasible assignment, not a heuristic estimate, native proof improvement or an additional CP-SAT constraint. The certificate code is confined to the diagnostic script. Exact-partition synthetic cases check that it never exceeds the independently enumerated optimum; the derivation and frozen-input arithmetic are subject to the independent technical review.

## Controlled constraint analysis: all rows below are relaxed diagnostics

Each staircase row adds only the named policy group. All keep departures and runtime definitions unchanged. Technical-only keeps q=5 but disables crew rules and sets pre/post=0; terminal-tasks restores pre/post=5. Elapsed duty also restores the redundant total-driving cap H. Continuous driving adds the 240/30 rule; general rest adds the 360/30 rule; lunch adds its original sustained eligibility; full additionally restores dinner. The full endpoint is the existing after600 run, not another optimization.

| Scenario | p50 native L / validated U | p75 native L / validated U | Proof |
|---|---:|---:|---|
| technical_only | 14 / 14 | 15 / 15 | Exact relaxed optimum |
| terminal_tasks | 16 / 16 | 16 / 16 | Exact relaxed optimum |
| elapsed_duty | 21 / 31 | 22 / 32 | Budget-limited relaxed result |
| continuous_driving | 21 / 34 | 22 / 35 | Budget-limited relaxed result |
| general_rest | 21 / 34 | 22 / 35 | Budget-limited relaxed result |
| lunch | 21 / 36 | 22 / 35 | Budget-limited relaxed result |
| full | 21 / 34 | 22 / 36 | Budget-limited; full endpoint is production policy |
| without_driving | 21 / 33 | 22 / 35 | Budget-limited relaxed result |
| without_general_rest | 21 / 34 | 22 / 38 | Budget-limited relaxed result |
| without_lunch | 21 / 35 | 22 / 34 | Budget-limited relaxed result |
| without_dinner | 21 / 36 | 22 / 35 | Budget-limited relaxed result |

`lunch` and `without_dinner` are the same request and reproduce the same result; their duplicate diagnostic runs are not pooled as extra optimization budget. Only the row labeled full supplies the primary fully constrained after result. A relaxed witness is never silently substituted into it.

What the evidence establishes:

- **Technical connections and terminal tasks:** exact matching/flow and native optima are 14/15 with technical-only connections, then 16/16 with terminal tasks. The extra tasks demonstrably increase the relaxed minimum by two/one vehicles. These are not integrated rosters.
- **Elapsed duty:** the independently derived workload floors 21/22 exceed the 16 task-only optimum, so the duty limit demonstrably rules out all 16-block assignments. Relaxed duty-only incumbents 31/32 are upper bounds, not necessary minima.
- **Continuous driving and protected resets:** the full-minus-driving witnesses meet all other declared rules but reach 330/340 continuous driving and fail independent full validation. The rule demonstrably excludes those assignments, and the reset-workload proof strengthens the certified full floors to 23/23. Overlapping feasible/proof ranges do not prove its exact incremental fleet cost or make it the principal remaining limitation.
- **General 30-minute rest:** it adds no existential assignment restriction for these frozen runtimes when continuous driving and whole-free-interval protection already apply. Without a >=30-minute free interval there is no reset, hence at most two trips and <=240 driving minutes. With integer free gaps <=29, such a duty spans at most 240+15+29+10=294 minutes, below the 360-minute threshold. Any duty reaching 360 therefore has a qualifying free interval that can be protected. This relies on the frozen zero reserve, task values and permitted whole-interval protection. Both no-general-rest witnesses pass full independent validation. Their different fleets reflect incomplete search.
- **Lunch and dinner eligibility:** full-minus-lunch witnesses fail specifically for missing required lunch (B002 in both runtime scenarios); full-minus-dinner witnesses fail specifically for missing required dinner (p50 B016 / p75 B018). Each rule demonstrably removes particular assignments. The remaining bounds overlap, so neither its minimum-fleet cost nor dominance is established. Thresholds/windows/overlap rules were not changed.

A useful search counterexample is p50: the fully constrained 34-block witness beats the relaxed lunch-only incumbent of 36. For p75, disabling general rest yields 38 while the full model finds 36, and that 38-block witness passes full validation. Feasible-set inclusion is monotone; bounded-search incumbents need not be. This prevents labeling the unresolved gap as constraint-dominant.

## Evidence, validation and reproduction

Compact checked evidence: [INTEGRATED_BLOCKING_V11_EVIDENCE.json](INTEGRATED_BLOCKING_V11_EVIDENCE.json). It records every production incumbent event, final metrics, matching constraint/request/runtime/policy fingerprints, relaxed-result labels, analytical arithmetic and source/artifact hashes. Complete private requests/witnesses remain under `outputs/integrated_gap_v11/`. Each recorded intermediate and final witness was independently revalidated against its own request. Relaxed witnesses were separately tried against the full request and the first precise rejection is recorded.

From the existing pilot worktree (original private artifacts required):

```powershell
$env:PYTHONPATH='src'
$env:PYTHONUTF8='1'
# Extract original source as bytes; use a fresh output directory for each experiment.
python -c "import subprocess,pathlib; pathlib.Path('outputs/original_solver.py').write_bytes(subprocess.check_output(['git','show','98427b194d63a077f3e3ca7ac6e3d73cf98cf93f:src/bus_schedule_engine/mvp/integrated_blocking.py']))"
python scripts/review_integrated_blocking_gap.py --frozen-results outputs/integrated_v1_primary/integrated_vehicle_crew_v1.json --output-dir outputs/gap_reproduction --phase before600 --original-solver outputs/original_solver.py
python scripts/review_integrated_blocking_gap.py --frozen-results outputs/integrated_v1_primary/integrated_vehicle_crew_v1.json --output-dir outputs/gap_reproduction --phase after600
python scripts/review_integrated_blocking_gap.py --frozen-results outputs/integrated_v1_primary/integrated_vehicle_crew_v1.json --output-dir outputs/gap_reproduction --phase constraints600
# Only after improved/clarified 600-minute results, the analogous before480 / after480 phases.
```

The runner refuses to overwrite an existing experiment record. It never resumes old checkpoints. The observer only inspects already validated retain calls and clones the model to fingerprint constraints without hints; a synthetic comparison checks that observation does not alter the solver result. The observer has an isolated test seam and is not imported by production.

Verification completed on 30 October 2026:

- Relevant integrated, crew-review, circulation, peak/off-peak, service-plan and Route 10 regressions: **202 passed, 4 skipped in 419.61 seconds**. The four skips are the older Route 6/10 acceptance workbook variables; the private Route 10 pilot workbook and frozen evidence were configured and checked.
- After adding the diagnostic arithmetic certificate, a fresh run of every integrated suite: **83 passed, no skips in 8.44 seconds**. The main seed regression was observed RED (five missing-helper failures) before implementation and GREEN after it.
- Repository Ruff lint, formatting of all four changed Python files, Contract V1 formatting (59 files) and `git diff --check` passed.
- An independent technical reviewer ran **35 synthetic tests**, checked all **28 saved results / 203 intermediate event witnesses**, verified ranks and first-native flags, compared every full request/constraint pair and the compact evidence, and freshly checked all **10 frozen file hashes**. The reviewer independently accepted the lower-bound derivation and general-rest redundancy proof. **No actionable findings; approved for commit and push.** The reviewer did not edit files or run further P0 optimization.

Experimental-policy satisfaction remains distinct from operational/statutory approval, as in V1. No claim of route infeasibility, global optimum or model-constraint dominance is made. This controlled experiment ends here.
