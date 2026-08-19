"""OR-Tools CP-SAT fixed-resource adapters for Contract V1 schedules."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace
from typing import ClassVar

import ortools
from ortools.sat.python import cp_model

from .evaluation import ScenarioBEvaluationBundleV1, ScenarioBEvaluationPolicyV1
from .models import (
    ContractDirection,
    DepartureTerminal,
    ExactTimetableTrip,
    NormalizedInputBundleV1,
)
from .problem_validation import validate_schedule_problem_v1
from .service_quality_metrics import (
    _recompute_demand_objective_vector_v1 as _recompute_solver_neutral_demand_vector_v1,
)
from .solver_fingerprints import candidate_fingerprint
from .solver_models import (
    BoundaryConvention,
    DirectionTripLockMode,
    FleetConstraintMode,
    InitialFleetPositioningMode,
    NativeSolverStatus,
    RawCandidateTripV1,
    RawHeadwayRegimeV1,
    RawScheduleCandidateV1,
    ScheduleGenerationContextV1,
    ScheduleProblemV1,
    SolverExecutionStatus,
    SolverPolicyV1,
    SolverRunResultV1,
)
from .solver_problem import (
    ScheduleProblemError,
    build_schedule_generation_context_v1,
    build_schedule_problem_v1,
    empty_adapter_context_fingerprint,
)

_FEASIBILITY_BOUNDARY_REASON = "FULL_DIRECTION_TECHNICAL_FEASIBILITY"
_SINGLETON_TARGET_HEADWAY_MINUTES = 1.0
_REGIME_IDS = {
    ContractDirection.OUTBOUND: "ORTOOLS-OUTBOUND-FEASIBILITY",
    ContractDirection.INBOUND: "ORTOOLS-INBOUND-FEASIBILITY",
}
_DEMAND_BOUNDARY_REASON = "FULL_DIRECTION_DEMAND_PRIORITY_OPTIMIZATION"
_DEMAND_REGIME_IDS = {
    ContractDirection.OUTBOUND: "ORTOOLS-OUTBOUND-DEMAND-OPTIMIZATION",
    ContractDirection.INBOUND: "ORTOOLS-INBOUND-DEMAND-OPTIMIZATION",
}
ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY = (
    "ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY"
)
_DEMAND_OBJECTIVE_NAMES = (
    "no_service_block_count",
    "critical_block_count",
    "total_critical_shortage_trips",
    "planning_warning_block_count",
    "total_planning_shortage_trips",
    "shifted_trip_count",
    "total_shift_minutes",
    "maximum_shift_minutes",
)


@dataclass(frozen=True, slots=True)
class _CpSatModelBundle:
    model: cp_model.CpModel
    departure_by_source_id: dict[str, cp_model.IntVar]
    initial_terminal_1: cp_model.IntVar
    initial_terminal_2: cp_model.IntVar
    terminal_occupancy_binary_variable_count: int
    terminal_occupancy_constraint_count: int
    terminal_occupancy_arrival_event_count: int


@dataclass(frozen=True, slots=True)
class _DemandObjectiveStage:
    name: str
    value: cp_model.IntVar


@dataclass(frozen=True, slots=True)
class _DemandCpSatModelBundle:
    hard: _CpSatModelBundle
    membership_by_source_and_block: dict[tuple[str, str], cp_model.IntVar]
    block_trip_count_by_id: dict[str, cp_model.IntVar]
    stages: tuple[_DemandObjectiveStage, ...]


def _ordered_directional_trips(
    problem: ScheduleProblemV1,
) -> dict[ContractDirection, tuple[ExactTimetableTrip, ...]]:
    return {
        direction: tuple(
            sorted(
                (
                    trip
                    for trip in problem.scenario_b.exact_timetable
                    if trip.direction == direction
                ),
                key=lambda item: (item.departure_time, item.trip_id),
            )
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    }


def _adapter_capability_issues(problem: ScheduleProblemV1, adapter_id: str) -> tuple[str, ...]:
    issues = [item.code for item in validate_schedule_problem_v1(problem).issues]
    scenario = problem.scenario_b
    if problem.solver_adapter != adapter_id:
        issues.append("PROBLEM_ADAPTER_CONTEXT_MISMATCH")
    if problem.direction_trip_lock_mode != DirectionTripLockMode.FIXED_BY_DIRECTION:
        issues.append("ORTOOLS_UNSUPPORTED_DIRECTION_TRIP_LOCK_MODE")
    if problem.fleet_constraint_mode != FleetConstraintMode.AVAILABLE_UPPER_BOUND:
        issues.append("ORTOOLS_UNSUPPORTED_FLEET_CONSTRAINT_MODE")
    if problem.initial_fleet_positioning_mode != InitialFleetPositioningMode.SOLVER_DETERMINED:
        issues.append("ORTOOLS_UNSUPPORTED_INITIAL_FLEET_POSITIONING_MODE")
    if problem.boundary_convention != BoundaryConvention.HALF_OPEN:
        issues.append("ORTOOLS_UNSUPPORTED_BOUNDARY_CONVENTION")
    if problem.direction_redistribution_authorization is not None:
        issues.append("ORTOOLS_UNSUPPORTED_DIRECTION_REDISTRIBUTION")
    if problem.fixed_initial_fleet is not None or problem.bounded_initial_fleet is not None:
        issues.append("ORTOOLS_UNSUPPORTED_INITIAL_FLEET_VALUES")
    if (
        not scenario.terminal_1_name.strip()
        or not scenario.terminal_2_name.strip()
        or scenario.terminal_1_name == scenario.terminal_2_name
    ):
        issues.append("ORTOOLS_INVALID_TWO_TERMINAL_SHAPE")

    source_ids = [trip.trip_id for trip in scenario.exact_timetable]
    if len(source_ids) != len(set(source_ids)):
        issues.append("ORTOOLS_INVALID_SOURCE_MAPPING")
    directional = _ordered_directional_trips(problem)
    if (
        len(scenario.exact_timetable) != scenario.total_daily_trips
        or len(directional[ContractDirection.OUTBOUND]) != scenario.trips_by_direction.outbound
        or len(directional[ContractDirection.INBOUND]) != scenario.trips_by_direction.inbound
        or scenario.total_daily_trips
        != scenario.trips_by_direction.outbound + scenario.trips_by_direction.inbound
    ):
        issues.append("ORTOOLS_INVALID_SOURCE_MAPPING")

    expected_terminal = {
        ContractDirection.OUTBOUND: DepartureTerminal.TERMINAL_1,
        ContractDirection.INBOUND: DepartureTerminal.TERMINAL_2,
    }
    for direction, trips in directional.items():
        if not trips or any(
            trip.departure_terminal != expected_terminal[direction]
            or trip.runtime_minutes <= 0
            or trip.arrival_time != trip.departure_time + trip.runtime_minutes * 60
            for trip in trips
        ):
            issues.append("ORTOOLS_INVALID_SOURCE_MAPPING")

    departure_values = [
        *(trip.departure_time for trip in scenario.exact_timetable),
        scenario.first_departures.terminal_1,
        scenario.first_departures.terminal_2,
        scenario.last_departures.terminal_1,
        scenario.last_departures.terminal_2,
    ]
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value % 60 != 0
        for value in departure_values
    ):
        issues.append("ORTOOLS_NON_MINUTE_ALIGNED_DEPARTURE")
    return tuple(dict.fromkeys(issues))


def _directional_window_minutes(
    problem: ScheduleProblemV1,
    direction: ContractDirection,
) -> tuple[int, int]:
    scenario = problem.scenario_b
    if direction == ContractDirection.OUTBOUND:
        return (
            scenario.first_departures.terminal_1 // 60,
            scenario.last_departures.terminal_1 // 60,
        )
    return (
        scenario.first_departures.terminal_2 // 60,
        scenario.last_departures.terminal_2 // 60,
    )


def _reified_less_than_or_equal(
    model: cp_model.CpModel,
    left,
    right,
    *,
    name: str,
) -> cp_model.IntVar:
    indicator = model.new_bool_var(name)
    model.add(left <= right).only_enforce_if(indicator)
    model.add(left >= right + 1).only_enforce_if(indicator.negated())
    return indicator


def _add_terminal_occupancy_capacity_constraints(
    model: cp_model.CpModel,
    *,
    terminal_name: str,
    capacity: int | None,
    initial_occupancy: cp_model.IntVar,
    arrival_trips: tuple[ExactTimetableTrip, ...],
    departure_trips: tuple[ExactTimetableTrip, ...],
    departure_by_source_id: dict[str, cp_model.IntVar],
) -> tuple[int, int, int]:
    if capacity is None:
        return 0, 0, 0

    binary_variables = 0
    constraints = 0
    model.add(initial_occupancy <= capacity)
    constraints += 1
    arrival_by_trip_id = {
        trip.trip_id: departure_by_source_id[trip.trip_id] + trip.runtime_minutes
        for trip in arrival_trips
    }
    for arrival_index, arrival_trip in enumerate(arrival_trips, start=1):
        arrival_time = arrival_by_trip_id[arrival_trip.trip_id]
        arrivals_at_or_before: list[int | cp_model.IntVar] = [1]
        for other_index, other_trip in enumerate(arrival_trips, start=1):
            if other_trip.trip_id == arrival_trip.trip_id:
                continue
            indicator = _reified_less_than_or_equal(
                model,
                arrival_by_trip_id[other_trip.trip_id],
                arrival_time,
                name=(
                    f"occupancy_{terminal_name}_arrival_"
                    f"{other_index:04d}_{other_trip.trip_id}_"
                    f"by_{arrival_index:04d}_{arrival_trip.trip_id}"
                ),
            )
            arrivals_at_or_before.append(indicator)
            binary_variables += 1
            constraints += 2

        departures_before: list[cp_model.IntVar] = []
        for departure_index, departure_trip in enumerate(departure_trips, start=1):
            indicator = _reified_less_than_or_equal(
                model,
                departure_by_source_id[departure_trip.trip_id],
                arrival_time - 1,
                name=(
                    f"occupancy_{terminal_name}_departure_"
                    f"{departure_index:04d}_{departure_trip.trip_id}_"
                    f"before_{arrival_index:04d}_{arrival_trip.trip_id}"
                ),
            )
            departures_before.append(indicator)
            binary_variables += 1
            constraints += 2

        model.add(
            initial_occupancy + sum(arrivals_at_or_before) - sum(departures_before) <= capacity
        )
        constraints += 1
    return binary_variables, constraints, len(arrival_trips)


def _build_cp_sat_model(
    problem: ScheduleProblemV1,
    *,
    departure_domain_by_source_id: dict[str, tuple[int, int]] | None = None,
    minimum_headway_minutes: int = 1,
) -> _CpSatModelBundle:
    model = cp_model.CpModel()
    directional = _ordered_directional_trips(problem)
    departure_by_source_id: dict[str, cp_model.IntVar] = {}
    for direction, trips in directional.items():
        first_minute, last_minute = _directional_window_minutes(problem, direction)
        variables: list[cp_model.IntVar] = []
        for index, trip in enumerate(trips, start=1):
            domain = (
                departure_domain_by_source_id[trip.trip_id]
                if departure_domain_by_source_id is not None
                else (first_minute, last_minute)
            )
            variable = model.new_int_var(
                domain[0],
                domain[1],
                f"departure_{direction.value}_{index:04d}_{trip.trip_id}",
            )
            variables.append(variable)
            departure_by_source_id[trip.trip_id] = variable
            model.add_hint(variable, trip.departure_time // 60)
        model.add(variables[0] == first_minute)
        model.add(variables[-1] == last_minute)
        for earlier, later in zip(variables, variables[1:], strict=False):
            model.add(later >= earlier + minimum_headway_minutes)

    fleet_limit = problem.scenario_b.available_fleet_limit
    initial_terminal_1 = model.new_int_var(0, fleet_limit, "initial_terminal_1")
    initial_terminal_2 = model.new_int_var(0, fleet_limit, "initial_terminal_2")
    model.add(initial_terminal_1 + initial_terminal_2 <= fleet_limit)

    outbound = directional[ContractDirection.OUTBOUND]
    inbound = directional[ContractDirection.INBOUND]
    turnaround_terminal_1 = problem.scenario_b.turnaround_minutes.terminal_1
    turnaround_terminal_2 = problem.scenario_b.turnaround_minutes.terminal_2

    for outbound_index, outbound_trip in enumerate(outbound, start=1):
        outbound_departure = departure_by_source_id[outbound_trip.trip_id]
        ready_indicators: list[cp_model.IntVar] = []
        for inbound_index, inbound_trip in enumerate(inbound, start=1):
            indicator = model.new_bool_var(
                "ready_terminal_1_"
                f"{inbound_index:04d}_{inbound_trip.trip_id}_"
                f"by_{outbound_index:04d}_{outbound_trip.trip_id}"
            )
            ready_indicators.append(indicator)
            ready_time = (
                departure_by_source_id[inbound_trip.trip_id]
                + inbound_trip.runtime_minutes
                + turnaround_terminal_1
            )
            model.add(ready_time <= outbound_departure).only_enforce_if(indicator)
            model.add(ready_time >= outbound_departure + 1).only_enforce_if(indicator.negated())
        model.add(initial_terminal_1 + sum(ready_indicators) >= outbound_index)

    for inbound_index, inbound_trip in enumerate(inbound, start=1):
        inbound_departure = departure_by_source_id[inbound_trip.trip_id]
        ready_indicators = []
        for outbound_index, outbound_trip in enumerate(outbound, start=1):
            indicator = model.new_bool_var(
                "ready_terminal_2_"
                f"{outbound_index:04d}_{outbound_trip.trip_id}_"
                f"by_{inbound_index:04d}_{inbound_trip.trip_id}"
            )
            ready_indicators.append(indicator)
            ready_time = (
                departure_by_source_id[outbound_trip.trip_id]
                + outbound_trip.runtime_minutes
                + turnaround_terminal_2
            )
            model.add(ready_time <= inbound_departure).only_enforce_if(indicator)
            model.add(ready_time >= inbound_departure + 1).only_enforce_if(indicator.negated())
        model.add(initial_terminal_2 + sum(ready_indicators) >= inbound_index)

    limits = problem.scenario_b.terminal_occupancy_limits
    terminal_1_counts = _add_terminal_occupancy_capacity_constraints(
        model,
        terminal_name="terminal_1",
        capacity=(limits.terminal_1 if limits is not None else None),
        initial_occupancy=initial_terminal_1,
        arrival_trips=inbound,
        departure_trips=outbound,
        departure_by_source_id=departure_by_source_id,
    )
    terminal_2_counts = _add_terminal_occupancy_capacity_constraints(
        model,
        terminal_name="terminal_2",
        capacity=(limits.terminal_2 if limits is not None else None),
        initial_occupancy=initial_terminal_2,
        arrival_trips=outbound,
        departure_trips=inbound,
        departure_by_source_id=departure_by_source_id,
    )
    return _CpSatModelBundle(
        model=model,
        departure_by_source_id=departure_by_source_id,
        initial_terminal_1=initial_terminal_1,
        initial_terminal_2=initial_terminal_2,
        terminal_occupancy_binary_variable_count=(terminal_1_counts[0] + terminal_2_counts[0]),
        terminal_occupancy_constraint_count=terminal_1_counts[1] + terminal_2_counts[1],
        terminal_occupancy_arrival_event_count=terminal_1_counts[2] + terminal_2_counts[2],
    )


def _demand_problem_authority_issues(problem: ScheduleProblemV1) -> tuple[str, ...]:
    issues: list[str] = []
    if (
        problem.observed_demand_fingerprint is None
        or problem.demand_resolution is None
        or not problem.analysis_blocks
        or not problem.block_requirements
    ):
        issues.append("ORTOOLS_DEMAND_AUTHORITY_MISSING")

    blocks_by_id = {block.block_id: block for block in problem.analysis_blocks}
    requirements_by_id = {
        requirement.block_id: requirement for requirement in problem.block_requirements
    }
    if len(blocks_by_id) != len(problem.analysis_blocks) or len(requirements_by_id) != len(
        problem.block_requirements
    ):
        issues.append("ORTOOLS_DEMAND_BLOCK_ID_DUPLICATE")
    if set(blocks_by_id) != set(requirements_by_id):
        issues.append("ORTOOLS_DEMAND_BLOCK_REQUIREMENT_MISMATCH")

    supported_directions = {
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
    }
    for block in problem.analysis_blocks:
        if block.direction not in supported_directions:
            issues.append("ORTOOLS_DEMAND_BLOCK_DIRECTION_UNSUPPORTED")
        if (
            isinstance(block.start_time, bool)
            or not isinstance(block.start_time, int)
            or isinstance(block.end_time, bool)
            or not isinstance(block.end_time, int)
            or block.start_time % 60
            or block.end_time % 60
            or block.end_time <= block.start_time
        ):
            issues.append("ORTOOLS_DEMAND_BLOCK_BOUNDARY_NOT_WHOLE_MINUTE")
        if not math.isfinite(block.observed_passengers) or block.observed_passengers < 0:
            issues.append("ORTOOLS_DEMAND_VALUE_INVALID")

        requirement = requirements_by_id.get(block.block_id)
        if requirement is None:
            continue
        if (
            requirement.direction != block.direction
            or requirement.block_start != block.start_time
            or requirement.block_end != block.end_time
            or requirement.duration_minutes != (block.end_time - block.start_time) // 60
            or not math.isclose(
                requirement.passenger_demand,
                block.observed_passengers,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            issues.append("ORTOOLS_DEMAND_BLOCK_REQUIREMENT_MISMATCH")
        if (
            not math.isfinite(requirement.passenger_demand)
            or requirement.passenger_demand < 0
            or isinstance(requirement.required_trips_90, bool)
            or not isinstance(requirement.required_trips_90, int)
            or requirement.required_trips_90 < 0
            or isinstance(requirement.required_trips_85, bool)
            or not isinstance(requirement.required_trips_85, int)
            or requirement.required_trips_85 < 0
        ):
            issues.append("ORTOOLS_DEMAND_VALUE_INVALID")

    for trip in problem.scenario_b.exact_timetable:
        memberships = sum(
            block.direction == trip.direction
            and block.start_time <= trip.departure_time < block.end_time
            for block in problem.analysis_blocks
        )
        if memberships != 1:
            issues.append("ORTOOLS_DEMAND_SOURCE_TRIP_BLOCK_MEMBERSHIP_INVALID")

    deduplicated = tuple(dict.fromkeys(issues))
    if not deduplicated:
        return ()
    return (
        ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY,
        *deduplicated,
    )


def _demand_request_authority_issues(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
) -> tuple[str, ...]:
    issues: list[str] = []
    if normalized_inputs.observed_demand is None:
        issues.append("ORTOOLS_DEMAND_OBSERVATIONS_MISSING")
    resolution = b_evaluation.demand_resolution
    if resolution is None:
        issues.append("ORTOOLS_DEMAND_RESOLUTION_MISSING")
    else:
        if not resolution.blocks:
            issues.append("ORTOOLS_DEMAND_BLOCKS_MISSING")
        coverage = resolution.coverage_assessment
        if coverage is None or not coverage.directional_c_generation_supported:
            issues.append("ORTOOLS_DEMAND_DIRECTIONAL_COVERAGE_UNSUPPORTED")
    if not b_evaluation.b_block_supply:
        issues.append("ORTOOLS_DEMAND_BLOCK_REQUIREMENTS_MISSING")
    if resolution is not None:
        blocks_by_id = {block.block_id: block for block in resolution.blocks}
        requirements_by_id = {
            requirement.block_id: requirement for requirement in b_evaluation.b_block_supply
        }
        if (
            len(blocks_by_id) != len(resolution.blocks)
            or len(requirements_by_id) != len(b_evaluation.b_block_supply)
            or set(blocks_by_id) != set(requirements_by_id)
        ):
            issues.append("ORTOOLS_DEMAND_BLOCK_REQUIREMENT_MISMATCH")
        for block in resolution.blocks:
            requirement = requirements_by_id.get(block.block_id)
            if block.direction not in {
                ContractDirection.OUTBOUND,
                ContractDirection.INBOUND,
            }:
                issues.append("ORTOOLS_DEMAND_BLOCK_DIRECTION_UNSUPPORTED")
            if (
                isinstance(block.start_time, bool)
                or not isinstance(block.start_time, int)
                or isinstance(block.end_time, bool)
                or not isinstance(block.end_time, int)
                or block.start_time % 60
                or block.end_time % 60
                or block.end_time <= block.start_time
            ):
                issues.append("ORTOOLS_DEMAND_BLOCK_BOUNDARY_NOT_WHOLE_MINUTE")
            if not math.isfinite(block.observed_passengers) or block.observed_passengers < 0:
                issues.append("ORTOOLS_DEMAND_VALUE_INVALID")
            if requirement is None:
                continue
            if (
                requirement.direction != block.direction
                or requirement.block_start != block.start_time
                or requirement.block_end != block.end_time
                or not math.isclose(
                    requirement.passenger_demand,
                    block.observed_passengers,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            ):
                issues.append("ORTOOLS_DEMAND_BLOCK_REQUIREMENT_MISMATCH")
            if (
                not math.isfinite(requirement.passenger_demand)
                or requirement.passenger_demand < 0
                or isinstance(requirement.required_trips_90, bool)
                or not isinstance(requirement.required_trips_90, int)
                or requirement.required_trips_90 < 0
                or isinstance(requirement.required_trips_85, bool)
                or not isinstance(requirement.required_trips_85, int)
                or requirement.required_trips_85 < 0
            ):
                issues.append("ORTOOLS_DEMAND_VALUE_INVALID")
        for trip in normalized_inputs.scenario_b.exact_timetable:
            memberships = sum(
                block.direction == trip.direction
                and block.start_time <= trip.departure_time < block.end_time
                for block in resolution.blocks
            )
            if memberships != 1:
                issues.append("ORTOOLS_DEMAND_SOURCE_TRIP_BLOCK_MEMBERSHIP_INVALID")
    return tuple(dict.fromkeys(issues))


def _bounded_sum_var(
    model: cp_model.CpModel,
    values: list[cp_model.IntVar],
    *,
    upper_bound: int,
    name: str,
) -> cp_model.IntVar:
    result = model.new_int_var(0, upper_bound, name)
    model.add(result == sum(values))
    return result


def _build_demand_cp_sat_model(problem: ScheduleProblemV1) -> _DemandCpSatModelBundle:
    hard = _build_cp_sat_model(problem)
    model = hard.model
    directional = _ordered_directional_trips(problem)
    blocks = tuple(
        sorted(
            problem.analysis_blocks,
            key=lambda item: (
                item.direction.value,
                item.start_time,
                item.end_time,
                item.block_id,
            ),
        )
    )
    requirements = {item.block_id: item for item in problem.block_requirements}
    membership_by_source_and_block: dict[tuple[str, str], cp_model.IntVar] = {}
    block_memberships: dict[str, list[cp_model.IntVar]] = {block.block_id: [] for block in blocks}

    for direction, trips in directional.items():
        compatible_blocks = tuple(block for block in blocks if block.direction == direction)
        for trip in trips:
            departure = hard.departure_by_source_id[trip.trip_id]
            trip_memberships: list[cp_model.IntVar] = []
            for block in compatible_blocks:
                start_minute = block.start_time // 60
                end_minute = block.end_time // 60
                at_or_after_start = model.new_bool_var(
                    f"at_or_after_start_{trip.trip_id}_{block.block_id}"
                )
                before_end = model.new_bool_var(f"before_end_{trip.trip_id}_{block.block_id}")
                member = model.new_bool_var(f"member_{trip.trip_id}_{block.block_id}")
                model.add(departure >= start_minute).only_enforce_if(at_or_after_start)
                model.add(departure <= start_minute - 1).only_enforce_if(
                    at_or_after_start.negated()
                )
                model.add(departure <= end_minute - 1).only_enforce_if(before_end)
                model.add(departure >= end_minute).only_enforce_if(before_end.negated())
                model.add(member <= at_or_after_start)
                model.add(member <= before_end)
                model.add(member >= at_or_after_start + before_end - 1)
                membership_by_source_and_block[(trip.trip_id, block.block_id)] = member
                block_memberships[block.block_id].append(member)
                trip_memberships.append(member)
            model.add(sum(trip_memberships) == 1)

    block_trip_count_by_id: dict[str, cp_model.IntVar] = {}
    no_service_vars: list[cp_model.IntVar] = []
    critical_vars: list[cp_model.IntVar] = []
    critical_shortage_vars: list[cp_model.IntVar] = []
    planning_warning_vars: list[cp_model.IntVar] = []
    planning_shortage_vars: list[cp_model.IntVar] = []
    total_trip_count = len(problem.scenario_b.exact_timetable)

    for block in blocks:
        members = block_memberships[block.block_id]
        block_count = model.new_int_var(
            0,
            len(directional[block.direction]),
            f"block_trip_count_{block.block_id}",
        )
        model.add(block_count == sum(members))
        block_trip_count_by_id[block.block_id] = block_count
        requirement = requirements[block.block_id]

        no_service = model.new_bool_var(f"no_service_{block.block_id}")
        if requirement.passenger_demand > 0:
            model.add(block_count == 0).only_enforce_if(no_service)
            model.add(block_count >= 1).only_enforce_if(no_service.negated())
        else:
            model.add(no_service == 0)
        no_service_vars.append(no_service)

        required_90 = requirement.required_trips_90
        critical = model.new_bool_var(f"critical_{block.block_id}")
        critical_shortage = model.new_int_var(
            0,
            required_90,
            f"critical_shortage_{block.block_id}",
        )
        if required_90 == 0:
            model.add(critical == 0)
            model.add(critical_shortage == 0)
        else:
            model.add(block_count <= required_90 - 1).only_enforce_if(critical)
            model.add(block_count >= required_90).only_enforce_if(critical.negated())
            model.add_max_equality(
                critical_shortage,
                [0, required_90 - block_count],
            )
        critical_vars.append(critical)
        critical_shortage_vars.append(critical_shortage)

        required_85 = requirement.required_trips_85
        planning_warning = model.new_bool_var(f"planning_warning_{block.block_id}")
        planning_shortage = model.new_int_var(
            0,
            required_85,
            f"planning_shortage_{block.block_id}",
        )
        if required_85 == 0:
            model.add(planning_warning == 0)
            model.add(planning_shortage == 0)
        else:
            model.add(block_count <= required_85 - 1).only_enforce_if(planning_warning)
            model.add(block_count >= required_85).only_enforce_if(planning_warning.negated())
            model.add_max_equality(
                planning_shortage,
                [0, required_85 - block_count],
            )
        planning_warning_vars.append(planning_warning)
        planning_shortage_vars.append(planning_shortage)

    shift_abs_vars: list[cp_model.IntVar] = []
    shift_abs_bounds: list[int] = []
    shifted_vars: list[cp_model.IntVar] = []
    maximum_possible_shift = 0
    for direction, trips in directional.items():
        first_minute, last_minute = _directional_window_minutes(problem, direction)
        for trip in trips:
            departure = hard.departure_by_source_id[trip.trip_id]
            source_minute = trip.departure_time // 60
            shift_bound = max(
                abs(first_minute - source_minute),
                abs(last_minute - source_minute),
            )
            maximum_possible_shift = max(maximum_possible_shift, shift_bound)
            shift_abs = model.new_int_var(
                0,
                shift_bound,
                f"shift_abs_{trip.trip_id}",
            )
            shifted = model.new_bool_var(f"shifted_{trip.trip_id}")
            model.add_abs_equality(shift_abs, departure - source_minute)
            model.add(shift_abs >= 1).only_enforce_if(shifted)
            model.add(shift_abs == 0).only_enforce_if(shifted.negated())
            shift_abs_vars.append(shift_abs)
            shift_abs_bounds.append(shift_bound)
            shifted_vars.append(shifted)

    no_service_count = _bounded_sum_var(
        model,
        no_service_vars,
        upper_bound=len(blocks),
        name=_DEMAND_OBJECTIVE_NAMES[0],
    )
    critical_count = _bounded_sum_var(
        model,
        critical_vars,
        upper_bound=len(blocks),
        name=_DEMAND_OBJECTIVE_NAMES[1],
    )
    total_critical_shortage = _bounded_sum_var(
        model,
        critical_shortage_vars,
        upper_bound=sum(item.required_trips_90 for item in requirements.values()),
        name=_DEMAND_OBJECTIVE_NAMES[2],
    )
    planning_warning_count = _bounded_sum_var(
        model,
        planning_warning_vars,
        upper_bound=len(blocks),
        name=_DEMAND_OBJECTIVE_NAMES[3],
    )
    total_planning_shortage = _bounded_sum_var(
        model,
        planning_shortage_vars,
        upper_bound=sum(item.required_trips_85 for item in requirements.values()),
        name=_DEMAND_OBJECTIVE_NAMES[4],
    )
    shifted_trip_count = _bounded_sum_var(
        model,
        shifted_vars,
        upper_bound=total_trip_count,
        name=_DEMAND_OBJECTIVE_NAMES[5],
    )
    total_shift_minutes = _bounded_sum_var(
        model,
        shift_abs_vars,
        upper_bound=sum(shift_abs_bounds),
        name=_DEMAND_OBJECTIVE_NAMES[6],
    )
    maximum_shift_minutes = model.new_int_var(
        0,
        maximum_possible_shift,
        _DEMAND_OBJECTIVE_NAMES[7],
    )
    model.add_max_equality(maximum_shift_minutes, shift_abs_vars)

    stage_values = (
        no_service_count,
        critical_count,
        total_critical_shortage,
        planning_warning_count,
        total_planning_shortage,
        shifted_trip_count,
        total_shift_minutes,
        maximum_shift_minutes,
    )
    return _DemandCpSatModelBundle(
        hard=hard,
        membership_by_source_and_block=membership_by_source_and_block,
        block_trip_count_by_id=block_trip_count_by_id,
        stages=tuple(
            _DemandObjectiveStage(name=name, value=value)
            for name, value in zip(
                _DEMAND_OBJECTIVE_NAMES,
                stage_values,
                strict=True,
            )
        ),
    )


def _map_cp_sat_status(status: cp_model.CpSolverStatus) -> NativeSolverStatus:
    return {
        cp_model.OPTIMAL: NativeSolverStatus.OPTIMAL,
        cp_model.FEASIBLE: NativeSolverStatus.FEASIBLE,
        cp_model.INFEASIBLE: NativeSolverStatus.INFEASIBLE,
        cp_model.MODEL_INVALID: NativeSolverStatus.MODEL_INVALID,
        cp_model.UNKNOWN: NativeSolverStatus.UNKNOWN,
    }[status]


def _solver_controls(problem: ScheduleProblemV1) -> tuple[float | None, int, int]:
    policy = problem.solver_policy
    return (
        policy.time_limit_seconds,
        policy.worker_count if policy.worker_count is not None else 1,
        policy.random_seed if policy.random_seed is not None else 0,
    )


def _solver_limitations(problem: ScheduleProblemV1) -> tuple[str, ...]:
    time_limit, worker_count, random_seed = _solver_controls(problem)
    configured_time_limit = "none" if time_limit is None else f"{time_limit:g} seconds"
    return (
        f"OR-Tools version {ortools.__version__}; configured time limit: "
        f"{configured_time_limit}; worker count: {worker_count}; random seed: {random_seed}.",
        "The CP-SAT model is feasibility-only; it does not optimize demand, headway, "
        "service quality, trip shifts, or fleet size.",
        "Raw headway regimes describe the solved timetable for Contract V1 reconciliation; "
        "they are not demand-derived or headway-optimized.",
    )


def _model_invalid_result(
    problem: ScheduleProblemV1,
    adapter_id: str,
    started: float,
    issues: tuple[str, ...],
) -> SolverRunResultV1:
    adapter_limitations = (
        _demand_solver_limitations(problem)
        if adapter_id == "ortools_cp_sat_demand_v1"
        else _solver_limitations(problem)
    )
    return SolverRunResultV1(
        execution_status=SolverExecutionStatus.COMPLETED,
        solver_status=NativeSolverStatus.MODEL_INVALID,
        solver_adapter=adapter_id,
        solve_duration_seconds=max(0.0, time.perf_counter() - started),
        candidate=None,
        explanations=tuple(f"{issue}: OR-Tools adapter rejected the problem." for issue in issues),
        limitations=(
            *adapter_limitations,
            "MODEL_INVALID identifies an adapter capability or integration defect, "
            "not route, timetable, fleet, or locked-parameter infeasibility.",
        ),
    )


def _previous_headways(
    rows: tuple[ExactTimetableTrip, ...],
    departure_by_source_id: dict[str, int],
) -> dict[str, float | None]:
    output: dict[str, float | None] = {}
    previous: int | None = None
    for trip in rows:
        departure = departure_by_source_id[trip.trip_id]
        output[trip.trip_id] = None if previous is None else float(departure - previous)
        previous = departure
    return output


def _regularity_status(headways: tuple[float, ...]) -> str:
    if not headways or max(headways) == min(headways):
        return "REGULAR"
    if max(headways) - min(headways) <= 1:
        return "BALANCED_ROUNDING"
    return "EXCEPTIONAL"


def _build_raw_candidate(
    problem: ScheduleProblemV1,
    bundle: _CpSatModelBundle,
    solver: cp_model.CpSolver,
    status: NativeSolverStatus,
    solve_duration_seconds: float,
    adapter_id: str,
    *,
    regime_ids: dict[ContractDirection, str] | None = None,
    boundary_reason: str = _FEASIBILITY_BOUNDARY_REASON,
    change_reason: str = "OR-Tools fixed-resource technical-feasibility solve.",
    explanation_override: str | None = None,
    limitations_override: tuple[str, ...] | None = None,
) -> RawScheduleCandidateV1:
    effective_regime_ids = regime_ids or _REGIME_IDS
    directional = _ordered_directional_trips(problem)
    source_order = tuple(
        sorted(
            problem.scenario_b.exact_timetable,
            key=lambda item: (item.departure_time, item.trip_id),
        )
    )
    c_id_by_source_id = {
        trip.trip_id: f"C-ORTOOLS-{index:04d}" for index, trip in enumerate(source_order, start=1)
    }
    solved_minutes = {
        trip.trip_id: solver.value(bundle.departure_by_source_id[trip.trip_id])
        for trip in source_order
    }
    b_minutes = {trip.trip_id: trip.departure_time // 60 for trip in source_order}
    previous_b: dict[str, float | None] = {}
    previous_c: dict[str, float | None] = {}
    for trips in directional.values():
        previous_b.update(_previous_headways(trips, b_minutes))
        previous_c.update(_previous_headways(trips, solved_minutes))

    raw_rows = [
        RawCandidateTripV1(
            c_trip_id=c_id_by_source_id[trip.trip_id],
            source_b_trip_id=trip.trip_id,
            direction=trip.direction,
            departure_terminal=trip.departure_terminal,
            b_departure_time=trip.departure_time,
            c_departure_time=solved_minutes[trip.trip_id] * 60,
            arrival_time=(solved_minutes[trip.trip_id] + trip.runtime_minutes) * 60,
            runtime_minutes=trip.runtime_minutes,
            shift_minutes=float(solved_minutes[trip.trip_id] - b_minutes[trip.trip_id]),
            previous_b_headway=previous_b[trip.trip_id],
            previous_c_headway=previous_c[trip.trip_id],
            headway_regime_id=effective_regime_ids[trip.direction],
            change_reason=change_reason,
        )
        for trip in source_order
    ]
    exact_timetable = tuple(
        sorted(raw_rows, key=lambda item: (item.c_departure_time, item.c_trip_id))
    )

    regimes: list[RawHeadwayRegimeV1] = []
    singleton_direction = False
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        members = tuple(
            sorted(
                (trip for trip in exact_timetable if trip.direction == direction),
                key=lambda item: (item.c_departure_time, item.c_trip_id),
            )
        )
        headways = tuple(
            float((later.c_departure_time - earlier.c_departure_time) // 60)
            for earlier, later in zip(members, members[1:], strict=False)
        )
        singleton_direction = singleton_direction or len(members) == 1
        target = sum(headways) / len(headways) if headways else _SINGLETON_TARGET_HEADWAY_MINUTES
        regimes.append(
            RawHeadwayRegimeV1(
                regime_id=effective_regime_ids[direction],
                direction=direction,
                start_time=members[0].c_departure_time,
                end_time=members[-1].c_departure_time,
                trip_count=len(members),
                target_headway=target,
                actual_headway_sequence=headways,
                boundary_reason=boundary_reason,
                legacy_regularity_status=_regularity_status(headways),
            )
        )
    raw_regimes = tuple(regimes)
    explanation = explanation_override or (
        "CP-SAT proved technical feasibility for the encoded fixed-resource model; "
        "no service-quality objective was optimized."
        if status == NativeSolverStatus.OPTIMAL
        else "CP-SAT found a technical-feasibility candidate for the encoded fixed-resource "
        "model; no service-quality objective was optimized."
    )
    limitations = (
        limitations_override if limitations_override is not None else _solver_limitations(problem)
    )
    if singleton_direction:
        limitations += (
            "A one-trip direction has no measurable headway; its descriptive regime uses "
            f"the positive {_SINGLETON_TARGET_HEADWAY_MINUTES:g}-minute placeholder target.",
        )
    return RawScheduleCandidateV1(
        solver_status=status,
        solver_adapter=adapter_id,
        solve_duration_seconds=solve_duration_seconds,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=problem.problem_fingerprint,
            solver_adapter=adapter_id,
            exact_timetable=exact_timetable,
            headway_regimes=raw_regimes,
        ),
        exact_timetable=exact_timetable,
        headway_regimes=raw_regimes,
        explanation=explanation,
        limitations=limitations,
    )


@dataclass(frozen=True, slots=True)
class OrToolsCpSatScheduleSolver:
    adapter_id: ClassVar[str] = "ortools_cp_sat_v1"

    def solve(self, problem: ScheduleProblemV1) -> SolverRunResultV1:
        started = time.perf_counter()
        issues = _adapter_capability_issues(problem, self.adapter_id)
        if issues:
            return _model_invalid_result(problem, self.adapter_id, started, issues)
        try:
            bundle = _build_cp_sat_model(problem)
            model_error = bundle.model.validate()
            if model_error:
                return _model_invalid_result(
                    problem,
                    self.adapter_id,
                    started,
                    ("ORTOOLS_CP_SAT_MODEL_VALIDATION_FAILED",),
                )
            solver = cp_model.CpSolver()
            time_limit, worker_count, random_seed = _solver_controls(problem)
            if time_limit is not None:
                solver.parameters.max_time_in_seconds = time_limit
            solver.parameters.num_search_workers = worker_count
            solver.parameters.random_seed = random_seed
            native_status = _map_cp_sat_status(solver.solve(bundle.model))
            duration = max(0.0, time.perf_counter() - started)
            candidate = (
                _build_raw_candidate(
                    problem,
                    bundle,
                    solver,
                    native_status,
                    duration,
                    self.adapter_id,
                )
                if native_status in {NativeSolverStatus.OPTIMAL, NativeSolverStatus.FEASIBLE}
                else None
            )
            explanation = (
                candidate.explanation
                if candidate is not None
                else {
                    NativeSolverStatus.INFEASIBLE: (
                        "CP-SAT proved the encoded fixed-resource model infeasible."
                    ),
                    NativeSolverStatus.MODEL_INVALID: (
                        "CP-SAT reported that the encoded model is invalid."
                    ),
                    NativeSolverStatus.UNKNOWN: (
                        "CP-SAT returned UNKNOWN; no feasibility or infeasibility proof "
                        "is available."
                    ),
                }[native_status]
            )
            limitations = (
                candidate.limitations if candidate is not None else _solver_limitations(problem)
            )
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=native_status,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=duration,
                candidate=candidate,
                explanations=(explanation,),
                limitations=limitations,
            )
        except Exception:
            return _model_invalid_result(
                problem,
                self.adapter_id,
                started,
                ("ORTOOLS_ADAPTER_FAILURE",),
            )


def _demand_solver_limitations(problem: ScheduleProblemV1) -> tuple[str, ...]:
    time_limit, worker_count, random_seed = _solver_controls(problem)
    configured_time_limit = "none" if time_limit is None else f"{time_limit:g} seconds"
    return (
        f"OR-Tools version {ortools.__version__}; total staged-solve time limit: "
        f"{configured_time_limit}; worker count: {worker_count}; random seed: {random_seed}.",
        "Milestone 4A1 optimizes no-service and one-sided overload protection before "
        "provisional B-preservation shift tie-breaks.",
        "Headway quality, service gaps, sustained-demand allocation, regime transitions, "
        "and fleet size are not optimized in Milestone 4A1.",
        "Raw headway regimes are descriptive reconciliation output only; they are not "
        "demand-derived or headway-optimized.",
    )


def _recompute_demand_objective_vector_v1(
    problem: ScheduleProblemV1,
    candidate: RawScheduleCandidateV1,
) -> tuple[int, int, int, int, int, int, int, int]:
    """Recompute the 4A1 vector without using CP-SAT variables or solver values."""
    return _recompute_solver_neutral_demand_vector_v1(problem, candidate)


def _demand_candidate_explanation(
    *,
    status: NativeSolverStatus,
    attempted: tuple[str, ...],
    proven: tuple[tuple[str, int], ...],
    vector: tuple[int, ...],
) -> str:
    proven_by_name = dict(proven)
    stage_descriptions = ", ".join(
        f"{name}={value}" + (" (proven)" if name in proven_by_name else " (candidate; unproven)")
        for name, value in zip(_DEMAND_OBJECTIVE_NAMES, vector, strict=True)
    )
    attempted_text = ", ".join(attempted) if attempted else "none"
    proven_text = ", ".join(f"{name}={value}" for name, value in proven) if proven else "none"
    return (
        f"CP-SAT demand-priority staged solve returned {status.value}. "
        f"Objective stages attempted: {attempted_text}. "
        f"Objective stages proven optimal: {proven_text}. "
        f"Emitted candidate objective vector: {stage_descriptions}. "
        "Headway and service-gap quality were not optimized in Milestone 4A1."
    )


def _build_demand_candidate(
    problem: ScheduleProblemV1,
    bundle: _DemandCpSatModelBundle,
    solver: cp_model.CpSolver,
    *,
    status: NativeSolverStatus,
    duration: float,
    attempted: tuple[str, ...],
    proven: tuple[tuple[str, int], ...],
    adapter_id: str,
) -> RawScheduleCandidateV1:
    candidate = _build_raw_candidate(
        problem,
        bundle.hard,
        solver,
        status,
        duration,
        adapter_id,
        regime_ids=_DEMAND_REGIME_IDS,
        boundary_reason=_DEMAND_BOUNDARY_REASON,
        change_reason="OR-Tools lexicographic demand-priority optimization.",
        explanation_override="Demand objective explanation pending independent recomputation.",
        limitations_override=_demand_solver_limitations(problem),
    )
    vector = _recompute_demand_objective_vector_v1(problem, candidate)
    for name, proven_value in proven:
        vector_value = vector[_DEMAND_OBJECTIVE_NAMES.index(name)]
        if vector_value != proven_value:
            raise ValueError(
                f"Independently recomputed {name}={vector_value} does not match "
                f"the solver-proven value {proven_value}"
            )
    return replace(
        candidate,
        explanation=_demand_candidate_explanation(
            status=status,
            attempted=attempted,
            proven=proven,
            vector=vector,
        ),
    )


def _demand_non_candidate_result(
    problem: ScheduleProblemV1,
    *,
    adapter_id: str,
    status: NativeSolverStatus,
    duration: float,
    attempted: tuple[str, ...],
    proven: tuple[tuple[str, int], ...],
    detail: str,
) -> SolverRunResultV1:
    proven_text = ", ".join(f"{name}={value}" for name, value in proven) if proven else "none"
    attempted_text = ", ".join(attempted) if attempted else "none"
    return SolverRunResultV1(
        execution_status=SolverExecutionStatus.COMPLETED,
        solver_status=status,
        solver_adapter=adapter_id,
        solve_duration_seconds=duration,
        candidate=None,
        explanations=(
            f"{detail} Objective stages attempted: {attempted_text}. "
            f"Objective stages proven optimal: {proven_text}.",
        ),
        limitations=_demand_solver_limitations(problem),
    )


@dataclass(frozen=True, slots=True)
class OrToolsCpSatDemandOptimizationSolver:
    adapter_id: ClassVar[str] = "ortools_cp_sat_demand_v1"

    def solve(self, problem: ScheduleProblemV1) -> SolverRunResultV1:
        started = time.perf_counter()
        issues = (
            *_adapter_capability_issues(problem, self.adapter_id),
            *_demand_problem_authority_issues(problem),
        )
        issues = tuple(dict.fromkeys(issues))
        if issues:
            return _model_invalid_result(problem, self.adapter_id, started, issues)
        try:
            bundle = _build_demand_cp_sat_model(problem)
            model_error = bundle.hard.model.validate()
            if model_error:
                return _model_invalid_result(
                    problem,
                    self.adapter_id,
                    started,
                    ("ORTOOLS_CP_SAT_MODEL_VALIDATION_FAILED",),
                )

            time_limit, worker_count, random_seed = _solver_controls(problem)
            attempted: list[str] = []
            proven: list[tuple[str, int]] = []
            latest_solver: cp_model.CpSolver | None = None

            for stage in bundle.stages:
                elapsed = max(0.0, time.perf_counter() - started)
                remaining = None if time_limit is None else max(0.0, time_limit - elapsed)
                if remaining is not None and remaining <= 0:
                    duration = max(0.0, time.perf_counter() - started)
                    if latest_solver is None:
                        return _demand_non_candidate_result(
                            problem,
                            adapter_id=self.adapter_id,
                            status=NativeSolverStatus.UNKNOWN,
                            duration=duration,
                            attempted=tuple(attempted),
                            proven=tuple(proven),
                            detail="The total adapter time budget expired before the first stage.",
                        )
                    candidate = _build_demand_candidate(
                        problem,
                        bundle,
                        latest_solver,
                        status=NativeSolverStatus.FEASIBLE,
                        duration=duration,
                        attempted=tuple(attempted),
                        proven=tuple(proven),
                        adapter_id=self.adapter_id,
                    )
                    return SolverRunResultV1(
                        execution_status=SolverExecutionStatus.COMPLETED,
                        solver_status=NativeSolverStatus.FEASIBLE,
                        solver_adapter=self.adapter_id,
                        solve_duration_seconds=duration,
                        candidate=candidate,
                        explanations=(candidate.explanation,),
                        limitations=candidate.limitations,
                    )

                attempted.append(stage.name)
                bundle.hard.model.minimize(stage.value)
                solver = cp_model.CpSolver()
                if remaining is not None:
                    solver.parameters.max_time_in_seconds = remaining
                solver.parameters.num_search_workers = worker_count
                solver.parameters.random_seed = random_seed
                native_status = _map_cp_sat_status(solver.solve(bundle.hard.model))
                duration = max(0.0, time.perf_counter() - started)

                if native_status == NativeSolverStatus.OPTIMAL:
                    stage_value = int(solver.value(stage.value))
                    proven.append((stage.name, stage_value))
                    bundle.hard.model.add(stage.value == stage_value)
                    latest_solver = solver
                    continue

                if native_status == NativeSolverStatus.FEASIBLE:
                    candidate = _build_demand_candidate(
                        problem,
                        bundle,
                        solver,
                        status=NativeSolverStatus.FEASIBLE,
                        duration=duration,
                        attempted=tuple(attempted),
                        proven=tuple(proven),
                        adapter_id=self.adapter_id,
                    )
                    return SolverRunResultV1(
                        execution_status=SolverExecutionStatus.COMPLETED,
                        solver_status=NativeSolverStatus.FEASIBLE,
                        solver_adapter=self.adapter_id,
                        solve_duration_seconds=duration,
                        candidate=candidate,
                        explanations=(candidate.explanation,),
                        limitations=candidate.limitations,
                    )

                if native_status == NativeSolverStatus.UNKNOWN and latest_solver is not None:
                    candidate = _build_demand_candidate(
                        problem,
                        bundle,
                        latest_solver,
                        status=NativeSolverStatus.FEASIBLE,
                        duration=duration,
                        attempted=tuple(attempted),
                        proven=tuple(proven),
                        adapter_id=self.adapter_id,
                    )
                    return SolverRunResultV1(
                        execution_status=SolverExecutionStatus.COMPLETED,
                        solver_status=NativeSolverStatus.FEASIBLE,
                        solver_adapter=self.adapter_id,
                        solve_duration_seconds=duration,
                        candidate=candidate,
                        explanations=(candidate.explanation,),
                        limitations=candidate.limitations,
                    )

                return _demand_non_candidate_result(
                    problem,
                    adapter_id=self.adapter_id,
                    status=native_status,
                    duration=duration,
                    attempted=tuple(attempted),
                    proven=tuple(proven),
                    detail={
                        NativeSolverStatus.UNKNOWN: (
                            "CP-SAT returned UNKNOWN before finding a candidate; "
                            "no feasibility or infeasibility proof is available."
                        ),
                        NativeSolverStatus.INFEASIBLE: (
                            "CP-SAT proved the encoded fixed-resource demand model infeasible."
                        ),
                        NativeSolverStatus.MODEL_INVALID: (
                            "CP-SAT reported that the encoded demand model is invalid."
                        ),
                    }[native_status],
                )

            duration = max(0.0, time.perf_counter() - started)
            if latest_solver is None:
                return _demand_non_candidate_result(
                    problem,
                    adapter_id=self.adapter_id,
                    status=NativeSolverStatus.UNKNOWN,
                    duration=duration,
                    attempted=tuple(attempted),
                    proven=tuple(proven),
                    detail="No demand objective stage produced a candidate.",
                )
            candidate = _build_demand_candidate(
                problem,
                bundle,
                latest_solver,
                status=NativeSolverStatus.OPTIMAL,
                duration=duration,
                attempted=tuple(attempted),
                proven=tuple(proven),
                adapter_id=self.adapter_id,
            )
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.OPTIMAL,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=duration,
                candidate=candidate,
                explanations=(candidate.explanation,),
                limitations=candidate.limitations,
            )
        except Exception:
            return _model_invalid_result(
                problem,
                self.adapter_id,
                started,
                ("ORTOOLS_ADAPTER_FAILURE",),
            )


def build_ortools_demand_optimization_request_v1(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    *,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    solver_policy: SolverPolicyV1 | None = None,
) -> tuple[
    ScheduleGenerationContextV1,
    OrToolsCpSatDemandOptimizationSolver,
]:
    request_issues = _demand_request_authority_issues(
        normalized_inputs,
        b_evaluation,
    )
    if request_issues:
        raise ScheduleProblemError(
            f"{ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY}: "
            + ", ".join(request_issues),
            code=ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY,
            codes=(
                ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY,
                *request_issues,
            ),
        )
    problem = build_schedule_problem_v1(
        normalized_inputs,
        b_evaluation,
        solver_adapter=OrToolsCpSatDemandOptimizationSolver.adapter_id,
        adapter_context_fingerprint=empty_adapter_context_fingerprint(),
        evaluation_policy=evaluation_policy,
        solver_policy=solver_policy,
        direction_trip_lock_mode=DirectionTripLockMode.FIXED_BY_DIRECTION,
        fleet_constraint_mode=FleetConstraintMode.AVAILABLE_UPPER_BOUND,
        initial_fleet_positioning_mode=InitialFleetPositioningMode.SOLVER_DETERMINED,
        boundary_convention=BoundaryConvention.HALF_OPEN,
    )
    problem_issues = _demand_problem_authority_issues(problem)
    if problem_issues:
        raise ScheduleProblemError(
            f"{ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY}: "
            + ", ".join(problem_issues[1:]),
            code=ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY,
            codes=problem_issues,
        )
    generation_context = build_schedule_generation_context_v1(
        problem,
        normalized_inputs,
        b_evaluation,
        evaluation_policy,
    )
    return generation_context, OrToolsCpSatDemandOptimizationSolver()


def build_ortools_schedule_request_v1(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    *,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    solver_policy: SolverPolicyV1 | None = None,
) -> tuple[ScheduleGenerationContextV1, OrToolsCpSatScheduleSolver]:
    problem = build_schedule_problem_v1(
        normalized_inputs,
        b_evaluation,
        solver_adapter=OrToolsCpSatScheduleSolver.adapter_id,
        adapter_context_fingerprint=empty_adapter_context_fingerprint(),
        evaluation_policy=evaluation_policy,
        solver_policy=solver_policy,
        direction_trip_lock_mode=DirectionTripLockMode.FIXED_BY_DIRECTION,
        fleet_constraint_mode=FleetConstraintMode.AVAILABLE_UPPER_BOUND,
        initial_fleet_positioning_mode=InitialFleetPositioningMode.SOLVER_DETERMINED,
        boundary_convention=BoundaryConvention.HALF_OPEN,
    )
    generation_context = build_schedule_generation_context_v1(
        problem,
        normalized_inputs,
        b_evaluation,
        evaluation_policy,
    )
    return generation_context, OrToolsCpSatScheduleSolver()


__all__ = [
    "OrToolsCpSatDemandOptimizationSolver",
    "OrToolsCpSatScheduleSolver",
    "build_ortools_demand_optimization_request_v1",
    "build_ortools_schedule_request_v1",
]
