from __future__ import annotations

import json
from pathlib import Path

from bus_schedule_engine.contracts_v1.fixed_timetable_fleet_inputs import (
    load_compiled_scenario_c_direction_v1,
    load_operational_authorities_v1,
    load_scenario_b_trips_v1,
    verify_operational_input_hashes_v1,
)
from bus_schedule_engine.contracts_v1.fixed_timetable_fleet_serialization import (
    fixed_timetable_fleet_result_to_contract_dict_v1,
)
from bus_schedule_engine.contracts_v1.fixed_timetable_fleet_validator import (
    FixedOperationalTripV1,
    FleetValidationStatusV1,
    build_compatibility_dag_v1,
    validate_fixed_timetable_fleet_v1,
)

_ROOT = Path(__file__).parents[1]
_OPERATIONAL_ROOT = _ROOT / "private_inputs" / "operational"
_OPERATIONAL_PATH = _OPERATIONAL_ROOT / "operational_inputs_mst_6_10_v1.json"
_SCENARIO_B_PATH = _OPERATIONAL_ROOT / "scenario_b_exact_departures_mst_6_10_v1.json"
_COMPILER_ROOT = _ROOT / "artifacts" / "uniform_headway_compiler_v1"


def _trip(
    trip_id: str,
    direction: str,
    departure: int,
    runtime: int = 10,
) -> FixedOperationalTripV1:
    if direction == "terminal_1_to_2":
        origin, destination = "T1", "T2"
    else:
        origin, destination = "T2", "T1"
    return FixedOperationalTripV1(
        trip_id=trip_id,
        route_id="TEST",
        direction=direction,
        origin_terminal=origin,
        destination_terminal=destination,
        departure_minute=departure,
        runtime_minutes=runtime,
        arrival_minute=departure + runtime,
    )


def _validate(
    *trips: FixedOperationalTripV1,
    limit: int = 99,
):
    return validate_fixed_timetable_fleet_v1(
        tuple(trips),
        minimum_layover_minutes=5,
        pilot_fleet_limit=limit,
        terminal_1_name="T1",
        terminal_2_name="T2",
    )


def test_simple_alternating_chain_requires_one_vehicle() -> None:
    result = _validate(
        _trip("T12-001", "terminal_1_to_2", 0),
        _trip("T21-001", "terminal_2_to_1", 15),
    )
    assert result.minimum_fleet_required == 1
    assert result.matching == (("T12-001", "T21-001"),)
    assert result.layover_metrics.minimum_actual_layover_minutes == 5


def test_four_minute_layover_connection_is_rejected() -> None:
    first = _trip("T12-001", "terminal_1_to_2", 0)
    second = _trip("T21-001", "terminal_2_to_1", 14)
    assert build_compatibility_dag_v1((first, second), 5)[first.trip_id] == ()
    assert _validate(first, second).minimum_fleet_required == 2


def test_multiple_simultaneous_departures_require_multiple_vehicles() -> None:
    result = _validate(
        _trip("T12-001", "terminal_1_to_2", 0),
        _trip("T12-002", "terminal_1_to_2", 0),
    )
    assert result.minimum_fleet_required == 2


def test_exact_minimum_path_cover_fleet_count() -> None:
    result = _validate(
        _trip("T12-001", "terminal_1_to_2", 0),
        _trip("T12-002", "terminal_1_to_2", 2),
        _trip("T21-001", "terminal_2_to_1", 15),
        _trip("T21-002", "terminal_2_to_1", 17),
        _trip("T12-003", "terminal_1_to_2", 30),
        _trip("T12-004", "terminal_1_to_2", 32),
    )
    assert len(result.matching) == 4
    assert result.minimum_fleet_required == 6 - 4 == 2


def test_canonical_matching_is_lexicographic_after_wait_objectives() -> None:
    result = _validate(
        _trip("A-T12", "terminal_1_to_2", 0),
        _trip("B-T12", "terminal_1_to_2", 0),
        _trip("C-T21", "terminal_2_to_1", 15),
        _trip("D-T21", "terminal_2_to_1", 15),
    )
    assert result.matching == (("A-T12", "C-T21"), ("B-T12", "D-T21"))


def test_no_same_direction_chain_without_deadhead() -> None:
    first = _trip("T12-001", "terminal_1_to_2", 0)
    second = _trip("T12-002", "terminal_1_to_2", 20)
    assert build_compatibility_dag_v1((first, second), 5) == {
        "T12-001": (),
        "T12-002": (),
    }


def test_trip_completeness_every_trip_exactly_once() -> None:
    trips = (
        _trip("T12-001", "terminal_1_to_2", 0),
        _trip("T21-001", "terminal_2_to_1", 15),
        _trip("T12-002", "terminal_1_to_2", 30),
    )
    result = _validate(*trips)
    flattened = [item.trip.trip_id for block in result.blocks for item in block.trips]
    assert len(flattened) == len(set(flattened)) == len(trips)
    assert set(flattened) == {trip.trip_id for trip in trips}


def test_initial_and_final_terminal_vehicle_counts() -> None:
    result = _validate(
        _trip("A-T12", "terminal_1_to_2", 0),
        _trip("B-T12", "terminal_1_to_2", 0),
        _trip("C-T21", "terminal_2_to_1", 15),
        _trip("D-T21", "terminal_2_to_1", 15),
    )
    assert (result.initial_fleet_terminal_1, result.initial_fleet_terminal_2) == (2, 0)
    assert (result.ending_fleet_terminal_1, result.ending_fleet_terminal_2) == (2, 0)


def test_scenario_b_json_ingestion_uses_operational_runtime() -> None:
    hashes = verify_operational_input_hashes_v1(_OPERATIONAL_PATH, _SCENARIO_B_PATH)
    authorities = load_operational_authorities_v1(_OPERATIONAL_PATH)
    trips, source = load_scenario_b_trips_v1(_SCENARIO_B_PATH, authorities["6"])
    assert hashes["scenario_b_exact_departures"] == source.source_file_sha256
    assert len(trips) == 156
    assert {trip.runtime_minutes for trip in trips} == {70}
    assert all(trip.arrival_minute == trip.departure_minute + 70 for trip in trips)


def test_compiler_c_artifact_ingestion_preserves_exact_departures() -> None:
    authority = load_operational_authorities_v1(_OPERATIONAL_PATH)["10"]
    path = _COMPILER_ROOT / "route-10-outbound-c3-balanced.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    trips, source = load_compiled_scenario_c_direction_v1(path, authority)
    assert source.candidate_id == "C3_BALANCED"
    assert [trip.departure_minute for trip in trips] == [
        row["departure_minute"] for row in raw["exact_departures"]
    ]
    assert {trip.runtime_minutes for trip in trips} == {80}


def test_pilot_fleet_limit_status_uses_pilot_wording() -> None:
    result = _validate(_trip("T12-001", "terminal_1_to_2", 0), limit=0)
    assert result.fleet_status == FleetValidationStatusV1.FEASIBLE_BUT_EXCEEDS_PILOT_FLEET_LIMIT
    assert result.fleet_margin == -1
    assert result.approved_active_fleet is None


def test_one_hundred_run_byte_identical_determinism() -> None:
    trips = (
        _trip("A-T12", "terminal_1_to_2", 0),
        _trip("B-T12", "terminal_1_to_2", 0),
        _trip("C-T21", "terminal_2_to_1", 15),
        _trip("D-T21", "terminal_2_to_1", 15),
    )
    serializations = set()
    for _ in range(100):
        result = _validate(*trips)
        payload = fixed_timetable_fleet_result_to_contract_dict_v1(
            result,
            scenario="C",
            outbound_candidate="C_TEST",
            inbound_candidate="C_TEST",
            sources=(),
            operational_input_sha256="0" * 64,
            minimum_layover_minutes=5,
        )
        serializations.add(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        )
    assert len(serializations) == 1
