"""Deterministic demand-profile segmentation with explainable boundary evidence.

This module deliberately stops at demand regimes.  It does not allocate trips,
choose headways, generate departures, or invoke any timetable solver.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from enum import StrEnum
from numbers import Real
from statistics import median

from .models import ContractDirection, ScenarioBInput
from .multi_period_demand import (
    DemandDirectionGrainV1,
    DemandProfileV1,
    DerivedDemandObservationV1,
)
from .regime_trip_allocation import contains_departure_v1

DEMAND_REGIME_DETECTOR_PROFILE_V1 = "deterministic_demand_regime_detector_v1"
DEMAND_REGIME_MODEL_SELECTOR_PROFILE_V1 = "deterministic_demand_regime_model_selector_v1"
INSUFFICIENT_DEMAND_COVERAGE = "INSUFFICIENT_DEMAND_COVERAGE"
INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS = "INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS"


class DemandRegimeDetectionStatusV1(StrEnum):
    SUCCESS = "SUCCESS"
    INSUFFICIENT_DEMAND_COVERAGE = INSUFFICIENT_DEMAND_COVERAGE


class RegimeModelSelectionStatusV1(StrEnum):
    SUCCESS = "SUCCESS"
    INSUFFICIENT_DEMAND_COVERAGE = INSUFFICIENT_DEMAND_COVERAGE
    INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS = INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS


class DemandRegimeScopeV1(StrEnum):
    SHARED_ROUTE_LEVEL_REGIMES = "SHARED_ROUTE_LEVEL_REGIMES"
    DIRECTION_SPECIFIC_REGIMES = "DIRECTION_SPECIFIC_REGIMES"


class BoundaryDecisionV1(StrEnum):
    KEEP = "KEEP"
    SUPPRESS = "SUPPRESS"


@dataclass(frozen=True, slots=True)
class DemandRegimeDetectorConfigV1:
    """Technical policy for exact-K segmentation and repeated-day selection.

    ``target_min_regime_minutes`` is converted to whole canonical buckets with
    ``ceil(target / bucket_minutes)`` as a search lower bound; exact interval
    duration is then enforced so a partial final bucket cannot create a short
    regime. ``complexity_penalty`` is retained only for the explicitly labeled
    legacy selector diagnostic. It has no authority in repeated-day CV.

    ``min_validation_days`` is a data-sufficiency threshold, not a preferred
    regime-count policy. Daily profiles require exact canonical-grid coverage.

    There is deliberately no business regime-count cap.  The finite search
    limit is derived from the canonical bucket grid and minimum duration.
    """

    target_min_regime_minutes: int = 90
    complexity_penalty: float = 0.05
    cost_tie_epsilon: float = 1e-12
    min_validation_days: int = 7

    def __post_init__(self) -> None:
        if (
            isinstance(self.target_min_regime_minutes, bool)
            or not isinstance(self.target_min_regime_minutes, int)
            or self.target_min_regime_minutes <= 0
        ):
            raise ValueError("target_min_regime_minutes must be a positive integer")
        _finite_nonnegative(self.complexity_penalty, "complexity_penalty")
        epsilon = _finite_nonnegative(self.cost_tie_epsilon, "cost_tie_epsilon")
        if epsilon == 0:
            raise ValueError("cost_tie_epsilon must be positive")
        if (
            isinstance(self.min_validation_days, bool)
            or not isinstance(self.min_validation_days, int)
            or self.min_validation_days < 2
        ):
            raise ValueError("min_validation_days must be an integer of at least two")


@dataclass(frozen=True, slots=True)
class DemandCoverageEvidenceV1:
    direction: ContractDirection
    service_start: int | None
    service_end: int | None
    bucket_granularity_minutes: int | None
    observed_bucket_count: int
    expected_bucket_count: int | None
    coverage_ratio: float
    missing_intervals: tuple[tuple[int, int], ...]
    sufficient: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class DemandBoundaryEvidenceV1:
    boundary_time: int
    decision: BoundaryDecisionV1
    before_start: int
    before_end: int
    before_demand_mean: float
    after_start: int
    after_end: int
    after_demand_mean: float
    relative_change_percent: float | None
    segmented_fit_improvement: float
    complexity_penalty: float
    net_objective_improvement: float
    reason_code: str
    reason: str


@dataclass(frozen=True, slots=True)
class DemandRegimeV1:
    """A service-demand interval with canonical half-open semantics ``[start, end)``.

    The boundaries indicate changes in demand/service policy.  They are not
    mandatory departure anchors.
    """

    regime_id: str
    direction: ContractDirection
    start_time: int
    end_time: int
    duration_minutes: int
    bucket_count: int
    demand_sum: float
    demand_mean: float
    demand_share: float
    normalized_demand_mean: float
    within_regime_error: float
    current_b_trip_count: int | None
    current_b_median_headway: float | None
    current_b_max_headway: int | None


@dataclass(frozen=True, slots=True)
class RegimeCountObjectiveV1:
    """Best feasible segmentation objective for one exact regime count."""

    regime_count: int
    fit_error: float
    boundary_penalty_total: float
    total_objective: float
    boundaries: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DemandRegimePlanV1:
    direction: ContractDirection
    scope: DemandRegimeScopeV1
    service_start: int
    service_end: int
    bucket_granularity_minutes: int
    minimum_regime_bucket_count: int
    natural_max_regimes: int
    selected_regime_count: int
    total_demand: float
    total_within_regime_error: float
    complexity_cost: float
    objective_cost: float
    regime_count_objectives: tuple[RegimeCountObjectiveV1, ...]
    current_b_exact_timetable_trip_count: int | None
    current_b_service_window_trip_count: int | None
    current_b_regime_trip_count: int | None
    current_b_outside_service_window_trip_count: int | None
    current_b_service_window_reconciled: bool | None
    regimes: tuple[DemandRegimeV1, ...]
    boundary_evidence: tuple[DemandBoundaryEvidenceV1, ...]


@dataclass(frozen=True, slots=True)
class DailyDemandObservationV1:
    """One observed date/bucket value; absent rows remain missing, never zero."""

    observation_date: date
    direction: ContractDirection
    interval_start: int
    interval_end: int
    passenger_demand: float


@dataclass(frozen=True, slots=True)
class RegimeCandidateV1:
    regime_count: int
    fit_error: float
    boundaries: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RegimeCandidateFrontierV1:
    direction: ContractDirection
    natural_max_regimes: int
    candidates: tuple[RegimeCandidateV1, ...]


@dataclass(frozen=True, slots=True)
class DailyDemandExclusionV1:
    observation_date: date
    reason_code: str
    reason: str
    observed_bucket_count: int
    expected_bucket_count: int
    coverage_ratio: float
    missing_intervals: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class RegimeModelScoreV1:
    regime_count: int
    full_data_fit_error: float
    mean_validation_error: float | None
    validation_standard_error: float | None
    eligible_fold_count: int
    within_one_se: bool | None


@dataclass(frozen=True, slots=True)
class BoundaryStabilityV1:
    boundary_time: int
    is_final_boundary: bool
    exact_support_count: int
    exact_boundary_frequency: float
    neighbor_support_count: int
    neighbor_boundary_frequency: float
    eligible_fold_count: int


@dataclass(frozen=True, slots=True)
class RegimeModelSelectionV1:
    direction: ContractDirection
    selection_method: str
    selection_status: RegimeModelSelectionStatusV1
    normalization_method: str
    total_observed_days: int
    eligible_validation_days: int
    excluded_days: tuple[DailyDemandExclusionV1, ...]
    natural_max_regimes: int
    legacy_penalty_selected_regime_count: int
    selected_regime_count: int | None
    best_validation_regime_count: int | None
    best_mean_validation_error: float | None
    best_standard_error: float | None
    one_se_threshold: float | None
    candidate_frontier: RegimeCandidateFrontierV1
    model_scores: tuple[RegimeModelScoreV1, ...]
    final_boundaries: tuple[int, ...]
    boundary_stability: tuple[BoundaryStabilityV1, ...]
    final_plan: DemandRegimePlanV1 | None
    failure_code: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class DemandRegimeModelSelectionResultV1:
    selector_profile: str
    status: RegimeModelSelectionStatusV1
    demand_profile_id: str
    demand_profile_fingerprint: str
    direction_grain: DemandDirectionGrainV1
    scope: DemandRegimeScopeV1
    config: DemandRegimeDetectorConfigV1
    coverage: tuple[DemandCoverageEvidenceV1, ...]
    selections: tuple[RegimeModelSelectionV1, ...]
    failure_code: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class DemandRegimeDetectionResultV1:
    detector_profile: str
    status: DemandRegimeDetectionStatusV1
    demand_profile_id: str
    demand_profile_fingerprint: str
    direction_grain: DemandDirectionGrainV1
    scope: DemandRegimeScopeV1
    config: DemandRegimeDetectorConfigV1
    coverage: tuple[DemandCoverageEvidenceV1, ...]
    plans: tuple[DemandRegimePlanV1, ...]
    failure_code: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class _Bucket:
    start: int
    end: int
    demand: float


@dataclass(frozen=True, slots=True)
class _Grid:
    buckets: tuple[_Bucket, ...]
    granularity_seconds: int | None
    coverage: DemandCoverageEvidenceV1


@dataclass(frozen=True, slots=True)
class _Partition:
    fit_error: float
    boundaries: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class _Segmentation:
    selected: _Partition
    minimum_bucket_count: int
    natural_max_regimes: int
    normalized_demand: tuple[float, ...]
    objectives: tuple[RegimeCountObjectiveV1, ...]
    error: Callable[[int, int], float]


def _finite_nonnegative(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{field} must be finite and non-negative")
    numeric = float(value)
    if not math.isfinite(numeric) or numeric < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return numeric


DEFAULT_DEMAND_REGIME_CONFIG_V1 = DemandRegimeDetectorConfigV1()


def _scope(profile: DemandProfileV1) -> DemandRegimeScopeV1:
    if profile.direction_grain == DemandDirectionGrainV1.COMBINED:
        return DemandRegimeScopeV1.SHARED_ROUTE_LEVEL_REGIMES
    return DemandRegimeScopeV1.DIRECTION_SPECIFIC_REGIMES


def _grid_for_direction(
    direction: ContractDirection,
    observations: list[DerivedDemandObservationV1],
) -> _Grid:
    ordered = sorted(observations, key=lambda item: (item.interval_start, item.interval_end))
    if not ordered:
        return _Grid(
            buckets=(),
            granularity_seconds=None,
            coverage=DemandCoverageEvidenceV1(
                direction=direction,
                service_start=None,
                service_end=None,
                bucket_granularity_minutes=None,
                observed_bucket_count=0,
                expected_bucket_count=None,
                coverage_ratio=0.0,
                missing_intervals=(),
                sufficient=False,
                reason="No observed demand buckets are available.",
            ),
        )

    buckets = tuple(
        _Bucket(
            start=int(item.interval_start),
            end=int(item.interval_end),
            demand=float(item.average_daily_passengers),
        )
        for item in ordered
    )
    durations = [item.end - item.start for item in buckets]
    positive_durations = [duration for duration in durations if duration > 0]
    duration_counts = Counter(positive_durations)
    nominal = (
        min(duration_counts, key=lambda value: (-duration_counts[value], value))
        if duration_counts
        else None
    )
    missing: list[tuple[int, int]] = []
    overlaps = False
    for left, right in zip(buckets, buckets[1:], strict=False):
        if right.start > left.end:
            missing.append((left.end, right.start))
        elif right.start < left.end:
            overlaps = True

    service_start = buckets[0].start
    service_end = buckets[-1].end
    expected_count: int | None = None
    coverage_ratio = 0.0
    valid_boundaries = all(item.start % 60 == 0 and item.end % 60 == 0 for item in buckets)
    valid_durations = bool(nominal) and all(
        duration == nominal or (index == len(durations) - 1 and 0 < duration < nominal)
        for index, duration in enumerate(durations)
    )
    aligned = bool(nominal) and all((item.start - service_start) % nominal == 0 for item in buckets)
    if nominal and service_end > service_start:
        expected_count = math.ceil((service_end - service_start) / nominal)
        coverage_ratio = min(1.0, len(buckets) / expected_count)

    reason: str | None = None
    if any(not math.isfinite(item.demand) or item.demand < 0 for item in buckets):
        reason = "Demand buckets must contain finite non-negative observed values."
    elif not valid_boundaries:
        reason = "Demand bucket boundaries must be expressed in whole minutes."
    elif overlaps:
        reason = "Demand buckets overlap."
    elif not nominal or not valid_durations or not aligned:
        reason = "Demand buckets do not form one canonical regular grid."
    elif missing:
        reason = "The canonical demand window contains unobserved buckets."

    sufficient = reason is None
    return _Grid(
        buckets=buckets,
        granularity_seconds=nominal,
        coverage=DemandCoverageEvidenceV1(
            direction=direction,
            service_start=service_start,
            service_end=service_end,
            bucket_granularity_minutes=(nominal // 60 if nominal else None),
            observed_bucket_count=len(buckets),
            expected_bucket_count=expected_count,
            coverage_ratio=coverage_ratio,
            missing_intervals=tuple(missing),
            sufficient=sufficient,
            reason=reason,
        ),
    )


def _prefer_partition(
    candidate: _Partition,
    incumbent: _Partition | None,
    epsilon: float,
) -> bool:
    if incumbent is None:
        return True
    if candidate.fit_error < incumbent.fit_error - epsilon:
        return True
    if abs(candidate.fit_error - incumbent.fit_error) <= epsilon:
        return candidate.boundaries < incumbent.boundaries
    return False


def _prefer_final(
    candidate: _Partition,
    candidate_count: int,
    incumbent: _Partition | None,
    incumbent_count: int | None,
    penalty: float,
    epsilon: float,
) -> bool:
    if incumbent is None or incumbent_count is None:
        return True
    candidate_cost = candidate.fit_error + penalty * (candidate_count - 1)
    incumbent_cost = incumbent.fit_error + penalty * (incumbent_count - 1)
    if candidate_cost < incumbent_cost - epsilon:
        return True
    if abs(candidate_cost - incumbent_cost) > epsilon:
        return False
    # Stable documented final tie-break: fewer regimes, lower fit error, then
    # lexicographically earlier canonical boundary sequence.
    if candidate_count != incumbent_count:
        return candidate_count < incumbent_count
    if candidate.fit_error < incumbent.fit_error - epsilon:
        return True
    if abs(candidate.fit_error - incumbent.fit_error) <= epsilon:
        return candidate.boundaries < incumbent.boundaries
    return False


def _normalization_scale(buckets: tuple[_Bucket, ...]) -> float:
    """Canonical scale: maximum positive demand of the training aggregate."""

    return max((item.demand for item in buckets if item.demand > 0), default=0.0)


def _normalized_values(
    buckets: tuple[_Bucket, ...],
    *,
    scale: float | None = None,
) -> tuple[float, ...]:
    selected_scale = _normalization_scale(buckets) if scale is None else scale
    return tuple(item.demand / selected_scale if selected_scale > 0 else 0.0 for item in buckets)


def _segmenter(
    buckets: tuple[_Bucket, ...],
    granularity_seconds: int,
    config: DemandRegimeDetectorConfigV1,
) -> _Segmentation:
    normalized = _normalized_values(buckets)
    weights = [(item.end - item.start) / granularity_seconds for item in buckets]
    prefix_w = [0.0]
    prefix_wx = [0.0]
    prefix_wx2 = [0.0]
    for weight, value in zip(weights, normalized, strict=True):
        prefix_w.append(prefix_w[-1] + weight)
        prefix_wx.append(prefix_wx[-1] + weight * value)
        prefix_wx2.append(prefix_wx2[-1] + weight * value * value)

    def error(start: int, end: int) -> float:
        weight = prefix_w[end] - prefix_w[start]
        weighted_sum = prefix_wx[end] - prefix_wx[start]
        squares = prefix_wx2[end] - prefix_wx2[start]
        return max(0.0, squares - weighted_sum * weighted_sum / weight)

    bucket_minutes = granularity_seconds / 60
    minimum = math.ceil(config.target_min_regime_minutes / bucket_minutes)
    count = len(buckets)
    target_seconds = config.target_min_regime_minutes * 60
    search_upper_bound = max(1, count // minimum)

    def has_minimum_duration(start: int, end: int) -> bool:
        return buckets[end - 1].end - buckets[start].start >= target_seconds

    states: dict[tuple[int, int], _Partition] = {}
    for end in range(minimum, count + 1):
        if has_minimum_duration(0, end):
            states[(1, end)] = _Partition(error(0, end), ())
    if not has_minimum_duration(0, count):
        # A service window shorter than the target still has one indivisible
        # regime; the minimum-duration policy cannot manufacture more service.
        states[(1, count)] = _Partition(error(0, count), ())

    for regime_count in range(2, search_upper_bound + 1):
        for end in range(regime_count * minimum, count + 1):
            best: _Partition | None = None
            for cut in range((regime_count - 1) * minimum, end - minimum + 1):
                previous = states.get((regime_count - 1, cut))
                if previous is None or not has_minimum_duration(cut, end):
                    continue
                candidate = _Partition(
                    fit_error=previous.fit_error + error(cut, end),
                    boundaries=(*previous.boundaries, cut),
                )
                if _prefer_partition(candidate, best, config.cost_tie_epsilon):
                    best = candidate
            if best is not None:
                states[(regime_count, end)] = best

    feasible = tuple(
        (regime_count, candidate)
        for regime_count in range(1, search_upper_bound + 1)
        if (candidate := states.get((regime_count, count))) is not None
    )
    natural_max_regimes = max(regime_count for regime_count, _ in feasible)
    selected: _Partition | None = None
    selected_count: int | None = None
    for regime_count, candidate in feasible:
        if _prefer_final(
            candidate,
            regime_count,
            selected,
            selected_count,
            config.complexity_penalty,
            config.cost_tie_epsilon,
        ):
            selected = candidate
            selected_count = regime_count
    if selected is None or selected_count is None:  # pragma: no cover - one segment always exists
        raise AssertionError("deterministic segmentation produced no partition")
    objectives = tuple(
        RegimeCountObjectiveV1(
            regime_count=regime_count,
            fit_error=partition.fit_error,
            boundary_penalty_total=config.complexity_penalty * (regime_count - 1),
            total_objective=(partition.fit_error + config.complexity_penalty * (regime_count - 1)),
            boundaries=tuple(buckets[cut].start for cut in partition.boundaries),
        )
        for regime_count, partition in feasible
    )
    return _Segmentation(
        selected=selected,
        minimum_bucket_count=minimum,
        natural_max_regimes=natural_max_regimes,
        normalized_demand=normalized,
        objectives=objectives,
        error=error,
    )


def _partition_for_objective(
    buckets: tuple[_Bucket, ...],
    objective: RegimeCountObjectiveV1,
) -> _Partition:
    start_indexes = {item.start: index for index, item in enumerate(buckets)}
    return _Partition(
        fit_error=objective.fit_error,
        boundaries=tuple(start_indexes[item] for item in objective.boundaries),
    )


def _candidate_frontier(
    direction: ContractDirection,
    segmentation: _Segmentation,
) -> RegimeCandidateFrontierV1:
    return RegimeCandidateFrontierV1(
        direction=direction,
        natural_max_regimes=segmentation.natural_max_regimes,
        candidates=tuple(
            RegimeCandidateV1(
                regime_count=item.regime_count,
                fit_error=item.fit_error,
                boundaries=item.boundaries,
            )
            for item in segmentation.objectives
        ),
    )


def _mean(buckets: tuple[_Bucket, ...], start: int, end: int) -> float:
    return sum(item.demand for item in buckets[start:end]) / (end - start)


def _relative_change(before: float, after: float) -> float | None:
    return (after - before) / before * 100 if before != 0 else None


def _boundary_evidence(
    buckets: tuple[_Bucket, ...],
    ranges: tuple[tuple[int, int], ...],
    selected_boundaries: tuple[int, ...],
    target_min_regime_seconds: int,
    error: Callable[[int, int], float],
    config: DemandRegimeDetectorConfigV1,
    *,
    fixed_count_selected: bool = False,
) -> tuple[DemandBoundaryEvidenceV1, ...]:
    evidence: list[DemandBoundaryEvidenceV1] = []
    kept = set(selected_boundaries)
    for cut in selected_boundaries:
        left_start, _ = next(item for item in ranges if item[1] == cut)
        _, right_end = next(item for item in ranges if item[0] == cut)
        before = _mean(buckets, left_start, cut)
        after = _mean(buckets, cut, right_end)
        improvement = error(left_start, right_end) - (
            error(left_start, cut) + error(cut, right_end)
        )
        evidence.append(
            DemandBoundaryEvidenceV1(
                boundary_time=buckets[cut].start,
                decision=BoundaryDecisionV1.KEEP,
                before_start=buckets[left_start].start,
                before_end=buckets[cut - 1].end,
                before_demand_mean=before,
                after_start=buckets[cut].start,
                after_end=buckets[right_end - 1].end,
                after_demand_mean=after,
                relative_change_percent=_relative_change(before, after),
                segmented_fit_improvement=improvement,
                complexity_penalty=config.complexity_penalty,
                net_objective_improvement=improvement - config.complexity_penalty,
                reason_code=(
                    "FIXED_K_FULL_DATA_BOUNDARY_SELECTED"
                    if fixed_count_selected
                    else "GLOBAL_OBJECTIVE_BOUNDARY_SELECTED"
                ),
                reason=(
                    "Kept by the globally minimum normalized weighted-SSE partition at the "
                    "cross-validated fixed regime count."
                    if fixed_count_selected
                    else "Kept by the globally minimum normalized weighted-SSE plus "
                    "boundary-penalty partition under the minimum-duration and natural "
                    "grid-feasibility constraints."
                ),
            )
        )

    for cut in range(1, len(buckets)):
        if cut in kept:
            continue
        containing_start, containing_end = next(item for item in ranges if item[0] < cut < item[1])
        before = _mean(buckets, containing_start, cut)
        after = _mean(buckets, cut, containing_end)
        improvement = error(containing_start, containing_end) - (
            error(containing_start, cut) + error(cut, containing_end)
        )
        net = improvement - config.complexity_penalty
        if (
            buckets[cut - 1].end - buckets[containing_start].start < target_min_regime_seconds
            or buckets[containing_end - 1].end - buckets[cut].start < target_min_regime_seconds
        ):
            code = "MINIMUM_REGIME_DURATION"
            reason = "Suppressed because at least one adjacent candidate regime is too short."
        elif net <= config.cost_tie_epsilon:
            code = "INSUFFICIENT_INCREMENTAL_FIT_IMPROVEMENT"
            reason = "Suppressed because its local fit improvement does not exceed the penalty."
        else:
            code = "GLOBAL_OBJECTIVE_NOT_SELECTED"
            reason = "Suppressed because it is not part of the globally preferred partition."
        evidence.append(
            DemandBoundaryEvidenceV1(
                boundary_time=buckets[cut].start,
                decision=BoundaryDecisionV1.SUPPRESS,
                before_start=buckets[containing_start].start,
                before_end=buckets[cut - 1].end,
                before_demand_mean=before,
                after_start=buckets[cut].start,
                after_end=buckets[containing_end - 1].end,
                after_demand_mean=after,
                relative_change_percent=_relative_change(before, after),
                segmented_fit_improvement=improvement,
                complexity_penalty=config.complexity_penalty,
                net_objective_improvement=net,
                reason_code=code,
                reason=reason,
            )
        )
    return tuple(sorted(evidence, key=lambda item: item.boundary_time))


def _scenario_b_statistics(
    scenario_b: ScenarioBInput | None,
    direction: ContractDirection,
    start: int,
    end: int,
) -> tuple[int | None, float | None, int | None]:
    if scenario_b is None:
        return None, None, None
    accepted_directions = _accepted_directions(direction)
    members = [
        trip
        for trip in scenario_b.exact_timetable
        if trip.direction in accepted_directions
        and contains_departure_v1(start, end, trip.departure_time)
    ]
    gaps: list[int] = []
    for member_direction in sorted(accepted_directions, key=lambda item: item.value):
        times = sorted(
            trip.departure_time for trip in members if trip.direction == member_direction
        )
        gaps.extend((right - left) // 60 for left, right in zip(times, times[1:], strict=False))
    return len(members), (float(median(gaps)) if gaps else None), (max(gaps) if gaps else None)


def _accepted_directions(direction: ContractDirection) -> set[ContractDirection]:
    return (
        {ContractDirection.OUTBOUND, ContractDirection.INBOUND}
        if direction == ContractDirection.COMBINED
        else {direction}
    )


def _build_plan(
    direction: ContractDirection,
    scope: DemandRegimeScopeV1,
    grid: _Grid,
    config: DemandRegimeDetectorConfigV1,
    scenario_b: ScenarioBInput | None,
    *,
    selected_regime_count: int | None = None,
) -> DemandRegimePlanV1:
    if grid.granularity_seconds is None:  # pragma: no cover - guarded by coverage
        raise AssertionError("sufficient coverage requires a canonical granularity")
    segmentation = _segmenter(
        grid.buckets,
        grid.granularity_seconds,
        config,
    )
    if selected_regime_count is None:
        partition = segmentation.selected
    else:
        objective = next(
            (
                item
                for item in segmentation.objectives
                if item.regime_count == selected_regime_count
            ),
            None,
        )
        if objective is None:
            raise ValueError(
                f"selected_regime_count {selected_regime_count} is not naturally feasible"
            )
        partition = _partition_for_objective(grid.buckets, objective)
    normalized = segmentation.normalized_demand
    error = segmentation.error
    cuts = (0, *partition.boundaries, len(grid.buckets))
    ranges = tuple(zip(cuts, cuts[1:], strict=False))
    total_demand = sum(item.demand for item in grid.buckets)
    regimes: list[DemandRegimeV1] = []
    for index, (start_index, end_index) in enumerate(ranges, start=1):
        selected = grid.buckets[start_index:end_index]
        demand_sum = sum(item.demand for item in selected)
        b_count, b_median, b_max = _scenario_b_statistics(
            scenario_b,
            direction,
            selected[0].start,
            selected[-1].end,
        )
        regimes.append(
            DemandRegimeV1(
                regime_id=f"DEMAND-{direction.value.upper()}-{index:02d}",
                direction=direction,
                start_time=selected[0].start,
                end_time=selected[-1].end,
                duration_minutes=(selected[-1].end - selected[0].start) // 60,
                bucket_count=len(selected),
                demand_sum=demand_sum,
                demand_mean=demand_sum / len(selected),
                demand_share=demand_sum / total_demand if total_demand > 0 else 0.0,
                normalized_demand_mean=(sum(normalized[start_index:end_index]) / len(selected)),
                within_regime_error=error(start_index, end_index),
                current_b_trip_count=b_count,
                current_b_median_headway=b_median,
                current_b_max_headway=b_max,
            )
        )
    complexity = config.complexity_penalty * (len(regimes) - 1)
    if scenario_b is None:
        b_exact_total = None
        b_window_total = None
        b_regime_total = None
        b_outside_window = None
        b_reconciled = None
    else:
        accepted_directions = _accepted_directions(direction)
        direction_departures = tuple(
            trip.departure_time
            for trip in scenario_b.exact_timetable
            if trip.direction in accepted_directions
        )
        b_exact_total = len(direction_departures)
        b_window_total = sum(
            contains_departure_v1(
                grid.buckets[0].start,
                grid.buckets[-1].end,
                departure,
            )
            for departure in direction_departures
        )
        b_regime_total = sum(regime.current_b_trip_count or 0 for regime in regimes)
        b_outside_window = b_exact_total - b_window_total
        b_reconciled = b_regime_total == b_window_total
    return DemandRegimePlanV1(
        direction=direction,
        scope=scope,
        service_start=grid.buckets[0].start,
        service_end=grid.buckets[-1].end,
        bucket_granularity_minutes=grid.granularity_seconds // 60,
        minimum_regime_bucket_count=segmentation.minimum_bucket_count,
        natural_max_regimes=segmentation.natural_max_regimes,
        selected_regime_count=len(regimes),
        total_demand=total_demand,
        total_within_regime_error=partition.fit_error,
        complexity_cost=complexity,
        objective_cost=partition.fit_error + complexity,
        regime_count_objectives=segmentation.objectives,
        current_b_exact_timetable_trip_count=b_exact_total,
        current_b_service_window_trip_count=b_window_total,
        current_b_regime_trip_count=b_regime_total,
        current_b_outside_service_window_trip_count=b_outside_window,
        current_b_service_window_reconciled=b_reconciled,
        regimes=tuple(regimes),
        boundary_evidence=_boundary_evidence(
            grid.buckets,
            ranges,
            partition.boundaries,
            config.target_min_regime_minutes * 60,
            error,
            config,
            fixed_count_selected=selected_regime_count is not None,
        ),
    )


def detect_demand_regimes_v1(
    profile: DemandProfileV1,
    config: DemandRegimeDetectorConfigV1 = DEFAULT_DEMAND_REGIME_CONFIG_V1,
    *,
    scenario_b: ScenarioBInput | None = None,
) -> DemandRegimeDetectionResultV1:
    """Detect regimes independently only when demand is genuinely directional.

    Missing intervals fail closed with ``INSUFFICIENT_DEMAND_COVERAGE``.  An
    observed zero is a valid value and therefore follows the normal segmentation
    path.
    """

    scope = _scope(profile)
    by_direction: dict[ContractDirection, list[DerivedDemandObservationV1]] = defaultdict(list)
    for item in profile.derived_observations:
        by_direction[item.direction].append(item)
    expected_directions = (
        (ContractDirection.COMBINED,)
        if profile.direction_grain == DemandDirectionGrainV1.COMBINED
        else (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    )
    grids = tuple(
        _grid_for_direction(direction, by_direction.get(direction, []))
        for direction in expected_directions
    )
    coverage = tuple(item.coverage for item in grids)
    if any(not item.sufficient for item in coverage):
        failed = "; ".join(
            f"{item.direction.value}: {item.reason}" for item in coverage if not item.sufficient
        )
        return DemandRegimeDetectionResultV1(
            detector_profile=DEMAND_REGIME_DETECTOR_PROFILE_V1,
            status=DemandRegimeDetectionStatusV1.INSUFFICIENT_DEMAND_COVERAGE,
            demand_profile_id=profile.profile_id,
            demand_profile_fingerprint=profile.profile_fingerprint,
            direction_grain=profile.direction_grain,
            scope=scope,
            config=config,
            coverage=coverage,
            plans=(),
            failure_code=INSUFFICIENT_DEMAND_COVERAGE,
            failure_message=failed,
        )

    plans = tuple(
        _build_plan(direction, scope, grid, config, scenario_b)
        for direction, grid in zip(expected_directions, grids, strict=True)
    )
    return DemandRegimeDetectionResultV1(
        detector_profile=DEMAND_REGIME_DETECTOR_PROFILE_V1,
        status=DemandRegimeDetectionStatusV1.SUCCESS,
        demand_profile_id=profile.profile_id,
        demand_profile_fingerprint=profile.profile_fingerprint,
        direction_grain=profile.direction_grain,
        scope=scope,
        config=config,
        coverage=coverage,
        plans=plans,
    )


def _legacy_selected_count(segmentation: _Segmentation) -> int:
    return len(segmentation.selected.boundaries) + 1


def _daily_profiles_for_direction(
    grid: _Grid,
    direction: ContractDirection,
    daily_observations: tuple[DailyDemandObservationV1, ...],
    observed_dates: tuple[date, ...],
) -> tuple[
    tuple[tuple[date, tuple[float, ...]], ...],
    tuple[DailyDemandExclusionV1, ...],
]:
    expected = tuple((item.start, item.end) for item in grid.buckets)
    expected_set = set(expected)
    rows_by_date: dict[date, list[DailyDemandObservationV1]] = defaultdict(list)
    for item in daily_observations:
        if item.direction == direction:
            rows_by_date[item.observation_date].append(item)

    eligible: list[tuple[date, tuple[float, ...]]] = []
    excluded: list[DailyDemandExclusionV1] = []
    for observed_date in observed_dates:
        rows = rows_by_date.get(observed_date, [])
        values: dict[tuple[int, int], float] = {}
        duplicates: set[tuple[int, int]] = set()
        unexpected: set[tuple[int, int]] = set()
        invalid_values = False
        for row in rows:
            key = (row.interval_start, row.interval_end)
            if key not in expected_set:
                unexpected.add(key)
                continue
            if key in values:
                duplicates.add(key)
            if (
                isinstance(row.passenger_demand, bool)
                or not isinstance(row.passenger_demand, Real)
                or not math.isfinite(float(row.passenger_demand))
                or float(row.passenger_demand) < 0
            ):
                invalid_values = True
                continue
            values[key] = float(row.passenger_demand)
        missing_keys = tuple(key for key in expected if key not in values)
        coverage_ratio = len(expected_set & set(values)) / len(expected) if expected else 0.0
        if invalid_values:
            reason_code = "DAILY_DEMAND_VALUE_INVALID"
            reason = "At least one expected bucket has a non-finite or negative demand value."
        elif duplicates:
            reason_code = "DAILY_DEMAND_BUCKET_DUPLICATE"
            reason = "At least one canonical bucket is duplicated for the observed date."
        elif unexpected:
            reason_code = "DAILY_DEMAND_GRID_MISMATCH"
            reason = "The observed date contains a bucket outside the canonical demand grid."
        elif missing_keys:
            reason_code = "DAILY_DEMAND_COVERAGE_INCOMPLETE"
            reason = "The observed date does not cover every canonical demand bucket."
        else:
            eligible.append((observed_date, tuple(values[key] for key in expected)))
            continue
        excluded.append(
            DailyDemandExclusionV1(
                observation_date=observed_date,
                reason_code=reason_code,
                reason=reason,
                observed_bucket_count=len(rows),
                expected_bucket_count=len(expected),
                coverage_ratio=coverage_ratio,
                missing_intervals=missing_keys,
            )
        )
    return tuple(eligible), tuple(excluded)


def _aggregate_daily_grid(
    base_grid: _Grid,
    daily_profiles: tuple[tuple[date, tuple[float, ...]], ...],
) -> _Grid:
    count = len(daily_profiles)
    if count == 0:
        raise ValueError("at least one eligible daily profile is required")
    buckets = tuple(
        _Bucket(
            start=base.start,
            end=base.end,
            demand=sum(values[index] for _, values in daily_profiles) / count,
        )
        for index, base in enumerate(base_grid.buckets)
    )
    return _Grid(
        buckets=buckets,
        granularity_seconds=base_grid.granularity_seconds,
        coverage=base_grid.coverage,
    )


def _validation_error(
    training_grid: _Grid,
    partition: _Partition,
    validation_values: tuple[float, ...],
) -> float:
    if training_grid.granularity_seconds is None:  # pragma: no cover - coverage guard
        raise AssertionError("training grid requires canonical granularity")
    scale = _normalization_scale(training_grid.buckets)
    training_values = _normalized_values(training_grid.buckets, scale=scale)
    validation_normalized = tuple(
        value / scale if scale > 0 else 0.0 for value in validation_values
    )
    weights = tuple(
        (item.end - item.start) / training_grid.granularity_seconds
        for item in training_grid.buckets
    )
    cuts = (0, *partition.boundaries, len(training_grid.buckets))
    total = 0.0
    for start, end in zip(cuts, cuts[1:], strict=False):
        regime_weight = sum(weights[start:end])
        training_mean = (
            sum(weights[index] * training_values[index] for index in range(start, end))
            / regime_weight
        )
        total += sum(
            weights[index] * (validation_normalized[index] - training_mean) ** 2
            for index in range(start, end)
        )
    return total


def _mean_and_standard_error(values: tuple[float, ...]) -> tuple[float, float]:
    mean_value = sum(values) / len(values)
    if len(values) <= 1:
        return mean_value, 0.0
    sample_variance = sum((item - mean_value) ** 2 for item in values) / (len(values) - 1)
    return mean_value, math.sqrt(sample_variance / len(values))


def _insufficient_selection(
    direction: ContractDirection,
    segmentation: _Segmentation,
    total_observed_days: int,
    eligible_count: int,
    excluded: tuple[DailyDemandExclusionV1, ...],
    config: DemandRegimeDetectorConfigV1,
) -> RegimeModelSelectionV1:
    frontier = _candidate_frontier(direction, segmentation)
    return RegimeModelSelectionV1(
        direction=direction,
        selection_method="leave_one_day_out_cross_validation_one_standard_error",
        selection_status=(RegimeModelSelectionStatusV1.INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS),
        normalization_method=("training_aggregate_max_positive; validation_scaled_by_training_max"),
        total_observed_days=total_observed_days,
        eligible_validation_days=eligible_count,
        excluded_days=excluded,
        natural_max_regimes=segmentation.natural_max_regimes,
        legacy_penalty_selected_regime_count=_legacy_selected_count(segmentation),
        selected_regime_count=None,
        best_validation_regime_count=None,
        best_mean_validation_error=None,
        best_standard_error=None,
        one_se_threshold=None,
        candidate_frontier=frontier,
        model_scores=tuple(
            RegimeModelScoreV1(
                regime_count=item.regime_count,
                full_data_fit_error=item.fit_error,
                mean_validation_error=None,
                validation_standard_error=None,
                eligible_fold_count=eligible_count,
                within_one_se=None,
            )
            for item in frontier.candidates
        ),
        final_boundaries=(),
        boundary_stability=(),
        final_plan=None,
        failure_code=INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS,
        failure_message=(
            f"{eligible_count} eligible date-keyed daily profiles are available; "
            f"at least {config.min_validation_days} are required. Period-level average-day "
            "profiles are not expanded into fabricated daily observations."
        ),
    )


def _select_for_direction(
    direction: ContractDirection,
    scope: DemandRegimeScopeV1,
    profile_grid: _Grid,
    daily_observations: tuple[DailyDemandObservationV1, ...],
    observed_dates: tuple[date, ...],
    config: DemandRegimeDetectorConfigV1,
    scenario_b: ScenarioBInput | None,
) -> RegimeModelSelectionV1:
    if profile_grid.granularity_seconds is None:  # pragma: no cover - coverage guard
        raise AssertionError("model selection requires canonical granularity")
    profile_segmentation = _segmenter(
        profile_grid.buckets,
        profile_grid.granularity_seconds,
        config,
    )
    eligible, excluded = _daily_profiles_for_direction(
        profile_grid,
        direction,
        daily_observations,
        observed_dates,
    )
    if len(eligible) < config.min_validation_days:
        return _insufficient_selection(
            direction,
            profile_segmentation,
            len(observed_dates),
            len(eligible),
            excluded,
            config,
        )

    full_grid = _aggregate_daily_grid(profile_grid, eligible)
    full_segmentation = _segmenter(
        full_grid.buckets,
        full_grid.granularity_seconds,
        config,
    )
    errors: dict[int, list[float]] = {
        item.regime_count: [] for item in full_segmentation.objectives
    }
    fold_boundaries: dict[int, list[tuple[int, ...]]] = {
        item.regime_count: [] for item in full_segmentation.objectives
    }
    for held_out_index, (_, validation_values) in enumerate(eligible):
        training = eligible[:held_out_index] + eligible[held_out_index + 1 :]
        training_grid = _aggregate_daily_grid(profile_grid, training)
        training_segmentation = _segmenter(
            training_grid.buckets,
            training_grid.granularity_seconds,
            config,
        )
        objectives = {item.regime_count: item for item in training_segmentation.objectives}
        for regime_count in sorted(errors):
            objective = objectives[regime_count]
            partition = _partition_for_objective(training_grid.buckets, objective)
            errors[regime_count].append(
                _validation_error(training_grid, partition, validation_values)
            )
            fold_boundaries[regime_count].append(partition.boundaries)

    summaries = {
        regime_count: _mean_and_standard_error(tuple(values))
        for regime_count, values in errors.items()
    }
    best_count = min(summaries)
    for regime_count in sorted(summaries):
        candidate_mean = summaries[regime_count][0]
        best_mean_so_far = summaries[best_count][0]
        if candidate_mean < best_mean_so_far - config.cost_tie_epsilon or (
            abs(candidate_mean - best_mean_so_far) <= config.cost_tie_epsilon
            and regime_count < best_count
        ):
            best_count = regime_count
    best_mean, best_se = summaries[best_count]
    threshold = best_mean + best_se
    selected_count = min(
        regime_count
        for regime_count in sorted(summaries)
        if summaries[regime_count][0] <= threshold + config.cost_tie_epsilon
    )
    full_objectives = {item.regime_count: item for item in full_segmentation.objectives}
    final_objective = full_objectives[selected_count]
    final_partition = _partition_for_objective(full_grid.buckets, final_objective)
    final_boundaries = final_objective.boundaries
    fold_selected_boundaries = fold_boundaries[selected_count]
    final_cut_indexes = set(final_partition.boundaries)
    stability = tuple(
        BoundaryStabilityV1(
            boundary_time=full_grid.buckets[cut].start,
            is_final_boundary=cut in final_cut_indexes,
            exact_support_count=sum(cut in boundaries for boundaries in fold_selected_boundaries),
            exact_boundary_frequency=(
                sum(cut in boundaries for boundaries in fold_selected_boundaries) / len(eligible)
            ),
            neighbor_support_count=sum(
                any(abs(candidate - cut) <= 1 for candidate in boundaries)
                for boundaries in fold_selected_boundaries
            ),
            neighbor_boundary_frequency=(
                sum(
                    any(abs(candidate - cut) <= 1 for candidate in boundaries)
                    for boundaries in fold_selected_boundaries
                )
                / len(eligible)
            ),
            eligible_fold_count=len(eligible),
        )
        for cut in range(1, len(full_grid.buckets))
    )
    full_fit = {item.regime_count: item.fit_error for item in full_segmentation.objectives}
    scores = tuple(
        RegimeModelScoreV1(
            regime_count=regime_count,
            full_data_fit_error=full_fit[regime_count],
            mean_validation_error=summaries[regime_count][0],
            validation_standard_error=summaries[regime_count][1],
            eligible_fold_count=len(eligible),
            within_one_se=(summaries[regime_count][0] <= threshold + config.cost_tie_epsilon),
        )
        for regime_count in sorted(summaries)
    )
    return RegimeModelSelectionV1(
        direction=direction,
        selection_method="leave_one_day_out_cross_validation_one_standard_error",
        selection_status=RegimeModelSelectionStatusV1.SUCCESS,
        normalization_method=("training_aggregate_max_positive; validation_scaled_by_training_max"),
        total_observed_days=len(observed_dates),
        eligible_validation_days=len(eligible),
        excluded_days=excluded,
        natural_max_regimes=full_segmentation.natural_max_regimes,
        legacy_penalty_selected_regime_count=_legacy_selected_count(profile_segmentation),
        selected_regime_count=selected_count,
        best_validation_regime_count=best_count,
        best_mean_validation_error=best_mean,
        best_standard_error=best_se,
        one_se_threshold=threshold,
        candidate_frontier=_candidate_frontier(direction, full_segmentation),
        model_scores=scores,
        final_boundaries=final_boundaries,
        boundary_stability=stability,
        final_plan=_build_plan(
            direction,
            scope,
            full_grid,
            config,
            scenario_b,
            selected_regime_count=selected_count,
        ),
    )


def select_demand_regime_model_v1(
    profile: DemandProfileV1,
    daily_observations: tuple[DailyDemandObservationV1, ...],
    config: DemandRegimeDetectorConfigV1 = DEFAULT_DEMAND_REGIME_CONFIG_V1,
    *,
    scenario_b: ScenarioBInput | None = None,
    observed_dates: tuple[date, ...] | None = None,
) -> DemandRegimeModelSelectionResultV1:
    """Choose K by deterministic leave-one-day-out CV, then refit on all eligible days.

    Daily eligibility requires exact coverage of the already validated canonical
    profile grid. Missing buckets exclude that date and are never interpreted as
    zero. The legacy complexity penalty is reported only as a diagnostic.
    """

    scope = _scope(profile)
    by_direction: dict[ContractDirection, list[DerivedDemandObservationV1]] = defaultdict(list)
    for item in profile.derived_observations:
        by_direction[item.direction].append(item)
    expected_directions = (
        (ContractDirection.COMBINED,)
        if profile.direction_grain == DemandDirectionGrainV1.COMBINED
        else (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    )
    grids = tuple(
        _grid_for_direction(direction, by_direction.get(direction, []))
        for direction in expected_directions
    )
    coverage = tuple(item.coverage for item in grids)
    if any(not item.sufficient for item in coverage):
        failed = "; ".join(
            f"{item.direction.value}: {item.reason}" for item in coverage if not item.sufficient
        )
        return DemandRegimeModelSelectionResultV1(
            selector_profile=DEMAND_REGIME_MODEL_SELECTOR_PROFILE_V1,
            status=RegimeModelSelectionStatusV1.INSUFFICIENT_DEMAND_COVERAGE,
            demand_profile_id=profile.profile_id,
            demand_profile_fingerprint=profile.profile_fingerprint,
            direction_grain=profile.direction_grain,
            scope=scope,
            config=config,
            coverage=coverage,
            selections=(),
            failure_code=INSUFFICIENT_DEMAND_COVERAGE,
            failure_message=failed,
        )
    accepted = set(expected_directions)
    if any(not isinstance(item.observation_date, date) for item in daily_observations):
        raise ValueError("daily observations require date-valued observation_date")
    derived_observed_dates = {
        item.observation_date for item in daily_observations if item.direction in accepted
    }
    if observed_dates is None:
        canonical_observed_dates = tuple(sorted(derived_observed_dates))
    else:
        if any(not isinstance(item, date) for item in observed_dates):
            raise ValueError("observed_dates must contain date values")
        canonical_observed_dates = tuple(sorted(set(observed_dates) | derived_observed_dates))
    selections = tuple(
        _select_for_direction(
            direction,
            scope,
            grid,
            daily_observations,
            canonical_observed_dates,
            config,
            scenario_b,
        )
        for direction, grid in zip(expected_directions, grids, strict=True)
    )
    successful = all(
        item.selection_status == RegimeModelSelectionStatusV1.SUCCESS for item in selections
    )
    status = (
        RegimeModelSelectionStatusV1.SUCCESS
        if successful
        else RegimeModelSelectionStatusV1.INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS
    )
    return DemandRegimeModelSelectionResultV1(
        selector_profile=DEMAND_REGIME_MODEL_SELECTOR_PROFILE_V1,
        status=status,
        demand_profile_id=profile.profile_id,
        demand_profile_fingerprint=profile.profile_fingerprint,
        direction_grain=profile.direction_grain,
        scope=scope,
        config=config,
        coverage=coverage,
        selections=selections,
        failure_code=(None if successful else INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS),
        failure_message=(
            None
            if successful
            else "At least one direction lacks sufficient eligible date-keyed daily demand."
        ),
    )


def demand_regime_detection_to_dict_v1(
    result: DemandRegimeDetectionResultV1,
) -> dict[str, object]:
    """Return a stable JSON-ready representation in canonical model order."""

    def convert(value: object) -> object:
        if isinstance(value, StrEnum):
            return value.value
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        return value

    return convert(asdict(result))  # type: ignore[return-value]


def demand_regime_model_selection_to_dict_v1(
    result: DemandRegimeModelSelectionResultV1,
) -> dict[str, object]:
    """Return a stable JSON-ready model-selection representation."""

    def convert(value: object) -> object:
        if isinstance(value, StrEnum):
            return value.value
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): convert(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        return value

    return convert(asdict(result))  # type: ignore[return-value]


__all__ = [
    "BoundaryStabilityV1",
    "BoundaryDecisionV1",
    "DailyDemandExclusionV1",
    "DailyDemandObservationV1",
    "DEFAULT_DEMAND_REGIME_CONFIG_V1",
    "DEMAND_REGIME_DETECTOR_PROFILE_V1",
    "DEMAND_REGIME_MODEL_SELECTOR_PROFILE_V1",
    "DemandBoundaryEvidenceV1",
    "DemandCoverageEvidenceV1",
    "DemandRegimeDetectionResultV1",
    "DemandRegimeDetectionStatusV1",
    "DemandRegimeDetectorConfigV1",
    "DemandRegimeModelSelectionResultV1",
    "DemandRegimePlanV1",
    "DemandRegimeScopeV1",
    "DemandRegimeV1",
    "INSUFFICIENT_DEMAND_COVERAGE",
    "INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS",
    "RegimeCandidateFrontierV1",
    "RegimeCandidateV1",
    "RegimeCountObjectiveV1",
    "RegimeModelScoreV1",
    "RegimeModelSelectionStatusV1",
    "RegimeModelSelectionV1",
    "demand_regime_detection_to_dict_v1",
    "demand_regime_model_selection_to_dict_v1",
    "detect_demand_regimes_v1",
    "select_demand_regime_model_v1",
]
