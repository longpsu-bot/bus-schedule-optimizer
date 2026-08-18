"""Solver-neutral authority for Scenario C balanced service regimes."""

from __future__ import annotations

import math
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
HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1 = "HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1"
SCENARIO_C_BALANCED_REGIME_POLICY_PROFILE = "scenario_c_balanced_regime_policy_v2"
SCENARIO_C_REPRESENTABLE_REGIME_STATUSES = frozenset({"UNIFORM", "BALANCED_ROUNDING"})
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
    target_headway: float | None
    minimum_internal_headway: int | None
    maximum_internal_headway: int | None
    headway_measurable: bool
    transition_headway_before: int | None
    transition_headway_after: int | None
    status: str


@dataclass(frozen=True, slots=True)
class _RegimeHeadwayPolicyResult:
    policy_profile: str
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


@dataclass(frozen=True, slots=True)
class _CandidateRegimeGroup:
    direction: ContractDirection
    phase_start_index: int
    phase_end_index: int
    trip_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _BalancedHeadwayShape:
    valid: bool
    status: str
    headways: tuple[int, ...]
    target_headway: float | None
    exact_headway: int | None
    maximum_internal_variation: int
    total_internal_variation: int
    error_code: str | None = None


def _headway_regime_representability_error_codes(
    policy: _RegimeHeadwayPolicyResult,
) -> tuple[str, ...]:
    if any(
        analysis.status not in SCENARIO_C_REPRESENTABLE_REGIME_STATUSES
        for analysis in policy.analyses
    ):
        return (HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1,)
    return ()


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
    """Derive demand phases used by the quality model before candidate reconciliation."""
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


def _ordered_members(
    trip_ids: tuple[str, ...],
    trip_by_id: dict[str, _ScheduleTrip],
) -> tuple[_ScheduleTrip, ...]:
    return tuple(
        sorted(
            (trip_by_id[trip_id] for trip_id in trip_ids),
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
    )


def _balanced_headway_shape(
    trip_ids: tuple[str, ...],
    trip_by_id: dict[str, _ScheduleTrip],
) -> _BalancedHeadwayShape:
    members = _ordered_members(trip_ids, trip_by_id)
    if not members:
        return _BalancedHeadwayShape(
            valid=False,
            status="NO_TRIPS",
            headways=(),
            target_headway=None,
            exact_headway=None,
            maximum_internal_variation=0,
            total_internal_variation=0,
        )
    if len(members) == 1:
        return _BalancedHeadwayShape(
            valid=False,
            status="SINGLE_TRIP_HEADWAY_NOT_MEASURABLE",
            headways=(),
            target_headway=None,
            exact_headway=None,
            maximum_internal_variation=0,
            total_internal_variation=0,
        )

    gaps_seconds = tuple(
        later.c_departure_time - earlier.c_departure_time
        for earlier, later in zip(members, members[1:], strict=False)
    )
    if any(gap <= 0 for gap in gaps_seconds):
        return _BalancedHeadwayShape(
            valid=False,
            status="INVALID_NON_UNIFORM",
            headways=(),
            target_headway=None,
            exact_headway=None,
            maximum_internal_variation=0,
            total_internal_variation=0,
            error_code="NON_POSITIVE_ADJACENT_HEADWAY",
        )
    if any(gap % 60 for gap in gaps_seconds):
        return _BalancedHeadwayShape(
            valid=False,
            status="INVALID_NON_UNIFORM",
            headways=(),
            target_headway=None,
            exact_headway=None,
            maximum_internal_variation=0,
            total_internal_variation=0,
            error_code="NON_WHOLE_MINUTE_ADJACENT_HEADWAY",
        )

    headways = tuple(gap // 60 for gap in gaps_seconds)
    span_minutes = (members[-1].c_departure_time - members[0].c_departure_time) // 60
    divisor = len(members) - 1
    floor_headway = span_minutes // divisor
    ceil_headway = math.ceil(span_minutes / divisor)
    allowed = {floor_headway, ceil_headway}
    variations = tuple(
        abs(later - earlier)
        for earlier, later in zip(headways, headways[1:], strict=False)
    )
    valid = (
        floor_headway > 0
        and all(headway in allowed for headway in headways)
        and sum(headways) == span_minutes
        and max(headways) - min(headways) <= 1
    )
    if not valid:
        return _BalancedHeadwayShape(
            valid=False,
            status="INVALID_NON_UNIFORM",
            headways=headways,
            target_headway=span_minutes / divisor,
            exact_headway=None,
            maximum_internal_variation=max(variations, default=0),
            total_internal_variation=sum(variations),
            error_code="WITHIN_REGIME_HEADWAY_NOT_UNIFORM",
        )
    uniform = min(headways) == max(headways)
    return _BalancedHeadwayShape(
        valid=True,
        status="UNIFORM" if uniform else "BALANCED_ROUNDING",
        headways=headways,
        target_headway=span_minutes / divisor,
        exact_headway=headways[0] if uniform else None,
        maximum_internal_variation=max(variations, default=0),
        total_internal_variation=sum(variations),
    )


def _merge_groups(
    left: _CandidateRegimeGroup,
    right: _CandidateRegimeGroup,
    trip_by_id: dict[str, _ScheduleTrip],
) -> _CandidateRegimeGroup:
    if left.direction != right.direction:
        raise _RegimeHeadwayPolicyError("HEADWAY_REGIME_DIRECTION_INVALID")
    trip_ids = tuple(
        trip.c_trip_id
        for trip in _ordered_members((*left.trip_ids, *right.trip_ids), trip_by_id)
    )
    return _CandidateRegimeGroup(
        direction=left.direction,
        phase_start_index=min(left.phase_start_index, right.phase_start_index),
        phase_end_index=max(left.phase_end_index, right.phase_end_index),
        trip_ids=trip_ids,
    )


def _transition_jump_for_singleton_merge(
    groups: list[_CandidateRegimeGroup],
    singleton_index: int,
    side: str,
    merged: _CandidateRegimeGroup,
    trip_by_id: dict[str, _ScheduleTrip],
) -> int:
    merged_shape = _balanced_headway_shape(merged.trip_ids, trip_by_id)
    if not merged_shape.valid or not merged_shape.headways:
        return 0
    members = _ordered_members(merged.trip_ids, trip_by_id)
    if side == "preceding":
        outer_index = singleton_index + 1
        if outer_index >= len(groups):
            return 0
        outer_members = _ordered_members(groups[outer_index].trip_ids, trip_by_id)
        transition = (outer_members[0].c_departure_time - members[-1].c_departure_time) // 60
        return abs(transition - merged_shape.headways[-1])
    outer_index = singleton_index - 1
    if outer_index < 0:
        return 0
    outer_members = _ordered_members(groups[outer_index].trip_ids, trip_by_id)
    transition = (members[0].c_departure_time - outer_members[-1].c_departure_time) // 60
    return abs(transition - merged_shape.headways[0])


def _repair_singletons(
    groups: list[_CandidateRegimeGroup],
    phases: tuple[_SustainedServiceRegime, ...],
    trip_by_id: dict[str, _ScheduleTrip],
) -> list[_CandidateRegimeGroup]:
    repaired = list(groups)
    index = 0
    while index < len(repaired):
        singleton = repaired[index]
        if len(singleton.trip_ids) != 1:
            index += 1
            continue
        singleton_trip = trip_by_id[singleton.trip_ids[0]]
        options: list[tuple[tuple[int, int, int, int, int], str, _CandidateRegimeGroup]] = []

        if index > 0:
            merged = _merge_groups(repaired[index - 1], singleton, trip_by_id)
            shape = _balanced_headway_shape(merged.trip_ids, trip_by_id)
            if shape.valid:
                boundary = phases[singleton.phase_start_index].start_time
                options.append(
                    (
                        (
                            shape.maximum_internal_variation,
                            shape.total_internal_variation,
                            _transition_jump_for_singleton_merge(
                                repaired,
                                index,
                                "preceding",
                                merged,
                                trip_by_id,
                            ),
                            abs(singleton_trip.c_departure_time - boundary) // 60,
                            0,
                        ),
                        "preceding",
                        merged,
                    )
                )

        if index + 1 < len(repaired):
            merged = _merge_groups(singleton, repaired[index + 1], trip_by_id)
            shape = _balanced_headway_shape(merged.trip_ids, trip_by_id)
            if shape.valid:
                boundary = phases[singleton.phase_end_index].end_time
                options.append(
                    (
                        (
                            shape.maximum_internal_variation,
                            shape.total_internal_variation,
                            _transition_jump_for_singleton_merge(
                                repaired,
                                index,
                                "following",
                                merged,
                                trip_by_id,
                            ),
                            abs(singleton_trip.c_departure_time - boundary) // 60,
                            1,
                        ),
                        "following",
                        merged,
                    )
                )

        if not options:
            index += 1
            continue

        _, side, merged = min(options, key=lambda item: item[0])
        if side == "preceding":
            repaired[index - 1] = merged
            del repaired[index]
            index = max(0, index - 1)
        else:
            repaired[index + 1] = merged
            del repaired[index]
    return repaired


def _merge_maximal_balanced_regimes(
    groups: list[_CandidateRegimeGroup],
    trip_by_id: dict[str, _ScheduleTrip],
) -> list[_CandidateRegimeGroup]:
    merged_groups = list(groups)
    changed = True
    while changed:
        changed = False
        index = 0
        while index + 1 < len(merged_groups):
            merged = _merge_groups(
                merged_groups[index],
                merged_groups[index + 1],
                trip_by_id,
            )
            if _balanced_headway_shape(merged.trip_ids, trip_by_id).valid:
                merged_groups[index : index + 2] = [merged]
                changed = True
                index = max(0, index - 1)
                continue
            index += 1
    return merged_groups


def _canonical_candidate_regimes(
    problem: ScheduleProblemV1,
    trips: tuple[_ScheduleTrip, ...],
    *,
    enforce_candidate_labels: bool,
) -> tuple[
    tuple[_SustainedServiceRegime, ...],
    dict[str, str],
    dict[str, _BalancedHeadwayShape],
    list[str],
]:
    demand_phases = _derive_sustained_service_regimes(problem)
    trip_by_id = {trip.c_trip_id: trip for trip in trips}
    errors: list[str] = []
    assignment_to_phase: dict[str, str] = {}
    for trip in trips:
        try:
            phase = _regime_for_departure(
                problem,
                demand_phases,
                trip.direction,
                trip.c_departure_time,
            )
        except _RegimeHeadwayPolicyError as exc:
            errors.append(exc.code)
            continue
        assignment_to_phase[trip.c_trip_id] = phase.regime_id

    final_regimes: list[_SustainedServiceRegime] = []
    final_assignments: dict[str, str] = {}
    final_shapes: dict[str, _BalancedHeadwayShape] = {}
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        phases = tuple(phase for phase in demand_phases if phase.direction == direction)
        phase_index_by_id = {phase.regime_id: index for index, phase in enumerate(phases)}
        groups: list[_CandidateRegimeGroup] = []
        for phase in phases:
            member_ids = tuple(
                trip.c_trip_id
                for trip in sorted(
                    (
                        item
                        for item in trips
                        if item.direction == direction
                        and assignment_to_phase.get(item.c_trip_id) == phase.regime_id
                    ),
                    key=lambda item: (item.c_departure_time, item.c_trip_id),
                )
            )
            if not member_ids:
                continue
            phase_index = phase_index_by_id[phase.regime_id]
            groups.append(
                _CandidateRegimeGroup(
                    direction=direction,
                    phase_start_index=phase_index,
                    phase_end_index=phase_index,
                    trip_ids=member_ids,
                )
            )

        groups = _repair_singletons(groups, phases, trip_by_id)
        groups = _merge_maximal_balanced_regimes(groups, trip_by_id)

        for regime_index, group in enumerate(groups, start=1):
            covered_phases = phases[group.phase_start_index : group.phase_end_index + 1]
            regime_id = f"SCENARIO-C-{direction.value.upper()}-{regime_index:04d}"
            regime = _SustainedServiceRegime(
                regime_id=regime_id,
                direction=direction,
                block_ids=tuple(
                    block_id for phase in covered_phases for block_id in phase.block_ids
                ),
                start_time=covered_phases[0].start_time,
                end_time=covered_phases[-1].end_time,
                duration_minutes=sum(phase.duration_minutes for phase in covered_phases),
                required_trips_85=sum(phase.required_trips_85 for phase in covered_phases),
            )
            shape = _balanced_headway_shape(group.trip_ids, trip_by_id)
            final_regimes.append(regime)
            final_shapes[regime_id] = shape
            if shape.error_code is not None:
                errors.append(shape.error_code)
            for trip_id in group.trip_ids:
                final_assignments[trip_id] = regime_id

    if len(final_assignments) != len(trip_by_id):
        errors.append("HEADWAY_REGIME_MEMBERSHIP_MISSING")
    if enforce_candidate_labels:
        for trip in trips:
            expected = final_assignments.get(trip.c_trip_id)
            if expected is not None and trip.headway_regime_id != expected:
                errors.append("HEADWAY_REGIME_AUTHORITY_MISMATCH")
    return tuple(final_regimes), final_assignments, final_shapes, errors


def _analyze_regime_headways(
    problem: ScheduleProblemV1,
    trips: tuple[_ScheduleTrip, ...],
    *,
    enforce_candidate_labels: bool,
) -> _RegimeHeadwayPolicyResult:
    regimes, regime_by_trip_id, shapes, errors = _canonical_candidate_regimes(
        problem,
        trips,
        enforce_candidate_labels=enforce_candidate_labels,
    )
    trips_by_direction: dict[ContractDirection, list[_ScheduleTrip]] = {
        ContractDirection.OUTBOUND: [],
        ContractDirection.INBOUND: [],
    }
    for trip in trips:
        if trip.direction not in trips_by_direction:
            errors.append("HEADWAY_REGIME_DIRECTION_INVALID")
            continue
        trips_by_direction[trip.direction].append(trip)

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
        member_ids = tuple(
            trip.c_trip_id
            for trip in sorted(
                (
                    trip
                    for trip in trips
                    if regime_by_trip_id.get(trip.c_trip_id) == regime.regime_id
                ),
                key=lambda item: (item.c_departure_time, item.c_trip_id),
            )
        )
        shape = shapes[regime.regime_id]
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
        if internal != shape.headways:
            errors.append("HEADWAY_REGIME_SEQUENCE_MISMATCH")

        analyses.append(
            _RegimeHeadwayAnalysis(
                regime=regime,
                trip_ids=member_ids,
                internal_headways=internal,
                exact_headway=shape.exact_headway,
                target_headway=shape.target_headway,
                minimum_internal_headway=min(internal) if internal else None,
                maximum_internal_headway=max(internal) if internal else None,
                headway_measurable=len(member_ids) >= 2,
                transition_headway_before=entering[-1] if entering else None,
                transition_headway_after=leaving[0] if leaving else None,
                status=shape.status,
            )
        )

    return _RegimeHeadwayPolicyResult(
        policy_profile=SCENARIO_C_BALANCED_REGIME_POLICY_PROFILE,
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
        if (
            analysis.status not in SCENARIO_C_REPRESENTABLE_REGIME_STATUSES
            or analysis.target_headway is None
            or analysis.target_headway <= 0
        ):
            continue
        members = tuple(trip_by_id[trip_id] for trip_id in analysis.trip_ids)
        raw_regimes.append(
            RawHeadwayRegimeV1(
                regime_id=regime.regime_id,
                direction=regime.direction,
                start_time=members[0].c_departure_time,
                end_time=members[-1].c_departure_time,
                trip_count=len(members),
                target_headway=float(analysis.target_headway),
                actual_headway_sequence=tuple(float(value) for value in analysis.internal_headways),
                boundary_reason=_BOUNDARY_REASON,
                legacy_regularity_status=analysis.status,
            )
        )
    return labeled_trips, tuple(raw_regimes), result
