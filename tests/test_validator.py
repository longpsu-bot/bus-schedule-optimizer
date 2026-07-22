from __future__ import annotations

from dataclasses import replace

from bus_schedule_engine.models import Direction, Trip
from bus_schedule_engine.validator import validate_schedule


def test_layover_violation_blocks_schedule(make_parameters) -> None:
    parameters = make_parameters(
        total_daily_trips=2,
        terminal_1_last_departure=6 * 3600,
        terminal_2_first_departure=6 * 3600 + 30 * 60,
        terminal_2_last_departure=6 * 3600 + 30 * 60,
    )
    trips = [
        Trip(
            "B",
            "T1",
            "Bến 1",
            Direction.TERMINAL_1_TO_2,
            6 * 3600,
            6 * 3600 + 30 * 60,
            "XE-01",
        ),
        Trip(
            "B",
            "T2",
            "Bến 2",
            Direction.TERMINAL_2_TO_1,
            6 * 3600 + 30 * 60,
            7 * 3600,
            "XE-01",
        ),
    ]
    report = validate_schedule(trips, parameters)
    assert not report.passed
    assert "LAYOVER_VIOLATION" in {issue.code for issue in report.issues}


def test_declared_trip_total_must_match_timetable(make_parameters, make_valid_trips) -> None:
    parameters = make_parameters(total_daily_trips=5)
    report = validate_schedule(make_valid_trips(parameters), parameters)
    assert "TRIP_COUNT_MISMATCH" in {issue.code for issue in report.issues}


def test_trip_outside_service_window_is_blocked(make_parameters, make_valid_trips) -> None:
    parameters = make_parameters(total_daily_trips=5)
    trips = make_valid_trips(parameters)
    trips.append(
        Trip(
            "B",
            "EARLY",
            parameters.terminal_1_name,
            Direction.TERMINAL_1_TO_2,
            parameters.terminal_1_first_departure - 10 * 60,
            parameters.terminal_1_first_departure + 20 * 60,
        )
    )
    report = validate_schedule(trips, parameters)
    assert "OUTSIDE_SERVICE_WINDOW" in {issue.code for issue in report.issues}


def test_final_trip_too_early_creates_warning(make_parameters, make_valid_trips) -> None:
    parameters = make_parameters()
    trips = make_valid_trips(parameters)
    trips[2] = replace(
        trips[2], departure_seconds=6 * 3600 + 45 * 60, arrival_seconds=7 * 3600 + 15 * 60
    )
    report = validate_schedule(trips, parameters)
    assert "FINAL_TRIP_TOO_EARLY" in {issue.code for issue in report.issues}


def test_missing_capacity_is_blocking(make_parameters, make_valid_trips) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=None)
    report = validate_schedule(make_valid_trips(parameters), parameters)
    assert not report.passed
    assert "MISSING_VEHICLE_CAPACITY" in {issue.code for issue in report.issues}


def test_runtime_range_accepts_every_integer_between_inclusive_bounds(
    make_parameters, make_valid_trips
) -> None:
    parameters = make_parameters(
        trip_runtime_minutes=65,
        allowed_trip_runtime_minutes=(55, 65),
    )
    trips = make_valid_trips(parameters)
    runtimes = (55, 65, 59, 61)
    trips = [
        replace(trip, arrival_seconds=trip.departure_seconds + runtime * 60)
        for trip, runtime in zip(trips, runtimes, strict=True)
    ]

    report = validate_schedule(trips, parameters)
    invalid_runtime_ids = {
        issue.trip_ids[0] for issue in report.issues if issue.code == "INVALID_TRIP_RUNTIME"
    }

    assert invalid_runtime_ids == set()


def test_runtime_range_rejects_values_outside_inclusive_bounds(
    make_parameters, make_valid_trips
) -> None:
    parameters = make_parameters(
        trip_runtime_minutes=65,
        allowed_trip_runtime_minutes=(55, 65),
    )
    trips = make_valid_trips(parameters)
    runtimes = (55, 65, 54, 66)
    trips = [
        replace(trip, arrival_seconds=trip.departure_seconds + runtime * 60)
        for trip, runtime in zip(trips, runtimes, strict=True)
    ]

    report = validate_schedule(trips, parameters)
    invalid_runtime_issues = [
        issue for issue in report.issues if issue.code == "INVALID_TRIP_RUNTIME"
    ]

    assert {issue.trip_ids[0] for issue in invalid_runtime_issues} == {"T3", "T4"}
    assert all("55–65" in issue.message for issue in invalid_runtime_issues)


def test_missing_arrival_uses_largest_allowed_runtime(make_parameters, make_valid_trips) -> None:
    parameters = make_parameters(
        trip_runtime_minutes=65,
        allowed_trip_runtime_minutes=(55, 65),
    )
    trips = make_valid_trips(parameters)
    trips[0] = replace(trips[0], arrival_seconds=None)

    report = validate_schedule(trips, parameters)

    assert not any(issue.code == "INVALID_TRIP_RUNTIME" for issue in report.issues)
