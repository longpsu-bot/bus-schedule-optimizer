"""Canonical serialization for Uniform-Headway Schedule Compiler V1."""

from __future__ import annotations

from fractions import Fraction

from .serialization import canonical_sha256
from .uniform_headway_compiler_models import CompiledScheduleCandidateV1


def minute_hhmm(minute: int | None) -> str | None:
    if minute is None:
        return None
    hour, minute_of_hour = divmod(minute, 60)
    return f"{hour:02d}:{minute_of_hour:02d}"


def fraction_to_contract(value: Fraction | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "exact": str(value),
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": float(value),
    }


def _candidate_payload(candidate: CompiledScheduleCandidateV1) -> dict[str, object]:
    return {
        "compiler_profile": "uniform_headway_schedule_compiler_v1",
        "route_id": candidate.route_id,
        "direction": candidate.direction,
        "source_allocation_candidate_id": candidate.source_allocation_candidate_id,
        "source_provenance": candidate.source_provenance,
        "source_compiler_input_fingerprint": candidate.source_compiler_input_fingerprint,
        "upstream_fingerprint_assertions": {
            "status": "PROVENANCE_ASSERTION_NOT_REPRODUCED_ON_THIS_MACHINE",
            "demand_regime": candidate.demand_regime_fingerprint_assertion,
            "trip_allocation": candidate.trip_allocation_fingerprint_assertion,
        },
        "service_start": minute_hhmm(candidate.service_start_minute),
        "service_end": minute_hhmm(candidate.service_end_minute),
        "service_start_minute": candidate.service_start_minute,
        "service_end_minute": candidate.service_end_minute,
        "total_trip_count": candidate.total_trip_count,
        "status": candidate.status.value,
        "fleet_validation_status": candidate.fleet_validation_status.value,
        "objective": {
            "worst_gap_excess": fraction_to_contract(candidate.worst_gap_excess),
            "total_gap_excess": fraction_to_contract(candidate.total_gap_excess),
            "total_quantization_error": fraction_to_contract(candidate.total_quantization_error),
            "service_regime_count": candidate.service_regime_count,
            "transition_shape_error": fraction_to_contract(candidate.transition_shape_error),
            "edge_balance_error": candidate.edge_balance_error,
        },
        "review_metrics": {
            "service_start_gap_minutes": candidate.service_start_gap_minutes,
            "service_end_gap_minutes": candidate.service_end_gap_minutes,
            "worst_transition_or_edge_gap_minutes": (
                candidate.worst_transition_or_edge_gap_minutes
            ),
            "minimum_actual_gap_minutes": candidate.minimum_actual_gap_minutes,
            "maximum_actual_gap_minutes": candidate.maximum_actual_gap_minutes,
            "median_actual_gap_minutes": fraction_to_contract(candidate.median_actual_gap_minutes),
        },
        "demand_regime_compilations": [
            {
                "regime_id": item.regime_id,
                "start": minute_hhmm(item.start_minute),
                "end": minute_hhmm(item.end_minute),
                "start_minute": item.start_minute,
                "end_minute": item.end_minute,
                "duration_minutes": item.duration_minutes,
                "allocated_trip_count": item.allocated_trip_count,
                "nominal_headway": fraction_to_contract(item.nominal_headway),
                "selected_integer_headway": item.selected_integer_headway,
                "phase_offset_minutes": item.phase_offset_minutes,
                "first_departure": minute_hhmm(item.first_departure_minute),
                "last_departure": minute_hhmm(item.last_departure_minute),
                "first_departure_minute": item.first_departure_minute,
                "last_departure_minute": item.last_departure_minute,
                "leading_slack_minutes": item.leading_slack_minutes,
                "trailing_slack_minutes": item.trailing_slack_minutes,
                "internal_headway_count": item.internal_headway_count,
                "quantization_error": fraction_to_contract(item.quantization_error),
                "actual_trip_count": item.actual_trip_count,
                "count_verified": item.count_verified,
            }
            for item in candidate.demand_regime_compilations
        ],
        "service_regimes": [
            {
                "service_regime_id": item.service_regime_id,
                "start": minute_hhmm(item.start_minute),
                "end": minute_hhmm(item.end_minute),
                "start_minute": item.start_minute,
                "end_minute": item.end_minute,
                "headway_minutes": item.headway_minutes,
                "departure_count": item.departure_count,
                "first_departure": minute_hhmm(item.first_departure_minute),
                "last_departure": minute_hhmm(item.last_departure_minute),
                "first_departure_minute": item.first_departure_minute,
                "last_departure_minute": item.last_departure_minute,
                "member_demand_regime_ids": list(item.member_demand_regime_ids),
            }
            for item in candidate.service_regimes
        ],
        "exact_departures": [
            {
                "trip_sequence": item.trip_sequence,
                "departure_time": minute_hhmm(item.departure_minute),
                "departure_minute": item.departure_minute,
                "source_demand_regime_id": item.source_demand_regime_id,
                "service_regime_id": item.service_regime_id,
            }
            for item in candidate.exact_departures
        ],
        "failure_evidence": list(candidate.failure_evidence),
    }


def compiled_schedule_to_contract_dict_v1(
    candidate: CompiledScheduleCandidateV1,
) -> dict[str, object]:
    payload = _candidate_payload(candidate)
    return {
        **payload,
        "compiled_schedule_fingerprint": canonical_sha256(payload),
    }


__all__ = [
    "compiled_schedule_to_contract_dict_v1",
    "fraction_to_contract",
    "minute_hhmm",
]
