"""Independent V3 comparison and product-final acceptance policy."""

from __future__ import annotations

from collections import defaultdict

from .models import ContractDirection
from .solver_models import GenerationResultStatus, ScheduleGenerationContextV1
from .solver_orchestration import run_schedule_solver_v1
from .two_stage_models import (
    FinalAcceptanceStateV1,
    TwoStageScenarioCResultV1,
    finalize_two_stage_result,
)
from .two_stage_solver import OrToolsCpSatTwoStageUniformSolver

TWO_STAGE_QUALITY_VECTOR_NAMES_V1 = (
    "positive_demand_no_service_blocks",
    "critical_shortage_trips",
    "planning_shortage_trips",
    "demand_allocation_error",
    "maximum_positive_demand_service_gap_minutes",
    "total_internal_headway_variation_minutes",
    "maximum_regime_transition_jump_minutes",
    "shifted_trip_count",
    "total_absolute_shift_minutes",
    "maximum_absolute_shift_minutes",
)


def classify_two_stage_final_acceptance_v1(
    b_quality_vector: tuple[int, ...],
    c_quality_vector: tuple[int, ...],
) -> FinalAcceptanceStateV1:
    """Classify an independently valid candidate without using native proof status."""
    if len(b_quality_vector) != len(TWO_STAGE_QUALITY_VECTOR_NAMES_V1) or len(
        c_quality_vector
    ) != len(TWO_STAGE_QUALITY_VECTOR_NAMES_V1):
        raise ValueError("B and C quality vectors must use the complete V3 comparison profile")
    if any(
        c_value > b_value
        for b_value, c_value in zip(
            b_quality_vector[:3],
            c_quality_vector[:3],
            strict=True,
        )
    ):
        return FinalAcceptanceStateV1.VALID_CANDIDATE_NOT_FINAL
    if c_quality_vector < b_quality_vector:
        return FinalAcceptanceStateV1.FINAL_RECOMMENDED
    return FinalAcceptanceStateV1.KEEP_SCENARIO_B


def _block_count_for_b(context: ScheduleGenerationContextV1, block) -> int:
    return sum(
        block.start_time <= trip.departure_time < block.end_time
        and (block.direction == ContractDirection.COMBINED or trip.direction == block.direction)
        for trip in context.problem.scenario_b.exact_timetable
    )


def _block_count_for_c(solution, block) -> int:
    return sum(
        block.start_time <= trip.c_departure_time < block.end_time
        and (block.direction == ContractDirection.COMBINED or trip.direction == block.direction)
        for trip in solution.c_exact_timetable
    )


def _service_gap_metrics(
    context: ScheduleGenerationContextV1,
    departures: tuple[tuple[ContractDirection, int], ...],
) -> int:
    maximum = 0
    for block in context.problem.analysis_blocks:
        if block.observed_passengers <= 0:
            continue
        directions = (
            (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
            if block.direction == ContractDirection.COMBINED
            else (block.direction,)
        )
        for direction in directions:
            members = sorted(
                minute
                for candidate_direction, minute in departures
                if candidate_direction == direction
                and block.start_time // 60 <= minute < block.end_time // 60
            )
            if not members:
                maximum = max(maximum, block.duration_minutes)
                continue
            gaps = (
                members[0] - block.start_time // 60,
                *(later - earlier for earlier, later in zip(members, members[1:], strict=False)),
                block.end_time // 60 - members[-1],
            )
            maximum = max(maximum, *gaps)
    return maximum


def _headway_variation(
    departures: tuple[tuple[ContractDirection, int], ...],
    regime_by_trip_index: tuple[str, ...] | None = None,
) -> tuple[int, int]:
    by_direction: dict[ContractDirection, list[tuple[int, str | None]]] = defaultdict(list)
    for index, (direction, minute) in enumerate(departures):
        regime = regime_by_trip_index[index] if regime_by_trip_index is not None else None
        by_direction[direction].append((minute, regime))
    total_internal = 0
    maximum_transition = 0
    for rows in by_direction.values():
        ordered = sorted(rows)
        gaps = tuple(
            (later[0] - earlier[0], earlier[1], later[1])
            for earlier, later in zip(ordered, ordered[1:], strict=False)
        )
        previous: tuple[int, str | None, str | None] | None = None
        for gap in gaps:
            if previous is not None:
                change = abs(gap[0] - previous[0])
                same_current_regime = (
                    regime_by_trip_index is not None
                    and previous[1] == previous[2] == gap[1] == gap[2]
                )
                if same_current_regime:
                    total_internal += change
                else:
                    maximum_transition = max(maximum_transition, change)
            previous = gap
    return total_internal, maximum_transition


def _quality_vector(
    context: ScheduleGenerationContextV1,
    *,
    solution=None,
) -> tuple[int, ...]:
    no_service = 0
    critical_shortage = 0
    planning_shortage = 0
    allocation_error = 0
    requirements = {item.block_id: item for item in context.problem.block_requirements}
    for block in context.problem.analysis_blocks:
        count = (
            _block_count_for_b(context, block)
            if solution is None
            else _block_count_for_c(solution, block)
        )
        requirement = requirements[block.block_id]
        no_service += int(block.observed_passengers > 0 and count == 0)
        critical_shortage += max(0, requirement.required_trips_90 - count)
        planning_shortage += max(0, requirement.required_trips_85 - count)
        allocation_error += abs(count - requirement.required_trips_85)

    if solution is None:
        departure_rows = tuple(
            (trip.direction, trip.departure_time // 60)
            for trip in context.problem.scenario_b.exact_timetable
        )
        regimes = None
        shifted_count = total_shift = maximum_shift = 0
    else:
        departure_rows = tuple(
            (trip.direction, trip.c_departure_time // 60) for trip in solution.c_exact_timetable
        )
        regimes = tuple(trip.headway_regime_id for trip in solution.c_exact_timetable)
        shifted_count = solution.shifted_trip_count
        total_shift = round(solution.total_shift_minutes)
        maximum_shift = round(solution.maximum_shift_minutes)
    max_gap = _service_gap_metrics(context, departure_rows)
    internal_variation, transition_jump = _headway_variation(departure_rows, regimes)
    return (
        no_service,
        critical_shortage,
        planning_shortage,
        allocation_error,
        max_gap,
        internal_variation,
        transition_jump,
        shifted_count,
        total_shift,
        maximum_shift,
    )


def run_two_stage_scenario_c_v1(
    context: ScheduleGenerationContextV1,
    solver: OrToolsCpSatTwoStageUniformSolver,
) -> TwoStageScenarioCResultV1:
    """Run both stages once, validate independently, compare with B, then classify finality."""
    outcome = run_schedule_solver_v1(context, solver)
    detailed = solver.last_detailed_run
    if detailed is None:  # pragma: no cover - adapter guarantees a detailed result
        raise AssertionError("two-stage adapter did not preserve its detailed run")
    b_vector = _quality_vector(context)
    if (
        outcome.result_status != GenerationResultStatus.SOLUTION_ACCEPTED
        or outcome.solution is None
        or detailed.selected_allocation_plan is None
    ):
        state = FinalAcceptanceStateV1.NO_FINAL_C_WITHIN_SOLVE_BUDGET
        c_vector = None
        explanations = (
            *outcome.explanations,
            "No independently accepted V3 candidate reached final comparison.",
        )
    else:
        c_vector = _quality_vector(context, solution=outcome.solution)
        state = classify_two_stage_final_acceptance_v1(b_vector, c_vector)
        if state == FinalAcceptanceStateV1.VALID_CANDIDATE_NOT_FINAL:
            explanations = (
                *outcome.explanations,
                "The candidate is domain-valid but deteriorates high-priority demand protection.",
            )
        elif state == FinalAcceptanceStateV1.FINAL_RECOMMENDED:
            explanations = (
                *outcome.explanations,
                "Independent V3 validation passed and the solver-neutral quality vector is "
                "lexicographically better than Scenario B without demand-protection deterioration.",
            )
        else:
            state = FinalAcceptanceStateV1.KEEP_SCENARIO_B
            explanations = (
                *outcome.explanations,
                "The accepted candidate is not materially better than Scenario B under the "
                "approved V3 comparison order.",
            )
    provisional = TwoStageScenarioCResultV1(
        final_acceptance_state=state,
        native_solver_status=outcome.solver_status,
        allocation_plan=detailed.selected_allocation_plan,
        candidate_outcome=outcome,
        final_tail_metrics=detailed.final_tail_metrics,
        diagnostics=detailed.diagnostics,
        b_quality_vector=b_vector,
        c_quality_vector=c_vector,
        explanations=tuple(explanations),
        limitations=outcome.limitations,
        result_fingerprint="",
    )
    return finalize_two_stage_result(provisional)


__all__ = [
    "TWO_STAGE_QUALITY_VECTOR_NAMES_V1",
    "classify_two_stage_final_acceptance_v1",
    "run_two_stage_scenario_c_v1",
]
