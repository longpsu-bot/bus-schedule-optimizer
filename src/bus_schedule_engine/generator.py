from __future__ import annotations

import math
from dataclasses import replace

from .c_config import FIXED_RESOURCE_STRATEGY_ID as _FIXED_RESOURCE_STRATEGY_ID
from .c_config import ScenarioCConfig
from .c_generator import generate_scenario_c
from .demand import required_trips
from .fleet import assign_fleet
from .models import (
    DemandRecord,
    Direction,
    GeneratedScenario,
    GenerationReport,
    ScenarioCStatus,
    ScenarioParameters,
    Trip,
)

FIXED_RESOURCE_STRATEGY_ID = _FIXED_RESOURCE_STRATEGY_ID


def even_departure_times(start_seconds: int, end_seconds: int, count: int) -> list[int]:
    """Return deterministic, equally spaced departures on [start, end)."""
    if count < 0 or end_seconds < start_seconds:
        raise ValueError("Block hoặc số chuyến không hợp lệ")
    if count == 0:
        return []
    if end_seconds == start_seconds:
        if count == 1:
            return [start_seconds]
        raise ValueError("Không thể tạo nhiều chuyến khác giờ trong block độ dài 0")
    step = (end_seconds - start_seconds) / count
    return [round(start_seconds + index * step) for index in range(count)]


def _integer_allocation(total: int, weights: list[float], minimums: list[int]) -> list[int]:
    if total < sum(minimums):
        raise ValueError("Tổng chuyến không đủ để giữ chuyến đầu và chuyến cuối")
    remaining = total - sum(minimums)
    normalized = [max(0.0, weight) for weight in weights]
    if sum(normalized) == 0:
        normalized = [1.0] * len(weights)
    raw = [remaining * weight / sum(normalized) for weight in normalized]
    base = [minimum + math.floor(value) for minimum, value in zip(minimums, raw, strict=True)]
    remainder = total - sum(base)
    order = sorted(
        range(len(raw)),
        key=lambda index: (-(raw[index] - math.floor(raw[index])), index),
    )
    for index in order[:remainder]:
        base[index] += 1
    return base


def _minimum_departures(first: int, last: int) -> int:
    return 1 if first == last else 2


def _direction_weights(demand: list[DemandRecord], trips_b: list[Trip]) -> tuple[list[float], str]:
    directional = {
        direction: sum(
            record.average_daily_demand for record in demand if record.direction == direction
        )
        for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    }
    if sum(directional.values()) > 0:
        return [
            directional[Direction.TERMINAL_1_TO_2],
            directional[Direction.TERMINAL_2_TO_1],
        ], "Phân bổ chuyến theo nhu cầu đã tách chiều."
    existing = [
        sum(trip.direction == direction for trip in trips_b)
        for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    ]
    if sum(existing) == 0:
        existing = [1, 1]
    return existing, (
        "Sản lượng không tách chiều; dùng tỷ trọng chuyến Scenario B làm giả định phân bổ."
    )


def _service_blocks(
    first: int,
    last: int,
    block_minutes: int,
    demand: list[DemandRecord],
    direction: Direction,
) -> list[tuple[int, int]]:
    if first == last:
        return [(first, last)]
    relevant = [
        record
        for record in demand
        if record.direction in {direction, Direction.COMBINED}
        and record.block_end_seconds > first
        and record.block_start_seconds < last
    ]
    if relevant:
        boundaries = {first, last}
        for record in relevant:
            boundaries.add(max(first, record.block_start_seconds))
            boundaries.add(min(last, record.block_end_seconds))
        ordered = sorted(boundaries)
        return list(zip(ordered, ordered[1:], strict=False))
    duration = block_minutes * 60
    boundaries = list(range(first, last, duration)) + [last]
    return list(zip(boundaries, boundaries[1:], strict=False))


def _block_weight(
    start: int,
    end: int,
    direction: Direction,
    demand: list[DemandRecord],
    combined_share: float,
) -> float:
    weight = 0.0
    for record in demand:
        overlap = max(
            0,
            min(end, record.block_end_seconds) - max(start, record.block_start_seconds),
        )
        if overlap == 0:
            continue
        record_duration = max(1, record.block_end_seconds - record.block_start_seconds)
        if record.direction == direction:
            multiplier = 1.0
        elif record.direction == Direction.COMBINED:
            multiplier = combined_share
        else:
            continue
        weight += record.average_daily_demand * overlap / record_duration * multiplier
    return weight


def _required_for_block(
    start: int,
    end: int,
    direction: Direction,
    demand: list[DemandRecord],
    combined_share: float,
    parameters: ScenarioParameters,
) -> int:
    block_demand = 0.0
    for record in demand:
        if record.direction == direction:
            multiplier = 1.0
        elif record.direction == Direction.COMBINED:
            multiplier = combined_share
        else:
            continue
        if record.block_end_seconds > start and record.block_start_seconds < end:
            block_demand += record.average_daily_demand * multiplier
    return required_trips(block_demand, parameters.capacity, parameters.target_load_factor)


def _block_minimums(
    blocks: list[tuple[int, int]],
    weights: list[float],
    count: int,
    direction: Direction,
    demand: list[DemandRecord],
    combined_share: float,
    parameters: ScenarioParameters,
    last: int,
) -> list[int]:
    required = [
        _required_for_block(
            start,
            end,
            direction,
            demand,
            combined_share,
            parameters,
        )
        for start, end in blocks
    ]
    if blocks:
        required[0] = max(1, required[0])
        required[-1] = max(1, required[-1])
        after_last_demand = sum(
            record.average_daily_demand
            * (combined_share if record.direction == Direction.COMBINED else 1.0)
            for record in demand
            if record.direction in {direction, Direction.COMBINED}
            and record.block_start_seconds == last
        )
        if after_last_demand:
            required[-1] += required_trips(
                after_last_demand,
                parameters.capacity,
                parameters.target_load_factor,
            )
    if sum(required) <= count:
        return required
    coverage = [1 if weight > 0 else 0 for weight in weights]
    if coverage:
        coverage[0] = 1
        coverage[-1] = 1
    if sum(coverage) <= count:
        return coverage
    minimums = [0] * len(blocks)
    protected = {0, len(blocks) - 1}
    for index in protected:
        minimums[index] = 1
    remaining = count - sum(minimums)
    candidates = sorted(
        (index for index in range(len(blocks)) if index not in protected),
        key=lambda index: (-weights[index], index),
    )
    for index in candidates[:remaining]:
        minimums[index] = 1
    return minimums


def _times_for_blocks(
    blocks: list[tuple[int, int]], counts: list[int], first: int, last: int
) -> list[int]:
    output: list[int] = []
    for index, ((start, end), count) in enumerate(zip(blocks, counts, strict=True)):
        if count == 0:
            continue
        is_first = index == 0
        is_final = index == len(blocks) - 1
        if start == end:
            if count != 1:
                raise ValueError("Block 0 phút chỉ có thể chứa một chuyến")
            times = [start]
        elif is_first and is_final:
            if count == 1:
                times = [first]
            else:
                step = (last - first) / (count - 1)
                times = [round(first + item * step) for item in range(count)]
        elif is_first:
            step = (end - start) / count
            times = [round(start + item * step) for item in range(count)]
            times[0] = first
        elif is_final:
            step = (end - start) / count
            times = [round(start + (item + 1) * step) for item in range(count)]
            times[-1] = last
        else:
            step = (end - start) / count
            times = [round(start + (item + 0.5) * step) for item in range(count)]
        output.extend(times)
    ordered = sorted(output)
    for index in range(1, len(ordered)):
        if ordered[index] <= ordered[index - 1]:
            ordered[index] = ordered[index - 1] + 1
    if ordered and (ordered[0] != first or ordered[-1] != last):
        raise ValueError("Không giữ được chuyến đầu/chuyến cuối theo thông số")
    return ordered


def _generate_direction(
    scenario_name: str,
    direction: Direction,
    terminal: str,
    first: int,
    last: int,
    count: int,
    block_minutes: int,
    demand: list[DemandRecord],
    combined_share: float,
    parameters: ScenarioParameters,
) -> list[Trip]:
    blocks = _service_blocks(first, last, block_minutes, demand, direction)
    weights = [
        _block_weight(start, end, direction, demand, combined_share) for start, end in blocks
    ]
    minimums = _block_minimums(
        blocks,
        weights,
        count,
        direction,
        demand,
        combined_share,
        parameters,
        last,
    )
    counts = _integer_allocation(count, weights, minimums)
    times = _times_for_blocks(blocks, counts, first, last)
    return [
        Trip(
            scenario=scenario_name,
            trip_id="",
            departure_terminal=terminal,
            direction=direction,
            departure_seconds=departure,
            arrival_seconds=departure + parameters.default_trip_runtime_minutes * 60,
        )
        for departure in times
    ]


def minimum_required_total_trips(demand: list[DemandRecord], parameters: ScenarioParameters) -> int:
    if parameters.vehicle_capacity_passengers is None:
        return 0
    combined = [record for record in demand if record.direction == Direction.COMBINED]
    directional = [record for record in demand if record.direction != Direction.COMBINED]
    records = directional if directional else combined
    needed = sum(
        required_trips(
            record.average_daily_demand,
            parameters.capacity,
            parameters.target_load_factor,
        )
        for record in records
    )
    endpoint_minimum = _minimum_departures(
        parameters.terminal_1_first_departure, parameters.terminal_1_last_departure
    ) + _minimum_departures(
        parameters.terminal_2_first_departure, parameters.terminal_2_last_departure
    )
    return max(needed, endpoint_minimum)


def _generate_scenario(
    name: str,
    total_trips: int,
    parameters: ScenarioParameters,
    trips_b: list[Trip],
    demand: list[DemandRecord],
) -> tuple[ScenarioParameters, list[Trip], str]:
    weights, assumption = _direction_weights(demand, trips_b)
    endpoint_minimums = [
        _minimum_departures(
            parameters.terminal_1_first_departure,
            parameters.terminal_1_last_departure,
        ),
        _minimum_departures(
            parameters.terminal_2_first_departure,
            parameters.terminal_2_last_departure,
        ),
    ]
    directional_records = [record for record in demand if record.direction != Direction.COMBINED]
    required_by_direction = [
        sum(
            required_trips(
                record.average_daily_demand,
                parameters.capacity,
                parameters.target_load_factor,
            )
            for record in directional_records
            if record.direction == direction
        )
        for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    ]
    demand_minimums = [
        max(endpoint, required)
        for endpoint, required in zip(endpoint_minimums, required_by_direction, strict=True)
    ]
    allocation_minimums = (
        demand_minimums
        if directional_records and sum(demand_minimums) <= total_trips
        else endpoint_minimums
    )
    direction_counts = _integer_allocation(total_trips, weights, allocation_minimums)
    total_weight = sum(weights) or 2
    shares = [weight / total_weight for weight in weights]
    generated = _generate_direction(
        name,
        Direction.TERMINAL_1_TO_2,
        parameters.terminal_1_name,
        parameters.terminal_1_first_departure,
        parameters.terminal_1_last_departure,
        direction_counts[0],
        parameters.time_block_minutes,
        demand,
        shares[0],
        parameters,
    )
    generated.extend(
        _generate_direction(
            name,
            Direction.TERMINAL_2_TO_1,
            parameters.terminal_2_name,
            parameters.terminal_2_first_departure,
            parameters.terminal_2_last_departure,
            direction_counts[1],
            parameters.time_block_minutes,
            demand,
            shares[1],
            parameters,
        )
    )
    ordered = sorted(generated, key=lambda trip: (trip.departure_seconds, trip.direction.value))
    trips = [replace(trip, trip_id=f"{name}-{index:04d}") for index, trip in enumerate(ordered, 1)]
    scenario_parameters = replace(parameters, total_daily_trips=total_trips)
    return scenario_parameters, trips, assumption


def generate_recommendations(
    parameters_b: ScenarioParameters,
    trips_b: list[Trip],
    demand: list[DemandRecord],
    available_fleet: int | None = None,
    configuration: dict[str, object] | None = None,
) -> GenerationReport:
    if parameters_b.vehicle_capacity_passengers is None:
        return GenerationReport(
            feasible=False,
            reasons=["Thiếu sức chứa phương tiện nên không thể sinh Scenario C."],
        )
    if parameters_b.effective_layover_minutes < parameters_b.regulatory_minimum_layover_minutes:
        return GenerationReport(
            feasible=False,
            reasons=["Thời gian quay đầu thấp hơn hard constraint."],
        )
    endpoint_minimum = _minimum_departures(
        parameters_b.terminal_1_first_departure,
        parameters_b.terminal_1_last_departure,
    ) + _minimum_departures(
        parameters_b.terminal_2_first_departure,
        parameters_b.terminal_2_last_departure,
    )
    if parameters_b.total_daily_trips < endpoint_minimum:
        return GenerationReport(
            feasible=False,
            reasons=["Tổng chuyến B không đủ để giữ chuyến đầu và chuyến cuối tại cả hai bến."],
            minimum_required_total_trips=endpoint_minimum,
            missing_trips=endpoint_minimum - parameters_b.total_daily_trips,
        )
    try:
        c_config = ScenarioCConfig.from_mapping(configuration)
        active_fleet = available_fleet or assign_fleet(trips_b, parameters_b).minimum_vehicles
        scenario_c = generate_scenario_c(
            parameters_b,
            trips_b,
            demand,
            active_fleet,
            c_config,
        )
    except ValueError as exc:
        return GenerationReport(feasible=False, reasons=[str(exc)])
    minimum = minimum_required_total_trips(demand, parameters_b)
    scenarios = [scenario_c]
    if minimum > parameters_b.total_daily_trips:
        c2_parameters, c2, c2_assumption = _generate_scenario(
            "C2", minimum, parameters_b, trips_b, demand
        )
        scenarios.append(
            GeneratedScenario(
                name="C2",
                parameters=c2_parameters,
                trips=c2,
                reason=(
                    "Ưu tiên đáp ứng nhu cầu ở target; có tăng tổng chuyến được ghi rõ. "
                    + c2_assumption
                ),
                strategy_id="demand_capacity_expansion",
                resource_fleet_limit=None,
                display_name="C2 — Mở rộng năng lực theo nhu cầu",
            )
        )
    no_improvement = scenario_c.generation_status in {
        ScenarioCStatus.NO_BETTER_REDISTRIBUTION,
        ScenarioCStatus.INFEASIBLE_FIXED_RESOURCES,
        ScenarioCStatus.INSUFFICIENT_DATA,
    }
    return GenerationReport(
        feasible=True,
        scenarios=scenarios,
        reasons=[scenario_c.reason] if no_improvement else [],
        minimum_required_total_trips=minimum,
        missing_trips=max(0, minimum - parameters_b.total_daily_trips),
        no_improvement=no_improvement,
    )
