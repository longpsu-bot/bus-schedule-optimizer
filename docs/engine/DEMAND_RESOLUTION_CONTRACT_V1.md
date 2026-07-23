# Demand Resolution Contract V1

The normative sources are [Engine Contract V1 §§2.4–2.6 and §7](ENGINE_CONTRACT_V1.md) and [Amendment V1-A1](EXTREME_SERVICE_CHANGE_AND_DEMAND_SCENARIO_AMENDMENT_V1.md). This document describes the planned block-building workflow without redefining those rules.

## Resolution detection

The normalizer records the source grain before aggregation:

1. Timestamp-level observations: retain actual timestamps; a supported bin may be derived and documented.
2. Trip-level observations: retain trip IDs/times; bins may be derived no finer than actual event evidence supports.
3. Regular intervals: `source_resolution_minutes` is the common interval duration.
4. Irregular intervals: retain each source interval and mark `source_is_irregular`.
5. Daily total only: mark `daily_total`; do not create intraday blocks.

Mixed resolutions require an explicit conservative policy. The default is the coarsest reliable resolution within a comparison, unless the higher-resolution subset is separately labeled and not generalized.

## Average-day normalization

For `total_observation_period`, normalized demand equals source passenger count divided by validated observation days. Preserve source total, period, denominator, and normalized result. For `average_day`, do not divide again. Zero/negative denominators and inconsistent period metadata are blocking.

## Native mode

Emit one analysis block per supported source interval after average-day normalization. Adjacent source records may remain separate even if their values match. No interpolation is implied.

## Adaptive mode

An implementation should use a deterministic, reviewable pipeline:

1. Begin with native intervals.
2. Apply only the configured smoothing method; `none` is valid and preferred for first implementation.
3. Mark candidate boundaries where the rate changes by at least `material_change_ratio` for `minimum_sustained_intervals`.
4. Merge adjacent intervals within min/max duration limits.
5. Before accepting a merge, test whether it would hide `CRITICAL_ABOVE_90`, `NO_SERVICE_WITH_DEMAND`, or material directional divergence.
6. Emit boundary reasons and all contributing source interval IDs.

The algorithm may merge; it may not manufacture sub-interval demand. Solver allocations may use minute-level departure variables, but demand evidence remains at the source-supported grain.

## Manual mode

Manual boundaries are validated against the source coverage and grain. Aggregating source intervals is permitted. Splitting a regular interval is not permitted unless timestamp/trip-level evidence supports it. If a manual boundary cuts a source interval for presentation only, the result must be labeled interpolated and is not authoritative for overload conclusions unless an approved interpolation method exists.

## Direction handling

- Directional observations produce outbound and inbound blocks at compatible boundaries; totals are reconciled from components.
- Combined observations produce combined blocks only.
- Combined values are never apportioned by current/proposed trip shares and then presented as observed directional demand.
- Adaptive merging is evaluated per direction and then aligned where necessary without hiding a directional event.

## Variable-duration comparisons

Every output exposes both passengers in interval and passengers/hour. Default diagrams and comparative tables use rates when durations vary. Required trips remain integer counts for the actual interval; required trip rates normalize those counts for comparison.

## Confidence and interpolation

Confidence is propagated, not upgraded by aggregation. A block confidence may be no stronger than its weakest material source unless a reviewed statistical rule says otherwise. `interpolation_status` values in the draft are `none`, `aggregated`, `interpolated_supported`, and `unsupported`; `unsupported` blocks cannot support authoritative demand-suitability conclusions.

## Acceptance checks

- source passenger totals reconcile before/after normalization and aggregation;
- no block is finer than unsupported source grain;
- block IDs and source IDs are complete;
- no overlap or unexplained gap exists in the declared coverage;
- critical/no-service states survive adaptive construction;
- daily-total-only data remains intraday-insufficient;
- demand block boundaries are not emitted as headway regime anchors.

## Structural service-change support

Demand resolution and proposed service resolution are separate. The engine derives `departures_per_source_demand_interval_A/B`, directional headways, total/directional service-change factors, and local interval changes from exact A/B timetables.

A source interval that contains several B departures supports aggregate interval demand and capacity only. It does not support observed passenger counts for each proposed departure. `demand_temporal_support` is `full`, `partial`, `coarse`, or `unsupported`; `frequency_change_support` is `within_observed_range`, `extrapolation`, or `structural_change`.

When the proposal is structural and no calibrated model exists, `demand_response_support = scenario_analysis_required`. Native/adaptive/manual block construction remains at source-supported grain. Scenario demand assumptions are evaluated over those same authoritative blocks and are labeled assumptions, never observations.

Acceptance checks additionally require:

- total trips are reconciled to actual directional counts before headway analysis;
- no global percentage threshold is the sole structural-change rule;
- coarse source demand is not split among finer B departures;
- static A demand is identified as a lower-bound comparison rather than a ridership forecast;
- required V1-A1 diagnostic codes and post-implementation monitoring limitations propagate to evaluation and presentation.
