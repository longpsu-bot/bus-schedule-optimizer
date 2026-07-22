from __future__ import annotations

import hashlib
import json

from .models import Trip


def timetable_payload(trips: list[Trip]) -> list[dict[str, object]]:
    return [
        {
            "scenario": trip.scenario,
            "trip_id": trip.trip_id,
            "source_b_trip_id": trip.source_b_trip_id,
            "departure_terminal": trip.departure_terminal,
            "direction": trip.direction.value,
            "departure_seconds": trip.departure_seconds,
            "arrival_seconds": trip.arrival_seconds,
            "vehicle_id": trip.vehicle_id,
            "vehicle_capacity_override": trip.vehicle_capacity_override,
            "source_b_departure_seconds": trip.source_b_departure_seconds,
        }
        for trip in trips
    ]


def timetable_fingerprint(trips: list[Trip]) -> str:
    serialized = json.dumps(
        timetable_payload(trips),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()
