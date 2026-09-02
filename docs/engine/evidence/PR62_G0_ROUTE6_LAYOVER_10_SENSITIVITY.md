# PR62-G0 — Route 6 minimum-layover robustness sensitivity

This is sensitivity evidence only. The official Route 6 minimum-layover authority remains 5 minutes.

## Three cases

| Case | Timetable | Layover | Fleet | Within 20 | Wait (min) | Mismatch |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| A | selected production baseline | 5 | 19 | yes | 6.043783393 | 0.007197180 |
| B | exact Case A timetable | 10 | 20 | yes | 6.043783393 | 0.007197180 |
| C | reoptimized sensitivity | 10 | 20 | yes | 6.043783393 | 0.007197180 |

Classification: **BASELINE_TIMETABLE_ROBUST_AT_10**.

The unchanged baseline timetable remains feasible at 10 minutes, using one additional vehicle (19 → 20). Reoptimization selects the same timetable and therefore introduces no passenger-quality or departure-time cost.

## Authority and determinism

Baseline is 70 / 5 / 20; endpoints are 04:55–21:00 in both directions; totals are 78 outbound and 78 inbound. Case C replayed twice with byte-equivalent deterministic signatures.

## Selected pairs

Case A: `b6712e5e1a552fa75fbfe042454b7d0568e4cd06b265b7d38d8760358dfb4063`.
Case C: `b6712e5e1a552fa75fbfe042454b7d0568e4cd06b265b7d38d8760358dfb4063`.

## A → C quality and ServiceRegimes

Fleet delta +1; expected-wait delta +0.000000000 minutes; mismatch delta +0.000000000; regime-count delta +0. Total/max excess terminal wait changes from 4283 / 88 to 4391 / 83 minutes.

Outbound headways remain [16, 10, 14, 10, 15, 8, 14, 15]; trip counts remain [5, 9, 13, 9, 16, 11, 6, 9]. Inbound headways remain [16, 9, 14, 10, 15, 9, 15]; trip counts remain [5, 10, 13, 9, 16, 10, 15]. No boundaries, tails, merges, or splits changed.

## A → C departure movement

0 of 156 departures changed (0.00%). Total absolute shift is 0 minutes; mean 0.000, median 0.000, maximum 0 minutes.

| Direction | Sequence | A | C | Absolute shift (min) |
| --- | ---: | --- | --- | ---: |

## Fleet and search diagnostics

A/B/C fleet requirements are 19 / 20 / 20; minimum connection layovers are 5 / 10 / 10 minutes. Median layovers are 37 / 41.5 / 41.5 minutes.

Case C generated 8463 states, evaluated 24, pruned 7291, retained 115 Pareto pairs, executed 24 fleet-feedback expansions, evaluated 2 response anchors, and evaluated 13 response descendants.

## Guards

No default authority, runtime, fleet ceiling, trip total, endpoint, budget, queue, Pareto, compiler, fleet-validator, or settlement change was made. No production source was changed.
