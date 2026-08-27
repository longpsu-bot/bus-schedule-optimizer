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
  -> exact-timestamp protected-window validation, when evidence-bound authority exists
  -> actual compiled-service metrics, rhythm diagnostics, and tail-ordering eligibility
  -> unchanged exact-timetable fleet validator for every retained pair
  -> explicit finite neighbors
  -> feasible operating-pair Pareto frontier
```

The state fingerprint is SHA-256 over canonical JSON containing the profile, route, direction,
fixed endpoints, complete ServiceRegime boundary vector, and integer trip-count vector. Parent
history, feedback, and seed labels are deliberately excluded. A fingerprint is evaluated at most
once.

The coordinator keeps three concepts separate:

The immutable evidence now includes both the original DAILY_VALIDATED demand buckets and the
already-selected canonical `DemandRegime` windows. Canonical regime IDs, directions, windows,
integrated demand mass, and demand rate are loaded from the frozen Route 6/10 model-selection
artifacts. The coordinator does not rerun detection or select K. These facts never contain mutable
service results. `ServicePlanStateV1` and its compiled `ServiceRegime` realization remain the
mutable decision side of the boundary. A pilot route with missing, failed, mixed-direction,
non-contiguous, or incomplete canonical evidence fails closed; generic synthetic contexts may
explicitly omit response evidence and then expose no response diagnostics.

### Hard authority

Hard service protection exists only when a
`ProtectedServiceFloorEnforcementAuthorityV1` is explicitly translated into evidence-bound
`ClosedLoopProtectedServiceWindowV1` records. When Scenario B is supplied at translation, the
canonical 6A2B verifier establishes current source provenance. Separately, the translated
authority verifies its canonical profile and semantics, source metadata shape, window invariants
and ordering, and translation fingerprint. Translated-authority internal verification does not
prove that its source remains current against Scenario B; source verification and internal
verification are distinct boundaries.

A malformed non-`None` translated authority reports
`INVALID_TRANSLATED_PROTECTION_AUTHORITY` and stops the route before compilation or fleet
validation. It is not reinterpreted as no protection, route/fleet infeasibility, or a seed prior.
With no authority, or with a valid authority containing no windows, diagnostics report
`VALID_NO_ENFORCEABLE_WINDOW`; the coordinator does not infer protection from demand regimes,
block demand, end-tail artifacts, or a baseline headway.

Each compiled directional timetable is checked before fleet pairing. For each protected window,
validation enumerates every eligible start/end departure pair inside the boundary tolerances and
accepts when at least one legal pair satisfies the minimum trip count plus positive, whole-minute
internal headways no greater than the maximum. A nearest failing boundary pair therefore cannot
mask another valid pair. When several pairs pass, minimum total boundary deviation and stable
tie-breaks select one diagnostic/fingerprint witness; witness selection never changes acceptance.
Transition gaps outside the protected span are not counted. Rejections retain the direction,
window, source regime ID, violated rule, and observed count, headway, or departure pair. This is
operational service-level/timestamp-level enforcement; it does not claim Scenario-B source-trip
identity or donor-removal semantics and invents no source trip IDs.

### Seed prior

The Scenario-B/end-tail-derived headway is a `seed_headway_prior_minutes` value. It remains
completely separate from hard protection and is used only by the initial sqrt-demand allocation to
construct a reasonable seed. It is not ServicePlan validity authority and is not passed to merge,
split, shift, one-trip, or tail neighborhood feasibility. Frozen C1/C2/C3 seed artifacts remain
unchanged.

### Optimization objectives

Ordinary unprotected service remains exposed to demand mismatch, `max_frequency_jump`,
`total_frequency_variation`, tail fit, exact directional totals, fixed endpoints, fleet, and
waiting metrics. Continuity remains an objective rather than a new hard maximum jump, and demand
does not map one-to-one to frequency. The final unprotected tail has no universal maximum headway
inherited from Scenario B. It must, however, be at least as slow as every earlier actual
ServiceRegime unless strictly higher immutable demand or binding translated protected-service
authority justifies a shorter tail headway.

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

Splits enumerate every grid-aligned boundary and every structurally feasible integer split.
Generic boundary shifts move exactly one planning bucket and enumerate every structurally feasible
redistribution of the two affected regimes. Every regime retains at least two trips and every move
preserves the authoritative direction total. The generic helpers remain backward compatible with
callers that intentionally provide a headway floor, but this coordinator passes no global floor.

Structured feedback location now constrains those same operators. A redundant boundary can only
request that boundary's merge. Frequency-jump feedback touches only the adjacent ServicePlan
regimes. Demand under/over feedback touches regimes overlapping the diagnosed interval and their
immediate donors. A canonical response boundary inside a ServiceRegime targets that regime's local
split and adjacent revision opportunities; an existing ServicePlan boundary targets only its two
adjacent regimes. Tail feedback remains tail-local. Pure fleet feedback is cross-directional exact
operational evidence, so it may revise every existing boundary, but it does not identify a missing
demand boundary, a new service state, or a region requiring subdivision. It therefore uses merges,
one-grid boundary shifts, one-trip transfers, and one-trip tail moves, but never creates a new
ServiceRegime with `SPLIT_REGIME`. A fleet boundary shift permits only feasible left-regime counts
equal to the parent's count minus one, unchanged, or plus one; it does not fall back to exhaustive
redistribution. Demand-response and other localized ServicePlan evidence retain their split
authority, including a split at a diagnosed canonical DemandRegime boundary. Fingerprint
deduplication and deterministic ordering are unchanged.

`TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION` has its own deliberately small repair family:
`TAIL_RELEASE_ONE`, plus `SHIFT_BOUNDARY_LEFT` at the final planning boundary by exactly one grid
step with `max_trip_count_delta=1`. It creates no split, global shift, global transfer, or
multi-trip neighborhood. Repeated evaluated generations may progressively release further tail
trips, with the normal state fingerprint remaining authoritative.

For `N` ServiceRegimes, the pure-fleet family has a semantic upper bound before fingerprint
deduplication of `9 * (N - 1) + 2`: per boundary, at most one merge, three left-shift allocations,
three right-shift allocations, and one transfer in each direction, plus at most two tail moves.
This is a consequence of the one-step actions, not a truncation limit.

Within one coordinator search, a semantic ServicePlan parent receives the global
`FLEET_LIMIT_EXCEEDED` one-step revision family at most once when an enqueue request contains only
fleet feedback. Independently evaluated infeasible exact pairs still count as separate feedback events,
while fleet expansion requests, executions, and skips are reported separately. Mixed or non-fleet
feedback remains unaffected. The cache is intentionally keyed by the semantic ServicePlan
fingerprint rather than compilation, pair, history, or fleet-excess magnitude. If bounded-queue
admission rejects a generated child, later pair multiplicity does not regenerate that unchanged
child for another admission attempt. This changes bounded search-control semantics and may change
the explored frontier. F2 changes the pure-fleet operator family, but it does not change generic or
non-fleet operators, queue priority, D1 queue identity, search budgets, Pareto semantics, the
compiler, or the exact fleet validator.

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

These clean-boundary compiler semantics are unchanged. Arithmetic settlement, the Route 6
14-minute boundary residual, and a `TRANSITION` ServiceRegime remain out of scope.

## Actual-service metrics

The evaluator maps exact compiled departures to the immutable 30-minute DAILY_VALIDATED demand
buckets:

```text
demand mismatch = sum((compiled trip share_b - observed demand share_b)^2)

frequency jump_i = abs(log((60 / h_right) / (60 / h_left)))
total variation = sum(frequency jump_i)

moved trips vs B = sum(abs(compiled bucket count - exact B bucket count)) / 2
```

Expected passenger wait is integrated from exact timestamps. For every interdeparture interval
`[d_i, d_(i+1))`, an arrival at `t` waits `d_(i+1) - t`; piecewise-constant demand intensity is
integrated over exact overlap with each immutable demand bucket. The only passenger-arrival model
is `UNIFORM_WITHIN_DEMAND_BUCKET_ASSUMPTION`. The active span is the exact fixed first-to-last
departure span. The evaluator reports demand-weighted expected wait, maximum bucket expected wait,
the deterministic per-bucket tuple, and active demand mass. It does not approximate wait as
ServiceRegime headway divided by two.

Demand-weighted expected passenger wait answers, “What does the average passenger experience?”
Maximum bucket expected wait answers, “What is the worst scheduled passenger-access interval in
the service day?” Low-demand periods, particularly final tails, therefore remain visible even when
they carry little weight in the average. Directional P90 is the deterministic nearest-rank value at
rank `ceil(0.90 * n)` in the ordered non-null active bucket waits. Pair P90 is the maximum of the two
directional P90 values; it is not pooled or demand-weighted and is diagnostic only.

Tail maximum bucket wait reuses those same exact per-bucket results. It takes the maximum for active
immutable-demand buckets whose active intervals overlap the exact final compiled ServiceRegime
support. It creates no pseudo-bucket and makes no `headway / 2` approximation. If no active demand
bucket overlaps that support, the diagnostic is null; no demand is fabricated.

Exact interdeparture frequency is also projected by temporal overlap onto every canonical
DemandRegime, independently of ServiceRegime boundaries. Adjacent canonical regimes expose
`delta_log_demand`, `delta_log_service`, demand/service direction, direction alignment, the
`0.5 * delta_log_demand` sqrt benchmark, and its residual. Schedule diagnostics include direction
accuracy, transition/aligned counts, and sqrt-response deviation. Sqrt demand remains benchmark
and seed semantics only: it is not protection, validity, a required elasticity, or a production
Pareto dimension.

At most one `DEMAND_RESPONSE_DIRECTION_MISMATCH` is emitted per exact direction when service is
flat or opposite to an UP/DOWN demand transition. The chosen transition maximizes absolute sqrt
residual, then absolute demand contrast, with stable time/regime-ID tie-breaks. A correctly directed
response is not called a mismatch merely because its amplitude differs from sqrt demand, and a
mismatch remains revision evidence rather than a validity failure.

Demand under/over feedback is emitted as a pair only when theoretically transferring one service
share quantum `q = 1 / exact_departure_count` from the selected overserved bucket to the selected
underserved bucket strictly reduces their squared mismatch beyond numerical epsilon. Tail
under/over feedback likewise requires adding/removing one trip share to reduce tail mismatch.
These checks establish discrete actionability only; the normal compile/evaluate loop remains the
authority on whether a local ServicePlan move is feasible.

### Slowest-tail ordering

Tail ordering is evaluated after exact compilation and protection validation, never in the
compiler or ServicePlan validator. Each actual compiled ServiceRegime inherits the exact
contiguous union of `demand_regime_slices` carrying its `service_regime_id`, clipped to
`[fixed_first_departure, fixed_last_departure)`. Missing, ambiguous, non-contiguous, mismatched, or
empty provenance fails closed. Immutable piecewise demand is integrated exactly over each support:

```text
demand_rate_per_hour = integrated_demand_mass / support_duration_hours
```

For every earlier regime with a headway longer than the tail, immutable demand justifies the
inversion only when the tail demand rate is strictly greater, using numerical epsilon only. Equal
demand does not justify it, and all offending earlier regimes must be justified. A translated
protection exception requires an accepted exact protection witness that binds an internal tail
gap and whose explicit maximum-headway authority is below the offending longer headway. Temporal
overlap alone is not authority. The assessment records all offenders and any exact protection
witnesses.

The deterministic classifications are `TAIL_IS_SLOWEST`,
`TAIL_SHORTER_DEMAND_JUSTIFIED`, `TAIL_SHORTER_PROTECTION_JUSTIFIED`,
`TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION`, and
`SINGLE_REGIME_NO_TAIL_ORDERING_CONFLICT`. The invalid classification rejects that directional
compilation before archive retention and exact fleet pairing, increments
`tail_ordering_compilations_rejected`, and still emits structured repair feedback. Existing
`TAIL_OVER_SERVICE` and `TAIL_UNDER_SERVICE` demand-share feedback remains independent.

### Rhythm simplicity

Rhythm metrics use actual compiled ServiceRegimes only. A sustained rhythm has at least two
internal gaps (`trip_count >= 3`). The principal vocabulary metric is the sorted distinct set of
uniform headways among sustained regimes; repeated occurrences do not increase its count. A
two-trip regime contributes one internal gap and is retained as a separate single-gap residual
diagnostic rather than rejected or counted as sustained.

The diagnostic effective palette uses tolerance ±1 whole minute. It finds the minimum tuple of
representatives selected from the actual sustained levels that covers every sustained exact level.
Equal-cardinality palettes minimize total internal-gap-weighted absolute deviation and then use the
lexicographically smaller representative tuple. No coverage percentage excludes a level, and this
effective palette is not a Pareto objective.

## Pairing and Pareto rule

Outbound and inbound modes are independent. Every new directional compilation is paired with the
bounded phase-diverse archive for the opposite direction before its own archive is compacted.
Directional demand, regularity, movement, quantization, and phase-quality metrics order retention
but are not cross-direction dominance authority. When archive capacity remains after state
diversity, deterministic anchors retain the lowest exact passenger wait and lowest sqrt-response
deviation before remaining exact-phase max-min selection. These anchors are retention diversity,
not dominance or validity. The existing fixed-timetable validator is called
without moving departures, repairing headways, inventing deadheads, or changing runtime/layover
authority. Final fleet feasibility is determined only after pairing exact outbound and inbound
timetables.

Fleet-feasible pairs are nondominated over:

1. observed-demand mismatch;
2. demand-weighted expected passenger wait, combined across directions by active demand mass;
3. maximum bucket expected passenger wait, the maximum of the two directional values;
4. actual ServiceRegime count;
5. total directional sustained-headway-level count;
6. maximum frequency jump;
7. total frequency variation;
8. moved trips versus exact Scenario B;
9. fleet required;
10. total excess terminal wait.

Effective palette count, single-gap count, raw transition count, Gamma, rank correlation,
peak/low ratio, direction accuracy, and sqrt-response deviation are not additional Pareto
dimensions. Pair diagnostics also expose the maximum directional sustained-level count, total
effective-palette count, total single-gap regime count, and maximum directional P90 bucket wait.
P90 and tail-specific wait are not Pareto dimensions. No hard headway or maximum-wait threshold is
created; the H slowest-tail eligibility rule remains unchanged.

No weighted scalar objective selects a timetable.

## Domain-priority post-search selection (PR62-L)

`OperationalSelectionPolicyV1` is an isolated post-search policy. It consumes the immutable exact
operating pairs on the existing 10-dimensional Pareto frontier and does not replace or truncate
`RouteCoordinatorResultV1.pareto_frontier`. The policy order is strict and lexicographic:

1. `HARD_OPERATIONAL_FEASIBILITY`;
2. `SCENARIO_B_MAX_ACCESS_NON_REGRESSION`;
3. `OBSERVED_DEMAND_MISMATCH`;
4. `RHYTHM_SIMPLICITY`;
5. `FLEET_EFFICIENCY`.

Hard feasibility independently revalidates fixed directional trip totals and endpoints,
whole-minute strictly increasing departures, exact uniform ServiceRegimes, clean-boundary
compilation, translated protection, demand-justified tail eligibility, authoritative runtime and
minimum layover, exact minimum-fleet path cover, fleet ceiling, exact connections, and compiler
provenance. Failure is non-selectable; no later metric can compensate.

Fleet feasibility and fleet efficiency are distinct. Fleet feasibility is the mandatory exact
runtime/layover/path-cover/ceiling gate. Fleet efficiency is only the final preference among pairs
already surviving feasibility, passenger access, demand fit, and rhythm; its tuple is fleet
required, total excess terminal wait, then maximum excess terminal wait. These concepts are never
combined into a score.

The only Scenario-B passenger gate compares each direction separately: candidate maximum active-
bucket expected wait must be no greater than the same-direction Scenario-B value plus numerical
epsilon. Pair maximum, mean wait, mismatch, P90, one-SE, and percentage-of-days rules cannot stand
in for this directional check. An empty survivor set is reported as
`ACCESS_GUARDRAIL_TOO_RESTRICTIVE` and is not relaxed automatically.

Among access-safe candidates, only production `observed_demand_mismatch` determines the strict
best-demand-fit set. If a numerical-epsilon tie remains, rhythm uses total directional sustained
headway-level count, actual ServiceRegime count, total directional effective-palette count, then
total single-gap regime count. If still tied, fleet efficiency applies. Pair fingerprint is used
only when all policy metrics remain metrically equivalent, as a deterministic identity tie-break.
Every stage exposes retained fingerprints and explicit rejection reasons.

## Deterministic safeguards

The V1 defaults are 24 state evaluations per route, 512 OPEN states, 4 compilations per state,
24 directional compilations, and 512 final pair candidates. Exhaustion returns
`SEARCH_BUDGET_EXHAUSTED` with the best feasible frontier already found. Reports expose generated,
evaluated, duplicate, pruned, compile, fleet, and iteration counters. Bounded diversity retention
is a V1 search approximation; technical phase/limit pruning remains visible in diagnostics and is
not reported as dominance pruning.

Prior demand, V2, and V3 artifacts are guarded by a checked SHA-256 manifest before and after each
route run. Outputs are written only under `outputs/service_plan_coordinator_v1/`.
