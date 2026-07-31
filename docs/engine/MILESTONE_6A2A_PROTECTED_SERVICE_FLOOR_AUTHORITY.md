# Milestone 6A2A: Protected high-demand service-floor authority

## 1. Purpose

Milestone 6A2A deterministically identifies current Scenario B service regimes that have
regular, short-headway service and sufficient repeated trip-level evidence of high demand. The
result is supplemental planning evidence for expert review. It does not alter Scenario C or any
optimization outcome.

## 2. Why authority precedes enforcement

A future hard floor can affect feasibility, donor supply, service windows, and solver results.
Those effects require a reviewed definition of the protected unit and its evidence first.
Milestone 6A2A therefore freezes the classification, reason codes, evidence, policy, and future
floor preview before Milestone 6A2B is authorized to enforce anything.

The preview explicitly states `NOT_ENFORCED_IN_6A2A`. It is never attached to a solver request,
candidate validator, heuristic, OR-Tools model, Scenario C, unified presentation, or Page 05
artifact.

## 3. Current B regime derivation

Regimes are derived independently for outbound and inbound directions from the exact normalized
Scenario B timetable. Trips are ordered by `(departure_time, trip_id)`. The established
`segment_continuous_headway_regimes_v1` exact-B service remains the single sustained-change
boundary detector; demand-derived and Scenario-C regime output is not reused as current-B
authority.

6A2A reconstructs the detector's boundaries into maximal, non-overlapping trip sequences. A
boundary trip belongs to exactly one regime, and the adjacent gap across the boundary is reported
as a transition rather than an internal headway. First/last trips and departures remain exact B
facts. A direction-wide single-gap fluctuation is retained as one regime and evaluated as
irregular instead of automatically creating a second protection candidate.

Internal headways must be positive whole minutes. Equal values are `REGULAR`; positive whole
minutes whose range is no larger than the policy tolerance are `BALANCED_ROUNDING`. Other
sequences carry explicit non-positive, non-whole-minute, or range-exceeded classifications.
Small or short derived segments remain visible so their failed minimum-size gates can be
reviewed.

## 4. Policy fields and defaults

`ProtectedServiceFloorPolicyV1` is frozen and slotted. Its defaults are:

- `maximum_protected_b_headway_minutes = 30`;
- `headway_rounding_tolerance_minutes = 1`;
- `minimum_departures_per_regime = 3`;
- `minimum_regime_duration_minutes = 30`;
- `minimum_observed_days_per_trip = 3`;
- `minimum_regime_trip_coverage_rate = 0.80`;
- `minimum_high_load_trip_share = 0.67`;
- `protected_load_statistic = "P85"`;
- `minimum_trip_ridership_confidence = "medium"`; and
- `future_service_window_boundary_tolerance_minutes = 0`.

Positive integer, nonnegative integer, rate, P85-only, and ordered-confidence validation is
performed by the policy model. Values are never inferred from the observed result.

The template declares isolated `protected_service_floor_*` keys in `CAU_HINH`. Isolation avoids
changing existing Scenario-C configuration semantics, especially the older
`minimum_regime_duration_minutes` setting. Workbooks without 6A2A keys receive the policy
defaults. Unprefixed Scenario-C or generic configuration keys are never aliases for 6A2A policy
and are ignored by the protected-service-floor policy loader.

## 5. Trip-ridership eligibility

Evidence is eligible only when the stored Milestone 6A1 analysis:

- verifies against the active workbook's supplemental-input fingerprint;
- verifies its own analysis fingerprint;
- matches the exact normalized Scenario B fingerprint;
- declares observed scenario B;
- matches Scenario B operating-day type; and
- meets the declared minimum confidence under
  `unknown < low < medium < high`.

User confidence is never upgraded. Missing input, failed analysis, stale analysis, and
below-minimum confidence produce stable not-evaluated classifications. There is no fallback to
`SAN_LUONG` block demand.

## 6. Per-trip evidence

Only 6A1 `MATCHED_EXACT` and `MATCHED_WITHIN_TOLERANCE` rows contribute. Every Scenario B trip in
a regime is joined to its existing 6A1 trip summary. A trip is coverage-eligible when its
distinct observation-day count meets the policy minimum. A coverage-eligible trip is high-load
when its P85 load factor is greater than or equal to Scenario B
`target_load_factor`.

Mean load factor never substitutes for P85. Scenario B `maximum_load_factor` is reported
separately as critical overload evidence and is not the high-demand threshold. Missing
observations remain missing rather than zero, and unobserved trip-days are not extrapolated.

## 7. Regime coverage

For each regime:

`regime trip coverage rate = coverage-eligible trips / total B trips`.

The evidence also reports trips with any usable observation, exact/tolerance match counts,
distinct represented service dates, and excluded records attributable to the regime where a
matched, supplied, or wholly contained candidate trip reference makes attribution deterministic.
Ambiguous records spanning regimes are not fabricated into either regime.

## 8. High-load classification

For each regime:

`high-load trip share = high-load eligible trips / coverage-eligible trips`.

When no trip is coverage-eligible, the share is `None`, not zero evidence. Minimum, median, and
maximum P85 load factor are calculated only from coverage-eligible trips with an available P85.
Trips whose P85 exceeds Scenario B `maximum_load_factor` are counted separately.

## 9. Protection gates

Protection is conjunctive. `PROTECTED_HIGH_DEMAND_SERVICE_FLOOR` requires:

1. regular or balanced-rounding representability;
2. a measurable B headway;
3. maximum internal B headway at or below the policy ceiling;
4. the minimum departure count;
5. the minimum duration;
6. eligible confidence;
7. the minimum regime trip-coverage rate;
8. the minimum high-load trip share;
9. at least one coverage-eligible trip; and
10. evidence bound to the current B timetable and trip dataset.

No strong result offsets another failed gate. Every applicable failed gate is returned in stable
order.

## 10. Non-protection reason codes

The stable public classifications include:

- `PROTECTED_HIGH_DEMAND_SERVICE_FLOOR`;
- `NOT_EVALUATED_NO_TRIP_RIDERSHIP`;
- `NOT_EVALUATED_STALE_TRIP_RIDERSHIP`;
- `NOT_EVALUATED_TRIP_RIDERSHIP_FAILED`;
- `NOT_EVALUATED_CONFIDENCE_BELOW_MINIMUM`;
- `NOT_PROTECTED_B_REGIME_NOT_REGULAR`;
- `NOT_PROTECTED_HEADWAY_NOT_MEASURABLE`;
- `NOT_PROTECTED_HEADWAY_ABOVE_CEILING`;
- `NOT_PROTECTED_TOO_FEW_DEPARTURES`;
- `NOT_PROTECTED_REGIME_TOO_SHORT`;
- `NOT_PROTECTED_INSUFFICIENT_TRIP_COVERAGE`; and
- `NOT_PROTECTED_HIGH_LOAD_SHARE_BELOW_THRESHOLD`.

`NOT_PROTECTED_NO_COVERAGE_ELIGIBLE_TRIPS` and
`NOT_PROTECTED_EVIDENCE_NOT_BOUND_TO_CURRENT_B` provide additional gate precision.

## 11. Future floor preview

Each protected regime receives a review-only preview:

- maximum future C headway equals maximum internal B headway;
- minimum future C trip count equals the current B regime trip count;
- protected window start/end equal the exact first/last B departures;
- boundary tolerance equals the policy value;
- donor removal is prohibited; and
- enforcement status is `NOT_ENFORCED_IN_6A2A`.

This describes the intended future 6A2B floor; it is not executable authority.

## 12. Fingerprints

The assessment contains separate Scenario B, trip-ridership input, trip-ridership analysis,
policy, regime-derivation, and assessment SHA-256 fingerprints. The assessment identity includes
the target/maximum load factors, regime facts, evidence, decisions, previews, issue codes, and
limitations.

The canonical currentness check validates the active Scenario B, trip-input and analysis
fingerprints, prefixed policy and policy fingerprint, target/maximum load thresholds,
regime-derivation profile and fingerprint, and the assessment fingerprint reconstructed from its
bound components. A missing, malformed, stale, or internally inconsistent binding fails closed.

Departure or timetable-order facts, headways, boundaries, passenger counts, dates, match and
collision results, P85, capacity, load thresholds, confidence, policy, and decisions alter the
appropriate identity. Source row order, notes, workbook path/bytes, and UI table order do not.

## 13. Runtime integration

The ordinary pipeline first obtains and verifies the Contract V1 result and unified
presentation. It then completes or classifies the optional 6A1 analysis, builds 6A2A against
`normalized_inputs.scenario_b`, and finally builds the unchanged figures and unified XLSX.

`UnifiedApplicationRunV1` stores
`protected_service_floor_assessment` or `protected_service_floor_failure`. Neither is part of
`BusScheduleOptimizationResult`, the presentation fingerprint, Scenario C, solver input, or
Page 05 metadata.

## 14. UI behavior

Page 01 displays the declared policy settings before submission but does not derive or classify
regimes. New upload, result clearing, and new execution clear both 6A2A session keys.

Below the 6A1 analysis, Page 03 displays the policy, every derived B regime, headway and
regularity, coverage/P85 evidence, decision, all failed gates, and protected previews. It labels
the result as proposed protection that is not applied to Scenario C. Page 03 delegates assessment
currentness to the canonical 6A2A domain helper and does not reclassify regimes. Pages 02, 04, and
05 retain their existing authority and behavior.

## 15. Failure isolation

An unexpected assessment exception produces
`PROTECTED_SERVICE_FLOOR_ASSESSMENT_FAILED`, a deterministic bounded correlation ID, and a
sanitized message. It exposes no raw observations and does not invalidate an otherwise valid
Contract result, presentation, figures, or downloads. It never invokes legacy.

## 16. Backward compatibility

Existing workbooks without the optional settings use reviewed defaults. Existing Contract/schema
files, normalization, solver requests, algorithms, objective vectors, candidate validation,
Scenario C, presentation, and Page 05 filenames/metadata remain unchanged. Milestone 6A1 remains
outside Contract demand authority.

## 17. Validation evidence

Focused tests cover uniform and balanced regimes, one-gap behavior, sustained boundaries,
transition classification, non-overlap, direction and row-order isolation, invalid headways,
every structural and evidence gate, P85 boundary behavior, coverage math, previews,
fingerprints, frozen/slotted models, input immutability, pipeline failure isolation, template
settings, UI labels, and protected-path source audits.

Regression validation includes Milestone 6A1, importer/template, application pipeline, Pages
01–05, unified presentation/export/artifacts, solver, route-corpus, release-audit, full Pytest,
Ruff, formatting, `git diff --check`, and protected-file diffs.

## 18. Exact 6A2B boundary

Milestone 6A2B may separately enforce:

- `headway_C <= headway_B`;
- `trip_count_C >= trip_count_B` inside the protected window;
- no material shrinking of the protected window; and
- no use of protected-regime trips as donor supply.

6A2A implements none of those constraints. It does not filter or reject candidates, change
donor selection, insert/delete trips, vary trip counts, minimize fleet, or add heuristic or
OR-Tools constraints.
