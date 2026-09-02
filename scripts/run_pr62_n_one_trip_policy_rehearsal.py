"""Generate PR62-N one-trip TE materiality policy rehearsal evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from bus_schedule_engine.contracts_v1.operational_selection_policy import NUMERICAL_EPSILON

_REPO_ROOT = Path(__file__).resolve().parents[1]
TE_MATERIALITY_BAND_TRIPS = 1.0
M1_COMMIT_SHA = "1902ac4e4b4d523d81a5a3d6d527c91fc8077b54"
OUTPUT_JSON = Path("docs/engine/evidence/PR62_N_ONE_TRIP_POLICY_REHEARSAL.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_N_ONE_TRIP_POLICY_REHEARSAL.md")
L_JSON = Path("docs/engine/evidence/PR62_L_DOMAIN_PRIORITY_SELECTOR.json")
L_MARKDOWN = Path("docs/engine/evidence/PR62_L_DOMAIN_PRIORITY_SELECTOR.md")
M_JSON = Path("docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.json")
M_MARKDOWN = Path("docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.md")
M1_JSON = Path("docs/engine/evidence/PR62_M1_RANK_CONCORDANCE_CLARIFICATION.json")
M1_MARKDOWN = Path("docs/engine/evidence/PR62_M1_RANK_CONCORDANCE_CLARIFICATION.md")
EXPECTED_UPSTREAM_ARTIFACTS = {
    L_JSON: (450425, "91925a47e27abdcf524c73b38c33cd446559b887a32f6708f624eacc3e62b843"),
    L_MARKDOWN: (4623, "a1106de9c6d0f33d56de8eb8c71433edbaed4ba5e86ec79d1c6fece597e013f0"),
    M_JSON: (525934, "f9c5438c3d4b0b871b8fc1ec24a9dcd3a392efd76e85e7ab9ec385532c98c0c9"),
    M_MARKDOWN: (5828, "b580540645bd3c941d2e14425b67f2c2773bc684a9e28836407df21f8030a309"),
    M1_JSON: (99878, "fcb77df73cc5bdf39738a7e81300456870938cab489144fbe2f59a414fbffcda"),
    M1_MARKDOWN: (6815, "ba9e989643a96dbee2079e104913355ca8b8184892ee4ca9599b9c3f89024cbf"),
}


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fingerprint(candidate: Mapping[str, Any]) -> str:
    return str(candidate["fingerprint"])


def _rhythm(candidate: Mapping[str, Any]) -> tuple[int, int, int, int]:
    values = candidate["rhythm_simplicity_tuple"]
    return tuple(int(value) for value in values)  # type: ignore[return-value]


def _fleet(candidate: Mapping[str, Any]) -> tuple[int, int, int]:
    values = candidate["fleet_efficiency_tuple"]
    return tuple(int(value) for value in values)  # type: ignore[return-value]


def _metric_best(candidates: Sequence[Mapping[str, Any]], metric: str) -> Mapping[str, Any]:
    return min(candidates, key=lambda row: (float(row[metric]), _fingerprint(row)))


def _metric_ranks(candidates: Sequence[Mapping[str, Any]], metric: str) -> dict[str, int]:
    ordered = sorted(candidates, key=lambda row: (float(row[metric]), _fingerprint(row)))
    return {_fingerprint(row): index + 1 for index, row in enumerate(ordered)}


def _pairwise_rank_disagreement_count(candidates: Sequence[Mapping[str, Any]]) -> int:
    count = 0
    ordered = sorted(candidates, key=_fingerprint)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            sse_delta = float(left["observed_demand_mismatch"]) - float(
                right["observed_demand_mismatch"]
            )
            te_delta = float(left["pair_trip_equivalent_error"]) - float(
                right["pair_trip_equivalent_error"]
            )
            if abs(sse_delta) <= NUMERICAL_EPSILON or abs(te_delta) <= NUMERICAL_EPSILON:
                continue
            if (sse_delta < 0) != (te_delta < 0):
                count += 1
    return count


def _candidate_record(
    candidate: Mapping[str, Any],
    *,
    anchor_te: float,
    sse_ranks: Mapping[str, int],
    te_ranks: Mapping[str, int],
) -> dict[str, Any]:
    fingerprint = _fingerprint(candidate)
    return {
        "fingerprint": fingerprint,
        "SSE": float(candidate["observed_demand_mismatch"]),
        "TE": float(candidate["pair_trip_equivalent_error"]),
        "delta_TE": float(candidate["pair_trip_equivalent_error"]) - anchor_te,
        "SSE_rank": sse_ranks[fingerprint],
        "TE_rank": te_ranks[fingerprint],
        "average_wait_minutes": float(candidate.get("average_wait_minutes", 0.0)),
        "directional_maximum_bucket_wait_minutes": dict(
            candidate.get("directional_maximum_bucket_wait_minutes", {})
        ),
        "maximum_directional_p90_bucket_wait_minutes": candidate.get(
            "maximum_directional_p90_bucket_wait_minutes"
        ),
        "rhythm_simplicity_tuple": list(_rhythm(candidate)),
        "fleet_efficiency_tuple": list(_fleet(candidate)),
        "tail_headways": dict(candidate.get("tail_headways", {})),
    }


def _stopped_result(
    classification: str,
    *,
    stage_counts: Mapping[str, int],
    top_anchor_concordant: bool,
) -> dict[str, Any]:
    return {
        "classification": classification,
        "policy_health": "REHEARSAL_POLICY_BLOCKED",
        "top_anchor_concordant": top_anchor_concordant,
        "in_band_selection_deterministic": False,
        "in_band_pairwise_rank_disagreement_count": 0,
        "common_demand_fit_anchor": None,
        "materiality_set": [],
        "selected": None,
        "selection_detail_classification": None,
        "stage_counts": dict(stage_counts),
    }


def rehearse_route(candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Apply the review-only staged N policy to supplied candidate evidence."""
    feasible = [row for row in candidates if bool(row.get("hard_operational_feasible", True))]
    access_safe = [
        row for row in feasible if bool(row.get("scenario_b_directional_max_access_safe", True))
    ]
    stage_counts = {
        "input_candidates": len(candidates),
        "hard_operational_feasible": len(feasible),
        "directional_access_safe": len(access_safe),
    }
    if not feasible:
        return _stopped_result(
            "N_EVIDENCE_INCONCLUSIVE",
            stage_counts=stage_counts,
            top_anchor_concordant=False,
        )
    if not access_safe:
        return _stopped_result(
            "ACCESS_GUARDRAIL_TOO_RESTRICTIVE",
            stage_counts=stage_counts,
            top_anchor_concordant=False,
        )

    sse_best = _metric_best(access_safe, "observed_demand_mismatch")
    te_best = _metric_best(access_safe, "pair_trip_equivalent_error")
    top_anchor_concordant = _fingerprint(sse_best) == _fingerprint(te_best)
    if not top_anchor_concordant:
        result = _stopped_result(
            "DEMAND_FIT_ANCHOR_CONFLICT",
            stage_counts=stage_counts,
            top_anchor_concordant=False,
        )
        result["SSE_BEST"] = _fingerprint(sse_best)
        result["TE_BEST"] = _fingerprint(te_best)
        return result

    anchor = sse_best
    anchor_te = float(anchor["pair_trip_equivalent_error"])
    deltas = [float(row["pair_trip_equivalent_error"]) - anchor_te for row in access_safe]
    if any(delta < -NUMERICAL_EPSILON for delta in deltas):
        return _stopped_result(
            "N_EVIDENCE_INCONCLUSIVE",
            stage_counts=stage_counts,
            top_anchor_concordant=True,
        )
    materiality = [
        row
        for row, delta in zip(access_safe, deltas, strict=True)
        if delta >= -NUMERICAL_EPSILON and delta <= TE_MATERIALITY_BAND_TRIPS + NUMERICAL_EPSILON
    ]
    if not materiality:
        return _stopped_result(
            "N_EVIDENCE_INCONCLUSIVE",
            stage_counts=stage_counts,
            top_anchor_concordant=True,
        )

    best_rhythm = min(_rhythm(row) for row in materiality)
    rhythm_survivors = [row for row in materiality if _rhythm(row) == best_rhythm]
    best_fleet = min(_fleet(row) for row in rhythm_survivors)
    fleet_survivors = [row for row in rhythm_survivors if _fleet(row) == best_fleet]
    selected = min(fleet_survivors, key=_fingerprint)
    metrically_tied = len(fleet_survivors) > 1
    selected_is_anchor = _fingerprint(selected) == _fingerprint(anchor)
    if metrically_tied:
        classification = "ONE_TRIP_BAND_METRICALLY_EQUIVALENT_TIE"
        detail = "METRICALLY_EQUIVALENT_DETERMINISTIC_TIEBREAK"
    elif selected_is_anchor:
        classification = "ONE_TRIP_BAND_SELECTS_ANCHOR"
        detail = None
    else:
        classification = "ONE_TRIP_BAND_SELECTS_SIMPLER_ALTERNATIVE"
        detail = None

    sse_ranks = _metric_ranks(access_safe, "observed_demand_mismatch")
    te_ranks = _metric_ranks(access_safe, "pair_trip_equivalent_error")
    materiality_records = [
        _candidate_record(
            row,
            anchor_te=anchor_te,
            sse_ranks=sse_ranks,
            te_ranks=te_ranks,
        )
        for row in sorted(
            materiality,
            key=lambda row: (float(row["pair_trip_equivalent_error"]), _fingerprint(row)),
        )
    ]
    anchor_record = _candidate_record(
        anchor,
        anchor_te=anchor_te,
        sse_ranks=sse_ranks,
        te_ranks=te_ranks,
    )
    selected_record = _candidate_record(
        selected,
        anchor_te=anchor_te,
        sse_ranks=sse_ranks,
        te_ranks=te_ranks,
    )
    simpler_in_band = [
        row
        for row in materiality_records
        if tuple(row["rhythm_simplicity_tuple"]) < _rhythm(anchor)
    ]
    health = (
        "REHEARSAL_POLICY_COHERENT_BUT_COMPLEX_ANCHOR_RETAINED"
        if selected_is_anchor and not metrically_tied
        else "REHEARSAL_POLICY_COHERENT_SIMPLICITY_GAIN"
        if not selected_is_anchor and not metrically_tied
        else "REHEARSAL_POLICY_COHERENT"
    )
    stage_counts.update(
        {
            "demand_fit_anchor_consistent": 1,
            "demand_fit_materiality_set": len(materiality),
            "best_rhythm_within_materiality_set": len(rhythm_survivors),
            "best_fleet_within_materiality_set": len(fleet_survivors),
        }
    )
    return {
        "classification": classification,
        "selection_detail_classification": detail,
        "policy_health": health,
        "top_anchor_concordant": True,
        "in_band_selection_deterministic": True,
        "in_band_pairwise_rank_disagreement_count": _pairwise_rank_disagreement_count(materiality),
        "common_demand_fit_anchor": anchor_record,
        "TE_anchor": anchor_te,
        "materiality_set": materiality_records,
        "materiality_set_size": len(materiality_records),
        "rhythm_simpler_than_anchor_in_band": bool(simpler_in_band),
        "rhythm_simpler_candidates_in_band": simpler_in_band,
        "BEST_RHYTHM_WITHIN_MATERIALITY_SET": [_fingerprint(row) for row in rhythm_survivors],
        "BEST_FLEET_WITHIN_MATERIALITY_SET": [_fingerprint(row) for row in fleet_survivors],
        "selected": selected_record,
        "stage_counts": stage_counts,
    }


def _verify_upstream_artifacts(repo_root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for relative_path, (expected_size, expected_digest) in EXPECTED_UPSTREAM_ARTIFACTS.items():
        path = repo_root / relative_path
        value = path.read_bytes()
        actual_digest = _sha256_bytes(value)
        if len(value) != expected_size or actual_digest != expected_digest:
            raise RuntimeError(f"upstream artifact changed: {relative_path}")
        records[str(relative_path).replace("\\", "/")] = {
            "size_bytes": len(value),
            "sha256": actual_digest,
        }
    return records


def _load_json(repo_root: Path, relative_path: Path) -> dict[str, Any]:
    return json.loads((repo_root / relative_path).read_text(encoding="utf-8"))


def _add_l_metrics(
    candidates: Sequence[Mapping[str, Any]], l_route: Mapping[str, Any]
) -> list[dict[str, Any]]:
    l_by_fingerprint = {_fingerprint(row): row for row in l_route["candidate_audit"]}
    enriched: list[dict[str, Any]] = []
    for candidate in candidates:
        row = dict(candidate)
        l_row = l_by_fingerprint[_fingerprint(candidate)]
        row["hard_operational_feasible"] = bool(l_row["hard_feasible"])
        row["scenario_b_directional_max_access_safe"] = bool(l_row["access_safe"])
        row["maximum_directional_p90_bucket_wait_minutes"] = l_row.get(
            "maximum_directional_p90_bucket_wait_minutes"
        )
        enriched.append(row)
    return enriched


def _selected_vs_anchor_tradeoff(route: Mapping[str, Any]) -> dict[str, Any]:
    anchor = route["common_demand_fit_anchor"]
    selected = route["selected"]
    anchor_access = anchor["directional_maximum_bucket_wait_minutes"]
    selected_access = selected["directional_maximum_bucket_wait_minutes"]
    anchor_tails = anchor["tail_headways"]
    selected_tails = selected["tail_headways"]
    wait_delta = selected["average_wait_minutes"] - anchor["average_wait_minutes"]
    anchor_p90 = anchor.get("maximum_directional_p90_bucket_wait_minutes")
    selected_p90 = selected.get("maximum_directional_p90_bucket_wait_minutes")
    return {
        "delta_SSE": selected["SSE"] - anchor["SSE"],
        "delta_TE": selected["TE"] - anchor["TE"],
        "average_wait_delta_minutes": wait_delta,
        "average_wait_delta_seconds_per_passenger": wait_delta * 60.0,
        "directional_max_access_delta_minutes": {
            direction: float(selected_access[direction]) - float(anchor_access[direction])
            for direction in ("outbound", "inbound")
        },
        "maximum_directional_p90_delta_minutes": (
            None if anchor_p90 is None or selected_p90 is None else selected_p90 - anchor_p90
        ),
        "fleet_required_delta": selected["fleet_efficiency_tuple"][0]
        - anchor["fleet_efficiency_tuple"][0],
        "total_excess_terminal_wait_delta": selected["fleet_efficiency_tuple"][1]
        - anchor["fleet_efficiency_tuple"][1],
        "max_excess_terminal_wait_delta": selected["fleet_efficiency_tuple"][2]
        - anchor["fleet_efficiency_tuple"][2],
        "rhythm_tuple_anchor": anchor["rhythm_simplicity_tuple"],
        "rhythm_tuple_selected": selected["rhythm_simplicity_tuple"],
        "tail_headway_delta_minutes": {
            direction: int(selected_tails[direction]) - int(anchor_tails[direction])
            for direction in ("outbound", "inbound")
        },
    }


def _human_final_context(m_route: Mapping[str, Any]) -> dict[str, Any]:
    human = m_route["human_final_comparison"]
    delta = human["selected_minus_human_final"]
    return {
        "classification": "POST_SEARCH_EXPERT_BENCHMARK",
        "selection_eligible": False,
        "Human_Final_TE": human["pair_trip_equivalent_error"],
        "anchor_TE": human["pair_trip_equivalent_error"] + delta["pair_trip_equivalent_error"],
        "SSE_relationship": "anchor_better",
        "rhythm_relationship": "anchor_more_complex_on_frozen_first_component",
        "fleet_relationship": "anchor_requires_one_more_vehicle",
        "wait_relationship": "anchor_has_lower_average_wait",
        "anchor_minus_human_final": delta,
        "Human_Final_tail_headways": human["tail_headways"],
    }


def build_evidence(repo_root: Path) -> dict[str, Any]:
    artifacts = _verify_upstream_artifacts(repo_root)
    l_payload = _load_json(repo_root, L_JSON)
    m_payload = _load_json(repo_root, M_JSON)
    m1_payload = _load_json(repo_root, M1_JSON)
    routes: dict[str, Any] = {}
    for route_id in ("6", "10"):
        candidates = _add_l_metrics(
            m_payload["routes"][route_id]["access_safe_candidates"],
            l_payload["routes"][route_id],
        )
        result = rehearse_route(candidates)
        result["route_id"] = route_id
        result["M1_in_band_pairwise_rank_disagreement_count"] = m1_payload["routes"][route_id][
            "one_TE_envelope_audit"
        ]["pairwise_disagreement_count"]
        if (
            result["in_band_pairwise_rank_disagreement_count"]
            != result["M1_in_band_pairwise_rank_disagreement_count"]
        ):
            raise RuntimeError(f"route {route_id} in-band disagreement count drifted")
        result["lower_rank_disagreement_policy"] = (
            "SSE establishes the common best-demand-fit anchor; TE fixes the operational "
            "materiality envelope; rhythm and then fleet select inside that envelope. "
            "SSE and TE are not treated as interchangeable rankings."
        )
        if route_id == "6":
            result["human_final_context"] = _human_final_context(m_payload["routes"][route_id])
        else:
            result["selected_vs_anchor_tradeoff"] = _selected_vs_anchor_tradeoff(result)
            result["access_exclusions"] = {
                "classification": "ACCESS_EXCLUDED_BEFORE_MATERIALITY",
                "candidates": m_payload["routes"][route_id]["extreme_tail_candidates"],
                "policy_effect": "TE tolerance cannot rescue schedules excluded by access.",
            }
        routes[route_id] = result

    coherent = all(
        route["policy_health"] != "REHEARSAL_POLICY_BLOCKED" for route in routes.values()
    )
    cross_route = (
        "ONE_TRIP_POLICY_REHEARSAL_SUPPORTED"
        if coherent
        else "ONE_TRIP_POLICY_REHEARSAL_NOT_SUPPORTED"
    )
    return {
        "profile": "PR62-N_ONE_TRIP_TE_MATERIALITY_POLICY_REHEARSAL",
        "M1_commit_SHA": M1_COMMIT_SHA,
        "upstream_evidence_artifacts": artifacts,
        "policy_stages": [
            "HARD_OPERATIONAL_FEASIBILITY",
            "DIRECTIONAL_SCENARIO_B_MAX_ACCESS_SAFEGUARD",
            "DEMAND_FIT_ANCHOR_CONSISTENCY",
            "ONE_TRIP_TE_MATERIALITY_ENVELOPE",
            "RHYTHM_SIMPLICITY",
            "FLEET_EFFICIENCY",
        ],
        "TE_MATERIALITY_BAND_TRIPS": TE_MATERIALITY_BAND_TRIPS,
        "one_trip_semantics": (
            "A 1.0 trip-equivalent concession means service-share allocation differs from "
            "the TE-best allocation by no more than one equivalent directional trip of "
            "service mass across the pair. It is an operational quantum, not a literal "
            "fractional trip or a timetable edit."
        ),
        "metric_roles": {
            "observed_demand_mismatch": "authoritative production demand-fit anchor metric",
            "pair_trip_equivalent_error": "review-only operational materiality diagnostic",
            "scalar_blend": False,
            "full_rank_concordance_required": False,
            "SSE_tolerance_created": False,
        },
        "routes": routes,
        "cross_route_classification": cross_route,
        "READY_FOR_ONE_TRIP_POLICY_FREEZE": cross_route == "ONE_TRIP_POLICY_REHEARSAL_SUPPORTED",
        "READY_FOR_FINAL_XLSX_RECERTIFICATION": False,
        "production_guards": {
            "coordinator_search_changed": False,
            "10_D_Pareto_changed": False,
            "production_L_selector_changed": False,
            "SSE_semantics_changed": False,
            "TE_semantics_changed": False,
            "compiler_changed": False,
            "tail_eligibility_changed": False,
            "access_guardrail_changed": False,
            "rhythm_semantics_changed": False,
            "fleet_validator_changed": False,
            "queue_changed": False,
            "budgets_changed": False,
            "settlement_added": False,
            "final_XLSX_regenerated": False,
            "private_workbook_opened": False,
            "private_workbook_committed": False,
            "one_trip_threshold_used_in_rehearsal": True,
            "one_trip_threshold_added_to_production_selector": False,
        },
        "deterministic_render": True,
    }


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.9f}"
    return str(value)


def _route_markdown(route: Mapping[str, Any]) -> list[str]:
    anchor = route["common_demand_fit_anchor"]
    selected = route["selected"]
    lines = [
        f"## Route {route['route_id']}",
        "",
        f"- Classification: `{route['classification']}`",
        f"- Policy health: `{route['policy_health']}`",
        f"- Common SSE/TE anchor: `{anchor['fingerprint']}`",
        f"- Anchor TE: {_fmt(anchor['TE'])}",
        f"- Materiality-set size: {route['materiality_set_size']}",
        f"- Rhythm-simpler member in band: {str(route['rhythm_simpler_than_anchor_in_band']).lower()}",
        f"- Selected: `{selected['fingerprint']}`",
        f"- Selected SSE / TE: {_fmt(selected['SSE'])} / {_fmt(selected['TE'])}",
        f"- Selected average wait: {_fmt(selected['average_wait_minutes'])} minutes",
        f"- Selected directional max access: `{selected['directional_maximum_bucket_wait_minutes']}`",
        f"- Selected rhythm / fleet: `{selected['rhythm_simplicity_tuple']}` / `{selected['fleet_efficiency_tuple']}`",
        f"- Selected tails: `{selected['tail_headways']}`",
        f"- Top anchor concordant: {str(route['top_anchor_concordant']).lower()}",
        f"- In-band deterministic: {str(route['in_band_selection_deterministic']).lower()}",
        f"- In-band SSE/TE pairwise disagreements: {route['in_band_pairwise_rank_disagreement_count']}",
        "",
        "### Materiality set",
        "",
        "| Fingerprint | SSE | TE | delta TE | SSE rank | TE rank | Avg wait | Max OB/IB | Rhythm | Fleet | Tails |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for row in route["materiality_set"]:
        access = row["directional_maximum_bucket_wait_minutes"]
        tails = row["tail_headways"]
        lines.append(
            f"| `{row['fingerprint']}` | {_fmt(row['SSE'])} | {_fmt(row['TE'])} | "
            f"{_fmt(row['delta_TE'])} | {row['SSE_rank']} | {row['TE_rank']} | "
            f"{_fmt(row['average_wait_minutes'])} | {_fmt(access.get('outbound'))} / "
            f"{_fmt(access.get('inbound'))} | `{row['rhythm_simplicity_tuple']}` | "
            f"`{row['fleet_efficiency_tuple']}` | `{tails}` |"
        )
    if route["route_id"] == "6":
        human = route["human_final_context"]
        lines.extend(
            [
                "",
                "### Human Final context",
                "",
                f"Human Final remains `{human['classification']}` and is not selection eligible. "
                f"Its TE is {_fmt(human['Human_Final_TE'])}, versus anchor TE "
                f"{_fmt(human['anchor_TE'])}. The anchor has better SSE and average wait, "
                "is lexicographically more complex on the first rhythm component, and needs "
                "one more vehicle.",
            ]
        )
    else:
        tradeoff = route["selected_vs_anchor_tradeoff"]
        lines.extend(
            [
                "",
                "### Selected versus anchor tradeoff",
                "",
                f"The simplicity gain concedes {_fmt(tradeoff['delta_TE'])} TE and "
                f"{_fmt(tradeoff['delta_SSE'])} SSE. Average wait changes by "
                f"{_fmt(tradeoff['average_wait_delta_minutes'])} minutes "
                f"({_fmt(tradeoff['average_wait_delta_seconds_per_passenger'])} "
                "seconds/passenger); fleet changes by "
                f"{tradeoff['fleet_required_delta']} vehicle and total terminal excess wait "
                f"by {tradeoff['total_excess_terminal_wait_delta']} minutes. Max-access, P90, "
                "rhythm, and tail effects are serialized without suppression in JSON.",
                "",
                "The 30/45/48/54-minute extreme-tail candidates are "
                "`ACCESS_EXCLUDED_BEFORE_MATERIALITY`; TE tolerance cannot rescue them.",
            ]
        )
    return lines


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# PR62-N — One-trip TE materiality policy rehearsal",
        "",
        "This is a post-search rehearsal only. SSE remains the authoritative demand-fit "
        "anchor; TE defines a fixed one-trip operational materiality envelope; frozen rhythm "
        "simplicity selects inside that envelope; fleet efficiency acts only after an exact "
        "rhythm tie.",
        "",
        "A one-trip-equivalent concession is an interpretable service-mass allocation quantum. "
        "It is not a literal fractional trip and does not describe timetable edits. No SSE "
        "tolerance, SSE/TE blend, or full-rank concordance requirement is introduced.",
        "",
        "## Policy stages",
        "",
    ]
    lines.extend(
        f"{index}. {stage.replace('_', ' ').title()}"
        for index, stage in enumerate(payload["policy_stages"], start=1)
    )
    lines.append("")
    for route_id in ("6", "10"):
        lines.extend(_route_markdown(payload["routes"][route_id]))
        lines.append("")
    lines.extend(
        [
            "## Decision",
            "",
            f"Cross-route classification: `{payload['cross_route_classification']}`.",
            "",
            f"- `READY_FOR_ONE_TRIP_POLICY_FREEZE = {str(payload['READY_FOR_ONE_TRIP_POLICY_FREEZE']).lower()}`",
            f"- `READY_FOR_FINAL_XLSX_RECERTIFICATION = {str(payload['READY_FOR_FINAL_XLSX_RECERTIFICATION']).lower()}`",
            "",
            "Lower-rank SSE/TE disagreement is acceptable here because the top anchor is common, "
            "the TE envelope is fixed, selection inside it is deterministic, and all candidates "
            "are feasibility/access safe. This gives SSE and TE distinct roles rather than "
            "treating them as interchangeable rankings.",
            "",
            "## Production guards",
            "",
            "Production selector, coordinator search, 10-D Pareto, compiler, access, rhythm, "
            "fleet validation, queue, budgets, and tail eligibility are unchanged. No final XLSX "
            "was regenerated and no private workbook was opened or committed. The one-trip "
            "threshold exists only in this rehearsal.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_evidence(repo_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    json_first = _canonical_json_bytes(payload)
    json_second = _canonical_json_bytes(payload)
    markdown_first = _markdown(payload).encode()
    markdown_second = _markdown(payload).encode()
    if json_first != json_second or markdown_first != markdown_second:
        raise RuntimeError("non-deterministic evidence render")
    if len(json_first) >= 500_000:
        raise RuntimeError("JSON evidence exceeds preferred 500 KB limit")
    json_path = repo_root / OUTPUT_JSON
    markdown_path = repo_root / OUTPUT_MARKDOWN
    json_path.write_bytes(json_first)
    markdown_path.write_bytes(markdown_first)
    return {
        "json": str(json_path),
        "json_sha256": _sha256_bytes(json_first),
        "json_bytes": len(json_first),
        "markdown": str(markdown_path),
        "markdown_sha256": _sha256_bytes(markdown_first),
        "markdown_bytes": len(markdown_first),
        "cross_route_classification": payload["cross_route_classification"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=_REPO_ROOT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    payload = build_evidence(repo_root)
    print(json.dumps(_write_evidence(repo_root, payload), sort_keys=True))
    _verify_upstream_artifacts(repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
