"""PR62-C2 Route 6 demand-response contrast calibration.

This module is experiment-only.  It characterizes exact timetable service frequency
against the already-selected canonical DemandRegimes; it changes no production policy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from route6_boundary_settlement_experiment import (
    REFERENCE_LABELS,
    _sha256,
    parse_route6_reference_workbook,
)

EXPERIMENT_PROFILE = "pr62_c2_route6_demand_response_contrast_v1"
EXPECTED_WORKBOOK_SHA256 = "c2038b31c5a3f6a3ee2377ce2067542cc718a7d1907722efa3ab45a536bdd14a"
EXPECTED_C1_PROFILE = "pr62_c1_route6_global_clean_rhythm_design_v1"
EXPECTED_DEMAND_SHA256 = "f9c89f16cf7a9b0f29ee76db065c0cc182de2b0698c4ba71ce8437f1e1f5e3b6"
EXPECTED_SHEETS = {
    "CURRENT": "06 hiện hữu",
    "EXTERNAL_AI": "06 AI",
    "HUMAN_FINAL": "06 final",
}
COMMON_SERVICE_START = 4 * 3600 + 55 * 60
COMMON_SERVICE_END = 21 * 3600
NUMERICAL_ZERO_TOLERANCE = 1e-12
OUTPUT_JSON = Path("docs/engine/evidence/PR62_C2_ROUTE6_DEMAND_RESPONSE_CONTRAST.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_C2_ROUTE6_DEMAND_RESPONSE_CONTRAST.md")
C1_EVIDENCE = Path("docs/engine/evidence/PR62_C1_ROUTE6_GLOBAL_CLEAN_RHYTHM_DESIGN.json")
DEMAND_EVIDENCE = Path("outputs/demand_regime_model_selection/route_6_demand_regimes.json")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _hhmm(seconds: int) -> str:
    minutes = seconds // 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _hhmm_seconds(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return (hour * 60 + minute) * 60


def _overlap_seconds(left_start: int, left_end: int, right_start: int, right_end: int) -> int:
    return max(0, min(left_end, right_end) - max(left_start, right_start))


def _bucket_value(bucket: Any, field: str) -> float | int | str:
    if isinstance(bucket, Mapping):
        aliases = {
            "start": ("start", "interval_start"),
            "end": ("end", "interval_end"),
            "observed_demand": ("observed_demand", "raw_derived_average"),
            "direction": ("direction",),
        }
        for name in aliases[field]:
            if name in bucket:
                return bucket[name]
        raise KeyError(field)
    return getattr(bucket, field)


def integrate_demand_mass(
    demand_buckets: Sequence[Any], *, window_start: int, window_end: int
) -> float:
    """Integrate piecewise-constant bucket mass by exact temporal overlap."""

    if window_end <= window_start:
        raise ValueError("demand integration window must have positive duration")
    mass = 0.0
    for bucket in demand_buckets:
        start = int(_bucket_value(bucket, "start"))
        end = int(_bucket_value(bucket, "end"))
        if end <= start:
            raise ValueError("demand bucket must have positive duration")
        overlap = _overlap_seconds(start, end, window_start, window_end)
        mass += float(_bucket_value(bucket, "observed_demand")) * overlap / (end - start)
    return mass


def effective_service_frequency_per_hour(
    departures: Sequence[int], *, window_start: int, window_end: int
) -> float:
    """Project exact interdeparture frequency onto a time window."""

    if window_end <= window_start:
        raise ValueError("service projection window must have positive duration")
    if len(departures) < 2 or tuple(sorted(departures)) != tuple(departures):
        raise ValueError("at least two strictly ordered departures are required")
    if len(set(departures)) != len(departures):
        raise ValueError("departures must be unique")
    integral = 0.0
    covered = 0
    for left, right in zip(departures, departures[1:], strict=False):
        overlap = _overlap_seconds(left, right, window_start, window_end)
        if overlap:
            integral += 3600.0 / (right - left) * overlap
            covered += overlap
    duration = window_end - window_start
    if covered != duration:
        raise ValueError(
            f"exact timetable covers {covered} of {duration} seconds in the DemandRegime"
        )
    return integral / duration


def build_canonical_regime_evidence(
    raw_regimes: Sequence[Mapping[str, Any]],
    demand_buckets: Sequence[Any],
    *,
    service_start: int = COMMON_SERVICE_START,
    service_end: int = COMMON_SERVICE_END,
) -> list[dict[str, Any]]:
    """Clip selected regimes to the common active span and integrate immutable demand."""

    evidence: list[dict[str, Any]] = []
    for raw in raw_regimes:
        start = max(int(raw["start_time"]), service_start)
        end = min(int(raw["end_time"]), service_end)
        if end <= start:
            continue
        mass = integrate_demand_mass(demand_buckets, window_start=start, window_end=end)
        duration_hours = (end - start) / 3600.0
        evidence.append(
            {
                "regime_id": str(raw["regime_id"]),
                "direction": str(raw["direction"]),
                "canonical_start": _hhmm(int(raw["start_time"])),
                "canonical_end": _hhmm(int(raw["end_time"])),
                "active_start": _hhmm(start),
                "active_end": _hhmm(end),
                "active_start_seconds": start,
                "active_end_seconds": end,
                "active_duration_minutes": (end - start) / 60.0,
                "integrated_immutable_demand_mass": mass,
                "demand_rate_per_hour": mass / duration_hours,
            }
        )
    if not evidence:
        raise ValueError("no canonical DemandRegime overlaps the active service span")
    return evidence


def _average_ranks(values: Sequence[float], *, descending: bool) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index], reverse=descending)
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position + 1
        while end < len(order) and values[order[end]] == values[order[position]]:
            end += 1
        rank = ((position + 1) + end) / 2.0
        for index in order[position:end]:
            ranks[index] = rank
        position = end
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) < 2 or len(left) != len(right):
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum(
        (left_value - left_mean) * (right_value - right_mean)
        for left_value, right_value in zip(left, right, strict=True)
    )
    left_scale = sum((value - left_mean) ** 2 for value in left)
    right_scale = sum((value - right_mean) ** 2 for value in right)
    if left_scale <= NUMERICAL_ZERO_TOLERANCE or right_scale <= NUMERICAL_ZERO_TOLERANCE:
        return None
    return numerator / math.sqrt(left_scale * right_scale)


def demand_service_rank_correlation(rows: Sequence[Mapping[str, Any]]) -> float | None:
    if len(rows) < 2:
        return None
    demand = [float(row["demand_rate_per_hour"]) for row in rows]
    service = [float(row["effective_service_frequency_per_hour"]) for row in rows]
    return _pearson(
        _average_ranks(demand, descending=True),
        _average_ranks(service, descending=True),
    )


def weighted_log_log_regression(rows: Sequence[Mapping[str, Any]]) -> dict[str, float | None]:
    """Fit log(service)=alpha+gamma*log(demand), weighted by active duration."""

    if len(rows) < 2:
        return {"alpha": None, "gamma": None, "weighted_rmse": None, "weighted_r_squared": None}
    x = [math.log(float(row["demand_rate_per_hour"])) for row in rows]
    y = [math.log(float(row["effective_service_frequency_per_hour"])) for row in rows]
    weights = [float(row["active_duration_minutes"]) for row in rows]
    weight_sum = sum(weights)
    x_mean = sum(weight * value for weight, value in zip(weights, x, strict=True)) / weight_sum
    y_mean = sum(weight * value for weight, value in zip(weights, y, strict=True)) / weight_sum
    denominator = sum(
        weight * (value - x_mean) ** 2 for weight, value in zip(weights, x, strict=True)
    )
    if denominator <= NUMERICAL_ZERO_TOLERANCE:
        return {"alpha": None, "gamma": None, "weighted_rmse": None, "weighted_r_squared": None}
    gamma = (
        sum(
            weight * (x_value - x_mean) * (y_value - y_mean)
            for weight, x_value, y_value in zip(weights, x, y, strict=True)
        )
        / denominator
    )
    alpha = y_mean - gamma * x_mean
    residuals = [y_value - (alpha + gamma * x_value) for x_value, y_value in zip(x, y, strict=True)]
    squared_error = sum(
        weight * residual**2 for weight, residual in zip(weights, residuals, strict=True)
    )
    total_error = sum(
        weight * (value - y_mean) ** 2 for weight, value in zip(weights, y, strict=True)
    )
    r_squared = None if total_error <= NUMERICAL_ZERO_TOLERANCE else 1 - squared_error / total_error
    return {
        "alpha": alpha,
        "gamma": gamma,
        "weighted_rmse": math.sqrt(squared_error / weight_sum),
        "weighted_r_squared": r_squared,
    }


def _sign(value: float) -> int:
    if math.isclose(value, 0.0, abs_tol=NUMERICAL_ZERO_TOLERANCE):
        return 0
    return 1 if value > 0 else -1


def _direction_name(sign: int, *, flat_allowed: bool) -> str:
    if sign > 0:
        return "UP"
    if sign < 0:
        return "DOWN"
    return "FLAT" if flat_allowed else "UNCHANGED"


def analyze_direction(
    departures: Sequence[int],
    canonical_regimes: Sequence[Mapping[str, Any]],
    *,
    exact_service_regime_headways: Sequence[float] | None = None,
) -> dict[str, Any]:
    """Calculate the complete C2 response evidence for one timetable direction."""

    rows: list[dict[str, Any]] = []
    for regime in canonical_regimes:
        frequency = effective_service_frequency_per_hour(
            departures,
            window_start=int(regime["active_start_seconds"]),
            window_end=int(regime["active_end_seconds"]),
        )
        rows.append(
            {
                **dict(regime),
                "effective_service_frequency_per_hour": frequency,
                "effective_headway_minutes": 60.0 / frequency,
            }
        )
    demand_ranks = _average_ranks(
        [float(row["demand_rate_per_hour"]) for row in rows], descending=True
    )
    service_ranks = _average_ranks(
        [float(row["effective_service_frequency_per_hour"]) for row in rows],
        descending=True,
    )
    for row, demand_rank, service_rank in zip(rows, demand_ranks, service_ranks, strict=True):
        row["demand_rank"] = demand_rank
        row["service_rank"] = service_rank

    adjacent: list[dict[str, Any]] = []
    for left, right in zip(rows, rows[1:], strict=False):
        delta_demand = math.log(
            float(right["demand_rate_per_hour"]) / float(left["demand_rate_per_hour"])
        )
        delta_service = math.log(
            float(right["effective_service_frequency_per_hour"])
            / float(left["effective_service_frequency_per_hour"])
        )
        demand_sign = _sign(delta_demand)
        service_sign = _sign(delta_service)
        weight = (
            float(left["active_duration_minutes"]) + float(right["active_duration_minutes"])
        ) / 2.0
        expected = 0.5 * delta_demand
        adjacent.append(
            {
                "left_regime_id": left["regime_id"],
                "right_regime_id": right["regime_id"],
                "duration_weight_minutes": weight,
                "delta_log_demand": delta_demand,
                "delta_log_service": delta_service,
                "demand_direction": _direction_name(demand_sign, flat_allowed=False),
                "service_direction": _direction_name(service_sign, flat_allowed=True),
                "sign_agreement": demand_sign != 0 and demand_sign == service_sign,
                "absolute_demand_contrast": abs(delta_demand),
                "absolute_service_contrast": abs(delta_service),
                "sqrt_seed_expected_delta_log_service": expected,
                "sqrt_response_residual": delta_service - expected,
            }
        )

    high = max(rows, key=lambda row: (float(row["demand_rate_per_hour"]), row["regime_id"]))
    low = min(rows, key=lambda row: (float(row["demand_rate_per_hour"]), row["regime_id"]))
    demand_ratio = float(high["demand_rate_per_hour"]) / float(low["demand_rate_per_hour"])
    service_ratio = float(high["effective_service_frequency_per_hour"]) / float(
        low["effective_service_frequency_per_hour"]
    )
    elasticity = None
    if not math.isclose(demand_ratio, 1.0, abs_tol=NUMERICAL_ZERO_TOLERANCE):
        elasticity = math.log(service_ratio) / math.log(demand_ratio)

    frequencies = [float(row["effective_service_frequency_per_hour"]) for row in rows]
    headways = [float(row["effective_headway_minutes"]) for row in rows]
    weight_sum = sum(float(item["duration_weight_minutes"]) for item in adjacent)
    nonzero_demand = [item for item in adjacent if _sign(float(item["delta_log_demand"]))]
    nonzero_weight = sum(float(item["duration_weight_minutes"]) for item in nonzero_demand)
    direction_accuracy = None
    if nonzero_weight:
        direction_accuracy = (
            sum(
                float(item["duration_weight_minutes"])
                for item in nonzero_demand
                if item["sign_agreement"]
            )
            / nonzero_weight
        )
    sqrt_deviation = None
    actual_amplitude = 0.0
    sqrt_amplitude = 0.0
    if weight_sum:
        sqrt_deviation = (
            sum(
                float(item["duration_weight_minutes"]) * abs(float(item["sqrt_response_residual"]))
                for item in adjacent
            )
            / weight_sum
        )
        actual_amplitude = sum(
            float(item["duration_weight_minutes"]) * abs(float(item["delta_log_service"]))
            for item in adjacent
        )
        sqrt_amplitude = sum(
            float(item["duration_weight_minutes"]) * 0.5 * abs(float(item["delta_log_demand"]))
            for item in adjacent
        )
    amplitude_ratio = (
        None if sqrt_amplitude <= NUMERICAL_ZERO_TOLERANCE else actual_amplitude / sqrt_amplitude
    )
    regression = weighted_log_log_regression(rows)
    payload: dict[str, Any] = {
        "exact_departure_fingerprint": _fingerprint(list(departures)),
        "demand_aligned_service_response_table": rows,
        "adjacent_demand_contrasts": adjacent,
        "peak_low_comparison": {
            "high_demand_regime_id": high["regime_id"],
            "low_demand_regime_id": low["regime_id"],
            "high_demand_rate_per_hour": high["demand_rate_per_hour"],
            "low_demand_rate_per_hour": low["demand_rate_per_hour"],
            "demand_peak_low_ratio": demand_ratio,
            "high_demand_service_frequency_per_hour": high["effective_service_frequency_per_hour"],
            "low_demand_service_frequency_per_hour": low["effective_service_frequency_per_hour"],
            "service_peak_low_ratio": service_ratio,
            "peak_low_response_elasticity": elasticity,
        },
        "service_differentiation": {
            "minimum_effective_service_frequency_per_hour": min(frequencies),
            "maximum_effective_service_frequency_per_hour": max(frequencies),
            "max_min_service_frequency_ratio": max(frequencies) / min(frequencies),
            "minimum_equivalent_headway_minutes": min(headways),
            "maximum_equivalent_headway_minutes": max(headways),
            "effective_headway_spread_minutes": max(headways) - min(headways),
            "exact_unique_service_regime_headway_count": (
                len(set(exact_service_regime_headways or ()))
                if exact_service_regime_headways is not None
                else None
            ),
        },
        "demand_service_rank_correlation": demand_service_rank_correlation(rows),
        "service_demand_response_regression": regression,
        "demand_response_direction_accuracy": direction_accuracy,
        "directionally_aligned_transition_count": sum(
            bool(item["sign_agreement"]) for item in nonzero_demand
        ),
        "nonzero_demand_transition_count": len(nonzero_demand),
        "sqrt_seed_response_deviation": sqrt_deviation,
        "actual_service_contrast_amplitude": actual_amplitude,
        "sqrt_reference_contrast_amplitude": sqrt_amplitude,
        "contrast_amplitude_ratio_to_sqrt_reference": amplitude_ratio,
    }
    payload["analysis_fingerprint"] = _fingerprint(payload)
    return payload


def _selected_regimes(demand_payload: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    selections = demand_payload["model_selection"]["selections"]
    result = {}
    for selection in selections:
        if selection["selection_status"] != "SUCCESS":
            raise ValueError(f"canonical selection failed for {selection['direction']}")
        direction = str(selection["direction"])
        result[direction] = list(selection["final_plan"]["regimes"])
    if set(result) != {"outbound", "inbound"}:
        raise ValueError(f"canonical Route 6 directions changed: {sorted(result)}")
    return result


def _demand_buckets(demand_payload: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {"outbound": [], "inbound": []}
    for bucket in demand_payload["raw_v3_reconciliation"]["buckets"]:
        result[str(bucket["direction"])].append(bucket)
    for direction in result:
        result[direction].sort(key=lambda item: int(item["interval_start"]))
    return result


def _headways(source: Mapping[str, Any]) -> list[float]:
    return [float(item["headway_minutes"]) for item in source["service_regimes"]]


def reference_lineage(label: str) -> dict[str, Any]:
    if label not in REFERENCE_LABELS:
        raise ValueError(f"unknown reference label: {label}")
    return {
        "lineage": "EXTERNAL_BENCHMARK" if label == "EXTERNAL_AI" else "SUPPLIED_REFERENCE",
        "project_engine_lineage": False,
    }


def _c1_identity(c1_path: Path, c1: Mapping[str, Any]) -> dict[str, Any]:
    if c1["experiment_profile"] != EXPECTED_C1_PROFILE:
        raise ValueError("C1 evidence profile changed")
    if len(c1["clean_pareto_candidates"]) != 9:
        raise ValueError("C1 sensitivity clean Pareto frontier no longer contains 9 candidates")
    return {
        "relative_path": C1_EVIDENCE.as_posix(),
        "sha256": _sha256(c1_path),
        "experiment_profile": c1["experiment_profile"],
        "evidence_classification": c1["evidence_classification"],
        "sensitivity_pareto_candidate_count": len(c1["clean_pareto_candidates"]),
    }


def _roles(candidates: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    metrics = {candidate["pareto_id"]: candidate["metrics"] for candidate in candidates}
    definitions = {
        "MINIMUM_FLEET_CLEAN_CANDIDATE": "fleet_required",
        "MINIMUM_DEMAND_MISMATCH_CLEAN_PARETO_CANDIDATE": "pair_immutable_demand_mismatch",
        "MINIMUM_EXPECTED_WAIT_CLEAN_PARETO_CANDIDATE": (
            "network_demand_weighted_expected_passenger_wait_minutes"
        ),
        "MINIMUM_REGULARITY_VARIATION_CLEAN_CANDIDATE": "total_frequency_variation",
    }
    result: dict[str, list[str]] = {candidate["pareto_id"]: [] for candidate in candidates}
    for role, metric in definitions.items():
        minimum = min(float(item[metric]) for item in metrics.values())
        for candidate_id, item in metrics.items():
            if float(item[metric]) == minimum:
                result[candidate_id].append(role)
    for candidate in candidates:
        headway_sets = {
            direction: {float(item["headway_minutes"]) for item in candidate[direction]["regimes"]}
            for direction in ("outbound", "inbound")
        }
        if headway_sets == {"outbound": {12.0, 13.0}, "inbound": {12.0, 13.0}}:
            result[candidate["pareto_id"]].append("CLEAN_12_13_TIMETABLE_CANDIDATE")
    return result


def _mean_available(values: Sequence[float | None]) -> float | None:
    available = [float(value) for value in values if value is not None]
    return sum(available) / len(available) if available else None


def _candidate_summary(candidate: Mapping[str, Any]) -> dict[str, Any]:
    directions = candidate["directions"]
    return {
        "mean_direction_accuracy": _mean_available(
            [directions[item]["demand_response_direction_accuracy"] for item in directions]
        ),
        "mean_rank_correlation": _mean_available(
            [directions[item]["demand_service_rank_correlation"] for item in directions]
        ),
        "mean_contrast_amplitude_ratio_to_sqrt": _mean_available(
            [directions[item]["contrast_amplitude_ratio_to_sqrt_reference"] for item in directions]
        ),
        "mean_gamma": _mean_available(
            [directions[item]["service_demand_response_regression"]["gamma"] for item in directions]
        ),
    }


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _relative_alignment_observation(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summaries = {item["pareto_id"]: _candidate_summary(item) for item in candidates}
    fields = (
        "mean_direction_accuracy",
        "mean_rank_correlation",
        "mean_contrast_amplitude_ratio_to_sqrt",
    )
    medians = {
        field: _median([float(summary[field]) for summary in summaries.values()])
        for field in fields
    }
    stronger = [
        candidate_id
        for candidate_id, summary in summaries.items()
        if float(summary["mean_direction_accuracy"]) > 0
        and float(summary["mean_rank_correlation"]) > 0
        and float(summary["mean_gamma"]) > 0
        and float(summary["mean_contrast_amplitude_ratio_to_sqrt"])
        >= medians["mean_contrast_amplitude_ratio_to_sqrt"]
    ]
    return {
        "method": (
            "sample-relative only: positive mean direction accuracy, rank correlation, and "
            "gamma, plus mean amplitude ratio at or above the nine-candidate median; this uses "
            "mathematical sign and a compared-sample median, not an absolute policy threshold "
            "or scalar score"
        ),
        "sample_medians": medians,
        "relatively_stronger_demand_aligned_candidates": stronger,
        "candidate_summaries": summaries,
    }


def _comparison_rows(
    references: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows = []
    for label, schedule in references.items():
        for direction, response in schedule["directions"].items():
            source = schedule["c1_metrics"][direction]
            rows.append(
                {
                    "schedule_or_candidate": label,
                    "direction": direction,
                    "fleet": schedule["pair_metrics"]["fleet_required"],
                    "demand_mismatch": source["immutable_demand_mismatch"],
                    "expected_passenger_wait_minutes": source[
                        "demand_weighted_expected_passenger_wait_minutes"
                    ],
                    "regime_count": source["regime_count"],
                    "service_peak_low_ratio": response["peak_low_comparison"][
                        "service_peak_low_ratio"
                    ],
                    "response_elasticity_gamma": response["service_demand_response_regression"][
                        "gamma"
                    ],
                    "demand_service_rank_correlation": response["demand_service_rank_correlation"],
                    "direction_accuracy": response["demand_response_direction_accuracy"],
                    "sqrt_response_deviation": response["sqrt_seed_response_deviation"],
                    "total_frequency_variation": source["total_frequency_variation"],
                }
            )
    for candidate in candidates:
        for direction, response in candidate["directions"].items():
            source = candidate["c1_direction_metrics"][direction]
            rows.append(
                {
                    "schedule_or_candidate": candidate["pareto_id"],
                    "direction": direction,
                    "fleet": candidate["c1_pair_metrics"]["fleet_required"],
                    "demand_mismatch": source["immutable_demand_mismatch"],
                    "expected_passenger_wait_minutes": source[
                        "demand_weighted_expected_passenger_wait_minutes"
                    ],
                    "regime_count": source["regime_count"],
                    "service_peak_low_ratio": response["peak_low_comparison"][
                        "service_peak_low_ratio"
                    ],
                    "response_elasticity_gamma": response["service_demand_response_regression"][
                        "gamma"
                    ],
                    "demand_service_rank_correlation": response["demand_service_rank_correlation"],
                    "direction_accuracy": response["demand_response_direction_accuracy"],
                    "sqrt_response_deviation": response["sqrt_seed_response_deviation"],
                    "total_frequency_variation": source["total_frequency_variation"],
                }
            )
    return rows


def run_experiment(*, repo_root: Path, workbook_path: Path, authority_root: Path) -> dict[str, Any]:
    if _sha256(workbook_path) != EXPECTED_WORKBOOK_SHA256:
        raise ValueError("private Route 6 workbook SHA-256 changed")
    parsed = parse_route6_reference_workbook(workbook_path)
    if parsed["reference_sheet_names"] != EXPECTED_SHEETS:
        raise ValueError("private Route 6 workbook sheet mapping changed")

    c1_path = repo_root / C1_EVIDENCE
    c1 = json.loads(c1_path.read_text(encoding="utf-8"))
    c1_identity = _c1_identity(c1_path, c1)
    demand_path = authority_root / DEMAND_EVIDENCE
    if _sha256(demand_path) != EXPECTED_DEMAND_SHA256:
        raise ValueError("canonical Route 6 DemandRegime evidence SHA-256 changed")
    demand = json.loads(demand_path.read_text(encoding="utf-8"))
    if str(demand["route_id"]) != "6" or demand["model_selection"]["status"] != "SUCCESS":
        raise ValueError("canonical Route 6 DemandRegime evidence identity changed")
    selected = _selected_regimes(demand)
    buckets = _demand_buckets(demand)
    canonical = {
        direction: build_canonical_regime_evidence(selected[direction], buckets[direction])
        for direction in ("outbound", "inbound")
    }

    references: dict[str, Any] = {}
    for label in REFERENCE_LABELS:
        c1_reference = c1["reference_timetable_metrics"][label]
        directions = {}
        for direction in ("outbound", "inbound"):
            departures = tuple(parsed["references"][label][direction])
            c1_departures = tuple(
                _hhmm_seconds(value) for value in c1_reference[direction]["exact_departures"]
            )
            if departures != c1_departures:
                raise ValueError(f"{label} {direction} differs between workbook and C1 evidence")
            directions[direction] = analyze_direction(
                departures,
                canonical[direction],
                exact_service_regime_headways=_headways(c1_reference[direction]),
            )
        references[label] = {
            "source_label": label,
            **reference_lineage(label),
            "sheet_name": parsed["reference_sheet_names"][label],
            "pair_metrics": c1_reference["pair"],
            "c1_metrics": {
                direction: {
                    key: c1_reference[direction][key]
                    for key in (
                        "immutable_demand_mismatch",
                        "demand_weighted_expected_passenger_wait_minutes",
                        "regime_count",
                        "total_frequency_variation",
                    )
                }
                for direction in ("outbound", "inbound")
            },
            "directions": directions,
        }

    candidate_roles = _roles(c1["clean_pareto_candidates"])
    candidates = []
    for candidate in c1["clean_pareto_candidates"]:
        directions = {}
        for direction in ("outbound", "inbound"):
            source = candidate[direction]["metrics"]
            directions[direction] = analyze_direction(
                tuple(_hhmm_seconds(value) for value in source["exact_departures"]),
                canonical[direction],
                exact_service_regime_headways=_headways(source),
            )
        candidates.append(
            {
                "pareto_id": candidate["pareto_id"],
                "pair_id": candidate["pair_id"],
                "roles": candidate_roles[candidate["pareto_id"]],
                "service_regime_composition": {
                    direction: candidate[direction]["regimes"]
                    for direction in ("outbound", "inbound")
                },
                "c1_pair_metrics": candidate["metrics"],
                "c1_direction_metrics": {
                    direction: {
                        key: candidate[direction]["metrics"][key]
                        for key in (
                            "immutable_demand_mismatch",
                            "demand_weighted_expected_passenger_wait_minutes",
                            "regime_count",
                            "total_frequency_variation",
                        )
                    }
                    for direction in ("outbound", "inbound")
                },
                "directions": directions,
            }
        )

    arithmetic = {
        "purpose": (
            "These arithmetic examples illustrate service differentiation only; they do not "
            "prove which headways Route 6 should use."
        ),
        "8_15": {
            "first_headway_minutes": 8,
            "first_frequency_per_hour": 60 / 8,
            "second_headway_minutes": 15,
            "second_frequency_per_hour": 60 / 15,
            "frequency_ratio": (60 / 8) / (60 / 15),
        },
        "10_12": {
            "first_headway_minutes": 10,
            "first_frequency_per_hour": 60 / 10,
            "second_headway_minutes": 12,
            "second_frequency_per_hour": 60 / 12,
            "frequency_ratio": (60 / 10) / (60 / 12),
        },
        "12_13": {
            "first_headway_minutes": 12,
            "first_frequency_per_hour": 60 / 12,
            "second_headway_minutes": 13,
            "second_frequency_per_hour": 60 / 13,
            "frequency_ratio": (60 / 12) / (60 / 13),
        },
    }
    relative = _relative_alignment_observation(candidates)
    payload = {
        "experiment_profile": EXPERIMENT_PROFILE,
        "review_only": True,
        "source_workbook": {
            "basename": workbook_path.name,
            "sha256": _sha256(workbook_path),
            "reference_sheet_names": parsed["reference_sheet_names"],
        },
        "c1_evidence_identity": c1_identity,
        "canonical_demand_regime_source": {
            "relative_path": DEMAND_EVIDENCE.as_posix(),
            "sha256": _sha256(demand_path),
            "route_id": demand["route_id"],
            "review_profile": demand["review_profile"],
            "selector_profile": demand["model_selection"]["selector_profile"],
            "demand_profile_id": demand["model_selection"]["demand_profile_id"],
            "demand_profile_fingerprint": demand["model_selection"]["demand_profile_fingerprint"],
        },
        "immutable_demand_source_identity": {
            "artifact_sha256": _sha256(demand_path),
            "raw_daily_source": {
                key: demand["raw_daily_source"][key]
                for key in (
                    "source_file",
                    "source_sha256",
                    "selected_period_start",
                    "selected_period_end",
                    "raw_time_granularity_seconds",
                    "route_id",
                )
            },
            "source_period_observation_days": demand["source_period_observation_days"],
            "bucket_granularity_minutes": 30,
            "semantics": (
                "raw_derived_average bucket mass, piecewise constant within each bucket and "
                "integrated by exact temporal overlap"
            ),
        },
        "methodology": {
            "common_active_service_span": ["04:55", "21:00"],
            "service_projection": (
                "time average of 60/headway_minutes over exact interdeparture overlap"
            ),
            "adjacent_duration_weight": (
                "arithmetic mean of the left and right active DemandRegime durations"
            ),
            "rank_ties": "deterministic average ranks; rank 1 is highest",
            "flat_definition": (
                "exact numerical zero only, using absolute tolerance 1e-12; no material threshold"
            ),
            "sqrt_seed_benchmark": (
                "existing engine seed descriptor frequency proportional to demand^0.5; not policy"
            ),
        },
        "canonical_demand_regimes": canonical,
        "reference_timetable_response_metrics": references,
        "c1_sensitivity_clean_pareto_response_metrics": candidates,
        "comparative_response_table": _comparison_rows(references, candidates),
        "sample_relative_alignment_observation": relative,
        "service_differentiation_arithmetic": arithmetic,
        "interpretation": {
            "human_final_status": "expert reference, not target or ground truth",
            "general_principle_tested": (
                "materially different demand states should not be represented by nearly "
                "indistinguishable service levels unless another operational objective justifies "
                "that trade-off"
            ),
            "c2_does_not_establish_8_15_optimal": True,
            "production_requirement_created": False,
        },
        "future_metric_candidates_evidence_only": [
            "service_peak_low_ratio paired with demand_peak_low_ratio",
            "service_demand_response_elasticity gamma",
            "demand_service_rank_correlation",
            "demand_response_direction_accuracy with raw transition count",
            "sqrt_seed_response_deviation and contrast_amplitude_ratio_to_sqrt_reference",
        ],
        "limitations": [
            "Single Route 6 calibration using frozen canonical regimes and immutable demand.",
            "Effective frequency is averaged within DemandRegimes and does not measure crowding, capacity, reliability, or cost directly.",
            "The sqrt-demand relationship is an existing seed benchmark, not transport policy or ground truth.",
            "Sample-relative candidate observations are descriptive and create no absolute threshold or scalar score.",
            "C2 does not establish that 8/15 is the optimal Route 6 rhythm composition.",
        ],
        "production_change_guard": {
            "production_scheduling_policy_changed": False,
            "compiler_changed": False,
            "production_pareto_vector_changed": False,
            "search_budgets_changed": False,
            "service_protection_changed": False,
            "settlement_behavior_changed": False,
            "statement": "NO PRODUCTION POLICY CHANGED",
        },
    }
    payload["experiment_fingerprint"] = _fingerprint(payload)
    return payload


def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def _response_summary(response: Mapping[str, Any]) -> str:
    peak = response["peak_low_comparison"]
    regression = response["service_demand_response_regression"]
    return (
        f"demand ratio {_fmt(peak['demand_peak_low_ratio'])}, service ratio "
        f"{_fmt(peak['service_peak_low_ratio'])}, gamma {_fmt(regression['gamma'])}, "
        f"rank {_fmt(response['demand_service_rank_correlation'])}, direction accuracy "
        f"{_fmt(response['demand_response_direction_accuracy'])}, sqrt deviation "
        f"{_fmt(response['sqrt_seed_response_deviation'])}"
    )


def _central_table(lines: list[str], response: Mapping[str, Any]) -> None:
    lines.extend(
        [
            "| DemandRegime | Active window | Demand rate/h | Service frequency/h | Effective headway | Demand rank | Service rank |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in response["demand_aligned_service_response_table"]:
        lines.append(
            f"| {row['regime_id']} | {row['active_start']}–{row['active_end']} | "
            f"{_fmt(row['demand_rate_per_hour'])} | "
            f"{_fmt(row['effective_service_frequency_per_hour'])} | "
            f"{_fmt(row['effective_headway_minutes'])} | {_fmt(row['demand_rank'], 1)} | "
            f"{_fmt(row['service_rank'], 1)} |"
        )


def _adjacent_table(lines: list[str], response: Mapping[str, Any]) -> None:
    lines.extend(
        [
            "",
            "| Transition | Demand Δlog | Service Δlog | Demand | Service | Agree | √ expected | √ residual |",
            "|---|---:|---:|---|---|---|---:|---:|",
        ]
    )
    for row in response["adjacent_demand_contrasts"]:
        lines.append(
            f"| {row['left_regime_id']}→{row['right_regime_id']} | "
            f"{_fmt(row['delta_log_demand'])} | {_fmt(row['delta_log_service'])} | "
            f"{row['demand_direction']} | {row['service_direction']} | "
            f"{_fmt(row['sign_agreement'])} | "
            f"{_fmt(row['sqrt_seed_expected_delta_log_service'])} | "
            f"{_fmt(row['sqrt_response_residual'])} |"
        )


def render_markdown(payload: Mapping[str, Any]) -> str:
    references = payload["reference_timetable_response_metrics"]
    candidates = payload["c1_sensitivity_clean_pareto_response_metrics"]
    twelve_thirteen = next(
        item for item in candidates if "CLEAN_12_13_TIMETABLE_CANDIDATE" in item["roles"]
    )
    relative = payload["sample_relative_alignment_observation"]
    lines = [
        "# PR62-C2 — Route 6 demand-response ServiceRegime contrast calibration",
        "",
        "> **NO PRODUCTION POLICY CHANGED.** C2 is experiment/calibration evidence only.",
        "",
        "## Answer first",
        "",
        (
            "Route 6's frozen canonical demand evidence contains "
            f"{len(payload['canonical_demand_regimes']['outbound'])} outbound and "
            f"{len(payload['canonical_demand_regimes']['inbound'])} inbound states. "
            "Their demand contrasts are materially visible numerically below; no materiality "
            "threshold is introduced."
        ),
        "",
        (
            "Outbound demand is highest in `DEMAND-OUTBOUND-06` and lowest in "
            f"`DEMAND-OUTBOUND-08` (ratio "
            f"{_fmt(references['CURRENT']['directions']['outbound']['peak_low_comparison']['demand_peak_low_ratio'])}). "
            "Inbound demand is highest in `DEMAND-INBOUND-06` and lowest in "
            f"`DEMAND-INBOUND-08` (ratio "
            f"{_fmt(references['CURRENT']['directions']['inbound']['peak_low_comparison']['demand_peak_low_ratio'])})."
        ),
        "",
    ]
    for label in REFERENCE_LABELS:
        lines.append(
            f"- **{label}:** outbound {_response_summary(references[label]['directions']['outbound'])}; "
            f"inbound {_response_summary(references[label]['directions']['inbound'])}."
        )
    lines.extend(
        [
            "",
            (
                f"- **12/13 clean design ({twelve_thirteen['pareto_id']}, "
                f"{twelve_thirteen['c1_pair_metrics']['fleet_required']} vehicles):** outbound "
                f"{_response_summary(twelve_thirteen['directions']['outbound'])}; inbound "
                f"{_response_summary(twelve_thirteen['directions']['inbound'])}."
            ),
            "",
            (
                "The 12/13 design's fleet efficiency is therefore assessed from its canonical "
                "demand/service ratios, gamma, rank, direction accuracy, and sqrt deviation—not "
                "from the visual neatness of its headways. Its near-unity service ratios and "
                "low contrast amplitude show that part of the 14-vehicle result comes from "
                "flattening service response across strongly different demand states."
            ),
            "",
            (
                "The C1 candidates that relatively best preserve aligned differentiation in this "
                "nine-candidate sample are: "
                + ", ".join(relative["relatively_stronger_demand_aligned_candidates"])
                + ". This is a sample-median descriptor across three separate metrics, not a "
                "scalar score or production frontier. Even these candidates preserve the "
                "response only partially: neither matches the expert references' alignment in "
                "both directions."
            ),
            "",
            "The expert references generally make the same directional response that the existing "
            "sqrt-demand seed implies, but their residuals show the sqrt relationship is only a "
            "benchmark. Human Final remains an expert reference, not a target or ground truth.",
            "",
            "Suitable evidence candidates for later ServicePlan evaluation are the paired "
            "demand/service peak-low ratios, gamma, rank correlation, direction accuracy plus raw "
            "transition count, and sqrt deviation/amplitude ratio. No threshold is selected here.",
            "",
            "C2 does not establish that 8/15 is the optimal Route 6 rhythm composition. It tests "
            "the more general principle that materially different demand states should not be "
            "represented by nearly indistinguishable service levels unless another operational "
            "objective justifies that trade-off.",
            "",
            "## Frozen sources and method",
            "",
            f"- Private workbook: `{payload['source_workbook']['basename']}` / `{payload['source_workbook']['sha256']}`",
            f"- C1 evidence: `{payload['c1_evidence_identity']['relative_path']}` / `{payload['c1_evidence_identity']['sha256']}`",
            f"- Canonical DemandRegimes: `{payload['canonical_demand_regime_source']['relative_path']}` / `{payload['canonical_demand_regime_source']['sha256']}`",
            "- Common active service span: 04:55–21:00.",
            "- Demand mass is integrated proportionally through exact overlap with immutable 30-minute buckets.",
            "- Service frequency is the exact time average of `60 / interdeparture headway` inside each DemandRegime.",
            "- Adjacent transition weights are the arithmetic mean of the two active regime durations.",
            "- `FLAT` means numerical zero to `1e-12`; it is not a policy or materiality threshold.",
            "",
            "## Canonical Route 6 demand differentiation",
        ]
    )
    for direction in ("outbound", "inbound"):
        lines.extend(
            [
                "",
                f"### {direction.title()}",
                "",
                "| Regime | Canonical window | Active window | Duration min | Integrated mass | Demand rate/h |",
                "|---|---|---|---:|---:|---:|",
            ]
        )
        for row in payload["canonical_demand_regimes"][direction]:
            lines.append(
                f"| {row['regime_id']} | {row['canonical_start']}–{row['canonical_end']} | "
                f"{row['active_start']}–{row['active_end']} | "
                f"{_fmt(row['active_duration_minutes'], 1)} | "
                f"{_fmt(row['integrated_immutable_demand_mass'])} | "
                f"{_fmt(row['demand_rate_per_hour'])} |"
            )

    arithmetic = payload["service_differentiation_arithmetic"]
    lines.extend(
        [
            "",
            "## Pedagogical service-differentiation arithmetic",
            "",
            "- 8 minutes = 7.50 departures/hour; 15 minutes = 4.00; ratio = 1.875.",
            "- 10 minutes = 6.00 departures/hour; 12 minutes = 5.00; ratio = 1.200.",
            "- 12 minutes = 5.00 departures/hour; 13 minutes ≈ 4.615; ratio ≈ 1.083.",
            "",
            f"**{arithmetic['purpose']}**",
            "",
            "## Comparative response table",
            "",
            "| Schedule | Dir | Fleet | Mismatch | Wait min | Regimes | Peak/low service | Gamma | Rank | Direction accuracy | √ deviation | Total variation |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["comparative_response_table"]:
        lines.append(
            f"| {row['schedule_or_candidate']} | {row['direction']} | {row['fleet']} | "
            f"{_fmt(row['demand_mismatch'], 5)} | "
            f"{_fmt(row['expected_passenger_wait_minutes'])} | {row['regime_count']} | "
            f"{_fmt(row['service_peak_low_ratio'])} | "
            f"{_fmt(row['response_elasticity_gamma'])} | "
            f"{_fmt(row['demand_service_rank_correlation'])} | "
            f"{_fmt(row['direction_accuracy'])} | {_fmt(row['sqrt_response_deviation'])} | "
            f"{_fmt(row['total_frequency_variation'])} |"
        )

    lines.extend(["", "## C1 candidate roles", ""])
    for candidate in candidates:
        roles = ", ".join(candidate["roles"]) or "Pareto candidate only"
        lines.append(f"- `{candidate['pareto_id']}`: {roles}.")
    lines.extend(
        [
            "",
            "## Demand-aligned response details",
            "",
            "Every schedule/direction below uses the same canonical DemandRegime evidence.",
        ]
    )
    schedules = [(label, references[label]["directions"]) for label in REFERENCE_LABELS] + [
        (item["pareto_id"], item["directions"]) for item in candidates
    ]
    for label, directions in schedules:
        for direction in ("outbound", "inbound"):
            response = directions[direction]
            lines.extend(["", f"### {label} — {direction}", ""])
            _central_table(lines, response)
            _adjacent_table(lines, response)
            lines.extend(
                [
                    "",
                    f"Summary: {_response_summary(response)}; amplitude ratio to sqrt "
                    f"{_fmt(response['contrast_amplitude_ratio_to_sqrt_reference'])}; "
                    f"aligned transitions {response['directionally_aligned_transition_count']}/"
                    f"{response['nonzero_demand_transition_count']}.",
                ]
            )

    lines.extend(
        [
            "",
            "## Limitations",
            "",
            *[f"- {item}" for item in payload["limitations"]],
            "",
            "## Production guard",
            "",
            "- Production scheduling policy changed: **No**.",
            "- Compiler changed: **No**.",
            "- Production Pareto vector changed: **No**.",
            "- Search budgets changed: **No**.",
            "- Service protection changed: **No**.",
            "- Settlement behavior changed: **No**.",
            "",
        ]
    )
    return "\n".join(lines)


def _resolve_workbook(repo_root: Path) -> Path:
    path = repo_root / "private/Route_6_Current_ExternalAI_HumanFinal.xlsx"
    if not path.is_file():
        raise FileNotFoundError(path.name)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--authority-root", type=Path, default=None)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    authority_root = (args.authority_root or repo_root).resolve()
    payload = run_experiment(
        repo_root=repo_root,
        workbook_path=_resolve_workbook(repo_root),
        authority_root=authority_root,
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
                "candidate_count": len(payload["c1_sensitivity_clean_pareto_response_metrics"]),
                "experiment_fingerprint": payload["experiment_fingerprint"],
                "json": OUTPUT_JSON.as_posix(),
                "markdown": OUTPUT_MARKDOWN.as_posix(),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
