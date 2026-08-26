# PR62-I — Worst-bucket passenger access

H commit: `fb77fc57be7da7756485b528801d8bd24c956d53`.

Demand-weighted expected passenger wait answers: **What does the average passenger experience?** Maximum bucket expected wait answers: **What is the worst scheduled passenger-access interval in the service day?** Low-demand periods, especially final tails, remain visible without a hard headway or wait threshold.

Directional P90 uses deterministic nearest rank `ceil(0.90 × n)` over ordered non-null active bucket waits. Pair P90 is the maximum directional P90 and is diagnostic only. Tail maximum wait reuses existing exact bucket waits for active buckets overlapping final actual ServiceRegime support; no pseudo-bucket or `headway / 2` approximation is used.

## Route 6 — H → I

H Pareto: **46**; I Pareto: **47**; H candidates removed only by maximum-bucket wait: **0**.

| Metric | H range | I range |
| --- | ---: | ---: |
| fleet | [14, 20] | [14, 20] |
| maximum_bucket_wait_minutes | [8.5, 27.5] | [8.5, 27.5] |
| mismatch | [0.006368300470867757, 0.015650510405009692] | [0.006368300470867757, 0.015650510405009692] |
| p90_bucket_wait_minutes | [6.866666666666666, 11.666666666666666] | [6.866666666666666, 11.666666666666666] |
| service_regime_count | [10, 20] | [10, 20] |
| sustained_headway_level_count | [6, 12] | [6, 13] |
| tail_headway_minutes | [14, 30] | [14, 30] |
| wait_minutes | [6.073427220303305, 6.217911989725442] | [6.073427220303305, 6.217911989725442] |

| Role | Fingerprint | Avg wait | Max bucket | P90 | Mismatch | Fleet | Regimes | Sustained count | Sustained palettes OB / IB | Effective palettes OB / IB | OB tail / max | IB tail / max |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: |
| MINIMUM_AVERAGE_WAIT | `5b88a90840c914acb13c44f84ebf07cf2144a03ed1d64aded2c0658b123e976e` | 6.073427 | 11.500000 | 7.500000 | 0.00814976 | 18 | 15 | 9 | [9, 10, 13, 14, 15] / [8, 9, 14, 15] | [9, 14] / [9, 15] | 15 / 7.5 | 15 / 7.500000000000001 |
| MINIMUM_FLEET | `033a75f2b83562191946307bb53f2dd8ad7f45fc29c1bd52209e5ffb7be3b1bc` | 6.166344 | 9.500000 | 7.500000 | 0.01440522 | 14 | 14 | 8 | [11, 12, 13, 15] / [11, 12, 13, 14] | [12, 15] / [12, 13] | 15 / 7.5 | 14 / 7.0 |
| MINIMUM_MAXIMUM_BUCKET_WAIT | `280cc2d49857a2ad1e77604e0e5c9f8e14a91da68661d28cf9457292b56d7593` | 6.195996 | 8.500000 | 6.966667 | 0.01437383 | 15 | 11 | 7 | [11, 12, 13, 14] / [11, 13, 14] | [12, 13] / [11, 13] | 14 / 7.0 | 14 / 7.0 |
| MINIMUM_MISMATCH | `d9812afa9dca31e7b88665c73568a6cf4bccdf93136ca0d8ddcfbcdacd439b89` | 6.144048 | 27.500000 | 10.166667 | 0.00636830 | 20 | 20 | 12 | [7, 9, 10, 12, 15, 18, 19] / [9, 10, 13, 14, 15] | [7, 10, 12, 15, 18] / [9, 14] | 30 / 14.999999999999998 | 15 / 7.5 |
| MINIMUM_SUSTAINED_PALETTE | `91bd392692a31e0c33b59cc5e0ec893d1147fcb7fb7b04661a40a378a2abc6dc` | 6.127912 | 12.500000 | 7.500000 | 0.00951140 | 18 | 12 | 6 | [11, 13, 14] / [8, 11, 15] | [11, 13] / [8, 11, 15] | 14 / 7.0 | 15 / 7.500000000000001 |

Average-vs-access tradeoff witnesses on I frontier: **545**.

## Route 10 — H → I

H Pareto: **11**; I Pareto: **11**; H candidates removed only by maximum-bucket wait: **0**.

| Metric | H range | I range |
| --- | ---: | ---: |
| fleet | [11, 13] | [11, 13] |
| maximum_bucket_wait_minutes | [12.900000000000002, 34.2] | [12.900000000000002, 34.2] |
| mismatch | [0.008393103418565044, 0.012524369948702048] | [0.008393103418565044, 0.012524369948702048] |
| p90_bucket_wait_minutes | [11.333333333333334, 15.000000000000002] | [11.333333333333334, 15.000000000000002] |
| service_regime_count | [11, 16] | [11, 16] |
| sustained_headway_level_count | [8, 13] | [8, 13] |
| tail_headway_minutes | [22, 54] | [22, 54] |
| wait_minutes | [9.579767336017012, 9.807655861327559] | [9.579767336017012, 9.807655861327559] |

| Role | Fingerprint | Avg wait | Max bucket | P90 | Mismatch | Fleet | Regimes | Sustained count | Sustained palettes OB / IB | Effective palettes OB / IB | OB tail / max | IB tail / max |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: |
| MINIMUM_AVERAGE_WAIT | `4e9ab6a29572ccb813f06a11a3a8ee62792d5fc9290f3485dbaa99706716b9be` | 9.579767 | 15.000000 | 12.600000 | 0.00924450 | 13 | 12 | 11 | [14, 18, 19, 20, 21, 23] / [13, 15, 20, 22, 30] | [14, 19, 20, 23] / [13, 15, 20, 22, 30] | 23 / 12.900000000000002 | 30 / 15.000000000000002 |
| MINIMUM_FLEET | `2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3` | 9.613878 | 14.066667 | 11.333333 | 0.01201364 | 11 | 11 | 9 | [17, 18, 19, 20, 22, 23] / [19, 20, 29] | [17, 20, 23] / [19, 29] | 23 / 12.900000000000002 | 29 / 14.066666666666666 |
| MINIMUM_MAXIMUM_BUCKET_WAIT | `9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0` | 9.593949 | 12.900000 | 12.400000 | 0.01061358 | 13 | 12 | 10 | [14, 18, 19, 20, 21, 23] / [14, 15, 22, 23] | [14, 19, 20, 23] / [14, 22] | 23 / 12.900000000000002 | 23 / 12.9 |
| MINIMUM_MISMATCH | `d8743c4608523fe045f6abda7e4c322c01c958ccad17e5ad80d72584f844fabb` | 9.640134 | 22.500000 | 15.000000 | 0.00839310 | 13 | 15 | 13 | [14, 18, 19, 20, 21, 23] / [12, 14, 15, 20, 21, 22, 30] | [14, 19, 20, 23] / [12, 14, 21, 30] | 23 / 12.900000000000002 | 45 / 22.500000000000004 |
| MINIMUM_SUSTAINED_PALETTE | `6dbd9d2cac0931e85b1b50283b7011c610488226c863ce0192ff6bdf22bd3f16` | 9.661527 | 14.066667 | 11.666667 | 0.01252437 | 12 | 11 | 8 | [15, 17, 19, 20, 22] / [19, 20, 29] | [15, 17, 19, 22] / [19, 29] | 22 / 11.933333333333335 | 29 / 14.066666666666666 |

Average-vs-access tradeoff witnesses on I frontier: **10**.

### Route 10 inbound 30/45-minute tail audit

- `4e9ab6a29572ccb813f06a11a3a8ee62792d5fc9290f3485dbaa99706716b9be` inbound tail 30: retained because its other objectives preserve a nondominated tradeoff.
- `d8743c4608523fe045f6abda7e4c322c01c958ccad17e5ad80d72584f844fabb` inbound tail 45: retained because its other objectives preserve a nondominated tradeoff.

## Human Final Route 6

Accepted workbook SHA matched. Post-search benchmark only: average wait 6.150963, max bucket 12.500000, P90 7.500000, mismatch 0.00680207, fleet 19.

## Decision

Classification: **WORST_BUCKET_WAIT_MATERIAL_TO_FRONTIER**.
Proceed to data-driven materiality selection: **TRUE**.

## Production change statement

- Average passenger wait changed: **NO**
- Compiler changed: **NO**
- Demand mismatch changed: **NO**
- Final XLSX regenerated: **NO**
- Fleet validator changed: **NO**
- Maximum bucket wait added to Pareto: **YES**
- Production Pareto semantics changed: **YES**
- Protection changed: **NO**
- Queue changed: **NO**
- Rhythm semantics changed from H: **NO**
- Search budgets changed: **NO**
- Settlement added: **NO**
- Tail eligibility changed from H: **NO**
