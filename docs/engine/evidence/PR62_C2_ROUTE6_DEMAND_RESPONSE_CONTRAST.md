# PR62-C2 — Route 6 demand-response ServiceRegime contrast calibration

> **NO PRODUCTION POLICY CHANGED.** C2 is experiment/calibration evidence only.

## Answer first

Route 6's frozen canonical demand evidence contains 8 outbound and 8 inbound states. Their demand contrasts are materially visible numerically below; no materiality threshold is introduced.

Outbound demand is highest in `DEMAND-OUTBOUND-06` and lowest in `DEMAND-OUTBOUND-08` (ratio 4.394). Inbound demand is highest in `DEMAND-INBOUND-06` and lowest in `DEMAND-INBOUND-08` (ratio 7.483).

- **CURRENT:** outbound demand ratio 4.394, service ratio 1.610, gamma 0.425, rank 0.952, direction accuracy 1.000, sqrt deviation 0.154; inbound demand ratio 7.483, service ratio 1.610, gamma 0.234, rank 0.781, direction accuracy 1.000, sqrt deviation 0.180.
- **EXTERNAL_AI:** outbound demand ratio 4.394, service ratio 1.804, gamma 0.404, rank 0.778, direction accuracy 1.000, sqrt deviation 0.177; inbound demand ratio 7.483, service ratio 1.686, gamma 0.269, rank 0.805, direction accuracy 0.880, sqrt deviation 0.187.
- **HUMAN_FINAL:** outbound demand ratio 4.394, service ratio 1.771, gamma 0.393, rank 0.778, direction accuracy 1.000, sqrt deviation 0.169; inbound demand ratio 7.483, service ratio 1.711, gamma 0.274, rank 0.913, direction accuracy 0.880, sqrt deviation 0.187.

- **12/13 clean design (CLEAN_PARETO_003, 14 vehicles):** outbound demand ratio 4.394, service ratio 1.000, gamma 0.025, rank 0.039, direction accuracy 0.189, sqrt deviation 0.285; inbound demand ratio 7.483, service ratio 1.000, gamma 0.030, rank 0.326, direction accuracy 0.189, sqrt deviation 0.316.

The 12/13 design's fleet efficiency is therefore assessed from its canonical demand/service ratios, gamma, rank, direction accuracy, and sqrt deviation—not from the visual neatness of its headways. Its near-unity service ratios and low contrast amplitude show that part of the 14-vehicle result comes from flattening service response across strongly different demand states.

The C1 candidates that relatively best preserve aligned differentiation in this nine-candidate sample are: CLEAN_PARETO_001, CLEAN_PARETO_002. This is a sample-median descriptor across three separate metrics, not a scalar score or production frontier. Even these candidates preserve the response only partially: neither matches the expert references' alignment in both directions.

The expert references generally make the same directional response that the existing sqrt-demand seed implies, but their residuals show the sqrt relationship is only a benchmark. Human Final remains an expert reference, not a target or ground truth.

Suitable evidence candidates for later ServicePlan evaluation are the paired demand/service peak-low ratios, gamma, rank correlation, direction accuracy plus raw transition count, and sqrt deviation/amplitude ratio. No threshold is selected here.

C2 does not establish that 8/15 is the optimal Route 6 rhythm composition. It tests the more general principle that materially different demand states should not be represented by nearly indistinguishable service levels unless another operational objective justifies that trade-off.

## Frozen sources and method

- Private workbook: `Route_6_Current_ExternalAI_HumanFinal.xlsx` / `c2038b31c5a3f6a3ee2377ce2067542cc718a7d1907722efa3ab45a536bdd14a`
- C1 evidence: `docs/engine/evidence/PR62_C1_ROUTE6_GLOBAL_CLEAN_RHYTHM_DESIGN.json` / `7aea189e95ebfbd3ba6da2ff78a5e91cf99a276ef24159a06989e439cbe79276`
- Canonical DemandRegimes: `outputs/demand_regime_model_selection/route_6_demand_regimes.json` / `f9c89f16cf7a9b0f29ee76db065c0cc182de2b0698c4ba71ce8437f1e1f5e3b6`
- Common active service span: 04:55–21:00.
- Demand mass is integrated proportionally through exact overlap with immutable 30-minute buckets.
- Service frequency is the exact time average of `60 / interdeparture headway` inside each DemandRegime.
- Adjacent transition weights are the arithmetic mean of the two active regime durations.
- `FLAT` means numerical zero to `1e-12`; it is not a policy or materiality threshold.

## Canonical Route 6 demand differentiation

### Outbound

| Regime | Canonical window | Active window | Duration min | Integrated mass | Demand rate/h |
|---|---|---|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:30–06:00 | 04:55–06:00 | 65.0 | 96.062 | 88.673 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 06:00–07:30 | 90.0 | 260.216 | 173.477 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 07:30–10:30 | 180.0 | 323.922 | 107.974 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 10:30–12:00 | 90.0 | 240.451 | 160.301 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 12:00–16:00 | 240.0 | 411.320 | 102.830 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 16:00–17:30 | 90.0 | 351.007 | 234.004 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 17:30–19:00 | 90.0 | 166.229 | 110.819 |
| DEMAND-OUTBOUND-08 | 19:00–21:30 | 19:00–21:00 | 120.0 | 106.516 | 53.258 |

### Inbound

| Regime | Canonical window | Active window | Duration min | Integrated mass | Demand rate/h |
|---|---|---|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:30–06:00 | 04:55–06:00 | 65.0 | 105.028 | 96.949 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 06:00–07:30 | 90.0 | 349.595 | 233.063 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 07:30–10:30 | 180.0 | 390.124 | 130.041 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 10:30–12:00 | 90.0 | 264.863 | 176.575 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 12:00–16:00 | 240.0 | 452.647 | 113.162 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 16:00–17:30 | 90.0 | 353.124 | 235.416 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 17:30–19:00 | 90.0 | 107.516 | 71.678 |
| DEMAND-INBOUND-08 | 19:00–21:30 | 19:00–21:00 | 120.0 | 62.922 | 31.461 |

## Pedagogical service-differentiation arithmetic

- 8 minutes = 7.50 departures/hour; 15 minutes = 4.00; ratio = 1.875.
- 10 minutes = 6.00 departures/hour; 12 minutes = 5.00; ratio = 1.200.
- 12 minutes = 5.00 departures/hour; 13 minutes ≈ 4.615; ratio ≈ 1.083.

**These arithmetic examples illustrate service differentiation only; they do not prove which headways Route 6 should use.**

## Comparative response table

| Schedule | Dir | Fleet | Mismatch | Wait min | Regimes | Peak/low service | Gamma | Rank | Direction accuracy | √ deviation | Total variation |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CURRENT | outbound | 20 | 0.00261 | 6.211 | 10 | 1.610 | 0.425 | 0.952 | 1.000 | 0.154 | 3.772 |
| CURRENT | inbound | 20 | 0.00417 | 6.123 | 10 | 1.610 | 0.234 | 0.781 | 1.000 | 0.180 | 3.772 |
| EXTERNAL_AI | outbound | 20 | 0.00256 | 6.215 | 14 | 1.804 | 0.404 | 0.778 | 1.000 | 0.177 | 5.352 |
| EXTERNAL_AI | inbound | 20 | 0.00438 | 6.111 | 8 | 1.686 | 0.269 | 0.805 | 0.880 | 0.187 | 3.841 |
| HUMAN_FINAL | outbound | 19 | 0.00242 | 6.215 | 9 | 1.771 | 0.393 | 0.778 | 1.000 | 0.169 | 3.772 |
| HUMAN_FINAL | inbound | 19 | 0.00438 | 6.091 | 8 | 1.711 | 0.274 | 0.913 | 0.880 | 0.187 | 3.772 |
| CLEAN_PARETO_001 | outbound | 20 | 0.00319 | 6.247 | 3 | 2.714 | 0.500 | 0.537 | 0.413 | 0.215 | 1.618 |
| CLEAN_PARETO_001 | inbound | 20 | 0.00870 | 6.254 | 2 | 1.000 | 0.030 | 0.326 | 0.189 | 0.316 | 0.080 |
| CLEAN_PARETO_002 | outbound | 17 | 0.00424 | 6.132 | 3 | 1.667 | 0.243 | 0.610 | 0.413 | 0.184 | 0.879 |
| CLEAN_PARETO_002 | inbound | 17 | 0.00870 | 6.254 | 2 | 1.000 | 0.030 | 0.326 | 0.189 | 0.316 | 0.080 |
| CLEAN_PARETO_003 | outbound | 14 | 0.00663 | 6.265 | 2 | 1.000 | 0.025 | 0.039 | 0.189 | 0.285 | 0.080 |
| CLEAN_PARETO_003 | inbound | 14 | 0.00870 | 6.254 | 2 | 1.000 | 0.030 | 0.326 | 0.189 | 0.316 | 0.080 |
| CLEAN_PARETO_004 | outbound | 15 | 0.00753 | 6.389 | 3 | 0.949 | -0.060 | -0.558 | 0.189 | 0.319 | 1.036 |
| CLEAN_PARETO_004 | inbound | 15 | 0.01059 | 6.486 | 4 | 0.882 | -0.065 | -0.491 | 0.000 | 0.369 | 1.911 |
| CLEAN_PARETO_005 | outbound | 19 | 0.00753 | 6.389 | 3 | 0.949 | -0.060 | -0.558 | 0.189 | 0.319 | 1.036 |
| CLEAN_PARETO_005 | inbound | 19 | 0.01121 | 6.494 | 3 | 1.000 | 0.053 | 0.342 | 0.155 | 0.327 | 0.693 |
| CLEAN_PARETO_006 | outbound | 17 | 0.00875 | 6.458 | 3 | 1.000 | -0.046 | -0.412 | 0.000 | 0.339 | 0.956 |
| CLEAN_PARETO_006 | inbound | 17 | 0.01059 | 6.486 | 4 | 0.882 | -0.065 | -0.491 | 0.000 | 0.369 | 1.911 |
| CLEAN_PARETO_007 | outbound | 16 | 0.00753 | 6.389 | 3 | 0.949 | -0.060 | -0.558 | 0.189 | 0.319 | 1.036 |
| CLEAN_PARETO_007 | inbound | 16 | 0.01194 | 6.472 | 3 | 1.000 | -0.013 | -0.247 | 0.000 | 0.369 | 0.956 |
| CLEAN_PARETO_008 | outbound | 20 | 0.00875 | 6.458 | 3 | 1.000 | -0.046 | -0.412 | 0.000 | 0.339 | 0.956 |
| CLEAN_PARETO_008 | inbound | 20 | 0.01121 | 6.494 | 3 | 1.000 | 0.053 | 0.342 | 0.155 | 0.327 | 0.693 |
| CLEAN_PARETO_009 | outbound | 18 | 0.00875 | 6.458 | 3 | 1.000 | -0.046 | -0.412 | 0.000 | 0.339 | 0.956 |
| CLEAN_PARETO_009 | inbound | 18 | 0.01194 | 6.472 | 3 | 1.000 | -0.013 | -0.247 | 0.000 | 0.369 | 0.956 |

## C1 candidate roles

- `CLEAN_PARETO_001`: MINIMUM_DEMAND_MISMATCH_CLEAN_PARETO_CANDIDATE.
- `CLEAN_PARETO_002`: MINIMUM_EXPECTED_WAIT_CLEAN_PARETO_CANDIDATE.
- `CLEAN_PARETO_003`: MINIMUM_FLEET_CLEAN_CANDIDATE, MINIMUM_REGULARITY_VARIATION_CLEAN_CANDIDATE, CLEAN_12_13_TIMETABLE_CANDIDATE.
- `CLEAN_PARETO_004`: Pareto candidate only.
- `CLEAN_PARETO_005`: Pareto candidate only.
- `CLEAN_PARETO_006`: Pareto candidate only.
- `CLEAN_PARETO_007`: Pareto candidate only.
- `CLEAN_PARETO_008`: Pareto candidate only.
- `CLEAN_PARETO_009`: Pareto candidate only.

## Demand-aligned response details

Every schedule/direction below uses the same canonical DemandRegime evidence.

### CURRENT — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 4.000 | 15.000 | 7.0 | 7.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 6.361 | 9.432 | 2.0 | 3.0 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.331 | 13.855 | 5.0 | 5.0 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 6.400 | 9.375 | 3.0 | 2.0 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.000 | 15.000 | 6.0 | 7.0 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 6.439 | 9.318 | 1.0 | 1.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 4.583 | 13.091 | 4.0 | 4.0 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 4.000 | 15.000 | 8.0 | 7.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | 0.464 | UP | UP | yes | 0.336 | 0.128 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | -0.385 | DOWN | DOWN | yes | -0.237 | -0.147 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | 0.391 | UP | UP | yes | 0.198 | 0.193 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | -0.470 | DOWN | DOWN | yes | -0.222 | -0.248 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.476 | UP | UP | yes | 0.411 | 0.065 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | -0.340 | DOWN | DOWN | yes | -0.374 | 0.034 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | -0.136 | DOWN | DOWN | yes | -0.366 | 0.230 |

Summary: demand ratio 4.394, service ratio 1.610, gamma 0.425, rank 0.952, direction accuracy 1.000, sqrt deviation 0.154; amplitude ratio to sqrt 1.307; aligned transitions 7/7.

### CURRENT — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 4.000 | 15.000 | 6.0 | 7.0 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 6.361 | 9.432 | 2.0 | 3.0 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 4.331 | 13.855 | 4.0 | 5.0 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 6.400 | 9.375 | 3.0 | 2.0 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.000 | 15.000 | 5.0 | 7.0 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 6.439 | 9.318 | 1.0 | 1.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.583 | 13.091 | 7.0 | 4.0 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 4.000 | 15.000 | 8.0 | 7.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | 0.464 | UP | UP | yes | 0.439 | 0.025 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | -0.385 | DOWN | DOWN | yes | -0.292 | -0.093 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | 0.391 | UP | UP | yes | 0.153 | 0.238 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | -0.470 | DOWN | DOWN | yes | -0.222 | -0.248 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | 0.476 | UP | UP | yes | 0.366 | 0.110 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | -0.340 | DOWN | DOWN | yes | -0.595 | 0.255 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | -0.136 | DOWN | DOWN | yes | -0.412 | 0.276 |

Summary: demand ratio 7.483, service ratio 1.610, gamma 0.234, rank 0.781, direction accuracy 1.000, sqrt deviation 0.180; amplitude ratio to sqrt 1.186; aligned transitions 7/7.

### EXTERNAL_AI — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 4.985 | 12.037 | 7.0 | 4.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 5.511 | 10.887 | 2.0 | 3.0 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.000 | 15.000 | 5.0 | 7.5 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 6.178 | 9.712 | 3.0 | 2.0 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.204 | 14.272 | 6.0 | 6.0 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 7.214 | 8.317 | 1.0 | 1.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 4.286 | 14.000 | 4.0 | 5.0 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 4.000 | 15.000 | 8.0 | 7.5 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | 0.100 | UP | UP | yes | 0.336 | -0.235 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | -0.320 | DOWN | DOWN | yes | -0.237 | -0.083 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | 0.435 | UP | UP | yes | 0.198 | 0.237 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | -0.385 | DOWN | DOWN | yes | -0.222 | -0.163 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.540 | UP | UP | yes | 0.411 | 0.129 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | -0.521 | DOWN | DOWN | yes | -0.374 | -0.147 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | -0.069 | DOWN | DOWN | yes | -0.366 | 0.297 |

Summary: demand ratio 4.394, service ratio 1.804, gamma 0.404, rank 0.778, direction accuracy 1.000, sqrt deviation 0.177; amplitude ratio to sqrt 1.211; aligned transitions 7/7.

### EXTERNAL_AI — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 4.000 | 15.000 | 6.0 | 7.0 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 7.111 | 8.438 | 2.0 | 1.0 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 4.311 | 13.918 | 4.0 | 4.0 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 5.867 | 10.227 | 3.0 | 3.0 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.000 | 15.000 | 5.0 | 7.0 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 6.800 | 8.824 | 1.0 | 2.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.000 | 15.000 | 7.0 | 7.0 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 4.033 | 14.876 | 8.0 | 5.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | 0.575 | UP | UP | yes | 0.439 | 0.137 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | -0.500 | DOWN | DOWN | yes | -0.292 | -0.209 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | 0.308 | UP | UP | yes | 0.153 | 0.155 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | -0.383 | DOWN | DOWN | yes | -0.222 | -0.161 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | 0.531 | UP | UP | yes | 0.366 | 0.164 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | -0.531 | DOWN | DOWN | yes | -0.595 | 0.064 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.008 | DOWN | UP | no | -0.412 | 0.420 |

Summary: demand ratio 7.483, service ratio 1.686, gamma 0.269, rank 0.805, direction accuracy 0.880, sqrt deviation 0.187; amplitude ratio to sqrt 1.227; aligned transitions 6/7.

### HUMAN_FINAL — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 5.077 | 11.818 | 7.0 | 4.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 5.489 | 10.931 | 2.0 | 3.0 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.000 | 15.000 | 5.0 | 7.5 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 6.178 | 9.712 | 3.0 | 2.0 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.219 | 14.222 | 6.0 | 6.0 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 7.083 | 8.471 | 1.0 | 1.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 4.333 | 13.846 | 4.0 | 5.0 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 4.000 | 15.000 | 8.0 | 7.5 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | 0.078 | UP | UP | yes | 0.336 | -0.258 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | -0.316 | DOWN | DOWN | yes | -0.237 | -0.079 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | 0.435 | UP | UP | yes | 0.198 | 0.237 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | -0.381 | DOWN | DOWN | yes | -0.222 | -0.159 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.518 | UP | UP | yes | 0.411 | 0.107 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | -0.491 | DOWN | DOWN | yes | -0.374 | -0.118 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | -0.080 | DOWN | DOWN | yes | -0.366 | 0.286 |

Summary: demand ratio 4.394, service ratio 1.771, gamma 0.393, rank 0.778, direction accuracy 1.000, sqrt deviation 0.169; amplitude ratio to sqrt 1.181; aligned transitions 7/7.

### HUMAN_FINAL — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 4.000 | 15.000 | 6.0 | 6.5 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 7.111 | 8.438 | 2.0 | 1.0 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 4.311 | 13.918 | 4.0 | 4.0 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 5.867 | 10.227 | 3.0 | 3.0 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.000 | 15.000 | 5.0 | 6.5 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 6.844 | 8.766 | 1.0 | 2.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.000 | 15.000 | 7.0 | 6.5 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 4.000 | 15.000 | 8.0 | 6.5 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | 0.575 | UP | UP | yes | 0.439 | 0.137 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | -0.500 | DOWN | DOWN | yes | -0.292 | -0.209 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | 0.308 | UP | UP | yes | 0.153 | 0.155 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | -0.383 | DOWN | DOWN | yes | -0.222 | -0.161 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | 0.537 | UP | UP | yes | 0.366 | 0.171 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | -0.537 | DOWN | DOWN | yes | -0.595 | 0.057 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.000 | DOWN | FLAT | no | -0.412 | 0.412 |

Summary: demand ratio 7.483, service ratio 1.711, gamma 0.274, rank 0.913, direction accuracy 0.880, sqrt deviation 0.187; amplitude ratio to sqrt 1.229; aligned transitions 6/7.

### CLEAN_PARETO_001 — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 4.615 | 13.000 | 7.0 | 5.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 4.615 | 13.000 | 2.0 | 5.0 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.615 | 13.000 | 5.0 | 5.0 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 4.615 | 13.000 | 3.0 | 3.0 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.648 | 12.908 | 6.0 | 2.0 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 8.571 | 7.000 | 1.0 | 1.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 4.361 | 13.759 | 4.0 | 7.0 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 3.158 | 19.000 | 8.0 | 8.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | 0.000 | UP | FLAT | no | 0.336 | -0.336 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | 0.000 | DOWN | FLAT | no | -0.237 | 0.237 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | 0.000 | UP | FLAT | no | 0.198 | -0.198 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | 0.007 | DOWN | UP | no | -0.222 | 0.229 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.612 | UP | UP | yes | 0.411 | 0.201 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | -0.676 | DOWN | DOWN | yes | -0.374 | -0.302 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | -0.323 | DOWN | DOWN | yes | -0.366 | 0.044 |

Summary: demand ratio 4.394, service ratio 2.714, gamma 0.500, rank 0.537, direction accuracy 0.413, sqrt deviation 0.215; amplitude ratio to sqrt 0.753; aligned transitions 3/7.

### CLEAN_PARETO_001 — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 5.000 | 12.000 | 6.0 | 2.5 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 5.000 | 12.000 | 2.0 | 2.5 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 5.000 | 12.000 | 4.0 | 2.5 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 5.000 | 12.000 | 3.0 | 2.5 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.627 | 12.968 | 5.0 | 5.0 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 4.615 | 13.000 | 1.0 | 7.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.615 | 13.000 | 7.0 | 7.0 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 4.615 | 13.000 | 8.0 | 7.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | 0.000 | UP | FLAT | no | 0.439 | -0.439 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | 0.000 | DOWN | FLAT | no | -0.292 | 0.292 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | 0.000 | UP | FLAT | no | 0.153 | -0.153 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | -0.078 | DOWN | DOWN | yes | -0.222 | 0.145 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | -0.002 | UP | DOWN | no | 0.366 | -0.369 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | 0.000 | DOWN | FLAT | no | -0.595 | 0.595 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.000 | DOWN | FLAT | no | -0.412 | 0.412 |

Summary: demand ratio 7.483, service ratio 1.000, gamma 0.030, rank 0.326, direction accuracy 0.189, sqrt deviation 0.316; amplitude ratio to sqrt 0.046; aligned transitions 1/7.

### CLEAN_PARETO_002 — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 4.615 | 13.000 | 7.0 | 6.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 4.615 | 13.000 | 2.0 | 6.0 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.615 | 13.000 | 5.0 | 6.0 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 4.615 | 13.000 | 3.0 | 4.0 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.744 | 12.649 | 6.0 | 3.0 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 6.667 | 9.000 | 1.0 | 1.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 4.889 | 12.273 | 4.0 | 2.0 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 4.000 | 15.000 | 8.0 | 8.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | 0.000 | UP | FLAT | no | 0.336 | -0.336 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | 0.000 | DOWN | FLAT | no | -0.237 | 0.237 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | 0.000 | UP | FLAT | no | 0.198 | -0.198 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | 0.027 | DOWN | UP | no | -0.222 | 0.249 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.340 | UP | UP | yes | 0.411 | -0.071 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | -0.310 | DOWN | DOWN | yes | -0.374 | 0.064 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | -0.201 | DOWN | DOWN | yes | -0.366 | 0.166 |

Summary: demand ratio 4.394, service ratio 1.667, gamma 0.243, rank 0.610, direction accuracy 0.413, sqrt deviation 0.184; amplitude ratio to sqrt 0.420; aligned transitions 3/7.

### CLEAN_PARETO_002 — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 5.000 | 12.000 | 6.0 | 2.5 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 5.000 | 12.000 | 2.0 | 2.5 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 5.000 | 12.000 | 4.0 | 2.5 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 5.000 | 12.000 | 3.0 | 2.5 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.627 | 12.968 | 5.0 | 5.0 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 4.615 | 13.000 | 1.0 | 7.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.615 | 13.000 | 7.0 | 7.0 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 4.615 | 13.000 | 8.0 | 7.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | 0.000 | UP | FLAT | no | 0.439 | -0.439 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | 0.000 | DOWN | FLAT | no | -0.292 | 0.292 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | 0.000 | UP | FLAT | no | 0.153 | -0.153 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | -0.078 | DOWN | DOWN | yes | -0.222 | 0.145 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | -0.002 | UP | DOWN | no | 0.366 | -0.369 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | 0.000 | DOWN | FLAT | no | -0.595 | 0.595 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.000 | DOWN | FLAT | no | -0.412 | 0.412 |

Summary: demand ratio 7.483, service ratio 1.000, gamma 0.030, rank 0.326, direction accuracy 0.189, sqrt deviation 0.316; amplitude ratio to sqrt 0.046; aligned transitions 1/7.

### CLEAN_PARETO_003 — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 5.000 | 12.000 | 7.0 | 2.5 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 5.000 | 12.000 | 2.0 | 2.5 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 5.000 | 12.000 | 5.0 | 2.5 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 5.000 | 12.000 | 3.0 | 2.5 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.627 | 12.968 | 6.0 | 5.0 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 4.615 | 13.000 | 1.0 | 7.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 4.615 | 13.000 | 4.0 | 7.0 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 4.615 | 13.000 | 8.0 | 7.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | 0.000 | UP | FLAT | no | 0.336 | -0.336 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | 0.000 | DOWN | FLAT | no | -0.237 | 0.237 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | 0.000 | UP | FLAT | no | 0.198 | -0.198 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | -0.078 | DOWN | DOWN | yes | -0.222 | 0.144 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | -0.002 | UP | DOWN | no | 0.411 | -0.414 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | 0.000 | DOWN | FLAT | no | -0.374 | 0.374 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | 0.000 | DOWN | FLAT | no | -0.366 | 0.366 |

Summary: demand ratio 4.394, service ratio 1.000, gamma 0.025, rank 0.039, direction accuracy 0.189, sqrt deviation 0.285; amplitude ratio to sqrt 0.051; aligned transitions 1/7.

### CLEAN_PARETO_003 — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 5.000 | 12.000 | 6.0 | 2.5 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 5.000 | 12.000 | 2.0 | 2.5 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 5.000 | 12.000 | 4.0 | 2.5 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 5.000 | 12.000 | 3.0 | 2.5 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.627 | 12.968 | 5.0 | 5.0 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 4.615 | 13.000 | 1.0 | 7.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.615 | 13.000 | 7.0 | 7.0 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 4.615 | 13.000 | 8.0 | 7.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | 0.000 | UP | FLAT | no | 0.439 | -0.439 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | 0.000 | DOWN | FLAT | no | -0.292 | 0.292 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | 0.000 | UP | FLAT | no | 0.153 | -0.153 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | -0.078 | DOWN | DOWN | yes | -0.222 | 0.145 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | -0.002 | UP | DOWN | no | 0.366 | -0.369 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | 0.000 | DOWN | FLAT | no | -0.595 | 0.595 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.000 | DOWN | FLAT | no | -0.412 | 0.412 |

Summary: demand ratio 7.483, service ratio 1.000, gamma 0.030, rank 0.326, direction accuracy 0.189, sqrt deviation 0.316; amplitude ratio to sqrt 0.046; aligned transitions 1/7.

### CLEAN_PARETO_004 — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 5.751 | 10.432 | 7.0 | 1.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 4.615 | 13.000 | 2.0 | 7.5 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.615 | 13.000 | 5.0 | 5.5 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 4.615 | 13.000 | 3.0 | 7.5 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.615 | 13.000 | 6.0 | 5.5 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 4.744 | 12.649 | 1.0 | 4.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 5.000 | 12.000 | 4.0 | 2.5 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 5.000 | 12.000 | 8.0 | 2.5 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | -0.220 | UP | DOWN | no | 0.336 | -0.556 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | 0.000 | DOWN | FLAT | no | -0.237 | 0.237 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | -0.000 | UP | FLAT | no | 0.198 | -0.198 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.027 | UP | UP | yes | 0.411 | -0.384 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | 0.053 | DOWN | UP | no | -0.374 | 0.426 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | 0.000 | DOWN | FLAT | no | -0.366 | 0.366 |

Summary: demand ratio 4.394, service ratio 0.949, gamma -0.060, rank -0.558, direction accuracy 0.189, sqrt deviation 0.319; amplitude ratio to sqrt 0.101; aligned transitions 1/7.

### CLEAN_PARETO_004 — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 6.036 | 9.941 | 6.0 | 1.0 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 4.615 | 13.000 | 2.0 | 5.0 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 4.615 | 13.000 | 4.0 | 8.0 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 4.615 | 13.000 | 3.0 | 5.0 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.615 | 13.000 | 5.0 | 5.0 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 4.615 | 13.000 | 1.0 | 5.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.615 | 13.000 | 7.0 | 5.0 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 5.231 | 11.471 | 8.0 | 2.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | -0.268 | UP | DOWN | no | 0.439 | -0.707 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | -0.000 | DOWN | FLAT | no | -0.292 | 0.292 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | 0.000 | UP | FLAT | no | 0.153 | -0.153 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | 0.000 | UP | FLAT | no | 0.366 | -0.366 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | 0.000 | DOWN | FLAT | no | -0.595 | 0.595 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.125 | DOWN | UP | no | -0.412 | 0.537 |

Summary: demand ratio 7.483, service ratio 0.882, gamma -0.065, rank -0.491, direction accuracy 0.000, sqrt deviation 0.369; amplitude ratio to sqrt 0.118; aligned transitions 0/7.

### CLEAN_PARETO_005 — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 5.751 | 10.432 | 7.0 | 1.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 4.615 | 13.000 | 2.0 | 7.5 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.615 | 13.000 | 5.0 | 5.5 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 4.615 | 13.000 | 3.0 | 7.5 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.615 | 13.000 | 6.0 | 5.5 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 4.744 | 12.649 | 1.0 | 4.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 5.000 | 12.000 | 4.0 | 2.5 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 5.000 | 12.000 | 8.0 | 2.5 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | -0.220 | UP | DOWN | no | 0.336 | -0.556 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | 0.000 | DOWN | FLAT | no | -0.237 | 0.237 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | -0.000 | UP | FLAT | no | 0.198 | -0.198 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.027 | UP | UP | yes | 0.411 | -0.384 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | 0.053 | DOWN | UP | no | -0.374 | 0.426 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | 0.000 | DOWN | FLAT | no | -0.366 | 0.366 |

Summary: demand ratio 4.394, service ratio 0.949, gamma -0.060, rank -0.558, direction accuracy 0.189, sqrt deviation 0.319; amplitude ratio to sqrt 0.101; aligned transitions 1/7.

### CLEAN_PARETO_005 — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 8.571 | 7.000 | 6.0 | 1.0 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 6.032 | 9.947 | 2.0 | 2.0 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 4.556 | 13.171 | 4.0 | 3.0 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 4.286 | 14.000 | 3.0 | 6.5 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.286 | 14.000 | 5.0 | 6.5 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 4.286 | 14.000 | 1.0 | 4.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.286 | 14.000 | 7.0 | 6.5 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 4.286 | 14.000 | 8.0 | 6.5 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | -0.351 | UP | DOWN | no | 0.439 | -0.790 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | -0.281 | DOWN | DOWN | yes | -0.292 | 0.011 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | -0.061 | UP | DOWN | no | 0.153 | -0.214 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | 0.000 | UP | FLAT | no | 0.366 | -0.366 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | -0.000 | DOWN | FLAT | no | -0.595 | 0.595 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.000 | DOWN | FLAT | no | -0.412 | 0.412 |

Summary: demand ratio 7.483, service ratio 1.000, gamma 0.053, rank 0.342, direction accuracy 0.155, sqrt deviation 0.327; amplitude ratio to sqrt 0.255; aligned transitions 1/7.

### CLEAN_PARETO_006 — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 7.172 | 8.366 | 7.0 | 1.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 4.615 | 13.000 | 2.0 | 5.0 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.615 | 13.000 | 5.0 | 5.0 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 4.615 | 13.000 | 3.0 | 5.0 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.615 | 13.000 | 6.0 | 5.0 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 4.615 | 13.000 | 1.0 | 5.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 4.615 | 13.000 | 4.0 | 5.0 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 4.615 | 13.000 | 8.0 | 5.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | -0.441 | UP | DOWN | no | 0.336 | -0.776 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | 0.000 | DOWN | FLAT | no | -0.237 | 0.237 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | 0.000 | UP | FLAT | no | 0.198 | -0.198 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.000 | UP | FLAT | no | 0.411 | -0.411 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | 0.000 | DOWN | FLAT | no | -0.374 | 0.374 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | 0.000 | DOWN | FLAT | no | -0.366 | 0.366 |

Summary: demand ratio 4.394, service ratio 1.000, gamma -0.046, rank -0.412, direction accuracy 0.000, sqrt deviation 0.339; amplitude ratio to sqrt 0.131; aligned transitions 0/7.

### CLEAN_PARETO_006 — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 6.036 | 9.941 | 6.0 | 1.0 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 4.615 | 13.000 | 2.0 | 5.0 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 4.615 | 13.000 | 4.0 | 8.0 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 4.615 | 13.000 | 3.0 | 5.0 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.615 | 13.000 | 5.0 | 5.0 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 4.615 | 13.000 | 1.0 | 5.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.615 | 13.000 | 7.0 | 5.0 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 5.231 | 11.471 | 8.0 | 2.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | -0.268 | UP | DOWN | no | 0.439 | -0.707 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | -0.000 | DOWN | FLAT | no | -0.292 | 0.292 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | 0.000 | UP | FLAT | no | 0.153 | -0.153 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | 0.000 | UP | FLAT | no | 0.366 | -0.366 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | 0.000 | DOWN | FLAT | no | -0.595 | 0.595 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.125 | DOWN | UP | no | -0.412 | 0.537 |

Summary: demand ratio 7.483, service ratio 0.882, gamma -0.065, rank -0.491, direction accuracy 0.000, sqrt deviation 0.369; amplitude ratio to sqrt 0.118; aligned transitions 0/7.

### CLEAN_PARETO_007 — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 5.751 | 10.432 | 7.0 | 1.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 4.615 | 13.000 | 2.0 | 7.5 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.615 | 13.000 | 5.0 | 5.5 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 4.615 | 13.000 | 3.0 | 7.5 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.615 | 13.000 | 6.0 | 5.5 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 4.744 | 12.649 | 1.0 | 4.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 5.000 | 12.000 | 4.0 | 2.5 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 5.000 | 12.000 | 8.0 | 2.5 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | -0.220 | UP | DOWN | no | 0.336 | -0.556 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | 0.000 | DOWN | FLAT | no | -0.237 | 0.237 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | -0.000 | UP | FLAT | no | 0.198 | -0.198 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.027 | UP | UP | yes | 0.411 | -0.384 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | 0.053 | DOWN | UP | no | -0.374 | 0.426 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | 0.000 | DOWN | FLAT | no | -0.366 | 0.366 |

Summary: demand ratio 4.394, service ratio 0.949, gamma -0.060, rank -0.558, direction accuracy 0.189, sqrt deviation 0.319; amplitude ratio to sqrt 0.101; aligned transitions 1/7.

### CLEAN_PARETO_007 — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 7.172 | 8.366 | 6.0 | 1.0 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 4.615 | 13.000 | 2.0 | 5.0 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 4.615 | 13.000 | 4.0 | 5.0 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 4.615 | 13.000 | 3.0 | 5.0 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.615 | 13.000 | 5.0 | 5.0 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 4.615 | 13.000 | 1.0 | 5.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.615 | 13.000 | 7.0 | 5.0 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 4.615 | 13.000 | 8.0 | 5.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | -0.441 | UP | DOWN | no | 0.439 | -0.879 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | 0.000 | DOWN | FLAT | no | -0.292 | 0.292 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | 0.000 | UP | FLAT | no | 0.153 | -0.153 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | 0.000 | UP | FLAT | no | 0.366 | -0.366 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | 0.000 | DOWN | FLAT | no | -0.595 | 0.595 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.000 | DOWN | FLAT | no | -0.412 | 0.412 |

Summary: demand ratio 7.483, service ratio 1.000, gamma -0.013, rank -0.247, direction accuracy 0.000, sqrt deviation 0.369; amplitude ratio to sqrt 0.119; aligned transitions 0/7.

### CLEAN_PARETO_008 — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 7.172 | 8.366 | 7.0 | 1.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 4.615 | 13.000 | 2.0 | 5.0 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.615 | 13.000 | 5.0 | 5.0 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 4.615 | 13.000 | 3.0 | 5.0 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.615 | 13.000 | 6.0 | 5.0 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 4.615 | 13.000 | 1.0 | 5.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 4.615 | 13.000 | 4.0 | 5.0 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 4.615 | 13.000 | 8.0 | 5.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | -0.441 | UP | DOWN | no | 0.336 | -0.776 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | 0.000 | DOWN | FLAT | no | -0.237 | 0.237 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | 0.000 | UP | FLAT | no | 0.198 | -0.198 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.000 | UP | FLAT | no | 0.411 | -0.411 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | 0.000 | DOWN | FLAT | no | -0.374 | 0.374 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | 0.000 | DOWN | FLAT | no | -0.366 | 0.366 |

Summary: demand ratio 4.394, service ratio 1.000, gamma -0.046, rank -0.412, direction accuracy 0.000, sqrt deviation 0.339; amplitude ratio to sqrt 0.131; aligned transitions 0/7.

### CLEAN_PARETO_008 — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 8.571 | 7.000 | 6.0 | 1.0 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 6.032 | 9.947 | 2.0 | 2.0 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 4.556 | 13.171 | 4.0 | 3.0 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 4.286 | 14.000 | 3.0 | 6.5 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.286 | 14.000 | 5.0 | 6.5 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 4.286 | 14.000 | 1.0 | 4.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.286 | 14.000 | 7.0 | 6.5 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 4.286 | 14.000 | 8.0 | 6.5 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | -0.351 | UP | DOWN | no | 0.439 | -0.790 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | -0.281 | DOWN | DOWN | yes | -0.292 | 0.011 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | -0.061 | UP | DOWN | no | 0.153 | -0.214 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | 0.000 | UP | FLAT | no | 0.366 | -0.366 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | -0.000 | DOWN | FLAT | no | -0.595 | 0.595 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.000 | DOWN | FLAT | no | -0.412 | 0.412 |

Summary: demand ratio 7.483, service ratio 1.000, gamma 0.053, rank 0.342, direction accuracy 0.155, sqrt deviation 0.327; amplitude ratio to sqrt 0.255; aligned transitions 1/7.

### CLEAN_PARETO_009 — outbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-OUTBOUND-01 | 04:55–06:00 | 88.673 | 7.172 | 8.366 | 7.0 | 1.0 |
| DEMAND-OUTBOUND-02 | 06:00–07:30 | 173.477 | 4.615 | 13.000 | 2.0 | 5.0 |
| DEMAND-OUTBOUND-03 | 07:30–10:30 | 107.974 | 4.615 | 13.000 | 5.0 | 5.0 |
| DEMAND-OUTBOUND-04 | 10:30–12:00 | 160.301 | 4.615 | 13.000 | 3.0 | 5.0 |
| DEMAND-OUTBOUND-05 | 12:00–16:00 | 102.830 | 4.615 | 13.000 | 6.0 | 5.0 |
| DEMAND-OUTBOUND-06 | 16:00–17:30 | 234.004 | 4.615 | 13.000 | 1.0 | 5.0 |
| DEMAND-OUTBOUND-07 | 17:30–19:00 | 110.819 | 4.615 | 13.000 | 4.0 | 5.0 |
| DEMAND-OUTBOUND-08 | 19:00–21:00 | 53.258 | 4.615 | 13.000 | 8.0 | 5.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-OUTBOUND-01→DEMAND-OUTBOUND-02 | 0.671 | -0.441 | UP | DOWN | no | 0.336 | -0.776 |
| DEMAND-OUTBOUND-02→DEMAND-OUTBOUND-03 | -0.474 | 0.000 | DOWN | FLAT | no | -0.237 | 0.237 |
| DEMAND-OUTBOUND-03→DEMAND-OUTBOUND-04 | 0.395 | 0.000 | UP | FLAT | no | 0.198 | -0.198 |
| DEMAND-OUTBOUND-04→DEMAND-OUTBOUND-05 | -0.444 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-OUTBOUND-05→DEMAND-OUTBOUND-06 | 0.822 | 0.000 | UP | FLAT | no | 0.411 | -0.411 |
| DEMAND-OUTBOUND-06→DEMAND-OUTBOUND-07 | -0.747 | 0.000 | DOWN | FLAT | no | -0.374 | 0.374 |
| DEMAND-OUTBOUND-07→DEMAND-OUTBOUND-08 | -0.733 | 0.000 | DOWN | FLAT | no | -0.366 | 0.366 |

Summary: demand ratio 4.394, service ratio 1.000, gamma -0.046, rank -0.412, direction accuracy 0.000, sqrt deviation 0.339; amplitude ratio to sqrt 0.131; aligned transitions 0/7.

### CLEAN_PARETO_009 — inbound

| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |
|---|---|---:|---:|---:|---:|---:|
| DEMAND-INBOUND-01 | 04:55–06:00 | 96.949 | 7.172 | 8.366 | 6.0 | 1.0 |
| DEMAND-INBOUND-02 | 06:00–07:30 | 233.063 | 4.615 | 13.000 | 2.0 | 5.0 |
| DEMAND-INBOUND-03 | 07:30–10:30 | 130.041 | 4.615 | 13.000 | 4.0 | 5.0 |
| DEMAND-INBOUND-04 | 10:30–12:00 | 176.575 | 4.615 | 13.000 | 3.0 | 5.0 |
| DEMAND-INBOUND-05 | 12:00–16:00 | 113.162 | 4.615 | 13.000 | 5.0 | 5.0 |
| DEMAND-INBOUND-06 | 16:00–17:30 | 235.416 | 4.615 | 13.000 | 1.0 | 5.0 |
| DEMAND-INBOUND-07 | 17:30–19:00 | 71.678 | 4.615 | 13.000 | 7.0 | 5.0 |
| DEMAND-INBOUND-08 | 19:00–21:00 | 31.461 | 4.615 | 13.000 | 8.0 | 5.0 |

| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |
|---|---:|---:|---|---|---|---:|---:|
| DEMAND-INBOUND-01→DEMAND-INBOUND-02 | 0.877 | -0.441 | UP | DOWN | no | 0.439 | -0.879 |
| DEMAND-INBOUND-02→DEMAND-INBOUND-03 | -0.583 | 0.000 | DOWN | FLAT | no | -0.292 | 0.292 |
| DEMAND-INBOUND-03→DEMAND-INBOUND-04 | 0.306 | 0.000 | UP | FLAT | no | 0.153 | -0.153 |
| DEMAND-INBOUND-04→DEMAND-INBOUND-05 | -0.445 | 0.000 | DOWN | FLAT | no | -0.222 | 0.222 |
| DEMAND-INBOUND-05→DEMAND-INBOUND-06 | 0.733 | 0.000 | UP | FLAT | no | 0.366 | -0.366 |
| DEMAND-INBOUND-06→DEMAND-INBOUND-07 | -1.189 | 0.000 | DOWN | FLAT | no | -0.595 | 0.595 |
| DEMAND-INBOUND-07→DEMAND-INBOUND-08 | -0.823 | 0.000 | DOWN | FLAT | no | -0.412 | 0.412 |

Summary: demand ratio 7.483, service ratio 1.000, gamma -0.013, rank -0.247, direction accuracy 0.000, sqrt deviation 0.369; amplitude ratio to sqrt 0.119; aligned transitions 0/7.

## Limitations

- Single Route 6 calibration using frozen canonical regimes and immutable demand.
- Effective frequency is averaged within DemandRegimes and does not measure crowding, capacity, reliability, or cost directly.
- The sqrt-demand relationship is an existing seed benchmark, not transport policy or ground truth.
- Sample-relative candidate observations are descriptive and create no absolute threshold or scalar score.
- C2 does not establish that 8/15 is the optimal Route 6 rhythm composition.

## Production guard

- Production scheduling policy changed: **No**.
- Compiler changed: **No**.
- Production Pareto vector changed: **No**.
- Search budgets changed: **No**.
- Service protection changed: **No**.
- Settlement behavior changed: **No**.
