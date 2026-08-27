# PR62-L — Domain-priority operational selector

Profile: `domain_priority_operational_selector_v1`.

Priority: hard operational feasibility → directional Scenario-B max-access non-regression → observed demand mismatch → rhythm simplicity → fleet efficiency.

## Route 6

| I Pareto | hard feasible | access-safe | best demand | best rhythm | best fleet | selected |
|---:|---:|---:|---:|---:|---:|---:|
| 47 | 47 | 41 | 1 | 1 | 1 | 1 |

Policy health: `DOMAIN_HIERARCHY_DEMAND_FIRST_COMPLEXITY_CONCERN`.

Selected: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`.

Mismatch `0.006691497`; average wait `6.087639` minutes; directional max OB/IB `10.500000`/`12.500000`; fleet `20/20`; regimes/sustained/effective `14`/`8`/`6`; tails OB/IB `15`/`15` minutes.

### Nearby alternatives

| roles | fingerprint | mismatch | Δ mismatch | avg wait | max OB/IB | fleet | regimes | sustained | effective | tails OB/IB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SELECTED | `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b` | 0.006691497 | 0.000000000 | 6.087639 | 10.500000/12.500000 | 20 | 14 | 8 | 6 | 15/15 |
| MINIMUM_SUSTAINED_PALETTE | `ccd0e2b10d9ec9c2f1cd1cf41e6a3ea72c3f84283830af9277b3dfb5fd620fdb` | 0.013296007 | 0.006604510 | 6.167884 | 8.500000/8.500000 | 14 | 10 | 6 | 4 | 14/14 |
| MINIMUM_FLEET | `7ed55e54ac0542416be3a51cc82dcbe6426d2980d31e85456225a634b8879150` | 0.013530214 | 0.006838717 | 6.117469 | 9.500000/9.500000 | 14 | 16 | 8 | 4 | 15/15 |
| MINIMUM_AVERAGE_WAIT | `5b88a90840c914acb13c44f84ebf07cf2144a03ed1d64aded2c0658b123e976e` | 0.008149760 | 0.001458263 | 6.073427 | 10.500000/11.500000 | 18 | 15 | 9 | 4 | 15/15 |
| NEXT_BEST_MISMATCH | `1ee89f8429eb087e4f9663975ae893fb8e636d0eadd617783cbc8428847192e8` | 0.006996508 | 0.000305011 | 6.086718 | 10.500000/12.500000 | 19 | 15 | 8 | 5 | 15/15 |

## Route 10

| I Pareto | hard feasible | access-safe | best demand | best rhythm | best fleet | selected |
|---:|---:|---:|---:|---:|---:|---:|
| 11 | 11 | 7 | 1 | 1 | 1 | 1 |

Policy health: `DOMAIN_HIERARCHY_DEMAND_FIRST_COMPLEXITY_CONCERN`.

Selected: `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`.

Mismatch `0.009369737`; average wait `9.592580` minutes; directional max OB/IB `12.900000`/`13.366667`; fleet `13/13`; regimes/sustained/effective `12`/`11`/`7`; tails OB/IB `23`/`24` minutes.

### Nearby alternatives

| roles | fingerprint | mismatch | Δ mismatch | avg wait | max OB/IB | fleet | regimes | sustained | effective | tails OB/IB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| SELECTED, MINIMUM_AVERAGE_WAIT | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 0.009369737 | 0.000000000 | 9.592580 | 12.900000/13.366667 | 13 | 12 | 11 | 7 | 23/24 |
| MINIMUM_SUSTAINED_PALETTE | `6dbd9d2cac0931e85b1b50283b7011c610488226c863ce0192ff6bdf22bd3f16` | 0.012524370 | 0.003154633 | 9.661527 | 12.866667/14.066667 | 12 | 11 | 8 | 6 | 22/29 |
| MINIMUM_FLEET | `2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3` | 0.012013640 | 0.002643903 | 9.613878 | 12.900000/14.066667 | 11 | 11 | 9 | 5 | 23/29 |
| NEXT_BEST_MISMATCH | `9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0` | 0.010613576 | 0.001243839 | 9.593949 | 12.900000/12.900000 | 13 | 12 | 10 | 6 | 23/23 |

### Inbound extreme-tail audit

- 30 minutes `4e9ab6a29572ccb813f06a11a3a8ee62792d5fc9290f3485dbaa99706716b9be`: `INBOUND_MAX_ACCESS_REGRESSION`; candidate IB max `15.000000` vs Scenario B `14.166667`.
- 45 minutes `d8743c4608523fe045f6abda7e4c322c01c958ccad17e5ad80d72584f844fabb`: `INBOUND_MAX_ACCESS_REGRESSION`; candidate IB max `22.500000` vs Scenario B `14.166667`.
- 48 minutes `025353e2311d8508d1984a34d4acb2ee9e7228a16af1a69bb97ff5b649e77934`: `INBOUND_MAX_ACCESS_REGRESSION`; candidate IB max `27.000000` vs Scenario B `14.166667`.
- 54 minutes `8fcacf72ae51cf31e351f29f367f0094fac654ea85bd0f3a29470502a0939d62`: `INBOUND_MAX_ACCESS_REGRESSION`; candidate IB max `34.200000` vs Scenario B `14.166667`.

## Route 6 Human Final

Classification: `POST_SEARCH_EXPERT_BENCHMARK`; never selectable.

Strict demand-fit-first substantially more complex: `True`.

## Decision

`READY_FOR_POST_HIJKL_RECERTIFICATION = false`.

## Production guards

- Pareto_changed: **NO**
- XLSX_regenerated: **NO**
- budgets_changed: **NO**
- compiler_changed: **NO**
- fleet_validator_changed: **NO**
- mismatch_semantics_changed: **NO**
- private_workbook_committed: **NO**
- queue_changed: **NO**
- settlement_added: **NO**
- tail_eligibility_changed: **NO**
- wait_semantics_changed: **NO**
