"""Generate PR62-M review-only discrete demand-fit materiality evidence."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
for _path in (_REPO_ROOT / "src", _REPO_ROOT / "scripts"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import run_pr62_i_worst_bucket_passenger_access as pr62_i  # noqa: E402
import run_pr62_l_domain_priority_selector as pr62_l  # noqa: E402

from bus_schedule_engine import service_plan_coordinator as coordinator  # noqa: E402
from bus_schedule_engine.contracts_v1.operational_selection_policy import (  # noqa: E402
    NUMERICAL_EPSILON,
)

PROFILE = "discrete_demand_fit_materiality_v1"
L_COMMIT_SHA = "b3c7127db283a96ab057400ddc3ac502673c2ee1"
EXPECTED_ACCESS_SAFE_SIZES = {"6": 41, "10": 7}
L_SELECTED = {
    "6": "ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b",
    "10": "bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c",
}
EXPECTED_NEXT_SSE = {
    "6": "1ee89f8429eb087e4f9663975ae893fb8e636d0eadd617783cbc8428847192e8",
    "10": "9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0",
}
OUTPUT_JSON = Path("docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.md")


def _directional_allocation_diagnostic(
    *,
    service_counts: Sequence[int],
    demand_shares: Sequence[float],
    service_shares: Sequence[float],
) -> dict[str, float | int]:
    """Return review-only directional allocation diagnostics."""
    counts = tuple(service_counts)
    demand = tuple(float(value) for value in demand_shares)
    service = tuple(float(value) for value in service_shares)
    if not counts or len(counts) != len(demand) or len(counts) != len(service):
        raise ValueError("bucket metrics must be non-empty and have equal lengths")
    if any(value < 0 or int(value) != value for value in counts):
        raise ValueError("bucket service counts must be non-negative integers")
    total_trips = sum(counts)
    if total_trips <= 0:
        raise ValueError("directional exact trip total must be positive")
    if abs(sum(demand) - 1.0) > NUMERICAL_EPSILON:
        raise ValueError("bucket demand shares must sum to one")
    if abs(sum(service) - 1.0) > NUMERICAL_EPSILON:
        raise ValueError("bucket service shares must sum to one")
    derived_service = tuple(value / total_trips for value in counts)
    if any(
        abs(actual - derived) > NUMERICAL_EPSILON
        for actual, derived in zip(service, derived_service, strict=True)
    ):
        raise ValueError("service shares do not match service counts")
    allocation_tv = 0.5 * sum(
        abs(actual - observed) for actual, observed in zip(service, demand, strict=True)
    )
    return {
        "directional_total_trips": total_trips,
        "directional_allocation_tv": allocation_tv,
        "directional_trip_equivalent_error": total_trips * allocation_tv,
    }


def _pair_trip_equivalent_error(outbound: float, inbound: float) -> float:
    return float(outbound) + float(inbound)


def _allocation_move_distance_trips(left_counts: Sequence[int], right_counts: Sequence[int]) -> int:
    left = tuple(left_counts)
    right = tuple(right_counts)
    if len(left) != len(right):
        raise ValueError("allocation vectors must have equal lengths")
    if sum(left) != sum(right):
        raise ValueError("allocation distance requires equal directional trip totals")
    l1_distance = sum(
        abs(left_value - right_value) for left_value, right_value in zip(left, right, strict=True)
    )
    if l1_distance % 2:
        raise ValueError("allocation distance must be an integral trip count")
    return l1_distance // 2


def _metric_ordering_audit(
    candidates: Sequence[Mapping[str, Any]],
    *,
    benchmark: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not candidates:
        raise ValueError("metric ordering audit requires candidates")
    sse_order = sorted(
        candidates,
        key=lambda item: (float(item["observed_demand_mismatch"]), str(item["fingerprint"])),
    )
    te_order = sorted(
        candidates,
        key=lambda item: (float(item["pair_trip_equivalent_error"]), str(item["fingerprint"])),
    )
    sse_ranks = {str(item["fingerprint"]): rank for rank, item in enumerate(sse_order, start=1)}
    te_ranks = {str(item["fingerprint"]): rank for rank, item in enumerate(te_order, start=1)}
    disagreements = 0
    for index, left in enumerate(candidates):
        for right in candidates[index + 1 :]:
            sse_delta = float(left["observed_demand_mismatch"]) - float(
                right["observed_demand_mismatch"]
            )
            te_delta = float(left["pair_trip_equivalent_error"]) - float(
                right["pair_trip_equivalent_error"]
            )
            if abs(sse_delta) <= NUMERICAL_EPSILON or abs(te_delta) <= NUMERICAL_EPSILON:
                continue
            if (sse_delta < 0) != (te_delta < 0):
                disagreements += 1

    def ranked_record(item: Mapping[str, Any]) -> dict[str, Any]:
        fingerprint = str(item["fingerprint"])
        return {
            "fingerprint": fingerprint,
            "observed_demand_mismatch": float(item["observed_demand_mismatch"]),
            "pair_trip_equivalent_error": float(item["pair_trip_equivalent_error"]),
            "SSE_rank": sse_ranks[fingerprint],
            "trip_equivalent_rank": te_ranks[fingerprint],
        }

    result: dict[str, Any] = {
        "production_metric": "observed_demand_mismatch",
        "review_metric_only": "pair_trip_equivalent_error",
        "SSE_BEST": ranked_record(sse_order[0]),
        "TV_BEST": ranked_record(te_order[0]),
        "same_best_candidate": (
            str(sse_order[0]["fingerprint"]) == str(te_order[0]["fingerprint"])
        ),
        "top_5_by_SSE": [ranked_record(item) for item in sse_order[:5]],
        "top_5_by_trip_equivalent": [ranked_record(item) for item in te_order[:5]],
        "pairwise_ranking_disagreement_count": disagreements,
    }
    if benchmark is not None:
        result["benchmark"] = {**dict(benchmark), "selection_eligible": False}
    return result


def _breakpoint_frontier(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    best_te = min(float(item["pair_trip_equivalent_error"]) for item in candidates)
    observed = sorted(
        max(0.0, float(item["pair_trip_equivalent_error"]) - best_te) for item in candidates
    )
    breakpoints: list[float] = []
    for value in observed:
        if not breakpoints or abs(value - breakpoints[-1]) > NUMERICAL_EPSILON:
            breakpoints.append(value)
    path: list[dict[str, Any]] = []
    previous: str | None = None
    for delta in breakpoints:
        envelope = [
            item
            for item in candidates
            if float(item["pair_trip_equivalent_error"]) <= best_te + delta + NUMERICAL_EPSILON
        ]
        preferred = min(
            envelope,
            key=lambda item: (
                tuple(item["rhythm_simplicity_tuple"]),
                tuple(item["fleet_efficiency_tuple"]),
                str(item["fingerprint"]),
            ),
        )
        fingerprint = str(preferred["fingerprint"])
        if fingerprint == previous:
            continue
        path.append(
            {
                "delta_trip_equivalent": delta,
                "envelope_candidate_count": len(envelope),
                "preferred_fingerprint": fingerprint,
                "preferred_rhythm_simplicity_tuple": list(preferred["rhythm_simplicity_tuple"]),
                "preferred_fleet_efficiency_tuple": list(preferred["fleet_efficiency_tuple"]),
            }
        )
        previous = fingerprint
    return path


def _one_trip_quantum_diagnostic(
    candidates: Sequence[Mapping[str, Any]], *, selected_fingerprint: str
) -> dict[str, Any]:
    if not candidates:
        raise ValueError("one-trip diagnostic requires candidates")
    selected = next(item for item in candidates if str(item["fingerprint"]) == selected_fingerprint)
    selected_rhythm = tuple(selected["rhythm_simplicity_tuple"])
    tv_best = min(float(item["pair_trip_equivalent_error"]) for item in candidates)
    simpler = [
        item for item in candidates if tuple(item["rhythm_simplicity_tuple"]) < selected_rhythm
    ]
    deltas = sorted(
        max(0.0, float(item["pair_trip_equivalent_error"]) - tv_best) for item in simpler
    )
    minimum_delta = deltas[0] if deltas else None
    first_above = next((value for value in deltas if value > 1.0 + NUMERICAL_EPSILON), None)
    return {
        "sub_one_trip_simpler_exists": any(value < 1.0 - NUMERICAL_EPSILON for value in deltas),
        "at_or_below_one_trip_simpler_exists": any(
            value <= 1.0 + NUMERICAL_EPSILON for value in deltas
        ),
        "minimum_delta_to_simpler_candidate": minimum_delta,
        "first_breakpoint_above_one_trip": first_above,
        "one_trip_is_diagnostic_not_policy": True,
        "production_policy_changed": False,
    }


def _route_classification(
    *, metric_ordering_conflict: bool, minimum_simpler_delta: float | None
) -> str:
    if metric_ordering_conflict:
        return "DEMAND_FIT_METRIC_ORDERING_CONFLICT"
    if minimum_simpler_delta is None:
        return "NO_SIMPLER_ACCESS_SAFE_ALTERNATIVE"
    if minimum_simpler_delta < 1.0 - NUMERICAL_EPSILON:
        return "SUB_ONE_TRIP_EQUIVALENT_SIMPLICITY_TRADEOFF"
    return "AT_LEAST_ONE_TRIP_EQUIVALENT_REQUIRED_FOR_SIMPLICITY"


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _rhythm_tuple(item: Mapping[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(item["sustained_headway_level_count"]),
        int(item["actual_service_regime_count"]),
        int(item["effective_palette_count"]),
        int(item["single_gap_regime_count"]),
    )


def _fleet_tuple(item: Mapping[str, Any]) -> tuple[int, int, int]:
    return (
        int(item["fleet_required"]),
        int(item["total_excess_terminal_wait"]),
        int(item["max_excess_terminal_wait"]),
    )


def _pair_allocation_move_distance(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
    return sum(
        _allocation_move_distance_trips(
            left["directions"][direction]["bucket_service_counts"],
            right["directions"][direction]["bucket_service_counts"],
        )
        for direction in ("outbound", "inbound")
    )


def _calibration_candidate(raw: Any, compact: Mapping[str, Any]) -> dict[str, Any]:
    directions: dict[str, Any] = {}
    for direction in ("outbound", "inbound"):
        metrics = getattr(raw, direction).metrics
        diagnostic = _directional_allocation_diagnostic(
            service_counts=metrics.bucket_service_counts,
            demand_shares=metrics.bucket_demand_shares,
            service_shares=metrics.bucket_service_shares,
        )
        directions[direction] = {
            **diagnostic,
            "bucket_service_counts": list(metrics.bucket_service_counts),
            "bucket_demand_shares": list(metrics.bucket_demand_shares),
            "bucket_service_shares": list(metrics.bucket_service_shares),
        }
    pair_te = _pair_trip_equivalent_error(
        float(directions["outbound"]["directional_trip_equivalent_error"]),
        float(directions["inbound"]["directional_trip_equivalent_error"]),
    )
    total_trips = sum(
        int(directions[direction]["directional_total_trips"])
        for direction in ("outbound", "inbound")
    )
    record = {
        "fingerprint": str(compact["fingerprint"]),
        "observed_demand_mismatch": float(compact["mismatch"]),
        "pair_trip_equivalent_error": pair_te,
        "pair_normalized_allocation_tv": pair_te / total_trips,
        "directions": directions,
        "average_wait_minutes": float(compact["average_wait_minutes"]),
        "directional_maximum_bucket_wait_minutes": dict(
            compact["directional_maximum_bucket_wait_minutes"]
        ),
        "fleet_required": int(compact["fleet_required"]),
        "total_excess_terminal_wait": int(compact["total_excess_terminal_wait"]),
        "max_excess_terminal_wait": int(compact["max_excess_terminal_wait"]),
        "actual_service_regime_count": int(compact["actual_service_regime_count"]),
        "sustained_headway_level_count": int(compact["sustained_headway_level_count"]),
        "effective_palette_count": int(compact["effective_palette_count"]),
        "single_gap_regime_count": int(compact["single_gap_regime_count"]),
        "tail_headways": dict(compact["tail_headways"]),
    }
    record["rhythm_simplicity_tuple"] = _rhythm_tuple(record)
    record["fleet_efficiency_tuple"] = _fleet_tuple(record)
    return record


def _comparison_to_selected(
    candidate: Mapping[str, Any], selected: Mapping[str, Any], *, tv_best_te: float
) -> dict[str, Any]:
    return {
        "fingerprint": candidate["fingerprint"],
        "delta_trip_equivalent_vs_tv_best": (
            float(candidate["pair_trip_equivalent_error"]) - tv_best_te
        ),
        "allocation_move_distance_from_L_selected": int(
            candidate["allocation_move_distance_vs_L_selected"]
        ),
        "SSE_mismatch_delta_vs_L_selected": (
            float(candidate["observed_demand_mismatch"])
            - float(selected["observed_demand_mismatch"])
        ),
        "average_wait_delta_minutes_vs_L_selected": (
            float(candidate["average_wait_minutes"]) - float(selected["average_wait_minutes"])
        ),
        "directional_max_access_delta_minutes_vs_L_selected": {
            direction: (
                float(candidate["directional_maximum_bucket_wait_minutes"][direction])
                - float(selected["directional_maximum_bucket_wait_minutes"][direction])
            )
            for direction in ("outbound", "inbound")
        },
        "fleet_delta_vs_L_selected": (
            int(candidate["fleet_required"]) - int(selected["fleet_required"])
        ),
        "rhythm_tuple_delta_vs_L_selected": [
            candidate_value - selected_value
            for candidate_value, selected_value in zip(
                candidate["rhythm_simplicity_tuple"],
                selected["rhythm_simplicity_tuple"],
                strict=True,
            )
        ],
    }


def _focused_candidates(
    candidates: Sequence[Mapping[str, Any]], *, selected_fingerprint: str
) -> tuple[list[dict[str, Any]], dict[str, Mapping[str, Any]]]:
    by_fingerprint = {str(item["fingerprint"]): item for item in candidates}
    selected = by_fingerprint[selected_fingerprint]
    definitions: tuple[tuple[str, Mapping[str, Any]], ...] = (
        ("L_SELECTED", selected),
        (
            "NEXT_BEST_SSE_MISMATCH",
            min(
                (item for item in candidates if item["fingerprint"] != selected_fingerprint),
                key=lambda item: (
                    float(item["observed_demand_mismatch"]),
                    str(item["fingerprint"]),
                ),
            ),
        ),
        (
            "MINIMUM_SUSTAINED_PALETTE",
            min(candidates, key=lambda item: (_rhythm_tuple(item), str(item["fingerprint"]))),
        ),
        (
            "MINIMUM_FLEET",
            min(candidates, key=lambda item: (_fleet_tuple(item), str(item["fingerprint"]))),
        ),
        (
            "MINIMUM_AVERAGE_WAIT",
            min(
                candidates,
                key=lambda item: (float(item["average_wait_minutes"]), str(item["fingerprint"])),
            ),
        ),
    )
    rows: dict[str, dict[str, Any]] = {}
    roles: dict[str, Mapping[str, Any]] = {}
    for role, item in definitions:
        roles[role] = item
        fingerprint = str(item["fingerprint"])
        if fingerprint not in rows:
            rows[fingerprint] = {
                key: item[key]
                for key in (
                    "fingerprint",
                    "observed_demand_mismatch",
                    "pair_trip_equivalent_error",
                    "pair_normalized_allocation_tv",
                    "delta_trip_equivalent_vs_tv_best",
                    "delta_trip_equivalent_vs_L_selected",
                    "allocation_move_distance_vs_L_selected",
                    "average_wait_minutes",
                    "directional_maximum_bucket_wait_minutes",
                    "fleet_required",
                    "rhythm_simplicity_tuple",
                    "tail_headways",
                    "directions",
                )
            }
            rows[fingerprint]["roles"] = []
        rows[fingerprint]["roles"].append(role)
    return list(rows.values()), roles


def _human_final_calibration(
    *, repo_root: Path, context: Any, selected: Mapping[str, Any]
) -> dict[str, Any]:
    comparison = pr62_l._human_final_comparison(
        repo_root=repo_root,
        context=context,
        selected=None,
    )
    base = {
        "available": bool(comparison.get("available")),
        "accepted_sha_match": bool(comparison.get("accepted_sha_match")),
        "classification": "POST_SEARCH_EXPERT_BENCHMARK",
        "selection_eligible": False,
    }
    if not comparison.get("accepted_sha_match"):
        return base
    workbook = pr62_i._human_final_workbook(repo_root)
    if workbook is None:
        return base
    source = pr62_i.parse_route6_reference_workbook(workbook)["references"]["HUMAN_FINAL"]
    directions: dict[str, Any] = {}
    for direction in ("outbound", "inbound"):
        departures = source[direction]
        demand_buckets = context.demand_buckets[direction]
        counts = coordinator._bucket_counts(departures, demand_buckets)
        total_demand = sum(float(bucket.observed_demand) for bucket in demand_buckets)
        demand_shares = tuple(
            float(bucket.observed_demand) / total_demand for bucket in demand_buckets
        )
        service_shares = tuple(count / len(departures) for count in counts)
        directions[direction] = {
            **_directional_allocation_diagnostic(
                service_counts=counts,
                demand_shares=demand_shares,
                service_shares=service_shares,
            ),
            "bucket_service_counts": list(counts),
            "bucket_demand_shares": list(demand_shares),
            "bucket_service_shares": list(service_shares),
        }
    pair_te = _pair_trip_equivalent_error(
        float(directions["outbound"]["directional_trip_equivalent_error"]),
        float(directions["inbound"]["directional_trip_equivalent_error"]),
    )
    total_trips = sum(len(source[direction]) for direction in ("outbound", "inbound"))
    human = {
        **base,
        "sha256": comparison["sha256"],
        "fingerprint": "HUMAN_FINAL",
        "observed_demand_mismatch": float(comparison["pair"]["mismatch"]),
        "pair_trip_equivalent_error": pair_te,
        "pair_normalized_allocation_tv": pair_te / total_trips,
        "directions": directions,
        "average_wait_minutes": float(comparison["pair"]["average_wait_minutes"]),
        "directional_maximum_bucket_wait_minutes": {
            direction: float(comparison["directions"][direction]["maximum_bucket_wait_minutes"])
            for direction in ("outbound", "inbound")
        },
        "fleet_required": int(comparison["pair"]["fleet"]),
        "actual_service_regime_count": int(comparison["actual_service_regime_count"]),
        "sustained_headway_level_count": int(comparison["sustained_headway_level_count"]),
        "effective_palette_count": int(comparison["effective_palette_count"]),
        "tail_headways": {
            direction: int(comparison["directions"][direction]["tail_headway_minutes"])
            for direction in ("outbound", "inbound")
        },
    }
    human["allocation_move_distance_vs_L_selected"] = _pair_allocation_move_distance(
        human, selected
    )
    human["selected_minus_human_final"] = {
        "pair_trip_equivalent_error": (float(selected["pair_trip_equivalent_error"]) - pair_te),
        "observed_demand_mismatch": (
            float(selected["observed_demand_mismatch"]) - float(human["observed_demand_mismatch"])
        ),
        "allocation_move_distance_trips": human["allocation_move_distance_vs_L_selected"],
        "sustained_headway_level_count": (
            int(selected["sustained_headway_level_count"])
            - int(human["sustained_headway_level_count"])
        ),
        "effective_palette_count": (
            int(selected["effective_palette_count"]) - int(human["effective_palette_count"])
        ),
        "fleet_required": int(selected["fleet_required"]) - int(human["fleet_required"]),
        "average_wait_minutes": (
            float(selected["average_wait_minutes"]) - float(human["average_wait_minutes"])
        ),
    }
    return human


def _evaluate_route(
    *,
    repo_root: Path,
    artifact_root: Path,
    route_id: str,
    accepted_i: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    l_route, internals = pr62_l._evaluate_route(
        repo_root=repo_root,
        artifact_root=artifact_root,
        route_id=route_id,
        accepted_i=accepted_i,
    )
    if l_route["stage_counts"]["access_safe"] != EXPECTED_ACCESS_SAFE_SIZES[route_id]:
        raise RuntimeError(f"route {route_id} L access-safe evidence drift")
    if l_route["selection_result"]["selected_pair_fingerprint"] != L_SELECTED[route_id]:
        raise RuntimeError(f"route {route_id} L selected fingerprint changed")
    compact_by_fingerprint = {
        str(item["fingerprint"]): item for item in l_route["access_safe_candidate_diagnostics"]
    }
    raw_access_safe = [
        item for item in internals["frontier"] if item.pair_fingerprint in compact_by_fingerprint
    ]
    candidates = [
        _calibration_candidate(item, compact_by_fingerprint[item.pair_fingerprint])
        for item in raw_access_safe
    ]
    candidates.sort(key=lambda item: str(item["fingerprint"]))
    audit = _metric_ordering_audit(candidates)
    selected = next(item for item in candidates if item["fingerprint"] == L_SELECTED[route_id])
    tv_best = next(
        item for item in candidates if item["fingerprint"] == audit["TV_BEST"]["fingerprint"]
    )
    tv_best_te = float(tv_best["pair_trip_equivalent_error"])
    sse_order = sorted(
        candidates,
        key=lambda item: (float(item["observed_demand_mismatch"]), str(item["fingerprint"])),
    )
    te_order = sorted(
        candidates,
        key=lambda item: (float(item["pair_trip_equivalent_error"]), str(item["fingerprint"])),
    )
    sse_ranks = {item["fingerprint"]: rank for rank, item in enumerate(sse_order, start=1)}
    te_ranks = {item["fingerprint"]: rank for rank, item in enumerate(te_order, start=1)}
    for item in candidates:
        item["SSE_rank"] = sse_ranks[item["fingerprint"]]
        item["trip_equivalent_rank"] = te_ranks[item["fingerprint"]]
        item["delta_trip_equivalent_vs_tv_best"] = (
            float(item["pair_trip_equivalent_error"]) - tv_best_te
        )
        item["delta_trip_equivalent_vs_L_selected"] = float(
            item["pair_trip_equivalent_error"]
        ) - float(selected["pair_trip_equivalent_error"])
        item["allocation_move_distance_vs_L_selected"] = _pair_allocation_move_distance(
            item, selected
        )
        item["allocation_move_distance_vs_TV_BEST"] = _pair_allocation_move_distance(item, tv_best)
    focused, roles = _focused_candidates(candidates, selected_fingerprint=L_SELECTED[route_id])
    if roles["NEXT_BEST_SSE_MISMATCH"]["fingerprint"] != EXPECTED_NEXT_SSE[route_id]:
        raise RuntimeError(f"route {route_id} next-best SSE fingerprint changed")
    simpler = [
        item
        for item in candidates
        if tuple(item["rhythm_simplicity_tuple"]) < tuple(selected["rhythm_simplicity_tuple"])
    ]
    minimum_simpler = min(
        simpler,
        default=None,
        key=lambda item: (
            float(item["delta_trip_equivalent_vs_tv_best"]),
            str(item["fingerprint"]),
        ),
    )
    minimum_simpler_delta = (
        None
        if minimum_simpler is None
        else float(minimum_simpler["delta_trip_equivalent_vs_tv_best"])
    )
    route_classification = _route_classification(
        metric_ordering_conflict=not bool(audit["same_best_candidate"]),
        minimum_simpler_delta=minimum_simpler_delta,
    )
    one_trip = _one_trip_quantum_diagnostic(candidates, selected_fingerprint=L_SELECTED[route_id])
    breakpoint_path = _breakpoint_frontier(candidates)
    one_trip["first_breakpoint_above_one_trip"] = next(
        (
            float(row["delta_trip_equivalent"])
            for row in breakpoint_path
            if float(row["delta_trip_equivalent"]) > 1.0 + NUMERICAL_EPSILON
        ),
        None,
    )
    specified = {
        role: _comparison_to_selected(item, selected, tv_best_te=tv_best_te)
        for role, item in roles.items()
        if role in {"MINIMUM_SUSTAINED_PALETTE", "MINIMUM_FLEET", "NEXT_BEST_SSE_MISMATCH"}
    }
    extreme_tails = []
    if route_id == "10":
        for tail in (30, 45, 48, 54):
            for row in l_route["inbound_extreme_tail_audit"][str(tail)]:
                extreme_tails.append(
                    {
                        **row,
                        "materiality_classification": ("ACCESS_EXCLUDED_NOT_MATERIALITY_EVALUATED"),
                    }
                )
    route_payload = {
        "route_id": route_id,
        "stage_counts": {
            "I_Pareto": l_route["stage_counts"]["I_Pareto"],
            "hard_feasible": l_route["stage_counts"]["hard_feasible"],
            "access_safe": l_route["stage_counts"]["access_safe"],
        },
        "L_selected_fingerprint": L_SELECTED[route_id],
        "metric_ordering_audit": audit,
        "access_safe_candidates": candidates,
        "focused_comparisons": focused,
        "minimum_trip_equivalent_concession_for_simpler_rhythm": (
            None
            if minimum_simpler is None
            else _comparison_to_selected(minimum_simpler, selected, tv_best_te=tv_best_te)
        ),
        "specified_alternative_materiality": specified,
        "trip_equivalent_breakpoint_path": breakpoint_path,
        "one_trip_quantum_diagnostic": one_trip,
        "classification": route_classification,
        "extreme_tail_candidates": extreme_tails,
    }
    return route_payload, {**internals, "selected_calibration": selected}


def build_evidence(repo_root: Path) -> dict[str, Any]:
    if dataclasses.astuple(pr62_l.FROZEN_BUDGET) != (24, 512, 4, 24, 512):
        raise RuntimeError("search budgets changed")
    accepted_l = json.loads((repo_root / pr62_l.OUTPUT_JSON).read_text(encoding="utf-8"))
    if accepted_l["routes"]["6"]["selected"]["fingerprint"] != L_SELECTED["6"]:
        raise RuntimeError("accepted PR62-L Route 6 selection changed")
    if accepted_l["routes"]["10"]["selected"]["fingerprint"] != L_SELECTED["10"]:
        raise RuntimeError("accepted PR62-L Route 10 selection changed")
    accepted_i = json.loads((repo_root / pr62_i.OUTPUT_JSON).read_text(encoding="utf-8"))
    artifact_root = pr62_i._artifact_root(repo_root)
    prior_before = coordinator.verify_frozen_prior_artifacts_v1(artifact_root)
    routes: dict[str, Any] = {}
    internals: dict[str, Any] = {}
    for route_id in ("6", "10"):
        routes[route_id], internals[route_id] = _evaluate_route(
            repo_root=repo_root,
            artifact_root=artifact_root,
            route_id=route_id,
            accepted_i=accepted_i,
        )
    prior_after = coordinator.verify_frozen_prior_artifacts_v1(artifact_root)
    if prior_before != prior_after:
        raise RuntimeError("frozen prior artifacts changed during PR62-M")
    human = _human_final_calibration(
        repo_root=repo_root,
        context=internals["6"]["context"],
        selected=internals["6"]["selected_calibration"],
    )
    if human.get("accepted_sha_match"):
        for candidate in routes["6"]["access_safe_candidates"]:
            candidate["allocation_move_distance_vs_HUMAN_FINAL"] = _pair_allocation_move_distance(
                candidate, human
            )
        human_distances = {
            candidate["fingerprint"]: candidate["allocation_move_distance_vs_HUMAN_FINAL"]
            for candidate in routes["6"]["access_safe_candidates"]
        }
        for candidate in routes["6"]["focused_comparisons"]:
            candidate["allocation_move_distance_vs_HUMAN_FINAL"] = human_distances[
                candidate["fingerprint"]
            ]
    routes["6"]["human_final_comparison"] = human
    any_conflict = any(
        route["classification"] == "DEMAND_FIT_METRIC_ORDERING_CONFLICT"
        for route in routes.values()
    )
    cross_route = (
        "TRIP_EQUIVALENT_METRIC_CONFLICT_REQUIRES_REVIEW"
        if any_conflict
        else "TRIP_EQUIVALENT_CALIBRATION_READY_FOR_POLICY"
    )
    return {
        "profile": PROFILE,
        "L_commit_SHA": L_COMMIT_SHA,
        "formulas": {
            "directional_allocation_tv": (
                "0.5 * sum_b abs(bucket_service_share_b - bucket_demand_share_b)"
            ),
            "directional_trip_equivalent_error": (
                "directional_total_trips * directional_allocation_tv"
            ),
            "pair_trip_equivalent_error": (
                "outbound_trip_equivalent_error + inbound_trip_equivalent_error"
            ),
            "pair_normalized_allocation_tv": (
                "pair_trip_equivalent_error / (outbound_total_trips + inbound_total_trips)"
            ),
            "allocation_move_distance_trips": (
                "0.5 * sum_b abs(bucket_service_count_A_b - bucket_service_count_B_b)"
            ),
        },
        "interpretation": {
            "trip_equivalent_error": (
                "Equivalent directional service allocation that would need to move between "
                "time buckets to reproduce immutable demand shares in a continuous "
                "proportional ideal; fractional values are not fractional physical trips."
            ),
            "allocation_move_distance": (
                "Minimum whole trip bucket assignments that differ between two exact "
                "candidate allocation histograms; distinct from demand-fit error."
            ),
        },
        "candidate_universe": {
            "name": "L_ACCESS_SAFE_SET",
            "source": "exact current I Pareto operating pairs after L feasibility and access",
            "human_final_included": False,
            "production_selector_changed": False,
            "frozen_search_budget": dataclasses.asdict(pr62_l.FROZEN_BUDGET),
        },
        "routes": routes,
        "human_final_route_6": human,
        "cross_route_classification": cross_route,
        "one_trip_boundary_implemented": False,
        "deterministic_render": {},
        "production_guards": {
            "coordinator_search_changed": "NO",
            "10-D_Pareto_changed": "NO",
            "L_selector_changed": "NO",
            "demand_mismatch_semantics_changed": "NO",
            "TV_added_to_production_objective": "NO",
            "compiler_changed": "NO",
            "tail_eligibility_changed": "NO",
            "access_guardrail_changed": "NO",
            "rhythm_semantics_changed": "NO",
            "fleet_validator_changed": "NO",
            "queue_changed": "NO",
            "budgets_changed": "NO",
            "settlement_added": "NO",
            "final_XLSX_regenerated": "NO",
            "production_selector_threshold_added": "NO",
            "private_workbook_committed": "NO",
        },
    }


def _fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# PR62-M — Discrete demand-fit materiality calibration",
        "",
        f"Profile: `{payload['profile']}`.",
        "",
        "Production SSE mismatch remains authoritative. Total-variation and trip-equivalent "
        "error are review-only interpretable companions.",
        "",
        "Directional TV is half the L1 distance between exact service shares and immutable "
        "demand shares. Directional trip-equivalent error multiplies TV by exact directional "
        "trip count; pair error sums directions without averaging.",
        "",
    ]
    for route_id in ("6", "10"):
        if route_id not in payload.get("routes", {}):
            continue
        route = payload["routes"][route_id]
        audit = route["metric_ordering_audit"]
        counts = route["stage_counts"]
        lines.extend(
            [
                f"## Route {route_id}",
                "",
                (
                    f"I Pareto `{counts['I_Pareto']}`; hard feasible "
                    f"`{counts['hard_feasible']}`; access-safe `{counts['access_safe']}`."
                ),
                "",
                f"SSE best: `{audit['SSE_BEST']['fingerprint']}`; TV/TE best: "
                f"`{audit['TV_BEST']['fingerprint']}`; same: "
                f"`{audit['same_best_candidate']}`; pairwise disagreements: "
                f"`{audit['pairwise_ranking_disagreement_count']}`.",
                "",
                "### Focused comparisons",
                "",
                "| roles | fingerprint | SSE | OB TV | IB TV | pair TE | ΔTE vs best | moves vs L | avg wait | max OB/IB | fleet | rhythm | tails OB/IB |",
                "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|",
            ]
        )
        for row in route["focused_comparisons"]:
            lines.append(
                f"| {', '.join(row['roles'])} | `{row['fingerprint']}` | "
                f"{_fmt(row['observed_demand_mismatch'], 9)} | "
                f"{_fmt(row['directions']['outbound']['directional_allocation_tv'], 9)} | "
                f"{_fmt(row['directions']['inbound']['directional_allocation_tv'], 9)} | "
                f"{_fmt(row['pair_trip_equivalent_error'])} | "
                f"{_fmt(row['delta_trip_equivalent_vs_tv_best'])} | "
                f"{row['allocation_move_distance_vs_L_selected']} | "
                f"{_fmt(row['average_wait_minutes'])} | "
                f"{_fmt(row['directional_maximum_bucket_wait_minutes']['outbound'])}/"
                f"{_fmt(row['directional_maximum_bucket_wait_minutes']['inbound'])} | "
                f"{row['fleet_required']} | {tuple(row['rhythm_simplicity_tuple'])} | "
                f"{row['tail_headways']['outbound']}/{row['tail_headways']['inbound']} |"
            )
        lines.extend(["", "### Exact breakpoint path", ""])
        for row in route["trip_equivalent_breakpoint_path"]:
            lines.append(
                f"- ΔTE `{_fmt(row['delta_trip_equivalent'])}`: "
                f"`{row['preferred_fingerprint']}` (envelope {row['envelope_candidate_count']})."
            )
        quantum = route["one_trip_quantum_diagnostic"]
        lines.extend(
            [
                "",
                f"One-trip diagnostic: simpler within <1 TE "
                f"`{quantum['sub_one_trip_simpler_exists']}`; within <=1 TE "
                f"`{quantum['at_or_below_one_trip_simpler_exists']}`; minimum "
                f"`{_fmt(quantum['minimum_delta_to_simpler_candidate'])}`.",
                "",
                f"Classification: `{route['classification']}`.",
                "",
            ]
        )
    human = payload.get("human_final_route_6", {})
    lines.extend(["## Route 6 Human Final", ""])
    if human.get("accepted_sha_match"):
        delta = human["selected_minus_human_final"]
        lines.extend(
            [
                "Classification: `POST_SEARCH_EXPERT_BENCHMARK`; never selectable.",
                "",
                f"Human Final pair TE `{_fmt(human['pair_trip_equivalent_error'])}`; selected-minus-human "
                f"TE `{_fmt(delta['pair_trip_equivalent_error'])}`; SSE "
                f"`{_fmt(delta['observed_demand_mismatch'], 9)}`; bucket moves "
                f"`{delta['allocation_move_distance_trips']}`; sustained/effective palette "
                f"difference `{delta['sustained_headway_level_count']}/"
                f"{delta['effective_palette_count']}`; fleet `{delta['fleet_required']}`; "
                f"wait `{_fmt(delta['average_wait_minutes'])}` minutes.",
                "",
            ]
        )
    else:
        lines.extend(["Accepted private benchmark was unavailable; comparison not performed.", ""])
    lines.extend(
        [
            "## Decision",
            "",
            f"Cross-route classification: `{payload['cross_route_classification']}`.",
            "",
            "A one-trip quantum is reported descriptively only. No materiality boundary or "
            "production selector change is implemented.",
            "",
            "## Production guards",
            "",
        ]
    )
    for key, value in payload.get("production_guards", {}).items():
        lines.append(f"- {key}: **{value}**")
    return "\n".join(lines) + "\n"


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
        raise RuntimeError("PR62-M evidence render is not byte-identical")
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
        "cross_route_classification": payload["cross_route_classification"],
        "route_classifications": {
            route_id: payload["routes"][route_id]["classification"] for route_id in ("6", "10")
        },
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
