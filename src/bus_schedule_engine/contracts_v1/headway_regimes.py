from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..c_generator import _balanced_values, _material_boundaries, _regime_drafts
from .models import ExactTimetableTrip


class ContinuousHeadwayPolicyV1(Protocol):
    minimum_sustained_change_intervals: int
    minimum_material_headway_change_minutes: int
    minimum_material_service_rate_change_ratio: float
    maximum_headway_regimes_per_direction: int


@dataclass(frozen=True, slots=True)
class ContinuousHeadwayRegimeV1:
    start_index: int
    end_index: int
    ordered_trip_ids: tuple[str, ...]
    first_departure: int
    last_departure: int
    actual_headway_sequence: tuple[float, ...]
    balanced_departure_sequence: tuple[int, ...]
    balanced_headway_sequence: tuple[float, ...]


def _balanced_departures(start: int, end: int, trip_count: int) -> tuple[int, ...]:
    if trip_count <= 0:
        return ()
    if trip_count == 1:
        return (start,)
    interval_count = trip_count - 1
    duration = end - start
    if start % 60 == 0 and end % 60 == 0:
        gaps = tuple(value * 60 for value in _balanced_values(duration // 60, interval_count))
    else:
        gaps = tuple(_balanced_values(duration, interval_count))
    output = [start]
    for gap in gaps:
        output.append(output[-1] + gap)
    output[-1] = end
    return tuple(output)


def segment_continuous_headway_regimes_v1(
    ordered_trips: tuple[ExactTimetableTrip, ...],
    policy: ContinuousHeadwayPolicyV1,
) -> tuple[ContinuousHeadwayRegimeV1, ...]:
    """Segment actual directional headways using the generator's pure V1 authority."""
    if not ordered_trips:
        return ()
    times = [trip.departure_time for trip in ordered_trips]
    boundaries = [index for index, _ in _material_boundaries(times, policy)]
    drafts, _ = _regime_drafts(times, boundaries)
    output: list[ContinuousHeadwayRegimeV1] = []
    for draft in drafts:
        members = ordered_trips[draft.start_index : draft.end_index + 1]
        balanced_departures = _balanced_departures(
            times[draft.start_index],
            times[draft.end_index],
            len(members),
        )
        balanced_headways = tuple(
            (right - left) / 60
            for left, right in zip(
                balanced_departures,
                balanced_departures[1:],
                strict=False,
            )
        )
        output.append(
            ContinuousHeadwayRegimeV1(
                start_index=draft.start_index,
                end_index=draft.end_index,
                ordered_trip_ids=tuple(trip.trip_id for trip in members),
                first_departure=times[draft.start_index],
                last_departure=times[draft.end_index],
                actual_headway_sequence=draft.actual_headways,
                balanced_departure_sequence=balanced_departures,
                balanced_headway_sequence=balanced_headways,
            )
        )
    return tuple(output)


__all__ = [
    "ContinuousHeadwayPolicyV1",
    "ContinuousHeadwayRegimeV1",
    "segment_continuous_headway_regimes_v1",
]
