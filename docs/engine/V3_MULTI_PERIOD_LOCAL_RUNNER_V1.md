# V3 multi-period demand and local runner V1

## Scope and compatibility

The V3 path is opt-in and is identified by:

- `multi_period_demand_input_v1`
- `demand_profile_derivation_v1`
- `v3_multi_period_runner_v1`

Legacy `SAN_LUONG` normalization remains single-period and continues to reject multiple
observation periods. V2 balanced-rounding behavior is not used or changed by this workflow.

## Authority flow

`PERIOD_CATALOG` and `SAN_LUONG_MULTI_PERIOD` are read as independent observation periods.
Each period is validated and fingerprinted before any profile is derived. Repeated time blocks
in different periods are valid; duplicates or overlaps inside one period are not.

The V1 derivation methods are:

- `single_period`: reproduce one validated period after converting total-period volume to an
  average day when necessary.
- `day_weighted_mean`: for every matching direction/time block, multiply each period's
  average-day value by its own `observation_days`, sum, and divide by total observation days.

The selected profile fingerprint binds the two-stage demand authority and adapter context.
Changing source values, observation days, direction grain, included periods, aggregation
configuration, or a source-period fingerprint therefore changes Scenario C problem identity.

## Structural-change diagnostic

For every included period and direction, the runner reports average daily passengers, the
normalized time-block share vector, the peak block, and peak share. Pairwise shape distance is:

```text
distance = sum(abs(period_share - other_period_share)) / 2
```

The metric is bounded from 0 to 1. The default warning threshold is `0.15`. Exceeding it emits
`MULTI_PERIOD_STRUCTURAL_CHANGE_DETECTED`; it never rejects the profile or changes weights.

## CLI

One explicit profile:

```powershell
python scripts/run_v3_two_stage.py `
  --input "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx" `
  --profile STABLE_MAR_JUL_2026 `
  --output-dir "output/mst6/stable_mar_jul"
```

If `--profile` is omitted, `default_demand_profile` in `THONG_TIN_DU_LIEU` is required.

Independent batch sensitivity:

```powershell
python scripts/run_v3_two_stage.py `
  --input "Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx" `
  --profiles STABLE_MAR_JUL_2026,BASELINE_MAR_JUN_2026,CURRENT_JUL_2026 `
  --output-dir "output/mst10"
```

Every profile receives a new solver and its own 120-second total budget. Stage 1 and all bounded
Stage 2 attempts share that budget. No run is retried automatically.

## Batch classification

- `STABLE_ACROSS_PROFILES`: status, Stage 1 allocation, regime structure/headways, fleet,
  maximum service gap, and shift metrics all match.
- `MATERIAL_PROFILE_SENSITIVITY`: any status, allocation, regime structure/headway, or fleet
  difference; a maximum service-gap or maximum-shift difference over 5 minutes; or a total-shift
  difference greater than one minute per daily trip.
- `MINOR_PROFILE_SENSITIVITY`: differences exist but none cross the material rule.

Material sensitivity also emits `PROFILE_SENSITIVITY_REVIEW_REQUIRED`. Classification never
changes the configured primary profile.

Private input workbooks and generated pilot outputs belong outside version control. The
repository ignores `local_inputs/` and `local_outputs/` for this purpose.
