from __future__ import annotations

from dataclasses import replace
from datetime import date

from bus_schedule_engine.fleet import assign_fleet
from bus_schedule_engine.generator import (
    FIXED_RESOURCE_STRATEGY_ID,
    even_departure_times,
    generate_recommendations,
)
from bus_schedule_engine.models import DemandRecord, Direction, Trip, VolumeType


def test_fleet_assignment_has_no_overlapping_vehicle_trips(
    make_parameters, make_valid_trips
) -> None:
    parameters = make_parameters()
    result = assign_fleet(make_valid_trips(parameters), parameters)
    by_vehicle = {}
    for assignment in result.assignments:
        by_vehicle.setdefault(assignment.vehicle_id, []).append(assignment)
    for assignments in by_vehicle.values():
        ordered = sorted(assignments, key=lambda item: item.departure_seconds)
        for previous, current in zip(ordered, ordered[1:], strict=False):
            assert current.departure_seconds >= previous.ready_seconds
            assert current.departure_terminal == previous.arrival_terminal


def test_fleet_fallback_uses_largest_allowed_runtime(make_parameters, make_valid_trips) -> None:
    parameters = make_parameters(
        trip_runtime_minutes=65,
        allowed_trip_runtime_minutes=(55, 65),
    )
    trips = make_valid_trips(parameters)
    trips[0] = replace(trips[0], arrival_seconds=None)

    assignment = next(
        item for item in assign_fleet(trips, parameters).assignments if item.trip_id == "T1"
    )

    assert assignment.arrival_seconds - assignment.departure_seconds == 65 * 60


def test_infeasible_parameters_return_report_not_fake_schedule(make_parameters) -> None:
    parameters = make_parameters(total_daily_trips=2)
    report = generate_recommendations(parameters, [], [])
    assert not report.feasible
    assert report.scenarios == []
    assert report.minimum_required_total_trips == 4


def test_generator_is_deterministic(make_parameters, make_valid_trips) -> None:
    parameters = make_parameters(total_daily_trips=8)
    first = generate_recommendations(parameters, make_valid_trips(parameters), [])
    second = generate_recommendations(parameters, make_valid_trips(parameters), [])
    first_signature = [
        (
            scenario.name,
            [(trip.trip_id, trip.departure_seconds) for trip in scenario.trips],
        )
        for scenario in first.scenarios
    ]
    second_signature = [
        (
            scenario.name,
            [(trip.trip_id, trip.departure_seconds) for trip in scenario.trips],
        )
        for scenario in second.scenarios
    ]
    assert first_signature == second_signature


def test_even_departures_do_not_oscillate() -> None:
    times = even_departure_times(0, 3600, 12)
    assert times == [index * 300 for index in range(12)]


def test_c_preserves_fixed_resources_and_internal_identity(
    make_parameters, make_valid_trips
) -> None:
    parameters = make_parameters()
    trips_b = make_valid_trips(parameters)
    available_fleet = assign_fleet(trips_b, parameters).minimum_vehicles
    report = generate_recommendations(parameters, trips_b, [], available_fleet)
    scenario = report.scenarios[0]
    assert scenario.name == "C"
    assert scenario.strategy_id == FIXED_RESOURCE_STRATEGY_ID
    assert scenario.resource_fleet_limit == available_fleet
    assert len(scenario.trips) == len(trips_b) == parameters.total_daily_trips
    assert scenario.parameters == parameters
    assert scenario.trips is not trips_b
    assert not ({id(trip) for trip in scenario.trips} & {id(trip) for trip in trips_b})
    assert {trip.source_b_trip_id for trip in scenario.trips} == {trip.trip_id for trip in trips_b}
    assert assign_fleet(scenario.trips, scenario.parameters).minimum_vehicles <= available_fleet


def test_c_does_not_reset_headway_at_equal_demand_boundary(make_parameters) -> None:
    parameters = replace(
        make_parameters(),
        total_daily_trips=14,
        terminal_1_last_departure=8 * 3600,
        terminal_2_first_departure=6 * 3600,
        terminal_2_last_departure=8 * 3600,
    )
    definitions = {
        Direction.TERMINAL_1_TO_2: [360, 375, 390, 420, 435, 450, 480],
        Direction.TERMINAL_2_TO_1: [360, 375, 390, 420, 435, 450, 480],
    }
    trips_b = []
    for direction, minute_values in definitions.items():
        terminal = parameters.terminal_for_direction(direction)
        trips_b.extend(
            Trip(
                scenario="B",
                trip_id=f"B-{direction.value}-{index}",
                departure_terminal=terminal,
                direction=direction,
                departure_seconds=minute * 60,
                arrival_seconds=(minute + parameters.trip_runtime_minutes) * 60,
            )
            for index, minute in enumerate(minute_values, 1)
        )
    demand = [
        DemandRecord(
            date(2026, 7, 1),
            date(2026, 7, 1),
            1,
            start_hour * 3600,
            (start_hour + 1) * 3600,
            direction,
            180,
            VolumeType.AVERAGE_DAY,
        )
        for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
        for start_hour in (6, 7)
    ]
    available_fleet = assign_fleet(trips_b, parameters).minimum_vehicles
    report = generate_recommendations(parameters, trips_b, demand, available_fleet)
    c_trips = report.scenarios[0].trips
    for direction in definitions:
        departures = sorted(
            trip.departure_seconds // 60 for trip in c_trips if trip.direction == direction
        )
        gaps = [right - left for left, right in zip(departures, departures[1:], strict=False)]
        assert gaps == [20] * 6
