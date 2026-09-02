# PR62-C1 — Global clean ServiceRegime rhythm-design experiment

> Experiment-only evidence. No production compiler/search policy changed.

## Question and method

The private benchmark `Route_6_Current_ExternalAI_HumanFinal.xlsx` is bound by SHA-256 `c2038b31c5a3f6a3ee2377ce2067542cc718a7d1907722efa3ab45a536bdd14a`. The search independently redesigns each complete 04:55–21:00 direction as sustained whole-minute ServiceRegimes with at least two gaps per regime.

The deterministic label-setting DP uses state `(gaps_used, elapsed_minutes, last_headway)`, headways 5–30 minutes, arithmetic feasibility pruning, metric anchors, and exact-departure max-min diversity. A general exhaustive one-to-three-regime arithmetic census supplies low-regime completeness anchors across the same headway domain. Archive caps are search approximations, not transport policy.

Expected passenger wait uses `UNIFORM_WITHIN_DEMAND_BUCKET_EXPERIMENT_ASSUMPTION` and exact interdeparture/bucket integration.

## Reference benchmarks

| Reference | Pair mismatch | Expected wait | Max bucket wait | Fleet | Excess wait total/max | Regimes | Unique complexity | Max jump | Total variation | Tails Out/In |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| CURRENT | 0.0067811133 | 6.1656 | 12.5000 | 20/20 | 6130/75 | 20 | 6 | 0.628609 | 7.543304 | 15@17:45 / 15@17:45 |
| EXTERNAL_AI | 0.0069443750 | 6.1612 | 12.5000 | 20/20 | 5846/94 | 22 | 10 | 0.628609 | 9.192919 | 15@17:45 / 15@17:16 |
| HUMAN_FINAL | 0.0068020725 | 6.1510 | 12.5000 | 19/20 | 5352/93 | 17 | 6 | 0.628609 | 7.543304 | 15@17:45 / 15@17:30 |

## Bounded-search sensitivity

| Configuration | State cap | Pool cap | Out/In states | Out/In complete | Out/In retained | Fleet validations | Feasible pairs | Pareto size | Classification |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| BASE | 16 | 64 | 490399/490399 | 29190/29190 | 64/64 | 4096 | 23 | 9 | CLEAN_VS_HUMAN_TRADEOFF |
| SENSITIVITY | 32 | 96 | 526204/526204 | 29222/29222 | 96/96 | 9216 | 27 | 9 | CLEAN_VS_HUMAN_TRADEOFF |

## Sensitivity clean Pareto frontier

| Candidate | Pair mismatch | Expected wait | Max bucket wait | Fleet | Excess wait total/max | Regimes | Unique complexity | Max jump | Total variation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CLEAN_PARETO_001 | 0.0118846787 | 6.2507 | 10.5000 | 20/20 | 2976/102 | 5 | 5 | 0.998529 | 1.697611 |
| CLEAN_PARETO_002 | 0.0129414924 | 6.1948 | 10.5000 | 17/20 | 2549/66 | 5 | 5 | 0.510826 | 0.958593 |
| CLEAN_PARETO_003 | 0.0153298967 | 6.2593 | 9.5000 | 14/20 | 1810/16 | 4 | 4 | 0.080043 | 0.160085 |
| CLEAN_PARETO_004 | 0.0181197416 | 6.4387 | 7.1000 | 15/20 | 2952/35 | 7 | 6 | 0.955511 | 2.946577 |
| CLEAN_PARETO_005 | 0.0187387173 | 6.4429 | 7.4000 | 19/20 | 6229/89 | 6 | 6 | 0.955511 | 1.728701 |
| CLEAN_PARETO_006 | 0.0193448095 | 6.4724 | 7.1000 | 17/20 | 4780/45 | 7 | 6 | 0.955511 | 2.866534 |
| CLEAN_PARETO_007 | 0.0194657318 | 6.4319 | 7.1000 | 16/20 | 3804/36 | 6 | 6 | 0.955511 | 1.991066 |
| CLEAN_PARETO_008 | 0.0199637852 | 6.4767 | 7.4000 | 20/20 | 7250/95 | 6 | 6 | 0.619039 | 1.648659 |
| CLEAN_PARETO_009 | 0.0206907997 | 6.4656 | 7.1000 | 18/20 | 5592/42 | 6 | 6 | 0.619039 | 1.911023 |

### CLEAN_PARETO_001

- OUTBOUND: `04:55-15:58@13 → 15:58-17:50@7 → 17:50-21:00@19`
- OUTBOUND arithmetic: `16 × 7 + 51 × 13 + 10 × 19 = 965`
- INBOUND: `04:55-12:07@12 → 12:07-21:00@13`
- INBOUND arithmetic: `36 × 12 + 41 × 13 = 965`

### CLEAN_PARETO_002

- OUTBOUND: `04:55-15:45@13 → 15:45-18:00@9 → 18:00-21:00@15`
- OUTBOUND arithmetic: `15 × 9 + 50 × 13 + 12 × 15 = 965`
- INBOUND: `04:55-12:07@12 → 12:07-21:00@13`
- INBOUND arithmetic: `36 × 12 + 41 × 13 = 965`

### CLEAN_PARETO_003

- OUTBOUND: `04:55-12:07@12 → 12:07-21:00@13`
- OUTBOUND arithmetic: `36 × 12 + 41 × 13 = 965`
- INBOUND: `04:55-12:07@12 → 12:07-21:00@13`
- INBOUND arithmetic: `36 × 12 + 41 × 13 = 965`

### CLEAN_PARETO_004

- OUTBOUND: `04:55-05:05@5 → 05:05-17:00@13 → 17:00-21:00@12`
- OUTBOUND arithmetic: `2 × 5 + 20 × 12 + 55 × 13 = 965`
- INBOUND: `04:55-05:05@5 → 05:05-05:27@11 → 05:27-20:50@13 → 20:50-21:00@5`
- INBOUND arithmetic: `4 × 5 + 2 × 11 + 71 × 13 = 965`

### CLEAN_PARETO_005

- OUTBOUND: `04:55-05:05@5 → 05:05-17:00@13 → 17:00-21:00@12`
- OUTBOUND arithmetic: `2 × 5 + 20 × 12 + 55 × 13 = 965`
- INBOUND: `04:55-06:26@7 → 06:26-08:38@12 → 08:38-21:00@14`
- INBOUND arithmetic: `13 × 7 + 11 × 12 + 53 × 14 = 965`

### CLEAN_PARETO_006

- OUTBOUND: `04:55-05:10@5 → 05:10-05:24@7 → 05:24-21:00@13`
- OUTBOUND arithmetic: `3 × 5 + 2 × 7 + 72 × 13 = 965`
- INBOUND: `04:55-05:05@5 → 05:05-05:27@11 → 05:27-20:50@13 → 20:50-21:00@5`
- INBOUND arithmetic: `4 × 5 + 2 × 11 + 71 × 13 = 965`

### CLEAN_PARETO_007

- OUTBOUND: `04:55-05:05@5 → 05:05-17:00@13 → 17:00-21:00@12`
- OUTBOUND arithmetic: `2 × 5 + 20 × 12 + 55 × 13 = 965`
- INBOUND: `04:55-05:10@5 → 05:10-05:24@7 → 05:24-21:00@13`
- INBOUND arithmetic: `3 × 5 + 2 × 7 + 72 × 13 = 965`

### CLEAN_PARETO_008

- OUTBOUND: `04:55-05:10@5 → 05:10-05:24@7 → 05:24-21:00@13`
- OUTBOUND arithmetic: `3 × 5 + 2 × 7 + 72 × 13 = 965`
- INBOUND: `04:55-06:26@7 → 06:26-08:38@12 → 08:38-21:00@14`
- INBOUND arithmetic: `13 × 7 + 11 × 12 + 53 × 14 = 965`

### CLEAN_PARETO_009

- OUTBOUND: `04:55-05:10@5 → 05:10-05:24@7 → 05:24-21:00@13`
- OUTBOUND arithmetic: `3 × 5 + 2 × 7 + 72 × 13 = 965`
- INBOUND: `04:55-05:10@5 → 05:10-05:24@7 → 05:24-21:00@13`
- INBOUND arithmetic: `3 × 5 + 2 × 7 + 72 × 13 = 965`

## Evidence classification

**CLEAN_VS_HUMAN_TRADEOFF**

Classification stable across base and sensitivity archives: **yes** (`STABLE_ACROSS_ARCHIVE_SETTINGS`).

This is evidence only. No settlement support, transition regime, compiler rule, or production search budget changed.

## Limitations

- Single Route 6 experiment; the 5-30 minute domain is a technical bound, not policy.
- Per-state and final-pool caps make the search an explicitly bounded approximation.
- Uniform passenger arrivals within immutable 30-minute buckets are an experiment assumption.
- Human Final is a post-search benchmark and is not a search target.
- No production compiler, search, fleet, demand, or protection semantics changed.
