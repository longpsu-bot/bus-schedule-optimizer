from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from bus_schedule_engine.time_utils import format_hhmm

from .models import (
    ContractDirection,
    DemandConfidence,
    DemandObservation,
    DemandResolutionType,
    NormalizedInputBundleV1,
    ScenarioCOptimizationModeV1,
    ScenarioId,
)

OVERLAPPING_DEMAND_OBSERVATIONS = "OVERLAPPING_DEMAND_OBSERVATIONS"
MIXED_DIRECTION_GRAIN_OVERLAP = "MIXED_DIRECTION_GRAIN_OVERLAP"
DEMAND_TEMPORAL_COVERAGE_GAP = "DEMAND_TEMPORAL_COVERAGE_GAP"
DEMAND_SERVICE_WINDOW_NOT_COVERED = "DEMAND_SERVICE_WINDOW_NOT_COVERED"
DEMAND_DEPARTURE_NOT_COVERED = "DEMAND_DEPARTURE_NOT_COVERED"
DEMAND_DIRECTION_STREAM_MISSING = "DEMAND_DIRECTION_STREAM_MISSING"
MIXED_DIRECTION_GRAIN_PARTIAL_SUPPORT = "MIXED_DIRECTION_GRAIN_PARTIAL_SUPPORT"
COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE = "COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE"
COMBINED_DEMAND_UNSUPPORTED_FOR_DIRECTIONAL_C = "COMBINED_DEMAND_UNSUPPORTED_FOR_DIRECTIONAL_C"
DEMAND_COVERAGE_INCOMPLETE_FOR_C_GENERATION = "DEMAND_COVERAGE_INCOMPLETE_FOR_C_GENERATION"
DEMAND_COVERAGE_INCOMPLETE_FOR_AUTHORITATIVE_C = "DEMAND_COVERAGE_INCOMPLETE_FOR_AUTHORITATIVE_C"

_DIRECTION_ORDER = {
    ContractDirection.OUTBOUND: 0,
    ContractDirection.INBOUND: 1,
    ContractDirection.COMBINED: 2,
}
_CONFIDENCE_RANK = {
    DemandConfidence.UNKNOWN: 0,
    DemandConfidence.LOW: 1,
    DemandConfidence.MEDIUM: 2,
    DemandConfidence.HIGH: 3,
}


class DemandCoverageModeV1(StrEnum):
    DIRECTIONAL_ONLY = "directional_only"
    COMBINED_ONLY = "combined_only"
    MIXED_DIRECTION_GRAIN = "mixed_direction_grain"
    DAILY_TOTAL_ONLY = "daily_total_only"
    NO_INTRADAY_EVIDENCE = "no_intraday_evidence"


@dataclass(frozen=True, slots=True)
class DemandSourceDefectV1:
    code: str
    message: str
    observation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DemandCoverageSegmentV1:
    stream: ContractDirection
    start_time: int
    end_time: int
    observation_ids: tuple[str, ...]

    @property
    def duration_minutes(self) -> int:
        return (self.end_time - self.start_time) // 60


@dataclass(frozen=True, slots=True)
class DemandRequiredSpanV1:
    stream: ContractDirection
    start_time: int
    end_time: int


@dataclass(frozen=True, slots=True)
class DemandUncoveredSegmentV1:
    code: str
    stream: ContractDirection
    start_time: int
    end_time: int


@dataclass(frozen=True, slots=True)
class DemandUncoveredDepartureV1:
    scenario: ScenarioId
    direction: ContractDirection
    trip_id: str
    departure_time: int
    required_stream: ContractDirection


@dataclass(frozen=True, slots=True)
class DemandCoverageAssessmentV1:
    mode: DemandCoverageModeV1
    required_spans: tuple[DemandRequiredSpanV1, ...]
    source_segments: tuple[DemandCoverageSegmentV1, ...]
    uncovered_segments: tuple[DemandUncoveredSegmentV1, ...]
    uncovered_departures: tuple[DemandUncoveredDepartureV1, ...]
    present_streams: tuple[ContractDirection, ...]
    missing_streams: tuple[ContractDirection, ...]
    whole_b_suitability_supported: bool
    directional_c_generation_supported: bool
    evaluation_issue_codes: tuple[str, ...]
    generation_issue_codes: tuple[str, ...]
    evidence: tuple[str, ...]
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Departure:
    scenario: ScenarioId
    direction: ContractDirection
    trip_id: str
    departure_time: int


def _overlaps(left: DemandObservation, right: DemandObservation) -> bool:
    return max(left.interval_start, right.interval_start) < min(
        left.interval_end,
        right.interval_end,
    )


def demand_source_defects_v1(
    observations: tuple[DemandObservation, ...],
) -> tuple[DemandSourceDefectV1, ...]:
    intraday = tuple(
        item
        for item in observations
        if item.source_resolution_type != DemandResolutionType.DAILY_TOTAL
    )
    defects: list[DemandSourceDefectV1] = []
    for direction in (
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
        ContractDirection.COMBINED,
    ):
        ordered = sorted(
            (item for item in intraday if item.direction == direction),
            key=lambda item: (
                item.interval_start,
                item.interval_end,
                item.observation_id,
            ),
        )
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                if right.interval_start >= left.interval_end:
                    break
                if _overlaps(left, right):
                    defects.append(
                        DemandSourceDefectV1(
                            code=OVERLAPPING_DEMAND_OBSERVATIONS,
                            message=(
                                "Overlapping demand observations are not authoritative "
                                f"within direction {direction.value}: "
                                f"{left.observation_id}, {right.observation_id}"
                            ),
                            observation_ids=(
                                left.observation_id,
                                right.observation_id,
                            ),
                        )
                    )

    combined = sorted(
        (item for item in intraday if item.direction == ContractDirection.COMBINED),
        key=lambda item: (
            item.interval_start,
            item.interval_end,
            item.observation_id,
        ),
    )
    directional = sorted(
        (item for item in intraday if item.direction != ContractDirection.COMBINED),
        key=lambda item: (
            _DIRECTION_ORDER[item.direction],
            item.interval_start,
            item.interval_end,
            item.observation_id,
        ),
    )
    for aggregate in combined:
        for component in directional:
            if _overlaps(aggregate, component):
                defects.append(
                    DemandSourceDefectV1(
                        code=MIXED_DIRECTION_GRAIN_OVERLAP,
                        message=(
                            "Combined and directional demand observations overlap without "
                            "an approved reconciliation policy: "
                            f"{aggregate.observation_id}, {component.observation_id}"
                        ),
                        observation_ids=(
                            aggregate.observation_id,
                            component.observation_id,
                        ),
                    )
                )
    return tuple(defects)


def _coverage_mode(
    observations: tuple[DemandObservation, ...],
) -> DemandCoverageModeV1:
    intraday_directions = {
        item.direction
        for item in observations
        if item.source_resolution_type != DemandResolutionType.DAILY_TOTAL
    }
    if not intraday_directions:
        if observations and all(
            item.source_resolution_type == DemandResolutionType.DAILY_TOTAL for item in observations
        ):
            return DemandCoverageModeV1.DAILY_TOTAL_ONLY
        return DemandCoverageModeV1.NO_INTRADAY_EVIDENCE
    has_combined = ContractDirection.COMBINED in intraday_directions
    has_directional = bool(
        intraday_directions
        & {
            ContractDirection.OUTBOUND,
            ContractDirection.INBOUND,
        }
    )
    if has_combined and has_directional:
        return DemandCoverageModeV1.MIXED_DIRECTION_GRAIN
    if has_combined:
        return DemandCoverageModeV1.COMBINED_ONLY
    return DemandCoverageModeV1.DIRECTIONAL_ONLY


def _source_segments(
    observations: tuple[DemandObservation, ...],
) -> tuple[DemandCoverageSegmentV1, ...]:
    by_stream: dict[ContractDirection, list[DemandObservation]] = {}
    for observation in observations:
        if observation.source_resolution_type == DemandResolutionType.DAILY_TOTAL:
            continue
        by_stream.setdefault(observation.direction, []).append(observation)

    output: list[DemandCoverageSegmentV1] = []
    for stream in sorted(by_stream, key=lambda item: _DIRECTION_ORDER[item]):
        ordered = sorted(
            by_stream[stream],
            key=lambda item: (
                item.interval_start,
                item.interval_end,
                item.observation_id,
            ),
        )
        start = ordered[0].interval_start
        end = ordered[0].interval_end
        observation_ids = [ordered[0].observation_id]
        for observation in ordered[1:]:
            if observation.interval_start <= end:
                end = max(end, observation.interval_end)
                observation_ids.append(observation.observation_id)
                continue
            output.append(
                DemandCoverageSegmentV1(
                    stream=stream,
                    start_time=start,
                    end_time=end,
                    observation_ids=tuple(observation_ids),
                )
            )
            start = observation.interval_start
            end = observation.interval_end
            observation_ids = [observation.observation_id]
        output.append(
            DemandCoverageSegmentV1(
                stream=stream,
                start_time=start,
                end_time=end,
                observation_ids=tuple(observation_ids),
            )
        )
    return tuple(output)


def _departures(bundle: NormalizedInputBundleV1) -> tuple[_Departure, ...]:
    output: list[_Departure] = []
    if (
        bundle.scenario_a is not None
        and bundle.optimization_mode == ScenarioCOptimizationModeV1.LEGACY_A_BOUND
    ):
        output.extend(
            _Departure(
                scenario=ScenarioId.A,
                direction=trip.direction,
                trip_id=trip.trip_id,
                departure_time=trip.departure_time,
            )
            for trip in bundle.scenario_a.exact_timetable
        )
    output.extend(
        _Departure(
            scenario=ScenarioId.B,
            direction=trip.direction,
            trip_id=trip.trip_id,
            departure_time=trip.departure_time,
        )
        for trip in bundle.scenario_b.exact_timetable
    )
    return tuple(
        sorted(
            output,
            key=lambda item: (
                _DIRECTION_ORDER[item.direction],
                item.departure_time,
                item.scenario.value,
                item.trip_id,
            ),
        )
    )


def _required_spans(
    departures: tuple[_Departure, ...],
) -> tuple[DemandRequiredSpanV1, ...]:
    output: list[DemandRequiredSpanV1] = []
    for direction in (
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
    ):
        times = [item.departure_time for item in departures if item.direction == direction]
        if times:
            output.append(
                DemandRequiredSpanV1(
                    stream=direction,
                    start_time=min(times),
                    end_time=max(times),
                )
            )
    all_times = [item.departure_time for item in departures]
    if all_times:
        output.append(
            DemandRequiredSpanV1(
                stream=ContractDirection.COMBINED,
                start_time=min(all_times),
                end_time=max(all_times),
            )
        )
    return tuple(output)


def _segments_for_stream(
    segments: tuple[DemandCoverageSegmentV1, ...],
    stream: ContractDirection,
) -> tuple[DemandCoverageSegmentV1, ...]:
    return tuple(item for item in segments if item.stream == stream)


def _source_internal_gaps(
    segments: tuple[DemandCoverageSegmentV1, ...],
) -> list[DemandUncoveredSegmentV1]:
    output: list[DemandUncoveredSegmentV1] = []
    for stream in (
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
        ContractDirection.COMBINED,
    ):
        directional = _segments_for_stream(segments, stream)
        for left, right in zip(directional, directional[1:], strict=False):
            output.append(
                DemandUncoveredSegmentV1(
                    code=DEMAND_TEMPORAL_COVERAGE_GAP,
                    stream=stream,
                    start_time=left.end_time,
                    end_time=right.start_time,
                )
            )
    return output


def _service_window_gaps(
    span: DemandRequiredSpanV1,
    segments: tuple[DemandCoverageSegmentV1, ...],
) -> list[DemandUncoveredSegmentV1]:
    if span.end_time <= span.start_time or not segments:
        return []
    output: list[DemandUncoveredSegmentV1] = []
    first = segments[0]
    last = segments[-1]
    if first.start_time > span.start_time:
        end = min(first.start_time, span.end_time)
        if end > span.start_time:
            output.append(
                DemandUncoveredSegmentV1(
                    code=DEMAND_SERVICE_WINDOW_NOT_COVERED,
                    stream=span.stream,
                    start_time=span.start_time,
                    end_time=end,
                )
            )
    if last.end_time < span.end_time:
        start = max(last.end_time, span.start_time)
        if span.end_time > start:
            output.append(
                DemandUncoveredSegmentV1(
                    code=DEMAND_SERVICE_WINDOW_NOT_COVERED,
                    stream=span.stream,
                    start_time=start,
                    end_time=span.end_time,
                )
            )
    return output


def _span_is_covered(
    span: DemandRequiredSpanV1,
    segments: tuple[DemandCoverageSegmentV1, ...],
) -> bool:
    if span.end_time <= span.start_time:
        return True
    cursor = span.start_time
    for segment in segments:
        if segment.end_time <= cursor:
            continue
        if segment.start_time > cursor:
            return False
        cursor = max(cursor, segment.end_time)
        if cursor >= span.end_time:
            return True
    return False


def _observation_covers(
    observations: tuple[DemandObservation, ...],
    stream: ContractDirection,
    departure_time: int,
) -> bool:
    return any(
        item.source_resolution_type != DemandResolutionType.DAILY_TOTAL
        and item.direction == stream
        and item.interval_start <= departure_time < item.interval_end
        for item in observations
    )


def _required_streams_for_mode(
    mode: DemandCoverageModeV1,
    present_streams: tuple[ContractDirection, ...],
) -> tuple[ContractDirection, ...]:
    if mode == DemandCoverageModeV1.DIRECTIONAL_ONLY:
        return tuple(
            item
            for item in (
                ContractDirection.OUTBOUND,
                ContractDirection.INBOUND,
            )
            if item in present_streams
        )
    if mode == DemandCoverageModeV1.COMBINED_ONLY:
        return (ContractDirection.COMBINED,)
    if mode == DemandCoverageModeV1.MIXED_DIRECTION_GRAIN:
        return present_streams
    return ()


def _departure_is_covered(
    departure: _Departure,
    mode: DemandCoverageModeV1,
    observations: tuple[DemandObservation, ...],
) -> tuple[bool, ContractDirection]:
    if mode == DemandCoverageModeV1.COMBINED_ONLY:
        required_stream = ContractDirection.COMBINED
        return (
            _observation_covers(
                observations,
                required_stream,
                departure.departure_time,
            ),
            required_stream,
        )
    if mode == DemandCoverageModeV1.MIXED_DIRECTION_GRAIN:
        if _observation_covers(
            observations,
            departure.direction,
            departure.departure_time,
        ):
            return True, departure.direction
        return (
            _observation_covers(
                observations,
                ContractDirection.COMBINED,
                departure.departure_time,
            ),
            ContractDirection.COMBINED,
        )
    return (
        _observation_covers(
            observations,
            departure.direction,
            departure.departure_time,
        ),
        departure.direction,
    )


def _is_final_service_sentinel(
    bundle: NormalizedInputBundleV1,
    departure: _Departure,
    mode: DemandCoverageModeV1,
    observations: tuple[DemandObservation, ...],
) -> bool:
    """Allow only the V3 locked B last departure at an exclusive analytical end."""
    if (
        bundle.optimization_mode != ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE
        or departure.scenario != ScenarioId.B
    ):
        return False
    directional_times = tuple(
        trip.departure_time
        for trip in bundle.scenario_b.exact_timetable
        if trip.direction == departure.direction
    )
    if not directional_times or departure.departure_time != max(directional_times):
        return False
    required_stream = (
        ContractDirection.COMBINED
        if mode == DemandCoverageModeV1.COMBINED_ONLY
        else departure.direction
    )
    stream_ends = tuple(
        item.interval_end
        for item in observations
        if item.source_resolution_type != DemandResolutionType.DAILY_TOTAL
        and item.direction == required_stream
    )
    return bool(stream_ends) and departure.departure_time == max(stream_ends)


def _deduplicate_uncovered_segments(
    values: list[DemandUncoveredSegmentV1],
) -> tuple[DemandUncoveredSegmentV1, ...]:
    unique = {
        (item.code, item.stream, item.start_time, item.end_time): item
        for item in values
        if item.end_time > item.start_time
    }
    return tuple(
        sorted(
            unique.values(),
            key=lambda item: (
                _DIRECTION_ORDER[item.stream],
                item.start_time,
                item.end_time,
                item.code,
            ),
        )
    )


def _confidence_supported(
    observations: tuple[DemandObservation, ...],
    streams: tuple[ContractDirection, ...],
    minimum: DemandConfidence,
) -> bool:
    relevant = [
        item
        for item in observations
        if item.source_resolution_type != DemandResolutionType.DAILY_TOTAL
        and item.direction in streams
    ]
    return bool(relevant) and all(
        _CONFIDENCE_RANK[item.demand_confidence] >= _CONFIDENCE_RANK[minimum] for item in relevant
    )


def _span_by_stream(
    spans: tuple[DemandRequiredSpanV1, ...],
) -> dict[ContractDirection, DemandRequiredSpanV1]:
    return {item.stream: item for item in spans}


def _diagnostic_evidence(
    *,
    mode: DemandCoverageModeV1,
    required_spans: tuple[DemandRequiredSpanV1, ...],
    source_segments: tuple[DemandCoverageSegmentV1, ...],
    uncovered_segments: tuple[DemandUncoveredSegmentV1, ...],
    uncovered_departures: tuple[DemandUncoveredDepartureV1, ...],
    present_streams: tuple[ContractDirection, ...],
    missing_streams: tuple[ContractDirection, ...],
    whole_b_supported: bool,
    directional_c_supported: bool,
) -> tuple[str, ...]:
    evidence = [
        f"coverage_mode={mode.value}",
        "present_streams=" + ",".join(item.value for item in present_streams),
        "missing_streams=" + ",".join(item.value for item in missing_streams),
    ]
    evidence.extend(
        f"required_span stream={item.stream.value} "
        f"start={format_hhmm(item.start_time)} end={format_hhmm(item.end_time)}"
        for item in required_spans
    )
    evidence.extend(
        f"source_segment stream={item.stream.value} "
        f"start={format_hhmm(item.start_time)} end={format_hhmm(item.end_time)} "
        f"covered_duration_minutes={item.duration_minutes} "
        f"observations={','.join(item.observation_ids)}"
        for item in source_segments
    )
    evidence.extend(
        f"{item.code} stream={item.stream.value} "
        f"uncovered_start={format_hhmm(item.start_time)} "
        f"uncovered_end={format_hhmm(item.end_time)}"
        for item in uncovered_segments
    )
    evidence.extend(
        f"{DEMAND_DEPARTURE_NOT_COVERED} scenario={item.scenario.value} "
        f"direction={item.direction.value} trip_id={item.trip_id} "
        f"departure_time={format_hhmm(item.departure_time)} "
        f"required_stream={item.required_stream.value}"
        for item in uncovered_departures
    )
    evidence.extend(
        (
            f"whole_b_demand_suitability_supported={str(whole_b_supported).lower()}",
            f"directional_c_generation_supported={str(directional_c_supported).lower()}",
        )
    )
    return tuple(evidence)


def assess_demand_coverage_v1(
    bundle: NormalizedInputBundleV1,
    *,
    minimum_confidence: DemandConfidence,
) -> DemandCoverageAssessmentV1:
    observations = bundle.observed_demand.observations if bundle.observed_demand is not None else ()
    mode = _coverage_mode(observations)
    source_segments = _source_segments(observations)
    departures = _departures(bundle)
    required_spans = _required_spans(departures)
    present_streams = tuple(
        stream
        for stream in (
            ContractDirection.OUTBOUND,
            ContractDirection.INBOUND,
            ContractDirection.COMBINED,
        )
        if any(item.stream == stream for item in source_segments)
    )
    missing_streams = tuple(
        stream
        for stream in (
            ContractDirection.OUTBOUND,
            ContractDirection.INBOUND,
            ContractDirection.COMBINED,
        )
        if stream not in present_streams
    )
    span_lookup = _span_by_stream(required_spans)
    uncovered_segments = _source_internal_gaps(source_segments)
    for stream in _required_streams_for_mode(mode, present_streams):
        span = span_lookup.get(stream)
        if span is None:
            continue
        uncovered_segments.extend(
            _service_window_gaps(
                span,
                _segments_for_stream(source_segments, stream),
            )
        )
    normalized_uncovered_segments = _deduplicate_uncovered_segments(uncovered_segments)

    uncovered_departures: list[DemandUncoveredDepartureV1] = []
    for departure in departures:
        covered, required_stream = _departure_is_covered(
            departure,
            mode,
            observations,
        )
        if not covered and not _is_final_service_sentinel(
            bundle,
            departure,
            mode,
            observations,
        ):
            uncovered_departures.append(
                DemandUncoveredDepartureV1(
                    scenario=departure.scenario,
                    direction=departure.direction,
                    trip_id=departure.trip_id,
                    departure_time=departure.departure_time,
                    required_stream=required_stream,
                )
            )
    normalized_uncovered_departures = tuple(uncovered_departures)

    defects = demand_source_defects_v1(observations)
    evaluation_issue_codes: list[str] = []
    generation_issue_codes: list[str] = []
    directional_streams = (
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
    )
    if mode == DemandCoverageModeV1.DIRECTIONAL_ONLY and any(
        stream not in present_streams for stream in directional_streams
    ):
        evaluation_issue_codes.append(DEMAND_DIRECTION_STREAM_MISSING)
    if normalized_uncovered_segments:
        if any(item.code == DEMAND_TEMPORAL_COVERAGE_GAP for item in normalized_uncovered_segments):
            evaluation_issue_codes.append(DEMAND_TEMPORAL_COVERAGE_GAP)
        if any(
            item.code == DEMAND_SERVICE_WINDOW_NOT_COVERED for item in normalized_uncovered_segments
        ):
            evaluation_issue_codes.append(DEMAND_SERVICE_WINDOW_NOT_COVERED)
    if normalized_uncovered_departures:
        evaluation_issue_codes.append(DEMAND_DEPARTURE_NOT_COVERED)
    if mode == DemandCoverageModeV1.MIXED_DIRECTION_GRAIN:
        evaluation_issue_codes.append(MIXED_DIRECTION_GRAIN_PARTIAL_SUPPORT)
    if mode == DemandCoverageModeV1.COMBINED_ONLY:
        evaluation_issue_codes.append(COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE)
        generation_issue_codes.append(COMBINED_DEMAND_UNSUPPORTED_FOR_DIRECTIONAL_C)
    for defect in defects:
        if defect.code not in evaluation_issue_codes:
            evaluation_issue_codes.append(defect.code)

    directional_span_supported = all(
        (
            span_lookup.get(stream) is not None
            and _span_is_covered(
                span_lookup[stream],
                _segments_for_stream(source_segments, stream),
            )
        )
        for stream in directional_streams
    )
    directional_departures_supported = all(
        (
            _observation_covers(
                observations,
                departure.direction,
                departure.departure_time,
            )
            or _is_final_service_sentinel(
                bundle,
                departure,
                mode,
                observations,
            )
        )
        for departure in departures
    )
    directional_confidence_supported = _confidence_supported(
        observations,
        directional_streams,
        minimum_confidence,
    )
    directional_supported = (
        mode == DemandCoverageModeV1.DIRECTIONAL_ONLY
        and all(stream in present_streams for stream in directional_streams)
        and directional_span_supported
        and directional_departures_supported
        and directional_confidence_supported
        and not defects
    )

    combined_span = span_lookup.get(ContractDirection.COMBINED)
    combined_supported = (
        mode == DemandCoverageModeV1.COMBINED_ONLY
        and combined_span is not None
        and _span_is_covered(
            combined_span,
            _segments_for_stream(
                source_segments,
                ContractDirection.COMBINED,
            ),
        )
        and all(
            (
                _observation_covers(
                    observations,
                    ContractDirection.COMBINED,
                    departure.departure_time,
                )
                or _is_final_service_sentinel(
                    bundle,
                    departure,
                    mode,
                    observations,
                )
            )
            for departure in departures
        )
        and _confidence_supported(
            observations,
            (ContractDirection.COMBINED,),
            minimum_confidence,
        )
        and not defects
    )
    whole_b_supported = directional_supported or combined_supported
    directional_c_supported = directional_supported
    if not directional_c_supported:
        generation_issue_codes.append(DEMAND_COVERAGE_INCOMPLETE_FOR_C_GENERATION)

    evidence = _diagnostic_evidence(
        mode=mode,
        required_spans=required_spans,
        source_segments=source_segments,
        uncovered_segments=normalized_uncovered_segments,
        uncovered_departures=normalized_uncovered_departures,
        present_streams=present_streams,
        missing_streams=missing_streams,
        whole_b_supported=whole_b_supported,
        directional_c_supported=directional_c_supported,
    )
    limitations = tuple(
        (
            f"{code}: demand evidence does not support the corresponding "
            "whole-window or directional conclusion."
        )
        for code in dict.fromkeys((*evaluation_issue_codes, *generation_issue_codes))
    )
    return DemandCoverageAssessmentV1(
        mode=mode,
        required_spans=required_spans,
        source_segments=source_segments,
        uncovered_segments=normalized_uncovered_segments,
        uncovered_departures=normalized_uncovered_departures,
        present_streams=present_streams,
        missing_streams=missing_streams,
        whole_b_suitability_supported=whole_b_supported,
        directional_c_generation_supported=directional_c_supported,
        evaluation_issue_codes=tuple(evaluation_issue_codes),
        generation_issue_codes=tuple(dict.fromkeys(generation_issue_codes)),
        evidence=evidence,
        limitations=limitations,
    )
