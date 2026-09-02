from __future__ import annotations

import dataclasses

import pytest

from bus_schedule_engine.contracts_v1.closed_loop_service_protection import (
    ACTIVE_TRANSLATED_PROTECTED_WINDOWS,
    AUTHORITY_EXPECTED_TYPE,
    AUTHORITY_SEMANTICS_MISMATCH,
    AUTHORITY_SOURCE_FINGERPRINT_INVALID,
    AUTHORITY_TRANSLATION_FINGERPRINT_MISMATCH,
    AUTHORITY_TRANSLATION_PROFILE_MISMATCH,
    CLOSED_LOOP_OPERATIONAL_SERVICE_LEVEL_SEMANTICS_V1,
    CLOSED_LOOP_SERVICE_PROTECTION_TRANSLATION_PROFILE_V1,
    INVALID_TRANSLATED_PROTECTION_AUTHORITY,
    VALID_NO_ENFORCEABLE_WINDOW,
    ClosedLoopProtectedServiceWindowV1,
    build_closed_loop_service_protection_authority_v1,
    validate_closed_loop_service_protection_authority_v1,
    validate_closed_loop_service_protection_v1,
)


def _window(
    source_regime_id: str = "PEAK-OUTBOUND-1",
    *,
    start: int = 0,
    end: int = 600,
) -> ClosedLoopProtectedServiceWindowV1:
    return ClosedLoopProtectedServiceWindowV1(
        source_regime_id=source_regime_id,
        direction="outbound",
        protected_window_start=start,
        protected_window_end=end,
        boundary_tolerance_minutes=0,
        maximum_headway_minutes=10,
        minimum_trip_count=2,
    )


def _authority(*windows: ClosedLoopProtectedServiceWindowV1):
    return build_closed_loop_service_protection_authority_v1(
        source_authority_profile="synthetic_verified_6a2b",
        source_authority_fingerprint="a" * 64,
        windows=windows or (_window(),),
    )


def test_valid_authority_and_valid_empty_authority_have_stable_statuses() -> None:
    active = validate_closed_loop_service_protection_authority_v1(_authority())
    empty_authority = build_closed_loop_service_protection_authority_v1(
        source_authority_profile="synthetic_verified_6a2b",
        source_authority_fingerprint="a" * 64,
        windows=(),
    )
    empty = validate_closed_loop_service_protection_authority_v1(empty_authority)

    assert active.passed
    assert active.status == ACTIVE_TRANSLATED_PROTECTED_WINDOWS
    assert empty.passed
    assert empty.status == VALID_NO_ENFORCEABLE_WINDOW


def test_wrong_authority_object_type_is_rejected() -> None:
    validation = validate_closed_loop_service_protection_authority_v1(object())

    assert not validation.passed
    assert validation.status == INVALID_TRANSLATED_PROTECTION_AUTHORITY
    assert validation.errors == (AUTHORITY_EXPECTED_TYPE,)


def test_window_tampering_with_stale_translation_fingerprint_is_rejected() -> None:
    valid = _authority()
    tampered = dataclasses.replace(
        valid,
        windows=(dataclasses.replace(valid.windows[0], maximum_headway_minutes=11),),
    )

    validation = validate_closed_loop_service_protection_authority_v1(tampered)

    assert not validation.passed
    assert validation.status == INVALID_TRANSLATED_PROTECTION_AUTHORITY
    assert AUTHORITY_TRANSLATION_FINGERPRINT_MISMATCH in validation.errors


@pytest.mark.parametrize(
    ("changes", "expected_error"),
    [
        (
            {"translation_profile": "not-canonical"},
            AUTHORITY_TRANSLATION_PROFILE_MISMATCH,
        ),
        ({"semantics": "not-canonical"}, AUTHORITY_SEMANTICS_MISMATCH),
        ({"source_authority_fingerprint": "malformed"}, AUTHORITY_SOURCE_FINGERPRINT_INVALID),
    ],
)
def test_noncanonical_authority_metadata_is_rejected(changes, expected_error) -> None:
    validation = validate_closed_loop_service_protection_authority_v1(
        dataclasses.replace(_authority(), **changes)
    )

    assert not validation.passed
    assert expected_error in validation.errors


def test_unsorted_and_overlapping_windows_are_rejected() -> None:
    first = _window("FIRST", start=0, end=600)
    second = _window("SECOND", start=1200, end=1800)
    ordered = _authority(first, second)
    unsorted = dataclasses.replace(ordered, windows=tuple(reversed(ordered.windows)))
    overlapping = dataclasses.replace(
        ordered,
        windows=(first, _window("OVERLAP", start=600, end=900)),
    )

    unsorted_validation = validate_closed_loop_service_protection_authority_v1(unsorted)
    overlapping_validation = validate_closed_loop_service_protection_authority_v1(overlapping)

    assert not unsorted_validation.passed
    assert "AUTHORITY_WINDOWS_NOT_CANONICALLY_SORTED" in unsorted_validation.errors
    assert not overlapping_validation.passed
    assert "AUTHORITY_WINDOWS_OVERLAP" in overlapping_validation.errors


def test_existential_end_tolerance_accepts_later_eligible_departure() -> None:
    protected_start = 9 * 3600 + 50 * 60
    protected_end = 10 * 3600
    authority = _authority(
        dataclasses.replace(
            _window(start=protected_start, end=protected_end),
            boundary_tolerance_minutes=1,
            minimum_trip_count=3,
        )
    )

    validation = validate_closed_loop_service_protection_v1(
        authority=authority,
        direction="outbound",
        exact_departures=(protected_start, protected_end - 60, protected_end + 60),
    )

    assert validation.passed
    assert validation.violations == ()
    assert validation.witnesses[0].end_departure == protected_end + 60


def test_valid_pair_witness_uses_deterministic_boundary_tie_break() -> None:
    protected_start = 9 * 3600 + 50 * 60
    protected_end = 10 * 3600
    authority = _authority(
        dataclasses.replace(
            _window(start=protected_start, end=protected_end),
            boundary_tolerance_minutes=1,
            maximum_headway_minutes=15,
        )
    )
    departures = (protected_start, protected_end - 60, protected_end + 60)

    first = validate_closed_loop_service_protection_v1(
        authority=authority,
        direction="outbound",
        exact_departures=departures,
    )
    second = validate_closed_loop_service_protection_v1(
        authority=authority,
        direction="outbound",
        exact_departures=departures,
    )

    assert first.passed
    assert first.witnesses == second.witnesses
    assert first.validation_fingerprint == second.validation_fingerprint
    assert first.witnesses[0].end_departure == protected_end - 60
    assert first.witnesses[0].end_index == 1


def test_canonical_metadata_constants_are_not_test_substitutes() -> None:
    authority = _authority()

    assert authority.translation_profile == CLOSED_LOOP_SERVICE_PROTECTION_TRANSLATION_PROFILE_V1
    assert authority.semantics == CLOSED_LOOP_OPERATIONAL_SERVICE_LEVEL_SEMANTICS_V1
