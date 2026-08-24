"""Route 6/10 clean-boundary pilot recompilation, fleet validation, and selection."""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .contracts_v1.clean_boundary_compiler import (
    CleanBoundaryCompilationStatusV1,
    CleanBoundaryCompilationV1,
    OperationalEndpointAuthorityV1,
    clean_boundary_compilation_to_dict_v1,
    compile_clean_boundary_timetable_v1,
    demand_regime_allocation_from_mapping_v1,
    scan_serialized_headway_outliers_v1,
)
from .time_utils import format_hhmm
from .v3_workbook import import_v3_multi_period_workbook_v1

CLEAN_BOUNDARY_PILOT_PROFILE_V1 = "routes_6_10_clean_boundary_pilot_v1"
FINAL_SELECTION_AUTHORITY_BRIDGE_V1 = "balanced_candidate_authority_bridge_v1"
PILOT_MINIMUM_LAYOVER_MINUTES_V1 = 5
_CANDIDATE_KEYS = ("c1_demand_fit", "c2_conservative", "c3_balanced")
_CANDIDATE_ROLE_RANK = {
    "C3_BALANCED": 0,
    "C2_CONSERVATIVE": 1,
    "C1_DEMAND_FIT": 2,
}


@dataclass(frozen=True, slots=True)
class FleetCombinationValidationV1:
    route_id: str
    outbound_candidate_id: str
    inbound_candidate_id: str
    status: str
    runtime_minutes: int
    minimum_layover_minutes: int
    fleet_requirement: int | None
    fleet_ceiling: int
    within_fleet_ceiling: bool
    minimum_connection_layover_minutes: int | None
    all_connections_meet_layover: bool
    average_scheduled_wait_minutes: float | None
    frozen_demand_mismatch: float
    frozen_moved_trips: int
    compiler_quantization_error: float | None
    service_regime_count: int | None


@dataclass(frozen=True, slots=True)
class FleetTripAssignmentV1:
    trip_id: str
    direction: str
    sequence: int
    departure: int
    arrival: int
    vehicle_id: str
    next_trip_id: str | None
    connection_layover_minutes: int | None


@dataclass(frozen=True, slots=True)
class FleetPlanV1:
    route_id: str
    outbound_candidate_id: str
    inbound_candidate_id: str
    fleet_requirement: int
    minimum_connection_layover_minutes: int | None
    assignments: tuple[FleetTripAssignmentV1, ...]


@dataclass(frozen=True, slots=True)
class FinalCandidateSelectionV1:
    selection_profile: str
    route_id: str
    outbound_candidate_id: str
    inbound_candidate_id: str
    selection_key: tuple[Any, ...]
    fleet_requirement: int
    fleet_ceiling: int
    average_scheduled_wait_minutes: float
    frozen_demand_mismatch: float
    frozen_moved_trips: int
    compiler_quantization_error: float
    service_regime_count: int


@dataclass(frozen=True, slots=True)
class ProductHeadwayRowV1:
    sequence: int
    departure: int
    service_regime_id: str
    service_headway_minutes: int
    gap_from_previous_minutes: int | None
    gap_owner_service_regime_id: str | None
    gap_ownership: str | None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_upstream_fingerprints_v1(repo_root: Path) -> dict[str, str]:
    relative_paths = (
        "outputs/demand_regime_model_selection/route_6_demand_regimes.json",
        "outputs/demand_regime_model_selection/route_10_demand_regimes.json",
        "outputs/demand_regime_review/route_6_demand_regimes.json",
        "outputs/demand_regime_review/route_10_demand_regimes.json",
        ("outputs/demand_regime_trip_allocation/route_6_demand_regime_trip_allocations.json"),
        ("outputs/demand_regime_trip_allocation/route_10_demand_regime_trip_allocations.json"),
    )
    return {relative: _sha256(repo_root / relative) for relative in relative_paths}


def _endpoint_authority(
    *,
    workbook_path: Path,
    direction: str,
    analysis_window_start: int,
    analysis_window_end: int,
) -> tuple[OperationalEndpointAuthorityV1, int, int]:
    imported = import_v3_multi_period_workbook_v1(workbook_path)
    parameters = imported.base_workbook.parameters_b
    if direction == "outbound":
        fixed_first = parameters.terminal_1_first_departure
        fixed_last = parameters.terminal_1_last_departure
        fields = "terminal_1_first_departure,terminal_1_last_departure"
    elif direction == "inbound":
        fixed_first = parameters.terminal_2_first_departure
        fixed_last = parameters.terminal_2_last_departure
        fields = "terminal_2_first_departure,terminal_2_last_departure"
    else:
        raise ValueError(f"unsupported direction {direction!r}")
    return (
        OperationalEndpointAuthorityV1(
            route_id=str(parameters.route_id),
            direction=direction,
            analysis_window_start=analysis_window_start,
            analysis_window_end=analysis_window_end,
            fixed_first_departure=fixed_first,
            fixed_last_departure=fixed_last,
            authority_source=f"{workbook_path.resolve()}::THAM_SO_B::{fields}",
        ),
        parameters.trip_runtime_minutes,
        parameters.available_fleet_limit,
    )


def _maximum_matching(adjacency: Sequence[Sequence[int]]) -> tuple[list[int], list[int]]:
    left_count = len(adjacency)
    pair_left = [-1] * left_count
    pair_right = [-1] * left_count
    distance = [-1] * left_count

    def breadth_first() -> bool:
        queue: deque[int] = deque()
        found = False
        for left in range(left_count):
            if pair_left[left] == -1:
                distance[left] = 0
                queue.append(left)
            else:
                distance[left] = -1
        while queue:
            left = queue.popleft()
            for right in adjacency[left]:
                previous_left = pair_right[right]
                if previous_left == -1:
                    found = True
                elif distance[previous_left] == -1:
                    distance[previous_left] = distance[left] + 1
                    queue.append(previous_left)
        return found

    def depth_first(left: int) -> bool:
        for right in adjacency[left]:
            previous_left = pair_right[right]
            if previous_left == -1 or (
                distance[previous_left] == distance[left] + 1 and depth_first(previous_left)
            ):
                pair_left[left] = right
                pair_right[right] = left
                return True
        distance[left] = -1
        return False

    while breadth_first():
        for left in range(left_count):
            if pair_left[left] == -1:
                depth_first(left)
    return pair_left, pair_right


def build_minimum_fleet_plan_v1(
    *,
    route_id: str,
    outbound_candidate_id: str,
    inbound_candidate_id: str,
    outbound_departures: Sequence[int],
    inbound_departures: Sequence[int],
    runtime_minutes: int,
    minimum_layover_minutes: int,
) -> FleetPlanV1:
    runtime_seconds = runtime_minutes * 60
    ready_seconds = (runtime_minutes + minimum_layover_minutes) * 60
    trips = sorted(
        (
            (departure, "outbound", sequence)
            for sequence, departure in enumerate(outbound_departures, start=1)
        ),
        key=lambda item: (item[0], item[1], item[2]),
    )
    trips.extend(
        (departure, "inbound", sequence)
        for sequence, departure in enumerate(inbound_departures, start=1)
    )
    trips.sort(key=lambda item: (item[0], item[1], item[2]))
    trip_count = len(trips)
    adjacency = tuple(
        tuple(
            right
            for right, (later_departure, later_direction, _) in enumerate(trips)
            if (later_direction != direction and later_departure >= departure + ready_seconds)
        )
        for departure, direction, _ in trips
    )
    successors, predecessors = _maximum_matching(adjacency)
    starts = tuple(index for index in range(trip_count) if predecessors[index] == -1)
    vehicle_by_trip: dict[int, str] = {}
    for vehicle_number, start in enumerate(starts, start=1):
        vehicle_id = f"V{vehicle_number:02d}"
        cursor = start
        while cursor != -1:
            if cursor in vehicle_by_trip:
                raise AssertionError("fleet path cover contains a cycle")
            vehicle_by_trip[cursor] = vehicle_id
            cursor = successors[cursor]
    if len(vehicle_by_trip) != trip_count:
        raise AssertionError("fleet path cover did not assign every trip")

    trip_ids = tuple(f"{direction.upper()}-{sequence:03d}" for _, direction, sequence in trips)
    assignments: list[FleetTripAssignmentV1] = []
    connection_layovers: list[int] = []
    for index, (departure, direction, sequence) in enumerate(trips):
        successor = successors[index]
        layover = None
        next_trip_id = None
        if successor != -1:
            next_trip_id = trip_ids[successor]
            layover = (trips[successor][0] - (departure + runtime_seconds)) // 60
            connection_layovers.append(layover)
        assignments.append(
            FleetTripAssignmentV1(
                trip_id=trip_ids[index],
                direction=direction,
                sequence=sequence,
                departure=departure,
                arrival=departure + runtime_seconds,
                vehicle_id=vehicle_by_trip[index],
                next_trip_id=next_trip_id,
                connection_layover_minutes=layover,
            )
        )
    minimum_connection = min(connection_layovers, default=None)
    if minimum_connection is not None and minimum_connection < minimum_layover_minutes:
        raise AssertionError("fleet assignment violates minimum layover")
    return FleetPlanV1(
        route_id=route_id,
        outbound_candidate_id=outbound_candidate_id,
        inbound_candidate_id=inbound_candidate_id,
        fleet_requirement=len(starts),
        minimum_connection_layover_minutes=minimum_connection,
        assignments=tuple(assignments),
    )


def _average_scheduled_wait_minutes(departures: Sequence[int]) -> float:
    if len(departures) < 2:
        return 0.0
    minutes = tuple(item // 60 for item in departures)
    span = minutes[-1] - minutes[0]
    if span <= 0:
        return 0.0
    gaps = tuple(later - earlier for earlier, later in zip(minutes, minutes[1:], strict=False))
    return sum(gap * gap for gap in gaps) / (2 * span)


def validate_fleet_combination_v1(
    *,
    route_id: str,
    outbound: CleanBoundaryCompilationV1,
    inbound: CleanBoundaryCompilationV1,
    outbound_allocation: Mapping[str, Any],
    inbound_allocation: Mapping[str, Any],
    runtime_minutes: int,
    minimum_layover_minutes: int,
    fleet_ceiling: int,
) -> FleetCombinationValidationV1:
    if (
        outbound.status != CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES
        or inbound.status != CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES
    ):
        return FleetCombinationValidationV1(
            route_id=route_id,
            outbound_candidate_id=outbound.candidate_id,
            inbound_candidate_id=inbound.candidate_id,
            status="COMPILATION_UNAVAILABLE",
            runtime_minutes=runtime_minutes,
            minimum_layover_minutes=minimum_layover_minutes,
            fleet_requirement=None,
            fleet_ceiling=fleet_ceiling,
            within_fleet_ceiling=False,
            minimum_connection_layover_minutes=None,
            all_connections_meet_layover=False,
            average_scheduled_wait_minutes=None,
            frozen_demand_mismatch=(
                float(outbound_allocation["demand_mismatch"])
                + float(inbound_allocation["demand_mismatch"])
            ),
            frozen_moved_trips=(
                int(outbound_allocation["moved_trips"]) + int(inbound_allocation["moved_trips"])
            ),
            compiler_quantization_error=None,
            service_regime_count=None,
        )
    plan = build_minimum_fleet_plan_v1(
        route_id=route_id,
        outbound_candidate_id=outbound.candidate_id,
        inbound_candidate_id=inbound.candidate_id,
        outbound_departures=outbound.exact_departures,
        inbound_departures=inbound.exact_departures,
        runtime_minutes=runtime_minutes,
        minimum_layover_minutes=minimum_layover_minutes,
    )
    minimum_connection = plan.minimum_connection_layover_minutes
    within_ceiling = plan.fleet_requirement <= fleet_ceiling
    all_layovers = minimum_connection is None or minimum_connection >= minimum_layover_minutes
    outbound_wait = _average_scheduled_wait_minutes(outbound.exact_departures)
    inbound_wait = _average_scheduled_wait_minutes(inbound.exact_departures)
    return FleetCombinationValidationV1(
        route_id=route_id,
        outbound_candidate_id=outbound.candidate_id,
        inbound_candidate_id=inbound.candidate_id,
        status="FLEET_FEASIBLE" if within_ceiling and all_layovers else "FLEET_INFEASIBLE",
        runtime_minutes=runtime_minutes,
        minimum_layover_minutes=minimum_layover_minutes,
        fleet_requirement=plan.fleet_requirement,
        fleet_ceiling=fleet_ceiling,
        within_fleet_ceiling=within_ceiling,
        minimum_connection_layover_minutes=minimum_connection,
        all_connections_meet_layover=all_layovers,
        average_scheduled_wait_minutes=(outbound_wait + inbound_wait) / 2,
        frozen_demand_mismatch=(
            float(outbound_allocation["demand_mismatch"])
            + float(inbound_allocation["demand_mismatch"])
        ),
        frozen_moved_trips=(
            int(outbound_allocation["moved_trips"]) + int(inbound_allocation["moved_trips"])
        ),
        compiler_quantization_error=(
            float(outbound.total_headway_quantization_error or 0)
            + float(inbound.total_headway_quantization_error or 0)
        ),
        service_regime_count=(len(outbound.service_regimes) + len(inbound.service_regimes)),
    )


def select_final_candidate_pair_v1(
    route_id: str,
    matrix: Sequence[FleetCombinationValidationV1],
) -> FinalCandidateSelectionV1:
    eligible = tuple(
        item
        for item in matrix
        if (
            item.status == "FLEET_FEASIBLE"
            and item.fleet_requirement is not None
            and item.average_scheduled_wait_minutes is not None
            and item.compiler_quantization_error is not None
            and item.service_regime_count is not None
        )
    )
    if not eligible:
        raise ValueError(f"route {route_id} has no fleet-feasible compiled candidate pair")

    def selection_key(item: FleetCombinationValidationV1) -> tuple[Any, ...]:
        outbound_rank = _CANDIDATE_ROLE_RANK[item.outbound_candidate_id]
        inbound_rank = _CANDIDATE_ROLE_RANK[item.inbound_candidate_id]
        return (
            max(outbound_rank, inbound_rank),
            outbound_rank + inbound_rank,
            item.frozen_demand_mismatch,
            item.frozen_moved_trips,
            item.fleet_requirement,
            item.average_scheduled_wait_minutes,
            item.compiler_quantization_error,
            item.service_regime_count,
            item.outbound_candidate_id,
            item.inbound_candidate_id,
        )

    selected = min(eligible, key=selection_key)
    key = selection_key(selected)
    return FinalCandidateSelectionV1(
        selection_profile=FINAL_SELECTION_AUTHORITY_BRIDGE_V1,
        route_id=route_id,
        outbound_candidate_id=selected.outbound_candidate_id,
        inbound_candidate_id=selected.inbound_candidate_id,
        selection_key=key,
        fleet_requirement=int(selected.fleet_requirement),
        fleet_ceiling=selected.fleet_ceiling,
        average_scheduled_wait_minutes=float(selected.average_scheduled_wait_minutes),
        frozen_demand_mismatch=selected.frozen_demand_mismatch,
        frozen_moved_trips=selected.frozen_moved_trips,
        compiler_quantization_error=float(selected.compiler_quantization_error),
        service_regime_count=int(selected.service_regime_count),
    )


def build_product_headway_rows_v1(
    compilation: CleanBoundaryCompilationV1,
) -> tuple[ProductHeadwayRowV1, ...]:
    if compilation.status != CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES:
        return ()
    service_by_departure: dict[int, tuple[str, int]] = {}
    for service in compilation.service_regimes:
        for departure in service.departures:
            service_by_departure[departure] = (
                service.service_regime_id,
                service.uniform_headway_minutes,
            )
    boundary_by_pair = {
        (item.departure_i, item.departure_j): item for item in compilation.boundary_diagnostics
    }
    rows: list[ProductHeadwayRowV1] = []
    previous: int | None = None
    for sequence, departure in enumerate(compilation.exact_departures, start=1):
        service_id, service_headway = service_by_departure[departure]
        gap = None
        gap_owner = None
        ownership = None
        if previous is not None:
            gap = (departure - previous) // 60
            boundary = boundary_by_pair.get((previous, departure))
            if boundary is None:
                previous_service, _ = service_by_departure[previous]
                if previous_service != service_id:
                    raise AssertionError("unclassified product boundary pair")
                gap_owner = service_id
                ownership = "INTERNAL_SERVICE_REGIME"
            else:
                ownership = boundary.ownership.value
                if ownership == "LEFT_SERVICE_REGIME":
                    gap_owner = service_by_departure[previous][0]
                else:
                    gap_owner = service_id
            owner_headway = next(
                item.uniform_headway_minutes
                for item in compilation.service_regimes
                if item.service_regime_id == gap_owner
            )
            if gap != owner_headway:
                raise ValueError("product headway row contains an isolated boundary outlier")
        rows.append(
            ProductHeadwayRowV1(
                sequence=sequence,
                departure=departure,
                service_regime_id=service_id,
                service_headway_minutes=service_headway,
                gap_from_previous_minutes=gap,
                gap_owner_service_regime_id=gap_owner,
                gap_ownership=ownership,
            )
        )
        previous = departure
    return tuple(rows)


def _candidate_lookup(
    allocation_payload: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for candidate_set in allocation_payload["candidate_sets"]:
        direction = str(candidate_set["direction"])
        for key in _CANDIDATE_KEYS:
            candidate = candidate_set[key]
            if candidate is not None:
                result[(direction, str(candidate["candidate_id"]))] = candidate
    return result


def run_clean_boundary_pilot_v1(
    *,
    repo_root: Path,
    route_workbooks: Mapping[str, Path],
    output_directory: Path,
) -> dict[str, Any]:
    fingerprints_before = frozen_upstream_fingerprints_v1(repo_root)
    routes_payload: list[dict[str, Any]] = []
    combined_outlier_count = 0

    for route_id in sorted(route_workbooks, key=int):
        workbook_path = route_workbooks[route_id]
        allocation_path = (
            repo_root
            / "outputs"
            / "demand_regime_trip_allocation"
            / f"route_{route_id}_demand_regime_trip_allocations.json"
        )
        allocation_payload = json.loads(allocation_path.read_text(encoding="utf-8"))
        candidate_lookup = _candidate_lookup(allocation_payload)
        compilations: dict[tuple[str, str], CleanBoundaryCompilationV1] = {}
        runtime_minutes: int | None = None
        fleet_ceiling: int | None = None
        authority_payload: list[dict[str, Any]] = []

        for candidate_set in allocation_payload["candidate_sets"]:
            direction = str(candidate_set["direction"])
            first_candidate = next(
                candidate_set[key] for key in _CANDIDATE_KEYS if candidate_set[key] is not None
            )
            first_regime = first_candidate["regime_allocations"][0]
            last_regime = first_candidate["regime_allocations"][-1]
            authority, route_runtime, route_ceiling = _endpoint_authority(
                workbook_path=workbook_path,
                direction=direction,
                analysis_window_start=int(first_regime["start_time"]),
                analysis_window_end=int(last_regime["end_time"]),
            )
            runtime_minutes = route_runtime
            fleet_ceiling = route_ceiling
            authority_payload.append(asdict(authority))
            for key in _CANDIDATE_KEYS:
                candidate = candidate_set[key]
                if candidate is None:
                    continue
                regimes = tuple(
                    demand_regime_allocation_from_mapping_v1(item)
                    for item in candidate["regime_allocations"]
                )
                compilation = compile_clean_boundary_timetable_v1(
                    route_id=route_id,
                    direction=direction,
                    candidate_id=str(candidate["candidate_id"]),
                    regimes=regimes,
                    endpoint_authority=authority,
                )
                compilations[(direction, compilation.candidate_id)] = compilation
                combined_outlier_count += len(scan_serialized_headway_outliers_v1(compilation))

        if runtime_minutes is None or fleet_ceiling is None:
            raise ValueError(f"route {route_id} authority is incomplete")
        candidate_ids = tuple(_CANDIDATE_ROLE_RANK)
        matrix = tuple(
            validate_fleet_combination_v1(
                route_id=route_id,
                outbound=compilations[("outbound", outbound_id)],
                inbound=compilations[("inbound", inbound_id)],
                outbound_allocation=candidate_lookup[("outbound", outbound_id)],
                inbound_allocation=candidate_lookup[("inbound", inbound_id)],
                runtime_minutes=runtime_minutes,
                minimum_layover_minutes=PILOT_MINIMUM_LAYOVER_MINUTES_V1,
                fleet_ceiling=fleet_ceiling,
            )
            for outbound_id in candidate_ids
            for inbound_id in candidate_ids
        )
        selection = select_final_candidate_pair_v1(route_id, matrix)
        selected_outbound = compilations[("outbound", selection.outbound_candidate_id)]
        selected_inbound = compilations[("inbound", selection.inbound_candidate_id)]
        selected_fleet = build_minimum_fleet_plan_v1(
            route_id=route_id,
            outbound_candidate_id=selection.outbound_candidate_id,
            inbound_candidate_id=selection.inbound_candidate_id,
            outbound_departures=selected_outbound.exact_departures,
            inbound_departures=selected_inbound.exact_departures,
            runtime_minutes=runtime_minutes,
            minimum_layover_minutes=PILOT_MINIMUM_LAYOVER_MINUTES_V1,
        )
        product_rows = {
            "outbound": [asdict(item) for item in build_product_headway_rows_v1(selected_outbound)],
            "inbound": [asdict(item) for item in build_product_headway_rows_v1(selected_inbound)],
        }
        routes_payload.append(
            {
                "route_id": route_id,
                "route_name": allocation_payload["route_name"],
                "canonical_workbook": str(workbook_path.resolve()),
                "canonical_workbook_sha256": _sha256(workbook_path),
                "endpoint_authority": authority_payload,
                "runtime_minutes": runtime_minutes,
                "minimum_layover_minutes": PILOT_MINIMUM_LAYOVER_MINUTES_V1,
                "minimum_layover_authority": "FIXED_RESOURCE_PILOT_AUTHORITY",
                "fleet_ceiling": fleet_ceiling,
                "compilations": [
                    clean_boundary_compilation_to_dict_v1(compilations[key])
                    for key in sorted(compilations)
                ],
                "fleet_matrix": [asdict(item) for item in matrix],
                "final_selection": asdict(selection),
                "selected_fleet_plan": asdict(selected_fleet),
                "selected_product_rows": product_rows,
            }
        )

    fingerprints_after = frozen_upstream_fingerprints_v1(repo_root)
    payload = {
        "review_profile": CLEAN_BOUNDARY_PILOT_PROFILE_V1,
        "output_version": "final_scenario_c_clean_boundaries_v2",
        "compiler_hard_constraints": [
            "FIXED_FIRST_DEPARTURE",
            "FIXED_LAST_DEPARTURE",
            "EXACT_FROZEN_DEMAND_REGIME_COUNTS",
            "WHOLE_MINUTE_UNIFORM_INTERNAL_HEADWAY",
            "BOUNDARY_GAP_EQUALS_LEFT_OR_RIGHT_HEADWAY",
            "CONTINUOUS_EQUAL_HEADWAY_SEGMENTS_MERGED",
        ],
        "final_selection_authority_bridge": FINAL_SELECTION_AUTHORITY_BRIDGE_V1,
        "routes": routes_payload,
        "product_headway_outlier_scan": {
            "status": "PASS" if combined_outlier_count == 0 else "FAIL",
            "outlier_count": combined_outlier_count,
        },
        "frozen_upstream_fingerprints_before": fingerprints_before,
        "frozen_upstream_fingerprints_after": fingerprints_after,
        "frozen_upstream_fingerprints_unchanged": fingerprints_before == fingerprints_after,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    report_path = output_directory / "clean_boundary_pilot_report.json"
    report_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def compact_pilot_summary_v1(payload: Mapping[str, Any]) -> str:
    lines = [
        f"profile={payload['review_profile']}",
        (f"product_headway_outlier_scan={payload['product_headway_outlier_scan']['status']}"),
    ]
    for route in payload["routes"]:
        selection = route["final_selection"]
        lines.append(
            "route="
            f"{route['route_id']} selected="
            f"{selection['outbound_candidate_id']}/{selection['inbound_candidate_id']} "
            f"fleet={selection['fleet_requirement']}/{selection['fleet_ceiling']}"
        )
        for compilation in route["compilations"]:
            authority = compilation["endpoint_authority"]
            lines.append(
                f"  {compilation['direction']} {compilation['candidate_id']} "
                f"{compilation['status']} "
                f"{format_hhmm(authority['fixed_first_departure'])}-"
                f"{format_hhmm(authority['fixed_last_departure'])}"
            )
    return "\n".join(lines)


__all__ = [
    "CLEAN_BOUNDARY_PILOT_PROFILE_V1",
    "FINAL_SELECTION_AUTHORITY_BRIDGE_V1",
    "PILOT_MINIMUM_LAYOVER_MINUTES_V1",
    "FinalCandidateSelectionV1",
    "FleetCombinationValidationV1",
    "FleetPlanV1",
    "FleetTripAssignmentV1",
    "ProductHeadwayRowV1",
    "build_minimum_fleet_plan_v1",
    "build_product_headway_rows_v1",
    "compact_pilot_summary_v1",
    "frozen_upstream_fingerprints_v1",
    "run_clean_boundary_pilot_v1",
    "select_final_candidate_pair_v1",
    "validate_fleet_combination_v1",
]
