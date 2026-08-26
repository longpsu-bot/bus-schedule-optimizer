"""Generate compact PR62-J paired daily materiality evidence.

This runner is deliberately review-only.  It evaluates the exact current I
Pareto timetables against paired complete daily demand profiles without
changing coordinator search, production Pareto semantics, or final products.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT / "src", _REPO_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import run_pr62_i_worst_bucket_passenger_access as pr62_i  # noqa: E402

import bus_schedule_engine.service_plan_coordinator as coordinator  # noqa: E402
from bus_schedule_engine.contracts_v1.demand_regimes import (  # noqa: E402
    DailyDemandObservationV1,
)
from bus_schedule_engine.contracts_v1.multi_period_demand import (  # noqa: E402
    derive_demand_profile_v1,
)
from bus_schedule_engine.raw_daily_demand import (  # noqa: E402
    RawDailyDemandRouteV1,
    import_t06_t10_daily_demand_v1,
    reconcile_raw_daily_demand_v1,
)
from bus_schedule_engine.v3_workbook import import_v3_multi_period_workbook_v1  # noqa: E402

NUMERICAL_EPSILON = 1e-12
PROFILE = "pr62_j_daily_materiality_calibration_v1"
I_COMMIT_SHA = "2bc34f5287abe76dc7f7f56f5426d0766777087f"
EXPECTED_I_PARETO_SIZES = {"6": 47, "10": 11}
EXPECTED_HUMAN_FINAL_SHA256 = pr62_i.EXPECTED_HUMAN_FINAL_SHA256
RAW_SOURCE_NAME = "T06&T10_01012025_31072026.xlsx"
OUTPUT_JSON = Path("docs/engine/evidence/PR62_J_DAILY_MATERIALITY_CALIBRATION.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_J_DAILY_MATERIALITY_CALIBRATION.md")
FROZEN_BUDGET = coordinator.CoordinatorSearchBudgetV1(24, 512, 4, 24, 512)
SECONDARY_OPERATING_DIMENSIONS = (
    "maximum_bucket_expected_wait_minutes",
    "sustained_headway_level_count",
    "service_regime_count",
    "fleet_required",
    "total_excess_terminal_wait",
)


def _paired_one_se(
    candidate_by_date: Mapping[date, float],
    reference_by_date: Mapping[date, float],
    *,
    expected_dates: Sequence[date],
    epsilon: float = NUMERICAL_EPSILON,
) -> dict[str, float | int | bool]:
    """Summarize same-date candidate-minus-reference differences."""

    dates = tuple(expected_dates)
    expected = set(dates)
    if not dates or len(expected) != len(dates):
        raise ValueError("expected paired date set must be nonempty and unique")
    if set(candidate_by_date) != expected or set(reference_by_date) != expected:
        raise ValueError("candidate and reference must match the authoritative paired date set")
    differences = tuple(
        float(candidate_by_date[item]) - float(reference_by_date[item]) for item in dates
    )
    mean_delta = statistics.fmean(differences)
    sample_sd = statistics.stdev(differences) if len(differences) > 1 else 0.0
    if all(item == differences[0] for item in differences):
        sample_sd = 0.0
    standard_error = sample_sd / math.sqrt(len(differences))
    passes_one_se = (
        mean_delta <= 0.0 if sample_sd == 0.0 else mean_delta <= standard_error + epsilon
    )
    better = sum(item < -epsilon for item in differences)
    worse = sum(item > epsilon for item in differences)
    equal = len(differences) - better - worse
    return {
        "mean_delta": mean_delta,
        "sample_standard_deviation": sample_sd,
        "standard_error": standard_error,
        "paired_date_count": len(differences),
        "candidate_better_percentage": 100.0 * better / len(differences),
        "reference_better_percentage": 100.0 * worse / len(differences),
        "equal_percentage": 100.0 * equal / len(differences),
        "passes_one_se": passes_one_se,
    }


def _passenger_equivalent_fingerprints(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(item["fingerprint"])
            for item in candidates
            if item["wait_one_se"] and item["mismatch_one_se"]
        )
    )


def _secondary_dominates(
    left: Mapping[str, float | int],
    right: Mapping[str, float | int],
    *,
    epsilon: float = NUMERICAL_EPSILON,
) -> bool:
    left_values = tuple(float(left[key]) for key in SECONDARY_OPERATING_DIMENSIONS)
    right_values = tuple(float(right[key]) for key in SECONDARY_OPERATING_DIMENSIONS)
    return all(a <= b + epsilon for a, b in zip(left_values, right_values, strict=True)) and any(
        a < b - epsilon for a, b in zip(left_values, right_values, strict=True)
    )


def _secondary_operating_frontier_fingerprints(
    candidates: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            str(item["fingerprint"])
            for item in candidates
            if not any(
                str(other["fingerprint"]) != str(item["fingerprint"])
                and _secondary_dominates(
                    other["secondary_metrics"],
                    item["secondary_metrics"],
                )
                for other in candidates
            )
        )
    )


def _metric_reference_fingerprint(
    candidates: Sequence[Mapping[str, Any]],
    daily_metric_key: str,
) -> str:
    if not candidates:
        raise ValueError("a metric reference requires at least one candidate")
    return str(
        min(
            candidates,
            key=lambda item: (
                statistics.fmean(float(value) for value in item[daily_metric_key].values()),
                str(item["fingerprint"]),
            ),
        )["fingerprint"]
    )


def _daily_direction_metrics(
    departures: Sequence[int],
    observations: Sequence[DailyDemandObservationV1],
) -> dict[str, float]:
    if not observations:
        raise ValueError("daily directional observations are required")
    ordered = tuple(sorted(observations, key=lambda item: (item.interval_start, item.interval_end)))
    dates = {item.observation_date for item in ordered}
    directions = {item.direction.value for item in ordered}
    if len(dates) != 1 or len(directions) != 1:
        raise ValueError("daily directional observations must share one date and direction")
    buckets = tuple(
        coordinator.DemandBucketEvidenceV1(
            direction=item.direction.value,
            start=item.interval_start,
            end=item.interval_end,
            observed_demand=item.passenger_demand,
        )
        for item in ordered
    )
    total_demand = sum(item.observed_demand for item in buckets)
    if total_demand <= 0:
        raise ValueError("daily directional demand must contain positive mass")
    counts = coordinator._bucket_counts(departures, buckets)
    total_trips = len(departures)
    demand_shares = tuple(item.observed_demand / total_demand for item in buckets)
    service_shares = tuple(item / total_trips for item in counts)
    mismatch = sum(
        (service - demand) ** 2
        for service, demand in zip(service_shares, demand_shares, strict=True)
    )
    expected_wait, _maximum, _per_bucket, active_mass = (
        coordinator.expected_passenger_wait_metrics_v1(departures, buckets)
    )
    return {
        "expected_wait_minutes": expected_wait,
        "observed_demand_mismatch": mismatch,
        "active_demand_mass": active_mass,
    }


def _route_classification(passenger_size: int, secondary_size: int) -> str:
    if passenger_size < 0 or secondary_size < 0 or secondary_size > passenger_size:
        raise ValueError("frontier sizes are inconsistent")
    if passenger_size == 0:
        return "NO_JOINT_ONE_SE_PASSENGER_EQUIVALENT_SET"
    if passenger_size == 1:
        return "UNIQUE_PASSENGER_EQUIVALENT_CANDIDATE"
    if secondary_size == 1:
        return "UNIQUE_MATERIALITY_OPERATING_CANDIDATE"
    return "MULTIPLE_MATERIALITY_EQUIVALENT_TRADEOFFS"


def _cross_route_classification(route_classifications: Sequence[str]) -> str:
    unique = {
        "UNIQUE_PASSENGER_EQUIVALENT_CANDIDATE",
        "UNIQUE_MATERIALITY_OPERATING_CANDIDATE",
    }
    if route_classifications and all(item in unique for item in route_classifications):
        return "MATERIALITY_RULE_SUPPORTED_FOR_PRODUCTION"
    if "MULTIPLE_MATERIALITY_EQUIVALENT_TRADEOFFS" in route_classifications:
        return "MATERIALITY_RULE_NEEDS_DOMAIN_TIEBREAK"
    return "MATERIALITY_RULE_NOT_SUPPORTED"


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _daily_authority(
    *,
    repo_root: Path,
    artifact_root: Path,
    route_id: str,
    workbook_path: Path,
) -> tuple[RawDailyDemandRouteV1, tuple[date, ...], dict[str, Any]]:
    raw_path = repo_root / RAW_SOURCE_NAME
    if not raw_path.is_file():
        raise FileNotFoundError(f"required raw daily source unavailable: {raw_path}")
    imported = import_v3_multi_period_workbook_v1(workbook_path)
    multi_period = imported.multi_period_demand
    profile_id = multi_period.default_profile_id
    if profile_id is None:
        raise ValueError(f"route {route_id} V3 workbook has no default demand profile")
    derivation = derive_demand_profile_v1(multi_period, profile_id)
    period_lookup = {item.period_id: item for item in multi_period.periods}
    periods = tuple(period_lookup[item] for item in derivation.profile.included_period_ids)
    period_start = min(item.period_start for item in periods)
    period_end = max(item.period_end for item in periods)
    accepted_path = (
        artifact_root
        / "outputs"
        / "demand_regime_model_selection"
        / f"route_{route_id}_demand_regimes.json"
    )
    accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
    accepted_raw = accepted.get("raw_daily_source")
    if not isinstance(accepted_raw, dict):
        raise ValueError(f"route {route_id} accepted raw daily authority is unavailable")
    result = import_t06_t10_daily_demand_v1(
        raw_path,
        derivation.profile,
        period_start=period_start,
        period_end=period_end,
        route_ids=(route_id,),
    )
    if result.source_sha256 != accepted_raw.get("source_sha256"):
        raise ValueError(f"route {route_id} raw daily source SHA does not match accepted authority")
    if result.selected_period_start.isoformat() != accepted_raw.get(
        "selected_period_start"
    ) or result.selected_period_end.isoformat() != accepted_raw.get("selected_period_end"):
        raise ValueError(f"route {route_id} selected raw date range changed")
    raw_route = next((item for item in result.routes if item.route_id == route_id), None)
    if raw_route is None:
        raise ValueError(f"raw daily source does not contain route {route_id}")
    reconciliation = reconcile_raw_daily_demand_v1(raw_route, derivation.profile)
    if (
        reconciliation.mismatched_bucket_count != 0
        or reconciliation.maximum_absolute_difference > NUMERICAL_EPSILON
    ):
        raise ValueError(f"route {route_id} frozen raw-to-V3 reconciliation failed")
    accepted_reconciliation = accepted.get("raw_v3_reconciliation")
    if (
        not isinstance(accepted_reconciliation, dict)
        or int(accepted_reconciliation.get("mismatched_bucket_count", -1)) != 0
    ):
        raise ValueError(f"route {route_id} accepted reconciliation is not exact")
    by_direction: dict[str, set[date]] = defaultdict(set)
    for item in raw_route.daily_observations:
        by_direction[item.direction.value].add(item.observation_date)
    eligible_dates = tuple(sorted(by_direction["outbound"] & by_direction["inbound"]))
    minimum_days = int(accepted["model_selection"]["config"]["min_validation_days"])
    if len(eligible_dates) < minimum_days:
        raise ValueError(
            f"route {route_id} has {len(eligible_dates)} paired complete dates; "
            f"accepted authority requires {minimum_days}"
        )
    audits = {}
    for audit in raw_route.direction_audits:
        direction_dates = tuple(sorted(by_direction[audit.direction.value]))
        if len(direction_dates) != audit.complete_date_count:
            raise ValueError(f"route {route_id} complete-day manifest does not reconcile")
        audits[audit.direction.value] = {
            "raw_source_path": RAW_SOURCE_NAME,
            "raw_source_sha256": result.source_sha256,
            "selected_date_range": [period_start.isoformat(), period_end.isoformat()],
            "total_raw_dates": audit.raw_date_count,
            "eligible_complete_dates": audit.complete_date_count,
            "complete_day_manifest": [item.isoformat() for item in direction_dates],
            "excluded_incomplete_date_count": len(audit.incomplete_dates),
            "excluded_incomplete_dates": [item.isoformat() for item in audit.incomplete_dates],
            "compared_bucket_count": sum(
                item.direction.value == audit.direction.value for item in reconciliation.buckets
            ),
            "minimum_complete_days_required": minimum_days,
            "reconciliation_status": "EXACT",
        }
    coverage = {
        "adapter_profile": result.adapter_profile,
        "source_path": RAW_SOURCE_NAME,
        "source_sha256": result.source_sha256,
        "selected_date_range": [period_start.isoformat(), period_end.isoformat()],
        "eligible_paired_date_count": len(eligible_dates),
        "eligible_paired_date_manifest": [item.isoformat() for item in eligible_dates],
        "compared_bucket_count": reconciliation.compared_bucket_count,
        "reconciliation_status": "EXACT",
        "directions": audits,
    }
    return raw_route, eligible_dates, coverage


def _observation_index(
    route: RawDailyDemandRouteV1,
) -> dict[tuple[date, str], tuple[DailyDemandObservationV1, ...]]:
    grouped: dict[tuple[date, str], list[DailyDemandObservationV1]] = defaultdict(list)
    for item in route.daily_observations:
        grouped[(item.observation_date, item.direction.value)].append(item)
    return {
        key: tuple(sorted(values, key=lambda item: (item.interval_start, item.interval_end)))
        for key, values in grouped.items()
    }


def _daily_pair_metrics(
    *,
    outbound_departures: Sequence[int],
    inbound_departures: Sequence[int],
    observation_index: Mapping[tuple[date, str], Sequence[DailyDemandObservationV1]],
    eligible_dates: Sequence[date],
) -> tuple[dict[date, float], dict[date, float]]:
    waits: dict[date, float] = {}
    mismatches: dict[date, float] = {}
    for observed_date in eligible_dates:
        outbound = _daily_direction_metrics(
            outbound_departures,
            observation_index[(observed_date, "outbound")],
        )
        inbound = _daily_direction_metrics(
            inbound_departures,
            observation_index[(observed_date, "inbound")],
        )
        total_mass = outbound["active_demand_mass"] + inbound["active_demand_mass"]
        if total_mass <= 0:
            raise ValueError(f"paired daily demand has no positive mass on {observed_date}")
        waits[observed_date] = (
            outbound["expected_wait_minutes"] * outbound["active_demand_mass"]
            + inbound["expected_wait_minutes"] * inbound["active_demand_mass"]
        ) / total_mass
        mismatches[observed_date] = (
            outbound["observed_demand_mismatch"] + inbound["observed_demand_mismatch"]
        )
    return waits, mismatches


def _candidate_record(
    item: coordinator.OperatingPairCandidateV1,
    *,
    observation_index: Mapping[tuple[date, str], Sequence[DailyDemandObservationV1]],
    eligible_dates: Sequence[date],
) -> dict[str, Any]:
    outbound = item.outbound.compile_variant.compilation.exact_departures
    inbound = item.inbound.compile_variant.compilation.exact_departures
    daily_wait, daily_mismatch = _daily_pair_metrics(
        outbound_departures=outbound,
        inbound_departures=inbound,
        observation_index=observation_index,
        eligible_dates=eligible_dates,
    )
    metrics = item.metrics
    return {
        "fingerprint": item.pair_fingerprint,
        "daily_wait": daily_wait,
        "daily_mismatch": daily_mismatch,
        "mean_daily_wait_minutes": statistics.fmean(daily_wait.values()),
        "mean_daily_mismatch": statistics.fmean(daily_mismatch.values()),
        "maximum_bucket_expected_wait_minutes": metrics.maximum_bucket_expected_wait_minutes,
        "p90_bucket_expected_wait_minutes": (metrics.maximum_directional_p90_bucket_wait_minutes),
        "fleet_required": metrics.fleet_required,
        "service_regime_count": metrics.actual_service_regime_count,
        "sustained_headway_level_count": (metrics.total_directional_sustained_headway_level_count),
        "effective_palette_count": metrics.total_directional_effective_palette_count,
        "total_excess_terminal_wait": metrics.total_excess_terminal_wait,
        "outbound_tail_headway_minutes": item.outbound.metrics.tail_headway_minutes,
        "inbound_tail_headway_minutes": item.inbound.metrics.tail_headway_minutes,
        "inbound_tail_maximum_bucket_wait_minutes": (
            item.inbound.metrics.tail_maximum_bucket_expected_wait_minutes
        ),
        "secondary_metrics": {
            "maximum_bucket_expected_wait_minutes": (metrics.maximum_bucket_expected_wait_minutes),
            "sustained_headway_level_count": (
                metrics.total_directional_sustained_headway_level_count
            ),
            "service_regime_count": metrics.actual_service_regime_count,
            "fleet_required": metrics.fleet_required,
            "total_excess_terminal_wait": metrics.total_excess_terminal_wait,
        },
    }


def _public_candidate_record(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if key not in {"daily_wait", "daily_mismatch", "secondary_metrics"}
    }


def _evaluate_route(
    *,
    repo_root: Path,
    artifact_root: Path,
    route_id: str,
    workbook_path: Path,
    accepted_i: Mapping[str, Any],
) -> tuple[dict[str, Any], Any, list[dict[str, Any]]]:
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
    raw_route, eligible_dates, coverage = _daily_authority(
        repo_root=repo_root,
        artifact_root=artifact_root,
        route_id=route_id,
        workbook_path=workbook_path,
    )
    index = _observation_index(raw_route)
    candidates = [
        _candidate_record(item, observation_index=index, eligible_dates=eligible_dates)
        for item in frontier
    ]
    wait_reference = _metric_reference_fingerprint(candidates, "daily_wait")
    mismatch_reference = _metric_reference_fingerprint(candidates, "daily_mismatch")
    by_id = {item["fingerprint"]: item for item in candidates}
    for item in candidates:
        wait_summary = _paired_one_se(
            item["daily_wait"],
            by_id[wait_reference]["daily_wait"],
            expected_dates=eligible_dates,
        )
        mismatch_summary = _paired_one_se(
            item["daily_mismatch"],
            by_id[mismatch_reference]["daily_mismatch"],
            expected_dates=eligible_dates,
        )
        item.update(
            {
                "wait_delta_vs_reference_minutes": wait_summary["mean_delta"],
                "wait_paired_sample_sd_minutes": wait_summary["sample_standard_deviation"],
                "wait_standard_error_minutes": wait_summary["standard_error"],
                "wait_one_se": wait_summary["passes_one_se"],
                "mismatch_delta_vs_reference": mismatch_summary["mean_delta"],
                "mismatch_paired_sample_sd": mismatch_summary["sample_standard_deviation"],
                "mismatch_standard_error": mismatch_summary["standard_error"],
                "mismatch_one_se": mismatch_summary["passes_one_se"],
            }
        )
    passenger_set = _passenger_equivalent_fingerprints(candidates)
    passenger_candidates = [item for item in candidates if item["fingerprint"] in passenger_set]
    secondary_frontier = _secondary_operating_frontier_fingerprints(passenger_candidates)
    classification = _route_classification(len(passenger_set), len(secondary_frontier))
    recommended = (
        passenger_set[0]
        if len(passenger_set) == 1
        else secondary_frontier[0]
        if len(secondary_frontier) == 1
        else None
    )
    route_evidence = {
        "route_id": route_id,
        "search_status": result.status,
        "search_budget": dataclasses.asdict(FROZEN_BUDGET),
        "search_statistics": dataclasses.asdict(result.statistics),
        "I_pareto_size": len(candidates),
        "eligible_daily_date_count": len(eligible_dates),
        "WAIT_REFERENCE": wait_reference,
        "MISMATCH_REFERENCE": mismatch_reference,
        "PASSENGER_EQUIVALENT_SET": list(passenger_set),
        "PASSENGER_EQUIVALENT_SET_size": len(passenger_set),
        "MATERIALITY_EQUIVALENT_OPERATING_FRONTIER": list(secondary_frontier),
        "MATERIALITY_EQUIVALENT_OPERATING_FRONTIER_size": len(secondary_frontier),
        "classification": classification,
        "recommended_for_recertification": recommended,
        "daily_evidence_coverage": coverage,
        "candidates": [_public_candidate_record(item) for item in candidates],
    }
    if route_id == "10":
        secondary_set = set(secondary_frontier)
        passenger_ids = set(passenger_set)
        route_evidence["inbound_tail_30_45_audit"] = {
            str(tail): [
                {
                    "fingerprint": item["fingerprint"],
                    "WAIT_ONE_SE": item["wait_one_se"],
                    "MISMATCH_ONE_SE": item["mismatch_one_se"],
                    "passenger_equivalent_set_member": item["fingerprint"] in passenger_ids,
                    "secondary_frontier_member": item["fingerprint"] in secondary_set,
                    "maximum_bucket_expected_wait_minutes": item[
                        "maximum_bucket_expected_wait_minutes"
                    ],
                    "p90_bucket_expected_wait_minutes": item["p90_bucket_expected_wait_minutes"],
                    "tail_maximum_bucket_wait_minutes": item[
                        "inbound_tail_maximum_bucket_wait_minutes"
                    ],
                    "fleet_required": item["fleet_required"],
                    "sustained_headway_level_count": item["sustained_headway_level_count"],
                    "service_regime_count": item["service_regime_count"],
                }
                for item in candidates
                if item["inbound_tail_headway_minutes"] == tail
            ]
            for tail in (30, 45)
        }
    return route_evidence, context, candidates


def _human_final_evidence(
    *,
    repo_root: Path,
    context: Any,
    candidates: Sequence[Mapping[str, Any]],
    route_evidence: Mapping[str, Any],
    raw_route: RawDailyDemandRouteV1,
    eligible_dates: Sequence[date],
) -> dict[str, Any]:
    workbook = repo_root / "private" / "Route_6_Current_ExternalAI_HumanFinal.xlsx"
    if not workbook.is_file():
        return {"available": False, "accepted_sha_match": False, "diagnostics": None}
    actual_sha = _sha256_path(workbook)
    if actual_sha != EXPECTED_HUMAN_FINAL_SHA256:
        return {
            "available": True,
            "accepted_sha_match": False,
            "sha256": actual_sha,
            "diagnostics": None,
        }
    parsed = pr62_i.parse_route6_reference_workbook(workbook)
    source = parsed["references"]["HUMAN_FINAL"]
    index = _observation_index(raw_route)
    daily_wait, daily_mismatch = _daily_pair_metrics(
        outbound_departures=source["outbound"],
        inbound_departures=source["inbound"],
        observation_index=index,
        eligible_dates=eligible_dates,
    )
    by_id = {item["fingerprint"]: item for item in candidates}
    wait_reference = by_id[str(route_evidence["WAIT_REFERENCE"])]
    mismatch_reference = by_id[str(route_evidence["MISMATCH_REFERENCE"])]
    wait_summary = _paired_one_se(
        daily_wait,
        wait_reference["daily_wait"],
        expected_dates=eligible_dates,
    )
    mismatch_summary = _paired_one_se(
        daily_mismatch,
        mismatch_reference["daily_mismatch"],
        expected_dates=eligible_dates,
    )
    deterministic = pr62_i._human_final(context, workbook)
    if deterministic is None or deterministic.get("diagnostics") is not None:
        raise RuntimeError("accepted Human Final deterministic diagnostics are unavailable")
    directions = deterministic["directions"]
    comparisons = []
    for item in candidates:
        summary = _paired_one_se(
            item["daily_wait"],
            daily_wait,
            expected_dates=eligible_dates,
        )
        mean_delta = float(summary["mean_delta"])
        standard_error = float(summary["standard_error"])
        if abs(mean_delta) <= standard_error + NUMERICAL_EPSILON:
            classification = "WITHIN_ONE_SE_OF_HUMAN_FINAL"
        elif mean_delta < 0:
            classification = "ENGINE_BETTER_BEYOND_ONE_SE"
        else:
            classification = "HUMAN_FINAL_BETTER_BEYOND_ONE_SE"
        comparisons.append(
            {
                "fingerprint": item["fingerprint"],
                "mean_delta_seconds_per_passenger": mean_delta * 60,
                "paired_sample_sd_seconds_per_passenger": float(
                    summary["sample_standard_deviation"]
                )
                * 60,
                "standard_error_seconds_per_passenger": standard_error * 60,
                "eligible_paired_dates": summary["paired_date_count"],
                "candidate_better_percentage": summary["candidate_better_percentage"],
                "human_final_better_percentage": summary["reference_better_percentage"],
                "equal_percentage": summary["equal_percentage"],
                "one_se_classification": classification,
            }
        )
    return {
        "available": True,
        "accepted_sha_match": True,
        "sha256": actual_sha,
        "classification": "POST_SEARCH_EXPERT_BENCHMARK",
        "pareto_eligible": False,
        "eligible_daily_date_count": len(eligible_dates),
        "mean_daily_expected_wait_minutes": statistics.fmean(daily_wait.values()),
        "wait_delta_vs_WAIT_REFERENCE_minutes": wait_summary["mean_delta"],
        "wait_paired_sample_sd_minutes": wait_summary["sample_standard_deviation"],
        "wait_standard_error_minutes": wait_summary["standard_error"],
        "WAIT_ONE_SE": wait_summary["passes_one_se"],
        "mean_daily_mismatch": statistics.fmean(daily_mismatch.values()),
        "mismatch_delta_vs_MISMATCH_REFERENCE": mismatch_summary["mean_delta"],
        "mismatch_paired_sample_sd": mismatch_summary["sample_standard_deviation"],
        "mismatch_standard_error": mismatch_summary["standard_error"],
        "MISMATCH_ONE_SE": mismatch_summary["passes_one_se"],
        "maximum_bucket_expected_wait_minutes": deterministic["pair"][
            "maximum_bucket_wait_minutes"
        ],
        "p90_bucket_expected_wait_minutes": deterministic["pair"][
            "maximum_directional_p90_bucket_wait_minutes"
        ],
        "fleet_required": deterministic["pair"]["fleet"],
        "service_regime_count": sum(
            directions[key]["actual_headway_run_count"] for key in ("outbound", "inbound")
        ),
        "sustained_headway_level_count": sum(
            len(directions[key]["sustained_headway_levels"]) for key in ("outbound", "inbound")
        ),
        "effective_palette_count": sum(
            len(directions[key]["effective_headway_palette"]) for key in ("outbound", "inbound")
        ),
        "engine_candidate_wait_comparisons": comparisons,
        "interpretation_limit": "Statistical practical equivalence is not causal proof.",
    }


def _production_change_lines(statement: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(f"- {key}: **{statement[key]}**" for key in sorted(statement))


def _fingerprint_set_line(label: str, fingerprints: Sequence[str]) -> str:
    rendered = ", ".join(f"`{item}`" for item in fingerprints) or "`none`"
    return f"{label}: {rendered}"


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# PR62-J — Paired daily materiality calibration",
        "",
        f"- I commit: `{payload['I_commit_SHA']}`",
        f"- Cross-route classification: **{payload['cross_route_classification']}**",
        f"- READY_FOR_POST_HI_RECERTIFICATION: **{str(payload['READY_FOR_POST_HI_RECERTIFICATION']).lower()}**",
        "- Candidate timetables: exact current I Pareto departures, evaluated post-search.",
        "- Pairing: candidate minus metric-specific reference on the same eligible date.",
        "- One-SE: mean paired delta ≤ sample SD / sqrt(n) + 1e-12; when variance is exactly zero, SE is 0 and only a non-positive mean passes.",
        "- Maximum-bucket, P90, tail access, fleet, and rhythm metrics remain deterministic.",
        "",
    ]
    for route_id in ("6", "10"):
        route = payload["routes"][route_id]
        coverage = route["daily_evidence_coverage"]
        lines.extend(
            [
                f"## Route {route_id}",
                "",
                f"Classification: **{route['classification']}**.",
                "",
                f"I Pareto / eligible dates / passenger-equivalent / secondary frontier: "
                f"**{route['I_pareto_size']} / {route['eligible_daily_date_count']} / "
                f"{route['PASSENGER_EQUIVALENT_SET_size']} / "
                f"{route['MATERIALITY_EQUIVALENT_OPERATING_FRONTIER_size']}**.",
                f"WAIT_REFERENCE: `{route['WAIT_REFERENCE']}`",
                f"MISMATCH_REFERENCE: `{route['MISMATCH_REFERENCE']}`",
                f"Recommended for recertification: "
                f"`{route['recommended_for_recertification'] or 'none — human review required'}`",
                "",
                "### Daily evidence coverage",
                "",
                f"Source: `{coverage['source_path']}`; SHA-256 "
                f"`{coverage['source_sha256']}`; selected "
                f"{coverage['selected_date_range'][0]} to {coverage['selected_date_range'][1]}; "
                f"reconciliation `{coverage['reconciliation_status']}`.",
                "",
                "| Direction | Raw dates | Complete | Excluded | Compared buckets | Status |",
                "|---|---:|---:|---:|---:|---|",
            ]
        )
        for direction in ("outbound", "inbound"):
            item = coverage["directions"][direction]
            lines.append(
                f"| {direction} | {item['total_raw_dates']} | "
                f"{item['eligible_complete_dates']} | "
                f"{item['excluded_incomplete_date_count']} | "
                f"{item['compared_bucket_count']} | {item['reconciliation_status']} |"
            )
        lines.extend(
            [
                "",
                "### Candidate calibration",
                "",
                "| Fingerprint | Mean wait | Δ wait | SE wait | W 1-SE | Mean mismatch | "
                "Δ mismatch | SE mismatch | M 1-SE | Max wait | P90 | Fleet | Regimes | "
                "Sustained | Effective | OB tail | IB tail |",
                "|---|---:|---:|---:|:---:|---:|---:|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for item in route["candidates"]:
            lines.append(
                f"| `{item['fingerprint']}` | {item['mean_daily_wait_minutes']:.6f} | "
                f"{item['wait_delta_vs_reference_minutes']:.6f} | "
                f"{item['wait_standard_error_minutes']:.6f} | "
                f"{'YES' if item['wait_one_se'] else 'NO'} | "
                f"{item['mean_daily_mismatch']:.8f} | "
                f"{item['mismatch_delta_vs_reference']:.8f} | "
                f"{item['mismatch_standard_error']:.8f} | "
                f"{'YES' if item['mismatch_one_se'] else 'NO'} | "
                f"{item['maximum_bucket_expected_wait_minutes']:.3f} | "
                f"{item['p90_bucket_expected_wait_minutes']:.3f} | "
                f"{item['fleet_required']} | {item['service_regime_count']} | "
                f"{item['sustained_headway_level_count']} | "
                f"{item['effective_palette_count']} | "
                f"{item['outbound_tail_headway_minutes']} | "
                f"{item['inbound_tail_headway_minutes']} |"
            )
        lines.extend(
            [
                "",
                _fingerprint_set_line(
                    "PASSENGER_EQUIVALENT_SET", route["PASSENGER_EQUIVALENT_SET"]
                ),
                "",
                _fingerprint_set_line(
                    "MATERIALITY_EQUIVALENT_OPERATING_FRONTIER",
                    route["MATERIALITY_EQUIVALENT_OPERATING_FRONTIER"],
                ),
                "",
            ]
        )
        if route_id == "10":
            lines.extend(["### Route 10 inbound 30/45-minute tail audit", ""])
            for tail in ("30", "45"):
                for item in route["inbound_tail_30_45_audit"][tail]:
                    lines.append(
                        f"- {tail}-minute `{item['fingerprint']}`: wait/mismatch "
                        f"1-SE={'YES' if item['WAIT_ONE_SE'] else 'NO'}/"
                        f"{'YES' if item['MISMATCH_ONE_SE'] else 'NO'}, "
                        f"passenger-set={'YES' if item['passenger_equivalent_set_member'] else 'NO'}, "
                        f"secondary={'YES' if item['secondary_frontier_member'] else 'NO'}, "
                        f"max/P90/tail-max={item['maximum_bucket_expected_wait_minutes']:.3f}/"
                        f"{item['p90_bucket_expected_wait_minutes']:.3f}/"
                        f"{item['tail_maximum_bucket_wait_minutes']:.3f}, "
                        f"fleet/sustained/regimes={item['fleet_required']}/"
                        f"{item['sustained_headway_level_count']}/"
                        f"{item['service_regime_count']}."
                    )
            lines.append("")
    human = payload["human_final_route_6"]
    lines.extend(["## Route 6 Human Final benchmark", ""])
    if not human["available"]:
        lines.append("Private Human Final workbook unavailable.")
    elif not human["accepted_sha_match"]:
        lines.append("Private Human Final workbook SHA does not match the accepted authority.")
    else:
        lines.extend(
            [
                f"Classification: `{human['classification']}`; Pareto eligible: **NO**.",
                f"Mean daily wait / mismatch: **{human['mean_daily_expected_wait_minutes']:.6f} / "
                f"{human['mean_daily_mismatch']:.8f}**.",
                f"Wait one-SE vs WAIT_REFERENCE: **{'YES' if human['WAIT_ONE_SE'] else 'NO'}** "
                f"(delta {human['wait_delta_vs_WAIT_REFERENCE_minutes'] * 60:.3f} sec/passenger, "
                f"SD {human['wait_paired_sample_sd_minutes'] * 60:.3f}, "
                f"SE {human['wait_standard_error_minutes'] * 60:.3f}, "
                f"n={human['eligible_daily_date_count']}).",
                f"Mismatch one-SE vs MISMATCH_REFERENCE: "
                f"**{'YES' if human['MISMATCH_ONE_SE'] else 'NO'}**.",
                "",
                "### Engine candidate versus Human Final paired wait",
                "",
                "| Fingerprint | Mean Δ sec/passenger | SD | SE | n | Engine better | Human better | Classification |",
                "|---|---:|---:|---:|---:|---:|---:|---|",
            ]
        )
        for item in human["engine_candidate_wait_comparisons"]:
            lines.append(
                f"| `{item['fingerprint']}` | "
                f"{item['mean_delta_seconds_per_passenger']:.3f} | "
                f"{item['paired_sample_sd_seconds_per_passenger']:.3f} | "
                f"{item['standard_error_seconds_per_passenger']:.3f} | "
                f"{item['eligible_paired_dates']} | "
                f"{item['candidate_better_percentage']:.1f}% | "
                f"{item['human_final_better_percentage']:.1f}% | "
                f"{item['one_se_classification']} |"
            )
        lines.extend(
            [
                "",
                "The one-SE convention is practical-equivalence evidence, not causal proof.",
            ]
        )
    lines.extend(["", "## Production change statement", ""])
    lines.extend(_production_change_lines(payload["production_change_statement"]))
    return "\n".join(lines)


def build_evidence(repo_root: Path) -> dict[str, Any]:
    if dataclasses.astuple(FROZEN_BUDGET) != (24, 512, 4, 24, 512):
        raise RuntimeError("search budgets changed")
    artifact_root = pr62_i._artifact_root(repo_root)
    prior_before = coordinator.verify_frozen_prior_artifacts_v1(artifact_root)
    accepted_i = json.loads(
        (repo_root / "docs/engine/evidence/PR62_I_WORST_BUCKET_PASSENGER_ACCESS.json").read_text(
            encoding="utf-8"
        )
    )
    workbooks = {
        route_id: repo_root / f"Engine_Input_MST_{route_id}_V3_MultiPeriod_Mar-Jul_2026.xlsx"
        for route_id in ("6", "10")
    }
    routes: dict[str, Any] = {}
    internal: dict[
        str, tuple[Any, list[dict[str, Any]], RawDailyDemandRouteV1, tuple[date, ...]]
    ] = {}
    for route_id in ("6", "10"):
        route, context, candidates = _evaluate_route(
            repo_root=repo_root,
            artifact_root=artifact_root,
            route_id=route_id,
            workbook_path=workbooks[route_id],
            accepted_i=accepted_i,
        )
        routes[route_id] = route
        raw_route, eligible_dates, _coverage = _daily_authority(
            repo_root=repo_root,
            artifact_root=artifact_root,
            route_id=route_id,
            workbook_path=workbooks[route_id],
        )
        internal[route_id] = (context, candidates, raw_route, eligible_dates)
    prior_after = coordinator.verify_frozen_prior_artifacts_v1(artifact_root)
    if prior_before != prior_after:
        raise RuntimeError("frozen prior artifacts changed during PR62-J evaluation")
    route6_context, route6_candidates, route6_raw, route6_dates = internal["6"]
    human = _human_final_evidence(
        repo_root=repo_root,
        context=route6_context,
        candidates=route6_candidates,
        route_evidence=routes["6"],
        raw_route=route6_raw,
        eligible_dates=route6_dates,
    )
    cross = _cross_route_classification(
        tuple(routes[route_id]["classification"] for route_id in ("6", "10"))
    )
    ready = all(
        routes[route_id]["recommended_for_recertification"] is not None for route_id in ("6", "10")
    )
    return {
        "profile": PROFILE,
        "I_commit_SHA": I_COMMIT_SHA,
        "daily_materiality_semantics": {
            "candidate_set": "exact current I Pareto timetables from one frozen-budget search per route",
            "evaluation": "post-search on immutable exact departures",
            "pairing": "candidate minus metric-specific reference on the same eligible complete date",
            "wait": "existing exact next-departure integration with that date's bucket demand",
            "mismatch": "existing sum of squared fixed-service-share minus daily-demand-share differences",
            "standard_deviation": "sample standard deviation of paired daily differences",
            "standard_error": "sample_sd / sqrt(n); exactly zero variance gives SE=0",
            "one_se_pass": (
                "mean paired delta <= standard error + 1e-12; when paired variance is "
                "exactly zero, only mean delta <= 0 passes"
            ),
            "joint_rule": "WAIT_ONE_SE and MISMATCH_ONE_SE must both pass",
            "maximum_bucket_in_statistical_test": False,
            "scalar_weight_added": False,
        },
        "secondary_operating_frontier": {
            "name": "MATERIALITY_EQUIVALENT_OPERATING_FRONTIER",
            "review_only": True,
            "dimensions": list(SECONDARY_OPERATING_DIMENSIONS),
            "scalar_weighted": False,
            "automatic_lexicographic_winner": False,
        },
        "routes": routes,
        "human_final_route_6": human,
        "cross_route_classification": cross,
        "READY_FOR_POST_HI_RECERTIFICATION": ready,
        "PR62_G_products_status": "FROZEN_HISTORICAL_PRE_H_PRODUCTS_NOT_REGENERATED",
        "deterministic_render": {},
        "production_change_statement": {
            "Coordinator search changed": "NO",
            "10-D Pareto changed": "NO",
            "Compiler changed": "NO",
            "Tail eligibility changed": "NO",
            "Rhythm semantics changed": "NO",
            "Queue changed": "NO",
            "Budgets changed": "NO",
            "Fleet validator changed": "NO",
            "Average-wait semantics changed": "NO",
            "Mismatch semantics changed": "NO",
            "Maximum-bucket semantics changed": "NO",
            "Settlement added": "NO",
            "Final XLSX regenerated": "NO",
            "Production selector added": "NO",
        },
    }


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
        raise RuntimeError("PR62-J evidence render is not byte-identical")
    if len(json_first) >= 1_000_000:
        raise RuntimeError("PR62-J JSON evidence exceeds preferred 1 MB limit")
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
