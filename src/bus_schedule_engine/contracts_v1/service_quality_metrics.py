"""Solver-neutral service-quality objective metrics for fixed-resource schedules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TypeAlias

from .exact_demand_authority import (
    _ExactDemandAuthority,
    _ExactDemandAuthorityError,
    _scale_exact_demand_authority,
)
from .models import ContractDirection
from .regime_headway_policy import (
    _analyze_regime_headways,
    _RegimeHeadwayPolicyError,
)
from .solver_models import (
    RawCandidateTripV1,
    RawScheduleCandidateV1,
    ScheduleProblemV1,
    ScheduleSolutionV1,
    SolutionTripV1,
)

SERVICE_QUALITY_OBJECTIVE_NAMES_V1: tuple[str, ...] = (
    "no_service_block_count",
    "critical_block_count",
    "total_critical_shortage_trips",
    "planning_warning_block_count",
    "total_planning_shortage_trips",
    "maximum_positive_demand_headway_minutes",
    "total_positive_demand_block_max_gap_minutes",
    "directional_demand_alignment_error",
    "maximum_within_regime_headway_change_minutes",
    "total_within_regime_headway_change_minutes",
    "maximum_regime_transition_headway_jump_minutes",
    "total_regime_transition_headway_jump_minutes",
    "shifted_trip_count",
    "total_shift_minutes",
    "maximum_shift_minutes",
)

_MAX_DEMAND_DECIMAL_PLACES = 6
_SAFE_CP_SAT_INTEGER = (1 << 62) - 1
_ScheduleTrip: TypeAlias = RawCandidateTripV1 | SolutionTripV1


class _QualityModelError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _ScaledDirectionalDemand:
    scale: int
    weight_by_block_id: dict[str, int]
    total_by_direction: dict[ContractDirection, int]
    total_alignment_upper_bound: int


def _decimal_places(value: Decimal) -> int:
    return max(0, -value.as_tuple().exponent)


def _scaled_directional_demand(
    problem: ScheduleProblemV1,
    exact_demand_authority: _ExactDemandAuthority | None = None,
) -> _ScaledDirectionalDemand:
    if exact_demand_authority is not None:
        try:
            exact = _scale_exact_demand_authority(
                exact_demand_authority,
                problem,
            )
        except _ExactDemandAuthorityError as exc:
            raise _QualityModelError(exc.code) from exc
        return _ScaledDirectionalDemand(
            scale=exact.scale,
            weight_by_block_id=exact.weight_by_block_id,
            total_by_direction=exact.total_by_direction,
            total_alignment_upper_bound=exact.total_alignment_upper_bound,
        )

    decimal_by_block: dict[str, Decimal] = {}
    decimal_places = 0
    for requirement in problem.block_requirements:
        try:
            value = Decimal(str(requirement.passenger_demand))
        except (InvalidOperation, ValueError) as exc:
            raise _QualityModelError("ORTOOLS_QUALITY_DEMAND_DECIMAL_INVALID") from exc
        if not value.is_finite() or value < 0:
            raise _QualityModelError("ORTOOLS_QUALITY_DEMAND_DECIMAL_INVALID")
        places = _decimal_places(value)
        if places > _MAX_DEMAND_DECIMAL_PLACES:
            raise _QualityModelError("ORTOOLS_QUALITY_DEMAND_PRECISION_UNSUPPORTED")
        decimal_places = max(decimal_places, places)
        decimal_by_block[requirement.block_id] = value

    scale = 10**decimal_places
    weight_by_block_id: dict[str, int] = {}
    for block_id, value in decimal_by_block.items():
        scaled = value * scale
        if scaled != scaled.to_integral_value():
            raise _QualityModelError("ORTOOLS_QUALITY_DEMAND_PRECISION_UNSUPPORTED")
        weight = int(scaled)
        if weight < 0 or weight > _SAFE_CP_SAT_INTEGER:
            raise _QualityModelError("ORTOOLS_QUALITY_DEMAND_INTEGER_UNSAFE")
        weight_by_block_id[block_id] = weight

    total_by_direction: dict[ContractDirection, int] = {}
    total_alignment_upper_bound = 0
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        directional_weights = [
            weight_by_block_id[block.block_id]
            for block in problem.analysis_blocks
            if block.direction == direction
        ]
        total_weight = sum(directional_weights)
        trip_count = (
            problem.scenario_b.trips_by_direction.outbound
            if direction == ContractDirection.OUTBOUND
            else problem.scenario_b.trips_by_direction.inbound
        )
        cross_product = trip_count * total_weight
        directional_bound = 2 * cross_product
        if (
            total_weight > _SAFE_CP_SAT_INTEGER
            or cross_product > _SAFE_CP_SAT_INTEGER
            or directional_bound > _SAFE_CP_SAT_INTEGER
            or total_alignment_upper_bound + directional_bound > _SAFE_CP_SAT_INTEGER
        ):
            raise _QualityModelError("ORTOOLS_QUALITY_DEMAND_INTEGER_UNSAFE")
        if any(trip_count * weight > _SAFE_CP_SAT_INTEGER for weight in directional_weights):
            raise _QualityModelError("ORTOOLS_QUALITY_DEMAND_INTEGER_UNSAFE")
        total_by_direction[direction] = total_weight
        total_alignment_upper_bound += directional_bound
    return _ScaledDirectionalDemand(
        scale=scale,
        weight_by_block_id=weight_by_block_id,
        total_by_direction=total_by_direction,
        total_alignment_upper_bound=total_alignment_upper_bound,
    )


def _schedule_trips(
    schedule: RawScheduleCandidateV1 | ScheduleSolutionV1,
) -> tuple[_ScheduleTrip, ...]:
    if isinstance(schedule, RawScheduleCandidateV1):
        return schedule.exact_timetable
    if isinstance(schedule, ScheduleSolutionV1):
        return schedule.c_exact_timetable
    raise TypeError("schedule must be a RawScheduleCandidateV1 or ScheduleSolutionV1")


def _directional_schedule_trips(
    schedule: RawScheduleCandidateV1 | ScheduleSolutionV1,
) -> dict[ContractDirection, tuple[_ScheduleTrip, ...]]:
    trips = _schedule_trips(schedule)
    return {
        direction: tuple(
            sorted(
                (trip for trip in trips if trip.direction == direction),
                key=lambda item: (item.c_departure_time, item.c_trip_id),
            )
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    }


def _recompute_demand_objective_vector_v1(
    problem: ScheduleProblemV1,
    schedule: RawScheduleCandidateV1 | ScheduleSolutionV1,
) -> tuple[int, int, int, int, int, int, int, int]:
    blocks = {block.block_id: block for block in problem.analysis_blocks}
    requirements = {item.block_id: item for item in problem.block_requirements}
    counts = {block_id: 0 for block_id in blocks}
    source_by_id = {trip.trip_id: trip for trip in problem.scenario_b.exact_timetable}
    trips = _schedule_trips(schedule)
    if {trip.source_b_trip_id for trip in trips} != set(source_by_id):
        raise ValueError("Schedule source mapping does not match ScheduleProblemV1")

    shifts: list[int] = []
    for trip in trips:
        memberships = [
            block_id
            for block_id, block in blocks.items()
            if block.direction == trip.direction
            and block.start_time <= trip.c_departure_time < block.end_time
        ]
        if len(memberships) != 1:
            raise ValueError(
                f"Schedule trip {trip.c_trip_id} does not have exactly one demand block"
            )
        counts[memberships[0]] += 1
        source = source_by_id[trip.source_b_trip_id]
        delta_seconds = abs(trip.c_departure_time - source.departure_time)
        if delta_seconds % 60:
            raise ValueError("Schedule departure shift is not a whole number of minutes")
        shifts.append(delta_seconds // 60)

    no_service = sum(
        requirements[block_id].passenger_demand > 0 and count == 0
        for block_id, count in counts.items()
    )
    critical_blocks = sum(
        requirements[block_id].required_trips_90 > 0
        and count < requirements[block_id].required_trips_90
        for block_id, count in counts.items()
    )
    critical_shortage = sum(
        max(0, requirements[block_id].required_trips_90 - count)
        for block_id, count in counts.items()
    )
    planning_warning_blocks = sum(
        requirements[block_id].required_trips_85 > 0
        and count < requirements[block_id].required_trips_85
        for block_id, count in counts.items()
    )
    planning_shortage = sum(
        max(0, requirements[block_id].required_trips_85 - count)
        for block_id, count in counts.items()
    )
    return (
        no_service,
        critical_blocks,
        critical_shortage,
        planning_warning_blocks,
        planning_shortage,
        sum(shift > 0 for shift in shifts),
        sum(shifts),
        max(shifts, default=0),
    )


def _recompute_service_quality_objective_vector_with_authority_v1(
    problem: ScheduleProblemV1,
    schedule: RawScheduleCandidateV1 | ScheduleSolutionV1,
    exact_demand_authority: _ExactDemandAuthority | None,
) -> tuple[int, ...]:
    demand_vector = _recompute_demand_objective_vector_v1(problem, schedule)
    requirements = {item.block_id: item for item in problem.block_requirements}
    scaled = _scaled_directional_demand(problem, exact_demand_authority)
    directional = _directional_schedule_trips(schedule)
    try:
        regime_policy = _analyze_regime_headways(
            problem,
            _schedule_trips(schedule),
            enforce_candidate_labels=True,
        )
    except _RegimeHeadwayPolicyError as exc:
        raise ValueError(exc.code) from exc
    if regime_policy.error_codes:
        raise ValueError(", ".join(regime_policy.error_codes))

    maximum_positive_headway = 0
    for direction, trips in directional.items():
        positive_blocks = tuple(
            block
            for block in problem.analysis_blocks
            if block.direction == direction and requirements[block.block_id].passenger_demand > 0
        )
        for earlier, later in zip(trips, trips[1:], strict=False):
            gap_seconds = later.c_departure_time - earlier.c_departure_time
            if gap_seconds <= 0 or gap_seconds % 60:
                raise ValueError("Schedule directional headway is not a positive whole minute")
            if any(
                earlier.c_departure_time < block.end_time
                and later.c_departure_time > block.start_time
                for block in positive_blocks
            ):
                maximum_positive_headway = max(
                    maximum_positive_headway,
                    gap_seconds // 60,
                )

    total_positive_block_max_gap = 0
    count_by_block_id = {block.block_id: 0 for block in problem.analysis_blocks}
    for block in problem.analysis_blocks:
        members = tuple(
            trip
            for trip in directional[block.direction]
            if block.start_time <= trip.c_departure_time < block.end_time
        )
        count_by_block_id[block.block_id] = len(members)
        if requirements[block.block_id].passenger_demand <= 0:
            continue
        if not members:
            total_positive_block_max_gap += (block.end_time - block.start_time) // 60
            continue
        gaps_seconds = (
            members[0].c_departure_time - block.start_time,
            *(
                later.c_departure_time - earlier.c_departure_time
                for earlier, later in zip(members, members[1:], strict=False)
            ),
            block.end_time - members[-1].c_departure_time,
        )
        if any(gap < 0 or gap % 60 for gap in gaps_seconds):
            raise ValueError("Schedule block coverage gap is not a non-negative whole minute")
        total_positive_block_max_gap += max(gaps_seconds) // 60

    alignment_error = 0
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        total_weight = scaled.total_by_direction[direction]
        trip_count = len(directional[direction])
        if total_weight == 0:
            continue
        alignment_error += sum(
            abs(
                count_by_block_id[block.block_id] * total_weight
                - trip_count * scaled.weight_by_block_id[block.block_id]
            )
            for block in problem.analysis_blocks
            if block.direction == direction
        )

    regime_by_trip_id = regime_policy.assignment_map()
    within_changes: list[int] = []
    transition_jumps: list[int] = []
    for trips in directional.values():
        for previous, current, following in zip(
            trips,
            trips[1:],
            trips[2:],
            strict=False,
        ):
            previous_headway = (current.c_departure_time - previous.c_departure_time) // 60
            next_headway = (following.c_departure_time - current.c_departure_time) // 60
            change = abs(next_headway - previous_headway)
            regime_ids = {
                regime_by_trip_id[previous.c_trip_id],
                regime_by_trip_id[current.c_trip_id],
                regime_by_trip_id[following.c_trip_id],
            }
            if len(regime_ids) == 1:
                within_changes.append(change)
            else:
                transition_jumps.append(change)

    return (
        *demand_vector[:5],
        maximum_positive_headway,
        total_positive_block_max_gap,
        alignment_error,
        max(within_changes, default=0),
        sum(within_changes),
        max(transition_jumps, default=0),
        sum(transition_jumps),
        *demand_vector[5:],
    )


def recompute_service_quality_objective_vector_v1(
    problem: ScheduleProblemV1,
    schedule: RawScheduleCandidateV1 | ScheduleSolutionV1,
) -> tuple[int, ...]:
    """Recompute the canonical 15-stage vector without trusting solver variables."""

    return _recompute_service_quality_objective_vector_with_authority_v1(
        problem,
        schedule,
        None,
    )


__all__ = [
    "SERVICE_QUALITY_OBJECTIVE_NAMES_V1",
    "recompute_service_quality_objective_vector_v1",
]
