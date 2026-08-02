from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import date

from bus_schedule_engine.c_generator import _balanced_times
from bus_schedule_engine.demand import evaluate_scenario
from bus_schedule_engine.fingerprint import timetable_fingerprint
from bus_schedule_engine.fleet import assign_fleet
from bus_schedule_engine.generator import generate_recommendations
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    HeadwayType,
    RouteType,
    ScenarioCStatus,
    ScenarioParameters,
    Trip,
    VolumeType,
)
from bus_schedule_engine.validator import validate_schedule


def _fixture(
    *, combined: bool = False, minor_noise: bool = False
) -> tuple[ScenarioParameters, list[Trip], list[DemandRecord], int]:
    parameters = ScenarioParameters(
        route_id="REG-01",
        route_name="Tuyến kiểm tra regime",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=30,
        total_daily_trips=26,
        terminal_1_name="Bến Đông",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=12 * 3600,
        terminal_2_name="Bến Tây",
        terminal_2_first_departure=6 * 3600 + 15 * 60,
        terminal_2_last_departure=12 * 3600 + 15 * 60,
        vehicle_capacity_passengers=60,
        target_load_factor=0.85,
        maximum_load_factor=0.90,
        time_block_minutes=60,
        minimum_layover_minutes=5,
    )
    trips: list[Trip] = []
    for direction, offset in (
        (Direction.TERMINAL_1_TO_2, 0),
        (Direction.TERMINAL_2_TO_1, 15),
    ):
        for index in range(13):
            departure = (360 + offset + index * 30) * 60
            trips.append(
                Trip(
                    scenario="B",
                    trip_id=f"B-{direction.value}-{index + 1:02d}",
                    departure_terminal=parameters.terminal_for_direction(direction),
                    direction=direction,
                    departure_seconds=departure,
                    arrival_seconds=departure + parameters.trip_runtime_minutes * 60,
                )
            )
    volumes = [90, 90, 90, 99 if minor_noise else 90, 90, 90]
    if not minor_noise:
        volumes = [150, 150, 30, 30, 150, 150]
    demand: list[DemandRecord] = []
    demand_directions = (
        (Direction.COMBINED,)
        if combined
        else (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    )
    for direction in demand_directions:
        for index, volume in enumerate(volumes):
            demand.append(
                DemandRecord(
                    period_start=date(2026, 7, 1),
                    period_end=date(2026, 7, 7),
                    observation_days=1,
                    block_start_seconds=(6 + index) * 3600,
                    block_end_seconds=(7 + index) * 3600,
                    direction=direction,
                    passenger_volume=volume * (2 if combined else 1),
                    volume_type=VolumeType.AVERAGE_DAY,
                )
            )
    active_fleet = assign_fleet(trips, parameters).minimum_vehicles
    return parameters, trips, demand, active_fleet


def test_balanced_rounding_generates_stable_integer_headways() -> None:
    five_minute = _balanced_times(6 * 3600, 6 * 3600 + 55 * 60, 12)
    assert [
        (right - left) // 60 for left, right in zip(five_minute, five_minute[1:], strict=False)
    ] == [5] * 11
    seven_point_five = _balanced_times(7 * 3600, 7 * 3600 + 30 * 60, 5)
    assert [
        (right - left) // 60
        for left, right in zip(seven_point_five, seven_point_five[1:], strict=False)
    ] == [7, 8, 7, 8]


def test_c_is_independent_traceable_and_preserves_all_resource_locks() -> None:
    parameters, trips_b, demand, active_fleet = _fixture()
    baseline_payload = tuple(trips_b)
    baseline_hash = timetable_fingerprint(trips_b)
    report = generate_recommendations(parameters, trips_b, demand, active_fleet)
    scenario = report.scenarios[0]
    assert scenario.name == "C"
    assert tuple(trips_b) == baseline_payload
    assert timetable_fingerprint(trips_b) == baseline_hash
    assert scenario.trips is not trips_b
    assert not ({id(trip) for trip in scenario.trips} & {id(trip) for trip in trips_b})
    assert scenario.parameters == parameters and scenario.parameters is not parameters
    assert len(scenario.trips) == len(trips_b)
    assert Counter(trip.direction for trip in scenario.trips) == Counter(
        trip.direction for trip in trips_b
    )
    assert {trip.source_b_trip_id for trip in scenario.trips} == {trip.trip_id for trip in trips_b}
    assert len({trip.source_b_trip_id for trip in scenario.trips}) == len(trips_b)
    # Current heuristic compatibility: it still echoes B's inferred active-fleet value.
    # Contract V1 instead defaults to an available upper bound and solver-determined split.
    assert scenario.active_vehicle_count == active_fleet
    assert assign_fleet(scenario.trips, parameters).minimum_vehicles <= active_fleet
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        b_times = sorted(trip.departure_seconds for trip in trips_b if trip.direction == direction)
        c_times = sorted(
            trip.departure_seconds for trip in scenario.trips if trip.direction == direction
        )
        assert (c_times[0], c_times[-1]) == (b_times[0], b_times[-1])


def test_c_inherits_each_source_b_trip_runtime_from_inclusive_range() -> None:
    parameters, trips_b, demand, _ = _fixture()
    parameters = replace(
        parameters,
        trip_runtime_minutes=30,
        allowed_trip_runtime_minutes=(25, 30),
    )
    trips_b = [
        replace(
            trip,
            arrival_seconds=trip.departure_seconds + (25 if index % 2 else 30) * 60,
        )
        for index, trip in enumerate(trips_b)
    ]
    active_fleet = assign_fleet(trips_b, parameters).minimum_vehicles

    scenario = generate_recommendations(parameters, trips_b, demand, active_fleet).scenarios[0]
    source_runtime_seconds = {
        trip.trip_id: trip.arrival_seconds - trip.departure_seconds for trip in trips_b
    }

    assert {(trip.arrival_seconds - trip.departure_seconds) // 60 for trip in scenario.trips} == {
        25,
        30,
    }
    assert all(
        trip.arrival_seconds - trip.departure_seconds
        == source_runtime_seconds[trip.source_b_trip_id]
        for trip in scenario.trips
    )


def test_sustained_demand_creates_few_variable_regimes_and_coordinated_respacing() -> None:
    parameters, trips_b, demand, active_fleet = _fixture()
    scenario = generate_recommendations(parameters, trips_b, demand, active_fleet).scenarios[0]
    assert scenario.generation_status == ScenarioCStatus.REGULAR_STILL_UNDERSUPPLIED
    assert scenario.regularity and scenario.regularity.gate_passed
    assert scenario.regularity.number_of_exceptional_headways == 0
    assert all(
        regime.maximum_headway_minutes - regime.minimum_headway_minutes <= 1
        for regime in scenario.headway_regimes
    )
    assert all(
        sum(regime.direction == direction for regime in scenario.headway_regimes) <= 6
        for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    )
    assert any(regime.start_seconds % 3600 != 0 for regime in scenario.headway_regimes[1:])
    shifted = [trace for trace in scenario.trip_traces if trace.shift_minutes != 0]
    assert len(shifted) >= 3
    assert any(
        left.retained_or_shifted == right.retained_or_shifted == "DỊCH CHUYỂN"
        for left, right in zip(shifted, shifted[1:], strict=False)
    )
    assert all(
        trace.change_reason
        for trace in scenario.trip_traces
        if trace.retained_or_shifted == "DỊCH CHUYỂN"
    )
    b_evaluation = evaluate_scenario(
        "B", trips_b, demand, parameters, validate_schedule(trips_b, parameters)
    )
    c_evaluation = evaluate_scenario(
        "C",
        scenario.trips,
        demand,
        parameters,
        validate_schedule(scenario.trips, parameters),
    )
    assert c_evaluation.blocks_over_maximum < b_evaluation.blocks_over_maximum
    assert all(block.trips > 0 for block in c_evaluation.blocks if block.demand > 0)
    assert dict(scenario.optimization_log.rejection_reason_counts)["FLEET_LIMIT"] > 0


def test_minor_one_block_noise_does_not_create_a_frequency_regime() -> None:
    parameters, trips_b, demand, active_fleet = _fixture(minor_noise=True)
    scenario = generate_recommendations(parameters, trips_b, demand, active_fleet).scenarios[0]
    assert all(
        sum(regime.direction == direction for regime in scenario.headway_regimes) == 1
        for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    )


def test_combined_demand_never_reallocates_trips_between_directions() -> None:
    parameters, trips_b, demand, active_fleet = _fixture(combined=True)
    scenario = generate_recommendations(parameters, trips_b, demand, active_fleet).scenarios[0]
    assert Counter(trip.direction for trip in scenario.trips) == Counter(
        trip.direction for trip in trips_b
    )


def test_regularity_gate_classifies_transition_and_rejects_unexplained_exceptions() -> None:
    parameters, trips_b, demand, active_fleet = _fixture()
    scenario = generate_recommendations(parameters, trips_b, demand, active_fleet).scenarios[0]
    assert any(trace.headway_type == HeadwayType.TRANSITION for trace in scenario.trip_traces)
    assert all(
        trace.exception_reason
        for trace in scenario.trip_traces
        if trace.headway_type == HeadwayType.EXCEPTIONAL
    )
    assert scenario.regularity and scenario.regularity.number_of_exceptional_headways == 0


def test_final_service_regime_can_be_longer_but_remains_balanced_and_locked() -> None:
    parameters, trips_b, demand, active_fleet = _fixture()
    final_low_profile = [150, 150, 150, 150, 30, 30] * 2
    demand = [
        replace(record, passenger_volume=volume)
        for record, volume in zip(demand, final_low_profile, strict=True)
    ]
    scenario = generate_recommendations(parameters, trips_b, demand, active_fleet).scenarios[0]
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        regimes = [regime for regime in scenario.headway_regimes if regime.direction == direction]
        assert regimes[-1].target_headway_minutes > regimes[-2].target_headway_minutes
        assert regimes[-1].maximum_headway_minutes - regimes[-1].minimum_headway_minutes <= 1
        b_last = max(trip.departure_seconds for trip in trips_b if trip.direction == direction)
        c_last = max(
            trip.departure_seconds for trip in scenario.trips if trip.direction == direction
        )
        assert c_last == b_last


def test_repeated_runs_are_deterministic() -> None:
    parameters, trips_b, demand, active_fleet = _fixture()
    first = generate_recommendations(parameters, trips_b, demand, active_fleet).scenarios[0]
    second = generate_recommendations(parameters, trips_b, demand, active_fleet).scenarios[0]
    assert first.timetable_fingerprint == second.timetable_fingerprint
    assert [trip.departure_seconds for trip in first.trips] == [
        trip.departure_seconds for trip in second.trips
    ]
    assert first.headway_regimes == second.headway_regimes
    assert first.optimization_log == second.optimization_log
