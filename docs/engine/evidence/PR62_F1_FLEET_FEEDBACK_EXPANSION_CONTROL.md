# PR62-F1 — Fleet-feedback expansion control

PR62-F1 makes pure `FLEET_LIMIT_EXCEEDED` neighbor expansion idempotent per semantic
ServicePlan fingerprint within one coordinator search. Independently evaluated infeasible exact
pairs remain authoritative feedback events. The production queue priority, budgets, fleet
operators, compiler, Pareto semantics, and settlement scope are unchanged.

The correction materially reduced repeated neighbor generation. Fleet-lineage children fell from
1,202,014 to 9,799 on Route 6 and from 603,103 to 8,130 on Route 10. Total generated states fell
from 1,209,043 to 16,828 and from 609,913 to 14,940 respectively. Both routes were deterministic
across two F1 runs.

## Search-control semantics

- Cache identity: semantic ServicePlan fingerprint, scoped to one coordinator search.
- Eligible request: non-empty feedback containing only `FLEET_LIMIT_EXCEEDED`.
- Fleet-excess magnitude, exact compilation, pair identity, history, and opposite candidate are not
  part of expansion identity.
- Mixed and non-fleet feedback calls are not suppressed.
- Feedback event counts remain independent from expansion requests, executions, and skips.
- A child rejected or pruned by the bounded open queue is not regenerated merely because another
  exact pair produces the same fleet feedback. This intentionally changes bounded search-control
  semantics and may change the explored frontier.

## Route 6 before → after

| Metric | PR62-E | PR62-F1 |
|---|---:|---:|
| Status | `SEARCH_BUDGET_EXHAUSTED` | `SEARCH_BUDGET_EXHAUSTED` |
| States generated | 1,209,043 | 16,828 |
| States evaluated | 24 | 24 |
| States pruned | 1,071,424 | 14,811 |
| Duplicate states skipped | 137,083 | 1,481 |
| Generation / evaluation | 50,376.79 | 701.17 |
| Fleet validations | 1,728 | 1,728 |
| Fleet feedback events | 1,372 | 1,372 |
| Fleet expansion requests | n/a | 2,744 |
| Fleet expansions executed | n/a | 23 |
| Fleet expansions skipped | n/a | 2,721 |
| Fleet-feedback generated children | 1,202,014 | 9,799 |
| Directional archive, outbound / inbound | 24 / 24 | 24 / 24 |
| Pareto size | 130 | 130 |
| Open queue at stop | 512 | 512 |

One executed Route 6 fleet expansion returned 267–494 children; median 473, total 9,799 across
23 semantic parents. `DEMAND_RESPONSE_DIRECTION_MISMATCH` generated 262 children both before and
after, with 0 evaluated descendants, 0 retained directional compilations, and 0 final Pareto
ancestry.

The final Route 6 frontier ranges were unchanged in this bounded run: fleet 14–20, expected wait
6.043783–6.237120 minutes, mismatch 0.006205–0.015651, and response-direction accuracy
0.567335–1.0. Representative pair
`b6712e5e1a552fa75fbfe042454b7d0568e4cd06b265b7d38d8760358dfb4063` requires fleet 19,
has expected wait 6.043783 minutes, mismatch 0.007197, 15 actual ServiceRegimes, meaningful demand
differentiation, and sustained clean ServiceRegimes. It remains a credible Route 6 candidate under
the requested broad quality checks.

## Route 10 before → after

| Metric | PR62-E | PR62-F1 |
|---|---:|---:|
| Status | `SEARCH_BUDGET_EXHAUSTED` | `SEARCH_BUDGET_EXHAUSTED` |
| States generated | 609,913 | 14,940 |
| States evaluated | 24 | 24 |
| States pruned | 543,328 | 12,978 |
| Duplicate states skipped | 66,041 | 1,418 |
| Generation / evaluation | 25,413.04 | 622.50 |
| Fleet validations | 1,392 | 1,392 |
| Fleet feedback events | 973 | 973 |
| Fleet expansion requests | n/a | 1,946 |
| Fleet expansions executed | n/a | 23 |
| Fleet expansions skipped | n/a | 1,923 |
| Fleet-feedback generated children | 603,103 | 8,130 |
| Directional archive, outbound / inbound | 24 / 24 | 24 / 24 |
| Pareto size | 124 | 124 |
| Open queue at stop | 512 | 512 |

One executed Route 10 fleet expansion returned 209–587 children; median 313, total 8,130 across
23 semantic parents. `DEMAND_RESPONSE_DIRECTION_MISMATCH` generated 279 children both before and
after, with 0 evaluated descendants, 0 retained directional compilations, and 0 final Pareto
ancestry. F1 therefore did not give Route 10 response-feedback descendants an evaluation slot under
the unchanged queue priority and budget.

The final Route 10 frontier ranges were also unchanged: fleet 11–13, expected wait
9.537105–10.064760 minutes, mismatch 0.007901–0.014005, and response-direction accuracy
0.119658–1.0. Representative pair
`e8daa851f95a2eee08d6e6ccf6524adfbd5a0187932dcf35cb90f257f9d0043b` requires fleet 12,
has expected wait 9.537105 minutes, mismatch 0.011871, 12 actual ServiceRegimes, meaningful demand
differentiation, and sustained clean ServiceRegimes.

## Interpretation

Fleet-feedback idempotence materially reduced repeated generation: 1,787,188 fleet-lineage child
attempts were removed across the two routes. Event counts remained unchanged, confirming the
separation between pair evidence and semantic-parent expansion.

Classification: `FLEET_UNIQUE_NEIGHBORHOOD_STILL_TOO_BROAD`. Repetition was a major amplification
mechanism, but a single unique global fleet revision still returns as many as 494 Route 6 children
and 587 Route 10 children, with fleet lineage still contributing 9,799 of 16,828 and 8,130 of
14,940 generated states. This is evidence for considering F2; F2 is not implemented here.

Queue classification remains `LOCALIZED_FEEDBACK_QUEUE_STARVATION` on both routes. Response-
mismatch descendants remain unevaluated. No clean-boundary blocker appeared, so settlement remains
`SETTLEMENT_NOT_CURRENTLY_NEEDED`.

## Determinism and guards

- Route 6 signature: `1874130d46c946171b6c13d32e494d0f0d30bb871c1a452399b12196dec367cd`.
- Route 10 signature: `19da6068e215f4aca31766695546000a5ee3c981a7ae13d9e124d9e05eb1b6e5`.
- Statistics, evaluated fingerprints, Pareto fingerprints, and feedback counts matched across both
  replays for each route.
- Budget remained exactly `24 / 512 / 4 / 24 / 512`.
- Queue priority changed: No.
- D1 queue identity changed: No.
- Fleet neighbor operator family changed: No.
- Pareto semantics changed: No.
- Compiler or fleet validator changed: No.
- Demand-response semantics changed: No.
- Settlement added: No.

The committed PR62-E Route 6/10 JSON and Markdown artifacts and architecture decision are referenced
by SHA-256 in the companion compact JSON. No large PR62-E artifact was regenerated, and no final
departure vectors are duplicated here.
