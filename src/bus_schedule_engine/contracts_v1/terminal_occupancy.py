"""Solver-neutral physical terminal occupancy reconstruction for Contract V1."""

from __future__ import annotations

from dataclasses import dataclass

from .models import ContractDirection, DepartureTerminal, ScenarioBInput

TERMINAL_OCCUPANCY_EVENT_ORDER = "ARRIVAL_BEFORE_DEPARTURE"
TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED = "TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED"
TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED = "TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED"
TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED = "TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED"
TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED = "TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED"
TERMINAL_2_OCCUPANCY_CAPACITY_EXCEEDED = "TERMINAL_2_OCCUPANCY_CAPACITY_EXCEEDED"
TERMINAL_1_PHYSICAL_OCCUPANCY_NEGATIVE = "TERMINAL_1_PHYSICAL_OCCUPANCY_NEGATIVE"
TERMINAL_2_PHYSICAL_OCCUPANCY_NEGATIVE = "TERMINAL_2_PHYSICAL_OCCUPANCY_NEGATIVE"


@dataclass(frozen=True, slots=True)
class _TerminalOccupancyEventV1:
    event_time: int
    arrival_trip_ids: tuple[str, ...]
    departure_trip_ids: tuple[str, ...]
    occupancy_before_arrivals: int
    occupancy_after_arrivals: int
    occupancy_after_departures: int


@dataclass(frozen=True, slots=True)
class _TerminalOccupancyProfileV1:
    terminal: DepartureTerminal
    capacity: int | None
    initial_physical_occupancy: int
    events: tuple[_TerminalOccupancyEventV1, ...]
    maximum_occupancy: int
    times_of_maximum_occupancy: tuple[int, ...]
    remaining_capacity_margin: int | None
    limit_binding: bool
    limit_exceeded: bool
    issue_codes: tuple[str, ...]

    @property
    def first_violating_event(self) -> _TerminalOccupancyEventV1 | None:
        if self.capacity is None:
            return None
        return next(
            (
                event
                for event in self.events
                if event.occupancy_before_arrivals > self.capacity
                or event.occupancy_after_arrivals > self.capacity
            ),
            None,
        )


@dataclass(frozen=True, slots=True)
class _TerminalOccupancyAssessmentV1:
    event_order: str
    terminal_1: _TerminalOccupancyProfileV1
    terminal_2: _TerminalOccupancyProfileV1
    issue_codes: tuple[str, ...]
    limitations: tuple[str, ...]


def _terminal_profile(
    scenario: ScenarioBInput,
    terminal: DepartureTerminal,
    *,
    initial_physical_occupancy: int,
    capacity: int | None,
) -> _TerminalOccupancyProfileV1:
    arrivals: dict[int, list[str]] = {}
    departures: dict[int, list[str]] = {}
    arrival_direction = (
        ContractDirection.INBOUND
        if terminal == DepartureTerminal.TERMINAL_1
        else ContractDirection.OUTBOUND
    )
    departure_direction = (
        ContractDirection.OUTBOUND
        if terminal == DepartureTerminal.TERMINAL_1
        else ContractDirection.INBOUND
    )
    for trip in scenario.exact_timetable:
        if trip.direction == arrival_direction:
            arrivals.setdefault(trip.resolved_arrival_time, []).append(trip.trip_id)
        if trip.direction == departure_direction:
            departures.setdefault(trip.departure_time, []).append(trip.trip_id)

    occupancy = initial_physical_occupancy
    maximum = occupancy
    minimum = occupancy
    maximum_times: list[int] = []
    events: list[_TerminalOccupancyEventV1] = []
    for event_time in sorted(set(arrivals) | set(departures)):
        arrival_ids = tuple(sorted(arrivals.get(event_time, ())))
        departure_ids = tuple(sorted(departures.get(event_time, ())))
        before = occupancy
        after_arrivals = before + len(arrival_ids)
        after_departures = after_arrivals - len(departure_ids)
        events.append(
            _TerminalOccupancyEventV1(
                event_time=event_time,
                arrival_trip_ids=arrival_ids,
                departure_trip_ids=departure_ids,
                occupancy_before_arrivals=before,
                occupancy_after_arrivals=after_arrivals,
                occupancy_after_departures=after_departures,
            )
        )
        if after_arrivals > maximum:
            maximum = after_arrivals
            maximum_times = [event_time]
        elif after_arrivals == maximum:
            maximum_times.append(event_time)
        minimum = min(minimum, before, after_arrivals, after_departures)
        occupancy = after_departures

    capacity_issue = (
        TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED
        if terminal == DepartureTerminal.TERMINAL_1
        else TERMINAL_2_OCCUPANCY_CAPACITY_EXCEEDED
    )
    negative_issue = (
        TERMINAL_1_PHYSICAL_OCCUPANCY_NEGATIVE
        if terminal == DepartureTerminal.TERMINAL_1
        else TERMINAL_2_PHYSICAL_OCCUPANCY_NEGATIVE
    )
    exceeded = capacity is not None and maximum > capacity
    issue_codes: list[str] = []
    if exceeded:
        issue_codes.append(capacity_issue)
    if minimum < 0:
        issue_codes.append(negative_issue)
    return _TerminalOccupancyProfileV1(
        terminal=terminal,
        capacity=capacity,
        initial_physical_occupancy=initial_physical_occupancy,
        events=tuple(events),
        maximum_occupancy=maximum,
        times_of_maximum_occupancy=tuple(dict.fromkeys(maximum_times)),
        remaining_capacity_margin=(None if capacity is None else capacity - maximum),
        limit_binding=capacity is not None and maximum == capacity,
        limit_exceeded=exceeded,
        issue_codes=tuple(issue_codes),
    )


def assess_terminal_occupancy_v1(
    scenario: ScenarioBInput,
    *,
    initial_terminal_1: int,
    initial_terminal_2: int,
) -> _TerminalOccupancyAssessmentV1:
    for field_name, value in (
        ("initial_terminal_1", initial_terminal_1),
        ("initial_terminal_2", initial_terminal_2),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{field_name} must be a non-negative integer")

    limits = scenario.terminal_occupancy_limits
    capacity_1 = limits.terminal_1 if limits is not None else None
    capacity_2 = limits.terminal_2 if limits is not None else None
    terminal_1 = _terminal_profile(
        scenario,
        DepartureTerminal.TERMINAL_1,
        initial_physical_occupancy=initial_terminal_1,
        capacity=capacity_1,
    )
    terminal_2 = _terminal_profile(
        scenario,
        DepartureTerminal.TERMINAL_2,
        initial_physical_occupancy=initial_terminal_2,
        capacity=capacity_2,
    )
    if capacity_1 is None and capacity_2 is None:
        limitations = (TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,)
    elif capacity_1 is None:
        limitations = (TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED,)
    elif capacity_2 is None:
        limitations = (TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED,)
    else:
        limitations = ()
    return _TerminalOccupancyAssessmentV1(
        event_order=TERMINAL_OCCUPANCY_EVENT_ORDER,
        terminal_1=terminal_1,
        terminal_2=terminal_2,
        issue_codes=terminal_1.issue_codes + terminal_2.issue_codes,
        limitations=limitations,
    )
