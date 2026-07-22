from __future__ import annotations

from collections import defaultdict

from bus_schedule_engine.contracts_v1.models import (
    ContractDirection,
    DemandConfidence,
    DemandObservation,
    DemandResolutionType,
    ObservedDemandInput,
    VolumeClassification,
)

from .models import (
    AggregationMethod,
    BlockBoundaryReason,
    DemandAnalysisBlock,
    DemandBlockMode,
    DemandResolutionEvidence,
    DemandResolutionPolicy,
    InterpolationStatus,
)


class DemandResolutionError(ValueError):
    pass


_CONFIDENCE_RANK = {
    DemandConfidence.UNKNOWN: 0,
    DemandConfidence.LOW: 1,
    DemandConfidence.MEDIUM: 2,
    DemandConfidence.HIGH: 3,
}


def _weakest_confidence(items: tuple[DemandObservation, ...]) -> DemandConfidence:
    return min((item.demand_confidence for item in items), key=_CONFIDENCE_RANK.get)


def _average_day_count(item: DemandObservation, observation_days: int) -> float:
    if item.volume_classification == VolumeClassification.AVERAGE_DAY:
        return float(item.passenger_count)
    if observation_days <= 0:
        raise DemandResolutionError("observation_days must be positive")
    return float(item.passenger_count) / observation_days


def detect_resolution(
    demand: ObservedDemandInput,
    policy: DemandResolutionPolicy,
) -> DemandResolutionEvidence:
    if not demand.observations:
        raise DemandResolutionError("demand observations are required")
    types = {item.source_resolution_type for item in demand.observations}
    if DemandResolutionType.DAILY_TOTAL in types:
        resolution_type = DemandResolutionType.DAILY_TOTAL
        resolution_minutes = None
    elif len(types) == 1:
        resolution_type = next(iter(types))
        minute_values = {
            item.source_resolution_minutes
            for item in demand.observations
            if item.source_resolution_minutes is not None
        }
        resolution_minutes = next(iter(minute_values)) if len(minute_values) == 1 else None
    else:
        resolution_type = DemandResolutionType.IRREGULAR_INTERVAL
        resolution_minutes = None
    sample_count = sum(item.sample_count or 0 for item in demand.observations)
    return DemandResolutionEvidence(
        source_resolution_type=resolution_type,
        source_resolution_minutes=resolution_minutes,
        source_is_timestamp_level=DemandResolutionType.TIMESTAMP in types,
        source_is_trip_level=DemandResolutionType.TRIP in types,
        source_is_irregular=(
            resolution_type == DemandResolutionType.IRREGULAR_INTERVAL or len(types) > 1
        ),
        block_mode=policy.block_mode,
        manual_boundaries=policy.manual_boundaries,
        minimum_block_duration=policy.minimum_block_duration,
        maximum_block_duration=policy.maximum_block_duration,
        minimum_sustained_intervals=policy.minimum_sustained_intervals,
        material_change_ratio=policy.material_change_ratio,
        smoothing_method=policy.smoothing_method,
        interpolation_method=policy.interpolation_method,
        confidence_level=_weakest_confidence(demand.observations),
        observation_days=demand.observation_days,
        sample_count=sample_count,
    )


def _native_blocks(demand: ObservedDemandInput) -> tuple[DemandAnalysisBlock, ...]:
    blocks: list[DemandAnalysisBlock] = []
    for index, item in enumerate(
        sorted(
            demand.observations,
            key=lambda value: (value.interval_start, value.interval_end, value.direction.value),
        ),
        start=1,
    ):
        duration = item.interval_end - item.interval_start
        if duration <= 0 or duration % 60:
            raise DemandResolutionError(f"invalid demand interval: {item.observation_id}")
        if item.source_resolution_type == DemandResolutionType.DAILY_TOTAL:
            continue
        blocks.append(
            DemandAnalysisBlock(
                block_id=f"DB-{index:04d}",
                start_time=item.interval_start,
                end_time=item.interval_end,
                direction=item.direction,
                observed_passengers=_average_day_count(item, demand.observation_days),
                source_interval_ids=(item.observation_id,),
                source_resolution_type=item.source_resolution_type,
                source_resolution_minutes=item.source_resolution_minutes,
                block_mode=DemandBlockMode.NATIVE,
                aggregation_method=AggregationMethod.NONE,
                confidence=item.demand_confidence,
                interpolation_status=InterpolationStatus.NONE,
                observation_days=demand.observation_days,
                sample_count=item.sample_count or 0,
                block_boundary_reason=BlockBoundaryReason.SOURCE_BOUNDARY,
            )
        )
    return tuple(blocks)


def _aggregate_group(
    group: tuple[DemandAnalysisBlock, ...],
    *,
    block_id: str,
    mode: DemandBlockMode,
    reason: BlockBoundaryReason,
) -> DemandAnalysisBlock:
    first, last = group[0], group[-1]
    return DemandAnalysisBlock(
        block_id=block_id,
        start_time=first.start_time,
        end_time=last.end_time,
        direction=first.direction,
        observed_passengers=sum(item.observed_passengers for item in group),
        source_interval_ids=tuple(
            source_id for item in group for source_id in item.source_interval_ids
        ),
        source_resolution_type=(
            first.source_resolution_type
            if len({item.source_resolution_type for item in group}) == 1
            else DemandResolutionType.IRREGULAR_INTERVAL
        ),
        source_resolution_minutes=(
            first.source_resolution_minutes
            if len({item.source_resolution_minutes for item in group}) == 1
            else None
        ),
        block_mode=mode,
        aggregation_method=AggregationMethod.SUM,
        confidence=min((item.confidence for item in group), key=_CONFIDENCE_RANK.get),
        interpolation_status=InterpolationStatus.AGGREGATED,
        observation_days=first.observation_days,
        sample_count=sum(item.sample_count for item in group),
        block_boundary_reason=reason,
    )


def _manual_blocks(
    native: tuple[DemandAnalysisBlock, ...],
    policy: DemandResolutionPolicy,
) -> tuple[DemandAnalysisBlock, ...]:
    boundaries = tuple(sorted(set(policy.manual_boundaries)))
    source_boundaries = {item.start_time for item in native} | {item.end_time for item in native}
    unsupported = [value for value in boundaries if value not in source_boundaries]
    if unsupported:
        raise DemandResolutionError(
            "manual boundaries may not split source intervals without supported evidence"
        )
    output: list[DemandAnalysisBlock] = []
    sequence = (min(source_boundaries), *boundaries, max(source_boundaries))
    for direction in ContractDirection:
        directional = tuple(item for item in native if item.direction == direction)
        if not directional:
            continue
        for start, end in zip(sequence, sequence[1:], strict=True):
            group = tuple(
                item for item in directional if item.start_time >= start and item.end_time <= end
            )
            if group:
                output.append(
                    _aggregate_group(
                        group,
                        block_id=f"DB-{len(output) + 1:04d}",
                        mode=DemandBlockMode.MANUAL,
                        reason=BlockBoundaryReason.MANUAL,
                    )
                )
    return tuple(sorted(output, key=lambda item: (item.start_time, item.direction.value)))


def _adaptive_blocks(
    native: tuple[DemandAnalysisBlock, ...],
    policy: DemandResolutionPolicy,
) -> tuple[DemandAnalysisBlock, ...]:
    if policy.smoothing_method != "none" or policy.interpolation_method != "none":
        raise DemandResolutionError("PR-02 supports adaptive mode only with no smoothing/interpolation")
    output: list[DemandAnalysisBlock] = []
    by_direction: dict[ContractDirection, list[DemandAnalysisBlock]] = defaultdict(list)
    for item in native:
        by_direction[item.direction].append(item)
    for direction in sorted(by_direction, key=lambda item: item.value):
        current: list[DemandAnalysisBlock] = []
        for item in sorted(by_direction[direction], key=lambda value: value.start_time):
            if not current:
                current = [item]
                continue
            previous = current[-1]
            current_duration = (item.end_time - current[0].start_time) // 60
            previous_rate = previous.demand_rate_per_hour
            change_ratio = (
                abs(item.demand_rate_per_hour - previous_rate) / previous_rate
                if previous_rate > 0
                else (0.0 if item.demand_rate_per_hour == 0 else float("inf"))
            )
            can_merge = (
                previous.end_time == item.start_time
                and current_duration <= policy.maximum_block_duration
                and change_ratio < policy.material_change_ratio
            )
            if can_merge:
                current.append(item)
            else:
                output.append(
                    _aggregate_group(
                        tuple(current),
                        block_id=f"DB-{len(output) + 1:04d}",
                        mode=DemandBlockMode.ADAPTIVE,
                        reason=BlockBoundaryReason.SUSTAINED_CHANGE,
                    )
                )
                current = [item]
        if current:
            output.append(
                _aggregate_group(
                    tuple(current),
                    block_id=f"DB-{len(output) + 1:04d}",
                    mode=DemandBlockMode.ADAPTIVE,
                    reason=BlockBoundaryReason.SUSTAINED_CHANGE,
                )
            )
    return tuple(sorted(output, key=lambda item: (item.start_time, item.direction.value)))


def build_demand_blocks(
    demand: ObservedDemandInput,
    policy: DemandResolutionPolicy | None = None,
) -> tuple[DemandResolutionEvidence, tuple[DemandAnalysisBlock, ...]]:
    selected = policy or DemandResolutionPolicy()
    evidence = detect_resolution(demand, selected)
    if evidence.source_resolution_type == DemandResolutionType.DAILY_TOTAL:
        return evidence, ()
    native = _native_blocks(demand)
    if selected.block_mode == DemandBlockMode.NATIVE:
        return evidence, native
    if selected.block_mode == DemandBlockMode.MANUAL:
        return evidence, _manual_blocks(native, selected)
    return evidence, _adaptive_blocks(native, selected)
