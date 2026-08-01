# Milestone 6A2D: Protected service-floor hard constraints in OR-Tools

## 1. Purpose and authority sequence

Milestone 6A2D makes the canonical `OrToolsCpSatServiceQualitySolver` search natively inside the
protected floors already defined by 6A2A and enforced at common candidate acceptance by 6A2B.
It follows 6A2C heuristic awareness so both production search paths now avoid knowingly returning
a floor-violating candidate.

Search constraints do not become acceptance authority. Every raw OR-Tools candidate still passes
through `validate_and_build_solution_v1` and the unchanged independent
`validate_candidate_against_protected_service_floors_v1` check.

## 2. Exact authority binding

`build_ortools_service_quality_request_v1` supplies the same complete
`ProtectedServiceFloorEnforcementAuthorityV1` to the generation context and the OR-Tools quality
adapter. The adapter retains that object alongside its existing exact-demand authority. It never
reconstructs floors from workbook policy, ridership observations, 6A2A rows, demand blocks,
solution regimes, or UI state.

The adapter exposes `protected_service_floor_enforcement_fingerprint`. It is the exact 6A2B
enforcement fingerprint only when regimes are enforceable; no authority and a valid empty
authority both expose `None` and use the historical no-floor path.

## 3. Conditional adapter-context fingerprint

Without enforceable protection, `problem.adapter_context_fingerprint` remains exactly the
historical exact-demand authority fingerprint. No optional `null` is introduced.

With enforceable protection, the adapter context is the canonical SHA-256 of:

- profile `ortools_quality_exact_demand_and_protected_floor_v1`;
- service-quality adapter ID `ortools_cp_sat_quality_v1`;
- exact-demand authority fingerprint; and
- protected-floor enforcement fingerprint.

The profile and both authority identities therefore contribute independently to the problem
fingerprint while valid no-floor requests preserve their previous identities byte for byte.

## 4. Execution-boundary reconciliation

Before `solver.solve(problem)` is called, orchestration validates and reconciles:

- the generation-context enforcement authority;
- the adapter-held enforcement authority;
- the adapter's optional native-search enforcement fingerprint;
- the self-consistent exact-demand authority fingerprint;
- the conditional composite adapter context;
- `problem.adapter_context_fingerprint`; and
- the authority's exact Scenario B fingerprint.

Malformed, stale, missing, crossed empty/enforceable, or differently bound authorities return
`MODEL_INVALID` with `ORTOOLS_PROTECTED_FLOOR_AUTHORITY_MISMATCH`. The solver and CP-SAT model
builder are not invoked. This result is an integration defect, not route, timetable, fleet,
demand, policy, or global infeasibility.

## 5. Deterministic projection

`ortools_protected_floor.py` mechanically projects the exact 6A2B authority into immutable
CP-SAT-ready facts. Each regime retains its ID, Contract direction, ordered protected source IDs,
directional source indices, inclusive first/last indices, maximum headway, minimum count,
minute-valued window boundaries, tolerance, and donor-removal rule.

The projection retains the exact enforcement and Scenario B fingerprints, uses profile
`m6a2d_ortools_protected_service_floor_projection_v1`, and has its own deterministic fingerprint.
It does not reclassify protection.

Projection validation proves authority validity, exact source uniqueness, declared direction,
canonical source and authority order, non-overlapping membership and source slices, minute-aligned
exact boundaries, nonnegative tolerance, positive headway, structural count feasibility, and the
exact-B feasibility invariant. A defect is `MODEL_INVALID`, never CP-SAT `INFEASIBLE`.

## 6. Source-slice equivalence

The model already has one minute-valued departure variable for every Scenario B source trip,
fixed source mapping and direction, strict directional source order, fixed directional endpoints,
and fixed trip counts.

For a projected regime, the inclusive canonical directional slice from its first protected
source index through its last protected source index is therefore exactly the set of
same-direction candidate trips inside the protected member-bounded window. Unprotected source
trips between protected members remain in the slice and count exactly as they do in 6A2B common
validation.

The slice length is checked against the minimum count before model construction. No trip-count
decision variable, insertion, deletion, or compensating trip is introduced.

## 7. CP-SAT hard constraints

For each regime, the quality model adds only linear constraints over existing departure
variables:

- every protected member subject to donor prohibition stays within
  `[protected start - tolerance, protected end + tolerance]`;
- the first protected member stays within `protected start +/- tolerance`;
- the last protected member stays within `protected end +/- tolerance`; and
- every consecutive pair in the complete inclusive source slice has a positive existing strict
  order gap no larger than the exact maximum protected headway.

Tolerance is not added to the internal-headway maximum. The gap before the first slice member and
the gap after the last slice member are not constrained by the protected maximum. Adjacent and
opposite-direction regimes are applied independently and never merged.

## 8. Exact-B feasibility invariant

Projection construction checks the exact Scenario B assignment against every donor interval,
boundary, structural count, and full-slice headway fact. An authority derived from current B must
permit exact B. Failure is an authority/integration defect and blocks model construction.

## 9. Solver status and proof scope

- `MODEL_INVALID` identifies authority binding, projection, integer, or model-construction
  defects and supplies no domain-infeasibility conclusion.
- `UNKNOWN` means the existing solve budget established neither feasibility nor infeasibility.
- `FEASIBLE` means CP-SAT found a candidate under the complete encoded hard model but did not
  finish the existing staged proof sequence.
- `OPTIMAL` means the unchanged staged objective sequence was proven for the encoded fixed-resource
  model; it is not global policy optimality.
- `INFEASIBLE` is limited to the complete encoded model: current Scenario B operating locks,
  fixed trip count and direction, available-fleet and terminal constraints, demand/service-quality
  hard constraints, and the exact bound floor. It is not a claim that the policy alone, expanded
  fleet, or every possible operating policy is infeasible.

## 10. Objective and control preservation

The fifteen service-quality stage names and lexicographic order are unchanged. Demand scaling,
regime-quality construction, time limit, worker count, random seed, candidate reconstruction, and
objective recomputation are unchanged. Protected constraints are hard feasibility conditions,
not penalties or new objectives.

## 11. Independent validation and identity compatibility

Candidate reconstruction remains one-to-one with Scenario B sources. Solver limitations identify
the exact encoded enforcement fingerprint and state that common 6A2B validation remains final.
Native feasibility cannot override common rejection.

Frozen no-floor regression evidence covers the exact-demand, adapter-context, problem, raw
candidate, solution, and outcome fingerprints; objective vector; status; timetable; and staged
attempted/proven evidence. No authority and valid empty authority preserve the historical model
and identities.

## 12. Non-goals and isolation

6A2D adds no objective, soft penalty, policy relaxation, variable trip count, trip insertion or
deletion, fleet expansion or minimization, direction redistribution, cross-regime substitution,
schema field, UI change, Page 05 change, presentation/export change, or route-fixture change.
The base historical OR-Tools adapters and the 6A2C heuristic implementation are unchanged.
