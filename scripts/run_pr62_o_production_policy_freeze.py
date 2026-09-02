"""Certify and freeze the V2 one-trip-TE production operational selector."""

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

from bus_schedule_engine import service_plan_coordinator as coordinator  # noqa: E402
from bus_schedule_engine.contracts_v1.operational_selection_policy import (  # noqa: E402
    NUMERICAL_EPSILON,
)
from bus_schedule_engine.contracts_v1.operational_selection_policy_v2 import (  # noqa: E402
    DEFAULT_OPERATIONAL_SELECTION_POLICY_V2,
    PRIORITY_ORDER_V2,
    build_operational_selection_candidate_v2,
    select_operational_candidates_v2,
)

N_COMMIT_SHA = "c956284102eb307e10068c1128151943da5246d7"
V1_EXPECTED_BLOB = "1fc1097356a3db732f093ebf25dac0810a1791a7"
FROZEN_BUDGET = coordinator.CoordinatorSearchBudgetV1(24, 512, 4, 24, 512)
OUTPUT_JSON = Path("docs/engine/evidence/PR62_O_PRODUCTION_POLICY_FREEZE.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_O_PRODUCTION_POLICY_FREEZE.md")
N_JSON = Path("docs/engine/evidence/PR62_N_ONE_TRIP_POLICY_REHEARSAL.json")
N_MARKDOWN = Path("docs/engine/evidence/PR62_N_ONE_TRIP_POLICY_REHEARSAL.md")
EXPECTED_N_EVIDENCE = {
    "json": (
        N_JSON,
        20224,
        "6e15939240963171e80e20b95a4d728df8ec6ccecb3f0b6b192135fb56ad371b",
    ),
    "markdown": (
        N_MARKDOWN,
        5927,
        "bf4d4b9a9d92f3b640b2c15b3d42ba42ed47e9ad350bf39aadf10d4203f5ce4b",
    ),
}
EXPECTED_ROUTE_LOCKS = {
    "6": {
        "pareto_count": 47,
        "hard_feasible_count": 47,
        "passenger_access_safe_count": 41,
        "sse_best_count": 1,
        "te_best_count": 1,
        "materiality_set_count": 5,
        "common_anchor_fingerprint": (
            "ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b"
        ),
        "selected_pair_fingerprint": (
            "ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b"
        ),
        "classification": "ONE_TRIP_MATERIALITY_SELECTS_ANCHOR",
    },
    "10": {
        "pareto_count": 11,
        "hard_feasible_count": 11,
        "passenger_access_safe_count": 7,
        "sse_best_count": 1,
        "te_best_count": 1,
        "materiality_set_count": 2,
        "common_anchor_fingerprint": (
            "bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c"
        ),
        "selected_pair_fingerprint": (
            "e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24"
        ),
        "classification": "ONE_TRIP_MATERIALITY_SELECTS_SIMPLER_ALTERNATIVE",
    },
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _git_blob_sha1(value: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(value)}\0".encode() + value,
        usedforsecurity=False,
    ).hexdigest()


def verify_n_evidence_lock(repo_root: Path) -> dict[str, dict[str, int | str]]:
    """Fail closed unless the committed PR62-N authority is byte-identical."""

    verified: dict[str, dict[str, int | str]] = {}
    for label, (relative_path, expected_size, expected_sha) in EXPECTED_N_EVIDENCE.items():
        value = (repo_root / relative_path).read_bytes()
        actual = {"bytes": len(value), "sha256": _sha256_bytes(value)}
        if actual != {"bytes": expected_size, "sha256": expected_sha}:
            raise RuntimeError(f"PR62-N {label} evidence lock changed")
        verified[label] = actual
    return verified


def production_freeze_decision(routes: dict[str, dict[str, object]]) -> dict[str, object]:
    """Derive readiness from exact V2 pilot outputs instead of expected fingerprints alone."""

    blockers: list[str] = []
    for route_id, expected in EXPECTED_ROUTE_LOCKS.items():
        route = routes.get(route_id)
        if route is None:
            blockers.append(f"ROUTE_{route_id}_MISSING")
            continue
        selection = route.get("selection_result")
        if not isinstance(selection, dict):
            blockers.append(f"ROUTE_{route_id}_SELECTION_RESULT_MISSING")
            continue
        actual = {
            "pareto_count": route.get("pareto_count"),
            **{key: selection.get(key) for key in expected if key != "pareto_count"},
        }
        if actual != expected:
            blockers.append(f"ROUTE_{route_id}_V2_REGRESSION_LOCK_MISMATCH")
    ready = not blockers
    return {
        "cross_route_classification": (
            "ONE_TRIP_PRODUCTION_POLICY_FROZEN"
            if ready
            else "ONE_TRIP_PRODUCTION_POLICY_FREEZE_BLOCKED"
        ),
        "READY_FOR_FINAL_XLSX_RECERTIFICATION": ready,
        "blockers": blockers,
    }


def _rhythm_tuple(snapshot: Any) -> tuple[int, int, int, int]:
    return (
        snapshot.total_directional_sustained_headway_level_count,
        snapshot.actual_service_regime_count,
        snapshot.total_directional_effective_palette_count,
        snapshot.total_single_gap_regime_count,
    )


def _fleet_tuple(snapshot: Any) -> tuple[int, int, int]:
    return (
        snapshot.fleet_required,
        snapshot.total_excess_terminal_wait,
        snapshot.max_excess_terminal_wait,
    )


def _candidate_record(
    item: Any, snapshot: Any, scenario_b_access: Mapping[str, float]
) -> dict[str, Any]:
    metrics = item.metrics
    directional_maximum = {
        "outbound": snapshot.outbound_maximum_bucket_expected_wait_minutes,
        "inbound": snapshot.inbound_maximum_bucket_expected_wait_minutes,
    }
    return {
        "fingerprint": snapshot.fingerprint,
        "hard_operational_feasible": snapshot.hard_feasible,
        "hard_feasibility_reasons": list(snapshot.hard_feasibility_reasons),
        "scenario_b_directional_max_access_safe": snapshot.hard_feasible
        and all(
            directional_maximum[direction]
            <= float(scenario_b_access[direction]) + NUMERICAL_EPSILON
            for direction in ("outbound", "inbound")
        ),
        "observed_demand_mismatch": snapshot.observed_demand_mismatch,
        "outbound_trip_equivalent_error": snapshot.outbound_trip_equivalent_error,
        "inbound_trip_equivalent_error": snapshot.inbound_trip_equivalent_error,
        "pair_trip_equivalent_error": snapshot.pair_trip_equivalent_error,
        "average_wait_minutes": metrics.demand_weighted_expected_passenger_wait_minutes,
        "directional_maximum_bucket_wait_minutes": directional_maximum,
        "maximum_directional_p90_bucket_wait_minutes": (
            metrics.maximum_directional_p90_bucket_wait_minutes
        ),
        "rhythm_simplicity_tuple": list(_rhythm_tuple(snapshot)),
        "fleet_efficiency_tuple": list(_fleet_tuple(snapshot)),
        "tail_headways": {
            "outbound": item.outbound.metrics.tail_headway_minutes,
            "inbound": item.inbound.metrics.tail_headway_minutes,
        },
    }


def _best_set(records: Sequence[Mapping[str, Any]], metric: str) -> list[str]:
    best = min(float(item[metric]) for item in records)
    return sorted(
        str(item["fingerprint"])
        for item in records
        if float(item[metric]) <= best + NUMERICAL_EPSILON
    )


def _selected_vs_anchor_tradeoff(
    selected: Mapping[str, Any], anchor: Mapping[str, Any]
) -> dict[str, Any]:
    selected_access = selected["directional_maximum_bucket_wait_minutes"]
    anchor_access = anchor["directional_maximum_bucket_wait_minutes"]
    return {
        "delta_TE": float(selected["pair_trip_equivalent_error"])
        - float(anchor["pair_trip_equivalent_error"]),
        "delta_SSE": float(selected["observed_demand_mismatch"])
        - float(anchor["observed_demand_mismatch"]),
        "average_wait_delta_minutes": float(selected["average_wait_minutes"])
        - float(anchor["average_wait_minutes"]),
        "average_wait_delta_seconds_per_passenger": 60
        * (float(selected["average_wait_minutes"]) - float(anchor["average_wait_minutes"])),
        "directional_max_access_delta_minutes": {
            direction: float(selected_access[direction]) - float(anchor_access[direction])
            for direction in ("outbound", "inbound")
        },
        "maximum_directional_p90_delta_minutes": float(
            selected["maximum_directional_p90_bucket_wait_minutes"]
        )
        - float(anchor["maximum_directional_p90_bucket_wait_minutes"]),
        "fleet_required_delta": int(selected["fleet_efficiency_tuple"][0])
        - int(anchor["fleet_efficiency_tuple"][0]),
        "total_excess_terminal_wait_delta": int(selected["fleet_efficiency_tuple"][1])
        - int(anchor["fleet_efficiency_tuple"][1]),
        "max_excess_terminal_wait_delta": int(selected["fleet_efficiency_tuple"][2])
        - int(anchor["fleet_efficiency_tuple"][2]),
        "rhythm_tuple_change": {
            "anchor": list(anchor["rhythm_simplicity_tuple"]),
            "selected": list(selected["rhythm_simplicity_tuple"]),
        },
        "tail_headway_change": {
            "anchor": dict(anchor["tail_headways"]),
            "selected": dict(selected["tail_headways"]),
        },
    }


def _evaluate_route(
    *,
    repo_root: Path,
    artifact_root: Path,
    route_id: str,
    accepted_i: Mapping[str, Any],
) -> dict[str, Any]:
    workbook = repo_root / f"Engine_Input_MST_{route_id}_V3_MultiPeriod_Mar-Jul_2026.xlsx"
    context, seeds = coordinator.load_route_coordinator_inputs_v1(
        repo_root=artifact_root,
        route_id=route_id,
        workbook_path=workbook,
    )
    coordinator_result = coordinator.search_route_service_plans_v1(
        context=context,
        seeds=seeds,
        budget=FROZEN_BUDGET,
    )
    frontier = tuple(
        sorted(coordinator_result.pareto_frontier, key=lambda item: item.pair_fingerprint)
    )
    fingerprints = tuple(item.pair_fingerprint for item in frontier)
    accepted_fingerprints = tuple(
        sorted(accepted_i["routes"][route_id]["deterministic_signature"]["i_pareto_fingerprints"])
    )
    if fingerprints != accepted_fingerprints:
        raise RuntimeError(f"EVIDENCE_DRIFT: route {route_id} exact PR62-I frontier changed")
    if len(frontier) != int(EXPECTED_ROUTE_LOCKS[route_id]["pareto_count"]):
        raise RuntimeError(f"EVIDENCE_DRIFT: route {route_id} Pareto size changed")
    if any(len(item.metrics.pareto_vector) != 10 for item in frontier):
        raise RuntimeError("EVIDENCE_DRIFT: production Pareto vector is not exactly 10-D")

    scenario_b_access = {
        direction: coordinator.expected_passenger_wait_metrics_v1(
            context.scenario_b_departures[direction], context.demand_buckets[direction]
        )[1]
        for direction in ("outbound", "inbound")
    }
    snapshots = tuple(
        build_operational_selection_candidate_v2(context=context, candidate=item)
        for item in frontier
    )
    selection = select_operational_candidates_v2(
        route_id=route_id,
        candidates=snapshots,
        scenario_b_directional_maximum_wait_minutes=scenario_b_access,
    )
    records = tuple(
        _candidate_record(item, snapshot, scenario_b_access)
        for item, snapshot in zip(frontier, snapshots, strict=True)
    )
    by_fingerprint = {str(item["fingerprint"]): item for item in records}
    access_safe = tuple(
        item for item in records if bool(item["scenario_b_directional_max_access_safe"])
    )
    sse_best = _best_set(access_safe, "observed_demand_mismatch")
    te_best = _best_set(access_safe, "pair_trip_equivalent_error")
    anchor = (
        None
        if selection.common_anchor_fingerprint is None
        else by_fingerprint[selection.common_anchor_fingerprint]
    )
    selected = (
        None
        if selection.selected_pair_fingerprint is None
        else by_fingerprint[selection.selected_pair_fingerprint]
    )
    access_rejections = tuple(
        item
        for item in selection.rejected_candidates
        if item.stage == "SCENARIO_B_MAX_ACCESS_NON_REGRESSION"
    )
    access_exclusions = [
        {
            "fingerprint": rejection.fingerprint,
            "reason": rejection.reason,
            "tail_headways": dict(by_fingerprint[rejection.fingerprint]["tail_headways"]),
            "directional_maximum_bucket_wait_minutes": dict(
                by_fingerprint[rejection.fingerprint]["directional_maximum_bucket_wait_minutes"]
            ),
        }
        for rejection in access_rejections
    ]
    if route_id == "10":
        observed_extreme_tails = {
            int(item["tail_headways"]["inbound"]) for item in access_exclusions
        }
        if not {30, 45, 48, 54}.issubset(observed_extreme_tails):
            raise RuntimeError("route 10 access exclusion tail authority changed")

    materiality_trace = next(
        item for item in selection.stage_trace if item.stage == "ONE_TRIP_TE_MATERIALITY_ENVELOPE"
    )
    route_payload: dict[str, Any] = {
        "route_id": route_id,
        "search_status": coordinator_result.status,
        "search_budget": dataclasses.asdict(FROZEN_BUDGET),
        "search_statistics": dataclasses.asdict(coordinator_result.statistics),
        "pareto_count": len(frontier),
        "pareto_fingerprints": list(fingerprints),
        "pareto_dimension_count": 10,
        "selection_result": dataclasses.asdict(selection),
        "SSE_BEST_SET": sse_best,
        "TE_BEST_SET": te_best,
        "common_anchor": anchor,
        "materiality_set_fingerprints": list(materiality_trace.retained_fingerprints),
        "selected": selected,
        "selected_vs_anchor_tradeoff": (
            None
            if selected is None or anchor is None
            else _selected_vs_anchor_tradeoff(selected, anchor)
        ),
        "scenario_b_directional_maximum_wait_minutes": scenario_b_access,
        "access_exclusions": {
            "classification": "ACCESS_EXCLUDED_BEFORE_MATERIALITY",
            "candidates": access_exclusions,
        },
        "candidate_audit": list(records),
    }
    return route_payload


def build_evidence(repo_root: Path) -> dict[str, Any]:
    """Run each frozen route once and assemble production-freeze evidence."""

    if dataclasses.astuple(FROZEN_BUDGET) != (24, 512, 4, 24, 512):
        raise RuntimeError("search budgets changed")
    n_lock = verify_n_evidence_lock(repo_root)
    v1_path = repo_root / "src/bus_schedule_engine/contracts_v1/operational_selection_policy.py"
    v1_bytes = v1_path.read_bytes()
    v1_blob = _git_blob_sha1(v1_bytes)
    if v1_blob != V1_EXPECTED_BLOB:
        raise RuntimeError("historical V1 selector changed")

    accepted_i = json.loads((repo_root / pr62_i.OUTPUT_JSON).read_text(encoding="utf-8"))
    artifact_root = pr62_i._artifact_root(repo_root)
    prior_before = coordinator.verify_frozen_prior_artifacts_v1(artifact_root)
    routes = {
        route_id: _evaluate_route(
            repo_root=repo_root,
            artifact_root=artifact_root,
            route_id=route_id,
            accepted_i=accepted_i,
        )
        for route_id in ("6", "10")
    }
    prior_after = coordinator.verify_frozen_prior_artifacts_v1(artifact_root)
    if prior_before != prior_after:
        raise RuntimeError("frozen prior artifacts changed during PR62-O")

    decision = production_freeze_decision(routes)
    return {
        "milestone": "PR62-O",
        "N_commit_SHA": N_COMMIT_SHA,
        "N_evidence_lock": n_lock,
        "V1_historical_selector": {
            "profile": "domain_priority_operational_selector_v1",
            "semantics": "historical strict-SSE-first selector retained for evidence/backward compatibility",
            "git_blob_sha1": v1_blob,
            "sha256": _sha256_bytes(v1_bytes),
            "changed": False,
        },
        "V2_current_production_selector": {
            "profile": DEFAULT_OPERATIONAL_SELECTION_POLICY_V2.profile,
            "priority_order": list(PRIORITY_ORDER_V2),
            "numerical_epsilon": DEFAULT_OPERATIONAL_SELECTION_POLICY_V2.numerical_epsilon,
            "te_materiality_band_trips": (
                DEFAULT_OPERATIONAL_SELECTION_POLICY_V2.te_materiality_band_trips
            ),
            "weighted_score": False,
            "pair_fingerprint_is_quality_objective": False,
            "TE_formula": {
                "directional_TV": "0.5 * sum(abs(service_share_b - demand_share_b))",
                "directional_TE": "directional_total_trips * directional_TV",
                "pair_TE": "outbound_TE + inbound_TE",
                "authority": "ActualServiceMetricsV1 bucket counts/demand shares/service shares",
                "directions_averaged": False,
            },
            "one_trip_semantics": (
                "A 1.0 trip-equivalent concession is an operational service-allocation quantum "
                "representing equivalent service mass displaced across demand buckets; it is not "
                "a fractional physical trip, timetable-edit count, trip movement instruction, or "
                "replacement for SSE."
            ),
            "anchor_fail_closed": {
                "unique_SSE_best_required": True,
                "unique_TE_best_required": True,
                "same_fingerprint_required": True,
                "conflict": "DEMAND_FIT_ANCHOR_CONFLICT",
                "non_unique": "DEMAND_FIT_ANCHOR_NOT_UNIQUE",
                "no_V1_fallback": True,
            },
        },
        "candidate_universe": {
            "source": "exact current post-H/I immutable 10-D Pareto frontier",
            "selector_role": "post-search consumer",
            "search_run_count_per_route": 1,
            "full_10_D_Pareto_unchanged": True,
            "search_budget": dataclasses.asdict(FROZEN_BUDGET),
        },
        "routes": routes,
        **decision,
        "next_milestone": (
            "PR62-P_FINAL_XLSX_RECERTIFICATION"
            if decision["READY_FOR_FINAL_XLSX_RECERTIFICATION"]
            else None
        ),
        "production_guards": {
            "V1_selector_semantics_changed": False,
            "V2_selector_added_and_frozen": True,
            "coordinator_search_semantics_changed": False,
            "search_budgets_changed": False,
            "10_D_Pareto_semantics_changed": False,
            "compiler_changed": False,
            "compiler_path_score_changed": False,
            "tail_eligibility_changed": False,
            "protection_changed": False,
            "access_safeguard_changed": False,
            "passenger_wait_semantics_changed": False,
            "SSE_semantics_changed": False,
            "rhythm_metrics_changed": False,
            "fleet_validator_changed": False,
            "queue_changed": False,
            "F1_F2_F3_changed": False,
            "settlement_added": False,
            "final_XLSX_regenerated": False,
            "private_workbook_opened": False,
            "private_workbook_committed": False,
        },
        "deterministic_render": True,
    }


def _fmt(value: Any) -> str:
    return f"{value:.9f}" if isinstance(value, float) else str(value)


def _directional_repr(value: Mapping[str, Any]) -> str:
    return f"{{'outbound': {value['outbound']!r}, 'inbound': {value['inbound']!r}}}"


def _route_markdown(route: Mapping[str, Any]) -> list[str]:
    selection = route["selection_result"]
    anchor = route["common_anchor"]
    selected = route["selected"]
    lines = [
        f"## Route {route['route_id']}",
        "",
        f"- Pareto / hard feasible / access safe: {route['pareto_count']} / "
        f"{selection['hard_feasible_count']} / {selection['passenger_access_safe_count']}",
        f"- SSE-best / TE-best: `{route['SSE_BEST_SET']}` / `{route['TE_BEST_SET']}`",
        f"- Common anchor: `{selection['common_anchor_fingerprint']}`",
    ]
    if anchor is None or selected is None:
        lines.extend(
            [
                f"- One-trip materiality set: {selection['materiality_set_count']}",
                f"- Selected: `{selection['selected_pair_fingerprint']}`",
                f"- Classification: `{selection['classification']}`",
                "",
                "Stage trace: " + " → ".join(item["stage"] for item in selection["stage_trace"]),
            ]
        )
        return lines
    lines.extend(
        [
            f"- Anchor SSE / TE: {_fmt(anchor['observed_demand_mismatch'])} / "
            f"{_fmt(anchor['pair_trip_equivalent_error'])}",
            f"- One-trip materiality set: {selection['materiality_set_count']}",
            f"- Selected: `{selection['selected_pair_fingerprint']}`",
            f"- Selected SSE / TE: {_fmt(selected['observed_demand_mismatch'])} / "
            f"{_fmt(selected['pair_trip_equivalent_error'])}",
            f"- Average wait: {_fmt(selected['average_wait_minutes'])} minutes",
            "- Directional max access: "
            f"`{_directional_repr(selected['directional_maximum_bucket_wait_minutes'])}`",
            f"- Rhythm / fleet: `{selected['rhythm_simplicity_tuple']}` / "
            f"`{selected['fleet_efficiency_tuple']}`",
            f"- Tails: `{_directional_repr(selected['tail_headways'])}`",
            f"- Classification: `{selection['classification']}`",
            "",
            "Stage trace: " + " → ".join(item["stage"] for item in selection["stage_trace"]),
        ]
    )
    if route["route_id"] == "10":
        tradeoff = route["selected_vs_anchor_tradeoff"]
        lines.extend(
            [
                "",
                "### Selected versus anchor tradeoff",
                "",
                f"ΔTE {_fmt(tradeoff['delta_TE'])}; ΔSSE {_fmt(tradeoff['delta_SSE'])}; "
                f"Δwait {_fmt(tradeoff['average_wait_delta_seconds_per_passenger'])} "
                "seconds/passenger; "
                f"fleet {tradeoff['fleet_required_delta']:+d}; terminal excess wait "
                f"{tradeoff['total_excess_terminal_wait_delta']:+d}. Directional max access, "
                "P90, rhythm, and tail changes are serialized in JSON without suppression.",
                "",
                "Inbound-tail 30/45/48/54-minute candidates remain "
                "`ACCESS_EXCLUDED_BEFORE_MATERIALITY`; headway is evidence, not a policy rule.",
            ]
        )
    return lines


def _markdown(payload: Mapping[str, Any]) -> str:
    policy = payload["V2_current_production_selector"]
    lines = [
        "# PR62-O — One-trip TE production policy freeze",
        "",
        "V1 remains the historical strict-SSE-first selector. V2 is the current production "
        "post-search selector for future closed-loop final selection.",
        "",
        "## Frozen production hierarchy",
        "",
    ]
    lines.extend(
        f"{index}. {stage}" for index, stage in enumerate(policy["priority_order"], start=1)
    )
    lines.extend(
        [
            "",
            "The fixed materiality envelope is +1.0 pair trip-equivalent around a unique common "
            "SSE/TE anchor. Anchor conflict or ambiguity fails closed; there is no V1 fallback.",
            "",
        ]
    )
    for route_id in ("6", "10"):
        lines.extend(_route_markdown(payload["routes"][route_id]))
        lines.append("")
    lines.extend(
        [
            "## Readiness",
            "",
            f"Cross-route classification: `{payload['cross_route_classification']}`.",
            "",
            f"- `READY_FOR_FINAL_XLSX_RECERTIFICATION = "
            f"{str(payload['READY_FOR_FINAL_XLSX_RECERTIFICATION']).lower()}`",
            "- The full immutable 10-D Pareto frontier and coordinator search are unchanged.",
            "- No final XLSX was regenerated and no private workbook was opened.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_evidence(repo_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    json_first = _canonical_json_bytes(payload)
    json_second = _canonical_json_bytes(payload)
    markdown_first = _markdown(payload).encode("utf-8")
    markdown_second = _markdown(payload).encode("utf-8")
    if json_first != json_second or markdown_first != markdown_second:
        raise RuntimeError("PR62-O evidence render is not byte-identical")
    if len(json_first) >= 500_000:
        raise RuntimeError("PR62-O JSON evidence exceeds preferred 500 KB limit")
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
        "READY_FOR_FINAL_XLSX_RECERTIFICATION": payload["READY_FOR_FINAL_XLSX_RECERTIFICATION"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    payload = build_evidence(repo_root)
    print(json.dumps(_write_evidence(repo_root, payload), sort_keys=True))
    verify_n_evidence_lock(repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
