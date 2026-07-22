# OR-Tools CP-SAT Target Design V1

This is a future implementation design, not solver code. Hard rules and objective priority come from [Engine Contract V1 §§3–4 and §§8–12](ENGINE_CONTRACT_V1.md), with top-level result behavior defined by [Schedule Generation Outcome Contract V1](RESULT_ENVELOPE_CONTRACT_V1.md).

## Why CP-SAT

The target problem combines integer departure minutes, integer block allocations, Boolean change/exception indicators, fixed trip counts, fleet/location constraints, turnaround, and lexicographic objectives. CP-SAT supports integer/Boolean modeling, reified constraints, hints, staged solves, and proof statuses appropriate to that structure.

## Adapter boundary

```text
ScheduleSolver.solve(problem: ScheduleProblemV1) -> ScheduleSolutionCandidate
```

`OrToolsCpSatScheduleSolver` will translate only normalized solver-neutral values. It returns raw variable values, native solver status, stage objectives, timings, counts, and logs. `DomainSolutionValidator` separately reconstructs trips/fleet chains and decides conformance. The application then wraps the result in `ScheduleGenerationOutcomeV1`; an accepted `ScheduleSolutionV1` is created only after domain validation succeeds.

## Proposed decision layers

1. **Block allocation:** integer `trips_in_block[direction, block]` obeying total/directional locks and minimum service.
2. **Exact times:** ordered integer `departure_time[direction, sequence]` within locked windows, with first/last equality.
3. **Regularity:** integer headways plus Boolean change/transition/exception indicators and regime membership.
4. **Fleet/terminal feasibility:** terminal balance or interval/circuit representation proving vehicle availability and turnaround.

Do not begin with a `vehicle × trip × minute` Boolean grid. Prefer O(trips + blocks + candidate connections) variables and use a time-indexed assignment model only if benchmarks show that more compact flow/circuit alternatives cannot express future requirements.

## Candidate variables

- `trips_in_block[d,b]` — integer planned allocation.
- `departure_time[d,i]` — exact service-day minute for ordered trip sequence.
- `headway[d,i] = departure_time[d,i] - departure_time[d,i-1]`.
- `headway_change[d,i]`, `transition[d,i]`, `exception[d,i]` — Boolean indicators.
- `regime_id[d,i]` or boundary indicators — regime segmentation.
- `shift_abs[i]` and `shifted[i]` — absolute departure shift from B and nonzero indicator.
- `overload_85[d,b]`, `overload_90[d,b]`, `backlog[d,b]` — non-negative one-sided shortage variables.
- `no_service[d,b]`, `large_gap[d,i]` — Boolean/positive gap variables.
- `actual_trips_in_block[d,b]` — derived count from exact times for reconciliation.
- `initial_fleet_terminal_1`, `initial_fleet_terminal_2` — solver-determined or constrained starting positions.
- terminal arrival/ready events and vehicle-balance variables, or feasible connection-arc variables.

Multiplication/division involving LF should be converted to scaled integer capacity inequalities. Passenger counts/rates require a declared rounding scale and tolerance.

## Hard constraints

- total C trips equal B; direction totals equal B in `fixed_by_direction`;
- `total_only` only when authorization/confidence preconditions are already validated;
- `minimum_required_fleet <= available_fleet_limit` and any explicit fleet/positioning mode;
- initial terminal counts satisfy fixed/bounded rules when configured;
- terminal stock remains non-negative on the continuous event timeline;
- departure windows and exact first/last departures;
- strict chronological order and preserved B sequence unless an approved rule allows reorder;
- runtime, arrival terminal, and minimum turnaround;
- no deadhead/repositioning unless a future contract adds it;
- minimum service and protected final service;
- block allocation sum and exact-time membership reconciliation;
- planned/actual block counts equal;
- every C sequence element maps to exactly one B trip.

### Fleet formulation candidates

Evaluate two formulations in Stage 4:

1. **Connection graph/path cover:** candidate arc exists only when terminal and ready time permit; selected paths represent vehicle chains, with fleet bounded by path starts.
2. **Terminal event balance/reservoir:** arrivals become availability events after turnaround; cumulative departures cannot exceed solver-determined initial stock plus ready arrivals at each terminal.

The chosen formulation must independently report minimum required fleet and recommended initial positioning. If approved or available fleet exceeds the minimum, idle/reserve vehicles remain permitted; no formulation may distort service merely to make every vehicle move.

## Lexicographic solve stages

Run staged solves or a mathematically safe lexicographic encoding:

1. find technical feasibility;
2. minimize demand blocks with no service;
3. minimize critical blocks and overload above 90%;
4. minimize overload above 85%;
5. minimize large service gaps;
6. improve sustained-demand allocation;
7. minimize exceptional/irregular headways;
8. minimize regime changes/transitions;
9. preserve stable B sections;
10. minimize shifted trips, total shift, then maximum shift;
11. use minimum fleet only as a late tie-breaker after service-quality objectives are fixed.

Each stage fixes the best proven prior-stage value before proceeding, or uses bounds that cannot trade away a higher priority. There is no symmetric distance-to-85 objective.

## Hints and decomposition

B is a natural exact-time hint. The reviewed heuristic may provide an additional feasible hint through the same adapter interface. A practical first implementation may solve block allocation, then exact times/fleet, then regularity while iterating only when exact-time reconciliation fails. Decomposition must not present a Level 1 plan as feasible until Level 2 validates it.

## Status and outcome mapping

CP-SAT native statuses remain `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `MODEL_INVALID`, and `UNKNOWN`. Record time limit, worker count, random seed, deterministic-time settings, best bound, and stage objective values. `FEASIBLE` is never relabeled optimal.

The engine-level `execution_status` belongs to `ScheduleGenerationOutcomeV1`:

- `NOT_RUN` means no solver was invoked and therefore native `solver_status` is null;
- `COMPLETED` means a solver invocation returned a native status.

Only a native `OPTIMAL` or `FEASIBLE` candidate that passes independent domain validation may populate `ScheduleSolutionV1`. Native `INFEASIBLE` maps to `NO_FEASIBLE_C_WITH_B_PARAMETERS` only for the reviewed encoded problem. Native `UNKNOWN` maps to `C_NOT_FOUND_WITHIN_SOLVE_LIMIT` and does not prove infeasibility. Native `MODEL_INVALID` maps to `C_NOT_GENERATED_MODEL_INVALID` and indicates a model/configuration defect. A candidate rejected by the domain validator remains non-authoritative and may appear only as diagnostic metadata in the outcome envelope.

## Performance and benchmark targets

Targets are measured on the approved reference machine and are gates, not guarantees:

| Daily trips | First feasible | Total staged solve | Peak memory | Intended gate |
|---:|---:|---:|---|
| 40–80 | ≤ 1 s | ≤ 5 s | ≤ 512 MB | interactive baseline |
| 150 | ≤ 5 s | ≤ 30 s | ≤ 1 GB | normal large route |
| 300 | ≤ 15 s | ≤ 120 s | ≤ 2 GB | large-case acceptance |
| 400–500 | ≤ 60 s | ≤ 300 s | ≤ 4 GB | stress, feasible result acceptable |

Collect model build time, variables by type, constraints by family, first-feasible time, total time, native status, outcome status, per-stage objective/bound, memory, branches/conflicts, and solution/outcome fingerprints. Model build SHOULD stay below 20% of the tier's total budget.

## Determinism

For an optimal result, repeated runs with identical input/configuration must produce the same objective vector and a canonical tie-broken fingerprint. For time-limited feasible results, record all solver controls; run a deterministic single-worker benchmark and a production-worker benchmark separately. Tie-break on ordered departure times/shift vector only after business objectives.

## Non-goals for the first adapter

Mixed fleets, multi-route interlining, deadhead, driver duties, depot pull-in/out, maintenance, and calibrated demand elasticity remain outside V1 unless separately contracted.
