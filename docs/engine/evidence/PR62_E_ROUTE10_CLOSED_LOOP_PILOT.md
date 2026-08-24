# PR62-E — Route 10 Closed-Loop Pilot

Status: **SEARCH_BUDGET_EXHAUSTED**. Deterministic replay: **passed**.

No production scheduling policy changed.

## Frozen authority and search

- Runtime / layover / fleet: 80 / 5 / 13
- Endpoints out: 05:00–21:00
- Endpoints in: 04:45–21:00
- Budgets: `{"max_compile_frontier_per_state": 4, "max_directional_compilations": 24, "max_open_states": 512, "max_pair_frontier": 512, "max_service_plan_evaluations": 24}`

## Search audit

| Generated | Evaluated | Duplicate | Pruned | Iterations | Compile | Protected rejected | Fleet | Out archive | In archive | Pareto | Open at stop |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 609913 | 24 | 66041 | 543328 | 24 | 88 | 0 | 1392 | 24 | 24 | 124 | 512 |

Generation/evaluation ratio: **25413.04**; pruned share: **0.8908**; duplicate share: **0.1083**.

Queue: **LOCALIZED_FEEDBACK_QUEUE_STARVATION**. Neighbor generation: **MATERIAL_NEIGHBOR_GENERATION_EXPLOSION**.

## Final frontier

- Mismatch: 0.007901–0.014005
- Exact passenger wait: 9.5371–10.0648 minutes
- Fleet: 11–13
- Exact wait changes frontier membership: true (124 with wait versus 102 without wait)
- Demand-regime frequency ratio out/in: 1.220–1.800 / 1.105–4.350
- Direction accuracy out/in: 0.123–1.000 / 0.120–1.000
- Exact-flat final directional compilations out/in: 0 / 0
- Clean-boundary blockers: 0
- Settlement: **SETTLEMENT_NOT_CURRENTLY_NEEDED**

### Representative clean candidate

Pair `e8daa851f95a2eee08d6e6ccf6524adfbd5a0187932dcf35cb90f257f9d0043b`: wait 9.5371 minutes, mismatch 0.011871, fleet 12, max jump 0.258.

- Out: `05:00–06:25 @17 (6); 06:42–07:54 @18 (5); 08:12–11:52 @20 (12); 12:11–15:21 @19 (11); 15:38–17:20 @17 (7); 17:37–18:43 @22 (4); 19:05–21:00 @23 (6)`
- In: `04:45–06:58 @19 (8); 07:18–15:18 @20 (25); 15:35–17:17 @17 (7); 17:34–19:40 @21 (7); 20:00–21:00 @20 (4)`

Exact ServiceRegimes, departures, per-direction waits, maximum bucket wait, demand-response projections, and terminal-wait metrics for every pair are serialized in the companion JSON.

## Feedback effectiveness

| Code | Emitted | Children | Evaluated descendants | Directional retained | Feasible pairs | Final ancestry |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DEMAND_OVERSERVED_INTERVAL | 88 | 685 | 4 | 6 | 74 | 27 |
| DEMAND_RESPONSE_DIRECTION_MISMATCH | 51 | 279 | 0 | 0 | 0 | 0 |
| DEMAND_UNDERSERVED_INTERVAL | 88 | 3069 | 9 | 15 | 109 | 31 |
| FLEET_LIMIT_EXCEEDED | 973 | 603103 | 12 | 19 | 178 | 52 |
| LARGEST_SERVICE_FREQUENCY_JUMP | 88 | 2755 | 8 | 13 | 104 | 28 |
| REDUNDANT_SERVICE_BOUNDARY | 13 | 10 | 0 | 0 | 0 | 0 |
| TAIL_OVER_SERVICE | 82 | 0 | 0 | 0 | 0 | 0 |
