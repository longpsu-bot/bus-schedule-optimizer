# Milestone 6A1: Trip-level ridership analysis

## 1. Purpose

Milestone 6A1 imports optional trip-level passenger observations, deterministically matches them
to the normalized Scenario B timetable, and produces coverage-aware descriptive statistics.
The output helps reviewers understand which scheduled trips have direct evidence and which input
records are unsafe to use.

## 2. Current interval-demand limitation

Contract V1 receives optimization demand only through `SAN_LUONG`. Those records describe time
intervals and do not identify one scheduled Scenario B trip. A route report or interval total
therefore cannot be treated as a trip observation.

## 3. Supplemental authority boundary

`SAN_LUONG_CHUYEN` is application/domain evidence outside Contract V1. It is never converted to
`SAN_LUONG`, `DemandObservation`, `ObservedDemandInput`, or `DemandResolutionType.TRIP`.
`SAN_LUONG` remains the only optimizer demand authority. Trip observations do not change the
adjustment decision, solver request, solver outcome, accepted Scenario C, unified presentation,
figures, or Page 05 artifacts.

When only trip observations exist, Contract V1 keeps its existing insufficient-demand behavior
while the supplemental analysis may still describe Scenario B.

## 4. Workbook sheets

- `THONG_TIN_SAN_LUONG_CHUYEN` contains dataset identity and matching authority.
- `SAN_LUONG_CHUYEN` contains one observation per row.

Both sheets are optional. A data sheet with records requires the metadata sheet. An empty data
sheet is treated as not provided. The separate metadata sheet prevents trip evidence from being
silently mixed with `THONG_TIN_DU_LIEU`.

## 5. Metadata contract

Records require:

- `trip_ridership_dataset_id`;
- `trip_ridership_source_type`;
- `trip_ridership_confidence`;
- `observed_schedule_scenario`, fixed to `B`;
- `operating_day_type`, one concrete day type exactly equal to Scenario B, except that any one
  concrete day type is compatible when Scenario B is `all_days`;
- `match_tolerance_minutes`, an integer from 0 through 30 inclusive.

`source_notes` is optional and is excluded from fingerprints. Source types are `ticketing`,
`manual_count`, `apc`, `survey`, or `other`; aggregate route reports are not accepted.
Operating-day type is never inferred from calendar dates. Trip-ridership metadata never accepts
`all_days`: the dataset retains one specific observed day classification, even when the same
Scenario B timetable applies on every day. No demand days are combined or fabricated.

## 6. Observation contract

The required columns are `observation_id`, `service_date`, `source_trip_id`,
`scheduled_trip_id`, `direction`, `scheduled_departure_time`, `actual_departure_time`,
`passenger_count`, `vehicle_id`, and `notes`.

Each nonblank row requires a unique trimmed observation ID, service date, `outbound` or
`inbound` direction, a whole passenger count greater than or equal to zero, and at least one of
scheduled trip ID, scheduled departure time, or actual departure time. Zero passengers is a real
observation. Trip times use the half-open service-day domain `0 <= seconds < 86400`: `00:00`
through `23:59:59` are valid, while every representation of `24:00` is rejected because
`service_date` owns the calendar-day boundary. Formulas are rejected as data authority. Imported
source rows and workbook bytes are never mutated.

## 7. Deterministic matching precedence

Matching uses this fixed precedence:

1. An explicit `scheduled_trip_id` must exist in Scenario B, have the same direction, and agree
   exactly with any supplied scheduled time. Contradictions are `INVALID` and never fall back.
2. Without an ID, scheduled departure time considers only same-direction Scenario B trips within
   the inclusive tolerance. A unique nearest candidate matches; equal nearest candidates are
   `AMBIGUOUS`.
3. Actual departure time is used only when both ID and scheduled time are absent, with the same
   same-direction nearest-candidate rule.

There is no global assignment, row-order tie-break, neighboring-row inference, or cross-direction
matching. One observation can provisionally match at most one trip.

## 8. Collision rules

After provisional matching, all records are grouped by `(service_date, Scenario B trip_id)`.
When a group contains two or more observations, every record becomes `COLLISION`. None is
selected, summed, averaged, or deduplicated. All remain in diagnostic output with
`DUPLICATE_OBSERVATION_FOR_TRIP_DATE`.

## 9. Usable-record rules

Only `MATCHED_EXACT` and `MATCHED_WITHIN_TOLERANCE` contribute passenger statistics.
`UNMATCHED`, `AMBIGUOUS`, `COLLISION`, and `INVALID` records are excluded. Missing observations
are not converted to zero; an explicit zero count remains included.

## 10. Per-trip statistics

Every Scenario B trip remains in output, including trips with no usable observation. Statistics
include observation and distinct-day counts, minimum, maximum, mean, median, nearest-rank P85
and P90, corresponding load factors, target/maximum threshold day counts and shares, match-method
counts, and absolute matching offsets.

An explicit trip capacity override is used when present; otherwise Scenario B vehicle capacity
is used. Nearest-rank percentiles select `ceil(p * N)` from sorted observations and never
interpolate passenger counts. Trips with no usable records have zero counts and `None`
descriptive values.

## 11. Direction and route summaries

Each direction and the route dataset report scheduled trips, observed trips, usable and excluded
status counts, distinct dates, observed matched passengers, matched passengers per observed trip,
matched passengers per service date, scheduled-trip coverage, and trip-date coverage. No missing
trip-day is extrapolated.

## 12. Coverage interpretation

Scheduled-trip coverage is:

`Scenario B trips with at least one usable observation / total Scenario B trips`.

Matched trip-date coverage is:

`unique usable (service_date, trip_id) pairs / (Scenario B trips * valid distinct service dates)`.

Passenger totals are labeled as observed matched passengers. Unless trip-date coverage is
exactly 100%, the analysis states that coverage-adjusted interpretation is unavailable and never
claims a full daily route total.

## 13. Supplemental input and analysis fingerprints

Supplemental input identity and analysis identity are separate. The deterministic SHA-256
`trip_ridership_input_fingerprint` is independently computable before matching from dataset ID,
source type, confidence, observed scenario, operating-day type, tolerance, sorted normalized
observation facts, and the Contract V1 Scenario B fingerprint. Workbook paths, bytes, metadata
notes, observation notes, and row order are excluded.

The distinct `analysis_fingerprint` binds that input identity to the matching-policy identity,
deterministic match and collision results, original record count, trip/direction/route summaries,
issue codes, and limitations. Semantic row reorder or notes-only edits change neither identity.
Passenger facts, dates, directions, references, tolerance, Scenario B, capacity, and collision
outcomes change the appropriate identity.

## 14. Runtime integration

The ordinary application remains readiness-first and Contract V1-only. It builds and verifies
the normal Contract result and presentation, then analyzes optional trip evidence against
`normalized_inputs.scenario_b`. The supplemental result is bound to
`normalized_inputs.scenario_b_fingerprint` and stored only in `trip_ridership_analysis` or
`trip_ridership_failure`.

## 15. UI behavior

Page 01 previews both new sheets and displays imported trip-record count before submission; it
does not match observations before the form is submitted. Page 03 labels the analysis as
supplemental, displays dataset quality, direction/route coverage, per-trip statistics, and
excluded-record diagnostics. Before rendering, Page 03 independently recomputes only the bounded
supplemental input fingerprint and verifies it together with Scenario B identity and the stored
analysis-integrity fingerprint. A stale same-B/different-dataset analysis is rejected without
rerunning matching. Pages 02, 04, and 05 retain their existing Contract V1 authority and Page 05
filenames/downloads.

## 16. Failure isolation

Normal unmatched, ambiguous, collided, invalid, or no-usable results are descriptive outcomes.
An unexpected exception produces `TRIP_RIDERSHIP_ANALYSIS_FAILED` and a bounded deterministic
correlation ID. It does not invoke legacy, erase a valid Contract V1 result, fabricate trip
statistics, or log raw observation rows.

## 17. Backward compatibility

`ImportedWorkbook` adds optional metadata and an immutable observation tuple with safe defaults.
Existing constructors and workbooks without the sheets retain prior behavior. Existing
`SAN_LUONG`, Contract V1 normalization, solver inputs, Scenario C generation, presentation, and
download authority are unchanged.

## 18. Validation evidence

Automated tests cover optional-sheet import, metadata and row validation, exact/fuzzy/ambiguous
matching, precedence, inclusive tolerance, direction isolation, collisions, multi-date
observations, descriptive statistics, capacity overrides, coverage, row-order determinism,
fingerprint sensitivity, source immutability, pipeline result equivalence, supplemental failure
isolation, Page 01 facts, Page 03 rendering, and stale-analysis rejection. Existing Contract,
solver, exporter, UI, route-corpus, and offline release-audit suites remain regression gates.

## 19. Explicit exclusions

Milestone 6A1 does not implement forecasting, imputation, trip insertion/deletion, variable trip
counts, fleet minimization, automatic workbook conversion, legacy deletion, Contract 1.1.0,
V1-A1, Milestone 5C3, or the cancelled Phase B architecture. It does not change headway,
candidate validation, objective vectors, heuristic logic, or OR-Tools logic.

## 20. Milestone 6A2 boundary

A future protected high-demand service floor may enforce:

- `headway_C <= headway_B`;
- `trip_count_C >= trip_count_B`;
- no material shrinking of the protected service window; and
- no removal of donor trips from a protected regime.

Milestone 6A1 only records this boundary. It does not classify protected regimes or enforce any
of these rules.
