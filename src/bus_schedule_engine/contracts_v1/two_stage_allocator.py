"""Stage 1 integer trip allocation and V3 representable-regime planning."""

from __future__ import annotations

import math
import time
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction

from ortools.sat.python import cp_model

from bus_schedule_engine.models import ProtectedServiceFloorEnforcementAuthorityV1

from .demand_resolution import DemandAnalysisBlockV1
from .models import ContractDirection, DemandAllocationAuthorityModeV1
from .ortools_protected_floor import (
    OrToolsProtectedFloorProjectionV1,
    build_ortools_protected_floor_projection_v1,
)
from .ortools_solver import _map_cp_sat_status, _ordered_directional_trips
from .serialization import canonical_sha256
from .solver_models import NativeSolverStatus, ScheduleProblemV1
from .two_stage_authority import TwoStageDemandAuthorityV1
from .two_stage_models import (
    SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE,
    TRIP_ALLOCATION_PLAN_PROFILE_V1,
    FinalServiceSentinelV1,
    ProposedServiceRegimeV1,
    ServiceBoundarySemanticsV1,
    Stage1AllocationResultV1,
    Stage1NecessaryFeasibilityResultV1,
    Stage1RegimeBuildDiagnosticV1,
    Stage1RegimeBuildFailureCodeV1,
    Stage2ConstraintFamilyV1,
    TripAllocationBlockV1,
    TripAllocationPlanV1,
    TripAllocationSolveStatusV1,
    UniformIntegerRegimePolicyV3,
    finalize_allocation_plan,
    finalize_stage_1_necessary_feasibility,
    finalize_stage_1_regime_build_diagnostic,
)

STAGE_1_ALLOCATION_MODEL_PROFILE_V1 = "scenario_c_stage_1_integer_allocation_v1"
STAGE_1_PROBLEM_AUTHORITY_MISMATCH = "STAGE_1_PROBLEM_AUTHORITY_MISMATCH"
STAGE_1_REGIME_UNREPRESENTABLE = "STAGE_1_REGIME_UNREPRESENTABLE"


class Stage1AllocationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class UniformRegimeRepresentationV1:
    start_minute: int
    end_minute: int
    uniform_headway_minutes: int | None
    departure_minutes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _AllocationModel:
    model: cp_model.CpModel
    count_by_direction_and_block: dict[tuple[ContractDirection, str], cp_model.IntVar]
    objective_terms: tuple[cp_model.IntVar, ...]
    objective_term_bounds: tuple[int, ...]
    blocks: tuple[DemandAnalysisBlockV1, ...]
    protected_minimum_by_direction_and_block: dict[tuple[ContractDirection, str], int]
    final_service_sentinels: tuple[FinalServiceSentinelV1, ...]


@dataclass(frozen=True, slots=True)
class _RegimeGroup:
    direction: ContractDirection
    blocks: tuple[DemandAnalysisBlockV1, ...]
    trip_count: int
    source_start_index: int
    source_end_index: int
    is_final_service_tail: bool
    has_final_service_sentinel: bool


@dataclass(frozen=True, slots=True)
class _GroupRepresentationProbe:
    representation: UniformRegimeRepresentationV1 | None
    start_window: tuple[int, int]
    end_window: tuple[int, int]
    failure_code: Stage1RegimeBuildFailureCodeV1 | None


@dataclass(frozen=True, slots=True)
class _RegimeBuildOutcome:
    regimes: tuple[ProposedServiceRegimeV1, ...] | None
    diagnostic: Stage1RegimeBuildDiagnosticV1 | None


def _bounded_sum(
    model: cp_model.CpModel,
    values: list[cp_model.IntVar],
    *,
    upper_bound: int,
    name: str,
) -> cp_model.IntVar:
    result = model.new_int_var(0, max(0, upper_bound), name)
    model.add(result == sum(values))
    return result


def _lexicographic_weights(bounds: tuple[int, ...]) -> tuple[int, ...]:
    weights = [1] * len(bounds)
    lower_maximum = 0
    for index in range(len(bounds) - 1, -1, -1):
        weights[index] = lower_maximum + 1
        lower_maximum += bounds[index] * weights[index]
    return tuple(weights)


def _representable_uniform_regime_candidates_v1(
    source_b_minutes: tuple[int, ...],
    *,
    permitted_start_window: tuple[int, int],
    permitted_end_window: tuple[int, int],
    minimum_headway_minutes: int,
    maximum_headway_minutes: int,
    absolute_max_shift_per_trip_minutes: int,
    preferred_start_minute: int,
    preferred_end_minute: int,
) -> tuple[UniformRegimeRepresentationV1, ...]:
    if not source_b_minutes:
        return ()
    if len(source_b_minutes) == 1:
        lower = max(
            permitted_start_window[0],
            permitted_end_window[0],
            source_b_minutes[0] - absolute_max_shift_per_trip_minutes,
        )
        upper = min(
            permitted_start_window[1],
            permitted_end_window[1],
            source_b_minutes[0] + absolute_max_shift_per_trip_minutes,
        )
        if lower > upper:
            return ()
        return tuple(
            UniformRegimeRepresentationV1(
                start_minute=minute,
                end_minute=minute,
                uniform_headway_minutes=None,
                departure_minutes=(minute,),
            )
            for minute in sorted(
                range(lower, upper + 1),
                key=lambda item: (abs(item - preferred_start_minute), item),
            )
        )

    candidates: list[tuple[tuple[int, int, int, int], UniformRegimeRepresentationV1]] = []
    divisor = len(source_b_minutes) - 1
    for headway in range(minimum_headway_minutes, maximum_headway_minutes + 1):
        start_lower = permitted_start_window[0]
        start_upper = permitted_start_window[1]
        start_lower = max(start_lower, permitted_end_window[0] - divisor * headway)
        start_upper = min(start_upper, permitted_end_window[1] - divisor * headway)
        for index, source_minute in enumerate(source_b_minutes):
            start_lower = max(
                start_lower,
                source_minute - absolute_max_shift_per_trip_minutes - index * headway,
            )
            start_upper = min(
                start_upper,
                source_minute + absolute_max_shift_per_trip_minutes - index * headway,
            )
        if start_lower > start_upper:
            continue
        for start in range(start_lower, start_upper + 1):
            end = start + divisor * headway
            departures = tuple(start + index * headway for index in range(len(source_b_minutes)))
            maximum_shift = max(
                abs(departure - source)
                for departure, source in zip(departures, source_b_minutes, strict=True)
            )
            score = (
                abs(start - preferred_start_minute) + abs(end - preferred_end_minute),
                maximum_shift,
                sum(
                    abs(departure - source)
                    for departure, source in zip(departures, source_b_minutes, strict=True)
                ),
                headway,
            )
            candidates.append(
                (
                    score,
                    UniformRegimeRepresentationV1(
                        start_minute=start,
                        end_minute=end,
                        uniform_headway_minutes=headway,
                        departure_minutes=departures,
                    ),
                )
            )
    return tuple(item[1] for item in sorted(candidates, key=lambda item: item[0]))


def find_representable_uniform_regime_v1(
    source_b_minutes: tuple[int, ...],
    *,
    permitted_start_window: tuple[int, int],
    permitted_end_window: tuple[int, int],
    minimum_headway_minutes: int,
    maximum_headway_minutes: int,
    absolute_max_shift_per_trip_minutes: int,
    preferred_start_minute: int,
    preferred_end_minute: int,
) -> UniformRegimeRepresentationV1 | None:
    """Find one exact arithmetic progression inside boundary and B-anchor domains."""
    candidates = _representable_uniform_regime_candidates_v1(
        source_b_minutes,
        permitted_start_window=permitted_start_window,
        permitted_end_window=permitted_end_window,
        minimum_headway_minutes=minimum_headway_minutes,
        maximum_headway_minutes=maximum_headway_minutes,
        absolute_max_shift_per_trip_minutes=absolute_max_shift_per_trip_minutes,
        preferred_start_minute=preferred_start_minute,
        preferred_end_minute=preferred_end_minute,
    )
    return candidates[0] if candidates else None


def _block_for_minute(
    blocks: tuple[DemandAnalysisBlockV1, ...],
    direction: ContractDirection,
    minute: int,
) -> DemandAnalysisBlockV1 | None:
    compatible = tuple(
        block
        for block in blocks
        if block.direction in {direction, ContractDirection.COMBINED}
        and block.start_time // 60 <= minute < block.end_time // 60
    )
    return compatible[0] if len(compatible) == 1 else None


def _protected_minimums(
    problem: ScheduleProblemV1,
    blocks: tuple[DemandAnalysisBlockV1, ...],
    authority: ProtectedServiceFloorEnforcementAuthorityV1 | None,
) -> tuple[
    dict[tuple[ContractDirection, str], int],
    OrToolsProtectedFloorProjectionV1 | None,
]:
    if authority is None or not authority.has_enforceable_regimes:
        return {}, None
    projection = build_ortools_protected_floor_projection_v1(authority, problem.scenario_b)
    if projection is None:
        return {}, None
    source_by_id = {trip.trip_id: trip for trip in problem.scenario_b.exact_timetable}
    minimums: dict[tuple[ContractDirection, str], int] = {}
    for regime in projection.regimes:
        for source_id in regime.ordered_b_trip_ids:
            source = source_by_id[source_id]
            block = _block_for_minute(blocks, regime.direction, source.departure_time // 60)
            if block is None:
                directional_sources = _ordered_directional_trips(problem)[regime.direction]
                compatible_ends = tuple(
                    item.end_time // 60
                    for item in blocks
                    if item.direction in {regime.direction, ContractDirection.COMBINED}
                )
                if (
                    source.trip_id == directional_sources[-1].trip_id
                    and compatible_ends
                    and source.departure_time // 60 == max(compatible_ends)
                ):
                    continue
                raise Stage1AllocationError(
                    STAGE_1_PROBLEM_AUTHORITY_MISMATCH,
                    "a protected B source does not map to one authoritative allocation block",
                )
            key = (regime.direction, block.block_id)
            minimums[key] = minimums.get(key, 0) + 1
    return minimums, projection


def _source_count(
    problem: ScheduleProblemV1,
    block: DemandAnalysisBlockV1,
    direction: ContractDirection,
) -> int:
    return sum(
        trip.direction == direction and block.start_time <= trip.departure_time < block.end_time
        for trip in problem.scenario_b.exact_timetable
    )


def _direction_total(problem: ScheduleProblemV1, direction: ContractDirection) -> int:
    return (
        problem.scenario_b.trips_by_direction.outbound
        if direction == ContractDirection.OUTBOUND
        else problem.scenario_b.trips_by_direction.inbound
    )


def _final_service_sentinels(
    problem: ScheduleProblemV1,
    blocks: tuple[DemandAnalysisBlockV1, ...],
) -> tuple[FinalServiceSentinelV1, ...]:
    """Identify locked last departures that equal an analytical exclusive end boundary."""
    directional = _ordered_directional_trips(problem)
    output: list[FinalServiceSentinelV1] = []
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        compatible = tuple(
            block for block in blocks if block.direction in {direction, ContractDirection.COMBINED}
        )
        if not compatible:
            continue
        final_boundary = max(block.end_time // 60 for block in compatible)
        source = directional[direction][-1]
        if source.departure_time // 60 == final_boundary:
            output.append(
                FinalServiceSentinelV1(
                    direction=direction,
                    source_b_trip_id=source.trip_id,
                    departure_minute=final_boundary,
                )
            )
    return tuple(output)


def _build_allocation_model(
    problem: ScheduleProblemV1,
    authority: TwoStageDemandAuthorityV1,
    policy: UniformIntegerRegimePolicyV3,
    protected_authority: ProtectedServiceFloorEnforcementAuthorityV1 | None,
) -> _AllocationModel:
    blocks = tuple(
        sorted(
            problem.analysis_blocks,
            key=lambda item: (item.start_time, item.end_time, item.direction.value, item.block_id),
        )
    )
    if not blocks:
        raise Stage1AllocationError(
            STAGE_1_PROBLEM_AUTHORITY_MISMATCH,
            "Stage 1 requires authoritative intraday demand blocks",
        )
    directions = (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    if authority.authority_mode == (
        DemandAllocationAuthorityModeV1.DIRECTIONAL_FIXED_DIRECTION_COUNTS
    ):
        if any(block.direction not in directions for block in blocks):
            raise Stage1AllocationError(
                STAGE_1_PROBLEM_AUTHORITY_MISMATCH,
                "directional authority contains a non-directional allocation block",
            )
    elif any(block.direction != ContractDirection.COMBINED for block in blocks):
        raise Stage1AllocationError(
            STAGE_1_PROBLEM_AUTHORITY_MISMATCH,
            "combined authority must use combined analysis blocks",
        )

    protected_minimums, _ = _protected_minimums(problem, blocks, protected_authority)
    final_service_sentinels = _final_service_sentinels(problem, blocks)
    sentinel_directions = {item.direction for item in final_service_sentinels}
    model = cp_model.CpModel()
    counts: dict[tuple[ContractDirection, str], cp_model.IntVar] = {}
    for block in blocks:
        compatible_directions = (block.direction,) if block.direction in directions else directions
        for direction in compatible_directions:
            upper = _direction_total(problem, direction)
            value = model.new_int_var(0, upper, f"stage1_count_{direction.value}_{block.block_id}")
            minimum = protected_minimums.get((direction, block.block_id), 0)
            if minimum:
                model.add(value >= minimum)
            counts[(direction, block.block_id)] = value

    for direction in directions:
        directional_values = [
            value
            for (candidate_direction, _), value in counts.items()
            if candidate_direction == direction
        ]
        analytical_total = _direction_total(problem, direction) - int(
            direction in sentinel_directions
        )
        model.add(sum(directional_values) == analytical_total)

        compatible_blocks = tuple(
            block for block in blocks if block.direction in {direction, ContractDirection.COMBINED}
        )
        last_block = max(compatible_blocks, key=lambda item: (item.end_time, item.block_id))
        total = _direction_total(problem, direction)
        if total >= policy.final_service_tail.final_service_tail_minimum_trip_count:
            model.add(
                counts[(direction, last_block.block_id)]
                >= max(
                    0,
                    policy.final_service_tail.final_service_tail_minimum_trip_count
                    - int(direction in sentinel_directions),
                )
            )

    no_service_values: list[cp_model.IntVar] = []
    critical_shortages: list[cp_model.IntVar] = []
    planning_shortages: list[cp_model.IntVar] = []
    allocation_errors: list[cp_model.IntVar] = []
    continuity_errors: list[cp_model.IntVar] = []
    total_trips = problem.scenario_b.total_daily_trips
    requirements = {item.block_id: item for item in problem.block_requirements}
    for block in blocks:
        compatible_directions = (block.direction,) if block.direction in directions else directions
        block_counts = [counts[(direction, block.block_id)] for direction in compatible_directions]
        aggregate = (
            block_counts[0]
            if len(block_counts) == 1
            else _bounded_sum(
                model,
                block_counts,
                upper_bound=total_trips,
                name=f"stage1_aggregate_{block.block_id}",
            )
        )
        requirement = requirements[block.block_id]
        no_service = model.new_bool_var(f"stage1_no_service_{block.block_id}")
        if block.observed_passengers > 0:
            model.add(aggregate == 0).only_enforce_if(no_service)
            model.add(aggregate >= 1).only_enforce_if(no_service.negated())
        else:
            model.add(no_service == 0)
        no_service_values.append(no_service)

        critical = model.new_int_var(
            0, requirement.required_trips_90, f"stage1_critical_shortage_{block.block_id}"
        )
        planning = model.new_int_var(
            0, requirement.required_trips_85, f"stage1_planning_shortage_{block.block_id}"
        )
        model.add_max_equality(critical, [0, requirement.required_trips_90 - aggregate])
        model.add_max_equality(planning, [0, requirement.required_trips_85 - aggregate])
        critical_shortages.append(critical)
        planning_shortages.append(planning)

        error_bound = max(total_trips, requirement.required_trips_85)
        error = model.new_int_var(0, error_bound, f"stage1_allocation_error_{block.block_id}")
        model.add_abs_equality(error, aggregate - requirement.required_trips_85)
        allocation_errors.append(error)

        for direction in compatible_directions:
            source_count = _source_count(problem, block, direction)
            continuity = model.new_int_var(
                0,
                _direction_total(problem, direction),
                f"stage1_continuity_{direction.value}_{block.block_id}",
            )
            model.add_abs_equality(
                continuity,
                counts[(direction, block.block_id)] - source_count,
            )
            continuity_errors.append(continuity)

    bounds = (
        len(no_service_values),
        sum(item.required_trips_90 for item in requirements.values()),
        sum(item.required_trips_85 for item in requirements.values()),
        sum(max(total_trips, item.required_trips_85) for item in requirements.values()),
        total_trips * 2,
    )
    terms = (
        _bounded_sum(model, no_service_values, upper_bound=bounds[0], name="stage1_no_service"),
        _bounded_sum(
            model,
            critical_shortages,
            upper_bound=bounds[1],
            name="stage1_critical_shortage",
        ),
        _bounded_sum(
            model,
            planning_shortages,
            upper_bound=bounds[2],
            name="stage1_planning_shortage",
        ),
        _bounded_sum(
            model,
            allocation_errors,
            upper_bound=bounds[3],
            name="stage1_allocation_error",
        ),
        _bounded_sum(
            model,
            continuity_errors,
            upper_bound=bounds[4],
            name="stage1_b_continuity",
        ),
    )
    baseline_no_service = 0
    baseline_critical_shortage = 0
    baseline_planning_shortage = 0
    for block in blocks:
        compatible_directions = (block.direction,) if block.direction in directions else directions
        source_count = sum(
            _source_count(problem, block, direction) for direction in compatible_directions
        )
        requirement = requirements[block.block_id]
        baseline_no_service += int(block.observed_passengers > 0 and source_count == 0)
        baseline_critical_shortage += max(0, requirement.required_trips_90 - source_count)
        baseline_planning_shortage += max(0, requirement.required_trips_85 - source_count)
    model.add(terms[0] <= baseline_no_service)
    model.add(terms[1] <= baseline_critical_shortage)
    model.add(terms[2] <= baseline_planning_shortage)
    weights = _lexicographic_weights(bounds)
    model.minimize(sum(term * weight for term, weight in zip(terms, weights, strict=True)))
    return _AllocationModel(
        model=model,
        count_by_direction_and_block=counts,
        objective_terms=terms,
        objective_term_bounds=bounds,
        blocks=blocks,
        protected_minimum_by_direction_and_block=protected_minimums,
        final_service_sentinels=final_service_sentinels,
    )


def _boundary_window(
    nominal: int,
    *,
    lower: int,
    upper: int,
    tolerance: int,
) -> tuple[int, int]:
    return max(lower, nominal - tolerance), min(upper, nominal + tolerance)


def _protected_maximum_headway(
    projection: OrToolsProtectedFloorProjectionV1 | None,
    direction: ContractDirection,
    source_start_index: int,
    source_end_index: int,
    default: int,
) -> int:
    if projection is None:
        return default
    bounds = [
        regime.maximum_future_c_headway_minutes
        for regime in projection.regimes
        if regime.direction == direction
        and not (
            regime.last_source_index < source_start_index
            or regime.first_source_index > source_end_index
        )
    ]
    return min((default, *bounds)) if bounds else default


def _initial_groups(
    problem: ScheduleProblemV1,
    allocation: dict[tuple[ContractDirection, str], int],
    blocks: tuple[DemandAnalysisBlockV1, ...],
    final_service_sentinels: tuple[FinalServiceSentinelV1, ...],
) -> dict[ContractDirection, list[_RegimeGroup]]:
    output: dict[ContractDirection, list[_RegimeGroup]] = {}
    sentinel_by_direction = {item.direction: item for item in final_service_sentinels}
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        compatible = tuple(
            block for block in blocks if block.direction in {direction, ContractDirection.COMBINED}
        )
        nonzero = tuple(
            (block, allocation[(direction, block.block_id)])
            for block in compatible
            if allocation[(direction, block.block_id)] > 0
        )
        cursor = 0
        groups: list[_RegimeGroup] = []
        for index, (block, count) in enumerate(nonzero):
            groups.append(
                _RegimeGroup(
                    direction=direction,
                    blocks=(block,),
                    trip_count=count,
                    source_start_index=cursor,
                    source_end_index=cursor + count - 1,
                    is_final_service_tail=index == len(nonzero) - 1,
                    has_final_service_sentinel=False,
                )
            )
            cursor += count
        sentinel = sentinel_by_direction.get(direction)
        if sentinel is not None:
            if groups:
                last = groups[-1]
                groups[-1] = _RegimeGroup(
                    direction=last.direction,
                    blocks=last.blocks,
                    trip_count=last.trip_count + 1,
                    source_start_index=last.source_start_index,
                    source_end_index=last.source_end_index + 1,
                    is_final_service_tail=True,
                    has_final_service_sentinel=True,
                )
            else:
                compatible_final = max(
                    compatible,
                    key=lambda item: (item.end_time, item.block_id),
                )
                groups.append(
                    _RegimeGroup(
                        direction=direction,
                        blocks=(compatible_final,),
                        trip_count=1,
                        source_start_index=0,
                        source_end_index=0,
                        is_final_service_tail=True,
                        has_final_service_sentinel=True,
                    )
                )
            cursor += 1
        if cursor != _direction_total(problem, direction):
            raise Stage1AllocationError(
                STAGE_1_PROBLEM_AUTHORITY_MISMATCH,
                "allocation does not reproduce a fixed directional total",
            )
        output[direction] = groups
    return output


def _merge_groups(left: _RegimeGroup, right: _RegimeGroup) -> _RegimeGroup:
    return _RegimeGroup(
        direction=left.direction,
        blocks=(*left.blocks, *right.blocks),
        trip_count=left.trip_count + right.trip_count,
        source_start_index=left.source_start_index,
        source_end_index=right.source_end_index,
        is_final_service_tail=right.is_final_service_tail,
        has_final_service_sentinel=right.has_final_service_sentinel,
    )


def _groups_are_contiguous(left: _RegimeGroup, right: _RegimeGroup) -> bool:
    return (
        left.direction == right.direction
        and left.source_end_index + 1 == right.source_start_index
        and left.blocks[-1].end_time == right.blocks[0].start_time
    )


def _representation_candidates_for_group(
    problem: ScheduleProblemV1,
    group: _RegimeGroup,
    policy: UniformIntegerRegimePolicyV3,
    projection: OrToolsProtectedFloorProjectionV1 | None,
    *,
    absolute_max_shift_per_trip_minutes: int | None = None,
    enforce_final_tail: bool = True,
    enforce_protected_floor: bool = True,
) -> tuple[
    tuple[UniformRegimeRepresentationV1, ...],
    tuple[int, int],
    tuple[int, int],
]:
    directional = _ordered_directional_trips(problem)[group.direction]
    sources = directional[group.source_start_index : group.source_end_index + 1]
    source_minutes = tuple(trip.departure_time // 60 for trip in sources)
    first_service = directional[0].departure_time // 60
    last_service = directional[-1].departure_time // 60
    block_start = min(block.start_time // 60 for block in group.blocks)
    block_end = max(block.end_time // 60 for block in group.blocks)
    lower = max(first_service, block_start)
    upper = min(
        last_service,
        block_end if group.has_final_service_sentinel else block_end - 1,
    )
    tolerance = policy.maximum_regime_boundary_adjustment_minutes
    if group.is_final_service_tail and enforce_final_tail:
        preferred_end = last_service
        preferred_start = max(
            lower,
            last_service - policy.final_service_tail.final_service_tail_window_minutes,
        )
    else:
        preferred_start = lower
        preferred_end = upper
    start_window = _boundary_window(
        preferred_start,
        lower=lower,
        upper=upper,
        tolerance=tolerance,
    )
    end_window = _boundary_window(
        preferred_end,
        lower=lower,
        upper=upper,
        tolerance=tolerance,
    )
    if group.source_start_index == 0:
        start_window = (first_service, first_service)
        preferred_start = first_service
    if group.source_end_index == len(directional) - 1:
        end_window = (last_service, last_service)
        preferred_end = last_service
    maximum = max(1, last_service - first_service)
    if group.is_final_service_tail and enforce_final_tail:
        maximum = min(
            maximum,
            policy.final_service_tail.final_service_tail_maximum_headway_minutes,
        )
    if enforce_protected_floor:
        maximum = _protected_maximum_headway(
            projection,
            group.direction,
            group.source_start_index,
            group.source_end_index,
            maximum,
        )
    candidates = _representable_uniform_regime_candidates_v1(
        source_minutes,
        permitted_start_window=start_window,
        permitted_end_window=end_window,
        minimum_headway_minutes=policy.minimum_operational_headway_minutes,
        maximum_headway_minutes=maximum,
        absolute_max_shift_per_trip_minutes=(
            policy.absolute_max_shift_per_trip_minutes
            if absolute_max_shift_per_trip_minutes is None
            else absolute_max_shift_per_trip_minutes
        ),
        preferred_start_minute=preferred_start,
        preferred_end_minute=preferred_end,
    )
    return candidates, start_window, end_window


def _exact_membership_representation(
    candidates: tuple[UniformRegimeRepresentationV1, ...],
    group: _RegimeGroup,
    allocation: dict[tuple[ContractDirection, str], int],
) -> UniformRegimeRepresentationV1 | None:
    return next(
        (
            representation
            for representation in candidates
            if all(
                sum(
                    block.start_time // 60 <= minute < block.end_time // 60
                    for minute in representation.departure_minutes
                )
                == allocation[(group.direction, block.block_id)]
                for block in group.blocks
            )
        ),
        None,
    )


def _representation_for_group(
    problem: ScheduleProblemV1,
    group: _RegimeGroup,
    policy: UniformIntegerRegimePolicyV3,
    projection: OrToolsProtectedFloorProjectionV1 | None,
    allocation: dict[tuple[ContractDirection, str], int],
) -> _GroupRepresentationProbe:
    candidates, start_window, end_window = _representation_candidates_for_group(
        problem,
        group,
        policy,
        projection,
    )
    representation = _exact_membership_representation(candidates, group, allocation)
    if representation is not None:
        return _GroupRepresentationProbe(representation, start_window, end_window, None)

    directional = _ordered_directional_trips(problem)[group.direction]
    first_service = directional[0].departure_time // 60
    last_service = directional[-1].departure_time // 60
    relaxed_shift = max(
        policy.absolute_max_shift_per_trip_minutes,
        last_service - first_service + 1,
    )
    relaxed_candidates, _, _ = _representation_candidates_for_group(
        problem,
        group,
        policy,
        projection,
        absolute_max_shift_per_trip_minutes=relaxed_shift,
    )
    if _exact_membership_representation(relaxed_candidates, group, allocation) is not None:
        failure = Stage1RegimeBuildFailureCodeV1.B_SHIFT_BOUND_UNREPRESENTABLE
    elif group.is_final_service_tail:
        relaxed_tail, _, _ = _representation_candidates_for_group(
            problem,
            group,
            policy,
            projection,
            enforce_final_tail=False,
        )
        if _exact_membership_representation(relaxed_tail, group, allocation) is not None:
            failure = Stage1RegimeBuildFailureCodeV1.FINAL_TAIL_UNREPRESENTABLE
        else:
            failure = None
    else:
        failure = None
    if failure is None and projection is not None:
        relaxed_protected, _, _ = _representation_candidates_for_group(
            problem,
            group,
            policy,
            projection,
            enforce_protected_floor=False,
        )
        if _exact_membership_representation(relaxed_protected, group, allocation) is not None:
            failure = Stage1RegimeBuildFailureCodeV1.PROTECTED_FLOOR_BLOCKED_MERGE
    if failure is None:
        failure = (
            Stage1RegimeBuildFailureCodeV1.ALLOCATION_MEMBERSHIP_UNREPRESENTABLE
            if candidates
            else Stage1RegimeBuildFailureCodeV1.GROUP_UNIFORM_REPRESENTATION_UNAVAILABLE
        )
    return _GroupRepresentationProbe(None, start_window, end_window, failure)


def _representation_shift_score(
    problem: ScheduleProblemV1,
    group: _RegimeGroup,
    representation: UniformRegimeRepresentationV1,
) -> tuple[int, int]:
    directional = _ordered_directional_trips(problem)[group.direction]
    source_minutes = tuple(
        trip.departure_time // 60
        for trip in directional[group.source_start_index : group.source_end_index + 1]
    )
    shifts = tuple(
        abs(departure - source)
        for departure, source in zip(
            representation.departure_minutes,
            source_minutes,
            strict=True,
        )
    )
    return max(shifts, default=0), sum(shifts)


def _service_rate(
    group: _RegimeGroup,
    values_by_block: dict[str, int],
) -> Fraction:
    duration = sum(block.duration_minutes for block in group.blocks)
    return Fraction(sum(values_by_block[block.block_id] for block in group.blocks) * 60, duration)


def _passenger_rate(group: _RegimeGroup) -> float:
    duration = sum(block.duration_minutes for block in group.blocks)
    return sum(block.observed_passengers for block in group.blocks) * 60.0 / duration


def _merge_score(
    problem: ScheduleProblemV1,
    left: _RegimeGroup,
    right: _RegimeGroup,
    merged: _RegimeGroup,
    representation: UniformRegimeRepresentationV1,
    required_by_block: dict[str, int],
    allocated_by_block: dict[str, int],
) -> tuple[object, ...]:
    maximum_shift, total_shift = _representation_shift_score(problem, merged, representation)
    return (
        abs(_service_rate(left, required_by_block) - _service_rate(right, required_by_block)),
        abs(_service_rate(left, allocated_by_block) - _service_rate(right, allocated_by_block)),
        round(abs(_passenger_rate(left) - _passenger_rate(right)), 12),
        maximum_shift,
        total_shift,
        left.source_start_index,
        right.source_end_index,
        tuple(block.block_id for block in merged.blocks),
    )


def _regime_build_diagnostic(
    candidate_fingerprint: str,
    direction: ContractDirection,
    initial_group_count: int,
    final_group_count: int,
    maximum_group_count: int,
    failure_code: Stage1RegimeBuildFailureCodeV1,
    groups: list[_RegimeGroup],
) -> Stage1RegimeBuildDiagnosticV1:
    block_ids = tuple(block.block_id for group in groups for block in group.blocks)
    if len(block_ids) > 6:
        block_ids = (*block_ids[:3], *block_ids[-3:])
    return finalize_stage_1_regime_build_diagnostic(
        Stage1RegimeBuildDiagnosticV1(
            allocation_candidate_fingerprint=candidate_fingerprint,
            failure_code=failure_code,
            direction=direction,
            initial_group_count=initial_group_count,
            final_group_count=final_group_count,
            maximum_group_count=maximum_group_count,
            failing_group_block_ids=block_ids,
            explanation=(
                f"Stage 1 regime construction stopped for {direction.value}: "
                f"{failure_code.value}; {initial_group_count} initial group(s), "
                f"{final_group_count} remaining group(s), cap={maximum_group_count}."
            ),
        )
    )


def _representable_regimes(
    problem: ScheduleProblemV1,
    allocation: dict[tuple[ContractDirection, str], int],
    blocks: tuple[DemandAnalysisBlockV1, ...],
    policy: UniformIntegerRegimePolicyV3,
    projection: OrToolsProtectedFloorProjectionV1 | None,
    final_service_sentinels: tuple[FinalServiceSentinelV1, ...],
    candidate_fingerprint: str,
) -> _RegimeBuildOutcome:
    groups_by_direction = _initial_groups(
        problem,
        allocation,
        blocks,
        final_service_sentinels,
    )
    requirements = {item.block_id: item.required_trips_85 for item in problem.block_requirements}
    output: list[ProposedServiceRegimeV1] = []
    for direction, original_groups in groups_by_direction.items():
        groups = list(original_groups)
        allocated = {
            block.block_id: allocation[(direction, block.block_id)]
            for block in blocks
            if block.direction in {direction, ContractDirection.COMBINED}
        }
        initial_group_count = len(groups)
        tail_target = policy.final_service_tail.final_service_tail_window_minutes
        while len(groups) >= 2:
            tail_representation = _representation_for_group(
                problem,
                groups[-1],
                policy,
                projection,
                allocation,
            )
            if tail_representation.representation is not None:
                tail_span = (
                    tail_representation.representation.end_minute
                    - tail_representation.representation.start_minute
                )
                if tail_span >= max(
                    0,
                    tail_target - policy.maximum_regime_boundary_adjustment_minutes,
                ):
                    break
            if not _groups_are_contiguous(groups[-2], groups[-1]):
                break
            expanded_tail = _merge_groups(groups[-2], groups[-1])
            expanded_probe = _representation_for_group(
                problem,
                expanded_tail,
                policy,
                projection,
                allocation,
            )
            if expanded_probe.representation is None:
                break
            groups[-2:] = [expanded_tail]
        while len(groups) > policy.maximum_headway_regimes_per_direction:
            options: list[tuple[tuple[object, ...], int, _RegimeGroup]] = []
            for index in range(len(groups) - 1):
                left, right = groups[index : index + 2]
                if not _groups_are_contiguous(left, right):
                    continue
                merged = _merge_groups(left, right)
                probe = _representation_for_group(
                    problem,
                    merged,
                    policy,
                    projection,
                    allocation,
                )
                if probe.representation is None:
                    continue
                options.append(
                    (
                        _merge_score(
                            problem,
                            left,
                            right,
                            merged,
                            probe.representation,
                            requirements,
                            allocated,
                        ),
                        index,
                        merged,
                    )
                )
            if not options:
                return _RegimeBuildOutcome(
                    regimes=None,
                    diagnostic=_regime_build_diagnostic(
                        candidate_fingerprint,
                        direction,
                        initial_group_count,
                        len(groups),
                        policy.maximum_headway_regimes_per_direction,
                        Stage1RegimeBuildFailureCodeV1.REGIME_COUNT_CAP_UNREPRESENTABLE,
                        groups,
                    ),
                )
            _, index, merged = min(options, key=lambda item: item[0])
            groups[index : index + 2] = [merged]

        while True:
            probes = [
                _representation_for_group(problem, group, policy, projection, allocation)
                for group in groups
            ]
            failing_indices = [
                index for index, probe in enumerate(probes) if probe.representation is None
            ]
            if not failing_indices:
                break
            repair_options: list[tuple[tuple[object, ...], int, _RegimeGroup]] = []
            candidate_pair_indices = sorted(
                {
                    pair_index
                    for failing_index in failing_indices
                    for pair_index in (failing_index - 1, failing_index)
                    if 0 <= pair_index < len(groups) - 1
                }
            )
            for pair_index in candidate_pair_indices:
                left, right = groups[pair_index : pair_index + 2]
                if not _groups_are_contiguous(left, right):
                    continue
                merged = _merge_groups(left, right)
                probe = _representation_for_group(
                    problem,
                    merged,
                    policy,
                    projection,
                    allocation,
                )
                if probe.representation is None:
                    continue
                repair_options.append(
                    (
                        _merge_score(
                            problem,
                            left,
                            right,
                            merged,
                            probe.representation,
                            requirements,
                            allocated,
                        ),
                        pair_index,
                        merged,
                    )
                )
            if not repair_options:
                first_failure = failing_indices[0]
                failure = probes[first_failure].failure_code
                assert failure is not None
                return _RegimeBuildOutcome(
                    regimes=None,
                    diagnostic=_regime_build_diagnostic(
                        candidate_fingerprint,
                        direction,
                        initial_group_count,
                        len(groups),
                        policy.maximum_headway_regimes_per_direction,
                        failure,
                        [groups[first_failure]],
                    ),
                )
            _, pair_index, merged = min(repair_options, key=lambda item: item[0])
            groups[pair_index : pair_index + 2] = [merged]

        for regime_index, (group, represented) in enumerate(
            zip(groups, probes, strict=True),
            start=1,
        ):
            representation = represented.representation
            assert representation is not None
            start_window = represented.start_window
            end_window = represented.end_window
            maximum = (
                policy.final_service_tail.final_service_tail_maximum_headway_minutes
                if group.is_final_service_tail
                else max(1, representation.end_minute - representation.start_minute)
            )
            maximum = _protected_maximum_headway(
                projection,
                direction,
                group.source_start_index,
                group.source_end_index,
                maximum,
            )
            output.append(
                ProposedServiceRegimeV1(
                    regime_id=f"V3-{direction.value.upper()}-{regime_index:04d}",
                    direction=direction,
                    covered_demand_block_ids=tuple(block.block_id for block in group.blocks),
                    trip_count=group.trip_count,
                    permitted_start_window=start_window,
                    permitted_end_window=end_window,
                    planned_start_minute=representation.start_minute,
                    planned_end_minute=representation.end_minute,
                    minimum_headway_minutes=policy.minimum_operational_headway_minutes,
                    maximum_headway_minutes=max(
                        policy.minimum_operational_headway_minutes,
                        maximum,
                    ),
                    uniform_headway_minutes=representation.uniform_headway_minutes,
                    boundary_reason=(
                        "FINAL_SERVICE_TAIL_ANCHORED_TO_LOCKED_LAST_DEPARTURE"
                        if group.is_final_service_tail
                        else (
                            "MERGED_SERVICE_LEVEL_AWARE_FOR_EXACT_REPRESENTABILITY"
                            if len(group.blocks) > 1
                            else "AUTHORITATIVE_DEMAND_BLOCK"
                        )
                    ),
                    is_final_service_tail=group.is_final_service_tail,
                    boundary_semantics=(
                        ServiceBoundarySemanticsV1.FINAL_SERVICE_SENTINEL
                        if group.has_final_service_sentinel
                        else ServiceBoundarySemanticsV1.HALF_OPEN_DEMAND_MEMBERSHIP
                    ),
                )
            )
    return _RegimeBuildOutcome(regimes=tuple(output), diagnostic=None)


def _allocation_blocks(
    problem: ScheduleProblemV1,
    model_bundle: _AllocationModel,
    allocation: dict[tuple[ContractDirection, str], int],
) -> tuple[TripAllocationBlockV1, ...]:
    requirements = {item.block_id: item for item in problem.block_requirements}
    output: list[TripAllocationBlockV1] = []
    for block in model_bundle.blocks:
        directions = (
            (block.direction,)
            if block.direction in {ContractDirection.OUTBOUND, ContractDirection.INBOUND}
            else (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
        )
        directional_counts = tuple(
            (direction, allocation[(direction, block.block_id)]) for direction in directions
        )
        requirement = requirements[block.block_id]
        output.append(
            TripAllocationBlockV1(
                block_id=block.block_id,
                direction=block.direction,
                start_minute=block.start_time // 60,
                end_minute=block.end_time // 60,
                trip_count=sum(value for _, value in directional_counts),
                observed_passengers=block.observed_passengers,
                required_trips_90=requirement.required_trips_90,
                required_trips_85=requirement.required_trips_85,
                source_b_trip_count=sum(
                    _source_count(problem, block, direction) for direction in directions
                ),
                protected_minimum_trip_count=sum(
                    model_bundle.protected_minimum_by_direction_and_block.get(
                        (direction, block.block_id),
                        0,
                    )
                    for direction in directions
                ),
                directional_trip_counts=directional_counts,
            )
        )
    return tuple(output)


def _allocation_candidate_fingerprint(
    problem: ScheduleProblemV1,
    allocation: dict[tuple[ContractDirection, str], int],
    policy: UniformIntegerRegimePolicyV3,
) -> str:
    return canonical_sha256(
        {
            "profile": STAGE_1_ALLOCATION_MODEL_PROFILE_V1,
            "source_b_fingerprint": problem.source_b_fingerprint,
            "policy_fingerprint": policy.policy_fingerprint,
            "allocation": [
                {
                    "direction": direction.value,
                    "block_id": block_id,
                    "trip_count": count,
                }
                for (direction, block_id), count in sorted(
                    allocation.items(),
                    key=lambda item: (item[0][0].value, item[0][1]),
                )
            ],
        }
    )


def _source_ids_by_regime(
    problem: ScheduleProblemV1,
    regimes: tuple[ProposedServiceRegimeV1, ...],
) -> dict[str, tuple[str, ...]]:
    directional = _ordered_directional_trips(problem)
    output: dict[str, tuple[str, ...]] = {}
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        cursor = 0
        ordered_regimes = sorted(
            (item for item in regimes if item.direction == direction),
            key=lambda item: (
                item.planned_start_minute,
                item.planned_end_minute,
                item.regime_id,
            ),
        )
        for regime in ordered_regimes:
            members = directional[direction][cursor : cursor + regime.trip_count]
            if len(members) != regime.trip_count:
                return {}
            output[regime.regime_id] = tuple(item.trip_id for item in members)
            cursor += regime.trip_count
        if cursor != len(directional[direction]):
            return {}
    return output


def _necessary_departure_domains(
    problem: ScheduleProblemV1,
    regimes: tuple[ProposedServiceRegimeV1, ...],
    final_service_sentinels: tuple[FinalServiceSentinelV1, ...],
    policy: UniformIntegerRegimePolicyV3,
) -> tuple[dict[str, tuple[int, int]], tuple[Stage2ConstraintFamilyV1, ...]]:
    source_ids_by_regime = _source_ids_by_regime(problem, regimes)
    if not source_ids_by_regime:
        return {}, (Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP,)
    regime_by_source = {
        source_id: regime
        for regime in regimes
        for source_id in source_ids_by_regime[regime.regime_id]
    }
    sentinel_by_source = {item.source_b_trip_id: item for item in final_service_sentinels}
    blocks = {item.block_id: item for item in problem.analysis_blocks}
    directional = _ordered_directional_trips(problem)
    output: dict[str, tuple[int, int]] = {}
    failures: set[Stage2ConstraintFamilyV1] = set()
    for trips in directional.values():
        service_start = trips[0].departure_time // 60
        service_end = trips[-1].departure_time // 60
        for source in trips:
            regime = regime_by_source[source.trip_id]
            covered = tuple(blocks[item] for item in regime.covered_demand_block_ids)
            regime_start = min(item.start_time // 60 for item in covered)
            regime_end = max(item.end_time // 60 - 1 for item in covered)
            sentinel = sentinel_by_source.get(source.trip_id)
            if sentinel is not None:
                regime_end = max(regime_end, sentinel.departure_minute)
            source_minute = source.departure_time // 60
            lower = max(
                service_start,
                regime_start,
                source_minute - policy.absolute_max_shift_per_trip_minutes,
            )
            upper = min(
                service_end,
                regime_end,
                source_minute + policy.absolute_max_shift_per_trip_minutes,
            )
            members = source_ids_by_regime[regime.regime_id]
            if source.trip_id == members[0]:
                lower = max(lower, regime.permitted_start_window[0])
                upper = min(upper, regime.permitted_start_window[1])
            if source.trip_id == members[-1]:
                lower = max(lower, regime.permitted_end_window[0])
                upper = min(upper, regime.permitted_end_window[1])
            if lower > upper:
                failures.update(
                    {
                        Stage2ConstraintFamilyV1.REGIME_BOUNDARIES,
                        Stage2ConstraintFamilyV1.B_SHIFT_BOUND,
                    }
                )
                if source is trips[0] or source is trips[-1]:
                    failures.add(Stage2ConstraintFamilyV1.FIRST_LAST_LOCK)
                if regime.is_final_service_tail:
                    failures.add(Stage2ConstraintFamilyV1.FINAL_SERVICE_TAIL)
                continue
            output[source.trip_id] = (lower, upper)
    return output, tuple(sorted(failures, key=lambda item: item.value))


def _fleet_lower_bound(
    problem: ScheduleProblemV1,
    domains: dict[str, tuple[int, int]],
) -> int:
    """Return a safe lower bound from intervals every feasible departure must occupy."""
    mandatory_intervals: list[tuple[int, int]] = []
    for source in problem.scenario_b.exact_timetable:
        lower, upper = domains[source.trip_id]
        turnaround = (
            problem.scenario_b.turnaround_minutes.terminal_2
            if source.direction == ContractDirection.OUTBOUND
            else problem.scenario_b.turnaround_minutes.terminal_1
        )
        earliest_ready = lower + source.runtime_minutes + turnaround
        if upper < earliest_ready:
            mandatory_intervals.append((upper, earliest_ready))
    if not mandatory_intervals:
        return 1
    points = sorted({value for interval in mandatory_intervals for value in interval})
    return max(
        1,
        max(sum(start <= minute < end for start, end in mandatory_intervals) for minute in points),
    )


def evaluate_stage_1_necessary_feasibility_v1(
    problem: ScheduleProblemV1,
    allocation: dict[tuple[ContractDirection, str], int],
    allocation_blocks: tuple[TripAllocationBlockV1, ...],
    regimes: tuple[ProposedServiceRegimeV1, ...],
    final_service_sentinels: tuple[FinalServiceSentinelV1, ...],
    policy: UniformIntegerRegimePolicyV3,
) -> Stage1NecessaryFeasibilityResultV1:
    """Apply cheap necessary Stage 2 checks without recreating the exact CP-SAT model."""
    candidate_fingerprint = _allocation_candidate_fingerprint(problem, allocation, policy)
    source_by_id = {item.trip_id: item for item in problem.scenario_b.exact_timetable}
    source_ids_by_regime = _source_ids_by_regime(problem, regimes)
    failures: set[Stage2ConstraintFamilyV1] = set()
    represented_by_regime: dict[str, tuple[int, ...]] = {}
    if not source_ids_by_regime:
        failures.add(Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP)
    for regime in regimes:
        source_ids = source_ids_by_regime.get(regime.regime_id, ())
        source_minutes = tuple(source_by_id[item].departure_time // 60 for item in source_ids)
        represented = find_representable_uniform_regime_v1(
            source_minutes,
            permitted_start_window=regime.permitted_start_window,
            permitted_end_window=regime.permitted_end_window,
            minimum_headway_minutes=regime.minimum_headway_minutes,
            maximum_headway_minutes=regime.maximum_headway_minutes,
            absolute_max_shift_per_trip_minutes=policy.absolute_max_shift_per_trip_minutes,
            preferred_start_minute=regime.planned_start_minute,
            preferred_end_minute=regime.planned_end_minute,
        )
        if represented is None:
            failures.update(
                {
                    Stage2ConstraintFamilyV1.UNIFORM_HEADWAY,
                    Stage2ConstraintFamilyV1.REGIME_BOUNDARIES,
                    Stage2ConstraintFamilyV1.B_SHIFT_BOUND,
                }
            )
            if regime.is_final_service_tail:
                failures.update(
                    {
                        Stage2ConstraintFamilyV1.FINAL_SERVICE_TAIL,
                        Stage2ConstraintFamilyV1.FIRST_LAST_LOCK,
                    }
                )
            continue
        represented_by_regime[regime.regime_id] = represented.departure_minutes

    for block in allocation_blocks:
        for direction, expected in block.directional_trip_counts:
            actual = sum(
                block.start_minute <= minute < block.end_minute
                for regime in regimes
                if regime.direction == direction
                for minute in represented_by_regime.get(regime.regime_id, ())
            )
            if actual != expected:
                failures.add(Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP)

    domains, domain_failures = _necessary_departure_domains(
        problem,
        regimes,
        final_service_sentinels,
        policy,
    )
    failures.update(domain_failures)
    fleet_lower_bound = None
    if len(domains) == problem.scenario_b.total_daily_trips:
        fleet_lower_bound = _fleet_lower_bound(problem, domains)
        if fleet_lower_bound > problem.scenario_b.available_fleet_limit:
            failures.add(Stage2ConstraintFamilyV1.FLEET)
    passed = not failures
    if passed:
        explanation = (
            "Stage 1 plan passed exact arithmetic-progression, B-anchor, half-open allocation, "
            f"final-tail, and safe fleet lower-bound checks (fleet lower bound "
            f"{fleet_lower_bound})."
        )
    else:
        explanation = (
            "Stage 1 plan failed cheap necessary Stage 2 checks for: "
            + ", ".join(item.value for item in sorted(failures, key=lambda item: item.value))
            + "."
        )
    return finalize_stage_1_necessary_feasibility(
        Stage1NecessaryFeasibilityResultV1(
            allocation_candidate_fingerprint=candidate_fingerprint,
            passed=passed,
            constraint_families=tuple(sorted(failures, key=lambda item: item.value)),
            fleet_lower_bound=fleet_lower_bound,
            explanation=explanation,
        )
    )


def _stage1_status(status: NativeSolverStatus) -> TripAllocationSolveStatusV1:
    return {
        NativeSolverStatus.OPTIMAL: TripAllocationSolveStatusV1.OPTIMAL,
        NativeSolverStatus.FEASIBLE: TripAllocationSolveStatusV1.FEASIBLE,
        NativeSolverStatus.INFEASIBLE: TripAllocationSolveStatusV1.INFEASIBLE,
        NativeSolverStatus.UNKNOWN: TripAllocationSolveStatusV1.NOT_FOUND_WITHIN_SOLVE_LIMIT,
        NativeSolverStatus.MODEL_INVALID: TripAllocationSolveStatusV1.INFEASIBLE,
    }[status]


def allocate_trips_stage_1_v1(
    problem: ScheduleProblemV1,
    demand_authority: TwoStageDemandAuthorityV1,
    *,
    policy: UniformIntegerRegimePolicyV3 | None = None,
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None,
    time_limit_seconds: float,
    worker_count: int = 1,
    random_seed: int = 0,
) -> Stage1AllocationResultV1:
    """Return a bounded ranked set of allocation plans within one Stage 1 budget."""
    if (
        not math.isfinite(time_limit_seconds)
        or time_limit_seconds <= 0
        or isinstance(time_limit_seconds, bool)
    ):
        raise ValueError("Stage 1 time_limit_seconds must be finite and positive")
    effective_policy = policy or UniformIntegerRegimePolicyV3()
    if (
        problem.source_b_fingerprint != demand_authority.source_b_fingerprint
        or problem.observed_demand_fingerprint != demand_authority.observed_demand_fingerprint
        or problem.demand_allocation_authority_mode != demand_authority.authority_mode
    ):
        raise Stage1AllocationError(
            STAGE_1_PROBLEM_AUTHORITY_MISMATCH,
            "problem and two-stage demand authority fingerprints or modes differ",
        )
    started = time.perf_counter()
    bundle = _build_allocation_model(
        problem,
        demand_authority,
        effective_policy,
        protected_service_floor_enforcement_authority,
    )
    _, projection = _protected_minimums(
        problem,
        bundle.blocks,
        protected_service_floor_enforcement_authority,
    )
    plans: list[TripAllocationPlanV1] = []
    pruned_necessary_feasibility: list[Stage1NecessaryFeasibilityResultV1] = []
    regime_build_rejected_count = 0
    regime_build_failure_counts: Counter[Stage1RegimeBuildFailureCodeV1] = Counter()
    regime_build_examples: list[Stage1RegimeBuildDiagnosticV1] = []
    candidate_count = 0
    last_status = NativeSolverStatus.UNKNOWN
    while len(plans) < effective_policy.maximum_stage_1_alternative_plans:
        elapsed = max(0.0, time.perf_counter() - started)
        remaining = max(0.0, time_limit_seconds - elapsed)
        if remaining <= 0:
            break
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = remaining
        solver.parameters.num_search_workers = worker_count
        solver.parameters.random_seed = random_seed
        last_status = _map_cp_sat_status(solver.solve(bundle.model))
        if last_status not in {NativeSolverStatus.OPTIMAL, NativeSolverStatus.FEASIBLE}:
            break
        candidate_count += 1
        allocation = {
            key: int(solver.value(value))
            for key, value in bundle.count_by_direction_and_block.items()
        }
        objective_vector = tuple(int(solver.value(term)) for term in bundle.objective_terms)
        candidate_fingerprint = _allocation_candidate_fingerprint(
            problem,
            allocation,
            effective_policy,
        )
        regime_build = _representable_regimes(
            problem,
            allocation,
            bundle.blocks,
            effective_policy,
            projection,
            bundle.final_service_sentinels,
            candidate_fingerprint,
        )
        if regime_build.regimes is not None:
            regimes = regime_build.regimes
            allocation_blocks = _allocation_blocks(problem, bundle, allocation)
            necessary_feasibility = evaluate_stage_1_necessary_feasibility_v1(
                problem,
                allocation,
                allocation_blocks,
                regimes,
                bundle.final_service_sentinels,
                effective_policy,
            )
            if not necessary_feasibility.passed:
                pruned_necessary_feasibility.append(necessary_feasibility)
            else:
                duration = max(0.0, time.perf_counter() - started)
                plan = TripAllocationPlanV1(
                    source_b_fingerprint=problem.source_b_fingerprint,
                    demand_authority_fingerprint=demand_authority.authority_fingerprint,
                    optimization_mode=problem.optimization_mode,
                    demand_authority_mode=demand_authority.authority_mode,
                    allocation_plan_profile=TRIP_ALLOCATION_PLAN_PROFILE_V1,
                    uniform_regime_profile=SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE,
                    final_tail_policy_fingerprint=effective_policy.policy_fingerprint,
                    total_trips=problem.scenario_b.total_daily_trips,
                    trips_by_direction=(
                        (
                            ContractDirection.OUTBOUND,
                            problem.scenario_b.trips_by_direction.outbound,
                        ),
                        (
                            ContractDirection.INBOUND,
                            problem.scenario_b.trips_by_direction.inbound,
                        ),
                    ),
                    allocation_blocks=allocation_blocks,
                    proposed_regimes=regimes,
                    final_service_sentinels=bundle.final_service_sentinels,
                    necessary_feasibility=necessary_feasibility,
                    objective_vector=objective_vector,
                    solve_status=_stage1_status(last_status),
                    solve_duration_seconds=duration,
                    allocation_fingerprint="",
                    rank=len(plans) + 1,
                )
                plans.append(finalize_allocation_plan(plan))
        else:
            diagnostic = regime_build.diagnostic
            assert diagnostic is not None
            regime_build_rejected_count += 1
            regime_build_failure_counts[diagnostic.failure_code] += 1
            if len(regime_build_examples) < 8:
                regime_build_examples.append(diagnostic)
        literals = []
        for index, (key, variable) in enumerate(
            sorted(
                bundle.count_by_direction_and_block.items(),
                key=lambda item: (item[0][0].value, item[0][1]),
            )
        ):
            different = bundle.model.new_bool_var(
                f"stage1_alternative_{candidate_count:04d}_{index:04d}"
            )
            bundle.model.add(variable != allocation[key]).only_enforce_if(different)
            bundle.model.add(variable == allocation[key]).only_enforce_if(different.negated())
            literals.append(different)
        bundle.model.add_bool_or(literals)

    duration = max(0.0, time.perf_counter() - started)
    budget_exhausted = duration >= time_limit_seconds
    if plans:
        status = (
            TripAllocationSolveStatusV1.OPTIMAL
            if plans[0].solve_status == TripAllocationSolveStatusV1.OPTIMAL
            else TripAllocationSolveStatusV1.FEASIBLE
        )
    elif candidate_count and last_status == NativeSolverStatus.INFEASIBLE:
        status = TripAllocationSolveStatusV1.UNREPRESENTABLE
    elif last_status == NativeSolverStatus.INFEASIBLE:
        status = TripAllocationSolveStatusV1.INFEASIBLE
    else:
        status = TripAllocationSolveStatusV1.NOT_FOUND_WITHIN_SOLVE_LIMIT
    return Stage1AllocationResultV1(
        solve_status=status,
        plans=tuple(plans),
        candidate_count=candidate_count,
        admissible_allocation_count=len(plans),
        necessary_feasibility_pruned_count=len(pruned_necessary_feasibility),
        pruned_necessary_feasibility=tuple(pruned_necessary_feasibility),
        solve_duration_seconds=duration,
        budget_exhausted=budget_exhausted,
        explanations=(
            f"Stage 1 evaluated {candidate_count} bounded integer allocation candidate(s) and "
            f"produced {len(plans)} V3-representable, necessary-feasible plan(s); "
            f"{regime_build_rejected_count} candidate(s) were rejected during regime build and "
            f"{len(pruned_necessary_feasibility)} candidate(s) were pruned by later deterministic "
            "necessary-feasibility domain/fleet checks.",
        ),
        limitations=(
            *demand_authority.limitations,
            "Stage 1 assigns counts and representable regime boundaries only; exact source-trip "
            "minute positions remain Stage 2 authority.",
        ),
        regime_build_rejected_count=regime_build_rejected_count,
        regime_build_failure_reason_counts=tuple(
            sorted(regime_build_failure_counts.items(), key=lambda item: item[0].value)
        ),
        regime_build_example_diagnostics=tuple(regime_build_examples),
    )


__all__ = [
    "STAGE_1_ALLOCATION_MODEL_PROFILE_V1",
    "STAGE_1_PROBLEM_AUTHORITY_MISMATCH",
    "STAGE_1_REGIME_UNREPRESENTABLE",
    "Stage1AllocationError",
    "UniformRegimeRepresentationV1",
    "allocate_trips_stage_1_v1",
    "evaluate_stage_1_necessary_feasibility_v1",
    "find_representable_uniform_regime_v1",
]
