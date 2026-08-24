"""Operational protected-service authority for exact closed-loop compilations."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from bus_schedule_engine.models import ProtectedServiceFloorEnforcementAuthorityV1
from bus_schedule_engine.protected_service_floor_enforcement import (
    protected_service_floor_enforcement_authority_is_valid_v1,
)

from .serialization import canonical_sha256

if TYPE_CHECKING:
    from .models import ScenarioBInput


CLOSED_LOOP_SERVICE_PROTECTION_TRANSLATION_PROFILE_V1 = (
    "closed_loop_service_protection_translation_v1"
)
CLOSED_LOOP_SERVICE_PROTECTION_VALIDATION_PROFILE_V1 = (
    "closed_loop_service_protection_validation_v1"
)
CLOSED_LOOP_OPERATIONAL_SERVICE_LEVEL_SEMANTICS_V1 = (
    "OPERATIONAL_EXACT_TIMESTAMPS_WITHOUT_SCENARIO_B_SOURCE_TRIP_IDENTITY"
)

ACTIVE_TRANSLATED_PROTECTED_WINDOWS = "ACTIVE_TRANSLATED_PROTECTED_WINDOWS"
VALID_NO_ENFORCEABLE_WINDOW = "VALID_NO_ENFORCEABLE_WINDOW"
INVALID_TRANSLATED_PROTECTION_AUTHORITY = "INVALID_TRANSLATED_PROTECTION_AUTHORITY"

AUTHORITY_EXPECTED_TYPE = "AUTHORITY_EXPECTED_TYPE"
AUTHORITY_TRANSLATION_PROFILE_MISMATCH = "AUTHORITY_TRANSLATION_PROFILE_MISMATCH"
AUTHORITY_SEMANTICS_MISMATCH = "AUTHORITY_SEMANTICS_MISMATCH"
AUTHORITY_SOURCE_PROFILE_MISSING = "AUTHORITY_SOURCE_PROFILE_MISSING"
AUTHORITY_SOURCE_FINGERPRINT_INVALID = "AUTHORITY_SOURCE_FINGERPRINT_INVALID"
AUTHORITY_TRANSLATION_FINGERPRINT_INVALID = "AUTHORITY_TRANSLATION_FINGERPRINT_INVALID"
AUTHORITY_WINDOWS_NOT_CANONICAL_TUPLE = "AUTHORITY_WINDOWS_NOT_CANONICAL_TUPLE"
AUTHORITY_WINDOW_TYPE_INVALID = "AUTHORITY_WINDOW_TYPE_INVALID"
AUTHORITY_WINDOW_STRUCTURAL_INVARIANT_FAILED = "AUTHORITY_WINDOW_STRUCTURAL_INVARIANT_FAILED"
AUTHORITY_WINDOWS_NOT_CANONICALLY_SORTED = "AUTHORITY_WINDOWS_NOT_CANONICALLY_SORTED"
AUTHORITY_SOURCE_REGIME_ID_DUPLICATE = "AUTHORITY_SOURCE_REGIME_ID_DUPLICATE"
AUTHORITY_WINDOWS_OVERLAP = "AUTHORITY_WINDOWS_OVERLAP"
AUTHORITY_TRANSLATION_FINGERPRINT_MISMATCH = "AUTHORITY_TRANSLATION_FINGERPRINT_MISMATCH"

PROTECTED_WINDOW_START_NOT_COVERED = "PROTECTED_WINDOW_START_NOT_COVERED"
PROTECTED_WINDOW_END_NOT_COVERED = "PROTECTED_WINDOW_END_NOT_COVERED"
PROTECTED_WINDOW_SPAN_INVALID = "PROTECTED_WINDOW_SPAN_INVALID"
PROTECTED_TRIP_COUNT_BELOW_MINIMUM = "PROTECTED_TRIP_COUNT_BELOW_MINIMUM"
PROTECTED_INTERNAL_HEADWAY_NOT_POSITIVE = "PROTECTED_INTERNAL_HEADWAY_NOT_POSITIVE"
PROTECTED_INTERNAL_HEADWAY_NOT_WHOLE_MINUTE = "PROTECTED_INTERNAL_HEADWAY_NOT_WHOLE_MINUTE"
PROTECTED_INTERNAL_HEADWAY_ABOVE_MAXIMUM = "PROTECTED_INTERNAL_HEADWAY_ABOVE_MAXIMUM"


@dataclass(frozen=True, slots=True)
class ClosedLoopProtectedServiceWindowV1:
    source_regime_id: str
    direction: str
    protected_window_start: int
    protected_window_end: int
    boundary_tolerance_minutes: int
    maximum_headway_minutes: int
    minimum_trip_count: int

    def __post_init__(self) -> None:
        if not self.source_regime_id.strip():
            raise ValueError("source_regime_id is required")
        if self.direction not in {"outbound", "inbound"}:
            raise ValueError("direction must be outbound or inbound")
        if self.protected_window_start < 0 or self.protected_window_end < 0:
            raise ValueError("protected window times must be non-negative")
        if self.protected_window_end < self.protected_window_start:
            raise ValueError("protected window end must not precede its start")
        if self.boundary_tolerance_minutes < 0:
            raise ValueError("boundary tolerance must be non-negative")
        if self.maximum_headway_minutes <= 0:
            raise ValueError("maximum headway must be positive")
        if self.minimum_trip_count < 2:
            raise ValueError("minimum protected trip count must be at least two")


def _window_sort_key(window: ClosedLoopProtectedServiceWindowV1) -> tuple[object, ...]:
    return (
        0 if window.direction == "outbound" else 1,
        window.protected_window_start,
        window.protected_window_end,
        window.source_regime_id,
    )


def _authority_payload(
    *,
    source_authority_profile: str,
    source_authority_fingerprint: str,
    windows: tuple[ClosedLoopProtectedServiceWindowV1, ...],
) -> dict[str, object]:
    return {
        "translation_profile": CLOSED_LOOP_SERVICE_PROTECTION_TRANSLATION_PROFILE_V1,
        "source_authority_profile": source_authority_profile,
        "source_authority_fingerprint": source_authority_fingerprint,
        "semantics": CLOSED_LOOP_OPERATIONAL_SERVICE_LEVEL_SEMANTICS_V1,
        "windows": [asdict(window) for window in windows],
    }


@dataclass(frozen=True, slots=True)
class ClosedLoopServiceProtectionAuthorityV1:
    source_authority_profile: str
    source_authority_fingerprint: str
    translation_profile: str
    windows: tuple[ClosedLoopProtectedServiceWindowV1, ...]
    translation_fingerprint: str
    semantics: str

    @property
    def has_enforceable_windows(self) -> bool:
        return bool(self.windows)

    @property
    def status(self) -> str:
        return (
            ACTIVE_TRANSLATED_PROTECTED_WINDOWS
            if self.has_enforceable_windows
            else VALID_NO_ENFORCEABLE_WINDOW
        )


@dataclass(frozen=True, slots=True)
class ClosedLoopServiceProtectionAuthorityValidationV1:
    status: str
    authority_fingerprint: str | None
    errors: tuple[str, ...]
    validation_fingerprint: str

    @property
    def passed(self) -> bool:
        return self.status != INVALID_TRANSLATED_PROTECTION_AUTHORITY


def _is_sha256_fingerprint(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def validate_closed_loop_service_protection_authority_v1(
    authority: object | None,
) -> ClosedLoopServiceProtectionAuthorityValidationV1:
    """Verify translated authority facts without claiming current Scenario-B provenance."""

    errors: list[str] = []
    authority_fingerprint: str | None = None
    if authority is None:
        status = VALID_NO_ENFORCEABLE_WINDOW
    elif not isinstance(authority, ClosedLoopServiceProtectionAuthorityV1):
        errors.append(AUTHORITY_EXPECTED_TYPE)
        status = INVALID_TRANSLATED_PROTECTION_AUTHORITY
    else:
        authority_fingerprint = authority.translation_fingerprint
        if authority.translation_profile != CLOSED_LOOP_SERVICE_PROTECTION_TRANSLATION_PROFILE_V1:
            errors.append(AUTHORITY_TRANSLATION_PROFILE_MISMATCH)
        if authority.semantics != CLOSED_LOOP_OPERATIONAL_SERVICE_LEVEL_SEMANTICS_V1:
            errors.append(AUTHORITY_SEMANTICS_MISMATCH)
        if not isinstance(authority.source_authority_profile, str) or not (
            authority.source_authority_profile.strip()
        ):
            errors.append(AUTHORITY_SOURCE_PROFILE_MISSING)
        if not _is_sha256_fingerprint(authority.source_authority_fingerprint):
            errors.append(AUTHORITY_SOURCE_FINGERPRINT_INVALID)
        if not _is_sha256_fingerprint(authority.translation_fingerprint):
            errors.append(AUTHORITY_TRANSLATION_FINGERPRINT_INVALID)

        windows_are_tuple = isinstance(authority.windows, tuple)
        if not windows_are_tuple:
            errors.append(AUTHORITY_WINDOWS_NOT_CANONICAL_TUPLE)
        windows = authority.windows if windows_are_tuple else ()
        windows_have_expected_type = all(
            isinstance(window, ClosedLoopProtectedServiceWindowV1) for window in windows
        )
        if not windows_have_expected_type:
            errors.append(AUTHORITY_WINDOW_TYPE_INVALID)
        structural_errors = False
        if windows_have_expected_type:
            for window in windows:
                try:
                    window.__post_init__()
                except (TypeError, ValueError, AttributeError):
                    structural_errors = True
                    break
        if structural_errors:
            errors.append(AUTHORITY_WINDOW_STRUCTURAL_INVARIANT_FAILED)

        windows_are_structurally_usable = (
            windows_are_tuple and windows_have_expected_type and not structural_errors
        )
        if windows_are_structurally_usable:
            if tuple(sorted(windows, key=_window_sort_key)) != windows:
                errors.append(AUTHORITY_WINDOWS_NOT_CANONICALLY_SORTED)
            if len({(item.direction, item.source_regime_id) for item in windows}) != len(windows):
                errors.append(AUTHORITY_SOURCE_REGIME_ID_DUPLICATE)
            previous_end: dict[str, int] = {}
            for window in windows:
                prior = previous_end.get(window.direction)
                if prior is not None and window.protected_window_start <= prior:
                    errors.append(AUTHORITY_WINDOWS_OVERLAP)
                    break
                previous_end[window.direction] = window.protected_window_end
            if (
                isinstance(authority.source_authority_profile, str)
                and isinstance(authority.source_authority_fingerprint, str)
                and canonical_sha256(
                    _authority_payload(
                        source_authority_profile=authority.source_authority_profile,
                        source_authority_fingerprint=authority.source_authority_fingerprint,
                        windows=windows,
                    )
                )
                != authority.translation_fingerprint
            ):
                errors.append(AUTHORITY_TRANSLATION_FINGERPRINT_MISMATCH)

        errors = list(dict.fromkeys(errors))
        status = (
            INVALID_TRANSLATED_PROTECTION_AUTHORITY
            if errors
            else (
                ACTIVE_TRANSLATED_PROTECTED_WINDOWS
                if authority.windows
                else VALID_NO_ENFORCEABLE_WINDOW
            )
        )

    validation_fingerprint = canonical_sha256(
        {
            "profile": CLOSED_LOOP_SERVICE_PROTECTION_VALIDATION_PROFILE_V1,
            "authority_fingerprint": authority_fingerprint,
            "status": status,
            "errors": errors,
        }
    )
    return ClosedLoopServiceProtectionAuthorityValidationV1(
        status=status,
        authority_fingerprint=authority_fingerprint,
        errors=tuple(errors),
        validation_fingerprint=validation_fingerprint,
    )


def build_closed_loop_service_protection_authority_v1(
    *,
    source_authority_profile: str,
    source_authority_fingerprint: str,
    windows: Sequence[ClosedLoopProtectedServiceWindowV1],
) -> ClosedLoopServiceProtectionAuthorityV1:
    """Build deterministic operational authority without inventing source-trip identity."""

    if not source_authority_profile.strip() or not source_authority_fingerprint.strip():
        raise ValueError("source authority profile and fingerprint are required")
    if not _is_sha256_fingerprint(source_authority_fingerprint):
        raise ValueError("source authority fingerprint must be a SHA-256 fingerprint")
    ordered = tuple(sorted(windows, key=_window_sort_key))
    if len({(item.direction, item.source_regime_id) for item in ordered}) != len(ordered):
        raise ValueError("protected source regime IDs must be unique within each direction")
    previous_end: dict[str, int] = {}
    for window in ordered:
        prior = previous_end.get(window.direction)
        if prior is not None and window.protected_window_start <= prior:
            raise ValueError("protected windows must not overlap within a direction")
        previous_end[window.direction] = window.protected_window_end
    fingerprint = canonical_sha256(
        _authority_payload(
            source_authority_profile=source_authority_profile,
            source_authority_fingerprint=source_authority_fingerprint,
            windows=ordered,
        )
    )
    authority = ClosedLoopServiceProtectionAuthorityV1(
        source_authority_profile=source_authority_profile,
        source_authority_fingerprint=source_authority_fingerprint,
        translation_profile=CLOSED_LOOP_SERVICE_PROTECTION_TRANSLATION_PROFILE_V1,
        windows=ordered,
        translation_fingerprint=fingerprint,
        semantics=CLOSED_LOOP_OPERATIONAL_SERVICE_LEVEL_SEMANTICS_V1,
    )
    if not validate_closed_loop_service_protection_authority_v1(authority).passed:
        raise ValueError("built closed-loop service protection authority failed self-validation")
    return authority


def translate_protected_service_floor_authority_v1(
    authority: ProtectedServiceFloorEnforcementAuthorityV1,
    *,
    scenario_b: ScenarioBInput | None = None,
) -> ClosedLoopServiceProtectionAuthorityV1:
    """Translate verified 6A2B facts into enforceable operational timestamp windows.

    When Scenario B is provided, the canonical 6A2B verifier is authoritative. Without it,
    callers are responsible for supplying an authority already verified at its source boundary.
    """

    if not isinstance(authority, ProtectedServiceFloorEnforcementAuthorityV1):
        raise TypeError("authority must be ProtectedServiceFloorEnforcementAuthorityV1")
    if scenario_b is not None and not protected_service_floor_enforcement_authority_is_valid_v1(
        authority, scenario_b
    ):
        raise ValueError("source protected-service authority failed canonical verification")
    translated = build_closed_loop_service_protection_authority_v1(
        source_authority_profile=authority.enforcement_profile,
        source_authority_fingerprint=authority.enforcement_fingerprint,
        windows=tuple(
            ClosedLoopProtectedServiceWindowV1(
                source_regime_id=regime.regime_id,
                direction=regime.direction.value,
                protected_window_start=regime.protected_window_start,
                protected_window_end=regime.protected_window_end,
                boundary_tolerance_minutes=regime.future_boundary_tolerance_minutes,
                maximum_headway_minutes=regime.maximum_future_c_headway_minutes,
                minimum_trip_count=regime.minimum_future_c_trip_count,
            )
            for regime in authority.protected_regimes
        ),
    )
    if not validate_closed_loop_service_protection_authority_v1(translated).passed:
        raise ValueError("translated closed-loop authority failed internal verification")
    return translated


@dataclass(frozen=True, slots=True)
class ClosedLoopServiceProtectionViolationV1:
    direction: str
    protected_window_start: int
    protected_window_end: int
    source_regime_id: str
    violated_rule: str
    observed_trip_count: int | None = None
    observed_headway_minutes: float | None = None
    departure_i: int | None = None
    departure_j: int | None = None


@dataclass(frozen=True, slots=True)
class ClosedLoopServiceProtectionWitnessV1:
    direction: str
    source_regime_id: str
    start_departure: int
    end_departure: int
    start_index: int
    end_index: int


@dataclass(frozen=True, slots=True)
class ClosedLoopServiceProtectionValidationV1:
    authority_status: str
    authority_fingerprint: str | None
    direction: str
    status: str
    violations: tuple[ClosedLoopServiceProtectionViolationV1, ...]
    witnesses: tuple[ClosedLoopServiceProtectionWitnessV1, ...]
    validation_fingerprint: str

    @property
    def passed(self) -> bool:
        return self.status == "ACCEPTED"


def closed_loop_service_protection_status_v1(
    authority: ClosedLoopServiceProtectionAuthorityV1 | None,
) -> str:
    return validate_closed_loop_service_protection_authority_v1(authority).status


def _eligible_boundary_indices(
    departures: tuple[int, ...],
    boundary: int,
    tolerance_seconds: int,
) -> tuple[int, ...]:
    return tuple(
        index
        for index, departure in enumerate(departures)
        if abs(departure - boundary) <= tolerance_seconds
    )


def _pair_order_key(
    departures: tuple[int, ...],
    window: ClosedLoopProtectedServiceWindowV1,
    start_index: int,
    end_index: int,
) -> tuple[int, ...]:
    start_departure = departures[start_index]
    end_departure = departures[end_index]
    start_deviation = abs(start_departure - window.protected_window_start)
    end_deviation = abs(end_departure - window.protected_window_end)
    return (
        start_deviation + end_deviation,
        max(start_deviation, end_deviation),
        start_departure,
        end_departure,
        start_index,
        end_index,
    )


def _violation(
    window: ClosedLoopProtectedServiceWindowV1,
    rule: str,
    *,
    observed_trip_count: int | None = None,
    observed_headway_minutes: float | None = None,
    departure_i: int | None = None,
    departure_j: int | None = None,
) -> ClosedLoopServiceProtectionViolationV1:
    return ClosedLoopServiceProtectionViolationV1(
        direction=window.direction,
        protected_window_start=window.protected_window_start,
        protected_window_end=window.protected_window_end,
        source_regime_id=window.source_regime_id,
        violated_rule=rule,
        observed_trip_count=observed_trip_count,
        observed_headway_minutes=observed_headway_minutes,
        departure_i=departure_i,
        departure_j=departure_j,
    )


def _validate_trusted_closed_loop_service_protection_v1(
    *,
    authority: ClosedLoopServiceProtectionAuthorityV1 | None,
    direction: str,
    exact_departures: Sequence[int],
    authority_validation: ClosedLoopServiceProtectionAuthorityValidationV1,
) -> ClosedLoopServiceProtectionValidationV1:
    if direction not in {"outbound", "inbound"}:
        raise ValueError("direction must be outbound or inbound")
    departures = tuple(exact_departures)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in departures):
        raise ValueError("exact departures must be integer seconds")
    if authority_validation.authority_fingerprint != (
        None if authority is None else authority.translation_fingerprint
    ):
        raise ValueError("authority validation does not match supplied authority")
    authority_status = authority_validation.status
    violations: list[ClosedLoopServiceProtectionViolationV1] = []
    witnesses: list[ClosedLoopServiceProtectionWitnessV1] = []
    windows = () if authority is None or not authority_validation.passed else authority.windows
    for window in (item for item in windows if item.direction == direction):
        tolerance_seconds = window.boundary_tolerance_minutes * 60
        start_indices = _eligible_boundary_indices(
            departures, window.protected_window_start, tolerance_seconds
        )
        end_indices = _eligible_boundary_indices(
            departures, window.protected_window_end, tolerance_seconds
        )

        if not start_indices:
            violations.append(_violation(window, PROTECTED_WINDOW_START_NOT_COVERED))
        if not end_indices:
            violations.append(_violation(window, PROTECTED_WINDOW_END_NOT_COVERED))
        if not start_indices or not end_indices:
            continue

        all_pairs = tuple(
            sorted(
                (
                    (start_index, end_index)
                    for start_index in start_indices
                    for end_index in end_indices
                ),
                key=lambda pair: _pair_order_key(departures, window, *pair),
            )
        )
        legal_pairs = tuple(pair for pair in all_pairs if pair[0] <= pair[1])
        if not legal_pairs:
            start_index, end_index = all_pairs[0]
            violations.append(
                _violation(
                    window,
                    PROTECTED_WINDOW_SPAN_INVALID,
                    observed_trip_count=0,
                    departure_i=departures[start_index],
                    departure_j=departures[end_index],
                )
            )
            continue

        pair_evaluations: list[
            tuple[int, int, tuple[ClosedLoopServiceProtectionViolationV1, ...]]
        ] = []
        for start_index, end_index in legal_pairs:
            pair_violations: list[ClosedLoopServiceProtectionViolationV1] = []
            protected_departures = departures[start_index : end_index + 1]
            if len(protected_departures) < window.minimum_trip_count:
                pair_violations.append(
                    _violation(
                        window,
                        PROTECTED_TRIP_COUNT_BELOW_MINIMUM,
                        observed_trip_count=len(protected_departures),
                        departure_i=departures[start_index],
                        departure_j=departures[end_index],
                    )
                )
            for departure_i, departure_j in zip(
                protected_departures, protected_departures[1:], strict=False
            ):
                gap_seconds = departure_j - departure_i
                if gap_seconds <= 0:
                    rule = PROTECTED_INTERNAL_HEADWAY_NOT_POSITIVE
                elif gap_seconds % 60:
                    rule = PROTECTED_INTERNAL_HEADWAY_NOT_WHOLE_MINUTE
                elif gap_seconds // 60 > window.maximum_headway_minutes:
                    rule = PROTECTED_INTERNAL_HEADWAY_ABOVE_MAXIMUM
                else:
                    continue
                pair_violations.append(
                    _violation(
                        window,
                        rule,
                        observed_headway_minutes=gap_seconds / 60,
                        departure_i=departure_i,
                        departure_j=departure_j,
                    )
                )
            pair_evaluations.append((start_index, end_index, tuple(pair_violations)))

        valid_pairs = tuple(item for item in pair_evaluations if not item[2])
        start_index, end_index, selected_violations = (
            valid_pairs[0] if valid_pairs else pair_evaluations[0]
        )
        if valid_pairs:
            witnesses.append(
                ClosedLoopServiceProtectionWitnessV1(
                    direction=window.direction,
                    source_regime_id=window.source_regime_id,
                    start_departure=departures[start_index],
                    end_departure=departures[end_index],
                    start_index=start_index,
                    end_index=end_index,
                )
            )
        else:
            violations.extend(selected_violations)

    violation_payload = [asdict(item) for item in violations]
    fingerprint = canonical_sha256(
        {
            "profile": CLOSED_LOOP_SERVICE_PROTECTION_VALIDATION_PROFILE_V1,
            "authority_status": authority_status,
            "authority_fingerprint": (
                None if authority is None else authority.translation_fingerprint
            ),
            "direction": direction,
            "exact_departures": list(departures),
            "violations": violation_payload,
            "witnesses": [asdict(item) for item in witnesses],
        }
    )
    return ClosedLoopServiceProtectionValidationV1(
        authority_status=authority_status,
        authority_fingerprint=None if authority is None else authority.translation_fingerprint,
        direction=direction,
        status=(
            "REJECTED"
            if violations or authority_status == INVALID_TRANSLATED_PROTECTION_AUTHORITY
            else "ACCEPTED"
        ),
        violations=tuple(violations),
        witnesses=tuple(witnesses),
        validation_fingerprint=fingerprint,
    )


def validate_closed_loop_service_protection_v1(
    *,
    authority: ClosedLoopServiceProtectionAuthorityV1 | None,
    direction: str,
    exact_departures: Sequence[int],
) -> ClosedLoopServiceProtectionValidationV1:
    """Validate protected operational service using only exact same-direction timestamps."""

    return _validate_trusted_closed_loop_service_protection_v1(
        authority=authority,
        direction=direction,
        exact_departures=exact_departures,
        authority_validation=validate_closed_loop_service_protection_authority_v1(authority),
    )


__all__ = [
    "ACTIVE_TRANSLATED_PROTECTED_WINDOWS",
    "AUTHORITY_SEMANTICS_MISMATCH",
    "AUTHORITY_SOURCE_FINGERPRINT_INVALID",
    "AUTHORITY_TRANSLATION_PROFILE_MISMATCH",
    "AUTHORITY_TRANSLATION_FINGERPRINT_MISMATCH",
    "CLOSED_LOOP_OPERATIONAL_SERVICE_LEVEL_SEMANTICS_V1",
    "CLOSED_LOOP_SERVICE_PROTECTION_TRANSLATION_PROFILE_V1",
    "CLOSED_LOOP_SERVICE_PROTECTION_VALIDATION_PROFILE_V1",
    "ClosedLoopProtectedServiceWindowV1",
    "ClosedLoopServiceProtectionAuthorityV1",
    "ClosedLoopServiceProtectionAuthorityValidationV1",
    "ClosedLoopServiceProtectionValidationV1",
    "ClosedLoopServiceProtectionViolationV1",
    "ClosedLoopServiceProtectionWitnessV1",
    "INVALID_TRANSLATED_PROTECTION_AUTHORITY",
    "PROTECTED_INTERNAL_HEADWAY_ABOVE_MAXIMUM",
    "PROTECTED_INTERNAL_HEADWAY_NOT_POSITIVE",
    "PROTECTED_INTERNAL_HEADWAY_NOT_WHOLE_MINUTE",
    "PROTECTED_TRIP_COUNT_BELOW_MINIMUM",
    "PROTECTED_WINDOW_END_NOT_COVERED",
    "PROTECTED_WINDOW_SPAN_INVALID",
    "PROTECTED_WINDOW_START_NOT_COVERED",
    "VALID_NO_ENFORCEABLE_WINDOW",
    "build_closed_loop_service_protection_authority_v1",
    "closed_loop_service_protection_status_v1",
    "translate_protected_service_floor_authority_v1",
    "validate_closed_loop_service_protection_authority_v1",
    "validate_closed_loop_service_protection_v1",
]
