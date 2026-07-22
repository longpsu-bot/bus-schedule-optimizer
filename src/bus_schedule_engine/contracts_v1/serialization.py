from __future__ import annotations

import hashlib
import json
from typing import Any

from bus_schedule_engine.time_utils import format_hhmm

from .models import (
    DemandObservation,
    ExactTimetableTrip,
    ObservedDemandInput,
    ScenarioInputV1,
    SourceMetadata,
)


def _source_metadata_to_dict(metadata: SourceMetadata) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_type": metadata.source_type.value,
        "source_id": metadata.source_id,
        "imported_at": metadata.imported_at.isoformat(),
    }
    if metadata.notes is not None:
        payload["notes"] = metadata.notes
    return payload


def _trip_to_dict(trip: ExactTimetableTrip) -> dict[str, object]:
    payload: dict[str, object] = {
        "trip_id": trip.trip_id,
        "direction": trip.direction.value,
        "departure_terminal": trip.departure_terminal.value,
        "departure_time": format_hhmm(trip.departure_time),
        "runtime_minutes": trip.runtime_minutes,
        "vehicle_assignment": trip.vehicle_assignment,
    }
    if trip.arrival_time is not None:
        payload["arrival_time"] = format_hhmm(trip.arrival_time)
    return payload


def scenario_to_contract_dict(scenario: ScenarioInputV1) -> dict[str, object]:
    return {
        "contract_version": scenario.contract_version,
        "scenario_id": scenario.scenario_id.value,
        "route_id": scenario.route_id,
        "route_name": scenario.route_name,
        "route_type": scenario.route_type.value,
        "terminal_1_name": scenario.terminal_1_name,
        "terminal_2_name": scenario.terminal_2_name,
        "trip_runtime_minutes": scenario.trip_runtime_minutes,
        "turnaround_minutes": {
            "terminal_1": scenario.turnaround_minutes.terminal_1,
            "terminal_2": scenario.turnaround_minutes.terminal_2,
        },
        "total_daily_trips": scenario.total_daily_trips,
        "trips_by_direction": {
            "outbound": scenario.trips_by_direction.outbound,
            "inbound": scenario.trips_by_direction.inbound,
        },
        "first_departures": {
            "terminal_1": format_hhmm(scenario.first_departures.terminal_1),
            "terminal_2": format_hhmm(scenario.first_departures.terminal_2),
        },
        "last_departures": {
            "terminal_1": format_hhmm(scenario.last_departures.terminal_1),
            "terminal_2": format_hhmm(scenario.last_departures.terminal_2),
        },
        "vehicle_capacity": scenario.vehicle_capacity,
        "approved_active_fleet": scenario.approved_active_fleet,
        "available_fleet_limit": scenario.available_fleet_limit,
        "operating_day_type": scenario.operating_day_type.value,
        "exact_timetable": [_trip_to_dict(trip) for trip in scenario.exact_timetable],
        "source_metadata": _source_metadata_to_dict(scenario.source_metadata),
    }


def _observation_to_dict(observation: DemandObservation) -> dict[str, object]:
    payload: dict[str, object] = {
        "observation_id": observation.observation_id,
        "direction": observation.direction.value,
        "interval_start": format_hhmm(observation.interval_start),
        "interval_end": format_hhmm(observation.interval_end),
        "passenger_count": observation.passenger_count,
        "source_resolution_type": observation.source_resolution_type.value,
        "source_resolution_minutes": observation.source_resolution_minutes,
        "source_type": observation.source_type.value,
        "volume_classification": observation.volume_classification.value,
        "demand_confidence": observation.demand_confidence.value,
        "sample_count": observation.sample_count,
    }
    if observation.notes is not None:
        payload["notes"] = observation.notes
    return payload


def demand_to_contract_dict(demand: ObservedDemandInput) -> dict[str, object]:
    return {
        "contract_version": demand.contract_version,
        "demand_dataset_id": demand.demand_dataset_id,
        "scenario_observed_under": demand.scenario_observed_under.value,
        "observation_period_start": demand.observation_period_start.isoformat(),
        "observation_period_end": demand.observation_period_end.isoformat(),
        "observation_days": demand.observation_days,
        "demand_response_mode": demand.demand_response_mode.value,
        "observations": [_observation_to_dict(item) for item in demand.observations],
        "source_metadata": _source_metadata_to_dict(demand.source_metadata),
    }


def canonical_sha256(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def scenario_fingerprint(scenario: ScenarioInputV1) -> str:
    payload = scenario_to_contract_dict(scenario)
    payload.pop("source_metadata", None)
    return canonical_sha256(payload)


def observed_demand_fingerprint(demand: ObservedDemandInput) -> str:
    payload = demand_to_contract_dict(demand)
    metadata = payload["source_metadata"]
    assert isinstance(metadata, dict)
    payload["source_metadata"] = {
        "source_type": metadata["source_type"],
        "source_id": metadata["source_id"],
    }
    return canonical_sha256(payload)
