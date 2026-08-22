"""Strict adapters for fixed-timetable fleet-validator V1 authorities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .fixed_timetable_fleet_validator import FixedOperationalTripV1

OPERATIONAL_INPUT_SHA256_V1 = "69eb92b7c13f3c6e4861a3898709bfdc8f857b151723113ab31525a3129de6c3"
SCENARIO_B_EXACT_DEPARTURES_SHA256_V1 = (
    "ac6291dbdef6d8afc30788b584541d56bac96f8a3563a3ae415e01685ca1a340"
)


@dataclass(frozen=True, slots=True)
class OperationalRouteAuthorityV1:
    route_id: str
    terminal_1_name: str
    terminal_2_name: str
    terminal_1_to_2_runtime_minutes: int
    terminal_2_to_1_runtime_minutes: int
    minimum_layover_minutes: int
    pilot_fleet_limit: int
    approved_active_fleet: None
    terminal_1_capacity: None
    terminal_2_capacity: None


@dataclass(frozen=True, slots=True)
class ScheduleSourceV1:
    scenario: str
    route_id: str
    direction: str | None
    candidate_id: str
    compiler_status: str
    source_path: str
    source_file_sha256: str
    upstream_fingerprints: dict[str, str]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_operational_input_hashes_v1(
    operational_input_path: Path,
    scenario_b_path: Path,
) -> dict[str, str]:
    actual = {
        "operational_inputs": file_sha256(operational_input_path),
        "scenario_b_exact_departures": file_sha256(scenario_b_path),
    }
    expected = {
        "operational_inputs": OPERATIONAL_INPUT_SHA256_V1,
        "scenario_b_exact_departures": SCENARIO_B_EXACT_DEPARTURES_SHA256_V1,
    }
    mismatches = {
        name: {"expected": expected[name], "actual": value}
        for name, value in actual.items()
        if value != expected[name]
    }
    if mismatches:
        raise ValueError(f"operational input SHA-256 mismatch: {mismatches}")
    return actual


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_operational_authorities_v1(
    operational_input_path: Path,
) -> dict[str, OperationalRouteAuthorityV1]:
    payload = _load_json(operational_input_path)
    if payload.get("schema_version") != "operational_inputs_mst_6_10_v1":
        raise ValueError("unexpected operational-input schema version")
    routes = payload.get("routes")
    if not isinstance(routes, dict) or set(routes) != {"6", "10"}:
        raise ValueError("operational inputs must contain exactly routes 6 and 10")
    result: dict[str, OperationalRouteAuthorityV1] = {}
    for route_id, value in routes.items():
        if not isinstance(value, dict):
            raise ValueError(f"route {route_id} operational authority must be an object")
        runtime = value["runtime"]
        turnaround = value["turnaround"]
        fleet = value["fleet"]
        terminals = value["terminals"]
        if not all(isinstance(item, dict) for item in (runtime, turnaround, fleet, terminals)):
            raise ValueError(f"route {route_id} operational authority has invalid sections")
        terminal_1 = terminals["terminal_1"]
        terminal_2 = terminals["terminal_2"]
        if fleet.get("approved_active_fleet") is not None:
            raise ValueError("approved_active_fleet must remain unknown/null")
        if (
            terminal_1.get("max_occupancy_vehicles") is not None
            or terminal_2.get("max_occupancy_vehicles") is not None
        ):
            raise ValueError("terminal capacity authority is unexpectedly populated")
        result[route_id] = OperationalRouteAuthorityV1(
            route_id=route_id,
            terminal_1_name=str(terminal_1["name"]),
            terminal_2_name=str(terminal_2["name"]),
            terminal_1_to_2_runtime_minutes=int(runtime["terminal_1_to_2_minutes"]),
            terminal_2_to_1_runtime_minutes=int(runtime["terminal_2_to_1_minutes"]),
            minimum_layover_minutes=int(turnaround["minimum_layover_minutes"]),
            pilot_fleet_limit=int(fleet["available_fleet_limit"]),
            approved_active_fleet=None,
            terminal_1_capacity=None,
            terminal_2_capacity=None,
        )
    return result


def parse_hhmm_v1(value: str) -> int:
    pieces = value.split(":")
    if len(pieces) != 2:
        raise ValueError(f"invalid HH:MM value: {value!r}")
    hour, minute = (int(piece) for piece in pieces)
    if hour < 0 or minute not in range(60):
        raise ValueError(f"invalid HH:MM value: {value!r}")
    return hour * 60 + minute


def load_scenario_b_trips_v1(
    scenario_b_path: Path,
    authority: OperationalRouteAuthorityV1,
) -> tuple[tuple[FixedOperationalTripV1, ...], ScheduleSourceV1]:
    payload = _load_json(scenario_b_path)
    if payload.get("schema_version") != "scenario_b_exact_departures_mst_6_10_v1":
        raise ValueError("unexpected Scenario B departure schema version")
    route = payload["routes"][authority.route_id]
    runtime_assertion = int(route["runtime_minutes"])
    if runtime_assertion not in {
        authority.terminal_1_to_2_runtime_minutes,
        authority.terminal_2_to_1_runtime_minutes,
    }:
        raise ValueError("Scenario B runtime assertion contradicts operational authority")
    trips: list[FixedOperationalTripV1] = []
    for direction, origin, destination, runtime in (
        (
            "terminal_1_to_2",
            authority.terminal_1_name,
            authority.terminal_2_name,
            authority.terminal_1_to_2_runtime_minutes,
        ),
        (
            "terminal_2_to_1",
            authority.terminal_2_name,
            authority.terminal_1_name,
            authority.terminal_2_to_1_runtime_minutes,
        ),
    ):
        rows = route[direction]
        for row in rows:
            if row["direction"] != direction or row["departure_terminal"] != origin:
                raise ValueError("Scenario B direction/terminal identity mismatch")
            departure = parse_hhmm_v1(row["departure_time"])
            arrival = departure + runtime
            if "arrival_time" in row and parse_hhmm_v1(row["arrival_time"]) != arrival:
                raise ValueError("Scenario B arrival contradicts authoritative runtime")
            trips.append(
                FixedOperationalTripV1(
                    trip_id=str(row["trip_id"]),
                    route_id=authority.route_id,
                    direction=direction,
                    origin_terminal=origin,
                    destination_terminal=destination,
                    departure_minute=departure,
                    runtime_minutes=runtime,
                    arrival_minute=arrival,
                )
            )
    source_hash = file_sha256(scenario_b_path)
    return tuple(trips), ScheduleSourceV1(
        scenario="B",
        route_id=authority.route_id,
        direction=None,
        candidate_id="SCENARIO_B",
        compiler_status="SCENARIO_B_OPERATIONAL_BASELINE",
        source_path=scenario_b_path.as_posix(),
        source_file_sha256=source_hash,
        upstream_fingerprints={"scenario_b_exact_departures_sha256": source_hash},
    )


def load_compiled_scenario_c_direction_v1(
    compiled_artifact_path: Path,
    authority: OperationalRouteAuthorityV1,
) -> tuple[tuple[FixedOperationalTripV1, ...], ScheduleSourceV1]:
    payload = _load_json(compiled_artifact_path)
    route_id = str(payload.get("route_id"))
    if route_id != authority.route_id:
        raise ValueError("compiled schedule route does not match operational authority")
    if payload.get("status") != "COMPILED":
        raise ValueError("Scenario C source schedule is not COMPILED")
    if payload.get("fleet_validation_status") != "NOT_FLEET_VALIDATED":
        raise ValueError("Scenario C source has unexpected upstream fleet status")
    direction = str(payload.get("direction"))
    candidate_id = str(payload.get("source_allocation_candidate_id"))
    if direction == "OUTBOUND":
        contract_direction = "terminal_1_to_2"
        origin = authority.terminal_1_name
        destination = authority.terminal_2_name
        runtime = authority.terminal_1_to_2_runtime_minutes
        trip_prefix = "T12"
    elif direction == "INBOUND":
        contract_direction = "terminal_2_to_1"
        origin = authority.terminal_2_name
        destination = authority.terminal_1_name
        runtime = authority.terminal_2_to_1_runtime_minutes
        trip_prefix = "T21"
    else:
        raise ValueError("compiled schedule direction must be OUTBOUND or INBOUND")
    departures = payload.get("exact_departures")
    if not isinstance(departures, list) or len(departures) != payload.get("total_trip_count"):
        raise ValueError("compiled exact departures do not reproduce total_trip_count")
    trips = tuple(
        FixedOperationalTripV1(
            trip_id=f"C-{trip_prefix}-{candidate_id}-{int(row['trip_sequence']):03d}",
            route_id=route_id,
            direction=contract_direction,
            origin_terminal=origin,
            destination_terminal=destination,
            departure_minute=int(row["departure_minute"]),
            runtime_minutes=runtime,
            arrival_minute=int(row["departure_minute"]) + runtime,
        )
        for row in departures
    )
    source_hash = file_sha256(compiled_artifact_path)
    upstream = {
        name: str(payload[name])
        for name in (
            "compiled_schedule_fingerprint",
            "source_compiler_input_fingerprint",
        )
    }
    assertions = payload.get("upstream_fingerprint_assertions", {})
    if isinstance(assertions, dict):
        for name in ("demand_regime", "trip_allocation"):
            if assertions.get(name) is not None:
                upstream[f"asserted_{name}_fingerprint"] = str(assertions[name])
    return trips, ScheduleSourceV1(
        scenario="C",
        route_id=route_id,
        direction=direction,
        candidate_id=candidate_id,
        compiler_status=str(payload["status"]),
        source_path=compiled_artifact_path.as_posix(),
        source_file_sha256=source_hash,
        upstream_fingerprints=upstream,
    )


__all__ = [
    "OPERATIONAL_INPUT_SHA256_V1",
    "SCENARIO_B_EXACT_DEPARTURES_SHA256_V1",
    "OperationalRouteAuthorityV1",
    "ScheduleSourceV1",
    "file_sha256",
    "load_compiled_scenario_c_direction_v1",
    "load_operational_authorities_v1",
    "load_scenario_b_trips_v1",
    "parse_hhmm_v1",
    "verify_operational_input_hashes_v1",
]
