# Scenario C V4: Adaptive Regime Skeleton + Exact Repair

Status: design authority for the V4 implementation branch.

## 1. Problem statement

The V3 pipeline over-couples 30-minute demand observations to timetable structure. It first allocates exact trips to observation blocks, then attempts to recover exact uniform regimes and an operational timetable. Real-route MST6 trials showed repeated semantic friction: a plausible demand allocation could fail representability, B-shift reachability, source slicing, or necessary-feasibility checks before the exact timetable solver was allowed to solve.

V4 changes the decomposition.

**Demand observations are evidence, not timetable structure.**

The engine shall infer an adaptive demand shape and a small set of meaningful service-regime candidates, then use an exact solver to choose regime boundaries, integer headways and departure times while proving operational feasibility.

## 2. Core design principle

The engine is flexible about demand representation and strict about operations.

Adaptive / soft:
- demand smoothing;
- change-point selection;
- number and placement of ordinary service regimes;
- demand-fit error;
- preferred headway targets;
- B continuity inside the hard shift domain.

Hard / exact:
- total daily trip count in fixed-resource mode;
- direction-specific trip counts;
- source direction and terminal;
- one-to-one Scenario B trip to Scenario C trip traceability;
- exact Scenario B runtime per source trip;
- first/last departure locks when the profile requires them;
- absolute Scenario B departure shift <= 30 minutes;
- fleet ceiling;
- operational turnaround / layover;
- protected service floors;
- whole-minute departures;
- exact uniform integer headway inside every service regime;
- final-tail policy;
- independent validation.

## 3. Scenario A

Scenario A is not required for B -> C optimization. V4 authority is Scenario B + demand + operating policy. Scenario A may be used only as optional historical/comparison evidence and must not alter B-anchored feasibility authority.

## 4. Demand evidence model

### 4.1 Observation grain is not regime grain

Input demand may be raw transactions or aggregated 15/30/60-minute intervals. The engine shall normalize all evidence into a time-indexed demand-rate representation while preserving source-period provenance and confidence.

A 30-minute input interval does **not** imply a 30-minute service regime and does not create a hard trip-count target.

### 4.2 Normalized demand curve

For each demand profile, derive a deterministic curve using observation overlap. A simple production-safe baseline is piecewise-constant demand rate inside each source interval, optionally followed by deterministic smoothing that cannot invent volume.

Required properties:
- preserve total passenger volume;
- preserve period/profile fingerprints;
- deterministic output;
- no interpolation presented as measured evidence;
- support combined-demand authority and direction-resolved demand.

### 4.3 Cross-period stability

When several source periods are available, change-point confidence should increase when the same shape change appears consistently across periods and decrease when a spike is isolated/noisy. The stable multi-period profile therefore informs both average demand level and structural confidence.

## 5. Adaptive demand segmentation

V4 shall infer candidate demand change points rather than treating every observation boundary as structural.

Preferred implementation characteristics:
- deterministic dynamic-programming or change-point segmentation;
- explainable cost function;
- no trained black-box model;
- penalty for additional segments;
- penalty for very short segments;
- reward only when a change materially improves fit to the demand curve.

A conceptual segmentation score is:

```text
segmentation_cost = demand_fit_error
                  + lambda_regime * number_of_segments
                  + lambda_short * short_segment_penalty
                  + lambda_instability * cross_period_instability
```

The implementation may use an equivalent deterministic formulation.

The segmentation output shall contain **boundary windows / candidate regions**, not over-precise claims that demand changes at an exact minute unsupported by the input evidence.

## 6. Service-regime skeleton

The demand segmentation produces one or more service-regime skeleton candidates.

A skeleton describes:
- ordered regime topology;
- approximate boundary windows;
- demand intensity / trend per regime;
- preferred headway range or service intensity;
- confidence;
- final-tail marker when applicable.

It does **not** prescribe exact departure times or exact trips per 30-minute observation bucket.

### 6.1 Regime count

The engine should use the smallest number of regimes that explains demand and produces an attractive timetable.

Policy:
- normal search should favor 3-8 regimes per direction/service span;
- expansion above 8 requires evidence that a simpler skeleton materially worsens demand/service quality or exact feasibility;
- 16 remains an absolute safety ceiling, never a target;
- short-lived ordinary regimes are strongly penalized;
- first shoulder and final tail may be shorter when justified.

## 7. Exact uniform-headway authority

Inside each service regime `r`, every consecutive departure gap is identical:

```text
C[i+1] - C[i] = H[r]
H[r] is a positive integer number of minutes
```

Approximate uniformity is invalid. Patterns such as 10/11/10 minutes may not be represented as one regime.

If a candidate regime is not exactly representable, the allowed remedies are:
1. choose another regime boundary within its candidate window;
2. choose another integer headway;
3. choose another skeleton candidate / merge or split where demand evidence justifies it;
4. reject the candidate.

Do not hide irregular gaps inside a nominally uniform regime.

## 8. Exact solver formulation

The exact solver should operate on the ordered Scenario B trip sequence directly instead of first converting demand blocks into exact trip allocations.

For each direction, let B trips be ordered `j = 0..N-1` and Scenario C departures be integer variables `t[j]`.

Core hard domains:

```text
B[j] - 30 <= t[j] <= B[j] + 30
first/last locks as configured
t[j+1] > t[j]
arrival[j] = t[j] + exact_source_runtime[j]
```

A regime skeleton defines candidate transition windows. The exact solver chooses which adjacent trip gap becomes each regime transition. Within a regime, all internal gaps equal one integer headway variable `H[r]`.

This formulation avoids requiring a precomputed `(end-start) % (n-1) == 0` witness. Exact representability is created directly by the departure variables and uniform-gap constraints.

## 9. Combined demand with fixed direction counts

For `COMBINED_DEMAND_FIXED_DIRECTION_COUNTS`:
- combined demand controls time-of-day service intensity and regime topology;
- outbound and inbound daily totals remain fixed to Scenario B;
- direction split is not inferred from combined passenger counts;
- Scenario B directional continuity may be used as a soft prior only;
- shared/near-shared boundary topology is preferred for interpretability, but exact directional representability may justify bounded directional boundary differences.

## 10. Headway attractiveness policy

The user-facing service goal is the shortest practical waiting time.

Preferred quality bands:
- `H <= 10 min`: excellent / strongly preferred;
- `10 < H <= 15 min`: good / preferred;
- `H > 15 min`: progressively penalized;
- longer headways are allowed when trip count, fleet, route runtime/distance, service span, or other hard constraints make 10-15 minutes infeasible.

`H <= 10` and `H <= 15` are **not** blanket hard constraints.

The engine shall compute a resource feasibility envelope before optimization, including theoretical trip-count and fleet lower bounds for 10- and 15-minute service. The final result must explain when a desired service band is impossible because of binding resources.

## 11. Passenger-weighted service quality

With fixed total trips, minimizing all headways simultaneously is impossible. V4 should rank service placement using passenger-weighted waiting / service shortage rather than symmetric absolute error to a per-block trip target.

A suitable approximation is proportional to:

```text
passenger_wait_cost ~= passenger_volume * headway / 2
```

The exact implementation may use demand-overlap integration or an equivalent deterministic score.

High-demand periods therefore receive greater benefit from shorter headways, while a separate attractiveness penalty prevents extreme low-demand gaps from becoming operationally unattractive.

## 12. Final-tail policy (hard)

The existing tail-end authority remains mandatory.

Requirements:
- last departure remains locked to Scenario B when the profile requires it;
- final-tail maximum headway remains bounded by the configured tail ceiling (default 60 minutes);
- when final-tail demand is non-increasing / not rising, the final-tail headway may not be shorter than the preceding measurable regime headway:

```text
H_tail >= H_previous
```

Tail non-densification is a hard constraint, not an objective trade-off.

The V4 implementation should reuse the existing tail-demand classification semantics unless a separate reviewed change explicitly replaces them.

## 13. Transition smoothness

Regime changes must remain operationally understandable.

Hard authority for the current fixed-resource policy:
- Scenario C maximum adjacent regime-headway jump may not exceed Scenario B's observed maximum relevant headway jump.

Optimization preference:
- minimize maximum transition jump;
- then minimize total transition change;
- avoid oscillating frequency patterns unless demand evidence strongly requires them.

## 14. Fleet and operations

Fleet/vehicle feasibility remains exact.

Hard checks include:
- exact runtime per source trip;
- terminal/vehicle occupancy where authoritative;
- minimum layover / turnaround;
- fleet required <= fleet available;
- preserved source direction and terminal identity.

For known route classes, minimum driver/vehicle turnaround remains policy authority (for example 5 minutes intra-provincial and 15 minutes inter-provincial where applicable).

## 15. Quality vector and candidate ranking

Do not optimize for `C=True` alone. Feasible candidates shall be ranked deterministically.

Recommended quality order:
1. hard feasibility / protected service;
2. no-service, critical and planning shortage avoidance;
3. passenger-weighted waiting / demand fit;
4. service unattractiveness above 15 minutes;
5. service unattractiveness above 10 minutes;
6. regime parsimony and short-regime avoidance;
7. transition smoothness;
8. preferred B continuity / shift <=15 minutes;
9. total and maximum B shift inside the hard <=30-minute domain.

The implementation may use lexicographic stages or a bounded deterministic composite, but the result payload must expose the component scores separately.

## 16. Resource feasibility envelope

Before exact search, compute diagnostics such as:

```text
average_headway_if_uniform = service_span / (direction_trips - 1)
minimum_trips_for_15 = ceil(service_span / 15) + 1
minimum_trips_for_10 = ceil(service_span / 10) + 1
approx_fleet_for_H = ceil(cycle_time / H)
```

These are diagnostics / necessary lower bounds, not substitutes for the exact fleet solver.

Report which resource is likely binding:
- trip count;
- fleet;
- runtime/cycle time;
- locked service span;
- protected floors;
- B-shift domain.

## 17. Independent validator

The validator must independently recompute from the final C timetable:
- trip totals and direction totals;
- first/last locks;
- B shift per trip;
- exact runtimes;
- fleet / turnaround;
- protected floors;
- regime boundaries and exact internal uniformity;
- transition jumps;
- final-tail non-densification and tail ceiling;
- demand/service quality metrics.

The validator must not validate by trusting solver-side cached witnesses.

## 18. Status semantics

Suggested final states:
- `FINAL_RECOMMENDED`: valid C and materially preferable to B;
- `VALID_CANDIDATE_NOT_FINAL`: valid C exists but product-quality/selection gate is not met;
- `KEEP_SCENARIO_B`: B is preferable to all valid C candidates;
- `NO_SAFE_C_WITHIN_SOLVE_BUDGET`: no valid C found within the bounded search budget;
- `PROVEN_HARD_INFEASIBILITY`: only when an exact or independently sufficient proof exists.

All attempted candidate skeletons failing does not automatically prove global infeasibility.

## 19. Solve budget

Keep the ordinary total solve budget at 120 seconds for production pilots.

Do not increase it to mask structural/semantic problems. Consider budget changes only when:
- exact Stage 2 / exact repair is genuinely running;
- the total budget is exhausted;
- diagnostics show search time, not pre-check semantics, is the blocker.

Prefer better candidate ordering, warm hints, bounded skeleton enumeration and Stage allocation before increasing the total cap.

## 20. Reuse vs retire

### Reuse from V3 where possible
- workbook import and multi-period demand provenance;
- Scenario B exact timetable normalization;
- demand-profile derivation and fingerprints;
- runtime/fleet/turnaround models;
- protected-service authority;
- result export infrastructure;
- independent validation patterns;
- tail-demand classification semantics;
- deterministic serialization/fingerprints.

### Do not carry forward as V4 authority
- exact Stage-1 trip allocation by 30-minute demand block;
- block-level bounded-phase logic as a production requirement;
- source slicing derived from exact analytical-block allocation;
- regime builders that must repair a precommitted block allocation;
- necessary-feasibility checks that reject one witness when the exact solver has a wider legal domain.

V3 remains intact for regression/reference. V4 is an opt-in path until MST6 and MST10 acceptance is complete.

## 21. Implementation sequence

### Milestone V4.1 — Demand shape + skeleton only
Produce deterministic adaptive demand segmentation and 3-8 regime skeleton candidates for MST6. No timetable mutation yet.

Acceptance:
- 30-minute input boundaries do not mechanically become regimes;
- peak/base/tail structure is explainable;
- candidate count bounded;
- output is fingerprinted and tested.

### Milestone V4.2 — Exact uniform-regime repair
Given a skeleton, solve exact departure times with integer uniform headways, B +/-30, first/last locks, exact runtime and fixed trip counts.

Acceptance:
- at least one synthetic and one MST6 skeleton reaches the exact solver;
- no approximate internal headways;
- no block-allocation compatibility adapter.

### Milestone V4.3 — Fleet + protected + tail + transition authority
Integrate all hard operating constraints and independent validator.

### Milestone V4.4 — Product quality ranking/export
Add passenger-weighted quality, 10/15-minute attractiveness, regime parsimony, resource-envelope explanation, B comparison and final acceptance state.

### Milestone V4.5 — Real-route gates
1. MST6 stable profile;
2. MST6 profile sensitivity;
3. MST10 stable profile;
4. MST10 profile sensitivity.

Do not merge V4 to main before real-route product review.

## 22. MST6 product acceptance gate

A production-ready MST6 C must:
- pass the independent validator;
- preserve 156 total trips and 78 per direction;
- respect fleet and all operating constraints;
- respect B +/-30 and exact runtime;
- use exact integer-uniform headways inside each regime;
- keep the final tail non-densifying when demand is not rising;
- keep maximum transition jump no worse than B;
- use materially fewer than the prior pathological 16 regimes per direction unless evidence proves otherwise;
- produce an operationally coherent full-day headway sequence;
- allocate shorter headways toward higher passenger demand;
- explain any headway above 15 minutes through demand/resource trade-offs;
- avoid gratuitous source-trip shifts;
- be preferable to B on the declared quality vector, otherwise return `KEEP_SCENARIO_B`.

## 23. Research branch disposition

PR #57 (`fix/v3-global-regularity-product`) is retained as research evidence and must not be merged while V4 is being evaluated. Its failures and fixes motivated this redesign but its adapter stack is not the V4 foundation.
