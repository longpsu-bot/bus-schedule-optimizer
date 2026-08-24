# Closed-Loop ServicePlan Coordinator V1

This review-only pilot treats validated demand as immutable evidence and an operational
`ServicePlanStateV1` as a mutable search decision. It runs only for Routes 6 and 10 and does not
replace the V2 clean-boundary or V3 end-tail products.

## Authority boundary

```text
DAILY_VALIDATED DemandRegime evidence (immutable)
  -> deterministic ServicePlan seeds
  -> frozen ServicePlanStateV1 (boundaries + integer counts)
  -> bounded CleanCompileFrontierV1
  -> unchanged exact-timetable fleet validator for every retained pair
  -> actual compiled-service metrics and structured feedback
  -> explicit finite neighbors
  -> feasible operating-pair Pareto frontier
```

The state fingerprint is SHA-256 over canonical JSON containing the profile, route, direction,
fixed endpoints, complete ServiceRegime boundary vector, and integer trip-count vector. Parent
history, feedback, and seed labels are deliberately excluded. A fingerprint is evaluated at most
once.

## Finite neighborhood

The only state transitions are:

- `MERGE_ADJACENT`
- `SPLIT_REGIME`
- `SHIFT_BOUNDARY_LEFT`
- `SHIFT_BOUNDARY_RIGHT`
- `MOVE_ONE_TRIP_LEFT_TO_RIGHT`
- `MOVE_ONE_TRIP_RIGHT_TO_LEFT`
- `TAIL_ABSORB_ONE`
- `TAIL_RELEASE_ONE`

Splits enumerate every grid-aligned boundary and every floor-feasible integer split. Boundary
shifts move exactly one planning bucket and enumerate every feasible redistribution of the two
affected regimes. Every move preserves the authoritative direction total.

## Compilation frontier

The legacy clean compiler's feasible path is retained as a mandatory witness, followed by a local-
quality anchor and deterministic headway-shape/exact-phase diversity. Headway quantization, actual
operational ServiceRegime count, and phase/edge quality are ordering and diversity signals only;
they are not pre-fleet dominance authority. Distinct exact departure vectors remain distinct. The
witness-preserving intermediate caps and `max_compile_frontier_per_state` are technical diversity
safeguards, not transport policy or mathematical dominance.

Every emitted timetable preserves the fixed first/last departures and exact state total, uses
whole-minute internal headways, has boundary gap `g in {h_left, h_right}`, merges continuous equal
rhythms, and has no transition headway/category.

## Actual-service metrics

The evaluator maps exact compiled departures to the immutable 30-minute DAILY_VALIDATED demand
buckets:

```text
demand mismatch = sum((compiled trip share_b - observed demand share_b)^2)

frequency jump_i = abs(log((60 / h_right) / (60 / h_left)))
total variation = sum(frequency jump_i)

moved trips vs B = sum(abs(compiled bucket count - exact B bucket count)) / 2
```

It also records actual ServiceRegime count, tail service/debt, fleet requirement, and total/maximum
connection layover above the authoritative minimum.

## Pairing and Pareto rule

Outbound and inbound modes are independent. Every new directional compilation is paired with the
bounded phase-diverse archive for the opposite direction before its own archive is compacted.
Directional demand, regularity, movement, quantization, and phase-quality metrics order retention
but are not cross-direction dominance authority. The existing fixed-timetable validator is called
without moving departures, repairing headways, inventing deadheads, or changing runtime/layover
authority. Final fleet feasibility is determined only after pairing exact outbound and inbound
timetables.

Fleet-feasible pairs are nondominated over:

1. observed-demand mismatch;
2. actual ServiceRegime count;
3. maximum frequency jump;
4. total frequency variation;
5. moved trips versus exact Scenario B;
6. fleet required;
7. total excess terminal wait.

No weighted scalar objective selects a timetable.

## Deterministic safeguards

The V1 defaults are 24 state evaluations per route, 512 OPEN states, 4 compilations per state,
24 directional compilations, and 512 final pair candidates. Exhaustion returns
`SEARCH_BUDGET_EXHAUSTED` with the best feasible frontier already found. Reports expose generated,
evaluated, duplicate, pruned, compile, fleet, and iteration counters. Bounded diversity retention
is a V1 search approximation; technical phase/limit pruning remains visible in diagnostics and is
not reported as dominance pruning.

Prior demand, V2, and V3 artifacts are guarded by a checked SHA-256 manifest before and after each
route run. Outputs are written only under `outputs/service_plan_coordinator_v1/`.
