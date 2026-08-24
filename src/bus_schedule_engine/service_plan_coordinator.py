"""Closed-loop ServicePlan search coordinator for the Route 6/10 review pilot."""

from __future__ import annotations

import hashlib
import heapq
import json
import math
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .clean_boundary_pilot import (
    build_minimum_fleet_plan_v1,
    validate_fleet_combination_v1,
)
from .contracts_v1.clean_boundary_compiler import OperationalEndpointAuthorityV1
from .contracts_v1.clean_compile_frontier import (
    CleanCompileVariantV1,
    compile_service_plan_frontier_v1,
)
from .contracts_v1.closed_loop_service_protection import (
    INVALID_TRANSLATED_PROTECTION_AUTHORITY,
    ClosedLoopServiceProtectionAuthorityV1,
    ClosedLoopServiceProtectionAuthorityValidationV1,
    ClosedLoopServiceProtectionViolationV1,
    _validate_trusted_closed_loop_service_protection_v1,
    validate_closed_loop_service_protection_authority_v1,
)
from .contracts_v1.service_plan_state import (
    ServicePlanMoveV1,
    ServicePlanNeighborV1,
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
    merge_adjacent_neighbors_v1,
    move_one_trip_left_to_right_neighbors_v1,
    move_one_trip_right_to_left_neighbors_v1,
    service_plan_fingerprint_payload_v1,
    service_plan_fingerprint_v1,
    shift_boundary_left_neighbors_v1,
    shift_boundary_right_neighbors_v1,
    split_regime_neighbors_v1,
    tail_absorb_one_neighbors_v1,
    tail_release_one_neighbors_v1,
    validate_service_plan_state_v1,
)
from .models import Direction
from .time_utils import format_hhmm
from .v3_workbook import import_v3_multi_period_workbook_v1

SERVICE_PLAN_COORDINATOR_PROFILE_V1 = "closed_loop_service_plan_coordinator_v1"
SEARCH_BUDGET_EXHAUSTED = "SEARCH_BUDGET_EXHAUSTED"
SEARCH_COMPLETE = "SEARCH_COMPLETE"

REDUNDANT_SERVICE_BOUNDARY = "REDUNDANT_SERVICE_BOUNDARY"
CLEAN_BOUNDARY_UNCOMPILABLE = "CLEAN_BOUNDARY_UNCOMPILABLE"
FLEET_LIMIT_EXCEEDED = "FLEET_LIMIT_EXCEEDED"
LARGEST_SERVICE_FREQUENCY_JUMP = "LARGEST_SERVICE_FREQUENCY_JUMP"
TAIL_OVER_SERVICE = "TAIL_OVER_SERVICE"
TAIL_UNDER_SERVICE = "TAIL_UNDER_SERVICE"
DEMAND_UNDERSERVED_INTERVAL = "DEMAND_UNDERSERVED_INTERVAL"
DEMAND_OVERSERVED_INTERVAL = "DEMAND_OVERSERVED_INTERVAL"
FIXED_ENDPOINT_CONFLICT = "FIXED_ENDPOINT_CONFLICT"
DEMAND_RESPONSE_DIRECTION_MISMATCH = "DEMAND_RESPONSE_DIRECTION_MISMATCH"

NUMERICAL_EPSILON = 1e-12
UNIFORM_WITHIN_DEMAND_BUCKET_ASSUMPTION = "UNIFORM_WITHIN_DEMAND_BUCKET_ASSUMPTION"


@dataclass(frozen=True, slots=True)
class CoordinatorSearchBudgetV1:
    max_service_plan_evaluations: int = 24
    max_open_states: int = 512
    max_compile_frontier_per_state: int = 4
    max_directional_compilations: int = 24
    max_pair_frontier: int = 512

    def __post_init__(self) -> None:
        if min(asdict(self).values()) <= 0:
            raise ValueError("all coordinator technical budgets must be positive")


DEFAULT_COORDINATOR_SEARCH_BUDGET_V1 = CoordinatorSearchBudgetV1()


@dataclass(slots=True)
class CoordinatorSearchStatisticsV1:
    states_generated: int = 0
    states_evaluated: int = 0
    duplicate_states_skipped: int = 0
    states_pruned: int = 0
    compile_variants_evaluated: int = 0
    protected_compile_variants_rejected: int = 0
    fleet_validations_run: int = 0
    fleet_feedback_expansion_requests: int = 0
    fleet_feedback_expansions_executed: int = 0
    fleet_feedback_expansions_skipped: int = 0
    search_iterations: int = 0
    budget_exhausted: bool = False


@dataclass(frozen=True, slots=True)
class DemandBucketEvidenceV1:
    direction: str
    start: int
    end: int
    observed_demand: float

    def __post_init__(self) -> None:
        if self.direction not in {"outbound", "inbound"}:
            raise ValueError("unsupported demand direction")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("invalid demand bucket")
        if not math.isfinite(self.observed_demand) or self.observed_demand < 0:
            raise ValueError("observed demand must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class DemandResponseRegimeEvidenceV1:
    regime_id: str
    direction: str
    start: int
    end: int
    integrated_demand_mass: float
    demand_rate_per_hour: float

    def __post_init__(self) -> None:
        if not self.regime_id.strip():
            raise ValueError("DemandRegime regime_id is required")
        if self.direction not in {"outbound", "inbound"}:
            raise ValueError("unsupported DemandRegime direction")
        if self.start < 0 or self.end <= self.start:
            raise ValueError("DemandRegime must have a positive interval")
        if self.start % 60 or self.end % 60:
            raise ValueError("DemandRegime boundaries must be whole-minute values")
        if not math.isfinite(self.integrated_demand_mass) or self.integrated_demand_mass <= 0:
            raise ValueError("DemandRegime integrated demand mass must be finite and positive")
        if not math.isfinite(self.demand_rate_per_hour) or self.demand_rate_per_hour <= 0:
            raise ValueError("DemandRegime demand rate must be finite and positive")


@dataclass(frozen=True, slots=True)
class DemandResponseRegimeProjectionV1:
    regime_id: str
    direction: str
    start: int
    end: int
    integrated_demand_mass: float
    demand_rate_per_hour: float
    effective_service_frequency_per_hour: float
    equivalent_effective_headway_minutes: float


@dataclass(frozen=True, slots=True)
class DemandResponseTransitionV1:
    direction: str
    boundary_time: int
    interval_start: int
    interval_end: int
    left_demand_regime_id: str
    right_demand_regime_id: str
    delta_log_demand: float
    delta_log_service: float
    demand_direction: str
    service_direction: str
    direction_aligned: bool
    sqrt_expected_delta_log_service: float
    sqrt_response_residual: float


@dataclass(frozen=True, slots=True)
class FeedbackEvidenceV1:
    code: str
    direction: str
    boundary_time: int | None = None
    regime_index: int | None = None
    interval_start: int | None = None
    interval_end: int | None = None
    magnitude: float | None = None
    detail: str = ""
    source_protected_regime_id: str | None = None
    violated_rule: str | None = None
    observed_trip_count: int | None = None
    observed_headway_minutes: float | None = None
    left_demand_regime_id: str | None = None
    right_demand_regime_id: str | None = None
    delta_log_demand: float | None = None
    delta_log_service: float | None = None
    expected_demand_direction: str | None = None
    observed_service_direction: str | None = None
    sqrt_expected_delta_log_service: float | None = None
    sqrt_response_residual: float | None = None


@dataclass(frozen=True, slots=True)
class ActualServiceMetricsV1:
    observed_demand_mismatch: float
    actual_service_regime_count: int
    max_frequency_jump: float
    total_frequency_variation: float
    moved_trips_vs_b: int
    largest_service_shock_boundary: int | None
    tail_headway_minutes: int
    tail_trip_count: int
    tail_start: int
    tail_demand_mismatch: float
    tail_demand_debt: float
    bucket_service_counts: tuple[int, ...]
    bucket_demand_shares: tuple[float, ...]
    bucket_service_shares: tuple[float, ...]
    demand_weighted_expected_passenger_wait_minutes: float
    maximum_bucket_expected_wait_minutes: float
    per_bucket_expected_wait_minutes: tuple[float | None, ...]
    active_demand_mass: float
    demand_response_regime_projections: tuple[DemandResponseRegimeProjectionV1, ...]
    demand_response_transitions: tuple[DemandResponseTransitionV1, ...]
    demand_response_direction_accuracy: float | None
    demand_response_transition_count: int
    demand_response_aligned_transition_count: int
    sqrt_seed_response_deviation: float | None


@dataclass(frozen=True, slots=True)
class DirectionalCompilationCandidateV1:
    state: ServicePlanStateV1
    state_fingerprint: str
    compile_variant: CleanCompileVariantV1
    metrics: ActualServiceMetricsV1
    feedback: tuple[FeedbackEvidenceV1, ...]
    history: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperatingPairMetricsV1:
    observed_demand_mismatch: float
    demand_weighted_expected_passenger_wait_minutes: float
    actual_service_regime_count: int
    max_frequency_jump: float
    total_frequency_variation: float
    moved_trips_vs_b: int
    fleet_required: int
    total_excess_terminal_wait: int
    max_excess_terminal_wait: int

    @property
    def pareto_vector(self) -> tuple[float | int, ...]:
        return (
            self.observed_demand_mismatch,
            self.demand_weighted_expected_passenger_wait_minutes,
            self.actual_service_regime_count,
            self.max_frequency_jump,
            self.total_frequency_variation,
            self.moved_trips_vs_b,
            self.fleet_required,
            self.total_excess_terminal_wait,
        )


@dataclass(frozen=True, slots=True)
class OperatingPairCandidateV1:
    pair_fingerprint: str
    outbound: DirectionalCompilationCandidateV1
    inbound: DirectionalCompilationCandidateV1
    metrics: OperatingPairMetricsV1
    fleet_ceiling: int
    minimum_connection_layover_minutes: int | None
    feedback: tuple[FeedbackEvidenceV1, ...]
    history: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouteCoordinatorContextV1:
    route_id: str
    route_name: str
    endpoint_authority: Mapping[str, OperationalEndpointAuthorityV1]
    demand_buckets: Mapping[str, tuple[DemandBucketEvidenceV1, ...]]
    scenario_b_departures: Mapping[str, tuple[int, ...]]
    seed_headway_prior_minutes: Mapping[str, float]
    planning_grid_seconds: int
    runtime_minutes: int
    minimum_layover_minutes: int
    fleet_ceiling: int
    immutable_demand_sha256: str
    demand_response_regimes: Mapping[str, tuple[DemandResponseRegimeEvidenceV1, ...]] | None = None
    service_protection_authority: ClosedLoopServiceProtectionAuthorityV1 | None = None


@dataclass(frozen=True, slots=True)
class RouteCoordinatorResultV1:
    route_id: str
    status: str
    search_budget: CoordinatorSearchBudgetV1
    statistics: CoordinatorSearchStatisticsV1
    seed_states: tuple[ServicePlanStateV1, ...]
    pareto_frontier: tuple[OperatingPairCandidateV1, ...]
    feedback_code_counts: Mapping[str, int]
    revision_examples: Mapping[str, tuple[str, ...]]
    evaluated_state_fingerprints: tuple[str, ...]
    protection_violations: tuple[ClosedLoopServiceProtectionViolationV1, ...]
    protection_authority_validation: ClosedLoopServiceProtectionAuthorityValidationV1


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_frozen_prior_artifacts_v1(repo_root: Path) -> dict[str, Any]:
    manifest_path = repo_root / "config" / "service_plan_coordinator_frozen_prior_v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected: dict[str, str] = manifest["sha256"]
    actual = {relative: _sha256(repo_root / relative) for relative in sorted(expected)}
    mismatches = {
        relative: {"expected": expected[relative], "actual": actual[relative]}
        for relative in sorted(expected)
        if actual[relative] != expected[relative]
    }
    if mismatches:
        raise ValueError(f"frozen V1/V2/V3 artifacts changed: {mismatches}")
    return {
        "profile": manifest["profile"],
        "unchanged": not mismatches,
        "sha256": actual,
    }


def _bucket_counts(
    departures: Sequence[int],
    buckets: Sequence[DemandBucketEvidenceV1],
) -> tuple[int, ...]:
    return tuple(
        sum(bucket.start <= departure < bucket.end for departure in departures)
        for bucket in buckets
    )


def _overlap(left_start: int, left_end: int, right_start: int, right_end: int) -> int:
    return max(0, min(left_end, right_end) - max(left_start, right_start))


def _tail_demand_share(
    buckets: Sequence[DemandBucketEvidenceV1],
    *,
    tail_start: int,
) -> float:
    total = sum(item.observed_demand for item in buckets)
    if total <= 0:
        return 0.0
    demand = 0.0
    for bucket in buckets:
        overlap = _overlap(bucket.start, bucket.end, tail_start, bucket.end)
        if overlap:
            demand += bucket.observed_demand * overlap / (bucket.end - bucket.start)
    return demand / total


def expected_passenger_wait_metrics_v1(
    departures: Sequence[int],
    demand_buckets: Sequence[DemandBucketEvidenceV1],
) -> tuple[float, float, tuple[float | None, ...], float]:
    """Integrate exact next-departure wait over piecewise-constant demand buckets."""

    exact = tuple(departures)
    if len(exact) < 2 or exact != tuple(sorted(set(exact))):
        raise ValueError("at least two strictly increasing exact departures are required")
    first, last = exact[0], exact[-1]
    total_mass = 0.0
    total_weighted_wait_seconds = 0.0
    per_bucket: list[float | None] = []
    for bucket in demand_buckets:
        active_start = max(first, bucket.start)
        active_end = min(last, bucket.end)
        if active_end <= active_start or bucket.observed_demand == 0:
            per_bucket.append(None)
            continue
        intensity = bucket.observed_demand / (bucket.end - bucket.start)
        bucket_mass = intensity * (active_end - active_start)
        bucket_weighted_wait_seconds = 0.0
        for left, right in zip(exact, exact[1:], strict=False):
            overlap_start = max(left, active_start)
            overlap_end = min(right, active_end)
            if overlap_end <= overlap_start:
                continue
            integrated_wait_seconds_squared = (
                right * (overlap_end - overlap_start) - (overlap_end**2 - overlap_start**2) / 2
            )
            bucket_weighted_wait_seconds += intensity * integrated_wait_seconds_squared
        expected_minutes = bucket_weighted_wait_seconds / bucket_mass / 60
        per_bucket.append(expected_minutes)
        total_mass += bucket_mass
        total_weighted_wait_seconds += bucket_weighted_wait_seconds
    if not math.isfinite(total_mass) or total_mass <= 0:
        raise ValueError("no positive immutable demand mass intersects the active service span")
    expected_wait = total_weighted_wait_seconds / total_mass / 60
    active_bucket_waits = tuple(value for value in per_bucket if value is not None)
    if not active_bucket_waits:
        raise ValueError("active demand buckets must contain expected-wait evidence")
    return expected_wait, max(active_bucket_waits), tuple(per_bucket), total_mass


def _effective_service_frequency_per_hour_v1(
    departures: Sequence[int],
    *,
    window_start: int,
    window_end: int,
) -> float:
    if window_end <= window_start:
        raise ValueError("service projection window must have positive duration")
    integral = 0.0
    covered = 0
    for left, right in zip(departures, departures[1:], strict=False):
        overlap = _overlap(left, right, window_start, window_end)
        if overlap:
            integral += 3600.0 / (right - left) * overlap
            covered += overlap
    if covered != window_end - window_start:
        raise ValueError(
            "exact timetable does not cover the complete canonical DemandRegime window"
        )
    frequency = integral / (window_end - window_start)
    if not math.isfinite(frequency) or frequency <= 0:
        raise ValueError("projected service frequency must be finite and positive")
    return frequency


def demand_response_diagnostics_v1(
    departures: Sequence[int],
    regimes: Sequence[DemandResponseRegimeEvidenceV1],
) -> tuple[
    tuple[DemandResponseRegimeProjectionV1, ...],
    tuple[DemandResponseTransitionV1, ...],
    float | None,
    int,
    int,
    float | None,
]:
    """Project an exact timetable onto immutable canonical DemandRegime windows."""

    exact = tuple(departures)
    if len(exact) < 2 or exact != tuple(sorted(set(exact))):
        raise ValueError("at least two strictly increasing exact departures are required")
    ordered = tuple(regimes)
    if not ordered:
        return (), (), None, 0, 0, None
    direction = ordered[0].direction
    if any(item.direction != direction for item in ordered):
        raise ValueError("canonical DemandRegime evidence cannot mix directions")
    if tuple(sorted(ordered, key=lambda item: (item.start, item.end, item.regime_id))) != ordered:
        raise ValueError("canonical DemandRegime evidence must be deterministically ordered")
    for left, right in zip(ordered, ordered[1:], strict=False):
        if left.end != right.start:
            raise ValueError("canonical DemandRegime evidence must be contiguous")
    projections = tuple(
        DemandResponseRegimeProjectionV1(
            regime_id=item.regime_id,
            direction=item.direction,
            start=item.start,
            end=item.end,
            integrated_demand_mass=item.integrated_demand_mass,
            demand_rate_per_hour=item.demand_rate_per_hour,
            effective_service_frequency_per_hour=(
                frequency := _effective_service_frequency_per_hour_v1(
                    exact,
                    window_start=item.start,
                    window_end=item.end,
                )
            ),
            equivalent_effective_headway_minutes=60.0 / frequency,
        )
        for item in ordered
    )
    transitions: list[DemandResponseTransitionV1] = []
    weights: list[float] = []
    for left, right in zip(projections, projections[1:], strict=False):
        delta_demand = math.log(right.demand_rate_per_hour / left.demand_rate_per_hour)
        if abs(delta_demand) <= NUMERICAL_EPSILON:
            raise ValueError("adjacent canonical DemandRegimes must have distinct demand rates")
        delta_service = math.log(
            right.effective_service_frequency_per_hour / left.effective_service_frequency_per_hour
        )
        demand_direction = "UP" if delta_demand > 0 else "DOWN"
        service_direction = (
            "FLAT"
            if abs(delta_service) <= NUMERICAL_EPSILON
            else ("UP" if delta_service > 0 else "DOWN")
        )
        expected = 0.5 * delta_demand
        transitions.append(
            DemandResponseTransitionV1(
                direction=direction,
                boundary_time=right.start,
                interval_start=left.start,
                interval_end=right.end,
                left_demand_regime_id=left.regime_id,
                right_demand_regime_id=right.regime_id,
                delta_log_demand=delta_demand,
                delta_log_service=delta_service,
                demand_direction=demand_direction,
                service_direction=service_direction,
                direction_aligned=(demand_direction == service_direction),
                sqrt_expected_delta_log_service=expected,
                sqrt_response_residual=delta_service - expected,
            )
        )
        weights.append(((left.end - left.start) + (right.end - right.start)) / 2)
    transition_tuple = tuple(transitions)
    weight_sum = sum(weights)
    aligned_count = sum(item.direction_aligned for item in transition_tuple)
    accuracy = (
        None
        if weight_sum <= 0
        else sum(
            weight
            for item, weight in zip(transition_tuple, weights, strict=True)
            if item.direction_aligned
        )
        / weight_sum
    )
    sqrt_deviation = (
        None
        if weight_sum <= 0
        else sum(
            weight * abs(item.sqrt_response_residual)
            for item, weight in zip(transition_tuple, weights, strict=True)
        )
        / weight_sum
    )
    return (
        projections,
        transition_tuple,
        accuracy,
        len(transition_tuple),
        aligned_count,
        sqrt_deviation,
    )


def evaluate_actual_service_v1(
    candidate: CleanCompileVariantV1,
    *,
    demand_buckets: Sequence[DemandBucketEvidenceV1],
    scenario_b_departures: Sequence[int],
    demand_response_regimes: Sequence[DemandResponseRegimeEvidenceV1] | None = None,
) -> tuple[ActualServiceMetricsV1, tuple[FeedbackEvidenceV1, ...]]:
    """Evaluate the exact compiled timestamps against immutable demand buckets."""

    compilation = candidate.compilation
    if not demand_buckets:
        raise ValueError("immutable demand buckets are required")
    total_demand = sum(item.observed_demand for item in demand_buckets)
    if total_demand <= 0:
        raise ValueError("immutable demand must contain positive mass")
    actual_counts = _bucket_counts(compilation.exact_departures, demand_buckets)
    b_counts = _bucket_counts(scenario_b_departures, demand_buckets)
    total_trips = len(compilation.exact_departures)
    demand_shares = tuple(item.observed_demand / total_demand for item in demand_buckets)
    service_shares = tuple(item / total_trips for item in actual_counts)
    mismatch = sum(
        (service - demand) ** 2
        for service, demand in zip(service_shares, demand_shares, strict=True)
    )
    movement_l1 = sum(
        abs(actual - baseline) for actual, baseline in zip(actual_counts, b_counts, strict=True)
    )
    moved = movement_l1 // 2
    jumps: list[tuple[float, int, int]] = []
    services = compilation.service_regimes
    for index, (left, right) in enumerate(zip(services, services[1:], strict=False)):
        left_frequency = 60 / left.uniform_headway_minutes
        right_frequency = 60 / right.uniform_headway_minutes
        jump = abs(math.log(right_frequency / left_frequency))
        jumps.append((jump, right.first_departure, index))
    max_jump = max((item[0] for item in jumps), default=0.0)
    total_variation = sum(item[0] for item in jumps)
    largest_boundary = min(
        (item for item in jumps if math.isclose(item[0], max_jump, abs_tol=1e-15)),
        default=None,
        key=lambda item: (item[1], item[2]),
    )
    tail = services[-1]
    tail_service_share = tail.trip_count / total_trips
    tail_demand_share = _tail_demand_share(demand_buckets, tail_start=tail.first_departure)
    tail_debt = tail_demand_share - tail_service_share
    (
        expected_wait,
        maximum_bucket_wait,
        per_bucket_wait,
        active_demand_mass,
    ) = expected_passenger_wait_metrics_v1(compilation.exact_departures, demand_buckets)
    (
        response_projections,
        response_transitions,
        response_accuracy,
        response_transition_count,
        response_aligned_count,
        sqrt_response_deviation,
    ) = demand_response_diagnostics_v1(
        compilation.exact_departures,
        () if demand_response_regimes is None else demand_response_regimes,
    )
    metrics = ActualServiceMetricsV1(
        observed_demand_mismatch=mismatch,
        actual_service_regime_count=len(services),
        max_frequency_jump=max_jump,
        total_frequency_variation=total_variation,
        moved_trips_vs_b=moved,
        largest_service_shock_boundary=(largest_boundary[1] if largest_boundary else None),
        tail_headway_minutes=tail.uniform_headway_minutes,
        tail_trip_count=tail.trip_count,
        tail_start=tail.first_departure,
        tail_demand_mismatch=abs(tail_debt),
        tail_demand_debt=tail_debt,
        bucket_service_counts=actual_counts,
        bucket_demand_shares=demand_shares,
        bucket_service_shares=service_shares,
        demand_weighted_expected_passenger_wait_minutes=expected_wait,
        maximum_bucket_expected_wait_minutes=maximum_bucket_wait,
        per_bucket_expected_wait_minutes=per_bucket_wait,
        active_demand_mass=active_demand_mass,
        demand_response_regime_projections=response_projections,
        demand_response_transitions=response_transitions,
        demand_response_direction_accuracy=response_accuracy,
        demand_response_transition_count=response_transition_count,
        demand_response_aligned_transition_count=response_aligned_count,
        sqrt_seed_response_deviation=sqrt_response_deviation,
    )
    feedback: list[FeedbackEvidenceV1] = []
    for index, diagnostic in enumerate(compilation.boundary_diagnostics):
        if diagnostic.ownership.value == "MERGED_EQUAL_HEADWAY_SERVICE_REGIME":
            feedback.append(
                FeedbackEvidenceV1(
                    REDUNDANT_SERVICE_BOUNDARY,
                    compilation.direction,
                    boundary_time=diagnostic.boundary_time,
                    regime_index=index,
                    detail="Compilation realized one continuous equal rhythm across this boundary.",
                )
            )
    if largest_boundary is not None and largest_boundary[0] > 0:
        feedback.append(
            FeedbackEvidenceV1(
                LARGEST_SERVICE_FREQUENCY_JUMP,
                compilation.direction,
                boundary_time=largest_boundary[1],
                regime_index=largest_boundary[2],
                magnitude=largest_boundary[0],
                detail="Largest relative frequency change in the actual compiled service.",
            )
        )
    differences = tuple(
        service - demand for service, demand in zip(service_shares, demand_shares, strict=True)
    )
    under_index = min(range(len(differences)), key=lambda index: (differences[index], index))
    over_index = max(range(len(differences)), key=lambda index: (differences[index], -index))
    under_error = differences[under_index]
    over_error = differences[over_index]
    quantum = 1 / total_trips
    transfer_before = under_error**2 + over_error**2
    transfer_after = (under_error + quantum) ** 2 + (over_error - quantum) ** 2
    demand_transfer_material = (
        under_error < 0 and over_error > 0 and transfer_after < transfer_before - NUMERICAL_EPSILON
    )
    if demand_transfer_material:
        bucket = demand_buckets[under_index]
        feedback.append(
            FeedbackEvidenceV1(
                DEMAND_UNDERSERVED_INTERVAL,
                compilation.direction,
                interval_start=bucket.start,
                interval_end=bucket.end,
                magnitude=-differences[under_index],
                detail="Largest immutable-bucket demand share minus compiled service share.",
            )
        )
    if demand_transfer_material:
        bucket = demand_buckets[over_index]
        feedback.append(
            FeedbackEvidenceV1(
                DEMAND_OVERSERVED_INTERVAL,
                compilation.direction,
                interval_start=bucket.start,
                interval_end=bucket.end,
                magnitude=differences[over_index],
                detail="Largest compiled service share minus immutable-bucket demand share.",
            )
        )
    tail_adjusted_debt = tail_debt - quantum if tail_debt > 0 else tail_debt + quantum
    if tail_adjusted_debt**2 < tail_debt**2 - NUMERICAL_EPSILON:
        feedback.append(
            FeedbackEvidenceV1(
                TAIL_UNDER_SERVICE if tail_debt > 0 else TAIL_OVER_SERVICE,
                compilation.direction,
                interval_start=tail.first_departure,
                interval_end=demand_buckets[-1].end,
                magnitude=abs(tail_debt),
                detail="Signed tail demand share minus compiled tail service share.",
            )
        )
    defects = tuple(item for item in response_transitions if not item.direction_aligned)
    if defects:
        defect = min(
            defects,
            key=lambda item: (
                -abs(item.sqrt_response_residual),
                -abs(item.delta_log_demand),
                item.boundary_time,
                item.left_demand_regime_id,
                item.right_demand_regime_id,
            ),
        )
        feedback.append(
            FeedbackEvidenceV1(
                code=DEMAND_RESPONSE_DIRECTION_MISMATCH,
                direction=compilation.direction,
                boundary_time=defect.boundary_time,
                interval_start=defect.interval_start,
                interval_end=defect.interval_end,
                magnitude=abs(defect.sqrt_response_residual),
                detail="Exact service response is flat or opposite to immutable demand direction.",
                left_demand_regime_id=defect.left_demand_regime_id,
                right_demand_regime_id=defect.right_demand_regime_id,
                delta_log_demand=defect.delta_log_demand,
                delta_log_service=defect.delta_log_service,
                expected_demand_direction=defect.demand_direction,
                observed_service_direction=defect.service_direction,
                sqrt_expected_delta_log_service=(defect.sqrt_expected_delta_log_service),
                sqrt_response_residual=defect.sqrt_response_residual,
            )
        )
    return metrics, tuple(feedback)


def dominates_operating_pair_v1(
    left: OperatingPairCandidateV1,
    right: OperatingPairCandidateV1,
    *,
    epsilon: float = 1e-12,
) -> bool:
    left_values = left.metrics.pareto_vector
    right_values = right.metrics.pareto_vector
    no_worse = all(
        float(a) <= float(b) + epsilon for a, b in zip(left_values, right_values, strict=True)
    )
    strictly_better = any(
        float(a) < float(b) - epsilon for a, b in zip(left_values, right_values, strict=True)
    )
    return no_worse and strictly_better


def update_operating_pair_pareto_v1(
    frontier: Sequence[OperatingPairCandidateV1],
    candidate: OperatingPairCandidateV1,
    *,
    limit: int | None = None,
) -> tuple[OperatingPairCandidateV1, ...]:
    if any(dominates_operating_pair_v1(item, candidate) for item in frontier):
        return tuple(frontier)
    retained = [item for item in frontier if not dominates_operating_pair_v1(candidate, item)]
    if all(item.pair_fingerprint != candidate.pair_fingerprint for item in retained):
        retained.append(candidate)
    retained.sort(key=lambda item: (*item.metrics.pareto_vector, item.pair_fingerprint))
    return tuple(retained if limit is None else retained[:limit])


def _pair_fingerprint(
    outbound: DirectionalCompilationCandidateV1,
    inbound: DirectionalCompilationCandidateV1,
) -> str:
    encoded = json.dumps(
        {
            "route_id": outbound.state.route_id,
            "outbound_compile": outbound.compile_variant.compilation_fingerprint,
            "inbound_compile": inbound.compile_variant.compilation_fingerprint,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def evaluate_operating_pair_v1(
    outbound: DirectionalCompilationCandidateV1,
    inbound: DirectionalCompilationCandidateV1,
    *,
    context: RouteCoordinatorContextV1,
) -> tuple[OperatingPairCandidateV1 | None, tuple[FeedbackEvidenceV1, ...]]:
    """Run the unchanged exact-timetable fleet validator before pair quality selection."""

    validation = validate_fleet_combination_v1(
        route_id=context.route_id,
        outbound=outbound.compile_variant.compilation,
        inbound=inbound.compile_variant.compilation,
        outbound_allocation={
            "demand_mismatch": outbound.metrics.observed_demand_mismatch,
            "moved_trips": outbound.metrics.moved_trips_vs_b,
        },
        inbound_allocation={
            "demand_mismatch": inbound.metrics.observed_demand_mismatch,
            "moved_trips": inbound.metrics.moved_trips_vs_b,
        },
        runtime_minutes=context.runtime_minutes,
        minimum_layover_minutes=context.minimum_layover_minutes,
        fleet_ceiling=context.fleet_ceiling,
    )
    if validation.fleet_requirement is None:
        return None, (
            FeedbackEvidenceV1(
                CLEAN_BOUNDARY_UNCOMPILABLE,
                "pair",
                detail="Fleet validator did not receive two compiled timetables.",
            ),
        )
    if validation.status != "FLEET_FEASIBLE":
        feedback = (
            FeedbackEvidenceV1(
                FLEET_LIMIT_EXCEEDED,
                "pair",
                magnitude=float(validation.fleet_requirement - context.fleet_ceiling),
                detail=(
                    f"Exact pair needs {validation.fleet_requirement} vehicles; "
                    f"ceiling is {context.fleet_ceiling}."
                ),
            ),
        )
        return None, feedback
    fleet_plan = build_minimum_fleet_plan_v1(
        route_id=context.route_id,
        outbound_candidate_id=outbound.compile_variant.compilation.candidate_id,
        inbound_candidate_id=inbound.compile_variant.compilation.candidate_id,
        outbound_departures=outbound.compile_variant.compilation.exact_departures,
        inbound_departures=inbound.compile_variant.compilation.exact_departures,
        runtime_minutes=context.runtime_minutes,
        minimum_layover_minutes=context.minimum_layover_minutes,
    )
    excess_waits = tuple(
        max(0, int(item.connection_layover_minutes) - context.minimum_layover_minutes)
        for item in fleet_plan.assignments
        if item.connection_layover_minutes is not None
    )
    outbound_mass = outbound.metrics.active_demand_mass
    inbound_mass = inbound.metrics.active_demand_mass
    pair_mass = outbound_mass + inbound_mass
    directional_wait_values = (
        outbound.metrics.demand_weighted_expected_passenger_wait_minutes,
        inbound.metrics.demand_weighted_expected_passenger_wait_minutes,
    )
    if (
        not all(math.isfinite(value) and value > 0 for value in (outbound_mass, inbound_mass))
        or not all(math.isfinite(value) and value >= 0 for value in directional_wait_values)
        or not math.isfinite(pair_mass)
        or pair_mass <= 0
    ):
        raise ValueError("pair expected wait requires finite positive active demand mass")
    pair_expected_wait = (
        directional_wait_values[0] * outbound_mass + directional_wait_values[1] * inbound_mass
    ) / pair_mass
    metrics = OperatingPairMetricsV1(
        observed_demand_mismatch=(
            outbound.metrics.observed_demand_mismatch + inbound.metrics.observed_demand_mismatch
        ),
        demand_weighted_expected_passenger_wait_minutes=pair_expected_wait,
        actual_service_regime_count=(
            outbound.metrics.actual_service_regime_count
            + inbound.metrics.actual_service_regime_count
        ),
        max_frequency_jump=max(
            outbound.metrics.max_frequency_jump,
            inbound.metrics.max_frequency_jump,
        ),
        total_frequency_variation=(
            outbound.metrics.total_frequency_variation + inbound.metrics.total_frequency_variation
        ),
        moved_trips_vs_b=(outbound.metrics.moved_trips_vs_b + inbound.metrics.moved_trips_vs_b),
        fleet_required=int(validation.fleet_requirement),
        total_excess_terminal_wait=sum(excess_waits),
        max_excess_terminal_wait=max(excess_waits, default=0),
    )
    pair_id = _pair_fingerprint(outbound, inbound)
    history = (
        *outbound.history,
        *inbound.history,
        (
            f"fleet {metrics.fleet_required}/{context.fleet_ceiling}; exact pair retained "
            "for Pareto comparison"
        ),
    )
    return (
        OperatingPairCandidateV1(
            pair_fingerprint=pair_id,
            outbound=outbound,
            inbound=inbound,
            metrics=metrics,
            fleet_ceiling=context.fleet_ceiling,
            minimum_connection_layover_minutes=validation.minimum_connection_layover_minutes,
            feedback=(),
            history=history,
        ),
        (),
    )


def _state_precompile_mismatch(
    state: ServicePlanStateV1,
    buckets: Sequence[DemandBucketEvidenceV1],
) -> float:
    total_demand = sum(item.observed_demand for item in buckets)
    demand_shares = tuple(item.observed_demand / total_demand for item in buckets)
    estimated: list[float] = []
    for bucket in buckets:
        count = 0.0
        for regime in state.service_regimes:
            overlap = _overlap(regime.start, regime.end, bucket.start, bucket.end)
            if overlap:
                count += regime.trip_count * overlap / (regime.end - regime.start)
        estimated.append(count / state.total_trips)
    return sum(
        (service - demand) ** 2 for service, demand in zip(estimated, demand_shares, strict=True)
    )


def _nearest_state_boundary_index(
    state: ServicePlanStateV1,
    boundary_time: int | None,
    regime_index: int | None,
) -> int | None:
    if not state.boundaries:
        return None
    if boundary_time is not None:
        return min(
            range(len(state.boundaries)),
            key=lambda index: (abs(state.boundaries[index] - boundary_time), index),
        )
    if regime_index is not None and 0 <= regime_index < len(state.boundaries):
        return regime_index
    return None


def _overlapping_state_regime_indices(
    state: ServicePlanStateV1,
    interval_start: int | None,
    interval_end: int | None,
) -> tuple[int, ...]:
    if interval_start is None or interval_end is None or interval_end <= interval_start:
        return ()
    return tuple(
        index
        for index, regime in enumerate(state.service_regimes)
        if _overlap(regime.start, regime.end, interval_start, interval_end)
    )


def _local_regime_and_pair_indices(
    state: ServicePlanStateV1,
    core_indices: Sequence[int],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    allowed = set(core_indices)
    for index in core_indices:
        if index > 0:
            allowed.add(index - 1)
        if index + 1 < len(state.service_regimes):
            allowed.add(index + 1)
    regimes = tuple(sorted(allowed))
    pairs = tuple(
        index
        for index in range(len(state.service_regimes) - 1)
        if index in allowed
        and index + 1 in allowed
        and (index in core_indices or index + 1 in core_indices)
    )
    return regimes, pairs


def generate_targeted_neighbors_v1(
    state: ServicePlanStateV1,
    *,
    feedback: Sequence[FeedbackEvidenceV1],
    planning_grid_seconds: int,
    floor_headway_minutes: float | None,
) -> tuple[ServicePlanNeighborV1, ...]:
    """Generate finite existing operators only where structured evidence is located."""

    all_neighbors: list[ServicePlanNeighborV1] = []

    def add(items: Iterable[ServicePlanNeighborV1]) -> None:
        all_neighbors.extend(items)

    def add_local_revision(
        evidence: FeedbackEvidenceV1,
        *,
        regime_indices: Sequence[int],
        pair_indices: Sequence[int],
        split_boundaries: Sequence[int] | None = None,
    ) -> None:
        add(
            split_regime_neighbors_v1(
                state,
                planning_grid_seconds=planning_grid_seconds,
                floor_headway_minutes=floor_headway_minutes,
                evidence_code=evidence.code,
                priority=0,
                affected_indices=regime_indices,
                split_boundary_seconds=split_boundaries,
            )
        )
        for operator in (shift_boundary_left_neighbors_v1, shift_boundary_right_neighbors_v1):
            add(
                operator(
                    state,
                    planning_grid_seconds=planning_grid_seconds,
                    floor_headway_minutes=floor_headway_minutes,
                    evidence_code=evidence.code,
                    priority=0,
                    affected_indices=pair_indices,
                )
            )
        for operator in (
            move_one_trip_left_to_right_neighbors_v1,
            move_one_trip_right_to_left_neighbors_v1,
        ):
            add(
                operator(
                    state,
                    floor_headway_minutes=floor_headway_minutes,
                    evidence_code=evidence.code,
                    priority=0,
                    affected_indices=pair_indices,
                )
            )

    def add_global(evidence_code: str | None, *, targeted: bool) -> None:
        common_priority = 0 if targeted else 2
        add(
            merge_adjacent_neighbors_v1(
                state,
                floor_headway_minutes=floor_headway_minutes,
                evidence_code=evidence_code,
                priority=3,
            )
        )
        add(
            split_regime_neighbors_v1(
                state,
                planning_grid_seconds=planning_grid_seconds,
                floor_headway_minutes=floor_headway_minutes,
                evidence_code=evidence_code,
                priority=3,
            )
        )
        for operator in (shift_boundary_left_neighbors_v1, shift_boundary_right_neighbors_v1):
            add(
                operator(
                    state,
                    planning_grid_seconds=planning_grid_seconds,
                    floor_headway_minutes=floor_headway_minutes,
                    evidence_code=evidence_code,
                    priority=common_priority,
                )
            )
        for operator in (
            move_one_trip_left_to_right_neighbors_v1,
            move_one_trip_right_to_left_neighbors_v1,
        ):
            add(
                operator(
                    state,
                    floor_headway_minutes=floor_headway_minutes,
                    evidence_code=evidence_code,
                    priority=common_priority,
                )
            )
        add(
            tail_absorb_one_neighbors_v1(
                state,
                floor_headway_minutes=floor_headway_minutes,
                evidence_code=evidence_code,
                priority=3,
            )
        )
        add(
            tail_release_one_neighbors_v1(
                state,
                floor_headway_minutes=floor_headway_minutes,
                evidence_code=evidence_code,
                priority=3,
            )
        )

    if not feedback:
        add_global(None, targeted=False)
    for evidence in feedback:
        if evidence.code == REDUNDANT_SERVICE_BOUNDARY:
            boundary_index = _nearest_state_boundary_index(
                state, evidence.boundary_time, evidence.regime_index
            )
            if boundary_index is not None:
                add(
                    merge_adjacent_neighbors_v1(
                        state,
                        floor_headway_minutes=floor_headway_minutes,
                        evidence_code=evidence.code,
                        priority=0,
                        affected_indices=(boundary_index,),
                    )
                )
        elif evidence.code == LARGEST_SERVICE_FREQUENCY_JUMP:
            boundary_index = _nearest_state_boundary_index(
                state, evidence.boundary_time, evidence.regime_index
            )
            if boundary_index is not None:
                add_local_revision(
                    evidence,
                    regime_indices=(boundary_index, boundary_index + 1),
                    pair_indices=(boundary_index,),
                )
        elif evidence.code in {DEMAND_UNDERSERVED_INTERVAL, DEMAND_OVERSERVED_INTERVAL}:
            core = _overlapping_state_regime_indices(
                state, evidence.interval_start, evidence.interval_end
            )
            if core:
                regimes, pairs = _local_regime_and_pair_indices(state, core)
                add_local_revision(evidence, regime_indices=core, pair_indices=pairs)
        elif evidence.code == DEMAND_RESPONSE_DIRECTION_MISMATCH:
            boundary = evidence.boundary_time
            if boundary is None:
                continue
            nearest = _nearest_state_boundary_index(state, boundary, evidence.regime_index)
            if nearest is not None and state.boundaries[nearest] == boundary:
                add_local_revision(
                    evidence,
                    regime_indices=(nearest, nearest + 1),
                    pair_indices=(nearest,),
                )
            else:
                containing = next(
                    (
                        index
                        for index, regime in enumerate(state.service_regimes)
                        if regime.start < boundary < regime.end
                    ),
                    None,
                )
                if containing is not None:
                    adjacent_pairs = tuple(
                        index
                        for index in (containing - 1, containing)
                        if 0 <= index < len(state.service_regimes) - 1
                    )
                    add_local_revision(
                        evidence,
                        regime_indices=(containing,),
                        pair_indices=adjacent_pairs,
                        split_boundaries=(boundary,),
                    )
        elif evidence.code == TAIL_UNDER_SERVICE:
            add(
                tail_absorb_one_neighbors_v1(
                    state,
                    floor_headway_minutes=floor_headway_minutes,
                    evidence_code=evidence.code,
                    priority=0,
                )
            )
        elif evidence.code == TAIL_OVER_SERVICE:
            add(
                tail_release_one_neighbors_v1(
                    state,
                    floor_headway_minutes=floor_headway_minutes,
                    evidence_code=evidence.code,
                    priority=0,
                )
            )
        elif evidence.code == FLEET_LIMIT_EXCEEDED:
            add_global(evidence.code, targeted=True)
        else:
            core = _overlapping_state_regime_indices(
                state, evidence.interval_start, evidence.interval_end
            )
            if core:
                _, pairs = _local_regime_and_pair_indices(state, core)
                add_local_revision(evidence, regime_indices=core, pair_indices=pairs)
            else:
                add_global(evidence.code, targeted=True)
    move_rank = {move: index for index, move in enumerate(ServicePlanMoveV1)}
    unique: dict[str, ServicePlanNeighborV1] = {}
    for neighbor in all_neighbors:
        fingerprint = service_plan_fingerprint_v1(neighbor.state)
        incumbent = unique.get(fingerprint)
        key = (neighbor.priority, move_rank[neighbor.move], neighbor.affected_index)
        if incumbent is None or key < (
            incumbent.priority,
            move_rank[incumbent.move],
            incumbent.affected_index,
        ):
            unique[fingerprint] = neighbor
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                item.priority,
                move_rank[item.move],
                item.affected_index,
                service_plan_fingerprint_v1(item.state),
            ),
        )
    )


def _directional_vector(item: DirectionalCompilationCandidateV1) -> tuple[float | int, ...]:
    return (
        item.metrics.observed_demand_mismatch,
        item.metrics.actual_service_regime_count,
        item.metrics.max_frequency_jump,
        item.metrics.total_frequency_variation,
        item.metrics.moved_trips_vs_b,
        item.compile_variant.headway_quantization,
        item.compile_variant.phase_edge_quality_minutes,
    )


def _directional_local_quality_key(
    item: DirectionalCompilationCandidateV1,
) -> tuple[Any, ...]:
    return (
        *_directional_vector(item),
        item.compile_variant.compilation.exact_departures,
        item.compile_variant.compilation_fingerprint,
    )


def _directional_departure_distance(
    left: DirectionalCompilationCandidateV1,
    right: DirectionalCompilationCandidateV1,
) -> int:
    return sum(
        abs(a - b)
        for a, b in zip(
            left.compile_variant.compilation.exact_departures,
            right.compile_variant.compilation.exact_departures,
            strict=True,
        )
    )


def _retain_directional_archive(
    items: Sequence[DirectionalCompilationCandidateV1],
    *,
    limit: int,
) -> list[DirectionalCompilationCandidateV1]:
    """Bound an exact-compilation archive with state and phase diversity."""

    if limit <= 0:
        raise ValueError("directional archive limit must be positive")
    unique: dict[str, DirectionalCompilationCandidateV1] = {}
    for item in sorted(items, key=_directional_local_quality_key):
        unique.setdefault(item.compile_variant.compilation_fingerprint, item)
    ordered = sorted(unique.values(), key=_directional_local_quality_key)
    if len(ordered) <= limit:
        return ordered

    selected = [ordered[0]]
    selected_fingerprints = {ordered[0].compile_variant.compilation_fingerprint}

    def select_max_min(
        candidates: Sequence[DirectionalCompilationCandidateV1],
    ) -> DirectionalCompilationCandidateV1:
        return min(
            candidates,
            key=lambda item: (
                -min(_directional_departure_distance(item, retained) for retained in selected),
                _directional_local_quality_key(item),
            ),
        )

    # When capacity permits, keep the best local representative of every state first.
    representative_by_state: dict[str, DirectionalCompilationCandidateV1] = {}
    for candidate in ordered:
        representative_by_state.setdefault(candidate.state_fingerprint, candidate)
    state_candidates = [
        candidate
        for candidate in representative_by_state.values()
        if candidate.compile_variant.compilation_fingerprint not in selected_fingerprints
    ]
    while state_candidates and len(selected) < limit:
        candidate = select_max_min(state_candidates)
        selected.append(candidate)
        selected_fingerprints.add(candidate.compile_variant.compilation_fingerprint)
        state_candidates.remove(candidate)

    # With capacity left after state diversity, retain exact wait and sqrt-response anchors.
    anchor_order = (
        min(
            ordered,
            key=lambda item: (
                item.metrics.demand_weighted_expected_passenger_wait_minutes,
                _directional_local_quality_key(item),
            ),
        ),
        min(
            ordered,
            key=lambda item: (
                math.inf
                if item.metrics.sqrt_seed_response_deviation is None
                else item.metrics.sqrt_seed_response_deviation,
                _directional_local_quality_key(item),
            ),
        ),
    )
    for candidate in anchor_order:
        fingerprint = candidate.compile_variant.compilation_fingerprint
        if len(selected) >= limit:
            break
        if fingerprint not in selected_fingerprints:
            selected.append(candidate)
            selected_fingerprints.add(fingerprint)

    # Use remaining slots for phase-distinct variants, again by exact max-min distance.
    remaining = [
        candidate
        for candidate in ordered
        if candidate.compile_variant.compilation_fingerprint not in selected_fingerprints
    ]
    while remaining and len(selected) < limit:
        candidate = select_max_min(remaining)
        selected.append(candidate)
        selected_fingerprints.add(candidate.compile_variant.compilation_fingerprint)
        remaining.remove(candidate)
    return selected


@dataclass(slots=True)
class _BoundedOpenQueue:
    limit: int
    heap: list[tuple[tuple[Any, ...], str, int, ServicePlanStateV1]] = field(default_factory=list)
    active: dict[str, tuple[tuple[Any, ...], int]] = field(default_factory=dict)
    _next_ticket: int = field(default=0, init=False)

    def push(
        self,
        state: ServicePlanStateV1,
        priority: tuple[Any, ...],
    ) -> tuple[bool, bool, str | None]:
        fingerprint = service_plan_fingerprint_v1(state)
        incumbent = self.active.get(fingerprint)
        if incumbent is not None and incumbent[0] <= priority:
            return False, False, None
        removed: str | None = None
        if incumbent is None and len(self.active) >= self.limit:
            worst_fingerprint, (worst_priority, _) = max(
                self.active.items(), key=lambda item: (item[1][0], item[0])
            )
            if (priority, fingerprint) >= (worst_priority, worst_fingerprint):
                return False, True, fingerprint
            removed = worst_fingerprint
            del self.active[worst_fingerprint]
        ticket = self._next_ticket
        self._next_ticket += 1
        self.active[fingerprint] = (priority, ticket)
        heapq.heappush(self.heap, (priority, fingerprint, ticket, state))
        return True, removed is not None, removed

    def pop(self) -> tuple[ServicePlanStateV1, tuple[Any, ...]] | None:
        while self.heap:
            priority, fingerprint, ticket, state = heapq.heappop(self.heap)
            if self.active.get(fingerprint) == (priority, ticket):
                del self.active[fingerprint]
                return state, priority
        return None

    def __bool__(self) -> bool:
        return bool(self.active)


def _queue_priority(
    state: ServicePlanStateV1,
    *,
    operator_priority: int,
    context: RouteCoordinatorContextV1,
) -> tuple[Any, ...]:
    return (
        operator_priority,
        _state_precompile_mismatch(state, context.demand_buckets[state.direction]),
        len(state.service_regimes),
        state.trip_count_vector,
        state.boundaries,
        state.direction,
        service_plan_fingerprint_v1(state),
    )


def search_route_service_plans_v1(
    *,
    context: RouteCoordinatorContextV1,
    seeds: Sequence[ServicePlanStateV1],
    budget: CoordinatorSearchBudgetV1 = DEFAULT_COORDINATOR_SEARCH_BUDGET_V1,
    compiler: Callable[..., Any] = compile_service_plan_frontier_v1,
) -> RouteCoordinatorResultV1:
    stats = CoordinatorSearchStatisticsV1()
    authority_validation = validate_closed_loop_service_protection_authority_v1(
        context.service_protection_authority
    )
    if not authority_validation.passed:
        return RouteCoordinatorResultV1(
            route_id=context.route_id,
            status=INVALID_TRANSLATED_PROTECTION_AUTHORITY,
            search_budget=budget,
            statistics=stats,
            seed_states=tuple(seeds),
            pareto_frontier=(),
            feedback_code_counts={INVALID_TRANSLATED_PROTECTION_AUTHORITY: 1},
            revision_examples={},
            evaluated_state_fingerprints=(),
            protection_violations=(),
            protection_authority_validation=authority_validation,
        )
    queue = _BoundedOpenQueue(budget.max_open_states)
    seen: set[str] = set()
    pair_seen: set[str] = set()
    expanded_fleet_feedback_parents: set[str] = set()
    history_by_state: dict[str, tuple[str, ...]] = {}
    archive: dict[str, list[DirectionalCompilationCandidateV1]] = {
        "outbound": [],
        "inbound": [],
    }
    pareto: tuple[OperatingPairCandidateV1, ...] = ()
    feedback_counts: Counter[str] = Counter()
    revision_examples: dict[str, tuple[str, ...]] = {}
    protection_violations: list[ClosedLoopServiceProtectionViolationV1] = []

    for seed_rank, state in enumerate(seeds):
        fingerprint = service_plan_fingerprint_v1(state)
        priority = _queue_priority(state, operator_priority=0, context=context)
        priority = (priority[0], seed_rank, *priority[1:])
        accepted, pruned, _ = queue.push(state, priority)
        stats.states_generated += 1
        if accepted:
            history_by_state[fingerprint] = (f"Seed {state.seed_id}",)
        else:
            stats.duplicate_states_skipped += int(not pruned)
        stats.states_pruned += int(pruned)

    def enqueue_neighbors(
        parent: ServicePlanStateV1,
        parent_history: tuple[str, ...],
        feedback: Sequence[FeedbackEvidenceV1],
    ) -> None:
        pure_fleet_feedback = bool(feedback) and all(
            item.code == FLEET_LIMIT_EXCEEDED for item in feedback
        )
        if pure_fleet_feedback:
            stats.fleet_feedback_expansion_requests += 1
            parent_fingerprint = service_plan_fingerprint_v1(parent)
            if parent_fingerprint in expanded_fleet_feedback_parents:
                stats.fleet_feedback_expansions_skipped += 1
                return
            # Mark the semantic parent before generation. A child rejected by the
            # bounded queue must not get another admission attempt merely because
            # another exact opposite compilation produces the same fleet feedback.
            expanded_fleet_feedback_parents.add(parent_fingerprint)
            stats.fleet_feedback_expansions_executed += 1
        neighbors = generate_targeted_neighbors_v1(
            parent,
            feedback=feedback,
            planning_grid_seconds=context.planning_grid_seconds,
            floor_headway_minutes=None,
        )
        for neighbor in neighbors:
            stats.states_generated += 1
            child = neighbor.state
            fingerprint = service_plan_fingerprint_v1(child)
            if fingerprint in seen:
                stats.duplicate_states_skipped += 1
                continue
            priority = _queue_priority(
                child,
                operator_priority=neighbor.priority + 1,
                context=context,
            )
            accepted, pruned, removed = queue.push(child, priority)
            if accepted:
                history_by_state[fingerprint] = (
                    *parent_history,
                    f"{neighbor.evidence_code or 'EXPLORATION'} -> {neighbor.move.value}",
                )
                if removed is not None:
                    history_by_state.pop(removed, None)
            else:
                stats.duplicate_states_skipped += int(not pruned)
            stats.states_pruned += int(pruned)

    while queue and stats.states_evaluated < budget.max_service_plan_evaluations:
        popped = queue.pop()
        if popped is None:
            break
        state, _ = popped
        stats.search_iterations += 1
        fingerprint = service_plan_fingerprint_v1(state)
        if fingerprint in seen:
            stats.duplicate_states_skipped += 1
            continue
        seen.add(fingerprint)
        stats.states_evaluated += 1
        history = history_by_state.get(fingerprint, (f"Seed {state.seed_id}",))
        errors = validate_service_plan_state_v1(
            state,
            authoritative_total_trips=seeds[0].total_trips
            if seeds[0].direction == state.direction
            else next(item.total_trips for item in seeds if item.direction == state.direction),
            planning_grid_seconds=context.planning_grid_seconds,
            floor_headway_minutes=None,
        )
        if errors:
            stats.states_pruned += 1
            feedback = tuple(
                FeedbackEvidenceV1(
                    code, state.direction, detail="Hard ServicePlan validation failed"
                )
                for code in errors
            )
            feedback_counts.update(item.code for item in feedback)
            enqueue_neighbors(state, history, feedback)
            continue
        compile_frontier = compiler(
            state,
            endpoint_authority=context.endpoint_authority[state.direction],
            compile_frontier_limit=budget.max_compile_frontier_per_state,
        )
        stats.compile_variants_evaluated += len(compile_frontier.variants)
        if not compile_frontier.variants:
            failure = compile_frontier.failure.failure if compile_frontier.failure else None
            feedback = (
                FeedbackEvidenceV1(
                    CLEAN_BOUNDARY_UNCOMPILABLE,
                    state.direction,
                    boundary_time=(failure.boundary_time if failure else None),
                    detail=(failure.reason if failure else "No clean compilation path."),
                ),
            )
            feedback_counts.update(item.code for item in feedback)
            enqueue_neighbors(state, history, feedback)
            continue
        direction_feedback: list[FeedbackEvidenceV1] = []
        current_records: list[DirectionalCompilationCandidateV1] = []
        for variant in compile_frontier.variants:
            protection = _validate_trusted_closed_loop_service_protection_v1(
                authority=context.service_protection_authority,
                direction=state.direction,
                exact_departures=variant.compilation.exact_departures,
                authority_validation=authority_validation,
            )
            if not protection.passed:
                stats.protected_compile_variants_rejected += 1
                protection_violations.extend(protection.violations)
                feedback = tuple(
                    FeedbackEvidenceV1(
                        code=violation.violated_rule,
                        direction=violation.direction,
                        interval_start=violation.protected_window_start,
                        interval_end=violation.protected_window_end,
                        magnitude=violation.observed_headway_minutes,
                        detail=(
                            "Exact compiled service violates translated operational protection."
                        ),
                        source_protected_regime_id=violation.source_regime_id,
                        violated_rule=violation.violated_rule,
                        observed_trip_count=violation.observed_trip_count,
                        observed_headway_minutes=violation.observed_headway_minutes,
                    )
                    for violation in protection.violations
                )
                feedback_counts.update(item.code for item in feedback)
                direction_feedback.extend(feedback)
                continue
            metrics, feedback = evaluate_actual_service_v1(
                variant,
                demand_buckets=context.demand_buckets[state.direction],
                scenario_b_departures=context.scenario_b_departures[state.direction],
                demand_response_regimes=(
                    None
                    if context.demand_response_regimes is None
                    else context.demand_response_regimes[state.direction]
                ),
            )
            feedback_counts.update(item.code for item in feedback)
            direction_feedback.extend(feedback)
            record = DirectionalCompilationCandidateV1(
                state=state,
                state_fingerprint=fingerprint,
                compile_variant=variant,
                metrics=metrics,
                feedback=feedback,
                history=(
                    *history,
                    (
                        f"clean compile {variant.frontier_rank}: "
                        f"{metrics.actual_service_regime_count} actual regimes, "
                        f"max jump {metrics.max_frequency_jump:.6f}"
                    ),
                ),
            )
            if state.operation is not None:
                revision_examples.setdefault(state.operation, record.history)
                if state.operation_evidence == FLEET_LIMIT_EXCEEDED:
                    revision_examples.setdefault(
                        "FLEET_VALIDATION_UPSTREAM_REVISION", record.history
                    )
                if state.operation_evidence == CLEAN_BOUNDARY_UNCOMPILABLE:
                    revision_examples.setdefault("COMPILATION_UPSTREAM_REVISION", record.history)
            current_records.append(record)
            opposite_direction = "inbound" if state.direction == "outbound" else "outbound"
            for opposite in archive[opposite_direction]:
                outbound = record if state.direction == "outbound" else opposite
                inbound = record if state.direction == "inbound" else opposite
                pair_fingerprint = _pair_fingerprint(outbound, inbound)
                if pair_fingerprint in pair_seen:
                    continue
                pair_seen.add(pair_fingerprint)
                stats.fleet_validations_run += 1
                pair, pair_feedback = evaluate_operating_pair_v1(
                    outbound,
                    inbound,
                    context=context,
                )
                feedback_counts.update(item.code for item in pair_feedback)
                if pair is None:
                    enqueue_neighbors(state, history, pair_feedback)
                    enqueue_neighbors(opposite.state, opposite.history, pair_feedback)
                    continue
                pareto = update_operating_pair_pareto_v1(
                    pareto,
                    pair,
                    limit=budget.max_pair_frontier,
                )
        archive[state.direction] = _retain_directional_archive(
            (*archive[state.direction], *current_records),
            limit=budget.max_directional_compilations,
        )
        enqueue_neighbors(state, history, tuple(direction_feedback))

    stats.budget_exhausted = bool(queue)
    status = SEARCH_BUDGET_EXHAUSTED if stats.budget_exhausted else SEARCH_COMPLETE
    return RouteCoordinatorResultV1(
        route_id=context.route_id,
        status=status,
        search_budget=budget,
        statistics=stats,
        seed_states=tuple(seeds),
        pareto_frontier=pareto,
        feedback_code_counts=dict(sorted(feedback_counts.items())),
        revision_examples=dict(sorted(revision_examples.items())),
        evaluated_state_fingerprints=tuple(sorted(seen)),
        protection_violations=tuple(protection_violations),
        protection_authority_validation=authority_validation,
    )


def _state_from_rows(
    *,
    route_id: str,
    direction: str,
    endpoint: OperationalEndpointAuthorityV1,
    rows: Sequence[Mapping[str, Any]],
    seed_id: str,
    start_key: str = "start_time",
    end_key: str = "end_time",
    count_key: str = "allocated_trip_count",
) -> ServicePlanStateV1:
    return ServicePlanStateV1(
        route_id=route_id,
        direction=direction,
        fixed_first_departure=endpoint.fixed_first_departure,
        fixed_last_departure=endpoint.fixed_last_departure,
        service_regimes=tuple(
            ServiceRegimeDecisionV1(
                int(item[start_key]),
                int(item[end_key]),
                int(item[count_key]),
            )
            for item in rows
        ),
        seed_id=seed_id,
    )


def _sqrt_demand_counts(
    regimes: Sequence[Mapping[str, Any]],
    *,
    total_trips: int,
    endpoint: OperationalEndpointAuthorityV1,
    seed_headway_prior_minutes: float,
) -> tuple[int, ...]:
    shells = tuple(
        ServiceRegimeDecisionV1(int(item["start_time"]), int(item["end_time"]), 2)
        for item in regimes
    )
    minimums: list[int] = []
    weights: list[float] = []
    for shell, evidence in zip(shells, regimes, strict=True):
        effective_start = max(shell.start, endpoint.fixed_first_departure)
        effective_end = min(shell.end, endpoint.fixed_last_departure)
        effective_minutes = max(1, (effective_end - effective_start) // 60)
        minimums.append(max(2, math.ceil(effective_minutes / seed_headway_prior_minutes)))
        intensity = float(evidence["demand_sum"]) / float(evidence["duration_minutes"])
        weights.append(shell.duration_minutes * math.sqrt(max(0.0, intensity)))
    remaining = total_trips - sum(minimums)
    if remaining < 0:
        raise ValueError("sqrt demand seed cannot satisfy its baseline headway priors")
    if remaining == 0:
        return tuple(minimums)
    weight_total = sum(weights)
    quotas = tuple(remaining * weight / weight_total for weight in weights)
    extra = [math.floor(value) for value in quotas]
    leftover = remaining - sum(extra)
    order = sorted(range(len(regimes)), key=lambda index: (-(quotas[index] - extra[index]), index))
    for index in order[:leftover]:
        extra[index] += 1
    return tuple(base + addition for base, addition in zip(minimums, extra, strict=True))


def build_initial_service_plan_seeds_v1(
    *,
    route_id: str,
    allocation_payload: Mapping[str, Any],
    demand_payload: Mapping[str, Any],
    end_tail_route_payload: Mapping[str, Any],
    endpoint_authority: Mapping[str, OperationalEndpointAuthorityV1],
) -> tuple[ServicePlanStateV1, ...]:
    seeds: list[ServicePlanStateV1] = []
    candidate_keys = ("c1_demand_fit", "c2_conservative", "c3_balanced")
    allocation_by_direction = {
        str(item["direction"]): item for item in allocation_payload["candidate_sets"]
    }
    demand_by_direction = {
        str(item["direction"]): item["final_plan"]
        for item in demand_payload["model_selection"]["selections"]
    }
    tail_by_direction = {
        str(item["direction"]): item for item in end_tail_route_payload["directions"]
    }
    for direction in ("outbound", "inbound"):
        candidate_set = allocation_by_direction[direction]
        endpoint = endpoint_authority[direction]
        for key in candidate_keys:
            candidate = candidate_set.get(key)
            if candidate is not None:
                seeds.append(
                    _state_from_rows(
                        route_id=route_id,
                        direction=direction,
                        endpoint=endpoint,
                        rows=candidate["regime_allocations"],
                        seed_id=f"A_V2_{candidate['candidate_id']}",
                    )
                )
        for selected in tail_by_direction[direction]["selected_candidates"]:
            slices = selected["compilation"]["demand_regime_slices"]
            seeds.append(
                _state_from_rows(
                    route_id=route_id,
                    direction=direction,
                    endpoint=endpoint,
                    rows=slices,
                    seed_id=f"B_V3_{selected['candidate_id']}",
                    start_key="demand_regime_start",
                    end_key="demand_regime_end",
                    count_key="authoritative_trip_count",
                )
            )
        demand_regimes = demand_by_direction[direction]["regimes"]
        counts = _sqrt_demand_counts(
            demand_regimes,
            total_trips=int(candidate_set["total_trips"]),
            endpoint=endpoint,
            seed_headway_prior_minutes=float(
                tail_by_direction[direction]["service_floor_headway_minutes"]
            ),
        )
        sqrt_rows = [
            {
                "start_time": item["start_time"],
                "end_time": item["end_time"],
                "allocated_trip_count": count,
            }
            for item, count in zip(demand_regimes, counts, strict=True)
        ]
        seeds.append(
            _state_from_rows(
                route_id=route_id,
                direction=direction,
                endpoint=endpoint,
                rows=sqrt_rows,
                seed_id="C_SQRT_DEMAND_RESPONSE",
            )
        )
        seeds.append(
            _state_from_rows(
                route_id=route_id,
                direction=direction,
                endpoint=endpoint,
                rows=candidate_set["b_reference"]["regime_allocations"],
                seed_id="D_SCENARIO_B_REFERENCE",
            )
        )
    unique: dict[str, ServicePlanStateV1] = {}
    for state in seeds:
        unique.setdefault(service_plan_fingerprint_v1(state), state)
    # Interleave directions so fleet validation begins before one direction can fill the archive.
    ordered = sorted(
        unique.values(),
        key=lambda item: (item.seed_id, 0 if item.direction == "outbound" else 1),
    )
    return tuple(ordered)


def load_canonical_demand_response_regimes_v1(
    *,
    demand_payload: Mapping[str, Any],
    demand_buckets: Mapping[str, Sequence[DemandBucketEvidenceV1]],
    endpoint_authority: Mapping[str, OperationalEndpointAuthorityV1],
) -> dict[str, tuple[DemandResponseRegimeEvidenceV1, ...]]:
    """Load already-selected canonical DemandRegimes without rerunning model selection."""

    try:
        selections = demand_payload["model_selection"]["selections"]
    except (KeyError, TypeError) as exc:
        raise ValueError("canonical DemandRegime selections are missing") from exc
    by_direction: dict[str, Mapping[str, Any]] = {}
    for selection in selections:
        direction = str(selection.get("direction", ""))
        if direction in by_direction:
            raise ValueError(f"duplicate canonical DemandRegime selection for {direction}")
        if direction not in {"outbound", "inbound"}:
            raise ValueError(f"unsupported canonical DemandRegime direction: {direction}")
        if selection.get("selection_status") != "SUCCESS":
            raise ValueError(f"canonical DemandRegime selection failed for {direction}")
        by_direction[direction] = selection
    expected_directions = {"outbound", "inbound"}
    if set(by_direction) != expected_directions:
        raise ValueError("canonical DemandRegime evidence must contain both independent directions")

    result: dict[str, tuple[DemandResponseRegimeEvidenceV1, ...]] = {}
    for direction in sorted(expected_directions):
        endpoint = endpoint_authority[direction]
        buckets = demand_buckets[direction]
        evidence: list[DemandResponseRegimeEvidenceV1] = []
        raw_regimes = by_direction[direction].get("final_plan", {}).get("regimes", ())
        for raw in raw_regimes:
            if str(raw.get("direction")) != direction:
                raise ValueError(f"canonical DemandRegime direction mismatch for {direction}")
            start = max(int(raw["start_time"]), endpoint.fixed_first_departure)
            end = min(int(raw["end_time"]), endpoint.fixed_last_departure)
            if end <= start:
                continue
            mass = sum(
                bucket.observed_demand
                * _overlap(bucket.start, bucket.end, start, end)
                / (bucket.end - bucket.start)
                for bucket in buckets
            )
            evidence.append(
                DemandResponseRegimeEvidenceV1(
                    regime_id=str(raw["regime_id"]),
                    direction=direction,
                    start=start,
                    end=end,
                    integrated_demand_mass=mass,
                    demand_rate_per_hour=mass / ((end - start) / 3600),
                )
            )
        ordered = tuple(sorted(evidence, key=lambda item: (item.start, item.end, item.regime_id)))
        if not ordered:
            raise ValueError(f"no canonical DemandRegime overlaps active {direction} service")
        if len({item.regime_id for item in ordered}) != len(ordered):
            raise ValueError(f"canonical DemandRegime IDs are not unique for {direction}")
        if (
            ordered[0].start != endpoint.fixed_first_departure
            or ordered[-1].end != endpoint.fixed_last_departure
            or any(
                left.end != right.start for left, right in zip(ordered, ordered[1:], strict=False)
            )
        ):
            raise ValueError(
                f"canonical DemandRegime evidence does not cover exact {direction} service span"
            )
        result[direction] = ordered
    return result


def load_route_coordinator_inputs_v1(
    *,
    repo_root: Path,
    route_id: str,
    workbook_path: Path,
) -> tuple[RouteCoordinatorContextV1, tuple[ServicePlanStateV1, ...]]:
    allocation_path = (
        repo_root
        / "outputs"
        / "demand_regime_trip_allocation"
        / f"route_{route_id}_demand_regime_trip_allocations.json"
    )
    demand_path = (
        repo_root
        / "outputs"
        / "demand_regime_model_selection"
        / f"route_{route_id}_demand_regimes.json"
    )
    end_tail_path = (
        repo_root / "outputs" / "end_tail_settlement_v3" / "end_tail_settlement_pilot_report.json"
    )
    allocation = json.loads(allocation_path.read_text(encoding="utf-8"))
    demand = json.loads(demand_path.read_text(encoding="utf-8"))
    end_tail = json.loads(end_tail_path.read_text(encoding="utf-8"))
    end_tail_route = next(item for item in end_tail["routes"] if str(item["route_id"]) == route_id)
    endpoints = {
        str(item["direction"]): OperationalEndpointAuthorityV1(**item["endpoint_authority"])
        for item in end_tail_route["directions"]
    }
    buckets: dict[str, list[DemandBucketEvidenceV1]] = {"outbound": [], "inbound": []}
    for item in demand["raw_v3_reconciliation"]["buckets"]:
        direction = str(item["direction"])
        buckets[direction].append(
            DemandBucketEvidenceV1(
                direction=direction,
                start=int(item["interval_start"]),
                end=int(item["interval_end"]),
                observed_demand=float(item["raw_derived_average"]),
            )
        )
    imported = import_v3_multi_period_workbook_v1(workbook_path).base_workbook
    b_departures = {
        "outbound": tuple(
            sorted(
                item.departure_seconds
                for item in imported.trips_b
                if item.direction == Direction.TERMINAL_1_TO_2
            )
        ),
        "inbound": tuple(
            sorted(
                item.departure_seconds
                for item in imported.trips_b
                if item.direction == Direction.TERMINAL_2_TO_1
            )
        ),
    }
    seed_priors = {
        str(item["direction"]): float(item["service_floor_headway_minutes"])
        for item in end_tail_route["directions"]
    }
    grid_minutes = min(
        int(item["bucket_granularity_minutes"]) for item in demand["model_selection"]["coverage"]
    )
    frozen_buckets = {
        key: tuple(sorted(value, key=lambda item: item.start)) for key, value in buckets.items()
    }
    response_regimes = load_canonical_demand_response_regimes_v1(
        demand_payload=demand,
        demand_buckets=frozen_buckets,
        endpoint_authority=endpoints,
    )
    context = RouteCoordinatorContextV1(
        route_id=route_id,
        route_name=str(allocation["route_name"]),
        endpoint_authority=endpoints,
        demand_buckets=frozen_buckets,
        scenario_b_departures=b_departures,
        seed_headway_prior_minutes=seed_priors,
        planning_grid_seconds=grid_minutes * 60,
        runtime_minutes=int(end_tail_route["runtime_minutes"]),
        minimum_layover_minutes=int(end_tail_route["minimum_layover_minutes"]),
        fleet_ceiling=int(end_tail_route["fleet_ceiling"]),
        immutable_demand_sha256=_sha256(demand_path),
        demand_response_regimes=response_regimes,
    )
    seeds = build_initial_service_plan_seeds_v1(
        route_id=route_id,
        allocation_payload=allocation,
        demand_payload=demand,
        end_tail_route_payload=end_tail_route,
        endpoint_authority=endpoints,
    )
    totals = {
        direction: {item.total_trips for item in seeds if item.direction == direction}
        for direction in ("outbound", "inbound")
    }
    if any(len(values) != 1 for values in totals.values()):
        raise ValueError(f"seed totals do not preserve authoritative direction totals: {totals}")
    return context, seeds


def _state_to_dict(state: ServicePlanStateV1) -> dict[str, Any]:
    return {
        **service_plan_fingerprint_payload_v1(state),
        "fingerprint": service_plan_fingerprint_v1(state),
        "seed_id": state.seed_id,
        "parent_fingerprint": state.parent_fingerprint,
        "operation": state.operation,
        "operation_evidence": state.operation_evidence,
        "service_regimes": [asdict(item) for item in state.service_regimes],
        "total_trips": state.total_trips,
    }


def _directional_to_dict(item: DirectionalCompilationCandidateV1) -> dict[str, Any]:
    compilation = item.compile_variant.compilation
    return {
        "state": _state_to_dict(item.state),
        "compile_variant": {
            "compilation_fingerprint": item.compile_variant.compilation_fingerprint,
            "frontier_rank": item.compile_variant.frontier_rank,
            "headway_quantization": item.compile_variant.headway_quantization,
            "phase_edge_quality_minutes": item.compile_variant.phase_edge_quality_minutes,
            "fixed_first_departure": compilation.exact_departures[0],
            "fixed_last_departure": compilation.exact_departures[-1],
            "exact_departures": list(compilation.exact_departures),
            "actual_service_regimes": [asdict(service) for service in compilation.service_regimes],
        },
        "actual_service_metrics": asdict(item.metrics),
        "feedback": [asdict(value) for value in item.feedback],
        "history": list(item.history),
    }


def _pair_to_dict(index: int, item: OperatingPairCandidateV1) -> dict[str, Any]:
    return {
        "plan": f"P{index:02d}",
        "pair_fingerprint": item.pair_fingerprint,
        "metrics": asdict(item.metrics),
        "fleet_ceiling": item.fleet_ceiling,
        "minimum_connection_layover_minutes": item.minimum_connection_layover_minutes,
        "outbound": _directional_to_dict(item.outbound),
        "inbound": _directional_to_dict(item.inbound),
        "history": list(item.history),
    }


def _regime_summary(item: DirectionalCompilationCandidateV1) -> str:
    return "; ".join(
        f"{format_hhmm(service.first_departure)}–{format_hhmm(service.last_departure)} "
        f"@{service.uniform_headway_minutes} ({service.trip_count})"
        for service in item.compile_variant.compilation.service_regimes
    )


def _result_markdown(payload: Mapping[str, Any]) -> str:
    stats = payload["search_statistics"]
    lines = [
        f"# Route {payload['route_id']} — Closed-Loop ServicePlan Coordinator V1",
        "",
        f"Status: **{payload['status']}**. This is review-only; no timetable is promoted.",
        "",
        "## Search audit",
        "",
        "| Generated | Evaluated | Duplicate | Pruned | Compile variants | Fleet validations | Iterations | Budget exhausted |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
        (
            f"| {stats['states_generated']} | {stats['states_evaluated']} | "
            f"{stats['duplicate_states_skipped']} | {stats['states_pruned']} | "
            f"{stats['compile_variants_evaluated']} | {stats['fleet_validations_run']} | "
            f"{stats['search_iterations']} | {str(stats['budget_exhausted']).lower()} |"
        ),
        "",
        "## Nondominated operating pairs",
        "",
        "| Plan | Out service regimes | In service regimes | Demand mismatch | Expected wait | Max frequency jump | Total variation | Moved trips | Fleet | Terminal wait |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["pareto_frontier"]:
        metrics = item["metrics"]
        lines.append(
            f"| {item['plan']} | {item['outbound']['actual_service_metrics']['actual_service_regime_count']} "
            f"| {item['inbound']['actual_service_metrics']['actual_service_regime_count']} "
            f"| {metrics['observed_demand_mismatch']:.8f} "
            f"| {metrics['demand_weighted_expected_passenger_wait_minutes']:.6f} "
            f"| {metrics['max_frequency_jump']:.6f} "
            f"| {metrics['total_frequency_variation']:.6f} "
            f"| {metrics['moved_trips_vs_b']} | {metrics['fleet_required']} "
            f"| {metrics['total_excess_terminal_wait']} |"
        )
    lines.extend(["", "## Operating detail", ""])
    for item in payload["pareto_frontier"]:
        lines.extend(
            [
                f"### {item['plan']}",
                "",
                f"- Out: `{item['outbound']['regime_summary']}`",
                f"- In: `{item['inbound']['regime_summary']}`",
                (
                    f"- Fixed endpoints out/in: "
                    f"{format_hhmm(item['outbound']['compile_variant']['fixed_first_departure'])}–"
                    f"{format_hhmm(item['outbound']['compile_variant']['fixed_last_departure'])} / "
                    f"{format_hhmm(item['inbound']['compile_variant']['fixed_first_departure'])}–"
                    f"{format_hhmm(item['inbound']['compile_variant']['fixed_last_departure'])}"
                ),
                (
                    f"- Tail out/in: @{item['outbound']['actual_service_metrics']['tail_headway_minutes']} "
                    f"({item['outbound']['actual_service_metrics']['tail_trip_count']} trips) / "
                    f"@{item['inbound']['actual_service_metrics']['tail_headway_minutes']} "
                    f"({item['inbound']['actual_service_metrics']['tail_trip_count']} trips)"
                ),
                (
                    "- Largest shock boundary out/in: "
                    f"{format_hhmm(item['outbound']['actual_service_metrics']['largest_service_shock_boundary']) if item['outbound']['actual_service_metrics']['largest_service_shock_boundary'] is not None else 'none'} / "
                    f"{format_hhmm(item['inbound']['actual_service_metrics']['largest_service_shock_boundary']) if item['inbound']['actual_service_metrics']['largest_service_shock_boundary'] is not None else 'none'}"
                ),
                "",
            ]
        )
    lines.extend(["## Search evolution evidence", ""])
    for move, history in payload["revision_examples"].items():
        lines.append(f"- **{move}**: " + " → ".join(history))
    lines.extend(["", "## ServiceRegime revision examples", ""])
    for code, evidence in payload["service_regime_revision_examples"].items():
        lines.append(
            f"- **{code}**: "
            + json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(", ", ": "))
        )
    lines.extend(
        [
            "",
            "## Authority and safeguards",
            "",
            "Demand evidence and Scenario B are read-only. The baseline headway is a seed prior, not global hard authority. Evidence-bound translated windows are checked on exact timestamps before fleet pairing. Every state is fingerprint-cached; all moves are finite; pre-fleet archives use deterministic phase-diversity caps, while only the final operating-pair frontier uses dominance. Technical budgets stop the search deterministically. Every retained clean compilation is fleet-validated before final Pareto pruning.",
            "",
        ]
    )
    return "\n".join(lines)


def route_result_payload_v1(
    *,
    context: RouteCoordinatorContextV1,
    result: RouteCoordinatorResultV1,
    prior_artifact_verification: Mapping[str, Any],
) -> dict[str, Any]:
    protection_authority = context.service_protection_authority
    protection_authority_has_expected_type = isinstance(
        protection_authority, ClosedLoopServiceProtectionAuthorityV1
    )
    frontier = []
    for index, item in enumerate(result.pareto_frontier, start=1):
        value = _pair_to_dict(index, item)
        value["outbound"]["regime_summary"] = _regime_summary(item.outbound)
        value["inbound"]["regime_summary"] = _regime_summary(item.inbound)
        frontier.append(value)
    prior_seeds = {"A_V2": False, "B_V3": False, "D_SCENARIO_B": False}
    for item in result.pareto_frontier:
        for direction in (item.outbound, item.inbound):
            if direction.state.operation is None:
                for prefix in prior_seeds:
                    prior_seeds[prefix] |= direction.state.seed_id.startswith(prefix)
    service_regime_revisions: dict[str, Any] = {}
    for item in frontier:
        for direction in ("outbound", "inbound"):
            value = item[direction]
            planned_count = len(value["state"]["service_regimes"])
            actual_count = value["actual_service_metrics"]["actual_service_regime_count"]
            operation = value["state"]["operation"]
            if (
                actual_count < planned_count
                and "MERGED_AFTER_COMPILATION" not in service_regime_revisions
            ):
                service_regime_revisions["MERGED_AFTER_COMPILATION"] = {
                    "plan": item["plan"],
                    "direction": direction,
                    "planned_regime_count": planned_count,
                    "actual_regime_count": actual_count,
                    "reason": "equal continuous compiled rhythm merged operationally",
                }
            if operation == ServicePlanMoveV1.SPLIT_REGIME.value:
                service_regime_revisions.setdefault(
                    "ADDED_BY_SPLIT",
                    {"plan": item["plan"], "direction": direction, "history": value["history"]},
                )
            if operation in {
                ServicePlanMoveV1.SHIFT_BOUNDARY_LEFT.value,
                ServicePlanMoveV1.SHIFT_BOUNDARY_RIGHT.value,
            }:
                service_regime_revisions.setdefault(
                    "SHIFTED_BOUNDARY",
                    {"plan": item["plan"], "direction": direction, "history": value["history"]},
                )
            if value["state"]["operation_evidence"] == FLEET_LIMIT_EXCEEDED:
                service_regime_revisions.setdefault(
                    "FLEET_FEEDBACK_UPSTREAM_REVISION",
                    {"plan": item["plan"], "direction": direction, "history": value["history"]},
                )
    return {
        "review_profile": SERVICE_PLAN_COORDINATOR_PROFILE_V1,
        "authority_status": "REVIEW_ONLY_NO_TIMETABLE_PROMOTION",
        "route_id": context.route_id,
        "route_name": context.route_name,
        "status": result.status,
        "immutable_demand_sha256": context.immutable_demand_sha256,
        "canonical_demand_response_regimes": (
            None
            if context.demand_response_regimes is None
            else {
                direction: [asdict(item) for item in context.demand_response_regimes[direction]]
                for direction in sorted(context.demand_response_regimes)
            }
        ),
        "seed_headway_prior_minutes": dict(sorted(context.seed_headway_prior_minutes.items())),
        "protected_service_authority": {
            "status": result.protection_authority_validation.status,
            "validation_errors": list(result.protection_authority_validation.errors),
            "validation_fingerprint": (
                result.protection_authority_validation.validation_fingerprint
            ),
            "authority_supplied": protection_authority is not None,
            "source_authority_profile": (
                None
                if not protection_authority_has_expected_type
                else protection_authority.source_authority_profile
            ),
            "source_authority_fingerprint": (
                None
                if not protection_authority_has_expected_type
                else protection_authority.source_authority_fingerprint
            ),
            "translation_profile": (
                None
                if not protection_authority_has_expected_type
                else protection_authority.translation_profile
            ),
            "translation_fingerprint": (
                None
                if not protection_authority_has_expected_type
                else protection_authority.translation_fingerprint
            ),
            "semantics": (
                None
                if not protection_authority_has_expected_type
                else protection_authority.semantics
            ),
            "windows": (
                []
                if (
                    not protection_authority_has_expected_type
                    or not result.protection_authority_validation.passed
                )
                else [asdict(window) for window in protection_authority.windows]
            ),
            "violations": [asdict(item) for item in result.protection_violations],
        },
        "state_schema": {
            "frozen": True,
            "identity": [
                "route_id",
                "direction",
                "fixed_first_departure",
                "fixed_last_departure",
                "service boundaries",
                "integer trip-count vector",
            ],
        },
        "state_fingerprint": (
            "sha256(canonical JSON of profile, route_id, direction, fixed endpoints, "
            "full service-boundary vector, trip-count vector)"
        ),
        "seed_generation": [
            "A: clean-boundary V2 C1/C2/C3",
            "B: tail-aware V3 C1/C2/C3",
            "C: duration * sqrt(observed demand intensity), seed-prior largest remainder",
            "D: exact Scenario B regime/count reference",
        ],
        "neighborhood_operators": [item.value for item in ServicePlanMoveV1],
        "compile_frontier": {
            "profile": "clean_compile_frontier_v1",
            "objectives": [
                "headway_quantization",
                "actual_service_regime_count",
                "phase_edge_quality_minutes",
            ],
            "ordering_after_dominance": (
                "not applicable pre-fleet; bounded order is compiler witness, local-quality "
                "anchor, state/headway-shape diversity, exact-wait and sqrt-response anchors, "
                "exact-departure max-min distance"
            ),
            "pre_fleet_dominance_authority": False,
            "fleet_every_retained_variant": True,
        },
        "actual_service_formulas": {
            "observed_demand_mismatch": (
                "sum((compiled_departure_share_30m - immutable_demand_share_30m)^2)"
            ),
            "frequency_jump": "abs(log((60/h_right)/(60/h_left)))",
            "total_variation": "sum(frequency_jump)",
            "moved_trips_vs_B": ("sum(abs(compiled_30m_count - exact_B_30m_count))/2"),
            "demand_weighted_expected_passenger_wait_minutes": (
                "exact integral of next-departure wait under "
                f"{UNIFORM_WITHIN_DEMAND_BUCKET_ASSUMPTION}"
            ),
            "demand_response_projection": (
                "overlap-weighted integral of exact interdeparture frequency on immutable "
                "canonical DemandRegimes"
            ),
            "terminal_wait": "sum/max(connection_layover - authoritative_minimum_layover)",
        },
        "pareto_dimensions": [
            "observed_demand_mismatch",
            "demand_weighted_expected_passenger_wait_minutes",
            "actual_service_regime_count",
            "max_frequency_jump",
            "total_frequency_variation",
            "moved_trips_vs_b",
            "fleet_required",
            "total_excess_terminal_wait",
        ],
        "structured_feedback_codes": [
            REDUNDANT_SERVICE_BOUNDARY,
            CLEAN_BOUNDARY_UNCOMPILABLE,
            FLEET_LIMIT_EXCEEDED,
            LARGEST_SERVICE_FREQUENCY_JUMP,
            TAIL_OVER_SERVICE,
            TAIL_UNDER_SERVICE,
            DEMAND_UNDERSERVED_INTERVAL,
            DEMAND_OVERSERVED_INTERVAL,
            DEMAND_RESPONSE_DIRECTION_MISMATCH,
            FIXED_ENDPOINT_CONFLICT,
        ],
        "targeted_neighbor_logic": {
            REDUNDANT_SERVICE_BOUNDARY: ["MERGE_ADJACENT"],
            CLEAN_BOUNDARY_UNCOMPILABLE: [
                "SHIFT_BOUNDARY_LEFT",
                "SHIFT_BOUNDARY_RIGHT",
                "MOVE_ONE_TRIP_LEFT_TO_RIGHT",
                "MOVE_ONE_TRIP_RIGHT_TO_LEFT",
                "MERGE_ADJACENT",
            ],
            LARGEST_SERVICE_FREQUENCY_JUMP: [
                "SPLIT_REGIME",
                "SHIFT_BOUNDARY_LEFT",
                "SHIFT_BOUNDARY_RIGHT",
                "MOVE_ONE_TRIP_LEFT_TO_RIGHT",
                "MOVE_ONE_TRIP_RIGHT_TO_LEFT",
            ],
            FLEET_LIMIT_EXCEEDED: [
                "SHIFT_BOUNDARY_LEFT",
                "SHIFT_BOUNDARY_RIGHT",
                "MOVE_ONE_TRIP_LEFT_TO_RIGHT",
                "MOVE_ONE_TRIP_RIGHT_TO_LEFT",
            ],
            TAIL_OVER_SERVICE: ["TAIL_RELEASE_ONE"],
            TAIL_UNDER_SERVICE: ["TAIL_ABSORB_ONE"],
            DEMAND_UNDERSERVED_INTERVAL: [
                "localized split, shift, and one-trip moves around the diagnosed interval"
            ],
            DEMAND_OVERSERVED_INTERVAL: [
                "localized split, shift, and one-trip moves around the diagnosed interval"
            ],
            DEMAND_RESPONSE_DIRECTION_MISMATCH: [
                "localized split, shift, and one-trip moves around the canonical boundary"
            ],
        },
        "queue_ordering": (
            "feedback/operator priority, estimated immutable-bucket mismatch, regime count, "
            "trip vector, boundaries, direction, fingerprint"
        ),
        "search_budget": asdict(result.search_budget),
        "search_statistics": asdict(result.statistics),
        "anti_loop_guarantees": [
            "SHA-256 state fingerprint cache",
            "finite explicit neighborhood",
            "exact-timetable deduplication and deterministic pre-fleet diversity caps",
            "final operating-pair dominance pruning after exact fleet validation",
            "bounded state, OPEN, compile, directional, and pair frontiers",
        ],
        "seed_states": [_state_to_dict(item) for item in result.seed_states],
        "feedback_code_counts": dict(result.feedback_code_counts),
        "revision_examples": {key: list(value) for key, value in result.revision_examples.items()},
        "service_regime_revision_examples": service_regime_revisions,
        "pareto_frontier": frontier,
        "prior_candidate_on_final_pareto": prior_seeds,
        "prior_artifact_fingerprint_verification": dict(prior_artifact_verification),
    }


def run_service_plan_coordinator_pilot_v1(
    *,
    repo_root: Path,
    route_workbooks: Mapping[str, Path],
    output_directory: Path,
    budget: CoordinatorSearchBudgetV1 = DEFAULT_COORDINATOR_SEARCH_BUDGET_V1,
) -> dict[str, Any]:
    prior_before = verify_frozen_prior_artifacts_v1(repo_root)
    route_payloads: list[dict[str, Any]] = []
    output_directory.mkdir(parents=True, exist_ok=True)
    for route_id in sorted(route_workbooks, key=int):
        context, seeds = load_route_coordinator_inputs_v1(
            repo_root=repo_root,
            route_id=route_id,
            workbook_path=route_workbooks[route_id],
        )
        result = search_route_service_plans_v1(context=context, seeds=seeds, budget=budget)
        prior_after = verify_frozen_prior_artifacts_v1(repo_root)
        verification = {
            "unchanged": prior_before == prior_after,
            "before": prior_before["sha256"],
            "after": prior_after["sha256"],
        }
        payload = route_result_payload_v1(
            context=context,
            result=result,
            prior_artifact_verification=verification,
        )
        route_payloads.append(payload)
        base = output_directory / f"route_{route_id}_coordinator_report"
        base.with_suffix(".json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        base.with_suffix(".md").write_text(_result_markdown(payload), encoding="utf-8")
    return {
        "review_profile": SERVICE_PLAN_COORDINATOR_PROFILE_V1,
        "routes": route_payloads,
        "prior_artifacts_unchanged": prior_before == verify_frozen_prior_artifacts_v1(repo_root),
    }


__all__ = [
    "CLEAN_BOUNDARY_UNCOMPILABLE",
    "CoordinatorSearchBudgetV1",
    "CoordinatorSearchStatisticsV1",
    "DEMAND_OVERSERVED_INTERVAL",
    "DEMAND_RESPONSE_DIRECTION_MISMATCH",
    "DEMAND_UNDERSERVED_INTERVAL",
    "DEFAULT_COORDINATOR_SEARCH_BUDGET_V1",
    "DemandBucketEvidenceV1",
    "DemandResponseRegimeEvidenceV1",
    "DemandResponseRegimeProjectionV1",
    "DemandResponseTransitionV1",
    "FLEET_LIMIT_EXCEEDED",
    "FeedbackEvidenceV1",
    "LARGEST_SERVICE_FREQUENCY_JUMP",
    "OperatingPairCandidateV1",
    "OperatingPairMetricsV1",
    "REDUNDANT_SERVICE_BOUNDARY",
    "RouteCoordinatorContextV1",
    "RouteCoordinatorResultV1",
    "SEARCH_BUDGET_EXHAUSTED",
    "SEARCH_COMPLETE",
    "SERVICE_PLAN_COORDINATOR_PROFILE_V1",
    "TAIL_OVER_SERVICE",
    "TAIL_UNDER_SERVICE",
    "build_initial_service_plan_seeds_v1",
    "demand_response_diagnostics_v1",
    "dominates_operating_pair_v1",
    "evaluate_actual_service_v1",
    "evaluate_operating_pair_v1",
    "expected_passenger_wait_metrics_v1",
    "generate_targeted_neighbors_v1",
    "load_canonical_demand_response_regimes_v1",
    "load_route_coordinator_inputs_v1",
    "route_result_payload_v1",
    "run_service_plan_coordinator_pilot_v1",
    "search_route_service_plans_v1",
    "update_operating_pair_pareto_v1",
    "verify_frozen_prior_artifacts_v1",
]
