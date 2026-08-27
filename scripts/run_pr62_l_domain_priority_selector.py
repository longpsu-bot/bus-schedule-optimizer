"""Generate PR62-L domain-priority operational-selector evidence."""

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
import run_pr62_k_baseline_safe_operational_shortlist as pr62_k  # noqa: E402

from bus_schedule_engine import service_plan_coordinator as coordinator  # noqa: E402
from bus_schedule_engine.contracts_v1.operational_selection_policy import (  # noqa: E402
    DEFAULT_OPERATIONAL_SELECTION_POLICY_V1,
    NUMERICAL_EPSILON,
    build_operational_selection_candidate_v1,
    select_operational_candidates_v1,
)

PROFILE = "domain_priority_operational_selector_v1"
K_COMMIT_SHA = "811226271d4f577e863149283481ef213c138c5f"
FROZEN_BUDGET = coordinator.CoordinatorSearchBudgetV1(24, 512, 4, 24, 512)
EXPECTED_I_PARETO_SIZES = {"6": 47, "10": 11}
OUTPUT_JSON = Path("docs/engine/evidence/PR62_L_DOMAIN_PRIORITY_SELECTOR.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_L_DOMAIN_PRIORITY_SELECTOR.md")


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


def _rhythm_tuple(item: Mapping[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(item["sustained_headway_level_count"]),
        int(item["actual_service_regime_count"]),
        int(item["effective_palette_count"]),
        int(item["single_gap_regime_count"]),
    )


def _policy_health_classification(
    *,
    selection_classification: str,
    selected: Mapping[str, Any] | None,
    access_safe: Sequence[Mapping[str, Any]],
) -> str:
    if selection_classification == "ACCESS_GUARDRAIL_TOO_RESTRICTIVE":
        return "DOMAIN_HIERARCHY_ACCESS_GUARDRAIL_TOO_RESTRICTIVE"
    if selected is None or not access_safe:
        return "DOMAIN_HIERARCHY_EVIDENCE_INCONCLUSIVE"
    if _rhythm_tuple(selected) > min(_rhythm_tuple(item) for item in access_safe):
        return "DOMAIN_HIERARCHY_DEMAND_FIRST_COMPLEXITY_CONCERN"
    return "DOMAIN_HIERARCHY_SELECTS_PLAUSIBLE_CANDIDATE"


def _human_final_complexity_concern(
    *,
    selected_sustained: int,
    selected_regimes: int,
    selected_effective: int,
    human_sustained: int,
    human_regimes: int,
    human_effective: int,
) -> bool:
    return (selected_sustained, selected_regimes, selected_effective) > (
        human_sustained,
        human_regimes,
        human_effective,
    )


def _nearby_alternatives(
    access_safe: Sequence[Mapping[str, Any]],
    *,
    selected_fingerprint: str,
) -> list[dict[str, Any]]:
    if not access_safe:
        return []
    by_fingerprint = {str(item["fingerprint"]): item for item in access_safe}
    selected = by_fingerprint[selected_fingerprint]
    definitions = (
        ("SELECTED", selected),
        (
            "MINIMUM_SUSTAINED_PALETTE",
            min(
                access_safe,
                key=lambda item: (
                    int(item["sustained_headway_level_count"]),
                    int(item["actual_service_regime_count"]),
                    int(item["effective_palette_count"]),
                    int(item["single_gap_regime_count"]),
                    str(item["fingerprint"]),
                ),
            ),
        ),
        (
            "MINIMUM_FLEET",
            min(
                access_safe,
                key=lambda item: (
                    int(item["fleet_required"]),
                    int(item["total_excess_terminal_wait"]),
                    int(item["max_excess_terminal_wait"]),
                    str(item["fingerprint"]),
                ),
            ),
        ),
        (
            "MINIMUM_AVERAGE_WAIT",
            min(
                access_safe,
                key=lambda item: (float(item["average_wait_minutes"]), str(item["fingerprint"])),
            ),
        ),
        (
            "NEXT_BEST_MISMATCH",
            min(
                (item for item in access_safe if str(item["fingerprint"]) != selected_fingerprint),
                key=lambda item: (float(item["mismatch"]), str(item["fingerprint"])),
                default=selected,
            ),
        ),
    )
    rows: dict[str, dict[str, Any]] = {}
    for role, item in definitions:
        fingerprint = str(item["fingerprint"])
        if fingerprint not in rows:
            rows[fingerprint] = {
                "fingerprint": fingerprint,
                "mismatch": item["mismatch"],
                "average_wait_minutes": item["average_wait_minutes"],
                "directional_maximum_bucket_wait_minutes": item[
                    "directional_maximum_bucket_wait_minutes"
                ],
                "fleet_required": item["fleet_required"],
                "actual_service_regime_count": item["actual_service_regime_count"],
                "sustained_headway_level_count": item["sustained_headway_level_count"],
                "effective_palette_count": item["effective_palette_count"],
                "single_gap_regime_count": item["single_gap_regime_count"],
                "total_excess_terminal_wait": item["total_excess_terminal_wait"],
                "max_excess_terminal_wait": item["max_excess_terminal_wait"],
                "tail_headways": item["tail_headways"],
                "roles": [],
                "delta_mismatch_vs_selected": (
                    float(item["mismatch"]) - float(selected["mismatch"])
                ),
            }
        rows[fingerprint]["roles"].append(role)
    return list(rows.values())[:5]


def _extreme_tail_audit(
    candidates: Sequence[Mapping[str, Any]],
    *,
    scenario_b_inbound_maximum_wait_minutes: float,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "policy_is_headway_threshold": False,
        "policy_rule": "SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
    }
    for tail in (30, 45, 48, 54):
        rows = []
        for item in candidates:
            if int(item["tail_headways"]["inbound"]) != tail:
                continue
            candidate_wait = float(item["directional_maximum_bucket_wait_minutes"]["inbound"])
            excluded = candidate_wait > scenario_b_inbound_maximum_wait_minutes + 1e-12
            rows.append(
                {
                    "fingerprint": item["fingerprint"],
                    "inbound_tail_headway_minutes": tail,
                    "candidate_inbound_maximum_bucket_expected_wait_minutes": candidate_wait,
                    "scenario_b_inbound_maximum_bucket_expected_wait_minutes": (
                        scenario_b_inbound_maximum_wait_minutes
                    ),
                    "excluded_by_access_guardrail": excluded,
                    "reason": ("INBOUND_MAX_ACCESS_REGRESSION" if excluded else "ACCESS_SAFE"),
                }
            )
        result[str(tail)] = sorted(rows, key=lambda item: str(item["fingerprint"]))
    return result


def _format_departure(seconds: int) -> str:
    return coordinator.format_hhmm(seconds)


def _headway_sequence(departures: Sequence[int]) -> list[int]:
    return [(right - left) // 60 for left, right in zip(departures, departures[1:], strict=False)]


def _service_regime_records(item: Any) -> list[dict[str, Any]]:
    return [
        {
            "service_regime_id": service.service_regime_id,
            "first_departure": _format_departure(service.first_departure),
            "last_departure": _format_departure(service.last_departure),
            "uniform_headway_minutes": service.uniform_headway_minutes,
            "trip_count": service.trip_count,
        }
        for service in item.compile_variant.compilation.service_regimes
    ]


def _candidate_record(
    item: Any,
    snapshot: Any,
    *,
    scenario_b_access: Mapping[str, float],
    best_access_safe_mismatch: float | None,
) -> dict[str, Any]:
    directions = {}
    for direction in ("outbound", "inbound"):
        record = getattr(item, direction)
        rhythm = record.metrics.rhythm_simplicity
        directions[direction] = {
            "maximum_bucket_expected_wait_minutes": (
                record.metrics.maximum_bucket_expected_wait_minutes
            ),
            "p90_bucket_expected_wait_minutes": record.metrics.p90_bucket_expected_wait_minutes,
            "tail_maximum_bucket_expected_wait_minutes": (
                record.metrics.tail_maximum_bucket_expected_wait_minutes
            ),
            "tail_headway_minutes": record.metrics.tail_headway_minutes,
            "tail_classification": record.metrics.tail_ordering.classification,
            "tail_eligible": record.metrics.tail_ordering.eligible,
            "service_regime_count": record.metrics.actual_service_regime_count,
            "sustained_headway_levels": list(rhythm.sustained_headway_levels),
            "effective_headway_palette": list(rhythm.effective_headway_palette),
            "single_gap_headway_levels": list(rhythm.single_gap_headway_levels),
            "bucket_service_shares": list(record.metrics.bucket_service_shares),
            "demand_response_direction_accuracy": (
                record.metrics.demand_response_direction_accuracy
            ),
            "sqrt_response_deviation": record.metrics.sqrt_seed_response_deviation,
            "under_over_feedback_presence": snapshot.diagnostics["under_over_feedback_presence"][
                direction
            ],
        }
    hard_feasible = bool(snapshot.hard_feasible)
    access_safe = hard_feasible and all(
        directions[direction]["maximum_bucket_expected_wait_minutes"]
        <= scenario_b_access[direction] + NUMERICAL_EPSILON
        for direction in ("outbound", "inbound")
    )
    metrics = item.metrics
    return {
        "fingerprint": item.pair_fingerprint,
        "hard_feasible": hard_feasible,
        "hard_feasibility_reasons": list(snapshot.hard_feasibility_reasons),
        "access_safe": access_safe,
        "mismatch": metrics.observed_demand_mismatch,
        "delta_mismatch_vs_best_access_safe": (
            None
            if best_access_safe_mismatch is None
            else metrics.observed_demand_mismatch - best_access_safe_mismatch
        ),
        "average_wait_minutes": metrics.demand_weighted_expected_passenger_wait_minutes,
        "directional_maximum_bucket_wait_minutes": {
            direction: directions[direction]["maximum_bucket_expected_wait_minutes"]
            for direction in ("outbound", "inbound")
        },
        "maximum_directional_p90_bucket_wait_minutes": (
            metrics.maximum_directional_p90_bucket_wait_minutes
        ),
        "fleet_required": metrics.fleet_required,
        "fleet_ceiling": item.fleet_ceiling,
        "fleet_spare": item.fleet_ceiling - metrics.fleet_required,
        "minimum_connection_layover_minutes": item.minimum_connection_layover_minutes,
        "actual_service_regime_count": metrics.actual_service_regime_count,
        "sustained_headway_level_count": (metrics.total_directional_sustained_headway_level_count),
        "effective_palette_count": metrics.total_directional_effective_palette_count,
        "single_gap_regime_count": metrics.total_single_gap_regime_count,
        "total_excess_terminal_wait": metrics.total_excess_terminal_wait,
        "max_excess_terminal_wait": metrics.max_excess_terminal_wait,
        "tail_headways": {
            direction: directions[direction]["tail_headway_minutes"]
            for direction in ("outbound", "inbound")
        },
        "directions": directions,
    }


def _candidate_audit_record(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item[key]
        for key in (
            "fingerprint",
            "hard_feasible",
            "hard_feasibility_reasons",
            "access_safe",
            "mismatch",
            "delta_mismatch_vs_best_access_safe",
            "average_wait_minutes",
            "directional_maximum_bucket_wait_minutes",
            "maximum_directional_p90_bucket_wait_minutes",
            "fleet_required",
            "actual_service_regime_count",
            "sustained_headway_level_count",
            "effective_palette_count",
            "single_gap_regime_count",
            "total_excess_terminal_wait",
            "max_excess_terminal_wait",
            "tail_headways",
        )
    }


def _selected_exact_record(item: Any, compact: Mapping[str, Any]) -> dict[str, Any]:
    directions = {}
    for direction in ("outbound", "inbound"):
        record = getattr(item, direction)
        departures = record.compile_variant.compilation.exact_departures
        directions[direction] = {
            **compact["directions"][direction],
            "exact_departures_seconds": list(departures),
            "exact_departures": [_format_departure(value) for value in departures],
            "headway_sequence_minutes": _headway_sequence(departures),
            "ServiceRegimes": _service_regime_records(record),
        }
    return {**dict(compact), "directions": directions}


def _stage_fingerprints(selection: Any, stage: str) -> list[str]:
    trace = next(item for item in selection.stage_trace if item.stage == stage)
    return list(trace.retained_fingerprints)


def _evaluate_route(
    *,
    repo_root: Path,
    artifact_root: Path,
    route_id: str,
    accepted_i: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    workbook = repo_root / f"Engine_Input_MST_{route_id}_V3_MultiPeriod_Mar-Jul_2026.xlsx"
    context, seeds = coordinator.load_route_coordinator_inputs_v1(
        repo_root=artifact_root,
        route_id=route_id,
        workbook_path=workbook,
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
        raise RuntimeError(f"route {route_id} I Pareto size changed")
    if any(len(item.metrics.pareto_vector) != 10 for item in frontier):
        raise RuntimeError("production Pareto vector is not exactly ten-dimensional")

    scenario_b_access = {
        direction: coordinator.expected_passenger_wait_metrics_v1(
            context.scenario_b_departures[direction], context.demand_buckets[direction]
        )[1]
        for direction in ("outbound", "inbound")
    }
    snapshots = tuple(
        build_operational_selection_candidate_v1(context=context, candidate=item)
        for item in frontier
    )
    selection = select_operational_candidates_v1(
        route_id=route_id,
        candidates=snapshots,
        scenario_b_directional_maximum_wait_minutes=scenario_b_access,
    )
    prelim_records = [
        _candidate_record(
            item,
            snapshot,
            scenario_b_access=scenario_b_access,
            best_access_safe_mismatch=None,
        )
        for item, snapshot in zip(frontier, snapshots, strict=True)
    ]
    access_safe_prelim = tuple(item for item in prelim_records if item["access_safe"])
    best_mismatch = (
        min(float(item["mismatch"]) for item in access_safe_prelim) if access_safe_prelim else None
    )
    records = [
        _candidate_record(
            item,
            snapshot,
            scenario_b_access=scenario_b_access,
            best_access_safe_mismatch=best_mismatch,
        )
        for item, snapshot in zip(frontier, snapshots, strict=True)
    ]
    by_fingerprint = {str(item["fingerprint"]): item for item in records}
    raw_by_fingerprint = {item.pair_fingerprint: item for item in frontier}
    access_safe = tuple(item for item in records if item["access_safe"])
    selected_fingerprint = selection.selected_pair_fingerprint
    selected_compact = (
        None if selected_fingerprint is None else by_fingerprint[selected_fingerprint]
    )
    selected = (
        None
        if selected_fingerprint is None
        else _selected_exact_record(raw_by_fingerprint[selected_fingerprint], selected_compact)
    )
    if selected is not None and selected_fingerprint is not None:
        selected_snapshot = snapshots[fingerprints.index(selected_fingerprint)]
        selected["hard_feasibility"] = selected_snapshot.hard_feasibility_metrics
    health = _policy_health_classification(
        selection_classification=selection.classification,
        selected=selected_compact,
        access_safe=access_safe,
    )
    stage_counts = {
        "I_Pareto": len(frontier),
        "hard_feasible": selection.hard_feasible_count,
        "access_safe": selection.passenger_access_safe_count,
        "best_demand_fit": selection.best_demand_fit_count,
        "best_rhythm": selection.best_rhythm_count,
        "best_fleet_efficiency": selection.best_fleet_efficiency_count,
        "selected": 0 if selected is None else 1,
    }
    route_payload: dict[str, Any] = {
        "route_id": route_id,
        "search_status": result.status,
        "search_budget": dataclasses.asdict(FROZEN_BUDGET),
        "search_statistics": dataclasses.asdict(result.statistics),
        "stage_counts": stage_counts,
        "selection_result": dataclasses.asdict(selection),
        "SCENARIO_B_MAX_ACCESS_NON_REGRESSION": {
            "directional_maximum_bucket_expected_wait_minutes": scenario_b_access,
            "comparison_is_directional": True,
            "mean_wait_gate": False,
            "mismatch_gate": False,
            "p90_gate": False,
            "one_se_gate": False,
            "percentage_of_days_gate": False,
        },
        "BEST_DEMAND_FIT_SET": _stage_fingerprints(selection, "OBSERVED_DEMAND_MISMATCH"),
        "BEST_RHYTHM_SET": _stage_fingerprints(selection, "RHYTHM_SIMPLICITY"),
        "BEST_FLEET_EFFICIENCY_SET": _stage_fingerprints(selection, "FLEET_EFFICIENCY"),
        "selected": selected,
        "access_safe_candidate_diagnostics": list(access_safe),
        "candidate_audit": [_candidate_audit_record(item) for item in records],
        "nearby_alternatives": (
            []
            if selected_fingerprint is None
            else _nearby_alternatives(access_safe, selected_fingerprint=selected_fingerprint)
        ),
        "policy_health_classification": health,
    }
    if route_id == "10":
        route_payload["inbound_extreme_tail_audit"] = _extreme_tail_audit(
            route_payload["candidate_audit"],
            scenario_b_inbound_maximum_wait_minutes=scenario_b_access["inbound"],
        )
    return route_payload, {
        "context": context,
        "frontier": frontier,
        "selected": selected,
        "selection": selection,
    }


def _human_final_comparison(
    *,
    repo_root: Path,
    context: Any,
    selected: Mapping[str, Any] | None,
) -> dict[str, Any]:
    workbook = pr62_i._human_final_workbook(repo_root)
    if workbook is None:
        return {
            "available": False,
            "accepted_sha_match": False,
            "classification": "POST_SEARCH_EXPERT_BENCHMARK",
            "selection_eligible": False,
        }
    human = pr62_i._human_final(context, workbook)
    if human is None or not human.get("accepted_sha_match"):
        return {
            "available": human is not None,
            "accepted_sha_match": False,
            "classification": "POST_SEARCH_EXPERT_BENCHMARK",
            "selection_eligible": False,
        }
    parsed = pr62_i.parse_route6_reference_workbook(workbook)
    source = parsed["references"]["HUMAN_FINAL"]
    human_directions = human["directions"]
    for direction in ("outbound", "inbound"):
        departures = source[direction]
        human_directions[direction]["exact_departures"] = [
            _format_departure(value) for value in departures
        ]
        human_directions[direction]["headway_sequence_minutes"] = _headway_sequence(departures)
        human_directions[direction]["ServiceRegimes"] = [
            {
                "headway_minutes": run.headway_minutes,
                "gap_count": run.gap_count,
                "first_departure": _format_departure(departures[run.gap_start_index]),
                "last_departure": _format_departure(
                    departures[run.gap_start_index + run.gap_count]
                ),
            }
            for run in pr62_i.exact_headway_runs(departures)
        ]
    human_regimes = sum(
        int(human_directions[direction]["actual_headway_run_count"])
        for direction in ("outbound", "inbound")
    )
    human_sustained = sum(
        len(human_directions[direction]["sustained_headway_levels"])
        for direction in ("outbound", "inbound")
    )
    human_effective = sum(
        len(human_directions[direction]["effective_headway_palette"])
        for direction in ("outbound", "inbound")
    )
    result: dict[str, Any] = {
        **human,
        "classification": "POST_SEARCH_EXPERT_BENCHMARK",
        "selection_eligible": False,
        "actual_service_regime_count": human_regimes,
        "sustained_headway_level_count": human_sustained,
        "effective_palette_count": human_effective,
    }
    if selected is None:
        result["comparison_to_selected"] = None
        result["strict_demand_fit_first_substantially_more_complex"] = None
        return result
    selected_directions = selected["directions"]
    result["comparison_to_selected"] = {
        "selected_fingerprint": selected["fingerprint"],
        "selected_minus_human_final": {
            "mismatch": selected["mismatch"] - human["pair"]["mismatch"],
            "average_wait_minutes": (
                selected["average_wait_minutes"] - human["pair"]["average_wait_minutes"]
            ),
            "outbound_maximum_bucket_wait_minutes": (
                selected_directions["outbound"]["maximum_bucket_expected_wait_minutes"]
                - human_directions["outbound"]["maximum_bucket_wait_minutes"]
            ),
            "inbound_maximum_bucket_wait_minutes": (
                selected_directions["inbound"]["maximum_bucket_expected_wait_minutes"]
                - human_directions["inbound"]["maximum_bucket_wait_minutes"]
            ),
            "maximum_directional_p90_bucket_wait_minutes": (
                selected["maximum_directional_p90_bucket_wait_minutes"]
                - human["pair"]["maximum_directional_p90_bucket_wait_minutes"]
            ),
            "fleet_required": selected["fleet_required"] - human["pair"]["fleet"],
            "actual_service_regime_count": (
                selected["actual_service_regime_count"] - human_regimes
            ),
            "sustained_headway_level_count": (
                selected["sustained_headway_level_count"] - human_sustained
            ),
            "effective_palette_count": (selected["effective_palette_count"] - human_effective),
        },
        "selected_tail_headways": selected["tail_headways"],
        "human_final_tail_headways": {
            direction: human_directions[direction]["tail_headway_minutes"]
            for direction in ("outbound", "inbound")
        },
    }
    substantially_more = _human_final_complexity_concern(
        selected_sustained=selected["sustained_headway_level_count"],
        selected_regimes=selected["actual_service_regime_count"],
        selected_effective=selected["effective_palette_count"],
        human_sustained=human_sustained,
        human_regimes=human_regimes,
        human_effective=human_effective,
    )
    result["strict_demand_fit_first_substantially_more_complex"] = substantially_more
    result["substantial_complexity_semantics"] = (
        "Compare sustained exact levels first, then actual ServiceRegimes, then effective palette, "
        "following the authoritative rhythm priority; no weighted score or numeric materiality "
        "threshold is introduced."
    )
    return result


def build_evidence(repo_root: Path) -> dict[str, Any]:
    if dataclasses.astuple(FROZEN_BUDGET) != (24, 512, 4, 24, 512):
        raise RuntimeError("search budgets changed")
    accepted_k = json.loads((repo_root / pr62_k.OUTPUT_JSON).read_text(encoding="utf-8"))
    if accepted_k["cross_route_classification"] != "BASELINE_SAFE_POLICY_TOO_RESTRICTIVE":
        raise RuntimeError("PR62-K accepted negative result changed")
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
        raise RuntimeError("frozen prior artifacts changed during PR62-L")
    human = _human_final_comparison(
        repo_root=repo_root,
        context=internals["6"]["context"],
        selected=routes["6"]["selected"],
    )
    routes["6"]["human_final_comparison"] = human
    ready = all(
        routes[route_id]["policy_health_classification"]
        == "DOMAIN_HIERARCHY_SELECTS_PLAUSIBLE_CANDIDATE"
        and routes[route_id]["selection_result"]["classification"]
        == "UNIQUE_DOMAIN_PRIORITY_SELECTION"
        for route_id in ("6", "10")
    )
    return {
        "profile": PROFILE,
        "version": "OperationalSelectionPolicyV1",
        "K_commit_SHA": K_COMMIT_SHA,
        "K_result": "COMPLETED_NEGATIVE_POLICY_EXPERIMENT_NOT_REINTERPRETED",
        "policy": {
            "profile": DEFAULT_OPERATIONAL_SELECTION_POLICY_V1.profile,
            "priority_order": list(DEFAULT_OPERATIONAL_SELECTION_POLICY_V1.priority_order),
            "numerical_epsilon": NUMERICAL_EPSILON,
            "lexicographic_not_weighted": True,
            "fleet_feasibility": {
                "role": "HARD_OPERATIONAL_FEASIBILITY",
                "authority": "runtime + minimum layover + exact minimum-fleet path cover + fleet ceiling",
                "failure_is_non_selectable": True,
            },
            "fleet_efficiency": {
                "role": "PREFERENCE_AFTER_FEASIBILITY_ACCESS_DEMAND_AND_RHYTHM",
                "tuple": [
                    "fleet_required",
                    "total_excess_terminal_wait",
                    "max_excess_terminal_wait",
                ],
                "combined_with_feasibility_score": False,
            },
            "access_guardrail": {
                "name": "SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
                "directional": True,
                "rule": "candidate directional maximum bucket expected wait <= Scenario B same-direction value + numerical epsilon",
                "only_new_scenario_b_hard_guardrail": True,
            },
            "demand_fit": {
                "authority": "OperatingPairMetricsV1.observed_demand_mismatch",
                "strict_minimum_within_numerical_epsilon": True,
                "one_se": False,
                "percentage_band": False,
                "arbitrary_rounding": False,
            },
            "rhythm_simplicity_tuple": [
                "total_directional_sustained_headway_level_count",
                "actual_service_regime_count",
                "total_directional_effective_palette_count",
                "total_single_gap_regime_count",
            ],
        },
        "candidate_universe": {
            "source": "exact current PR62-I production Pareto frontier",
            "immutable_exact_operating_pairs": True,
            "frozen_search_budget": dataclasses.asdict(FROZEN_BUDGET),
            "new_candidate_family": False,
            "demand_regime_model_selection_rerun": False,
            "exact_departures_moved_during_selection": False,
        },
        "routes": routes,
        "human_final_route_6": human,
        "READY_FOR_POST_HIJKL_RECERTIFICATION": ready,
        "PR62_G_products_status": "FROZEN_HISTORICAL_PRODUCTS_NOT_REGENERATED",
        "deterministic_render": {},
        "production_guards": {
            "compiler_changed": "NO",
            "queue_changed": "NO",
            "budgets_changed": "NO",
            "Pareto_changed": "NO",
            "mismatch_semantics_changed": "NO",
            "wait_semantics_changed": "NO",
            "tail_eligibility_changed": "NO",
            "fleet_validator_changed": "NO",
            "settlement_added": "NO",
            "XLSX_regenerated": "NO",
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
        "# PR62-L — Domain-priority operational selector",
        "",
        f"Profile: `{payload['profile']}`.",
        "",
        "Priority: hard operational feasibility → directional Scenario-B max-access "
        "non-regression → observed demand mismatch → rhythm simplicity → fleet efficiency.",
        "",
    ]
    for route_id in ("6", "10"):
        if route_id not in payload.get("routes", {}):
            continue
        route = payload["routes"][route_id]
        counts = route["stage_counts"]
        selected = route["selected"]
        lines.extend(
            [
                f"## Route {route_id}",
                "",
                "| I Pareto | hard feasible | access-safe | best demand | best rhythm | best fleet | selected |",
                "|---:|---:|---:|---:|---:|---:|---:|",
                (
                    f"| {counts['I_Pareto']} | {counts['hard_feasible']} | "
                    f"{counts['access_safe']} | {counts['best_demand_fit']} | "
                    f"{counts['best_rhythm']} | {counts['best_fleet_efficiency']} | "
                    f"{counts['selected']} |"
                ),
                "",
                f"Policy health: `{route['policy_health_classification']}`.",
                "",
            ]
        )
        if selected is None:
            lines.extend(["No candidate selected.", ""])
        else:
            lines.extend(
                [
                    f"Selected: `{selected['fingerprint']}`.",
                    "",
                    (
                        f"Mismatch `{_fmt(selected['mismatch'], 9)}`; average wait "
                        f"`{_fmt(selected['average_wait_minutes'])}` minutes; directional max "
                        f"OB/IB `{_fmt(selected['directional_maximum_bucket_wait_minutes']['outbound'])}`/"
                        f"`{_fmt(selected['directional_maximum_bucket_wait_minutes']['inbound'])}`; "
                        f"fleet `{selected['fleet_required']}/{selected['fleet_ceiling']}`; "
                        f"regimes/sustained/effective `{selected['actual_service_regime_count']}`/"
                        f"`{selected['sustained_headway_level_count']}`/"
                        f"`{selected['effective_palette_count']}`; tails OB/IB "
                        f"`{selected['tail_headways']['outbound']}`/"
                        f"`{selected['tail_headways']['inbound']}` minutes."
                    ),
                    "",
                    "### Nearby alternatives",
                    "",
                    "| roles | fingerprint | mismatch | Δ mismatch | avg wait | max OB/IB | fleet | regimes | sustained | effective | tails OB/IB |",
                    "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
                ]
            )
            for row in route["nearby_alternatives"]:
                lines.append(
                    f"| {', '.join(row['roles'])} | `{row['fingerprint']}` | "
                    f"{_fmt(row['mismatch'], 9)} | {_fmt(row['delta_mismatch_vs_selected'], 9)} | "
                    f"{_fmt(row['average_wait_minutes'])} | "
                    f"{_fmt(row['directional_maximum_bucket_wait_minutes']['outbound'])}/"
                    f"{_fmt(row['directional_maximum_bucket_wait_minutes']['inbound'])} | "
                    f"{row['fleet_required']} | {row['actual_service_regime_count']} | "
                    f"{row['sustained_headway_level_count']} | {row['effective_palette_count']} | "
                    f"{row['tail_headways']['outbound']}/{row['tail_headways']['inbound']} |"
                )
            lines.append("")
        if route_id == "10":
            audit = route["inbound_extreme_tail_audit"]
            lines.extend(["### Inbound extreme-tail audit", ""])
            for tail in (30, 45, 48, 54):
                rows = audit[str(tail)]
                if not rows:
                    lines.append(f"- {tail} minutes: not present.")
                for row in rows:
                    lines.append(
                        f"- {tail} minutes `{row['fingerprint']}`: `{row['reason']}`; "
                        f"candidate IB max `{_fmt(row['candidate_inbound_maximum_bucket_expected_wait_minutes'])}` "
                        f"vs Scenario B `{_fmt(row['scenario_b_inbound_maximum_bucket_expected_wait_minutes'])}`."
                    )
            lines.append("")
    human = payload.get("human_final_route_6")
    if human:
        lines.extend(
            [
                "## Route 6 Human Final",
                "",
                "Classification: `POST_SEARCH_EXPERT_BENCHMARK`; never selectable.",
                "",
                (
                    "Strict demand-fit-first substantially more complex: "
                    f"`{human.get('strict_demand_fit_first_substantially_more_complex')}`."
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## Decision",
            "",
            "`READY_FOR_POST_HIJKL_RECERTIFICATION = "
            f"{str(payload['READY_FOR_POST_HIJKL_RECERTIFICATION']).lower()}`.",
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
        raise RuntimeError("PR62-L evidence render is not byte-identical")
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
        "ready_for_recertification": payload["READY_FOR_POST_HIJKL_RECERTIFICATION"],
        "route_classifications": {
            route_id: payload["routes"][route_id]["policy_health_classification"]
            for route_id in ("6", "10")
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
