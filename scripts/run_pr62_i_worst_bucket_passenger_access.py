"""Generate compact PR62-I worst-bucket passenger-access evidence."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT / "src", _REPO_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from route6_boundary_settlement_experiment import (  # noqa: E402
    directional_metrics as reference_directional_metrics,
)
from route6_boundary_settlement_experiment import (  # noqa: E402
    exact_headway_runs,
    parse_route6_reference_workbook,
)
from route6_boundary_settlement_experiment import (  # noqa: E402
    pair_metrics as reference_pair_metrics,
)

import bus_schedule_engine.service_plan_coordinator as coordinator  # noqa: E402

PROFILE = "pr62_i_worst_bucket_passenger_access_v1"
H_COMMIT_SHA = "fb77fc57be7da7756485b528801d8bd24c956d53"
EXPECTED_H_PARETO_SIZES = {"6": 46, "10": 11}
EXPECTED_HUMAN_FINAL_SHA256 = "c2038b31c5a3f6a3ee2377ce2067542cc718a7d1907722efa3ab45a536bdd14a"
OUTPUT_JSON = Path("docs/engine/evidence/PR62_I_WORST_BUCKET_PASSENGER_ACCESS.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_I_WORST_BUCKET_PASSENGER_ACCESS.md")
FROZEN_BUDGET = coordinator.CoordinatorSearchBudgetV1(24, 512, 4, 24, 512)
H_DIMENSIONS = (
    "mismatch",
    "average_wait",
    "service_regimes",
    "sustained_levels",
    "maximum_frequency_jump",
    "total_frequency_variation",
    "moved_trips",
    "fleet",
    "total_excess_terminal_wait",
)
I_DIMENSIONS = (
    "mismatch",
    "average_wait",
    "max_wait",
    "service_regimes",
    "sustained_levels",
    "maximum_frequency_jump",
    "total_frequency_variation",
    "moved_trips",
    "fleet",
    "total_excess_terminal_wait",
)
PRODUCTION_I_DIMENSIONS = (
    "observed_demand_mismatch",
    "demand_weighted_expected_passenger_wait_minutes",
    "maximum_bucket_expected_wait_minutes",
    "actual_service_regime_count",
    "total_directional_sustained_headway_level_count",
    "max_frequency_jump",
    "total_frequency_variation",
    "moved_trips_vs_b",
    "fleet_required",
    "total_excess_terminal_wait",
)


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


def _equal_metrics() -> dict[str, float | int]:
    return {
        "mismatch": 1.0,
        "average_wait": 5.0,
        "service_regimes": 4,
        "sustained_levels": 3,
        "maximum_frequency_jump": 1.0,
        "total_frequency_variation": 1.0,
        "moved_trips": 1,
        "fleet": 4,
        "total_excess_terminal_wait": 1,
    }


def _synthetic_record(
    fingerprint: str, *, average_wait: float, max_wait: float, fleet: int
) -> dict[str, Any]:
    metrics = {
        **_equal_metrics(),
        "average_wait": average_wait,
        "max_wait": max_wait,
        "fleet": fleet,
        "p90_wait": max_wait,
    }
    return {"fingerprint": fingerprint, "metrics": metrics, "directions": {}}


def _dominates(
    left: Mapping[str, float | int],
    right: Mapping[str, float | int],
    dimensions: Sequence[str],
    *,
    epsilon: float = 1e-12,
) -> bool:
    left_values = tuple(float(left[key]) for key in dimensions)
    right_values = tuple(float(right[key]) for key in dimensions)
    return all(a <= b + epsilon for a, b in zip(left_values, right_values, strict=True)) and any(
        a < b - epsilon for a, b in zip(left_values, right_values, strict=True)
    )


def _frontier(
    records: Sequence[Mapping[str, Any]], dimensions: Sequence[str]
) -> list[Mapping[str, Any]]:
    return sorted(
        (
            item
            for item in records
            if not any(
                other["fingerprint"] != item["fingerprint"]
                and _dominates(other["metrics"], item["metrics"], dimensions)
                for other in records
            )
        ),
        key=lambda item: item["fingerprint"],
    )


def _compare_h_to_i_frontiers(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    h_frontier = _frontier(records, H_DIMENSIONS)
    i_frontier = _frontier(records, I_DIMENSIONS)
    i_fingerprints = {item["fingerprint"] for item in i_frontier}
    removed = []
    for item in h_frontier:
        if item["fingerprint"] in i_fingerprints:
            continue
        dominators = sorted(
            other["fingerprint"]
            for other in i_frontier
            if _dominates(other["metrics"], item["metrics"], I_DIMENSIONS)
        )
        removed.append({"fingerprint": item["fingerprint"], "dominated_by": dominators})
    return {
        "h_pareto_fingerprints": [item["fingerprint"] for item in h_frontier],
        "i_pareto_fingerprints": [item["fingerprint"] for item in i_frontier],
        "removed_only_by_maximum_bucket_wait": removed,
    }


def _review_roles(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    definitions = {
        "MINIMUM_AVERAGE_WAIT": "average_wait",
        "MINIMUM_MAXIMUM_BUCKET_WAIT": "max_wait",
        "MINIMUM_SUSTAINED_PALETTE": "sustained_levels",
        "MINIMUM_FLEET": "fleet",
        "MINIMUM_MISMATCH": "mismatch",
    }
    return {
        role: min(
            records,
            key=lambda item: (
                float(item["metrics"][metric]),
                item["fingerprint"],
            ),
        )
        for role, metric in definitions.items()
    }


def _direction_record(item: Any) -> dict[str, Any]:
    rhythm = item.metrics.rhythm_simplicity
    tail = item.metrics.tail_ordering
    return {
        "maximum_bucket_expected_wait_minutes": (item.metrics.maximum_bucket_expected_wait_minutes),
        "p90_bucket_expected_wait_minutes": item.metrics.p90_bucket_expected_wait_minutes,
        "tail_maximum_bucket_expected_wait_minutes": (
            item.metrics.tail_maximum_bucket_expected_wait_minutes
        ),
        "tail_headway_minutes": item.metrics.tail_headway_minutes,
        "tail_ordering_classification": tail.classification,
        "tail_slowest_margin_minutes": tail.tail_slowest_margin_minutes,
        "sustained_headway_levels": list(rhythm.sustained_headway_levels),
        "effective_headway_palette": list(rhythm.effective_headway_palette),
    }


def _pair_record(item: Any) -> dict[str, Any]:
    metrics = item.metrics
    return {
        "fingerprint": item.pair_fingerprint,
        "metrics": {
            "mismatch": metrics.observed_demand_mismatch,
            "average_wait": metrics.demand_weighted_expected_passenger_wait_minutes,
            "max_wait": metrics.maximum_bucket_expected_wait_minutes,
            "p90_wait": metrics.maximum_directional_p90_bucket_wait_minutes,
            "service_regimes": metrics.actual_service_regime_count,
            "sustained_levels": metrics.total_directional_sustained_headway_level_count,
            "effective_palette": metrics.total_directional_effective_palette_count,
            "maximum_frequency_jump": metrics.max_frequency_jump,
            "total_frequency_variation": metrics.total_frequency_variation,
            "moved_trips": metrics.moved_trips_vs_b,
            "fleet": metrics.fleet_required,
            "total_excess_terminal_wait": metrics.total_excess_terminal_wait,
        },
        "directions": {
            "outbound": _direction_record(item.outbound),
            "inbound": _direction_record(item.inbound),
        },
    }


@contextmanager
def _capture_feasible_pairs():
    original = coordinator.evaluate_operating_pair_v1
    captured: dict[str, Any] = {}

    def wrapped(outbound: Any, inbound: Any, *, context: Any):
        pair, feedback = original(outbound, inbound, context=context)
        if pair is not None:
            captured[pair.pair_fingerprint] = pair
        return pair, feedback

    coordinator.evaluate_operating_pair_v1 = wrapped
    try:
        yield captured
    finally:
        coordinator.evaluate_operating_pair_v1 = original


def _run_once(repo_root: Path, route_id: str, workbook: Path) -> tuple[Any, list[dict[str, Any]]]:
    context, seeds = coordinator.load_route_coordinator_inputs_v1(
        repo_root=repo_root,
        route_id=route_id,
        workbook_path=workbook,
    )
    with _capture_feasible_pairs() as captured:
        result = coordinator.search_route_service_plans_v1(
            context=context,
            seeds=seeds,
            budget=FROZEN_BUDGET,
        )
    records = [_pair_record(captured[key]) for key in sorted(captured)]
    production_i = sorted(item.pair_fingerprint for item in result.pareto_frontier)
    recomputed_i = [item["fingerprint"] for item in _frontier(records, I_DIMENSIONS)]
    if production_i != recomputed_i:
        raise RuntimeError(f"Route {route_id} production/recomputed I frontier mismatch")
    return (context, result), records


def _run_signature(result: Any, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    comparison = _compare_h_to_i_frontiers(records)
    return {
        "status": result.status,
        "statistics": dataclasses.asdict(result.statistics),
        "evaluated_state_fingerprints": list(result.evaluated_state_fingerprints),
        "feasible_pair_fingerprint": _sha256_bytes(_canonical_json_bytes(records)),
        "h_pareto_fingerprints": comparison["h_pareto_fingerprints"],
        "i_pareto_fingerprints": comparison["i_pareto_fingerprints"],
        "feedback_code_counts": dict(result.feedback_code_counts),
    }


def _range(records: Sequence[Mapping[str, Any]], key: str) -> list[float | int]:
    values = [item["metrics"][key] for item in records]
    return [min(values), max(values)]


def _tail_headway_range(records: Sequence[Mapping[str, Any]]) -> list[int]:
    values = [
        item["directions"][direction]["tail_headway_minutes"]
        for item in records
        for direction in ("outbound", "inbound")
    ]
    return [min(values), max(values)]


def _compact_candidate(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fingerprint": item["fingerprint"],
        **item["metrics"],
        "outbound": item["directions"]["outbound"],
        "inbound": item["directions"]["inbound"],
    }


def _average_access_tradeoffs(records: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    witnesses = []
    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            left_average = float(left["metrics"]["average_wait"])
            right_average = float(right["metrics"]["average_wait"])
            left_max = float(left["metrics"]["max_wait"])
            right_max = float(right["metrics"]["max_wait"])
            if (left_average < right_average and left_max > right_max) or (
                right_average < left_average and right_max > left_max
            ):
                witnesses.append(
                    {
                        "candidate_a": left["fingerprint"],
                        "candidate_b": right["fingerprint"],
                    }
                )
    return witnesses


def _route_evidence(
    route_id: str,
    result: Any,
    records: Sequence[Mapping[str, Any]],
    signature: Mapping[str, Any],
) -> dict[str, Any]:
    comparison = _compare_h_to_i_frontiers(records)
    h_records = [
        item for item in records if item["fingerprint"] in comparison["h_pareto_fingerprints"]
    ]
    i_records = [
        item for item in records if item["fingerprint"] in comparison["i_pareto_fingerprints"]
    ]
    if len(h_records) != EXPECTED_H_PARETO_SIZES[route_id]:
        raise RuntimeError(
            f"Route {route_id} H Pareto changed: {len(h_records)} != "
            f"{EXPECTED_H_PARETO_SIZES[route_id]}"
        )
    ranges = {}
    for label, key in (
        ("wait_minutes", "average_wait"),
        ("maximum_bucket_wait_minutes", "max_wait"),
        ("p90_bucket_wait_minutes", "p90_wait"),
        ("mismatch", "mismatch"),
        ("fleet", "fleet"),
        ("service_regime_count", "service_regimes"),
        ("sustained_headway_level_count", "sustained_levels"),
    ):
        ranges[label] = {"H": _range(h_records, key), "I": _range(i_records, key)}
    ranges["tail_headway_minutes"] = {
        "H": _tail_headway_range(h_records),
        "I": _tail_headway_range(i_records),
    }
    roles = {role: _compact_candidate(item) for role, item in _review_roles(i_records).items()}
    tradeoffs = _average_access_tradeoffs(i_records)
    evidence = {
        "route_id": route_id,
        "status": result.status,
        "search_budget": dataclasses.asdict(FROZEN_BUDGET),
        "search_statistics": dataclasses.asdict(result.statistics),
        "H_pareto_size": len(h_records),
        "I_pareto_size": len(i_records),
        "ranges": ranges,
        "H_pareto_removed_only_by_new_dimension": comparison["removed_only_by_maximum_bucket_wait"],
        "H_pareto_removed_only_by_new_dimension_count": len(
            comparison["removed_only_by_maximum_bucket_wait"]
        ),
        "review_roles": roles,
        "average_vs_access_tradeoff_count": len(tradeoffs),
        "average_vs_access_tradeoff_witnesses": tradeoffs[:10],
        "deterministic_signature": signature,
    }
    if route_id == "10":
        i_by_id = {item["fingerprint"]: item for item in i_records}
        audits = {}
        for tail_headway in (30, 45):
            matching = [
                item
                for item in h_records
                if item["directions"]["inbound"]["tail_headway_minutes"] == tail_headway
            ]
            audits[str(tail_headway)] = [
                {
                    **_compact_candidate(item),
                    "retained_in_I": item["fingerprint"] in i_by_id,
                    "dominated_by": next(
                        (
                            removed["dominated_by"]
                            for removed in comparison["removed_only_by_maximum_bucket_wait"]
                            if removed["fingerprint"] == item["fingerprint"]
                        ),
                        [],
                    ),
                }
                for item in matching
            ]
        evidence["inbound_tail_30_45_audit"] = audits
    return evidence


def _human_final_workbook(repo_root: Path) -> Path | None:
    workbook = repo_root / "private" / "Route_6_Current_ExternalAI_HumanFinal.xlsx"
    if workbook.is_file() and _sha256_path(workbook) == EXPECTED_HUMAN_FINAL_SHA256:
        return workbook
    return None


def _human_final(context: Any, workbook: Path | None) -> dict[str, Any] | None:
    if workbook is None:
        return None
    actual_sha = _sha256_path(workbook)
    if actual_sha != EXPECTED_HUMAN_FINAL_SHA256:
        return {
            "available": True,
            "accepted_sha_match": False,
            "sha256": actual_sha,
            "diagnostics": None,
        }
    parsed = parse_route6_reference_workbook(workbook)
    source = parsed["references"]["HUMAN_FINAL"]
    current = parsed["references"]["CURRENT"]
    directions = {}
    for direction in ("outbound", "inbound"):
        departures = source[direction]
        regularity = reference_directional_metrics(
            departures,
            demand_buckets=context.demand_buckets[direction],
            current_bucket_counts=coordinator._bucket_counts(
                current[direction], context.demand_buckets[direction]
            ),
        )
        average, maximum, per_bucket, mass = coordinator.expected_passenger_wait_metrics_v1(
            departures, context.demand_buckets[direction]
        )
        runs = exact_headway_runs(departures)
        sustained = tuple(item for item in runs if item.gap_count >= 2)
        single_gap = tuple(item for item in runs if item.gap_count == 1)
        weights: dict[int, int] = {}
        for run in sustained:
            weights[run.headway_minutes] = weights.get(run.headway_minutes, 0) + run.gap_count
        levels = tuple(sorted(weights))
        effective = coordinator._minimum_effective_headway_palette_v1(levels, weights)
        tail_run = runs[-1]
        tail_start = departures[tail_run.gap_start_index]
        p90, tail_maximum = coordinator.bucket_wait_access_diagnostics_v1(
            per_bucket_expected_wait_minutes=per_bucket,
            demand_buckets=context.demand_buckets[direction],
            active_span_start=departures[0],
            active_span_end=departures[-1],
            tail_support_start=tail_start,
            tail_support_end=departures[-1],
        )
        directions[direction] = {
            "observed_demand_mismatch": regularity["immutable_demand_mismatch"],
            "average_wait_minutes": average,
            "maximum_bucket_wait_minutes": maximum,
            "p90_bucket_wait_minutes": p90,
            "tail_maximum_bucket_wait_minutes": tail_maximum,
            "tail_headway_minutes": tail_run.headway_minutes,
            "active_demand_mass": mass,
            "actual_headway_run_count": len(runs),
            "sustained_headway_levels": list(levels),
            "single_gap_headway_levels": sorted({item.headway_minutes for item in single_gap}),
            "effective_headway_palette": list(effective),
        }
    fleet = reference_pair_metrics(
        source["outbound"],
        source["inbound"],
        outbound_metrics=reference_directional_metrics(
            source["outbound"], demand_buckets=context.demand_buckets["outbound"]
        ),
        inbound_metrics=reference_directional_metrics(
            source["inbound"], demand_buckets=context.demand_buckets["inbound"]
        ),
        runtime_minutes=context.runtime_minutes,
        minimum_layover_minutes=context.minimum_layover_minutes,
        fleet_ceiling=context.fleet_ceiling,
        candidate_id="HUMAN_FINAL",
    )
    masses = [directions[key]["active_demand_mass"] for key in ("outbound", "inbound")]
    waits = [directions[key]["average_wait_minutes"] for key in ("outbound", "inbound")]
    return {
        "available": True,
        "accepted_sha_match": True,
        "sha256": actual_sha,
        "post_search_benchmark_only": True,
        "pareto_eligible": False,
        "directions": directions,
        "pair": {
            "average_wait_minutes": sum(
                mass * wait for mass, wait in zip(masses, waits, strict=True)
            )
            / sum(masses),
            "maximum_bucket_wait_minutes": max(
                directions[key]["maximum_bucket_wait_minutes"] for key in ("outbound", "inbound")
            ),
            "maximum_directional_p90_bucket_wait_minutes": max(
                directions[key]["p90_bucket_wait_minutes"] for key in ("outbound", "inbound")
            ),
            "mismatch": sum(
                directions[key]["observed_demand_mismatch"] for key in ("outbound", "inbound")
            ),
            "fleet": fleet["fleet_required"],
        },
    }


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# PR62-I — Worst-bucket passenger access",
        "",
        f"H commit: `{payload['H_commit_SHA']}`.",
        "",
        "Demand-weighted expected passenger wait answers: **What does the average passenger experience?** Maximum bucket expected wait answers: **What is the worst scheduled passenger-access interval in the service day?** Low-demand periods, especially final tails, remain visible without a hard headway or wait threshold.",
        "",
        "Directional P90 uses deterministic nearest rank `ceil(0.90 × n)` over ordered non-null active bucket waits. Pair P90 is the maximum directional P90 and is diagnostic only. Tail maximum wait reuses existing exact bucket waits for active buckets overlapping final actual ServiceRegime support; no pseudo-bucket or `headway / 2` approximation is used.",
        "",
    ]
    for route_id in ("6", "10"):
        route = payload["routes"][route_id]
        lines.extend(
            [
                f"## Route {route_id} — H → I",
                "",
                f"H Pareto: **{route['H_pareto_size']}**; I Pareto: **{route['I_pareto_size']}**; H candidates removed only by maximum-bucket wait: **{route['H_pareto_removed_only_by_new_dimension_count']}**.",
                "",
                "| Metric | H range | I range |",
                "| --- | ---: | ---: |",
            ]
        )
        for label, values in route["ranges"].items():
            lines.append(f"| {label} | {values['H']} | {values['I']} |")
        lines.extend(
            [
                "",
                "| Role | Fingerprint | Avg wait | Max bucket | P90 | Mismatch | Fleet | Regimes | Sustained count | Sustained palettes OB / IB | Effective palettes OB / IB | OB tail / max | IB tail / max |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: | ---: |",
            ]
        )
        for role, item in route["review_roles"].items():
            lines.append(
                f"| {role} | `{item['fingerprint']}` | {item['average_wait']:.6f} | {item['max_wait']:.6f} | {item['p90_wait']:.6f} | {item['mismatch']:.8f} | {item['fleet']} | {item['service_regimes']} | {item['sustained_levels']} | {item['outbound']['sustained_headway_levels']} / {item['inbound']['sustained_headway_levels']} | {item['outbound']['effective_headway_palette']} / {item['inbound']['effective_headway_palette']} | {item['outbound']['tail_headway_minutes']} / {item['outbound']['tail_maximum_bucket_expected_wait_minutes']} | {item['inbound']['tail_headway_minutes']} / {item['inbound']['tail_maximum_bucket_expected_wait_minutes']} |"
            )
        lines.extend(
            [
                "",
                f"Average-vs-access tradeoff witnesses on I frontier: **{route['average_vs_access_tradeoff_count']}**.",
                "",
            ]
        )
        if route_id == "10":
            lines.extend(["### Route 10 inbound 30/45-minute tail audit", ""])
            for headway, items in route["inbound_tail_30_45_audit"].items():
                if not items:
                    lines.append(f"- Inbound tail {headway}: no H-Pareto candidate.")
                for item in items:
                    reason = (
                        "retained because its other objectives preserve a nondominated tradeoff"
                        if item["retained_in_I"]
                        else f"removed; dominated by {item['dominated_by']}"
                    )
                    lines.append(f"- `{item['fingerprint']}` inbound tail {headway}: {reason}.")
            lines.append("")
    human = payload["human_final_route_6"]
    lines.extend(["## Human Final Route 6", ""])
    if human is None:
        lines.append("Private Human Final workbook unavailable; diagnostics are null.")
    elif not human["accepted_sha_match"]:
        lines.append(
            "Private Human Final workbook is available but does not match the accepted SHA."
        )
    else:
        pair = human["pair"]
        lines.append(
            f"Accepted workbook SHA matched. Post-search benchmark only: average wait {pair['average_wait_minutes']:.6f}, max bucket {pair['maximum_bucket_wait_minutes']:.6f}, P90 {pair['maximum_directional_p90_bucket_wait_minutes']:.6f}, mismatch {pair['mismatch']:.8f}, fleet {pair['fleet']}."
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"Classification: **{payload['post_I_classification']}**.",
            f"Proceed to data-driven materiality selection: **{str(payload['proceed_to_data_driven_materiality_selection']).upper()}**.",
            "",
            "## Production change statement",
            "",
        ]
    )
    for key, value in payload["production_change_statement"].items():
        lines.append(f"- {key}: **{value}**")
    return "\n".join(lines) + "\n"


def _artifact_root(repo_root: Path) -> Path:
    required = (
        Path("outputs/demand_regime_model_selection/route_6_demand_regimes.json"),
        Path("outputs/demand_regime_model_selection/route_10_demand_regimes.json"),
        Path("outputs/demand_regime_trip_allocation/route_6_demand_regime_trip_allocations.json"),
        Path("outputs/demand_regime_trip_allocation/route_10_demand_regime_trip_allocations.json"),
        Path("outputs/end_tail_settlement_v3/end_tail_settlement_pilot_report.json"),
    )
    for candidate in (repo_root, repo_root / "bus-schedule-optimizer-main-run"):
        if all((candidate / path).is_file() for path in required):
            return candidate
    raise FileNotFoundError("restored frozen production inputs are unavailable")


def build_evidence(repo_root: Path) -> dict[str, Any]:
    if dataclasses.astuple(FROZEN_BUDGET) != (24, 512, 4, 24, 512):
        raise RuntimeError("search budgets changed")
    artifact_root = _artifact_root(repo_root)
    route_workbooks = {
        "6": repo_root / "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx",
        "10": repo_root / "Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    }
    prior_before = coordinator.verify_frozen_prior_artifacts_v1(artifact_root)
    routes = {}
    route6_context = None
    for route_id in ("6", "10"):
        first, first_records = _run_once(artifact_root, route_id, route_workbooks[route_id])
        second, second_records = _run_once(artifact_root, route_id, route_workbooks[route_id])
        first_context, first_result = first
        _second_context, second_result = second
        first_signature = _run_signature(first_result, first_records)
        second_signature = _run_signature(second_result, second_records)
        if _canonical_json_bytes(first_signature) != _canonical_json_bytes(second_signature):
            raise RuntimeError(f"Route {route_id} deterministic replay mismatch")
        routes[route_id] = _route_evidence(route_id, first_result, first_records, first_signature)
        if route_id == "6":
            route6_context = first_context
    prior_after = coordinator.verify_frozen_prior_artifacts_v1(artifact_root)
    if prior_before != prior_after:
        raise RuntimeError("frozen prior artifacts changed during PR62-I rerun")
    material = any(
        route["H_pareto_size"] != route["I_pareto_size"]
        or route["H_pareto_removed_only_by_new_dimension_count"] > 0
        or route["average_vs_access_tradeoff_count"] > 0
        for route in routes.values()
    )
    classification = (
        "WORST_BUCKET_WAIT_MATERIAL_TO_FRONTIER" if material else "WORST_BUCKET_WAIT_REDUNDANT"
    )
    assert route6_context is not None
    payload = {
        "profile": PROFILE,
        "H_commit_SHA": H_COMMIT_SHA,
        "metric_semantics": {
            "average_wait_question": "What does the average passenger experience?",
            "maximum_bucket_wait_question": (
                "What is the worst scheduled passenger-access interval in the service day?"
            ),
            "maximum_bucket_wait": (
                "max of outbound/inbound existing exact active-bucket maximum waits"
            ),
            "directional_p90": (
                "nearest rank ceil(0.90*n) over ordered non-null active bucket waits"
            ),
            "pair_p90": "max(outbound directional P90, inbound directional P90)",
            "tail_maximum_wait": (
                "maximum existing exact wait for active immutable-demand buckets overlapping "
                "final actual ServiceRegime support; null when none overlap"
            ),
            "hard_headway_or_wait_threshold_added": False,
        },
        "pair_pareto_change": {
            "dimension_count": 10,
            "dimensions": list(PRODUCTION_I_DIMENSIONS),
            "only_new_dimension": "maximum_bucket_expected_wait_minutes",
            "scalar_weight_added": False,
            "p90_in_pareto": False,
            "tail_wait_in_pareto": False,
        },
        "routes": routes,
        "human_final_route_6": _human_final(
            route6_context,
            _human_final_workbook(repo_root),
        ),
        "deterministic_render": {},
        "post_I_classification": classification,
        "proceed_to_data_driven_materiality_selection": material,
        "PR62_G_PRODUCT_REQUIRES_RECERTIFICATION_AFTER_H": True,
        "production_change_statement": {
            "Production Pareto semantics changed": "YES",
            "Maximum bucket wait added to Pareto": "YES",
            "Tail eligibility changed from H": "NO",
            "Rhythm semantics changed from H": "NO",
            "Compiler changed": "NO",
            "Queue changed": "NO",
            "Search budgets changed": "NO",
            "Average passenger wait changed": "NO",
            "Demand mismatch changed": "NO",
            "Fleet validator changed": "NO",
            "Protection changed": "NO",
            "Settlement added": "NO",
            "Final XLSX regenerated": "NO",
        },
    }
    return payload


def _write_evidence(repo_root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    preliminary_json = _canonical_json_bytes(payload)
    preliminary_markdown = _markdown(payload).encode("utf-8")
    payload["deterministic_render"] = {
        "pre_metadata_json_sha256": _sha256_bytes(preliminary_json),
        "pre_metadata_markdown_sha256": _sha256_bytes(preliminary_markdown),
        "rendered_twice_byte_identical": True,
    }
    json_first = _canonical_json_bytes(payload)
    json_second = _canonical_json_bytes(payload)
    markdown_first = _markdown(payload).encode("utf-8")
    markdown_second = _markdown(payload).encode("utf-8")
    if json_first != json_second or markdown_first != markdown_second:
        raise RuntimeError("evidence render is not byte-identical")
    json_path = repo_root / OUTPUT_JSON
    markdown_path = repo_root / OUTPUT_MARKDOWN
    json_path.write_bytes(json_first)
    markdown_path.write_bytes(markdown_first)
    if json_path.stat().st_size >= 1_000_000:
        raise RuntimeError("PR62-I JSON evidence exceeds preferred 1 MB limit")
    return {
        "json": str(json_path),
        "json_bytes": len(json_first),
        "json_sha256": _sha256_bytes(json_first),
        "markdown": str(markdown_path),
        "markdown_sha256": _sha256_bytes(markdown_first),
        "classification": payload["post_I_classification"],
    }


def _refresh_human_final_only(repo_root: Path) -> dict[str, Any]:
    json_path = repo_root / OUTPUT_JSON
    if not json_path.is_file():
        raise FileNotFoundError(
            "existing PR62-I evidence is required for a diagnostic-only refresh"
        )
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    artifact_root = _artifact_root(repo_root)
    context, _seeds = coordinator.load_route_coordinator_inputs_v1(
        repo_root=artifact_root,
        route_id="6",
        workbook_path=repo_root / "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    )
    payload["human_final_route_6"] = _human_final(
        context,
        _human_final_workbook(repo_root),
    )
    payload["pair_pareto_change"]["dimensions"] = list(PRODUCTION_I_DIMENSIONS)
    payload["pair_pareto_change"]["only_new_dimension"] = "maximum_bucket_expected_wait_minutes"
    payload["deterministic_render"] = {}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    parser.add_argument("--refresh-human-final-only", action="store_true")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    payload = (
        _refresh_human_final_only(repo_root)
        if args.refresh_human_final_only
        else build_evidence(repo_root)
    )
    print(json.dumps(_write_evidence(repo_root, payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
