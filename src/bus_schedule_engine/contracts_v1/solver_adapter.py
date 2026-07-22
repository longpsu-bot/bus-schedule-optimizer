from __future__ import annotations

import math
import time
from dataclasses import asdict, replace
from enum import Enum
from typing import Any

from bus_schedule_engine.c_generator import generate_scenario_c
from bus_schedule_engine.fleet import assign_fleet
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    GeneratedScenario,
    HeadwayType,
    ScenarioCStatus,
    ScenarioParameters,
    Trip,
)

from .demand_resolution import DemandAnalysisBlockV1, InterpolationStatus
from .evaluation import (
    BDisposition,
    BlockEvaluationV1,
    BlockSupplyPlanV1,
    BlockSupplyStatus,
    DimensionStatus,
    ScenarioBEvaluationBundleV1,
    ScenarioBEvaluationPolicyV1,
    assess_scenario_b_fleet_v1,
)
from .models import (
    ContractDirection,
    DemandConfidence,
    DepartureTerminal,
    ExactTimetableTrip,
    NormalizedInputBundleV1,
    ScenarioBInput,
    ScenarioId,
)
from .serialization import canonical_sha256
from .solver_models import (
    CandidateValidationResultV1,
    CandidateValidationStatus,
    FleetAssignmentV1,
    GenerationResultStatus,
    InitialFleetPositioningMode,
    NativeSolverStatus,
    OperatingParameterLockV1,
    RawCandidateTripV1,
    RawHeadwayRegimeV1,
    RawScheduleCandidateV1,
    RejectedCandidateDiagnosticV1,
    ScheduleGenerationOutcomeV1,
    ScheduleProblemV1,
    ScheduleSolutionV1,
    ScheduleSolver,
    SolutionHeadwayRegimeV1,
    SolutionTripV1,
    SolverExecutionStatus,
    SolverRunResultV1,
    StockProfileEventV1,
)
from .validation import validate_scenario_input


class ScheduleProblemError(ValueError):
    """Raised when legacy heuristic inputs do not reconcile with normalized Contract V1."""


_CONFIDENCE_RANK = {
    DemandConfidence.UNKNOWN: 0,
    DemandConfidence.LOW: 1,
    DemandConfidence.MEDIUM: 2,
    DemandConfidence.HIGH: 3,
}


_ACCEPTED_HEURISTIC_STATUSES = {
    ScenarioCStatus.SUITABLE_REGULAR,
    ScenarioCStatus.DEMAND_IMPROVED_NOT_REGULAR,
    ScenarioCStatus.REGULAR_STILL_UNDERSUPPLIED,
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _contract_direction(direction: Direction) -> ContractDirection:
    if direction == Direction.TERMINAL_1_TO_2:
        return ContractDirection.OUTBOUND
    if direction == Direction.TERMINAL_2_TO_1:
        return ContractDirection.INBOUND
    return ContractDirection.COMBINED


def _legacy_direction(direction: ContractDirection) -> Direction:
    if direction == ContractDirection.OUTBOUND:
        return Direction.TERMINAL_1_TO_2
    if direction == ContractDirection.INBOUND:
        return Direction.TERMINAL_2_TO_1
    raise ScheduleProblemError("Timetable candidates cannot use combined direction")


def _departure_terminal(
    direction: ContractDirection,
) -> DepartureTerminal:
    if direction == ContractDirection.OUTBOUND:
        return DepartureTerminal.TERMINAL_1
    if direction == ContractDirection.INBOUND:
        return DepartureTerminal.TERMINAL_2
    raise ScheduleProblemError("Timetable candidates cannot use combined direction")


def _validate_problem_legacy_parameters(
    normalized: NormalizedInputBundleV1,
    legacy: ScenarioParameters,
) -> None:
    scenario_b = normalized.scenario_b
    comparisons = {
        "route_id": (legacy.route_id, scenario_b.route_id),
        "route_name": (legacy.route_name, scenario_b.route_name),
        "route_type": (legacy.route_type, scenario_b.route_type),
        "terminal_1_name": (legacy.terminal_1_name, scenario_b.terminal_1_name),
        "terminal_2_name": (legacy.terminal_2_name, scenario_b.terminal_2_name),
        "total_daily_trips": (legacy.total_daily_trips, scenario_b.total_daily_trips),
        "vehicle_capacity": (legacy.capacity, scenario_b.vehicle_capacity),
        "trip_runtime_minutes": (
            legacy.default_trip_runtime_minutes,
            scenario_b.trip_runtime_minutes,
        ),
        "terminal_1_first_departure": (
            legacy.terminal_1_first_departure,
            scenario_b.first_departures.terminal_1,
        ),
        "terminal_2_first_departure": (
            legacy.terminal_2_first_departure,
            scenario_b.first_departures.terminal_2,
        ),
        "terminal_1_last_departure": (
            legacy.terminal_1_last_departure,
            scenario_b.last_departures.terminal_1,
        ),
        "terminal_2_last_departure": (
            legacy.terminal_2_last_departure,
            scenario_b.last_departures.terminal_2,
        ),
    }
    mismatches = [
        field
        for field, (legacy_value, normalized_value) in comparisons.items()
        if legacy_value != normalized_value
    ]
    if mismatches:
        raise ScheduleProblemError(
            "Legacy parameters do not reconcile with Scenario B: "
            + ", ".join(mismatches)
        )
    if not (
        legacy.effective_layover_minutes
        == scenario_b.turnaround_minutes.terminal_1
        == scenario_b.turnaround_minutes.terminal_2
    ):
        raise ScheduleProblemError(
            "The legacy heuristic adapter supports equal terminal turnaround values only"
        )


def _validate_problem_legacy_timetable(
    normalized: NormalizedInputBundleV1,
    legacy_trips_b: tuple[Trip, ...],
) -> None:
    normalized_by_id = {
        trip.trip_id: trip for trip in normalized.scenario_b.exact_timetable
    }
    legacy_by_id = {trip.trip_id: trip for trip in legacy_trips_b}
    if len(legacy_by_id) != len(legacy_trips_b):
        raise ScheduleProblemError("Legacy Scenario B contains duplicate trip IDs")
    if set(normalized_by_id) != set(legacy_by_id):
        raise ScheduleProblemError(
            "Legacy and normalized Scenario B trip identities do not reconcile"
        )
    for trip_id, normalized_trip in normalized_by_id.items():
        legacy_trip = legacy_by_id[trip_id]
        expected_direction = _contract_direction(legacy_trip.direction)
        expected_terminal = _departure_terminal(expected_direction)
        arrival = legacy_trip.resolved_arrival_seconds(
            normalized.scenario_b.trip_runtime_minutes
        )
        if (
            expected_direction != normalized_trip.direction
            or expected_terminal != normalized_trip.departure_terminal
            or legacy_trip.departure_seconds != normalized_trip.departure_time
            or arrival != normalized_trip.resolved_arrival_time
        ):
            raise ScheduleProblemError(
                f"Legacy and normalized Scenario B differ for trip {trip_id}"
            )


def _validate_problem_legacy_demand(
    normalized: NormalizedInputBundleV1,
    legacy_demand: tuple[DemandRecord, ...],
) -> None:
    observed = normalized.observed_demand
    if observed is None:
        if legacy_demand:
            raise ScheduleProblemError(
                "Legacy demand is present while normalized observed demand is absent"
            )
        return
    if len(observed.observations) != len(legacy_demand):
        raise ScheduleProblemError(
            "Legacy and normalized demand row counts do not reconcile"
        )
    normalized_rows = sorted(
        (
            observation.direction.value,
            observation.interval_start,
            observation.interval_end,
            float(observation.passenger_count),
            observation.volume_classification.value,
        )
        for observation in observed.observations
    )
    legacy_rows = sorted(
        (
            _contract_direction(record.direction).value,
            record.block_start_seconds,
            record.block_end_seconds,
            float(record.passenger_volume),
            record.volume_type.value,
        )
        for record in legacy_demand
    )
    if normalized_rows != legacy_rows:
        raise ScheduleProblemError(
            "Legacy and normalized demand observations do not reconcile"
        )


def build_schedule_problem_v1(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    legacy_parameters: ScenarioParameters,
    legacy_trips_b: list[Trip] | tuple[Trip, ...],
    legacy_demand: list[DemandRecord] | tuple[DemandRecord, ...],
    heuristic_config,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
) -> ScheduleProblemV1:
    evaluation_policy = evaluation_policy or ScenarioBEvaluationPolicyV1()
    trips = tuple(legacy_trips_b)
    demand = tuple(legacy_demand)
    _validate_problem_legacy_parameters(normalized_inputs, legacy_parameters)
    _validate_problem_legacy_timetable(normalized_inputs, trips)
    _validate_problem_legacy_demand(normalized_inputs, demand)

    payload = {
        "contract_version": normalized_inputs.scenario_b.contract_version,
        "source_b_fingerprint": normalized_inputs.scenario_b_fingerprint,
        "observed_demand_fingerprint": normalized_inputs.observed_demand_fingerprint,
        "b_disposition": b_evaluation.evaluation.disposition.value,
        "evaluation_policy": _jsonable(asdict(evaluation_policy)),
        "heuristic_config": _jsonable(asdict(heuristic_config)),
    }
    return ScheduleProblemV1(
        normalized_inputs=normalized_inputs,
        b_evaluation=b_evaluation,
        evaluation_policy=evaluation_policy,
        legacy_parameters=legacy_parameters,
        legacy_trips_b=trips,
        legacy_demand=demand,
        heuristic_config=heuristic_config,
        problem_fingerprint=canonical_sha256(payload),
    )


def _trace_map(generated: GeneratedScenario):
    return {trace.c_trip_id: trace for trace in generated.trip_traces}


def _raw_candidate_from_generated(
    generated: GeneratedScenario,
    problem: ScheduleProblemV1,
    solve_duration_seconds: float,
    adapter_id: str,
) -> RawScheduleCandidateV1:
    traces = _trace_map(generated)
    source_b = {
        trip.trip_id: trip for trip in problem.normalized_inputs.scenario_b.exact_timetable
    }
    trips: list[RawCandidateTripV1] = []
    for trip in sorted(
        generated.trips,
        key=lambda item: (item.departure_seconds, item.trip_id),
    ):
        trace = traces.get(trip.trip_id)
        source_id = (
            trace.source_b_trip_id
            if trace is not None
            else trip.source_b_trip_id or trip.trip_id
        )
        if source_id not in source_b:
            raise ScheduleProblemError(
                f"Heuristic candidate trip {trip.trip_id} has unknown source B trip"
            )
        source = source_b[source_id]
        direction = _contract_direction(trip.direction)
        arrival = trip.resolved_arrival_seconds(
            problem.normalized_inputs.scenario_b.trip_runtime_minutes
        )
        runtime_seconds = arrival - trip.departure_seconds
        if runtime_seconds <= 0 or runtime_seconds % 60:
            raise ScheduleProblemError(
                f"Heuristic candidate trip {trip.trip_id} has invalid runtime"
            )
        trips.append(
            RawCandidateTripV1(
                c_trip_id=trip.trip_id,
                source_b_trip_id=source_id,
                direction=direction,
                departure_terminal=_departure_terminal(direction),
                b_departure_time=source.departure_time,
                c_departure_time=trip.departure_seconds,
                arrival_time=arrival,
                runtime_minutes=runtime_seconds // 60,
                shift_minutes=(trip.departure_seconds - source.departure_time) / 60,
                previous_b_headway=(
                    trace.original_previous_headway if trace is not None else None
                ),
                previous_c_headway=(
                    trace.new_previous_headway if trace is not None else None
                ),
                headway_regime_id=(
                    trace.headway_regime_id
                    if trace is not None
                    else "REGIME_UNSPECIFIED"
                ),
                change_reason=(
                    trace.change_reason if trace is not None else generated.reason
                ),
            )
        )
    regimes = tuple(
        RawHeadwayRegimeV1(
            regime_id=regime.regime_id,
            direction=_contract_direction(regime.direction),
            start_time=regime.start_seconds,
            end_time=regime.end_seconds,
            trip_count=regime.trip_count,
            target_headway=regime.target_headway_minutes,
            actual_headway_sequence=tuple(regime.actual_headway_sequence),
            boundary_reason=regime.boundary_reason.value,
            legacy_regularity_status=regime.headway_status,
        )
        for regime in generated.headway_regimes
    )
    candidate_payload = {
        "source_b_fingerprint": problem.normalized_inputs.scenario_b_fingerprint,
        "solver_adapter": adapter_id,
        "trips": [
            {
                "c_trip_id": item.c_trip_id,
                "source_b_trip_id": item.source_b_trip_id,
                "direction": item.direction.value,
                "departure_terminal": item.departure_terminal.value,
                "b_departure_time": item.b_departure_time,
                "c_departure_time": item.c_departure_time,
                "arrival_time": item.arrival_time,
                "runtime_minutes": item.runtime_minutes,
            }
            for item in trips
        ],
    }
    return RawScheduleCandidateV1(
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter=adapter_id,
        solve_duration_seconds=solve_duration_seconds,
        candidate_fingerprint=canonical_sha256(candidate_payload),
        exact_timetable=tuple(trips),
        headway_regimes=regimes,
        explanation=generated.reason,
        limitations=(
            "The legacy heuristic adapter proves only that this candidate was found; "
            "it does not prove optimality or global infeasibility.",
        ),
    )


class HeuristicScheduleSolverAdapter:
    adapter_id = "legacy_heuristic_v1"

    def solve(self, problem: ScheduleProblemV1) -> SolverRunResultV1:
        started = time.perf_counter()
        try:
            generated = generate_scenario_c(
                problem.legacy_parameters,
                list(problem.legacy_trips_b),
                list(problem.legacy_demand),
                problem.normalized_inputs.scenario_b.available_fleet_limit,
                problem.heuristic_config,
            )
            duration = max(0.0, time.perf_counter() - started)
            if generated.generation_status in _ACCEPTED_HEURISTIC_STATUSES:
                candidate = _raw_candidate_from_generated(
                    generated,
                    problem,
                    duration,
                    self.adapter_id,
                )
                return SolverRunResultV1(
                    execution_status=SolverExecutionStatus.COMPLETED,
                    solver_status=NativeSolverStatus.FEASIBLE,
                    solver_adapter=self.adapter_id,
                    solve_duration_seconds=duration,
                    candidate=candidate,
                    explanations=(generated.reason,),
                    limitations=candidate.limitations,
                )
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.UNKNOWN,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=duration,
                candidate=None,
                explanations=(generated.reason,),
                limitations=(
                    "The heuristic candidate space was exhausted without an accepted "
                    "candidate; this is not proof that B's locked parameters are infeasible.",
                ),
            )
        except Exception as exc:
            duration = max(0.0, time.perf_counter() - started)
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.MODEL_INVALID,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=duration,
                candidate=None,
                explanations=(f"Heuristic adapter failed: {exc}",),
                limitations=(
                    "MODEL_INVALID identifies an adapter or compatibility defect, not "
                    "route or timetable infeasibility.",
                ),
            )


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
            vehicle_assignment=None,
        )
        for trip in candidate.exact_timetable
    )
    return ScenarioBInput(
        route_id=b.route_id,
        route_name=b.route_name,
        route_type=b.route_type,
        terminal_1_name=b.terminal_1_name,
        terminal_2_name=b.terminal_2_name,
        trip_runtime_minutes=b.trip_runtime_minutes,
        turnaround_minutes=b.turnaround_minutes,
        total_daily_trips=b.total_daily_trips,
        trips_by_direction=b.trips_by_direction,
        first_departures=b.first_departures,
        last_departures=b.last_departures,
        vehicle_capacity=b.vehicle_capacity,
        available_fleet_limit=b.available_fleet_limit,
        operating_day_type=b.operating_day_type,
        exact_timetable=exact,
        source_metadata=b.source_metadata,
        approved_active_fleet=b.approved_active_fleet,
    )


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
            direction=_legacy_direction(trip.direction),
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
        and (
            block.direction == ContractDirection.COMBINED
            or trip.direction == block.direction
        )
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
        load_factor = (
            block.observed_passengers / nominal if nominal > 0 else None
        )
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
        status = _candidate_block_status(
            block,
            count,
            load_factor,
            problem.evaluation_policy,
        )
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
                    a_by_id[block.block_id].a_trip_count
                    if block.block_id in a_by_id
                    else None
                ),
                b_trip_count=(
                    b_by_id[block.block_id].b_trip_count
                    if block.block_id in b_by_id
                    else None
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
                status=status,
                allocation_reason=(
                    "PR-03 heuristic adapter reports planned and actual C counts as "
                    "the same validated candidate allocation."
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
                block.direction == ContractDirection.COMBINED
                or block.direction == regime.direction
            )
        )
        if not covered:
            covered = ("OUTSIDE_DEMAND_COVERAGE",)
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
                exceptional_headways=(
                    actual if regularity_status == "EXCEPTIONAL" else ()
                ),
                boundary_reason=regime.boundary_reason,
                regularity_status=regularity_status,
            )
        )
    return tuple(output)


def _stock_events(events) -> tuple[StockProfileEventV1, ...]:
    return tuple(
        StockProfileEventV1(
            event_time=event.event_time,
            event_type=(
                "VEHICLE_READY" if event.event_type == "READY" else "DEPARTURE"
            ),
            trip_id=event.trip_id,
            stock_before=event.stock_before,
            stock_after=event.stock_after,
            arriving_or_ready_vehicle_count=(
                1 if event.event_type == "READY" else 0
            ),
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
    payload = _jsonable(asdict(solution))
    payload.pop("solution_fingerprint", None)
    return payload


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

    if rejection_codes:
        codes = tuple(sorted(set(rejection_codes)))
        return CandidateValidationResultV1(
            status=CandidateValidationStatus.REJECTED,
            rejection_codes=codes,
            summary="Candidate failed independent Contract V1 validation.",
            fleet_assessment=fleet,
            solution=None,
        )

    assignment_by_trip = {
        item.trip_id: item for item in assignments.assignments
    }
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
        recommended_initial_fleet_terminal_1=(
            fleet.recommended_initial_fleet_terminal_1
        ),
        recommended_initial_fleet_terminal_2=(
            fleet.recommended_initial_fleet_terminal_2
        ),
        initial_fleet_positioning_mode=(
            InitialFleetPositioningMode.SOLVER_DETERMINED
        ),
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
            "The candidate passed independent timetable, traceability, and fleet validation.",
        ),
        limitations=candidate.limitations,
    )
    solution = replace(
        provisional,
        solution_fingerprint=canonical_sha256(
            _solution_fingerprint_payload(provisional)
        ),
    )
    return CandidateValidationResultV1(
        status=CandidateValidationStatus.ACCEPTED,
        rejection_codes=(),
        summary="Candidate passed independent Contract V1 validation.",
        fleet_assessment=fleet,
        solution=solution,
    )


def _outcome_fingerprint_payload(
    outcome: ScheduleGenerationOutcomeV1,
) -> dict[str, object]:
    payload = _jsonable(asdict(outcome))
    payload.pop("outcome_fingerprint", None)
    return payload


def _finalize_outcome(
    outcome: ScheduleGenerationOutcomeV1,
) -> ScheduleGenerationOutcomeV1:
    return replace(
        outcome,
        outcome_fingerprint=canonical_sha256(
            _outcome_fingerprint_payload(outcome)
        ),
    )


def _not_run_outcome(
    problem: ScheduleProblemV1,
    result_status: GenerationResultStatus,
    explanation: str,
    limitations: tuple[str, ...] = (),
) -> ScheduleGenerationOutcomeV1:
    return _finalize_outcome(
        ScheduleGenerationOutcomeV1(
            result_status=result_status,
            execution_status=SolverExecutionStatus.NOT_RUN,
            solver_status=None,
            solver_adapter=None,
            solve_duration_seconds=0.0,
            outcome_fingerprint="",
            source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,
            solution=None,
            diagnostic_candidate=None,
            explanations=(explanation,),
            limitations=limitations,
        )
    )


def run_schedule_solver_v1(
    problem: ScheduleProblemV1,
    solver: ScheduleSolver,
) -> ScheduleGenerationOutcomeV1:
    disposition = problem.b_evaluation.evaluation.disposition
    if disposition == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE:
        return _not_run_outcome(
            problem,
            GenerationResultStatus.C_NOT_REQUIRED_B_SUITABLE,
            "Scenario B is technically feasible and demand-suitable; no duplicate C is generated.",
        )
    if disposition == BDisposition.INSUFFICIENT_DATA:
        return _not_run_outcome(
            problem,
            GenerationResultStatus.C_NOT_GENERATED_INSUFFICIENT_DATA,
            "Demand evidence is insufficient for authoritative demand-optimized C generation.",
        )
    if disposition == BDisposition.PARAMETERS_INFEASIBLE:
        return _not_run_outcome(
            problem,
            GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS,
            "B's locked parameters were independently proven infeasible before solver invocation.",
        )

    run = solver.solve(problem)
    if run.execution_status != SolverExecutionStatus.COMPLETED:
        return _not_run_outcome(
            problem,
            GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,
            "Solver adapter returned an invalid execution-state combination.",
        )
    if run.solver_status == NativeSolverStatus.MODEL_INVALID:
        return _finalize_outcome(
            ScheduleGenerationOutcomeV1(
                result_status=GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,
                execution_status=run.execution_status,
                solver_status=run.solver_status,
                solver_adapter=run.solver_adapter,
                solve_duration_seconds=run.solve_duration_seconds,
                outcome_fingerprint="",
                source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,
                solution=None,
                diagnostic_candidate=None,
                explanations=run.explanations,
                limitations=run.limitations,
            )
        )
    if run.solver_status == NativeSolverStatus.INFEASIBLE:
        return _finalize_outcome(
            ScheduleGenerationOutcomeV1(
                result_status=GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS,
                execution_status=run.execution_status,
                solver_status=run.solver_status,
                solver_adapter=run.solver_adapter,
                solve_duration_seconds=run.solve_duration_seconds,
                outcome_fingerprint="",
                source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,
                solution=None,
                diagnostic_candidate=None,
                explanations=run.explanations,
                limitations=run.limitations,
            )
        )
    if run.solver_status == NativeSolverStatus.UNKNOWN or run.candidate is None:
        return _finalize_outcome(
            ScheduleGenerationOutcomeV1(
                result_status=GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT,
                execution_status=run.execution_status,
                solver_status=NativeSolverStatus.UNKNOWN,
                solver_adapter=run.solver_adapter,
                solve_duration_seconds=run.solve_duration_seconds,
                outcome_fingerprint="",
                source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,
                solution=None,
                diagnostic_candidate=None,
                explanations=run.explanations,
                limitations=run.limitations,
            )
        )

    validation = validate_and_build_solution_v1(problem, run.candidate)
    if not validation.passed or validation.solution is None:
        diagnostic = RejectedCandidateDiagnosticV1(
            candidate_fingerprint=run.candidate.candidate_fingerprint,
            rejection_codes=validation.rejection_codes,
            summary=validation.summary,
        )
        return _finalize_outcome(
            ScheduleGenerationOutcomeV1(
                result_status=(
                    GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
                ),
                execution_status=run.execution_status,
                solver_status=run.solver_status,
                solver_adapter=run.solver_adapter,
                solve_duration_seconds=run.solve_duration_seconds,
                outcome_fingerprint="",
                source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,
                solution=None,
                diagnostic_candidate=diagnostic,
                explanations=run.explanations,
                limitations=run.limitations,
            )
        )
    return _finalize_outcome(
        ScheduleGenerationOutcomeV1(
            result_status=GenerationResultStatus.SOLUTION_ACCEPTED,
            execution_status=run.execution_status,
            solver_status=run.solver_status,
            solver_adapter=run.solver_adapter,
            solve_duration_seconds=run.solve_duration_seconds,
            outcome_fingerprint="",
            source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,
            solution=validation.solution,
            diagnostic_candidate=None,
            explanations=run.explanations,
            limitations=run.limitations,
        )
    )
