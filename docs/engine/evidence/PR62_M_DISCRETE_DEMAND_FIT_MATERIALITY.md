# PR62-M — Discrete demand-fit materiality calibration

Profile: `discrete_demand_fit_materiality_v1`.

Production SSE mismatch remains authoritative. Total-variation and trip-equivalent error are review-only interpretable companions.

Directional TV is half the L1 distance between exact service shares and immutable demand shares. Directional trip-equivalent error multiplies TV by exact directional trip count; pair error sums directions without averaging.

## Route 6

I Pareto `47`; hard feasible `47`; access-safe `41`.

SSE best: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`; TV/TE best: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b`; same: `True`; pairwise disagreements: `61`.

### Focused comparisons

| roles | fingerprint | SSE | OB TV | IB TV | pair TE | ΔTE vs best | moves vs L | avg wait | max OB/IB | fleet | rhythm | tails OB/IB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| L_SELECTED | `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b` | 0.006691497 | 0.114673942 | 0.153579568 | 20.923774 | 0.000000 | 0 | 6.087639 | 10.500000/12.500000 | 20 | (8, 14, 6, 0) | 15/15 |
| NEXT_BEST_SSE_MISMATCH | `1ee89f8429eb087e4f9663975ae893fb8e636d0eadd617783cbc8428847192e8` | 0.006996508 | 0.124026522 | 0.153579568 | 21.653275 | 0.729501 | 3 | 6.086718 | 10.500000/12.500000 | 19 | (8, 15, 5, 0) | 15/15 |
| MINIMUM_SUSTAINED_PALETTE | `ccd0e2b10d9ec9c2f1cd1cf41e6a3ea72c3f84283830af9277b3dfb5fd620fdb` | 0.013296007 | 0.169748660 | 0.206386450 | 29.338539 | 8.414765 | 14 | 6.167884 | 8.500000/8.500000 | 14 | (6, 10, 4, 0) | 14/14 |
| MINIMUM_FLEET | `7ed55e54ac0542416be3a51cc82dcbe6426d2980d31e85456225a634b8879150` | 0.013530214 | 0.157671379 | 0.197984837 | 27.741185 | 6.817411 | 14 | 6.117469 | 9.500000/9.500000 | 14 | (8, 16, 4, 0) | 15/15 |
| MINIMUM_AVERAGE_WAIT | `5b88a90840c914acb13c44f84ebf07cf2144a03ed1d64aded2c0658b123e976e` | 0.008149760 | 0.124026522 | 0.159801295 | 22.138570 | 1.214796 | 5 | 6.073427 | 10.500000/11.500000 | 18 | (9, 15, 4, 0) | 15/15 |

### Exact breakpoint path

- ΔTE `0.000000`: `ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b` (envelope 1).
- ΔTE `3.353800`: `ae3c74d827222635551a604db5dfcc138d439813d4fcff2d3a85d4102b2a17fa` (envelope 10).
- ΔTE `3.809881`: `469d9aca5c96181be86ec08d2fa606bb8114dd45e8389d693ae1ce2967704ab9` (envelope 15).
- ΔTE `4.295828`: `91bd392692a31e0c33b59cc5e0ec893d1147fcb7fb7b04661a40a378a2abc6dc` (envelope 21).
- ΔTE `8.414765`: `ccd0e2b10d9ec9c2f1cd1cf41e6a3ea72c3f84283830af9277b3dfb5fd620fdb` (envelope 37).

One-trip diagnostic: simpler within <1 TE `False`; within <=1 TE `False`; minimum `3.353800`.

Classification: `AT_LEAST_ONE_TRIP_EQUIVALENT_REQUIRED_FOR_SIMPLICITY`.

## Route 10

I Pareto `11`; hard feasible `11`; access-safe `7`.

SSE best: `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`; TV/TE best: `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c`; same: `True`; pairwise disagreements: `2`.

### Focused comparisons

| roles | fingerprint | SSE | OB TV | IB TV | pair TE | ΔTE vs best | moves vs L | avg wait | max OB/IB | fleet | rhythm | tails OB/IB |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| L_SELECTED, MINIMUM_AVERAGE_WAIT | `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` | 0.009369737 | 0.172595560 | 0.159898559 | 16.957200 | 0.000000 | 0 | 9.592580 | 12.900000/13.366667 | 13 | (11, 12, 7, 0) | 23/24 |
| NEXT_BEST_SSE_MISMATCH | `9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0` | 0.010613576 | 0.172595560 | 0.180251715 | 17.995211 | 1.038011 | 2 | 9.593949 | 12.900000/12.900000 | 13 | (10, 12, 6, 0) | 23/23 |
| MINIMUM_SUSTAINED_PALETTE | `6dbd9d2cac0931e85b1b50283b7011c610488226c863ce0192ff6bdf22bd3f16` | 0.012524370 | 0.208119660 | 0.173864274 | 19.481181 | 2.523981 | 17 | 9.661527 | 12.866667/14.066667 | 12 | (8, 11, 6, 0) | 22/29 |
| MINIMUM_FLEET | `2a7a8c3c142d6aee45394dcacf024718f9f57b277e32587964f20d941c4d39f3` | 0.012013640 | 0.187205060 | 0.173864274 | 18.414536 | 1.457336 | 13 | 9.613878 | 12.900000/14.066667 | 11 | (9, 11, 5, 0) | 23/29 |

### Exact breakpoint path

- ΔTE `0.000000`: `bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c` (envelope 1).
- ΔTE `0.712251`: `e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24` (envelope 2).
- ΔTE `1.188629`: `c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7` (envelope 4).
- ΔTE `1.696236`: `91e7e59f64f782f45705d945fa8a8338cf5cd4c812a3e97a93e40d95b0d79ede` (envelope 6).

One-trip diagnostic: simpler within <1 TE `True`; within <=1 TE `True`; minimum `0.712251`.

Classification: `SUB_ONE_TRIP_EQUIVALENT_SIMPLICITY_TRADEOFF`.

## Route 6 Human Final

Classification: `POST_SEARCH_EXPERT_BENCHMARK`; never selectable.

Human Final pair TE `19.892407`; selected-minus-human TE `1.031367`; SSE `-0.000110576`; bucket moves `6`; sustained/effective palette difference `3/1`; fleet `1`; wait `-0.063324` minutes.

## Decision

Cross-route classification: `TRIP_EQUIVALENT_CALIBRATION_READY_FOR_POLICY`.

A one-trip quantum is reported descriptively only. No materiality boundary or production selector change is implemented.

## Production guards

- coordinator_search_changed: **NO**
- 10-D_Pareto_changed: **NO**
- L_selector_changed: **NO**
- demand_mismatch_semantics_changed: **NO**
- TV_added_to_production_objective: **NO**
- compiler_changed: **NO**
- tail_eligibility_changed: **NO**
- access_guardrail_changed: **NO**
- rhythm_semantics_changed: **NO**
- fleet_validator_changed: **NO**
- queue_changed: **NO**
- budgets_changed: **NO**
- settlement_added: **NO**
- final_XLSX_regenerated: **NO**
- production_selector_threshold_added: **NO**
- private_workbook_committed: **NO**
