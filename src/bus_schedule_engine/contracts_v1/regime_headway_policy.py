"""Solver-neutral authority for demand-derived regime headway policy."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TypeAlias

from .models import ContractDirection, ExactTimetableTrip
from .solver_models import (
    RawCandidateTripV1,
    RawHeadwayRegimeV1,
    ScheduleProblemV1,
    SolutionTripV1,
)

_BOUNDARY_REASON = "MATERIAL_FREQUENCY_CHANGE"
_ScheduleTrip: TypeAlias = RawCandidateTripV1 | SolutionTripV1


class _RegimeHeadwayPolicyError(ValueError):
    def __init__(self, code: str, detail: str | None = None) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _SustainedServiceRegime:
    regime_id: str
    direction: ContractDirection
    block_ids: tuple[str, ...]
    start_time: int
    end_time: int
    duration_minutes: int
    required_trips_85: int


@dataclass(frozen=True, slots=True)
class _RegimeHeadwayPair:
    direction: ContractDirection
    earlier_trip_id: str
    later_trip_id: str
    headway_minutes: int
    earlier_regime_id: str
    later_regime_id: str

    @property
    def internal_regime_id(self) -> str | None:
        if self.earlier_regime_id == self.later_regime_id:
            return self.earlier_regime_id
        return None


@dataclass(frozen=True, slots=True)
class _RegimeHeadwayAnalysis:
    regime: _SustainedServiceRegime
    trip_ids: tuple[str, ...]
    internal_headways: tuple[int, ...]
    exact_headway: int | None
    minimum_internal_headway: int | None
    maximum_internal_headway: int | None
    headway_measurable: bool
    transition_headway_before: int | None
    transition_headway_after: int | None
    status: str


@dataclass(frozen=True, slots=True)
class _RegimeHeadwayPolicyResult:
    regimes: tuple[_SustainedServiceRegime, ...]
    regime_by_trip_id: tuple[tuple[str, str], ...]
    internal_pairs: tuple[_RegimeHeadwayPair, ...]
    transition_pairs: tuple[_RegimeHeadwayPair, ...]
    analyses: tuple[_RegimeHeadwayAnalysis, ...]
    error_codes: tuple[str, ...]

    def assignment_map(self) -> dict[str, str]:
        return dict(self.regime_by_trip_id)

    def analysis_by_regime_id(self) -> dict[str, _RegimeHeadwayAnalysis]:
        return {analysis.regime.regime_id: analysis for analysis in self.analyses}


def _ordered_problem_trips(
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


def _derive_sustained_service_regimes(
    problem: ScheduleProblemV1,
) -> tuple[_SustainedServiceRegime, ...]:
    requirements = {item.block_id: item for item in problem.block_requirements}
    directional_trips = _ordered_problem_trips(problem)
    output: list[_SustainedServiceRegime] = []
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        blocks = tuple(
            sorted(
                (block for block in problem.analysis_blocks if block.direction == direction),
                key=lambda item: (item.start_time, item.end_time, item.block_id),
            )
        )
        trips = directional_trips[direction]
        if not blocks or not trips:
            raise _RegimeHeadwayPolicyError("ORTOOLS_QUALITY_DIRECTIONAL_COVERAGE_INCOMPLETE")
        if blocks[0].start_time > trips[0].departure_time or (
            blocks[-1].end_time <= trips[-1].departure_time
        ):
            raise _RegimeHeadwayPolicyError("ORTOOLS_QUALITY_DIRECTIONAL_COVERAGE_INCOMPLETE")
        for earlier, later in zip(blocks, blocks[1:], strict=False):
            if earlier.end_time > later.start_time:
                raise _RegimeHeadwayPolicyError("ORTOOLS_QUALITY_BLOCKS_OVERLAP")
            if earlier.end_time != later.start_time:
                raise _RegimeHeadwayPolicyError("ORTOOLS_QUALITY_DIRECTIONAL_COVERAGE_INCOMPLETE")
        if any(block.block_id not in requirements for block in blocks):
            raise _RegimeHeadwayPolicyError("ORTOOLS_QUALITY_BLOCK_REQUIREMENT_MISSING")

        groups: list[list[object]] = []
        for block in blocks:
            requirement = requirements[block.block_id]
            if not groups:
                groups.append([block])
                continue
            previous = groups[-1][-1]
            previous_requirement = requirements[previous.block_id]
            exact_equal_planning_rate = (
                previous_requirement.required_trips_85 * requirement.duration_minutes
                == requirement.required_trips_85 * previous_requirement.duration_minutes
            )
            if previous.end_time == block.start_time and exact_equal_planning_rate:
                groups[-1].append(block)
            else:
                groups.append([block])

        for index, group in enumerate(groups, start=1):
            typed_group = tuple(group)
            group_requirements = tuple(requirements[item.block_id] for item in typed_group)
            output.append(
                _SustainedServiceRegime(
                    regime_id=(f"ORTOOLS-QUALITY-{direction.value.upper()}-{index:04d}"),
                    direction=direction,
                    block_ids=tuple(item.block_id for item in typed_group),
                    start_time=typed_group[0].start_time,
                    end_time=typed_group[-1].end_time,
                    duration_minutes=sum(item.duration_minutes for item in group_requirements),
                    required_trips_85=sum(item.required_trips_85 for item in group_requirements),
                )
            )
    return tuple(output)


def _regime_for_departure(
    problem: ScheduleProblemV1,
    regimes: tuple[_SustainedServiceRegime, ...],
    direction: ContractDirection,
    departure_time: int,
) -> _SustainedServiceRegime:
    if direction not in {
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
    }:
        raise _RegimeHeadwayPolicyError("HEADWAY_REGIME_DIRECTION_INVALID")
    matching_blocks = [
        block
        for block in problem.analysis_blocks
        if block.direction == direction and block.start_time <= departure_time < block.end_time
    ]
    if not matching_blocks:
        raise _RegimeHeadwayPolicyError("HEADWAY_REGIME_MEMBERSHIP_MISSING")
    if len(matching_blocks) != 1:
        raise _RegimeHeadwayPolicyError("HEADWAY_REGIME_MEMBERSHIP_MULTIPLE")
    block_id = matching_blocks[0].block_id
    matches = [
        regime
        for regime in regimes
        if regime.direction == direction and block_id in regime.block_ids
    ]
    if not matches:
        raise _RegimeHeadwayPolicyError("HEADWAY_REGIME_MEMBERSHIP_MISSING")
    if len(matches) != 1:
        raise _RegimeHeadwayPolicyError("HEADWAY_REGIME_MEMBERSHIP_MULTIPLE")
    return matches[0]


def _analyze_regime_headways(
    problem: ScheduleProblemV1,
    trips: tuple[_ScheduleTrip, ...],
    *,
    enforce_candidate_labels: bool,
) -> _RegimeHeadwayPolicyResult:
    regimes = _derive_sustained_service_regimes(problem)
    errors: list[str] = []
    regime_by_trip_id: dict[str, str] = {}
    trips_by_direction: dict[ContractDirection, list[_ScheduleTrip]] = {
        ContractDirection.OUTBOUND: [],
        ContractDirection.INBOUND: [],
    }
    for trip in trips:
        if trip.direction not in trips_by_direction:
            errors.append("HEADWAY_REGIME_DIRECTION_INVALID")
            continue
        trips_by_direction[trip.direction].append(trip)
        try:
            regime = _regime_for_departure(
                problem,
                regimes,
                trip.direction,
                trip.c_departure_time,
            )
        except _RegimeHeadwayPolicyError as exc:
            errors.append(exc.code)
            continue
        regime_by_trip_id[trip.c_trip_id] = regime.regime_id
        if enforce_candidate_labels and trip.headway_regime_id != regime.regime_id:
            errors.append("HEADWAY_REGIME_AUTHORITY_MISMATCH")

    internal_pairs: list[_RegimeHeadwayPair] = []
    transition_pairs: list[_RegimeHeadwayPair] = []
    for direction, directional_trips in trips_by_direction.items():
        ordered = sorted(
            directional_trips,
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            earlier_regime_id = regime_by_trip_id.get(earlier.c_trip_id)
            later_regime_id = regime_by_trip_id.get(later.c_trip_id)
            if earlier_regime_id is None or later_regime_id is None:
                continue
            gap_seconds = later.c_departure_time - earlier.c_departure_time
            if gap_seconds <= 0:
                errors.append("NON_POSITIVE_ADJACENT_HEADWAY")
                continue
            if gap_seconds % 60:
                errors.append("NON_WHOLE_MINUTE_ADJACENT_HEADWAY")
                continue
            pair = _RegimeHeadwayPair(
                direction=direction,
                earlier_trip_id=earlier.c_trip_id,
                later_trip_id=later.c_trip_id,
                headway_minutes=gap_seconds // 60,
                earlier_regime_id=earlier_regime_id,
                later_regime_id=later_regime_id,
            )
            if pair.internal_regime_id is None:
                transition_pairs.append(pair)
            else:
                internal_pairs.append(pair)

    analyses: list[_RegimeHeadwayAnalysis] = []
    for regime in regimes:
        members = tuple(
            sorted(
                (
                    trip
                    for trip in trips
                    if regime_by_trip_id.get(trip.c_trip_id) == regime.regime_id
                ),
                key=lambda item: (item.c_departure_time, item.c_trip_id),
            )
        )
        internal = tuple(
            pair.headway_minutes
            for pair in internal_pairs
            if pair.internal_regime_id == regime.regime_id
        )
        entering = tuple(
            pair.headway_minutes
            for pair in transition_pairs
            if pair.later_regime_id == regime.regime_id
        )
        leaving = tuple(
            pair.headway_minutes
            for pair in transition_pairs
            if pair.earlier_regime_id == regime.regime_id
        )
        if len(entering) > 1 or len(leaving) > 1:
            errors.append("HEADWAY_REGIME_TRANSITION_CLASSIFICATION_INVALID")

        if not members:
            status = "NO_TRIPS"
            exact_headway = None
        elif len(members) == 1:
            status = "SINGLE_TRIP_HEADWAY_NOT_MEASURABLE"
            exact_headway = None
        elif len(internal) == len(members) - 1 and internal and min(internal) == max(internal):
            status = "UNIFORM"
            exact_headway = internal[0]
        else:
            status = "INVALID_NON_UNIFORM"
            exact_headway = None
            errors.append("WITHIN_REGIME_HEADWAY_NOT_UNIFORM")

        analyses.append(
            _RegimeHeadwayAnalysis(
                regime=regime,
                trip_ids=tuple(member.c_trip_id for member in members),
                internal_headways=internal,
                exact_headway=exact_headway,
                minimum_internal_headway=min(internal) if internal else None,
                maximum_internal_headway=max(internal) if internal else None,
                headway_measurable=len(members) >= 2,
                transition_headway_before=entering[-1] if entering else None,
                transition_headway_after=leaving[0] if leaving else None,
                status=status,
            )
        )

    return _RegimeHeadwayPolicyResult(
        regimes=regimes,
        regime_by_trip_id=tuple(sorted(regime_by_trip_id.items())),
        internal_pairs=tuple(internal_pairs),
        transition_pairs=tuple(transition_pairs),
        analyses=tuple(analyses),
        error_codes=tuple(sorted(set(errors))),
    )


def _authoritative_candidate_payload(
    problem: ScheduleProblemV1,
    trips: tuple[RawCandidateTripV1, ...],
) -> tuple[
    tuple[RawCandidateTripV1, ...],
    tuple[RawHeadwayRegimeV1, ...],
    _RegimeHeadwayPolicyResult,
]:
    preliminary = _analyze_regime_headways(
        problem,
        trips,
        enforce_candidate_labels=False,
    )
    assignments = preliminary.assignment_map()
    labeled_trips = tuple(
        replace(
            trip,
            headway_regime_id=assignments.get(
                trip.c_trip_id,
                "REGIME_AUTHORITY_UNRESOLVED",
            ),
        )
        for trip in trips
    )
    result = _analyze_regime_headways(
        problem,
        labeled_trips,
        enforce_candidate_labels=True,
    )
    analyses = result.analysis_by_regime_id()
    raw_regimes: list[RawHeadwayRegimeV1] = []
    trip_by_id = {trip.c_trip_id: trip for trip in labeled_trips}
    for regime in result.regimes:
        analysis = analyses[regime.regime_id]
        members = tuple(trip_by_id[trip_id] for trip_id in analysis.trip_ids)
        raw_regimes.append(
            RawHeadwayRegimeV1(
                regime_id=regime.regime_id,
                direction=regime.direction,
                start_time=(members[0].c_departure_time if members else regime.start_time),
                end_time=(members[-1].c_departure_time if members else regime.end_time),
                trip_count=len(members),
                target_headway=float(analysis.exact_headway or 0),
                actual_headway_sequence=tuple(float(value) for value in analysis.internal_headways),
                boundary_reason=_BOUNDARY_REASON,
                legacy_regularity_status=analysis.status,
            )
        )
    return labeled_trips, tuple(raw_regimes), result
