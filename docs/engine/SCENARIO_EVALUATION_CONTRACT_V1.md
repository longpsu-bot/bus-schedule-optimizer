# Scenario Evaluation Contract V1

The normative rules are [Engine Contract V1 §§5–6 and §11](ENGINE_CONTRACT_V1.md). This document defines evaluation sequencing and evidence expectations.

## Evaluation sequence

1. Validate input shape and required data.
2. Validate declared parameters against the exact timetable.
3. Calculate independent fleet need and technical feasibility.
4. Evaluate timetable quality.
5. If demand evidence is sufficient, evaluate demand suitability.
6. Derive the B disposition from the separate dimensions.
7. Decide whether C generation is allowed.

A later stage cannot erase an earlier failure. A good demand fit does not make an infeasible timetable technically feasible.

## Dimension result shape

Each dimension returns `status`, `issues`, `evidence`, `explanation`, and `confidence`. Issue entries have a stable code, severity, entity/block references, human-readable message, and suggested corrective action. `NOT_EVALUATED` is distinct from `PASS`.

## B disposition decision table

| Inputs/parameters | Technical | Demand | Disposition | C action |
|---|---|---|---|---|
| valid/consistent | feasible | suitable | `B_TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE` | normally no optimization; explain |
| valid/consistent | feasible | unsuitable | `B_TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE` | may generate C |
| valid/consistent | infeasible timetable | any known result | `B_TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION` | may search for feasible C under locks |
| fixed parameters infeasible | infeasible | any | `B_PARAMETERS_INFEASIBLE` | return `NO_FEASIBLE_C_WITH_B_PARAMETERS` |
| demand evidence insufficient | feasible or not evaluable | insufficient | `B_INSUFFICIENT_DATA` | no demand-optimized C |

Parameter infeasibility requires evidence about the locked parameter set, not merely failure of the submitted exact timetable. Examples include impossible trip/endpoint requirements or a proven fleet/turnaround contradiction within the operating span.

## Timetable quality evidence

Report per-direction consecutive headways, maximum gap, coefficient of variation where meaningful, short-long-short patterns, first/final coverage, regime count, transitions, and exceptions. Use chronological service-day ordering. Quality thresholds are configuration with provenance; they are not solver proof.

## Demand suitability evidence

For every authoritative block, return demand, capacity, LF, required trips at 85% and 90%, shortage/backlog, service-gap evidence, status, and confidence. Apply the one-sided interpretation in Contract V1 §6. Low load may generate a review note but not a trip-reduction recommendation.

## C validation

C is validated with the same B parameters and independent rules. In addition, compare B/C locked values, total/directional counts, first/last trips, source mapping, planned/actual block counts, fleet mode, and fingerprints. A solver result rejected by this validator is not exposed as `ScheduleSolutionV1`.

## Explanations

Explanations state: what was evaluated; which observed evidence was used; what changed from B to C; which high-priority objective improved; which residual shortages remain; solver proof status; and limitations. They do not claim forecasted ridership response in `static` mode.
