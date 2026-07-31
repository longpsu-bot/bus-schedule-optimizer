"""Milestone 6A2B protected-service-floor acceptance enforcement."""

from __future__ import annotations

import math
import re
from dataclasses import asdict

from .contracts_v1.models import ContractDirection, ScenarioBInput
from .contracts_v1.serialization import canonical_sha256, scenario_fingerprint
from .contracts_v1.solver_models import RawScheduleCandidateV1
from .importer import ImportedWorkbook
from .models import (
    ProtectedServiceFloorAssessmentV1,
    ProtectedServiceFloorCandidateValidationV1,
    ProtectedServiceFloorEnforcementAuthorityV1,
    ProtectedServiceFloorEnforcementRegimeV1,
    TripRidershipAnalysisV1,
    TripRidershipDirectionV1,
)
from .protected_service_floor import protected_service_floor_assessment_is_current_v1
from .protected_service_floor_codes import (
    NOT_ENFORCED_IN_6A2A,
    PROTECTED_DONOR_REMOVAL,
    PROTECTED_FLOOR_REJECTION_CODE_ORDER,
    PROTECTED_HEADWAY_NOT_MEASURABLE_OR_INVALID,
    PROTECTED_HIGH_DEMAND_SERVICE_FLOOR,
    PROTECTED_INTERNAL_HEADWAY_ABOVE_FLOOR,
    PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID,
    PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_MISMATCH,
    PROTECTED_SOURCE_ORDER_VIOLATION,
    PROTECTED_SOURCE_TRIP_MISSING_OR_DUPLICATED,
    PROTECTED_TRIP_COUNT_BELOW_FLOOR,
    PROTECTED_WINDOW_END_VIOLATION,
    PROTECTED_WINDOW_START_VIOLATION,
)

PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE = (
    "m6a2b_protected_service_floor_acceptance_enforcement_v1"
)
PROTECTED_SERVICE_FLOOR_VALIDATION_PROFILE = "m6a2b_protected_service_floor_candidate_validation_v1"

_DIRECTION_ORDER = {
    TripRidershipDirectionV1.OUTBOUND: 0,
    TripRidershipDirectionV1.INBOUND: 1,
}
_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}")


class ProtectedServiceFloorEnforcementAuthorityError(ValueError):
    """Raised when the current 6A2A chain cannot become 6A2B authority."""

    code = PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID


def _valid_fingerprint(value: object) -> bool:
    return isinstance(value, str) and _FINGERPRINT_PATTERN.fullmatch(value) is not None


def _regime_payload(
    regime: ProtectedServiceFloorEnforcementRegimeV1,
) -> dict[str, object]:
    payload = asdict(regime)
    payload["direction"] = regime.direction.value
    payload["ordered_b_trip_ids"] = list(regime.ordered_b_trip_ids)
    return payload


def _authority_fingerprint_payload(
    *,
    scenario_b_fingerprint: str,
    assessment_fingerprint: str,
    policy_fingerprint: str,
    regime_derivation_fingerprint: str,
    trip_ridership_input_fingerprint: str | None,
    trip_ridership_analysis_fingerprint: str | None,
    target_load_factor: float,
    maximum_load_factor: float,
    protected_regimes: tuple[ProtectedServiceFloorEnforcementRegimeV1, ...],
) -> dict[str, object]:
    return {
        "profile": PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
        "scenario_b_fingerprint": scenario_b_fingerprint,
        "assessment_fingerprint": assessment_fingerprint,
        "policy_fingerprint": policy_fingerprint,
        "regime_derivation_fingerprint": regime_derivation_fingerprint,
        "trip_ridership_input_fingerprint": trip_ridership_input_fingerprint,
        "trip_ridership_analysis_fingerprint": trip_ridership_analysis_fingerprint,
        "target_load_factor": target_load_factor,
        "maximum_load_factor": maximum_load_factor,
        "protected_regimes": [_regime_payload(item) for item in protected_regimes],
    }


def _regime_sort_key(
    regime: ProtectedServiceFloorEnforcementRegimeV1,
) -> tuple[int, int, int, str]:
    return (
        _DIRECTION_ORDER[regime.direction],
        regime.protected_window_start,
        regime.protected_window_end,
        regime.regime_id,
    )


def build_protected_service_floor_enforcement_authority_v1(
    imported: ImportedWorkbook,
    scenario_b: ScenarioBInput,
    trip_ridership_analysis: TripRidershipAnalysisV1 | None,
    assessment: ProtectedServiceFloorAssessmentV1,
) -> ProtectedServiceFloorEnforcementAuthorityV1:
    """Promote only a current, verified 6A2A assessment into 6A2B authority."""
    if not protected_service_floor_assessment_is_current_v1(
        assessment,
        imported,
        scenario_b,
        trip_ridership_analysis,
    ):
        raise ProtectedServiceFloorEnforcementAuthorityError(
            f"{PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID}: "
            "the 6A2A assessment is stale, malformed, or inconsistent"
        )

    regime_by_id = {item.regime_id: item for item in assessment.regimes}
    preview_by_id = {item.regime_id: item for item in assessment.protected_previews}
    protected_ids = tuple(
        item.regime_id
        for item in assessment.decisions
        if item.classification == PROTECTED_HIGH_DEMAND_SERVICE_FLOOR
    )
    if (
        len(regime_by_id) != len(assessment.regimes)
        or len(preview_by_id) != len(assessment.protected_previews)
        or len(set(protected_ids)) != len(protected_ids)
        or set(protected_ids) != set(preview_by_id)
        or any(regime_id not in regime_by_id for regime_id in protected_ids)
        or any(
            preview.enforcement_status != NOT_ENFORCED_IN_6A2A
            for preview in assessment.protected_previews
        )
    ):
        raise ProtectedServiceFloorEnforcementAuthorityError(
            f"{PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID}: "
            "protected decisions, regimes, and previews do not reconcile"
        )

    protected_regimes = tuple(
        sorted(
            (
                ProtectedServiceFloorEnforcementRegimeV1(
                    regime_id=regime_id,
                    direction=regime_by_id[regime_id].direction,
                    ordered_b_trip_ids=regime_by_id[regime_id].b_trip_ids,
                    maximum_future_c_headway_minutes=(
                        preview_by_id[regime_id].maximum_future_c_headway_minutes
                    ),
                    minimum_future_c_trip_count=(
                        preview_by_id[regime_id].minimum_future_c_trip_count
                    ),
                    protected_window_start=(preview_by_id[regime_id].protected_window_start),
                    protected_window_end=(preview_by_id[regime_id].protected_window_end),
                    future_boundary_tolerance_minutes=(
                        preview_by_id[regime_id].future_boundary_tolerance_minutes
                    ),
                    donor_removal_prohibited=(preview_by_id[regime_id].donor_removal_prohibited),
                )
                for regime_id in protected_ids
            ),
            key=_regime_sort_key,
        )
    )
    fingerprint = canonical_sha256(
        _authority_fingerprint_payload(
            scenario_b_fingerprint=assessment.scenario_b_fingerprint,
            assessment_fingerprint=assessment.assessment_fingerprint,
            policy_fingerprint=assessment.policy_fingerprint,
            regime_derivation_fingerprint=assessment.regime_derivation_fingerprint,
            trip_ridership_input_fingerprint=(assessment.trip_ridership_input_fingerprint),
            trip_ridership_analysis_fingerprint=(assessment.trip_ridership_analysis_fingerprint),
            target_load_factor=assessment.target_load_factor,
            maximum_load_factor=assessment.maximum_load_factor,
            protected_regimes=protected_regimes,
        )
    )
    authority = ProtectedServiceFloorEnforcementAuthorityV1(
        scenario_b_fingerprint=assessment.scenario_b_fingerprint,
        assessment_fingerprint=assessment.assessment_fingerprint,
        policy_fingerprint=assessment.policy_fingerprint,
        regime_derivation_fingerprint=assessment.regime_derivation_fingerprint,
        trip_ridership_input_fingerprint=assessment.trip_ridership_input_fingerprint,
        trip_ridership_analysis_fingerprint=(assessment.trip_ridership_analysis_fingerprint),
        target_load_factor=assessment.target_load_factor,
        maximum_load_factor=assessment.maximum_load_factor,
        protected_regimes=protected_regimes,
        enforcement_profile=PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
        enforcement_fingerprint=fingerprint,
    )
    if not protected_service_floor_enforcement_authority_is_valid_v1(authority, scenario_b):
        raise ProtectedServiceFloorEnforcementAuthorityError(
            f"{PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_INVALID}: "
            "the derived enforcement authority failed semantic verification"
        )
    return authority


def protected_service_floor_enforcement_authority_is_valid_v1(
    authority: ProtectedServiceFloorEnforcementAuthorityV1 | None,
    scenario_b: ScenarioBInput | None,
) -> bool:
    """Verify authority identity, ordering, direction, and exact Scenario B membership."""
    if not isinstance(authority, ProtectedServiceFloorEnforcementAuthorityV1) or not isinstance(
        scenario_b, ScenarioBInput
    ):
        return False
    required = (
        authority.scenario_b_fingerprint,
        authority.assessment_fingerprint,
        authority.policy_fingerprint,
        authority.regime_derivation_fingerprint,
        authority.enforcement_fingerprint,
    )
    if not all(_valid_fingerprint(value) for value in required):
        return False
    if any(
        value is not None and not _valid_fingerprint(value)
        for value in (
            authority.trip_ridership_input_fingerprint,
            authority.trip_ridership_analysis_fingerprint,
        )
    ):
        return False
    if (
        authority.enforcement_profile != PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE
        or authority.scenario_b_fingerprint != scenario_fingerprint(scenario_b)
        or tuple(sorted(authority.protected_regimes, key=_regime_sort_key))
        != authority.protected_regimes
        or not math.isfinite(authority.target_load_factor)
        or not math.isfinite(authority.maximum_load_factor)
        or authority.target_load_factor <= 0
        or authority.maximum_load_factor < authority.target_load_factor
        or (
            authority.protected_regimes
            and (
                authority.trip_ridership_input_fingerprint is None
                or authority.trip_ridership_analysis_fingerprint is None
            )
        )
    ):
        return False

    source_by_id = {trip.trip_id: trip for trip in scenario_b.exact_timetable}
    protected_members: set[str] = set()
    previous_window_end_by_direction: dict[TripRidershipDirectionV1, int] = {}
    for regime in authority.protected_regimes:
        if (
            not regime.regime_id
            or not regime.ordered_b_trip_ids
            or len(set(regime.ordered_b_trip_ids)) != len(regime.ordered_b_trip_ids)
            or protected_members.intersection(regime.ordered_b_trip_ids)
            or regime.maximum_future_c_headway_minutes <= 0
            or regime.minimum_future_c_trip_count != len(regime.ordered_b_trip_ids)
            or regime.protected_window_start > regime.protected_window_end
            or regime.future_boundary_tolerance_minutes < 0
            or not regime.donor_removal_prohibited
        ):
            return False
        members = [source_by_id.get(trip_id) for trip_id in regime.ordered_b_trip_ids]
        if any(member is None for member in members):
            return False
        expected_direction = ContractDirection(regime.direction.value)
        if any(member.direction != expected_direction for member in members if member is not None):
            return False
        ordered_ids = tuple(
            item.trip_id
            for item in sorted(
                (member for member in members if member is not None),
                key=lambda item: (item.departure_time, item.trip_id),
            )
        )
        if (
            ordered_ids != regime.ordered_b_trip_ids
            or members[0].departure_time != regime.protected_window_start
            or members[-1].departure_time != regime.protected_window_end
        ):
            return False
        internal_gap_seconds = tuple(
            later.departure_time - earlier.departure_time
            for earlier, later in zip(members, members[1:], strict=False)
        )
        if (
            not internal_gap_seconds
            or any(gap <= 0 or gap % 60 != 0 for gap in internal_gap_seconds)
            or max(internal_gap_seconds) // 60 != regime.maximum_future_c_headway_minutes
        ):
            return False
        previous_window_end = previous_window_end_by_direction.get(regime.direction)
        if previous_window_end is not None and regime.protected_window_start <= previous_window_end:
            return False
        previous_window_end_by_direction[regime.direction] = regime.protected_window_end
        protected_members.update(regime.ordered_b_trip_ids)

    expected_fingerprint = canonical_sha256(
        _authority_fingerprint_payload(
            scenario_b_fingerprint=authority.scenario_b_fingerprint,
            assessment_fingerprint=authority.assessment_fingerprint,
            policy_fingerprint=authority.policy_fingerprint,
            regime_derivation_fingerprint=authority.regime_derivation_fingerprint,
            trip_ridership_input_fingerprint=(authority.trip_ridership_input_fingerprint),
            trip_ridership_analysis_fingerprint=(authority.trip_ridership_analysis_fingerprint),
            target_load_factor=authority.target_load_factor,
            maximum_load_factor=authority.maximum_load_factor,
            protected_regimes=authority.protected_regimes,
        )
    )
    return authority.enforcement_fingerprint == expected_fingerprint


def _ordered_rejection_codes(codes: set[str]) -> tuple[str, ...]:
    return tuple(code for code in PROTECTED_FLOOR_REJECTION_CODE_ORDER if code in codes)


def _candidate_validation(
    authority: ProtectedServiceFloorEnforcementAuthorityV1,
    candidate: RawScheduleCandidateV1,
    codes: set[str],
) -> ProtectedServiceFloorCandidateValidationV1:
    rejection_codes = _ordered_rejection_codes(codes)
    status = "REJECTED" if rejection_codes else "ACCEPTED"
    validation_fingerprint = canonical_sha256(
        {
            "profile": PROTECTED_SERVICE_FLOOR_VALIDATION_PROFILE,
            "enforcement_fingerprint": authority.enforcement_fingerprint,
            "candidate_fingerprint": candidate.candidate_fingerprint,
            "status": status,
            "rejection_codes": list(rejection_codes),
        }
    )
    return ProtectedServiceFloorCandidateValidationV1(
        enforcement_fingerprint=authority.enforcement_fingerprint,
        candidate_fingerprint=candidate.candidate_fingerprint,
        status=status,
        rejection_codes=rejection_codes,
        validation_fingerprint=validation_fingerprint,
    )


def validate_candidate_against_protected_service_floors_v1(
    authority: ProtectedServiceFloorEnforcementAuthorityV1,
    scenario_b: ScenarioBInput,
    candidate: RawScheduleCandidateV1,
) -> ProtectedServiceFloorCandidateValidationV1:
    """Independently validate every protected regime without solver-specific trust."""
    codes: set[str] = set()
    if not protected_service_floor_enforcement_authority_is_valid_v1(authority, scenario_b):
        codes.add(PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_MISMATCH)
        return _candidate_validation(authority, candidate, codes)

    candidate_by_source: dict[str, list[object]] = {}
    for trip in candidate.exact_timetable:
        candidate_by_source.setdefault(trip.source_b_trip_id, []).append(trip)

    for regime in authority.protected_regimes:
        mappings = {
            trip_id: candidate_by_source.get(trip_id, []) for trip_id in regime.ordered_b_trip_ids
        }
        if any(len(items) != 1 for items in mappings.values()):
            codes.add(PROTECTED_SOURCE_TRIP_MISSING_OR_DUPLICATED)

        mapped_members = [items[0] for items in mappings.values() if len(items) == 1]
        tolerance_seconds = regime.future_boundary_tolerance_minutes * 60
        permitted_start = regime.protected_window_start - tolerance_seconds
        permitted_end = regime.protected_window_end + tolerance_seconds
        if regime.donor_removal_prohibited and any(
            trip.c_departure_time < permitted_start or trip.c_departure_time > permitted_end
            for trip in mapped_members
        ):
            codes.add(PROTECTED_DONOR_REMOVAL)

        complete_mapping = len(mapped_members) == len(regime.ordered_b_trip_ids)
        if complete_mapping:
            candidate_member_order = tuple(
                trip.source_b_trip_id
                for trip in sorted(
                    mapped_members,
                    key=lambda item: (item.c_departure_time, item.c_trip_id),
                )
            )
            if candidate_member_order != regime.ordered_b_trip_ids:
                codes.add(PROTECTED_SOURCE_ORDER_VIOLATION)

        if not mapped_members:
            codes.update(
                {
                    PROTECTED_WINDOW_START_VIOLATION,
                    PROTECTED_WINDOW_END_VIOLATION,
                    PROTECTED_TRIP_COUNT_BELOW_FLOOR,
                    PROTECTED_HEADWAY_NOT_MEASURABLE_OR_INVALID,
                }
            )
            continue

        earliest = min(mapped_members, key=lambda item: (item.c_departure_time, item.c_trip_id))
        latest = max(mapped_members, key=lambda item: (item.c_departure_time, item.c_trip_id))
        if abs(earliest.c_departure_time - regime.protected_window_start) > tolerance_seconds:
            codes.add(PROTECTED_WINDOW_START_VIOLATION)
        if abs(latest.c_departure_time - regime.protected_window_end) > tolerance_seconds:
            codes.add(PROTECTED_WINDOW_END_VIOLATION)

        first_mapping = mappings[regime.ordered_b_trip_ids[0]]
        last_mapping = mappings[regime.ordered_b_trip_ids[-1]]
        if len(first_mapping) != 1 or len(last_mapping) != 1:
            codes.add(PROTECTED_TRIP_COUNT_BELOW_FLOOR)
            codes.add(PROTECTED_HEADWAY_NOT_MEASURABLE_OR_INVALID)
            continue
        candidate_window_start = first_mapping[0].c_departure_time
        candidate_window_end = last_mapping[0].c_departure_time
        if candidate_window_start > candidate_window_end:
            codes.add(PROTECTED_SOURCE_ORDER_VIOLATION)
            codes.add(PROTECTED_TRIP_COUNT_BELOW_FLOOR)
            codes.add(PROTECTED_HEADWAY_NOT_MEASURABLE_OR_INVALID)
            continue

        expected_direction = ContractDirection(regime.direction.value)
        inside = tuple(
            sorted(
                (
                    trip
                    for trip in candidate.exact_timetable
                    if trip.direction == expected_direction
                    and candidate_window_start <= trip.c_departure_time <= candidate_window_end
                ),
                key=lambda item: (item.c_departure_time, item.c_trip_id),
            )
        )
        if len(inside) < regime.minimum_future_c_trip_count:
            codes.add(PROTECTED_TRIP_COUNT_BELOW_FLOOR)
        if len(inside) < 2:
            codes.add(PROTECTED_HEADWAY_NOT_MEASURABLE_OR_INVALID)
            continue
        for earlier, later in zip(inside, inside[1:], strict=False):
            gap_seconds = later.c_departure_time - earlier.c_departure_time
            if gap_seconds <= 0 or gap_seconds % 60 != 0:
                codes.add(PROTECTED_HEADWAY_NOT_MEASURABLE_OR_INVALID)
                continue
            if gap_seconds // 60 > regime.maximum_future_c_headway_minutes:
                codes.add(PROTECTED_INTERNAL_HEADWAY_ABOVE_FLOOR)

    return _candidate_validation(authority, candidate, codes)


__all__ = [
    "PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE",
    "PROTECTED_SERVICE_FLOOR_VALIDATION_PROFILE",
    "ProtectedServiceFloorEnforcementAuthorityError",
    "build_protected_service_floor_enforcement_authority_v1",
    "protected_service_floor_enforcement_authority_is_valid_v1",
    "validate_candidate_against_protected_service_floors_v1",
]
