from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from bus_schedule_engine.models import RouteType

from .models import (
    ContractDirection,
    DepartureTerminal,
    NormalizedInputBundleV1,
    ObservedDemandInput,
    ScenarioInputV1,
)


class ContractValidationSeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class ContractValidationIssue:
    code: str
    path: str
    message: str
    severity: ContractValidationSeverity = ContractValidationSeverity.ERROR


@dataclass(frozen=True, slots=True)
class ContractValidationResult:
    issues: tuple[ContractValidationIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(
            issue.severity == ContractValidationSeverity.ERROR for issue in self.issues
        )

    @property
    def error_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues if issue.severity == ContractValidationSeverity.ERROR)


class ContractValidationError(ValueError):
    def __init__(self, issues: tuple[ContractValidationIssue, ...]):
        self.issues = issues
        summary = "; ".join(f"{item.code} ({item.path})" for item in issues)
        super().__init__(summary or "Contract V1 validation failed")


def _issue(code: str, path: str, message: str) -> ContractValidationIssue:
    return ContractValidationIssue(code=code, path=path, message=message)


def _validate_imported_at(imported_at: datetime, path: str) -> list[ContractValidationIssue]:
    if imported_at.tzinfo is None or imported_at.utcoffset() is None:
        return [
            _issue(
                "SOURCE_IMPORTED_AT_NOT_TIMEZONE_AWARE",
                path,
                "imported_at must include a timezone offset",
            )
        ]
    return []


def validate_scenario_input(scenario: ScenarioInputV1) -> ContractValidationResult:
    issues: list[ContractValidationIssue] = []
    prefix = f"scenario_{scenario.scenario_id.value.lower()}"

    if not scenario.route_id.strip():
        issues.append(_issue("EMPTY_ROUTE_ID", f"{prefix}.route_id", "route_id is required"))
    if not scenario.route_name.strip():
        issues.append(_issue("EMPTY_ROUTE_NAME", f"{prefix}.route_name", "route_name is required"))
    if not scenario.terminal_1_name.strip() or not scenario.terminal_2_name.strip():
        issues.append(
            _issue("EMPTY_TERMINAL_NAME", f"{prefix}.terminals", "both terminal names are required")
        )
    elif scenario.terminal_1_name == scenario.terminal_2_name:
        issues.append(
            _issue(
                "DUPLICATE_TERMINAL_NAME",
                f"{prefix}.terminals",
                "terminal_1_name and terminal_2_name must differ",
            )
        )

    if scenario.trip_runtime_minutes <= 0:
        issues.append(
            _issue(
                "INVALID_TRIP_RUNTIME",
                f"{prefix}.trip_runtime_minutes",
                "trip runtime must be positive",
            )
        )
    regulatory_turnaround = 5 if scenario.route_type == RouteType.INTRA_PROVINCIAL else 15
    for terminal_name, value in (
        ("terminal_1", scenario.turnaround_minutes.terminal_1),
        ("terminal_2", scenario.turnaround_minutes.terminal_2),
    ):
        if value < regulatory_turnaround:
            issues.append(
                _issue(
                    "TURNAROUND_BELOW_REGULATORY_MINIMUM",
                    f"{prefix}.turnaround_minutes.{terminal_name}",
                    f"turnaround must be at least {regulatory_turnaround} minutes",
                )
            )

    if scenario.total_daily_trips <= 0:
        issues.append(
            _issue(
                "INVALID_TOTAL_DAILY_TRIPS",
                f"{prefix}.total_daily_trips",
                "total_daily_trips must be positive",
            )
        )
    if scenario.trips_by_direction.outbound <= 0 or scenario.trips_by_direction.inbound <= 0:
        issues.append(
            _issue(
                "INVALID_DIRECTIONAL_TRIP_TOTAL",
                f"{prefix}.trips_by_direction",
                "both directional trip totals must be positive",
            )
        )
    if scenario.trips_by_direction.total != scenario.total_daily_trips:
        issues.append(
            _issue(
                "DIRECTIONAL_TOTAL_MISMATCH",
                f"{prefix}.trips_by_direction",
                "outbound plus inbound trips must equal total_daily_trips",
            )
        )
    if len(scenario.exact_timetable) != scenario.total_daily_trips:
        issues.append(
            _issue(
                "TIMETABLE_TOTAL_MISMATCH",
                f"{prefix}.exact_timetable",
                "exact timetable length must equal total_daily_trips",
            )
        )

    if scenario.vehicle_capacity <= 0:
        issues.append(
            _issue(
                "INVALID_VEHICLE_CAPACITY",
                f"{prefix}.vehicle_capacity",
                "vehicle capacity must be positive",
            )
        )
    if scenario.available_fleet_limit <= 0:
        issues.append(
            _issue(
                "INVALID_AVAILABLE_FLEET_LIMIT",
                f"{prefix}.available_fleet_limit",
                "available fleet limit must be positive",
            )
        )
    if (
        scenario.approved_active_fleet is not None
        and scenario.approved_active_fleet > scenario.available_fleet_limit
    ):
        issues.append(
            _issue(
                "APPROVED_FLEET_EXCEEDS_AVAILABLE_LIMIT",
                f"{prefix}.approved_active_fleet",
                "approved_active_fleet must not exceed available_fleet_limit",
            )
        )

    first_times = (
        scenario.first_departures.terminal_1,
        scenario.first_departures.terminal_2,
    )
    last_times = (
        scenario.last_departures.terminal_1,
        scenario.last_departures.terminal_2,
    )
    for index, (first, last) in enumerate(zip(first_times, last_times, strict=True), start=1):
        if not 0 <= first < 24 * 3600 or not 0 <= last < 24 * 3600:
            issues.append(
                _issue(
                    "TIME_OUTSIDE_SERVICE_DAY",
                    f"{prefix}.terminal_{index}_window",
                    "Contract V1 adapter times must be within one service day",
                )
            )
        elif first > last:
            issues.append(
                _issue(
                    "INVALID_SERVICE_WINDOW",
                    f"{prefix}.terminal_{index}_window",
                    "first departure must not be later than last departure",
                )
            )

    trip_ids = Counter(item.trip_id for item in scenario.exact_timetable)
    duplicates = sorted(trip_id for trip_id, count in trip_ids.items() if count > 1)
    if duplicates:
        issues.append(
            _issue(
                "DUPLICATE_TRIP_ID",
                f"{prefix}.exact_timetable",
                f"duplicate trip IDs: {', '.join(duplicates)}",
            )
        )

    by_terminal: dict[DepartureTerminal, list[int]] = defaultdict(list)
    direction_counts = Counter(item.direction for item in scenario.exact_timetable)
    for index, trip in enumerate(scenario.exact_timetable):
        path = f"{prefix}.exact_timetable[{index}]"
        expected_terminal = (
            DepartureTerminal.TERMINAL_1
            if trip.direction == ContractDirection.OUTBOUND
            else DepartureTerminal.TERMINAL_2
        )
        if trip.direction == ContractDirection.COMBINED:
            issues.append(
                _issue(
                    "COMBINED_TIMETABLE_DIRECTION",
                    f"{path}.direction",
                    "combined is valid only for demand, not timetable trips",
                )
            )
        elif trip.departure_terminal != expected_terminal:
            issues.append(
                _issue(
                    "DIRECTION_TERMINAL_MISMATCH",
                    f"{path}.departure_terminal",
                    "trip direction does not match departure terminal",
                )
            )
        if not trip.trip_id.strip():
            issues.append(_issue("EMPTY_TRIP_ID", f"{path}.trip_id", "trip_id is required"))
        if trip.runtime_minutes <= 0:
            issues.append(
                _issue(
                    "INVALID_TRIP_RUNTIME",
                    f"{path}.runtime_minutes",
                    "trip runtime must be positive",
                )
            )
        if trip.arrival_time is not None:
            expected_arrival = trip.departure_time + trip.runtime_minutes * 60
            if trip.arrival_time != expected_arrival:
                issues.append(
                    _issue(
                        "ARRIVAL_RUNTIME_MISMATCH",
                        f"{path}.arrival_time",
                        "arrival_time must equal departure_time plus runtime_minutes",
                    )
                )
        by_terminal[trip.departure_terminal].append(trip.departure_time)

    if direction_counts[ContractDirection.OUTBOUND] != scenario.trips_by_direction.outbound:
        issues.append(
            _issue(
                "OUTBOUND_TOTAL_MISMATCH",
                f"{prefix}.trips_by_direction.outbound",
                "declared outbound total does not match exact timetable",
            )
        )
    if direction_counts[ContractDirection.INBOUND] != scenario.trips_by_direction.inbound:
        issues.append(
            _issue(
                "INBOUND_TOTAL_MISMATCH",
                f"{prefix}.trips_by_direction.inbound",
                "declared inbound total does not match exact timetable",
            )
        )

    for terminal, expected_first, expected_last in (
        (
            DepartureTerminal.TERMINAL_1,
            scenario.first_departures.terminal_1,
            scenario.last_departures.terminal_1,
        ),
        (
            DepartureTerminal.TERMINAL_2,
            scenario.first_departures.terminal_2,
            scenario.last_departures.terminal_2,
        ),
    ):
        departures = by_terminal.get(terminal, [])
        path = f"{prefix}.{terminal.value}"
        if not departures:
            issues.append(_issue("NO_TERMINAL_DEPARTURES", path, "terminal has no departures"))
            continue
        if min(departures) != expected_first:
            issues.append(
                _issue(
                    "FIRST_DEPARTURE_MISMATCH",
                    path,
                    "first exact departure does not match declared first departure",
                )
            )
        if max(departures) != expected_last:
            issues.append(
                _issue(
                    "LAST_DEPARTURE_MISMATCH",
                    path,
                    "last exact departure does not match declared last departure",
                )
            )
        if any(not expected_first <= value <= expected_last for value in departures):
            issues.append(
                _issue(
                    "DEPARTURE_OUTSIDE_WINDOW",
                    path,
                    "one or more departures are outside the declared terminal window",
                )
            )

    issues.extend(
        _validate_imported_at(scenario.source_metadata.imported_at, f"{prefix}.source_metadata.imported_at")
    )
    if not scenario.source_metadata.source_id.strip():
        issues.append(
            _issue(
                "EMPTY_SOURCE_ID",
                f"{prefix}.source_metadata.source_id",
                "source_id is required",
            )
        )
    return ContractValidationResult(tuple(issues))


def validate_observed_demand(demand: ObservedDemandInput) -> ContractValidationResult:
    issues: list[ContractValidationIssue] = []
    prefix = "observed_demand"
    if not demand.demand_dataset_id.strip():
        issues.append(
            _issue(
                "EMPTY_DEMAND_DATASET_ID",
                f"{prefix}.demand_dataset_id",
                "demand_dataset_id is required",
            )
        )
    if demand.observation_period_start > demand.observation_period_end:
        issues.append(
            _issue(
                "INVALID_OBSERVATION_PERIOD",
                f"{prefix}.observation_period",
                "observation period start must not be after end",
            )
        )
    if demand.observation_days <= 0:
        issues.append(
            _issue(
                "INVALID_OBSERVATION_DAYS",
                f"{prefix}.observation_days",
                "observation_days must be positive",
            )
        )
    if not demand.observations:
        issues.append(
            _issue(
                "EMPTY_DEMAND_OBSERVATIONS",
                f"{prefix}.observations",
                "at least one demand observation is required",
            )
        )

    ids = Counter(item.observation_id for item in demand.observations)
    duplicates = sorted(item_id for item_id, count in ids.items() if count > 1)
    if duplicates:
        issues.append(
            _issue(
                "DUPLICATE_OBSERVATION_ID",
                f"{prefix}.observations",
                f"duplicate observation IDs: {', '.join(duplicates)}",
            )
        )

    for index, observation in enumerate(demand.observations):
        path = f"{prefix}.observations[{index}]"
        if not observation.observation_id.strip():
            issues.append(
                _issue("EMPTY_OBSERVATION_ID", f"{path}.observation_id", "observation_id is required")
            )
        if observation.passenger_count < 0:
            issues.append(
                _issue(
                    "NEGATIVE_PASSENGER_COUNT",
                    f"{path}.passenger_count",
                    "passenger_count must be non-negative",
                )
            )
        if not 0 <= observation.interval_start < 24 * 3600:
            issues.append(
                _issue(
                    "INVALID_INTERVAL_START",
                    f"{path}.interval_start",
                    "interval_start must be within the service day",
                )
            )
        if not 0 <= observation.interval_end < 24 * 3600:
            issues.append(
                _issue(
                    "INVALID_INTERVAL_END",
                    f"{path}.interval_end",
                    "interval_end must be within the service day",
                )
            )
        if observation.interval_start >= observation.interval_end:
            issues.append(
                _issue(
                    "INVALID_DEMAND_INTERVAL",
                    path,
                    "interval_start must be before interval_end",
                )
            )
        duration_seconds = observation.interval_end - observation.interval_start
        if observation.source_resolution_minutes is not None:
            if observation.source_resolution_minutes <= 0:
                issues.append(
                    _issue(
                        "INVALID_SOURCE_RESOLUTION",
                        f"{path}.source_resolution_minutes",
                        "source resolution must be positive",
                    )
                )
            elif (
                observation.source_resolution_type.value == "regular_interval"
                and duration_seconds == observation.source_resolution_minutes * 60
            ):
                pass
            elif observation.source_resolution_type.value == "regular_interval":
                issues.append(
                    _issue(
                        "RESOLUTION_DURATION_MISMATCH",
                        f"{path}.source_resolution_minutes",
                        "regular interval duration must match source_resolution_minutes",
                    )
                )
        if observation.sample_count is not None and observation.sample_count < 0:
            issues.append(
                _issue(
                    "INVALID_SAMPLE_COUNT",
                    f"{path}.sample_count",
                    "sample_count must be non-negative",
                )
            )

    issues.extend(
        _validate_imported_at(demand.source_metadata.imported_at, f"{prefix}.source_metadata.imported_at")
    )
    return ContractValidationResult(tuple(issues))


def validate_normalized_bundle(bundle: NormalizedInputBundleV1) -> ContractValidationResult:
    issues: list[ContractValidationIssue] = []
    if bundle.scenario_a is not None:
        issues.extend(validate_scenario_input(bundle.scenario_a).issues)
    issues.extend(validate_scenario_input(bundle.scenario_b).issues)
    if bundle.observed_demand is not None:
        issues.extend(validate_observed_demand(bundle.observed_demand).issues)
        if bundle.scenario_a is None:
            issues.append(
                _issue(
                    "DEMAND_WITHOUT_SCENARIO_A",
                    "observed_demand",
                    "observed demand is associated with Scenario A, but Scenario A is absent",
                )
            )
    if bundle.scenario_a is not None:
        if bundle.scenario_a.route_id != bundle.scenario_b.route_id:
            issues.append(
                _issue(
                    "A_B_ROUTE_ID_MISMATCH",
                    "scenario_a.route_id",
                    "Scenario A and B must describe the same route",
                )
            )
        if (
            bundle.scenario_a.terminal_1_name != bundle.scenario_b.terminal_1_name
            or bundle.scenario_a.terminal_2_name != bundle.scenario_b.terminal_2_name
        ):
            issues.append(
                _issue(
                    "A_B_TERMINAL_MISMATCH",
                    "scenario_a.terminals",
                    "Scenario A and B terminal identities must match",
                )
            )
    return ContractValidationResult(tuple(issues))


def ensure_valid_bundle(bundle: NormalizedInputBundleV1) -> None:
    result = validate_normalized_bundle(bundle)
    if not result.passed:
        raise ContractValidationError(
            tuple(
                issue
                for issue in result.issues
                if issue.severity == ContractValidationSeverity.ERROR
            )
        )
