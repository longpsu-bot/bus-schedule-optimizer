# Milestone 6A2G — All-Days Operating Timetables

## Decision

Contract V1 adds one exact `OperatingDayType` value:

```text
all_days
```

This resolves `ALL_DAYS_CONTRACT_EXTENSION_REQUIRED` for an authorized operating fact that the
same approved timetable applies on every controlled calendar-day classification. Private source
workbooks, route-specific values, and private review reports remain outside the repository.

## Meaning

`all_days` means one authoritative timetable applies identically on:

- weekdays;
- Saturdays;
- Sundays;
- holidays; and
- special day classifications.

There is no separate timetable variant for any of those classifications. Scenario C inherits
the value through the existing operating-parameter lock and cannot change it.

## Demand and calendar boundary

The value grants timetable authority only. It does not mean:

- passenger demand is identical across day types;
- demand evidence covers every day type;
- holiday observations equal weekday observations;
- a route necessarily follows one timetable for the entire year;
- a calendar date can be inferred; or
- day-specific demand may be combined, duplicated, extrapolated, or fabricated.

Trip-ridership metadata therefore continues to require exactly one concrete day type. A concrete
dataset is compatible with an `all_days` Scenario B timetable because that timetable applies on
the dataset's declared day, but the dataset remains labeled with its original concrete type.
`all_days` is not accepted as a trip-ridership dataset day type.

## Runtime and artifact changes

- `OperatingDayType.ALL_DAYS` serializes as `all_days`.
- Scenario A and Scenario B JSON Schemas accept the new value and retain Contract V1's existing
  required-field behavior.
- XLSX Scenario A/B parameter validations expose `all_days` and explain its timetable-only scope.
- XLSX trip-ridership validation continues to expose only concrete day types.
- Import, normalization, serialization, solver problem construction, review output, and the
  existing Scenario C operating-day lock preserve the new value without calendar inference.
- Specific-day trip-ridership analysis and protected-floor evidence can bind to the matching
  `all_days` timetable without broadening demand authority.

## Compatibility

The change is additive. Existing five operating-day values, examples, and workbooks keep their
meaning. Contract version `1.0.0` is unchanged, and unknown values still fail closed.

## Acceptance evidence

Automated coverage verifies:

- enum, importer, normalization, serialization, and JSON Schema acceptance of `all_days`;
- rejection of unknown contract day types;
- XLSX timetable dropdown inclusion and trip-ridership dropdown exclusion;
- preservation of a concrete trip-ridership day under an `all_days` timetable;
- rejection of `all_days` as demand-observation coverage metadata; and
- continued eligibility and freshness checks for compatible protected-floor evidence.
