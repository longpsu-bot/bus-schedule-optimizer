from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from enum import Enum
from typing import Any

from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    ScenarioParameters,
    Trip,
)

from .models import (
    ContractDirection,
    DepartureTerminal,
    NormalizedInputBundleV1,
    ScenarioBInput,
)
from .serialization import canonical_sha256
from .solver_models import ScheduleProblemV1

HEURISTIC_CONTEXT_FINGERPRINT_PROFILE = "contract_v1_h4_heuristic_context"
HEURISTIC_TURNAROUND_BRIDGE_MODE = "conservative_max_terminal_turnaround"


class HeuristicCompatibilityContextError(ValueError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class HeuristicCompatibilityContextV1:
    legacy_parameters: ScenarioParameters
    legacy_trips_b: tuple[Trip, ...]
    legacy_demand: tuple[DemandRecord, ...]
    heuristic_config: ScenarioCConfig
    turnaround_bridge_mode: str
    turnaround_bridge_value_minutes: int
    source_b_fingerprint: str
    observed_demand_fingerprint: str | None
    context_fingerprint: str
    protected_service_floor_enforcement_fingerprint: str | None = None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def contract_direction(direction: Direction) -> ContractDirection:
    if direction == Direction.TERMINAL_1_TO_2:
        return ContractDirection.OUTBOUND
    if direction == Direction.TERMINAL_2_TO_1:
        return ContractDirection.INBOUND
    return ContractDirection.COMBINED


def legacy_direction(direction: ContractDirection) -> Direction:
    if direction == ContractDirection.OUTBOUND:
        return Direction.TERMINAL_1_TO_2
    if direction == ContractDirection.INBOUND:
        return Direction.TERMINAL_2_TO_1
    raise HeuristicCompatibilityContextError(
        "Timetable candidates cannot use combined direction",
        code="HEURISTIC_CONTEXT_SOURCE_MISMATCH",
    )


def departure_terminal(direction: ContractDirection) -> DepartureTerminal:
    if direction == ContractDirection.OUTBOUND:
        return DepartureTerminal.TERMINAL_1
    if direction == ContractDirection.INBOUND:
        return DepartureTerminal.TERMINAL_2
    raise HeuristicCompatibilityContextError(
        "Timetable candidates cannot use combined direction",
        code="HEURISTIC_CONTEXT_SOURCE_MISMATCH",
    )


def _validate_legacy_parameters(
    scenario_b: ScenarioBInput,
    legacy: ScenarioParameters,
) -> None:
    comparisons = {
        "route_id": (legacy.route_id, scenario_b.route_id),
        "route_name": (legacy.route_name, scenario_b.route_name),
        "route_type": (legacy.route_type, scenario_b.route_type),
        "terminal_1_name": (legacy.terminal_1_name, scenario_b.terminal_1_name),
        "terminal_2_name": (legacy.terminal_2_name, scenario_b.terminal_2_name),
        "total_daily_trips": (legacy.total_daily_trips, scenario_b.total_daily_trips),
        "vehicle_capacity": (legacy.capacity, scenario_b.vehicle_capacity),
        "trip_runtime_minutes": (
            legacy.trip_runtime_minutes,
            scenario_b.trip_runtime_minutes,
        ),
        "terminal_1_first_departure": (
            legacy.terminal_1_first_departure,
            scenario_b.first_departures.terminal_1,
        ),
        "terminal_2_first_departure": (
            legacy.terminal_2_first_departure,
            scenario_b.first_departures.terminal_2,
        ),
        "terminal_1_last_departure": (
            legacy.terminal_1_last_departure,
            scenario_b.last_departures.terminal_1,
        ),
        "terminal_2_last_departure": (
            legacy.terminal_2_last_departure,
            scenario_b.last_departures.terminal_2,
        ),
    }
    mismatches = [
        field
        for field, (legacy_value, canonical_value) in comparisons.items()
        if legacy_value != canonical_value
    ]
    if mismatches:
        raise HeuristicCompatibilityContextError(
            "Legacy parameters do not reconcile with Scenario B: " + ", ".join(mismatches),
            code="HEURISTIC_CONTEXT_SOURCE_MISMATCH",
        )


def _validate_legacy_timetable(
    scenario_b: ScenarioBInput,
    legacy_trips_b: tuple[Trip, ...],
    legacy_parameters: ScenarioParameters,
) -> None:
    canonical_by_id = {trip.trip_id: trip for trip in scenario_b.exact_timetable}
    legacy_by_id = {trip.trip_id: trip for trip in legacy_trips_b}
    if len(legacy_by_id) != len(legacy_trips_b):
        raise HeuristicCompatibilityContextError(
            "Legacy Scenario B contains duplicate trip IDs",
            code="HEURISTIC_CONTEXT_SOURCE_MISMATCH",
        )
    if set(canonical_by_id) != set(legacy_by_id):
        raise HeuristicCompatibilityContextError(
            "Legacy and canonical Scenario B trip identities do not reconcile",
            code="HEURISTIC_CONTEXT_SOURCE_MISMATCH",
        )
    for trip_id, canonical_trip in canonical_by_id.items():
        legacy_trip = legacy_by_id[trip_id]
        expected_direction = contract_direction(legacy_trip.direction)
        expected_terminal = departure_terminal(expected_direction)
        arrival = legacy_trip.resolved_arrival_seconds(
            legacy_parameters.default_trip_runtime_minutes
        )
        runtime_seconds = arrival - legacy_trip.departure_seconds
        if (
            expected_direction != canonical_trip.direction
            or expected_terminal != canonical_trip.departure_terminal
            or legacy_trip.departure_seconds != canonical_trip.departure_time
            or arrival != canonical_trip.resolved_arrival_time
            or runtime_seconds != canonical_trip.runtime_minutes * 60
        ):
            raise HeuristicCompatibilityContextError(
                f"Legacy and canonical Scenario B differ for trip {trip_id}",
                code="HEURISTIC_CONTEXT_SOURCE_MISMATCH",
            )


def _validate_legacy_demand(
    normalized: NormalizedInputBundleV1,
    legacy_demand: tuple[DemandRecord, ...],
) -> None:
    observed = normalized.observed_demand
    if observed is None:
        if legacy_demand:
            raise HeuristicCompatibilityContextError(
                "Legacy demand is present while observed demand is absent",
                code="HEURISTIC_CONTEXT_DEMAND_MISMATCH",
            )
        return
    if len(observed.observations) != len(legacy_demand):
        raise HeuristicCompatibilityContextError(
            "Legacy and normalized demand row counts do not reconcile",
            code="HEURISTIC_CONTEXT_DEMAND_MISMATCH",
        )
    normalized_rows = sorted(
        (
            observation.direction.value,
            observation.interval_start,
            observation.interval_end,
            float(observation.passenger_count),
            observation.volume_classification.value,
        )
        for observation in observed.observations
    )
    legacy_rows = sorted(
        (
            contract_direction(record.direction).value,
            record.block_start_seconds,
            record.block_end_seconds,
            float(record.passenger_volume),
            record.volume_type.value,
        )
        for record in legacy_demand
    )
    if normalized_rows != legacy_rows:
        raise HeuristicCompatibilityContextError(
            "Legacy and normalized demand observations do not reconcile",
            code="HEURISTIC_CONTEXT_DEMAND_MISMATCH",
        )


def _canonical_trip_rows(trips: tuple[Trip, ...]) -> list[dict[str, object]]:
    return [
        _jsonable(asdict(item))
        for item in sorted(
            trips,
            key=lambda item: (item.departure_seconds, item.trip_id),
        )
    ]


def _canonical_demand_rows(
    rows: tuple[DemandRecord, ...],
) -> list[dict[str, object]]:
    return [
        _jsonable(asdict(item))
        for item in sorted(
            rows,
            key=lambda item: (
                item.direction.value,
                item.block_start_seconds,
                item.block_end_seconds,
                item.period_start,
                item.period_end,
                item.passenger_volume,
            ),
        )
    ]


def heuristic_context_fingerprint(
    *,
    legacy_parameters: ScenarioParameters,
    legacy_trips_b: tuple[Trip, ...],
    legacy_demand: tuple[DemandRecord, ...],
    heuristic_config: ScenarioCConfig,
    turnaround_bridge_mode: str,
    turnaround_bridge_value_minutes: int,
    source_b_fingerprint: str,
    observed_demand_fingerprint: str | None,
    protected_service_floor_enforcement_fingerprint: str | None = None,
) -> str:
    payload = {
        "fingerprint_profile": HEURISTIC_CONTEXT_FINGERPRINT_PROFILE,
        "source_b_fingerprint": source_b_fingerprint,
        "observed_demand_fingerprint": observed_demand_fingerprint,
        "legacy_parameters": _jsonable(asdict(legacy_parameters)),
        "legacy_trips_b": _canonical_trip_rows(legacy_trips_b),
        "legacy_demand": _canonical_demand_rows(legacy_demand),
        "heuristic_config": _jsonable(asdict(heuristic_config)),
        "turnaround_bridge_mode": turnaround_bridge_mode,
        "turnaround_bridge_value_minutes": turnaround_bridge_value_minutes,
    }
    if protected_service_floor_enforcement_fingerprint is not None:
        payload["protected_service_floor_enforcement_fingerprint"] = (
            protected_service_floor_enforcement_fingerprint
        )
    return canonical_sha256(payload)


def build_heuristic_compatibility_context_v1(
    normalized_inputs: NormalizedInputBundleV1,
    legacy_parameters: ScenarioParameters,
    legacy_trips_b: list[Trip] | tuple[Trip, ...],
    legacy_demand: list[DemandRecord] | tuple[DemandRecord, ...],
    heuristic_config: ScenarioCConfig,
    protected_service_floor_enforcement_fingerprint: str | None = None,
) -> HeuristicCompatibilityContextV1:
    trips = tuple(
        sorted(
            legacy_trips_b,
            key=lambda item: (item.departure_seconds, item.trip_id),
        )
    )
    demand = tuple(
        sorted(
            legacy_demand,
            key=lambda item: (
                item.direction.value,
                item.block_start_seconds,
                item.block_end_seconds,
                item.period_start,
                item.period_end,
                item.passenger_volume,
            ),
        )
    )
    _validate_legacy_parameters(normalized_inputs.scenario_b, legacy_parameters)
    _validate_legacy_timetable(normalized_inputs.scenario_b, trips, legacy_parameters)
    _validate_legacy_demand(normalized_inputs, demand)

    bridge_value = max(
        normalized_inputs.scenario_b.turnaround_minutes.terminal_1,
        normalized_inputs.scenario_b.turnaround_minutes.terminal_2,
    )
    compatibility_parameters = replace(
        legacy_parameters,
        minimum_layover_minutes=bridge_value,
    )
    fingerprint = heuristic_context_fingerprint(
        legacy_parameters=compatibility_parameters,
        legacy_trips_b=trips,
        legacy_demand=demand,
        heuristic_config=heuristic_config,
        turnaround_bridge_mode=HEURISTIC_TURNAROUND_BRIDGE_MODE,
        turnaround_bridge_value_minutes=bridge_value,
        source_b_fingerprint=normalized_inputs.scenario_b_fingerprint,
        observed_demand_fingerprint=normalized_inputs.observed_demand_fingerprint,
        protected_service_floor_enforcement_fingerprint=(
            protected_service_floor_enforcement_fingerprint
        ),
    )
    return HeuristicCompatibilityContextV1(
        legacy_parameters=compatibility_parameters,
        legacy_trips_b=trips,
        legacy_demand=demand,
        heuristic_config=heuristic_config,
        turnaround_bridge_mode=HEURISTIC_TURNAROUND_BRIDGE_MODE,
        turnaround_bridge_value_minutes=bridge_value,
        source_b_fingerprint=normalized_inputs.scenario_b_fingerprint,
        observed_demand_fingerprint=normalized_inputs.observed_demand_fingerprint,
        context_fingerprint=fingerprint,
        protected_service_floor_enforcement_fingerprint=(
            protected_service_floor_enforcement_fingerprint
        ),
    )


def heuristic_context_mismatch_codes(
    problem: ScheduleProblemV1,
    context: HeuristicCompatibilityContextV1,
) -> tuple[str, ...]:
    codes: list[str] = []
    expected_fingerprint = heuristic_context_fingerprint(
        legacy_parameters=context.legacy_parameters,
        legacy_trips_b=context.legacy_trips_b,
        legacy_demand=context.legacy_demand,
        heuristic_config=context.heuristic_config,
        turnaround_bridge_mode=context.turnaround_bridge_mode,
        turnaround_bridge_value_minutes=context.turnaround_bridge_value_minutes,
        source_b_fingerprint=context.source_b_fingerprint,
        observed_demand_fingerprint=context.observed_demand_fingerprint,
        protected_service_floor_enforcement_fingerprint=(
            context.protected_service_floor_enforcement_fingerprint
        ),
    )
    if (
        context.context_fingerprint != expected_fingerprint
        or problem.adapter_context_fingerprint != context.context_fingerprint
    ):
        codes.append("PROBLEM_ADAPTER_CONTEXT_MISMATCH")
    if context.source_b_fingerprint != problem.source_b_fingerprint:
        codes.append("HEURISTIC_CONTEXT_SOURCE_MISMATCH")
    if context.observed_demand_fingerprint != problem.observed_demand_fingerprint:
        codes.append("HEURISTIC_CONTEXT_DEMAND_MISMATCH")
    try:
        _validate_legacy_parameters(problem.scenario_b, context.legacy_parameters)
        _validate_legacy_timetable(
            problem.scenario_b,
            context.legacy_trips_b,
            context.legacy_parameters,
        )
    except HeuristicCompatibilityContextError:
        codes.append("HEURISTIC_CONTEXT_SOURCE_MISMATCH")
    return tuple(sorted(set(codes)))
