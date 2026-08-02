"""Deterministic no-solver review for partially authorized Scenario B timetables."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum, StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from statistics import mean, median

from .contracts_v1.models import ContractDirection, DepartureTerminal, ExactTimetableTrip
from .importer import ImportedWorkbook, import_workbook
from .input_authority import (
    SOURCE_VEHICLE_ASSIGNMENT_NOT_SUPPLIED,
    CapabilityReadinessStatusV1,
    CapabilityReadinessV1,
    DataAuthorityCapabilityV1,
    LayeredDataAuthorityReadinessV1,
    assess_layered_data_authority_v1,
)
from .models import Direction, TimetableAuthorityStatusV1, Trip
from .protected_service_floor import (
    derive_exact_timetable_service_regimes_v1,
    protected_service_floor_policy_from_workbook_v1,
)
from .time_utils import format_hhmm

PARTIAL_REVIEW_PROFILE_V1 = "m6a2f_partial_timetable_review_v1"
DATA_AUTHORITY_REVIEW_JSON_FILENAME = "data-authority-review.json"
DATA_AUTHORITY_REVIEW_MARKDOWN_FILENAME = "data-authority-review.md"
CORE_TIMETABLE_IMPORT_REQUIRED = "CORE_TIMETABLE_IMPORT_REQUIRED"
DECLARED_TRIP_COUNT_MISMATCH = "DECLARED_TRIP_COUNT_MISMATCH"
DECLARED_ENDPOINT_MISMATCH = "DECLARED_ENDPOINT_MISMATCH"
DUPLICATE_TIMETABLE_TRIP_ID = "DUPLICATE_TIMETABLE_TRIP_ID"
DIRECTIONAL_SOURCE_ORDER_NOT_CHRONOLOGICAL = "DIRECTIONAL_SOURCE_ORDER_NOT_CHRONOLOGICAL"
COMBINED_DIRECTION_NOT_ALLOWED_FOR_TIMETABLE_TRIP = (
    "COMBINED_DIRECTION_NOT_ALLOWED_FOR_TIMETABLE_TRIP"
)
UNKNOWN_DEPARTURE_TERMINAL = "UNKNOWN_DEPARTURE_TERMINAL"
DIRECTION_TERMINAL_MISMATCH = "DIRECTION_TERMINAL_MISMATCH"
TRIP_RUNTIME_NON_POSITIVE_OR_NON_INTEGER_MINUTE = "TRIP_RUNTIME_NON_POSITIVE_OR_NON_INTEGER_MINUTE"
TRIP_RUNTIME_OUTSIDE_ALLOWED_RANGE = "TRIP_RUNTIME_OUTSIDE_ALLOWED_RANGE"
SOURCE_ASSIGNMENT_PARTIAL = "SOURCE_ASSIGNMENT_PARTIAL"
SOURCE_ASSIGNMENT_OVERLAP_FREE = "SOURCE_ASSIGNMENT_OVERLAP_FREE"
SOURCE_ASSIGNMENT_OVERLAP_DETECTED = "SOURCE_ASSIGNMENT_OVERLAP_DETECTED"
SOURCE_ASSIGNMENT_TERMINAL_DISCONTINUITY = "SOURCE_ASSIGNMENT_TERMINAL_DISCONTINUITY"
SOURCE_ASSIGNMENT_TERMINAL_DISCONTINUITY_DETECTED = (
    "SOURCE_ASSIGNMENT_TERMINAL_DISCONTINUITY_DETECTED"
)
NO_SOLVER_CALLED = "NO_SOLVER_CALLED"
RAW_PASSENGER_ROWS_EXCLUDED = "RAW_PASSENGER_ROWS_EXCLUDED"
NO_AUTHORITY_INFERRED = "NO_AUTHORITY_INFERRED"
EXTERNAL_APPROVAL_NOT_GRANTED_OR_REVOKED = "EXTERNAL_APPROVAL_NOT_GRANTED_OR_REVOKED"
DRIVER_DEPOT_DEADHEAD_MAINTENANCE_OUTSIDE_SCOPE = "DRIVER_DEPOT_DEADHEAD_MAINTENANCE_OUTSIDE_SCOPE"

_FORBIDDEN_PAYLOAD_FIELD_FRAGMENTS = (
    "workbook_path",
    "output_path",
    "machine_identity",
    "raw_passenger",
    "passenger_count",
    "wall_clock",
)


class PartialTimetableReviewStatusV1(StrEnum):
    REVIEW_COMPLETE = "REVIEW_COMPLETE"
    CORE_TIMETABLE_NOT_REVIEWABLE = "CORE_TIMETABLE_NOT_REVIEWABLE"


class TurnaroundComplianceStatusV1(StrEnum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    NOT_EVALUATED = "NOT_EVALUATED"


_EXIT_CODE_BY_STATUS = {
    PartialTimetableReviewStatusV1.REVIEW_COMPLETE: 0,
    PartialTimetableReviewStatusV1.CORE_TIMETABLE_NOT_REVIEWABLE: 2,
}


@dataclass(frozen=True, slots=True)
class PartialTimetableReviewV1:
    profile: str
    source_id: str
    review_status: PartialTimetableReviewStatusV1
    timetable_authority: Mapping[str, object]
    capability_readiness: Mapping[str, object]
    missing_authority_codes_by_capability: Mapping[str, object]
    route_and_terminal_facts: Mapping[str, object]
    exact_timetable_consistency: Mapping[str, object]
    runtime_review: Mapping[str, object]
    headway_and_regime_review: Mapping[str, object]
    source_vehicle_cycle_review: Mapping[str, object]
    turnaround_review: Mapping[str, object]
    demand_authority_review: Mapping[str, object]
    fleet_and_terminal_authority: Mapping[str, object]
    optimization_eligibility: Mapping[str, object]
    limitations: tuple[str, ...]
    review_fingerprint: str


@dataclass(frozen=True, slots=True)
class DataAuthorityReviewPackageV1:
    review: PartialTimetableReviewV1
    json_bytes: bytes
    markdown_bytes: bytes
    exit_code: int


def _jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("partial review payload may not contain non-finite numbers")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported partial review payload type: {value.__class__.__name__}")


def partial_timetable_review_to_dict_v1(
    review: PartialTimetableReviewV1,
) -> dict[str, object]:
    if not isinstance(review, PartialTimetableReviewV1):
        raise TypeError("review must be a PartialTimetableReviewV1")
    payload = _jsonable(review)
    if not isinstance(payload, dict):
        raise TypeError("partial review serialization did not produce an object")
    return payload


def _canonical_json_bytes(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def calculate_partial_timetable_review_fingerprint_v1(
    review: PartialTimetableReviewV1,
) -> str:
    payload = partial_timetable_review_to_dict_v1(review)
    payload.pop("review_fingerprint", None)
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _is_absolute_path_string(value: str) -> bool:
    candidate = value.strip()
    return bool(candidate) and (
        PureWindowsPath(candidate).is_absolute() or PurePosixPath(candidate).is_absolute()
    )


def _payload_respects_privacy(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).casefold()
            if any(fragment in normalized_key for fragment in _FORBIDDEN_PAYLOAD_FIELD_FRAGMENTS):
                return False
            if not _payload_respects_privacy(item):
                return False
        return True
    if isinstance(value, (tuple, list)):
        return all(_payload_respects_privacy(item) for item in value)
    if isinstance(value, str):
        return not _is_absolute_path_string(value)
    return True


def verify_partial_timetable_review_fingerprint_v1(review: PartialTimetableReviewV1) -> bool:
    if not isinstance(review, PartialTimetableReviewV1):
        return False
    if review.profile != PARTIAL_REVIEW_PROFILE_V1 or not re.fullmatch(
        r"[0-9a-f]{64}", review.review_fingerprint
    ):
        return False
    payload = partial_timetable_review_to_dict_v1(review)
    return _payload_respects_privacy(payload) and (
        calculate_partial_timetable_review_fingerprint_v1(review) == review.review_fingerprint
    )


def verify_partial_timetable_review_json_bytes_v1(content: bytes) -> bool:
    try:
        payload = json.loads(content)
        if not isinstance(payload, dict) or payload.get("profile") != PARTIAL_REVIEW_PROFILE_V1:
            return False
        fingerprint = payload.pop("review_fingerprint")
        if not isinstance(fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            return False
        expected = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
        restored = {**payload, "review_fingerprint": fingerprint}
        return (
            fingerprint == expected
            and _payload_respects_privacy(restored)
            and content == _canonical_json_bytes(restored)
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def serialize_partial_timetable_review_v1(review: PartialTimetableReviewV1) -> bytes:
    if not verify_partial_timetable_review_fingerprint_v1(review):
        raise ValueError("partial timetable review fingerprint verification failed")
    content = _canonical_json_bytes(partial_timetable_review_to_dict_v1(review))
    if not verify_partial_timetable_review_json_bytes_v1(content):
        raise ValueError("partial timetable review canonical JSON integrity failed")
    return content


def _time_value(seconds: int | None) -> Mapping[str, object] | None:
    if seconds is None:
        return None
    return {"seconds": seconds, "hhmm": format_hhmm(seconds)}


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 3)


def _contract_direction(direction: Direction) -> ContractDirection | None:
    if direction == Direction.TERMINAL_1_TO_2:
        return ContractDirection.OUTBOUND
    if direction == Direction.TERMINAL_2_TO_1:
        return ContractDirection.INBOUND
    return None


def _departure_terminal(imported: ImportedWorkbook, trip: Trip) -> DepartureTerminal | None:
    parameters = imported.parameters_b
    if trip.departure_terminal == parameters.terminal_1_name:
        return DepartureTerminal.TERMINAL_1
    if trip.departure_terminal == parameters.terminal_2_name:
        return DepartureTerminal.TERMINAL_2
    return None


def _runtime_minutes(imported: ImportedWorkbook, trip: Trip) -> float:
    arrival = trip.resolved_arrival_seconds(imported.parameters_b.default_trip_runtime_minutes)
    return (arrival - trip.departure_seconds) / 60


def _exact_trips_and_issues(
    imported: ImportedWorkbook,
) -> tuple[
    tuple[ExactTimetableTrip, ...],
    tuple[Mapping[str, object], ...],
    tuple[Mapping[str, object], ...],
]:
    parameters = imported.parameters_b
    exact: list[ExactTimetableTrip] = []
    terminal_issues: list[Mapping[str, object]] = []
    runtime_issues: list[Mapping[str, object]] = []
    for trip in imported.trips_b:
        direction = _contract_direction(trip.direction)
        terminal = _departure_terminal(imported, trip)
        if direction is None:
            terminal_issues.append(
                {
                    "code": COMBINED_DIRECTION_NOT_ALLOWED_FOR_TIMETABLE_TRIP,
                    "trip_id": trip.trip_id,
                }
            )
        if terminal is None:
            terminal_issues.append({"code": UNKNOWN_DEPARTURE_TERMINAL, "trip_id": trip.trip_id})
        expected_terminal = (
            DepartureTerminal.TERMINAL_1
            if direction == ContractDirection.OUTBOUND
            else DepartureTerminal.TERMINAL_2
            if direction == ContractDirection.INBOUND
            else None
        )
        if terminal is not None and expected_terminal is not None and terminal != expected_terminal:
            terminal_issues.append({"code": DIRECTION_TERMINAL_MISMATCH, "trip_id": trip.trip_id})

        runtime = _runtime_minutes(imported, trip)
        if runtime <= 0 or not float(runtime).is_integer():
            runtime_issues.append(
                {
                    "code": TRIP_RUNTIME_NON_POSITIVE_OR_NON_INTEGER_MINUTE,
                    "trip_id": trip.trip_id,
                    "runtime_minutes": _round(runtime),
                }
            )
        elif not parameters.accepts_trip_runtime(int(runtime)):
            runtime_issues.append(
                {
                    "code": TRIP_RUNTIME_OUTSIDE_ALLOWED_RANGE,
                    "trip_id": trip.trip_id,
                    "runtime_minutes": int(runtime),
                    "allowed_minimum_minutes": min(parameters.runtime_options),
                    "allowed_maximum_minutes": max(parameters.runtime_options),
                }
            )
        if direction is None or terminal is None:
            continue
        exact.append(
            ExactTimetableTrip(
                trip_id=trip.trip_id,
                direction=direction,
                departure_terminal=terminal,
                departure_time=trip.departure_seconds,
                arrival_time=trip.resolved_arrival_seconds(parameters.default_trip_runtime_minutes),
                runtime_minutes=(
                    int(runtime)
                    if runtime > 0 and float(runtime).is_integer()
                    else parameters.default_trip_runtime_minutes
                ),
                vehicle_assignment=trip.vehicle_id,
            )
        )
    return (
        tuple(
            sorted(
                exact, key=lambda item: (item.departure_time, item.direction.value, item.trip_id)
            )
        ),
        tuple(sorted(terminal_issues, key=lambda item: (str(item["code"]), str(item["trip_id"])))),
        tuple(sorted(runtime_issues, key=lambda item: (str(item["code"]), str(item["trip_id"])))),
    )


def _direction_key(direction: Direction) -> str:
    if direction == Direction.TERMINAL_1_TO_2:
        return ContractDirection.OUTBOUND.value
    if direction == Direction.TERMINAL_2_TO_1:
        return ContractDirection.INBOUND.value
    return ContractDirection.COMBINED.value


def _headway_review(imported: ImportedWorkbook) -> Mapping[str, object]:
    output: dict[str, object] = {}
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        trips = tuple(
            sorted(
                (trip for trip in imported.trips_b if trip.direction == direction),
                key=lambda trip: (trip.departure_seconds, trip.trip_id),
            )
        )
        headways = tuple(
            (right.departure_seconds - left.departure_seconds) / 60
            for left, right in zip(trips, trips[1:], strict=False)
        )
        output[_direction_key(direction)] = {
            "trip_count": len(trips),
            "first_departure": _time_value(trips[0].departure_seconds) if trips else None,
            "last_departure": _time_value(trips[-1].departure_seconds) if trips else None,
            "headway_sequence_minutes": tuple(_round(value) for value in headways),
            "minimum_headway_minutes": _round(min(headways)) if headways else None,
            "median_headway_minutes": _round(median(headways)) if headways else None,
            "mean_headway_minutes": _round(mean(headways)) if headways else None,
            "maximum_headway_minutes": _round(max(headways)) if headways else None,
        }
    return output


def _regime_review(
    imported: ImportedWorkbook,
    exact_trips: tuple[ExactTimetableTrip, ...],
) -> tuple[Mapping[str, object], ...]:
    policy = protected_service_floor_policy_from_workbook_v1(imported)
    regimes = derive_exact_timetable_service_regimes_v1(exact_trips, policy)
    return tuple(
        {
            "regime_id": regime.regime_id,
            "direction": regime.direction.value,
            "first_departure": _time_value(regime.first_departure),
            "last_departure": _time_value(regime.last_departure),
            "trip_count": regime.trip_count,
            "internal_headway_sequence_minutes": tuple(
                _round(value) for value in regime.internal_headway_sequence
            ),
            "minimum_headway_minutes": _round(regime.minimum_b_headway),
            "representative_headway_minutes": _round(regime.representative_b_headway),
            "maximum_headway_minutes": _round(regime.maximum_b_headway),
            "transition_headway_before_minutes": _round(regime.transition_headway_before),
            "transition_headway_after_minutes": _round(regime.transition_headway_after),
            "regularity_classification": regime.regularity_classification,
            "derivation_reason_codes": tuple(regime.derivation_reason_codes),
        }
        for regime in regimes
    )


def _source_vehicle_cycle_review(
    imported: ImportedWorkbook,
    exact_trips: tuple[ExactTimetableTrip, ...],
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    groups: dict[str, list[ExactTimetableTrip]] = defaultdict(list)
    for trip in exact_trips:
        if trip.vehicle_assignment is not None:
            groups[trip.vehicle_assignment].append(trip)
    assigned_trip_count = sum(len(items) for items in groups.values())
    unassigned_trip_count = len(imported.trips_b) - assigned_trip_count
    if not groups:
        cycle = {
            "assignment_status": SOURCE_VEHICLE_ASSIGNMENT_NOT_SUPPLIED,
            "supplied_vehicle_cycle_count": 0,
            "assigned_trip_count": 0,
            "unassigned_trip_count": len(imported.trips_b),
            "overlap_issues": (),
            "terminal_discontinuity_issues": (),
            "observed_minimum_inter_trip_gap_by_vehicle": (),
            "observed_minimum_inter_trip_gap_minutes": None,
        }
        turnaround = {
            "authoritative_minimum_turnaround_minutes": (
                imported.parameters_b.minimum_layover_minutes
            ),
            "regulatory_fallback_minutes": (
                imported.parameters_b.regulatory_minimum_layover_minutes
            ),
            "regulatory_fallback_is_operator_supplied_terminal_authority": False,
            "compliance_status": TurnaroundComplianceStatusV1.NOT_EVALUATED.value,
            "observed_minimum_inter_trip_gap_minutes": None,
        }
        return cycle, turnaround

    overlap_issues: list[Mapping[str, object]] = []
    terminal_discontinuity_issues: list[Mapping[str, object]] = []
    by_vehicle: list[Mapping[str, object]] = []
    all_gaps: list[float] = []
    for vehicle_id, trips in sorted(groups.items()):
        ordered = tuple(sorted(trips, key=lambda item: (item.departure_time, item.trip_id)))
        gaps = []
        for current, following in zip(ordered, ordered[1:], strict=False):
            gap = (following.departure_time - current.resolved_arrival_time) / 60
            gaps.append(gap)
            all_gaps.append(gap)
            if gap < 0:
                overlap_issues.append(
                    {
                        "vehicle_id": vehicle_id,
                        "from_trip_id": current.trip_id,
                        "to_trip_id": following.trip_id,
                        "overlap_minutes": _round(-gap),
                    }
                )
            expected_departure_terminal = (
                DepartureTerminal.TERMINAL_2
                if current.direction == ContractDirection.OUTBOUND
                else DepartureTerminal.TERMINAL_1
            )
            if following.departure_terminal != expected_departure_terminal:
                terminal_discontinuity_issues.append(
                    {
                        "code": SOURCE_ASSIGNMENT_TERMINAL_DISCONTINUITY,
                        "vehicle_id": vehicle_id,
                        "from_trip_id": current.trip_id,
                        "to_trip_id": following.trip_id,
                        "expected_departure_terminal": expected_departure_terminal.value,
                        "actual_departure_terminal": following.departure_terminal.value,
                    }
                )
        by_vehicle.append(
            {
                "vehicle_id": vehicle_id,
                "trip_count": len(ordered),
                "minimum_inter_trip_gap_minutes": _round(min(gaps)) if gaps else None,
            }
        )
    if overlap_issues:
        assignment_status = SOURCE_ASSIGNMENT_OVERLAP_DETECTED
    elif terminal_discontinuity_issues:
        assignment_status = SOURCE_ASSIGNMENT_TERMINAL_DISCONTINUITY_DETECTED
    elif unassigned_trip_count:
        assignment_status = SOURCE_ASSIGNMENT_PARTIAL
    else:
        assignment_status = SOURCE_ASSIGNMENT_OVERLAP_FREE

    minimum_authority = imported.parameters_b.minimum_layover_minutes
    if minimum_authority is None or not all_gaps:
        compliance = TurnaroundComplianceStatusV1.NOT_EVALUATED
    elif overlap_issues or terminal_discontinuity_issues or min(all_gaps) < minimum_authority:
        compliance = TurnaroundComplianceStatusV1.NON_COMPLIANT
    else:
        compliance = TurnaroundComplianceStatusV1.COMPLIANT
    observed_minimum = _round(min(all_gaps)) if all_gaps else None
    cycle = {
        "assignment_status": assignment_status,
        "supplied_vehicle_cycle_count": len(groups),
        "assigned_trip_count": assigned_trip_count,
        "unassigned_trip_count": unassigned_trip_count,
        "overlap_issues": tuple(overlap_issues),
        "terminal_discontinuity_issues": tuple(terminal_discontinuity_issues),
        "observed_minimum_inter_trip_gap_by_vehicle": tuple(by_vehicle),
        "observed_minimum_inter_trip_gap_minutes": observed_minimum,
    }
    turnaround = {
        "authoritative_minimum_turnaround_minutes": minimum_authority,
        "regulatory_fallback_minutes": imported.parameters_b.regulatory_minimum_layover_minutes,
        "regulatory_fallback_is_operator_supplied_terminal_authority": False,
        "compliance_status": compliance.value,
        "observed_minimum_inter_trip_gap_minutes": observed_minimum,
    }
    return cycle, turnaround


def _capability_maps(
    readiness: LayeredDataAuthorityReadinessV1,
) -> tuple[Mapping[str, object], Mapping[str, object]]:
    capability = {
        item.capability.value: {
            "status": item.status.value,
            "ready": item.ready,
            "missing_authority_codes": item.missing_authority_codes,
            "limitation_codes": item.limitation_codes,
        }
        for item in readiness.capabilities
    }
    missing = {
        item.capability.value: item.missing_authority_codes for item in readiness.capabilities
    }
    return capability, missing


def _unreviewable_readiness() -> LayeredDataAuthorityReadinessV1:
    return LayeredDataAuthorityReadinessV1(
        capabilities=tuple(
            CapabilityReadinessV1(
                capability=capability,
                status=CapabilityReadinessStatusV1.BLOCKED,
                ready=False,
                missing_authority_codes=(CORE_TIMETABLE_IMPORT_REQUIRED,),
            )
            for capability in DataAuthorityCapabilityV1
        )
    )


def _authority_summary(imported: ImportedWorkbook | None) -> Mapping[str, object]:
    if imported is None:
        return {
            "status": TimetableAuthorityStatusV1.UNKNOWN.value,
            "reference": None,
            "effective_date": None,
            "source_approved": False,
        }
    metadata = imported.authority_metadata.timetable_authority
    return {
        "status": metadata.status.value,
        "reference": metadata.reference,
        "effective_date": (
            metadata.effective_date.isoformat() if metadata.effective_date is not None else None
        ),
        "source_approved": metadata.source_approved,
    }


def _unreviewable_review(source_id: str) -> PartialTimetableReviewV1:
    readiness = _unreviewable_readiness()
    capability, missing = _capability_maps(readiness)
    review = PartialTimetableReviewV1(
        profile=PARTIAL_REVIEW_PROFILE_V1,
        source_id=source_id,
        review_status=PartialTimetableReviewStatusV1.CORE_TIMETABLE_NOT_REVIEWABLE,
        timetable_authority=_authority_summary(None),
        capability_readiness=capability,
        missing_authority_codes_by_capability=missing,
        route_and_terminal_facts={"availability": "NOT_EVALUATED"},
        exact_timetable_consistency={"availability": "NOT_EVALUATED"},
        runtime_review={"availability": "NOT_EVALUATED"},
        headway_and_regime_review={"availability": "NOT_EVALUATED"},
        source_vehicle_cycle_review={"availability": "NOT_EVALUATED"},
        turnaround_review={"compliance_status": TurnaroundComplianceStatusV1.NOT_EVALUATED.value},
        demand_authority_review={"availability": "NOT_EVALUATED"},
        fleet_and_terminal_authority={"availability": "NOT_EVALUATED"},
        optimization_eligibility={
            "eligible": False,
            "missing_authority_codes": (CORE_TIMETABLE_IMPORT_REQUIRED,),
        },
        limitations=(
            CORE_TIMETABLE_IMPORT_REQUIRED,
            EXTERNAL_APPROVAL_NOT_GRANTED_OR_REVOKED,
            NO_AUTHORITY_INFERRED,
            NO_SOLVER_CALLED,
            RAW_PASSENGER_ROWS_EXCLUDED,
        ),
        review_fingerprint="0" * 64,
    )
    return replace(
        review,
        review_fingerprint=calculate_partial_timetable_review_fingerprint_v1(review),
    )


def build_partial_timetable_review_v1(
    imported: ImportedWorkbook,
    *,
    source_id: str,
) -> PartialTimetableReviewV1:
    """Build a deterministic structural review without normalization or solver execution."""
    if not isinstance(imported, ImportedWorkbook):
        raise TypeError("imported must be an ImportedWorkbook")
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must be a non-empty string")
    source_id = source_id.strip()
    parameters = imported.parameters_b
    layered = assess_layered_data_authority_v1(imported)
    capability, missing = _capability_maps(layered)
    exact_trips, terminal_issues, runtime_issues = _exact_trips_and_issues(imported)

    identifiers = Counter(trip.trip_id for trip in imported.trips_b)
    chronology_issues: list[Mapping[str, object]] = [
        {"code": DUPLICATE_TIMETABLE_TRIP_ID, "trip_id": trip_id, "count": count}
        for trip_id, count in sorted(identifiers.items())
        if count > 1
    ]
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        source_order = tuple(trip for trip in imported.trips_b if trip.direction == direction)
        for previous, current in zip(source_order, source_order[1:], strict=False):
            if current.departure_seconds < previous.departure_seconds:
                chronology_issues.append(
                    {
                        "code": DIRECTIONAL_SOURCE_ORDER_NOT_CHRONOLOGICAL,
                        "direction": _direction_key(direction),
                        "previous_trip_id": previous.trip_id,
                        "trip_id": current.trip_id,
                    }
                )

    exact_counts = {
        ContractDirection.OUTBOUND.value: sum(
            trip.direction == Direction.TERMINAL_1_TO_2 for trip in imported.trips_b
        ),
        ContractDirection.INBOUND.value: sum(
            trip.direction == Direction.TERMINAL_2_TO_1 for trip in imported.trips_b
        ),
        ContractDirection.COMBINED.value: sum(
            trip.direction == Direction.COMBINED for trip in imported.trips_b
        ),
    }
    consistency_codes = []
    if parameters.total_daily_trips != len(imported.trips_b):
        consistency_codes.append(DECLARED_TRIP_COUNT_MISMATCH)

    window_facts: dict[str, object] = {}
    for label, direction, declared_first, declared_last in (
        (
            "terminal_1",
            Direction.TERMINAL_1_TO_2,
            parameters.terminal_1_first_departure,
            parameters.terminal_1_last_departure,
        ),
        (
            "terminal_2",
            Direction.TERMINAL_2_TO_1,
            parameters.terminal_2_first_departure,
            parameters.terminal_2_last_departure,
        ),
    ):
        departures = sorted(
            trip.departure_seconds for trip in imported.trips_b if trip.direction == direction
        )
        exact_first = departures[0] if departures else None
        exact_last = departures[-1] if departures else None
        matches = exact_first == declared_first and exact_last == declared_last
        if not matches:
            consistency_codes.append(DECLARED_ENDPOINT_MISMATCH)
        window_facts[label] = {
            "declared_first_departure": _time_value(declared_first),
            "exact_first_departure": _time_value(exact_first),
            "declared_last_departure": _time_value(declared_last),
            "exact_last_departure": _time_value(exact_last),
            "matches": matches,
        }

    runtime_values = tuple(_runtime_minutes(imported, trip) for trip in imported.trips_b)
    headways = _headway_review(imported)
    regimes = _regime_review(imported, exact_trips)
    vehicle_cycles, turnaround = _source_vehicle_cycle_review(imported, exact_trips)
    demand_counts = Counter(record.direction.value for record in imported.demand)
    has_outbound_demand = demand_counts[Direction.TERMINAL_1_TO_2.value] > 0
    has_inbound_demand = demand_counts[Direction.TERMINAL_2_TO_1.value] > 0
    metadata = imported.authority_metadata
    optimization = layered.for_capability(DataAuthorityCapabilityV1.OPTIMIZATION)
    terminal = layered.for_capability(DataAuthorityCapabilityV1.TERMINAL_CAPACITY)

    limitations = {
        EXTERNAL_APPROVAL_NOT_GRANTED_OR_REVOKED,
        NO_AUTHORITY_INFERRED,
        NO_SOLVER_CALLED,
        RAW_PASSENGER_ROWS_EXCLUDED,
        DRIVER_DEPOT_DEADHEAD_MAINTENANCE_OUTSIDE_SCOPE,
        *layered.all_missing_authority_codes,
    }
    if vehicle_cycles["assignment_status"] == SOURCE_VEHICLE_ASSIGNMENT_NOT_SUPPLIED:
        limitations.add(SOURCE_VEHICLE_ASSIGNMENT_NOT_SUPPLIED)
    if vehicle_cycles["terminal_discontinuity_issues"]:
        limitations.add(SOURCE_ASSIGNMENT_TERMINAL_DISCONTINUITY)

    review = PartialTimetableReviewV1(
        profile=PARTIAL_REVIEW_PROFILE_V1,
        source_id=source_id,
        review_status=PartialTimetableReviewStatusV1.REVIEW_COMPLETE,
        timetable_authority=_authority_summary(imported),
        capability_readiness=capability,
        missing_authority_codes_by_capability=missing,
        route_and_terminal_facts={
            "route_id": parameters.route_id,
            "route_name": parameters.route_name,
            "route_type": parameters.route_type.value,
            "terminal_1_name": parameters.terminal_1_name,
            "terminal_2_name": parameters.terminal_2_name,
        },
        exact_timetable_consistency={
            "status": (
                "CONSISTENT"
                if not consistency_codes and not chronology_issues and not terminal_issues
                else "ISSUES_FOUND"
            ),
            "declared_total_daily_trips": parameters.total_daily_trips,
            "exact_total_daily_trips": len(imported.trips_b),
            "exact_directional_trip_counts": exact_counts,
            "declared_versus_exact_service_windows": window_facts,
            "chronology_issues": tuple(chronology_issues),
            "terminal_direction_issues": terminal_issues,
            "issue_codes": tuple(
                sorted(
                    {
                        *consistency_codes,
                        *(str(item["code"]) for item in chronology_issues),
                        *(str(item["code"]) for item in terminal_issues),
                    }
                )
            ),
        },
        runtime_review={
            "allowed_runtime_minutes": parameters.runtime_options,
            "resolved_trip_count": len(runtime_values),
            "minimum_runtime_minutes": _round(min(runtime_values)) if runtime_values else None,
            "median_runtime_minutes": _round(median(runtime_values)) if runtime_values else None,
            "mean_runtime_minutes": _round(mean(runtime_values)) if runtime_values else None,
            "maximum_runtime_minutes": _round(max(runtime_values)) if runtime_values else None,
            "runtime_violations": runtime_issues,
        },
        headway_and_regime_review={
            "directional_headways": headways,
            "canonical_sustained_regimes": regimes,
            "canonical_regime_derivation_reused": True,
        },
        source_vehicle_cycle_review=vehicle_cycles,
        turnaround_review=turnaround,
        demand_authority_review={
            "descriptive_record_count": len(imported.demand),
            "record_counts_by_declared_direction": dict(sorted(demand_counts.items())),
            "combined_descriptive_review_available": (demand_counts[Direction.COMBINED.value] > 0),
            "directional_descriptive_review_available": (
                has_outbound_demand and has_inbound_demand
            ),
            "directional_demand_fabricated": False,
            "demand_dataset_id": metadata.demand_dataset_id,
            "demand_source_type": (
                metadata.demand_source_type.value
                if metadata.demand_source_type is not None
                else None
            ),
            "demand_confidence": (
                metadata.demand_confidence.value if metadata.demand_confidence is not None else None
            ),
            "demand_response_mode": (
                metadata.demand_response_mode.value
                if metadata.demand_response_mode is not None
                else None
            ),
            "vehicle_capacity_passengers": parameters.vehicle_capacity_passengers,
        },
        fleet_and_terminal_authority={
            "available_fleet_limit": parameters.available_fleet_limit,
            "approved_active_fleet": parameters.approved_active_fleet,
            "approved_active_fleet_is_available_fleet_limit": False,
            "terminal_1_max_occupancy_vehicles": (parameters.terminal_1_max_occupancy_vehicles),
            "terminal_2_max_occupancy_vehicles": (parameters.terminal_2_max_occupancy_vehicles),
            "terminal_capacity_status": terminal.status.value,
            "terminal_capacity_limitation_codes": terminal.missing_authority_codes,
            "fleet_or_terminal_limits_inferred": False,
        },
        optimization_eligibility={
            "eligible": optimization.ready,
            "status": optimization.status.value,
            "missing_authority_codes": optimization.missing_authority_codes,
            "solver_called": False,
        },
        limitations=tuple(sorted(limitations)),
        review_fingerprint="0" * 64,
    )
    review = replace(
        review,
        review_fingerprint=calculate_partial_timetable_review_fingerprint_v1(review),
    )
    if not verify_partial_timetable_review_fingerprint_v1(review):
        raise ValueError("constructed partial timetable review failed integrity verification")
    return review


def _md_value(value: object) -> str:
    if value is None:
        return "Not supplied"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (tuple, list)):
        return ", ".join(_md_value(item) for item in value) if value else "None"
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {_md_value(item)}" for key, item in value.items())
    return str(value).replace("|", "\\|").replace("\n", " ")


def _authority_markdown(authority: Mapping[str, object]) -> str:
    status = authority.get("status")
    if status == TimetableAuthorityStatusV1.APPROVED_OPERATIONAL.value:
        return "The workbook explicitly declares the timetable as source-approved for operations."
    if status == TimetableAuthorityStatusV1.CURRENT_OPERATIONAL.value:
        return "The workbook explicitly declares the timetable as current operational service."
    if status == TimetableAuthorityStatusV1.PROPOSED.value:
        return "The workbook declares the timetable as proposed; the engine does not promote it."
    return "Timetable authority is unknown; the engine does not infer approval."


def render_partial_timetable_review_markdown_v1(review: PartialTimetableReviewV1) -> bytes:
    if not verify_partial_timetable_review_fingerprint_v1(review):
        raise ValueError("cannot render an unverified partial timetable review")
    authority = review.timetable_authority
    consistency = review.exact_timetable_consistency
    runtime = review.runtime_review
    headway = review.headway_and_regime_review
    cycles = review.source_vehicle_cycle_review
    turnaround = review.turnaround_review
    demand = review.demand_authority_review
    fleet = review.fleet_and_terminal_authority
    optimization = review.optimization_eligibility
    capability_rows = tuple(
        f"| {name} | `{details['status']}` | {_md_value(details['missing_authority_codes'])} |"
        for name, details in review.capability_readiness.items()
    )
    lines = [
        "# Layered data-authority and partial timetable review",
        "",
        "This review does not call a solver. It can preserve an explicitly supplied external "
        "approval, but it does not grant or revoke that approval. Missing optimization metadata "
        "is not a technical rejection of the timetable.",
        "",
        "## 1. Review conclusion",
        "",
        f"- Review status: `{review.review_status.value}`",
        f"- Timetable review ready: {_md_value(review.capability_readiness['TIMETABLE_REVIEW']['ready'])}",
        f"- Optimization eligible: {_md_value(optimization.get('eligible'))}",
        "- Solver called: No",
        "",
        "## 2. Timetable authority",
        "",
        f"- {_authority_markdown(authority)}",
        f"- Declared status: `{_md_value(authority.get('status'))}`",
        f"- Reference: {_md_value(authority.get('reference'))}",
        f"- Effective date: {_md_value(authority.get('effective_date'))}",
        "- Technical review does not bypass technical checks and does not revoke external approval.",
        "",
        "## 3. Capability readiness",
        "",
        "| Capability | Status | Missing authority |",
        "|---|---|---|",
        *capability_rows,
        "",
        "## 4. Exact timetable consistency",
        "",
        f"- Route/terminals: {_md_value(review.route_and_terminal_facts)}",
        f"- Consistency status: {_md_value(consistency.get('status'))}",
        f"- Declared/exact trips: {_md_value(consistency.get('declared_total_daily_trips'))} / {_md_value(consistency.get('exact_total_daily_trips'))}",
        f"- Directional counts: {_md_value(consistency.get('exact_directional_trip_counts'))}",
        f"- Service windows: {_md_value(consistency.get('declared_versus_exact_service_windows'))}",
        f"- Chronology issues: {_md_value(consistency.get('chronology_issues'))}",
        f"- Terminal/direction issues: {_md_value(consistency.get('terminal_direction_issues'))}",
        "",
        "## 5. Runtime review",
        "",
        f"- Allowed runtimes: {_md_value(runtime.get('allowed_runtime_minutes'))} minutes",
        f"- Minimum / median / mean / maximum: {_md_value(runtime.get('minimum_runtime_minutes'))} / {_md_value(runtime.get('median_runtime_minutes'))} / {_md_value(runtime.get('mean_runtime_minutes'))} / {_md_value(runtime.get('maximum_runtime_minutes'))} minutes",
        f"- Violations: {_md_value(runtime.get('runtime_violations'))}",
        "",
        "## 6. Headway and regime review",
        "",
        f"- Directional headways: {_md_value(headway.get('directional_headways'))}",
        f"- Canonical sustained regimes: {_md_value(headway.get('canonical_sustained_regimes'))}",
        "- Transition headways are reported separately from regime-internal headways.",
        "",
        "## 7. Source vehicle-cycle review",
        "",
        f"- Assignment status: `{_md_value(cycles.get('assignment_status'))}`",
        f"- Supplied vehicle cycles: {_md_value(cycles.get('supplied_vehicle_cycle_count'))}",
        f"- Observed minimum gaps by vehicle: {_md_value(cycles.get('observed_minimum_inter_trip_gap_by_vehicle'))}",
        f"- Overlap issues: {_md_value(cycles.get('overlap_issues'))}",
        f"- Terminal-continuity issues: {_md_value(cycles.get('terminal_discontinuity_issues'))}",
        "- An overlap-free source assignment is not described as globally fleet-optimal.",
        "",
        "## 8. Turnaround authority",
        "",
        f"- Supplied minimum: {_md_value(turnaround.get('authoritative_minimum_turnaround_minutes'))} minutes",
        f"- Observed minimum inter-trip gap: {_md_value(turnaround.get('observed_minimum_inter_trip_gap_minutes'))} minutes",
        f"- Compliance: `{_md_value(turnaround.get('compliance_status'))}`",
        f"- Current-contract regulatory fallback, reported separately: {_md_value(turnaround.get('regulatory_fallback_minutes'))} minutes",
        "",
        "## 9. Demand authority",
        "",
        f"- Descriptive records: {_md_value(demand.get('descriptive_record_count'))}",
        f"- Declared directions: {_md_value(demand.get('record_counts_by_declared_direction'))}",
        f"- Combined descriptive review available: {_md_value(demand.get('combined_descriptive_review_available'))}",
        f"- Directional descriptive review available: {_md_value(demand.get('directional_descriptive_review_available'))}",
        "- Combined demand is not divided or duplicated into directions.",
        "",
        "## 10. Fleet and terminal authority",
        "",
        f"- Available-fleet limit: {_md_value(fleet.get('available_fleet_limit'))}",
        f"- Approved active fleet metadata: {_md_value(fleet.get('approved_active_fleet'))}",
        f"- Terminal 1 / terminal 2 limits: {_md_value(fleet.get('terminal_1_max_occupancy_vehicles'))} / {_md_value(fleet.get('terminal_2_max_occupancy_vehicles'))}",
        f"- Terminal-capacity status: `{_md_value(fleet.get('terminal_capacity_status'))}`",
        "- No fleet or terminal limit is inferred from vehicle IDs, occupancy, names, or approval status.",
        "",
        "## 11. Optimization blockers",
        "",
        f"- Eligible: {_md_value(optimization.get('eligible'))}",
        f"- Missing authority: {_md_value(optimization.get('missing_authority_codes'))}",
        "- No solver adapter was called.",
        "",
        "## 12. Required data-completion actions",
        "",
        f"- Supply only the declared facts identified here: {_md_value(review.missing_authority_codes_by_capability)}",
        "- Do not infer capacity, fleet, directional demand, turnaround, or terminal limits to unlock a capability.",
        "",
        "## 13. Limitations",
        "",
        f"- Codes: {_md_value(review.limitations)}",
        "- Driver duties, breaks, depot/deadhead work, maintenance, and stochastic traffic remain outside this review.",
        "",
        "## 14. Fingerprint references",
        "",
        f"- Review profile: `{review.profile}`",
        f"- Review fingerprint: `{review.review_fingerprint}`",
        "- Workbook paths, machine identity, wall-clock duration, raw passenger rows, and inferred authority are excluded.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def create_data_authority_review_package_v1(
    workbook: str | Path | bytes,
    *,
    source_id: str,
) -> DataAuthorityReviewPackageV1:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must be a non-empty string")
    source_id = source_id.strip()
    try:
        imported = import_workbook(workbook)
    except Exception:
        review = _unreviewable_review(source_id)
    else:
        review = build_partial_timetable_review_v1(imported, source_id=source_id)
    package = DataAuthorityReviewPackageV1(
        review=review,
        json_bytes=serialize_partial_timetable_review_v1(review),
        markdown_bytes=render_partial_timetable_review_markdown_v1(review),
        exit_code=_EXIT_CODE_BY_STATUS[review.review_status],
    )
    _verify_data_authority_review_package_v1(package)
    return package


def data_authority_review_output_filenames_v1() -> tuple[str, str]:
    return DATA_AUTHORITY_REVIEW_JSON_FILENAME, DATA_AUTHORITY_REVIEW_MARKDOWN_FILENAME


def _verify_data_authority_review_package_v1(package: DataAuthorityReviewPackageV1) -> None:
    if not isinstance(package, DataAuthorityReviewPackageV1):
        raise TypeError("package must be a DataAuthorityReviewPackageV1")
    if not verify_partial_timetable_review_fingerprint_v1(package.review):
        raise ValueError("partial review package model failed integrity verification")
    if package.json_bytes != serialize_partial_timetable_review_v1(package.review):
        raise ValueError("partial review package JSON does not belong to the supplied review")
    if package.markdown_bytes != render_partial_timetable_review_markdown_v1(package.review):
        raise ValueError("partial review package Markdown does not belong to the supplied review")
    if type(package.exit_code) is not int or package.exit_code != _EXIT_CODE_BY_STATUS.get(
        package.review.review_status
    ):
        raise ValueError("partial review package exit code does not match review status")


def write_data_authority_review_package_v1(
    package: DataAuthorityReviewPackageV1,
    output_dir: str | Path,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Verify before mutation and write only the two bounded output filenames."""
    _verify_data_authority_review_package_v1(package)
    target = Path(output_dir)
    paths = tuple(target / name for name in data_authority_review_output_filenames_v1())
    collisions = tuple(path for path in paths if path.exists())
    if any(not path.is_file() for path in collisions):
        raise IsADirectoryError("a bounded data-authority output filename is not a file")
    if collisions and not overwrite:
        raise FileExistsError("data-authority review output exists; pass --overwrite to replace it")
    target.mkdir(parents=True, exist_ok=True)
    if overwrite:
        for path in collisions:
            path.unlink()
    paths[0].write_bytes(package.json_bytes)
    paths[1].write_bytes(package.markdown_bytes)
    return paths


__all__ = [
    "DATA_AUTHORITY_REVIEW_JSON_FILENAME",
    "DATA_AUTHORITY_REVIEW_MARKDOWN_FILENAME",
    "DataAuthorityReviewPackageV1",
    "PARTIAL_REVIEW_PROFILE_V1",
    "PartialTimetableReviewStatusV1",
    "PartialTimetableReviewV1",
    "TurnaroundComplianceStatusV1",
    "build_partial_timetable_review_v1",
    "calculate_partial_timetable_review_fingerprint_v1",
    "create_data_authority_review_package_v1",
    "data_authority_review_output_filenames_v1",
    "partial_timetable_review_to_dict_v1",
    "render_partial_timetable_review_markdown_v1",
    "serialize_partial_timetable_review_v1",
    "verify_partial_timetable_review_fingerprint_v1",
    "verify_partial_timetable_review_json_bytes_v1",
    "write_data_authority_review_package_v1",
]
