from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from .demand import classify_load_factor, required_trips
from .models import (
    AnalysisBundle,
    BlockEvaluation,
    Direction,
    EvaluationStatus,
    ScenarioResult,
)

DAY_SECONDS = 24 * 60 * 60


class SupplyPresentationStatus(StrEnum):
    TARGET_MET = "Đạt mục tiêu LF ≤ 85%"
    WARNING = "Đáp ứng nhưng LF trên 85%"
    CRITICAL = "Thiếu chuyến — LF vượt 90%"
    NO_SERVICE_WITH_DEMAND = "Có nhu cầu nhưng không có chuyến"
    INSUFFICIENT_DATA = "Không đủ dữ liệu"


@dataclass(frozen=True)
class BlockSupplyComparison:
    block_start_seconds: int
    block_end_seconds: int
    direction: Direction
    passenger_demand: float
    vehicle_capacity: int
    b_trip_count: int
    c_trip_count: int
    required_trips_85: int
    minimum_trips_90: int
    b_nominal_capacity: float
    c_nominal_capacity: float
    b_target_capacity: float
    c_target_capacity: float
    b_load_factor: float | None
    c_load_factor: float | None
    b_trip_gap_to_85: int
    c_trip_gap_to_85: int
    b_status: SupplyPresentationStatus
    c_status: SupplyPresentationStatus
    demand_confidence: str

    @property
    def key(self) -> tuple[int, int, Direction]:
        return self.block_start_seconds, self.block_end_seconds, self.direction


def _departure_count(result: ScenarioResult, block: BlockEvaluation) -> int:
    return sum(
        block.block_start_seconds <= trip.departure_seconds < block.block_end_seconds
        and (block.direction == Direction.COMBINED or trip.direction == block.direction)
        for trip in result.trips
    )


def _status_from_evaluation_status(
    status: EvaluationStatus,
) -> SupplyPresentationStatus:
    mapping = {
        EvaluationStatus.SUITABLE: SupplyPresentationStatus.TARGET_MET,
        EvaluationStatus.MONITOR: SupplyPresentationStatus.WARNING,
        EvaluationStatus.UNSUITABLE: SupplyPresentationStatus.CRITICAL,
        EvaluationStatus.NO_SERVICE_WITH_DEMAND: SupplyPresentationStatus.NO_SERVICE_WITH_DEMAND,
        EvaluationStatus.INSUFFICIENT_DATA: SupplyPresentationStatus.INSUFFICIENT_DATA,
    }
    return mapping[status]


def _status_from_evaluation(block: BlockEvaluation) -> SupplyPresentationStatus:
    return _status_from_evaluation_status(block.status)


def _status_from_counts(
    demand: float,
    actual_trips: int,
    required_trips_85: int,
    minimum_trips_90: int,
) -> SupplyPresentationStatus:
    if demand > 0 and actual_trips == 0:
        return SupplyPresentationStatus.NO_SERVICE_WITH_DEMAND
    if actual_trips >= required_trips_85:
        return SupplyPresentationStatus.TARGET_MET
    if actual_trips >= minimum_trips_90:
        return SupplyPresentationStatus.WARNING
    if demand <= 0:
        return SupplyPresentationStatus.TARGET_MET
    return SupplyPresentationStatus.CRITICAL


def _demand_confidence(block: BlockEvaluation) -> str:
    if block.data_note:
        return block.data_note
    if block.direction == Direction.COMBINED:
        return "Nhu cầu tổng hợp hai chiều — ước tính"
    return "Dữ liệu nhu cầu đã tách chiều"


def _contains_departure(block: BlockEvaluation, departure_seconds: int) -> bool:
    start = block.block_start_seconds
    end = block.block_end_seconds
    departure = departure_seconds
    while end <= start:
        end += DAY_SECONDS
    while departure < start:
        departure += DAY_SECONDS
    return start <= departure < end


def _needs_canonical_grid(
    result_b: ScenarioResult,
    result_c: ScenarioResult,
    result_a: ScenarioResult | None = None,
) -> bool:
    blocks = result_b.evaluation.blocks
    if not blocks:
        return False
    block_seconds = result_b.parameters.time_block_minutes * 60
    if any(
        (block.block_end_seconds - block.block_start_seconds) % DAY_SECONDS != block_seconds
        for block in blocks
    ):
        return True
    if len({block.block_start_seconds % block_seconds for block in blocks}) > 1:
        return True
    results = [result_b, result_c]
    if result_a is not None and result_a.trips:
        results.append(result_a)
    for result in results:
        for trip in result.trips:
            matching_blocks = sum(
                _contains_departure(block, trip.departure_seconds)
                and (block.direction == Direction.COMBINED or block.direction == trip.direction)
                for block in blocks
            )
            if matching_blocks != 1:
                return True
    return False


def _clock_origin(
    blocks: list[BlockEvaluation],
    departure_seconds: list[int] | None = None,
) -> int:
    points = sorted(
        {block.block_start_seconds % DAY_SECONDS for block in blocks}
        | {value % DAY_SECONDS for value in (departure_seconds or [])}
    )
    if len(points) <= 1:
        return points[0] if points else 0
    gaps = [
        ((points[(index + 1) % len(points)] - point) % DAY_SECONDS, index)
        for index, point in enumerate(points)
    ]
    _, gap_index = max(gaps)
    return points[(gap_index + 1) % len(points)]


def _project_seconds(seconds: int, origin: int) -> int:
    origin_clock = origin % DAY_SECONDS
    day_base = origin - origin_clock
    projected = seconds % DAY_SECONDS
    if projected < origin_clock:
        projected += DAY_SECONDS
    return day_base + projected


def _project_block(block: BlockEvaluation, origin: int) -> tuple[int, int]:
    start = _project_seconds(block.block_start_seconds, origin)
    duration = block.block_end_seconds - block.block_start_seconds
    while duration <= 0:
        duration += DAY_SECONDS
    return start, start + duration


def _trips_in_canonical_block(
    result: ScenarioResult,
    direction: Direction,
    start: int,
    end: int,
    origin: int,
):
    return [
        trip
        for trip in result.trips
        if start <= _project_seconds(trip.departure_seconds, origin) < end
        and (direction == Direction.COMBINED or trip.direction == direction)
    ]


def _canonical_supply_rows(
    result_b: ScenarioResult,
    result_c: ScenarioResult,
    result_a: ScenarioResult | None = None,
) -> list[BlockSupplyComparison]:
    source_blocks = result_b.evaluation.blocks
    block_seconds = result_b.parameters.time_block_minutes * 60
    span_results = [result_b, result_c]
    if result_a is not None and result_a.trips:
        span_results.append(result_a)
    departures = [
        trip.departure_seconds
        for result in span_results
        for trip in result.trips
    ]
    preliminary_origin = _clock_origin(source_blocks, departures)
    preliminary_points = [
        _project_block(block, preliminary_origin)[0] for block in source_blocks
    ] + [
        _project_seconds(trip.departure_seconds, preliminary_origin)
        for result in span_results
        for trip in result.trips
    ]
    grid_start = math.floor(min(preliminary_points) / block_seconds) * block_seconds
    origin = grid_start
    projected_blocks = [
        (block, *_project_block(block, origin)) for block in source_blocks
    ]
    projected_trips = [
        _project_seconds(trip.departure_seconds, origin)
        for result in span_results
        for trip in result.trips
    ]
    grid_end = math.ceil(
        max(
            [end for _, _, end in projected_blocks]
            + [departure + 1 for departure in projected_trips]
        )
        / block_seconds
    ) * block_seconds
    if grid_end <= grid_start:
        grid_end = grid_start + block_seconds

    directions = sorted({block.direction for block in source_blocks}, key=lambda item: item.value)
    capacity = result_b.parameters.capacity
    rows: list[BlockSupplyComparison] = []
    for direction in directions:
        directional_blocks = [
            (block, start, end)
            for block, start, end in projected_blocks
            if block.direction == direction
        ]
        for start in range(grid_start, grid_end, block_seconds):
            end = start + block_seconds
            demand = sum(
                block.demand * max(0, min(end, block_end) - max(start, block_start))
                / max(1, block_end - block_start)
                for block, block_start, block_end in directional_blocks
            )

            trips_b = _trips_in_canonical_block(result_b, direction, start, end, origin)
            trips_c = _trips_in_canonical_block(result_c, direction, start, end, origin)
            b_nominal = sum(
                trip.vehicle_capacity_override or result_b.parameters.capacity for trip in trips_b
            )
            c_nominal = sum(
                trip.vehicle_capacity_override or result_c.parameters.capacity for trip in trips_c
            )
            b_load = demand / b_nominal if b_nominal else None
            c_load = demand / c_nominal if c_nominal else None
            required_85 = required_trips(
                demand,
                capacity,
                result_b.parameters.target_load_factor,
            )
            minimum_90 = required_trips(
                demand,
                capacity,
                result_b.parameters.maximum_load_factor,
            )
            b_status = classify_load_factor(
                b_load,
                result_b.parameters.target_load_factor,
                result_b.parameters.maximum_load_factor,
                has_demand=demand > 0,
                trips=len(trips_b),
            )
            c_status = classify_load_factor(
                c_load,
                result_c.parameters.target_load_factor,
                result_c.parameters.maximum_load_factor,
                has_demand=demand > 0,
                trips=len(trips_c),
            )
            rows.append(
                BlockSupplyComparison(
                    block_start_seconds=start,
                    block_end_seconds=end,
                    direction=direction,
                    passenger_demand=demand,
                    vehicle_capacity=capacity,
                    b_trip_count=len(trips_b),
                    c_trip_count=len(trips_c),
                    required_trips_85=required_85,
                    minimum_trips_90=minimum_90,
                    b_nominal_capacity=b_nominal,
                    c_nominal_capacity=c_nominal,
                    b_target_capacity=b_nominal * result_b.parameters.target_load_factor,
                    c_target_capacity=c_nominal * result_c.parameters.target_load_factor,
                    b_load_factor=b_load,
                    c_load_factor=c_load,
                    b_trip_gap_to_85=len(trips_b) - required_85,
                    c_trip_gap_to_85=len(trips_c) - required_85,
                    b_status=_status_from_evaluation_status(b_status),
                    c_status=_status_from_evaluation_status(c_status),
                    demand_confidence=(
                        "Nhu cầu tổng hợp hai chiều — ước tính"
                        if direction == Direction.COMBINED
                        else (
                            "Dữ liệu nhu cầu đã tách chiều · tái nhóm theo "
                            f"block {result_b.parameters.time_block_minutes} phút"
                        )
                    ),
                )
            )
    return rows


def build_block_supply_comparison(bundle: AnalysisBundle) -> list[BlockSupplyComparison]:
    """Build the B/C presentation dataset from authoritative block evaluations.

    The equality checks deliberately compare evaluated trip counts with the exact
    timetable objects that feed the separate departure-detail diagram.
    """
    result_b = bundle.get("B")
    result_c = bundle.get("C")
    result_a = bundle.get("A")
    if result_b is None or result_c is None:
        return []
    if result_b.parameters.capacity != result_c.parameters.capacity:
        raise ValueError(
            "Không thể dùng một đường yêu cầu chung khi sức chứa xe của B và C khác nhau"
        )

    c_by_key = {
        (block.block_start_seconds, block.block_end_seconds, block.direction): block
        for block in result_c.evaluation.blocks
    }
    if len(c_by_key) != len(result_b.evaluation.blocks):
        raise ValueError("Số block đánh giá của B và C không khớp")
    for block_b in result_b.evaluation.blocks:
        key = (block_b.block_start_seconds, block_b.block_end_seconds, block_b.direction)
        block_c = c_by_key.get(key)
        if block_c is None:
            raise ValueError(f"Scenario C thiếu block đánh giá tương ứng với B: {key}")
        if abs(block_b.demand - block_c.demand) > 1e-9:
            raise ValueError(f"Nhu cầu block B và C không khớp: {key}")
    if _needs_canonical_grid(result_b, result_c, result_a):
        rows = _canonical_supply_rows(result_b, result_c, result_a)
        _assert_supply_reconciliation(rows, result_b, result_c)
        return rows

    rows: list[BlockSupplyComparison] = []
    for block_b in result_b.evaluation.blocks:
        key = (block_b.block_start_seconds, block_b.block_end_seconds, block_b.direction)
        block_c = c_by_key.get(key)
        if block_c is None:
            raise ValueError(f"Scenario C thiếu block đánh giá tương ứng với B: {key}")
        if abs(block_b.demand - block_c.demand) > 1e-9:
            raise ValueError(f"Nhu cầu block B và C không khớp: {key}")

        counted_b = _departure_count(result_b, block_b)
        counted_c = _departure_count(result_c, block_c)
        if counted_b != block_b.trips:
            raise ValueError(
                f"Số chuyến B trong block {key} ({block_b.trips}) không khớp timetable ({counted_b})"
            )
        if counted_c != block_c.trips:
            raise ValueError(
                f"Số chuyến C trong block {key} ({block_c.trips}) không khớp timetable ({counted_c})"
            )

        capacity = result_b.parameters.capacity
        required_85 = block_b.required_trips
        if required_85 != block_c.required_trips:
            raise ValueError(f"Số chuyến cần tại target của B và C không khớp: {key}")
        minimum_90 = required_trips(
            block_b.demand,
            capacity,
            result_b.parameters.maximum_load_factor,
        )
        rows.append(
            BlockSupplyComparison(
                block_start_seconds=block_b.block_start_seconds,
                block_end_seconds=block_b.block_end_seconds,
                direction=block_b.direction,
                passenger_demand=block_b.demand,
                vehicle_capacity=capacity,
                b_trip_count=block_b.trips,
                c_trip_count=block_c.trips,
                required_trips_85=required_85,
                minimum_trips_90=minimum_90,
                b_nominal_capacity=block_b.nominal_capacity,
                c_nominal_capacity=block_c.nominal_capacity,
                b_target_capacity=block_b.target_capacity,
                c_target_capacity=block_c.target_capacity,
                b_load_factor=block_b.load_factor,
                c_load_factor=block_c.load_factor,
                b_trip_gap_to_85=block_b.trip_gap_to_target,
                c_trip_gap_to_85=block_c.trip_gap_to_target,
                b_status=_status_from_evaluation(block_b),
                c_status=_status_from_evaluation(block_c),
                demand_confidence=_demand_confidence(block_b),
            )
        )
    if rows:
        _assert_supply_reconciliation(rows, result_b, result_c)
    return rows


def aggregate_block_supply(
    rows: list[BlockSupplyComparison], direction: Direction
) -> list[BlockSupplyComparison]:
    if direction != Direction.COMBINED:
        return sorted(
            (row for row in rows if row.direction == direction),
            key=lambda row: (row.block_start_seconds, row.block_end_seconds),
        )

    grouped: dict[tuple[int, int], list[BlockSupplyComparison]] = {}
    for row in rows:
        grouped.setdefault((row.block_start_seconds, row.block_end_seconds), []).append(row)

    combined_rows: list[BlockSupplyComparison] = []
    for (start, end), candidates in sorted(grouped.items()):
        authoritative_combined = [row for row in candidates if row.direction == Direction.COMBINED]
        selected = authoritative_combined or candidates
        demand = sum(row.passenger_demand for row in selected)
        b_trips = sum(row.b_trip_count for row in selected)
        c_trips = sum(row.c_trip_count for row in selected)
        required_85 = sum(row.required_trips_85 for row in selected)
        minimum_90 = sum(row.minimum_trips_90 for row in selected)
        b_nominal = sum(row.b_nominal_capacity for row in selected)
        c_nominal = sum(row.c_nominal_capacity for row in selected)
        combined_rows.append(
            BlockSupplyComparison(
                block_start_seconds=start,
                block_end_seconds=end,
                direction=Direction.COMBINED,
                passenger_demand=demand,
                vehicle_capacity=selected[0].vehicle_capacity,
                b_trip_count=b_trips,
                c_trip_count=c_trips,
                required_trips_85=required_85,
                minimum_trips_90=minimum_90,
                b_nominal_capacity=b_nominal,
                c_nominal_capacity=c_nominal,
                b_target_capacity=sum(row.b_target_capacity for row in selected),
                c_target_capacity=sum(row.c_target_capacity for row in selected),
                b_load_factor=demand / b_nominal if b_nominal else None,
                c_load_factor=demand / c_nominal if c_nominal else None,
                b_trip_gap_to_85=b_trips - required_85,
                c_trip_gap_to_85=c_trips - required_85,
                b_status=_status_from_counts(demand, b_trips, required_85, minimum_90),
                c_status=_status_from_counts(demand, c_trips, required_85, minimum_90),
                demand_confidence=(
                    selected[0].demand_confidence
                    if authoritative_combined
                    else "Tổng hợp từ dữ liệu nhu cầu đã tách chiều"
                ),
            )
        )
    return combined_rows


def _assert_supply_reconciliation(
    rows: list[BlockSupplyComparison],
    result_b: ScenarioResult,
    result_c: ScenarioResult,
) -> None:
    combined = aggregate_block_supply(rows, Direction.COMBINED)
    whole_day_checks = (
        ("B", sum(row.b_trip_count for row in combined), len(result_b.trips)),
        ("C", sum(row.c_trip_count for row in combined), len(result_c.trips)),
    )
    for scenario, line_total, timetable_total in whole_day_checks:
        if line_total != timetable_total:
            raise ValueError(
                f"Tổng đường số chuyến {scenario} theo block ({line_total}) "
                f"không khớp timetable ({timetable_total})"
            )

    available_directions = {row.direction for row in rows}
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        if direction not in available_directions:
            continue
        directional = aggregate_block_supply(rows, direction)
        expected_b = sum(trip.direction == direction for trip in result_b.trips)
        expected_c = sum(trip.direction == direction for trip in result_c.trips)
        actual_b = sum(row.b_trip_count for row in directional)
        actual_c = sum(row.c_trip_count for row in directional)
        if actual_b != expected_b or actual_c != expected_c:
            raise ValueError(
                f"Tổng số chuyến theo chiều {direction.value} không khớp timetable: "
                f"B {actual_b}/{expected_b}, C {actual_c}/{expected_c}"
            )


def available_supply_directions(bundle: AnalysisBundle) -> tuple[Direction, ...]:
    rows = build_block_supply_comparison(bundle)
    directions = {row.direction for row in rows}
    available = [Direction.COMBINED]
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        if direction in directions:
            available.append(direction)
    return tuple(available)


def scenario_supply_summary(bundle: AnalysisBundle) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for result in bundle.scenarios:
        statuses = [block.status for block in result.evaluation.blocks]
        rows.append(
            {
                "Phương án": result.display_name or result.name,
                "Tổng chuyến": len(result.trips),
                "Xe hoạt động": result.active_vehicle_count or result.fleet.minimum_vehicles,
                "LF cao nhất": result.evaluation.maximum_load_factor,
                "Block đạt 85%": sum(status == EvaluationStatus.SUITABLE for status in statuses),
                "Block 85–90%": sum(status == EvaluationStatus.MONITOR for status in statuses),
                "Block >90%": sum(
                    status in {EvaluationStatus.UNSUITABLE, EvaluationStatus.NO_SERVICE_WITH_DEMAND}
                    for status in statuses
                ),
            }
        )
    return rows
