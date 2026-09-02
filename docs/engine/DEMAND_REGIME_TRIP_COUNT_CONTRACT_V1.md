# Demand Regime Interval and Trip-Count Contract V1

**Status:** canonical future-facing domain contract
**Scope:** deterministic demand regimes and the input boundary for a later trip-allocation stage
**Does not implement:** trip allocation, departure generation, phase optimization, timetable
compilation, transition optimization, fleet assignment, or OR/CP-SAT changes

## Regime interval

A demand regime is a service-demand interval with half-open semantics:

```text
[start, end)
start <= departure < end
```

For adjacent regimes `[07:00, 10:00)` and `[10:00, 13:00)`, a `10:00` departure
belongs only to the later regime. The intervals partition their service-demand window without
overlap or double-counting.

A boundary records a change in demand or service policy. It is not a departure anchor. A compiled
timetable is not required to contain a departure at either `regime.start` or `regime.end`.

## Allocation contract

`RegimeTripAllocationV1.trip_count` means:

```text
trip_count_r = #{t : start_r <= departure_t < end_r}
```

The allocation contract contains only `regime_id` and `trip_count`. Exact departures, headway,
phase, transition gaps, and fleet assignment belong to later stages.

For a positive trip count, nominal service headway is a service-rate quantity:

```text
h_nominal = regime_duration / trip_count
```

For a 180-minute regime and 10 trips, nominal headway is 18 minutes, not 20 minutes. A zero trip
count produces no nominal headway (`None`) and never division by zero. Whether a zero-trip regime is
operationally permitted is a later service-floor decision.

## Future compiler constraints

Because boundaries are not departure anchors, a future compiler may select a phase offset in a
representation such as `t_k = start + phase + k * h`, provided every generated departure belongs
to `[start, end)`. Phase selection is not implemented in this milestone.

Future internal regime headways may be uniform while a cross-boundary transition gap differs from
both adjacent internal headways. For example, internal headways of 20 and 12 minutes may be joined
by a 14-minute transition gap. The compiler will assess transition quality globally; this milestone
does not optimize it.

## Service-floor implication

For a closing regime `[19:00, 21:30)` of 150 minutes and a target maximum nominal headway of 30
minutes, the nominal allocation basis is `ceil(150 / 30) = 5` trips. It is not automatically six
trips from anchoring both endpoints. Allocation floors and compiled-timetable feasibility remain
separate: the future compiler must validate actual first/last-trip and cross-boundary gaps across the
whole timetable.

## Architecture

```text
DemandProfile
      -> Deterministic Regime Detector
      -> RegimePlan
      -> Deterministic Trip Allocation          (next milestone)
      -> RegimeTripAllocationV1
      -> Schedule Compiler
           - integer-minute internal headway
           - uniform internal headway
           - phase optimization
           - boundary transition quality
      -> Fleet / OR Validator
      -> Final timetable C
```

Existing Scenario C headway-regime models describe exact member-departure endpoints and may use a
`trip_count - 1` gap count. They are a different contract and are not authority for demand-regime
allocation semantics.
