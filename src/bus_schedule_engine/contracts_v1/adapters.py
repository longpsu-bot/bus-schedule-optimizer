from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from bus_schedule_engine.importer import ImportedWorkbook, import_workbook
from bus_schedule_engine.models import DemandRecord, Direction, ScenarioParameters, Trip, VolumeType

from .models import (
    ContractDirection,
    DemandConfidence,
    DemandObservation,
    DemandResolutionType,
    DemandResponseMode,
    DemandSourceType,
    DepartureTerminal,
    ExactTimetableTrip,
    InputSourceType,
    NormalizedInputBundleV1,
    ObservedDemandInput,
    OperatingDayType,
    ScenarioAInput,
    ScenarioBInput,
    ScenarioInputV1,
    SourceMetadata,
    TerminalDepartureTimes,
    TerminalOccupancyLimitsV1,
    TripsByDirection,
    TurnaroundMinutes,
    VolumeClassification,
)
from .serialization import observed_demand_fingerprint, scenario_fingerprint
from .validation import ContractValidationError, ensure_valid_bundle


class NormalizationError(ValueError):
    """Raised when a legacy input cannot be normalized without inventing required data."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class NormalizationOptions:
    source_id: str
    imported_at: datetime
    operating_day_type_b: OperatingDayType | None = None
    available_fleet_limit_b: int | None = None
    approved_active_fleet_b: int | None = None
    operating_day_type_a: OperatingDayType | None = None
    available_fleet_limit_a: int | None = None
    approved_active_fleet_a: int | None = None
    terminal_1_max_occupancy_vehicles_b: int | None = None
    terminal_2_max_occupancy_vehicles_b: int | None = None
    source_type: InputSourceType = InputSourceType.XLSX
    source_notes: str | None = None
    demand_dataset_id: str | None = None
    demand_source_type: DemandSourceType = DemandSourceType.AGGREGATE_REPORT
    demand_confidence: DemandConfidence = DemandConfidence.UNKNOWN
    demand_response_mode: DemandResponseMode = DemandResponseMode.STATIC


def _contract_direction(direction: Direction) -> ContractDirection:
    mapping = {
        Direction.TERMINAL_1_TO_2: ContractDirection.OUTBOUND,
        Direction.TERMINAL_2_TO_1: ContractDirection.INBOUND,
        Direction.COMBINED: ContractDirection.COMBINED,
    }
    return mapping[direction]


def _departure_terminal(parameters: ScenarioParameters, terminal: str) -> DepartureTerminal:
    if terminal == parameters.terminal_1_name:
        return DepartureTerminal.TERMINAL_1
    if terminal == parameters.terminal_2_name:
        return DepartureTerminal.TERMINAL_2
    raise NormalizationError(
        f"Unknown departure terminal for route {parameters.route_id}: {terminal}"
    )


def _available_fleet_limit(
    parameters: ScenarioParameters,
    override: int | None,
    scenario_id: str,
) -> int:
    declared = parameters.available_fleet_limit
    value = override if override is not None else declared
    if value is None:
        raise NormalizationError(
            f"Scenario {scenario_id} requires available_fleet_limit; "
            "the legacy workbook does not contain it and the adapter must not infer it"
        )
    return int(value)


def _approved_active_fleet(
    parameters: ScenarioParameters,
    override: int | None,
) -> int | None:
    if override is not None:
        return int(override)
    if parameters.approved_active_fleet is None:
        return None
    return int(parameters.approved_active_fleet)


def _terminal_occupancy_limits(
    parameters: ScenarioParameters,
    terminal_1_override: int | None,
    terminal_2_override: int | None,
) -> TerminalOccupancyLimitsV1 | None:
    terminal_1 = (
        terminal_1_override
        if terminal_1_override is not None
        else parameters.terminal_1_max_occupancy_vehicles
    )
    terminal_2 = (
        terminal_2_override
        if terminal_2_override is not None
        else parameters.terminal_2_max_occupancy_vehicles
    )
    if terminal_1 is None and terminal_2 is None:
        return None
    try:
        return TerminalOccupancyLimitsV1(terminal_1=terminal_1, terminal_2=terminal_2)
    except ValueError as exc:
        raise NormalizationError(f"Invalid Scenario B terminal occupancy limit: {exc}") from exc


def _operating_day_type(
    parameters: ScenarioParameters,
    override: OperatingDayType | None,
    scenario_id: str,
) -> OperatingDayType:
    if override is not None:
        return override
    if parameters.operating_day_type is not None:
        try:
            return OperatingDayType(parameters.operating_day_type)
        except ValueError as exc:
            raise NormalizationError(
                f"Scenario {scenario_id} has invalid operating_day_type: "
                f"{parameters.operating_day_type}"
            ) from exc
    raise NormalizationError(
        f"Scenario {scenario_id} requires explicit operating_day_type; it is not inferred from dates"
    )


def _normalized_trip(parameters: ScenarioParameters, trip: Trip) -> ExactTimetableTrip:
    departure_terminal = _departure_terminal(parameters, trip.departure_terminal)
    direction = _contract_direction(trip.direction)
    if direction == ContractDirection.COMBINED:
        raise NormalizationError(f"Timetable trip {trip.trip_id} cannot use combined direction")
    arrival_time = trip.resolved_arrival_seconds(parameters.default_trip_runtime_minutes)
    runtime_seconds = arrival_time - trip.departure_seconds
    if runtime_seconds <= 0 or runtime_seconds % 60:
        raise NormalizationError(
            f"Trip {trip.trip_id} has a non-positive or non-integer-minute runtime"
        )
    runtime_minutes = runtime_seconds // 60
    if trip.arrival_seconds is not None and not parameters.accepts_trip_runtime(runtime_minutes):
        minimum_runtime = min(parameters.runtime_options)
        maximum_runtime = max(parameters.runtime_options)
        code = "TRIP_RUNTIME_OUTSIDE_ALLOWED_RANGE"
        raise NormalizationError(
            "TRIP_RUNTIME_OUTSIDE_ALLOWED_RANGE: "
            f"Trip {trip.trip_id} has explicit runtime {runtime_minutes} minutes; "
            f"allowed range is {minimum_runtime}-{maximum_runtime} minutes",
            code=code,
        )
    return ExactTimetableTrip(
        trip_id=trip.trip_id,
        direction=direction,
        departure_terminal=departure_terminal,
        departure_time=trip.departure_seconds,
        arrival_time=arrival_time,
        runtime_minutes=runtime_minutes,
        vehicle_assignment=trip.vehicle_id,
    )


def _scenario_input(
    *,
    scenario_id: str,
    parameters: ScenarioParameters,
    trips: list[Trip],
    source_metadata: SourceMetadata,
    operating_day_type: OperatingDayType,
    available_fleet_limit: int,
    approved_active_fleet: int | None,
    terminal_occupancy_limits: TerminalOccupancyLimitsV1 | None,
) -> ScenarioInputV1:
    exact_timetable = tuple(
        sorted(
            (_normalized_trip(parameters, trip) for trip in trips),
            key=lambda item: (item.departure_time, item.direction.value, item.trip_id),
        )
    )
    outbound = sum(item.direction == ContractDirection.OUTBOUND for item in exact_timetable)
    inbound = sum(item.direction == ContractDirection.INBOUND for item in exact_timetable)
    common = dict(
        route_id=parameters.route_id,
        route_name=parameters.route_name,
        route_type=parameters.route_type,
        terminal_1_name=parameters.terminal_1_name,
        terminal_2_name=parameters.terminal_2_name,
        trip_runtime_minutes=parameters.trip_runtime_minutes,
        turnaround_minutes=TurnaroundMinutes(
            terminal_1=parameters.effective_layover_minutes,
            terminal_2=parameters.effective_layover_minutes,
        ),
        total_daily_trips=parameters.total_daily_trips,
        trips_by_direction=TripsByDirection(outbound=outbound, inbound=inbound),
        first_departures=TerminalDepartureTimes(
            terminal_1=parameters.terminal_1_first_departure,
            terminal_2=parameters.terminal_2_first_departure,
        ),
        last_departures=TerminalDepartureTimes(
            terminal_1=parameters.terminal_1_last_departure,
            terminal_2=parameters.terminal_2_last_departure,
        ),
        vehicle_capacity=parameters.capacity,
        approved_active_fleet=approved_active_fleet,
        available_fleet_limit=available_fleet_limit,
        operating_day_type=operating_day_type,
        exact_timetable=exact_timetable,
        source_metadata=source_metadata,
    )
    if scenario_id == "A":
        return ScenarioAInput(**common)
    if scenario_id == "B":
        return ScenarioBInput(
            **common,
            terminal_occupancy_limits=terminal_occupancy_limits,
        )
    raise NormalizationError(f"Unsupported scenario: {scenario_id}")


def _demand_resolution(records: list[DemandRecord]) -> DemandResolutionType:
    durations = {item.block_end_seconds - item.block_start_seconds for item in records}
    if len(durations) == 1 and next(iter(durations)) > 0:
        return DemandResolutionType.REGULAR_INTERVAL
    return DemandResolutionType.IRREGULAR_INTERVAL


def _observed_demand(
    records: list[DemandRecord],
    *,
    source_metadata: SourceMetadata,
    options: NormalizationOptions,
) -> ObservedDemandInput:
    period_keys = {(item.period_start, item.period_end, item.observation_days) for item in records}
    if len(period_keys) != 1:
        raise NormalizationError(
            "Legacy demand rows contain multiple observation periods; split them into separate "
            "datasets before Contract V1 normalization"
        )
    period_start, period_end, observation_days = next(iter(period_keys))
    resolution_type = _demand_resolution(records)
    observations: list[DemandObservation] = []
    for index, record in enumerate(
        sorted(
            records,
            key=lambda item: (
                item.block_start_seconds,
                item.block_end_seconds,
                item.direction.value,
            ),
        ),
        start=1,
    ):
        duration_seconds = record.block_end_seconds - record.block_start_seconds
        resolution_minutes = (
            duration_seconds // 60
            if resolution_type == DemandResolutionType.REGULAR_INTERVAL
            and duration_seconds > 0
            and duration_seconds % 60 == 0
            else None
        )
        observations.append(
            DemandObservation(
                observation_id=f"D-{index:04d}",
                direction=_contract_direction(record.direction),
                interval_start=record.block_start_seconds,
                interval_end=record.block_end_seconds,
                passenger_count=float(record.passenger_volume),
                source_resolution_type=resolution_type,
                source_resolution_minutes=resolution_minutes,
                source_type=options.demand_source_type,
                volume_classification=(
                    VolumeClassification.AVERAGE_DAY
                    if record.volume_type == VolumeType.AVERAGE_DAY
                    else VolumeClassification.TOTAL_OBSERVATION_PERIOD
                ),
                demand_confidence=options.demand_confidence,
                sample_count=None,
            )
        )
    return ObservedDemandInput(
        demand_dataset_id=options.demand_dataset_id or f"{options.source_id}:demand",
        observation_period_start=period_start,
        observation_period_end=period_end,
        observation_days=observation_days,
        observations=tuple(observations),
        source_metadata=source_metadata,
        demand_response_mode=options.demand_response_mode,
    )


def normalize_imported_workbook_v1(
    imported: ImportedWorkbook,
    options: NormalizationOptions,
) -> NormalizedInputBundleV1:
    source_metadata = SourceMetadata(
        source_type=options.source_type,
        source_id=options.source_id,
        imported_at=options.imported_at,
        notes=options.source_notes,
    )
    scenario_a: ScenarioAInput | None = None
    if imported.parameters_a is not None:
        scenario_a = _scenario_input(
            scenario_id="A",
            parameters=imported.parameters_a,
            trips=imported.trips_a,
            source_metadata=source_metadata,
            operating_day_type=_operating_day_type(
                imported.parameters_a,
                options.operating_day_type_a,
                "A",
            ),
            available_fleet_limit=_available_fleet_limit(
                imported.parameters_a,
                options.available_fleet_limit_a,
                "A",
            ),
            approved_active_fleet=_approved_active_fleet(
                imported.parameters_a,
                options.approved_active_fleet_a,
            ),
            terminal_occupancy_limits=None,
        )

    scenario_b = _scenario_input(
        scenario_id="B",
        parameters=imported.parameters_b,
        trips=imported.trips_b,
        source_metadata=source_metadata,
        operating_day_type=_operating_day_type(
            imported.parameters_b,
            options.operating_day_type_b,
            "B",
        ),
        available_fleet_limit=_available_fleet_limit(
            imported.parameters_b,
            options.available_fleet_limit_b,
            "B",
        ),
        approved_active_fleet=_approved_active_fleet(
            imported.parameters_b,
            options.approved_active_fleet_b,
        ),
        terminal_occupancy_limits=_terminal_occupancy_limits(
            imported.parameters_b,
            options.terminal_1_max_occupancy_vehicles_b,
            options.terminal_2_max_occupancy_vehicles_b,
        ),
    )
    observed_demand = (
        _observed_demand(imported.demand, source_metadata=source_metadata, options=options)
        if imported.demand
        else None
    )
    bundle = NormalizedInputBundleV1(
        scenario_a=scenario_a,
        scenario_b=scenario_b,
        observed_demand=observed_demand,
        scenario_a_fingerprint=(scenario_fingerprint(scenario_a) if scenario_a else None),
        scenario_b_fingerprint=scenario_fingerprint(scenario_b),
        observed_demand_fingerprint=(
            observed_demand_fingerprint(observed_demand) if observed_demand else None
        ),
    )
    try:
        ensure_valid_bundle(bundle)
    except ContractValidationError as exc:
        raise NormalizationError(str(exc)) from exc
    return bundle


def import_and_normalize_workbook_v1(
    source: str | Path | bytes | BinaryIO,
    options: NormalizationOptions,
) -> NormalizedInputBundleV1:
    return normalize_imported_workbook_v1(import_workbook(source), options)
