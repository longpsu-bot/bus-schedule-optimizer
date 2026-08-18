# Scenario C Balanced Regime Policy V2

**Profile:** `scenario_c_balanced_regime_policy_v2`

## Decision

Scenario C service regimes are canonical output semantics, not immutable copies of demand phases.
Demand phases remain analytical inputs to demand evaluation and native solver objectives.

A representable Scenario C service regime has at least two trips and positive whole-minute
internal headways. Let `H = (last departure - first departure) / (trip count - 1)`. Every internal
headway must be either `floor(H)` or `ceil(H)`, their sum must equal the regime span, and the
maximum and minimum internal headways may differ by at most one minute. Accepted statuses are
`UNIFORM` and `BALANCED_ROUNDING`.

Regression tests must therefore treat adjacent-minute sequences such as 10/11 minutes as valid
balanced rounding; genuinely irregular sequences require internal variation greater than one
minute or another explicit representability violation.

## Boundary repair and maximality

Canonical construction begins from demand-phase membership. A singleton phase is tested against
the preceding and following nonempty regimes and may be absorbed only when the resulting regime
remains balanced. Deterministic tie-breaking prefers lower maximum internal variation, lower total
internal variation, lower transition jump, lower distance from the demand-phase boundary, then the
preceding regime.

After singleton repair, adjacent regimes are repeatedly merged whenever the complete combined
trip sequence, including the cross-boundary headway, remains balanced. Final Scenario C regimes
are therefore maximal under the balanced-regime rule.

## Transitions

A headway between two final service regimes is a transition headway. It is not part of either
regime's internal balance test, but remains visible in solution metrics and artifacts and remains
subject to transition-jump and service-gap objectives.

## Solver boundary

The heuristic and OR-Tools paths reconcile raw candidates through the same canonical builder.
Solver-supplied labels are claims, not independent regime authority. OR-Tools may optimize
regularity over demand phases internally; if canonical V2 regrouping changes those boundaries,
native solver status is preserved while downstream regime-dependent proof claims are explicitly
qualified. Independent candidate validation remains final.

## Preserved constraints

This policy does not relax runtime, terminal turnaround, fixed trip counts, directional trip
counts, first/last departure locks, source traceability, fleet limits, terminal occupancy, demand
authority, or protected-service-floor direction, membership, trip-count, service-window, and
maximum-future-headway constraints.

Scenario B irregularity remains diagnostic and does not become an optimization-readiness or hard
feasibility failure.

## Identity

The V2 profile is included in relevant Scenario C candidate, solution, and outcome fingerprints so
results produced under earlier regime semantics cannot silently reuse the same identities.

## Acceptance validation

The focused implementation is accepted only when the complete repository suite, Ruff lint, Ruff
format check, and diff hygiene all pass with no private route data committed. Real-route pilot
quality remains a separate expert acceptance step after repository correctness.
