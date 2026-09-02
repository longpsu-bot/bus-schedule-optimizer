# PR62-F3 — Bounded demand-response exploration fairness

Seeds remain first. Each direction may reserve one response anchor in lane 1; all ordinary revisions retain their prior relative order in lane 2+.

## F2 → F3 response effectiveness

| Route | Children F2 → F3 | Anchor candidate / enqueued / evaluated | Evaluated descendants F2 → F3 | Retained F2 → F3 | Feasible pairs F2 → F3 | Pareto ancestry F2 → F3 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6 | 262 → 263 | 2 / 2 / 2 | 0 → 13 | 0 → 20 | 0 → 120 | 0 → 25 |
| 10 | 279 → 279 | 2 / 2 / 2 | 8 → 7 | 13 → 13 | 103 → 155 | 28 → 38 |

## Frontier

### Route 6

Pareto 130 → 140; fleet 14–20 → 14–20; wait 6.043783–6.237120 → 6.043783–6.217912; mismatch 0.006205–0.015651 → 0.005873–0.015651; response accuracy 0.567335–1.000000 → 0.567335–1.000000.

Representative `b6712e5e1a552fa75fbfe042454b7d0568e4cd06b265b7d38d8760358dfb4063`: fleet 19, wait 6.043783, mismatch 0.007197. Pair changed: false; ServiceRegimes changed: false.

### Route 10

Pareto 124 → 129; fleet 11–13 → 11–13; wait 9.537105–10.064760 → 9.537105–9.932414; mismatch 0.007901–0.014005 → 0.008306–0.014005; response accuracy 0.119658–1.000000 → 0.119658–1.000000.

Representative `e8daa851f95a2eee08d6e6ccf6524adfbd5a0187932dcf35cb90f257f9d0043b`: fleet 12, wait 9.537105, mismatch 0.011871. Pair changed: false; ServiceRegimes changed: false.

## Decision and guards

Classification: **RESPONSE_FAIRNESS_SUFFICIENT**.
Settlement: **SETTLEMENT_NOT_CURRENTLY_NEEDED**.

Production search-controller semantics changed: yes; queue ordering changed only for the bounded response-anchor lane. D1 identity, F1 idempotence, the F2 fleet family, budgets, Pareto, compiler, fleet validator, demand-response diagnosis, and settlement remain unchanged.

Both routes replayed twice with equal statistics, response-anchor fingerprints, evaluated fingerprints, feedback counts, and Pareto fingerprints.
