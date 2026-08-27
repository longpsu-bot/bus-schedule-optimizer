"""Generate PR62-K baseline-safe operational-shortlist evidence."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import statistics
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT / "src", _REPO_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import run_pr62_j_daily_materiality_calibration as pr62_j  # noqa: E402

NUMERICAL_EPSILON = 1e-12
PROFILE = "pr62_k_baseline_safe_operational_shortlist_v1"
J_COMMIT_SHA = "18166c5774b99eceb487e3c6c2368a01dee1c850"
EXPECTED_I_PARETO_SIZES = {"6": 47, "10": 11}
OUTPUT_JSON = Path("docs/engine/evidence/PR62_K_BASELINE_SAFE_OPERATIONAL_SHORTLIST.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_K_BASELINE_SAFE_OPERATIONAL_SHORTLIST.md")
FROZEN_BUDGET = pr62_j.FROZEN_BUDGET
coordinator = pr62_j.coordinator
pr62_i = pr62_j.pr62_i
OPERATIONAL_DIMENSIONS = (
    "sustained_headway_level_count",
    "service_regime_count",
    "fleet_required",
    "total_excess_terminal_wait",
    "maximum_bucket_expected_wait_minutes",
)


def _daily_pair_metrics_with_mass(
    *,
    outbound_departures: Sequence[int],
    inbound_departures: Sequence[int],
    observation_index: Mapping[tuple[date, str], Sequence[Any]],
    eligible_dates: Sequence[date],
) -> dict[date, dict[str, float]]:
    daily: dict[date, dict[str, float]] = {}
    for observed_date in eligible_dates:
        outbound = pr62_j._daily_direction_metrics(
            outbound_departures,
            observation_index[(observed_date, "outbound")],
        )
        inbound = pr62_j._daily_direction_metrics(
            inbound_departures,
            observation_index[(observed_date, "inbound")],
        )
        active_mass = outbound["active_demand_mass"] + inbound["active_demand_mass"]
        if active_mass <= 0:
            raise ValueError(f"paired daily demand has no positive mass on {observed_date}")
        daily[observed_date] = {
            "expected_wait_minutes": (
                outbound["expected_wait_minutes"] * outbound["active_demand_mass"]
                + inbound["expected_wait_minutes"] * inbound["active_demand_mass"]
            )
            / active_mass,
            "observed_demand_mismatch": (
                outbound["observed_demand_mismatch"]
                + inbound["observed_demand_mismatch"]
            ),
            "active_passenger_mass": active_mass,
        }
    return daily


def _baseline_safety(
    candidate: Mapping[str, float],
    baseline: Mapping[str, float],
    *,
    epsilon: float = NUMERICAL_EPSILON,
) -> dict[str, bool]:
    wait = (
        float(candidate["mean_daily_wait_minutes"])
        <= float(baseline["mean_daily_wait_minutes"]) + epsilon
    )
    mismatch = (
        float(candidate["mean_daily_mismatch"])
        <= float(baseline["mean_daily_mismatch"]) + epsilon
    )
    maximum = (
        float(candidate["maximum_bucket_expected_wait_minutes"])
        <= float(baseline["maximum_bucket_expected_wait_minutes"]) + epsilon
    )
    return {
        "wait_non_regression": wait,
        "mismatch_non_regression": mismatch,
        "maximum_bucket_wait_non_regression": maximum,
        "baseline_safe_passenger_service": wait and mismatch and maximum,
    }


def _baseline_safe_engine_fingerprints(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(item["fingerprint"])
            for item in candidates
            if item.get("selection_eligible") is True
            and item.get("baseline_safe_passenger_service") is True
        )
    )


def _operational_dominates(
    left: Mapping[str, float | int],
    right: Mapping[str, float | int],
    *,
    epsilon: float = NUMERICAL_EPSILON,
) -> bool:
    left_values = tuple(float(left[key]) for key in OPERATIONAL_DIMENSIONS)
    right_values = tuple(float(right[key]) for key in OPERATIONAL_DIMENSIONS)
    return all(a <= b + epsilon for a, b in zip(left_values, right_values, strict=True)) and any(
        a < b - epsilon for a, b in zip(left_values, right_values, strict=True)
    )


def _operational_frontier_fingerprints(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    eligible = tuple(
        item
        for item in candidates
        if item.get("selection_eligible") is True
        and item.get("baseline_safe_passenger_service") is True
    )
    return tuple(
        sorted(
            str(item["fingerprint"])
            for item in eligible
            if not any(
                str(other["fingerprint"]) != str(item["fingerprint"])
                and _operational_dominates(other["secondary_metrics"], item["secondary_metrics"])
                for other in eligible
            )
        )
    )


def _route_classification(baseline_safe_size: int, frontier_size: int) -> str:
    if baseline_safe_size < 0 or frontier_size < 0 or frontier_size > baseline_safe_size:
        raise ValueError("frontier sizes are inconsistent")
    if frontier_size == 0:
        return "NO_BASELINE_SAFE_OPERATING_CANDIDATE"
    if frontier_size == 1:
        return "UNIQUE_BASELINE_SAFE_OPERATING_CANDIDATE"
    return "MULTIPLE_BASELINE_SAFE_OPERATING_TRADEOFFS"


def _daily_comparison(
    candidate: Mapping[date, Mapping[str, float]],
    baseline: Mapping[date, Mapping[str, float]],
    *,
    expected_dates: Sequence[date],
    epsilon: float = NUMERICAL_EPSILON,
) -> dict[str, float | int]:
    dates = tuple(expected_dates)
    if not dates or len(set(dates)) != len(dates):
        raise ValueError("expected paired date set must be nonempty and unique")
    if set(candidate) != set(dates) or set(baseline) != set(dates):
        raise ValueError("candidate and baseline must match the authoritative paired date set")
    wait_deltas: list[float] = []
    mismatch_deltas: list[float] = []
    passenger_minutes_saved: list[float] = []
    for observed_date in dates:
        candidate_mass = float(candidate[observed_date]["active_passenger_mass"])
        baseline_mass = float(baseline[observed_date]["active_passenger_mass"])
        if abs(candidate_mass - baseline_mass) > epsilon:
            raise ValueError("candidate and baseline daily passenger mass changed")
        wait_delta = float(candidate[observed_date]["expected_wait_minutes"]) - float(
            baseline[observed_date]["expected_wait_minutes"]
        )
        mismatch_delta = float(candidate[observed_date]["observed_demand_mismatch"]) - float(
            baseline[observed_date]["observed_demand_mismatch"]
        )
        wait_deltas.append(wait_delta)
        mismatch_deltas.append(mismatch_delta)
        passenger_minutes_saved.append(-wait_delta * baseline_mass)

    def percentages(values: Sequence[float], prefix: str) -> dict[str, float]:
        better = sum(value < -epsilon for value in values)
        worse = sum(value > epsilon for value in values)
        equal = len(values) - better - worse
        return {
            f"{prefix}_candidate_better_percentage": 100.0 * better / len(values),
            f"{prefix}_equal_percentage": 100.0 * equal / len(values),
            f"{prefix}_candidate_worse_percentage": 100.0 * worse / len(values),
        }

    minutes = statistics.fmean(passenger_minutes_saved)
    return {
        "paired_date_count": len(dates),
        **percentages(wait_deltas, "wait"),
        **percentages(mismatch_deltas, "mismatch"),
        "passenger_wait_minutes_saved_per_average_day": minutes,
        "passenger_wait_hours_saved_per_average_day": minutes / 60.0,
    }


def _daily_vector_fingerprint(values: Mapping[date, float]) -> str:
    serialized = [[key.isoformat(), float(values[key])] for key in sorted(values)]
    encoded = json.dumps(serialized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _cross_route_classification(routes: Mapping[str, Mapping[str, int]]) -> str:
    required = tuple(routes[route_id] for route_id in ("6", "10"))
    if any(int(route["BASELINE_SAFE_SET_size"]) == 0 for route in required):
        return "BASELINE_SAFE_POLICY_TOO_RESTRICTIVE"
    if all(
        0 < int(route["BASELINE_SAFE_OPERATIONAL_FRONTIER_size"])
        < int(route["I_pareto_size"])
        for route in required
    ):
        return "BASELINE_SAFE_POLICY_PROMISING"
    return "BASELINE_SAFE_POLICY_INCONCLUSIVE"


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _headway_run_record(run: Any) -> dict[str, int]:
    return {
        "headway_minutes": run.headway_minutes,
        "gap_count": run.gap_count,
        "start_departure_index": run.gap_start_index,
        "end_departure_index": run.gap_start_index + run.gap_count,
    }


def _direction_diagnostics(
    departures: Sequence[int],
    *,
    demand_buckets: Sequence[Any],
) -> dict[str, Any]:
    average, maximum, per_bucket, active_mass = coordinator.expected_passenger_wait_metrics_v1(
        departures, demand_buckets
    )
    runs = pr62_i.exact_headway_runs(departures)
    sustained = tuple(item for item in runs if item.gap_count >= 2)
    weights: dict[int, int] = {}
    for run in sustained:
        weights[run.headway_minutes] = weights.get(run.headway_minutes, 0) + run.gap_count
    levels = tuple(sorted(weights))
    effective = coordinator._minimum_effective_headway_palette_v1(levels, weights)
    tail_run = runs[-1]
    tail_start = departures[tail_run.gap_start_index]
    p90, tail_maximum = coordinator.bucket_wait_access_diagnostics_v1(
        per_bucket_expected_wait_minutes=per_bucket,
        demand_buckets=demand_buckets,
        active_span_start=departures[0],
        active_span_end=departures[-1],
        tail_support_start=tail_start,
        tail_support_end=departures[-1],
    )
    return {
        "departure_count": len(departures),
        "first_departure_seconds": departures[0],
        "last_departure_seconds": departures[-1],
        "aggregate_expected_wait_minutes": average,
        "maximum_bucket_expected_wait_minutes": maximum,
        "p90_bucket_expected_wait_minutes": p90,
        "tail_maximum_bucket_wait_minutes": tail_maximum,
        "active_passenger_mass": active_mass,
        "actual_service_regime_count": len(runs),
        "sustained_headway_levels_minutes": list(levels),
        "effective_headway_palette_minutes": list(effective),
        "tail_headway_minutes": tail_run.headway_minutes,
        "headway_runs": [_headway_run_record(run) for run in runs],
    }


def _reference_record(
    *,
    fingerprint: str,
    outbound_departures: Sequence[int],
    inbound_departures: Sequence[int],
    context: Any,
    daily: Mapping[date, Mapping[str, float]],
    selection_eligible: bool,
) -> dict[str, Any]:
    departures = {
        "outbound": tuple(outbound_departures),
        "inbound": tuple(inbound_departures),
    }
    directions = {
        direction: _direction_diagnostics(
            departures[direction], demand_buckets=context.demand_buckets[direction]
        )
        for direction in ("outbound", "inbound")
    }
    regularity = {
        direction: pr62_i.reference_directional_metrics(
            departures[direction], demand_buckets=context.demand_buckets[direction]
        )
        for direction in ("outbound", "inbound")
    }
    fleet = pr62_i.reference_pair_metrics(
        departures["outbound"],
        departures["inbound"],
        outbound_metrics=regularity["outbound"],
        inbound_metrics=regularity["inbound"],
        runtime_minutes=context.runtime_minutes,
        minimum_layover_minutes=context.minimum_layover_minutes,
        fleet_ceiling=context.fleet_ceiling,
        candidate_id=fingerprint,
    )
    daily_wait = {key: float(value["expected_wait_minutes"]) for key, value in daily.items()}
    daily_mismatch = {
        key: float(value["observed_demand_mismatch"]) for key, value in daily.items()
    }
    return {
        "fingerprint": fingerprint,
        "selection_eligible": selection_eligible,
        "daily": dict(daily),
        "mean_daily_wait_minutes": statistics.fmean(daily_wait.values()),
        "mean_daily_mismatch": statistics.fmean(daily_mismatch.values()),
        "maximum_bucket_expected_wait_minutes": max(
            directions[direction]["maximum_bucket_expected_wait_minutes"]
            for direction in ("outbound", "inbound")
        ),
        "p90_bucket_expected_wait_minutes": max(
            directions[direction]["p90_bucket_expected_wait_minutes"]
            for direction in ("outbound", "inbound")
        ),
        "tail_maximum_bucket_wait_minutes": max(
            directions[direction]["tail_maximum_bucket_wait_minutes"]
            for direction in ("outbound", "inbound")
            if directions[direction]["tail_maximum_bucket_wait_minutes"] is not None
        ),
        "fleet_required": fleet["fleet_required"],
        "service_regime_count": sum(
            directions[direction]["actual_service_regime_count"]
            for direction in ("outbound", "inbound")
        ),
        "sustained_headway_level_count": sum(
            len(directions[direction]["sustained_headway_levels_minutes"])
            for direction in ("outbound", "inbound")
        ),
        "effective_palette_count": sum(
            len(directions[direction]["effective_headway_palette_minutes"])
            for direction in ("outbound", "inbound")
        ),
        "total_excess_terminal_wait": fleet["total_excess_terminal_wait_minutes"],
        "outbound_tail_headway_minutes": directions["outbound"]["tail_headway_minutes"],
        "inbound_tail_headway_minutes": directions["inbound"]["tail_headway_minutes"],
        "inbound_tail_maximum_bucket_wait_minutes": directions["inbound"][
            "tail_maximum_bucket_wait_minutes"
        ],
        "directions": directions,
        "daily_wait_vector_sha256": _daily_vector_fingerprint(daily_wait),
        "daily_mismatch_vector_sha256": _daily_vector_fingerprint(daily_mismatch),
    }


def _engine_candidate_record(
    item: Any,
    *,
    observation_index: Mapping[tuple[date, str], Sequence[Any]],
    eligible_dates: Sequence[date],
) -> dict[str, Any]:
    outbound = item.outbound.compile_variant.compilation.exact_departures
    inbound = item.inbound.compile_variant.compilation.exact_departures
    daily = _daily_pair_metrics_with_mass(
        outbound_departures=outbound,
        inbound_departures=inbound,
        observation_index=observation_index,
        eligible_dates=eligible_dates,
    )
    daily_wait = {key: value["expected_wait_minutes"] for key, value in daily.items()}
    daily_mismatch = {key: value["observed_demand_mismatch"] for key, value in daily.items()}
    metrics = item.metrics
    record = {
        "fingerprint": item.pair_fingerprint,
        "selection_eligible": True,
        "daily": daily,
        "mean_daily_wait_minutes": statistics.fmean(daily_wait.values()),
        "mean_daily_mismatch": statistics.fmean(daily_mismatch.values()),
        "maximum_bucket_expected_wait_minutes": metrics.maximum_bucket_expected_wait_minutes,
        "p90_bucket_expected_wait_minutes": metrics.maximum_directional_p90_bucket_wait_minutes,
        "fleet_required": metrics.fleet_required,
        "service_regime_count": metrics.actual_service_regime_count,
        "sustained_headway_level_count": metrics.total_directional_sustained_headway_level_count,
        "effective_palette_count": metrics.total_directional_effective_palette_count,
        "total_excess_terminal_wait": metrics.total_excess_terminal_wait,
        "outbound_tail_headway_minutes": item.outbound.metrics.tail_headway_minutes,
        "inbound_tail_headway_minutes": item.inbound.metrics.tail_headway_minutes,
        "inbound_tail_maximum_bucket_wait_minutes": (
            item.inbound.metrics.tail_maximum_bucket_expected_wait_minutes
        ),
        "daily_wait_vector_sha256": _daily_vector_fingerprint(daily_wait),
        "daily_mismatch_vector_sha256": _daily_vector_fingerprint(daily_mismatch),
    }
    record["secondary_metrics"] = {
        key: record[key] for key in OPERATIONAL_DIMENSIONS
    }
    return record


def _marginal_delta(item: Mapping[str, Any], reference: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "reference": reference["fingerprint"],
        "delta_mean_wait_seconds_per_passenger": (
            float(item["mean_daily_wait_minutes"])
            - float(reference["mean_daily_wait_minutes"])
        )
        * 60.0,
        "delta_mean_mismatch": float(item["mean_daily_mismatch"])
        - float(reference["mean_daily_mismatch"]),
        "delta_maximum_bucket_wait_minutes": float(
            item["maximum_bucket_expected_wait_minutes"]
        )
        - float(reference["maximum_bucket_expected_wait_minutes"]),
        "delta_p90_bucket_wait_minutes": float(item["p90_bucket_expected_wait_minutes"])
        - float(reference["p90_bucket_expected_wait_minutes"]),
        "delta_fleet_required": int(item["fleet_required"]) - int(reference["fleet_required"]),
        "delta_service_regime_count": int(item["service_regime_count"])
        - int(reference["service_regime_count"]),
        "delta_sustained_palette_count": int(item["sustained_headway_level_count"])
        - int(reference["sustained_headway_level_count"]),
        "delta_effective_palette_count": int(item["effective_palette_count"])
        - int(reference["effective_palette_count"]),
        "delta_total_excess_terminal_wait": int(item["total_excess_terminal_wait"])
        - int(reference["total_excess_terminal_wait"]),
    }


def _public_record(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in {"daily", "secondary_metrics"}
    }


def _human_final(
    *,
    repo_root: Path,
    context: Any,
    observation_index: Mapping[tuple[date, str], Sequence[Any]],
    eligible_dates: Sequence[date],
    scenario_b: Mapping[str, Any],
) -> dict[str, Any]:
    workbook = repo_root / "private" / "Route_6_Current_ExternalAI_HumanFinal.xlsx"
    if not workbook.is_file():
        return {
            "available": False,
            "accepted_sha_match": False,
            "classification": "POST_SEARCH_EXPERT_BENCHMARK",
            "selection_eligible": False,
        }
    actual_sha = pr62_j._sha256_path(workbook)
    if actual_sha != pr62_i.EXPECTED_HUMAN_FINAL_SHA256:
        return {
            "available": True,
            "accepted_sha_match": False,
            "sha256": actual_sha,
            "classification": "POST_SEARCH_EXPERT_BENCHMARK",
            "selection_eligible": False,
        }
    source = pr62_i.parse_route6_reference_workbook(workbook)["references"]["HUMAN_FINAL"]
    daily = _daily_pair_metrics_with_mass(
        outbound_departures=source["outbound"],
        inbound_departures=source["inbound"],
        observation_index=observation_index,
        eligible_dates=eligible_dates,
    )
    record = _reference_record(
        fingerprint="HUMAN_FINAL",
        outbound_departures=source["outbound"],
        inbound_departures=source["inbound"],
        context=context,
        daily=daily,
        selection_eligible=False,
    )
    safety = _baseline_safety(record, scenario_b)
    comparison = _daily_comparison(record["daily"], scenario_b["daily"], expected_dates=eligible_dates)
    return {
        **_public_record(record),
        "available": True,
        "accepted_sha_match": True,
        "sha256": actual_sha,
        "classification": "POST_SEARCH_EXPERT_BENCHMARK",
        "pareto_eligible": False,
        **safety,
        "mean_wait_delta_vs_scenario_b_seconds_per_passenger": (
            record["mean_daily_wait_minutes"] - scenario_b["mean_daily_wait_minutes"]
        )
        * 60.0,
        "mismatch_delta_vs_scenario_b": (
            record["mean_daily_mismatch"] - scenario_b["mean_daily_mismatch"]
        ),
        "maximum_bucket_delta_vs_scenario_b_minutes": (
            record["maximum_bucket_expected_wait_minutes"]
            - scenario_b["maximum_bucket_expected_wait_minutes"]
        ),
        "daily_robustness_vs_scenario_b": comparison,
    }


def _evaluate_route(
    *,
    repo_root: Path,
    artifact_root: Path,
    route_id: str,
    workbook_path: Path,
    accepted_i: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    context, seeds = coordinator.load_route_coordinator_inputs_v1(
        repo_root=artifact_root,
        route_id=route_id,
        workbook_path=workbook_path,
    )
    result = coordinator.search_route_service_plans_v1(
        context=context,
        seeds=seeds,
        budget=FROZEN_BUDGET,
    )
    frontier = tuple(sorted(result.pareto_frontier, key=lambda item: item.pair_fingerprint))
    fingerprints = tuple(item.pair_fingerprint for item in frontier)
    accepted_fingerprints = tuple(
        sorted(accepted_i["routes"][route_id]["deterministic_signature"]["i_pareto_fingerprints"])
    )
    if fingerprints != accepted_fingerprints:
        raise RuntimeError(f"route {route_id} exact current I Pareto fingerprints changed")
    if len(frontier) != EXPECTED_I_PARETO_SIZES[route_id]:
        raise RuntimeError(f"route {route_id} current I Pareto size changed")
    if any(len(item.metrics.pareto_vector) != 10 for item in frontier):
        raise RuntimeError("production I Pareto vector is not exactly ten-dimensional")
    raw_route, eligible_dates, coverage = pr62_j._daily_authority(
        repo_root=repo_root,
        artifact_root=artifact_root,
        route_id=route_id,
        workbook_path=workbook_path,
    )
    index = pr62_j._observation_index(raw_route)
    scenario_daily = _daily_pair_metrics_with_mass(
        outbound_departures=context.scenario_b_departures["outbound"],
        inbound_departures=context.scenario_b_departures["inbound"],
        observation_index=index,
        eligible_dates=eligible_dates,
    )
    scenario_b = _reference_record(
        fingerprint="SCENARIO_B",
        outbound_departures=context.scenario_b_departures["outbound"],
        inbound_departures=context.scenario_b_departures["inbound"],
        context=context,
        daily=scenario_daily,
        selection_eligible=False,
    )
    candidates = [
        _engine_candidate_record(
            item,
            observation_index=index,
            eligible_dates=eligible_dates,
        )
        for item in frontier
    ]
    for item in candidates:
        item.update(_baseline_safety(item, scenario_b))
        item["daily_robustness_vs_scenario_b"] = _daily_comparison(
            item["daily"], scenario_b["daily"], expected_dates=eligible_dates
        )
    baseline_safe = _baseline_safe_engine_fingerprints(candidates)
    operational_frontier = _operational_frontier_fingerprints(candidates)
    classification = _route_classification(len(baseline_safe), len(operational_frontier))
    by_id = {str(item["fingerprint"]): item for item in candidates}
    minimum_wait = min(
        candidates, key=lambda item: (item["mean_daily_wait_minutes"], item["fingerprint"])
    )
    minimum_mismatch = min(
        candidates, key=lambda item: (item["mean_daily_mismatch"], item["fingerprint"])
    )
    minimum_palette = min(
        candidates,
        key=lambda item: (
            item["effective_palette_count"],
            item["sustained_headway_level_count"],
            item["fingerprint"],
        ),
    )
    marginal = []
    for fingerprint in operational_frontier:
        item = by_id[fingerprint]
        marginal.append(
            {
                "fingerprint": fingerprint,
                "vs_scenario_b": _marginal_delta(item, scenario_b),
                "vs_minimum_wait_i": _marginal_delta(item, minimum_wait),
                "vs_minimum_mismatch_i": _marginal_delta(item, minimum_mismatch),
            }
        )
    public_scenario = _public_record(scenario_b)
    route_evidence: dict[str, Any] = {
        "route_id": route_id,
        "search_status": result.status,
        "search_budget": dataclasses.asdict(FROZEN_BUDGET),
        "search_statistics": dataclasses.asdict(result.statistics),
        "I_pareto_size": len(candidates),
        "eligible_daily_date_count": len(eligible_dates),
        "daily_evidence_coverage": coverage,
        "SCENARIO_B": public_scenario,
        "SCENARIO_B_role": "NON_REGRESSION_BASELINE_NOT_ENGINE_CANDIDATE",
        "MINIMUM_WAIT_I_CANDIDATE": minimum_wait["fingerprint"],
        "MINIMUM_MISMATCH_I_CANDIDATE": minimum_mismatch["fingerprint"],
        "MINIMUM_PALETTE_I_CANDIDATE": minimum_palette["fingerprint"],
        "minimum_palette_basis": "effective palette, then sustained palette, then fingerprint",
        "BASELINE_SAFE_SET": list(baseline_safe),
        "BASELINE_SAFE_SET_size": len(baseline_safe),
        "BASELINE_SAFE_SET_status": (
            "BASELINE_SAFE_SET_EMPTY" if not baseline_safe else "BASELINE_SAFE_SET_NONEMPTY"
        ),
        "BASELINE_SAFE_OPERATIONAL_FRONTIER": list(operational_frontier),
        "BASELINE_SAFE_OPERATIONAL_FRONTIER_size": len(operational_frontier),
        "classification": classification,
        "recommended_for_recertification": (
            operational_frontier[0] if len(operational_frontier) == 1 else None
        ),
        "marginal_tradeoff_table": marginal,
        "candidates": [_public_record(item) for item in candidates],
    }
    internal = {
        "context": context,
        "eligible_dates": eligible_dates,
        "observation_index": index,
        "scenario_b": scenario_b,
        "candidates": candidates,
        "minimum_wait": minimum_wait,
        "minimum_mismatch": minimum_mismatch,
        "minimum_palette": minimum_palette,
    }
    if route_id == "10":
        safe_set = set(baseline_safe)
        operating_set = set(operational_frontier)
        route_evidence["inbound_extreme_tail_audit"] = {
            str(tail): [
                {
                    "fingerprint": item["fingerprint"],
                    "baseline_safe_wait": item["wait_non_regression"],
                    "baseline_safe_mismatch": item["mismatch_non_regression"],
                    "baseline_safe_maximum_bucket_wait": item[
                        "maximum_bucket_wait_non_regression"
                    ],
                    "BASELINE_SAFE_SET_member": item["fingerprint"] in safe_set,
                    "BASELINE_SAFE_OPERATIONAL_FRONTIER_member": (
                        item["fingerprint"] in operating_set
                    ),
                    "maximum_bucket_expected_wait_minutes": item[
                        "maximum_bucket_expected_wait_minutes"
                    ],
                    "p90_bucket_expected_wait_minutes": item[
                        "p90_bucket_expected_wait_minutes"
                    ],
                    "tail_maximum_bucket_wait_minutes": item[
                        "inbound_tail_maximum_bucket_wait_minutes"
                    ],
                    "fleet_required": item["fleet_required"],
                }
                for item in candidates
                if item["inbound_tail_headway_minutes"] == tail
            ]
            for tail in (30, 45, 48, 54)
        }
    return route_evidence, internal


def _route6_key_comparison(
    route: Mapping[str, Any],
    internal: Mapping[str, Any],
    human: Mapping[str, Any],
) -> list[dict[str, Any]]:
    by_id = {item["fingerprint"]: item for item in internal["candidates"]}
    rows: list[tuple[str, Mapping[str, Any]]] = [
        ("SCENARIO_B", internal["scenario_b"]),
        ("I_MINIMUM_WAIT", internal["minimum_wait"]),
        ("I_MINIMUM_PALETTE", internal["minimum_palette"]),
    ]
    rows.extend(
        ("BASELINE_SAFE_OPERATIONAL_FRONTIER", by_id[fingerprint])
        for fingerprint in route["BASELINE_SAFE_OPERATIONAL_FRONTIER"]
    )
    if human.get("available") and human.get("accepted_sha_match"):
        rows.append(("HUMAN_FINAL", human))
    return [
        {
            "role": role,
            "fingerprint": item["fingerprint"],
            "baseline_safe_passenger_service": (
                True if role == "SCENARIO_B" else item["baseline_safe_passenger_service"]
            ),
            "mean_daily_wait_minutes": item["mean_daily_wait_minutes"],
            "mean_daily_mismatch": item["mean_daily_mismatch"],
            "maximum_bucket_expected_wait_minutes": item[
                "maximum_bucket_expected_wait_minutes"
            ],
            "fleet_required": item["fleet_required"],
            "service_regime_count": item["service_regime_count"],
            "sustained_headway_level_count": item["sustained_headway_level_count"],
            "effective_palette_count": item["effective_palette_count"],
        }
        for role, item in rows
    ]


def build_evidence(repo_root: Path) -> dict[str, Any]:
    if dataclasses.astuple(FROZEN_BUDGET) != (24, 512, 4, 24, 512):
        raise RuntimeError("search budgets changed")
    accepted_j = json.loads(
        (repo_root / pr62_j.OUTPUT_JSON).read_text(encoding="utf-8")
    )
    if accepted_j["cross_route_classification"] != "MATERIALITY_RULE_NOT_SUPPORTED":
        raise RuntimeError("PR62-J is not the accepted negative calibration result")
    if any(
        accepted_j["routes"][route_id]["classification"]
        != "NO_JOINT_ONE_SE_PASSENGER_EQUIVALENT_SET"
        for route_id in ("6", "10")
    ):
        raise RuntimeError("PR62-J route classifications changed")
    artifact_root = pr62_i._artifact_root(repo_root)
    prior_before = coordinator.verify_frozen_prior_artifacts_v1(artifact_root)
    accepted_i = json.loads((repo_root / pr62_i.OUTPUT_JSON).read_text(encoding="utf-8"))
    routes: dict[str, Any] = {}
    internals: dict[str, Any] = {}
    for route_id in ("6", "10"):
        route, internal = _evaluate_route(
            repo_root=repo_root,
            artifact_root=artifact_root,
            route_id=route_id,
            workbook_path=(
                repo_root / f"Engine_Input_MST_{route_id}_V3_MultiPeriod_Mar-Jul_2026.xlsx"
            ),
            accepted_i=accepted_i,
        )
        routes[route_id] = route
        internals[route_id] = internal
    prior_after = coordinator.verify_frozen_prior_artifacts_v1(artifact_root)
    if prior_before != prior_after:
        raise RuntimeError("frozen prior artifacts changed during PR62-K evaluation")
    route6 = internals["6"]
    human = _human_final(
        repo_root=repo_root,
        context=route6["context"],
        observation_index=route6["observation_index"],
        eligible_dates=route6["eligible_dates"],
        scenario_b=route6["scenario_b"],
    )
    routes["6"]["key_comparison"] = _route6_key_comparison(routes["6"], route6, human)
    cross = _cross_route_classification(routes)
    ready = all(
        routes[route_id]["classification"] == "UNIQUE_BASELINE_SAFE_OPERATING_CANDIDATE"
        for route_id in ("6", "10")
    )
    return {
        "profile": PROFILE,
        "J_commit_SHA": J_COMMIT_SHA,
        "J_result": "COMPLETED_NEGATIVE_CALIBRATION_RESULT",
        "policy_question": (
            "Given the same authoritative trip total, does the proposed redistribution avoid "
            "making core passenger outcomes worse than the existing timetable?"
        ),
        "scenario_b_metric_authority": {
            "role": "NON_REGRESSION_BASELINE_NOT_OPTIMIZATION_TARGET",
            "departures": "exact authoritative Scenario B departures loaded by the coordinator",
            "daily_demand": "same raw daily demand source and 153 complete paired dates as PR62-J",
            "wait": "exact next-departure integration",
            "mismatch": "existing daily fixed-service-share minus daily-demand-share semantics",
            "maximum_bucket_wait": "existing active-bucket exact expected-wait semantics",
            "fleet": "current authoritative runtime and minimum layover",
            "demand_regime_model_selection_rerun": False,
        },
        "baseline_safe_semantics": {
            "name": "BASELINE_SAFE_PASSENGER_SERVICE",
            "statistical_equivalence": False,
            "numerical_epsilon": NUMERICAL_EPSILON,
            "all_required": [
                "mean daily expected wait <= Scenario B + numerical epsilon",
                "mean daily mismatch <= Scenario B + numerical epsilon",
                "maximum bucket expected wait <= Scenario B + numerical epsilon",
            ],
            "one_se_used": False,
            "percentage_tolerance_used": False,
            "five_second_rule_used": False,
            "weighted_score_used": False,
            "p90_is_diagnostic_only": True,
            "tail_maximum_is_diagnostic_only": True,
        },
        "operational_secondary_frontier": {
            "name": "BASELINE_SAFE_OPERATIONAL_FRONTIER",
            "applied_after_passenger_gates": True,
            "dimensions": list(OPERATIONAL_DIMENSIONS),
            "scalar_weighted": False,
            "automatic_lexicographic_winner": False,
        },
        "passenger_hours_semantics": (
            "For each complete date, Scenario B minus candidate mean wait is multiplied by that "
            "date's authoritative active passenger mass; daily passenger-wait minutes are then "
            "averaged across the 153 dates."
        ),
        "routes": routes,
        "human_final_route_6": human,
        "cross_route_classification": cross,
        "READY_FOR_POST_HI_RECERTIFICATION": ready,
        "PR62_G_products_status": "FROZEN_HISTORICAL_PRE_H_PRODUCTS_NOT_REGENERATED",
        "production_selector_added": False,
        "deterministic_render": {},
        "production_change_statement": {
            "Coordinator search changed": "NO",
            "10-D I Pareto vector changed": "NO",
            "Compiler changed": "NO",
            "Tail eligibility changed": "NO",
            "Rhythm metrics changed": "NO",
            "Queue changed": "NO",
            "F1/F2/F3 changed": "NO",
            "Search budgets changed": "NO",
            "Fleet validator changed": "NO",
            "Protection changed": "NO",
            "Settlement changed": "NO",
            "Final XLSX regenerated": "NO",
            "Production selector added": "NO",
        },
    }


def _set_line(label: str, values: Sequence[str]) -> str:
    return f"{label}: " + (", ".join(f"`{item}`" for item in values) or "`none`")


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# PR62-K — Baseline-safe operational shortlist calibration",
        "",
        f"J commit: `{payload['J_commit_SHA']}`; J remains a completed negative calibration result.",
        "",
        f"Cross-route classification: **`{payload['cross_route_classification']}`**.",
        f"READY_FOR_POST_HI_RECERTIFICATION: **{str(payload['READY_FOR_POST_HI_RECERTIFICATION']).upper()}**.",
        "",
        "K is a strict current-service non-regression policy experiment, not a statistical-equivalence test. Scenario B is an exact-departure reference row, not an I-search candidate. No one-SE, percentage tolerance, five-second rule, scalar score, or lexicographic winner is used.",
        "",
    ]
    for route_id in ("6", "10"):
        route = payload["routes"][route_id]
        baseline = route["SCENARIO_B"]
        lines.extend(
            [
                f"## Route {route_id}",
                "",
                f"Classification: **`{route['classification']}`**. I Pareto: **{route['I_pareto_size']}**; baseline-safe: **{route['BASELINE_SAFE_SET_size']}**; operational frontier: **{route['BASELINE_SAFE_OPERATIONAL_FRONTIER_size']}**.",
                "",
                f"Scenario B mean wait/mismatch/max/P90: **{baseline['mean_daily_wait_minutes']:.6f} min / {baseline['mean_daily_mismatch']:.8f} / {baseline['maximum_bucket_expected_wait_minutes']:.3f} min / {baseline['p90_bucket_expected_wait_minutes']:.3f} min**. Fleet/regimes/sustained/effective/excess terminal wait: **{baseline['fleet_required']}/{baseline['service_regime_count']}/{baseline['sustained_headway_level_count']}/{baseline['effective_palette_count']}/{baseline['total_excess_terminal_wait']}**.",
                "",
                _set_line("BASELINE_SAFE_SET", route["BASELINE_SAFE_SET"]),
                "",
                _set_line(
                    "BASELINE_SAFE_OPERATIONAL_FRONTIER",
                    route["BASELINE_SAFE_OPERATIONAL_FRONTIER"],
                ),
                "",
                "| Candidate | Safe W/M/Max | Mean wait | ΔB sec/pax | Mean mismatch | ΔB mismatch | Max | P90 | Fleet | Regimes | Sustained | Effective | Excess wait | Days W better/equal/worse | Pax-hours saved/day |",
                "|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for item in route["candidates"]:
            robustness = item["daily_robustness_vs_scenario_b"]
            lines.append(
                f"| `{item['fingerprint']}` | "
                f"{'Y' if item['wait_non_regression'] else 'N'}/"
                f"{'Y' if item['mismatch_non_regression'] else 'N'}/"
                f"{'Y' if item['maximum_bucket_wait_non_regression'] else 'N'} | "
                f"{item['mean_daily_wait_minutes']:.6f} | "
                f"{(item['mean_daily_wait_minutes'] - baseline['mean_daily_wait_minutes']) * 60:.3f} | "
                f"{item['mean_daily_mismatch']:.8f} | "
                f"{item['mean_daily_mismatch'] - baseline['mean_daily_mismatch']:.8f} | "
                f"{item['maximum_bucket_expected_wait_minutes']:.3f} | "
                f"{item['p90_bucket_expected_wait_minutes']:.3f} | "
                f"{item['fleet_required']} | {item['service_regime_count']} | "
                f"{item['sustained_headway_level_count']} | {item['effective_palette_count']} | "
                f"{item['total_excess_terminal_wait']} | "
                f"{robustness['wait_candidate_better_percentage']:.1f}/"
                f"{robustness['wait_equal_percentage']:.1f}/"
                f"{robustness['wait_candidate_worse_percentage']:.1f}% | "
                f"{robustness['passenger_wait_hours_saved_per_average_day']:.3f} |"
            )
        lines.extend(["", "### Marginal operational-frontier tradeoffs", ""])
        if not route["marginal_tradeoff_table"]:
            lines.append("No baseline-safe operational-frontier candidate.")
        else:
            lines.extend(
                [
                    "| Candidate | Reference | Δ wait sec/pax | Δ mismatch | Δ max | Δ P90 | Δ fleet | Δ regimes | Δ sustained | Δ effective | Δ excess wait |",
                    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for item in route["marginal_tradeoff_table"]:
                for key in ("vs_scenario_b", "vs_minimum_wait_i", "vs_minimum_mismatch_i"):
                    delta = item[key]
                    lines.append(
                        f"| `{item['fingerprint']}` | `{delta['reference']}` | "
                        f"{delta['delta_mean_wait_seconds_per_passenger']:.3f} | "
                        f"{delta['delta_mean_mismatch']:.8f} | "
                        f"{delta['delta_maximum_bucket_wait_minutes']:.3f} | "
                        f"{delta['delta_p90_bucket_wait_minutes']:.3f} | "
                        f"{delta['delta_fleet_required']} | {delta['delta_service_regime_count']} | "
                        f"{delta['delta_sustained_palette_count']} | "
                        f"{delta['delta_effective_palette_count']} | "
                        f"{delta['delta_total_excess_terminal_wait']} |"
                    )
        lines.append("")
        if route_id == "10":
            lines.extend(["### Route 10 inbound extreme-tail audit", ""])
            for tail, items in route["inbound_extreme_tail_audit"].items():
                if not items:
                    lines.append(f"- {tail} minutes: not present in current I frontier.")
                for item in items:
                    lines.append(
                        f"- {tail}-minute `{item['fingerprint']}`: W/M/Max "
                        f"{'YES' if item['baseline_safe_wait'] else 'NO'}/"
                        f"{'YES' if item['baseline_safe_mismatch'] else 'NO'}/"
                        f"{'YES' if item['baseline_safe_maximum_bucket_wait'] else 'NO'}; "
                        f"baseline-safe set {'YES' if item['BASELINE_SAFE_SET_member'] else 'NO'}; "
                        f"operational frontier {'YES' if item['BASELINE_SAFE_OPERATIONAL_FRONTIER_member'] else 'NO'}."
                    )
            lines.append("")
    human = payload["human_final_route_6"]
    lines.extend(["## Route 6 Human Final", ""])
    if not human["available"]:
        lines.append("Accepted Human Final workbook is unavailable.")
    elif not human["accepted_sha_match"]:
        lines.append("Human Final workbook SHA does not match the accepted authority.")
    else:
        lines.append(
            f"`POST_SEARCH_EXPERT_BENCHMARK`; selectable: **NO**; baseline-safe: **{'YES' if human['baseline_safe_passenger_service'] else 'NO'}**. Δ wait/mismatch/max vs Scenario B: **{human['mean_wait_delta_vs_scenario_b_seconds_per_passenger']:.3f} sec/passenger / {human['mismatch_delta_vs_scenario_b']:.8f} / {human['maximum_bucket_delta_vs_scenario_b_minutes']:.3f} min**. Fleet/regimes/sustained/effective: **{human['fleet_required']}/{human['service_regime_count']}/{human['sustained_headway_level_count']}/{human['effective_palette_count']}**."
        )
    lines.extend(["", "## Route 6 key comparison", ""])
    lines.extend(
        [
            "| Role | Fingerprint | Baseline-safe | Wait | Mismatch | Max | Fleet | Regimes | Sustained | Effective |",
            "|---|---|:---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for item in payload["routes"]["6"]["key_comparison"]:
        lines.append(
            f"| {item['role']} | `{item['fingerprint']}` | "
            f"{'YES' if item['baseline_safe_passenger_service'] else 'NO'} | "
            f"{item['mean_daily_wait_minutes']:.6f} | {item['mean_daily_mismatch']:.8f} | "
            f"{item['maximum_bucket_expected_wait_minutes']:.3f} | "
            f"{item['fleet_required']} | {item['service_regime_count']} | "
            f"{item['sustained_headway_level_count']} | {item['effective_palette_count']} |"
        )
    lines.extend(["", "## Production status", ""])
    lines.extend(
        f"- {key}: **{payload['production_change_statement'][key]}**"
        for key in sorted(payload["production_change_statement"])
    )
    return "\n".join(lines)


def _write_evidence(repo_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    preliminary_json = _canonical_json_bytes(payload)
    preliminary_markdown = (_markdown(payload) + "\n").encode("utf-8")
    payload["deterministic_render"] = {
        "pre_metadata_json_sha256": _sha256_bytes(preliminary_json),
        "pre_metadata_markdown_sha256": _sha256_bytes(preliminary_markdown),
        "rendered_twice_byte_identical": True,
    }
    json_first = _canonical_json_bytes(payload)
    json_second = _canonical_json_bytes(payload)
    markdown_first = (_markdown(payload) + "\n").encode("utf-8")
    markdown_second = (_markdown(payload) + "\n").encode("utf-8")
    if json_first != json_second or markdown_first != markdown_second:
        raise RuntimeError("PR62-K evidence render is not byte-identical")
    json_path = repo_root / OUTPUT_JSON
    markdown_path = repo_root / OUTPUT_MARKDOWN
    json_path.write_bytes(json_first)
    markdown_path.write_bytes(markdown_first)
    return {
        "json": str(json_path),
        "json_bytes": len(json_first),
        "json_sha256": _sha256_bytes(json_first),
        "markdown": str(markdown_path),
        "markdown_bytes": len(markdown_first),
        "markdown_sha256": _sha256_bytes(markdown_first),
        "classification": payload["cross_route_classification"],
        "ready_for_recertification": payload["READY_FOR_POST_HI_RECERTIFICATION"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    payload = build_evidence(repo_root)
    print(json.dumps(_write_evidence(repo_root, payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
