# PR62-F2 — Fleet neighborhood narrowing

F2 replaces the pure `FLEET_LIMIT_EXCEEDED` global redesign family with small, reversible perturbations of existing ServiceRegimes. Fleet evidence remains cross-directional operational evidence; it does not localize a missing demand boundary and therefore no longer authorizes `SPLIT_REGIME`.

Generic/non-fleet shifts remain exhaustive. Pure-fleet shifts move one planning-grid boundary step and retain only feasible left counts at parent count - 1, unchanged, or + 1, with no exhaustive fallback. The resulting pre-dedupe bound is `9 * (N - 1) + 2`; this is structural, not a truncation cap.

## F1 → F2 search metrics

### Route 6

| Metric | PR62-F1 | PR62-F2 |
|---|---:|---:|
| States generated | 16,828 | 8,644 |
| States evaluated | 24 | 24 |
| States pruned | 14,811 | 7,438 |
| Duplicates | 1,481 | 670 |
| Generation / evaluation | 701.17 | 360.17 |
| Fleet validations | 1,728 | 1,728 |
| Fleet feedback events | 1,372 | 1,372 |
| Fleet expansion requests / executions / skips | 2,744 / 23 / 2,721 | 2,744 / 23 / 2,721 |
| Fleet-generated children | 9,799 | 1,615 |
| Fleet children per parent min / median / max | 267 / 473 / 494 | 60 / 63 / 87 |
| Pareto size | 130 | 130 |
| Open queue at stop | 512 | 512 |

Pure-fleet move attribution: `MERGE_ADJACENT` 208, `MOVE_ONE_TRIP_LEFT_TO_RIGHT` 189, `MOVE_ONE_TRIP_RIGHT_TO_LEFT` 190, `SHIFT_BOUNDARY_LEFT` 510, `SHIFT_BOUNDARY_RIGHT` 518, `SPLIT_REGIME` 0, `TAIL_ABSORB_ONE` 0, `TAIL_RELEASE_ONE` 0.

Response feedback: 262 generated / 0 evaluated in F1; 262 generated / 0 evaluated / 0 retained directional compilations / 0 feasible pair participations / 0 final Pareto ancestry in F2.

Queue classification: `LOCALIZED_FEEDBACK_QUEUE_STARVATION_PERSISTS`. Determinism signature: `47aa88aa5c16b0f59b73cbbbf9d38784239cfbea40d60abb9fa3f23b73f78d41`.

### Route 10

| Metric | PR62-F1 | PR62-F2 |
|---|---:|---:|
| States generated | 14,940 | 8,036 |
| States evaluated | 24 | 24 |
| States pruned | 12,978 | 6,790 |
| Duplicates | 1,418 | 710 |
| Generation / evaluation | 622.50 | 334.83 |
| Fleet validations | 1,392 | 1,392 |
| Fleet feedback events | 973 | 973 |
| Fleet expansion requests / executions / skips | 1,946 / 23 / 1,923 | 1,946 / 23 / 1,923 |
| Fleet-generated children | 8,130 | 1,226 |
| Fleet children per parent min / median / max | 209 / 313 / 587 | 36 / 59 / 68 |
| Pareto size | 124 | 124 |
| Open queue at stop | 512 | 512 |

Pure-fleet move attribution: `MERGE_ADJACENT` 143, `MOVE_ONE_TRIP_LEFT_TO_RIGHT` 139, `MOVE_ONE_TRIP_RIGHT_TO_LEFT` 132, `SHIFT_BOUNDARY_LEFT` 406, `SHIFT_BOUNDARY_RIGHT` 406, `SPLIT_REGIME` 0, `TAIL_ABSORB_ONE` 0, `TAIL_RELEASE_ONE` 0.

Response feedback: 279 generated / 0 evaluated in F1; 279 generated / 8 evaluated / 13 retained directional compilations / 103 feasible pair participations / 28 final Pareto ancestry in F2.

Queue classification: `LOCALIZED_FEEDBACK_QUEUE_STARVATION_RESOLVED`. Determinism signature: `82062d271c25b5cbce870ee0b9b60f30e6bfd5e4414bcffa47165db8f885b3a8`.

## Frontier quality

- Route 6: Pareto 130; fleet 14–20; wait 6.043783–6.237120; mismatch 0.006205–0.015651; response accuracy 0.567335–1.000000. Representative `b6712e5e1a552fa75fbfe042454b7d0568e4cd06b265b7d38d8760358dfb4063` has fleet 19, wait 6.043783, meaningful demand differentiation, and sustained clean ServiceRegimes. Representative changed: no.
- Route 10: Pareto 124; fleet 11–13; wait 9.537105–10.064760; mismatch 0.007901–0.014005; response accuracy 0.119658–1.000000. Representative `e8daa851f95a2eee08d6e6ccf6524adfbd5a0187932dcf35cb90f257f9d0043b` has fleet 12, wait 9.537105, meaningful demand differentiation, and sustained clean ServiceRegimes. Representative changed: no.

## Decision and guards

Classification: `QUEUE_PRIORITY_NOW_PRIMARY`. Fleet breadth is materially corrected and no longer dominates pathologically. Route 10 localized response revisions now receive meaningful evaluation and exact-pair participation; Route 6 response children remain unevaluated under the unchanged queue ordering and 24-state budget. Queue-priority work is therefore justified for the remaining Route 6 starvation, but is not implemented in F2.

No queue-priority, D1 identity, F1 cache, budget, generic/non-fleet operator, Pareto, compiler, fleet-validator, demand-response, or settlement semantics changed. No clean-boundary blocker appeared, so settlement remains `SETTLEMENT_NOT_CURRENTLY_NEEDED`.
