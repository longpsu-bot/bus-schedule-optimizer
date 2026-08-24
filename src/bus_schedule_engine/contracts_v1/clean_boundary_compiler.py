"""Deterministic compiler for fixed-endpoint, clean-boundary Scenario C timetables.

Demand-regime detection and trip allocation are upstream authorities.  This module only
compiles an already frozen vector of per-regime trip counts into exact whole-minute rhythms.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Any

CLEAN_BOUNDARY_COMPILER_PROFILE_V1 = "clean_boundary_schedule_compiler_v1"
CLEAN_BOUNDARY_UNCOMPILABLE = "CLEAN_BOUNDARY_UNCOMPILABLE"


class CleanBoundaryCompilationStatusV1(StrEnum):
    COMPILED_CLEAN_BOUNDARIES = "COMPILED_CLEAN_BOUNDARIES"
    CLEAN_BOUNDARY_UNCOMPILABLE = CLEAN_BOUNDARY_UNCOMPILABLE


class BoundaryOwnershipV1(StrEnum):
    LEFT = "LEFT_SERVICE_REGIME"
    RIGHT = "RIGHT_SERVICE_REGIME"
    MERGED = "MERGED_EQUAL_HEADWAY_SERVICE_REGIME"


@dataclass(frozen=True, slots=True)
class OperationalEndpointAuthorityV1:
    route_id: str
    direction: str
    analysis_window_start: int
    analysis_window_end: int
    fixed_first_departure: int
    fixed_last_departure: int
    authority_source: str

    def __post_init__(self) -> None:
        if self.analysis_window_start >= self.analysis_window_end:
            raise ValueError("analysis window must be positive")
        if not (
            self.analysis_window_start
            <= self.fixed_first_departure
            <= self.fixed_last_departure
            < self.analysis_window_end
        ):
            raise ValueError("fixed departures must lie inside the demand analysis window")


@dataclass(frozen=True, slots=True)
class DemandRegimeAllocationV1:
    regime_id: str
    start_time: int
    end_time: int
    allocated_trip_count: int
    nominal_headway: float

    def __post_init__(self) -> None:
        if self.start_time >= self.end_time:
            raise ValueError(f"{self.regime_id} must have a positive interval")
        if self.allocated_trip_count < 2:
            raise ValueError(f"{self.regime_id} requires at least two allocated trips")
        if self.start_time % 60 or self.end_time % 60:
            raise ValueError(f"{self.regime_id} boundaries must be whole-minute values")


@dataclass(frozen=True, slots=True)
class CompiledDemandRegimeSliceV1:
    demand_regime_id: str
    demand_regime_start: int
    demand_regime_end: int
    authoritative_trip_count: int
    service_regime_id: str
    uniform_headway_minutes: int
    first_departure: int
    last_departure: int
    departures: tuple[int, ...]
    headway_quantization_error: float
    phase_imbalance_minutes: int


@dataclass(frozen=True, slots=True)
class CompiledServiceRegimeV1:
    service_regime_id: str
    direction: str
    demand_regime_ids: tuple[str, ...]
    uniform_headway_minutes: int
    first_departure: int
    last_departure: int
    trip_count: int
    departures: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class BoundaryGapDiagnosticV1:
    boundary_time: int
    departure_i: int
    departure_j: int
    gap_minutes: int
    left_service_headway: int
    right_service_headway: int
    ownership: BoundaryOwnershipV1
    valid: bool


@dataclass(frozen=True, slots=True)
class CleanBoundaryFailureEvidenceV1:
    route_id: str
    direction: str
    candidate_id: str
    boundary_time: int
    left_trip_count: int
    right_trip_count: int
    left_feasible_headways: tuple[int, ...]
    right_feasible_headways: tuple[int, ...]
    fixed_first_departure: int
    fixed_last_departure: int
    reason: str


@dataclass(frozen=True, slots=True)
class CleanBoundaryCompilationV1:
    compiler_profile: str
    route_id: str
    direction: str
    candidate_id: str
    status: CleanBoundaryCompilationStatusV1
    endpoint_authority: OperationalEndpointAuthorityV1
    demand_regime_slices: tuple[CompiledDemandRegimeSliceV1, ...]
    service_regimes: tuple[CompiledServiceRegimeV1, ...]
    exact_departures: tuple[int, ...]
    boundary_diagnostics: tuple[BoundaryGapDiagnosticV1, ...]
    total_headway_quantization_error: float | None
    total_phase_imbalance_minutes: int | None
    failure: CleanBoundaryFailureEvidenceV1 | None


@dataclass(frozen=True, slots=True)
class _PhaseCandidate:
    first_minute: int
    headway_minutes: int
    last_minute: int
    departures_minutes: tuple[int, ...]
    quantization_error: Fraction
    phase_imbalance_minutes: int


@dataclass(frozen=True, order=True, slots=True)
class _PathScore:
    quantization_error: Fraction
    service_regime_count: int
    phase_imbalance_minutes: int
    headway_vector: tuple[int, ...]
    departure_vector: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _PathState:
    score: _PathScore
    candidate_indices: tuple[int, ...]


def _minutes(seconds: int, *, field: str) -> int:
    if seconds % 60:
        raise ValueError(f"{field} must be a whole-minute value")
    return seconds // 60


def _seconds(minutes: int) -> int:
    return minutes * 60


def demand_regime_allocation_from_mapping_v1(
    value: Mapping[str, Any],
) -> DemandRegimeAllocationV1:
    return DemandRegimeAllocationV1(
        regime_id=str(value["regime_id"]),
        start_time=int(value["start_time"]),
        end_time=int(value["end_time"]),
        allocated_trip_count=int(value["allocated_trip_count"]),
        nominal_headway=float(value["nominal_headway"]),
    )


def _validate_regime_contract(
    regimes: Sequence[DemandRegimeAllocationV1],
    authority: OperationalEndpointAuthorityV1,
) -> None:
    if not regimes:
        raise ValueError("at least one frozen DemandRegime is required")
    if regimes[0].start_time != authority.analysis_window_start:
        raise ValueError("the first DemandRegime must start at analysis_window_start")
    if regimes[-1].end_time != authority.analysis_window_end:
        raise ValueError("the final DemandRegime must end at analysis_window_end")
    for left, right in zip(regimes, regimes[1:], strict=False):
        if left.end_time != right.start_time:
            raise ValueError("frozen DemandRegimes must be contiguous and ordered")
    if not (regimes[0].start_time <= authority.fixed_first_departure < regimes[0].end_time):
        raise ValueError("the first DemandRegime must contain fixed_first_departure")
    if not (regimes[-1].start_time <= authority.fixed_last_departure < regimes[-1].end_time):
        raise ValueError("the final DemandRegime must contain fixed_last_departure")


def _phase_candidates(
    regime: DemandRegimeAllocationV1,
    *,
    regime_index: int,
    regime_count: int,
    authority: OperationalEndpointAuthorityV1,
) -> tuple[_PhaseCandidate, ...]:
    window_start = _minutes(regime.start_time, field=f"{regime.regime_id}.start_time")
    window_end = _minutes(regime.end_time, field=f"{regime.regime_id}.end_time")
    fixed_first = _minutes(authority.fixed_first_departure, field="fixed_first_departure")
    fixed_last = _minutes(authority.fixed_last_departure, field="fixed_last_departure")
    trip_count = regime.allocated_trip_count
    duration = window_end - window_start
    maximum_headway = (duration - 1) // (trip_count - 1)
    candidates: list[_PhaseCandidate] = []

    for headway in range(1, maximum_headway + 1):
        first_minute = window_start
        final_first_minute = window_end - 1 - (trip_count - 1) * headway
        if regime_index == 0:
            first_minute = fixed_first
            final_first_minute = fixed_first
        if regime_index == regime_count - 1:
            anchored_first = fixed_last - (trip_count - 1) * headway
            first_minute = anchored_first
            final_first_minute = anchored_first
        if first_minute > final_first_minute:
            continue

        for start in range(first_minute, final_first_minute + 1):
            departures = tuple(start + offset * headway for offset in range(trip_count))
            last = departures[-1]
            if not (window_start <= start and last < window_end):
                continue
            if regime_index == 0 and start != fixed_first:
                continue
            if regime_index == regime_count - 1 and last != fixed_last:
                continue
            quantization_error = Fraction(abs(headway * trip_count - duration), duration)
            phase_imbalance = (
                0
                if regime_index in {0, regime_count - 1}
                else abs((start - window_start) - (window_end - last))
            )
            candidates.append(
                _PhaseCandidate(
                    first_minute=start,
                    headway_minutes=headway,
                    last_minute=last,
                    departures_minutes=departures,
                    quantization_error=quantization_error,
                    phase_imbalance_minutes=phase_imbalance,
                )
            )
    return tuple(candidates)


def _candidate_path(
    phase_candidates: Sequence[tuple[_PhaseCandidate, ...]],
) -> tuple[_PhaseCandidate, ...] | None:
    if not phase_candidates or not phase_candidates[0]:
        return None
    reachable: dict[int, _PathState] = {}
    for index, candidate in enumerate(phase_candidates[0]):
        reachable[index] = _PathState(
            score=_PathScore(
                quantization_error=candidate.quantization_error,
                service_regime_count=1,
                phase_imbalance_minutes=candidate.phase_imbalance_minutes,
                headway_vector=(candidate.headway_minutes,),
                departure_vector=candidate.departures_minutes,
            ),
            candidate_indices=(index,),
        )

    for regime_index in range(1, len(phase_candidates)):
        current_candidates = phase_candidates[regime_index]
        if not current_candidates:
            return None
        by_start: dict[int, list[int]] = {}
        by_predecessor: dict[int, list[int]] = {}
        for index, candidate in enumerate(current_candidates):
            by_start.setdefault(candidate.first_minute, []).append(index)
            by_predecessor.setdefault(
                candidate.first_minute - candidate.headway_minutes, []
            ).append(index)

        next_reachable: dict[int, _PathState] = {}
        previous_candidates = phase_candidates[regime_index - 1]
        for previous_index, state in reachable.items():
            previous = previous_candidates[previous_index]
            legal_indices = set(
                by_start.get(
                    previous.last_minute + previous.headway_minutes,
                    (),
                )
            )
            legal_indices.update(by_predecessor.get(previous.last_minute, ()))
            for current_index in sorted(legal_indices):
                current = current_candidates[current_index]
                score = _PathScore(
                    quantization_error=(
                        state.score.quantization_error + current.quantization_error
                    ),
                    service_regime_count=(
                        state.score.service_regime_count
                        + (previous.headway_minutes != current.headway_minutes)
                    ),
                    phase_imbalance_minutes=(
                        state.score.phase_imbalance_minutes + current.phase_imbalance_minutes
                    ),
                    headway_vector=(state.score.headway_vector + (current.headway_minutes,)),
                    departure_vector=(state.score.departure_vector + current.departures_minutes),
                )
                incumbent = next_reachable.get(current_index)
                if incumbent is None or score < incumbent.score:
                    next_reachable[current_index] = _PathState(
                        score=score,
                        candidate_indices=state.candidate_indices + (current_index,),
                    )
        if not next_reachable:
            return None
        reachable = next_reachable

    best = min(reachable.values(), key=lambda state: state.score)
    return tuple(
        phase_candidates[index][candidate_index]
        for index, candidate_index in enumerate(best.candidate_indices)
    )


def _failure_boundary_index(
    phase_candidates: Sequence[tuple[_PhaseCandidate, ...]],
) -> int:
    if len(phase_candidates) == 1:
        return 0
    if not phase_candidates[0]:
        return 1
    reachable = set(range(len(phase_candidates[0])))
    for regime_index in range(1, len(phase_candidates)):
        current = phase_candidates[regime_index]
        if not current:
            return regime_index
        by_start: dict[int, set[int]] = {}
        by_predecessor: dict[int, set[int]] = {}
        for index, candidate in enumerate(current):
            by_start.setdefault(candidate.first_minute, set()).add(index)
            by_predecessor.setdefault(
                candidate.first_minute - candidate.headway_minutes, set()
            ).add(index)
        next_reachable: set[int] = set()
        previous = phase_candidates[regime_index - 1]
        for previous_index in reachable:
            item = previous[previous_index]
            next_reachable.update(by_start.get(item.last_minute + item.headway_minutes, set()))
            next_reachable.update(by_predecessor.get(item.last_minute, set()))
        if not next_reachable:
            return regime_index
        reachable = next_reachable
    return len(phase_candidates) - 1


def _build_service_regimes(
    direction: str,
    regimes: Sequence[DemandRegimeAllocationV1],
    path: Sequence[_PhaseCandidate],
) -> tuple[tuple[CompiledServiceRegimeV1, ...], tuple[str, ...]]:
    groups: list[list[int]] = [[0]]
    for index in range(1, len(path)):
        previous = path[index - 1]
        current = path[index]
        gap = current.first_minute - previous.last_minute
        if previous.headway_minutes == current.headway_minutes and gap == current.headway_minutes:
            groups[-1].append(index)
        else:
            groups.append([index])

    service_regimes: list[CompiledServiceRegimeV1] = []
    service_id_by_demand_regime = [""] * len(path)
    for service_index, group in enumerate(groups, start=1):
        service_id = f"SERVICE-{direction.upper()}-{service_index:02d}"
        departures = tuple(
            departure
            for regime_index in group
            for departure in path[regime_index].departures_minutes
        )
        headway = path[group[0]].headway_minutes
        if any(
            later - earlier != headway
            for earlier, later in zip(departures, departures[1:], strict=False)
        ):
            raise AssertionError("equal-headway merged sequence is not exactly uniform")
        for regime_index in group:
            service_id_by_demand_regime[regime_index] = service_id
        service_regimes.append(
            CompiledServiceRegimeV1(
                service_regime_id=service_id,
                direction=direction,
                demand_regime_ids=tuple(regimes[index].regime_id for index in group),
                uniform_headway_minutes=headway,
                first_departure=_seconds(departures[0]),
                last_departure=_seconds(departures[-1]),
                trip_count=len(departures),
                departures=tuple(_seconds(item) for item in departures),
            )
        )
    return tuple(service_regimes), tuple(service_id_by_demand_regime)


def _boundary_diagnostics(
    regimes: Sequence[DemandRegimeAllocationV1],
    path: Sequence[_PhaseCandidate],
) -> tuple[BoundaryGapDiagnosticV1, ...]:
    diagnostics: list[BoundaryGapDiagnosticV1] = []
    for index, (left, right) in enumerate(zip(path, path[1:], strict=False)):
        gap = right.first_minute - left.last_minute
        if gap == left.headway_minutes == right.headway_minutes:
            ownership = BoundaryOwnershipV1.MERGED
        elif gap == left.headway_minutes:
            ownership = BoundaryOwnershipV1.LEFT
        elif gap == right.headway_minutes:
            ownership = BoundaryOwnershipV1.RIGHT
        else:
            raise AssertionError("compiler admitted an unowned boundary gap")
        diagnostics.append(
            BoundaryGapDiagnosticV1(
                boundary_time=regimes[index].end_time,
                departure_i=_seconds(left.last_minute),
                departure_j=_seconds(right.first_minute),
                gap_minutes=gap,
                left_service_headway=left.headway_minutes,
                right_service_headway=right.headway_minutes,
                ownership=ownership,
                valid=(gap in {left.headway_minutes, right.headway_minutes}),
            )
        )
    return tuple(diagnostics)


def compile_clean_boundary_timetable_v1(
    *,
    route_id: str,
    direction: str,
    candidate_id: str,
    regimes: Sequence[DemandRegimeAllocationV1],
    endpoint_authority: OperationalEndpointAuthorityV1,
) -> CleanBoundaryCompilationV1:
    """Compile frozen DemandRegime counts without moving endpoints or boundary trips."""

    if endpoint_authority.route_id != route_id or endpoint_authority.direction != direction:
        raise ValueError("endpoint authority identity does not match compiler request")
    _validate_regime_contract(regimes, endpoint_authority)
    phase_candidates = tuple(
        _phase_candidates(
            regime,
            regime_index=index,
            regime_count=len(regimes),
            authority=endpoint_authority,
        )
        for index, regime in enumerate(regimes)
    )
    path = _candidate_path(phase_candidates)
    if path is None:
        boundary_index = _failure_boundary_index(phase_candidates)
        left_index = max(0, boundary_index - 1)
        right_index = min(len(regimes) - 1, boundary_index)
        left_candidates = phase_candidates[left_index]
        right_candidates = phase_candidates[right_index]
        failure = CleanBoundaryFailureEvidenceV1(
            route_id=route_id,
            direction=direction,
            candidate_id=candidate_id,
            boundary_time=regimes[right_index].start_time,
            left_trip_count=regimes[left_index].allocated_trip_count,
            right_trip_count=regimes[right_index].allocated_trip_count,
            left_feasible_headways=tuple(
                sorted({item.headway_minutes for item in left_candidates})
            ),
            right_feasible_headways=tuple(
                sorted({item.headway_minutes for item in right_candidates})
            ),
            fixed_first_departure=endpoint_authority.fixed_first_departure,
            fixed_last_departure=endpoint_authority.fixed_last_departure,
            reason=(
                "No legal phase/headway path simultaneously satisfies the fixed endpoints, "
                "exact frozen counts, whole-minute internal uniformity, and g in {hL, hR}."
            ),
        )
        return CleanBoundaryCompilationV1(
            compiler_profile=CLEAN_BOUNDARY_COMPILER_PROFILE_V1,
            route_id=route_id,
            direction=direction,
            candidate_id=candidate_id,
            status=CleanBoundaryCompilationStatusV1.CLEAN_BOUNDARY_UNCOMPILABLE,
            endpoint_authority=endpoint_authority,
            demand_regime_slices=(),
            service_regimes=(),
            exact_departures=(),
            boundary_diagnostics=(),
            total_headway_quantization_error=None,
            total_phase_imbalance_minutes=None,
            failure=failure,
        )

    service_regimes, service_ids = _build_service_regimes(direction, regimes, path)
    slices = tuple(
        CompiledDemandRegimeSliceV1(
            demand_regime_id=regime.regime_id,
            demand_regime_start=regime.start_time,
            demand_regime_end=regime.end_time,
            authoritative_trip_count=regime.allocated_trip_count,
            service_regime_id=service_ids[index],
            uniform_headway_minutes=phase.headway_minutes,
            first_departure=_seconds(phase.first_minute),
            last_departure=_seconds(phase.last_minute),
            departures=tuple(_seconds(item) for item in phase.departures_minutes),
            headway_quantization_error=float(phase.quantization_error),
            phase_imbalance_minutes=phase.phase_imbalance_minutes,
        )
        for index, (regime, phase) in enumerate(zip(regimes, path, strict=True))
    )
    exact_departures = tuple(departure for item in slices for departure in item.departures)
    boundary_diagnostics = _boundary_diagnostics(regimes, path)
    result = CleanBoundaryCompilationV1(
        compiler_profile=CLEAN_BOUNDARY_COMPILER_PROFILE_V1,
        route_id=route_id,
        direction=direction,
        candidate_id=candidate_id,
        status=CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES,
        endpoint_authority=endpoint_authority,
        demand_regime_slices=slices,
        service_regimes=service_regimes,
        exact_departures=exact_departures,
        boundary_diagnostics=boundary_diagnostics,
        total_headway_quantization_error=float(
            sum((item.quantization_error for item in path), start=Fraction(0))
        ),
        total_phase_imbalance_minutes=sum(item.phase_imbalance_minutes for item in path),
        failure=None,
    )
    validate_clean_boundary_compilation_v1(result, regimes)
    return result


def validate_clean_boundary_compilation_v1(
    compilation: CleanBoundaryCompilationV1,
    regimes: Sequence[DemandRegimeAllocationV1],
) -> None:
    if compilation.status != CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES:
        return
    if not compilation.exact_departures:
        raise ValueError("compiled timetable is empty")
    authority = compilation.endpoint_authority
    if compilation.exact_departures[0] != authority.fixed_first_departure:
        raise ValueError("compiled first departure differs from fixed authority")
    if compilation.exact_departures[-1] != authority.fixed_last_departure:
        raise ValueError("compiled last departure differs from fixed authority")
    if len(compilation.demand_regime_slices) != len(regimes):
        raise ValueError("compiled DemandRegime slice count differs from frozen authority")
    for regime, compiled in zip(regimes, compilation.demand_regime_slices, strict=True):
        actual = tuple(
            departure
            for departure in compilation.exact_departures
            if regime.start_time <= departure < regime.end_time
        )
        if len(actual) != regime.allocated_trip_count:
            raise ValueError(f"{regime.regime_id} compiled trip count changed")
        if actual != compiled.departures:
            raise ValueError(f"{regime.regime_id} membership serialization mismatch")
        if any(
            later - earlier != compiled.uniform_headway_minutes * 60
            for earlier, later in zip(actual, actual[1:], strict=False)
        ):
            raise ValueError(f"{regime.regime_id} is not internally uniform")
    if any(not diagnostic.valid for diagnostic in compilation.boundary_diagnostics):
        raise ValueError("compiled timetable contains an unowned boundary gap")
    for diagnostic in compilation.boundary_diagnostics:
        if diagnostic.gap_minutes not in {
            diagnostic.left_service_headway,
            diagnostic.right_service_headway,
        }:
            raise ValueError("compiled boundary gap differs from both adjacent headways")
    for service in compilation.service_regimes:
        if any(
            later - earlier != service.uniform_headway_minutes * 60
            for earlier, later in zip(service.departures, service.departures[1:], strict=False)
        ):
            raise ValueError(f"{service.service_regime_id} is not exactly uniform")


def clean_boundary_compilation_to_dict_v1(
    compilation: CleanBoundaryCompilationV1,
) -> dict[str, Any]:
    return asdict(compilation)


def scan_serialized_headway_outliers_v1(
    compilation: CleanBoundaryCompilationV1,
) -> tuple[BoundaryGapDiagnosticV1, ...]:
    """Return every boundary diagnostic that is not owned by an adjacent rhythm."""

    return tuple(
        diagnostic
        for diagnostic in compilation.boundary_diagnostics
        if (
            not diagnostic.valid
            or diagnostic.gap_minutes
            not in {
                diagnostic.left_service_headway,
                diagnostic.right_service_headway,
            }
        )
    )


__all__ = [
    "BoundaryGapDiagnosticV1",
    "BoundaryOwnershipV1",
    "CLEAN_BOUNDARY_COMPILER_PROFILE_V1",
    "CLEAN_BOUNDARY_UNCOMPILABLE",
    "CleanBoundaryCompilationStatusV1",
    "CleanBoundaryCompilationV1",
    "CleanBoundaryFailureEvidenceV1",
    "CompiledDemandRegimeSliceV1",
    "CompiledServiceRegimeV1",
    "DemandRegimeAllocationV1",
    "OperationalEndpointAuthorityV1",
    "clean_boundary_compilation_to_dict_v1",
    "compile_clean_boundary_timetable_v1",
    "demand_regime_allocation_from_mapping_v1",
    "scan_serialized_headway_outliers_v1",
    "validate_clean_boundary_compilation_v1",
]
