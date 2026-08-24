"""Canonical trip-count semantics for future demand-regime allocation.

This module is intentionally arithmetic-only.  It does not choose trip counts,
headways, phases, departures, vehicles, or timetable transitions.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from numbers import Real


def _integer_seconds(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an integer number of service-day seconds")
    return value


def contains_departure_v1(
    start_time: int,
    end_time: int,
    departure_time: int,
) -> bool:
    """Return whether a departure belongs to the half-open interval ``[start, end)``.

    A boundary is a demand/service-policy change, not a required departure.  In
    adjacent intervals, a departure at the shared boundary belongs only to the
    later interval.
    """

    start = _integer_seconds(start_time, "start_time")
    end = _integer_seconds(end_time, "end_time")
    departure = _integer_seconds(departure_time, "departure_time")
    if start >= end:
        raise ValueError("start_time must be before end_time")
    return start <= departure < end


def count_departures_in_regime_v1(
    start_time: int,
    end_time: int,
    departure_times: Iterable[int],
) -> int:
    """Count departures in ``[start_time, end_time)`` without endpoint anchoring."""

    return sum(
        contains_departure_v1(start_time, end_time, departure_time)
        for departure_time in departure_times
    )


def nominal_service_headway_minutes_v1(
    regime_duration_minutes: Real,
    trip_count: int,
) -> float | None:
    """Return ``duration / trip_count``, or ``None`` when ``trip_count == 0``.

    This is a service-rate quantity, not the gap between endpoint-anchored
    departure points.  It therefore never uses ``duration / (trip_count - 1)``.
    """

    if isinstance(regime_duration_minutes, bool) or not isinstance(regime_duration_minutes, Real):
        raise ValueError("regime_duration_minutes must be finite and positive")
    duration = float(regime_duration_minutes)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("regime_duration_minutes must be finite and positive")
    if isinstance(trip_count, bool) or not isinstance(trip_count, int) or trip_count < 0:
        raise ValueError("trip_count must be a non-negative integer")
    return None if trip_count == 0 else duration / trip_count


@dataclass(frozen=True, slots=True)
class RegimeTripAllocationV1:
    """Future-facing allocation result for one demand regime.

    ``trip_count`` is the number of departures whose timestamps fall inside the
    associated demand regime's half-open interval ``[regime.start, regime.end)``.
    It does not imply departures at either boundary.
    """

    regime_id: str
    trip_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.regime_id, str) or not self.regime_id.strip():
            raise ValueError("regime_id must be a non-empty string")
        if (
            isinstance(self.trip_count, bool)
            or not isinstance(self.trip_count, int)
            or self.trip_count < 0
        ):
            raise ValueError("trip_count must be a non-negative integer")


__all__ = [
    "RegimeTripAllocationV1",
    "contains_departure_v1",
    "count_departures_in_regime_v1",
    "nominal_service_headway_minutes_v1",
]
