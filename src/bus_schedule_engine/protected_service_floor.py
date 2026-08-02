"""Deterministic, non-enforced Milestone 6A2A protected-service-floor authority."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from enum import Enum
from numbers import Integral, Real
from statistics import mean, median
from typing import Any

from .contracts_v1.headway_regimes import segment_continuous_headway_regimes_v1
from .contracts_v1.models import ContractDirection, ExactTimetableTrip, ScenarioBInput
from .contracts_v1.serialization import scenario_fingerprint
from .importer import ImportedWorkbook
from .models import (
    CurrentBServiceRegimeV1,
    ProtectedRegimeDecisionV1,
    ProtectedRegimeEvidenceV1,
    ProtectedServiceFloorAssessmentV1,
    ProtectedServiceFloorPolicyV1,
    ProtectedServiceFloorPreviewV1,
    TripRidershipAnalysisV1,
    TripRidershipDatasetStatusV1,
    TripRidershipDirectionV1,
    TripRidershipMatchStatusV1,
)
from .protected_service_floor_codes import (
    BALANCED_ROUNDING,
    DIRECTION_DERIVED_INDEPENDENTLY,
    FAILED_GATE_ORDER,
    HEADWAY_NOT_MEASURABLE,
    INSUFFICIENT_OBSERVED_DAYS_EXCLUDED_FROM_COVERAGE,
    IRREGULAR_HEADWAY_RANGE_EXCEEDS_TOLERANCE,
    IRREGULAR_NON_POSITIVE_HEADWAY,
    IRREGULAR_NON_WHOLE_MINUTE_HEADWAY,
    MATERIAL_SUSTAINED_SERVICE_RATE_CHANGE,
    MISSING_TRIP_OBSERVATIONS_ARE_NOT_ZERO,
    NOT_ENFORCED_IN_6A2A,
    NOT_EVALUATED_CONFIDENCE_BELOW_MINIMUM,
    NOT_EVALUATED_NO_TRIP_RIDERSHIP,
    NOT_EVALUATED_STALE_TRIP_RIDERSHIP,
    NOT_EVALUATED_TRIP_RIDERSHIP_FAILED,
    NOT_PROTECTED_B_REGIME_NOT_REGULAR,
    NOT_PROTECTED_EVIDENCE_NOT_BOUND_TO_CURRENT_B,
    NOT_PROTECTED_HEADWAY_ABOVE_CEILING,
    NOT_PROTECTED_HEADWAY_NOT_MEASURABLE,
    NOT_PROTECTED_HIGH_LOAD_SHARE_BELOW_THRESHOLD,
    NOT_PROTECTED_INSUFFICIENT_TRIP_COVERAGE,
    NOT_PROTECTED_NO_COVERAGE_ELIGIBLE_TRIPS,
    NOT_PROTECTED_REGIME_TOO_SHORT,
    NOT_PROTECTED_TOO_FEW_DEPARTURES,
    OPERATING_WINDOW_END,
    OPERATING_WINDOW_START,
    ORDERED_BY_DEPARTURE_TIME_THEN_TRIP_ID,
    P85_LOAD_FACTOR_UNAVAILABLE,
    PROTECTED_HIGH_DEMAND_SERVICE_FLOOR,
    REGULAR,
    SUPPLEMENTAL_PLANNING_EVIDENCE_ONLY,
    TRANSITION_GAP_EXCLUDED_FROM_INTERNAL_HEADWAYS,
    UNOBSERVED_TRIP_DAYS_ARE_NOT_EXTRAPOLATED,
    UNSAFE_MATCH_RECORDS_EXCLUDED,
)
from .trip_ridership import (
    trip_ridership_analysis_is_current_v1,
    trip_ridership_input_fingerprint_v1,
)

PROTECTED_SERVICE_FLOOR_POLICY_PROFILE = "m6a2a_protected_service_floor_policy_v1"
CURRENT_B_REGIME_DERIVATION_PROFILE = "m6a2a_current_b_service_regimes_v1"
PROTECTED_SERVICE_FLOOR_ASSESSMENT_PROFILE = "m6a2a_protected_service_floor_assessment_v1"

_CONFIDENCE_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3}
_DIRECTION_ORDER = (
    ContractDirection.OUTBOUND,
    ContractDirection.INBOUND,
)
_USABLE_STATUSES = {
    TripRidershipMatchStatusV1.MATCHED_EXACT,
    TripRidershipMatchStatusV1.MATCHED_WITHIN_TOLERANCE,
}


@dataclass(frozen=True, slots=True)
class _CurrentBBoundaryPolicyV1:
    """Existing exact-B detector parameters, isolated from Scenario-C configuration."""

    minimum_sustained_change_intervals: int = 2
    minimum_material_headway_change_minutes: int = 5
    minimum_material_service_rate_change_ratio: float = 0.15
    maximum_headway_regimes_per_direction: int = 6


_BOUNDARY_POLICY = _CurrentBBoundaryPolicyV1()


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "isoformat") and callable(value.isoformat):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    return value


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        _canonical_value(payload),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256_fingerprint(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _direction(direction: ContractDirection) -> TripRidershipDirectionV1:
    if direction == ContractDirection.OUTBOUND:
        return TripRidershipDirectionV1.OUTBOUND
    if direction == ContractDirection.INBOUND:
        return TripRidershipDirectionV1.INBOUND
    raise ValueError("Scenario B service regimes cannot combine directions")


def _gap_minutes(earlier: object, later: object) -> float:
    return (later.departure_time - earlier.departure_time) / 60


def _regularity(
    headways: tuple[float, ...],
    tolerance_minutes: int,
) -> tuple[str, tuple[str, ...]]:
    if not headways:
        return HEADWAY_NOT_MEASURABLE, (HEADWAY_NOT_MEASURABLE,)
    if any(value <= 0 for value in headways):
        return IRREGULAR_NON_POSITIVE_HEADWAY, (IRREGULAR_NON_POSITIVE_HEADWAY,)
    if any(not float(value).is_integer() for value in headways):
        return IRREGULAR_NON_WHOLE_MINUTE_HEADWAY, (IRREGULAR_NON_WHOLE_MINUTE_HEADWAY,)
    if max(headways) - min(headways) > tolerance_minutes:
        return IRREGULAR_HEADWAY_RANGE_EXCEEDS_TOLERANCE, (
            IRREGULAR_HEADWAY_RANGE_EXCEEDS_TOLERANCE,
        )
    if math.isclose(max(headways), min(headways), rel_tol=0, abs_tol=1e-12):
        return REGULAR, (REGULAR,)
    return BALANCED_ROUNDING, (BALANCED_ROUNDING,)


def _is_single_gap_fluctuation(
    trips: tuple[object, ...],
    tolerance_minutes: int,
) -> bool:
    headways = tuple(
        _gap_minutes(earlier, later) for earlier, later in zip(trips, trips[1:], strict=False)
    )
    if len(headways) < 3:
        return False
    for excluded_index in range(len(headways)):
        retained = headways[:excluded_index] + headways[excluded_index + 1 :]
        if (
            retained
            and all(value > 0 and float(value).is_integer() for value in retained)
            and max(retained) - min(retained) <= tolerance_minutes
            and (
                headways[excluded_index] < min(retained) - tolerance_minutes
                or headways[excluded_index] > max(retained) + tolerance_minutes
            )
        ):
            return True
    return False


def derive_exact_timetable_service_regimes_v1(
    exact_timetable: tuple[ExactTimetableTrip, ...],
    policy: ProtectedServiceFloorPolicyV1,
) -> tuple[CurrentBServiceRegimeV1, ...]:
    """Derive canonical non-overlapping regimes from an exact timetable only."""
    regimes: list[CurrentBServiceRegimeV1] = []
    for direction in _DIRECTION_ORDER:
        trips = tuple(
            sorted(
                (trip for trip in exact_timetable if trip.direction == direction),
                key=lambda item: (item.departure_time, item.trip_id),
            )
        )
        if not trips:
            continue
        canonical = segment_continuous_headway_regimes_v1(trips, _BOUNDARY_POLICY)
        boundary_indices = (
            ()
            if _is_single_gap_fluctuation(
                trips,
                policy.headway_rounding_tolerance_minutes,
            )
            else tuple(item.start_index for item in canonical[1:])
        )
        starts = (0, *boundary_indices)
        ends = (*boundary_indices, len(trips))
        for regime_index, (start_index, end_index) in enumerate(
            zip(starts, ends, strict=True),
            start=1,
        ):
            members = trips[start_index:end_index]
            if not members:
                continue
            headways = tuple(
                _gap_minutes(earlier, later)
                for earlier, later in zip(members, members[1:], strict=False)
            )
            classification, regularity_reasons = _regularity(
                headways,
                policy.headway_rounding_tolerance_minutes,
            )
            transition_before = (
                _gap_minutes(trips[start_index - 1], trips[start_index])
                if start_index > 0
                else None
            )
            transition_after = (
                _gap_minutes(trips[end_index - 1], trips[end_index])
                if end_index < len(trips)
                else None
            )
            reasons = [
                DIRECTION_DERIVED_INDEPENDENTLY,
                ORDERED_BY_DEPARTURE_TIME_THEN_TRIP_ID,
                *regularity_reasons,
            ]
            if start_index == 0:
                reasons.append(OPERATING_WINDOW_START)
            else:
                reasons.extend(
                    (
                        MATERIAL_SUSTAINED_SERVICE_RATE_CHANGE,
                        TRANSITION_GAP_EXCLUDED_FROM_INTERNAL_HEADWAYS,
                    )
                )
            if end_index == len(trips):
                reasons.append(OPERATING_WINDOW_END)
            else:
                reasons.extend(
                    (
                        MATERIAL_SUSTAINED_SERVICE_RATE_CHANGE,
                        TRANSITION_GAP_EXCLUDED_FROM_INTERNAL_HEADWAYS,
                    )
                )
            regimes.append(
                CurrentBServiceRegimeV1(
                    regime_id=(f"B-SERVICE-{direction.value.upper()}-R{regime_index:03d}"),
                    direction=_direction(direction),
                    first_b_trip_id=members[0].trip_id,
                    last_b_trip_id=members[-1].trip_id,
                    b_trip_ids=tuple(item.trip_id for item in members),
                    first_departure=members[0].departure_time,
                    last_departure=members[-1].departure_time,
                    trip_count=len(members),
                    duration_minutes=(
                        (members[-1].departure_time - members[0].departure_time) / 60
                    ),
                    internal_headway_sequence=headways,
                    minimum_b_headway=min(headways, default=None),
                    maximum_b_headway=max(headways, default=None),
                    representative_b_headway=(mean(headways) if headways else None),
                    regularity_classification=classification,
                    transition_headway_before=transition_before,
                    transition_headway_after=transition_after,
                    derivation_reason_codes=tuple(dict.fromkeys(reasons)),
                )
            )
    return tuple(regimes)


def derive_current_b_service_regimes_v1(
    scenario_b: ScenarioBInput,
    policy: ProtectedServiceFloorPolicyV1,
) -> tuple[CurrentBServiceRegimeV1, ...]:
    """Derive non-overlapping current-B regimes via the canonical exact-B boundary service."""
    return derive_exact_timetable_service_regimes_v1(scenario_b.exact_timetable, policy)


def _coerce_policy_value(name: str, value: object) -> object:
    integer_fields = {
        "maximum_protected_b_headway_minutes",
        "headway_rounding_tolerance_minutes",
        "minimum_departures_per_regime",
        "minimum_regime_duration_minutes",
        "minimum_observed_days_per_trip",
        "future_service_window_boundary_tolerance_minutes",
    }
    rate_fields = {
        "minimum_regime_trip_coverage_rate",
        "minimum_high_load_trip_share",
    }
    if name in integer_fields:
        if isinstance(value, bool):
            # Pandas coerces numeric 0/1 cells in the mixed CAU_HINH value
            # column to bool when that column also contains declared switches.
            return int(value)
        if isinstance(value, Integral):
            return int(value)
        if isinstance(value, Real) and math.isfinite(float(value)) and float(value).is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                parsed = float(value.strip())
            except ValueError:
                return value
            return int(parsed) if math.isfinite(parsed) and parsed.is_integer() else value
    if name in rate_fields and isinstance(value, (Real, str)) and not isinstance(value, bool):
        try:
            return float(value)
        except ValueError:
            return value
    if name == "protected_load_statistic" and isinstance(value, str):
        return value.strip().upper()
    if name == "minimum_trip_ridership_confidence" and isinstance(value, str):
        return value.strip().lower()
    return value


def protected_service_floor_policy_from_workbook_v1(
    imported: ImportedWorkbook,
) -> ProtectedServiceFloorPolicyV1:
    """Read optional declared 6A2A settings without inferring from observations."""
    defaults = ProtectedServiceFloorPolicyV1()
    configuration = dict(imported.configuration)
    values: dict[str, object] = {}
    fields = tuple(asdict(defaults))
    for name in fields:
        prefixed = f"protected_service_floor_{name}"
        if prefixed in configuration:
            values[name] = _coerce_policy_value(name, configuration[prefixed])
    return ProtectedServiceFloorPolicyV1(**values)


def _protected_service_floor_policy_fingerprint_v1(
    policy: ProtectedServiceFloorPolicyV1,
) -> str:
    return _canonical_sha256(
        {
            "profile": PROTECTED_SERVICE_FLOOR_POLICY_PROFILE,
            "policy": asdict(policy),
        }
    )


def _current_b_regime_derivation_fingerprint_v1(
    regimes: tuple[CurrentBServiceRegimeV1, ...],
    policy: ProtectedServiceFloorPolicyV1,
) -> str:
    return _canonical_sha256(
        {
            "profile": CURRENT_B_REGIME_DERIVATION_PROFILE,
            "boundary_policy": asdict(_BOUNDARY_POLICY),
            "rounding_tolerance_minutes": policy.headway_rounding_tolerance_minutes,
            "regimes": [asdict(regime) for regime in regimes],
        }
    )


def _analysis_trip_facts_match_active_workbook(
    imported: ImportedWorkbook,
    scenario_b: ScenarioBInput,
    analysis: TripRidershipAnalysisV1,
) -> bool:
    if imported.parameters_b.capacity != scenario_b.vehicle_capacity:
        return False
    expected_trips = {trip.trip_id: trip for trip in scenario_b.exact_timetable}
    summaries = {summary.trip_id: summary for summary in analysis.trip_summaries}
    if set(summaries) != set(expected_trips):
        return False
    overrides = {
        trip.trip_id: trip.vehicle_capacity_override
        for trip in imported.trips_b
        if trip.vehicle_capacity_override is not None
    }
    for trip_id, trip in expected_trips.items():
        summary = summaries[trip_id]
        expected_capacity = int(overrides.get(trip_id, scenario_b.vehicle_capacity))
        if (
            summary.scheduled_departure_seconds != trip.departure_time
            or summary.direction != _direction(trip.direction)
            or summary.nominal_trip_capacity != expected_capacity
        ):
            return False
        expected_p85_load_factor = (
            summary.passenger_p85 / expected_capacity if summary.passenger_p85 is not None else None
        )
        if (expected_p85_load_factor is None and summary.p85_load_factor is not None) or (
            expected_p85_load_factor is not None
            and (
                summary.p85_load_factor is None
                or not math.isclose(
                    summary.p85_load_factor,
                    expected_p85_load_factor,
                    rel_tol=0,
                    abs_tol=1e-12,
                )
            )
        ):
            return False
    return True


def _analysis_eligibility(
    imported: ImportedWorkbook,
    scenario_b: ScenarioBInput,
    analysis: TripRidershipAnalysisV1 | None,
    policy: ProtectedServiceFloorPolicyV1,
) -> tuple[str | None, bool]:
    has_input = bool(
        imported.trip_ridership_metadata is not None and imported.trip_ridership_observations
    )
    if not has_input:
        return NOT_EVALUATED_NO_TRIP_RIDERSHIP, False
    if analysis is None:
        return NOT_EVALUATED_TRIP_RIDERSHIP_FAILED, False
    if analysis.dataset_summary.status == TripRidershipDatasetStatusV1.FAILED:
        return NOT_EVALUATED_TRIP_RIDERSHIP_FAILED, False
    b_fingerprint = scenario_fingerprint(scenario_b)
    metadata = imported.trip_ridership_metadata
    assert metadata is not None
    if (
        not trip_ridership_analysis_is_current_v1(
            analysis,
            imported,
            b_fingerprint,
        )
        or analysis.operating_day_type != scenario_b.operating_day_type.value
        or metadata.operating_day_type != scenario_b.operating_day_type.value
        or analysis.match_policy.observed_schedule_scenario != "B"
        or metadata.observed_schedule_scenario != "B"
        or not _analysis_trip_facts_match_active_workbook(
            imported,
            scenario_b,
            analysis,
        )
    ):
        return NOT_EVALUATED_STALE_TRIP_RIDERSHIP, False
    confidence = _CONFIDENCE_ORDER.get(analysis.confidence)
    if confidence is None:
        return NOT_EVALUATED_STALE_TRIP_RIDERSHIP, False
    if confidence < _CONFIDENCE_ORDER[policy.minimum_trip_ridership_confidence]:
        return NOT_EVALUATED_CONFIDENCE_BELOW_MINIMUM, False
    return None, True


def _empty_evidence(
    regime: CurrentBServiceRegimeV1,
    limitation: str,
) -> ProtectedRegimeEvidenceV1:
    return ProtectedRegimeEvidenceV1(
        regime_id=regime.regime_id,
        total_b_trips=regime.trip_count,
        trips_with_any_usable_observation=0,
        coverage_eligible_trips=0,
        high_load_eligible_trips=0,
        trips_above_maximum_load_factor_at_p85=0,
        regime_trip_coverage_rate=0.0,
        high_load_trip_share=None,
        minimum_p85_load_factor=None,
        median_p85_load_factor=None,
        maximum_p85_load_factor=None,
        total_distinct_service_dates=0,
        exact_match_count=0,
        tolerance_match_count=0,
        excluded_record_count=0,
        coverage_eligible_trip_ids=(),
        high_load_eligible_trip_ids=(),
        trips_above_maximum_load_factor_at_p85_ids=(),
        evidence_limitations=(
            limitation,
            MISSING_TRIP_OBSERVATIONS_ARE_NOT_ZERO,
            UNOBSERVED_TRIP_DAYS_ARE_NOT_EXTRAPOLATED,
            SUPPLEMENTAL_PLANNING_EVIDENCE_ONLY,
        ),
    )


def _excluded_row_is_attributable(row: object, trip_ids: frozenset[str]) -> bool:
    if row.match_status in _USABLE_STATUSES:
        return False
    if row.matched_trip_id in trip_ids:
        return True
    if row.supplied_scheduled_trip_id in trip_ids:
        return True
    candidates = frozenset(row.candidate_trip_ids)
    return bool(candidates and candidates.issubset(trip_ids))


def _regime_evidence(
    imported: ImportedWorkbook,
    regime: CurrentBServiceRegimeV1,
    analysis: TripRidershipAnalysisV1,
    policy: ProtectedServiceFloorPolicyV1,
) -> ProtectedRegimeEvidenceV1:
    trip_ids = frozenset(regime.b_trip_ids)
    summaries = tuple(summary for summary in analysis.trip_summaries if summary.trip_id in trip_ids)
    summary_by_id = {summary.trip_id: summary for summary in summaries}
    coverage_ids = tuple(
        trip_id
        for trip_id in regime.b_trip_ids
        if trip_id in summary_by_id
        and summary_by_id[trip_id].distinct_observation_day_count
        >= policy.minimum_observed_days_per_trip
    )
    high_ids = tuple(
        trip_id
        for trip_id in coverage_ids
        if summary_by_id[trip_id].p85_load_factor is not None
        and summary_by_id[trip_id].p85_load_factor >= imported.parameters_b.target_load_factor
    )
    above_maximum_ids = tuple(
        trip_id
        for trip_id in coverage_ids
        if summary_by_id[trip_id].p85_load_factor is not None
        and summary_by_id[trip_id].p85_load_factor > imported.parameters_b.maximum_load_factor
    )
    p85_values = tuple(
        float(summary_by_id[trip_id].p85_load_factor)
        for trip_id in coverage_ids
        if summary_by_id[trip_id].p85_load_factor is not None
    )
    regime_rows = tuple(
        row
        for row in analysis.match_rows
        if row.matched_trip_id in trip_ids and row.match_status in _USABLE_STATUSES
    )
    limitations = [
        MISSING_TRIP_OBSERVATIONS_ARE_NOT_ZERO,
        UNOBSERVED_TRIP_DAYS_ARE_NOT_EXTRAPOLATED,
        SUPPLEMENTAL_PLANNING_EVIDENCE_ONLY,
    ]
    if len(coverage_ids) < regime.trip_count:
        limitations.append(INSUFFICIENT_OBSERVED_DAYS_EXCLUDED_FROM_COVERAGE)
    if any(summary_by_id[trip_id].p85_load_factor is None for trip_id in coverage_ids):
        limitations.append(P85_LOAD_FACTOR_UNAVAILABLE)
    excluded_count = sum(
        _excluded_row_is_attributable(row, trip_ids) for row in analysis.match_rows
    )
    if excluded_count:
        limitations.append(UNSAFE_MATCH_RECORDS_EXCLUDED)
    return ProtectedRegimeEvidenceV1(
        regime_id=regime.regime_id,
        total_b_trips=regime.trip_count,
        trips_with_any_usable_observation=sum(
            summary.observation_count > 0 for summary in summaries
        ),
        coverage_eligible_trips=len(coverage_ids),
        high_load_eligible_trips=len(high_ids),
        trips_above_maximum_load_factor_at_p85=len(above_maximum_ids),
        regime_trip_coverage_rate=(
            len(coverage_ids) / regime.trip_count if regime.trip_count else 0.0
        ),
        high_load_trip_share=(len(high_ids) / len(coverage_ids) if coverage_ids else None),
        minimum_p85_load_factor=min(p85_values, default=None),
        median_p85_load_factor=median(p85_values) if p85_values else None,
        maximum_p85_load_factor=max(p85_values, default=None),
        total_distinct_service_dates=len({row.service_date for row in regime_rows}),
        exact_match_count=sum(
            row.match_status == TripRidershipMatchStatusV1.MATCHED_EXACT for row in regime_rows
        ),
        tolerance_match_count=sum(
            row.match_status == TripRidershipMatchStatusV1.MATCHED_WITHIN_TOLERANCE
            for row in regime_rows
        ),
        excluded_record_count=excluded_count,
        coverage_eligible_trip_ids=coverage_ids,
        high_load_eligible_trip_ids=high_ids,
        trips_above_maximum_load_factor_at_p85_ids=above_maximum_ids,
        evidence_limitations=tuple(dict.fromkeys(limitations)),
    )


def _ordered_failures(codes: set[str]) -> tuple[str, ...]:
    order = {code: index for index, code in enumerate(FAILED_GATE_ORDER)}
    return tuple(sorted(codes, key=lambda code: (order.get(code, len(order)), code)))


def _decision(
    regime: CurrentBServiceRegimeV1,
    evidence: ProtectedRegimeEvidenceV1,
    policy: ProtectedServiceFloorPolicyV1,
    eligibility_code: str | None,
    evidence_is_current: bool,
) -> ProtectedRegimeDecisionV1:
    failed: set[str] = set()
    if regime.regularity_classification not in {REGULAR, BALANCED_ROUNDING}:
        failed.add(NOT_PROTECTED_B_REGIME_NOT_REGULAR)
    if regime.maximum_b_headway is None:
        failed.add(NOT_PROTECTED_HEADWAY_NOT_MEASURABLE)
    elif regime.maximum_b_headway > policy.maximum_protected_b_headway_minutes:
        failed.add(NOT_PROTECTED_HEADWAY_ABOVE_CEILING)
    if regime.trip_count < policy.minimum_departures_per_regime:
        failed.add(NOT_PROTECTED_TOO_FEW_DEPARTURES)
    if regime.duration_minutes < policy.minimum_regime_duration_minutes:
        failed.add(NOT_PROTECTED_REGIME_TOO_SHORT)
    if eligibility_code is not None:
        failed.add(eligibility_code)
    elif not evidence_is_current:
        failed.add(NOT_PROTECTED_EVIDENCE_NOT_BOUND_TO_CURRENT_B)
    else:
        if evidence.regime_trip_coverage_rate < policy.minimum_regime_trip_coverage_rate:
            failed.add(NOT_PROTECTED_INSUFFICIENT_TRIP_COVERAGE)
        if evidence.coverage_eligible_trips == 0:
            failed.add(NOT_PROTECTED_NO_COVERAGE_ELIGIBLE_TRIPS)
        if (
            evidence.high_load_trip_share is None
            or evidence.high_load_trip_share < policy.minimum_high_load_trip_share
        ):
            failed.add(NOT_PROTECTED_HIGH_LOAD_SHARE_BELOW_THRESHOLD)
    failed_codes = _ordered_failures(failed)
    classification = (
        PROTECTED_HIGH_DEMAND_SERVICE_FLOOR
        if not failed_codes
        else eligibility_code or failed_codes[0]
    )
    return ProtectedRegimeDecisionV1(
        regime_id=regime.regime_id,
        classification=classification,
        failed_gate_codes=failed_codes,
        evidence=evidence,
    )


def _protected_service_floor_assessment_fingerprint_v1(
    *,
    scenario_b_fingerprint: str,
    trip_ridership_input_fingerprint: str | None,
    trip_ridership_analysis_fingerprint: str | None,
    policy_fingerprint: str,
    regime_derivation_fingerprint: str,
    target_load_factor: float,
    maximum_load_factor: float,
    decisions: tuple[ProtectedRegimeDecisionV1, ...],
    protected_previews: tuple[ProtectedServiceFloorPreviewV1, ...],
    issue_codes: tuple[str, ...],
    limitations: tuple[str, ...],
) -> str:
    return _canonical_sha256(
        {
            "profile": PROTECTED_SERVICE_FLOOR_ASSESSMENT_PROFILE,
            "scenario_b_fingerprint": scenario_b_fingerprint,
            "trip_ridership_input_fingerprint": trip_ridership_input_fingerprint,
            "trip_ridership_analysis_fingerprint": trip_ridership_analysis_fingerprint,
            "policy_fingerprint": policy_fingerprint,
            "regime_derivation_fingerprint": regime_derivation_fingerprint,
            "target_load_factor": target_load_factor,
            "maximum_load_factor": maximum_load_factor,
            "decisions": [asdict(decision) for decision in decisions],
            "protected_previews": [asdict(preview) for preview in protected_previews],
            "issue_codes": issue_codes,
            "limitations": limitations,
        }
    )


def assess_protected_service_floors_v1(
    imported: ImportedWorkbook,
    scenario_b: ScenarioBInput,
    trip_ridership_analysis: TripRidershipAnalysisV1 | None,
    policy: ProtectedServiceFloorPolicyV1,
) -> ProtectedServiceFloorAssessmentV1:
    """Assess future floor eligibility without constructing, filtering, or solving Scenario C."""
    b_fingerprint = scenario_fingerprint(scenario_b)
    input_fingerprint = trip_ridership_input_fingerprint_v1(
        imported,
        b_fingerprint,
    )
    policy_fingerprint = _protected_service_floor_policy_fingerprint_v1(policy)
    regimes = derive_current_b_service_regimes_v1(scenario_b, policy)
    regime_derivation_fingerprint = _current_b_regime_derivation_fingerprint_v1(
        regimes,
        policy,
    )
    eligibility_code, evidence_is_current = _analysis_eligibility(
        imported,
        scenario_b,
        trip_ridership_analysis,
        policy,
    )
    decisions: list[ProtectedRegimeDecisionV1] = []
    for regime in regimes:
        evidence = (
            _regime_evidence(
                imported,
                regime,
                trip_ridership_analysis,
                policy,
            )
            if evidence_is_current and trip_ridership_analysis is not None
            else _empty_evidence(
                regime,
                eligibility_code or NOT_PROTECTED_EVIDENCE_NOT_BOUND_TO_CURRENT_B,
            )
        )
        decisions.append(
            _decision(
                regime,
                evidence,
                policy,
                eligibility_code,
                evidence_is_current,
            )
        )
    decision_tuple = tuple(decisions)
    decision_by_id = {decision.regime_id: decision for decision in decision_tuple}
    previews = tuple(
        ProtectedServiceFloorPreviewV1(
            regime_id=regime.regime_id,
            maximum_future_c_headway_minutes=int(regime.maximum_b_headway),
            minimum_future_c_trip_count=regime.trip_count,
            protected_window_start=regime.first_departure,
            protected_window_end=regime.last_departure,
            future_boundary_tolerance_minutes=(
                policy.future_service_window_boundary_tolerance_minutes
            ),
            donor_removal_prohibited=True,
            enforcement_status=NOT_ENFORCED_IN_6A2A,
        )
        for regime in regimes
        if (
            decision_by_id[regime.regime_id].classification == PROTECTED_HIGH_DEMAND_SERVICE_FLOOR
            and regime.maximum_b_headway is not None
        )
    )
    issue_codes = tuple(
        dict.fromkeys(
            (
                *((eligibility_code,) if eligibility_code is not None else ()),
                *(code for decision in decision_tuple for code in decision.failed_gate_codes),
            )
        )
    )
    limitations = tuple(
        dict.fromkeys(
            (
                SUPPLEMENTAL_PLANNING_EVIDENCE_ONLY,
                NOT_ENFORCED_IN_6A2A,
                MISSING_TRIP_OBSERVATIONS_ARE_NOT_ZERO,
                UNOBSERVED_TRIP_DAYS_ARE_NOT_EXTRAPOLATED,
                *(
                    limitation
                    for decision in decision_tuple
                    for limitation in decision.evidence.evidence_limitations
                ),
            )
        )
    )
    analysis_fingerprint = (
        trip_ridership_analysis.analysis_fingerprint
        if trip_ridership_analysis is not None
        else None
    )
    assessment_fingerprint = _protected_service_floor_assessment_fingerprint_v1(
        scenario_b_fingerprint=b_fingerprint,
        trip_ridership_input_fingerprint=input_fingerprint,
        trip_ridership_analysis_fingerprint=analysis_fingerprint,
        policy_fingerprint=policy_fingerprint,
        regime_derivation_fingerprint=regime_derivation_fingerprint,
        target_load_factor=imported.parameters_b.target_load_factor,
        maximum_load_factor=imported.parameters_b.maximum_load_factor,
        decisions=decision_tuple,
        protected_previews=previews,
        issue_codes=issue_codes,
        limitations=limitations,
    )
    return ProtectedServiceFloorAssessmentV1(
        scenario_b_fingerprint=b_fingerprint,
        trip_ridership_input_fingerprint=input_fingerprint,
        trip_ridership_analysis_fingerprint=analysis_fingerprint,
        policy_fingerprint=policy_fingerprint,
        regime_derivation_fingerprint=regime_derivation_fingerprint,
        assessment_fingerprint=assessment_fingerprint,
        target_load_factor=imported.parameters_b.target_load_factor,
        maximum_load_factor=imported.parameters_b.maximum_load_factor,
        policy=policy,
        regimes=regimes,
        decisions=decision_tuple,
        protected_previews=previews,
        issue_codes=issue_codes,
        limitations=limitations,
    )


def protected_service_floor_assessment_is_current_v1(
    assessment: ProtectedServiceFloorAssessmentV1 | None,
    imported: ImportedWorkbook | None,
    scenario_b: ScenarioBInput | None,
    trip_ridership_analysis: TripRidershipAnalysisV1 | None,
) -> bool:
    """Verify the full current 6A2A authority chain without reclassifying regimes."""
    if (
        not isinstance(assessment, ProtectedServiceFloorAssessmentV1)
        or not isinstance(imported, ImportedWorkbook)
        or not isinstance(scenario_b, ScenarioBInput)
        or not isinstance(assessment.policy, ProtectedServiceFloorPolicyV1)
    ):
        return False

    required_fingerprints = (
        assessment.scenario_b_fingerprint,
        assessment.policy_fingerprint,
        assessment.regime_derivation_fingerprint,
        assessment.assessment_fingerprint,
    )
    if not all(_is_sha256_fingerprint(value) for value in required_fingerprints):
        return False
    for optional_fingerprint in (
        assessment.trip_ridership_input_fingerprint,
        assessment.trip_ridership_analysis_fingerprint,
    ):
        if optional_fingerprint is not None and not _is_sha256_fingerprint(optional_fingerprint):
            return False

    try:
        current_b_fingerprint = scenario_fingerprint(scenario_b)
        current_input_fingerprint = trip_ridership_input_fingerprint_v1(
            imported,
            current_b_fingerprint,
        )
        current_policy = protected_service_floor_policy_from_workbook_v1(imported)
        current_policy_fingerprint = _protected_service_floor_policy_fingerprint_v1(current_policy)
        current_derivation_fingerprint = _current_b_regime_derivation_fingerprint_v1(
            assessment.regimes,
            current_policy,
        )
    except (AttributeError, TypeError, ValueError):
        return False

    current_analysis_fingerprint: str | None = None
    if trip_ridership_analysis is not None:
        if not trip_ridership_analysis_is_current_v1(
            trip_ridership_analysis,
            imported,
            current_b_fingerprint,
        ):
            return False
        current_analysis_fingerprint = trip_ridership_analysis.analysis_fingerprint
        if not _is_sha256_fingerprint(current_analysis_fingerprint):
            return False

    if current_input_fingerprint is not None and not _is_sha256_fingerprint(
        current_input_fingerprint
    ):
        return False
    if (
        assessment.scenario_b_fingerprint != current_b_fingerprint
        or assessment.trip_ridership_input_fingerprint != current_input_fingerprint
        or assessment.trip_ridership_analysis_fingerprint != current_analysis_fingerprint
        or assessment.policy != current_policy
        or assessment.policy_fingerprint != current_policy_fingerprint
        or assessment.regime_derivation_fingerprint != current_derivation_fingerprint
        or assessment.target_load_factor != imported.parameters_b.target_load_factor
        or assessment.maximum_load_factor != imported.parameters_b.maximum_load_factor
    ):
        return False

    try:
        expected_assessment_fingerprint = _protected_service_floor_assessment_fingerprint_v1(
            scenario_b_fingerprint=assessment.scenario_b_fingerprint,
            trip_ridership_input_fingerprint=(assessment.trip_ridership_input_fingerprint),
            trip_ridership_analysis_fingerprint=(assessment.trip_ridership_analysis_fingerprint),
            policy_fingerprint=assessment.policy_fingerprint,
            regime_derivation_fingerprint=(assessment.regime_derivation_fingerprint),
            target_load_factor=assessment.target_load_factor,
            maximum_load_factor=assessment.maximum_load_factor,
            decisions=assessment.decisions,
            protected_previews=assessment.protected_previews,
            issue_codes=assessment.issue_codes,
            limitations=assessment.limitations,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return assessment.assessment_fingerprint == expected_assessment_fingerprint


__all__ = [
    "CURRENT_B_REGIME_DERIVATION_PROFILE",
    "PROTECTED_SERVICE_FLOOR_ASSESSMENT_PROFILE",
    "PROTECTED_SERVICE_FLOOR_POLICY_PROFILE",
    "assess_protected_service_floors_v1",
    "derive_current_b_service_regimes_v1",
    "derive_exact_timetable_service_regimes_v1",
    "protected_service_floor_assessment_is_current_v1",
    "protected_service_floor_policy_from_workbook_v1",
]
