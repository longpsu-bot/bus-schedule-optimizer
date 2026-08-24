"""PR62-C1 global clean Route 6 ServiceRegime rhythm-design experiment.

The bounded label-setting search, exact wait integration, and evidence generation in this
module are experiment-only. Production compiler/search/fleet semantics remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from route6_boundary_settlement_experiment import (
    EXPECTED_DIRECT_ARTIFACTS,
    REFERENCE_LABELS,
    _bucket_counts,
    _hhmm,
    _sha256,
    exact_headway_runs,
    parse_route6_reference_workbook,
)

from bus_schedule_engine.clean_boundary_pilot import build_minimum_fleet_plan_v1
from bus_schedule_engine.service_plan_coordinator import (
    DemandBucketEvidenceV1,
    load_route_coordinator_inputs_v1,
)

EXPERIMENT_PROFILE = "pr62_c1_route6_global_clean_rhythm_design_v1"
WAIT_ASSUMPTION = "UNIFORM_WITHIN_DEMAND_BUCKET_EXPERIMENT_ASSUMPTION"
TECHNICAL_HEADWAY_MIN = 5
TECHNICAL_HEADWAY_MAX = 30
FIXED_FIRST_DEPARTURE = 4 * 3600 + 55 * 60
FIXED_LAST_DEPARTURE = 21 * 3600
TOTAL_GAPS = 77
OPERATING_SPAN_MINUTES = 965
OUTPUT_JSON = Path("docs/engine/evidence/PR62_C1_ROUTE6_GLOBAL_CLEAN_RHYTHM_DESIGN.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_C1_ROUTE6_GLOBAL_CLEAN_RHYTHM_DESIGN.md")
COMPARISON_EPSILON = 1e-12


@dataclass(frozen=True, slots=True)
class SearchSettings:
    name: str
    per_state_archive: int
    directional_final_pool: int
    per_gap_layer_label_cap: int | None = None


@dataclass(frozen=True, slots=True)
class ServiceRegime:
    headway_minutes: int
    gap_count: int


@dataclass(frozen=True, slots=True)
class DesignLabel:
    regimes: tuple[ServiceRegime, ...]
    departure_offsets_minutes: tuple[int, ...]
    fingerprint: str

    @property
    def gaps_used(self) -> int:
        return len(self.departure_offsets_minutes) - 1


@dataclass(slots=True)
class DpStatistics:
    states_reached: int = 1
    labels_generated: int = 0
    duplicate_labels: int = 0
    technical_labels_pruned: int = 0
    arithmetic_infeasible_transitions: int = 0
    complete_labels_generated: int = 0
    complete_directional_designs_found: int = 0
    retained_directional_candidates: int = 0


@dataclass(frozen=True, slots=True)
class DirectionalCandidate:
    candidate_id: str
    direction: str
    label: DesignLabel
    departures: tuple[int, ...]
    metrics: Mapping[str, Any]


def _fingerprint_offsets(offsets: Sequence[int]) -> str:
    encoded = json.dumps(list(offsets), separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _new_label(label: DesignLabel, *, headway_minutes: int, gap_count: int) -> DesignLabel:
    last = label.departure_offsets_minutes[-1]
    appended = tuple(last + headway_minutes * index for index in range(1, gap_count + 1))
    offsets = (*label.departure_offsets_minutes, *appended)
    regimes = (*label.regimes, ServiceRegime(headway_minutes, gap_count))
    fingerprint = f"{label.fingerprint}|{headway_minutes:02d}x{gap_count:02d}"
    return DesignLabel(regimes, offsets, fingerprint)


def _initial_label() -> DesignLabel:
    offsets = (0,)
    return DesignLabel((), offsets, "START")


def _frequency_metrics(regimes: Sequence[ServiceRegime]) -> tuple[float, float]:
    jumps = tuple(
        abs(math.log(right.headway_minutes / left.headway_minutes))
        for left, right in zip(regimes, regimes[1:], strict=False)
    )
    return max(jumps, default=0.0), sum(jumps)


def _partial_order_metrics(
    label: DesignLabel,
    *,
    fixed_first_departure: int,
    demand_buckets: Sequence[DemandBucketEvidenceV1],
) -> tuple[float | int, ...]:
    del fixed_first_departure, demand_buckets
    gaps = tuple(
        right - left
        for left, right in zip(
            label.departure_offsets_minutes,
            label.departure_offsets_minutes[1:],
            strict=False,
        )
    )
    unweighted_wait = sum(gap * gap for gap in gaps) / (2 * sum(gaps)) if gaps else 0.0
    phase_dispersion = sum(
        min(offset % 30, 30 - offset % 30) for offset in label.departure_offsets_minutes
    ) / len(label.departure_offsets_minutes)
    max_jump, total_variation = _frequency_metrics(label.regimes)
    return (
        phase_dispersion,
        unweighted_wait,
        len(label.regimes),
        len({regime.headway_minutes for regime in label.regimes}),
        max_jump,
        total_variation,
        max(gaps, default=0),
    )


def _departure_distance(left: DesignLabel, right: DesignLabel) -> int:
    return sum(
        abs(a - b)
        for a, b in zip(
            left.departure_offsets_minutes,
            right.departure_offsets_minutes,
            strict=True,
        )
    )


def _select_with_anchors(
    labels: Sequence[DesignLabel],
    *,
    capacity: int,
    metric: Callable[[DesignLabel], tuple[float | int, ...]],
    extra_anchor_keys: Sequence[Callable[[DesignLabel], Any]] = (),
) -> tuple[DesignLabel, ...]:
    unique = {label.departure_offsets_minutes: label for label in labels}
    ordered = sorted(unique.values(), key=lambda item: item.fingerprint)
    if len(ordered) <= capacity:
        return tuple(ordered)
    metrics = {label.fingerprint: metric(label) for label in ordered}
    metric_width = len(next(iter(metrics.values())))
    anchors: list[Callable[[DesignLabel], Any]] = [
        *[
            lambda item, index=index: (
                metrics[item.fingerprint][index],
                item.fingerprint,
            )
            for index in range(metric_width)
        ],
        lambda item: (item.departure_offsets_minutes, item.fingerprint),
        lambda item: (
            tuple(-value for value in item.departure_offsets_minutes),
            item.fingerprint,
        ),
        *extra_anchor_keys,
    ]
    retained: list[DesignLabel] = []
    retained_fingerprints: set[str] = set()
    for key in anchors:
        chosen = min(ordered, key=key)
        if chosen.fingerprint not in retained_fingerprints:
            retained.append(chosen)
            retained_fingerprints.add(chosen.fingerprint)
        if len(retained) == capacity:
            return tuple(retained)
    matrix = np.asarray([item.departure_offsets_minutes for item in ordered], dtype=np.int16)
    index_by_fingerprint = {item.fingerprint: index for index, item in enumerate(ordered)}
    active = np.ones(len(ordered), dtype=bool)
    minimum_distance = np.full(len(ordered), np.iinfo(np.int64).max, dtype=np.int64)
    for kept in retained:
        kept_index = index_by_fingerprint[kept.fingerprint]
        active[kept_index] = False
        minimum_distance = np.minimum(
            minimum_distance,
            np.abs(matrix - matrix[kept_index]).sum(axis=1, dtype=np.int64),
        )
    while len(retained) < capacity:
        active_indices = np.flatnonzero(active)
        if not len(active_indices):
            break
        greatest_distance = int(minimum_distance[active_indices].max())
        tied_indices = active_indices[minimum_distance[active_indices] == greatest_distance]
        chosen = min(
            (ordered[int(index)] for index in tied_indices),
            key=lambda item: (
                metrics[item.fingerprint],
                item.fingerprint,
            ),
        )
        retained.append(chosen)
        retained_fingerprints.add(chosen.fingerprint)
        chosen_index = index_by_fingerprint[chosen.fingerprint]
        active[chosen_index] = False
        minimum_distance = np.minimum(
            minimum_distance,
            np.abs(matrix - matrix[chosen_index]).sum(axis=1, dtype=np.int64),
        )
    return tuple(retained)


def _composition_histogram(label: DesignLabel) -> Counter[int]:
    histogram: Counter[int] = Counter()
    for regime in label.regimes:
        histogram[regime.headway_minutes] += regime.gap_count
    return histogram


def _matches_oracle(label: DesignLabel, expected: Mapping[int, int]) -> bool:
    return _composition_histogram(label) == Counter(expected)


def enumerate_exact_clean_sequences_up_to_three_regimes(
    *,
    total_gaps: int = TOTAL_GAPS,
    operating_span_minutes: int = OPERATING_SPAN_MINUTES,
    minimum_headway: int = TECHNICAL_HEADWAY_MIN,
    maximum_headway: int = TECHNICAL_HEADWAY_MAX,
) -> tuple[tuple[ServiceRegime, ...], ...]:
    """General exhaustive arithmetic oracle for one-, two-, and three-regime sequences."""

    sequences: set[tuple[ServiceRegime, ...]] = set()
    for headway in range(minimum_headway, maximum_headway + 1):
        if headway * total_gaps == operating_span_minutes:
            sequences.add((ServiceRegime(headway, total_gaps),))
    for first_headway in range(minimum_headway, maximum_headway + 1):
        for second_headway in range(minimum_headway, maximum_headway + 1):
            if first_headway == second_headway:
                continue
            for first_count in range(2, total_gaps - 1):
                second_count = total_gaps - first_count
                if (
                    second_count >= 2
                    and first_headway * first_count + second_headway * second_count
                    == operating_span_minutes
                ):
                    sequences.add(
                        (
                            ServiceRegime(first_headway, first_count),
                            ServiceRegime(second_headway, second_count),
                        )
                    )
    for first_headway in range(minimum_headway, maximum_headway + 1):
        for second_headway in range(minimum_headway, maximum_headway + 1):
            if first_headway == second_headway:
                continue
            for third_headway in range(minimum_headway, maximum_headway + 1):
                if second_headway == third_headway:
                    continue
                denominator = second_headway - third_headway
                for first_count in range(2, total_gaps - 3):
                    numerator = (
                        operating_span_minutes
                        - third_headway * total_gaps
                        - (first_headway - third_headway) * first_count
                    )
                    if numerator % denominator:
                        continue
                    second_count = numerator // denominator
                    third_count = total_gaps - first_count - second_count
                    if second_count >= 2 and third_count >= 2:
                        sequences.add(
                            (
                                ServiceRegime(first_headway, first_count),
                                ServiceRegime(second_headway, second_count),
                                ServiceRegime(third_headway, third_count),
                            )
                        )
    return tuple(
        sorted(
            sequences,
            key=lambda sequence: tuple(
                (regime.headway_minutes, regime.gap_count) for regime in sequence
            ),
        )
    )


def arithmetic_acceptance_oracles() -> dict[str, Any]:
    sequences = enumerate_exact_clean_sequences_up_to_three_regimes()
    histograms = []
    for sequence in sequences:
        histogram: Counter[int] = Counter()
        for regime in sequence:
            histogram[regime.headway_minutes] += regime.gap_count
        histograms.append(histogram)
    return {
        "general_sequences_enumerated_with_one_to_three_regimes": len(sequences),
        "two_headway_38x10_39x15_discovered": Counter({10: 38, 15: 39}) in histograms,
        "three_headway_25x8_3x10_49x15_discovered": Counter({8: 25, 10: 3, 15: 49}) in histograms,
    }


def _labels_from_regime_sequences(
    sequences: Sequence[Sequence[ServiceRegime]],
) -> tuple[DesignLabel, ...]:
    labels = []
    for sequence in sequences:
        label = _initial_label()
        for regime in sequence:
            label = _new_label(
                label,
                headway_minutes=regime.headway_minutes,
                gap_count=regime.gap_count,
            )
        labels.append(label)
    return tuple(labels)


def run_directional_dp(
    *,
    direction: str,
    demand_buckets: Sequence[DemandBucketEvidenceV1],
    settings: SearchSettings,
    fixed_first_departure: int = FIXED_FIRST_DEPARTURE,
    total_gaps: int = TOTAL_GAPS,
    operating_span_minutes: int = OPERATING_SPAN_MINUTES,
    minimum_headway: int = TECHNICAL_HEADWAY_MIN,
    maximum_headway: int = TECHNICAL_HEADWAY_MAX,
) -> tuple[tuple[DesignLabel, ...], DpStatistics, dict[str, bool]]:
    """Run the bounded deterministic segment-level label-setting frontier."""

    if direction not in {"outbound", "inbound"}:
        raise ValueError("unsupported direction")
    layer_cap = (
        settings.per_gap_layer_label_cap
        if settings.per_gap_layer_label_cap is not None
        else settings.directional_final_pool
    )
    archives: dict[tuple[int, int, int], list[DesignLabel]] = {(0, 0, 0): [_initial_label()]}
    states_by_gaps: dict[int, set[tuple[int, int, int]]] = defaultdict(set)
    states_by_gaps[0].add((0, 0, 0))
    layer_label_counts: dict[int, int] = defaultdict(int)
    layer_label_counts[0] = 1
    seen_states = {(0, 0, 0)}
    stats = DpStatistics()
    partial_cache: dict[str, tuple[float | int, ...]] = {}
    oracle_flags = {
        "two_headway_38x10_39x15_generated": False,
        "three_headway_25x8_3x10_49x15_generated": False,
    }

    def metric(label: DesignLabel) -> tuple[float | int, ...]:
        cached = partial_cache.get(label.fingerprint)
        if cached is None:
            cached = _partial_order_metrics(
                label,
                fixed_first_departure=fixed_first_departure,
                demand_buckets=demand_buckets,
            )
            partial_cache[label.fingerprint] = cached
        return cached

    def prune(key: tuple[int, int, int]) -> None:
        archive = archives[key]
        if len(archive) <= settings.per_state_archive:
            return
        selected = _select_with_anchors(
            archive,
            capacity=settings.per_state_archive,
            metric=metric,
        )
        stats.technical_labels_pruned += len(archive) - len(selected)
        layer_label_counts[key[0]] -= len(archive) - len(selected)
        archives[key] = list(selected)

    def prune_layer(gap_layer: int) -> None:
        keys = tuple(sorted(states_by_gaps.get(gap_layer, ())))
        for state_key in keys:
            if state_key in archives:
                prune(state_key)
        labels = [label for state_key in keys for label in archives.get(state_key, ())]
        if len(labels) <= layer_cap:
            layer_label_counts[gap_layer] = len(labels)
            return
        selected = _select_with_anchors(
            labels,
            capacity=layer_cap,
            metric=metric,
            extra_anchor_keys=(
                lambda item: (
                    item.departure_offsets_minutes[-1],
                    item.regimes[-1].headway_minutes,
                    item.fingerprint,
                ),
                lambda item: (
                    -item.departure_offsets_minutes[-1],
                    -item.regimes[-1].headway_minutes,
                    item.fingerprint,
                ),
            ),
        )
        selected_fingerprints = {label.fingerprint for label in selected}
        removed = len(labels) - len(selected)
        stats.technical_labels_pruned += removed
        for state_key in keys:
            kept = [
                label
                for label in archives.get(state_key, ())
                if label.fingerprint in selected_fingerprints
            ]
            if kept:
                archives[state_key] = kept
            else:
                archives.pop(state_key, None)
        states_by_gaps[gap_layer] = {state_key for state_key in keys if state_key in archives}
        layer_label_counts[gap_layer] = len(selected)

    for gaps_used in range(total_gaps):
        prune_layer(gaps_used)
        for key in sorted(states_by_gaps.get(gaps_used, ())):
            _, elapsed, last_headway = key
            labels = tuple(sorted(archives[key], key=lambda item: item.fingerprint))
            remaining_capacity = total_gaps - gaps_used
            for label in labels:
                for headway in range(minimum_headway, maximum_headway + 1):
                    if headway == last_headway:
                        continue
                    remaining_minutes_before = operating_span_minutes - elapsed
                    maximum_gap_count = remaining_capacity
                    if headway > minimum_headway:
                        maximum_gap_count = min(
                            maximum_gap_count,
                            (remaining_minutes_before - minimum_headway * remaining_capacity)
                            // (headway - minimum_headway),
                        )
                    if headway < maximum_headway:
                        maximum_gap_count = min(
                            maximum_gap_count,
                            (maximum_headway * remaining_capacity - remaining_minutes_before)
                            // (maximum_headway - headway),
                        )
                    for gap_count in range(2, maximum_gap_count + 1):
                        new_gaps = gaps_used + gap_count
                        new_elapsed = elapsed + headway * gap_count
                        remaining_gaps = total_gaps - new_gaps
                        remaining_minutes = operating_span_minutes - new_elapsed
                        if remaining_minutes < 0:
                            break
                        feasible = (remaining_gaps == 0 and remaining_minutes == 0) or (
                            remaining_gaps >= 2
                            and remaining_gaps * minimum_headway
                            <= remaining_minutes
                            <= remaining_gaps * maximum_headway
                        )
                        if not feasible:
                            stats.arithmetic_infeasible_transitions += 1
                            continue
                        candidate = _new_label(
                            label,
                            headway_minutes=headway,
                            gap_count=gap_count,
                        )
                        stats.labels_generated += 1
                        if remaining_gaps == 0:
                            stats.complete_labels_generated += 1
                            if _matches_oracle(candidate, {10: 38, 15: 39}):
                                oracle_flags["two_headway_38x10_39x15_generated"] = True
                            if _matches_oracle(candidate, {8: 25, 10: 3, 15: 49}):
                                oracle_flags["three_headway_25x8_3x10_49x15_generated"] = True
                        target = (new_gaps, new_elapsed, headway)
                        archive = archives.setdefault(target, [])
                        if any(
                            existing.departure_offsets_minutes
                            == candidate.departure_offsets_minutes
                            for existing in archive
                        ):
                            stats.duplicate_labels += 1
                            continue
                        archive.append(candidate)
                        layer_label_counts[new_gaps] += 1
                        if len(archive) > settings.per_state_archive * 4:
                            prune(target)
                        if target not in seen_states:
                            seen_states.add(target)
                            stats.states_reached += 1
                        if target not in states_by_gaps[new_gaps]:
                            states_by_gaps[new_gaps].add(target)
                        if layer_label_counts[new_gaps] > layer_cap * 32:
                            prune_layer(new_gaps)

    complete: list[DesignLabel] = []
    prune_layer(total_gaps)
    for key in sorted(states_by_gaps.get(total_gaps, ())):
        if key[1] != operating_span_minutes:
            continue
        prune(key)
        complete.extend(archives[key])
    complete_by_offsets = {label.departure_offsets_minutes: label for label in complete}
    completed = tuple(sorted(complete_by_offsets.values(), key=lambda item: item.fingerprint))
    stats.complete_directional_designs_found = len(completed)
    return completed, stats, oracle_flags


def expected_passenger_wait_metrics(
    departures: Sequence[int],
    demand_buckets: Sequence[DemandBucketEvidenceV1],
) -> dict[str, Any]:
    """Integrate exact next-departure wait under piecewise-constant demand intensity."""

    if len(departures) < 2 or tuple(sorted(departures)) != tuple(departures):
        raise ValueError("strictly increasing departures are required")
    first, last = departures[0], departures[-1]
    total_mass = 0.0
    weighted_wait_passenger_seconds = 0.0
    per_bucket = []
    for bucket in demand_buckets:
        active_start = max(first, bucket.start)
        active_end = min(last, bucket.end)
        if active_end <= active_start:
            continue
        intensity = bucket.observed_demand / (bucket.end - bucket.start)
        bucket_mass = intensity * (active_end - active_start)
        bucket_wait = 0.0
        for left, right in zip(departures, departures[1:], strict=False):
            overlap_start = max(left, active_start)
            overlap_end = min(right, active_end)
            if overlap_end <= overlap_start:
                continue
            integrated_wait_seconds_squared = (
                right * (overlap_end - overlap_start)
                - (overlap_end * overlap_end - overlap_start * overlap_start) / 2
            )
            bucket_wait += intensity * integrated_wait_seconds_squared
        expected_minutes = bucket_wait / bucket_mass / 60 if bucket_mass else 0.0
        total_mass += bucket_mass
        weighted_wait_passenger_seconds += bucket_wait
        per_bucket.append(
            {
                "start": _hhmm(bucket.start),
                "end": _hhmm(bucket.end),
                "active_demand_mass": bucket_mass,
                "expected_wait_minutes": expected_minutes,
            }
        )
    if total_mass <= 0:
        raise ValueError("no immutable demand mass intersects the active service span")
    return {
        "assumption": WAIT_ASSUMPTION,
        "active_service_span": [_hhmm(first), _hhmm(last)],
        "active_demand_mass": total_mass,
        "weighted_wait_passenger_minutes": weighted_wait_passenger_seconds / 60,
        "demand_weighted_expected_passenger_wait_minutes": (
            weighted_wait_passenger_seconds / total_mass / 60
        ),
        "maximum_bucket_expected_wait_minutes": max(
            item["expected_wait_minutes"] for item in per_bucket
        ),
        "per_demand_bucket": per_bucket,
    }


def _tail_metrics(
    departures: Sequence[int],
    regimes: Sequence[ServiceRegime],
    demand_buckets: Sequence[DemandBucketEvidenceV1],
) -> dict[str, Any]:
    if not regimes:
        raise ValueError("at least one exact headway run is required")
    gap_counts = [regime.gap_count for regime in regimes]
    stable_indices = [index for index, count in enumerate(gap_counts) if count >= 2]
    if not stable_indices:
        raise ValueError("no sustained tail rhythm with at least two gaps")
    tail_index = stable_indices[-1]
    start_gap_index = sum(regime.gap_count for regime in regimes[:tail_index])
    tail_start = departures[start_gap_index]
    h = regimes[tail_index].headway_minutes
    tail_departures = tuple(departures[start_gap_index:])
    phases = Counter((departure // 60) % h for departure in tail_departures)
    dominant_phase, aligned = min(phases.items(), key=lambda item: (-item[1], item[0]))
    phase_deviations = [
        min(
            abs((departure // 60) % h - dominant_phase),
            h - abs((departure // 60) % h - dominant_phase),
        )
        for departure in tail_departures
    ]
    total_demand = sum(bucket.observed_demand for bucket in demand_buckets)
    tail_demand = 0.0
    for bucket in demand_buckets:
        overlap = max(0, min(bucket.end, departures[-1]) - max(bucket.start, tail_start))
        if overlap:
            tail_demand += bucket.observed_demand * overlap / (bucket.end - bucket.start)
    tail_demand_share = tail_demand / total_demand
    tail_service_share = len(tail_departures) / len(departures)
    return {
        "tail_headway_minutes": h,
        "tail_start": _hhmm(tail_start),
        "tail_departure_count": len(tail_departures),
        "tail_demand_share": tail_demand_share,
        "tail_service_share": tail_service_share,
        "tail_demand_mismatch": abs(tail_service_share - tail_demand_share),
        "dominant_modulo_phase_minutes": dominant_phase,
        "exact_alignment_proportion": aligned / len(tail_departures),
        "maximum_phase_deviation_minutes": max(phase_deviations, default=0),
    }


def _regimes_from_departures(departures: Sequence[int]) -> tuple[ServiceRegime, ...]:
    return tuple(
        ServiceRegime(run.headway_minutes, run.gap_count) for run in exact_headway_runs(departures)
    )


def _composition_payload(regimes: Sequence[ServiceRegime]) -> dict[str, Any]:
    histogram = Counter()
    for regime in regimes:
        histogram[regime.headway_minutes] += regime.gap_count
    return {
        "headway_gap_counts": {str(key): histogram[key] for key in sorted(histogram)},
        "algebra": " + ".join(f"{histogram[key]} × {key}" for key in sorted(histogram))
        + f" = {sum(key * count for key, count in histogram.items())}",
        "sum_gap_counts": sum(histogram.values()),
        "sum_headway_times_gap_count_minutes": sum(key * count for key, count in histogram.items()),
    }


def _regime_sequence_payload(
    departures: Sequence[int], regimes: Sequence[ServiceRegime]
) -> list[dict[str, Any]]:
    payload = []
    gap_cursor = 0
    for regime in regimes:
        payload.append(
            {
                "headway_minutes": regime.headway_minutes,
                "gap_count": regime.gap_count,
                "departure_count": regime.gap_count + 1,
                "start": _hhmm(departures[gap_cursor]),
                "end": _hhmm(departures[gap_cursor + regime.gap_count]),
            }
        )
        gap_cursor += regime.gap_count
    return payload


def directional_metrics(
    departures: Sequence[int],
    *,
    regimes: Sequence[ServiceRegime],
    demand_buckets: Sequence[DemandBucketEvidenceV1],
    current_departures: Sequence[int],
    human_final_departures: Sequence[int],
) -> dict[str, Any]:
    gaps = tuple(
        (right - left) // 60 for left, right in zip(departures, departures[1:], strict=False)
    )
    if any(regime.gap_count < 1 for regime in regimes):
        raise ValueError("invalid exact headway run")
    counts = _bucket_counts(departures, demand_buckets)
    current_counts = _bucket_counts(current_departures, demand_buckets)
    total_demand = sum(bucket.observed_demand for bucket in demand_buckets)
    demand_shares = tuple(bucket.observed_demand / total_demand for bucket in demand_buckets)
    service_shares = tuple(count / len(departures) for count in counts)
    mismatch = sum(
        (service - demand) ** 2
        for service, demand in zip(service_shares, demand_shares, strict=True)
    )
    max_jump, total_variation = _frequency_metrics(regimes)
    wait = expected_passenger_wait_metrics(departures, demand_buckets)
    bucket_service = []
    for index, (bucket, count) in enumerate(zip(demand_buckets, counts, strict=True)):
        bucket_service.append(
            {
                "start": _hhmm(bucket.start),
                "end": _hhmm(bucket.end),
                "observed_demand": bucket.observed_demand,
                "service_count": count,
                "demand_share": demand_shares[index],
                "service_share": service_shares[index],
                "movement_vs_current": count - current_counts[index],
            }
        )
    movement_current = [
        abs(value - reference) // 60
        for value, reference in zip(departures, current_departures, strict=True)
    ]
    movement_human = [
        abs(value - reference) // 60
        for value, reference in zip(departures, human_final_departures, strict=True)
    ]
    return {
        "exact_departures": [_hhmm(value) for value in departures],
        "service_regimes": _regime_sequence_payload(departures, regimes),
        "headway_composition": _composition_payload(regimes),
        "regime_count": len(regimes),
        "unique_headway_count": len(set(gaps)),
        "unique_headways_minutes": sorted(set(gaps)),
        "headway_histogram": {str(key): count for key, count in sorted(Counter(gaps).items())},
        "singleton_run_count": sum(regime.gap_count == 1 for regime in regimes),
        "first_departure": _hhmm(departures[0]),
        "last_departure": _hhmm(departures[-1]),
        "total_departures": len(departures),
        "demand_bucket_service": bucket_service,
        "immutable_demand_mismatch": mismatch,
        "demand_weighted_expected_passenger_wait_minutes": wait[
            "demand_weighted_expected_passenger_wait_minutes"
        ],
        "maximum_bucket_expected_wait_minutes": wait["maximum_bucket_expected_wait_minutes"],
        "wait_evidence": wait,
        "maximum_adjacent_frequency_jump": max_jump,
        "total_frequency_variation": total_variation,
        "tail": _tail_metrics(departures, regimes, demand_buckets),
        "movement_vs_current": {
            "sum_absolute_timestamp_minutes": sum(movement_current),
            "maximum_absolute_timestamp_minutes": max(movement_current, default=0),
        },
        "movement_vs_human_final": {
            "sum_absolute_timestamp_minutes": sum(movement_human),
            "maximum_absolute_timestamp_minutes": max(movement_human, default=0),
        },
    }


def _full_metric_tuple(metrics: Mapping[str, Any]) -> tuple[float | int, ...]:
    return (
        metrics["demand_weighted_expected_passenger_wait_minutes"],
        metrics["maximum_bucket_expected_wait_minutes"],
        metrics["immutable_demand_mismatch"],
        metrics["regime_count"],
        metrics["unique_headway_count"],
        metrics["maximum_adjacent_frequency_jump"],
        metrics["total_frequency_variation"],
        metrics["tail"]["tail_demand_mismatch"],
        metrics["tail"]["maximum_phase_deviation_minutes"],
    )


def _directional_selection_metrics(
    departures: Sequence[int],
    *,
    regimes: Sequence[ServiceRegime],
    demand_buckets: Sequence[DemandBucketEvidenceV1],
) -> tuple[tuple[float | int, ...], str]:
    counts = _bucket_counts(departures, demand_buckets)
    total_demand = sum(bucket.observed_demand for bucket in demand_buckets)
    demand_shares = tuple(bucket.observed_demand / total_demand for bucket in demand_buckets)
    service_shares = tuple(count / len(departures) for count in counts)
    mismatch = sum(
        (service - demand) ** 2
        for service, demand in zip(service_shares, demand_shares, strict=True)
    )
    wait = expected_passenger_wait_metrics(departures, demand_buckets)
    maximum_jump, total_variation = _frequency_metrics(regimes)
    tail = _tail_metrics(departures, regimes, demand_buckets)
    metrics = {
        "demand_weighted_expected_passenger_wait_minutes": wait[
            "demand_weighted_expected_passenger_wait_minutes"
        ],
        "maximum_bucket_expected_wait_minutes": wait["maximum_bucket_expected_wait_minutes"],
        "immutable_demand_mismatch": mismatch,
        "regime_count": len(regimes),
        "unique_headway_count": len({regime.headway_minutes for regime in regimes}),
        "maximum_adjacent_frequency_jump": maximum_jump,
        "total_frequency_variation": total_variation,
        "tail": tail,
    }
    return _full_metric_tuple(metrics), tail["tail_start"]


def retain_directional_pool(
    labels: Sequence[DesignLabel],
    *,
    direction: str,
    capacity: int,
    demand_buckets: Sequence[DemandBucketEvidenceV1],
    current_departures: Sequence[int],
    human_final_departures: Sequence[int],
    selection_metric_cache: dict[tuple[str, str], tuple[tuple[float | int, ...], str]]
    | None = None,
    full_metrics_cache: dict[tuple[str, str], Mapping[str, Any]] | None = None,
) -> tuple[DirectionalCandidate, ...]:
    selection_by_fingerprint: dict[str, tuple[tuple[float | int, ...], str]] = {}
    for label in labels:
        departures = tuple(
            FIXED_FIRST_DEPARTURE + offset * 60 for offset in label.departure_offsets_minutes
        )
        if (
            len(departures) != 78
            or departures[0] != FIXED_FIRST_DEPARTURE
            or departures[-1] != FIXED_LAST_DEPARTURE
            or any(regime.gap_count < 2 for regime in label.regimes)
            or any(
                left.headway_minutes == right.headway_minutes
                for left, right in zip(label.regimes, label.regimes[1:], strict=False)
            )
        ):
            raise AssertionError("bounded DP emitted a non-clean directional candidate")
        cache_key = (direction, label.fingerprint)
        cached_selection = (
            selection_metric_cache.get(cache_key) if selection_metric_cache is not None else None
        )
        if cached_selection is None:
            cached_selection = _directional_selection_metrics(
                departures,
                regimes=label.regimes,
                demand_buckets=demand_buckets,
            )
            if selection_metric_cache is not None:
                selection_metric_cache[cache_key] = cached_selection
        selection_by_fingerprint[label.fingerprint] = cached_selection

    def metric(label: DesignLabel) -> tuple[float | int, ...]:
        return selection_by_fingerprint[label.fingerprint][0]

    selected = _select_with_anchors(
        labels,
        capacity=capacity,
        metric=metric,
        extra_anchor_keys=(
            lambda item: (
                selection_by_fingerprint[item.fingerprint][1],
                item.fingerprint,
            ),
            lambda item: (
                tuple(-value for value in item.departure_offsets_minutes),
                item.fingerprint,
            ),
        ),
    )
    retained = []
    for index, label in enumerate(selected, start=1):
        departures = tuple(
            FIXED_FIRST_DEPARTURE + offset * 60 for offset in label.departure_offsets_minutes
        )
        cache_key = (direction, label.fingerprint)
        full_metrics = full_metrics_cache.get(cache_key) if full_metrics_cache is not None else None
        if full_metrics is None:
            full_metrics = directional_metrics(
                departures,
                regimes=label.regimes,
                demand_buckets=demand_buckets,
                current_departures=current_departures,
                human_final_departures=human_final_departures,
            )
            if full_metrics_cache is not None:
                full_metrics_cache[cache_key] = full_metrics
        retained.append(
            DirectionalCandidate(
                candidate_id=f"{direction.upper()}_CLEAN_{index:03d}",
                direction=direction,
                label=label,
                departures=departures,
                metrics=full_metrics,
            )
        )
    return tuple(retained)


def _pair_fleet_metrics(
    outbound: DirectionalCandidate,
    inbound: DirectionalCandidate,
    *,
    runtime_minutes: int,
    minimum_layover_minutes: int,
    fleet_ceiling: int,
) -> dict[str, Any]:
    plan = build_minimum_fleet_plan_v1(
        route_id="6",
        outbound_candidate_id=outbound.candidate_id,
        inbound_candidate_id=inbound.candidate_id,
        outbound_departures=outbound.departures,
        inbound_departures=inbound.departures,
        runtime_minutes=runtime_minutes,
        minimum_layover_minutes=minimum_layover_minutes,
    )
    excess_waits = [
        max(0, assignment.connection_layover_minutes - minimum_layover_minutes)
        for assignment in plan.assignments
        if assignment.connection_layover_minutes is not None
    ]
    return {
        "fleet_required": plan.fleet_requirement,
        "fleet_ceiling": fleet_ceiling,
        "fleet_feasible": plan.fleet_requirement <= fleet_ceiling,
        "minimum_connection_layover_minutes": plan.minimum_connection_layover_minutes,
        "total_excess_terminal_wait_minutes": sum(excess_waits),
        "maximum_excess_terminal_wait_minutes": max(excess_waits, default=0),
    }


def _pair_operational_metrics(
    outbound: DirectionalCandidate,
    inbound: DirectionalCandidate,
    fleet: Mapping[str, Any],
) -> dict[str, Any]:
    out = outbound.metrics
    inn = inbound.metrics
    total_mass = (
        out["wait_evidence"]["active_demand_mass"] + inn["wait_evidence"]["active_demand_mass"]
    )
    total_weighted_wait = (
        out["wait_evidence"]["weighted_wait_passenger_minutes"]
        + inn["wait_evidence"]["weighted_wait_passenger_minutes"]
    )
    return {
        **fleet,
        "pair_immutable_demand_mismatch": (
            out["immutable_demand_mismatch"] + inn["immutable_demand_mismatch"]
        ),
        "network_demand_weighted_expected_passenger_wait_minutes": (
            total_weighted_wait / total_mass
        ),
        "maximum_bucket_expected_wait_minutes": max(
            out["maximum_bucket_expected_wait_minutes"],
            inn["maximum_bucket_expected_wait_minutes"],
        ),
        "total_service_regime_count": out["regime_count"] + inn["regime_count"],
        "total_unique_headway_complexity": (
            out["unique_headway_count"] + inn["unique_headway_count"]
        ),
        "maximum_frequency_jump": max(
            out["maximum_adjacent_frequency_jump"],
            inn["maximum_adjacent_frequency_jump"],
        ),
        "total_frequency_variation": (
            out["total_frequency_variation"] + inn["total_frequency_variation"]
        ),
    }


PAIR_OBJECTIVES = (
    "pair_immutable_demand_mismatch",
    "network_demand_weighted_expected_passenger_wait_minutes",
    "maximum_bucket_expected_wait_minutes",
    "fleet_required",
    "total_excess_terminal_wait_minutes",
    "maximum_excess_terminal_wait_minutes",
    "total_service_regime_count",
    "total_unique_headway_complexity",
    "maximum_frequency_jump",
    "total_frequency_variation",
)


def _pair_vector(pair: Mapping[str, Any]) -> tuple[float, ...]:
    metrics = pair["metrics"]
    return tuple(float(metrics[key]) for key in PAIR_OBJECTIVES)


def _dominates(
    left: Sequence[float], right: Sequence[float], *, epsilon: float = COMPARISON_EPSILON
) -> bool:
    no_worse = all(a <= b + epsilon for a, b in zip(left, right, strict=True))
    strictly_better = any(a < b - epsilon for a, b in zip(left, right, strict=True))
    return no_worse and strictly_better


def pareto_frontier(pairs: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    frontier: list[Mapping[str, Any]] = []
    for pair in sorted(pairs, key=lambda item: (*_pair_vector(item), item["pair_id"])):
        vector = _pair_vector(pair)
        if any(_dominates(_pair_vector(other), vector) for other in frontier):
            continue
        frontier = [other for other in frontier if not _dominates(vector, _pair_vector(other))]
        frontier.append(pair)
    return tuple(sorted(frontier, key=lambda item: (*_pair_vector(item), item["pair_id"])))


def pair_directional_pools(
    outbound_pool: Sequence[DirectionalCandidate],
    inbound_pool: Sequence[DirectionalCandidate],
    *,
    runtime_minutes: int,
    minimum_layover_minutes: int,
    fleet_ceiling: int,
) -> tuple[list[dict[str, Any]], tuple[Mapping[str, Any], ...]]:
    pairs = []
    for outbound in outbound_pool:
        for inbound in inbound_pool:
            fleet = _pair_fleet_metrics(
                outbound,
                inbound,
                runtime_minutes=runtime_minutes,
                minimum_layover_minutes=minimum_layover_minutes,
                fleet_ceiling=fleet_ceiling,
            )
            pair_id = f"{outbound.candidate_id}__{inbound.candidate_id}"
            pairs.append(
                {
                    "pair_id": pair_id,
                    "outbound_candidate_id": outbound.candidate_id,
                    "inbound_candidate_id": inbound.candidate_id,
                    "metrics": _pair_operational_metrics(outbound, inbound, fleet),
                }
            )
    feasible = [pair for pair in pairs if pair["metrics"]["fleet_feasible"]]
    return pairs, pareto_frontier(feasible)


def _candidate_payload(candidate: DirectionalCandidate) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "direction": candidate.direction,
        "exact_departure_fingerprint": _fingerprint_offsets(
            candidate.label.departure_offsets_minutes
        ),
        "clean_design_verified": True,
        "regimes": [asdict(regime) for regime in candidate.label.regimes],
        "metrics": candidate.metrics,
    }


def _pool_diversity(pool: Sequence[DirectionalCandidate]) -> dict[str, Any]:
    distances = []
    for index, left in enumerate(pool):
        for right in pool[index + 1 :]:
            distances.append(
                sum(
                    abs(a - b) // 60 for a, b in zip(left.departures, right.departures, strict=True)
                )
            )
    sequence_count = len(
        {
            tuple((regime.headway_minutes, regime.gap_count) for regime in item.label.regimes)
            for item in pool
        }
    )
    composition_count = len(
        {tuple(sorted(_composition_histogram(item.label).items())) for item in pool}
    )
    return {
        "distinct_service_regime_sequences": sequence_count,
        "distinct_headway_composition_histograms": composition_count,
        "distinct_exact_departure_vectors": len(
            {item.label.departure_offsets_minutes for item in pool}
        ),
        "pairwise_departure_vector_l1_minutes": {
            "minimum": min(distances, default=0),
            "median": statistics.median(distances) if distances else 0,
            "maximum": max(distances, default=0),
        },
    }


def _reference_candidate(
    label: str,
    direction: str,
    departures: Sequence[int],
    *,
    demand_buckets: Sequence[DemandBucketEvidenceV1],
    current_departures: Sequence[int],
    human_final_departures: Sequence[int],
) -> DirectionalCandidate:
    regimes = _regimes_from_departures(departures)
    offsets = tuple((value - departures[0]) // 60 for value in departures)
    design = DesignLabel(regimes, offsets, _fingerprint_offsets(offsets))
    return DirectionalCandidate(
        candidate_id=f"{label}_{direction.upper()}",
        direction=direction,
        label=design,
        departures=tuple(departures),
        metrics=directional_metrics(
            departures,
            regimes=regimes,
            demand_buckets=demand_buckets,
            current_departures=current_departures,
            human_final_departures=human_final_departures,
        ),
    )


def _reference_metrics(parsed: Mapping[str, Any], context: Any) -> dict[str, Any]:
    current = parsed["references"]["CURRENT"]
    human = parsed["references"]["HUMAN_FINAL"]
    references = {}
    for label in REFERENCE_LABELS:
        supplied = parsed["references"][label]
        outbound = _reference_candidate(
            label,
            "outbound",
            supplied["outbound"],
            demand_buckets=context.demand_buckets["outbound"],
            current_departures=current["outbound"],
            human_final_departures=human["outbound"],
        )
        inbound = _reference_candidate(
            label,
            "inbound",
            supplied["inbound"],
            demand_buckets=context.demand_buckets["inbound"],
            current_departures=current["inbound"],
            human_final_departures=human["inbound"],
        )
        fleet = _pair_fleet_metrics(
            outbound,
            inbound,
            runtime_minutes=context.runtime_minutes,
            minimum_layover_minutes=context.minimum_layover_minutes,
            fleet_ceiling=context.fleet_ceiling,
        )
        references[label] = {
            "source_label": label,
            "sheet_name": supplied["sheet_name"],
            "external_project_lineage": False if label == "EXTERNAL_AI" else None,
            "outbound": outbound.metrics,
            "inbound": inbound.metrics,
            "pair": _pair_operational_metrics(outbound, inbound, fleet),
        }
    return references


def _reference_pair_vector(reference: Mapping[str, Any]) -> tuple[float, ...]:
    wrapper = {"metrics": reference["pair"]}
    return _pair_vector(wrapper)


def classify_clean_vs_human(
    frontier: Sequence[Mapping[str, Any]], human_reference: Mapping[str, Any]
) -> tuple[str, list[str]]:
    if not frontier:
        return "NO_CLEAN_GLOBAL_DESIGN_FOUND", []
    human_vector = _reference_pair_vector(human_reference)
    clean_dominating = [
        pair["pair_id"] for pair in frontier if _dominates(_pair_vector(pair), human_vector)
    ]
    if clean_dominating:
        return "CLEAN_DESIGN_DOMINATING_HUMAN_REFERENCE_EXISTS", sorted(clean_dominating)
    if all(_dominates(human_vector, _pair_vector(pair)) for pair in frontier):
        return "HUMAN_REFERENCE_NONDOMINATED_BY_CLEAN_DESIGNS", []
    return "CLEAN_VS_HUMAN_TRADEOFF", []


def _authority_evidence(
    repo_root: Path, authority_root: Path, coordinator_workbook: Path, context: Any
) -> dict[str, Any]:
    manifest = json.loads(
        (repo_root / "config/service_plan_coordinator_frozen_prior_v1.json").read_text(
            encoding="utf-8"
        )
    )
    artifacts = []
    for relative in EXPECTED_DIRECT_ARTIFACTS:
        path = authority_root / relative
        actual = _sha256(path)
        if actual != manifest["sha256"].get(relative):
            raise ValueError(f"frozen authority artifact changed: {relative}")
        artifacts.append({"relative_path": relative, "sha256": actual})
    if (context.runtime_minutes, context.minimum_layover_minutes, context.fleet_ceiling) != (
        70,
        5,
        20,
    ):
        raise ValueError("Route 6 operating authority changed")
    return {
        "loader": "load_route_coordinator_inputs_v1",
        "immutable_demand_sha256": context.immutable_demand_sha256,
        "coordinator_input_workbook": {
            "basename": coordinator_workbook.name,
            "sha256": _sha256(coordinator_workbook),
        },
        "direct_frozen_artifacts": artifacts,
        "runtime_minutes_each_direction": context.runtime_minutes,
        "minimum_layover_minutes": context.minimum_layover_minutes,
        "fleet_ceiling": context.fleet_ceiling,
    }


def _run_configuration(
    *,
    settings: SearchSettings,
    parsed: Mapping[str, Any],
    context: Any,
    selection_metric_cache: dict[tuple[str, str], tuple[tuple[float | int, ...], str]],
    full_metrics_cache: dict[tuple[str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    current = parsed["references"]["CURRENT"]
    human = parsed["references"]["HUMAN_FINAL"]
    bounded_completed, shared_stats, bounded_oracles = run_directional_dp(
        direction="outbound",
        demand_buckets=context.demand_buckets["outbound"],
        settings=settings,
    )
    low_regime_sequences = enumerate_exact_clean_sequences_up_to_three_regimes()
    low_regime_labels = _labels_from_regime_sequences(low_regime_sequences)
    completed_by_vector = {
        label.departure_offsets_minutes: label for label in (*bounded_completed, *low_regime_labels)
    }
    completed = tuple(sorted(completed_by_vector.values(), key=lambda item: item.fingerprint))
    pools: dict[str, tuple[DirectionalCandidate, ...]] = {}
    dp_payload = {}
    for direction in ("outbound", "inbound"):
        pool = retain_directional_pool(
            completed,
            direction=direction,
            capacity=settings.directional_final_pool,
            demand_buckets=context.demand_buckets[direction],
            current_departures=current[direction],
            human_final_departures=human[direction],
            selection_metric_cache=selection_metric_cache,
            full_metrics_cache=full_metrics_cache,
        )
        pools[direction] = pool
        statistics_payload = asdict(shared_stats)
        statistics_payload["bounded_dp_complete_designs_found"] = (
            shared_stats.complete_directional_designs_found
        )
        statistics_payload["exhaustive_one_to_three_regime_designs_found"] = len(low_regime_labels)
        statistics_payload["complete_directional_designs_found"] = len(completed)
        statistics_payload["retained_directional_candidates"] = len(pool)
        dp_payload[direction] = {
            "statistics": statistics_payload,
            "bounded_archive_oracle_presence": bounded_oracles,
            "pool_diversity": _pool_diversity(pool),
            "retained_candidates": [_candidate_payload(item) for item in pool],
        }
    pairs, frontier = pair_directional_pools(
        pools["outbound"],
        pools["inbound"],
        runtime_minutes=context.runtime_minutes,
        minimum_layover_minutes=context.minimum_layover_minutes,
        fleet_ceiling=context.fleet_ceiling,
    )
    return {
        "settings": asdict(settings),
        "directional_search": dp_payload,
        "pair_fleet_validations": len(pairs),
        "pair_results": pairs,
        "fleet_feasible_pair_count": sum(pair["metrics"]["fleet_feasible"] for pair in pairs),
        "pareto_frontier_pair_ids": [pair["pair_id"] for pair in frontier],
        "pareto_frontier": list(frontier),
        "pareto_size": len(frontier),
    }


def _name_pareto_pairs(
    configuration: Mapping[str, Any],
) -> list[dict[str, Any]]:
    outbound = {
        item["candidate_id"]: item
        for item in configuration["directional_search"]["outbound"]["retained_candidates"]
    }
    inbound = {
        item["candidate_id"]: item
        for item in configuration["directional_search"]["inbound"]["retained_candidates"]
    }
    named = []
    for index, pair in enumerate(configuration["pareto_frontier"], start=1):
        named.append(
            {
                "pareto_id": f"CLEAN_PARETO_{index:03d}",
                "pair_id": pair["pair_id"],
                "outbound": outbound[pair["outbound_candidate_id"]],
                "inbound": inbound[pair["inbound_candidate_id"]],
                "metrics": pair["metrics"],
            }
        )
    return named


def run_experiment(
    *,
    repo_root: Path,
    workbook_path: Path,
    authority_root: Path,
    coordinator_workbook: Path,
) -> dict[str, Any]:
    if _sha256(workbook_path) != "c2038b31c5a3f6a3ee2377ce2067542cc718a7d1907722efa3ab45a536bdd14a":
        raise ValueError("private Route 6 workbook SHA-256 changed")
    parsed = parse_route6_reference_workbook(workbook_path)
    if parsed["reference_sheet_names"] != {
        "CURRENT": "06 hiện hữu",
        "EXTERNAL_AI": "06 AI",
        "HUMAN_FINAL": "06 final",
    }:
        raise ValueError("private Route 6 workbook sheet mapping changed")
    context, _ = load_route_coordinator_inputs_v1(
        repo_root=authority_root,
        route_id="6",
        workbook_path=coordinator_workbook,
    )
    references = _reference_metrics(parsed, context)
    selection_metric_cache: dict[tuple[str, str], tuple[tuple[float | int, ...], str]] = {}
    full_metrics_cache: dict[tuple[str, str], Mapping[str, Any]] = {}
    base = _run_configuration(
        settings=SearchSettings("BASE", 16, 64, 64),
        parsed=parsed,
        context=context,
        selection_metric_cache=selection_metric_cache,
        full_metrics_cache=full_metrics_cache,
    )
    sensitivity = _run_configuration(
        settings=SearchSettings("SENSITIVITY", 32, 96, 96),
        parsed=parsed,
        context=context,
        selection_metric_cache=selection_metric_cache,
        full_metrics_cache=full_metrics_cache,
    )
    base_classification, base_dominating = classify_clean_vs_human(
        base["pareto_frontier"], references["HUMAN_FINAL"]
    )
    sensitivity_classification, sensitivity_dominating = classify_clean_vs_human(
        sensitivity["pareto_frontier"], references["HUMAN_FINAL"]
    )
    stable = base_classification == sensitivity_classification
    base["human_final_comparison"] = {
        "classification": base_classification,
        "clean_pairs_dominating_human_final": base_dominating,
    }
    sensitivity["human_final_comparison"] = {
        "classification": sensitivity_classification,
        "clean_pairs_dominating_human_final": sensitivity_dominating,
    }
    named_pareto = _name_pareto_pairs(sensitivity)
    return {
        "experiment_profile": EXPERIMENT_PROFILE,
        "review_only": True,
        "source_workbook": {
            "basename": workbook_path.name,
            "sha256": _sha256(workbook_path),
            "reference_sheet_names": parsed["reference_sheet_names"],
        },
        "fixed_timetable_authority": {
            "departures_per_direction": 78,
            "first_departure": "04:55",
            "last_departure": "21:00",
            "gaps_per_direction": TOTAL_GAPS,
            "operating_span_minutes": OPERATING_SPAN_MINUTES,
            "whole_minute_departures": True,
        },
        "route6_authority": _authority_evidence(
            repo_root, authority_root, coordinator_workbook, context
        ),
        "technical_search": {
            "algorithm": (
                "BOUNDED_DETERMINISTIC_ALL_K_SEGMENT_LABEL_SETTING_DP_PLUS_"
                "EXHAUSTIVE_ONE_TO_THREE_REGIME_ANCHOR_CENSUS"
            ),
            "state": ["gaps_used", "elapsed_minutes", "last_headway"],
            "technical_headway_domain_minutes": [
                TECHNICAL_HEADWAY_MIN,
                TECHNICAL_HEADWAY_MAX,
            ],
            "minimum_service_regime_gap_count": 2,
            "arithmetic_feasibility_pruning": (
                "remaining_gaps*min_headway <= remaining_minutes <= remaining_gaps*max_headway"
            ),
            "bounded_archive_is_search_approximation_not_transport_policy": True,
            "per_gap_layer_label_cap_derivation": "equal to directional_final_pool",
            "direction_local_pareto_elimination_used": False,
            "retention": (
                "deterministic metric anchors followed by greedy max-min exact-departure distance"
            ),
            "arithmetic_acceptance_oracles": arithmetic_acceptance_oracles(),
        },
        "expected_wait_metric": {
            "name": "demand_weighted_expected_passenger_wait_minutes",
            "assumption": WAIT_ASSUMPTION,
            "calculation": (
                "exact integration of next-departure wait over each interdeparture/bucket "
                "overlap, weighted by piecewise-constant immutable demand intensity"
            ),
            "common_active_service_span": ["04:55", "21:00"],
        },
        "reference_timetable_metrics": references,
        "base_search": base,
        "sensitivity_search": sensitivity,
        "clean_pareto_candidates": named_pareto,
        "human_final_comparison": {
            "base_classification": base_classification,
            "sensitivity_classification": sensitivity_classification,
            "classification_stable_across_archive_settings": stable,
            "classification_confidence": (
                "STABLE_ACROSS_ARCHIVE_SETTINGS" if stable else "BOUNDED_SEARCH_SENSITIVE"
            ),
            "clean_pairs_dominating_human_final": sensitivity_dominating,
        },
        "evidence_classification": sensitivity_classification,
        "limitations": [
            "Single Route 6 experiment; the 5-30 minute domain is a technical bound, not policy.",
            "Per-state and final-pool caps make the search an explicitly bounded approximation.",
            "Uniform passenger arrivals within immutable 30-minute buckets are an experiment assumption.",
            "Human Final is a post-search benchmark and is not a search target.",
            "No production compiler, search, fleet, demand, or protection semantics changed.",
        ],
        "production_change_guard": {
            "production_policy_changed": False,
            "compiler_policy_changed": False,
            "production_coordinator_budget_changed": False,
            "statement": "NO PRODUCTION POLICY CHANGED",
        },
    }


def _compact_structure(candidate: Mapping[str, Any]) -> str:
    return " → ".join(
        f"{item['start']}-{item['end']}@{item['headway_minutes']}"
        for item in candidate["metrics"]["service_regimes"]
    )


def render_markdown(payload: Mapping[str, Any]) -> str:
    source = payload["source_workbook"]
    references = payload["reference_timetable_metrics"]
    base = payload["base_search"]
    sensitivity = payload["sensitivity_search"]
    lines = [
        "# PR62-C1 — Global clean ServiceRegime rhythm-design experiment",
        "",
        "> Experiment-only evidence. No production compiler/search policy changed.",
        "",
        "## Question and method",
        "",
        f"The private benchmark `{source['basename']}` is bound by SHA-256 "
        f"`{source['sha256']}`. The search independently redesigns each complete 04:55–21:00 "
        "direction as sustained whole-minute ServiceRegimes with at least two gaps per regime.",
        "",
        "The deterministic label-setting DP uses state `(gaps_used, elapsed_minutes, "
        "last_headway)`, headways 5–30 minutes, arithmetic feasibility pruning, metric anchors, "
        "and exact-departure max-min diversity. A general exhaustive one-to-three-regime "
        "arithmetic census supplies low-regime completeness anchors across the same headway "
        "domain. Archive caps are search approximations, not transport policy.",
        "",
        f"Expected passenger wait uses `{WAIT_ASSUMPTION}` and exact interdeparture/bucket "
        "integration.",
        "",
        "## Reference benchmarks",
        "",
        "| Reference | Pair mismatch | Expected wait | Max bucket wait | Fleet | Excess wait "
        "total/max | Regimes | Unique complexity | Max jump | Total variation | Tails Out/In |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for label in REFERENCE_LABELS:
        item = references[label]
        pair = item["pair"]
        lines.append(
            f"| {label} | {pair['pair_immutable_demand_mismatch']:.10f} | "
            f"{pair['network_demand_weighted_expected_passenger_wait_minutes']:.4f} | "
            f"{pair['maximum_bucket_expected_wait_minutes']:.4f} | "
            f"{pair['fleet_required']}/{pair['fleet_ceiling']} | "
            f"{pair['total_excess_terminal_wait_minutes']}/"
            f"{pair['maximum_excess_terminal_wait_minutes']} | "
            f"{pair['total_service_regime_count']} | "
            f"{pair['total_unique_headway_complexity']} | "
            f"{pair['maximum_frequency_jump']:.6f} | "
            f"{pair['total_frequency_variation']:.6f} | "
            f"{item['outbound']['tail']['tail_headway_minutes']}@"
            f"{item['outbound']['tail']['tail_start']} / "
            f"{item['inbound']['tail']['tail_headway_minutes']}@"
            f"{item['inbound']['tail']['tail_start']} |"
        )
    lines.extend(
        [
            "",
            "## Bounded-search sensitivity",
            "",
            "| Configuration | State cap | Pool cap | Out/In states | Out/In complete | "
            "Out/In retained | Fleet validations | Feasible pairs | Pareto size | Classification |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for config in (base, sensitivity):
        out = config["directional_search"]["outbound"]["statistics"]
        inn = config["directional_search"]["inbound"]["statistics"]
        lines.append(
            f"| {config['settings']['name']} | {config['settings']['per_state_archive']} | "
            f"{config['settings']['directional_final_pool']} | "
            f"{out['states_reached']}/{inn['states_reached']} | "
            f"{out['complete_directional_designs_found']}/"
            f"{inn['complete_directional_designs_found']} | "
            f"{out['retained_directional_candidates']}/"
            f"{inn['retained_directional_candidates']} | "
            f"{config['pair_fleet_validations']} | {config['fleet_feasible_pair_count']} | "
            f"{config['pareto_size']} | "
            f"{config['human_final_comparison']['classification']} |"
        )
    lines.extend(
        [
            "",
            "## Sensitivity clean Pareto frontier",
            "",
            "| Candidate | Pair mismatch | Expected wait | Max bucket wait | Fleet | Excess wait "
            "total/max | Regimes | Unique complexity | Max jump | Total variation |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for candidate in payload["clean_pareto_candidates"]:
        metrics = candidate["metrics"]
        lines.append(
            f"| {candidate['pareto_id']} | "
            f"{metrics['pair_immutable_demand_mismatch']:.10f} | "
            f"{metrics['network_demand_weighted_expected_passenger_wait_minutes']:.4f} | "
            f"{metrics['maximum_bucket_expected_wait_minutes']:.4f} | "
            f"{metrics['fleet_required']}/{metrics['fleet_ceiling']} | "
            f"{metrics['total_excess_terminal_wait_minutes']}/"
            f"{metrics['maximum_excess_terminal_wait_minutes']} | "
            f"{metrics['total_service_regime_count']} | "
            f"{metrics['total_unique_headway_complexity']} | "
            f"{metrics['maximum_frequency_jump']:.6f} | "
            f"{metrics['total_frequency_variation']:.6f} |"
        )
    for candidate in payload["clean_pareto_candidates"]:
        lines.extend(
            [
                "",
                f"### {candidate['pareto_id']}",
                "",
                f"- OUTBOUND: `{_compact_structure(candidate['outbound'])}`",
                f"- OUTBOUND arithmetic: "
                f"`{candidate['outbound']['metrics']['headway_composition']['algebra']}`",
                f"- INBOUND: `{_compact_structure(candidate['inbound'])}`",
                f"- INBOUND arithmetic: "
                f"`{candidate['inbound']['metrics']['headway_composition']['algebra']}`",
            ]
        )
    comparison = payload["human_final_comparison"]
    lines.extend(
        [
            "",
            "## Evidence classification",
            "",
            f"**{payload['evidence_classification']}**",
            "",
            "Classification stable across base and sensitivity archives: "
            f"**{'yes' if comparison['classification_stable_across_archive_settings'] else 'no'}** "
            f"(`{comparison['classification_confidence']}`).",
            "",
            "This is evidence only. No settlement support, transition regime, compiler rule, "
            "or production search budget changed.",
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in payload["limitations"]],
            "",
        ]
    )
    return "\n".join(lines)


def _resolve_private_workbook(repo_root: Path) -> Path:
    path = repo_root / "private/Route_6_Current_ExternalAI_HumanFinal.xlsx"
    if not path.is_file():
        raise FileNotFoundError(path.name)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--authority-root", type=Path, default=None)
    parser.add_argument("--coordinator-workbook", type=Path, default=None)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    authority_root = (args.authority_root or repo_root).resolve()
    coordinator_workbook = (
        args.coordinator_workbook
        or repo_root / "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx"
    ).resolve()
    payload = run_experiment(
        repo_root=repo_root,
        workbook_path=_resolve_private_workbook(repo_root),
        authority_root=authority_root,
        coordinator_workbook=coordinator_workbook,
    )
    json_path = repo_root / OUTPUT_JSON
    markdown_path = repo_root / OUTPUT_MARKDOWN
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    markdown_path.write_text(render_markdown(payload), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "classification": payload["evidence_classification"],
                "classification_stable": payload["human_final_comparison"][
                    "classification_stable_across_archive_settings"
                ],
                "pareto_size": len(payload["clean_pareto_candidates"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
