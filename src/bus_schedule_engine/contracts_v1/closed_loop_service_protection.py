"""Operational protected-service authority for exact closed-loop compilations."""

from __future__ import annotations

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


def build_closed_loop_service_protection_authority_v1(
    *,
    source_authority_profile: str,
    source_authority_fingerprint: str,
    windows: Sequence[ClosedLoopProtectedServiceWindowV1],
) -> ClosedLoopServiceProtectionAuthorityV1:
    """Build deterministic operational authority without inventing source-trip identity."""

    if not source_authority_profile.strip() or not source_authority_fingerprint.strip():
        raise ValueError("source authority profile and fingerprint are required")
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
    return ClosedLoopServiceProtectionAuthorityV1(
        source_authority_profile=source_authority_profile,
        source_authority_fingerprint=source_authority_fingerprint,
        translation_profile=CLOSED_LOOP_SERVICE_PROTECTION_TRANSLATION_PROFILE_V1,
        windows=ordered,
        translation_fingerprint=fingerprint,
        semantics=CLOSED_LOOP_OPERATIONAL_SERVICE_LEVEL_SEMANTICS_V1,
    )


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
    return build_closed_loop_service_protection_authority_v1(
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
class ClosedLoopServiceProtectionValidationV1:
    authority_status: str
    authority_fingerprint: str | None
    direction: str
    status: str
    violations: tuple[ClosedLoopServiceProtectionViolationV1, ...]
    validation_fingerprint: str

    @property
    def passed(self) -> bool:
        return self.status == "ACCEPTED"


def closed_loop_service_protection_status_v1(
    authority: ClosedLoopServiceProtectionAuthorityV1 | None,
) -> str:
    if authority is None or not authority.windows:
        return VALID_NO_ENFORCEABLE_WINDOW
    return ACTIVE_TRANSLATED_PROTECTED_WINDOWS


def _nearest_boundary_index(
    departures: tuple[int, ...],
    boundary: int,
    tolerance_seconds: int,
) -> int | None:
    eligible = tuple(
        (abs(departure - boundary), departure, index)
        for index, departure in enumerate(departures)
        if abs(departure - boundary) <= tolerance_seconds
    )
    return min(eligible)[2] if eligible else None


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


def validate_closed_loop_service_protection_v1(
    *,
    authority: ClosedLoopServiceProtectionAuthorityV1 | None,
    direction: str,
    exact_departures: Sequence[int],
) -> ClosedLoopServiceProtectionValidationV1:
    """Validate protected operational service using only exact same-direction timestamps."""

    if direction not in {"outbound", "inbound"}:
        raise ValueError("direction must be outbound or inbound")
    departures = tuple(exact_departures)
    if any(isinstance(item, bool) or not isinstance(item, int) for item in departures):
        raise ValueError("exact departures must be integer seconds")
    authority_status = closed_loop_service_protection_status_v1(authority)
    violations: list[ClosedLoopServiceProtectionViolationV1] = []
    windows = () if authority is None else authority.windows
    for window in (item for item in windows if item.direction == direction):
        tolerance_seconds = window.boundary_tolerance_minutes * 60
        start_index = _nearest_boundary_index(
            departures, window.protected_window_start, tolerance_seconds
        )
        end_index = _nearest_boundary_index(
            departures, window.protected_window_end, tolerance_seconds
        )

        if start_index is None:
            violations.append(_violation(window, PROTECTED_WINDOW_START_NOT_COVERED))
        if end_index is None:
            violations.append(_violation(window, PROTECTED_WINDOW_END_NOT_COVERED))
        if start_index is None or end_index is None:
            continue
        if start_index > end_index:
            violations.append(
                _violation(window, PROTECTED_WINDOW_SPAN_INVALID, observed_trip_count=0)
            )
            continue
        protected_departures = departures[start_index : end_index + 1]
        if len(protected_departures) < window.minimum_trip_count:
            violations.append(
                _violation(
                    window,
                    PROTECTED_TRIP_COUNT_BELOW_MINIMUM,
                    observed_trip_count=len(protected_departures),
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
            violations.append(
                _violation(
                    window,
                    rule,
                    observed_headway_minutes=gap_seconds / 60,
                    departure_i=departure_i,
                    departure_j=departure_j,
                )
            )

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
        }
    )
    return ClosedLoopServiceProtectionValidationV1(
        authority_status=authority_status,
        authority_fingerprint=None if authority is None else authority.translation_fingerprint,
        direction=direction,
        status="REJECTED" if violations else "ACCEPTED",
        violations=tuple(violations),
        validation_fingerprint=fingerprint,
    )


__all__ = [
    "ACTIVE_TRANSLATED_PROTECTED_WINDOWS",
    "CLOSED_LOOP_OPERATIONAL_SERVICE_LEVEL_SEMANTICS_V1",
    "CLOSED_LOOP_SERVICE_PROTECTION_TRANSLATION_PROFILE_V1",
    "CLOSED_LOOP_SERVICE_PROTECTION_VALIDATION_PROFILE_V1",
    "ClosedLoopProtectedServiceWindowV1",
    "ClosedLoopServiceProtectionAuthorityV1",
    "ClosedLoopServiceProtectionValidationV1",
    "ClosedLoopServiceProtectionViolationV1",
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
    "validate_closed_loop_service_protection_v1",
]
