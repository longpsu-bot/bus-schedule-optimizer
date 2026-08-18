"""Reviewable Contract V1 artifacts for the V3 two-stage Scenario C workflow."""

from __future__ import annotations

from .solver_models import ScheduleSolutionV1
from .two_stage_acceptance import TWO_STAGE_QUALITY_VECTOR_NAMES_V1
from .two_stage_models import (
    FinalAcceptanceStateV1,
    TripAllocationPlanV1,
    TwoStageScenarioCResultV1,
)


def _minute_hhmmss(minute: int) -> str:
    hour, minute_of_hour = divmod(minute, 60)
    return f"{hour:02d}:{minute_of_hour:02d}:00"


def _second_hhmmss(second: int) -> str:
    hour, remainder = divmod(second, 3600)
    minute, second_of_minute = divmod(remainder, 60)
    return f"{hour:02d}:{minute:02d}:{second_of_minute:02d}"


def trip_allocation_plan_to_contract_dict_v1(
    plan: TripAllocationPlanV1,
) -> dict[str, object]:
    return {
        "allocation_plan_profile": plan.allocation_plan_profile,
        "allocation_fingerprint": plan.allocation_fingerprint,
        "source_b_fingerprint": plan.source_b_fingerprint,
        "demand_authority_fingerprint": plan.demand_authority_fingerprint,
        "optimization_mode": plan.optimization_mode.value,
        "demand_authority_mode": plan.demand_authority_mode.value,
        "uniform_regime_profile": plan.uniform_regime_profile,
        "final_tail_policy_fingerprint": plan.final_tail_policy_fingerprint,
        "solve_status": plan.solve_status.value,
        "rank": plan.rank,
        "solve_duration_seconds": plan.solve_duration_seconds,
        "total_trips": plan.total_trips,
        "trips_by_direction": {
            direction.value: count for direction, count in plan.trips_by_direction
        },
        "objective_vector": list(plan.objective_vector),
        "necessary_feasibility": {
            "diagnostic_profile": plan.necessary_feasibility.diagnostic_profile,
            "diagnostic_fingerprint": plan.necessary_feasibility.diagnostic_fingerprint,
            "allocation_candidate_fingerprint": (
                plan.necessary_feasibility.allocation_candidate_fingerprint
            ),
            "passed": plan.necessary_feasibility.passed,
            "constraint_families": [
                item.value for item in plan.necessary_feasibility.constraint_families
            ],
            "fleet_lower_bound": plan.necessary_feasibility.fleet_lower_bound,
            "explanation": plan.necessary_feasibility.explanation,
        },
        "final_service_sentinels": [
            {
                "direction": item.direction.value,
                "source_b_trip_id": item.source_b_trip_id,
                "departure_time": _minute_hhmmss(item.departure_minute),
                "boundary_semantics": item.boundary_semantics.value,
            }
            for item in plan.final_service_sentinels
        ],
        "allocation_by_demand_interval": [
            {
                "block_id": block.block_id,
                "direction": block.direction.value,
                "start_time": _minute_hhmmss(block.start_minute),
                "end_time": _minute_hhmmss(block.end_minute),
                "trip_count": block.trip_count,
                "directional_trip_counts": {
                    direction.value: count for direction, count in block.directional_trip_counts
                },
                "source_b_trip_count": block.source_b_trip_count,
                "protected_minimum_trip_count": block.protected_minimum_trip_count,
                "observed_passengers": block.observed_passengers,
                "required_trips_90": block.required_trips_90,
                "required_trips_85": block.required_trips_85,
            }
            for block in plan.allocation_blocks
        ],
        "proposed_service_regimes": [
            {
                "regime_id": regime.regime_id,
                "direction": regime.direction.value,
                "covered_demand_block_ids": list(regime.covered_demand_block_ids),
                "trip_count": regime.trip_count,
                "permitted_start_window": [
                    _minute_hhmmss(regime.permitted_start_window[0]),
                    _minute_hhmmss(regime.permitted_start_window[1]),
                ],
                "permitted_end_window": [
                    _minute_hhmmss(regime.permitted_end_window[0]),
                    _minute_hhmmss(regime.permitted_end_window[1]),
                ],
                "planned_start": _minute_hhmmss(regime.planned_start_minute),
                "planned_end": _minute_hhmmss(regime.planned_end_minute),
                "uniform_headway_minutes": regime.uniform_headway_minutes,
                "minimum_headway_minutes": regime.minimum_headway_minutes,
                "maximum_headway_minutes": regime.maximum_headway_minutes,
                "boundary_reason": regime.boundary_reason,
                "is_final_service_tail": regime.is_final_service_tail,
                "boundary_semantics": regime.boundary_semantics.value,
                "headway_measurement_status": (
                    "EXACT_UNIFORM_INTEGER_MINUTE"
                    if regime.measurable
                    else "SINGLE_TRIP_HEADWAY_NOT_MEASURABLE"
                ),
            }
            for regime in plan.proposed_regimes
        ],
    }


def _accepted_candidate_artifact(solution: ScheduleSolutionV1) -> dict[str, object]:
    def stock_event(item) -> dict[str, object]:
        return {
            "event_time": _second_hhmmss(item.event_time),
            "event_type": item.event_type,
            "trip_id": item.trip_id,
            "stock_before": item.stock_before,
            "stock_after": item.stock_after,
            "arriving_or_ready_vehicle_count": item.arriving_or_ready_vehicle_count,
            "departure_count": item.departure_count,
        }

    return {
        "solution_fingerprint": solution.solution_fingerprint,
        "solver_status": solution.solver_status.value,
        "required_fleet": solution.minimum_required_fleet,
        "available_fleet_limit": solution.available_fleet_limit,
        "recommended_initial_fleet": {
            "terminal_1": solution.recommended_initial_fleet_terminal_1,
            "terminal_2": solution.recommended_initial_fleet_terminal_2,
        },
        "final_service_regimes": [
            {
                "regime_id": regime.regime_id,
                "direction": regime.direction.value,
                "start_time": _second_hhmmss(regime.start_time),
                "end_time": _second_hhmmss(regime.end_time),
                "trip_count": regime.trip_count,
                "uniform_headway_minutes": (
                    regime.actual_headway_sequence[0] if regime.actual_headway_sequence else None
                ),
                "internal_headway_sequence": list(regime.actual_headway_sequence),
                "transition_headways": list(regime.transition_headways),
                "boundary_reason": regime.boundary_reason,
                "regularity_status": regime.regularity_status,
            }
            for regime in solution.c_headway_regimes
        ],
        "exact_timetable_and_b_to_c_shifts": [
            {
                "c_trip_id": trip.c_trip_id,
                "source_b_trip_id": trip.source_b_trip_id,
                "direction": trip.direction.value,
                "departure_terminal": trip.departure_terminal.value,
                "b_departure_time": _second_hhmmss(trip.b_departure_time),
                "c_departure_time": _second_hhmmss(trip.c_departure_time),
                "shift_minutes": trip.shift_minutes,
                "headway_regime_id": trip.headway_regime_id,
                "vehicle_assignment": trip.vehicle_assignment,
                "change_reason": trip.change_reason,
            }
            for trip in solution.c_exact_timetable
        ],
        "fleet_assignment": [
            {
                "vehicle_id": assignment.vehicle_id,
                "c_trip_id": assignment.c_trip_id,
                "departure_terminal": assignment.departure_terminal.value,
                "arrival_terminal": assignment.arrival_terminal.value,
                "departure_time": _second_hhmmss(assignment.departure_time),
                "arrival_time": _second_hhmmss(assignment.arrival_time),
                "ready_time": _second_hhmmss(assignment.ready_time),
            }
            for assignment in solution.fleet_assignment
        ],
        "terminal_stock": {
            "terminal_1": [stock_event(item) for item in solution.vehicle_stock_profile_terminal_1],
            "terminal_2": [stock_event(item) for item in solution.vehicle_stock_profile_terminal_2],
        },
    }


def two_stage_result_to_contract_dict_v1(
    result: TwoStageScenarioCResultV1,
) -> dict[str, object]:
    solution = result.candidate_outcome.solution if result.candidate_outcome is not None else None
    return {
        "contract_version": "1.0.0",
        "result_profile": "scenario_c_two_stage_result_v1",
        "result_fingerprint": result.result_fingerprint,
        "final_acceptance_state": result.final_acceptance_state.value,
        "recommended_scenario_c": (
            result.final_acceptance_state == FinalAcceptanceStateV1.FINAL_RECOMMENDED
        ),
        "native_solver_status": (
            result.native_solver_status.value if result.native_solver_status is not None else None
        ),
        "stage_1_allocation": (
            trip_allocation_plan_to_contract_dict_v1(result.allocation_plan)
            if result.allocation_plan is not None
            else None
        ),
        "accepted_candidate": (
            _accepted_candidate_artifact(solution) if solution is not None else None
        ),
        "final_service_tail_metrics": [
            {
                "direction": item.direction.value,
                "final_tail_start": _second_hhmmss(item.final_tail_start),
                "final_tail_end": _second_hhmmss(item.final_tail_end),
                "final_tail_span_minutes": item.final_tail_span_minutes,
                "final_tail_trip_count": item.final_tail_trip_count,
                "final_tail_uniform_headway_minutes": (item.final_tail_uniform_headway_minutes),
                "minutes_from_penultimate_trip_to_last_departure": (
                    item.minutes_from_penultimate_trip_to_last_departure
                ),
            }
            for item in result.final_tail_metrics
        ],
        "demand_service_comparison": {
            "metric_names": list(TWO_STAGE_QUALITY_VECTOR_NAMES_V1),
            "scenario_b": list(result.b_quality_vector),
            "scenario_c": (
                list(result.c_quality_vector) if result.c_quality_vector is not None else None
            ),
        },
        "solve_diagnostics": {
            "stage_1_candidate_count": result.diagnostics.stage_1_candidate_count,
            "stage_1_admissible_allocation_count": (
                result.diagnostics.stage_1_admissible_allocation_count
            ),
            "stage_1_necessary_feasibility_pruned_count": (
                result.diagnostics.stage_1_necessary_feasibility_pruned_count
            ),
            "stage_2_allocation_attempt_count": (
                result.diagnostics.stage_2_allocation_attempt_count
            ),
            "stage_2_variable_count": result.diagnostics.stage_2_variable_count,
            "stage_2_constraint_count": result.diagnostics.stage_2_constraint_count,
            "maximum_stage_2_departure_domain_width_minutes": (
                result.diagnostics.maximum_stage_2_departure_domain_width_minutes
            ),
            "full_service_window_domain_count": (
                result.diagnostics.full_service_window_domain_count
            ),
            "regime_count_by_direction": {
                direction.value: count
                for direction, count in result.diagnostics.regime_count_by_direction
            },
            "solve_duration_stage_1": result.diagnostics.solve_duration_stage_1,
            "solve_duration_stage_2": result.diagnostics.solve_duration_stage_2,
            "total_solve_duration": result.diagnostics.total_solve_duration,
            "total_budget_seconds": result.diagnostics.total_budget_seconds,
            "budget_exhausted": result.diagnostics.budget_exhausted,
            "stage_2_infeasibility_diagnostics": [
                {
                    "allocation_plan_fingerprint": item.allocation_plan_fingerprint,
                    "native_solver_status": item.native_solver_status.value,
                    "constraint_families": [family.value for family in item.constraint_families],
                    "explanation": item.explanation,
                    "diagnostic_profile": item.diagnostic_profile,
                    "diagnostic_fingerprint": item.diagnostic_fingerprint,
                }
                for item in result.diagnostics.stage_2_infeasibility_diagnostics
            ],
        },
        "explanations": list(result.explanations),
        "limitations": list(result.limitations),
    }


__all__ = [
    "trip_allocation_plan_to_contract_dict_v1",
    "two_stage_result_to_contract_dict_v1",
]
