from __future__ import annotations

from dataclasses import dataclass

from .models import DepartureTerminal, ExactTimetableTrip, TurnaroundMinutes
from .solver_models import FleetAssignmentV1, RawCandidateTripV1


class ContractFleetAssignmentError(ValueError):
    """Raised when exact Contract V1 fleet chronology cannot be derived."""


@dataclass(frozen=True, slots=True)
class ContractFleetAssignmentResultV1:
    assignments: tuple[FleetAssignmentV1, ...]
    available_fleet_limit: int
    vehicle_count: int
    initial_fleet_terminal_1: int
    initial_fleet_terminal_2: int
    feasible: bool


@dataclass(slots=True)
class _VehicleState:
    vehicle_id: str
    location: DepartureTerminal
    ready_time: int


def _arrival_terminal(departure_terminal: DepartureTerminal) -> DepartureTerminal:
    if departure_terminal == DepartureTerminal.TERMINAL_1:
        return DepartureTerminal.TERMINAL_2
    return DepartureTerminal.TERMINAL_1


def _turnaround_at(
    terminal: DepartureTerminal,
    turnaround_minutes: TurnaroundMinutes,
) -> int:
    if terminal == DepartureTerminal.TERMINAL_1:
        return turnaround_minutes.terminal_1
    return turnaround_minutes.terminal_2


def assign_contract_v1_fleet(
    candidate_trips: tuple[RawCandidateTripV1, ...],
    source_b_trips: tuple[ExactTimetableTrip, ...],
    turnaround_minutes: TurnaroundMinutes,
    available_fleet_limit: int,
) -> ContractFleetAssignmentResultV1:
    """Assign vehicles using exact source runtimes and arrival-terminal turnaround."""
    if available_fleet_limit <= 0:
        raise ContractFleetAssignmentError("available_fleet_limit must be positive")
    source_by_id = {trip.trip_id: trip for trip in source_b_trips}
    if len(source_by_id) != len(source_b_trips):
        raise ContractFleetAssignmentError("Source B contains duplicate trip IDs")

    states: list[_VehicleState] = []
    assignments: list[FleetAssignmentV1] = []
    initial_terminal_1 = 0
    initial_terminal_2 = 0
    for trip in sorted(
        candidate_trips,
        key=lambda item: (item.c_departure_time, item.c_trip_id),
    ):
        source = source_by_id.get(trip.source_b_trip_id)
        if source is None:
            raise ContractFleetAssignmentError(
                f"Candidate trip {trip.c_trip_id} has unknown source B trip"
            )
        eligible = [
            state
            for state in states
            if state.location == trip.departure_terminal
            and state.ready_time <= trip.c_departure_time
        ]
        if eligible:
            state = min(
                eligible,
                key=lambda item: (-item.ready_time, item.vehicle_id),
            )
        else:
            state = _VehicleState(
                vehicle_id=f"XE-{len(states) + 1:03d}",
                location=trip.departure_terminal,
                ready_time=trip.c_departure_time,
            )
            states.append(state)
            if trip.departure_terminal == DepartureTerminal.TERMINAL_1:
                initial_terminal_1 += 1
            else:
                initial_terminal_2 += 1

        arrival_terminal = _arrival_terminal(trip.departure_terminal)
        arrival_time = trip.c_departure_time + source.runtime_minutes * 60
        ready_time = (
            arrival_time
            + _turnaround_at(
                arrival_terminal,
                turnaround_minutes,
            )
            * 60
        )
        state.location = arrival_terminal
        state.ready_time = ready_time
        assignments.append(
            FleetAssignmentV1(
                vehicle_id=state.vehicle_id,
                c_trip_id=trip.c_trip_id,
                departure_terminal=trip.departure_terminal,
                arrival_terminal=arrival_terminal,
                departure_time=trip.c_departure_time,
                arrival_time=arrival_time,
                ready_time=ready_time,
            )
        )

    return ContractFleetAssignmentResultV1(
        assignments=tuple(assignments),
        available_fleet_limit=available_fleet_limit,
        vehicle_count=len(states),
        initial_fleet_terminal_1=initial_terminal_1,
        initial_fleet_terminal_2=initial_terminal_2,
        feasible=len(states) <= available_fleet_limit,
    )
