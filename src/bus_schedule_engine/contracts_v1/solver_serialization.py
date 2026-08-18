from __future__ import annotations

from bus_schedule_engine.time_utils import format_hhmm

from .evaluation_serialization import block_supply_plan_to_contract_dict
from .solver_models import (
    OperatingParameterLockV1,
    ScheduleGenerationOutcomeV1,
    ScheduleSolutionV1,
    SolutionHeadwayRegimeV1,
    SolutionTripV1,
    StockProfileEventV1,
)


def _lock_to_dict(lock: OperatingParameterLockV1) -> dict[str, object]:
    return {
        "field": lock.field,
        "value": lock.value,
        "locked": lock.locked,
        "source_fingerprint": lock.source_fingerprint,
        "authorized_exception": lock.authorized_exception,
    }


def _regime_to_dict(regime: SolutionHeadwayRegimeV1) -> dict[str, object]:
    return {
        "regime_id": regime.regime_id,
        "direction": regime.direction.value,
        "start_time": format_hhmm(regime.start_time),
        "end_time": format_hhmm(regime.end_time),
        "covered_analysis_blocks": list(regime.covered_analysis_blocks),
        "trip_count": regime.trip_count,
        "target_service_rate": regime.target_service_rate,
        "target_headway": regime.target_headway,
        "actual_headway_sequence": list(regime.actual_headway_sequence),
        "transition_headways": list(regime.transition_headways),
        "exceptional_headways": list(regime.exceptional_headways),
        "boundary_reason": regime.boundary_reason,
        "regularity_status": regime.regularity_status,
    }


def _trip_to_dict(trip: SolutionTripV1) -> dict[str, object]:
    return {
        "c_trip_id": trip.c_trip_id,
        "source_b_trip_id": trip.source_b_trip_id,
        "direction": trip.direction.value,
        "departure_terminal": trip.departure_terminal.value,
        "b_departure_time": format_hhmm(trip.b_departure_time),
        "c_departure_time": format_hhmm(trip.c_departure_time),
        "shift_minutes": trip.shift_minutes,
        "previous_b_headway": trip.previous_b_headway,
        "previous_c_headway": trip.previous_c_headway,
        "headway_regime_id": trip.headway_regime_id,
        "change_reason": trip.change_reason,
        "vehicle_assignment": trip.vehicle_assignment,
    }


def _stock_event_to_dict(event: StockProfileEventV1) -> dict[str, object]:
    return {
        "event_time": format_hhmm(event.event_time),
        "event_type": event.event_type,
        "trip_id": event.trip_id,
        "stock_before": event.stock_before,
        "stock_after": event.stock_after,
        "arriving_or_ready_vehicle_count": event.arriving_or_ready_vehicle_count,
        "departure_count": event.departure_count,
    }


def schedule_solution_to_contract_dict(
    solution: ScheduleSolutionV1,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "contract_version": solution.contract_version,
        "solver_status": solution.solver_status.value,
        "solver_adapter": solution.solver_adapter,
        "solve_duration_seconds": solution.solve_duration_seconds,
        "solution_fingerprint": solution.solution_fingerprint,
        "source_b_fingerprint": solution.source_b_fingerprint,
        "operating_parameter_locks": [
            _lock_to_dict(item) for item in solution.operating_parameter_locks
        ],
        "c_block_supply_plan": [
            block_supply_plan_to_contract_dict(item) for item in solution.c_block_supply_plan
        ],
        "c_headway_regimes": [_regime_to_dict(item) for item in solution.c_headway_regimes],
        "c_exact_timetable": [_trip_to_dict(item) for item in solution.c_exact_timetable],
        "fleet_assignment": [
            {
                "vehicle_id": item.vehicle_id,
                "c_trip_id": item.c_trip_id,
                "departure_terminal": item.departure_terminal.value,
                "arrival_terminal": item.arrival_terminal.value,
                "departure_time": format_hhmm(item.departure_time),
                "arrival_time": format_hhmm(item.arrival_time),
                "ready_time": format_hhmm(item.ready_time),
            }
            for item in solution.fleet_assignment
        ],
        "available_fleet_limit": solution.available_fleet_limit,
        "approved_active_fleet": solution.approved_active_fleet,
        "minimum_required_fleet": solution.minimum_required_fleet,
        "recommended_initial_fleet_terminal_1": (solution.recommended_initial_fleet_terminal_1),
        "recommended_initial_fleet_terminal_2": (solution.recommended_initial_fleet_terminal_2),
        "initial_fleet_positioning_mode": (solution.initial_fleet_positioning_mode.value),
        "fleet_margin": solution.fleet_margin,
        "maximum_simultaneous_vehicle_use": (solution.maximum_simultaneous_vehicle_use),
        "vehicle_stock_profile_terminal_1": [
            _stock_event_to_dict(item) for item in solution.vehicle_stock_profile_terminal_1
        ],
        "vehicle_stock_profile_terminal_2": [
            _stock_event_to_dict(item) for item in solution.vehicle_stock_profile_terminal_2
        ],
        "fleet_feasibility_status": solution.fleet_feasibility_status,
        "block_evaluation": [
            {
                "block_id": item.block_id,
                "direction": item.direction.value,
                "load_factor": item.load_factor,
                "shortage": item.shortage,
                "status": item.status.value,
            }
            for item in solution.block_evaluation
        ],
        "residual_overload": solution.residual_overload,
        "shifted_trip_count": solution.shifted_trip_count,
        "total_shift_minutes": solution.total_shift_minutes,
        "maximum_shift_minutes": solution.maximum_shift_minutes,
        "status": solution.status.value,
        "explanations": list(solution.explanations),
        "limitations": list(solution.limitations),
    }
    if solution.protected_service_floor_enforcement_fingerprint is not None:
        payload["protected_service_floor_enforcement_fingerprint"] = (
            solution.protected_service_floor_enforcement_fingerprint
        )
        payload["protected_service_floor_validation_fingerprint"] = (
            solution.protected_service_floor_validation_fingerprint
        )
    if solution.allocation_plan_fingerprint is not None:
        payload.update(
            {
                "allocation_plan_fingerprint": solution.allocation_plan_fingerprint,
                "scenario_c_optimization_mode": (
                    solution.optimization_mode.value
                    if solution.optimization_mode is not None
                    else None
                ),
                "demand_allocation_authority_mode": (
                    solution.demand_allocation_authority_mode.value
                    if solution.demand_allocation_authority_mode is not None
                    else None
                ),
                "uniform_regime_policy_profile": solution.uniform_regime_policy_profile,
                "final_tail_policy_fingerprint": solution.final_tail_policy_fingerprint,
            }
        )
    return payload


def schedule_outcome_to_contract_dict(
    outcome: ScheduleGenerationOutcomeV1,
) -> dict[str, object]:
    diagnostic = outcome.diagnostic_candidate
    payload: dict[str, object] = {
        "contract_version": outcome.contract_version,
        "result_status": outcome.result_status.value,
        "execution_status": outcome.execution_status.value,
        "solver_status": (
            outcome.solver_status.value if outcome.solver_status is not None else None
        ),
        "solver_adapter": outcome.solver_adapter,
        "solve_duration_seconds": outcome.solve_duration_seconds,
        "outcome_fingerprint": outcome.outcome_fingerprint,
        "source_b_fingerprint": outcome.source_b_fingerprint,
        "solution": (
            schedule_solution_to_contract_dict(outcome.solution)
            if outcome.solution is not None
            else None
        ),
        "diagnostic_candidate": (
            {
                "candidate_fingerprint": diagnostic.candidate_fingerprint,
                "rejection_codes": list(diagnostic.rejection_codes),
                "summary": diagnostic.summary,
                **(
                    {
                        "protected_service_floor_enforcement_fingerprint": (
                            diagnostic.protected_service_floor_enforcement_fingerprint
                        ),
                        "protected_service_floor_validation_fingerprint": (
                            diagnostic.protected_service_floor_validation_fingerprint
                        ),
                    }
                    if diagnostic.protected_service_floor_enforcement_fingerprint is not None
                    else {}
                ),
            }
            if diagnostic is not None
            else None
        ),
        "explanations": list(outcome.explanations),
        "limitations": list(outcome.limitations),
    }
    if outcome.protected_service_floor_enforcement_fingerprint is not None:
        payload["protected_service_floor_enforcement_fingerprint"] = (
            outcome.protected_service_floor_enforcement_fingerprint
        )
        payload["protected_service_floor_validation_fingerprint"] = (
            outcome.protected_service_floor_validation_fingerprint
        )
    return payload
