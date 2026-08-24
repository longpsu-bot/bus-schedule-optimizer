"""Deterministic integer trip allocation over validated demand regimes.

This module stops at integer counts and compile-quality diagnostics.  It does not
generate departures, choose phases, regularize service regimes, or validate fleet
feasibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from .demand_regimes import DemandRegimePlanV1, DemandRegimeV1
from .models import ContractDirection, ScenarioBInput
from .regime_trip_allocation import (
    RegimeTripAllocationV1,
    count_departures_in_regime_v1,
    nominal_service_headway_minutes_v1,
)

DETERMINISTIC_TRIP_ALLOCATOR_PROFILE_V1 = "validated_demand_regime_trip_allocator_v1"
BASELINE_DERIVED_SERVICE_FLOOR = "BASELINE_DERIVED_SERVICE_FLOOR"
DAILY_VALIDATED = "DAILY_VALIDATED"
INFEASIBLE_SERVICE_FLOORS = "INFEASIBLE_SERVICE_FLOORS"
INFEASIBLE_ALLOCATION_UPPER_BOUNDS = "INFEASIBLE_ALLOCATION_UPPER_BOUNDS"
INVALID_ALLOCATION_INPUT = "INVALID_ALLOCATION_INPUT"
NO_IMPROVING_CONSERVATIVE_ALLOCATION = "NO_IMPROVING_CONSERVATIVE_ALLOCATION"


class TripAllocationCandidateStatusV1(StrEnum):
    SUCCESS = "SUCCESS"
    NO_IMPROVING_CONSERVATIVE_ALLOCATION = NO_IMPROVING_CONSERVATIVE_ALLOCATION


class TripAllocationSetStatusV1(StrEnum):
    SUCCESS = "SUCCESS"
    INFEASIBLE = "INFEASIBLE"
    INVALID_INPUT = "INVALID_INPUT"


@dataclass(frozen=True, slots=True)
class DeterministicTripAllocatorConfigV1:
    improvement_epsilon: float = 1e-12
    minimum_headway_minutes: int | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.improvement_epsilon, bool)
            or not isinstance(self.improvement_epsilon, (int, float))
            or not math.isfinite(float(self.improvement_epsilon))
            or self.improvement_epsilon < 0
        ):
            raise ValueError("improvement_epsilon must be finite and non-negative")
        if self.minimum_headway_minutes is not None and (
            isinstance(self.minimum_headway_minutes, bool)
            or not isinstance(self.minimum_headway_minutes, int)
            or self.minimum_headway_minutes < 1
        ):
            raise ValueError("minimum_headway_minutes must be a positive integer when supplied")


DEFAULT_DETERMINISTIC_TRIP_ALLOCATOR_CONFIG_V1 = DeterministicTripAllocatorConfigV1()


@dataclass(frozen=True, slots=True)
class RegimeAllocationEvidenceV1:
    allocation: RegimeTripAllocationV1
    start_time: int
    end_time: int
    duration_minutes: int
    demand_sum: float
    demand_share: float
    b_trip_count: int
    b_service_share: float
    b_nominal_headway: float | None
    ideal_trip_count_float: float
    min_trip_count: int
    max_trip_count: int
    max_trip_count_provenance: str
    nominal_headway: float | None
    best_integer_headway_proxy: int | None
    headway_quantization_error: float | None
    observed_demand_per_allocated_trip: float | None
    service_floor_binding: bool

    @property
    def regime_id(self) -> str:
        return self.allocation.regime_id

    @property
    def allocated_trip_count(self) -> int:
        return self.allocation.trip_count


@dataclass(frozen=True, slots=True)
class ServiceRegimeMergeHintV1:
    boundary_time: int
    earlier_regime_id: str
    later_regime_id: str
    earlier_integer_headway_proxy: int | None
    later_integer_headway_proxy: int | None
    same_integer_headway_proxy: bool
    service_rate_merge_candidate: bool


@dataclass(frozen=True, slots=True)
class TripAllocationCandidateV1:
    candidate_id: str
    status: TripAllocationCandidateStatusV1
    direction: ContractDirection
    total_trips: int
    regime_allocations: tuple[RegimeAllocationEvidenceV1, ...]
    demand_mismatch: float
    demand_mismatch_improvement_vs_b: float
    moved_trips: int
    compile_quality_score: float
    minimum_nominal_headway: float
    maximum_nominal_headway: float
    duration_weighted_average_nominal_headway: float
    largest_trip_increase_vs_b: int
    largest_trip_decrease_vs_b: int
    changed_regime_count: int
    service_floor_provenance: str
    merge_hints: tuple[ServiceRegimeMergeHintV1, ...]

    @property
    def allocation_vector(self) -> tuple[int, ...]:
        return tuple(item.allocated_trip_count for item in self.regime_allocations)


@dataclass(frozen=True, slots=True)
class TripAllocationCandidateSetV1:
    allocator_profile: str
    status: TripAllocationSetStatusV1
    direction: ContractDirection
    evidence_status: str
    total_trips: int
    service_floor_provenance: str
    service_floor_headway_minutes: float | None
    minimum_headway_policy_minutes: int | None
    b_reference: TripAllocationCandidateV1 | None
    c1_demand_fit: TripAllocationCandidateV1 | None
    c2_conservative: TripAllocationCandidateV1 | None
    c3_balanced: TripAllocationCandidateV1 | None
    feasible_dp_state_count: int
    pareto_frontier_size: int
    failure_code: str | None = None
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class _RegimeInput:
    regime: DemandRegimeV1
    demand_share: Fraction
    b_trip_count: int
    minimum: int
    maximum: int
    maximum_provenance: str


@dataclass(frozen=True, slots=True)
class _AllocationRecord:
    vector: tuple[int, ...]
    demand_mismatch: Fraction
    l1_deviation: int
    compile_quality: Fraction

    @property
    def moved_trips(self) -> int:
        return self.l1_deviation // 2


def _fraction(value: float) -> Fraction:
    return Fraction(Decimal(str(value)))


def _ceiling(value: Fraction) -> int:
    return -(-value.numerator // value.denominator)


def _integer_headway_proxy(
    duration_minutes: int,
    trip_count: int,
    minimum_headway_minutes: int | None,
) -> tuple[int | None, Fraction | None]:
    if trip_count < 1:
        raise ValueError("service-protected allocation requires at least one trip")
    if trip_count == 1:
        return None, None
    lower = minimum_headway_minutes or 1
    upper = (duration_minutes - 1) // (trip_count - 1)
    if lower > upper:
        raise ValueError("allocation has no feasible positive integer-minute internal headway")
    nominal = Fraction(duration_minutes, trip_count)
    candidates = {max(lower, min(upper, nominal.numerator // nominal.denominator))}
    candidates.add(max(lower, min(upper, _ceiling(nominal))))
    headway = min(candidates, key=lambda item: (abs(Fraction(item) - nominal), item))
    error = Fraction(abs(duration_minutes - trip_count * headway), duration_minutes)
    return headway, error


def _maximum_trip_count(duration: int, minimum_headway: int | None) -> tuple[int, str]:
    if minimum_headway is None:
        return duration, "POSITIVE_INTEGER_MINUTE_COMPILE_FEASIBILITY"
    return ((duration - 1) // minimum_headway) + 1, "EXPLICIT_MINIMUM_HEADWAY_POLICY"


def _direction_total(scenario_b: ScenarioBInput, direction: ContractDirection) -> int:
    return (
        scenario_b.trips_by_direction.outbound
        if direction == ContractDirection.OUTBOUND
        else scenario_b.trips_by_direction.inbound
    )


def _invalid_result(
    plan: DemandRegimePlanV1,
    evidence_status: str,
    total: int,
    code: str,
    message: str,
    *,
    status: TripAllocationSetStatusV1 = TripAllocationSetStatusV1.INVALID_INPUT,
    config: DeterministicTripAllocatorConfigV1,
) -> TripAllocationCandidateSetV1:
    return TripAllocationCandidateSetV1(
        allocator_profile=DETERMINISTIC_TRIP_ALLOCATOR_PROFILE_V1,
        status=status,
        direction=plan.direction,
        evidence_status=evidence_status,
        total_trips=total,
        service_floor_provenance=BASELINE_DERIVED_SERVICE_FLOOR,
        service_floor_headway_minutes=None,
        minimum_headway_policy_minutes=config.minimum_headway_minutes,
        b_reference=None,
        c1_demand_fit=None,
        c2_conservative=None,
        c3_balanced=None,
        feasible_dp_state_count=0,
        pareto_frontier_size=0,
        failure_code=code,
        failure_message=message,
    )


def _validate_and_prepare(
    plan: DemandRegimePlanV1,
    scenario_b: ScenarioBInput,
    evidence_status: str,
    config: DeterministicTripAllocatorConfigV1,
) -> tuple[tuple[_RegimeInput, ...], int, Fraction] | TripAllocationCandidateSetV1:
    total = _direction_total(scenario_b, plan.direction)
    if evidence_status != DAILY_VALIDATED:
        return _invalid_result(
            plan,
            evidence_status,
            total,
            INVALID_ALLOCATION_INPUT,
            "trip allocation requires a DAILY_VALIDATED demand-regime plan",
            config=config,
        )
    if plan.direction not in {ContractDirection.OUTBOUND, ContractDirection.INBOUND}:
        return _invalid_result(
            plan,
            evidence_status,
            total,
            INVALID_ALLOCATION_INPUT,
            "allocation requires one canonical timetable direction",
            config=config,
        )
    regimes = tuple(sorted(plan.regimes, key=lambda item: (item.start_time, item.regime_id)))
    if (
        not regimes
        or regimes[0].start_time != plan.service_start
        or regimes[-1].end_time != plan.service_end
        or any(item.direction != plan.direction for item in regimes)
        or any(
            left.end_time != right.start_time
            for left, right in zip(regimes, regimes[1:], strict=False)
        )
    ):
        return _invalid_result(
            plan,
            evidence_status,
            total,
            INVALID_ALLOCATION_INPUT,
            "demand regimes must be direction-isolated and cover the complete service window",
            config=config,
        )
    if total < 1 or plan.total_demand <= 0:
        return _invalid_result(
            plan,
            evidence_status,
            total,
            INVALID_ALLOCATION_INPUT,
            "allocation requires positive Scenario B trips and observed demand",
            config=config,
        )
    exact_directional = tuple(
        trip.departure_time
        for trip in scenario_b.exact_timetable
        if trip.direction == plan.direction
    )
    if len(exact_directional) != total:
        return _invalid_result(
            plan,
            evidence_status,
            total,
            INVALID_ALLOCATION_INPUT,
            "Scenario B directional declaration does not match its exact timetable",
            config=config,
        )
    b_counts = tuple(
        count_departures_in_regime_v1(
            regime.start_time,
            regime.end_time,
            exact_directional,
        )
        for regime in regimes
    )
    if sum(b_counts) != total:
        return _invalid_result(
            plan,
            evidence_status,
            total,
            INVALID_ALLOCATION_INPUT,
            "half-open demand regimes do not reconcile to the Scenario B direction total",
            config=config,
        )
    served_headways = tuple(
        Fraction(regime.duration_minutes, count)
        for regime, count in zip(regimes, b_counts, strict=True)
        if count > 0
    )
    if not served_headways:
        return _invalid_result(
            plan,
            evidence_status,
            total,
            INVALID_ALLOCATION_INPUT,
            "Scenario B provides no service in the validated demand window",
            config=config,
        )
    floor_headway = max(served_headways)
    prepared: list[_RegimeInput] = []
    total_demand = _fraction(plan.total_demand)
    for regime, b_count in zip(regimes, b_counts, strict=True):
        minimum = max(1, _ceiling(Fraction(regime.duration_minutes) / floor_headway))
        maximum, maximum_provenance = _maximum_trip_count(
            regime.duration_minutes,
            config.minimum_headway_minutes,
        )
        prepared.append(
            _RegimeInput(
                regime=regime,
                demand_share=_fraction(regime.demand_sum) / total_demand,
                b_trip_count=b_count,
                minimum=minimum,
                maximum=maximum,
                maximum_provenance=maximum_provenance,
            )
        )
    if sum(item.minimum for item in prepared) > total:
        return _invalid_result(
            plan,
            evidence_status,
            total,
            INFEASIBLE_SERVICE_FLOORS,
            "baseline-derived service floors require more trips than Scenario B provides",
            status=TripAllocationSetStatusV1.INFEASIBLE,
            config=config,
        )
    if sum(item.maximum for item in prepared) < total or any(
        item.minimum > item.maximum for item in prepared
    ):
        return _invalid_result(
            plan,
            evidence_status,
            total,
            INFEASIBLE_ALLOCATION_UPPER_BOUNDS,
            "compile-feasibility or explicit minimum-headway bounds cannot absorb the total",
            status=TripAllocationSetStatusV1.INFEASIBLE,
            config=config,
        )
    return tuple(prepared), total, floor_headway


def _generate_records(
    inputs: tuple[_RegimeInput, ...],
    total: int,
    minimum_headway: int | None,
) -> tuple[tuple[_AllocationRecord, ...], int]:
    states: dict[tuple[int, int], _AllocationRecord] = {
        (0, 0): _AllocationRecord((), Fraction(0), 0, Fraction(0))
    }
    visited = 1
    remaining_minimum = [0] * (len(inputs) + 1)
    remaining_maximum = [0] * (len(inputs) + 1)
    for index in range(len(inputs) - 1, -1, -1):
        remaining_minimum[index] = remaining_minimum[index + 1] + inputs[index].minimum
        remaining_maximum[index] = remaining_maximum[index + 1] + inputs[index].maximum
    for index, item in enumerate(inputs):
        next_states: dict[tuple[int, int], _AllocationRecord] = {}
        for (used, l1), record in sorted(states.items()):
            lower = max(item.minimum, total - used - remaining_maximum[index + 1])
            upper = min(item.maximum, total - used - remaining_minimum[index + 1])
            for count in range(lower, upper + 1):
                _, quantization = _integer_headway_proxy(
                    item.regime.duration_minutes,
                    count,
                    minimum_headway,
                )
                mismatch = Fraction(count, total) - item.demand_share
                candidate = _AllocationRecord(
                    vector=(*record.vector, count),
                    demand_mismatch=record.demand_mismatch + mismatch * mismatch,
                    l1_deviation=l1 + abs(count - item.b_trip_count),
                    compile_quality=record.compile_quality + (quantization or Fraction(0)),
                )
                key = (used + count, candidate.l1_deviation)
                incumbent = next_states.get(key)
                if incumbent is None or (
                    candidate.demand_mismatch,
                    candidate.compile_quality,
                    candidate.vector,
                ) < (
                    incumbent.demand_mismatch,
                    incumbent.compile_quality,
                    incumbent.vector,
                ):
                    next_states[key] = candidate
        visited += len(next_states)
        states = next_states
    return (
        tuple(record for (used, _), record in sorted(states.items()) if used == total),
        visited,
    )


def _record_for_vector(
    vector: tuple[int, ...],
    inputs: tuple[_RegimeInput, ...],
    total: int,
    minimum_headway: int | None,
) -> _AllocationRecord:
    mismatch = Fraction(0)
    compile_quality = Fraction(0)
    l1 = 0
    for count, item in zip(vector, inputs, strict=True):
        difference = Fraction(count, total) - item.demand_share
        mismatch += difference * difference
        _, quantization = _integer_headway_proxy(
            item.regime.duration_minutes,
            count,
            minimum_headway,
        )
        compile_quality += quantization or Fraction(0)
        l1 += abs(count - item.b_trip_count)
    return _AllocationRecord(vector, mismatch, l1, compile_quality)


def _pareto_frontier(
    records: tuple[_AllocationRecord, ...],
    b: _AllocationRecord,
    c1: _AllocationRecord,
) -> tuple[_AllocationRecord, ...]:
    bounded = tuple(
        item
        for item in records
        if item.demand_mismatch <= b.demand_mismatch and item.moved_trips <= c1.moved_trips
    )
    frontier = []
    for candidate in bounded:
        dominated = any(
            other.demand_mismatch <= candidate.demand_mismatch
            and other.moved_trips <= candidate.moved_trips
            and (
                other.demand_mismatch < candidate.demand_mismatch
                or other.moved_trips < candidate.moved_trips
            )
            for other in bounded
        )
        if not dominated:
            frontier.append(candidate)
    return tuple(
        sorted(
            frontier,
            key=lambda item: (
                item.moved_trips,
                item.demand_mismatch,
                item.compile_quality,
                item.vector,
            ),
        )
    )


def _balanced_record(
    frontier: tuple[_AllocationRecord, ...],
    b: _AllocationRecord,
    c1: _AllocationRecord,
) -> _AllocationRecord:
    demand_denominator = b.demand_mismatch - c1.demand_mismatch
    if demand_denominator <= 0 or c1.moved_trips == 0:
        return b
    movement_denominator = max(1, c1.moved_trips)

    def key(item: _AllocationRecord) -> tuple[Fraction, Fraction, int, Fraction, tuple[int, ...]]:
        demand_normalized = (item.demand_mismatch - c1.demand_mismatch) / demand_denominator
        movement_normalized = Fraction(item.moved_trips, movement_denominator)
        squared_distance = demand_normalized**2 + movement_normalized**2
        return (
            squared_distance,
            item.compile_quality,
            item.moved_trips,
            item.demand_mismatch,
            item.vector,
        )

    return min(frontier, key=key)


def _merge_hints(
    allocations: tuple[RegimeAllocationEvidenceV1, ...],
) -> tuple[ServiceRegimeMergeHintV1, ...]:
    hints = []
    for earlier, later in zip(allocations, allocations[1:], strict=False):
        same = (
            earlier.best_integer_headway_proxy is not None
            and earlier.best_integer_headway_proxy == later.best_integer_headway_proxy
        )
        hints.append(
            ServiceRegimeMergeHintV1(
                boundary_time=earlier.end_time,
                earlier_regime_id=earlier.regime_id,
                later_regime_id=later.regime_id,
                earlier_integer_headway_proxy=earlier.best_integer_headway_proxy,
                later_integer_headway_proxy=later.best_integer_headway_proxy,
                same_integer_headway_proxy=same,
                service_rate_merge_candidate=same,
            )
        )
    return tuple(hints)


def _candidate(
    candidate_id: str,
    status: TripAllocationCandidateStatusV1,
    record: _AllocationRecord,
    b_record: _AllocationRecord,
    inputs: tuple[_RegimeInput, ...],
    total: int,
    minimum_headway: int | None,
) -> TripAllocationCandidateV1:
    allocations = []
    for count, item in zip(record.vector, inputs, strict=True):
        proxy, quantization = _integer_headway_proxy(
            item.regime.duration_minutes,
            count,
            minimum_headway,
        )
        allocations.append(
            RegimeAllocationEvidenceV1(
                allocation=RegimeTripAllocationV1(item.regime.regime_id, count),
                start_time=item.regime.start_time,
                end_time=item.regime.end_time,
                duration_minutes=item.regime.duration_minutes,
                demand_sum=item.regime.demand_sum,
                demand_share=float(item.demand_share),
                b_trip_count=item.b_trip_count,
                b_service_share=item.b_trip_count / total,
                b_nominal_headway=nominal_service_headway_minutes_v1(
                    item.regime.duration_minutes,
                    item.b_trip_count,
                ),
                ideal_trip_count_float=float(item.demand_share * total),
                min_trip_count=item.minimum,
                max_trip_count=item.maximum,
                max_trip_count_provenance=item.maximum_provenance,
                nominal_headway=nominal_service_headway_minutes_v1(
                    item.regime.duration_minutes,
                    count,
                ),
                best_integer_headway_proxy=proxy,
                headway_quantization_error=(
                    float(quantization) if quantization is not None else None
                ),
                observed_demand_per_allocated_trip=item.regime.demand_sum / count,
                service_floor_binding=count == item.minimum,
            )
        )
    typed_allocations = tuple(allocations)
    headways = tuple(item.nominal_headway for item in typed_allocations)
    numeric_headways = tuple(item for item in headways if item is not None)
    total_duration = sum(item.duration_minutes for item in typed_allocations)
    differences = tuple(item.allocated_trip_count - item.b_trip_count for item in typed_allocations)
    return TripAllocationCandidateV1(
        candidate_id=candidate_id,
        status=status,
        direction=inputs[0].regime.direction,
        total_trips=total,
        regime_allocations=typed_allocations,
        demand_mismatch=float(record.demand_mismatch),
        demand_mismatch_improvement_vs_b=float(b_record.demand_mismatch - record.demand_mismatch),
        moved_trips=record.moved_trips,
        compile_quality_score=float(record.compile_quality),
        minimum_nominal_headway=min(numeric_headways),
        maximum_nominal_headway=max(numeric_headways),
        duration_weighted_average_nominal_headway=(
            sum(item.duration_minutes * float(item.nominal_headway) for item in typed_allocations)
            / total_duration
        ),
        largest_trip_increase_vs_b=max(differences, default=0),
        largest_trip_decrease_vs_b=min(differences, default=0),
        changed_regime_count=sum(item != 0 for item in differences),
        service_floor_provenance=BASELINE_DERIVED_SERVICE_FLOOR,
        merge_hints=_merge_hints(typed_allocations),
    )


def allocate_validated_demand_regimes_v1(
    plan: DemandRegimePlanV1,
    scenario_b: ScenarioBInput,
    *,
    evidence_status: str,
    config: DeterministicTripAllocatorConfigV1 = DEFAULT_DETERMINISTIC_TRIP_ALLOCATOR_CONFIG_V1,
) -> TripAllocationCandidateSetV1:
    """Build B/C1/C2/C3 integer candidates without generating departure times."""

    prepared = _validate_and_prepare(plan, scenario_b, evidence_status, config)
    if isinstance(prepared, TripAllocationCandidateSetV1):
        return prepared
    inputs, total, floor_headway = prepared
    records, state_count = _generate_records(inputs, total, config.minimum_headway_minutes)
    if not records:  # pragma: no cover - bounds checks make this defensive
        return _invalid_result(
            plan,
            evidence_status,
            total,
            INFEASIBLE_ALLOCATION_UPPER_BOUNDS,
            "bounded dynamic programming found no exact-total allocation",
            status=TripAllocationSetStatusV1.INFEASIBLE,
            config=config,
        )
    b_vector = tuple(item.b_trip_count for item in inputs)
    b_record = _record_for_vector(b_vector, inputs, total, config.minimum_headway_minutes)
    c1_record = min(
        records,
        key=lambda item: (
            item.demand_mismatch,
            item.compile_quality,
            item.moved_trips,
            item.vector,
        ),
    )
    epsilon = Fraction(Decimal(str(config.improvement_epsilon)))
    improving = tuple(
        item for item in records if item.demand_mismatch < b_record.demand_mismatch - epsilon
    )
    if improving:
        c2_record = min(
            improving,
            key=lambda item: (
                item.moved_trips,
                item.demand_mismatch,
                item.compile_quality,
                item.vector,
            ),
        )
        c2_status = TripAllocationCandidateStatusV1.SUCCESS
    else:
        c2_record = b_record
        c2_status = TripAllocationCandidateStatusV1.NO_IMPROVING_CONSERVATIVE_ALLOCATION
    frontier = _pareto_frontier(records, b_record, c1_record)
    c3_record = _balanced_record(frontier, b_record, c1_record)
    return TripAllocationCandidateSetV1(
        allocator_profile=DETERMINISTIC_TRIP_ALLOCATOR_PROFILE_V1,
        status=TripAllocationSetStatusV1.SUCCESS,
        direction=plan.direction,
        evidence_status=evidence_status,
        total_trips=total,
        service_floor_provenance=BASELINE_DERIVED_SERVICE_FLOOR,
        service_floor_headway_minutes=float(floor_headway),
        minimum_headway_policy_minutes=config.minimum_headway_minutes,
        b_reference=_candidate(
            "B_REFERENCE",
            TripAllocationCandidateStatusV1.SUCCESS,
            b_record,
            b_record,
            inputs,
            total,
            config.minimum_headway_minutes,
        ),
        c1_demand_fit=_candidate(
            "C1_DEMAND_FIT",
            TripAllocationCandidateStatusV1.SUCCESS,
            c1_record,
            b_record,
            inputs,
            total,
            config.minimum_headway_minutes,
        ),
        c2_conservative=_candidate(
            "C2_CONSERVATIVE",
            c2_status,
            c2_record,
            b_record,
            inputs,
            total,
            config.minimum_headway_minutes,
        ),
        c3_balanced=_candidate(
            "C3_BALANCED",
            TripAllocationCandidateStatusV1.SUCCESS,
            c3_record,
            b_record,
            inputs,
            total,
            config.minimum_headway_minutes,
        ),
        feasible_dp_state_count=state_count,
        pareto_frontier_size=len(frontier),
    )


def trip_allocation_candidate_set_to_dict_v1(
    result: TripAllocationCandidateSetV1,
) -> dict[str, object]:
    def allocation_to_dict(item: RegimeAllocationEvidenceV1) -> dict[str, object]:
        return {
            "regime_id": item.regime_id,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "duration_minutes": item.duration_minutes,
            "demand_sum": item.demand_sum,
            "demand_share": item.demand_share,
            "b_trip_count": item.b_trip_count,
            "b_service_share": item.b_service_share,
            "b_nominal_headway": item.b_nominal_headway,
            "ideal_trip_count_float": item.ideal_trip_count_float,
            "min_trip_count": item.min_trip_count,
            "max_trip_count": item.max_trip_count,
            "max_trip_count_provenance": item.max_trip_count_provenance,
            "allocated_trip_count": item.allocated_trip_count,
            "nominal_headway": item.nominal_headway,
            "best_integer_headway_proxy": item.best_integer_headway_proxy,
            "headway_quantization_error": item.headway_quantization_error,
            "observed_demand_per_allocated_trip": item.observed_demand_per_allocated_trip,
            "service_floor_binding": item.service_floor_binding,
        }

    def candidate_to_dict(item: TripAllocationCandidateV1 | None) -> dict[str, object] | None:
        if item is None:
            return None
        return {
            "candidate_id": item.candidate_id,
            "status": item.status.value,
            "direction": item.direction.value,
            "total_trips": item.total_trips,
            "regime_allocations": [allocation_to_dict(row) for row in item.regime_allocations],
            "demand_mismatch": item.demand_mismatch,
            "demand_mismatch_improvement_vs_b": item.demand_mismatch_improvement_vs_b,
            "moved_trips": item.moved_trips,
            "compile_quality_score": item.compile_quality_score,
            "minimum_nominal_headway": item.minimum_nominal_headway,
            "maximum_nominal_headway": item.maximum_nominal_headway,
            "duration_weighted_average_nominal_headway": (
                item.duration_weighted_average_nominal_headway
            ),
            "largest_trip_increase_vs_b": item.largest_trip_increase_vs_b,
            "largest_trip_decrease_vs_b": item.largest_trip_decrease_vs_b,
            "changed_regime_count": item.changed_regime_count,
            "service_floor_provenance": item.service_floor_provenance,
            "merge_hints": [
                {
                    "boundary_time": hint.boundary_time,
                    "earlier_regime_id": hint.earlier_regime_id,
                    "later_regime_id": hint.later_regime_id,
                    "earlier_integer_headway_proxy": hint.earlier_integer_headway_proxy,
                    "later_integer_headway_proxy": hint.later_integer_headway_proxy,
                    "same_integer_headway_proxy": hint.same_integer_headway_proxy,
                    "service_rate_merge_candidate": hint.service_rate_merge_candidate,
                }
                for hint in item.merge_hints
            ],
        }

    return {
        "allocator_profile": result.allocator_profile,
        "status": result.status.value,
        "direction": result.direction.value,
        "evidence_status": result.evidence_status,
        "total_trips": result.total_trips,
        "service_floor_provenance": result.service_floor_provenance,
        "service_floor_headway_minutes": result.service_floor_headway_minutes,
        "minimum_headway_policy_minutes": result.minimum_headway_policy_minutes,
        "feasible_dp_state_count": result.feasible_dp_state_count,
        "pareto_frontier_size": result.pareto_frontier_size,
        "failure_code": result.failure_code,
        "failure_message": result.failure_message,
        "b_reference": candidate_to_dict(result.b_reference),
        "c1_demand_fit": candidate_to_dict(result.c1_demand_fit),
        "c2_conservative": candidate_to_dict(result.c2_conservative),
        "c3_balanced": candidate_to_dict(result.c3_balanced),
    }


__all__ = [
    "BASELINE_DERIVED_SERVICE_FLOOR",
    "DAILY_VALIDATED",
    "DEFAULT_DETERMINISTIC_TRIP_ALLOCATOR_CONFIG_V1",
    "DETERMINISTIC_TRIP_ALLOCATOR_PROFILE_V1",
    "INFEASIBLE_ALLOCATION_UPPER_BOUNDS",
    "INFEASIBLE_SERVICE_FLOORS",
    "INVALID_ALLOCATION_INPUT",
    "NO_IMPROVING_CONSERVATIVE_ALLOCATION",
    "DeterministicTripAllocatorConfigV1",
    "RegimeAllocationEvidenceV1",
    "ServiceRegimeMergeHintV1",
    "TripAllocationCandidateSetV1",
    "TripAllocationCandidateStatusV1",
    "TripAllocationCandidateV1",
    "TripAllocationSetStatusV1",
    "allocate_validated_demand_regimes_v1",
    "trip_allocation_candidate_set_to_dict_v1",
]
