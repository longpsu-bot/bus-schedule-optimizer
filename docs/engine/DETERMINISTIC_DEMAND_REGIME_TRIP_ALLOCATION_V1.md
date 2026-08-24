# Deterministic Demand-Regime Trip Allocation V1

**Status:** reviewable integer allocation authority after daily demand validation
**Inputs:** `DAILY_VALIDATED DemandRegimePlanV1`, canonical Scenario B, observed-demand evidence
**Outputs:** `B_REFERENCE`, `C1_DEMAND_FIT`, `C2_CONSERVATIVE`, `C3_BALANCED`
**Excluded:** exact departures, phases, service-regime regularization, Schedule Compiler, fleet,
vehicle chaining, and OR/CP-SAT

## Architectural distinction

`DemandRegime` is a descriptive segmentation of observed realized demand. `ServiceRegime` is a
future operational interval using one uniform headway. Eight validated demand regimes do not imply
eight final timetable headway regimes. Allocation exposes adjacent equal-headway-proxy merge hints,
but it never changes the validated demand boundaries.

Observed ticket demand was realized under Scenario B service. Candidate scores therefore measure
**observed-demand fit**, not a causal or latent-demand optimum.

## Scenario B and demand targets

Scenario B departures are recounted in each half-open interval `[start,end)`. The directional total
must reconcile exactly. For regime `r`:

```text
s_r = demand_sum_r / total_demand
ideal_r = T * s_r
DemandMismatch(x) = sum_r (x_r / T - s_r)^2
L1(x,B) = sum_r abs(x_r - b_r)
MovedTrips(x,B) = L1(x,B) / 2
```

Counts are solved jointly, so `sum(x_r) = T`; ideal values are never independently rounded.

## Service floor

The exact-trip protected-floor authority and legacy two-stage minimum-headway policy do not govern
the new demand-regime intervals. The allocator therefore labels its continuity safeguard:

```text
BASELINE_DERIVED_SERVICE_FLOOR
H_floor = max_r(duration_r / BTripCount_r) for regimes with B service
minTrips_r = max(1, ceil(duration_r / H_floor))
```

The closing regime uses the same floor. The allocator does not require a departure at service end.
If floor totals exceed available directional trips, allocation fails with
`INFEASIBLE_SERVICE_FLOORS`; floors are not weakened.

No arbitrary minimum-headway policy is invented. With no explicit policy, a count is rejected only
when no positive integer-minute internal headway can exist. If a future caller supplies an explicit
minimum headway `h_min`, the corresponding maximum is
`floor((duration-1)/h_min)+1`.

## Integer-headway compile proxy

For `x >= 2`, feasible positive integer headways satisfy `(x-1)h < duration`. The proxy selects the
integer `h` closest to `duration/x`, breaking a tie toward the smaller integer. Per-regime normalized
quantization error is:

```text
abs(duration - x*h) / duration
```

Candidate compile quality is the sum of these errors. For `x = 1`, internal headway and
quantization error are `None`; no headway is fabricated. Nominal headway always remains
`duration/x`, never `duration/(x-1)`.

## Bounded dynamic programming

At each regime the DP state is:

```text
(regime_index, trips_used, L1_deviation_from_B)
```

Each transition assigns one integer count within the regime's floor and compile/policy upper bound.
For an identical state, retain the prefix with lower exact rational demand mismatch, then lower exact
rational compile error, then lexicographically earlier allocation vector. Final states use exactly
`T` trips. One best record per L1 value is sufficient because future additive costs are identical
for prefixes at the same state.

All ranking calculations use exact `Fraction` arithmetic derived deterministically from decimal
demand values. Floats appear only in the reporting model.

## Candidate rules

- `B_REFERENCE`: recounted canonical Scenario B, separate from C candidates.
- `C1_DEMAND_FIT`: minimum mismatch; then compile error; then moved trips; then allocation vector.
- `C2_CONSERVATIVE`: among allocations improving B by more than epsilon, minimum moved trips; then
  mismatch; compile error; allocation vector. If none improves, retain B with
  `NO_IMPROVING_CONSERVATIVE_ALLOCATION`.
- `C3_BALANCED`: build the nondominated mismatch/movement frontier bounded between B and C1. Let
  `D_min` be C1 mismatch, normalize demand by `(D-D_min)/(D_B-D_min)` and movement by
  `MovedTrips/max(1,MovedTrips_C1)`, and minimize the squared Euclidean distance to `(0,0)`.
  Squared distance avoids nondeterministic square roots. Ties use compile error, moved trips,
  mismatch, then allocation vector. When B is demand-optimal or C1 moves zero trips, C3 is B.

## Review boundary

Candidate rows expose `RegimeTripAllocationV1`, demand evidence, B reference counts and headways,
floor/bound data, nominal and integer proxy headways, quantization error, and observed demand per
allocated trip. Equal adjacent integer proxies are merge diagnostics only. No output contains an
exact Scenario C departure timestamp.
