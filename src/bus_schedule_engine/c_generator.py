from __future__ import annotations

import itertools
from collections import Counter
from dataclasses import asdict, dataclass, replace
from statistics import mean, pstdev

from .c_config import FIXED_RESOURCE_STRATEGY_ID, SCENARIO_C_DISPLAY_NAME, ScenarioCConfig
from .demand import evaluate_scenario
from .fingerprint import timetable_fingerprint
from .fleet import assign_fleet
from .models import (
    DemandRecord,
    Direction,
    GeneratedScenario,
    HeadwayRegime,
    HeadwayType,
    OptimizationLog,
    RegimeBoundaryReason,
    RegularityMetrics,
    ScenarioCStatus,
    ScenarioParameters,
    Trip,
    TripTrace,
)
from .time_utils import block_label
from .validator import validate_schedule


@dataclass(frozen=True)
class _RegimeDraft:
    start_index: int
    end_index: int
    target_headway_minutes: float
    actual_headways: tuple[float, ...]
    boundary_reason: RegimeBoundaryReason


@dataclass(frozen=True)
class _DirectionPlan:
    direction: Direction
    times: tuple[int, ...]
    regimes: tuple[_RegimeDraft, ...]
    headway_types: tuple[HeadwayType, ...]
    distance_to_demand_minutes: float
    shifted_trip_count: int
    total_shift_minutes: float
    maximum_shift_minutes: float


@dataclass
class _Candidate:
    trips: list[Trip]
    regimes: list[HeadwayRegime]
    traces: list[TripTrace]
    regularity: RegularityMetrics
    objective: tuple[float, ...]
    reason: str
    fleet_minimum: int
    evaluation: object


def _ordered_direction_trips(trips: list[Trip], direction: Direction) -> list[Trip]:
    return sorted(
        (trip for trip in trips if trip.direction == direction),
        key=lambda trip: (trip.departure_seconds, trip.trip_id),
    )


def _direction_demand(
    demand: list[DemandRecord], direction: Direction
) -> tuple[list[DemandRecord], bool]:
    directional = [record for record in demand if record.direction == direction]
    if directional:
        return directional, False
    return [record for record in demand if record.direction == Direction.COMBINED], True


def _continuous_demand_targets(
    source_times: list[int], direction: Direction, demand: list[DemandRecord]
) -> list[int]:
    if len(source_times) <= 2:
        return list(source_times)
    first, last = source_times[0], source_times[-1]
    records, _ = _direction_demand(demand, direction)
    relevant = [
        record
        for record in records
        if record.block_end_seconds > first and record.block_start_seconds < last
    ]
    if not relevant or sum(record.average_daily_demand for record in relevant) <= 0:
        return _balanced_times(first, last, len(source_times))

    boundaries = {first, last}
    for record in relevant:
        boundaries.add(max(first, record.block_start_seconds))
        boundaries.add(min(last, record.block_end_seconds))
    ordered_boundaries = sorted(boundaries)
    segments: list[tuple[int, int, float]] = []
    for start, end in zip(ordered_boundaries, ordered_boundaries[1:], strict=False):
        if end <= start:
            continue
        mass = 0.0
        for record in relevant:
            overlap = max(
                0,
                min(end, record.block_end_seconds) - max(start, record.block_start_seconds),
            )
            duration = max(1, record.block_end_seconds - record.block_start_seconds)
            mass += record.average_daily_demand * overlap / duration
        segments.append((start, end, mass))
    total_mass = sum(mass for _, _, mass in segments)
    if total_mass <= 0:
        return _balanced_times(first, last, len(source_times))

    targets = [first]
    for index in range(1, len(source_times) - 1):
        quantile = total_mass * index / (len(source_times) - 1)
        cumulative = 0.0
        departure = first
        for segment_index, (start, end, mass) in enumerate(segments):
            next_cumulative = cumulative + mass
            if mass > 0 and (quantile <= next_cumulative or segment_index == len(segments) - 1):
                ratio = min(1.0, max(0.0, (quantile - cumulative) / mass))
                departure = round((start + ratio * (end - start)) / 60) * 60
                break
            cumulative = next_cumulative
        targets.append(departure)
    targets.append(last)
    return _strict_times(targets, first, last, minimum_gap_seconds=60)


def _strict_times(
    values: list[int], first: int, last: int, *, minimum_gap_seconds: int
) -> list[int]:
    if not values:
        return []
    if len(values) == 1:
        return [first]
    if last - first < minimum_gap_seconds * (len(values) - 1):
        raise ValueError("Cửa sổ khai thác không đủ dài để tạo các giờ đi riêng biệt")
    ordered = sorted(values)
    ordered[0] = first
    ordered[-1] = last
    for index in range(1, len(ordered) - 1):
        latest = last - minimum_gap_seconds * (len(ordered) - 1 - index)
        ordered[index] = min(
            latest,
            max(ordered[index - 1] + minimum_gap_seconds, ordered[index]),
        )
    return ordered


def _balanced_values(total: int, intervals: int) -> list[int]:
    if intervals <= 0:
        return []
    base, remainder = divmod(total, intervals)
    return [
        base
        + (1 if ((index + 1) * remainder) // intervals > (index * remainder) // intervals else 0)
        for index in range(intervals)
    ]


def _balanced_times(start: int, end: int, trip_count: int) -> list[int]:
    if trip_count <= 0:
        return []
    if trip_count == 1:
        return [start]
    intervals = trip_count - 1
    duration = end - start
    if duration < intervals * 60:
        raise ValueError("Khoảng neo không đủ dài để giữ thứ tự chuyến")
    if start % 60 == 0 and end % 60 == 0:
        gaps = [value * 60 for value in _balanced_values(duration // 60, intervals)]
    else:
        gaps = _balanced_values(duration, intervals)
    output = [start]
    for gap in gaps:
        output.append(output[-1] + gap)
    output[-1] = end
    return output


def _material_boundaries(
    target_times: list[int], config: ScenarioCConfig
) -> list[tuple[int, float]]:
    gaps = [
        (right - left) / 60 for left, right in zip(target_times, target_times[1:], strict=False)
    ]
    sustained = config.minimum_sustained_change_intervals
    candidates: list[tuple[int, float]] = []
    for index in range(sustained, len(gaps) - sustained + 1):
        left = mean(gaps[index - sustained : index])
        right = mean(gaps[index : index + sustained])
        absolute_change = abs(left - right)
        rate_change = abs((60 / max(right, 0.001)) - (60 / max(left, 0.001))) / max(
            60 / max(left, 0.001),
            0.001,
        )
        if (
            absolute_change >= config.minimum_material_headway_change_minutes
            or rate_change >= config.minimum_material_service_rate_change_ratio
        ):
            candidates.append((index, absolute_change + 10 * rate_change))

    selected: list[tuple[int, float]] = []
    for index, score in sorted(candidates, key=lambda item: (-item[1], item[0])):
        if any(abs(index - existing) < sustained for existing, _ in selected):
            continue
        selected.append((index, score))
        if len(selected) >= config.maximum_headway_regimes_per_direction - 1:
            break
    return sorted(selected)


def _regime_drafts(
    times: list[int], boundary_indices: list[int]
) -> tuple[tuple[_RegimeDraft, ...], tuple[HeadwayType, ...]]:
    anchors = [0, *boundary_indices, len(times) - 1]
    regimes: list[_RegimeDraft] = []
    headway_types = [HeadwayType.REGULAR] * len(times)
    previous_target: float | None = None
    for regime_index, (start_index, end_index) in enumerate(
        zip(anchors, anchors[1:], strict=False)
    ):
        gaps = tuple(
            (times[index] - times[index - 1]) / 60
            for index in range(start_index + 1, end_index + 1)
        )
        target = (times[end_index] - times[start_index]) / 60 / max(1, end_index - start_index)
        if regime_index == 0:
            reason = RegimeBoundaryReason.FIRST_SERVICE_CONSTRAINT
        elif regime_index == len(anchors) - 2:
            reason = RegimeBoundaryReason.FINAL_SERVICE_CONSTRAINT
        else:
            reason = RegimeBoundaryReason.SUSTAINED_DEMAND_CHANGE
        regimes.append(_RegimeDraft(start_index, end_index, target, gaps, reason))
        gap_type = (
            HeadwayType.REGULAR
            if not gaps or max(gaps) - min(gaps) == 0
            else HeadwayType.BALANCED_ROUNDING
        )
        for trip_index in range(start_index + 1, end_index + 1):
            headway_types[trip_index] = gap_type
        if (
            regime_index > 0
            and previous_target is not None
            and abs(target - previous_target) > 0
            and start_index + 1 < len(headway_types)
        ):
            headway_types[start_index + 1] = HeadwayType.TRANSITION
        previous_target = target
    return tuple(regimes), tuple(headway_types)


def _direction_plans(
    source: list[Trip], direction: Direction, demand: list[DemandRecord], config: ScenarioCConfig
) -> list[_DirectionPlan]:
    source_times = [trip.departure_seconds for trip in source]
    if len(source_times) < 2:
        return []
    targets = _continuous_demand_targets(source_times, direction, demand)
    boundaries_ranked = _material_boundaries(targets, config)
    ranked_by_materiality = [
        index for index, _ in sorted(boundaries_ranked, key=lambda item: (-item[1], item[0]))
    ]
    boundary_sets = [[]]
    for count in range(1, len(ranked_by_materiality) + 1):
        boundary_sets.append(sorted(ranked_by_materiality[:count]))

    plans: list[_DirectionPlan] = []
    seen: set[tuple[int, ...]] = set()
    for boundary_indices in boundary_sets:
        anchors = [0, *boundary_indices, len(source_times) - 1]
        for alpha in (0.25, 0.50, 0.75, 1.0):
            anchor_times = [source_times[0]]
            for index in boundary_indices:
                blended = source_times[index] + alpha * (targets[index] - source_times[index])
                anchor_times.append(round(blended / 60) * 60)
            anchor_times.append(source_times[-1])
            if any(
                right <= left for left, right in zip(anchor_times, anchor_times[1:], strict=False)
            ):
                continue
            generated: list[int] = []
            feasible = True
            for segment_index, (left_index, right_index) in enumerate(
                zip(anchors, anchors[1:], strict=False)
            ):
                try:
                    segment = _balanced_times(
                        anchor_times[segment_index],
                        anchor_times[segment_index + 1],
                        right_index - left_index + 1,
                    )
                except ValueError:
                    feasible = False
                    break
                generated.extend(segment if segment_index == 0 else segment[1:])
            if not feasible or len(generated) != len(source_times):
                continue
            signature = tuple(generated)
            if signature in seen:
                continue
            seen.add(signature)
            shifts = [
                abs(current - baseline) / 60
                for current, baseline in zip(generated, source_times, strict=True)
            ]
            maximum_shift = max(shifts, default=0.0)
            if maximum_shift > config.absolute_max_shift_per_trip_minutes:
                continue
            drafts, types = _regime_drafts(generated, boundary_indices)
            if len(drafts) > config.maximum_headway_regimes_per_direction:
                continue
            if any(
                index not in {0, len(drafts) - 1}
                and draft.end_index - draft.start_index + 1
                < config.minimum_departures_per_normal_regime
                and (generated[draft.end_index] - generated[draft.start_index]) / 60
                < config.minimum_regime_duration_minutes
                for index, draft in enumerate(drafts)
            ):
                continue
            if any(
                draft.actual_headways
                and max(draft.actual_headways) - min(draft.actual_headways)
                > config.headway_rounding_tolerance_minutes
                for draft in drafts
            ):
                continue
            plans.append(
                _DirectionPlan(
                    direction=direction,
                    times=signature,
                    regimes=drafts,
                    headway_types=types,
                    distance_to_demand_minutes=sum(
                        abs(current - target) / 60
                        for current, target in zip(generated, targets, strict=True)
                    ),
                    shifted_trip_count=sum(shift > 0 for shift in shifts),
                    total_shift_minutes=sum(shifts),
                    maximum_shift_minutes=maximum_shift,
                )
            )
    return sorted(
        plans,
        key=lambda plan: (
            plan.distance_to_demand_minutes,
            len(plan.regimes),
            plan.shifted_trip_count,
            plan.total_shift_minutes,
            plan.times,
        ),
    )[:18]


def _build_candidate_trips(
    source_by_direction: dict[Direction, list[Trip]],
    plans: dict[Direction, _DirectionPlan],
    parameters: ScenarioParameters,
) -> list[Trip]:
    generated: list[Trip] = []
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        for source, departure in zip(
            source_by_direction[direction], plans[direction].times, strict=True
        ):
            generated.append(
                Trip(
                    scenario="C",
                    trip_id="",
                    departure_terminal=source.departure_terminal,
                    direction=direction,
                    departure_seconds=departure,
                    arrival_seconds=(
                        departure
                        + source.resolved_arrival_seconds(parameters.default_trip_runtime_minutes)
                        - source.departure_seconds
                    ),
                    vehicle_capacity_override=source.vehicle_capacity_override,
                    source_b_trip_id=source.trip_id,
                    source_b_departure_seconds=source.departure_seconds,
                )
            )
    ordered = sorted(generated, key=lambda trip: (trip.departure_seconds, trip.direction.value))
    return [replace(trip, trip_id=f"C-{index:04d}") for index, trip in enumerate(ordered, 1)]


def _build_fallback_trips(
    source_by_direction: dict[Direction, list[Trip]],
) -> list[Trip]:
    """Clone B exactly for a diagnostic C fallback without normalizing its arrivals."""
    generated: list[Trip] = []
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        for source in source_by_direction[direction]:
            generated.append(
                replace(
                    source,
                    scenario="C",
                    trip_id="",
                    vehicle_id=None,
                    source_b_trip_id=source.trip_id,
                    source_b_departure_seconds=source.departure_seconds,
                )
            )
    ordered = sorted(generated, key=lambda trip: (trip.departure_seconds, trip.direction.value))
    return [replace(trip, trip_id=f"C-{index:04d}") for index, trip in enumerate(ordered, 1)]


def _headway_stats(gaps: list[float]) -> tuple[float | None, float | None]:
    if not gaps:
        return None, None
    average = mean(gaps)
    deviation = pstdev(gaps)
    return deviation, deviation / average if average else 0.0


def _build_regimes(
    trips: list[Trip],
    source_by_direction: dict[Direction, list[Trip]],
    plans: dict[Direction, _DirectionPlan],
    config: ScenarioCConfig,
) -> tuple[list[HeadwayRegime], dict[str, str], dict[str, HeadwayType]]:
    by_source = {trip.source_b_trip_id: trip for trip in trips}
    regimes: list[HeadwayRegime] = []
    regime_by_source: dict[str, str] = {}
    type_by_source: dict[str, HeadwayType] = {}
    for direction_index, direction in enumerate(
        (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1), 1
    ):
        source = source_by_direction[direction]
        plan = plans[direction]
        for index, source_trip in enumerate(source):
            type_by_source[source_trip.trip_id] = plan.headway_types[index]
        for regime_index, draft in enumerate(plan.regimes, 1):
            regime_id = f"C-D{direction_index}-R{regime_index:02d}"
            first_source = source[draft.start_index].trip_id
            last_source = source[draft.end_index].trip_id
            for source_index in range(draft.start_index, draft.end_index + 1):
                regime_by_source.setdefault(source[source_index].trip_id, regime_id)
            gaps = list(draft.actual_headways)
            deviation, coefficient = _headway_stats(gaps)
            headway_range = max(gaps) - min(gaps) if gaps else 0
            regimes.append(
                HeadwayRegime(
                    regime_id=regime_id,
                    direction=direction,
                    start_seconds=by_source[first_source].departure_seconds,
                    end_seconds=by_source[last_source].departure_seconds,
                    first_trip_id=by_source[first_source].trip_id,
                    last_trip_id=by_source[last_source].trip_id,
                    trip_count=draft.end_index - draft.start_index + 1,
                    target_headway_minutes=draft.target_headway_minutes,
                    actual_headway_sequence=tuple(gaps),
                    headway_status=(
                        "ĐẠT"
                        if headway_range <= config.headway_rounding_tolerance_minutes
                        else "KHÔNG ĐẠT"
                    ),
                    boundary_reason=draft.boundary_reason,
                    minimum_headway_minutes=min(gaps) if gaps else None,
                    maximum_headway_minutes=max(gaps) if gaps else None,
                    mean_headway_minutes=mean(gaps) if gaps else None,
                    standard_deviation_minutes=deviation,
                    coefficient_of_variation=coefficient,
                )
            )
    return regimes, regime_by_source, type_by_source


def _demand_interval_label(
    departure_seconds: int, direction: Direction, demand: list[DemandRecord]
) -> str:
    record = next(
        (
            item
            for item in demand
            if item.direction in {direction, Direction.COMBINED}
            and item.block_start_seconds <= departure_seconds < item.block_end_seconds
        ),
        None,
    )
    return (
        block_label(record.block_start_seconds, record.block_end_seconds)
        if record is not None
        else "Ngoài khung nhu cầu"
    )


def _build_traces(
    trips: list[Trip],
    source_by_direction: dict[Direction, list[Trip]],
    demand: list[DemandRecord],
    regime_by_source: dict[str, str],
    type_by_source: dict[str, HeadwayType],
) -> list[TripTrace]:
    c_by_source = {trip.source_b_trip_id: trip for trip in trips}
    traces: list[TripTrace] = []
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        source = source_by_direction[direction]
        current = [c_by_source[trip.trip_id] for trip in source]
        for index, (trip_b, trip_c) in enumerate(zip(source, current, strict=True)):
            original_previous = (
                None
                if index == 0
                else (trip_b.departure_seconds - source[index - 1].departure_seconds) / 60
            )
            new_previous = (
                None
                if index == 0
                else (trip_c.departure_seconds - current[index - 1].departure_seconds) / 60
            )
            original_next = (
                None
                if index == len(source) - 1
                else (source[index + 1].departure_seconds - trip_b.departure_seconds) / 60
            )
            new_next = (
                None
                if index == len(current) - 1
                else (current[index + 1].departure_seconds - trip_c.departure_seconds) / 60
            )
            shift = (trip_c.departure_seconds - trip_b.departure_seconds) / 60
            if shift == 0:
                change_reason = (
                    "FINAL_SERVICE_PRESERVED"
                    if index == len(source) - 1
                    else "RETAINED_STABLE_B_SPAN"
                )
            else:
                change_reason = "LOCAL_SEQUENCE_RESPACED"
            headway_type = type_by_source.get(trip_b.trip_id, HeadwayType.REGULAR)
            traces.append(
                TripTrace(
                    c_trip_id=trip_c.trip_id,
                    source_b_trip_id=trip_b.trip_id,
                    direction=direction,
                    departure_terminal=trip_c.departure_terminal,
                    b_departure_seconds=trip_b.departure_seconds,
                    c_departure_seconds=trip_c.departure_seconds,
                    shift_minutes=shift,
                    retained_or_shifted="GIỮ NGUYÊN" if shift == 0 else "DỊCH CHUYỂN",
                    original_previous_headway=original_previous,
                    new_previous_headway=new_previous,
                    original_next_headway=original_next,
                    new_next_headway=new_next,
                    original_demand_interval=_demand_interval_label(
                        trip_b.departure_seconds, direction, demand
                    ),
                    new_demand_interval=_demand_interval_label(
                        trip_c.departure_seconds, direction, demand
                    ),
                    headway_regime_id=regime_by_source.get(trip_b.trip_id, ""),
                    headway_type=headway_type,
                    change_reason=change_reason,
                    exception_reason=(
                        "BASELINE_UNCHANGED_NO_BETTER_PLAN"
                        if headway_type == HeadwayType.EXCEPTIONAL
                        else ""
                    ),
                )
            )
    return sorted(traces, key=lambda item: (item.c_departure_seconds, item.c_trip_id))


def _regularity_metrics(
    trips: list[Trip],
    regimes: list[HeadwayRegime],
    traces: list[TripTrace],
    config: ScenarioCConfig,
) -> RegularityMetrics:
    gaps: list[float] = []
    consecutive_changes: list[float] = []
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        times = [trip.departure_seconds for trip in _ordered_direction_trips(trips, direction)]
        direction_gaps = [
            (right - left) / 60 for left, right in zip(times, times[1:], strict=False)
        ]
        gaps.extend(direction_gaps)
        consecutive_changes.extend(
            abs(right - left)
            for left, right in zip(direction_gaps, direction_gaps[1:], strict=False)
        )
    counts = Counter(
        trace.headway_type for trace in traces if trace.new_previous_headway is not None
    )
    gate_failures: list[str] = []
    if any(regime.headway_status != "ĐẠT" for regime in regimes):
        gate_failures.append("NORMAL_REGIME_RANGE")
    if counts[HeadwayType.EXCEPTIONAL]:
        gate_failures.append("UNEXPLAINED_EXCEPTIONAL_HEADWAY")
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        regime_count = sum(regime.direction == direction for regime in regimes)
        if regime_count > config.maximum_headway_regimes_per_direction:
            gate_failures.append(f"MAX_REGIMES_{direction.value}")
        transition_count = sum(
            trace.direction == direction and trace.headway_type == HeadwayType.TRANSITION
            for trace in traces
        )
        if (
            transition_count
            > max(0, regime_count - 1) * config.maximum_transition_headways_per_boundary
        ):
            gate_failures.append(f"MAX_TRANSITIONS_{direction.value}")
    deviation, coefficient = _headway_stats(gaps)
    material_changes = sum(
        abs(current.target_headway_minutes - previous.target_headway_minutes)
        >= config.minimum_material_headway_change_minutes
        for previous, current in zip(regimes, regimes[1:], strict=False)
        if previous.direction == current.direction
    )
    return RegularityMetrics(
        number_of_headway_regimes=len(regimes),
        number_of_material_frequency_changes=material_changes,
        number_of_regular_headways=counts[HeadwayType.REGULAR],
        number_of_balanced_rounding_headways=counts[HeadwayType.BALANCED_ROUNDING],
        number_of_transition_headways=counts[HeadwayType.TRANSITION],
        number_of_exceptional_headways=counts[HeadwayType.EXCEPTIONAL],
        maximum_consecutive_headway_difference=max(consecutive_changes, default=0.0),
        sum_absolute_consecutive_headway_changes=sum(consecutive_changes),
        headway_standard_deviation=deviation,
        headway_coefficient_of_variation=coefficient,
        maximum_service_gap=max(gaps) if gaps else None,
        gate_passed=not gate_failures,
        gate_failures=tuple(gate_failures),
    )


def _objective(
    evaluation,
    validation,
    regularity: RegularityMetrics,
    traces: list[TripTrace],
) -> tuple[float, ...]:
    hard_failures = sum(not validation.passed for _ in [0])
    no_service = sum(block.demand > 0 and block.trips == 0 for block in evaluation.blocks)
    overload_passengers = sum(
        max(0.0, block.demand - block.maximum_recommended_capacity) for block in evaluation.blocks
    )
    max_load = evaluation.maximum_load_factor
    maximum_load = 999.0 if max_load is None and no_service else (max_load or 0.0)
    shifted = [trace for trace in traces if trace.shift_minutes != 0]
    return (
        float(hard_failures),
        float(no_service),
        float(evaluation.blocks_over_maximum),
        round(overload_passengers, 6),
        round(maximum_load, 9),
        float(evaluation.blocks_over_target),
        round(regularity.maximum_service_gap or 0.0, 6),
        float(regularity.number_of_exceptional_headways),
        float(len(regularity.gate_failures)),
        float(regularity.number_of_headway_regimes),
        float(regularity.number_of_transition_headways),
        round(regularity.sum_absolute_consecutive_headway_changes, 6),
        float(len(shifted)),
        round(sum(abs(trace.shift_minutes) for trace in shifted), 6),
        round(max((abs(trace.shift_minutes) for trace in shifted), default=0.0), 6),
    )


def _observed_plan(
    direction: Direction, times: list[int], config: ScenarioCConfig
) -> _DirectionPlan:
    gaps = [(right - left) / 60 for left, right in zip(times, times[1:], strict=False)]
    segments: list[tuple[int, int]] = []
    start_index = 0
    current_gaps: list[float] = []
    for gap_index, gap in enumerate(gaps):
        proposed = [*current_gaps, gap]
        if (
            current_gaps
            and max(proposed) - min(proposed) > config.headway_rounding_tolerance_minutes
        ):
            segments.append((start_index, gap_index))
            start_index = gap_index
            current_gaps = [gap]
        else:
            current_gaps = proposed
    segments.append((start_index, len(times) - 1))

    drafts: list[_RegimeDraft] = []
    headway_types = [HeadwayType.REGULAR] * len(times)
    for segment_index, (start, end) in enumerate(segments):
        actual = tuple(gaps[start:end])
        if segment_index == 0:
            reason = RegimeBoundaryReason.FIRST_SERVICE_CONSTRAINT
        elif segment_index == len(segments) - 1:
            reason = RegimeBoundaryReason.FINAL_SERVICE_CONSTRAINT
        else:
            reason = RegimeBoundaryReason.MATERIAL_FREQUENCY_CHANGE
        target = mean(actual) if actual else 0.0
        drafts.append(_RegimeDraft(start, end, target, actual, reason))
        normal_size = (
            end - start + 1 >= config.minimum_departures_per_normal_regime
            or (times[end] - times[start]) / 60 >= config.minimum_regime_duration_minutes
        )
        headway_type = (
            HeadwayType.REGULAR
            if normal_size or segment_index in {0, len(segments) - 1}
            else HeadwayType.EXCEPTIONAL
        )
        for trip_index in range(start + 1, end + 1):
            headway_types[trip_index] = headway_type
    return _DirectionPlan(
        direction,
        tuple(times),
        tuple(drafts),
        tuple(headway_types),
        0.0,
        0,
        0.0,
        0.0,
    )


def _fallback_plans(
    source_by_direction: dict[Direction, list[Trip]], config: ScenarioCConfig
) -> dict[Direction, _DirectionPlan]:
    return {
        direction: _observed_plan(
            direction,
            [trip.departure_seconds for trip in source],
            config,
        )
        for direction, source in source_by_direction.items()
    }


def _generation_timestamp(demand: list[DemandRecord]) -> str:
    if not demand:
        return "N/A"
    return f"{max(record.period_end for record in demand).isoformat()}T00:00:00"


def analyze_baseline_regularity(
    trips: list[Trip], parameters: ScenarioParameters, config: ScenarioCConfig
) -> RegularityMetrics:
    source_by_direction = {
        direction: _ordered_direction_trips(trips, direction)
        for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    }
    plans = _fallback_plans(source_by_direction, config)
    cloned = _build_candidate_trips(source_by_direction, plans, parameters)
    regimes, regime_map, type_map = _build_regimes(cloned, source_by_direction, plans, config)
    traces = _build_traces(cloned, source_by_direction, [], regime_map, type_map)
    return _regularity_metrics(cloned, regimes, traces, config)


def generate_scenario_c(
    parameters: ScenarioParameters,
    trips_b: list[Trip],
    demand: list[DemandRecord],
    active_vehicle_count: int,
    config: ScenarioCConfig,
) -> GeneratedScenario:
    baseline_hash = timetable_fingerprint(trips_b)
    baseline_copy = [replace(trip) for trip in trips_b]
    if baseline_copy is trips_b or any(
        copied is original for copied, original in zip(baseline_copy, trips_b, strict=True)
    ):
        raise AssertionError("Không tạo được bản sao độc lập của Scenario B")
    if len(trips_b) != parameters.total_daily_trips:
        raise ValueError("Tổng chuyến thực tế của B không khớp tổng chuyến khai báo")
    if len({trip.trip_id for trip in trips_b}) != len(trips_b):
        raise ValueError("Scenario B có trip_id trùng nên không thể truy vết một-một")

    directions = (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    source_by_direction = {
        direction: _ordered_direction_trips(baseline_copy, direction) for direction in directions
    }
    if any(len(source_by_direction[direction]) < 2 for direction in directions):
        raise ValueError("Mỗi chiều cần tối thiểu hai chuyến để khóa chuyến đầu và chuyến cuối")
    if active_vehicle_count <= 0:
        raise ValueError("Không xác định được số xe hoạt động của Scenario B")

    baseline_parameters = replace(parameters)
    baseline_validation = validate_schedule(trips_b, parameters)
    baseline_evaluation = evaluate_scenario("B", trips_b, demand, parameters, baseline_validation)
    fallback_plans = _fallback_plans(source_by_direction, config)
    fallback_trips = _build_fallback_trips(source_by_direction)
    fallback_regimes, fallback_regime_map, fallback_type_map = _build_regimes(
        fallback_trips, source_by_direction, fallback_plans, config
    )
    fallback_traces = _build_traces(
        fallback_trips,
        source_by_direction,
        demand,
        fallback_regime_map,
        fallback_type_map,
    )
    fallback_regularity = _regularity_metrics(
        fallback_trips, fallback_regimes, fallback_traces, config
    )
    baseline_objective = _objective(
        baseline_evaluation, baseline_validation, fallback_regularity, fallback_traces
    )

    if not demand:
        status = ScenarioCStatus.INSUFFICIENT_DATA
        reason = "Không có dữ liệu nhu cầu để xác định tái phân bổ ổn định tốt hơn B."
        return _fallback_result(
            baseline_parameters,
            fallback_trips,
            fallback_regimes,
            fallback_traces,
            fallback_regularity,
            active_vehicle_count,
            baseline_hash,
            baseline_objective,
            status,
            reason,
            config,
            demand,
            Counter(),
        )

    plans_by_direction = {
        direction: _direction_plans(source_by_direction[direction], direction, demand, config)
        for direction in directions
    }
    rejection_counts: Counter[str] = Counter()
    candidate_count = 0
    accepted: list[_Candidate] = []
    for first_plan, second_plan in itertools.product(
        plans_by_direction[directions[0]], plans_by_direction[directions[1]]
    ):
        candidate_count += 1
        plans = {directions[0]: first_plan, directions[1]: second_plan}
        candidate_trips = _build_candidate_trips(source_by_direction, plans, parameters)
        if all(
            trip.departure_seconds == trip.source_b_departure_seconds for trip in candidate_trips
        ):
            rejection_counts["UNCHANGED_FROM_B"] += 1
            continue
        if len(candidate_trips) != len(trips_b):
            rejection_counts["TRIP_COUNT_LOCK"] += 1
            continue
        if any(
            sum(trip.direction == direction for trip in candidate_trips)
            != len(source_by_direction[direction])
            for direction in directions
        ):
            rejection_counts["DIRECTION_TRIP_LOCK"] += 1
            continue
        validation = validate_schedule(candidate_trips, parameters)
        if not validation.passed:
            rejection_counts["AUTHORITATIVE_VALIDATOR"] += 1
            continue
        fleet = assign_fleet(candidate_trips, parameters)
        if fleet.minimum_vehicles > active_vehicle_count:
            rejection_counts["FLEET_LIMIT"] += 1
            continue
        regimes, regime_map, type_map = _build_regimes(
            candidate_trips, source_by_direction, plans, config
        )
        traces = _build_traces(candidate_trips, source_by_direction, demand, regime_map, type_map)
        regularity = _regularity_metrics(candidate_trips, regimes, traces, config)
        if not regularity.gate_passed:
            rejection_counts["REGULARITY_GATE"] += 1
            continue
        evaluation = evaluate_scenario("C", candidate_trips, demand, parameters, validation)
        objective = _objective(evaluation, validation, regularity, traces)
        if objective >= baseline_objective:
            rejection_counts["NOT_BETTER_THAN_B"] += 1
            continue
        shifted = [trace for trace in traces if trace.shift_minutes != 0]
        reason = (
            "C tái phân bổ từ B theo các vùng có mốc neo và tái giãn cách đồng bộ; "
            f"{len(shifted)}/{len(traces)} chuyến dịch chuyển, "
            f"tổng dịch chuyển {sum(abs(item.shift_minutes) for item in shifted):.0f} phút; "
            f"{len(regimes)} chế độ giãn cách, không vượt {active_vehicle_count} xe hoạt động."
        )
        accepted.append(
            _Candidate(
                candidate_trips,
                regimes,
                traces,
                regularity,
                objective,
                reason,
                fleet.minimum_vehicles,
                evaluation,
            )
        )

    if timetable_fingerprint(trips_b) != baseline_hash:
        raise AssertionError("Scenario B đã bị thay đổi trong quá trình sinh Scenario C")

    if not accepted:
        status = ScenarioCStatus.NO_BETTER_REDISTRIBUTION
        if candidate_count and rejection_counts["FLEET_LIMIT"] == candidate_count:
            status = ScenarioCStatus.INFEASIBLE_FIXED_RESOURCES
        reason = (
            "Không tìm thấy phương án tái phân bổ vừa tốt hơn B, vừa đạt kiểm tra giãn cách "
            "và không vượt số xe hiện có; C được giữ bằng B và không được gắn nhãn khuyến nghị."
        )
        return _fallback_result(
            baseline_parameters,
            fallback_trips,
            fallback_regimes,
            fallback_traces,
            fallback_regularity,
            active_vehicle_count,
            baseline_hash,
            baseline_objective,
            status,
            reason,
            config,
            demand,
            rejection_counts,
            candidate_count,
        )

    selected = min(accepted, key=lambda item: (item.objective, timetable_fingerprint(item.trips)))
    if (
        selected.evaluation.blocks_over_target == 0
        and selected.evaluation.blocks_over_maximum == 0
        and not any(block.demand > 0 and block.trips == 0 for block in selected.evaluation.blocks)
    ):
        status = ScenarioCStatus.SUITABLE_REGULAR
    else:
        status = ScenarioCStatus.REGULAR_STILL_UNDERSUPPLIED
    log = OptimizationLog(
        candidate_count=candidate_count,
        accepted_candidates=len(accepted),
        rejected_candidates=candidate_count - len(accepted),
        rejection_reason_counts=tuple(sorted(rejection_counts.items())),
        objective_before=baseline_objective,
        objective_after=selected.objective,
        regularity_gate_result="ĐẠT" if selected.regularity.gate_passed else "KHÔNG ĐẠT",
        generation_status=status,
        configuration_version=config.configuration_version,
        generation_timestamp=_generation_timestamp(demand),
    )
    return GeneratedScenario(
        name="C",
        parameters=baseline_parameters,
        trips=selected.trips,
        reason=selected.reason,
        strategy_id=FIXED_RESOURCE_STRATEGY_ID,
        resource_fleet_limit=active_vehicle_count,
        display_name=SCENARIO_C_DISPLAY_NAME,
        active_vehicle_count=active_vehicle_count,
        generation_status=status,
        headway_regimes=selected.regimes,
        trip_traces=selected.traces,
        regularity=selected.regularity,
        optimization_log=log,
        timetable_fingerprint=timetable_fingerprint(selected.trips),
        source_timetable_fingerprint=baseline_hash,
        generation_config=asdict(config),
    )


def _fallback_result(
    parameters: ScenarioParameters,
    trips: list[Trip],
    regimes: list[HeadwayRegime],
    traces: list[TripTrace],
    regularity: RegularityMetrics,
    active_vehicle_count: int,
    baseline_hash: str,
    baseline_objective: tuple[float, ...],
    status: ScenarioCStatus,
    reason: str,
    config: ScenarioCConfig,
    demand: list[DemandRecord],
    rejection_counts: Counter[str],
    candidate_count: int = 0,
) -> GeneratedScenario:
    log = OptimizationLog(
        candidate_count=candidate_count,
        accepted_candidates=0,
        rejected_candidates=candidate_count,
        rejection_reason_counts=tuple(sorted(rejection_counts.items())),
        objective_before=baseline_objective,
        objective_after=baseline_objective,
        regularity_gate_result="ĐẠT" if regularity.gate_passed else "KHÔNG ĐẠT",
        generation_status=status,
        configuration_version=config.configuration_version,
        generation_timestamp=_generation_timestamp(demand),
    )
    return GeneratedScenario(
        name="C",
        parameters=parameters,
        trips=trips,
        reason=reason,
        strategy_id=FIXED_RESOURCE_STRATEGY_ID,
        resource_fleet_limit=active_vehicle_count,
        display_name=SCENARIO_C_DISPLAY_NAME,
        active_vehicle_count=active_vehicle_count,
        generation_status=status,
        headway_regimes=regimes,
        trip_traces=traces,
        regularity=regularity,
        optimization_log=log,
        timetable_fingerprint=timetable_fingerprint(trips),
        source_timetable_fingerprint=baseline_hash,
        generation_config=asdict(config),
    )
