# Two-Stage Uniform-Regime Scenario C Optimization V1

**Status:** implementation specification

**Target repository:** `longpsu-bot/bus-schedule-optimizer`

**Implementation intent:** replace the current “single large search” mental model for fixed-resource Scenario C with an explicit two-stage optimization workflow:

1. determine how many trips should serve each demand interval / service regime;
2. place the exact departure times inside those regimes under strict operational constraints.

This document is implementation authority for the new workflow. Existing Contract V1 behavior must remain backward compatible unless this document explicitly requires a new versioned mode or profile.

---

## 1. Product decision

Scenario C is a **B-anchored fixed-resource redistribution**.

The optimization question is not “invent a new timetable from scratch.” It is:

> Starting from Scenario B, keep the authorized operating resources and operating parameters, determine where the existing trips should be allocated according to observed demand, then place those trips into exact departure times that are operationally feasible and internally regular.

For this workflow:

- Scenario B is the source timetable and source-trip authority.
- Observed passenger demand is the demand authority.
- Scenario A is optional context and must not be required merely because demand exists.
- Scenario C preserves one-to-one source traceability to Scenario B.
- Scenario C preserves the authorized trip total and, unless a separately versioned capability explicitly allows otherwise, the Scenario B trip count by direction.
- Scenario C must not exceed Scenario B's available fleet constraint.
- Per-trip runtime remains locked to the Scenario B source trip.
- Arrival-terminal turnaround remains a hard constraint.

Do not remove Scenario A support from the existing evaluation workflow. Instead add a B-anchored optimization mode in which A is optional.

Recommended mode/profile names:

- optimization mode: `B_ANCHORED_TWO_STAGE_REBALANCE_V1`
- regime policy profile: `scenario_c_uniform_integer_regime_policy_v3`

The V3 profile is intentionally new. Do **not** silently reinterpret `scenario_c_balanced_regime_policy_v2`, because V2 currently accepts balanced-rounding sequences such as 6/7 or 10/11 minutes. The new policy requires exact uniformity inside a regime.

---

## 2. Mandatory time semantics

### 2.1 Whole-minute alignment

All generated Scenario C departure times must be minute-aligned:

```text
HH:MM:00
```

Examples:

```text
06:00:00
06:06:00
06:13:00
```

No generated departure may contain non-zero seconds.

In integer-minute solver space this means every departure variable is an integer minute. In second-based public contracts or artifacts:

```text
c_departure_time % 60 == 0
```

The phrase “phút chẵn” in this specification means **whole-minute aligned**, not “an even-numbered minute.” Both 6-minute and 7-minute headways are valid integers.

### 2.2 Strict uniform headway inside a regime

Within one final Scenario C service regime, every internal headway must be exactly the same integer number of minutes.

For regime `r` with ordered departures:

```text
x[r,1], x[r,2], ..., x[r,n]
```

there must be one integer variable / value:

```text
h[r] >= 1 minute
```

such that:

```text
x[r,j+1] - x[r,j] == h[r]
```

for every adjacent pair inside the regime.

Valid examples:

```text
06:00, 06:06, 06:12, 06:18      -> 6, 6, 6
07:00, 07:07, 07:14, 07:21      -> 7, 7, 7
```

Invalid examples under V3:

```text
06:00, 06:06, 06:13, 06:19      -> 6, 7, 6
07:00, 07:10, 07:21, 07:31      -> 10, 11, 10
```

Balanced rounding is not accepted inside a V3 regime.

### 2.3 Transition headways

A headway crossing from one final regime to another is a transition headway.

Transition headways:

- are not internal members of either regime's uniformity equation;
- remain visible in metrics and artifacts;
- remain subject to a bounded transition-jump policy;
- must never be used to hide an irregular internal headway by arbitrary regime fragmentation.

The final regime partition must therefore remain bounded and materially justified.

---

## 3. Consequence of strict uniformity: representability must move upstream

Under V2 a span may be represented with floor/ceil balanced rounding. V3 removes that escape hatch.

For a regime with:

- first departure `s`;
- last departure `e`;
- trip count `n >= 2`;

strict uniformity requires:

```text
(e - s) / (n - 1)
```

to be a positive whole number of minutes.

Equivalently:

```text
(e - s) % (n - 1) == 0
```

when the span is expressed in minutes.

Therefore Stage 1 must not emit a regime definition that Stage 2 cannot represent exactly.

If a demand interval and proposed trip count are not exactly representable, the system must use one of these deterministic mechanisms, in this order:

1. move the service-regime boundary within an explicit bounded boundary tolerance;
2. choose a neighboring feasible trip count if demand-service constraints still permit it;
3. merge or split regimes only when material demand-change and minimum-regime rules permit it;
4. otherwise declare the proposed allocation unrepresentable and continue searching for another Stage 1 allocation.

Do **not** reintroduce 6/7, 10/11, or other floor/ceil alternation as a hidden fallback.

Add a policy field such as:

```text
maximum_regime_boundary_adjustment_minutes
```

with a conservative default. Reuse an existing equivalent field only if its semantics are genuinely identical and the resulting fingerprints remain explicit.

---

## 4. Two-stage solver architecture

The authoritative fixed-resource optimization pipeline becomes:

```text
Normalized inputs
    -> Scenario B evaluation
    -> adjustment decision
    -> Stage 1 allocation optimization
    -> canonical representable service-regime plan
    -> Stage 2 exact-timetable optimization
    -> independent Contract V1 validation
    -> compare C against B
    -> final acceptance state
```

The two stages share one total wall-clock solve budget.

### Stage 1 — Trip allocation / service-rate solve

Purpose:

> Decide how many existing B trips should serve each demand interval or candidate service regime.

Stage 1 should operate on small integer allocation variables rather than exact departure timestamps wherever possible.

Suggested variables:

```text
n[d,k] = number of trips assigned to direction d and demand/service block k
```

where `d` is outbound/inbound and `k` is an authoritative demand interval or derived contiguous candidate regime unit.

Required hard constraints:

```text
sum_k n[outbound,k] == B outbound trip count
sum_k n[inbound,k]  == B inbound trip count
n[d,k] >= 0 integer
```

Additional protected-service-floor constraints must remain authoritative.

Stage 1 must derive / validate representable regime candidates under Section 3 before a plan can be passed to Stage 2.

Stage 1 objective priority should be small and explicit:

1. eliminate positive-demand intervals with no service where fixed resources can avoid them;
2. minimize critical demand shortage;
3. minimize planning demand shortage;
4. minimize demand-allocation error;
5. preserve Scenario B allocation as a continuity tie-break when demand does not justify a material change.

Avoid reproducing all exact-timetable quality metrics in Stage 1.

Stage 1 output should be a versioned immutable contract, for example:

```text
TripAllocationPlanV1
    source_b_fingerprint
    demand_authority_fingerprint
    total_trips
    trips_by_direction
    allocation_blocks[]
    proposed_regimes[]
    objective_vector
    solve_status
    solve_duration_seconds
    allocation_fingerprint
```

Each proposed regime should carry at least:

```text
regime_id
direction
covered_demand_block_ids
trip_count
permitted_start_window
permitted_end_window
minimum_headway_minutes
maximum_headway_minutes
boundary_reason
```

Do not assign exact source B trip IDs to final minute positions during Stage 1 unless necessary for protected-floor authority. Exact source mapping remains Stage 2 responsibility.

### Stage 2 — Exact timetable solve

Purpose:

> Given a fixed Stage 1 trip allocation and representable regime plan, place each Scenario B source trip at one exact Scenario C departure minute while satisfying all operational constraints.

For every source B trip `i`, create one integer-minute departure variable:

```text
x[i]
```

Scenario C remains one-to-one with B:

```text
B trip i -> exactly one C trip i
```

No trip creation or deletion occurs in this workflow.

---

## 5. B-anchored departure domains

The current broad `first_departure <= x[i] <= last_departure` domain is too permissive for production optimization.

Add a hard per-trip maximum shift from Scenario B:

```text
B[i] - absolute_max_shift <= x[i] <= B[i] + absolute_max_shift
```

intersected with the route service window and any regime membership window.

Recommended existing policy reuse:

```text
preferred_max_shift_per_trip_minutes = 15
absolute_max_shift_per_trip_minutes = 30
```

The absolute maximum is a hard domain bound.

The preferred maximum may be used as a soft penalty / secondary objective if desired.

Scenario B departure times should continue to be supplied as CP-SAT hints.

Do not use the hint as a substitute for the hard maximum-shift domain.

---

## 6. Stage 2 hard constraints

The exact-timetable model must enforce all of the following.

### 6.1 Source identity and counts

- exact one-to-one source B -> C mapping;
- total daily trip count fixed to B;
- directional trip counts fixed to B in this V1 workflow;
- source direction fixed;
- source departure terminal fixed;
- source runtime fixed.

### 6.2 First / last departure policy

Preserve current first/last departure locks unless a separately versioned configuration explicitly authorizes bounded movement.

Default V1 behavior:

```text
first C departure by direction == first B departure by direction
last C departure by direction  == last B departure by direction
```

If future flexibility is required, implement it as a new policy with explicit tolerances and fingerprints. Do not silently relax these locks.

### 6.3 Strict source order

For ordered source trips in a direction:

```text
x[i+1] > x[i]
```

Use an operational minimum headway rather than the current technical 1-minute separation when policy provides one.

Add a hard field such as:

```text
minimum_operational_headway_minutes
```

This must be a positive integer minute value.

Do not infer an aggressive value from demand. It is a safety / operational quality floor.

### 6.4 Uniform regime equations

For every final Stage 1 regime `r`, introduce one integer headway:

```text
h[r]
```

and enforce:

```text
h[r] >= minimum_operational_headway_minutes
```

plus any regime-specific maximum derived from service requirements or protected floors.

Every adjacent departure pair whose two trips are internal members of `r` must satisfy:

```text
x[j+1] - x[j] == h[r]
```

No tolerance of ±1 minute is allowed under V3.

### 6.5 Allocation membership

Stage 2 must reproduce the exact Stage 1 trip count assigned to every regime / allocation block.

It must not silently move a trip into another regime to make the timetable easier.

If exact placement is impossible, Stage 2 returns infeasible for that allocation plan and orchestration may try the next bounded Stage 1 plan if the global budget remains.

### 6.6 Runtime and arrival

For every source B trip `i`:

```text
C arrival[i] = C departure[i] + B source runtime[i]
```

Per-trip runtime is a hard source lock.

Do not replace exact source runtime with one route-average runtime during authoritative validation.

### 6.7 Arrival-terminal turnaround

Vehicle reuse must respect the exact turnaround at the terminal where the vehicle arrives.

The existing regulatory floor remains hard:

- intra-provincial route: at least 5 minutes;
- inter-provincial route: at least 15 minutes.

If the Scenario B source defines a larger valid turnaround, preserve the authoritative configured value.

### 6.8 Fleet

Scenario C must satisfy:

```text
minimum_required_fleet(C) <= B.available_fleet_limit
```

Preserve exact Contract V1 fleet-assignment validation as final authority.

### 6.9 Terminal occupancy

Existing terminal occupancy limits remain hard when supplied.

### 6.10 Protected service floors

Existing protected-service-floor authority remains hard.

For a protected regime, the new uniform headway must also respect:

```text
h[r] <= maximum_future_c_headway_minutes
```

where applicable.

Protected membership, donor prohibition, service window, trip-count and boundary authority must not be weakened by the two-stage refactor.

---

## 7. Final Service Tail Policy

The end of the operating day requires separate treatment because a purely demand-minimizing allocation can otherwise pull late trips earlier and leave passengers with little or no practical opportunity to board near the published end of service.

### 7.1 Policy intent

For each direction, the final portion of the service day should form a deliberate **final-service tail regime** anchored to the locked last departure.

The intended behavior is:

- preserve the final departure exactly by default;
- preserve meaningful service coverage through approximately the final hour of operation;
- avoid bunching the last several trips too early merely to improve demand or shift objectives;
- allow the final regime to use a **longer uniform headway** than the preceding normal regime when demand is lower and this helps extend service opportunities toward the end of the day;
- keep that longer headway perfectly uniform inside the final regime;
- never interpret “longer final headway” as permission for an unbounded or passenger-hostile final gap.

The product goal is not to maximize late headway. It is to **spread the remaining trips through the end of service** so passengers arriving late still have a reasonable opportunity to catch a bus.

### 7.2 Versioned policy fields

Introduce explicit fields rather than hiding this behavior in objective weights. Suggested fields:

```text
final_service_tail_window_minutes = 60
final_service_tail_minimum_trip_count = 2
final_service_tail_maximum_headway_minutes = <policy value>
prefer_final_tail_headway_not_shorter_than_previous_regime = true
```

If the existing `final_service_block_minutes` field is reused, first verify that its semantics are exactly the same. If not, keep it for backward compatibility and add the new fields under the V3 profile.

The default `60` is a planning target for the final protected service window, not a requirement that every route always have a regime exactly 60 minutes long.

### 7.3 Stage 1 requirements

Stage 1 must reserve enough late-day allocation for a representable final regime when the service day contains at least two departures in the final-tail area.

The final regime must:

- be the last regime in the direction;
- include the locked last departure;
- contain at least `final_service_tail_minimum_trip_count` trips when feasible;
- be representable with one exact whole-minute headway;
- preferentially span a substantial portion of `final_service_tail_window_minutes` rather than compressing all final-regime trips near its start;
- remain demand-aware: a strong verified late peak may justify a shorter final headway, but low late demand must not cause the tail to disappear.

Do not sacrifice protected high-demand service elsewhere solely to satisfy the tail preference. Hard safety/fleet/protected-service constraints remain higher authority.

### 7.4 Stage 2 equations

Let the final regime in a direction contain `n >= 2` trips with uniform headway `h_final` and locked last departure `L`.

Then:

```text
x_final[j+1] - x_final[j] == h_final
x_final[n] == L
```

and therefore:

```text
x_final[1] == L - (n - 1) * h_final
```

This relationship should be used for propagation rather than allowing each final-tail trip to float independently.

When policy and demand allow, prefer:

```text
h_final >= h_previous_regime
```

as a **soft preference**, not a universal hard constraint.

The hard upper bound remains:

```text
h_final <= final_service_tail_maximum_headway_minutes
```

plus any stricter protected-service or service-gap constraint.

### 7.5 Acceptance checks

A final candidate must not be marked `FINAL_RECOMMENDED` if it exhibits any of the following without an explicit policy-authorized exception:

- last departure moved earlier than the locked B last departure;
- no service coverage through the configured final-tail area despite enough fixed trips to provide it;
- final-tail trips compressed materially earlier while leaving an avoidable long gap before the last departure;
- non-uniform internal final-regime headways;
- final headway above the configured final-service maximum;
- final-tail behavior that violates fleet, turnaround, terminal occupancy or protected-service floors.

Expose final-tail metrics in the solution/report:

```text
final_tail_start
final_tail_end
final_tail_span_minutes
final_tail_trip_count
final_tail_uniform_headway_minutes
minutes_from_penultimate_trip_to_last_departure
```

---

## 8. Exact uniformity versus demand blocks

Demand blocks and service regimes are related but not identical concepts.

A demand block describes evidence.
A service regime describes the timetable pattern.

Do not force every hourly demand block to become exactly one regime.

The regime builder may merge adjacent demand blocks when:

- demand/service-rate difference is not material;
- the merged regime remains representable with one exact integer-minute headway;
- protected floors permit the merge;
- minimum/maximum regime-count policies permit it.

The builder may place a regime boundary near, but not exactly on, a demand-block boundary when this is required for exact integer-headway representability and the boundary shift stays within the configured tolerance.

Example:

A 50-minute nominal span with 4 trips implies 16.666... minutes and is not V3 representable.

Valid outcomes include:

- adjust the service-regime span to 48 minutes -> 16,16,16;
- adjust it to 51 minutes -> 17,17,17;
- choose a different trip count if demand constraints allow;
- merge/split with a neighboring interval if justified.

Invalid outcome:

```text
16,17,17
```

inside one regime.

---

## 9. Combined two-direction demand mode

The engine must distinguish demand authority from timetable direction locks.

When authoritative demand is directional, Stage 1 may optimize `n[outbound,k]` and `n[inbound,k]` directly.

When demand is combined across both directions, do not fabricate a 50/50 split or claim directional passenger evidence that does not exist.

Add a separately identified mode such as:

```text
COMBINED_DEMAND_FIXED_DIRECTION_COUNTS
```

In this mode:

- total B outbound trips remain fixed;
- total B inbound trips remain fixed;
- combined demand determines the desired total service by time block;
- Scenario B directional distribution by time may be used only as a continuity prior / tie-breaker;
- generated artifacts must state that the demand source did not support directional passenger inference.

Stage 1 can therefore constrain / optimize:

```text
n[outbound,k] + n[inbound,k]
```

against combined demand while preserving daily directional totals.

This mode must be explicit in fingerprints and limitations. It must not masquerade as full directional demand authority.

---

## 10. Solver objective design

Do not require fifteen separate CP-SAT solves merely because the quality vector contains fifteen metrics.

Keep the detailed solver-neutral quality vector for evaluation and comparison, but group native optimization into a small number of lexicographic stages.

Recommended Stage 2 priorities:

### Objective group 1 — hard demand/service protection

Prefer converting genuine non-negotiable requirements into hard constraints in Stage 1. Remaining optimization should prioritize:

```text
no-service deterioration
critical shortage deterioration
planning shortage deterioration
```

### Objective group 2 — passenger service continuity

Minimize:

```text
maximum positive-demand service gap
total positive-demand block max gap
```

### Objective group 3 — regime and transition quality

Internal V3 regime variation is already zero by hard constraint.

Optimize only remaining transition behavior, for example:

```text
maximum regime transition jump
total regime transition jump
final-tail coverage quality
```

### Objective group 4 — preserve B

Minimize:

```text
shifted trip count
total absolute shift minutes
maximum shift minutes
preferred-shift exceedance
```

Use deterministic bounded weights only within a group. Preserve true lexicographic priority between groups.

Document weight bounds and prove that lower-priority terms cannot dominate higher-priority terms if weighted aggregation is used.

---

## 11. Solve budgets and termination

Ordinary application execution already has a finite OR-Tools total budget. Preserve that principle.

The new two-stage workflow must use one explicit total wall-clock budget, for example the existing ordinary 120-second default.

Suggested orchestration:

```text
total_budget = policy.time_limit_seconds
stage_1 receives a bounded share / remaining budget
stage_2 receives only the remaining budget
validation and comparison occur outside the CP-SAT search budget but remain bounded application work
```

Do not give every objective group a fresh full budget.

If Stage 1 cannot produce any admissible allocation within its budget:

```text
C_NOT_FOUND_WITHIN_SOLVE_LIMIT
```

If Stage 1 produces an allocation but Stage 2 cannot prove or find a timetable within the remaining budget, preserve the strongest truthful status:

- proven infeasible allocation -> reject that allocation and try the next bounded Stage 1 plan if budget remains;
- timeout with no timetable -> unknown / not found within solve limit;
- feasible timetable found -> pass it to independent validation and final acceptance.

No automatic unbounded rerun is permitted.

---

## 12. Final candidate acceptance policy

A solver-produced candidate is not automatically the product-final Scenario C merely because CP-SAT returned `FEASIBLE`.

Add a versioned final-acceptance layer after independent domain validation.

Suggested states:

```text
FINAL_RECOMMENDED
VALID_CANDIDATE_NOT_FINAL
KEEP_SCENARIO_B
NO_FINAL_C_WITHIN_SOLVE_BUDGET
```

`FINAL_RECOMMENDED` requires all hard/domain checks to pass and must include at least:

- exact trip count and directional count locks;
- exact source runtime and turnaround feasibility;
- fleet and terminal occupancy feasibility;
- whole-minute departures;
- strict uniform internal headway in every V3 regime;
- final-service-tail checks;
- protected-service-floor checks;
- no deterioration of high-priority demand protection relative to B;
- any configured maximum service-gap / transition ceilings;
- absolute per-trip shift limits.

Then compare the solver-neutral C quality vector to the B vector.

If C is not materially better than B under the approved comparison policy:

```text
KEEP_SCENARIO_B
```

Do not emit a changed timetable merely because a different feasible one exists.

If C is valid and better on some dimensions but does not meet final product thresholds:

```text
VALID_CANDIDATE_NOT_FINAL
```

Do not automatically rerun indefinitely.

---

## 13. Scenario A optionality for B-anchored optimization

Current Contract V1 associates observed demand with Scenario A and can reject `demand + no A`.

Do not globally remove that provenance model.

Instead version the authority semantics for B-anchored optimization so that observed demand may be attached to a route/time period independently of requiring an exact Scenario A timetable.

Requirements:

- existing A/B evaluation paths remain unchanged;
- B-anchored optimization accepts `scenario_a=None` when all other route, demand and B authorities are valid;
- demand provenance remains explicit and fingerprinted;
- do not invent Scenario A to satisfy validation;
- no weakening of demand-period, confidence, resolution or coverage checks.

The implementation must include regression tests for:

```text
B + valid demand + no A -> valid for B-anchored optimization mode
B + demand + no A -> existing legacy/A-bound mode behavior remains unchanged
```

---

## 14. Search-space controls

The implementation must intentionally reduce CP-SAT search space.

Required controls:

1. integer-minute departure variables only;
2. B ± absolute shift domain intersection;
3. fixed source order;
4. fixed Stage 1 regime membership/counts during Stage 2;
5. one headway variable per regime, with equality equations for internal pairs;
6. first/last departure locks by default;
7. B timetable hints;
8. bounded regime count;
9. bounded regime-boundary movement;
10. bounded number of Stage 1 alternative allocation plans passed to Stage 2;
11. final-tail propagation anchored at the last departure.

Add diagnostics for at least:

```text
stage_1_candidate_count
stage_1_admissible_allocation_count
stage_2_allocation_attempt_count
stage_2_variable_count
stage_2_constraint_count
regime_count_by_direction
solve_duration_stage_1
solve_duration_stage_2
total_solve_duration
```

These diagnostics are needed to tune real-route performance without guessing.

---

## 15. Versioning and migration constraints

This change intentionally conflicts with the existing V2 balanced-rounding rule.

Therefore:

- preserve `scenario_c_balanced_regime_policy_v2` behavior for old fingerprints/tests;
- add V3 as a new explicit policy;
- do not rewrite old stored solution identities;
- include optimization mode, allocation-plan profile, uniform-regime profile, final-tail policy and relevant thresholds in fingerprints;
- do not silently migrate old expected outputs;
- update comparison logic so V2 and V3 solutions are never treated as identical under one fingerprint.

Deprecation of V2, if desired later, must be a separate explicit decision after real-route validation.

---

## 16. Test requirements

### 16.1 Unit tests — minute alignment

Assert every accepted V3 C trip satisfies:

```text
c_departure_time % 60 == 0
```

Reject non-minute-aligned candidate claims.

### 16.2 Unit tests — strict uniform regime

Accept:

```text
6,6,6
7,7,7
20,20
```

Reject:

```text
6,7,6
10,11,10
20,21
```

under V3 even though some of these are valid V2 balanced rounding.

### 16.3 Representability tests

Cover:

- exact divisible span;
- non-divisible span repaired by bounded boundary movement;
- non-divisible span repaired by alternate trip count;
- merge/split case;
- no representable allocation -> explicit failure, no balanced-rounding fallback.

### 16.4 Stage 1 allocation tests

Verify:

- daily total fixed;
- directional totals fixed;
- demand-priority allocation improves or preserves high-priority B service;
- protected floors cannot be donors;
- combined-demand mode never claims directional demand authority.

### 16.5 Stage 2 operational tests

Verify:

- one-to-one source mapping;
- B ± absolute shift hard bound;
- exact source runtime;
- arrival-terminal turnaround;
- fleet upper bound;
- terminal occupancy;
- first/last locks;
- exact regime counts from Stage 1;
- strict uniform headway equations.

### 16.6 Final Service Tail tests

Include at least:

1. low late demand with sufficient trips: final regime remains spread through the final ~60-minute area and ends at the locked last departure;
2. final regime internal headways are one exact integer value;
3. candidate that bunches late trips early then leaves an avoidable long final gap is rejected or scored below the compliant alternative;
4. final headway may be longer than the preceding regime when policy permits;
5. strong late demand may justify a shorter final headway without violating the final-tail policy;
6. final-tail policy cannot violate protected floors, fleet or turnaround;
7. one-trip final tail is handled explicitly and not falsely described as a measurable uniform regime.

### 16.7 Budget tests

Verify:

- no unbounded solve path in ordinary application runtime;
- Stage 1 + Stage 2 share one total budget;
- timeout is not reported as infeasibility;
- a valid feasible candidate can be returned honestly without claiming optimality;
- no automatic infinite retry loop.

### 16.8 A-optional mode tests

Verify B-anchored mode can normalize/evaluate/solve with B + valid demand and no A while legacy authority behavior remains stable.

### 16.9 Regression suite

Run at minimum:

```text
pytest
ruff check
ruff format --check
```

Preserve all existing protected-floor, fleet, terminal occupancy, authority/fingerprint and ordinary-runtime budget regressions.

---

## 17. Real-route pilot acceptance

Repository correctness is not sufficient for product acceptance.

After implementation, run the new V3 workflow against the two current pilot routes using their Scenario B timetables and passenger-production data.

For each direction and route, export / inspect:

- Stage 1 trip allocation by demand interval;
- final service regimes;
- exact C timetable;
- internal headway of each regime;
- transition headways;
- final-service-tail span/headway;
- B -> C shift per trip;
- required fleet and terminal stock;
- demand-service comparison B versus C;
- reason every regime boundary exists;
- solver status and budget use;
- final acceptance state.

Product acceptance requires expert review that the resulting timetable is understandable operationally, not merely solver-feasible.

---

## 18. Non-goals for this implementation

Do not add in this change unless required to preserve correctness:

- variable total daily trip count;
- automatic fleet increase/reduction;
- automatic redistribution of total trip counts between directions when demand is not directionally authoritative;
- stochastic passenger-demand forecasting;
- arbitrary second-level departure times;
- balanced-rounding headways inside V3 regimes;
- removal of Scenario A from existing evaluation workflows;
- automatic unbounded solver reruns;
- UI redesign unrelated to exposing the new results.

---

## 19. Implementation sequence for Codex

Implement incrementally and keep each boundary testable.

### Phase 1 — contracts and policy

1. Add the B-anchored two-stage optimization mode/profile.
2. Add V3 strict-uniform regime policy.
3. Add final-service-tail policy fields.
4. Add Stage 1 allocation-plan immutable models and fingerprints.
5. Add explicit final-acceptance states/models.

### Phase 2 — authority and normalization

1. Allow B + demand + no A only in the new B-anchored mode.
2. Preserve old A-bound behavior elsewhere.
3. Add combined-demand fixed-direction-count authority mode.

### Phase 3 — Stage 1 allocator

1. Build integer trip-allocation model.
2. Bind fixed daily/directional totals.
3. Bind protected floors.
4. Generate only V3-representable regime plans.
5. Add final-tail allocation protection.
6. Return a bounded ranked set of admissible allocation plans.

### Phase 4 — Stage 2 exact timetable CP-SAT

1. Create integer-minute B-anchored departure domains.
2. Add B hints.
3. Add exact Stage 1 regime membership/count constraints.
4. Add one integer headway per regime with equality constraints.
5. Add final-tail last-departure propagation.
6. Preserve runtime, turnaround, fleet, occupancy and protected-floor constraints.
7. Optimize the reduced objective groups.

### Phase 5 — validation and comparison

1. Teach the independent validator V3 exact uniformity.
2. Validate final-tail behavior.
3. Recompute solver-neutral quality metrics.
4. Compare C with B.
5. Apply final-acceptance policy.

### Phase 6 — artifacts and diagnostics

1. Expose Stage 1 allocation.
2. Expose final regimes and headways.
3. Expose final-tail metrics.
4. Expose B-to-C trip shifts and fleet assignment.
5. Expose solve diagnostics and final state.

### Phase 7 — pilot validation

Run the two real pilot routes, record findings, and only then decide whether V3 becomes the ordinary default.

---

## 20. Definition of done

This implementation is complete only when all of the following are true:

1. OR-Tools no longer searches the entire service window for every trip when a B-anchored domain is available.
2. Stage 1 explicitly determines trip allocation before exact departure placement.
3. Every accepted V3 departure is `HH:MM:00` aligned.
4. Every measurable V3 regime uses one exact integer-minute internal headway; no 6/7 or 10/11 balanced rounding is accepted.
5. Stage 2 preserves B source runtime, turnaround, fleet, occupancy, first/last locks and protected floors.
6. The final-service tail remains meaningfully spread to the locked last departure and cannot be compressed away by demand optimization.
7. B + valid demand + no A is supported only in the explicit B-anchored mode.
8. Combined demand is handled without fabricating directional passenger evidence.
9. Stage 1 and Stage 2 share a finite total solve budget and cannot enter an unbounded retry loop.
10. A feasible candidate is not automatically a final recommendation; independent validation, B comparison and final acceptance remain authoritative.
11. Existing V2 fingerprints/semantics remain stable.
12. Full repository tests and quality checks pass.
13. The two real pilot routes produce reviewable timetable artifacts and explicit solver diagnostics.
