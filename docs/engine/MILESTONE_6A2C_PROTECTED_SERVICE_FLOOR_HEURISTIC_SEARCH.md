# Milestone 6A2C: Protected service-floor-aware heuristic search

## 1. Purpose

Milestone 6A2C makes the existing legacy-compatible heuristic search aware of the protected
service floors already enforced by Milestone 6A2B. When a current enforceable authority exists,
the heuristic combines and evaluates only direction plans that satisfy its protected regimes.

Search awareness follows acceptance enforcement deliberately. Milestone 6A2B first established
one solver-independent meaning for membership, direction, order, donor removal, boundaries,
count, and headway. 6A2C can now prune the bounded heuristic search without becoming a second
acceptance authority. Every returned raw candidate still passes through the unchanged common
6A2B validator.

## 2. Scope

This milestone changes only the legacy-compatible heuristic request, adapter context, solver
adapter, and `generate_scenario_c` direction-plan search. It retains:

- the total trip count and trip count by direction;
- one-to-one Scenario B source mapping;
- source direction and source order;
- first and last full-direction departures;
- fixed available fleet;
- the existing technical, fleet, regularity, demand, and objective evaluation order; and
- the exact-Scenario-B fallback.

It does not add OR-Tools protected-floor constraints or objectives. It also does not add trip
insertion, trip deletion, variable trip counts, fleet expansion, policy relaxation,
cross-direction redistribution, or cross-regime donor substitution.

## 3. Authority-to-adapter binding

`build_heuristic_schedule_request_v1` supplies the same complete
`ProtectedServiceFloorEnforcementAuthorityV1` object to the generation context and the heuristic
adapter when enforceable regimes exist. The adapter retains that authority instead of
reconstructing floor values.

The heuristic compatibility context contains an optional enforcement fingerprint. When
protection is enforceable, its context fingerprint binds:

- the exact Scenario B fingerprint;
- the exact 6A2B enforcement fingerprint;
- the legacy parameter and timetable compatibility facts;
- the heuristic configuration;
- the observed-demand fingerprint; and
- the conservative turnaround bridge mode and value.

The resulting context fingerprint remains `problem.adapter_context_fingerprint`, so the problem,
compatibility context, and adapter-held authority reconcile before search.

Solver orchestration also derives the enforceable fingerprint from the actual
`ScheduleGenerationContextV1` supplied for execution and requires it to equal the heuristic
adapter's native-search fingerprint and compatibility-context binding before calling the adapter.
A mismatch returns `MODEL_INVALID` with `HEURISTIC_PROTECTED_FLOOR_AUTHORITY_MISMATCH`; the
heuristic generator does not execute.

## 4. Conditional fingerprint compatibility

The enforcement fingerprint field is added to the heuristic context fingerprint payload only
when enforceable regimes exist. It is not serialized as an always-present `null`.

Consequently, no authority and a valid authority with no enforceable regimes retain the merged
6A2B context, problem, candidate, solution, and outcome identities and the same timetable and
optimization log. Focused regression tests freeze the historical no-floor fingerprints rather
than comparing only two post-change runs.

## 5. Pre-search validation

Before calling `generate_scenario_c`, the adapter verifies that:

1. the adapter-held authority is semantically valid for `problem.scenario_b`;
2. its Scenario B fingerprint equals `problem.source_b_fingerprint`;
3. its enforcement fingerprint equals the optional compatibility-context binding;
4. the recomputed compatibility fingerprint equals `problem.adapter_context_fingerprint`; and
5. its deterministic search projection reconciles with the exact legacy Scenario B source
   timetable.

Missing membership, duplicate membership, overlapping regimes, wrong direction, wrong authority
order, stale boundaries, invalid counts, invalid headways, or an unbound fingerprint fails before
candidate enumeration. The adapter returns `MODEL_INVALID` with the stable sanitized code
`HEURISTIC_PROTECTED_FLOOR_AUTHORITY_MISMATCH`. It does not run an unprotected search or classify
the defect as route, fleet, demand, or timetable infeasibility.

## 6. Deterministic heuristic projection

The projection preserves the authority's existing regime order. Each projected regime contains:

- regime ID;
- explicit legacy direction;
- ordered Scenario B source trip IDs;
- maximum future Scenario C headway;
- minimum future Scenario C trip count;
- protected window start and end;
- future boundary tolerance; and
- donor-removal prohibition.

The projection is a mechanical view of 6A2B authority. `c_generator.py` does not read workbook
policy, trip-ridership observations, 6A2A decisions, or 6A2A previews and does not reclassify
demand evidence.

## 7. Direction-plan gates

Ordinary direction plans are derived first. For a protected direction, every derived plan is
then checked before the cross-direction Cartesian product and before complete candidates are
built. Up to the existing bound of 18 plans per direction is retained after filtering, allowing
compliant alternatives to replace higher-ranked violating plans in the bounded plan set.

Each protected regime is evaluated independently:

- **Membership and direction:** every ordered source ID must exist exactly once in Scenario B and
  must belong to the regime's explicit legacy direction.
- **Donor window:** every protected source departure stays between the protected start minus
  tolerance and protected end plus tolerance when donor removal is prohibited. An unrelated
  departure inside the window does not substitute for the protected source.
- **Boundaries:** the first and last protected source departures remain within tolerance of the
  protected start and end. Tolerance is not added to internal headways.
- **Source order:** projected membership follows Scenario B order and proposed protected
  departures remain strictly increasing. A source-order defect is an integration error.
- **Trip count:** the protected source slice must contain at least the declared minimum. The
  current heuristic never inserts or deletes trips.
- **Internal headway:** consecutive proposed protected-source departures must be positive,
  whole-minute gaps no greater than the declared maximum. Transition gaps outside the first and
  last protected members are excluded.

Outbound and inbound projections are grouped and filtered separately. Adjacent regimes are not
merged, and protected source membership may not overlap.

## 8. Candidate choice and exact-B fallback

After filtering, compliant outbound and inbound plans enter the existing complete-candidate
pipeline. Technical validation, fixed-fleet validation, regularity gates, demand evaluation, and
the existing objective tuple are unchanged. The best compliant improving candidate is therefore
selected by the historical objective order and timetable fingerprint tie-break.

The exact-Scenario-B fallback is checked defensively against every projected regime before native
enumeration. An authority derived from that same current B must accept the fallback. A failure is
an authority or integration defect, not a normal search rejection.

## 9. Bounded-search no-proof behavior

If every improving direction plan violates protection, no violating raw candidate is returned.
The generator retains exact B and the heuristic adapter returns its historical `UNKNOWN` /
no-candidate result. It does not return `INFEASIBLE` and does not produce
`NO_FEASIBLE_C_WITH_B_PARAMETERS`.

The limitation explicitly states that the bounded heuristic search found no improving
protected-floor-compliant candidate and that this does not prove global infeasibility.

## 10. Diagnostics

Protected searches add deterministic conditional entries to
`OptimizationLog.rejection_reason_counts`:

- `PROTECTED_FLOOR_DIRECTION_PLANS_EVALUATED`;
- `PROTECTED_FLOOR_DIRECTION_PLANS_FILTERED`;
- `PROTECTED_FLOOR_DONOR_WINDOW`;
- `PROTECTED_FLOOR_BOUNDARY`;
- `PROTECTED_FLOOR_TRIP_COUNT`;
- `PROTECTED_FLOOR_INTERNAL_HEADWAY`;
- `PROTECTED_FLOOR_SOURCE_AUTHORITY`; and
- `PROTECTED_FLOOR_NO_IMPROVING_COMPLIANT_CANDIDATE`.

The counts contain no passenger-level observation. They explain native heuristic pruning and do
not replace the canonical 6A2B candidate-rejection codes. These entries are absent when no floor
is enforceable, preserving historical logs.

## 11. Independent validation remains final

`validate_candidate_against_protected_service_floors_v1` remains integrated in
`validate_and_build_solution_v1`. Native filtering is an optimization only. It neither marks a
candidate accepted nor supplies proof-bearing feasibility.

Tests verify that an accepted native heuristic candidate passes common validation and that a
deliberately tampered post-search candidate is rejected by the common validator even when a
solver result continues to claim `FEASIBLE`.

## 12. Failure semantics

- Invalid or stale authority, missing binding, malformed projection, or source integration defect
  returns sanitized `MODEL_INVALID` before protected search.
- Exhausted bounded compliant search returns the existing non-proof `UNKNOWN` / no-candidate
  outcome.
- Unexpected generator failures retain sanitized heuristic-adapter failure handling and do not
  expose exception text, workbook paths, observations, or stack traces.

## 13. OR-Tools deferral

OR-Tools model constraints, objective stages, solver controls, outputs, and fingerprints are not
changed in 6A2C. [Milestone 6A2D](MILESTONE_6A2D_PROTECTED_SERVICE_FLOOR_ORTOOLS_CONSTRAINTS.md)
now implements the separately reviewed CP-SAT hard constraints and proof semantics.
