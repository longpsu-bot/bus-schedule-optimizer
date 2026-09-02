# PR62-E — Closed-Loop Architecture Decision

No production scheduling policy changed.

## Cross-route decision

- Queue starvation: **LOCALIZED_FEEDBACK_QUEUE_STARVATION**
- Neighbor generation: **MATERIAL_NEIGHBOR_GENERATION_EXPLOSION**
- Settlement: **SETTLEMENT_NOT_CURRENTLY_NEEDED**
- Route 6 exact wait changes evaluated-feasible frontier membership: **true**
- Route 10 exact wait changes evaluated-feasible frontier membership: **true**

Queue starvation and neighbor-generation amplification are classified independently. Queued states are assessed only with pre-compile evidence; uncompiled states receive no fabricated exact wait or fleet metric.

## Pilot questions

- **Localized feedback is useful but selective.** Route 6 final ancestry includes 15 overservice-feedback pairs and 8 fleet-feedback pairs; Route 10 includes 27 overservice, 31 underservice, 28 largest-jump, and 52 fleet-feedback pairs. Demand-response-mismatch children were generated on both routes but none reached the final frontier within 24 evaluations.
- **Exact passenger wait is material to the evaluated frontier.** Route 6 retains 130 pairs with the wait dimension versus 116 without it; Route 10 retains 124 versus 102.
- **Demand differentiation survives.** No final directional compilation is exactly flat. Frequency max/min ratios span 1.256–3.105 outbound and 1.256–2.571 inbound on Route 6; 1.220–1.800 and 1.105–4.350 on Route 10. Route 10's flattest inbound ratio of 1.105 remains a review tradeoff, not a rejected threshold case.
- **Useful exact-fleet-feasible candidates exist.** Every final pair passed exact fleet validation; fleets span 14–20 on Route 6 and 11–13 on Route 10.
- **Strict clean-boundary compilation did not reject an evaluated ServicePlan on either route.** There are no blocker witnesses, so settlement is not currently needed; Human Final's isolated 14-minute residual does not change that conclusion.
- **Neighbor generation is materially amplified.** Route 6 generated 1,209,043 states for 24 evaluations (50,376.79:1); Route 10 generated 609,913 (25,413.04:1). Fleet-limit lineage alone generated 1,202,014 and 603,103 children respectively.

## Route 6 expert benchmark

Human Final records fleet 19, mismatch 0.006802, wait 6.1510 minutes, and 9/8 outbound/inbound headway runs. Production finds lower-wait and lower-mismatch points separately across its Pareto frontier, while its representative 19-vehicle clean pair has wait 6.0438, mismatch 0.007197, and 8/7 sustained compiled ServiceRegimes. This is a real tradeoff, not reproduction of Human Final timestamps.

## Route comparison

| Route | Status | Generated / evaluated | Ratio | Pareto | Queue | Neighbor generation | Blockers | Settlement |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: | --- |
| 6 | SEARCH_BUDGET_EXHAUSTED | 1209043 / 24 | 50376.79 | 130 | LOCALIZED_FEEDBACK_QUEUE_STARVATION | MATERIAL_NEIGHBOR_GENERATION_EXPLOSION | 0 | SETTLEMENT_NOT_CURRENTLY_NEEDED |
| 10 | SEARCH_BUDGET_EXHAUSTED | 609913 / 24 | 25413.04 | 124 | LOCALIZED_FEEDBACK_QUEUE_STARVATION | MATERIAL_NEIGHBOR_GENERATION_EXPLOSION | 0 | SETTLEMENT_NOT_CURRENTLY_NEEDED |

## Interpretation boundaries

- The 24-state evaluation budget was not increased and no larger-budget rerun was made.
- Flatness diagnostics select no new policy threshold; exact-flat and the flattest observed Pareto schedules are listed.
- Human Final remains a post-search benchmark. Its 14-minute residual alone is not settlement evidence.
- Exact passenger wait is compared with a counterfactual frontier over the same evaluated exact-fleet-feasible pair set.
- Full exact departures are retained only for final Pareto directional compilations.
