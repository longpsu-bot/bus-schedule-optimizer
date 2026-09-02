"""Generate PR62-M1 demand-fit rank-concordance clarification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from bus_schedule_engine.contracts_v1.operational_selection_policy import NUMERICAL_EPSILON

_REPO_ROOT = Path(__file__).resolve().parents[1]
M_COMMIT_SHA = "3d6ebb9c4126aca833f5d7ddce12e2fa4755442a"
M_JSON = Path("docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.json")
M_MARKDOWN = Path("docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.md")
OUTPUT_JSON = Path("docs/engine/evidence/PR62_M1_RANK_CONCORDANCE_CLARIFICATION.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_M1_RANK_CONCORDANCE_CLARIFICATION.md")
EXPECTED_M_ARTIFACTS = {
    M_JSON: {
        "sha256": "f9c5438c3d4b0b871b8fc1ec24a9dcd3a392efd76e85e7ab9ec385532c98c0c9",
        "size_bytes": 525934,
    },
    M_MARKDOWN: {
        "sha256": "b580540645bd3c941d2e14425b67f2c2773bc684a9e28836407df21f8030a309",
        "size_bytes": 5828,
    },
}
EXPECTED_CANDIDATE_COUNTS = {"6": 41, "10": 7}
EXPECTED_DISAGREEMENTS = {"6": 61, "10": 2}


def _canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fingerprint(candidate: Mapping[str, Any]) -> str:
    return str(candidate["fingerprint"])


def _rhythm(candidate: Mapping[str, Any]) -> tuple[int, int, int, int]:
    return tuple(int(value) for value in candidate["rhythm_simplicity_tuple"])  # type: ignore[return-value]


def _fleet(candidate: Mapping[str, Any]) -> tuple[int, ...]:
    return tuple(int(value) for value in candidate["fleet_efficiency_tuple"])


def _review_key(candidate: Mapping[str, Any]) -> tuple[Any, ...]:
    return (_rhythm(candidate), _fleet(candidate), _fingerprint(candidate))


def _metric_order(
    candidates: Sequence[Mapping[str, Any]], metric_key: str
) -> list[Mapping[str, Any]]:
    return sorted(candidates, key=lambda row: (float(row[metric_key]), _fingerprint(row)))


def _metric_breakpoint_path(
    candidates: Sequence[Mapping[str, Any]], *, metric_key: str, delta_key: str
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    best = min(float(candidate[metric_key]) for candidate in candidates)
    observed = sorted(max(0.0, float(candidate[metric_key]) - best) for candidate in candidates)
    deltas: list[float] = []
    for delta in observed:
        if not deltas or abs(delta - deltas[-1]) > NUMERICAL_EPSILON:
            deltas.append(delta)
    path: list[dict[str, Any]] = []
    previous: str | None = None
    for delta in deltas:
        envelope = [
            candidate
            for candidate in candidates
            if float(candidate[metric_key]) <= best + delta + NUMERICAL_EPSILON
        ]
        preferred = min(envelope, key=_review_key)
        fingerprint = _fingerprint(preferred)
        if fingerprint == previous:
            continue
        path.append(
            {
                delta_key: delta,
                "envelope_candidate_count": len(envelope),
                "preferred_fingerprint": fingerprint,
                "preferred_rhythm_simplicity_tuple": list(_rhythm(preferred)),
                "preferred_fleet_efficiency_tuple": list(_fleet(preferred)),
            }
        )
        previous = fingerprint
    return path


def _first_simpler(
    candidates: Sequence[Mapping[str, Any]], *, selected_fingerprint: str, metric_key: str
) -> Mapping[str, Any] | None:
    selected = next(
        candidate for candidate in candidates if _fingerprint(candidate) == selected_fingerprint
    )
    simpler = [candidate for candidate in candidates if _rhythm(candidate) < _rhythm(selected)]
    if not simpler:
        return None
    return min(
        simpler,
        key=lambda candidate: (
            float(candidate[metric_key]),
            _rhythm(candidate),
            _fleet(candidate),
            _fingerprint(candidate),
        ),
    )


def _add_role(roles: dict[str, set[str]], candidate: Mapping[str, Any] | None, role: str) -> None:
    if candidate is not None:
        roles.setdefault(_fingerprint(candidate), set()).add(role)


def _derive_roles(
    candidates: Sequence[Mapping[str, Any]],
    *,
    selected_fingerprint: str,
    te_path: Sequence[Mapping[str, Any]],
    sse_path: Sequence[Mapping[str, Any]],
    first_te: Mapping[str, Any] | None,
    first_sse: Mapping[str, Any] | None,
    focused_fingerprints: set[str],
) -> dict[str, set[str]]:
    roles: dict[str, set[str]] = {selected_fingerprint: {"L_SELECTED"}}
    sse_order = _metric_order(candidates, "observed_demand_mismatch")
    te_order = _metric_order(candidates, "pair_trip_equivalent_error")
    _add_role(roles, sse_order[0], "SSE_BEST")
    _add_role(roles, te_order[0], "TE_BEST")
    next_best_sse = min(
        (row for row in candidates if _fingerprint(row) != selected_fingerprint),
        key=lambda row: (float(row["observed_demand_mismatch"]), _fingerprint(row)),
        default=None,
    )
    _add_role(roles, next_best_sse, "NEXT_BEST_SSE")
    minimum_palette = min(
        candidates,
        key=lambda row: (_rhythm(row), _fingerprint(row)),
    )
    _add_role(roles, minimum_palette, "MINIMUM_SUSTAINED_PALETTE")
    _add_role(
        roles,
        min(
            candidates,
            key=lambda row: (
                int(row["fleet_required"]),
                _fleet(row),
                _fingerprint(row),
            ),
        ),
        "MINIMUM_FLEET",
    )
    _add_role(
        roles,
        min(candidates, key=lambda row: (float(row["average_wait_minutes"]), _fingerprint(row))),
        "MINIMUM_AVERAGE_WAIT",
    )
    for row in te_path:
        roles.setdefault(str(row["preferred_fingerprint"]), set()).add("TE_BREAKPOINT_PREFERRED")
    for row in sse_path:
        roles.setdefault(str(row["preferred_fingerprint"]), set()).add("SSE_BREAKPOINT_PREFERRED")
    _add_role(roles, first_te, "FIRST_TE_SIMPLER_WITNESS")
    _add_role(roles, first_sse, "FIRST_SSE_SIMPLER_WITNESS")
    for fingerprint in focused_fingerprints:
        roles.setdefault(fingerprint, set()).add("FOCUSED_ROLE_CANDIDATE")
    return roles


def _pairwise_disagreements(
    candidates: Sequence[Mapping[str, Any]], *, roles_by_fingerprint: Mapping[str, set[str]]
) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=_fingerprint)
    best_te = min(float(candidate["pair_trip_equivalent_error"]) for candidate in candidates)
    witnesses: list[dict[str, Any]] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            sse_left = float(left["observed_demand_mismatch"])
            sse_right = float(right["observed_demand_mismatch"])
            te_left = float(left["pair_trip_equivalent_error"])
            te_right = float(right["pair_trip_equivalent_error"])
            sse_delta = sse_left - sse_right
            te_delta = te_left - te_right
            if abs(sse_delta) <= NUMERICAL_EPSILON or abs(te_delta) <= NUMERICAL_EPSILON:
                continue
            if (sse_delta < 0) == (te_delta < 0):
                continue
            left_fp, right_fp = _fingerprint(left), _fingerprint(right)
            pair_roles = roles_by_fingerprint.get(left_fp, set()) | roles_by_fingerprint.get(
                right_fp, set()
            )
            tags: list[str] = []
            tag_roles = (
                ("L_SELECTED", "INVOLVES_L_SELECTED"),
                ("SSE_BEST", "INVOLVES_SSE_OR_TE_BEST"),
                ("TE_BEST", "INVOLVES_SSE_OR_TE_BEST"),
                ("NEXT_BEST_SSE", "INVOLVES_NEXT_BEST_SSE"),
                ("FOCUSED_ROLE_CANDIDATE", "INVOLVES_FOCUSED_ROLE_CANDIDATE"),
                ("TE_BREAKPOINT_PREFERRED", "INVOLVES_TE_BREAKPOINT_PREFERRED"),
                ("SSE_BREAKPOINT_PREFERRED", "INVOLVES_SSE_BREAKPOINT_PREFERRED"),
            )
            for role, tag in tag_roles:
                if role in pair_roles and tag not in tags:
                    tags.append(tag)
            if {
                "FIRST_TE_SIMPLER_WITNESS",
                "FIRST_SSE_SIMPLER_WITNESS",
            } & pair_roles:
                tags.append("INVOLVES_FIRST_SIMPLER_WITNESS")
            if te_left <= best_te + 1.0 + NUMERICAL_EPSILON and te_right <= (
                best_te + 1.0 + NUMERICAL_EPSILON
            ):
                tags.append("BOTH_WITHIN_ONE_TE_OF_BEST")
            if pair_roles:
                tags.append("DECISION_RELEVANT")
            else:
                tags.append("NON_DECISION_RELEVANT")
            witnesses.append(
                {
                    "candidate_a_fingerprint": left_fp,
                    "candidate_b_fingerprint": right_fp,
                    "SSE_a": sse_left,
                    "SSE_b": sse_right,
                    "SSE_delta_a_minus_b": sse_delta,
                    "TE_a": te_left,
                    "TE_b": te_right,
                    "TE_delta_a_minus_b": te_delta,
                    "SSE_preferred_fingerprint": left_fp if sse_delta < 0 else right_fp,
                    "TE_preferred_fingerprint": left_fp if te_delta < 0 else right_fp,
                    "relevance_tags": tags,
                }
            )
    return witnesses


def _candidate_record(
    candidate: Mapping[str, Any] | None,
    *,
    sse_best: float,
    te_best: float,
) -> dict[str, Any] | None:
    if candidate is None:
        return None
    access = candidate.get("directional_maximum_bucket_wait_minutes", {})
    return {
        "fingerprint": _fingerprint(candidate),
        "SSE": float(candidate["observed_demand_mismatch"]),
        "delta_SSE_vs_best": float(candidate["observed_demand_mismatch"]) - sse_best,
        "TE": float(candidate["pair_trip_equivalent_error"]),
        "delta_TE_vs_best": float(candidate["pair_trip_equivalent_error"]) - te_best,
        "fleet_required": int(candidate["fleet_required"]),
        "fleet_efficiency_tuple": list(_fleet(candidate)),
        "average_wait_minutes": float(candidate["average_wait_minutes"]),
        "maximum_access_minutes": max((float(value) for value in access.values()), default=None),
        "rhythm_simplicity_tuple": list(_rhythm(candidate)),
    }


def _path_comparison(
    te_path: Sequence[Mapping[str, Any]], sse_path: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    te_sequence = [str(row["preferred_fingerprint"]) for row in te_path]
    sse_sequence = [str(row["preferred_fingerprint"]) for row in sse_path]
    te_first = te_sequence[1] if len(te_sequence) > 1 else None
    sse_first = sse_sequence[1] if len(sse_sequence) > 1 else None
    max_length = max(len(te_sequence), len(sse_sequence))
    differing_positions = [
        {
            "position": index + 1,
            "TE": te_sequence[index] if index < len(te_sequence) else None,
            "SSE": sse_sequence[index] if index < len(sse_sequence) else None,
        }
        for index in range(max_length)
        if (te_sequence[index] if index < len(te_sequence) else None)
        != (sse_sequence[index] if index < len(sse_sequence) else None)
    ]
    return {
        "same_best_candidate": bool(
            te_sequence and sse_sequence and te_sequence[0] == sse_sequence[0]
        ),
        "TE_preferred_fingerprint_sequence": te_sequence,
        "SSE_preferred_fingerprint_sequence": sse_sequence,
        "exact_sequence_identical": te_sequence == sse_sequence,
        "first_preferred_change_from_best_TE": te_first,
        "first_preferred_change_from_best_SSE": sse_first,
        "same_first_preferred_change_candidate": te_first == sse_first,
        "final_preferred_candidate_TE": te_sequence[-1] if te_sequence else None,
        "final_preferred_candidate_SSE": sse_sequence[-1] if sse_sequence else None,
        "same_final_preferred_candidate": bool(
            te_sequence and sse_sequence and te_sequence[-1] == sse_sequence[-1]
        ),
        "preferred_path_overlap_count": len(set(te_sequence) & set(sse_sequence)),
        "preferred_path_union_count": len(set(te_sequence) | set(sse_sequence)),
        "differing_positions": differing_positions,
    }


def _one_te_envelope(
    candidates: Sequence[Mapping[str, Any]], roles: Mapping[str, set[str]]
) -> dict[str, Any]:
    sse_order = _metric_order(candidates, "observed_demand_mismatch")
    te_order = _metric_order(candidates, "pair_trip_equivalent_error")
    sse_ranks = {_fingerprint(row): rank for rank, row in enumerate(sse_order, start=1)}
    te_ranks = {_fingerprint(row): rank for rank, row in enumerate(te_order, start=1)}
    te_best = float(te_order[0]["pair_trip_equivalent_error"])
    envelope = [
        row
        for row in te_order
        if float(row["pair_trip_equivalent_error"]) <= te_best + 1.0 + NUMERICAL_EPSILON
    ]
    preferred = min(envelope, key=_review_key)
    disagreements = _pairwise_disagreements(envelope, roles_by_fingerprint=roles)
    return {
        "threshold_TE": 1.0,
        "diagnostic_only": True,
        "candidates": [
            {
                "fingerprint": _fingerprint(row),
                "SSE": float(row["observed_demand_mismatch"]),
                "SSE_rank": sse_ranks[_fingerprint(row)],
                "TE": float(row["pair_trip_equivalent_error"]),
                "TE_rank": te_ranks[_fingerprint(row)],
                "delta_TE_vs_best": float(row["pair_trip_equivalent_error"]) - te_best,
                "rhythm_simplicity_tuple": list(_rhythm(row)),
                "fleet_efficiency_tuple": list(_fleet(row)),
            }
            for row in envelope
        ],
        "pairwise_disagreement_count": len(disagreements),
        "pairwise_disagreements": disagreements,
        "review_preferred_fingerprint": _fingerprint(preferred),
        "rank_disagreement_changes_review_preferred_candidate": False,
        "reason": "The fixed <=1 TE envelope is reviewed by rhythm, fleet, then fingerprint; SSE/TE rank order does not change that deterministic choice.",
    }


def _classify(
    *, same_best: bool, first_te: str | None, first_sse: str | None, paths_equal: bool
) -> str:
    if not same_best:
        return "TOP_DEMAND_FIT_METRIC_CONFLICT"
    if first_te is None and first_sse is None:
        return "NO_SIMPLER_ACCESS_SAFE_ALTERNATIVE"
    if first_te != first_sse:
        return "TOP_CONCORDANT_FIRST_SIMPLICITY_CONFLICT"
    if not paths_equal:
        return "TOP_AND_FIRST_SIMPLICITY_CONCORDANT_PATH_VARIATION"
    return "TOP_AND_MATERIALITY_PATH_CONCORDANT"


def _materiality_effects(
    disagreements: list[dict[str, Any]],
    *,
    sse_best: str,
    te_best: str,
    first_sse: str | None,
    first_te: str | None,
    te_path: Sequence[Mapping[str, Any]],
    sse_path: Sequence[Mapping[str, Any]],
) -> None:
    te_members = {str(row["preferred_fingerprint"]) for row in te_path}
    sse_members = {str(row["preferred_fingerprint"]) for row in sse_path}
    for witness in disagreements:
        pair = {
            str(witness["candidate_a_fingerprint"]),
            str(witness["candidate_b_fingerprint"]),
        }
        reasons: list[str] = []
        if sse_best != te_best and {sse_best, te_best} <= pair:
            reasons.append("changes top candidate")
        if (
            first_sse != first_te
            and first_sse is not None
            and first_te is not None
            and {
                first_sse,
                first_te,
            }
            <= pair
        ):
            reasons.append("changes first simpler witness")
        if pair & te_members and pair & sse_members and te_members != sse_members:
            reasons.append("participates in differing breakpoint preferred paths")
        if "BOTH_WITHIN_ONE_TE_OF_BEST" in witness["relevance_tags"]:
            reasons.append("occurs inside the <=1 TE audit envelope without changing review order")
        if "INVOLVES_FOCUSED_ROLE_CANDIDATE" in witness["relevance_tags"]:
            reasons.append("changes a focused comparison's SSE-versus-TE ordering interpretation")
        effect_reasons = [reason for reason in reasons if "without changing" not in reason]
        witness["materiality_path_effect"] = bool(effect_reasons)
        witness["materiality_path_effect_reason"] = (
            "; ".join(reasons)
            if reasons
            else "lower-rank ordering only; no audited path role is altered"
        )


def _analyze_candidates(
    candidates: Sequence[Mapping[str, Any]],
    *,
    selected_fingerprint: str,
    focused_fingerprints: set[str] | None = None,
) -> dict[str, Any]:
    if not candidates:
        raise ValueError("rank-concordance audit requires candidates")
    if selected_fingerprint not in {_fingerprint(row) for row in candidates}:
        raise ValueError("L-selected fingerprint is absent from the candidate universe")
    te_path = _metric_breakpoint_path(
        candidates, metric_key="pair_trip_equivalent_error", delta_key="delta_TE"
    )
    sse_path = _metric_breakpoint_path(
        candidates, metric_key="observed_demand_mismatch", delta_key="delta_SSE"
    )
    first_te = _first_simpler(
        candidates,
        selected_fingerprint=selected_fingerprint,
        metric_key="pair_trip_equivalent_error",
    )
    first_sse = _first_simpler(
        candidates,
        selected_fingerprint=selected_fingerprint,
        metric_key="observed_demand_mismatch",
    )
    roles = _derive_roles(
        candidates,
        selected_fingerprint=selected_fingerprint,
        te_path=te_path,
        sse_path=sse_path,
        first_te=first_te,
        first_sse=first_sse,
        focused_fingerprints=focused_fingerprints or set(),
    )
    disagreements = _pairwise_disagreements(candidates, roles_by_fingerprint=roles)
    sse_order = _metric_order(candidates, "observed_demand_mismatch")
    te_order = _metric_order(candidates, "pair_trip_equivalent_error")
    sse_best_fp, te_best_fp = _fingerprint(sse_order[0]), _fingerprint(te_order[0])
    _materiality_effects(
        disagreements,
        sse_best=sse_best_fp,
        te_best=te_best_fp,
        first_sse=_fingerprint(first_sse) if first_sse else None,
        first_te=_fingerprint(first_te) if first_te else None,
        te_path=te_path,
        sse_path=sse_path,
    )
    path_comparison = _path_comparison(te_path, sse_path)
    sse_best = float(sse_order[0]["observed_demand_mismatch"])
    te_best = float(te_order[0]["pair_trip_equivalent_error"])
    possible_pairs = len(candidates) * (len(candidates) - 1) // 2
    first_te_fp = _fingerprint(first_te) if first_te else None
    first_sse_fp = _fingerprint(first_sse) if first_sse else None
    return {
        "candidate_count": len(candidates),
        "possible_pair_count": possible_pairs,
        "pairwise_disagreement_count": len(disagreements),
        "pairwise_disagreement_rate": len(disagreements) / possible_pairs
        if possible_pairs
        else 0.0,
        "decision_relevant_disagreement_count": sum(
            "DECISION_RELEVANT" in row["relevance_tags"] for row in disagreements
        ),
        "materiality_path_effect_disagreement_count": sum(
            bool(row["materiality_path_effect"]) for row in disagreements
        ),
        "same_best_candidate": sse_best_fp == te_best_fp,
        "top_rank_concordant": sse_best_fp == te_best_fp,
        "full_rank_concordant": not disagreements,
        "SSE_BEST": _candidate_record(sse_order[0], sse_best=sse_best, te_best=te_best),
        "TE_BEST": _candidate_record(te_order[0], sse_best=sse_best, te_best=te_best),
        "NEXT_BEST_SSE": _candidate_record(
            sse_order[1] if len(sse_order) > 1 else None, sse_best=sse_best, te_best=te_best
        ),
        "decision_roles": {key: sorted(value) for key, value in sorted(roles.items())},
        "pairwise_disagreements": disagreements,
        "TE_breakpoint_path": te_path,
        "SSE_breakpoint_path": sse_path,
        "path_comparison": path_comparison,
        "first_TE_simpler_witness": _candidate_record(first_te, sse_best=sse_best, te_best=te_best),
        "first_SSE_simpler_witness": _candidate_record(
            first_sse, sse_best=sse_best, te_best=te_best
        ),
        "first_simpler_comparison": {
            "TE_fingerprint": first_te_fp,
            "SSE_fingerprint": first_sse_fp,
            "same_candidate": first_te_fp == first_sse_fp,
        },
        "one_TE_envelope_audit": _one_te_envelope(candidates, roles),
        "classification": _classify(
            same_best=sse_best_fp == te_best_fp,
            first_te=first_te_fp,
            first_sse=first_sse_fp,
            paths_equal=bool(path_comparison["exact_sequence_identical"]),
        ),
    }


def _verify_m_artifacts(repo_root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for relative_path, expected in EXPECTED_M_ARTIFACTS.items():
        path = repo_root / relative_path
        data = path.read_bytes()
        actual = {"sha256": _sha256_bytes(data), "size_bytes": len(data)}
        if actual != expected:
            raise RuntimeError(f"PR62-M evidence drift: {relative_path}: {actual}")
        result[str(relative_path).replace("\\", "/")] = {**actual, "immutable": True}
    return result


def _focused_fingerprints(route: Mapping[str, Any]) -> set[str]:
    return {_fingerprint(row) for row in route.get("focused_comparisons", [])}


def _assert_reconstructed_te_path(
    route_id: str,
    reconstructed: Sequence[Mapping[str, Any]],
    committed: Sequence[Mapping[str, Any]],
) -> None:
    normalized = [
        {
            "delta_trip_equivalent": row["delta_TE"],
            "envelope_candidate_count": row["envelope_candidate_count"],
            "preferred_fingerprint": row["preferred_fingerprint"],
            "preferred_rhythm_simplicity_tuple": row["preferred_rhythm_simplicity_tuple"],
            "preferred_fleet_efficiency_tuple": row["preferred_fleet_efficiency_tuple"],
        }
        for row in reconstructed
    ]
    if normalized != list(committed):
        raise RuntimeError(f"Route {route_id} reconstructed TE path differs from PR62-M")


def _route_interpretation(route_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    disagreements = result["pairwise_disagreements"]
    first_te = result["first_TE_simpler_witness"]
    first_delta = first_te["delta_TE_vs_best"] if first_te else None
    beyond = [
        row
        for row in disagreements
        if first_delta is not None
        and row["TE_a"] > result["TE_BEST"]["TE"] + first_delta + NUMERICAL_EPSILON
        and row["TE_b"] > result["TE_BEST"]["TE"] + first_delta + NUMERICAL_EPSILON
    ]
    base = {
        "any_disagreement_involves_L_SELECTED": any(
            "INVOLVES_L_SELECTED" in row["relevance_tags"] for row in disagreements
        ),
        "any_disagreement_alters_SSE_BEST_vs_TE_BEST": not result["same_best_candidate"],
        "first_TE_and_SSE_simpler_same": result["first_simpler_comparison"]["same_candidate"],
        "TE_and_SSE_path_sequences_differ": not result["path_comparison"][
            "exact_sequence_identical"
        ],
        "preferred_path_differing_positions": result["path_comparison"]["differing_positions"],
        "disagreements_entirely_beyond_first_TE_simpler_breakpoint": len(beyond),
        "disagreement_concentration_basis": (
            "Count whose two candidates both lie beyond the exact first-TE-simpler breakpoint; no arbitrary threshold is used."
        ),
    }
    if route_id == "6":
        base["at_least_one_TE_conclusion_structurally_meaningful"] = bool(
            first_delta is not None
            and first_delta > 1.0 + NUMERICAL_EPSILON
            and result["same_best_candidate"]
        )
        base["structural_reason"] = (
            "The exact TE path minimizes TE across every rhythm-simpler candidate and its first simpler breakpoint remains above one TE; the SSE path is reported independently without an invented SSE threshold."
        )
    else:
        envelope = result["one_TE_envelope_audit"]
        first_fp = first_te["fingerprint"] if first_te else None
        base.update(
            {
                "exact_disagreement_pairs": [
                    [row["candidate_a_fingerprint"], row["candidate_b_fingerprint"]]
                    for row in disagreements
                ],
                "disagreement_involves_selected": any(
                    "INVOLVES_L_SELECTED" in row["relevance_tags"] for row in disagreements
                ),
                "disagreement_involves_next_best_SSE": any(
                    "INVOLVES_NEXT_BEST_SSE" in row["relevance_tags"] for row in disagreements
                ),
                "disagreement_involves_first_TE_simpler": any(
                    first_fp in {row["candidate_a_fingerprint"], row["candidate_b_fingerprint"]}
                    for row in disagreements
                ),
                "disagreement_entirely_inside_one_TE_envelope": any(
                    "BOTH_WITHIN_ONE_TE_OF_BEST" in row["relevance_tags"] for row in disagreements
                ),
                "alters_first_simpler_candidate": not result["first_simpler_comparison"][
                    "same_candidate"
                ],
                "alters_one_TE_review_preferred_candidate": envelope[
                    "rank_disagreement_changes_review_preferred_candidate"
                ],
                "sub_one_trip_simplicity_result_robust": bool(
                    first_delta is not None
                    and first_delta < 1.0 - NUMERICAL_EPSILON
                    and envelope["review_preferred_fingerprint"] == first_fp
                    and not envelope["rank_disagreement_changes_review_preferred_candidate"]
                ),
            }
        )
    return base


def build_evidence(repo_root: Path) -> dict[str, Any]:
    artifacts = _verify_m_artifacts(repo_root)
    m_payload = json.loads((repo_root / M_JSON).read_text(encoding="utf-8"))
    routes: dict[str, Any] = {}
    for route_id in ("6", "10"):
        source_route = m_payload["routes"][route_id]
        candidates = source_route["access_safe_candidates"]
        if len(candidates) != EXPECTED_CANDIDATE_COUNTS[route_id]:
            raise RuntimeError(f"Route {route_id} access-safe candidate count drift")
        result = _analyze_candidates(
            candidates,
            selected_fingerprint=str(source_route["L_selected_fingerprint"]),
            focused_fingerprints=_focused_fingerprints(source_route),
        )
        if result["pairwise_disagreement_count"] != EXPECTED_DISAGREEMENTS[route_id]:
            raise RuntimeError(f"Route {route_id} pairwise disagreement count drift")
        _assert_reconstructed_te_path(
            route_id, result["TE_breakpoint_path"], source_route["trip_equivalent_breakpoint_path"]
        )
        result["TE_path_exactly_reproduces_M"] = True
        result["interpretation"] = _route_interpretation(route_id, result)
        routes[route_id] = result
    ready = all(
        routes[route_id]["same_best_candidate"]
        and routes[route_id]["first_simpler_comparison"]["same_candidate"]
        and not routes[route_id]["interpretation"].get(
            "alters_one_TE_review_preferred_candidate", False
        )
        for route_id in ("6", "10")
    )
    if any(not routes[route_id]["same_best_candidate"] for route_id in ("6", "10")):
        cross_route = "DEMAND_FIT_METRIC_CONFLICT_REQUIRES_REVIEW"
    elif any(
        not routes[route_id]["first_simpler_comparison"]["same_candidate"]
        for route_id in ("6", "10")
    ):
        cross_route = "MATERIALITY_PATH_VARIATION_REQUIRES_POLICY_REVIEW"
    elif ready:
        cross_route = "MATERIALITY_CALIBRATION_READY_WITH_NON_TOP_RANK_DISCORDANCE"
    else:
        cross_route = "M1_EVIDENCE_INCONCLUSIVE"
    human = m_payload["human_final_route_6"]
    human_context = {
        "classification": human["classification"],
        "selection_eligible": human["selection_eligible"],
        "Human_Final_TE": human["pair_trip_equivalent_error"],
        "selected_TE": routes["6"]["TE_BEST"]["TE"],
        "selected_minus_Human_Final_SSE": human["selected_minus_human_final"][
            "observed_demand_mismatch"
        ],
        "selected_minus_Human_Final_rhythm": {
            "sustained_headway_level_count": human["selected_minus_human_final"][
                "sustained_headway_level_count"
            ],
            "effective_palette_count": human["selected_minus_human_final"][
                "effective_palette_count"
            ],
        },
        "ranking_note": "Human Final is outside the selectable universe and cannot create candidate-ranking discordance.",
    }
    return {
        "profile": "demand_fit_rank_concordance_clarification_v1",
        "M_commit_SHA": M_COMMIT_SHA,
        "M_artifacts": artifacts,
        "M_artifact_immutability": True,
        "semantic_clarification": "Same SSE/TE best candidate does not imply zero rank disagreement.",
        "concordance_distinction": {
            "TOP-RANK_CONCORDANCE": "SSE_BEST equals TE_BEST.",
            "FULL-RANK_CONCORDANCE": "No epsilon-qualified unordered candidate pair reverses SSE versus TE order.",
            "M_history": "PR62-M remains historical evidence; its classification was too coarse for lower-rank concordance analysis.",
        },
        "formulas": {
            "SSE": "observed_demand_mismatch; lower is better",
            "TE": "pair_trip_equivalent_error; lower is better",
            "sse_delta": "SSE(A) - SSE(B)",
            "te_delta": "TE(A) - TE(B)",
            "pairwise_disagreement": "abs(deltas) > NUMERICAL_EPSILON and sign(sse_delta) != sign(te_delta)",
            "possible_pair_count": "n * (n - 1) / 2",
            "review_order": "rhythm simplicity tuple, fleet efficiency tuple, fingerprint for exact metric tie",
            "numerical_epsilon": NUMERICAL_EPSILON,
        },
        "candidate_universe": "routes.<route>.access_safe_candidates from committed PR62-M only",
        "routes": routes,
        "human_final_route_6_context": human_context,
        "route_classifications": {
            route_id: routes[route_id]["classification"] for route_id in routes
        },
        "cross_route_classification": cross_route,
        "one_trip_materiality_discussion_can_proceed": cross_route
        == "MATERIALITY_CALIBRATION_READY_WITH_NON_TOP_RANK_DISCORDANCE",
        "one_trip_threshold_implemented": False,
        "deterministic_render": {"rendered_twice_byte_identical": True},
        "production_guards": {
            "Coordinator search changed": "NO",
            "10-D Pareto changed": "NO",
            "L selector changed": "NO",
            "SSE mismatch semantics changed": "NO",
            "TE semantics changed": "NO",
            "One-trip threshold added": "NO",
            "Access guardrail changed": "NO",
            "Compiler changed": "NO",
            "Tail eligibility changed": "NO",
            "Rhythm semantics changed": "NO",
            "Fleet validator changed": "NO",
            "Queue changed": "NO",
            "Budgets changed": "NO",
            "Settlement added": "NO",
            "Final XLSX regenerated": "NO",
            "Private workbook opened": "NO",
            "Private workbook committed": "NO",
            "M artifacts modified": "NO",
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
        "# PR62-M1 — Demand-fit rank-concordance clarification",
        "",
        "Same SSE/TE best candidate does not imply zero rank disagreement.",
        "",
        "TOP-RANK CONCORDANCE means the two metrics select the same best candidate. FULL-RANK CONCORDANCE means every epsilon-qualified candidate pair has the same relative ordering.",
        "",
    ]
    for route_id in ("6", "10"):
        route = payload.get("routes", {}).get(route_id)
        if not route:
            continue
        lines.extend(
            [
                f"## Route {route_id}",
                "",
                f"Candidates `{route['candidate_count']}`; possible pairs `{route['possible_pair_count']}`; disagreements `{route['pairwise_disagreement_count']}` ({route['pairwise_disagreement_rate']:.6%}); decision-relevant `{route['decision_relevant_disagreement_count']}`; materiality-path effect `{route['materiality_path_effect_disagreement_count']}`.",
                "",
                f"SSE best: `{route['SSE_BEST']['fingerprint']}`. TE best: `{route['TE_BEST']['fingerprint']}`. Same: `{route['same_best_candidate']}`.",
                "",
                f"First SSE simpler: `{route['first_simpler_comparison']['SSE_fingerprint']}`. First TE simpler: `{route['first_simpler_comparison']['TE_fingerprint']}`. Same: `{route['first_simpler_comparison']['same_candidate']}`.",
                "",
                "TE path: "
                + " -> ".join(route["path_comparison"]["TE_preferred_fingerprint_sequence"]),
                "",
                "SSE path: "
                + " -> ".join(route["path_comparison"]["SSE_preferred_fingerprint_sequence"]),
                "",
                f"Exact path sequence identical: `{route['path_comparison']['exact_sequence_identical']}`; final candidate same: `{route['path_comparison']['same_final_preferred_candidate']}`; overlap/union `{route['path_comparison']['preferred_path_overlap_count']}/{route['path_comparison']['preferred_path_union_count']}`.",
                "",
                f"Classification: `{route['classification']}`.",
                "",
            ]
        )
        if route_id == "6":
            interpretation = route["interpretation"]
            lines.extend(
                [
                    "### Required review",
                    "",
                    f"- Any disagreement involves L_SELECTED: `{interpretation['any_disagreement_involves_L_SELECTED']}`.",
                    f"- Any disagreement alters SSE_BEST versus TE_BEST: `{interpretation['any_disagreement_alters_SSE_BEST_vs_TE_BEST']}`.",
                    f"- FIRST_TE_SIMPLER equals FIRST_SSE_SIMPLER: `{interpretation['first_TE_and_SSE_simpler_same']}`.",
                    f"- TE and SSE preferred paths differ: `{interpretation['TE_and_SSE_path_sequences_differ']}`.",
                    f"- Differing path positions: `{json.dumps(interpretation['preferred_path_differing_positions'], sort_keys=True)}`.",
                    f"Disagreements with both candidates beyond the exact first-TE-simpler breakpoint: `{interpretation['disagreements_entirely_beyond_first_TE_simpler_breakpoint']}`.",
                    "",
                    f"The at-least-one-TE conclusion remains structurally meaningful: `{interpretation['at_least_one_TE_conclusion_structurally_meaningful']}`. {interpretation['structural_reason']}",
                    "",
                ]
            )
        else:
            lines.extend(["### Exact disagreement pairs", ""])
            for witness in route["pairwise_disagreements"]:
                lines.append(
                    f"- `{witness['candidate_a_fingerprint']}` vs `{witness['candidate_b_fingerprint']}`; SSE prefers `{witness['SSE_preferred_fingerprint']}`; TE prefers `{witness['TE_preferred_fingerprint']}`; tags: {', '.join(witness['relevance_tags'])}."
                )
            envelope = route["one_TE_envelope_audit"]
            lines.extend(
                [
                    "",
                    f"Involves L_SELECTED: `{route['interpretation']['disagreement_involves_selected']}`; NEXT_BEST_SSE: `{route['interpretation']['disagreement_involves_next_best_SSE']}`; +0.712251 first-TE-simpler witness: `{route['interpretation']['disagreement_involves_first_TE_simpler']}`; any pair entirely inside <=1 TE: `{route['interpretation']['disagreement_entirely_inside_one_TE_envelope']}`.",
                    "",
                    "### Route 10 <=1 TE envelope",
                    "",
                    "| fingerprint | ΔTE | SSE rank | TE rank | rhythm | fleet |",
                    "|---|---:|---:|---:|---|---|",
                ]
            )
            for row in envelope["candidates"]:
                lines.append(
                    f"| `{row['fingerprint']}` | {_fmt(row['delta_TE_vs_best'])} | {row['SSE_rank']} | {row['TE_rank']} | {tuple(row['rhythm_simplicity_tuple'])} | {tuple(row['fleet_efficiency_tuple'])} |"
                )
            lines.extend(
                [
                    "",
                    f"Review preferred: `{envelope['review_preferred_fingerprint']}`. In-envelope disagreements: `{envelope['pairwise_disagreement_count']}`. Changes review preference: `{envelope['rank_disagreement_changes_review_preferred_candidate']}`.",
                    "",
                    f"Sub-one-trip simplicity result robust: `{route['interpretation']['sub_one_trip_simplicity_result_robust']}`.",
                    "",
                ]
            )
    if payload.get("human_final_route_6_context"):
        human = payload["human_final_route_6_context"]
        lines.extend(
            [
                "## Route 6 Human Final context",
                "",
                f"Human Final is `{human['classification']}` and is not selectable. Human Final TE `{_fmt(human['Human_Final_TE'])}`; selected TE `{_fmt(human['selected_TE'])}`; selected-minus-Human-Final SSE `{_fmt(human['selected_minus_Human_Final_SSE'], 9)}`.",
                "",
                f"Selected-minus-Human-Final rhythm: sustained headway levels `{human['selected_minus_Human_Final_rhythm']['sustained_headway_level_count']}`; effective palette `{human['selected_minus_Human_Final_rhythm']['effective_palette_count']}`.",
                "",
                human["ranking_note"],
                "",
            ]
        )
    if payload.get("cross_route_classification"):
        lines.extend(
            [
                "## Policy readiness",
                "",
                f"Cross-route classification: `{payload['cross_route_classification']}`.",
                "",
                f"One-trip materiality discussion can proceed: `{payload['one_trip_materiality_discussion_can_proceed']}`. No threshold is implemented.",
                "",
                "PR62-M remains unchanged historical evidence. Its classification was too coarse for lower-rank concordance analysis.",
                "",
                "## Production guards",
                "",
            ]
        )
        for key, value in payload["production_guards"].items():
            lines.append(f"- {key}: **{value}**")
    return "\n".join(lines) + "\n"


def _write_evidence(repo_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    json_first = _canonical_json_bytes(payload)
    json_second = _canonical_json_bytes(payload)
    markdown_first = _markdown(payload).encode("utf-8")
    markdown_second = _markdown(payload).encode("utf-8")
    if json_first != json_second or markdown_first != markdown_second:
        raise RuntimeError("PR62-M1 evidence render is not byte-identical")
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
    _verify_m_artifacts(repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
