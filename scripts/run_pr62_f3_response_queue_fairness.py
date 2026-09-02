"""Generate compact PR62-F3 bounded response-queue fairness evidence."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
_SCRIPTS = _REPO_ROOT / "scripts"
for _root in (_SRC, _SCRIPTS):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import run_pr62_e_closed_loop_pilot as pilot  # noqa: E402

from bus_schedule_engine.service_plan_coordinator import (  # noqa: E402
    DEMAND_RESPONSE_DIRECTION_MISMATCH,
    load_route_coordinator_inputs_v1,
)

PROFILE = "pr62_f3_response_queue_fairness_v1"
REQUIRED_STARTING_SHA = "473afa9e542b38936be69e3f7463df8649c0ef58"
F2_PATH = Path("docs/engine/evidence/PR62_F2_FLEET_NEIGHBORHOOD_NARROWING.json")
OUTPUT_JSON = Path("docs/engine/evidence/PR62_F3_RESPONSE_QUEUE_FAIRNESS.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_F3_RESPONSE_QUEUE_FAIRNESS.md")
MAX_JSON_BYTES = 1024 * 1024


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _response_accuracy_range(result: Any) -> dict[str, float] | None:
    values = [
        record.metrics.demand_response_direction_accuracy
        for pair in result.pareto_frontier
        for record in (pair.outbound, pair.inbound)
        if record.metrics.demand_response_direction_accuracy is not None
    ]
    if not values:
        return None
    return {"minimum": min(values), "maximum": max(values)}


def _frontier(result: Any) -> dict[str, Any]:
    ranges = pilot._metric_ranges(result)
    return {
        "pareto_size": len(result.pareto_frontier),
        "metric_ranges": {
            "fleet_required": ranges["fleet_required"],
            "demand_weighted_expected_passenger_wait_minutes": ranges[
                "demand_weighted_expected_passenger_wait_minutes"
            ],
            "observed_demand_mismatch": ranges["observed_demand_mismatch"],
            "demand_response_direction_accuracy": _response_accuracy_range(result),
        },
        "representative": pilot._representative(result),
    }


def _route_evidence(
    *,
    route_id: str,
    result: Any,
    audit: Any,
    signature: dict[str, Any],
    f2: dict[str, Any],
) -> dict[str, Any]:
    response = pilot._feedback_effectiveness(result, audit)[DEMAND_RESPONSE_DIRECTION_MISMATCH]
    blockers, settlement = pilot._blocker_and_settlement(result, audit)
    stats = dataclasses.asdict(result.statistics)
    return {
        "route_id": route_id,
        "f2": {
            "search": f2["after_pr62_f2"],
            "frontier": f2["frontier"]["pr62_f2"],
        },
        "f3": {
            "status": result.status,
            "search_statistics": stats,
            "response_mismatch": {
                **response,
                "anchor_candidate_count": stats["response_feedback_anchor_candidates"],
                "anchors_enqueued": stats["response_feedback_anchors_enqueued"],
                "anchors_evaluated": stats["response_feedback_anchors_evaluated"],
                "anchor_fingerprints_by_direction": dict(
                    sorted(audit.response_anchor_fingerprints.items())
                ),
            },
            "frontier": _frontier(result),
            "final_directional_archive_sizes": {
                direction: len(audit.archives[direction]) for direction in ("outbound", "inbound")
            },
            "clean_boundary_blocker_count": len(blockers),
            "settlement_classification": settlement,
        },
        "determinism": {
            "passed": True,
            "signature_sha256": pilot._fingerprint(signature),
            "compared_fields": list(signature),
        },
    }


def _classification(routes: dict[str, Any]) -> str:
    fairness = all(
        route["f3"]["response_mismatch"]["anchors_enqueued"] == 2
        and route["f3"]["response_mismatch"]["anchors_evaluated"] == 2
        and set(route["f3"]["response_mismatch"]["anchor_fingerprints_by_direction"])
        == {"outbound", "inbound"}
        for route in routes.values()
    )
    if not fairness:
        return "QUEUE_FAIRNESS_STILL_INSUFFICIENT"
    useful = any(
        route["f3"]["response_mismatch"][field] > 0
        for route in routes.values()
        for field in (
            "retained_directional_compilations",
            "feasible_pair_participation",
            "final_pareto_ancestry",
        )
    )
    return (
        "RESPONSE_FAIRNESS_SUFFICIENT" if useful else "RESPONSE_REVISIONS_EVALUATED_BUT_NOT_USEFUL"
    )


def build_evidence(
    route_workbooks: dict[str, Path], *, input_artifact_root: Path
) -> dict[str, Any]:
    f2_bytes = (_REPO_ROOT / F2_PATH).read_bytes()
    f2_payload = json.loads(f2_bytes)
    prior_manifest = _REPO_ROOT / "config/service_plan_coordinator_frozen_prior_v1.json"
    prior_before = _sha256(prior_manifest.read_bytes())
    routes: dict[str, Any] = {}
    for route_id in ("6", "10"):
        context, seeds = load_route_coordinator_inputs_v1(
            repo_root=input_artifact_root,
            route_id=route_id,
            workbook_path=route_workbooks[route_id],
        )
        pilot._authority_payload(context)
        print(f"route={route_id} replay=1 starting", flush=True)
        first_result, first_audit = pilot._audited_run(context, seeds)
        print(f"route={route_id} replay=2 starting", flush=True)
        second_result, second_audit = pilot._audited_run(context, seeds)
        prior_after = _sha256(prior_manifest.read_bytes())
        prior = {
            "unchanged": prior_before == prior_after,
            "before": prior_before,
            "after": prior_after,
        }
        first_signature = pilot._result_signature(first_result, first_audit, prior)
        second_signature = pilot._result_signature(second_result, second_audit, prior)
        if first_signature != second_signature:
            raise RuntimeError(f"Route {route_id} deterministic replay failed")
        routes[route_id] = _route_evidence(
            route_id=route_id,
            result=first_result,
            audit=first_audit,
            signature=first_signature,
            f2=f2_payload["routes"][route_id],
        )
        print(
            f"route={route_id} generated={first_result.statistics.states_generated} "
            f"evaluated={first_result.statistics.states_evaluated} "
            f"anchors={first_result.statistics.response_feedback_anchors_evaluated} "
            f"pareto={len(first_result.pareto_frontier)} replay=passed",
            flush=True,
        )

    classification = _classification(routes)
    settlements = {route["f3"]["settlement_classification"] for route in routes.values()}
    return {
        "evidence_profile": PROFILE,
        "required_starting_sha": REQUIRED_STARTING_SHA,
        "f2_artifact": {
            "committed_head_sha": REQUIRED_STARTING_SHA,
            "path": F2_PATH.as_posix(),
            "size_bytes": len(f2_bytes),
            "sha256": _sha256(f2_bytes),
        },
        "pilot_inputs": {
            "generated_artifact_root": input_artifact_root.name,
            "read_only_untracked_inputs_committed": False,
            "route_workbook_basenames": {
                route_id: route_workbooks[route_id].name for route_id in ("6", "10")
            },
        },
        "queue_lane_semantics": {
            "lane_0": "seed states",
            "lane_1": (
                "at most one selected DEMAND_RESPONSE_DIRECTION_MISMATCH anchor per direction"
            ),
            "lane_2_plus": "ordinary revision children at neighbor.priority + 2",
            "ordinary_relative_quality_order": [
                "operator priority",
                "precompile demand mismatch",
                "ServiceRegime count",
                "trip-count vector",
                "boundaries",
                "direction",
                "semantic fingerprint",
            ],
            "anchor_selection": (
                "minimum eligible unseen response child under its ordinary semantic queue key"
            ),
            "maximum_special_anchors_per_route": 2,
        },
        "routes": routes,
        "post_f3_decision": {
            "classification": classification,
            "settlement_classification": (
                "SETTLEMENT_NOT_CURRENTLY_NEEDED"
                if settlements == {"SETTLEMENT_NOT_CURRENTLY_NEEDED"}
                else "F3_EVIDENCE_INCONCLUSIVE"
            ),
            "search_controller_adequate_for_final_timetable_selection": (
                classification == "RESPONSE_FAIRNESS_SUFFICIENT"
            ),
        },
        "production_change_statement": {
            "production_search_controller_semantics_changed": True,
            "queue_ordering_changed": True,
            "queue_ordering_change_scope": "bounded response-anchor lane only",
            "d1_queue_identity_changed": False,
            "f1_idempotence_changed": False,
            "f2_fleet_family_changed": False,
            "search_budgets_changed": False,
            "pareto_changed": False,
            "compiler_changed": False,
            "fleet_validator_changed": False,
            "demand_response_diagnosis_changed": False,
            "settlement_added": False,
        },
    }


def _range_text(value: dict[str, Any] | None, digits: int) -> str:
    if value is None:
        return "n/a"
    return f"{value['minimum']:.{digits}f}\u2013{value['maximum']:.{digits}f}"


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# PR62-F3 \u2014 Bounded demand-response exploration fairness",
        "",
        "Seeds remain first. Each direction may reserve one response anchor in lane 1; all "
        "ordinary revisions retain their prior relative order in lane 2+.",
        "",
        "## F2 \u2192 F3 response effectiveness",
        "",
        "| Route | Children F2 \u2192 F3 | Anchor candidate / enqueued / evaluated | "
        "Evaluated descendants F2 \u2192 F3 | Retained F2 \u2192 F3 | Feasible pairs F2 \u2192 F3 | "
        "Pareto ancestry F2 \u2192 F3 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for route_id in ("6", "10"):
        route = payload["routes"][route_id]
        before = route["f2"]["search"]["response_mismatch"]
        after = route["f3"]["response_mismatch"]
        lines.append(
            f"| {route_id} | {before['generated_child_states']} \u2192 "
            f"{after['generated_child_states']} | {after['anchor_candidate_count']} / "
            f"{after['anchors_enqueued']} / {after['anchors_evaluated']} | "
            f"{before['evaluated_descendants']} \u2192 {after['evaluated_descendants']} | "
            f"{before['retained_directional_compilations']} \u2192 "
            f"{after['retained_directional_compilations']} | "
            f"{before.get('feasible_pair_participation', 0)} \u2192 "
            f"{after['feasible_pair_participation']} | "
            f"{before['final_pareto_ancestry']} \u2192 {after['final_pareto_ancestry']} |"
        )
    lines.extend(["", "## Frontier", ""])
    for route_id in ("6", "10"):
        route = payload["routes"][route_id]
        before = route["f2"]["frontier"]
        after = route["f3"]["frontier"]
        before_ranges = before["metric_ranges"]
        after_ranges = after["metric_ranges"]
        representative = after["representative"]
        prior_representative = before["representative"]
        representative_changed = (
            prior_representative["pair_fingerprint"] != representative["pair_fingerprint"]
        )

        def regime_identity(rows: list[dict[str, Any]]) -> tuple[tuple[Any, ...], ...]:
            return tuple(
                (
                    row["first_departure"],
                    row["last_departure"],
                    row["trip_count"],
                    row["uniform_headway_minutes"],
                )
                for row in rows
            )

        regimes_changed = any(
            regime_identity(prior_representative[f"{direction}_service_regimes"])
            != regime_identity(representative[f"{direction}_service_regimes"])
            for direction in ("outbound", "inbound")
        )
        lines.extend(
            [
                f"### Route {route_id}",
                "",
                f"Pareto {before['pareto_size']} \u2192 {after['pareto_size']}; fleet "
                f"{_range_text(before_ranges['fleet_required'], 0)} \u2192 "
                f"{_range_text(after_ranges['fleet_required'], 0)}; wait "
                f"{_range_text(before_ranges['demand_weighted_expected_passenger_wait_minutes'], 6)} \u2192 "
                f"{_range_text(after_ranges['demand_weighted_expected_passenger_wait_minutes'], 6)}; "
                f"mismatch {_range_text(before_ranges['observed_demand_mismatch'], 6)} \u2192 "
                f"{_range_text(after_ranges['observed_demand_mismatch'], 6)}; response accuracy "
                f"{_range_text(before_ranges['demand_response_direction_accuracy'], 6)} \u2192 "
                f"{_range_text(after_ranges['demand_response_direction_accuracy'], 6)}.",
                "",
                f"Representative `{representative['pair_fingerprint']}`: fleet "
                f"{representative['metrics']['fleet_required']}, wait "
                f"{representative['metrics']['demand_weighted_expected_passenger_wait_minutes']:.6f}, "
                f"mismatch {representative['metrics']['observed_demand_mismatch']:.6f}. "
                f"Pair changed: {str(representative_changed).lower()}; ServiceRegimes changed: "
                f"{str(regimes_changed).lower()}.",
                "",
            ]
        )
    decision = payload["post_f3_decision"]
    lines.extend(
        [
            "## Decision and guards",
            "",
            f"Classification: **{decision['classification']}**.",
            f"Settlement: **{decision['settlement_classification']}**.",
            "",
            "Production search-controller semantics changed: yes; queue ordering changed only "
            "for the bounded response-anchor lane. D1 identity, F1 idempotence, the F2 fleet "
            "family, budgets, Pareto, compiler, fleet validator, demand-response diagnosis, "
            "and settlement remain unchanged.",
            "",
            "Both routes replayed twice with equal statistics, response-anchor fingerprints, "
            "evaluated fingerprints, feedback counts, and Pareto fingerprints.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_twice(path: Path, first: bytes, second: bytes) -> dict[str, Any]:
    if first != second:
        raise RuntimeError(f"non-deterministic rendering for {path}")
    absolute = _REPO_ROOT / path
    absolute.write_bytes(first)
    first_disk = absolute.read_bytes()
    absolute.write_bytes(second)
    second_disk = absolute.read_bytes()
    if first_disk != second_disk:
        raise RuntimeError(f"non-deterministic repeated generation for {path}")
    return {
        "path": path.as_posix(),
        "size_bytes": len(second_disk),
        "sha256": _sha256(second_disk),
        "byte_identical_repeated_generation": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--route-6-workbook",
        type=Path,
        default=_REPO_ROOT / "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    )
    parser.add_argument(
        "--route-10-workbook",
        type=Path,
        default=_REPO_ROOT / "Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    )
    parser.add_argument(
        "--input-artifact-root",
        type=Path,
        default=_REPO_ROOT / "bus-schedule-optimizer-main-run",
    )
    parser.add_argument("--render-existing-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = (
        json.loads((_REPO_ROOT / OUTPUT_JSON).read_text(encoding="utf-8"))
        if args.render_existing_only
        else build_evidence(
            {"6": args.route_6_workbook, "10": args.route_10_workbook},
            input_artifact_root=args.input_artifact_root,
        )
    )
    json_first = _canonical_json(payload)
    json_second = _canonical_json(payload)
    if len(json_first) >= MAX_JSON_BYTES:
        raise RuntimeError(f"F3 JSON exceeds 1 MiB: {len(json_first)} bytes")
    markdown_first = render_markdown(payload).encode("utf-8")
    markdown_second = render_markdown(payload).encode("utf-8")
    artifacts = [
        _write_twice(OUTPUT_JSON, json_first, json_second),
        _write_twice(OUTPUT_MARKDOWN, markdown_first, markdown_second),
    ]
    print(json.dumps({"artifacts": artifacts}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
