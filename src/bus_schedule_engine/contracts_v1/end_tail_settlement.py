"""Tail-aware integer allocation and backward-anchored end-tail compilation.

This is a side-by-side pilot path.  DemandRegime boundaries and observed-demand
shares remain upstream evidence; only operational spans are clipped to the fixed
first/last departure authorities for service calculations.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Any

from .clean_boundary_compiler import (
    BoundaryGapDiagnosticV1,
    BoundaryOwnershipV1,
    CleanBoundaryCompilationStatusV1,
    CleanBoundaryCompilationV1,
    CompiledDemandRegimeSliceV1,
    CompiledServiceRegimeV1,
    DemandRegimeAllocationV1,
    OperationalEndpointAuthorityV1,
    validate_clean_boundary_compilation_v1,
)

TAIL_AWARE_ALLOCATOR_PROFILE_V2 = "tail_aware_trip_allocator_v2"
END_TAIL_SETTLEMENT_COMPILER_PROFILE_V2 = "end_tail_settlement_compiler_v2"
TAIL_SETTLEMENT_NOT_ELIGIBLE = "TAIL_SETTLEMENT_NOT_ELIGIBLE"
TAIL_DEBT_CAPACITY_EXCEEDED = "TAIL_DEBT_CAPACITY_EXCEEDED"
TAIL_SERVICE_ENVELOPE_INFEASIBLE = "TAIL_SERVICE_ENVELOPE_INFEASIBLE"
END_TAIL_SETTLEMENT_UNCOMPILABLE = "END_TAIL_SETTLEMENT_UNCOMPILABLE"


class TailEligibilityStatusV2(StrEnum):
    ELIGIBLE = "TAIL_SETTLEMENT_ELIGIBLE"
    NOT_ELIGIBLE = TAIL_SETTLEMENT_NOT_ELIGIBLE


class TailAwareAllocationStatusV2(StrEnum):
    SUCCESS = "SUCCESS"
    NOT_ELIGIBLE = TAIL_SETTLEMENT_NOT_ELIGIBLE
    INFEASIBLE = "TAIL_AWARE_ALLOCATION_INFEASIBLE"


@dataclass(frozen=True, slots=True)
class EffectiveServiceSpanV1:
    regime_id: str
    demand_start: int
    demand_end: int
    effective_start: int
    effective_end: int

    def __post_init__(self) -> None:
        if self.demand_start >= self.demand_end:
            raise ValueError("demand span must be positive")
        if not (self.demand_start <= self.effective_start < self.effective_end <= self.demand_end):
            raise ValueError("effective service span must be a positive subset of demand span")
        if any(
            value % 60
            for value in (
                self.demand_start,
                self.demand_end,
                self.effective_start,
                self.effective_end,
            )
        ):
            raise ValueError("effective service span boundaries must be whole-minute values")

    @property
    def effective_duration_minutes(self) -> int:
        return (self.effective_end - self.effective_start) // 60

    @property
    def demand_duration_minutes(self) -> int:
        return (self.demand_end - self.demand_start) // 60


@dataclass(frozen=True, slots=True)
class TailAwareDemandRegimeV2:
    regime_id: str
    start_time: int
    end_time: int
    demand_share: float
    b_trip_count: int

    def __post_init__(self) -> None:
        if self.start_time >= self.end_time:
            raise ValueError(f"{self.regime_id} must have a positive demand span")
        if self.start_time % 60 or self.end_time % 60:
            raise ValueError(f"{self.regime_id} boundaries must be whole-minute values")
        if not math.isfinite(self.demand_share) or self.demand_share < 0:
            raise ValueError("demand_share must be finite and non-negative")
        if self.b_trip_count < 1:
            raise ValueError("b_trip_count must be positive")


@dataclass(frozen=True, slots=True)
class TailEligibilityEvidenceV2:
    status: TailEligibilityStatusV2
    final_regime_id: str
    final_demand_share: float
    final_duration_share: float
    final_demand_density_index: float
    previous_regime_id: str
    previous_demand_density_index: float
    tail_zone_start: int
    tail_zone_end: int
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CoreRegimeAllocationEvidenceV2:
    regime_id: str
    demand_start: int
    demand_end: int
    effective_start: int
    effective_end: int
    effective_duration_minutes: int
    demand_share: float
    b_trip_count: int
    allocated_trip_count: int
    ideal_trip_count: float
    minimum_trip_count: int
    maximum_trip_count: int
    nominal_operational_headway: float
    best_integer_headway_proxy: int
    headway_quantization_error: float


@dataclass(frozen=True, slots=True)
class TailAwareAllocationCandidateV2:
    candidate_record_id: str
    core_trip_counts: tuple[int, ...]
    core_trip_total: int
    residual_tail_trip_count: int
    core_demand_mismatch: float
    full_day_demand_mismatch_after_tail: float
    moved_trips_vs_b: int
    compile_quality_proxy: float
    core_regime_evidence: tuple[CoreRegimeAllocationEvidenceV2, ...]


@dataclass(frozen=True, slots=True)
class TailAwareAllocationFrontierV2:
    allocator_profile: str
    status: TailAwareAllocationStatusV2
    total_trips: int
    service_floor_headway_minutes: float | None
    service_floor_provenance: str
    effective_spans: tuple[EffectiveServiceSpanV1, ...]
    eligibility: TailEligibilityEvidenceV2
    tail_ideal_trip_count: float
    b_full_day_demand_mismatch: float
    candidates: tuple[TailAwareAllocationCandidateV2, ...]
    generated_record_count: int
    bounded_frontier_limit: int
    failure_code: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class TailSettlementEvidenceV2:
    final_demand_regime_id: str
    final_demand_density_index: float
    tail_eligibility: str
    tail_zone_start: int
    tail_zone_end: int
    fixed_last_departure: int
    previous_core_headway: int
    tail_trip_count: int
    tail_ideal_trip_count: float
    tail_trip_debt: float
    tail_headway: int
    tail_start: int
    tail_last_departure: int
    feasible_tail_trip_counts: tuple[int, ...]
    min_feasible_tail_trip_count: int
    max_feasible_tail_trip_count: int
    clean_boundary_gap_minutes: int
    clean_boundary_ownership: str
    low_demand_monotonicity_satisfied: bool
    service_floor_satisfied: bool


@dataclass(frozen=True, slots=True)
class EndTailSettlementFailureV2:
    code: str
    reason: str
    core_trip_counts: tuple[int, ...]
    residual_tail_trip_count: int
    feasible_tail_trip_counts: tuple[int, ...]
    min_feasible_tail_trip_count: int | None
    max_feasible_tail_trip_count: int | None


@dataclass(frozen=True, slots=True)
class EndTailSettlementPlanV2:
    allocation: TailAwareAllocationCandidateV2
    compilation: CleanBoundaryCompilationV1 | None
    tail_evidence: TailSettlementEvidenceV2 | None
    failure: EndTailSettlementFailureV2 | None

    @property
    def compiled(self) -> bool:
        return self.compilation is not None and self.failure is None


@dataclass(frozen=True, slots=True)
class TailAwareSelectedCandidateV2:
    candidate_id: str
    semantic_status: str
    plan: EndTailSettlementPlanV2


@dataclass(frozen=True, slots=True)
class TailAwareCandidateSetV2:
    allocator_profile: str
    compiler_profile: str
    eligibility: TailEligibilityEvidenceV2
    frontier: TailAwareAllocationFrontierV2
    c1_demand_fit: TailAwareSelectedCandidateV2 | None
    c2_conservative: TailAwareSelectedCandidateV2 | None
    c3_balanced: TailAwareSelectedCandidateV2 | None
    feasible_compiled_candidate_count: int
    infeasible_candidate_count: int
    pareto_frontier_size: int
    failure_code_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class TailAwareAllocatorConfigV2:
    frontier_limit: int = 128
    improvement_epsilon: float = 1e-12
    minimum_headway_minutes: int | None = None

    def __post_init__(self) -> None:
        if self.frontier_limit < 3:
            raise ValueError("frontier_limit must be at least three")
        if not math.isfinite(self.improvement_epsilon) or self.improvement_epsilon < 0:
            raise ValueError("improvement_epsilon must be finite and non-negative")
        if self.minimum_headway_minutes is not None and self.minimum_headway_minutes < 1:
            raise ValueError("minimum_headway_minutes must be positive when supplied")


DEFAULT_TAIL_AWARE_ALLOCATOR_CONFIG_V2 = TailAwareAllocatorConfigV2()


@dataclass(frozen=True, slots=True)
class _CoreInput:
    regime: TailAwareDemandRegimeV2
    span: EffectiveServiceSpanV1
    demand_share: Fraction
    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class _CoreRecord:
    vector: tuple[int, ...]
    used: int
    core_mismatch: Fraction
    core_l1: int
    compile_quality: Fraction


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


def _fraction(value: float) -> Fraction:
    return Fraction(Decimal(str(value)))


def _ceil(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _minutes(seconds: int, *, field: str) -> int:
    if seconds % 60:
        raise ValueError(f"{field} must be a whole-minute value")
    return seconds // 60


def _seconds(minutes: int) -> int:
    return minutes * 60


def tail_aware_regime_from_mapping_v2(value: Mapping[str, Any]) -> TailAwareDemandRegimeV2:
    return TailAwareDemandRegimeV2(
        regime_id=str(value["regime_id"]),
        start_time=int(value["start_time"]),
        end_time=int(value["end_time"]),
        demand_share=float(value["demand_share"]),
        b_trip_count=int(value["b_trip_count"]),
    )


def effective_service_spans_v1(
    regimes: Sequence[TailAwareDemandRegimeV2],
    endpoint_authority: OperationalEndpointAuthorityV1,
) -> tuple[EffectiveServiceSpanV1, ...]:
    if len(regimes) < 2:
        raise ValueError("tail settlement requires at least one core and one final regime")
    ordered = tuple(regimes)
    if ordered[0].start_time != endpoint_authority.analysis_window_start:
        raise ValueError("first DemandRegime must start at the analysis window")
    if ordered[-1].end_time != endpoint_authority.analysis_window_end:
        raise ValueError("final DemandRegime must end at the analysis window")
    for left, right in zip(ordered, ordered[1:], strict=False):
        if left.end_time != right.start_time:
            raise ValueError("DemandRegimes must be contiguous and ordered")
    spans = tuple(
        EffectiveServiceSpanV1(
            regime_id=item.regime_id,
            demand_start=item.start_time,
            demand_end=item.end_time,
            effective_start=max(item.start_time, endpoint_authority.fixed_first_departure),
            effective_end=min(item.end_time, endpoint_authority.fixed_last_departure),
        )
        for item in ordered
    )
    return spans


def evaluate_tail_eligibility_v2(
    regimes: Sequence[TailAwareDemandRegimeV2],
    endpoint_authority: OperationalEndpointAuthorityV1,
) -> TailEligibilityEvidenceV2:
    if len(regimes) < 2:
        raise ValueError("tail eligibility requires a previous and final DemandRegime")
    total_duration = (regimes[-1].end_time - regimes[0].start_time) // 60
    if total_duration <= 0:
        raise ValueError("demand analysis duration must be positive")
    previous = regimes[-2]
    final = regimes[-1]
    previous_duration_share = Fraction(
        (previous.end_time - previous.start_time) // 60,
        total_duration,
    )
    final_duration_share = Fraction(
        (final.end_time - final.start_time) // 60,
        total_duration,
    )
    previous_density = _fraction(previous.demand_share) / previous_duration_share
    final_density = _fraction(final.demand_share) / final_duration_share
    eligible = final_density < 1 and final_density <= previous_density
    return TailEligibilityEvidenceV2(
        status=(
            TailEligibilityStatusV2.ELIGIBLE if eligible else TailEligibilityStatusV2.NOT_ELIGIBLE
        ),
        final_regime_id=final.regime_id,
        final_demand_share=final.demand_share,
        final_duration_share=float(final_duration_share),
        final_demand_density_index=float(final_density),
        previous_regime_id=previous.regime_id,
        previous_demand_density_index=float(previous_density),
        tail_zone_start=final.start_time,
        tail_zone_end=endpoint_authority.fixed_last_departure,
        reason=(
            None
            if eligible
            else (
                "The final demand-density index must be below 1.0 and no greater "
                "than the preceding DemandRegime density."
            )
        ),
    )


def _integer_headway_proxy(duration: int, count: int, minimum_headway: int) -> tuple[int, Fraction]:
    if count < 2:
        raise ValueError("core allocation requires at least two trips per regime")
    maximum = (duration - 1) // (count - 1)
    if minimum_headway > maximum:
        raise ValueError("core count has no whole-minute internal headway")
    nominal = Fraction(duration, count)
    lower = max(minimum_headway, min(maximum, nominal.numerator // nominal.denominator))
    upper = max(minimum_headway, min(maximum, _ceil(nominal)))
    headway = min((lower, upper), key=lambda value: (abs(Fraction(value) - nominal), value))
    return headway, Fraction(abs(duration - count * headway), duration)


def _prepare_core_inputs(
    regimes: Sequence[TailAwareDemandRegimeV2],
    spans: Sequence[EffectiveServiceSpanV1],
    total_trips: int,
    minimum_headway: int,
) -> tuple[tuple[_CoreInput, ...], Fraction]:
    floor_headway = max(
        Fraction(span.effective_duration_minutes, regime.b_trip_count)
        for regime, span in zip(regimes, spans, strict=True)
    )
    core_inputs: list[_CoreInput] = []
    for regime, span in zip(regimes[:-1], spans[:-1], strict=True):
        duration = span.effective_duration_minutes
        minimum = max(2, _ceil(Fraction(duration, 1) / floor_headway))
        maximum = min(total_trips - 1, ((duration - 1) // minimum_headway) + 1)
        if minimum > maximum:
            raise ValueError("effective-span service floor exceeds compile capacity")
        core_inputs.append(
            _CoreInput(
                regime=regime,
                span=span,
                demand_share=_fraction(regime.demand_share),
                minimum=minimum,
                maximum=maximum,
            )
        )
    return tuple(core_inputs), floor_headway


def _generate_core_records(
    inputs: Sequence[_CoreInput],
    *,
    total_trips: int,
    minimum_headway: int,
) -> tuple[tuple[_CoreRecord, ...], int]:
    states: dict[tuple[int, int], _CoreRecord] = {
        (0, 0): _CoreRecord((), 0, Fraction(0), 0, Fraction(0))
    }
    visited = 1
    remaining_minimum = [0] * (len(inputs) + 1)
    for index in range(len(inputs) - 1, -1, -1):
        remaining_minimum[index] = remaining_minimum[index + 1] + inputs[index].minimum
    for index, item in enumerate(inputs):
        next_states: dict[tuple[int, int], _CoreRecord] = {}
        for (_, _), record in sorted(states.items()):
            upper = min(
                item.maximum,
                total_trips - record.used - remaining_minimum[index + 1] - 1,
            )
            for count in range(item.minimum, upper + 1):
                _, quantization = _integer_headway_proxy(
                    item.span.effective_duration_minutes,
                    count,
                    minimum_headway,
                )
                difference = Fraction(count, total_trips) - item.demand_share
                candidate = _CoreRecord(
                    vector=(*record.vector, count),
                    used=record.used + count,
                    core_mismatch=record.core_mismatch + difference * difference,
                    core_l1=record.core_l1 + abs(count - item.regime.b_trip_count),
                    compile_quality=record.compile_quality + quantization,
                )
                key = (candidate.used, candidate.core_l1)
                incumbent = next_states.get(key)
                if incumbent is None or (
                    candidate.core_mismatch,
                    candidate.compile_quality,
                    candidate.vector,
                ) < (
                    incumbent.core_mismatch,
                    incumbent.compile_quality,
                    incumbent.vector,
                ):
                    next_states[key] = candidate
        visited += len(next_states)
        states = next_states
    return tuple(sorted(states.values(), key=lambda item: item.vector)), visited


def _allocation_candidate(
    record: _CoreRecord,
    *,
    record_number: int,
    inputs: Sequence[_CoreInput],
    tail: TailAwareDemandRegimeV2,
    total_trips: int,
    minimum_headway: int,
) -> TailAwareAllocationCandidateV2:
    residual = total_trips - record.used
    tail_difference = Fraction(residual, total_trips) - _fraction(tail.demand_share)
    full_mismatch = record.core_mismatch + tail_difference * tail_difference
    full_l1 = record.core_l1 + abs(residual - tail.b_trip_count)
    evidence: list[CoreRegimeAllocationEvidenceV2] = []
    for count, item in zip(record.vector, inputs, strict=True):
        proxy, quantization = _integer_headway_proxy(
            item.span.effective_duration_minutes,
            count,
            minimum_headway,
        )
        evidence.append(
            CoreRegimeAllocationEvidenceV2(
                regime_id=item.regime.regime_id,
                demand_start=item.regime.start_time,
                demand_end=item.regime.end_time,
                effective_start=item.span.effective_start,
                effective_end=item.span.effective_end,
                effective_duration_minutes=item.span.effective_duration_minutes,
                demand_share=item.regime.demand_share,
                b_trip_count=item.regime.b_trip_count,
                allocated_trip_count=count,
                ideal_trip_count=item.regime.demand_share * total_trips,
                minimum_trip_count=item.minimum,
                maximum_trip_count=item.maximum,
                nominal_operational_headway=item.span.effective_duration_minutes / count,
                best_integer_headway_proxy=proxy,
                headway_quantization_error=float(quantization),
            )
        )
    return TailAwareAllocationCandidateV2(
        candidate_record_id=f"CORE-{record_number:04d}",
        core_trip_counts=record.vector,
        core_trip_total=record.used,
        residual_tail_trip_count=residual,
        core_demand_mismatch=float(record.core_mismatch),
        full_day_demand_mismatch_after_tail=float(full_mismatch),
        moved_trips_vs_b=full_l1 // 2,
        compile_quality_proxy=float(record.compile_quality),
        core_regime_evidence=tuple(evidence),
    )


def _bounded_frontier(
    candidates: Sequence[TailAwareAllocationCandidateV2],
    *,
    b_mismatch: float,
    limit: int,
    epsilon: float,
) -> tuple[TailAwareAllocationCandidateV2, ...]:
    by_c1 = sorted(
        candidates,
        key=lambda item: (
            item.core_demand_mismatch,
            item.full_day_demand_mismatch_after_tail,
            item.compile_quality_proxy,
            item.moved_trips_vs_b,
            item.core_trip_counts,
        ),
    )
    improving = [
        item
        for item in candidates
        if item.full_day_demand_mismatch_after_tail < b_mismatch - epsilon
    ]
    by_c2 = sorted(
        improving or candidates,
        key=lambda item: (
            item.moved_trips_vs_b,
            item.full_day_demand_mismatch_after_tail,
            item.compile_quality_proxy,
            item.core_trip_counts,
        ),
    )
    nondominated = [
        candidate
        for candidate in candidates
        if not any(
            other.full_day_demand_mismatch_after_tail
            <= candidate.full_day_demand_mismatch_after_tail
            and other.moved_trips_vs_b <= candidate.moved_trips_vs_b
            and other.compile_quality_proxy <= candidate.compile_quality_proxy
            and (
                other.full_day_demand_mismatch_after_tail
                < candidate.full_day_demand_mismatch_after_tail
                or other.moved_trips_vs_b < candidate.moved_trips_vs_b
                or other.compile_quality_proxy < candidate.compile_quality_proxy
            )
            for other in candidates
        )
    ]
    by_c3 = sorted(
        nondominated,
        key=lambda item: (
            item.moved_trips_vs_b,
            item.full_day_demand_mismatch_after_tail,
            item.compile_quality_proxy,
            item.core_trip_counts,
        ),
    )
    selected: list[TailAwareAllocationCandidateV2] = []
    seen: set[tuple[int, ...]] = set()
    lists = (by_c1, by_c2, by_c3)
    indices = [0, 0, 0]
    while len(selected) < limit and any(
        index < len(items) for index, items in zip(indices, lists, strict=True)
    ):
        for list_index, items in enumerate(lists):
            while indices[list_index] < len(items):
                item = items[indices[list_index]]
                indices[list_index] += 1
                if item.core_trip_counts not in seen:
                    selected.append(item)
                    seen.add(item.core_trip_counts)
                    break
            if len(selected) >= limit:
                break
    return tuple(selected)


def allocate_tail_aware_trips_v2(
    *,
    regimes: Sequence[TailAwareDemandRegimeV2],
    total_trips: int,
    endpoint_authority: OperationalEndpointAuthorityV1,
    config: TailAwareAllocatorConfigV2 = DEFAULT_TAIL_AWARE_ALLOCATOR_CONFIG_V2,
) -> TailAwareAllocationFrontierV2:
    """Allocate core regimes; the final DemandRegime receives the residual count."""

    if total_trips < 3:
        raise ValueError("tail-aware allocation requires at least three total trips")
    spans = effective_service_spans_v1(regimes, endpoint_authority)
    eligibility = evaluate_tail_eligibility_v2(regimes, endpoint_authority)
    b_vector = tuple(item.b_trip_count for item in regimes)
    if sum(b_vector) != total_trips:
        raise ValueError("B reference counts must reconcile to total_trips")
    b_mismatch = sum(
        (Fraction(count, total_trips) - _fraction(item.demand_share)) ** 2
        for count, item in zip(b_vector, regimes, strict=True)
    )
    if eligibility.status != TailEligibilityStatusV2.ELIGIBLE:
        return TailAwareAllocationFrontierV2(
            allocator_profile=TAIL_AWARE_ALLOCATOR_PROFILE_V2,
            status=TailAwareAllocationStatusV2.NOT_ELIGIBLE,
            total_trips=total_trips,
            service_floor_headway_minutes=None,
            service_floor_provenance="EFFECTIVE_SPAN_BASELINE_DERIVED_SERVICE_FLOOR",
            effective_spans=spans,
            eligibility=eligibility,
            tail_ideal_trip_count=regimes[-1].demand_share * total_trips,
            b_full_day_demand_mismatch=float(b_mismatch),
            candidates=(),
            generated_record_count=0,
            bounded_frontier_limit=config.frontier_limit,
            failure_code=TAIL_SETTLEMENT_NOT_ELIGIBLE,
            failure_message=eligibility.reason,
        )
    minimum_headway = config.minimum_headway_minutes or 1
    inputs, floor_headway = _prepare_core_inputs(
        regimes,
        spans,
        total_trips,
        minimum_headway,
    )
    records, generated = _generate_core_records(
        inputs,
        total_trips=total_trips,
        minimum_headway=minimum_headway,
    )
    all_candidates = tuple(
        _allocation_candidate(
            record,
            record_number=index,
            inputs=inputs,
            tail=regimes[-1],
            total_trips=total_trips,
            minimum_headway=minimum_headway,
        )
        for index, record in enumerate(records, start=1)
    )
    bounded = _bounded_frontier(
        all_candidates,
        b_mismatch=float(b_mismatch),
        limit=config.frontier_limit,
        epsilon=config.improvement_epsilon,
    )
    status = (
        TailAwareAllocationStatusV2.SUCCESS if bounded else TailAwareAllocationStatusV2.INFEASIBLE
    )
    return TailAwareAllocationFrontierV2(
        allocator_profile=TAIL_AWARE_ALLOCATOR_PROFILE_V2,
        status=status,
        total_trips=total_trips,
        service_floor_headway_minutes=float(floor_headway),
        service_floor_provenance="EFFECTIVE_SPAN_BASELINE_DERIVED_SERVICE_FLOOR",
        effective_spans=spans,
        eligibility=eligibility,
        tail_ideal_trip_count=regimes[-1].demand_share * total_trips,
        b_full_day_demand_mismatch=float(b_mismatch),
        candidates=bounded,
        generated_record_count=generated,
        bounded_frontier_limit=config.frontier_limit,
        failure_code=None if bounded else "TAIL_AWARE_ALLOCATION_INFEASIBLE",
        failure_message=None
        if bounded
        else "No bounded core allocation leaves a positive tail count.",
    )


def _core_phase_candidates(
    evidence: CoreRegimeAllocationEvidenceV2,
    *,
    regime_index: int,
    minimum_headway: int,
) -> tuple[_PhaseCandidate, ...]:
    start_minute = _minutes(evidence.effective_start, field="effective_start")
    end_minute = _minutes(evidence.effective_end, field="effective_end")
    count = evidence.allocated_trip_count
    duration = end_minute - start_minute
    maximum_headway = (duration - 1) // (count - 1)
    candidates: list[_PhaseCandidate] = []
    for headway in range(minimum_headway, maximum_headway + 1):
        first = start_minute
        final_first = end_minute - 1 - (count - 1) * headway
        if regime_index == 0:
            final_first = first
        for phase_start in range(first, final_first + 1):
            departures = tuple(phase_start + offset * headway for offset in range(count))
            last = departures[-1]
            if phase_start < start_minute or last >= end_minute:
                continue
            quantization = Fraction(abs(duration - count * headway), duration)
            phase_imbalance = (
                0 if regime_index == 0 else abs((phase_start - start_minute) - (end_minute - last))
            )
            candidates.append(
                _PhaseCandidate(
                    first_minute=phase_start,
                    headway_minutes=headway,
                    last_minute=last,
                    departures_minutes=departures,
                    quantization_error=quantization,
                    phase_imbalance_minutes=phase_imbalance,
                )
            )
    return tuple(candidates)


def _reachable_core_states(
    phase_candidates: Sequence[tuple[_PhaseCandidate, ...]],
) -> tuple[tuple[_PathState, _PhaseCandidate], ...]:
    if not phase_candidates or not phase_candidates[0]:
        return ()
    reachable: dict[int, _PathState] = {}
    for index, candidate in enumerate(phase_candidates[0]):
        reachable[index] = _PathState(
            score=_PathScore(
                candidate.quantization_error,
                1,
                candidate.phase_imbalance_minutes,
                (candidate.headway_minutes,),
                candidate.departures_minutes,
            ),
            candidate_indices=(index,),
        )
    for regime_index in range(1, len(phase_candidates)):
        current = phase_candidates[regime_index]
        if not current:
            return ()
        by_start: dict[int, list[int]] = {}
        by_predecessor: dict[int, list[int]] = {}
        for index, candidate in enumerate(current):
            by_start.setdefault(candidate.first_minute, []).append(index)
            by_predecessor.setdefault(
                candidate.first_minute - candidate.headway_minutes,
                [],
            ).append(index)
        previous_candidates = phase_candidates[regime_index - 1]
        next_reachable: dict[int, _PathState] = {}
        for previous_index, state in reachable.items():
            previous = previous_candidates[previous_index]
            legal = set(by_start.get(previous.last_minute + previous.headway_minutes, ()))
            legal.update(by_predecessor.get(previous.last_minute, ()))
            for current_index in sorted(legal):
                candidate = current[current_index]
                score = _PathScore(
                    state.score.quantization_error + candidate.quantization_error,
                    state.score.service_regime_count
                    + (previous.headway_minutes != candidate.headway_minutes),
                    state.score.phase_imbalance_minutes + candidate.phase_imbalance_minutes,
                    state.score.headway_vector + (candidate.headway_minutes,),
                    state.score.departure_vector + candidate.departures_minutes,
                )
                incumbent = next_reachable.get(current_index)
                if incumbent is None or score < incumbent.score:
                    next_reachable[current_index] = _PathState(
                        score=score,
                        candidate_indices=state.candidate_indices + (current_index,),
                    )
        if not next_reachable:
            return ()
        reachable = next_reachable
    final_candidates = phase_candidates[-1]
    return tuple((state, final_candidates[index]) for index, state in sorted(reachable.items()))


def enumerate_feasible_tail_counts_v2(
    *,
    last_core_departure_minute: int,
    previous_core_headway: int,
    tail_zone_start_minute: int,
    fixed_last_departure_minute: int,
    service_floor_headway_minutes: float,
    maximum_tail_trip_count: int,
) -> dict[int, tuple[_PhaseCandidate, BoundaryOwnershipV1]]:
    """Derive tail debt capacity from actual legal integer headways and boundaries."""

    maximum_headway = math.floor(service_floor_headway_minutes)
    if previous_core_headway > maximum_headway:
        return {}
    result: dict[int, tuple[_PhaseCandidate, BoundaryOwnershipV1]] = {}
    tail_duration = fixed_last_departure_minute - tail_zone_start_minute
    for count in range(1, maximum_tail_trip_count + 1):
        legal: list[tuple[_PhaseCandidate, BoundaryOwnershipV1]] = []
        for headway in range(previous_core_headway, maximum_headway + 1):
            start = fixed_last_departure_minute - (count - 1) * headway
            if start < tail_zone_start_minute:
                continue
            gap = start - last_core_departure_minute
            if gap == previous_core_headway == headway:
                ownership = BoundaryOwnershipV1.MERGED
            elif gap == previous_core_headway:
                ownership = BoundaryOwnershipV1.LEFT
            elif gap == headway:
                ownership = BoundaryOwnershipV1.RIGHT
            else:
                continue
            departures = tuple(start + offset * headway for offset in range(count))
            quantization = Fraction(abs(tail_duration - count * headway), max(1, tail_duration))
            legal.append(
                (
                    _PhaseCandidate(
                        first_minute=start,
                        headway_minutes=headway,
                        last_minute=fixed_last_departure_minute,
                        departures_minutes=departures,
                        quantization_error=quantization,
                        phase_imbalance_minutes=0,
                    ),
                    ownership,
                )
            )
        if legal:
            result[count] = min(
                legal,
                key=lambda item: (
                    item[0].quantization_error,
                    item[0].headway_minutes,
                    item[0].first_minute,
                    item[1].value,
                ),
            )
    return result


def _path_from_state(
    state: _PathState,
    phase_candidates: Sequence[tuple[_PhaseCandidate, ...]],
) -> tuple[_PhaseCandidate, ...]:
    return tuple(
        phase_candidates[index][candidate_index]
        for index, candidate_index in enumerate(state.candidate_indices)
    )


def _build_service_regimes(
    direction: str,
    regimes: Sequence[TailAwareDemandRegimeV2],
    path: Sequence[_PhaseCandidate],
) -> tuple[tuple[CompiledServiceRegimeV1, ...], tuple[str, ...]]:
    groups: list[list[int]] = [[0]]
    for index in range(1, len(path)):
        left = path[index - 1]
        right = path[index]
        gap = right.first_minute - left.last_minute
        if left.headway_minutes == right.headway_minutes == gap:
            groups[-1].append(index)
        else:
            groups.append([index])
    services: list[CompiledServiceRegimeV1] = []
    ids = [""] * len(path)
    for service_number, group in enumerate(groups, start=1):
        service_id = f"TAIL-V2-{direction.upper()}-{service_number:02d}"
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
            raise AssertionError("merged tail-aware ServiceRegime is not uniform")
        for regime_index in group:
            ids[regime_index] = service_id
        services.append(
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
    return tuple(services), tuple(ids)


def _boundary_diagnostics(
    regimes: Sequence[TailAwareDemandRegimeV2],
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
            raise AssertionError("tail-aware compiler admitted an unowned boundary gap")
        diagnostics.append(
            BoundaryGapDiagnosticV1(
                boundary_time=regimes[index].end_time,
                departure_i=_seconds(left.last_minute),
                departure_j=_seconds(right.first_minute),
                gap_minutes=gap,
                left_service_headway=left.headway_minutes,
                right_service_headway=right.headway_minutes,
                ownership=ownership,
                valid=True,
            )
        )
    return tuple(diagnostics)


def compile_end_tail_settlement_v2(
    *,
    route_id: str,
    direction: str,
    candidate_id: str,
    regimes: Sequence[TailAwareDemandRegimeV2],
    endpoint_authority: OperationalEndpointAuthorityV1,
    frontier: TailAwareAllocationFrontierV2,
    allocation: TailAwareAllocationCandidateV2,
    minimum_headway_minutes: int = 1,
) -> EndTailSettlementPlanV2:
    """Compile authoritative core counts and a backward-anchored residual tail."""

    if frontier.status != TailAwareAllocationStatusV2.SUCCESS:
        raise ValueError("tail-aware allocation frontier must be successful")
    if endpoint_authority.route_id != route_id or endpoint_authority.direction != direction:
        raise ValueError("endpoint authority identity does not match compiler request")
    phase_candidates = tuple(
        _core_phase_candidates(
            evidence,
            regime_index=index,
            minimum_headway=minimum_headway_minutes,
        )
        for index, evidence in enumerate(allocation.core_regime_evidence)
    )
    states = _reachable_core_states(phase_candidates)
    residual = allocation.residual_tail_trip_count
    if not states:
        return EndTailSettlementPlanV2(
            allocation=allocation,
            compilation=None,
            tail_evidence=None,
            failure=EndTailSettlementFailureV2(
                code=END_TAIL_SETTLEMENT_UNCOMPILABLE,
                reason="Core counts have no clean whole-minute phase path from fixed first.",
                core_trip_counts=allocation.core_trip_counts,
                residual_tail_trip_count=residual,
                feasible_tail_trip_counts=(),
                min_feasible_tail_trip_count=None,
                max_feasible_tail_trip_count=None,
            ),
        )
    fixed_last = _minutes(endpoint_authority.fixed_last_departure, field="fixed_last")
    zone_start = _minutes(frontier.eligibility.tail_zone_start, field="tail_zone_start")
    best: (
        tuple[
            _PathScore,
            tuple[_PhaseCandidate, ...],
            _PhaseCandidate,
            BoundaryOwnershipV1,
            tuple[int, ...],
        ]
        | None
    ) = None
    capacity_union: set[int] = set()
    envelope_possible = False
    for state, final_core in states:
        if final_core.headway_minutes <= math.floor(float(frontier.service_floor_headway_minutes)):
            envelope_possible = True
        capacity = enumerate_feasible_tail_counts_v2(
            last_core_departure_minute=final_core.last_minute,
            previous_core_headway=final_core.headway_minutes,
            tail_zone_start_minute=zone_start,
            fixed_last_departure_minute=fixed_last,
            service_floor_headway_minutes=float(frontier.service_floor_headway_minutes),
            maximum_tail_trip_count=frontier.total_trips,
        )
        capacity_union.update(capacity)
        selected_tail = capacity.get(residual)
        if selected_tail is None:
            continue
        tail, ownership = selected_tail
        core_path = _path_from_state(state, phase_candidates)
        full_score = _PathScore(
            state.score.quantization_error + tail.quantization_error,
            state.score.service_regime_count + (final_core.headway_minutes != tail.headway_minutes),
            state.score.phase_imbalance_minutes,
            state.score.headway_vector + (tail.headway_minutes,),
            state.score.departure_vector + tail.departures_minutes,
        )
        candidate = (
            full_score,
            core_path,
            tail,
            ownership,
            tuple(sorted(capacity)),
        )
        if best is None or candidate[0] < best[0]:
            best = candidate
    if best is None:
        feasible = tuple(sorted(capacity_union))
        code = (
            TAIL_DEBT_CAPACITY_EXCEEDED if envelope_possible else TAIL_SERVICE_ENVELOPE_INFEASIBLE
        )
        reason = (
            "Residual tail count is outside the derived capacity of all clean compiled core states."
            if code == TAIL_DEBT_CAPACITY_EXCEEDED
            else "No integer tail headway exists between the preceding rhythm and service floor."
        )
        return EndTailSettlementPlanV2(
            allocation=allocation,
            compilation=None,
            tail_evidence=None,
            failure=EndTailSettlementFailureV2(
                code=code,
                reason=reason,
                core_trip_counts=allocation.core_trip_counts,
                residual_tail_trip_count=residual,
                feasible_tail_trip_counts=feasible,
                min_feasible_tail_trip_count=min(feasible, default=None),
                max_feasible_tail_trip_count=max(feasible, default=None),
            ),
        )
    score, core_path, tail, ownership, feasible = best
    path = (*core_path, tail)
    services, service_ids = _build_service_regimes(direction, regimes, path)
    allocations = tuple(
        DemandRegimeAllocationV1(
            regime_id=regime.regime_id,
            start_time=regime.start_time,
            end_time=regime.end_time,
            allocated_trip_count=count,
            nominal_headway=(frontier.effective_spans[index].effective_duration_minutes / count),
        )
        for index, (regime, count) in enumerate(
            zip(
                regimes,
                (*allocation.core_trip_counts, allocation.residual_tail_trip_count),
                strict=True,
            )
        )
    )
    slices = tuple(
        CompiledDemandRegimeSliceV1(
            demand_regime_id=regime.regime_id,
            demand_regime_start=regime.start_time,
            demand_regime_end=regime.end_time,
            authoritative_trip_count=count,
            service_regime_id=service_ids[index],
            uniform_headway_minutes=phase.headway_minutes,
            first_departure=_seconds(phase.first_minute),
            last_departure=_seconds(phase.last_minute),
            departures=tuple(_seconds(item) for item in phase.departures_minutes),
            headway_quantization_error=float(phase.quantization_error),
            phase_imbalance_minutes=phase.phase_imbalance_minutes,
        )
        for index, (regime, count, phase) in enumerate(
            zip(
                regimes,
                (*allocation.core_trip_counts, allocation.residual_tail_trip_count),
                path,
                strict=True,
            )
        )
    )
    exact_departures = tuple(departure for item in slices for departure in item.departures)
    diagnostics = _boundary_diagnostics(regimes, path)
    compilation = CleanBoundaryCompilationV1(
        compiler_profile=END_TAIL_SETTLEMENT_COMPILER_PROFILE_V2,
        route_id=route_id,
        direction=direction,
        candidate_id=candidate_id,
        status=CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES,
        endpoint_authority=endpoint_authority,
        demand_regime_slices=slices,
        service_regimes=services,
        exact_departures=exact_departures,
        boundary_diagnostics=diagnostics,
        total_headway_quantization_error=float(score.quantization_error),
        total_phase_imbalance_minutes=score.phase_imbalance_minutes,
        failure=None,
    )
    validate_clean_boundary_compilation_v1(compilation, allocations)
    tail_boundary = diagnostics[-1]
    evidence = TailSettlementEvidenceV2(
        final_demand_regime_id=regimes[-1].regime_id,
        final_demand_density_index=frontier.eligibility.final_demand_density_index,
        tail_eligibility=frontier.eligibility.status.value,
        tail_zone_start=frontier.eligibility.tail_zone_start,
        tail_zone_end=frontier.eligibility.tail_zone_end,
        fixed_last_departure=endpoint_authority.fixed_last_departure,
        previous_core_headway=core_path[-1].headway_minutes,
        tail_trip_count=residual,
        tail_ideal_trip_count=frontier.tail_ideal_trip_count,
        tail_trip_debt=residual - frontier.tail_ideal_trip_count,
        tail_headway=tail.headway_minutes,
        tail_start=_seconds(tail.first_minute),
        tail_last_departure=_seconds(tail.last_minute),
        feasible_tail_trip_counts=feasible,
        min_feasible_tail_trip_count=min(feasible),
        max_feasible_tail_trip_count=max(feasible),
        clean_boundary_gap_minutes=tail_boundary.gap_minutes,
        clean_boundary_ownership=tail_boundary.ownership.value,
        low_demand_monotonicity_satisfied=(tail.headway_minutes >= core_path[-1].headway_minutes),
        service_floor_satisfied=(
            tail.headway_minutes <= float(frontier.service_floor_headway_minutes)
        ),
    )
    return EndTailSettlementPlanV2(
        allocation=allocation,
        compilation=compilation,
        tail_evidence=evidence,
        failure=None,
    )


def _feasible_pareto(
    plans: Sequence[EndTailSettlementPlanV2],
    *,
    b_mismatch: float,
    c1_moved: int,
) -> tuple[EndTailSettlementPlanV2, ...]:
    bounded = tuple(
        item
        for item in plans
        if item.allocation.full_day_demand_mismatch_after_tail <= b_mismatch
        and item.allocation.moved_trips_vs_b <= c1_moved
    )
    frontier = tuple(
        candidate
        for candidate in bounded
        if not any(
            other.allocation.full_day_demand_mismatch_after_tail
            <= candidate.allocation.full_day_demand_mismatch_after_tail
            and other.allocation.moved_trips_vs_b <= candidate.allocation.moved_trips_vs_b
            and (
                other.allocation.full_day_demand_mismatch_after_tail
                < candidate.allocation.full_day_demand_mismatch_after_tail
                or other.allocation.moved_trips_vs_b < candidate.allocation.moved_trips_vs_b
            )
            for other in bounded
        )
    )
    return tuple(
        sorted(
            frontier,
            key=lambda item: (
                item.allocation.moved_trips_vs_b,
                item.allocation.full_day_demand_mismatch_after_tail,
                float(item.compilation.total_headway_quantization_error),
                item.allocation.core_trip_counts,
            ),
        )
    )


def _balanced_plan(
    frontier: Sequence[EndTailSettlementPlanV2],
    *,
    b_mismatch: float,
    c1: EndTailSettlementPlanV2,
) -> EndTailSettlementPlanV2:
    denominator = b_mismatch - c1.allocation.full_day_demand_mismatch_after_tail
    movement_denominator = max(1, c1.allocation.moved_trips_vs_b)
    if denominator <= 0 or c1.allocation.moved_trips_vs_b == 0:
        return min(
            frontier,
            key=lambda item: (
                item.allocation.moved_trips_vs_b,
                item.allocation.full_day_demand_mismatch_after_tail,
                float(item.compilation.total_headway_quantization_error),
                item.allocation.core_trip_counts,
            ),
        )

    def key(item: EndTailSettlementPlanV2) -> tuple[float, float, int, float, tuple[int, ...]]:
        demand_normalized = (
            item.allocation.full_day_demand_mismatch_after_tail
            - c1.allocation.full_day_demand_mismatch_after_tail
        ) / denominator
        movement_normalized = item.allocation.moved_trips_vs_b / movement_denominator
        return (
            demand_normalized**2 + movement_normalized**2,
            float(item.compilation.total_headway_quantization_error),
            item.allocation.moved_trips_vs_b,
            item.allocation.full_day_demand_mismatch_after_tail,
            item.allocation.core_trip_counts,
        )

    return min(frontier, key=key)


def select_tail_aware_candidates_v2(
    *,
    route_id: str,
    direction: str,
    regimes: Sequence[TailAwareDemandRegimeV2],
    endpoint_authority: OperationalEndpointAuthorityV1,
    frontier: TailAwareAllocationFrontierV2,
    config: TailAwareAllocatorConfigV2 = DEFAULT_TAIL_AWARE_ALLOCATOR_CONFIG_V2,
) -> TailAwareCandidateSetV2:
    """Compile the bounded frontier, then assign C1/C2/C3 semantics."""

    if frontier.status != TailAwareAllocationStatusV2.SUCCESS:
        return TailAwareCandidateSetV2(
            allocator_profile=TAIL_AWARE_ALLOCATOR_PROFILE_V2,
            compiler_profile=END_TAIL_SETTLEMENT_COMPILER_PROFILE_V2,
            eligibility=frontier.eligibility,
            frontier=frontier,
            c1_demand_fit=None,
            c2_conservative=None,
            c3_balanced=None,
            feasible_compiled_candidate_count=0,
            infeasible_candidate_count=0,
            pareto_frontier_size=0,
            failure_code_counts=(),
        )
    plans = tuple(
        compile_end_tail_settlement_v2(
            route_id=route_id,
            direction=direction,
            candidate_id=item.candidate_record_id,
            regimes=regimes,
            endpoint_authority=endpoint_authority,
            frontier=frontier,
            allocation=item,
            minimum_headway_minutes=config.minimum_headway_minutes or 1,
        )
        for item in frontier.candidates
    )
    feasible = tuple(item for item in plans if item.compiled)
    failures: dict[str, int] = {}
    for item in plans:
        if item.failure is not None:
            failures[item.failure.code] = failures.get(item.failure.code, 0) + 1
    if not feasible:
        return TailAwareCandidateSetV2(
            allocator_profile=TAIL_AWARE_ALLOCATOR_PROFILE_V2,
            compiler_profile=END_TAIL_SETTLEMENT_COMPILER_PROFILE_V2,
            eligibility=frontier.eligibility,
            frontier=frontier,
            c1_demand_fit=None,
            c2_conservative=None,
            c3_balanced=None,
            feasible_compiled_candidate_count=0,
            infeasible_candidate_count=len(plans),
            pareto_frontier_size=0,
            failure_code_counts=tuple(sorted(failures.items())),
        )
    c1 = min(
        feasible,
        key=lambda item: (
            item.allocation.core_demand_mismatch,
            item.allocation.full_day_demand_mismatch_after_tail,
            float(item.compilation.total_headway_quantization_error),
            len(item.compilation.service_regimes),
            item.allocation.moved_trips_vs_b,
            item.allocation.core_trip_counts,
        ),
    )
    improving = tuple(
        item
        for item in feasible
        if item.allocation.full_day_demand_mismatch_after_tail
        < frontier.b_full_day_demand_mismatch - config.improvement_epsilon
    )
    if improving:
        c2 = min(
            improving,
            key=lambda item: (
                item.allocation.moved_trips_vs_b,
                item.allocation.full_day_demand_mismatch_after_tail,
                float(item.compilation.total_headway_quantization_error),
                len(item.compilation.service_regimes),
                item.allocation.core_trip_counts,
            ),
        )
        c2_status = "SUCCESS"
    else:
        c2 = min(
            feasible,
            key=lambda item: (
                item.allocation.moved_trips_vs_b,
                item.allocation.full_day_demand_mismatch_after_tail,
                float(item.compilation.total_headway_quantization_error),
                item.allocation.core_trip_counts,
            ),
        )
        c2_status = "NO_IMPROVING_CONSERVATIVE_ALLOCATION"
    pareto = _feasible_pareto(
        feasible,
        b_mismatch=frontier.b_full_day_demand_mismatch,
        c1_moved=c1.allocation.moved_trips_vs_b,
    )
    c3 = _balanced_plan(pareto or (c1,), b_mismatch=frontier.b_full_day_demand_mismatch, c1=c1)

    def selected(
        candidate_id: str, plan: EndTailSettlementPlanV2, status: str = "SUCCESS"
    ) -> TailAwareSelectedCandidateV2:
        compilation = plan.compilation
        assert compilation is not None
        renamed = CleanBoundaryCompilationV1(
            compiler_profile=compilation.compiler_profile,
            route_id=compilation.route_id,
            direction=compilation.direction,
            candidate_id=candidate_id,
            status=compilation.status,
            endpoint_authority=compilation.endpoint_authority,
            demand_regime_slices=compilation.demand_regime_slices,
            service_regimes=compilation.service_regimes,
            exact_departures=compilation.exact_departures,
            boundary_diagnostics=compilation.boundary_diagnostics,
            total_headway_quantization_error=compilation.total_headway_quantization_error,
            total_phase_imbalance_minutes=compilation.total_phase_imbalance_minutes,
            failure=None,
        )
        return TailAwareSelectedCandidateV2(
            candidate_id=candidate_id,
            semantic_status=status,
            plan=EndTailSettlementPlanV2(
                allocation=plan.allocation,
                compilation=renamed,
                tail_evidence=plan.tail_evidence,
                failure=None,
            ),
        )

    return TailAwareCandidateSetV2(
        allocator_profile=TAIL_AWARE_ALLOCATOR_PROFILE_V2,
        compiler_profile=END_TAIL_SETTLEMENT_COMPILER_PROFILE_V2,
        eligibility=frontier.eligibility,
        frontier=frontier,
        c1_demand_fit=selected("C1_DEMAND_FIT", c1),
        c2_conservative=selected("C2_CONSERVATIVE", c2, c2_status),
        c3_balanced=selected("C3_BALANCED", c3),
        feasible_compiled_candidate_count=len(feasible),
        infeasible_candidate_count=len(plans) - len(feasible),
        pareto_frontier_size=len(pareto),
        failure_code_counts=tuple(sorted(failures.items())),
    )


def tail_aware_candidate_set_to_dict_v2(result: TailAwareCandidateSetV2) -> dict[str, Any]:
    return asdict(result)


__all__ = [
    "DEFAULT_TAIL_AWARE_ALLOCATOR_CONFIG_V2",
    "END_TAIL_SETTLEMENT_COMPILER_PROFILE_V2",
    "END_TAIL_SETTLEMENT_UNCOMPILABLE",
    "TAIL_AWARE_ALLOCATOR_PROFILE_V2",
    "TAIL_DEBT_CAPACITY_EXCEEDED",
    "TAIL_SERVICE_ENVELOPE_INFEASIBLE",
    "TAIL_SETTLEMENT_NOT_ELIGIBLE",
    "CoreRegimeAllocationEvidenceV2",
    "EffectiveServiceSpanV1",
    "EndTailSettlementFailureV2",
    "EndTailSettlementPlanV2",
    "TailAwareAllocationCandidateV2",
    "TailAwareAllocationFrontierV2",
    "TailAwareAllocatorConfigV2",
    "TailAwareCandidateSetV2",
    "TailAwareDemandRegimeV2",
    "TailAwareSelectedCandidateV2",
    "TailEligibilityEvidenceV2",
    "TailEligibilityStatusV2",
    "TailSettlementEvidenceV2",
    "allocate_tail_aware_trips_v2",
    "compile_end_tail_settlement_v2",
    "effective_service_spans_v1",
    "enumerate_feasible_tail_counts_v2",
    "evaluate_tail_eligibility_v2",
    "select_tail_aware_candidates_v2",
    "tail_aware_candidate_set_to_dict_v2",
    "tail_aware_regime_from_mapping_v2",
]
