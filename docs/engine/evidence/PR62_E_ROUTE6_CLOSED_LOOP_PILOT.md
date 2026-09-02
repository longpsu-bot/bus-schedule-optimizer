# PR62-E — Route 6 Closed-Loop Pilot

Status: **SEARCH_BUDGET_EXHAUSTED**. Deterministic replay: **passed**.

No production scheduling policy changed.

## Frozen authority and search

- Runtime / layover / fleet: 70 / 5 / 20
- Endpoints out: 04:55–21:00
- Endpoints in: 04:55–21:00
- Budgets: `{"max_compile_frontier_per_state": 4, "max_directional_compilations": 24, "max_open_states": 512, "max_pair_frontier": 512, "max_service_plan_evaluations": 24}`

## Search audit

| Generated | Evaluated | Duplicate | Pruned | Iterations | Compile | Protected rejected | Fleet | Out archive | In archive | Pareto | Open at stop |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1209043 | 24 | 137083 | 1071424 | 24 | 96 | 0 | 1728 | 24 | 24 | 130 | 512 |

Generation/evaluation ratio: **50376.79**; pruned share: **0.8862**; duplicate share: **0.1134**.

Queue: **LOCALIZED_FEEDBACK_QUEUE_STARVATION**. Neighbor generation: **MATERIAL_NEIGHBOR_GENERATION_EXPLOSION**.

## Final frontier

- Mismatch: 0.006205–0.015651
- Exact passenger wait: 6.0438–6.2371 minutes
- Fleet: 14–20
- Exact wait changes frontier membership: true (130 with wait versus 116 without wait)
- Demand-regime frequency ratio out/in: 1.256–3.105 / 1.256–2.571
- Direction accuracy out/in: 0.567–1.000 / 0.567–1.000
- Exact-flat final directional compilations out/in: 0 / 0
- Clean-boundary blockers: 0
- Settlement: **SETTLEMENT_NOT_CURRENTLY_NEEDED**

### Representative clean candidate

Pair `b6712e5e1a552fa75fbfe042454b7d0568e4cd06b265b7d38d8760358dfb4063`: wait 6.0438 minutes, mismatch 0.007197, fleet 19, max jump 0.629.

- Out: `04:55–05:59 @16 (5); 06:09–07:29 @10 (9); 07:39–10:27 @14 (13); 10:37–11:57 @10 (9); 12:07–15:52 @15 (16); 16:07–17:27 @8 (11); 17:35–18:45 @14 (6); 19:00–21:00 @15 (9)`
- In: `04:55–05:59 @16 (5); 06:08–07:29 @9 (10); 07:38–10:26 @14 (13); 10:36–11:56 @10 (9); 12:06–15:51 @15 (16); 16:00–17:21 @9 (10); 17:30–21:00 @15 (15)`

Exact ServiceRegimes, departures, per-direction waits, maximum bucket wait, demand-response projections, and terminal-wait metrics for every pair are serialized in the companion JSON.

## Feedback effectiveness

| Code | Emitted | Children | Evaluated descendants | Directional retained | Feasible pairs | Final ancestry |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DEMAND_OVERSERVED_INTERVAL | 96 | 1558 | 13 | 15 | 93 | 15 |
| DEMAND_RESPONSE_DIRECTION_MISMATCH | 39 | 262 | 0 | 0 | 0 | 0 |
| DEMAND_UNDERSERVED_INTERVAL | 96 | 2927 | 8 | 9 | 39 | 0 |
| FLEET_LIMIT_EXCEEDED | 1372 | 1202014 | 12 | 14 | 76 | 8 |
| LARGEST_SERVICE_FREQUENCY_JUMP | 96 | 2247 | 7 | 8 | 36 | 0 |
| REDUNDANT_SERVICE_BOUNDARY | 37 | 24 | 0 | 0 | 0 | 0 |
| TAIL_OVER_SERVICE | 96 | 0 | 0 | 0 | 0 | 0 |

## Route 6 expert references

The private workbook was loaded only after both production Route 6 searches and was never supplied to the search.

| Reference | Fleet | Mismatch | Expected wait | Out regimes | In regimes |
| --- | ---: | ---: | ---: | ---: | ---: |
| CURRENT | 20 | 0.006781 | 6.1656 | 10 | 10 |
| EXTERNAL_AI | 20 | 0.006944 | 6.1612 | 14 | 8 |
| HUMAN_FINAL | 19 | 0.006802 | 6.1510 | 9 | 8 |

Human Final uses 19 vehicles, mismatch 0.006802, and exact expected wait 6.1510 minutes. The production frontier spans fleet 14–20, mismatch 0.006205–0.015651, and wait 6.0438–6.2371. The representative 19-vehicle clean pair improves exact wait but trades to higher mismatch and more ServiceRegimes than Human Final; Human Final remains a benchmark, not search input.
