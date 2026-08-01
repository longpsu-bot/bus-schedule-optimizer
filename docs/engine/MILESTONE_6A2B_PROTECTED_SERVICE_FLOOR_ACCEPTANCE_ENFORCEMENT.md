# Milestone 6A2B: Protected service-floor acceptance enforcement

## 1. Purpose

Milestone 6A2B makes the reviewed 6A2A floor executable at the common independent candidate
validator. A solver-produced Scenario C candidate cannot be accepted when it weakens a current,
evidence-bound protected Scenario B regime below its approved floor.

This milestone enforces acceptance semantics only. It does not add protected-floor constraints
or objectives to the heuristic or OR-Tools search implementations.

Status note: [Milestone 6A2C](MILESTONE_6A2C_PROTECTED_SERVICE_FLOOR_HEURISTIC_SEARCH.md) now
adds bounded heuristic search awareness while retaining this common validator as final authority.
[Milestone 6A2D](MILESTONE_6A2D_PROTECTED_SERVICE_FLOOR_ORTOOLS_CONSTRAINTS.md) now adds hard
constraints to the canonical OR-Tools service-quality model with the same final-validator rule.

## 2. Authoritative pre-solver sequence

The ordinary application path now performs these steps in order:

1. assess workbook input readiness;
2. normalize the workbook once;
3. build or classify trip-ridership analysis against that normalized Scenario B;
4. build 6A2A and call its canonical currentness verifier against the same inputs;
5. derive and verify the 6A2B enforcement authority;
6. evaluate Scenario B and conditionally run the selected solver;
7. independently validate any raw candidate against Contract V1 and 6A2B; and
8. build presentation and artifacts from the verified result.

`analyze_and_optimize_schedule_v1` remains the backward-compatible imported-workbook wrapper and
always normalizes the supplied workbook with the supplied normalization options. The ordinary
application calls the package-internal normalized execution path directly with its already
verified bundle, so normalization is not repeated and callers cannot inject a normalized bundle
through the public wrapper.

## 3. Enforcement authority

`ProtectedServiceFloorEnforcementAuthorityV1` and its regime records are frozen and slotted. The
authority binds:

- the exact Scenario B fingerprint;
- the 6A2A assessment fingerprint;
- the protected-floor policy and regime-derivation fingerprints;
- the trip-ridership input and analysis fingerprints, including reviewed `None` values;
- the active target and maximum load factors;
- deterministically ordered enforceable regimes; and
- the `m6a2b_protected_service_floor_acceptance_enforcement_v1` profile and its SHA-256
  enforcement fingerprint.

Only a 6A2A decision classified `PROTECTED_HIGH_DEMAND_SERVICE_FLOOR` can become an enforceable
regime. Decisions, previews, and derived regimes must reconcile one-to-one. Regimes are sorted by
direction, protected start, protected end, and regime ID. Their ordered Scenario B member IDs are
also checked against exact Scenario B departure order. A protected source member cannot belong to
two enforcement regimes.

The builder calls `protected_service_floor_assessment_is_current_v1` before promotion. The
generation-context validator then rechecks the enforcement fingerprint, exact Scenario B
fingerprint, member existence, direction, ordering, boundary facts, non-overlap, and numeric
limits before a solver may run.

## 4. Candidate enforcement semantics

Every protected regime is evaluated independently and by direction.

### Protected membership and order

Every ordered protected Scenario B source trip must map to exactly one raw Scenario C trip.
Missing and duplicated protected mappings are rejected even when Contract V1 also reports its
one-to-one mapping codes. Every uniquely mapped protected source must independently retain the
protected regime direction; a wrong-direction mapping is rejected and is ineligible for protected
order, boundary, donor, count-window, or headway authority. Unrelated correctly directed trips do
not cure that source-direction violation. Eligible protected members must preserve Scenario B
order when sorted by `(c_departure_time, c_trip_id)`.

### Donor removal

When `donor_removal_prohibited` is true, each protected source member must remain between:

`protected_window_start - boundary_tolerance`

and

`protected_window_end + boundary_tolerance`.

Moving a protected member outside that interval is donor removal. An unrelated replacement trip
does not cure the violation.

### Service window

The earliest protected source member must remain within the declared tolerance of the protected
start, and the latest member must remain within the tolerance of the protected end. With the
default zero tolerance, both boundaries are exact. Inward, outward, shifted, or materially
shortened windows outside tolerance are rejected.

The tolerance applies only to the two window boundaries. It is not added to any internal
headway allowance.

### Count and internal headways

The candidate count window is bounded by the uniquely reconciled first and last ordered protected
source members. All Scenario C departures in the same direction and inside that inclusive window
count, including additional same-direction trips. Opposite-direction trips never count.

The count must be at least `minimum_future_c_trip_count`. Same-direction departures inside the
window are sorted by `(c_departure_time, c_trip_id)`. Every consecutive internal gap must be
positive, divisible by 60 seconds, and no larger than
`maximum_future_c_headway_minutes`. Transition gaps outside the verified window are excluded.

Adjacent 6A2A regimes remain separate. They are neither merged nor allowed to share protected
source membership, even when their floors are numerically equal.

## 5. Stable rejection codes

Protected-floor codes are appended after deterministically sorted Contract V1 codes in this
stable order:

1. `PROTECTED_SOURCE_TRIP_MISSING_OR_DUPLICATED`;
2. `PROTECTED_SOURCE_DIRECTION_VIOLATION`;
3. `PROTECTED_SOURCE_ORDER_VIOLATION`;
4. `PROTECTED_DONOR_REMOVAL`;
5. `PROTECTED_WINDOW_START_VIOLATION`;
6. `PROTECTED_WINDOW_END_VIOLATION`;
7. `PROTECTED_TRIP_COUNT_BELOW_FLOOR`;
8. `PROTECTED_INTERNAL_HEADWAY_ABOVE_FLOOR`;
9. `PROTECTED_HEADWAY_NOT_MEASURABLE_OR_INVALID`; and
10. `PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_MISMATCH`.

The validator collects every applicable protected failure; it does not stop at the first one.
Existing Contract V1 validation and rejection codes continue to run.

## 6. Result and identity binding

A solver candidate that fails 6A2B uses
`CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR`. Its diagnostic contains all rejection codes plus the
enforcement and enforcement-validation fingerprints. The validation fingerprint binds the
authority fingerprint, raw candidate fingerprint, acceptance status, and ordered rejection
codes.

Accepted solutions and outcomes carry the enforcement and validation fingerprints. Their
solution and outcome fingerprints therefore bind the supplemental authority whenever a floor is
enforced. The generation context also carries the typed authority.

When there are no enforceable regimes, the authority is retained as reviewed application
evidence but omitted from the Contract V1 generation context. Optional enforcement fields are
omitted from Contract serialization and fingerprint payloads. Existing problem, candidate,
solution, and outcome fingerprints consequently remain byte-for-byte unchanged.

The Contract V1 schemas add only optional fingerprint properties. Contract V2 is not introduced.

## 7. No protection versus authority failure

No observations, insufficient confidence or coverage, and no regime passing all protection gates
are valid reviewed no-protection results. The solver runs normally and Scenario C behavior and
identities remain unchanged.

Unexpected analysis failure, assessment construction failure, failed 6A2A currentness, Scenario B
mismatch, or invalid enforcement identity produces
`PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID`. Scenario B normalization and evaluation
remain available, but Scenario C generation is blocked. The application does not silently fall
back to an unprotected solver run, classify the failure as route or fleet infeasibility, expose
raw observations, or display exception text.

## 8. Candidate rejection is not infeasibility proof

Rejection proves only that the returned raw candidate cannot be accepted under the current floor.
Because neither solver searches natively within that floor, rejection is not proof that no
compliant candidate exists. The outcome limitation says so explicitly and does not use
`NO_FEASIBLE_C_WITH_B_PARAMETERS` for this case.

## 9. UI and artifact boundary

Page 03 displays a separate 6A2B state: no protected regimes, current authority, accepted under
the floors, rejected by floor validation, or invalid authority. The historical 6A2A preview keeps
`NOT_ENFORCED_IN_6A2A`. Raw trip observations remain hidden.

Page 05, its filenames, workbook metadata, charts, exporters, and presentation authority are not
changed. Enforcement evidence remains in the optimization outcome and Page 03 state.

## 10. Deferred search-aware work

This milestone does not change `generate_scenario_c`, donor selection, heuristic movement,
OR-Tools hard constraints, CP-SAT objective stages, trip count, solver limits, worker count, or
random seed. Native protected-floor search requires a separate reviewed milestone. The common
validator remains final acceptance authority even after native search constraints exist.
