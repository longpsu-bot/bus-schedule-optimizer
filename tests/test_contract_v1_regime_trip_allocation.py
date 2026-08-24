from __future__ import annotations

import pytest

from bus_schedule_engine.contracts_v1.regime_trip_allocation import (
    RegimeTripAllocationV1,
    contains_departure_v1,
    count_departures_in_regime_v1,
    nominal_service_headway_minutes_v1,
)


def _minutes(hour: int, minute: int) -> int:
    return (hour * 60 + minute) * 60


def test_half_open_interval_start_is_inclusive_and_interior_is_inside() -> None:
    start = _minutes(7, 0)
    end = _minutes(10, 0)

    assert contains_departure_v1(start, end, start)
    assert contains_departure_v1(start, end, _minutes(8, 22))


def test_half_open_interval_end_is_exclusive() -> None:
    assert not contains_departure_v1(_minutes(7, 0), _minutes(10, 0), _minutes(10, 0))


def test_adjacent_intervals_assign_shared_boundary_exactly_once() -> None:
    boundary = _minutes(10, 0)
    memberships = (
        contains_departure_v1(_minutes(7, 0), boundary, boundary),
        contains_departure_v1(boundary, _minutes(13, 0), boundary),
    )

    assert memberships == (False, True)
    assert sum(memberships) == 1


def test_trip_count_does_not_require_either_boundary_departure() -> None:
    departures = tuple(
        _minutes(hour, minute)
        for hour, minute in (
            (7, 9),
            (7, 27),
            (7, 45),
            (8, 3),
            (8, 21),
            (8, 39),
            (8, 57),
            (9, 15),
            (9, 33),
            (9, 51),
        )
    )

    assert (
        count_departures_in_regime_v1(
            _minutes(7, 0),
            _minutes(10, 0),
            departures,
        )
        == 10
    )
    assert _minutes(7, 0) not in departures
    assert _minutes(10, 0) not in departures


def test_nominal_headway_uses_duration_divided_by_trip_count() -> None:
    assert nominal_service_headway_minutes_v1(180, 10) == 18.0
    assert nominal_service_headway_minutes_v1(180, 10) != 180 / (10 - 1)


def test_zero_trip_count_has_no_nominal_headway() -> None:
    assert nominal_service_headway_minutes_v1(180, 0) is None
    assert RegimeTripAllocationV1(regime_id="R-01", trip_count=0).trip_count == 0


@pytest.mark.parametrize("trip_count", [-1, 1.5, True])
def test_allocation_rejects_invalid_trip_counts(trip_count: object) -> None:
    with pytest.raises(ValueError, match="trip_count"):
        RegimeTripAllocationV1(regime_id="R-01", trip_count=trip_count)  # type: ignore[arg-type]
