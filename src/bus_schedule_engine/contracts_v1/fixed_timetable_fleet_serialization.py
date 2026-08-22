"""Canonical serialization for fixed-timetable fleet-validator V1."""

from __future__ import annotations

from fractions import Fraction

from .fixed_timetable_fleet_inputs import ScheduleSourceV1
from .fixed_timetable_fleet_validator import FixedTimetableFleetResultV1
from .serialization import canonical_sha256


def minute_hhmm_v1(minute: int) -> str:
    hour, minute_of_hour = divmod(minute, 60)
    return f"{hour:02d}:{minute_of_hour:02d}"


def _fraction_number(value: Fraction | None) -> int | float | None:
    if value is None:
        return None
    if value.denominator == 1:
        return value.numerator
    return value.numerator / value.denominator


def _source_to_dict(source: ScheduleSourceV1) -> dict[str, object]:
    return {
        "scenario": source.scenario,
        "route_id": source.route_id,
        "direction": source.direction,
        "candidate_id": source.candidate_id,
        "compiler_status": source.compiler_status,
        "source_path": source.source_path,
        "source_file_sha256": source.source_file_sha256,
        "upstream_fingerprints": dict(sorted(source.upstream_fingerprints.items())),
    }


def fixed_timetable_fleet_result_to_contract_dict_v1(
    result: FixedTimetableFleetResultV1,
    *,
    scenario: str,
    outbound_candidate: str,
    inbound_candidate: str,
    sources: tuple[ScheduleSourceV1, ...],
    operational_input_sha256: str,
    minimum_layover_minutes: int,
) -> dict[str, object]:
    metrics = result.layover_metrics
    payload: dict[str, object] = {
        "validator_profile": "fixed_timetable_fleet_feasibility_validator_v1",
        "scenario": scenario,
        "route": result.route_id,
        "outbound_candidate": outbound_candidate,
        "inbound_candidate": inbound_candidate,
        "total_departures": result.total_departures,
        "direction_totals": dict(result.direction_totals),
        "minimum_fleet_required": result.minimum_fleet_required,
        "pilot_fleet_limit": result.pilot_fleet_limit,
        "fleet_margin": result.fleet_margin,
        "approved_active_fleet": result.approved_active_fleet,
        "initial_fleet_terminal_1": result.initial_fleet_terminal_1,
        "initial_fleet_terminal_2": result.initial_fleet_terminal_2,
        "ending_fleet_terminal_1": result.ending_fleet_terminal_1,
        "ending_fleet_terminal_2": result.ending_fleet_terminal_2,
        "minimum_actual_layover_minutes": metrics.minimum_actual_layover_minutes,
        "median_actual_layover_minutes": _fraction_number(metrics.median_actual_layover_minutes),
        "maximum_actual_layover_minutes": metrics.maximum_actual_layover_minutes,
        "minimum_required_layover_minutes": minimum_layover_minutes,
        "total_excess_terminal_wait_minutes": (metrics.total_excess_terminal_wait_minutes),
        "maximum_excess_terminal_wait_minutes": (metrics.maximum_excess_terminal_wait_minutes),
        "number_of_vehicle_blocks": len(result.blocks),
        "compiler_status": ("SCENARIO_B_OPERATIONAL_BASELINE" if scenario == "B" else "COMPILED"),
        "fleet_status": result.fleet_status.value,
        "fleet_limit_assessment": (
            "WITHIN_PILOT_FLEET_LIMIT"
            if result.minimum_fleet_required <= result.pilot_fleet_limit
            else "EXCEEDS_PILOT_FLEET_LIMIT"
        ),
        "terminal_capacity_status": result.terminal_capacity_status,
        "operational_input_sha256": operational_input_sha256,
        "schedule_sources": [_source_to_dict(source) for source in sources],
        "canonical_matching_objectives": [
            "maximum_legal_trip_links",
            "minimum_total_excess_terminal_wait",
            "minimum_maximum_individual_excess_terminal_wait",
            "lexicographically_earlier_successor_assignments_then_trip_ids",
        ],
        "vehicle_blocks": [
            {
                "vehicle_id": block.vehicle_id,
                "initial_terminal": block.trips[0].trip.origin_terminal,
                "ending_terminal": block.trips[-1].trip.destination_terminal,
                "trips": [
                    {
                        "sequence_within_block": item.sequence,
                        "trip_id": item.trip.trip_id,
                        "direction": item.trip.direction,
                        "origin_terminal": item.trip.origin_terminal,
                        "destination_terminal": item.trip.destination_terminal,
                        "departure_time": minute_hhmm_v1(item.trip.departure_minute),
                        "departure_minute": item.trip.departure_minute,
                        "runtime_minutes": item.trip.runtime_minutes,
                        "arrival_time": minute_hhmm_v1(item.trip.arrival_minute),
                        "arrival_minute": item.trip.arrival_minute,
                        "next_trip_layover_minutes": item.next_trip_layover_minutes,
                    }
                    for item in block.trips
                ],
            }
            for block in result.blocks
        ],
    }
    return {**payload, "validation_fingerprint": canonical_sha256(payload)}


__all__ = [
    "fixed_timetable_fleet_result_to_contract_dict_v1",
    "minute_hhmm_v1",
]
