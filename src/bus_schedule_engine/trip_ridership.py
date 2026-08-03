"""Deterministic supplemental analysis of trip-level ridership observations."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import fields, is_dataclass, replace
from datetime import date
from enum import Enum
from statistics import mean, median
from typing import TYPE_CHECKING, Any

from .contracts_v1.models import (
    ContractDirection,
    DepartureTerminal,
    OperatingDayType,
    ScenarioBInput,
)
from .contracts_v1.serialization import scenario_fingerprint
from .models import (
    TripRidershipAnalysisV1,
    TripRidershipDatasetStatusV1,
    TripRidershipDatasetSummaryV1,
    TripRidershipDirectionSummaryV1,
    TripRidershipDirectionV1,
    TripRidershipMatchMethodV1,
    TripRidershipMatchPolicyV1,
    TripRidershipMatchStatusV1,
    TripRidershipMatchV1,
    TripRidershipObservationV1,
    TripRidershipTripSummaryV1,
)
from .trip_ridership_codes import (
    AMBIGUOUS_TRIP_TIME_MATCH,
    DUPLICATE_OBSERVATION_FOR_TRIP_DATE,
    DUPLICATE_TRIP_RIDERSHIP_OBSERVATION_ID,
    EXPLICIT_SCHEDULED_TIME_MISMATCH,
    EXPLICIT_SCHEDULED_TRIP_ID_NOT_FOUND,
    EXPLICIT_TRIP_DIRECTION_MISMATCH,
    NO_TRIP_WITHIN_MATCH_TOLERANCE,
    TRIP_RIDERSHIP_ANALYSIS_FAILED,
    TRIP_RIDERSHIP_COMBINED_DIRECTION_NOT_ALLOWED,
    TRIP_RIDERSHIP_CONFIDENCE_INVALID,
    TRIP_RIDERSHIP_DATASET_ID_MISSING,
    TRIP_RIDERSHIP_DIRECTION_INVALID,
    TRIP_RIDERSHIP_FORMULA_NOT_ALLOWED,
    TRIP_RIDERSHIP_MATCH_TOLERANCE_INVALID,
    TRIP_RIDERSHIP_METADATA_MISSING,
    TRIP_RIDERSHIP_NO_USABLE_MATCHES,
    TRIP_RIDERSHIP_OPERATING_DAY_TYPE_MISMATCH,
    TRIP_RIDERSHIP_PASSENGER_COUNT_INVALID,
    TRIP_RIDERSHIP_REFERENCE_MISSING,
    TRIP_RIDERSHIP_SCENARIO_INVALID,
    TRIP_RIDERSHIP_SOURCE_TYPE_INVALID,
)

if TYPE_CHECKING:
    from .importer import ImportedWorkbook


SUPPLEMENTAL_ONLY_LIMITATION = "SUPPLEMENTAL_ONLY_NOT_SOLVER_AUTHORITY"
MISSING_TRIP_DAYS_NOT_ZERO_LIMITATION = "MISSING_TRIP_DAYS_ARE_NOT_ZERO"
NO_EXTRAPOLATION_LIMITATION = "MISSING_TRIP_DAYS_ARE_NOT_EXTRAPOLATED"
EXCLUDED_RECORDS_LIMITATION = "UNSAFE_MATCH_STATUSES_ARE_EXCLUDED"
INCOMPLETE_COVERAGE_LIMITATION = "OBSERVED_MATCHED_PASSENGERS_ARE_NOT_FULL_RIDERSHIP"
NO_USABLE_TRIP_OBSERVATIONS_LIMITATION = "NO_USABLE_TRIP_RIDERSHIP_OBSERVATIONS"

_USABLE_STATUSES = {
    TripRidershipMatchStatusV1.MATCHED_EXACT,
    TripRidershipMatchStatusV1.MATCHED_WITHIN_TOLERANCE,
}
_DIRECTION_ORDER = (
    TripRidershipDirectionV1.OUTBOUND,
    TripRidershipDirectionV1.INBOUND,
)
_CONCRETE_OPERATING_DAY_TYPES = frozenset(
    day_type.value for day_type in OperatingDayType if day_type != OperatingDayType.ALL_DAYS
)


def trip_ridership_day_type_matches_timetable_v1(
    ridership_day_type: str,
    timetable_day_type: OperatingDayType,
) -> bool:
    """Bind one concrete demand day type without broadening its coverage authority."""
    return ridership_day_type in _CONCRETE_OPERATING_DAY_TYPES and (
        timetable_day_type == OperatingDayType.ALL_DAYS
        or ridership_day_type == timetable_day_type.value
    )


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if is_dataclass(value):
        return {item.name: _canonical_value(getattr(value, item.name)) for item in fields(value)}
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


def _trip_direction(direction: ContractDirection) -> TripRidershipDirectionV1:
    if direction == ContractDirection.OUTBOUND:
        return TripRidershipDirectionV1.OUTBOUND
    if direction == ContractDirection.INBOUND:
        return TripRidershipDirectionV1.INBOUND
    raise ValueError("Scenario B cannot contain combined-direction trips")


def _departure_terminal_name(scenario_b: ScenarioBInput, terminal: DepartureTerminal) -> str:
    if terminal == DepartureTerminal.TERMINAL_1:
        return scenario_b.terminal_1_name
    if terminal == DepartureTerminal.TERMINAL_2:
        return scenario_b.terminal_2_name
    raise ValueError(f"Unsupported Scenario B departure terminal: {terminal}")


def _base_match(
    observation: TripRidershipObservationV1,
    *,
    method: TripRidershipMatchMethodV1,
    status: TripRidershipMatchStatusV1,
    matched_trip_id: str | None = None,
    candidate_trip_ids: tuple[str, ...] = (),
    absolute_time_offset_seconds: int | None = None,
    issue_codes: tuple[str, ...] = (),
) -> TripRidershipMatchV1:
    return TripRidershipMatchV1(
        observation_id=observation.observation_id,
        service_date=observation.service_date,
        direction=observation.direction,
        source_trip_id=observation.source_trip_id,
        supplied_scheduled_trip_id=observation.scheduled_trip_id,
        scheduled_departure_seconds=observation.scheduled_departure_seconds,
        actual_departure_seconds=observation.actual_departure_seconds,
        passenger_count=observation.passenger_count,
        match_method=method,
        match_status=status,
        matched_trip_id=matched_trip_id,
        candidate_trip_ids=candidate_trip_ids,
        absolute_time_offset_seconds=absolute_time_offset_seconds,
        issue_codes=tuple(sorted(set(issue_codes))),
    )


def _match_by_time(
    observation: TripRidershipObservationV1,
    *,
    method: TripRidershipMatchMethodV1,
    reference_seconds: int,
    trips_by_direction: dict[TripRidershipDirectionV1, tuple[object, ...]],
    tolerance_seconds: int,
) -> TripRidershipMatchV1:
    candidates = tuple(
        sorted(
            (
                (abs(trip.departure_time - reference_seconds), trip.departure_time, trip.trip_id)
                for trip in trips_by_direction[observation.direction]
                if abs(trip.departure_time - reference_seconds) <= tolerance_seconds
            ),
            key=lambda item: (item[0], item[1], item[2]),
        )
    )
    if not candidates:
        return _base_match(
            observation,
            method=method,
            status=TripRidershipMatchStatusV1.UNMATCHED,
            issue_codes=(NO_TRIP_WITHIN_MATCH_TOLERANCE,),
        )

    nearest_offset = candidates[0][0]
    nearest = tuple(item for item in candidates if item[0] == nearest_offset)
    candidate_ids = tuple(item[2] for item in candidates)
    if len(nearest) > 1:
        return _base_match(
            observation,
            method=method,
            status=TripRidershipMatchStatusV1.AMBIGUOUS,
            candidate_trip_ids=candidate_ids,
            absolute_time_offset_seconds=nearest_offset,
            issue_codes=(AMBIGUOUS_TRIP_TIME_MATCH,),
        )

    matched_trip_id = nearest[0][2]
    return _base_match(
        observation,
        method=method,
        status=(
            TripRidershipMatchStatusV1.MATCHED_EXACT
            if nearest_offset == 0
            else TripRidershipMatchStatusV1.MATCHED_WITHIN_TOLERANCE
        ),
        matched_trip_id=matched_trip_id,
        candidate_trip_ids=candidate_ids,
        absolute_time_offset_seconds=nearest_offset,
    )


def _provisional_match(
    observation: TripRidershipObservationV1,
    *,
    trips_by_id: dict[str, object],
    trips_by_direction: dict[TripRidershipDirectionV1, tuple[object, ...]],
    tolerance_seconds: int,
) -> TripRidershipMatchV1:
    if observation.scheduled_trip_id is not None:
        method = TripRidershipMatchMethodV1.EXPLICIT_SCHEDULED_TRIP_ID
        trip = trips_by_id.get(observation.scheduled_trip_id)
        if trip is None:
            return _base_match(
                observation,
                method=method,
                status=TripRidershipMatchStatusV1.INVALID,
                issue_codes=(EXPLICIT_SCHEDULED_TRIP_ID_NOT_FOUND,),
            )
        if _trip_direction(trip.direction) != observation.direction:
            return _base_match(
                observation,
                method=method,
                status=TripRidershipMatchStatusV1.INVALID,
                candidate_trip_ids=(trip.trip_id,),
                issue_codes=(EXPLICIT_TRIP_DIRECTION_MISMATCH,),
            )
        if (
            observation.scheduled_departure_seconds is not None
            and observation.scheduled_departure_seconds != trip.departure_time
        ):
            return _base_match(
                observation,
                method=method,
                status=TripRidershipMatchStatusV1.INVALID,
                candidate_trip_ids=(trip.trip_id,),
                absolute_time_offset_seconds=abs(
                    observation.scheduled_departure_seconds - trip.departure_time
                ),
                issue_codes=(EXPLICIT_SCHEDULED_TIME_MISMATCH,),
            )
        return _base_match(
            observation,
            method=method,
            status=TripRidershipMatchStatusV1.MATCHED_EXACT,
            matched_trip_id=trip.trip_id,
            candidate_trip_ids=(trip.trip_id,),
            absolute_time_offset_seconds=0,
        )

    if observation.scheduled_departure_seconds is not None:
        return _match_by_time(
            observation,
            method=TripRidershipMatchMethodV1.SCHEDULED_DEPARTURE_TIME,
            reference_seconds=observation.scheduled_departure_seconds,
            trips_by_direction=trips_by_direction,
            tolerance_seconds=tolerance_seconds,
        )

    if observation.actual_departure_seconds is not None:
        return _match_by_time(
            observation,
            method=TripRidershipMatchMethodV1.ACTUAL_DEPARTURE_TIME,
            reference_seconds=observation.actual_departure_seconds,
            trips_by_direction=trips_by_direction,
            tolerance_seconds=tolerance_seconds,
        )

    return _base_match(
        observation,
        method=TripRidershipMatchMethodV1.NONE,
        status=TripRidershipMatchStatusV1.INVALID,
        issue_codes=(TRIP_RIDERSHIP_REFERENCE_MISSING,),
    )


def _apply_collisions(
    matches: tuple[TripRidershipMatchV1, ...],
) -> tuple[TripRidershipMatchV1, ...]:
    groups: dict[tuple[date, str], list[str]] = defaultdict(list)
    for match in matches:
        if match.match_status in _USABLE_STATUSES and match.matched_trip_id is not None:
            groups[(match.service_date, match.matched_trip_id)].append(match.observation_id)
    collided_ids = {
        observation_id
        for observation_ids in groups.values()
        if len(observation_ids) > 1
        for observation_id in observation_ids
    }
    return tuple(
        replace(
            match,
            match_status=TripRidershipMatchStatusV1.COLLISION,
            issue_codes=tuple(sorted({*match.issue_codes, DUPLICATE_OBSERVATION_FOR_TRIP_DATE})),
        )
        if match.observation_id in collided_ids
        else match
        for match in matches
    )


def _nearest_rank(values: list[int] | list[float], percentile: float) -> int | float:
    ordered = sorted(values)
    rank = min(len(ordered), max(1, math.ceil(percentile * len(ordered))))
    return ordered[rank - 1]


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _coverage_interpretation(rate: float | None) -> str:
    if rate == 1.0:
        return "Observed matched passengers cover every scheduled trip-date in scope."
    return "Coverage-adjusted interpretation not available; missing trip-days are not extrapolated."


def _trip_summaries(
    imported: ImportedWorkbook,
    scenario_b: ScenarioBInput,
    matches: tuple[TripRidershipMatchV1, ...],
) -> tuple[TripRidershipTripSummaryV1, ...]:
    usable_by_trip: dict[str, list[TripRidershipMatchV1]] = defaultdict(list)
    for match in matches:
        if match.match_status in _USABLE_STATUSES and match.matched_trip_id is not None:
            usable_by_trip[match.matched_trip_id].append(match)

    overrides = {
        trip.trip_id: trip.vehicle_capacity_override
        for trip in imported.trips_b
        if trip.vehicle_capacity_override is not None
    }
    summaries: list[TripRidershipTripSummaryV1] = []
    for trip in sorted(
        scenario_b.exact_timetable,
        key=lambda item: (item.direction.value, item.departure_time, item.trip_id),
    ):
        capacity = int(overrides.get(trip.trip_id, scenario_b.vehicle_capacity))
        if capacity < 1:
            raise ValueError(f"Trip {trip.trip_id} has a non-positive capacity")
        rows = sorted(
            usable_by_trip.get(trip.trip_id, []),
            key=lambda item: (item.service_date, item.observation_id),
        )
        counts = [item.passenger_count for item in rows]
        offsets = [
            item.absolute_time_offset_seconds / 60
            for item in rows
            if item.absolute_time_offset_seconds is not None
        ]
        days = {item.service_date for item in rows}
        if counts:
            passenger_mean = mean(counts)
            passenger_median = median(counts)
            passenger_p85 = int(_nearest_rank(counts, 0.85))
            passenger_p90 = int(_nearest_rank(counts, 0.90))
            at_target = sum(
                count / capacity >= imported.parameters_b.target_load_factor for count in counts
            )
            above_maximum = sum(
                count / capacity > imported.parameters_b.maximum_load_factor for count in counts
            )
            limitations = (SUPPLEMENTAL_ONLY_LIMITATION,)
        else:
            passenger_mean = None
            passenger_median = None
            passenger_p85 = None
            passenger_p90 = None
            at_target = 0
            above_maximum = 0
            limitations = (
                SUPPLEMENTAL_ONLY_LIMITATION,
                NO_USABLE_TRIP_OBSERVATIONS_LIMITATION,
            )
        summaries.append(
            TripRidershipTripSummaryV1(
                trip_id=trip.trip_id,
                direction=_trip_direction(trip.direction),
                departure_terminal=_departure_terminal_name(scenario_b, trip.departure_terminal),
                scheduled_departure_seconds=trip.departure_time,
                nominal_trip_capacity=capacity,
                observation_count=len(rows),
                distinct_observation_day_count=len(days),
                passenger_minimum=min(counts) if counts else None,
                passenger_maximum=max(counts) if counts else None,
                passenger_mean=passenger_mean,
                passenger_median=passenger_median,
                passenger_p85=passenger_p85,
                passenger_p90=passenger_p90,
                mean_load_factor=(
                    passenger_mean / capacity if passenger_mean is not None else None
                ),
                median_load_factor=(
                    passenger_median / capacity if passenger_median is not None else None
                ),
                p85_load_factor=(passenger_p85 / capacity if passenger_p85 is not None else None),
                p90_load_factor=(passenger_p90 / capacity if passenger_p90 is not None else None),
                days_at_or_above_target_load_factor=at_target,
                share_observed_days_at_or_above_target_load_factor=_safe_rate(at_target, len(rows)),
                days_above_maximum_load_factor=above_maximum,
                share_observed_days_above_maximum_load_factor=_safe_rate(above_maximum, len(rows)),
                exact_match_count=sum(
                    item.match_status == TripRidershipMatchStatusV1.MATCHED_EXACT for item in rows
                ),
                tolerance_match_count=sum(
                    item.match_status == TripRidershipMatchStatusV1.MATCHED_WITHIN_TOLERANCE
                    for item in rows
                ),
                mean_absolute_matching_offset_minutes=(mean(offsets) if offsets else None),
                maximum_absolute_matching_offset_minutes=(max(offsets) if offsets else None),
                descriptive_limitations=limitations,
            )
        )
    return tuple(summaries)


def _status_count(
    matches: tuple[TripRidershipMatchV1, ...],
    status: TripRidershipMatchStatusV1,
) -> int:
    return sum(item.match_status == status for item in matches)


def _direction_summaries(
    scenario_b: ScenarioBInput,
    matches: tuple[TripRidershipMatchV1, ...],
) -> tuple[TripRidershipDirectionSummaryV1, ...]:
    summaries: list[TripRidershipDirectionSummaryV1] = []
    for direction in _DIRECTION_ORDER:
        direction_matches = tuple(item for item in matches if item.direction == direction)
        usable = tuple(item for item in direction_matches if item.match_status in _USABLE_STATUSES)
        trip_ids = {
            trip.trip_id
            for trip in scenario_b.exact_timetable
            if _trip_direction(trip.direction) == direction
        }
        observed_trip_ids = {
            item.matched_trip_id for item in usable if item.matched_trip_id is not None
        }
        dates = {item.service_date for item in direction_matches}
        trip_dates = {
            (item.service_date, item.matched_trip_id)
            for item in usable
            if item.matched_trip_id is not None
        }
        observed_total = sum(item.passenger_count for item in usable)
        trip_date_coverage = _safe_rate(len(trip_dates), len(trip_ids) * len(dates))
        summaries.append(
            TripRidershipDirectionSummaryV1(
                direction=direction,
                total_b_trips=len(trip_ids),
                b_trips_with_usable_observation=len(observed_trip_ids),
                scheduled_trip_coverage_rate=_safe_rate(len(observed_trip_ids), len(trip_ids)),
                usable_matched_records=len(usable),
                exact_matches=_status_count(
                    direction_matches, TripRidershipMatchStatusV1.MATCHED_EXACT
                ),
                tolerance_matches=_status_count(
                    direction_matches,
                    TripRidershipMatchStatusV1.MATCHED_WITHIN_TOLERANCE,
                ),
                ambiguous_records=_status_count(
                    direction_matches, TripRidershipMatchStatusV1.AMBIGUOUS
                ),
                unmatched_records=_status_count(
                    direction_matches, TripRidershipMatchStatusV1.UNMATCHED
                ),
                collided_records=_status_count(
                    direction_matches, TripRidershipMatchStatusV1.COLLISION
                ),
                invalid_records=_status_count(
                    direction_matches, TripRidershipMatchStatusV1.INVALID
                ),
                distinct_service_dates=len(dates),
                observed_matched_passengers=observed_total,
                average_matched_passenger_count_per_observed_trip=(
                    observed_total / len(usable) if usable else None
                ),
                observed_matched_passengers_per_service_date=(
                    observed_total / len(dates) if dates else None
                ),
                matched_trip_date_coverage_rate=trip_date_coverage,
                coverage_adjusted_interpretation=_coverage_interpretation(trip_date_coverage),
            )
        )
    return tuple(summaries)


def _dataset_summary(
    scenario_b: ScenarioBInput,
    matches: tuple[TripRidershipMatchV1, ...],
) -> TripRidershipDatasetSummaryV1:
    usable = tuple(item for item in matches if item.match_status in _USABLE_STATUSES)
    total_trips = len(scenario_b.exact_timetable)
    observed_trip_ids = {
        item.matched_trip_id for item in usable if item.matched_trip_id is not None
    }
    dates = {item.service_date for item in matches}
    trip_dates = {
        (item.service_date, item.matched_trip_id)
        for item in usable
        if item.matched_trip_id is not None
    }
    expected_directions = {_trip_direction(item.direction) for item in scenario_b.exact_timetable}
    observed_directions = {item.direction for item in usable}
    observed_total = sum(item.passenger_count for item in usable)
    offsets = sorted(
        item.absolute_time_offset_seconds / 60
        for item in usable
        if item.absolute_time_offset_seconds is not None
    )
    trip_date_coverage = _safe_rate(len(trip_dates), total_trips * len(dates))
    exact = _status_count(matches, TripRidershipMatchStatusV1.MATCHED_EXACT)
    tolerance = _status_count(matches, TripRidershipMatchStatusV1.MATCHED_WITHIN_TOLERANCE)
    excluded = len(matches) - len(usable)
    if not usable:
        status = TripRidershipDatasetStatusV1.NO_USABLE_MATCHES
    elif tolerance or excluded or trip_date_coverage != 1.0:
        status = TripRidershipDatasetStatusV1.COMPLETE_WITH_WARNINGS
    else:
        status = TripRidershipDatasetStatusV1.COMPLETE
    return TripRidershipDatasetSummaryV1(
        status=status,
        original_record_count=len(matches),
        total_b_trips=total_trips,
        b_trips_with_usable_observation=len(observed_trip_ids),
        scheduled_trip_coverage_rate=_safe_rate(len(observed_trip_ids), total_trips),
        usable_matched_records=len(usable),
        exact_matches=exact,
        tolerance_matches=tolerance,
        unmatched_records=_status_count(matches, TripRidershipMatchStatusV1.UNMATCHED),
        ambiguous_records=_status_count(matches, TripRidershipMatchStatusV1.AMBIGUOUS),
        collided_records=_status_count(matches, TripRidershipMatchStatusV1.COLLISION),
        invalid_records=_status_count(matches, TripRidershipMatchStatusV1.INVALID),
        usable_match_rate=_safe_rate(len(usable), len(matches)),
        exact_match_rate=_safe_rate(exact, len(matches)),
        distinct_service_dates=len(dates),
        directions_with_usable_observations=len(observed_directions),
        direction_coverage_rate=_safe_rate(
            len(observed_directions & expected_directions), len(expected_directions)
        ),
        observed_matched_passengers=observed_total,
        average_matched_passenger_count_per_observed_trip=(
            observed_total / len(usable) if usable else None
        ),
        observed_matched_passengers_per_service_date=(
            observed_total / len(dates) if dates else None
        ),
        matched_trip_date_coverage_rate=trip_date_coverage,
        minimum_absolute_matching_offset_minutes=min(offsets) if offsets else None,
        mean_absolute_matching_offset_minutes=mean(offsets) if offsets else None,
        median_absolute_matching_offset_minutes=median(offsets) if offsets else None,
        p85_absolute_matching_offset_minutes=(
            float(_nearest_rank(offsets, 0.85)) if offsets else None
        ),
        p90_absolute_matching_offset_minutes=(
            float(_nearest_rank(offsets, 0.90)) if offsets else None
        ),
        maximum_absolute_matching_offset_minutes=max(offsets) if offsets else None,
        coverage_adjusted_interpretation=_coverage_interpretation(trip_date_coverage),
    )


def _observation_fingerprint_facts(
    observations: tuple[TripRidershipObservationV1, ...],
) -> tuple[dict[str, object], ...]:
    facts = [
        {
            "observation_id": item.observation_id,
            "service_date": item.service_date,
            "source_trip_id": item.source_trip_id,
            "scheduled_trip_id": item.scheduled_trip_id,
            "direction": item.direction,
            "scheduled_departure_seconds": item.scheduled_departure_seconds,
            "actual_departure_seconds": item.actual_departure_seconds,
            "passenger_count": item.passenger_count,
            "vehicle_id": item.vehicle_id,
        }
        for item in observations
    ]
    return tuple(
        sorted(
            facts,
            key=lambda item: json.dumps(
                _canonical_value(item),
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    )


def trip_ridership_input_fingerprint_v1(
    imported: ImportedWorkbook,
    scenario_b_fingerprint: str,
) -> str | None:
    """Fingerprint normalized supplemental inputs without running matching."""
    metadata = imported.trip_ridership_metadata
    observations = tuple(imported.trip_ridership_observations)
    if metadata is None or not observations:
        return None
    return _canonical_sha256(
        {
            "dataset_id": metadata.dataset_id,
            "source_type": metadata.source_type,
            "confidence": metadata.confidence,
            "observed_schedule_scenario": metadata.observed_schedule_scenario,
            "operating_day_type": metadata.operating_day_type,
            "match_tolerance_minutes": metadata.match_tolerance_minutes,
            "observations": _observation_fingerprint_facts(observations),
            "scenario_b_fingerprint": scenario_b_fingerprint,
        }
    )


def _analysis_fingerprint_v1(
    *,
    trip_ridership_input_fingerprint: str,
    matching_policy_fingerprint: str,
    original_record_count: int,
    matches: tuple[TripRidershipMatchV1, ...],
    trip_summaries: tuple[TripRidershipTripSummaryV1, ...],
    directional_summaries: tuple[TripRidershipDirectionSummaryV1, ...],
    dataset_summary: TripRidershipDatasetSummaryV1,
    issue_codes: tuple[str, ...],
    limitations: tuple[str, ...],
) -> str:
    return _canonical_sha256(
        {
            "trip_ridership_input_fingerprint": trip_ridership_input_fingerprint,
            "matching_policy_fingerprint": matching_policy_fingerprint,
            "original_record_count": original_record_count,
            "matches": matches,
            "trip_summaries": trip_summaries,
            "directional_summaries": directional_summaries,
            "dataset_summary": dataset_summary,
            "issue_codes": issue_codes,
            "limitations": limitations,
        }
    )


def analyze_trip_ridership_v1(
    imported: ImportedWorkbook,
    scenario_b: ScenarioBInput,
) -> TripRidershipAnalysisV1:
    """Match and summarize supplemental trip observations without solver authority."""
    metadata = imported.trip_ridership_metadata
    observations = tuple(imported.trip_ridership_observations)
    if not observations or metadata is None:
        raise ValueError(f"{TRIP_RIDERSHIP_METADATA_MISSING}: no analyzable dataset")
    if metadata.observed_schedule_scenario != "B":
        raise ValueError(f"{TRIP_RIDERSHIP_SCENARIO_INVALID}: Scenario B is required")
    if not 0 <= metadata.match_tolerance_minutes <= 30:
        raise ValueError(
            f"{TRIP_RIDERSHIP_MATCH_TOLERANCE_INVALID}: tolerance must be from 0 to 30"
        )
    if not trip_ridership_day_type_matches_timetable_v1(
        metadata.operating_day_type,
        scenario_b.operating_day_type,
    ):
        raise ValueError(
            f"{TRIP_RIDERSHIP_OPERATING_DAY_TYPE_MISMATCH}: dataset and Scenario B differ"
        )

    b_fingerprint = scenario_fingerprint(scenario_b)
    input_fingerprint = trip_ridership_input_fingerprint_v1(imported, b_fingerprint)
    if input_fingerprint is None:
        raise ValueError(f"{TRIP_RIDERSHIP_METADATA_MISSING}: no analyzable dataset")
    policy = TripRidershipMatchPolicyV1(
        match_tolerance_minutes=metadata.match_tolerance_minutes,
        observed_schedule_scenario=metadata.observed_schedule_scenario,
    )
    policy_fingerprint = _canonical_sha256(policy)
    trips_by_id = {trip.trip_id: trip for trip in scenario_b.exact_timetable}
    trips_by_direction = {
        direction: tuple(
            sorted(
                (
                    trip
                    for trip in scenario_b.exact_timetable
                    if _trip_direction(trip.direction) == direction
                ),
                key=lambda trip: (trip.departure_time, trip.trip_id),
            )
        )
        for direction in _DIRECTION_ORDER
    }
    provisional = tuple(
        _provisional_match(
            observation,
            trips_by_id=trips_by_id,
            trips_by_direction=trips_by_direction,
            tolerance_seconds=metadata.match_tolerance_minutes * 60,
        )
        for observation in sorted(
            observations,
            key=lambda item: (
                item.observation_id,
                item.service_date,
                item.direction.value,
            ),
        )
    )
    matches = _apply_collisions(provisional)
    trip_summaries = _trip_summaries(imported, scenario_b, matches)
    directional_summaries = _direction_summaries(scenario_b, matches)
    dataset_summary = _dataset_summary(scenario_b, matches)
    issue_codes = tuple(
        sorted(
            {
                *(code for match in matches for code in match.issue_codes),
                *(
                    (TRIP_RIDERSHIP_NO_USABLE_MATCHES,)
                    if dataset_summary.usable_matched_records == 0
                    else ()
                ),
            }
        )
    )
    limitations = [
        SUPPLEMENTAL_ONLY_LIMITATION,
        MISSING_TRIP_DAYS_NOT_ZERO_LIMITATION,
        NO_EXTRAPOLATION_LIMITATION,
    ]
    if any(item.match_status not in _USABLE_STATUSES for item in matches):
        limitations.append(EXCLUDED_RECORDS_LIMITATION)
    if dataset_summary.matched_trip_date_coverage_rate != 1.0:
        limitations.append(INCOMPLETE_COVERAGE_LIMITATION)
    limitations_tuple = tuple(limitations)
    analysis_fingerprint = _analysis_fingerprint_v1(
        trip_ridership_input_fingerprint=input_fingerprint,
        matching_policy_fingerprint=policy_fingerprint,
        original_record_count=len(observations),
        matches=matches,
        trip_summaries=trip_summaries,
        directional_summaries=directional_summaries,
        dataset_summary=dataset_summary,
        issue_codes=issue_codes,
        limitations=limitations_tuple,
    )
    return TripRidershipAnalysisV1(
        dataset_id=metadata.dataset_id,
        source_type=metadata.source_type,
        confidence=metadata.confidence,
        operating_day_type=metadata.operating_day_type,
        scenario_b_timetable_fingerprint=b_fingerprint,
        trip_ridership_input_fingerprint=input_fingerprint,
        match_policy=policy,
        matching_policy_fingerprint=policy_fingerprint,
        analysis_fingerprint=analysis_fingerprint,
        original_record_count=len(observations),
        match_rows=matches,
        trip_summaries=trip_summaries,
        directional_summaries=directional_summaries,
        dataset_summary=dataset_summary,
        issue_codes=issue_codes,
        limitations=limitations_tuple,
    )


def trip_ridership_analysis_is_current_v1(
    analysis: TripRidershipAnalysisV1 | None,
    imported: ImportedWorkbook | None,
    scenario_b_timetable_fingerprint: str | None,
) -> bool:
    if (
        not isinstance(analysis, TripRidershipAnalysisV1)
        or imported is None
        or imported.trip_ridership_metadata is None
        or not imported.trip_ridership_observations
        or not scenario_b_timetable_fingerprint
        or analysis.scenario_b_timetable_fingerprint != scenario_b_timetable_fingerprint
    ):
        return False

    metadata = imported.trip_ridership_metadata
    current_input_fingerprint = trip_ridership_input_fingerprint_v1(
        imported,
        scenario_b_timetable_fingerprint,
    )
    if (
        current_input_fingerprint is None
        or analysis.trip_ridership_input_fingerprint != current_input_fingerprint
        or analysis.dataset_id != metadata.dataset_id
        or analysis.source_type != metadata.source_type
        or analysis.confidence != metadata.confidence
        or analysis.operating_day_type != metadata.operating_day_type
        or analysis.match_policy.observed_schedule_scenario != metadata.observed_schedule_scenario
        or analysis.match_policy.match_tolerance_minutes != metadata.match_tolerance_minutes
        or analysis.matching_policy_fingerprint != _canonical_sha256(analysis.match_policy)
        or analysis.original_record_count != len(imported.trip_ridership_observations)
        or analysis.original_record_count != len(analysis.match_rows)
    ):
        return False

    expected_analysis_fingerprint = _analysis_fingerprint_v1(
        trip_ridership_input_fingerprint=analysis.trip_ridership_input_fingerprint,
        matching_policy_fingerprint=analysis.matching_policy_fingerprint,
        original_record_count=analysis.original_record_count,
        matches=analysis.match_rows,
        trip_summaries=analysis.trip_summaries,
        directional_summaries=analysis.directional_summaries,
        dataset_summary=analysis.dataset_summary,
        issue_codes=analysis.issue_codes,
        limitations=analysis.limitations,
    )
    return analysis.analysis_fingerprint == expected_analysis_fingerprint


__all__ = [
    "AMBIGUOUS_TRIP_TIME_MATCH",
    "DUPLICATE_OBSERVATION_FOR_TRIP_DATE",
    "DUPLICATE_TRIP_RIDERSHIP_OBSERVATION_ID",
    "EXPLICIT_SCHEDULED_TIME_MISMATCH",
    "EXPLICIT_SCHEDULED_TRIP_ID_NOT_FOUND",
    "EXPLICIT_TRIP_DIRECTION_MISMATCH",
    "NO_TRIP_WITHIN_MATCH_TOLERANCE",
    "TRIP_RIDERSHIP_ANALYSIS_FAILED",
    "TRIP_RIDERSHIP_COMBINED_DIRECTION_NOT_ALLOWED",
    "TRIP_RIDERSHIP_CONFIDENCE_INVALID",
    "TRIP_RIDERSHIP_DATASET_ID_MISSING",
    "TRIP_RIDERSHIP_DIRECTION_INVALID",
    "TRIP_RIDERSHIP_FORMULA_NOT_ALLOWED",
    "TRIP_RIDERSHIP_MATCH_TOLERANCE_INVALID",
    "TRIP_RIDERSHIP_METADATA_MISSING",
    "TRIP_RIDERSHIP_NO_USABLE_MATCHES",
    "TRIP_RIDERSHIP_OPERATING_DAY_TYPE_MISMATCH",
    "TRIP_RIDERSHIP_PASSENGER_COUNT_INVALID",
    "TRIP_RIDERSHIP_REFERENCE_MISSING",
    "TRIP_RIDERSHIP_SCENARIO_INVALID",
    "TRIP_RIDERSHIP_SOURCE_TYPE_INVALID",
    "analyze_trip_ridership_v1",
    "trip_ridership_analysis_is_current_v1",
    "trip_ridership_day_type_matches_timetable_v1",
    "trip_ridership_input_fingerprint_v1",
]
