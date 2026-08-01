"""Internal deterministic 6A2B authority projection for OR-Tools quality search."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from bus_schedule_engine.models import ProtectedServiceFloorEnforcementAuthorityV1
from bus_schedule_engine.protected_service_floor_enforcement import (
    protected_service_floor_enforcement_authority_is_valid_v1,
)

from .models import ContractDirection, ScenarioBInput
from .serialization import canonical_sha256, scenario_fingerprint

ORTOOLS_PROTECTED_FLOOR_PROJECTION_PROFILE = "m6a2d_ortools_protected_service_floor_projection_v1"
ORTOOLS_PROTECTED_FLOOR_PROJECTION_INVALID = "ORTOOLS_PROTECTED_FLOOR_PROJECTION_INVALID"


class OrToolsProtectedFloorProjectionError(ValueError):
    """A protected-floor authority cannot be projected onto canonical source variables."""

    code = ORTOOLS_PROTECTED_FLOOR_PROJECTION_INVALID


@dataclass(frozen=True, slots=True)
class OrToolsProtectedFloorRegimeProjectionV1:
    regime_id: str
    direction: ContractDirection
    ordered_b_trip_ids: tuple[str, ...]
    source_indices: tuple[int, ...]
    first_source_index: int
    last_source_index: int
    maximum_future_c_headway_minutes: int
    minimum_future_c_trip_count: int
    protected_window_start_minutes: int
    protected_window_end_minutes: int
    boundary_tolerance_minutes: int
    donor_removal_prohibited: bool


@dataclass(frozen=True, slots=True)
class OrToolsProtectedFloorProjectionV1:
    projection_profile: str
    enforcement_fingerprint: str
    scenario_b_fingerprint: str
    regimes: tuple[OrToolsProtectedFloorRegimeProjectionV1, ...]
    projection_fingerprint: str

    @property
    def source_member_count(self) -> int:
        return sum(len(regime.ordered_b_trip_ids) for regime in self.regimes)

    @property
    def internal_pair_constraint_count(self) -> int:
        return sum(regime.last_source_index - regime.first_source_index for regime in self.regimes)

    @property
    def boundary_constraint_count(self) -> int:
        return 2 * len(self.regimes)

    @property
    def donor_constraint_count(self) -> int:
        return sum(
            len(regime.ordered_b_trip_ids)
            for regime in self.regimes
            if regime.donor_removal_prohibited
        )


def _projection_payload(
    *,
    enforcement_fingerprint: str,
    scenario_b_fingerprint: str,
    regimes: tuple[OrToolsProtectedFloorRegimeProjectionV1, ...],
) -> dict[str, object]:
    return {
        "profile": ORTOOLS_PROTECTED_FLOOR_PROJECTION_PROFILE,
        "enforcement_fingerprint": enforcement_fingerprint,
        "scenario_b_fingerprint": scenario_b_fingerprint,
        "regimes": [asdict(regime) for regime in regimes],
    }


def _raise_projection_error(detail: str) -> None:
    raise OrToolsProtectedFloorProjectionError(
        f"{ORTOOLS_PROTECTED_FLOOR_PROJECTION_INVALID}: {detail}"
    )


def _directional_trips(scenario_b: ScenarioBInput) -> dict[ContractDirection, tuple]:
    return {
        direction: tuple(
            sorted(
                (trip for trip in scenario_b.exact_timetable if trip.direction == direction),
                key=lambda trip: (trip.departure_time, trip.trip_id),
            )
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    }


def _validate_exact_b_floor(
    regime: OrToolsProtectedFloorRegimeProjectionV1,
    directional_trips: tuple,
) -> None:
    source_slice = directional_trips[regime.first_source_index : regime.last_source_index + 1]
    if len(source_slice) < regime.minimum_future_c_trip_count:
        _raise_projection_error("the fixed inclusive source slice is below the trip-count floor")
    start = regime.protected_window_start_minutes
    end = regime.protected_window_end_minutes
    tolerance = regime.boundary_tolerance_minutes
    protected_by_id = {trip.trip_id: trip for trip in directional_trips}
    protected_minutes = tuple(
        protected_by_id[source_id].departure_time // 60 for source_id in regime.ordered_b_trip_ids
    )
    if regime.donor_removal_prohibited and any(
        minute < start - tolerance or minute > end + tolerance for minute in protected_minutes
    ):
        _raise_projection_error("exact Scenario B violates its projected donor interval")
    if (
        abs(protected_minutes[0] - start) > tolerance
        or abs(protected_minutes[-1] - end) > tolerance
    ):
        _raise_projection_error("exact Scenario B violates its projected window boundary")
    for earlier, later in zip(source_slice, source_slice[1:], strict=False):
        gap_seconds = later.departure_time - earlier.departure_time
        if (
            gap_seconds <= 0
            or gap_seconds % 60 != 0
            or gap_seconds // 60 > regime.maximum_future_c_headway_minutes
        ):
            _raise_projection_error("exact Scenario B violates a projected internal headway")


def validate_ortools_protected_floor_projection_v1(
    projection: OrToolsProtectedFloorProjectionV1,
    scenario_b: ScenarioBInput,
) -> None:
    """Fail closed if a projection no longer mechanically matches Scenario B."""
    if not isinstance(projection, OrToolsProtectedFloorProjectionV1):
        _raise_projection_error("projection type is invalid")
    if (
        projection.projection_profile != ORTOOLS_PROTECTED_FLOOR_PROJECTION_PROFILE
        or projection.scenario_b_fingerprint != scenario_fingerprint(scenario_b)
        or not projection.regimes
    ):
        _raise_projection_error("projection identity or Scenario B binding is invalid")
    expected_fingerprint = canonical_sha256(
        _projection_payload(
            enforcement_fingerprint=projection.enforcement_fingerprint,
            scenario_b_fingerprint=projection.scenario_b_fingerprint,
            regimes=projection.regimes,
        )
    )
    if projection.projection_fingerprint != expected_fingerprint:
        _raise_projection_error("projection fingerprint is inconsistent")
    direction_order = {
        ContractDirection.OUTBOUND: 0,
        ContractDirection.INBOUND: 1,
    }
    if (
        any(regime.direction not in direction_order for regime in projection.regimes)
        or tuple(
            sorted(
                projection.regimes,
                key=lambda regime: (
                    direction_order[regime.direction],
                    regime.protected_window_start_minutes,
                    regime.protected_window_end_minutes,
                    regime.regime_id,
                ),
            )
        )
        != projection.regimes
    ):
        _raise_projection_error("projected regimes are not in deterministic authority order")

    directional = _directional_trips(scenario_b)
    source_occurrences: dict[str, int] = {}
    for trip in scenario_b.exact_timetable:
        source_occurrences[trip.trip_id] = source_occurrences.get(trip.trip_id, 0) + 1
    used_members: set[str] = set()
    last_slice_end_by_direction: dict[ContractDirection, int] = {}
    for regime in projection.regimes:
        trips = directional[regime.direction]
        index_by_id = {trip.trip_id: index for index, trip in enumerate(trips)}
        if (
            not regime.regime_id
            or not regime.ordered_b_trip_ids
            or len(regime.ordered_b_trip_ids) != len(regime.source_indices)
            or any(
                source_occurrences.get(source_id) != 1 for source_id in regime.ordered_b_trip_ids
            )
            or used_members.intersection(regime.ordered_b_trip_ids)
            or regime.maximum_future_c_headway_minutes <= 0
            or regime.minimum_future_c_trip_count <= 0
            or regime.boundary_tolerance_minutes < 0
            or not regime.donor_removal_prohibited
        ):
            _raise_projection_error("projected regime facts are invalid")
        expected_indices = tuple(
            index_by_id.get(source_id, -1) for source_id in regime.ordered_b_trip_ids
        )
        if (
            expected_indices != regime.source_indices
            or any(index < 0 for index in expected_indices)
            or tuple(sorted(expected_indices)) != expected_indices
            or len(set(expected_indices)) != len(expected_indices)
            or regime.first_source_index != expected_indices[0]
            or regime.last_source_index != expected_indices[-1]
        ):
            _raise_projection_error("protected source order or indices are invalid")
        previous_end = last_slice_end_by_direction.get(regime.direction)
        if previous_end is not None and regime.first_source_index <= previous_end:
            _raise_projection_error("same-direction protected source slices overlap")
        first = trips[regime.first_source_index]
        last = trips[regime.last_source_index]
        if (
            first.departure_time % 60 != 0
            or last.departure_time % 60 != 0
            or first.departure_time // 60 != regime.protected_window_start_minutes
            or last.departure_time // 60 != regime.protected_window_end_minutes
            or regime.protected_window_start_minutes > regime.protected_window_end_minutes
        ):
            _raise_projection_error("protected window boundaries are stale or not minute-aligned")
        if (
            regime.last_source_index - regime.first_source_index + 1
            < regime.minimum_future_c_trip_count
        ):
            _raise_projection_error("the structural source count cannot satisfy the floor")
        _validate_exact_b_floor(regime, trips)
        used_members.update(regime.ordered_b_trip_ids)
        last_slice_end_by_direction[regime.direction] = regime.last_source_index


def build_ortools_protected_floor_projection_v1(
    authority: ProtectedServiceFloorEnforcementAuthorityV1,
    scenario_b: ScenarioBInput,
) -> OrToolsProtectedFloorProjectionV1 | None:
    """Mechanically project a valid 6A2B authority; never reclassify protection."""
    if not protected_service_floor_enforcement_authority_is_valid_v1(authority, scenario_b):
        _raise_projection_error("enforcement authority is malformed or stale")
    if not authority.has_enforceable_regimes:
        return None

    directional = _directional_trips(scenario_b)
    source_occurrences: dict[str, int] = {}
    for trip in scenario_b.exact_timetable:
        source_occurrences[trip.trip_id] = source_occurrences.get(trip.trip_id, 0) + 1
    regimes: list[OrToolsProtectedFloorRegimeProjectionV1] = []
    for regime in authority.protected_regimes:
        direction = ContractDirection(regime.direction.value)
        trips = directional[direction]
        index_by_id = {trip.trip_id: index for index, trip in enumerate(trips)}
        if any(source_occurrences.get(source_id) != 1 for source_id in regime.ordered_b_trip_ids):
            _raise_projection_error("a protected source ID does not exist exactly once")
        indices = tuple(index_by_id.get(source_id, -1) for source_id in regime.ordered_b_trip_ids)
        if any(index < 0 for index in indices):
            _raise_projection_error("a protected source is missing from its declared direction")
        if regime.protected_window_start % 60 != 0 or regime.protected_window_end % 60 != 0:
            _raise_projection_error("protected window boundaries must be minute-aligned")
        regimes.append(
            OrToolsProtectedFloorRegimeProjectionV1(
                regime_id=regime.regime_id,
                direction=direction,
                ordered_b_trip_ids=regime.ordered_b_trip_ids,
                source_indices=indices,
                first_source_index=indices[0],
                last_source_index=indices[-1],
                maximum_future_c_headway_minutes=(regime.maximum_future_c_headway_minutes),
                minimum_future_c_trip_count=regime.minimum_future_c_trip_count,
                protected_window_start_minutes=regime.protected_window_start // 60,
                protected_window_end_minutes=regime.protected_window_end // 60,
                boundary_tolerance_minutes=(regime.future_boundary_tolerance_minutes),
                donor_removal_prohibited=regime.donor_removal_prohibited,
            )
        )
    projected = tuple(regimes)
    projection = OrToolsProtectedFloorProjectionV1(
        projection_profile=ORTOOLS_PROTECTED_FLOOR_PROJECTION_PROFILE,
        enforcement_fingerprint=authority.enforcement_fingerprint,
        scenario_b_fingerprint=authority.scenario_b_fingerprint,
        regimes=projected,
        projection_fingerprint=canonical_sha256(
            _projection_payload(
                enforcement_fingerprint=authority.enforcement_fingerprint,
                scenario_b_fingerprint=authority.scenario_b_fingerprint,
                regimes=projected,
            )
        ),
    )
    validate_ortools_protected_floor_projection_v1(projection, scenario_b)
    return projection


__all__ = [
    "ORTOOLS_PROTECTED_FLOOR_PROJECTION_INVALID",
    "ORTOOLS_PROTECTED_FLOOR_PROJECTION_PROFILE",
    "OrToolsProtectedFloorProjectionError",
    "OrToolsProtectedFloorProjectionV1",
    "OrToolsProtectedFloorRegimeProjectionV1",
    "build_ortools_protected_floor_projection_v1",
    "validate_ortools_protected_floor_projection_v1",
]
