from __future__ import annotations

import math
from statistics import mean, pstdev

from .models import (
    BlockEvaluation,
    DemandRecord,
    Direction,
    EvaluationStatus,
    HeadwayStats,
    ScenarioEvaluation,
    ScenarioParameters,
    Trip,
    ValidationReport,
)
from .time_utils import block_label


def required_trips(demand: float, capacity: int, target_load_factor: float) -> int:
    if capacity <= 0 or target_load_factor <= 0:
        raise ValueError("Sức chứa và target load factor phải lớn hơn 0")
    return math.ceil(demand / (capacity * target_load_factor)) if demand > 0 else 0


def classify_load_factor(
    load_factor: float | None,
    target_load_factor: float,
    maximum_load_factor: float,
    *,
    has_demand: bool,
    trips: int,
) -> EvaluationStatus:
    if has_demand and trips == 0:
        return EvaluationStatus.NO_SERVICE_WITH_DEMAND
    if load_factor is None:
        return EvaluationStatus.INSUFFICIENT_DATA
    if load_factor <= target_load_factor:
        return EvaluationStatus.SUITABLE
    if load_factor <= maximum_load_factor:
        return EvaluationStatus.MONITOR
    return EvaluationStatus.UNSUITABLE


def headway_statistics(departure_seconds: list[int]) -> HeadwayStats:
    ordered = sorted(departure_seconds)
    if len(ordered) < 2:
        return HeadwayStats(len(ordered), None, None, None, None, None)
    gaps = [(right - left) / 60 for left, right in zip(ordered, ordered[1:], strict=False)]
    return _headway_statistics_from_gaps(len(ordered), gaps)


def _headway_statistics_from_gaps(departure_count: int, gaps: list[float]) -> HeadwayStats:
    if not gaps:
        return HeadwayStats(departure_count, None, None, None, None, None)
    average = mean(gaps)
    deviation = pstdev(gaps)
    return HeadwayStats(
        departure_count,
        average,
        min(gaps),
        max(gaps),
        deviation,
        deviation / average if average > 0 else 0.0,
    )


def _continuous_block_headway(
    trips: list[Trip], record: DemandRecord, matching_departure_count: int
) -> HeadwayStats:
    """Assign continuous same-direction gaps to the block containing the later trip."""
    directions = (
        (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
        if record.direction == Direction.COMBINED
        else (record.direction,)
    )
    gaps: list[float] = []
    for direction in directions:
        ordered = sorted(trip.departure_seconds for trip in trips if trip.direction == direction)
        gaps.extend(
            (current - previous) / 60
            for previous, current in zip(ordered, ordered[1:], strict=False)
            if record.block_start_seconds <= current < record.block_end_seconds
        )
    return _headway_statistics_from_gaps(matching_departure_count, gaps)


def _aggregate_headway(trips: list[Trip]) -> HeadwayStats:
    gaps: list[float] = []
    departure_count = 0
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        times = sorted(trip.departure_seconds for trip in trips if trip.direction == direction)
        departure_count += len(times)
        gaps.extend((right - left) / 60 for left, right in zip(times, times[1:], strict=False))
    if not gaps:
        return HeadwayStats(departure_count, None, None, None, None, None)
    average = mean(gaps)
    deviation = pstdev(gaps)
    return HeadwayStats(
        departure_count,
        average,
        min(gaps),
        max(gaps),
        deviation,
        deviation / average if average else 0,
    )


def _trip_capacity(trip: Trip, parameters: ScenarioParameters) -> int:
    return trip.vehicle_capacity_override or parameters.capacity


def _block_evaluation(
    scenario: str,
    trips: list[Trip],
    record: DemandRecord,
    parameters: ScenarioParameters,
) -> BlockEvaluation:
    if record.direction == Direction.COMBINED:
        matching = [
            trip
            for trip in trips
            if record.block_start_seconds <= trip.departure_seconds < record.block_end_seconds
        ]
        note = "Sản lượng tổng hai chiều; chỉ kết luận ở cấp tổng hợp, không kết luận riêng chiều."
    else:
        matching = [
            trip
            for trip in trips
            if trip.direction == record.direction
            and record.block_start_seconds <= trip.departure_seconds < record.block_end_seconds
        ]
        note = ""
    demand = record.average_daily_demand
    nominal_capacity = sum(_trip_capacity(trip, parameters) for trip in matching)
    load_factor = demand / nominal_capacity if nominal_capacity > 0 else None
    target_capacity = nominal_capacity * parameters.target_load_factor
    maximum_capacity = nominal_capacity * parameters.maximum_load_factor
    needed = required_trips(demand, parameters.capacity, parameters.target_load_factor)
    status = classify_load_factor(
        load_factor,
        parameters.target_load_factor,
        parameters.maximum_load_factor,
        has_demand=demand > 0,
        trips=len(matching),
    )
    return BlockEvaluation(
        scenario=scenario,
        block_start_seconds=record.block_start_seconds,
        block_end_seconds=record.block_end_seconds,
        direction=record.direction,
        trips=len(matching),
        nominal_capacity=nominal_capacity,
        target_capacity=target_capacity,
        maximum_recommended_capacity=maximum_capacity,
        demand=demand,
        load_factor=load_factor,
        required_trips=needed,
        trip_gap_to_target=len(matching) - needed,
        status=status,
        headway=_continuous_block_headway(trips, record, len(matching)),
        data_note=note,
    )


def evaluate_scenario(
    scenario: str,
    trips: list[Trip],
    demand: list[DemandRecord],
    parameters: ScenarioParameters,
    validation: ValidationReport,
    *,
    final_trip_tolerance_minutes: int = 15,
) -> ScenarioEvaluation:
    blocks = [_block_evaluation(scenario, trips, record, parameters) for record in demand]
    load_factors = [block.load_factor for block in blocks if block.load_factor is not None]
    statuses = {block.status for block in blocks}
    if not demand:
        demand_status = EvaluationStatus.INSUFFICIENT_DATA
    elif (
        EvaluationStatus.NO_SERVICE_WITH_DEMAND in statuses
        or EvaluationStatus.UNSUITABLE in statuses
    ):
        demand_status = EvaluationStatus.UNSUITABLE
    elif EvaluationStatus.MONITOR in statuses:
        demand_status = EvaluationStatus.MONITOR
    else:
        demand_status = EvaluationStatus.SUITABLE
    technical_status = (
        EvaluationStatus.SUITABLE if validation.passed else EvaluationStatus.UNSUITABLE
    )
    if technical_status == EvaluationStatus.UNSUITABLE:
        overall = EvaluationStatus.UNSUITABLE
    elif demand_status == EvaluationStatus.INSUFFICIENT_DATA:
        overall = EvaluationStatus.INSUFFICIENT_DATA
    else:
        overall = demand_status

    by_terminal = {
        terminal: sorted(
            trip.departure_seconds for trip in trips if trip.departure_terminal == terminal
        )
        for terminal in (parameters.terminal_1_name, parameters.terminal_2_name)
    }
    expected = {
        parameters.terminal_1_name: (
            parameters.terminal_1_first_departure,
            parameters.terminal_1_last_departure,
        ),
        parameters.terminal_2_name: (
            parameters.terminal_2_first_departure,
            parameters.terminal_2_last_departure,
        ),
    }
    early_gaps: list[float] = []
    late_gaps: list[float] = []
    warnings: list[str] = []
    for terminal, times in by_terminal.items():
        first, last = expected[terminal]
        if not times:
            early_gaps.append(float("inf"))
            late_gaps.append(float("inf"))
            continue
        early_gaps.append(max(0, times[0] - first) / 60)
        late_gap = max(0, last - times[-1]) / 60
        late_gaps.append(late_gap)
        if late_gap > final_trip_tolerance_minutes:
            warnings.append(f"Chuyến cuối tại {terminal} sớm hơn giờ kết thúc {late_gap:.0f} phút.")
    limitations: list[str] = []
    if any(record.direction == Direction.COMBINED for record in demand):
        limitations.append(
            "Có sản lượng combined: không kết luận quá tải/thiếu chuyến cho một chiều cụ thể."
        )
    if any(block.status == EvaluationStatus.NO_SERVICE_WITH_DEMAND for block in blocks):
        warnings.append("Có block có nhu cầu nhưng không có chuyến phục vụ.")
    return ScenarioEvaluation(
        scenario=scenario,
        blocks=blocks,
        overall_status=overall,
        technical_status=technical_status,
        demand_status=demand_status,
        maximum_load_factor=max(load_factors) if load_factors else None,
        blocks_over_target=sum(
            block.load_factor is not None and block.load_factor > parameters.target_load_factor
            for block in blocks
        ),
        blocks_over_maximum=sum(
            block.load_factor is not None and block.load_factor > parameters.maximum_load_factor
            for block in blocks
        ),
        headway=_aggregate_headway(trips),
        early_coverage_gap_minutes=max(early_gaps, default=0),
        late_coverage_gap_minutes=max(late_gaps, default=0),
        warnings=warnings,
        limitations=limitations,
    )


def blocks_needing_more_trips(blocks: list[BlockEvaluation]) -> list[str]:
    return [
        f"{block_label(block.block_start_seconds, block.block_end_seconds)} / {block.direction.value}"
        for block in blocks
        if block.trip_gap_to_target < 0
    ]
