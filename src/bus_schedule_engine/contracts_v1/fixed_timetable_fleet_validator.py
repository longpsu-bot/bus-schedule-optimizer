"""Exact fleet validation for immutable two-terminal fixed timetables.

This module deliberately has no timetable-generation or timetable-repair API.
It converts authoritative departures to trips, builds the legal successor DAG,
and solves the exact minimum path cover with a deterministic matching hierarchy.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction


class FleetValidationStatusV1(StrEnum):
    FEASIBLE_WITHIN_PILOT_FLEET_LIMIT = "FEASIBLE_WITHIN_PILOT_FLEET_LIMIT"
    FEASIBLE_BUT_EXCEEDS_PILOT_FLEET_LIMIT = "FEASIBLE_BUT_EXCEEDS_PILOT_FLEET_LIMIT"


TERMINAL_CAPACITY_NOT_VALIDATED = "TERMINAL_CAPACITY_NOT_VALIDATED"


@dataclass(frozen=True, slots=True)
class FixedOperationalTripV1:
    trip_id: str
    route_id: str
    direction: str
    origin_terminal: str
    destination_terminal: str
    departure_minute: int
    runtime_minutes: int
    arrival_minute: int

    def __post_init__(self) -> None:
        if not self.trip_id.strip() or not self.route_id.strip():
            raise ValueError("trip and route identities must be non-empty")
        if self.direction not in {"terminal_1_to_2", "terminal_2_to_1"}:
            raise ValueError("fixed trip direction is invalid")
        if self.origin_terminal == self.destination_terminal:
            raise ValueError("fixed trip terminals must differ")
        if self.runtime_minutes <= 0:
            raise ValueError("runtime_minutes must be positive")
        if self.arrival_minute != self.departure_minute + self.runtime_minutes:
            raise ValueError("arrival must equal departure plus authoritative runtime")


@dataclass(frozen=True, slots=True)
class VehicleBlockTripV1:
    sequence: int
    trip: FixedOperationalTripV1
    next_trip_layover_minutes: int | None


@dataclass(frozen=True, slots=True)
class VehicleBlockV1:
    vehicle_id: str
    trips: tuple[VehicleBlockTripV1, ...]


@dataclass(frozen=True, slots=True)
class LayoverMetricsV1:
    minimum_actual_layover_minutes: int | None
    median_actual_layover_minutes: Fraction | None
    maximum_actual_layover_minutes: int | None
    total_excess_terminal_wait_minutes: int
    maximum_excess_terminal_wait_minutes: int | None


@dataclass(frozen=True, slots=True)
class FixedTimetableFleetResultV1:
    route_id: str
    total_departures: int
    direction_totals: dict[str, int]
    minimum_fleet_required: int
    pilot_fleet_limit: int
    fleet_margin: int
    approved_active_fleet: None
    initial_fleet_terminal_1: int
    initial_fleet_terminal_2: int
    ending_fleet_terminal_1: int
    ending_fleet_terminal_2: int
    layover_metrics: LayoverMetricsV1
    blocks: tuple[VehicleBlockV1, ...]
    matching: tuple[tuple[str, str], ...]
    fleet_status: FleetValidationStatusV1
    terminal_capacity_status: str


@dataclass(slots=True)
class _ResidualEdge:
    target: int
    reverse_index: int
    capacity: int
    cost: int
    identity: tuple[str, str] | None = None


def can_chain_trips_v1(
    previous: FixedOperationalTripV1,
    successor: FixedOperationalTripV1,
    minimum_layover_minutes: int,
) -> bool:
    """Return whether successor can legally follow previous without deadhead."""

    return (
        previous.destination_terminal == successor.origin_terminal
        and successor.departure_minute >= previous.arrival_minute + minimum_layover_minutes
    )


def build_compatibility_dag_v1(
    trips: tuple[FixedOperationalTripV1, ...],
    minimum_layover_minutes: int,
) -> dict[str, tuple[str, ...]]:
    """Build the deterministic fixed-trip compatibility DAG."""

    if minimum_layover_minutes < 0:
        raise ValueError("minimum_layover_minutes cannot be negative")
    if len({trip.trip_id for trip in trips}) != len(trips):
        raise ValueError("trip ids must be unique")
    ordered = sorted(trips, key=lambda trip: trip.trip_id)
    return {
        trip.trip_id: tuple(
            successor.trip_id
            for successor in ordered
            if can_chain_trips_v1(trip, successor, minimum_layover_minutes)
        )
        for trip in ordered
    }


def _maximum_matching_cardinality(
    left_ids: tuple[str, ...],
    adjacency: dict[str, tuple[str, ...]],
) -> int:
    """Hopcroft-Karp cardinality for the path-cover bipartite graph."""

    left_match: dict[str, str] = {}
    right_match: dict[str, str] = {}
    distance: dict[str, int] = {}

    def breadth_first() -> bool:
        queue: deque[str] = deque()
        found = False
        for left in left_ids:
            if left not in left_match:
                distance[left] = 0
                queue.append(left)
            else:
                distance[left] = -1
        while queue:
            left = queue.popleft()
            for right in adjacency[left]:
                paired_left = right_match.get(right)
                if paired_left is None:
                    found = True
                elif distance[paired_left] < 0:
                    distance[paired_left] = distance[left] + 1
                    queue.append(paired_left)
        return found

    def depth_first(left: str) -> bool:
        for right in adjacency[left]:
            paired_left = right_match.get(right)
            if paired_left is None or (
                distance.get(paired_left) == distance[left] + 1 and depth_first(paired_left)
            ):
                left_match[left] = right
                right_match[right] = left
                return True
        distance[left] = -1
        return False

    while breadth_first():
        for left in left_ids:
            if left not in left_match:
                depth_first(left)
    return len(left_match)


def _add_residual_arc(
    graph: list[list[_ResidualEdge]],
    source: int,
    target: int,
    capacity: int,
    cost: int,
    identity: tuple[str, str] | None = None,
) -> None:
    forward = _ResidualEdge(target, len(graph[target]), capacity, cost, identity)
    reverse = _ResidualEdge(source, len(graph[source]), 0, -cost)
    graph[source].append(forward)
    graph[target].append(reverse)


def _minimum_cost_matching(
    left_ids: tuple[str, ...],
    right_ids: tuple[str, ...],
    edge_costs: dict[tuple[str, str], int],
    required_cardinality: int,
) -> tuple[int, dict[str, str]] | None:
    """Exact cardinality min-cost bipartite matching via residual shortest paths."""

    if required_cardinality == 0:
        return 0, {}
    left_offset = 1
    right_offset = left_offset + len(left_ids)
    sink = right_offset + len(right_ids)
    graph: list[list[_ResidualEdge]] = [[] for _ in range(sink + 1)]
    left_node = {value: left_offset + index for index, value in enumerate(left_ids)}
    right_node = {value: right_offset + index for index, value in enumerate(right_ids)}
    for left in left_ids:
        _add_residual_arc(graph, 0, left_node[left], 1, 0)
    for right in right_ids:
        _add_residual_arc(graph, right_node[right], sink, 1, 0)
    for left in left_ids:
        for right in right_ids:
            key = (left, right)
            if key in edge_costs:
                _add_residual_arc(
                    graph,
                    left_node[left],
                    right_node[right],
                    1,
                    edge_costs[key],
                    identity=key,
                )

    total_cost = 0
    for _ in range(required_cardinality):
        distance: list[int | None] = [None] * len(graph)
        predecessor: list[tuple[int, int] | None] = [None] * len(graph)
        in_queue = [False] * len(graph)
        queue: deque[int] = deque([0])
        distance[0] = 0
        in_queue[0] = True
        while queue:
            node = queue.popleft()
            in_queue[node] = False
            node_distance = distance[node]
            assert node_distance is not None
            for edge_index, edge in enumerate(graph[node]):
                if edge.capacity == 0:
                    continue
                candidate = node_distance + edge.cost
                if distance[edge.target] is None or candidate < distance[edge.target]:
                    distance[edge.target] = candidate
                    predecessor[edge.target] = (node, edge_index)
                    if not in_queue[edge.target]:
                        queue.append(edge.target)
                        in_queue[edge.target] = True
        if distance[sink] is None:
            return None
        total_cost += distance[sink]
        node = sink
        while node != 0:
            step = predecessor[node]
            assert step is not None
            previous, edge_index = step
            edge = graph[previous][edge_index]
            edge.capacity -= 1
            graph[node][edge.reverse_index].capacity += 1
            node = previous

    matching: dict[str, str] = {}
    for left in left_ids:
        for edge in graph[left_node[left]]:
            if edge.identity is not None and edge.capacity == 0:
                matching[edge.identity[0]] = edge.identity[1]
    if len(matching) != required_cardinality:
        raise RuntimeError("internal min-cost matching extraction failure")
    return total_cost, matching


def _canonical_matching(
    trips: tuple[FixedOperationalTripV1, ...],
    minimum_layover_minutes: int,
) -> dict[str, str]:
    by_id = {trip.trip_id: trip for trip in trips}
    left_ids = tuple(sorted(by_id))
    right_ids = left_ids
    adjacency = build_compatibility_dag_v1(trips, minimum_layover_minutes)
    cardinality = _maximum_matching_cardinality(left_ids, adjacency)
    if cardinality == 0:
        return {}
    excess = {
        (left, right): (
            by_id[right].departure_minute - by_id[left].arrival_minute - minimum_layover_minutes
        )
        for left in left_ids
        for right in adjacency[left]
    }
    minimum_total_result = _minimum_cost_matching(left_ids, right_ids, excess, cardinality)
    if minimum_total_result is None:
        raise RuntimeError("maximum matching cardinality could not be reproduced")
    minimum_total_excess = minimum_total_result[0]

    thresholds = sorted(set(excess.values()))
    low = 0
    high = len(thresholds) - 1
    while low < high:
        middle = (low + high) // 2
        threshold = thresholds[middle]
        restricted = {edge: cost for edge, cost in excess.items() if cost <= threshold}
        result = _minimum_cost_matching(left_ids, right_ids, restricted, cardinality)
        if result is not None and result[0] == minimum_total_excess:
            high = middle
        else:
            low = middle + 1
    minimum_maximum_excess = thresholds[low]

    # Encode the complete successor vector (unmatched sorts after all trip ids)
    # as a positional integer. Its full range is smaller than total_scale, so it
    # can break ties but can never trade one minute of total excess waiting.
    base = len(right_ids) + 1
    total_scale = base ** len(left_ids)
    unmatched_rank = len(right_ids)
    right_rank = {right: index for index, right in enumerate(right_ids)}
    lexicographic_costs: dict[tuple[str, str], int] = {}
    for left_index, left in enumerate(left_ids):
        positional_weight = base ** (len(left_ids) - left_index - 1)
        for right in adjacency[left]:
            edge = (left, right)
            if excess[edge] <= minimum_maximum_excess:
                lexicographic_delta = (right_rank[right] - unmatched_rank) * positional_weight
                lexicographic_costs[edge] = excess[edge] * total_scale + lexicographic_delta
    canonical = _minimum_cost_matching(left_ids, right_ids, lexicographic_costs, cardinality)
    if canonical is None:
        raise RuntimeError("canonical matching could not be reconstructed")
    matching = canonical[1]
    if sum(excess[edge] for edge in matching.items()) != minimum_total_excess:
        raise RuntimeError("canonical matching violated minimum total waiting")
    if max(excess[edge] for edge in matching.items()) != minimum_maximum_excess:
        raise RuntimeError("canonical matching violated minimum maximum waiting")
    return matching


def _reconstruct_blocks(
    trips: tuple[FixedOperationalTripV1, ...],
    matching: dict[str, str],
) -> tuple[VehicleBlockV1, ...]:
    by_id = {trip.trip_id: trip for trip in trips}
    successor_ids = set(matching.values())
    starts = sorted(
        (trip for trip in trips if trip.trip_id not in successor_ids),
        key=lambda trip: (trip.departure_minute, trip.trip_id),
    )
    blocks: list[VehicleBlockV1] = []
    visited: set[str] = set()
    for block_index, start in enumerate(starts, start=1):
        block_trips: list[VehicleBlockTripV1] = []
        current = start
        sequence = 1
        while True:
            if current.trip_id in visited:
                raise RuntimeError("cycle or duplicate found during block reconstruction")
            visited.add(current.trip_id)
            successor_id = matching.get(current.trip_id)
            layover = (
                by_id[successor_id].departure_minute - current.arrival_minute
                if successor_id is not None
                else None
            )
            block_trips.append(VehicleBlockTripV1(sequence, current, layover))
            if successor_id is None:
                break
            current = by_id[successor_id]
            sequence += 1
        blocks.append(VehicleBlockV1(f"Vehicle {block_index:02d}", tuple(block_trips)))
    if visited != set(by_id):
        raise RuntimeError("block reconstruction omitted one or more fixed trips")
    return tuple(blocks)


def validate_fixed_timetable_fleet_v1(
    trips: tuple[FixedOperationalTripV1, ...],
    *,
    minimum_layover_minutes: int,
    pilot_fleet_limit: int,
    terminal_1_name: str,
    terminal_2_name: str,
) -> FixedTimetableFleetResultV1:
    """Validate a fixed timetable and return its exact canonical vehicle blocks."""

    if not trips:
        raise ValueError("fleet validation requires at least one fixed trip")
    if pilot_fleet_limit < 0:
        raise ValueError("pilot_fleet_limit cannot be negative")
    route_ids = {trip.route_id for trip in trips}
    if len(route_ids) != 1:
        raise ValueError("all fixed trips must belong to one route")
    matching = _canonical_matching(trips, minimum_layover_minutes)
    blocks = _reconstruct_blocks(trips, matching)
    by_id = {trip.trip_id: trip for trip in trips}
    actual_layovers = [
        by_id[right].departure_minute - by_id[left].arrival_minute
        for left, right in matching.items()
    ]
    if any(value < minimum_layover_minutes for value in actual_layovers):
        raise RuntimeError("canonical block contains an illegal layover")
    excess_waits = [value - minimum_layover_minutes for value in actual_layovers]
    initial_t1 = sum(block.trips[0].trip.origin_terminal == terminal_1_name for block in blocks)
    initial_t2 = sum(block.trips[0].trip.origin_terminal == terminal_2_name for block in blocks)
    ending_t1 = sum(
        block.trips[-1].trip.destination_terminal == terminal_1_name for block in blocks
    )
    ending_t2 = sum(
        block.trips[-1].trip.destination_terminal == terminal_2_name for block in blocks
    )
    minimum_fleet = len(blocks)
    status = (
        FleetValidationStatusV1.FEASIBLE_WITHIN_PILOT_FLEET_LIMIT
        if minimum_fleet <= pilot_fleet_limit
        else FleetValidationStatusV1.FEASIBLE_BUT_EXCEEDS_PILOT_FLEET_LIMIT
    )
    direction_totals = {
        direction: sum(trip.direction == direction for trip in trips)
        for direction in ("terminal_1_to_2", "terminal_2_to_1")
    }
    ordered_layovers = sorted(actual_layovers)
    if not ordered_layovers:
        median_layover = None
    elif len(ordered_layovers) % 2:
        median_layover = Fraction(ordered_layovers[len(ordered_layovers) // 2])
    else:
        middle = len(ordered_layovers) // 2
        median_layover = Fraction(ordered_layovers[middle - 1] + ordered_layovers[middle], 2)
    return FixedTimetableFleetResultV1(
        route_id=next(iter(route_ids)),
        total_departures=len(trips),
        direction_totals=direction_totals,
        minimum_fleet_required=minimum_fleet,
        pilot_fleet_limit=pilot_fleet_limit,
        fleet_margin=pilot_fleet_limit - minimum_fleet,
        approved_active_fleet=None,
        initial_fleet_terminal_1=initial_t1,
        initial_fleet_terminal_2=initial_t2,
        ending_fleet_terminal_1=ending_t1,
        ending_fleet_terminal_2=ending_t2,
        layover_metrics=LayoverMetricsV1(
            minimum_actual_layover_minutes=(min(actual_layovers) if actual_layovers else None),
            median_actual_layover_minutes=median_layover,
            maximum_actual_layover_minutes=(max(actual_layovers) if actual_layovers else None),
            total_excess_terminal_wait_minutes=sum(excess_waits),
            maximum_excess_terminal_wait_minutes=(max(excess_waits) if excess_waits else None),
        ),
        blocks=blocks,
        matching=tuple(sorted(matching.items())),
        fleet_status=status,
        terminal_capacity_status=TERMINAL_CAPACITY_NOT_VALIDATED,
    )


__all__ = [
    "TERMINAL_CAPACITY_NOT_VALIDATED",
    "FixedOperationalTripV1",
    "FixedTimetableFleetResultV1",
    "FleetValidationStatusV1",
    "LayoverMetricsV1",
    "VehicleBlockTripV1",
    "VehicleBlockV1",
    "build_compatibility_dag_v1",
    "can_chain_trips_v1",
    "validate_fixed_timetable_fleet_v1",
]
