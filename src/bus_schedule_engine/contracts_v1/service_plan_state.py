"""Canonical immutable search state and finite ServicePlan neighborhood for V1."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

SERVICE_PLAN_STATE_PROFILE_V1 = "service_plan_state_v1"
SERVICE_PLAN_FINGERPRINT_PROFILE_V1 = "service_plan_state_fingerprint_v1"


class ServicePlanMoveV1(StrEnum):
    MERGE_ADJACENT = "MERGE_ADJACENT"
    SPLIT_REGIME = "SPLIT_REGIME"
    SHIFT_BOUNDARY_LEFT = "SHIFT_BOUNDARY_LEFT"
    SHIFT_BOUNDARY_RIGHT = "SHIFT_BOUNDARY_RIGHT"
    MOVE_ONE_TRIP_LEFT_TO_RIGHT = "MOVE_ONE_TRIP_LEFT_TO_RIGHT"
    MOVE_ONE_TRIP_RIGHT_TO_LEFT = "MOVE_ONE_TRIP_RIGHT_TO_LEFT"
    TAIL_ABSORB_ONE = "TAIL_ABSORB_ONE"
    TAIL_RELEASE_ONE = "TAIL_RELEASE_ONE"


@dataclass(frozen=True, slots=True)
class ServiceRegimeDecisionV1:
    start: int
    end: int
    trip_count: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("ServiceRegime must be a positive half-open interval")
        if self.start % 60 or self.end % 60:
            raise ValueError("ServiceRegime boundaries must be whole-minute values")
        if isinstance(self.trip_count, bool) or self.trip_count < 2:
            raise ValueError("ServiceRegime trip_count must be an integer >= 2")

    @property
    def duration_minutes(self) -> int:
        return (self.end - self.start) // 60


@dataclass(frozen=True, slots=True)
class ServicePlanStateV1:
    route_id: str
    direction: str
    fixed_first_departure: int
    fixed_last_departure: int
    service_regimes: tuple[ServiceRegimeDecisionV1, ...]
    seed_id: str
    parent_fingerprint: str | None = None
    operation: str | None = None
    operation_evidence: str | None = None

    def __post_init__(self) -> None:
        if not self.route_id.strip():
            raise ValueError("route_id is required")
        if self.direction not in {"outbound", "inbound"}:
            raise ValueError("direction must be outbound or inbound")
        if not self.service_regimes:
            raise ValueError("at least one ServiceRegime is required")
        if not (
            self.service_regimes[0].start
            <= self.fixed_first_departure
            <= self.fixed_last_departure
            < self.service_regimes[-1].end
        ):
            raise ValueError("fixed endpoints must lie in the ServicePlan window")
        for left, right in zip(self.service_regimes, self.service_regimes[1:], strict=False):
            if left.end != right.start:
                raise ValueError("ServiceRegimes must be ordered, contiguous, and non-overlapping")

    @property
    def total_trips(self) -> int:
        return sum(item.trip_count for item in self.service_regimes)

    @property
    def boundaries(self) -> tuple[int, ...]:
        return tuple(item.end for item in self.service_regimes[:-1])

    @property
    def trip_count_vector(self) -> tuple[int, ...]:
        return tuple(item.trip_count for item in self.service_regimes)


@dataclass(frozen=True, slots=True)
class ServicePlanNeighborV1:
    move: ServicePlanMoveV1
    affected_index: int
    priority: int
    evidence_code: str | None
    state: ServicePlanStateV1


def service_plan_fingerprint_payload_v1(state: ServicePlanStateV1) -> dict[str, Any]:
    """Return only authoritative state identity; history never changes cache identity."""

    return {
        "profile": SERVICE_PLAN_FINGERPRINT_PROFILE_V1,
        "route_id": state.route_id,
        "direction": state.direction,
        "fixed_first_departure": state.fixed_first_departure,
        "fixed_last_departure": state.fixed_last_departure,
        "service_boundaries": [
            state.service_regimes[0].start,
            *(item.end for item in state.service_regimes),
        ],
        "trip_count_vector": list(state.trip_count_vector),
    }


def service_plan_fingerprint_v1(state: ServicePlanStateV1) -> str:
    payload = json.dumps(
        service_plan_fingerprint_payload_v1(state),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def minimum_trip_count_v1(
    regime: ServiceRegimeDecisionV1,
    floor_headway_minutes: float | None,
) -> int:
    if floor_headway_minutes is None:
        return 2
    if not math.isfinite(floor_headway_minutes) or floor_headway_minutes <= 0:
        raise ValueError("floor_headway_minutes must be finite and positive")
    return max(2, math.ceil(regime.duration_minutes / floor_headway_minutes))


def _state_minimum_trip_count(
    state: ServicePlanStateV1,
    regime: ServiceRegimeDecisionV1,
    floor_headway_minutes: float | None,
) -> int:
    if floor_headway_minutes is None:
        return 2
    effective_start = max(regime.start, state.fixed_first_departure)
    effective_end = min(regime.end, state.fixed_last_departure)
    effective_minutes = max(1, (effective_end - effective_start) // 60)
    return max(2, math.ceil(effective_minutes / floor_headway_minutes))


def validate_service_plan_state_v1(
    state: ServicePlanStateV1,
    *,
    authoritative_total_trips: int,
    planning_grid_seconds: int,
    floor_headway_minutes: float | None,
) -> tuple[str, ...]:
    errors: list[str] = []
    if state.total_trips != authoritative_total_trips:
        errors.append("FIXED_TOTAL_TRIPS")
    if planning_grid_seconds <= 0 or planning_grid_seconds % 60:
        raise ValueError("planning_grid_seconds must be a positive whole-minute grid")
    window_start = state.service_regimes[0].start
    for boundary in state.boundaries:
        if (boundary - window_start) % planning_grid_seconds:
            errors.append("NON_CANONICAL_SERVICE_BOUNDARY")
            break
    for regime in state.service_regimes:
        if regime.trip_count < _state_minimum_trip_count(state, regime, floor_headway_minutes):
            errors.append("MINIMUM_SERVICE_FLOOR")
            break
    return tuple(errors)


def _child_state(
    state: ServicePlanStateV1,
    regimes: Sequence[ServiceRegimeDecisionV1],
    *,
    move: ServicePlanMoveV1,
    affected_index: int,
    evidence_code: str | None,
) -> ServicePlanStateV1:
    return ServicePlanStateV1(
        route_id=state.route_id,
        direction=state.direction,
        fixed_first_departure=state.fixed_first_departure,
        fixed_last_departure=state.fixed_last_departure,
        service_regimes=tuple(regimes),
        seed_id=state.seed_id,
        parent_fingerprint=service_plan_fingerprint_v1(state),
        operation=move.value,
        operation_evidence=evidence_code,
    )


def _is_floor_feasible(
    state: ServicePlanStateV1,
    regimes: Iterable[ServiceRegimeDecisionV1],
    floor_headway_minutes: float | None,
) -> bool:
    return all(
        regime.trip_count >= _state_minimum_trip_count(state, regime, floor_headway_minutes)
        for regime in regimes
    )


def _target_indices(length: int, affected_indices: Iterable[int] | None) -> tuple[int, ...]:
    if affected_indices is None:
        return tuple(range(length))
    return tuple(sorted(index for index in set(affected_indices) if 0 <= index < length))


def merge_adjacent_neighbors_v1(
    state: ServicePlanStateV1,
    *,
    floor_headway_minutes: float | None,
    evidence_code: str | None = None,
    priority: int = 1,
    affected_indices: Iterable[int] | None = None,
) -> tuple[ServicePlanNeighborV1, ...]:
    result: list[ServicePlanNeighborV1] = []
    for index in _target_indices(len(state.service_regimes) - 1, affected_indices):
        left = state.service_regimes[index]
        right = state.service_regimes[index + 1]
        merged = ServiceRegimeDecisionV1(left.start, right.end, left.trip_count + right.trip_count)
        if not _is_floor_feasible(state, (merged,), floor_headway_minutes):
            continue
        regimes = (*state.service_regimes[:index], merged, *state.service_regimes[index + 2 :])
        result.append(
            ServicePlanNeighborV1(
                ServicePlanMoveV1.MERGE_ADJACENT,
                index,
                priority,
                evidence_code,
                _child_state(
                    state,
                    regimes,
                    move=ServicePlanMoveV1.MERGE_ADJACENT,
                    affected_index=index,
                    evidence_code=evidence_code,
                ),
            )
        )
    return tuple(result)


def split_regime_neighbors_v1(
    state: ServicePlanStateV1,
    *,
    planning_grid_seconds: int,
    floor_headway_minutes: float | None,
    evidence_code: str | None = None,
    priority: int = 1,
    affected_indices: Iterable[int] | None = None,
    split_boundary_seconds: Iterable[int] | None = None,
) -> tuple[ServicePlanNeighborV1, ...]:
    """Enumerate every grid-aligned split and every floor-feasible integer allocation."""

    result: list[ServicePlanNeighborV1] = []
    window_start = state.service_regimes[0].start
    target_boundaries = None if split_boundary_seconds is None else set(split_boundary_seconds)
    for index in _target_indices(len(state.service_regimes), affected_indices):
        parent = state.service_regimes[index]
        first = parent.start + planning_grid_seconds
        for boundary in range(first, parent.end, planning_grid_seconds):
            if (boundary - window_start) % planning_grid_seconds:
                continue
            if target_boundaries is not None and boundary not in target_boundaries:
                continue
            left_shell = ServiceRegimeDecisionV1(parent.start, boundary, 2)
            right_shell = ServiceRegimeDecisionV1(boundary, parent.end, 2)
            left_min = _state_minimum_trip_count(state, left_shell, floor_headway_minutes)
            right_min = _state_minimum_trip_count(state, right_shell, floor_headway_minutes)
            for left_count in range(left_min, parent.trip_count - right_min + 1):
                right_count = parent.trip_count - left_count
                left = ServiceRegimeDecisionV1(parent.start, boundary, left_count)
                right = ServiceRegimeDecisionV1(boundary, parent.end, right_count)
                regimes = (
                    *state.service_regimes[:index],
                    left,
                    right,
                    *state.service_regimes[index + 1 :],
                )
                result.append(
                    ServicePlanNeighborV1(
                        ServicePlanMoveV1.SPLIT_REGIME,
                        index,
                        priority,
                        evidence_code,
                        _child_state(
                            state,
                            regimes,
                            move=ServicePlanMoveV1.SPLIT_REGIME,
                            affected_index=index,
                            evidence_code=evidence_code,
                        ),
                    )
                )
    return tuple(result)


def _shift_boundary_neighbors(
    state: ServicePlanStateV1,
    *,
    delta_seconds: int,
    move: ServicePlanMoveV1,
    planning_grid_seconds: int,
    floor_headway_minutes: float | None,
    evidence_code: str | None,
    priority: int,
    affected_indices: Iterable[int] | None,
    max_trip_count_delta: int | None,
) -> tuple[ServicePlanNeighborV1, ...]:
    if abs(delta_seconds) != planning_grid_seconds:
        raise ValueError("boundary shifts must be exactly one planning bucket")
    if max_trip_count_delta is not None and (
        isinstance(max_trip_count_delta, bool)
        or not isinstance(max_trip_count_delta, int)
        or max_trip_count_delta < 0
    ):
        raise ValueError("max_trip_count_delta must be a non-negative integer or None")
    result: list[ServicePlanNeighborV1] = []
    for index in _target_indices(len(state.service_regimes) - 1, affected_indices):
        left = state.service_regimes[index]
        right = state.service_regimes[index + 1]
        boundary = left.end + delta_seconds
        if boundary <= left.start or boundary >= right.end:
            continue
        left_shell = ServiceRegimeDecisionV1(left.start, boundary, 2)
        right_shell = ServiceRegimeDecisionV1(boundary, right.end, 2)
        combined = left.trip_count + right.trip_count
        left_min = _state_minimum_trip_count(state, left_shell, floor_headway_minutes)
        right_min = _state_minimum_trip_count(state, right_shell, floor_headway_minutes)
        left_max = combined - right_min
        if max_trip_count_delta is not None:
            left_min = max(left_min, left.trip_count - max_trip_count_delta)
            left_max = min(left_max, left.trip_count + max_trip_count_delta)
        for left_count in range(left_min, left_max + 1):
            shifted_left = ServiceRegimeDecisionV1(left.start, boundary, left_count)
            shifted_right = ServiceRegimeDecisionV1(boundary, right.end, combined - left_count)
            regimes = (
                *state.service_regimes[:index],
                shifted_left,
                shifted_right,
                *state.service_regimes[index + 2 :],
            )
            result.append(
                ServicePlanNeighborV1(
                    move,
                    index,
                    priority,
                    evidence_code,
                    _child_state(
                        state,
                        regimes,
                        move=move,
                        affected_index=index,
                        evidence_code=evidence_code,
                    ),
                )
            )
    return tuple(result)


def shift_boundary_left_neighbors_v1(
    state: ServicePlanStateV1,
    *,
    planning_grid_seconds: int,
    floor_headway_minutes: float | None,
    evidence_code: str | None = None,
    priority: int = 1,
    affected_indices: Iterable[int] | None = None,
    max_trip_count_delta: int | None = None,
) -> tuple[ServicePlanNeighborV1, ...]:
    return _shift_boundary_neighbors(
        state,
        delta_seconds=-planning_grid_seconds,
        move=ServicePlanMoveV1.SHIFT_BOUNDARY_LEFT,
        planning_grid_seconds=planning_grid_seconds,
        floor_headway_minutes=floor_headway_minutes,
        evidence_code=evidence_code,
        priority=priority,
        affected_indices=affected_indices,
        max_trip_count_delta=max_trip_count_delta,
    )


def shift_boundary_right_neighbors_v1(
    state: ServicePlanStateV1,
    *,
    planning_grid_seconds: int,
    floor_headway_minutes: float | None,
    evidence_code: str | None = None,
    priority: int = 1,
    affected_indices: Iterable[int] | None = None,
    max_trip_count_delta: int | None = None,
) -> tuple[ServicePlanNeighborV1, ...]:
    return _shift_boundary_neighbors(
        state,
        delta_seconds=planning_grid_seconds,
        move=ServicePlanMoveV1.SHIFT_BOUNDARY_RIGHT,
        planning_grid_seconds=planning_grid_seconds,
        floor_headway_minutes=floor_headway_minutes,
        evidence_code=evidence_code,
        priority=priority,
        affected_indices=affected_indices,
        max_trip_count_delta=max_trip_count_delta,
    )


def _move_one_neighbors(
    state: ServicePlanStateV1,
    *,
    left_delta: int,
    move: ServicePlanMoveV1,
    floor_headway_minutes: float | None,
    evidence_code: str | None,
    priority: int,
    only_final_pair: bool = False,
    affected_indices: Iterable[int] | None = None,
) -> tuple[ServicePlanNeighborV1, ...]:
    result: list[ServicePlanNeighborV1] = []
    pairs = range(len(state.service_regimes) - 1)
    if only_final_pair:
        pairs = range(max(0, len(state.service_regimes) - 2), len(state.service_regimes) - 1)
    elif affected_indices is not None:
        pairs = _target_indices(len(state.service_regimes) - 1, affected_indices)
    for index in pairs:
        left = state.service_regimes[index]
        right = state.service_regimes[index + 1]
        if left.trip_count + left_delta < 2 or right.trip_count - left_delta < 2:
            continue
        changed_left = ServiceRegimeDecisionV1(left.start, left.end, left.trip_count + left_delta)
        changed_right = ServiceRegimeDecisionV1(
            right.start, right.end, right.trip_count - left_delta
        )
        if not _is_floor_feasible(state, (changed_left, changed_right), floor_headway_minutes):
            continue
        regimes = (
            *state.service_regimes[:index],
            changed_left,
            changed_right,
            *state.service_regimes[index + 2 :],
        )
        result.append(
            ServicePlanNeighborV1(
                move,
                index,
                priority,
                evidence_code,
                _child_state(
                    state,
                    regimes,
                    move=move,
                    affected_index=index,
                    evidence_code=evidence_code,
                ),
            )
        )
    return tuple(result)


def move_one_trip_left_to_right_neighbors_v1(
    state: ServicePlanStateV1,
    *,
    floor_headway_minutes: float | None,
    evidence_code: str | None = None,
    priority: int = 1,
    affected_indices: Iterable[int] | None = None,
) -> tuple[ServicePlanNeighborV1, ...]:
    return _move_one_neighbors(
        state,
        left_delta=-1,
        move=ServicePlanMoveV1.MOVE_ONE_TRIP_LEFT_TO_RIGHT,
        floor_headway_minutes=floor_headway_minutes,
        evidence_code=evidence_code,
        priority=priority,
        affected_indices=affected_indices,
    )


def move_one_trip_right_to_left_neighbors_v1(
    state: ServicePlanStateV1,
    *,
    floor_headway_minutes: float | None,
    evidence_code: str | None = None,
    priority: int = 1,
    affected_indices: Iterable[int] | None = None,
) -> tuple[ServicePlanNeighborV1, ...]:
    return _move_one_neighbors(
        state,
        left_delta=1,
        move=ServicePlanMoveV1.MOVE_ONE_TRIP_RIGHT_TO_LEFT,
        floor_headway_minutes=floor_headway_minutes,
        evidence_code=evidence_code,
        priority=priority,
        affected_indices=affected_indices,
    )


def tail_absorb_one_neighbors_v1(
    state: ServicePlanStateV1,
    *,
    floor_headway_minutes: float | None,
    evidence_code: str | None = None,
    priority: int = 1,
) -> tuple[ServicePlanNeighborV1, ...]:
    return _move_one_neighbors(
        state,
        left_delta=-1,
        move=ServicePlanMoveV1.TAIL_ABSORB_ONE,
        floor_headway_minutes=floor_headway_minutes,
        evidence_code=evidence_code,
        priority=priority,
        only_final_pair=True,
    )


def tail_release_one_neighbors_v1(
    state: ServicePlanStateV1,
    *,
    floor_headway_minutes: float | None,
    evidence_code: str | None = None,
    priority: int = 1,
) -> tuple[ServicePlanNeighborV1, ...]:
    return _move_one_neighbors(
        state,
        left_delta=1,
        move=ServicePlanMoveV1.TAIL_RELEASE_ONE,
        floor_headway_minutes=floor_headway_minutes,
        evidence_code=evidence_code,
        priority=priority,
        only_final_pair=True,
    )


__all__ = [
    "SERVICE_PLAN_FINGERPRINT_PROFILE_V1",
    "SERVICE_PLAN_STATE_PROFILE_V1",
    "ServicePlanMoveV1",
    "ServicePlanNeighborV1",
    "ServicePlanStateV1",
    "ServiceRegimeDecisionV1",
    "merge_adjacent_neighbors_v1",
    "minimum_trip_count_v1",
    "move_one_trip_left_to_right_neighbors_v1",
    "move_one_trip_right_to_left_neighbors_v1",
    "service_plan_fingerprint_payload_v1",
    "service_plan_fingerprint_v1",
    "shift_boundary_left_neighbors_v1",
    "shift_boundary_right_neighbors_v1",
    "split_regime_neighbors_v1",
    "tail_absorb_one_neighbors_v1",
    "tail_release_one_neighbors_v1",
    "validate_service_plan_state_v1",
]
