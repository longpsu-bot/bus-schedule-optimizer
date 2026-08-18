"""Stage 1 integer trip allocation and V3 representable-regime planning."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ortools.sat.python import cp_model

from bus_schedule_engine.models import ProtectedServiceFloorEnforcementAuthorityV1

from .demand_resolution import DemandAnalysisBlockV1
from .models import ContractDirection, DemandAllocationAuthorityModeV1
from .ortools_protected_floor import (
    OrToolsProtectedFloorProjectionV1,
    build_ortools_protected_floor_projection_v1,
)
from .ortools_solver import _map_cp_sat_status, _ordered_directional_trips
from .solver_models import NativeSolverStatus, ScheduleProblemV1
from .two_stage_authority import TwoStageDemandAuthorityV1
from .two_stage_models import (
    SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE,
    TRIP_ALLOCATION_PLAN_PROFILE_V1,
    ProposedServiceRegimeV1,
    Stage1AllocationResultV1,
    TripAllocationBlockV1,
    TripAllocationPlanV1,
    TripAllocationSolveStatusV1,
    UniformIntegerRegimePolicyV3,
    finalize_allocation_plan,
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


@dataclass(frozen=True, slots=True)
class _RegimeGroup:
    direction: ContractDirection
    blocks: tuple[DemandAnalysisBlockV1, ...]
    trip_count: int
    source_start_index: int
    source_end_index: int
    is_final_service_tail: bool


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
    if not source_b_minutes:
        return None
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
            return None
        minute = min(range(lower, upper + 1), key=lambda item: abs(item - preferred_start_minute))
        return UniformRegimeRepresentationV1(
            start_minute=minute,
            end_minute=minute,
            uniform_headway_minutes=None,
            departure_minutes=(minute,),
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
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


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
        model.add(sum(directional_values) == _direction_total(problem, direction))

        compatible_blocks = tuple(
            block for block in blocks if block.direction in {direction, ContractDirection.COMBINED}
        )
        last_block = max(compatible_blocks, key=lambda item: (item.end_time, item.block_id))
        total = _direction_total(problem, direction)
        if total >= policy.final_service_tail.final_service_tail_minimum_trip_count:
            model.add(
                counts[(direction, last_block.block_id)]
                >= policy.final_service_tail.final_service_tail_minimum_trip_count
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


def _materially_mergeable(
    left: _RegimeGroup,
    right: _RegimeGroup,
    policy: UniformIntegerRegimePolicyV3,
) -> bool:
    left_duration = sum(block.duration_minutes for block in left.blocks)
    right_duration = sum(block.duration_minutes for block in right.blocks)
    left_demand = sum(block.observed_passengers for block in left.blocks) / max(1, left_duration)
    right_demand = sum(block.observed_passengers for block in right.blocks) / max(1, right_duration)
    denominator = max(left_demand, right_demand, 1e-9)
    return abs(left_demand - right_demand) / denominator < (
        policy.minimum_material_service_rate_change_ratio
    )


def _initial_groups(
    problem: ScheduleProblemV1,
    allocation: dict[tuple[ContractDirection, str], int],
    blocks: tuple[DemandAnalysisBlockV1, ...],
) -> dict[ContractDirection, list[_RegimeGroup]]:
    output: dict[ContractDirection, list[_RegimeGroup]] = {}
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
                )
            )
            cursor += count
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
    )


def _representation_for_group(
    problem: ScheduleProblemV1,
    group: _RegimeGroup,
    policy: UniformIntegerRegimePolicyV3,
    projection: OrToolsProtectedFloorProjectionV1 | None,
    allocation: dict[tuple[ContractDirection, str], int],
) -> tuple[UniformRegimeRepresentationV1, tuple[int, int], tuple[int, int]] | None:
    directional = _ordered_directional_trips(problem)[group.direction]
    sources = directional[group.source_start_index : group.source_end_index + 1]
    source_minutes = tuple(trip.departure_time // 60 for trip in sources)
    first_service = directional[0].departure_time // 60
    last_service = directional[-1].departure_time // 60
    block_start = min(block.start_time // 60 for block in group.blocks)
    block_end = max(block.end_time // 60 for block in group.blocks)
    lower = max(first_service, block_start)
    upper = min(last_service, block_end - 1)
    tolerance = policy.maximum_regime_boundary_adjustment_minutes
    if group.is_final_service_tail:
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
    if group.is_final_service_tail:
        maximum = min(
            maximum,
            policy.final_service_tail.final_service_tail_maximum_headway_minutes,
        )
    maximum = _protected_maximum_headway(
        projection,
        group.direction,
        group.source_start_index,
        group.source_end_index,
        maximum,
    )
    representation = find_representable_uniform_regime_v1(
        source_minutes,
        permitted_start_window=start_window,
        permitted_end_window=end_window,
        minimum_headway_minutes=policy.minimum_operational_headway_minutes,
        maximum_headway_minutes=maximum,
        absolute_max_shift_per_trip_minutes=policy.absolute_max_shift_per_trip_minutes,
        preferred_start_minute=preferred_start,
        preferred_end_minute=preferred_end,
    )
    if representation is None:
        return None
    for block in group.blocks:
        represented_count = sum(
            block.start_time // 60 <= minute < block.end_time // 60
            for minute in representation.departure_minutes
        )
        if represented_count != allocation[(group.direction, block.block_id)]:
            return None
    return representation, start_window, end_window


def _representable_regimes(
    problem: ScheduleProblemV1,
    allocation: dict[tuple[ContractDirection, str], int],
    blocks: tuple[DemandAnalysisBlockV1, ...],
    policy: UniformIntegerRegimePolicyV3,
    projection: OrToolsProtectedFloorProjectionV1 | None,
) -> tuple[ProposedServiceRegimeV1, ...] | None:
    groups_by_direction = _initial_groups(problem, allocation, blocks)
    output: list[ProposedServiceRegimeV1] = []
    for direction, original_groups in groups_by_direction.items():
        groups = list(original_groups)
        tail_target = policy.final_service_tail.final_service_tail_window_minutes
        while len(groups) >= 2:
            tail_representation = _representation_for_group(
                problem,
                groups[-1],
                policy,
                projection,
                allocation,
            )
            if tail_representation is not None:
                tail_span = tail_representation[0].end_minute - tail_representation[0].start_minute
                if tail_span >= max(
                    0,
                    tail_target - policy.maximum_regime_boundary_adjustment_minutes,
                ):
                    break
            expanded_tail = _merge_groups(groups[-2], groups[-1])
            if (
                _representation_for_group(
                    problem,
                    expanded_tail,
                    policy,
                    projection,
                    allocation,
                )
                is None
            ):
                break
            groups[-2:] = [expanded_tail]
        while len(groups) > policy.maximum_headway_regimes_per_direction:
            options = [
                (index, _merge_groups(groups[index], groups[index + 1]))
                for index in range(len(groups) - 1)
                if _materially_mergeable(groups[index], groups[index + 1], policy)
            ]
            if not options:
                return None
            index, merged = min(options, key=lambda item: item[1].trip_count)
            groups[index : index + 2] = [merged]

        index = 0
        while index < len(groups):
            group = groups[index]
            represented = _representation_for_group(
                problem,
                group,
                policy,
                projection,
                allocation,
            )
            if (
                represented is None
                and index + 1 < len(groups)
                and _materially_mergeable(
                    group,
                    groups[index + 1],
                    policy,
                )
            ):
                groups[index : index + 2] = [_merge_groups(group, groups[index + 1])]
                continue
            if (
                represented is None
                and index > 0
                and _materially_mergeable(
                    groups[index - 1],
                    group,
                    policy,
                )
            ):
                groups[index - 1 : index + 1] = [_merge_groups(groups[index - 1], group)]
                index -= 1
                continue
            if represented is None:
                return None
            representation, start_window, end_window = represented
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
                    regime_id=f"V3-{direction.value.upper()}-{index + 1:04d}",
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
                            "MERGED_NON_MATERIAL_DEMAND_BLOCKS_FOR_EXACT_REPRESENTABILITY"
                            if len(group.blocks) > 1
                            else "AUTHORITATIVE_DEMAND_BLOCK"
                        )
                    ),
                    is_final_service_tail=group.is_final_service_tail,
                )
            )
            index += 1
    return tuple(output)


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
        regimes = _representable_regimes(
            problem,
            allocation,
            bundle.blocks,
            effective_policy,
            projection,
        )
        if regimes is not None:
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
                    (ContractDirection.OUTBOUND, problem.scenario_b.trips_by_direction.outbound),
                    (ContractDirection.INBOUND, problem.scenario_b.trips_by_direction.inbound),
                ),
                allocation_blocks=_allocation_blocks(problem, bundle, allocation),
                proposed_regimes=regimes,
                objective_vector=objective_vector,
                solve_status=_stage1_status(last_status),
                solve_duration_seconds=duration,
                allocation_fingerprint="",
                rank=len(plans) + 1,
            )
            plans.append(finalize_allocation_plan(plan))
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
        solve_duration_seconds=duration,
        budget_exhausted=budget_exhausted,
        explanations=(
            f"Stage 1 evaluated {candidate_count} bounded integer allocation candidate(s) and "
            f"produced {len(plans)} V3-representable plan(s).",
        ),
        limitations=(
            *demand_authority.limitations,
            "Stage 1 assigns counts and representable regime boundaries only; exact source-trip "
            "minute positions remain Stage 2 authority.",
        ),
    )


__all__ = [
    "STAGE_1_ALLOCATION_MODEL_PROFILE_V1",
    "STAGE_1_PROBLEM_AUTHORITY_MISMATCH",
    "STAGE_1_REGIME_UNREPRESENTABLE",
    "Stage1AllocationError",
    "UniformRegimeRepresentationV1",
    "allocate_trips_stage_1_v1",
    "find_representable_uniform_regime_v1",
]
