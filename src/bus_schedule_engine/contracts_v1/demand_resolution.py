from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .demand_coverage import DemandCoverageAssessmentV1
from .models import (
    CONTRACT_VERSION,
    ContractDirection,
    DemandConfidence,
    DemandObservation,
    DemandResolutionType,
    ObservedDemandInput,
    VolumeClassification,
)


class DemandResolutionError(ValueError):
    """Raised when authoritative demand blocks cannot be built without inventing data."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(f"{code}: {message}" if code is not None else message)
        self.code = code


class BlockMode(StrEnum):
    NATIVE = "native"
    ADAPTIVE = "adaptive"
    MANUAL = "manual"


class SmoothingMethod(StrEnum):
    NONE = "none"
    MOVING_AVERAGE = "moving_average"
    MEDIAN = "median"
    APPROVED_CUSTOM = "approved_custom"


class InterpolationMethod(StrEnum):
    NONE = "none"
    STEP = "step"
    PROPORTIONAL = "proportional"
    APPROVED_CUSTOM = "approved_custom"


class AggregationMethod(StrEnum):
    NONE = "none"
    SUM = "sum"
    WEIGHTED_SUM = "weighted_sum"
    APPROVED_CUSTOM = "approved_custom"


class InterpolationStatus(StrEnum):
    NONE = "none"
    AGGREGATED = "aggregated"
    INTERPOLATED_SUPPORTED = "interpolated_supported"
    UNSUPPORTED = "unsupported"


class BlockBoundaryReason(StrEnum):
    SOURCE_BOUNDARY = "source_boundary"
    SUSTAINED_CHANGE = "sustained_change"
    MANUAL = "manual"
    OPERATING_WINDOW = "operating_window"
    CRITICAL_CONDITION_PROTECTION = "critical_condition_protection"
    DIRECTION_CHANGE_PROTECTION = "direction_change_protection"


_CONFIDENCE_RANK = {
    DemandConfidence.UNKNOWN: 0,
    DemandConfidence.LOW: 1,
    DemandConfidence.MEDIUM: 2,
    DemandConfidence.HIGH: 3,
}

_RESOLUTION_COARSENESS = {
    DemandResolutionType.TIMESTAMP: 0,
    DemandResolutionType.TRIP: 1,
    DemandResolutionType.REGULAR_INTERVAL: 2,
    DemandResolutionType.IRREGULAR_INTERVAL: 3,
    DemandResolutionType.DAILY_TOTAL: 4,
}


@dataclass(frozen=True, slots=True)
class DemandBlockPolicyV1:
    block_mode: BlockMode = BlockMode.NATIVE
    manual_boundaries: tuple[int, ...] = ()
    minimum_block_duration: int = 1
    maximum_block_duration: int = 120
    minimum_sustained_intervals: int = 2
    material_change_ratio: float = 0.20
    smoothing_method: SmoothingMethod = SmoothingMethod.NONE
    interpolation_method: InterpolationMethod = InterpolationMethod.NONE


@dataclass(frozen=True, slots=True)
class DemandResolutionContractV1:
    source_resolution_type: DemandResolutionType
    source_resolution_minutes: int | None
    source_is_timestamp_level: bool
    source_is_trip_level: bool
    source_is_irregular: bool
    block_mode: BlockMode
    manual_boundaries: tuple[int, ...]
    minimum_block_duration: int
    maximum_block_duration: int
    minimum_sustained_intervals: int
    material_change_ratio: float
    smoothing_method: SmoothingMethod
    interpolation_method: InterpolationMethod
    confidence_level: DemandConfidence
    observation_days: int
    sample_count: int

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class DemandAnalysisBlockV1:
    block_id: str
    start_time: int
    end_time: int
    direction: ContractDirection
    observed_passengers: float
    source_interval_ids: tuple[str, ...]
    source_resolution_type: DemandResolutionType
    source_resolution_minutes: int | None
    block_mode: BlockMode
    aggregation_method: AggregationMethod
    confidence: DemandConfidence
    interpolation_status: InterpolationStatus
    observation_days: int
    sample_count: int
    block_boundary_reason: BlockBoundaryReason

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION

    @property
    def duration_minutes(self) -> int:
        duration_seconds = self.end_time - self.start_time
        if duration_seconds <= 0 or duration_seconds % 60:
            raise DemandResolutionError(
                f"Block {self.block_id} duration must be a positive whole number of minutes"
            )
        return duration_seconds // 60

    @property
    def demand_rate_per_hour(self) -> float:
        return self.observed_passengers * 60 / self.duration_minutes


@dataclass(frozen=True, slots=True)
class DemandResolutionResultV1:
    contract: DemandResolutionContractV1
    blocks: tuple[DemandAnalysisBlockV1, ...]
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    coverage_assessment: DemandCoverageAssessmentV1 | None = None


@dataclass(frozen=True, slots=True)
class _NativeInterval:
    observation_id: str
    start_time: int
    end_time: int
    direction: ContractDirection
    passengers: float
    source_resolution_type: DemandResolutionType
    source_resolution_minutes: int | None
    confidence: DemandConfidence
    sample_count: int

    @property
    def duration_minutes(self) -> int:
        duration_seconds = self.end_time - self.start_time
        if duration_seconds <= 0 or duration_seconds % 60:
            raise DemandResolutionError(
                f"Observation {self.observation_id} must span a positive whole number of minutes"
            )
        return duration_seconds // 60

    @property
    def rate_per_hour(self) -> float:
        return self.passengers * 60 / self.duration_minutes


def _weakest_confidence(values: list[DemandConfidence]) -> DemandConfidence:
    if not values:
        return DemandConfidence.UNKNOWN
    return min(values, key=lambda item: _CONFIDENCE_RANK[item])


def _normalized_passengers(observation: DemandObservation, observation_days: int) -> float:
    if observation.volume_classification == VolumeClassification.AVERAGE_DAY:
        return float(observation.passenger_count)
    if observation_days <= 0:
        raise DemandResolutionError("observation_days must be positive")
    return float(observation.passenger_count) / observation_days


def _source_resolution_type(demand: ObservedDemandInput) -> DemandResolutionType:
    types = {item.source_resolution_type for item in demand.observations}
    if not types:
        raise DemandResolutionError("Observed demand has no observations")
    if len(types) == 1:
        return next(iter(types))
    return max(types, key=lambda item: _RESOLUTION_COARSENESS[item])


def _source_resolution_minutes(demand: ObservedDemandInput) -> int | None:
    values = {
        item.source_resolution_minutes
        for item in demand.observations
        if item.source_resolution_minutes is not None
    }
    return next(iter(values)) if len(values) == 1 else None


def detect_demand_resolution_v1(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1 | None = None,
) -> DemandResolutionContractV1:
    policy = policy or DemandBlockPolicyV1()
    if demand.observation_days <= 0:
        raise DemandResolutionError("observation_days must be positive")
    if policy.minimum_block_duration <= 0:
        raise DemandResolutionError("minimum_block_duration must be positive")
    if policy.maximum_block_duration < policy.minimum_block_duration:
        raise DemandResolutionError(
            "maximum_block_duration must be greater than or equal to minimum_block_duration"
        )
    if policy.minimum_sustained_intervals <= 0:
        raise DemandResolutionError("minimum_sustained_intervals must be positive")
    if policy.material_change_ratio < 0:
        raise DemandResolutionError("material_change_ratio must be non-negative")
    if policy.smoothing_method != SmoothingMethod.NONE:
        raise DemandResolutionError(
            "PR-02 authoritative implementation supports smoothing_method=none only"
        )

    source_type = _source_resolution_type(demand)
    confidence = _weakest_confidence([item.demand_confidence for item in demand.observations])
    sample_count = sum(item.sample_count or 0 for item in demand.observations)
    return DemandResolutionContractV1(
        source_resolution_type=source_type,
        source_resolution_minutes=_source_resolution_minutes(demand),
        source_is_timestamp_level=any(
            item.source_resolution_type == DemandResolutionType.TIMESTAMP
            for item in demand.observations
        ),
        source_is_trip_level=any(
            item.source_resolution_type == DemandResolutionType.TRIP for item in demand.observations
        ),
        source_is_irregular=(
            source_type == DemandResolutionType.IRREGULAR_INTERVAL
            or len({item.source_resolution_type for item in demand.observations}) > 1
        ),
        block_mode=policy.block_mode,
        manual_boundaries=tuple(policy.manual_boundaries),
        minimum_block_duration=policy.minimum_block_duration,
        maximum_block_duration=policy.maximum_block_duration,
        minimum_sustained_intervals=policy.minimum_sustained_intervals,
        material_change_ratio=policy.material_change_ratio,
        smoothing_method=policy.smoothing_method,
        interpolation_method=policy.interpolation_method,
        confidence_level=confidence,
        observation_days=demand.observation_days,
        sample_count=sample_count,
    )


def _native_intervals(demand: ObservedDemandInput) -> list[_NativeInterval]:
    intervals = [
        _NativeInterval(
            observation_id=item.observation_id,
            start_time=item.interval_start,
            end_time=item.interval_end,
            direction=item.direction,
            passengers=_normalized_passengers(item, demand.observation_days),
            source_resolution_type=item.source_resolution_type,
            source_resolution_minutes=item.source_resolution_minutes,
            confidence=item.demand_confidence,
            sample_count=item.sample_count or 0,
        )
        for item in demand.observations
        if item.source_resolution_type != DemandResolutionType.DAILY_TOTAL
    ]
    return sorted(
        intervals,
        key=lambda item: (
            item.direction.value,
            item.start_time,
            item.end_time,
            item.observation_id,
        ),
    )


def _block_id(direction: ContractDirection, index: int) -> str:
    return f"DB-{direction.value.upper()}-{index:04d}"


def _native_blocks(demand: ObservedDemandInput) -> tuple[DemandAnalysisBlockV1, ...]:
    counters: dict[ContractDirection, int] = {}
    blocks: list[DemandAnalysisBlockV1] = []
    for interval in _native_intervals(demand):
        counters[interval.direction] = counters.get(interval.direction, 0) + 1
        blocks.append(
            DemandAnalysisBlockV1(
                block_id=_block_id(interval.direction, counters[interval.direction]),
                start_time=interval.start_time,
                end_time=interval.end_time,
                direction=interval.direction,
                observed_passengers=interval.passengers,
                source_interval_ids=(interval.observation_id,),
                source_resolution_type=interval.source_resolution_type,
                source_resolution_minutes=interval.source_resolution_minutes,
                block_mode=BlockMode.NATIVE,
                aggregation_method=AggregationMethod.NONE,
                confidence=interval.confidence,
                interpolation_status=InterpolationStatus.NONE,
                observation_days=demand.observation_days,
                sample_count=interval.sample_count,
                block_boundary_reason=BlockBoundaryReason.SOURCE_BOUNDARY,
            )
        )
    return tuple(blocks)


def _relative_change(left: float, right: float) -> float:
    denominator = max(abs(left), 1e-9)
    return abs(right - left) / denominator


def _protected_boundaries(
    intervals: list[_NativeInterval],
    policy: DemandBlockPolicyV1,
) -> set[int]:
    protected: set[int] = set()
    for index in range(1, len(intervals)):
        left = intervals[index - 1]
        right = intervals[index]
        if left.end_time != right.start_time:
            protected.add(index)
            continue
        if left.source_resolution_type != right.source_resolution_type:
            protected.add(index)
            continue
        if (left.passengers == 0) != (right.passengers == 0):
            protected.add(index)
            continue
        if _relative_change(left.rate_per_hour, right.rate_per_hour) < policy.material_change_ratio:
            continue
        window = intervals[index : index + policy.minimum_sustained_intervals]
        if len(window) < policy.minimum_sustained_intervals:
            continue
        increasing = right.rate_per_hour > left.rate_per_hour
        sustained = all(
            item.start_time == (right.start_time if offset == 0 else window[offset - 1].end_time)
            and (
                item.rate_per_hour >= left.rate_per_hour * (1 + policy.material_change_ratio)
                if increasing
                else item.rate_per_hour <= left.rate_per_hour * (1 - policy.material_change_ratio)
            )
            for offset, item in enumerate(window)
        )
        if sustained:
            protected.add(index)
    return protected


def _merge_group(
    group: list[_NativeInterval],
    *,
    block_id: str,
    mode: BlockMode,
    reason: BlockBoundaryReason,
    observation_days: int,
) -> DemandAnalysisBlockV1:
    source_types = {item.source_resolution_type for item in group}
    source_type = (
        next(iter(source_types))
        if len(source_types) == 1
        else DemandResolutionType.IRREGULAR_INTERVAL
    )
    resolution_values = {
        item.source_resolution_minutes
        for item in group
        if item.source_resolution_minutes is not None
    }
    return DemandAnalysisBlockV1(
        block_id=block_id,
        start_time=group[0].start_time,
        end_time=group[-1].end_time,
        direction=group[0].direction,
        observed_passengers=sum(item.passengers for item in group),
        source_interval_ids=tuple(item.observation_id for item in group),
        source_resolution_type=source_type,
        source_resolution_minutes=(
            next(iter(resolution_values)) if len(resolution_values) == 1 else None
        ),
        block_mode=mode,
        aggregation_method=(AggregationMethod.NONE if len(group) == 1 else AggregationMethod.SUM),
        confidence=_weakest_confidence([item.confidence for item in group]),
        interpolation_status=(
            InterpolationStatus.NONE if len(group) == 1 else InterpolationStatus.AGGREGATED
        ),
        observation_days=observation_days,
        sample_count=sum(item.sample_count for item in group),
        block_boundary_reason=reason,
    )


def _adaptive_blocks(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1,
) -> tuple[DemandAnalysisBlockV1, ...]:
    by_direction: dict[ContractDirection, list[_NativeInterval]] = {}
    for interval in _native_intervals(demand):
        by_direction.setdefault(interval.direction, []).append(interval)

    output: list[DemandAnalysisBlockV1] = []
    for direction in sorted(by_direction, key=lambda item: item.value):
        intervals = by_direction[direction]
        protected = _protected_boundaries(intervals, policy)
        groups: list[tuple[list[_NativeInterval], BlockBoundaryReason]] = []
        current = [intervals[0]]
        current_reason = BlockBoundaryReason.SOURCE_BOUNDARY
        for index in range(1, len(intervals)):
            candidate = intervals[index]
            combined_minutes = (candidate.end_time - current[0].start_time) // 60
            can_merge = (
                index not in protected
                and current[-1].end_time == candidate.start_time
                and combined_minutes <= policy.maximum_block_duration
            )
            if can_merge:
                current.append(candidate)
                continue
            groups.append((current, current_reason))
            current = [candidate]
            current_reason = (
                BlockBoundaryReason.SUSTAINED_CHANGE
                if index in protected
                else BlockBoundaryReason.SOURCE_BOUNDARY
            )
        groups.append((current, current_reason))

        for index, (group, reason) in enumerate(groups, start=1):
            output.append(
                _merge_group(
                    group,
                    block_id=_block_id(direction, index),
                    mode=BlockMode.ADAPTIVE,
                    reason=reason,
                    observation_days=demand.observation_days,
                )
            )
    return tuple(output)


def _manual_blocks(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1,
) -> tuple[DemandAnalysisBlockV1, ...]:
    boundaries = tuple(sorted(set(policy.manual_boundaries)))
    if len(boundaries) < 2:
        raise DemandResolutionError("Manual mode requires at least two unique boundaries")
    if boundaries != tuple(policy.manual_boundaries):
        raise DemandResolutionError("Manual boundaries must be unique and chronological")

    intervals = _native_intervals(demand)
    if not intervals:
        return ()
    coverage_start = min(item.start_time for item in intervals)
    coverage_end = max(item.end_time for item in intervals)
    if boundaries[0] != coverage_start or boundaries[-1] != coverage_end:
        raise DemandResolutionError(
            "Manual boundaries must cover the complete observed intraday demand window"
        )
    for boundary in boundaries[1:-1]:
        cutting = [
            item.observation_id for item in intervals if item.start_time < boundary < item.end_time
        ]
        if cutting:
            raise DemandResolutionError(
                "Manual boundaries may not split source intervals without supported event-level "
                f"interpolation; affected observations: {', '.join(cutting)}"
            )

    by_direction: dict[ContractDirection, list[_NativeInterval]] = {}
    for interval in intervals:
        by_direction.setdefault(interval.direction, []).append(interval)

    output: list[DemandAnalysisBlockV1] = []
    for direction in sorted(by_direction, key=lambda item: item.value):
        index = 0
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            selected = [
                item
                for item in by_direction[direction]
                if start <= item.start_time and item.end_time <= end
            ]
            if not selected:
                continue
            ordered = sorted(selected, key=lambda item: (item.start_time, item.end_time))
            if ordered[0].start_time != start or ordered[-1].end_time != end:
                raise DemandResolutionError(
                    f"Manual block {start}-{end} does not have complete source coverage for "
                    f"direction {direction.value}"
                )
            if any(
                left.end_time != right.start_time
                for left, right in zip(ordered, ordered[1:], strict=False)
            ):
                raise DemandResolutionError(
                    f"Manual block {start}-{end} contains an unexplained demand gap"
                )
            index += 1
            output.append(
                _merge_group(
                    ordered,
                    block_id=_block_id(direction, index),
                    mode=BlockMode.MANUAL,
                    reason=BlockBoundaryReason.MANUAL,
                    observation_days=demand.observation_days,
                )
            )
    return tuple(output)


def build_demand_analysis_blocks_v1(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1 | None = None,
) -> DemandResolutionResultV1:
    policy = policy or DemandBlockPolicyV1()
    contract = detect_demand_resolution_v1(demand, policy)
    if contract.source_resolution_type == DemandResolutionType.DAILY_TOTAL:
        return DemandResolutionResultV1(
            contract=contract,
            blocks=(),
            limitations=(
                "Daily-total-only demand cannot support authoritative intraday demand blocks.",
            ),
        )
    if any(
        item.source_resolution_type == DemandResolutionType.DAILY_TOTAL
        for item in demand.observations
    ):
        raise DemandResolutionError(
            "Mixed daily-total and intraday demand must be separated into distinct datasets"
        )

    if policy.block_mode == BlockMode.NATIVE:
        blocks = _native_blocks(demand)
    elif policy.block_mode == BlockMode.ADAPTIVE:
        blocks = _adaptive_blocks(demand, policy)
    else:
        blocks = _manual_blocks(demand, policy)

    for block in blocks:
        if block.duration_minutes < policy.minimum_block_duration:
            raise DemandResolutionError(
                f"Block {block.block_id} is shorter than minimum_block_duration"
            )
        if block.duration_minutes > policy.maximum_block_duration:
            raise DemandResolutionError(f"Block {block.block_id} exceeds maximum_block_duration")
    return DemandResolutionResultV1(contract=contract, blocks=blocks)
