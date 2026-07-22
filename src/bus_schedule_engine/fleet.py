from __future__ import annotations

from dataclasses import dataclass

from .models import FleetResult, FleetTripAssignment, ScenarioParameters, Trip


@dataclass
class _VehicleState:
    vehicle_id: str
    location: str
    ready_seconds: int
    first_departure_seconds: int
    last_ready_seconds: int
    travel_seconds: int = 0
    waiting_seconds: int = 0
    trips: int = 0


def assign_fleet(trips: list[Trip], parameters: ScenarioParameters) -> FleetResult:
    """Assign the minimum practical fleet deterministically by terminal availability."""
    states: list[_VehicleState] = []
    assignments: list[FleetTripAssignment] = []
    layover_seconds = parameters.effective_layover_minutes * 60
    ordered = sorted(trips, key=lambda item: (item.departure_seconds, item.trip_id))
    for trip in ordered:
        arrival = trip.resolved_arrival_seconds(parameters.default_trip_runtime_minutes)
        arrival_terminal = parameters.opposite_terminal(trip.departure_terminal)
        candidates = [
            state
            for state in states
            if state.location == trip.departure_terminal
            and state.ready_seconds <= trip.departure_seconds
        ]
        if candidates:
            state = sorted(candidates, key=lambda item: (-item.ready_seconds, item.vehicle_id))[0]
            waiting_seconds = trip.departure_seconds - state.ready_seconds
        else:
            vehicle_id = f"XE-{len(states) + 1:03d}"
            state = _VehicleState(
                vehicle_id=vehicle_id,
                location=trip.departure_terminal,
                ready_seconds=trip.departure_seconds,
                first_departure_seconds=trip.departure_seconds,
                last_ready_seconds=trip.departure_seconds,
            )
            states.append(state)
            waiting_seconds = 0
        ready = arrival + layover_seconds
        state.location = arrival_terminal
        state.ready_seconds = ready
        state.last_ready_seconds = ready
        state.travel_seconds += arrival - trip.departure_seconds
        state.waiting_seconds += waiting_seconds
        state.trips += 1
        assignments.append(
            FleetTripAssignment(
                vehicle_id=state.vehicle_id,
                trip_id=trip.trip_id,
                direction=trip.direction,
                departure_terminal=trip.departure_terminal,
                arrival_terminal=arrival_terminal,
                departure_seconds=trip.departure_seconds,
                arrival_seconds=arrival,
                ready_seconds=ready,
                waiting_minutes=waiting_seconds / 60,
            )
        )
    summaries = [
        {
            "vehicle_id": state.vehicle_id,
            "trips": state.trips,
            "active_minutes": (state.last_ready_seconds - state.first_departure_seconds) / 60,
            "travel_minutes": state.travel_seconds / 60,
            "waiting_minutes": state.waiting_seconds / 60,
            "final_terminal": state.location,
        }
        for state in sorted(states, key=lambda item: item.vehicle_id)
    ]
    return FleetResult(len(states), assignments, summaries)
