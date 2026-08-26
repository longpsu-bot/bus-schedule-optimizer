# PR62-H — Operational rhythm simplicity and slowest-tail semantics

Starting G commit: `bb8a53cfb433a8a6ae89771f96da54f4fc005164`.

Production search semantics changed: **YES**. Compiler, compiler path score, generic queue priority, search budgets, passenger-wait semantics, fleet validation, protection semantics, and final XLSX products are unchanged.

## Route 6 — G → H

G eligible under H: **NO**.

- G outbound: `TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION`, tail 15 min, max prior 16 min, margin -1 min, tail demand 53.258170/h.
- G inbound: `TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION`, tail 15 min, max prior 16 min, margin -1 min, tail demand 48.696545/h.

H: `SEARCH_BUDGET_EXHAUSTED`; generated/evaluated/pruned 7884/24/6920; tail rejections 68; fleet validations 140; response anchors 2; Pareto 46.

H_REVIEW_REPRESENTATIVE `5b88a90840c914acb13c44f84ebf07cf2144a03ed1d64aded2c0658b123e976e`: fleet 18, wait 6.073427, mismatch 0.00814976, ServiceRegimes 15, sustained palette count 9, effective palette count 4.

| Role | Fingerprint | Wait | Mismatch | Fleet | Regimes | Sustained levels | Effective palette | OB tail | IB tail |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| MINIMUM_WAIT | `5b88a90840c9` | 6.073427 | 0.00814976 | 18 | 15 | 9 | 4 | 15/0 `TAIL_IS_SLOWEST` | 15/0 `TAIL_IS_SLOWEST` |
| MINIMUM_SUSTAINED_PALETTE | `91bd392692a3` | 6.127912 | 0.00951140 | 18 | 12 | 6 | 5 | 14/1 `TAIL_IS_SLOWEST` | 15/0 `TAIL_IS_SLOWEST` |
| MINIMUM_FLEET | `7ed55e54ac05` | 6.117469 | 0.01353021 | 14 | 16 | 8 | 4 | 15/2 `TAIL_IS_SLOWEST` | 15/2 `TAIL_IS_SLOWEST` |
| MINIMUM_MISMATCH | `d9812afa9dca` | 6.144048 | 0.00636830 | 20 | 20 | 12 | 7 | 30/0 `TAIL_IS_SLOWEST` | 15/0 `TAIL_IS_SLOWEST` |

## Route 10 — G → H

G eligible under H: **NO**.

- G outbound: `TAIL_IS_SLOWEST`, tail 23 min, max prior 22 min, margin 1 min, tail demand 34.055556/h.
- G inbound: `TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION`, tail 20 min, max prior 21 min, margin -1 min, tail demand 32.359477/h.

H: `SEARCH_BUDGET_EXHAUSTED`; generated/evaluated/pruned 7864/24/6957; tail rejections 56; fleet validations 135; response anchors 2; Pareto 11.

H_REVIEW_REPRESENTATIVE `4e9ab6a29572ccb813f06a11a3a8ee62792d5fc9290f3485dbaa99706716b9be`: fleet 13, wait 9.579767, mismatch 0.00924450, ServiceRegimes 12, sustained palette count 11, effective palette count 9.

| Role | Fingerprint | Wait | Mismatch | Fleet | Regimes | Sustained levels | Effective palette | OB tail | IB tail |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| MINIMUM_WAIT | `4e9ab6a29572` | 9.579767 | 0.00924450 | 13 | 12 | 11 | 9 | 23/2 `TAIL_IS_SLOWEST` | 30/8 `TAIL_IS_SLOWEST` |
| MINIMUM_SUSTAINED_PALETTE | `91e7e59f64f7` | 9.620537 | 0.01175862 | 12 | 11 | 8 | 6 | 24/2 `TAIL_IS_SLOWEST` | 29/9 `TAIL_IS_SLOWEST` |
| MINIMUM_FLEET | `2a7a8c3c142d` | 9.613878 | 0.01201364 | 11 | 11 | 9 | 5 | 23/1 `TAIL_IS_SLOWEST` | 29/9 `TAIL_IS_SLOWEST` |
| MINIMUM_MISMATCH | `d8743c460852` | 9.640134 | 0.00839310 | 13 | 15 | 13 | 8 | 23/2 `TAIL_IS_SLOWEST` | 45/15 `TAIL_IS_SLOWEST` |

## Human Final

Workbook SHA matched: **TRUE**. Wait 6.150963, mismatch 0.00680207, fleet 19.

- outbound: sustained (8, 10, 15); single-gap (); effective (8, 10, 15); runs 9; tail `TAIL_IS_SLOWEST`.
- inbound: sustained (8, 15); single-gap (14,); effective (8, 15); runs 8; tail `TAIL_IS_SLOWEST`.

## Decision

- Product recertification required: **TRUE**.
- Route 6 tail: `TAIL_RULE_EFFECTIVE`; rhythm: `RHYTHM_SIMPLICITY_MATERIAL_TRADEOFF`.
- Route 10 tail: `TAIL_RULE_EFFECTIVE`; rhythm: `RHYTHM_SIMPLICITY_MATERIAL_TRADEOFF`.
- A subsequent materiality-selection milestone is justified; H intentionally adds no scalar wait-per-level threshold.

## Determinism

- route_10_coordinator_report.json: `b8ce2134936c98dd0f59861f3451f52db426369c81ddfb78b587de93407db715`
- route_10_coordinator_report.md: `376df2236502530d1510cbca39fe8995ec8b509831c2169578111add54190f5c`
- route_6_coordinator_report.json: `f0034bd42796a5df739152bdb17b028b6f473f26c706972d69fe75f7d40ce3d0`
- route_6_coordinator_report.md: `a4855bf1328718cdec5654c04bed8c98ccd5b7dceb2586e5135b890f7da25156`
