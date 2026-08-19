"""Run the bounded-phase V3 review with matching Stage 1 necessary-feasibility semantics.

This wrapper fixes an inconsistency discovered by the first real MST 6 phase-review run:
regime construction and Stage 2 used bounded +/-1 block phase deviation, while the cheap
Stage 1 necessary-feasibility pre-check still required exact 30-minute block membership.
The production V3 runner remains unchanged.
"""

from __future__ import annotations

from collections import defaultdict

import run_v3_two_stage_phase_review as base

from bus_schedule_engine.contracts_v1 import two_stage_allocator as allocator


def _planned_departures(regime) -> tuple[int, ...]:
    if regime.trip_count == 1:
        return (regime.planned_start_minute,)
    assert regime.uniform_headway_minutes is not None
    return tuple(
        regime.planned_start_minute + index * regime.uniform_headway_minutes
        for index in range(regime.trip_count)
    )


def _bounded_phase_necessary_feasibility(
    problem,
    allocation,
    allocation_blocks,
    regimes,
    final_service_sentinels,
    policy,
):
    """Apply the same bounded-phase semantics as the opt-in review runner.

    This remains a cheap necessary check: it verifies the Stage 1 planned arithmetic-progression
    witness, local/cumulative block phase bounds, B-anchor domains, and the existing safe fleet
    lower bound. It does not replace the exact Stage 2 CP-SAT proof.
    """

    candidate_fingerprint = allocator._allocation_candidate_fingerprint(problem, allocation, policy)
    source_by_id = {item.trip_id: item for item in problem.scenario_b.exact_timetable}
    source_ids_by_regime = allocator._source_ids_by_regime(problem, regimes)
    failures: set[allocator.Stage2ConstraintFamilyV1] = set()
    represented_by_regime: dict[str, tuple[int, ...]] = {}

    if not source_ids_by_regime:
        failures.add(allocator.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP)

    for regime in regimes:
        source_ids = source_ids_by_regime.get(regime.regime_id, ())
        departures = _planned_departures(regime)
        if len(source_ids) != regime.trip_count or len(departures) != regime.trip_count:
            failures.add(allocator.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP)
            continue

        if departures[0] != regime.planned_start_minute or departures[-1] != regime.planned_end_minute:
            failures.update(
                {
                    allocator.Stage2ConstraintFamilyV1.UNIFORM_HEADWAY,
                    allocator.Stage2ConstraintFamilyV1.REGIME_BOUNDARIES,
                }
            )
            continue

        for source_id, minute in zip(source_ids, departures, strict=True):
            source_minute = source_by_id[source_id].departure_time // 60
            if abs(minute - source_minute) > policy.absolute_max_shift_per_trip_minutes:
                failures.add(allocator.Stage2ConstraintFamilyV1.B_SHIFT_BOUND)

        represented_by_regime[regime.regime_id] = departures

    # Evaluate actual vs Stage 1 target counts under the same review rule used by regime building:
    # +/-1 in one 30-minute block, cumulative prefix deviation <=1, and zero final drift.
    rows_by_direction = defaultdict(list)
    for block in allocation_blocks:
        targets = dict(block.directional_trip_counts)
        for direction, expected in targets.items():
            actual = sum(
                block.start_minute <= minute < block.end_minute
                for regime in regimes
                if regime.direction == direction
                for minute in represented_by_regime.get(regime.regime_id, ())
            )
            rows_by_direction[direction].append((block, expected, actual))
            if abs(actual - expected) > base._PHASE_DEVIATION_PER_BLOCK:
                failures.add(allocator.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP)
            if block.observed_passengers > 0 and expected > 0 and actual == 0:
                failures.add(allocator.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP)

    for direction, rows in rows_by_direction.items():
        del direction
        cumulative_actual = 0
        cumulative_target = 0
        for _block, expected, actual in sorted(
            rows,
            key=lambda item: (item[0].start_minute, item[0].end_minute, item[0].block_id),
        ):
            cumulative_actual += actual
            cumulative_target += expected
            if abs(cumulative_actual - cumulative_target) > base._PHASE_DEVIATION_CUMULATIVE:
                failures.add(allocator.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP)
        if cumulative_actual != cumulative_target:
            failures.add(allocator.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP)

    domains, domain_failures = allocator._necessary_departure_domains(
        problem,
        regimes,
        final_service_sentinels,
        policy,
    )
    failures.update(domain_failures)

    fleet_lower_bound = None
    if len(domains) == problem.scenario_b.total_daily_trips:
        fleet_lower_bound = allocator._fleet_lower_bound(problem, domains)
        if fleet_lower_bound > problem.scenario_b.available_fleet_limit:
            failures.add(allocator.Stage2ConstraintFamilyV1.FLEET)

    passed = not failures
    if passed:
        explanation = (
            "Phase-review Stage 1 plan passed bounded block-phase, B-anchor, final-tail, "
            f"and safe fleet lower-bound checks (fleet lower bound {fleet_lower_bound})."
        )
    else:
        explanation = (
            "Phase-review Stage 1 plan failed cheap necessary Stage 2 checks for: "
            + ", ".join(item.value for item in sorted(failures, key=lambda item: item.value))
            + "."
        )

    return allocator.finalize_stage_1_necessary_feasibility(
        allocator.Stage1NecessaryFeasibilityResultV1(
            allocation_candidate_fingerprint=candidate_fingerprint,
            passed=passed,
            constraint_families=tuple(sorted(failures, key=lambda item: item.value)),
            fleet_lower_bound=fleet_lower_bound,
            explanation=explanation,
        )
    )


allocator.evaluate_stage_1_necessary_feasibility_v1 = _bounded_phase_necessary_feasibility


if __name__ == "__main__":
    raise SystemExit(base.main())
