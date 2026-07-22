from __future__ import annotations

import math
from dataclasses import asdict, replace

from bus_schedule_engine.fleet import assign_fleet
from bus_schedule_engine.models import Trip

from .demand_resolution import DemandAnalysisBlockV1, InterpolationStatus
from .evaluation import (
    BlockEvaluationV1,
    BlockSupplyPlanV1,
    BlockSupplyStatus,
    ScenarioBEvaluationPolicyV1,
    assess_scenario_b_fleet_v1,
)
from .models import (
    ContractDirection,
    DemandConfidence,
    DepartureTerminal,
    ExactTimetableTrip,
    ScenarioBInput,
    ScenarioId,
)
from .serialization import canonical_sha256
from .solver_models import (
    CandidateValidationResultV1,
    CandidateValidationStatus,
    FleetAssignmentV1,
    InitialFleetPositioningMode,
    NativeSolverStatus,
    OperatingParameterLockV1,
    RawScheduleCandidateV1,
    ScheduleProblemV1,
    ScheduleSolutionV1,
    SolutionHeadwayRegimeV1,
    SolutionTripV1,
    StockProfileEventV1,
)
from .solver_problem import jsonable, legacy_direction
from .validation import validate_scenario_input

_CONFIDENCE_RANK = {
    DemandConfidence.UNKNOWN: 0,
    DemandConfidence.LOW: 1,
    DemandConfidence.MEDIUM: 2,
    DemandConfidence.HIGH: 3,
}


def _candidate_scenario(
    problem: ScheduleProblemV1,
    candidate: RawScheduleCandidateV1,
) -> ScenarioBInput:
    b = problem.normalized_inputs.scenario_b
    exact = tuple(
        ExactTimetableTrip(
            trip_id=trip.c_trip_id,
            direction=trip.direction,
            departure_terminal=trip.departure_terminal,
            departure_time=trip.c_departure_time,
            runtime_minutes=trip.runtime_minutes,
            arrival_time=trip.arrival_time,
        )
        for trip in candidate.exact_timetable
    )
    return replace(b, exact_timetable=exact)


def _legacy_candidate_trips(
    problem: ScheduleProblemV1,
    candidate: RawScheduleCandidateV1,
) -> list[Trip]:
    b = problem.normalized_inputs.scenario_b
    return [
        Trip(
            scenario="C",
            trip_id=trip.c_trip_id,
            departure_terminal=(
                b.terminal_1_name
                if trip.departure_terminal == DepartureTerminal.TERMINAL_1
                else b.terminal_2_name
            ),
            direction=legacy_direction(trip.direction),
            departure_seconds=trip.c_departure_time,
            arrival_seconds=trip.arrival_time,
            source_b_trip_id=trip.source_b_trip_id,
            source_b_departure_seconds=trip.b_departure_time,
        )
        for trip in candidate.exact_timetable
    ]


def _confidence_at_least(
    value: DemandConfidence,
    minimum: DemandConfidence,
) -> bool:
    return _CONFIDENCE_RANK[value] >= _CONFIDENCE_RANK[minimum]


def _block_trip_count(
    candidate: RawScheduleCandidateV1,
    block: DemandAnalysisBlockV1,
) -> int:
    return sum(
        block.start_time <= trip.c_departure_time < block.end_time
        and (block.direction == ContractDirection.COMBINED or trip.direction == block.direction)
        for trip in candidate.exact_timetable
    )


def _required_trips(demand: float, capacity: int, ceiling: float) -> int:
    return math.ceil(demand / (capacity * ceiling)) if demand > 0 else 0


def _candidate_block_status(
    block: DemandAnalysisBlockV1,
    trip_count: int,
    load_factor: float | None,
    policy: ScenarioBEvaluationPolicyV1,
) -> BlockSupplyStatus:
    if block.interpolation_status == InterpolationStatus.UNSUPPORTED:
        return BlockSupplyStatus.INSUFFICIENT_DATA
    if block.observed_passengers > 0 and trip_count == 0:
        return BlockSupplyStatus.NO_SERVICE_WITH_DEMAND
    if not _confidence_at_least(
        block.confidence,
        policy.minimum_authoritative_demand_confidence,
    ):
        return BlockSupplyStatus.INSUFFICIENT_DATA
    if load_factor is None:
        return BlockSupplyStatus.WITHIN_PLANNING_CEILING
    if load_factor > policy.critical_load_factor_ceiling:
        return BlockSupplyStatus.CRITICAL_ABOVE_90
    if load_factor > policy.planning_load_factor_ceiling:
        return BlockSupplyStatus.WARNING_ABOVE_85
    if load_factor < policy.low_load_review_threshold:
        return BlockSupplyStatus.LOW_LOAD_REVIEW_ONLY
    return BlockSupplyStatus.WITHIN_PLANNING_CEILING


def _candidate_block_supply(
    problem: ScheduleProblemV1,
    candidate: RawScheduleCandidateV1,
) -> tuple[BlockSupplyPlanV1, ...]:
    resolution = problem.b_evaluation.demand_resolution
    if resolution is None:
        return ()
    a_by_id = {item.block_id: item for item in problem.b_evaluation.a_block_supply}
    b_by_id = {item.block_id: item for item in problem.b_evaluation.b_block_supply}
    capacity = problem.normalized_inputs.scenario_b.vehicle_capacity
    rows: list[BlockSupplyPlanV1] = []
    for block in resolution.blocks:
        count = _block_trip_count(candidate, block)
        nominal = count * capacity
        load_factor = block.observed_passengers / nominal if nominal > 0 else None
        required_85 = _required_trips(
            block.observed_passengers,
            capacity,
            problem.evaluation_policy.planning_load_factor_ceiling,
        )
        required_90 = _required_trips(
            block.observed_passengers,
            capacity,
            problem.evaluation_policy.critical_load_factor_ceiling,
        )
        capacity_85 = nominal * problem.evaluation_policy.planning_load_factor_ceiling
        capacity_90 = nominal * problem.evaluation_policy.critical_load_factor_ceiling
        rows.append(
            BlockSupplyPlanV1(
                scenario=ScenarioId.C,
                direction=block.direction,
                block_id=block.block_id,
                block_start=block.start_time,
                block_end=block.end_time,
                duration_minutes=block.duration_minutes,
                passenger_demand=block.observed_passengers,
                demand_rate_per_hour=block.demand_rate_per_hour,
                vehicle_capacity=capacity,
                a_trip_count=(
                    a_by_id[block.block_id].a_trip_count if block.block_id in a_by_id else None
                ),
                b_trip_count=(
                    b_by_id[block.block_id].b_trip_count if block.block_id in b_by_id else None
                ),
                c_planned_trip_count=count,
                c_actual_trip_count=count,
                trip_rate_per_hour=count * 60 / block.duration_minutes,
                required_trips_85=required_85,
                required_trips_90=required_90,
                required_trip_rate_85=required_85 * 60 / block.duration_minutes,
                required_trip_rate_90=required_90 * 60 / block.duration_minutes,
                nominal_capacity=nominal,
                capacity_at_85=capacity_85,
                capacity_at_90=capacity_90,
                load_factor=load_factor,
                shortage=max(0.0, block.observed_passengers - capacity_85),
                status=_candidate_block_status(
                    block,
                    count,
                    load_factor,
                    problem.evaluation_policy,
                ),
                allocation_reason=(
                    "Validated heuristic candidate: planned and actual C counts reconcile."
                ),
                confidence=block.confidence,
            )
        )
    return tuple(rows)


def _solution_regimes(
    problem: ScheduleProblemV1,
    candidate: RawScheduleCandidateV1,
) -> tuple[SolutionHeadwayRegimeV1, ...]:
    resolution = problem.b_evaluation.demand_resolution
    blocks = resolution.blocks if resolution is not None else ()
    output: list[SolutionHeadwayRegimeV1] = []
    for regime in candidate.headway_regimes:
        covered = tuple(
            block.block_id
            for block in blocks
            if block.start_time < regime.end_time
            and block.end_time > regime.start_time
            and (
                block.direction == ContractDirection.COMBINED or block.direction == regime.direction
            )
        ) or ("OUTSIDE_DEMAND_COVERAGE",)
        actual = tuple(max(1, int(round(item))) for item in regime.actual_headway_sequence)
        regularity_status = (
            "REGULAR"
            if not actual or max(actual) == min(actual)
            else "BALANCED_ROUNDING"
            if max(actual) - min(actual) <= 1
            else "EXCEPTIONAL"
        )
        output.append(
            SolutionHeadwayRegimeV1(
                regime_id=regime.regime_id,
                direction=regime.direction,
                start_time=regime.start_time,
                end_time=regime.end_time,
                covered_analysis_blocks=covered,
                trip_count=regime.trip_count,
                target_service_rate=(
                    60 / regime.target_headway if regime.target_headway > 0 else 0
                ),
                target_headway=regime.target_headway,
                actual_headway_sequence=actual,
                transition_headways=(),
                exceptional_headways=(actual if regularity_status == "EXCEPTIONAL" else ()),
                boundary_reason=regime.boundary_reason,
                regularity_status=regularity_status,
            )
        )
    return tuple(output)


def _stock_events(events) -> tuple[StockProfileEventV1, ...]:
    return tuple(
        StockProfileEventV1(
            event_time=event.event_time,
            event_type=("VEHICLE_READY" if event.event_type == "READY" else "DEPARTURE"),
            trip_id=event.trip_id,
            stock_before=event.stock_before,
            stock_after=event.stock_after,
            arriving_or_ready_vehicle_count=(1 if event.event_type == "READY" else 0),
            departure_count=(1 if event.event_type == "DEPARTURE" else 0),
        )
        for event in events
    )


def _operating_locks(problem: ScheduleProblemV1) -> tuple[OperatingParameterLockV1, ...]:
    b = problem.normalized_inputs.scenario_b
    source = problem.normalized_inputs.scenario_b_fingerprint
    values = {
        "route_id": b.route_id,
        "route_name": b.route_name,
        "route_type": b.route_type.value,
        "terminal_1_name": b.terminal_1_name,
        "terminal_2_name": b.terminal_2_name,
        "trip_runtime_minutes": b.trip_runtime_minutes,
        "turnaround_minutes": {
            "terminal_1": b.turnaround_minutes.terminal_1,
            "terminal_2": b.turnaround_minutes.terminal_2,
        },
        "vehicle_capacity": b.vehicle_capacity,
        "total_daily_trips": b.total_daily_trips,
        "trips_by_direction": {
            "outbound": b.trips_by_direction.outbound,
            "inbound": b.trips_by_direction.inbound,
        },
        "first_departures": {
            "terminal_1": b.first_departures.terminal_1,
            "terminal_2": b.first_departures.terminal_2,
        },
        "last_departures": {
            "terminal_1": b.last_departures.terminal_1,
            "terminal_2": b.last_departures.terminal_2,
        },
        "available_fleet_limit": b.available_fleet_limit,
        "operating_day_type": b.operating_day_type.value,
    }
    return tuple(
        OperatingParameterLockV1(
            field=field,
            value=value,
            source_fingerprint=source,
        )
        for field, value in values.items()
    )


def _solution_fingerprint_payload(solution: ScheduleSolutionV1) -> dict[str, object]:
    payload = jsonable(asdict(solution))
    payload.pop("solution_fingerprint", None)
    payload.pop("solve_duration_seconds", None)
    return payload


def _source_lock_errors(
    problem: ScheduleProblemV1,
    candidate: RawScheduleCandidateV1,
) -> list[str]:
    source_by_id = {
        trip.trip_id: trip for trip in problem.normalized_inputs.scenario_b.exact_timetable
    }
    errors: list[str] = []
    for trip in candidate.exact_timetable:
        source = source_by_id.get(trip.source_b_trip_id)
        if source is None:
            continue
        if trip.direction != source.direction:
            errors.append("SOURCE_DIRECTION_LOCK_VIOLATION")
        if trip.departure_terminal != source.departure_terminal:
            errors.append("SOURCE_TERMINAL_LOCK_VIOLATION")
        if trip.b_departure_time != source.departure_time:
            errors.append("SOURCE_B_DEPARTURE_TRACE_MISMATCH")
        if trip.runtime_minutes != source.runtime_minutes:
            errors.append("SOURCE_RUNTIME_LOCK_VIOLATION")
    return errors


def validate_and_build_solution_v1(
    problem: ScheduleProblemV1,
    candidate: RawScheduleCandidateV1,
) -> CandidateValidationResultV1:
    rejection_codes: list[str] = []
    b = problem.normalized_inputs.scenario_b
    source_ids = [trip.source_b_trip_id for trip in candidate.exact_timetable]
    c_ids = [trip.c_trip_id for trip in candidate.exact_timetable]
    expected_source_ids = [trip.trip_id for trip in b.exact_timetable]
    if len(set(c_ids)) != len(c_ids):
        rejection_codes.append("DUPLICATE_C_TRIP_ID")
    if len(set(source_ids)) != len(source_ids):
        rejection_codes.append("DUPLICATE_SOURCE_B_TRIP_ID")
    if set(source_ids) != set(expected_source_ids):
        rejection_codes.append("SOURCE_B_MAPPING_NOT_ONE_TO_ONE")
    rejection_codes.extend(_source_lock_errors(problem, candidate))
    if candidate.solver_status not in {
        NativeSolverStatus.OPTIMAL,
        NativeSolverStatus.FEASIBLE,
    }:
        rejection_codes.append("UNACCEPTABLE_SOLVER_STATUS")

    candidate_scenario = _candidate_scenario(problem, candidate)
    validation = validate_scenario_input(candidate_scenario)
    rejection_codes.extend(validation.error_codes)
    fleet = assess_scenario_b_fleet_v1(candidate_scenario)
    if not fleet.feasible:
        rejection_codes.append("AVAILABLE_FLEET_LIMIT_EXCEEDED")

    legacy_trips = _legacy_candidate_trips(problem, candidate)
    assignments = assign_fleet(legacy_trips, problem.legacy_parameters)
    if assignments.minimum_vehicles != fleet.minimum_required_fleet:
        rejection_codes.append("FLEET_ASSESSMENT_MISMATCH")

    regime_ids = {regime.regime_id for regime in candidate.headway_regimes}
    if not regime_ids:
        rejection_codes.append("MISSING_HEADWAY_REGIMES")
    if any(trip.headway_regime_id not in regime_ids for trip in candidate.exact_timetable):
        rejection_codes.append("UNKNOWN_HEADWAY_REGIME_REFERENCE")

    if rejection_codes:
        codes = tuple(sorted(set(rejection_codes)))
        return CandidateValidationResultV1(
            status=CandidateValidationStatus.REJECTED,
            rejection_codes=codes,
            summary="Candidate failed independent Contract V1 validation.",
            fleet_assessment=fleet,
            solution=None,
        )

    assignment_by_trip = {item.trip_id: item for item in assignments.assignments}
    solution_trips = tuple(
        SolutionTripV1(
            c_trip_id=trip.c_trip_id,
            source_b_trip_id=trip.source_b_trip_id,
            direction=trip.direction,
            departure_terminal=trip.departure_terminal,
            b_departure_time=trip.b_departure_time,
            c_departure_time=trip.c_departure_time,
            shift_minutes=trip.shift_minutes,
            previous_b_headway=trip.previous_b_headway,
            previous_c_headway=trip.previous_c_headway,
            headway_regime_id=trip.headway_regime_id,
            change_reason=trip.change_reason,
            vehicle_assignment=assignment_by_trip[trip.c_trip_id].vehicle_id,
        )
        for trip in candidate.exact_timetable
    )
    fleet_assignments = tuple(
        FleetAssignmentV1(
            vehicle_id=item.vehicle_id,
            c_trip_id=item.trip_id,
            departure_terminal=(
                DepartureTerminal.TERMINAL_1
                if item.departure_terminal == b.terminal_1_name
                else DepartureTerminal.TERMINAL_2
            ),
            arrival_terminal=(
                DepartureTerminal.TERMINAL_1
                if item.arrival_terminal == b.terminal_1_name
                else DepartureTerminal.TERMINAL_2
            ),
            departure_time=item.departure_seconds,
            arrival_time=item.arrival_seconds,
            ready_time=item.ready_seconds,
        )
        for item in assignments.assignments
    )
    block_supply = _candidate_block_supply(problem, candidate)
    block_evaluation = tuple(
        BlockEvaluationV1(
            block_id=item.block_id,
            direction=item.direction,
            load_factor=item.load_factor,
            shortage=item.shortage,
            status=item.status,
            confidence=item.confidence,
        )
        for item in block_supply
    )
    shifted = [trip for trip in solution_trips if trip.shift_minutes != 0]
    provisional = ScheduleSolutionV1(
        solver_status=candidate.solver_status,
        solver_adapter=candidate.solver_adapter,
        solve_duration_seconds=candidate.solve_duration_seconds,
        solution_fingerprint="",
        source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,
        operating_parameter_locks=_operating_locks(problem),
        c_block_supply_plan=block_supply,
        c_headway_regimes=_solution_regimes(problem, candidate),
        c_exact_timetable=solution_trips,
        fleet_assignment=fleet_assignments,
        available_fleet_limit=b.available_fleet_limit,
        approved_active_fleet=b.approved_active_fleet,
        minimum_required_fleet=fleet.minimum_required_fleet,
        recommended_initial_fleet_terminal_1=(fleet.recommended_initial_fleet_terminal_1),
        recommended_initial_fleet_terminal_2=(fleet.recommended_initial_fleet_terminal_2),
        initial_fleet_positioning_mode=(InitialFleetPositioningMode.SOLVER_DETERMINED),
        fleet_margin=fleet.fleet_margin,
        maximum_simultaneous_vehicle_use=fleet.minimum_required_fleet,
        vehicle_stock_profile_terminal_1=_stock_events(fleet.terminal_1_events),
        vehicle_stock_profile_terminal_2=_stock_events(fleet.terminal_2_events),
        fleet_feasibility_status="FLEET_FEASIBLE",
        block_evaluation=block_evaluation,
        residual_overload=sum(item.shortage for item in block_supply),
        shifted_trip_count=len(shifted),
        total_shift_minutes=sum(abs(item.shift_minutes) for item in shifted),
        maximum_shift_minutes=max(
            (abs(item.shift_minutes) for item in shifted),
            default=0.0,
        ),
        explanations=(
            candidate.explanation,
            "Candidate passed independent timetable, traceability, and fleet validation.",
        ),
        limitations=candidate.limitations,
    )
    solution = replace(
        provisional,
        solution_fingerprint=canonical_sha256(_solution_fingerprint_payload(provisional)),
    )
    return CandidateValidationResultV1(
        status=CandidateValidationStatus.ACCEPTED,
        rejection_codes=(),
        summary="Candidate passed independent Contract V1 validation.",
        fleet_assessment=fleet,
        solution=solution,
    )
