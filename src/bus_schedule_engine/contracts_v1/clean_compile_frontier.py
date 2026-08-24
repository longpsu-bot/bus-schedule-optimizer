"""Bounded deterministic clean-compilation frontier for a ServicePlan state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from .clean_boundary_compiler import (
    CLEAN_BOUNDARY_COMPILER_PROFILE_V1,
    CleanBoundaryCompilationStatusV1,
    CleanBoundaryCompilationV1,
    CompiledDemandRegimeSliceV1,
    DemandRegimeAllocationV1,
    OperationalEndpointAuthorityV1,
    _boundary_diagnostics,
    _build_service_regimes,
    _candidate_path,
    _phase_candidates,
    compile_clean_boundary_timetable_v1,
    validate_clean_boundary_compilation_v1,
)
from .service_plan_state import ServicePlanStateV1, service_plan_fingerprint_v1

CLEAN_COMPILE_FRONTIER_PROFILE_V1 = "clean_compile_frontier_v1"


@dataclass(frozen=True, slots=True)
class CleanCompileVariantV1:
    compilation_fingerprint: str
    frontier_rank: int
    headway_quantization: float
    actual_service_regime_count: int
    phase_edge_quality_minutes: int
    compilation: CleanBoundaryCompilationV1


@dataclass(frozen=True, slots=True)
class CleanCompileFrontierV1:
    profile: str
    service_plan_fingerprint: str
    compile_frontier_limit: int
    variants_considered: int
    phase_candidates_technical_pruned: int
    variants_dominance_pruned: int
    variants_limit_pruned: int
    deterministic_limit_order: str
    variants: tuple[CleanCompileVariantV1, ...]
    failure: CleanBoundaryCompilationV1 | None


@dataclass(frozen=True, slots=True)
class _FrontierPath:
    path: tuple[Any, ...]
    quantization: Fraction
    service_regime_count: int
    phase_edge_quality_minutes: int

    @property
    def headways(self) -> tuple[int, ...]:
        return tuple(item.headway_minutes for item in self.path)

    @property
    def departures(self) -> tuple[int, ...]:
        return tuple(value for item in self.path for value in item.departures_minutes)

    @property
    def objective(self) -> tuple[Fraction, int, int]:
        return (
            self.quantization,
            self.service_regime_count,
            self.phase_edge_quality_minutes,
        )

    @property
    def order_key(self) -> tuple[Any, ...]:
        return (*self.objective, self.headways, self.departures)


def clean_compilation_fingerprint_v1(compilation: CleanBoundaryCompilationV1) -> str:
    payload = {
        "route_id": compilation.route_id,
        "direction": compilation.direction,
        "exact_departures": list(compilation.exact_departures),
        "service_headways": [item.uniform_headway_minutes for item in compilation.service_regimes],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dominates_path(left: _FrontierPath, right: _FrontierPath) -> bool:
    left_values = left.objective
    right_values = right.objective
    return all(a <= b for a, b in zip(left_values, right_values, strict=True)) and any(
        a < b for a, b in zip(left_values, right_values, strict=True)
    )


def _nondominated_paths(paths: list[_FrontierPath]) -> list[_FrontierPath]:
    unique: dict[tuple[int, ...], _FrontierPath] = {}
    for path in paths:
        incumbent = unique.get(path.departures)
        if incumbent is None or path.order_key < incumbent.order_key:
            unique[path.departures] = path
    ordered = sorted(unique.values(), key=lambda item: item.order_key)
    return [
        candidate
        for candidate in ordered
        if not any(
            other is not candidate and _dominates_path(other, candidate) for other in ordered
        )
    ]


def _reachable_frontier_paths(
    phase_candidates: tuple[tuple[Any, ...], ...],
    *,
    compile_frontier_limit: int,
) -> list[_FrontierPath]:
    if not phase_candidates or not phase_candidates[0]:
        return []
    per_terminal_limit = max(16, compile_frontier_limit * 8)
    reachable: dict[int, list[_FrontierPath]] = {
        index: [
            _FrontierPath(
                path=(candidate,),
                quantization=candidate.quantization_error,
                service_regime_count=1,
                phase_edge_quality_minutes=candidate.phase_imbalance_minutes,
            )
        ]
        for index, candidate in enumerate(phase_candidates[0])
    }
    for regime_index in range(1, len(phase_candidates)):
        current_candidates = phase_candidates[regime_index]
        if not current_candidates:
            return []
        by_start: dict[int, list[int]] = {}
        by_predecessor: dict[int, list[int]] = {}
        for index, candidate in enumerate(current_candidates):
            by_start.setdefault(candidate.first_minute, []).append(index)
            by_predecessor.setdefault(
                candidate.first_minute - candidate.headway_minutes, []
            ).append(index)
        next_reachable: dict[int, list[_FrontierPath]] = {}
        previous_candidates = phase_candidates[regime_index - 1]
        for previous_index in sorted(reachable):
            previous = previous_candidates[previous_index]
            legal = set(by_start.get(previous.last_minute + previous.headway_minutes, ()))
            legal.update(by_predecessor.get(previous.last_minute, ()))
            for current_index in sorted(legal):
                current = current_candidates[current_index]
                bucket = next_reachable.setdefault(current_index, [])
                for path in reachable[previous_index]:
                    bucket.append(
                        _FrontierPath(
                            path=(*path.path, current),
                            quantization=path.quantization + current.quantization_error,
                            service_regime_count=(
                                path.service_regime_count
                                + (previous.headway_minutes != current.headway_minutes)
                            ),
                            phase_edge_quality_minutes=(
                                path.phase_edge_quality_minutes + current.phase_imbalance_minutes
                            ),
                        )
                    )
        if not next_reachable:
            return []
        reachable = {
            index: _nondominated_paths(paths)[:per_terminal_limit]
            for index, paths in next_reachable.items()
        }
    return _nondominated_paths(
        [path for terminal_paths in reachable.values() for path in terminal_paths]
    )


def _bounded_phase_candidates(
    candidates: tuple[Any, ...],
    *,
    witness: Any | None,
    limit: int,
) -> tuple[Any, ...]:
    """Keep deterministic headway, edge, and phase diversity under a technical cap."""

    if len(candidates) <= limit:
        return candidates
    by_headway: dict[int, list[Any]] = {}
    for candidate in candidates:
        by_headway.setdefault(candidate.headway_minutes, []).append(candidate)
    selected: dict[tuple[int, int], Any] = {}

    def keep(candidate: Any) -> None:
        selected[(candidate.headway_minutes, candidate.first_minute)] = candidate

    if witness is not None:
        keep(witness)
    for headway in sorted(by_headway):
        group = sorted(
            by_headway[headway],
            key=lambda item: (
                item.phase_imbalance_minutes,
                item.first_minute,
                item.departures_minutes,
            ),
        )
        keep(group[0])
        keep(min(group, key=lambda item: item.first_minute))
        keep(max(group, key=lambda item: item.first_minute))
    if len(selected) > limit:
        mandatory = sorted(
            selected.values(),
            key=lambda item: (
                item is not witness,
                item.quantization_error,
                item.phase_imbalance_minutes,
                item.headway_minutes,
                item.first_minute,
            ),
        )[:limit]
        selected = {
            (candidate.headway_minutes, candidate.first_minute): candidate
            for candidate in mandatory
        }
    ordered = sorted(
        candidates,
        key=lambda item: (
            item.quantization_error,
            item.phase_imbalance_minutes,
            item.headway_minutes,
            item.first_minute,
            item.departures_minutes,
        ),
    )
    for candidate in ordered:
        if len(selected) >= limit:
            break
        keep(candidate)
    return tuple(
        sorted(
            selected.values(),
            key=lambda item: (
                item.first_minute,
                item.headway_minutes,
                item.last_minute,
                item.departures_minutes,
            ),
        )
    )


def _regimes_from_state(state: ServicePlanStateV1) -> tuple[DemandRegimeAllocationV1, ...]:
    return tuple(
        DemandRegimeAllocationV1(
            regime_id=f"PLAN-{state.direction.upper()}-{index:02d}",
            start_time=regime.start,
            end_time=regime.end,
            allocated_trip_count=regime.trip_count,
            nominal_headway=regime.duration_minutes / regime.trip_count,
        )
        for index, regime in enumerate(state.service_regimes, start=1)
    )


def _compilation_from_path(
    *,
    state: ServicePlanStateV1,
    state_fingerprint: str,
    authority: OperationalEndpointAuthorityV1,
    regimes: tuple[DemandRegimeAllocationV1, ...],
    path: _FrontierPath,
    rank: int,
) -> CleanBoundaryCompilationV1:
    service_regimes, service_ids = _build_service_regimes(state.direction, regimes, path.path)
    slices = tuple(
        CompiledDemandRegimeSliceV1(
            demand_regime_id=regime.regime_id,
            demand_regime_start=regime.start_time,
            demand_regime_end=regime.end_time,
            authoritative_trip_count=regime.allocated_trip_count,
            service_regime_id=service_ids[index],
            uniform_headway_minutes=phase.headway_minutes,
            first_departure=phase.first_minute * 60,
            last_departure=phase.last_minute * 60,
            departures=tuple(item * 60 for item in phase.departures_minutes),
            headway_quantization_error=float(phase.quantization_error),
            phase_imbalance_minutes=phase.phase_imbalance_minutes,
        )
        for index, (regime, phase) in enumerate(zip(regimes, path.path, strict=True))
    )
    compilation = CleanBoundaryCompilationV1(
        compiler_profile=CLEAN_BOUNDARY_COMPILER_PROFILE_V1,
        route_id=state.route_id,
        direction=state.direction,
        candidate_id=f"SP-{state_fingerprint[:12]}-C{rank:03d}",
        status=CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES,
        endpoint_authority=authority,
        demand_regime_slices=slices,
        service_regimes=service_regimes,
        exact_departures=tuple(item * 60 for item in path.departures),
        boundary_diagnostics=_boundary_diagnostics(regimes, path.path),
        total_headway_quantization_error=float(path.quantization),
        total_phase_imbalance_minutes=path.phase_edge_quality_minutes,
        failure=None,
    )
    validate_clean_boundary_compilation_v1(compilation, regimes)
    return compilation


def compile_service_plan_frontier_v1(
    state: ServicePlanStateV1,
    *,
    endpoint_authority: OperationalEndpointAuthorityV1,
    compile_frontier_limit: int,
) -> CleanCompileFrontierV1:
    """Retain compiler-nondominated exact timetables before any fleet decision."""

    if compile_frontier_limit <= 0:
        raise ValueError("compile_frontier_limit must be positive")
    if (
        endpoint_authority.route_id != state.route_id
        or endpoint_authority.direction != state.direction
    ):
        raise ValueError("endpoint authority identity does not match ServicePlan")
    regimes = _regimes_from_state(state)
    raw_phase_candidates = tuple(
        _phase_candidates(
            regime,
            regime_index=index,
            regime_count=len(regimes),
            authority=endpoint_authority,
        )
        for index, regime in enumerate(regimes)
    )
    witness_path = _candidate_path(raw_phase_candidates)
    phase_candidate_limit = max(64, compile_frontier_limit * 16)
    phase_candidates = tuple(
        _bounded_phase_candidates(
            candidates,
            witness=(witness_path[index] if witness_path is not None else None),
            limit=phase_candidate_limit,
        )
        for index, candidates in enumerate(raw_phase_candidates)
    )
    phase_pruned = sum(
        len(raw) - len(bounded)
        for raw, bounded in zip(raw_phase_candidates, phase_candidates, strict=True)
    )
    paths = _reachable_frontier_paths(
        phase_candidates,
        compile_frontier_limit=compile_frontier_limit,
    )
    state_fingerprint = service_plan_fingerprint_v1(state)
    if not paths:
        failure = compile_clean_boundary_timetable_v1(
            route_id=state.route_id,
            direction=state.direction,
            candidate_id=f"SP-{state_fingerprint[:12]}-FAIL",
            regimes=regimes,
            endpoint_authority=endpoint_authority,
        )
        return CleanCompileFrontierV1(
            profile=CLEAN_COMPILE_FRONTIER_PROFILE_V1,
            service_plan_fingerprint=state_fingerprint,
            compile_frontier_limit=compile_frontier_limit,
            variants_considered=0,
            phase_candidates_technical_pruned=phase_pruned,
            variants_dominance_pruned=0,
            variants_limit_pruned=0,
            deterministic_limit_order=(
                "phase-cap-witness,quantization,service_regime_count,phase_edge_quality,headways,departures"
            ),
            variants=(),
            failure=failure,
        )
    paths.sort(key=lambda item: item.order_key)
    retained = paths[:compile_frontier_limit]
    variants: list[CleanCompileVariantV1] = []
    for rank, path in enumerate(retained, start=1):
        compilation = _compilation_from_path(
            state=state,
            state_fingerprint=state_fingerprint,
            authority=endpoint_authority,
            regimes=regimes,
            path=path,
            rank=rank,
        )
        variants.append(
            CleanCompileVariantV1(
                compilation_fingerprint=clean_compilation_fingerprint_v1(compilation),
                frontier_rank=rank,
                headway_quantization=float(path.quantization),
                actual_service_regime_count=len(compilation.service_regimes),
                phase_edge_quality_minutes=path.phase_edge_quality_minutes,
                compilation=compilation,
            )
        )
    considered = sum(len(items) for items in raw_phase_candidates)
    return CleanCompileFrontierV1(
        profile=CLEAN_COMPILE_FRONTIER_PROFILE_V1,
        service_plan_fingerprint=state_fingerprint,
        compile_frontier_limit=compile_frontier_limit,
        variants_considered=considered,
        phase_candidates_technical_pruned=phase_pruned,
        variants_dominance_pruned=max(0, considered - len(paths)),
        variants_limit_pruned=max(0, len(paths) - len(retained)),
        deterministic_limit_order=(
            "phase-cap-witness,quantization,service_regime_count,phase_edge_quality,headways,departures"
        ),
        variants=tuple(variants),
        failure=None,
    )


__all__ = [
    "CLEAN_COMPILE_FRONTIER_PROFILE_V1",
    "CleanCompileFrontierV1",
    "CleanCompileVariantV1",
    "clean_compilation_fingerprint_v1",
    "compile_service_plan_frontier_v1",
]
