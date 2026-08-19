from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from bus_schedule_engine.models import RouteType

CONTRACT_VERSION = "1.0.0"
B_ANCHORED_TWO_STAGE_REBALANCE_V1 = "B_ANCHORED_TWO_STAGE_REBALANCE_V1"
COMBINED_DEMAND_FIXED_DIRECTION_COUNTS = "COMBINED_DEMAND_FIXED_DIRECTION_COUNTS"
DIRECTIONAL_DEMAND_FIXED_DIRECTION_COUNTS = "DIRECTIONAL_DEMAND_FIXED_DIRECTION_COUNTS"


class ScenarioCOptimizationModeV1(StrEnum):
    """Demand provenance mode used before building a solver problem."""

    LEGACY_A_BOUND = "LEGACY_A_BOUND"
    B_ANCHORED_TWO_STAGE_REBALANCE = B_ANCHORED_TWO_STAGE_REBALANCE_V1


class DemandAllocationAuthorityModeV1(StrEnum):
    DIRECTIONAL_FIXED_DIRECTION_COUNTS = DIRECTIONAL_DEMAND_FIXED_DIRECTION_COUNTS
    COMBINED_FIXED_DIRECTION_COUNTS = COMBINED_DEMAND_FIXED_DIRECTION_COUNTS


class ScenarioId(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class ContractDirection(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"
    COMBINED = "combined"


class DepartureTerminal(StrEnum):
    TERMINAL_1 = "terminal_1"
    TERMINAL_2 = "terminal_2"


class OperatingDayType(StrEnum):
    WEEKDAY = "weekday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"
    HOLIDAY = "holiday"
    SPECIAL = "special"
    ALL_DAYS = "all_days"


class InputSourceType(StrEnum):
    XLSX = "xlsx"
    UI = "ui"
    API = "api"
    MANUAL = "manual"
    OTHER = "other"


class DemandResponseMode(StrEnum):
    STATIC = "static"
    ELASTICITY_SCENARIO = "elasticity_scenario"
    CALIBRATED = "calibrated"


class DemandResolutionType(StrEnum):
    REGULAR_INTERVAL = "regular_interval"
    TIMESTAMP = "timestamp"
    TRIP = "trip"
    IRREGULAR_INTERVAL = "irregular_interval"
    DAILY_TOTAL = "daily_total"


class DemandSourceType(StrEnum):
    TICKETING = "ticketing"
    MANUAL_COUNT = "manual_count"
    APC = "apc"
    SURVEY = "survey"
    AGGREGATE_REPORT = "aggregate_report"
    OTHER = "other"


class VolumeClassification(StrEnum):
    TOTAL_OBSERVATION_PERIOD = "total_observation_period"
    AVERAGE_DAY = "average_day"


class DemandConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    source_type: InputSourceType
    source_id: str
    imported_at: datetime
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class TurnaroundMinutes:
    terminal_1: int
    terminal_2: int


@dataclass(frozen=True, slots=True)
class TripsByDirection:
    outbound: int
    inbound: int

    @property
    def total(self) -> int:
        return self.outbound + self.inbound


@dataclass(frozen=True, slots=True)
class TerminalDepartureTimes:
    terminal_1: int
    terminal_2: int


@dataclass(frozen=True, slots=True)
class ExactTimetableTrip:
    trip_id: str
    direction: ContractDirection
    departure_terminal: DepartureTerminal
    departure_time: int
    runtime_minutes: int
    arrival_time: int | None = None
    vehicle_assignment: str | None = None

    @property
    def resolved_arrival_time(self) -> int:
        if self.arrival_time is not None:
            return self.arrival_time
        return self.departure_time + self.runtime_minutes * 60


@dataclass(frozen=True, slots=True)
class ScenarioInputV1:
    route_id: str
    route_name: str
    route_type: RouteType
    terminal_1_name: str
    terminal_2_name: str
    trip_runtime_minutes: int
    turnaround_minutes: TurnaroundMinutes
    total_daily_trips: int
    trips_by_direction: TripsByDirection
    first_departures: TerminalDepartureTimes
    last_departures: TerminalDepartureTimes
    vehicle_capacity: int
    available_fleet_limit: int
    operating_day_type: OperatingDayType
    exact_timetable: tuple[ExactTimetableTrip, ...]
    source_metadata: SourceMetadata
    approved_active_fleet: int | None = None

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    @property
    def scenario_id(self) -> ScenarioId:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class ScenarioAInput(ScenarioInputV1):
    @property
    def scenario_id(self) -> ScenarioId:
        return ScenarioId.A


@dataclass(frozen=True, slots=True)
class TerminalOccupancyLimitsV1:
    terminal_1: int | None = None
    terminal_2: int | None = None

    def __post_init__(self) -> None:
        if self.terminal_1 is None and self.terminal_2 is None:
            raise ValueError("at least one terminal occupancy limit must be supplied")
        for field_name, value in (
            ("terminal_1", self.terminal_1),
            ("terminal_2", self.terminal_2),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 1
            ):
                raise ValueError(f"{field_name} occupancy limit must be an integer >= 1")


@dataclass(frozen=True, slots=True)
class ScenarioBInput(ScenarioInputV1):
    terminal_occupancy_limits: TerminalOccupancyLimitsV1 | None = None

    @property
    def scenario_id(self) -> ScenarioId:
        return ScenarioId.B


@dataclass(frozen=True, slots=True)
class DemandObservation:
    observation_id: str
    direction: ContractDirection
    interval_start: int
    interval_end: int
    passenger_count: float
    source_resolution_type: DemandResolutionType
    source_type: DemandSourceType
    volume_classification: VolumeClassification
    demand_confidence: DemandConfidence
    source_resolution_minutes: int | None = None
    sample_count: int | None = None
    notes: str | None = None

    def average_daily_passenger_count(self, observation_days: int) -> float:
        if self.volume_classification == VolumeClassification.AVERAGE_DAY:
            return float(self.passenger_count)
        if observation_days <= 0:
            raise ValueError("observation_days must be positive")
        return float(self.passenger_count) / observation_days


@dataclass(frozen=True, slots=True)
class ObservedDemandInput:
    demand_dataset_id: str
    observation_period_start: date
    observation_period_end: date
    observation_days: int
    observations: tuple[DemandObservation, ...]
    source_metadata: SourceMetadata
    demand_response_mode: DemandResponseMode = DemandResponseMode.STATIC

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    @property
    def scenario_observed_under(self) -> ScenarioId:
        return ScenarioId.A


@dataclass(frozen=True, slots=True)
class NormalizedInputBundleV1:
    scenario_a: ScenarioAInput | None
    scenario_b: ScenarioBInput
    observed_demand: ObservedDemandInput | None
    scenario_a_fingerprint: str | None
    scenario_b_fingerprint: str
    observed_demand_fingerprint: str | None
    optimization_mode: ScenarioCOptimizationModeV1 = ScenarioCOptimizationModeV1.LEGACY_A_BOUND
