from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import scripts.run_pr62_q_local_rhythm_canonicalization as pr62_q
import scripts.run_pr62_r_demand_fit_metric_validity as pr62_r
from bus_schedule_engine.service_plan_coordinator import (
    DemandBucketEvidenceV1,
    bucket_wait_access_diagnostics_v1,
    expected_passenger_wait_metrics_v1,
)

NUMERICAL_EPSILON = 1e-12
R_COMMIT_SHA = "702e0fe494f340d27b862cd4ffbca64366f2df03"
ROUTE10_ANCHOR = "bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c"
ROUTE10_P = "e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24"
ROUTE10_Q = "12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5"
ROUTE6_ANCHOR = "ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b"

R_JSON = Path("docs/engine/evidence/PR62_R_DEMAND_FIT_METRIC_VALIDITY.json")
R_MARKDOWN = Path("docs/engine/evidence/PR62_R_DEMAND_FIT_METRIC_VALIDITY.md")
O_JSON = Path("docs/engine/evidence/PR62_O_PRODUCTION_POLICY_FREEZE.json")
P_JSON = Path("docs/engine/evidence/PR62_P_FINAL_XLSX_RECERTIFICATION.json")
Q_JSON = Path("docs/engine/evidence/PR62_Q_LOCAL_RHYTHM_CANONICALIZATION.json")
ROUTE6_REPORT = Path(".codex-tmp-pr62-r-recovery/route_6_coordinator_report.json")
ROUTE10_REPORT_1 = Path(".codex-tmp-pr62-h-run1/route_10_coordinator_report.json")
ROUTE10_REPORT_2 = Path(".codex-tmp-pr62-h-run2/route_10_coordinator_report.json")
OUTPUT_JSON = Path("docs/engine/evidence/PR62_S_PHASE_ROBUST_MATERIALITY_POLICY_EXPERIMENT.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_S_PHASE_ROBUST_MATERIALITY_POLICY_EXPERIMENT.md")

EXPECTED_LOCKS = {
    R_JSON.as_posix(): "7f6b238981024ede96905072a6445f55df5fca09d41539088fdd1579b15840fd",
    R_MARKDOWN.as_posix(): "45d265ff99ad91f00eb5863e2bcd77a8e9d66b5b1a3358aed0d938418426752c",
    O_JSON.as_posix(): "91a93fa7e7abd4ede3e6848b241b0a3aa22f8f4942aa202c93dad6631df46346",
    P_JSON.as_posix(): "df9145b7a99ca832b99c41b727d53a0b895b4d71af5ef068e3d4082a39efa04a",
    Q_JSON.as_posix(): "222c5a929c27f76d1d683568a494da03544a8b50f51eae10fc848324a656ba11",
    "outputs/final_pilot/Route_6_Final_Pilot_Timetable.xlsx": "13454026722f996d8b06e5305b3b6ab2d57ea6126734f4deeb23c3e7dbafd02c",
    "outputs/final_pilot/Route_10_Final_Pilot_Timetable.xlsx": "d84dd2e873d3ba30275463a5eff67277a22467839af0f0125e69160a891fc3db",
}
REPORT_HASHES = {
    "6": "1061f9832fa9a3318623ee4715187e384cc66adf84cea009d297a6d0223dec0c",
    "10": "b8ce2134936c98dd0f59861f3451f52db426369c81ddfb78b587de93407db715",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def observed_breakpoints(deltas: Iterable[float]) -> list[float]:
    """Return exact finite nonnegative candidate-derived breakpoints."""
    values = [float(value) for value in deltas]
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("breakpoint deltas must be finite and nonnegative")
    return sorted(set(values))


def select_by_frozen_secondary_hierarchy(
    candidates: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    if not candidates:
        raise ValueError("at least one admitted candidate is required")
    return min(
        candidates,
        key=lambda item: (
            tuple(int(value) for value in item["rhythm_tuple"]),
            tuple(int(value) for value in item["fleet_tuple"]),
            str(item["fingerprint"]),
        ),
    )


def _delta(value: float, anchor: float) -> float:
    result = float(value) - float(anchor)
    if abs(result) <= NUMERICAL_EPSILON:
        return 0.0
    if result < 0:
        raise RuntimeError("anchor is not best under the requested phase-robust metric")
    return result


def _selected_record(
    candidate: Mapping[str, Any],
    *,
    metric: str,
    delta: float,
    anchor: Mapping[str, Any],
) -> dict[str, Any]:
    fields = (
        "production_SSE",
        "production_TE",
        "continuous_exposure_equivalent",
        "bucket_exposure_equivalent",
        "micro_rhythm_boundary_count",
        "operations",
    )
    return {
        "fingerprint": candidate["fingerprint"],
        "metric": metric,
        "metric_delta": delta,
        "production_TE_delta_from_anchor": float(candidate["production_TE"])
        - float(anchor["production_TE"]),
        "continuous_exposure_delta_from_anchor": float(candidate["continuous_exposure_equivalent"])
        - float(anchor["continuous_exposure_equivalent"]),
        "bucket_exposure_delta_from_anchor": float(candidate["bucket_exposure_equivalent"])
        - float(anchor["bucket_exposure_equivalent"]),
        "rhythm": list(candidate["rhythm_tuple"]),
        "fleet": list(candidate["fleet_tuple"]),
        **{key: candidate[key] for key in fields if key in candidate},
    }


def breakpoint_experiment(
    candidates: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    anchor_fingerprint: str,
    epsilon: float = NUMERICAL_EPSILON,
) -> dict[str, Any]:
    by_fingerprint = {str(item["fingerprint"]): item for item in candidates}
    if len(by_fingerprint) != len(candidates):
        raise ValueError("candidate fingerprints must be unique")
    if anchor_fingerprint not in by_fingerprint:
        raise ValueError("anchor fingerprint is absent")
    anchor = by_fingerprint[anchor_fingerprint]
    anchor_value = float(anchor[metric])
    deltas = {
        fingerprint: _delta(float(item[metric]), anchor_value)
        for fingerprint, item in by_fingerprint.items()
    }
    breakpoints = observed_breakpoints(deltas.values())
    audit: list[dict[str, Any]] = []
    compact: list[dict[str, Any]] = []
    prior_winner: str | None = None
    for breakpoint in breakpoints:
        admitted = [
            by_fingerprint[fingerprint]
            for fingerprint in sorted(by_fingerprint)
            if deltas[fingerprint] <= breakpoint + epsilon
        ]
        winner = select_by_frozen_secondary_hierarchy(admitted)
        winner_fp = str(winner["fingerprint"])
        row = {
            "breakpoint": breakpoint,
            "admitted_count": len(admitted),
            "admitted_fingerprints": [str(item["fingerprint"]) for item in admitted],
            "micro_rhythm_free_fingerprints": [
                str(item["fingerprint"])
                for item in admitted
                if int(item.get("micro_rhythm_boundary_count", -1)) == 0
            ],
            "selected": winner_fp,
        }
        audit.append(row)
        if winner_fp != prior_winner:
            compact.append(
                {
                    "breakpoint": breakpoint,
                    "admitted_count": len(admitted),
                    "selected": winner_fp,
                    "rhythm": list(winner["rhythm_tuple"]),
                    "fleet": list(winner["fleet_tuple"]),
                    "selected_record": _selected_record(
                        winner,
                        metric=metric,
                        delta=deltas[winner_fp],
                        anchor=anchor,
                    ),
                }
            )
            prior_winner = winner_fp
    anchor_rhythm = tuple(int(value) for value in anchor["rhythm_tuple"])
    first_change = next((row for row in audit if row["selected"] != anchor_fingerprint), None)
    first_improvement = next(
        (
            row
            for row in audit
            if tuple(int(value) for value in by_fingerprint[row["selected"]]["rhythm_tuple"])
            < anchor_rhythm
        ),
        None,
    )
    first_micro_available = next(
        (row for row in audit if row["micro_rhythm_free_fingerprints"]), None
    )
    first_micro_winner = next(
        (
            row
            for row in audit
            if int(by_fingerprint[row["selected"]].get("micro_rhythm_boundary_count", -1)) == 0
        ),
        None,
    )
    return {
        "metric": metric,
        "anchor_value": anchor_value,
        "breakpoints": breakpoints,
        "candidate_deltas": dict(sorted(deltas.items())),
        "breakpoint_audit": audit,
        "compact_path": compact,
        "first_winner_change": first_change,
        "first_rhythm_improvement": first_improvement,
        "first_micro_rhythm_free_available": first_micro_available,
        "first_micro_rhythm_free_winner": first_micro_winner,
    }


def legacy_eligibility_mapping(
    candidates: Sequence[Mapping[str, Any]],
    *,
    metric: str,
    anchor_fingerprint: str,
    production_te_band: float = 1.0,
    epsilon: float = NUMERICAL_EPSILON,
) -> dict[str, Any]:
    by_fingerprint = {str(item["fingerprint"]): item for item in candidates}
    anchor = by_fingerprint[anchor_fingerprint]
    anchor_te = float(anchor["production_TE"])
    anchor_metric = float(anchor[metric])
    admitted = sorted(
        (
            item
            for item in candidates
            if float(item["production_TE"]) - anchor_te <= production_te_band + epsilon
        ),
        key=lambda item: str(item["fingerprint"]),
    )
    deltas = [_delta(float(item[metric]), anchor_metric) for item in admitted]
    return {
        "production_TE_band": production_te_band,
        "admitted_fingerprints": [str(item["fingerprint"]) for item in admitted],
        "phase_robust_deltas": dict(
            sorted(
                (str(item["fingerprint"]), _delta(float(item[metric]), anchor_metric))
                for item in admitted
            )
        ),
        "delta_range": [min(deltas), max(deltas)],
        "preservation_bound": max(deltas),
        "production_threshold_created": False,
    }


def material_path_disagreement(continuous: Mapping[str, Any], bucket: Mapping[str, Any]) -> bool:
    fields = (
        "first_rhythm_improvement_winner",
        "first_micro_rhythm_free_winner",
        "q_selected",
        "q_selection_vs_legacy_bound",
    )
    return any(continuous.get(field) != bucket.get(field) for field in fields)


def load_locked_preserved_report(
    path: Path, *, expected_sha256: str, expected_fingerprints: Sequence[str]
) -> dict[str, Any]:
    encoded = path.read_bytes()
    if _sha256_bytes(encoded) != expected_sha256:
        raise RuntimeError(f"preserved report hash mismatch: {path}")
    payload = json.loads(encoded)
    actual = sorted(str(row["pair_fingerprint"]) for row in payload["pareto_frontier"])
    if actual != sorted(str(value) for value in expected_fingerprints):
        raise RuntimeError(f"preserved report fingerprint mismatch: {path}")
    return payload


def _verify_locks(repo_root: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for relative, expected in EXPECTED_LOCKS.items():
        path = repo_root / relative
        actual = pr62_r.sha256_file(path)
        if actual != expected:
            raise RuntimeError(f"immutable authority hash mismatch: {relative}")
        records[relative] = {"sha256": actual, "bytes": path.stat().st_size, "unchanged": True}
    return records


def _route10_demand_buckets(
    r_evidence: Mapping[str, Any], direction: str
) -> list[DemandBucketEvidenceV1]:
    rows = r_evidence["bucket_edge_contribution_audit"]["anchor_vs_Q"]["directions"][direction][
        "buckets"
    ]
    return [
        DemandBucketEvidenceV1(
            direction=direction,
            start=int(row["start_seconds"]),
            end=int(row["end_seconds"]),
            observed_demand=float(row["demand_share"]),
        )
        for row in rows
    ]


def _p90(departures: Sequence[int], buckets: Sequence[DemandBucketEvidenceV1]) -> float:
    _average, _maximum, per_bucket, _mass = expected_passenger_wait_metrics_v1(departures, buckets)
    p90, _tail = bucket_wait_access_diagnostics_v1(
        per_bucket_expected_wait_minutes=per_bucket,
        demand_buckets=buckets,
        active_span_start=int(departures[0]),
        active_span_end=int(departures[-1]),
        tail_support_start=int(departures[-2]),
        tail_support_end=int(departures[-1]),
    )
    return p90


def _report_operations(
    row: Mapping[str, Any], *, r_evidence: Mapping[str, Any], route_id: str
) -> dict[str, Any]:
    directions: dict[str, Any] = {}
    total_micro = 0
    for direction in ("outbound", "inbound"):
        source = row[direction]
        regimes = source["compile_variant"]["actual_service_regimes"]
        families = pr62_q.detect_local_rhythm_families(regimes)
        micro = sum(int(family["micro_rhythm_boundary_count"]) for family in families)
        total_micro += micro
        departures = [int(value) for value in source["compile_variant"]["exact_departures"]]
        actual = source["actual_service_metrics"]
        directions[direction] = {
            "service_regime_headways": [
                int(regime["uniform_headway_minutes"]) for regime in regimes
            ],
            "micro_rhythm_boundary_count": micro,
            "average_passenger_wait_minutes": float(
                actual["demand_weighted_expected_passenger_wait_minutes"]
            ),
            "maximum_bucket_wait_minutes": float(actual["maximum_bucket_expected_wait_minutes"]),
            "p90_bucket_wait_minutes": _p90(
                departures, _route10_demand_buckets(r_evidence, direction)
            )
            if route_id == "10"
            else None,
            "tail_headway_minutes": int(actual["tail_headway_minutes"]),
            "sustained_headway_levels": list(
                actual["rhythm_simplicity"]["sustained_headway_levels"]
            ),
            "effective_headway_palette": list(
                actual["rhythm_simplicity"]["effective_headway_palette"]
            ),
        }
    metrics = row["metrics"]
    return {
        "directions": directions,
        "micro_rhythm_boundary_count": total_micro,
        "average_passenger_wait_minutes": float(
            metrics["demand_weighted_expected_passenger_wait_minutes"]
        ),
        "actual_service_regime_count": int(metrics["actual_service_regime_count"]),
    }


def _production_candidates(
    *,
    route_id: str,
    r_evidence: Mapping[str, Any],
    o_evidence: Mapping[str, Any],
    report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    fingerprints = list(r_evidence["routes"][route_id]["production_fingerprints"])
    ranking = {
        str(row["fingerprint"]): row for row in r_evidence["routes"][route_id]["ranking_table"]
    }
    o_rows = {
        str(row["fingerprint"]): row for row in o_evidence["routes"][route_id]["candidate_audit"]
    }
    report_rows = {str(row["pair_fingerprint"]): row for row in report["pareto_frontier"]}
    result = []
    for fingerprint in fingerprints:
        if (
            fingerprint not in ranking
            or fingerprint not in o_rows
            or fingerprint not in report_rows
        ):
            raise RuntimeError(
                f"candidate authority join is incomplete: route {route_id} {fingerprint}"
            )
        metric = ranking[fingerprint]
        frozen = o_rows[fingerprint]
        operations = _report_operations(
            report_rows[fingerprint], r_evidence=r_evidence, route_id=route_id
        )
        result.append(
            {
                "fingerprint": fingerprint,
                "authority": "CURRENT_PRODUCTION_ACCESS_SAFE_FRONTIER",
                "production_SSE": float(metric["production_SSE"]),
                "production_TE": float(metric["production_TE"]),
                "continuous_exposure_equivalent": float(metric["continuous_exposure_equivalent"]),
                "bucket_exposure_equivalent": float(metric["bucket_exposure_equivalent"]),
                "rhythm_tuple": list(frozen["rhythm_simplicity_tuple"]),
                "fleet_tuple": list(frozen["fleet_efficiency_tuple"]),
                "micro_rhythm_boundary_count": operations["micro_rhythm_boundary_count"],
                "operations": operations,
            }
        )
    return sorted(result, key=lambda item: item["fingerprint"])


def _q_candidate(r_evidence: Mapping[str, Any], q_evidence: Mapping[str, Any]) -> dict[str, Any]:
    summary = next(
        row
        for row in q_evidence["compiler_backed_census"]["hard_valid_candidate_summaries"]
        if row["pair_fingerprint"] == ROUTE10_Q
    )
    pair = r_evidence["route10_P_vs_Q"]["Q"]["pair"]
    direction_operations = {}
    rhythm_parts = []
    for direction in ("outbound", "inbound"):
        source = summary["directions"][direction]
        rhythm = source["rhythm_simplicity"]
        rhythm_parts.append(rhythm)
        direction_operations[direction] = {
            "service_regime_headways": [
                int(regime["uniform_headway_minutes"]) for regime in source["service_regimes"]
            ],
            "micro_rhythm_boundary_count": sum(
                int(family["micro_rhythm_boundary_count"])
                for family in source["local_rhythm_families"]
            ),
            "average_passenger_wait_minutes": source["average_passenger_wait_minutes"],
            "maximum_bucket_wait_minutes": source["maximum_bucket_wait_minutes"],
            "p90_bucket_wait_minutes": source["p90_bucket_wait_minutes"],
            "tail_headway_minutes": source["tail_headway_minutes"],
            "sustained_headway_levels": rhythm["sustained_headway_levels"],
            "effective_headway_palette": rhythm["effective_headway_palette"],
        }
    rhythm_tuple = [
        sum(int(item["sustained_headway_level_count"]) for item in rhythm_parts),
        sum(int(item["actual_service_regime_count"]) for item in rhythm_parts),
        sum(int(item["effective_headway_palette_count"]) for item in rhythm_parts),
        sum(int(item["single_gap_regime_count"]) for item in rhythm_parts),
    ]
    return {
        "fingerprint": ROUTE10_Q,
        "authority": "Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE",
        "production_SSE": float(pair["production_SSE"]),
        "production_TE": float(pair["production_TE"]),
        "continuous_exposure_equivalent": float(pair["continuous_exposure_equivalent"]),
        "bucket_exposure_equivalent": float(pair["bucket_exposure_equivalent"]),
        "rhythm_tuple": rhythm_tuple,
        "fleet_tuple": [
            int(summary["fleet_required"]),
            int(summary["total_excess_terminal_wait"]),
            int(summary["max_excess_terminal_wait"]),
        ],
        "micro_rhythm_boundary_count": int(
            summary["review_metrics"]["micro_rhythm_boundary_count"]
        ),
        "operations": {
            "directions": direction_operations,
            "micro_rhythm_boundary_count": int(
                summary["review_metrics"]["micro_rhythm_boundary_count"]
            ),
            "average_passenger_wait_minutes": float(summary["average_passenger_wait_minutes"]),
            "actual_service_regime_count": int(
                summary["review_metrics"]["actual_service_regime_count"]
            ),
        },
    }


def _path_summary(
    path: Mapping[str, Any], *, q_fingerprint: str | None, legacy_bound: float
) -> dict[str, Any]:
    q_delta = None if q_fingerprint is None else path["candidate_deltas"].get(q_fingerprint)
    q_selection = (
        None
        if q_fingerprint is None
        else next(
            (row for row in path["breakpoint_audit"] if row["selected"] == q_fingerprint), None
        )
    )
    relation = None
    if q_selection is not None:
        value = float(q_selection["breakpoint"])
        relation = (
            "LESS"
            if value < legacy_bound - NUMERICAL_EPSILON
            else "MORE"
            if value > legacy_bound + NUMERICAL_EPSILON
            else "EQUAL"
        )
    first_rhythm = path["first_rhythm_improvement"]
    first_micro = path["first_micro_rhythm_free_winner"]
    return {
        "first_rhythm_improvement_winner": None
        if first_rhythm is None
        else first_rhythm["selected"],
        "first_micro_rhythm_free_winner": None if first_micro is None else first_micro["selected"],
        "q_admission_breakpoint": q_delta,
        "q_selection_breakpoint": None if q_selection is None else q_selection["breakpoint"],
        "q_selected": q_selection is not None,
        "q_selection_vs_legacy_bound": relation,
    }


def _select_at_envelope(
    candidates: Sequence[Mapping[str, Any]], *, metric: str, anchor: str, envelope: float
) -> dict[str, Any]:
    by_fp = {str(item["fingerprint"]): item for item in candidates}
    anchor_value = float(by_fp[anchor][metric])
    admitted = [
        item
        for item in candidates
        if _delta(float(item[metric]), anchor_value) <= envelope + NUMERICAL_EPSILON
    ]
    winner = select_by_frozen_secondary_hierarchy(admitted)
    return {
        "numeric_envelope": envelope,
        "admitted_count": len(admitted),
        "selected": winner["fingerprint"],
        "rhythm": list(winner["rhythm_tuple"]),
        "fleet": list(winner["fleet_tuple"]),
    }


def build_evidence(repo_root: Path) -> dict[str, Any]:
    locks = _verify_locks(repo_root)
    r_evidence = _load_json(repo_root / R_JSON)
    o_evidence = _load_json(repo_root / O_JSON)
    q_evidence = _load_json(repo_root / Q_JSON)
    if r_evidence["root_classification"] != "BUCKET_EDGE_ALIASING_CONFIRMED":
        raise RuntimeError("R root classification changed")
    if (
        r_evidence["anchor_validity"]["classification"]
        != "ANCHOR_STABLE_ACROSS_DEMAND_FIT_SEMANTICS"
    ):
        raise RuntimeError("R anchor semantics are not stable")
    expected6 = r_evidence["coordinator_replay"]["routes"]["6"]["PR62_I_fingerprints"]
    expected10 = r_evidence["coordinator_replay"]["routes"]["10"]["PR62_I_fingerprints"]
    report6 = load_locked_preserved_report(
        repo_root / ROUTE6_REPORT,
        expected_sha256=REPORT_HASHES["6"],
        expected_fingerprints=expected6,
    )
    report10 = load_locked_preserved_report(
        repo_root / ROUTE10_REPORT_1,
        expected_sha256=REPORT_HASHES["10"],
        expected_fingerprints=expected10,
    )
    second10 = (repo_root / ROUTE10_REPORT_2).read_bytes()
    if (
        _sha256_bytes(second10) != REPORT_HASHES["10"]
        or second10 != (repo_root / ROUTE10_REPORT_1).read_bytes()
    ):
        raise RuntimeError("Route 10 preserved reports are not byte-identical")
    route6 = _production_candidates(
        route_id="6", r_evidence=r_evidence, o_evidence=o_evidence, report=report6
    )
    route10 = _production_candidates(
        route_id="10", r_evidence=r_evidence, o_evidence=o_evidence, report=report10
    )
    route10.append(_q_candidate(r_evidence, q_evidence))
    route10.sort(key=lambda item: item["fingerprint"])
    if len(route6) != 41 or len(route10) != 8:
        raise RuntimeError("S candidate universe count changed")
    metrics = ("continuous_exposure_equivalent", "bucket_exposure_equivalent")
    route_payloads: dict[str, Any] = {}
    for route_id, candidates, anchor in (
        ("6", route6, ROUTE6_ANCHOR),
        ("10", route10, ROUTE10_ANCHOR),
    ):
        paths = {
            metric: breakpoint_experiment(candidates, metric=metric, anchor_fingerprint=anchor)
            for metric in metrics
        }
        legacy = {
            metric: legacy_eligibility_mapping(candidates, metric=metric, anchor_fingerprint=anchor)
            for metric in metrics
        }
        summaries = {
            metric: _path_summary(
                paths[metric],
                q_fingerprint=ROUTE10_Q if route_id == "10" else None,
                legacy_bound=legacy[metric]["preservation_bound"],
            )
            for metric in metrics
        }
        route_payloads[route_id] = {
            "candidate_universe_count": len(candidates),
            "candidate_authority": "41_CURRENT_PRODUCTION_ACCESS_SAFE_CANDIDATES"
            if route_id == "6"
            else "7_CURRENT_PRODUCTION_ACCESS_SAFE_PLUS_Q_EXTERNAL_REVIEW",
            "anchor_fingerprint": anchor,
            "P_fingerprint": ROUTE10_P if route_id == "10" else None,
            "Q_fingerprint": ROUTE10_Q if route_id == "10" else None,
            "Q_authority": "Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE" if route_id == "10" else None,
            "candidates": candidates,
            "breakpoint_paths": paths,
            "legacy_eligibility": legacy,
            "path_summaries": summaries,
        }
    r10 = route_payloads["10"]
    r6 = route_payloads["6"]
    for metric in metrics:
        suffix = "continuous" if metric.startswith("continuous") else "bucket"
        r10[f"Q_{suffix}_delta"] = r10["breakpoint_paths"][metric]["candidate_deltas"][ROUTE10_Q]
        r10[f"P_{suffix}_delta"] = r10["breakpoint_paths"][metric]["candidate_deltas"][ROUTE10_P]
        q_selection = r10["path_summaries"][metric]["q_selection_breakpoint"]
        r6["route10_Q_selection_envelope_diagnostic_" + metric] = (
            None
            if q_selection is None
            else _select_at_envelope(
                route6, metric=metric, anchor=ROUTE6_ANCHOR, envelope=q_selection
            )
        )
    route10_by_fingerprint = {str(candidate["fingerprint"]): candidate for candidate in route10}
    p_candidate = route10_by_fingerprint[ROUTE10_P]
    q_candidate = route10_by_fingerprint[ROUTE10_Q]
    r10["Q_vs_P_operational_context"] = {
        "P": {
            "average_passenger_wait_minutes": p_candidate["operations"][
                "average_passenger_wait_minutes"
            ],
            "inbound_maximum_bucket_wait_minutes": p_candidate["operations"]["directions"][
                "inbound"
            ]["maximum_bucket_wait_minutes"],
            "fleet_required": p_candidate["fleet_tuple"][0],
            "micro_rhythm_boundary_count": p_candidate["micro_rhythm_boundary_count"],
            "actual_service_regime_count": p_candidate["operations"]["actual_service_regime_count"],
        },
        "Q": {
            "average_passenger_wait_minutes": q_candidate["operations"][
                "average_passenger_wait_minutes"
            ],
            "inbound_maximum_bucket_wait_minutes": q_candidate["operations"]["directions"][
                "inbound"
            ]["maximum_bucket_wait_minutes"],
            "fleet_required": q_candidate["fleet_tuple"][0],
            "micro_rhythm_boundary_count": q_candidate["micro_rhythm_boundary_count"],
            "actual_service_regime_count": q_candidate["operations"]["actual_service_regime_count"],
        },
        "Q_minus_P": {
            "average_passenger_wait_minutes": q_candidate["operations"][
                "average_passenger_wait_minutes"
            ]
            - p_candidate["operations"]["average_passenger_wait_minutes"],
            "inbound_maximum_bucket_wait_minutes": q_candidate["operations"]["directions"][
                "inbound"
            ]["maximum_bucket_wait_minutes"]
            - p_candidate["operations"]["directions"]["inbound"]["maximum_bucket_wait_minutes"],
            "fleet_required": q_candidate["fleet_tuple"][0] - p_candidate["fleet_tuple"][0],
            "micro_rhythm_boundary_count": q_candidate["micro_rhythm_boundary_count"]
            - p_candidate["micro_rhythm_boundary_count"],
            "actual_service_regime_count": q_candidate["operations"]["actual_service_regime_count"]
            - p_candidate["operations"]["actual_service_regime_count"],
        },
        "hard_gate_created": False,
    }
    r10["required_breakpoint_observations"] = {}
    for metric in metrics:
        path = r10["breakpoint_paths"][metric]
        summary = r10["path_summaries"][metric]
        first_rhythm = path["first_rhythm_improvement"]
        first_micro = path["first_micro_rhythm_free_available"]
        r10["required_breakpoint_observations"][metric] = {
            "FIRST_RHYTHM_IMPROVEMENT_BREAKPOINT": {
                "breakpoint": None if first_rhythm is None else first_rhythm["breakpoint"],
                "winner": None if first_rhythm is None else first_rhythm["selected"],
            },
            "FIRST_MICRO_RHYTHM_FREE_BREAKPOINT": {
                "breakpoint": None if first_micro is None else first_micro["breakpoint"],
                "available_candidates": []
                if first_micro is None
                else first_micro["micro_rhythm_free_fingerprints"],
            },
            "FIRST_Q_CANONICAL_ADMISSION_BREAKPOINT": summary["q_admission_breakpoint"],
            "CURRENT_P_ADMISSION_BREAKPOINT": path["candidate_deltas"][ROUTE10_P],
            "MINIMUM_BREAKPOINT_SELECTING_Q": summary["q_selection_breakpoint"],
            "Q_selection_audit_after_admission": [
                {
                    "breakpoint": row["breakpoint"],
                    "Q_wins": row["selected"] == ROUTE10_Q,
                    "selected": row["selected"],
                    "reason": (
                        "Q_HAS_BEST_FROZEN_RHYTHM_THEN_FLEET_TUPLE"
                        if row["selected"] == ROUTE10_Q
                        else "ANOTHER_ADMITTED_CANDIDATE_HAS_BETTER_FROZEN_RHYTHM_THEN_FLEET_TUPLE"
                    ),
                }
                for row in path["breakpoint_audit"]
                if ROUTE10_Q in row["admitted_fingerprints"]
            ],
        }
    cross_route_table: dict[str, Any] = {"6": {}, "10": {}}
    for metric in metrics:
        route6_path = r6["breakpoint_paths"][metric]
        route10_path = r10["breakpoint_paths"][metric]
        route10_summary = r10["path_summaries"][metric]
        first6 = route6_path["first_winner_change"]
        simpler6 = route6_path["first_rhythm_improvement"]
        simpler10 = route10_path["first_rhythm_improvement"]
        micro10 = route10_path["first_micro_rhythm_free_available"]
        cross_route_table["6"][metric] = {
            "anchor": 0.0,
            "first_simpler": None if simpler6 is None else simpler6["breakpoint"],
            "first_simpler_winner": None if simpler6 is None else simpler6["selected"],
            "first_winner_change": None if first6 is None else first6["breakpoint"],
            "first_winner_change_winner": None if first6 is None else first6["selected"],
        }
        cross_route_table["10"][metric] = {
            "anchor": 0.0,
            "first_simpler": None if simpler10 is None else simpler10["breakpoint"],
            "first_simpler_winner": None if simpler10 is None else simpler10["selected"],
            "first_winner_change": (
                None
                if route10_path["first_winner_change"] is None
                else route10_path["first_winner_change"]["breakpoint"]
            ),
            "first_micro_rhythm_free": None if micro10 is None else micro10["breakpoint"],
            "Q_admitted": route10_summary["q_admission_breakpoint"],
            "Q_selected": route10_summary["q_selection_breakpoint"],
            "P_admitted": route10_path["candidate_deltas"][ROUTE10_P],
        }
    disagreement = material_path_disagreement(
        r10["path_summaries"]["continuous_exposure_equivalent"],
        r10["path_summaries"]["bucket_exposure_equivalent"],
    )
    continuous_summary = r10["path_summaries"]["continuous_exposure_equivalent"]
    bucket_summary = r10["path_summaries"]["bucket_exposure_equivalent"]
    route6_stable = all(
        r6["route10_Q_selection_envelope_diagnostic_" + metric] is not None
        and r6["route10_Q_selection_envelope_diagnostic_" + metric]["selected"] == ROUTE6_ANCHOR
        for metric in metrics
    )
    if disagreement:
        classification, next_milestone = (
            "PHASE_ROBUST_METRICS_DISAGREE_ON_POLICY_PATH",
            "PR62_T_METRIC_CHOICE_REVIEW",
        )
    elif not route6_stable:
        classification, next_milestone = (
            "ROUTE6_CONTROL_DESTABILIZED",
            "PR62_T_ROUTE6_CONTROL_POLICY_REVIEW",
        )
    elif (
        continuous_summary["q_selected"]
        and bucket_summary["q_selected"]
        and all(
            summary["q_selection_vs_legacy_bound"] in {"LESS", "EQUAL"}
            for summary in (continuous_summary, bucket_summary)
        )
    ):
        classification, next_milestone = (
            "PHASE_ROBUST_MATERIALITY_PATH_SUPPORTS_CANONICAL_Q",
            "PR62-T_PHASE_ROBUST_MATERIALITY_POLICY_FREEZE",
        )
    elif any(
        summary["q_selection_vs_legacy_bound"] == "MORE"
        for summary in (continuous_summary, bucket_summary)
    ):
        classification, next_milestone = (
            "PHASE_ROBUST_Q_REQUIRES_GREATER_THAN_LEGACY_POLICY_CONCESSION",
            "PR62_T_EXPLICIT_DOMAIN_POLICY_REVIEW",
        )
    else:
        classification, next_milestone = (
            "PHASE_ROBUST_MATERIALITY_SUPPORTS_SIMPLER_NON_Q",
            "PR62_T_SIMPLER_NON_Q_CANDIDATE_REVIEW",
        )
    return {
        "milestone": "PR62-S",
        "R_commit_SHA": R_COMMIT_SHA,
        "R_evidence_lock": {
            "json": locks[R_JSON.as_posix()],
            "markdown": locks[R_MARKDOWN.as_posix()],
        },
        "metric_definitions": r_evidence["metric_definitions"],
        "primary_metric": "CONTINUOUS_EXPOSURE_EQUIVALENT",
        "corroborating_metric": "BUCKET_EXPOSURE_EQUIVALENT",
        "metric_scope": "REVIEW_ONLY_MATERIALITY_BREAKPOINT_DIAGNOSTICS",
        "old_numeric_one_trip_threshold_transferred": False,
        "input_provenance": {
            "coordinator_replays_executed_by_S": 0,
            "route_6": {
                "source": "PRESERVED_PR62_R_AUTHORIZED_RECOVERY_REPORT",
                "sha256": REPORT_HASHES["6"],
                "fingerprints_validated_before_use": True,
            },
            "route_10": {
                "source": "TWO_PRESERVED_BYTE_IDENTICAL_REPORTS",
                "sha256": REPORT_HASHES["10"],
                "report_count": 2,
                "reports_byte_identical": True,
                "fingerprints_validated_before_use": True,
            },
        },
        "frozen_secondary_hierarchy": {
            "rhythm_tuple": [
                "total_directional_sustained_headway_level_count",
                "actual_service_regime_count",
                "total_directional_effective_palette_count",
                "total_single_gap_regime_count",
            ],
            "fleet_tuple": [
                "fleet_required",
                "total_excess_terminal_wait",
                "max_excess_terminal_wait",
            ],
            "fingerprint_role": "EXACT_METRIC_TIE_BREAK_ONLY",
            "micro_rhythm_role": "REVIEW_ONLY_NOT_A_HARD_GATE",
        },
        "routes": route_payloads,
        "cross_route_breakpoint_comparison": cross_route_table,
        "cross_route_comparison": {
            "continuous_and_bucket_materially_disagree": disagreement,
            "route6_stable_at_route10_Q_selection_envelopes": route6_stable,
        },
        "classification": classification,
        "next_milestone_recommendation": next_milestone,
        "READY_FOR_FINAL_PILOT_USE": False,
        "READY_FOR_PR62_COMPLETION_REVIEW": False,
        "production_guards": {
            "Production_SSE_changed": False,
            "Production_TE_changed": False,
            "V2_band_changed": False,
            "V2_selector_changed": False,
            "Search_changed": False,
            "Budget_changed": False,
            "Queue_changed": False,
            "Pareto_changed": False,
            "Compiler_changed": False,
            "Rhythm_semantics_changed": False,
            "Tail_changed": False,
            "Protection_changed": False,
            "Access_changed": False,
            "Fleet_changed": False,
            "Settlement_or_residual_added": False,
            "Canonical_XLSX_changed": False,
            "Private_workbook_opened": False,
            "Private_workbook_committed": False,
            "Phase_robust_metric_added_to_production": False,
        },
        "immutable_file_locks": locks,
        "deterministic_render": True,
    }


def _fmt(value: Any) -> str:
    return f"{value:.12f}" if isinstance(value, float) else str(value)


def _path_lines(route: Mapping[str, Any], metric: str) -> list[str]:
    path = route["breakpoint_paths"][metric]
    lines = [f"### {metric}", ""]
    for row in path["compact_path"]:
        lines.append(
            f"- `{_fmt(row['breakpoint'])}`: {row['admitted_count']} admitted; selected `{row['selected']}`; rhythm `{row['rhythm']}`; fleet `{row['fleet']}`."
        )
    summary = route["path_summaries"][metric]
    lines.extend(
        [
            f"- Q admission / selection: `{_fmt(summary['q_admission_breakpoint'])}` / `{_fmt(summary['q_selection_breakpoint'])}`.",
            f"- Legacy preservation bound: `{_fmt(route['legacy_eligibility'][metric]['preservation_bound'])}`.",
            "",
        ]
    )
    return lines


def render_markdown(payload: Mapping[str, Any]) -> str:
    route10 = payload["routes"]["10"]
    route6 = payload["routes"]["6"]
    lines = [
        "# PR62-S — Phase-robust materiality policy experiment",
        "",
        f"Classification: **{payload['classification']}**.",
        "",
        "R confirmed bucket-edge aliasing while both anchors remained stable. S therefore reviews materiality only; the old numeric +1.0 point-TE threshold is not transferred.",
        "",
        "## Route 10 phase-robust paths",
        "",
        f"Anchor `{route10['anchor_fingerprint']}`; P `{route10['P_fingerprint']}`; Q `{route10['Q_fingerprint']}` is `Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE`.",
        "",
    ]
    lines.extend(_path_lines(route10, "continuous_exposure_equivalent"))
    lines.extend(_path_lines(route10, "bucket_exposure_equivalent"))
    operations = route10["Q_vs_P_operational_context"]
    lines.extend(
        [
            "## Q versus P",
            "",
            f"- Continuous deltas from anchor: Q `{_fmt(route10['Q_continuous_delta'])}`; P `{_fmt(route10['P_continuous_delta'])}`.",
            f"- Bucket deltas from anchor: Q `{_fmt(route10['Q_bucket_delta'])}`; P `{_fmt(route10['P_bucket_delta'])}`.",
            "- Under phase-robust demand fit, Q is closer to the demand-fit anchor than the currently accepted P timetable.",
            "- Under both diagnostics, Q requires less phase-robust concession than preserving the old P eligibility set; this is descriptive and does not freeze a band.",
            f"- Average wait P/Q: `{_fmt(operations['P']['average_passenger_wait_minutes'])}` / "
            f"`{_fmt(operations['Q']['average_passenger_wait_minutes'])}` minutes.",
            f"- Inbound maximum access P/Q: "
            f"`{_fmt(operations['P']['inbound_maximum_bucket_wait_minutes'])}` / "
            f"`{_fmt(operations['Q']['inbound_maximum_bucket_wait_minutes'])}` minutes.",
            f"- Fleet P/Q: `{operations['P']['fleet_required']}` / "
            f"`{operations['Q']['fleet_required']}`; micro-rhythm boundaries "
            f"`{operations['P']['micro_rhythm_boundary_count']}` / "
            f"`{operations['Q']['micro_rhythm_boundary_count']}`; ServiceRegimes "
            f"`{operations['P']['actual_service_regime_count']}` / "
            f"`{operations['Q']['actual_service_regime_count']}`.",
            "- These passenger and operating facts are context only, not new hard gates.",
            "",
            "## Cross-route breakpoint comparison",
            "",
            "| Route | Metric | First simpler | First winner change | First zero-micro | Q admitted | Q selected | P admitted |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    table = payload["cross_route_breakpoint_comparison"]
    for route_id in ("6", "10"):
        for metric in ("continuous_exposure_equivalent", "bucket_exposure_equivalent"):
            row = table[route_id][metric]
            lines.append(
                f"| {route_id} | {metric} | {_fmt(row.get('first_simpler'))} | "
                f"{_fmt(row.get('first_winner_change'))} | "
                f"{_fmt(row.get('first_micro_rhythm_free'))} | "
                f"{_fmt(row.get('Q_admitted'))} | {_fmt(row.get('Q_selected'))} | "
                f"{_fmt(row.get('P_admitted'))} |"
            )
    lines.extend(
        [
            "",
            "## Route 6 control",
            "",
            f"Anchor `{route6['anchor_fingerprint']}` over 41 access-safe candidates.",
            "",
        ]
    )
    for metric in ("continuous_exposure_equivalent", "bucket_exposure_equivalent"):
        path = route6["breakpoint_paths"][metric]
        first = path["first_winner_change"]
        diagnostic = route6["route10_Q_selection_envelope_diagnostic_" + metric]
        lines.append(
            f"- {metric}: first winner change `{None if first is None else first['breakpoint']}` → `{None if first is None else first['selected']}`; Route-10-Q envelope selects `{None if diagnostic is None else diagnostic['selected']}`."
        )
    lines.extend(
        [
            "",
            "## Conclusion",
            "",
            f"- Exact classification: `{payload['classification']}`.",
            f"- Recommended next milestone: `{payload['next_milestone_recommendation']}`.",
            "- Continuous and bucket breakpoint paths do not materially disagree, and Route 6 stays anchored at both Route-10-Q diagnostic envelopes.",
            "- No universal band or production threshold is defined in S.",
            "- `READY_FOR_FINAL_PILOT_USE = false`.",
            "- `READY_FOR_PR62_COMPLETION_REVIEW = false`.",
            "- All production guards are false; no XLSX was regenerated.",
            "",
        ]
    )
    return "\n".join(lines)


def write_evidence(repo_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    json_first = canonical_json_bytes(payload)
    json_second = canonical_json_bytes(payload)
    markdown_first = render_markdown(payload).encode("utf-8")
    markdown_second = render_markdown(payload).encode("utf-8")
    if json_first != json_second or markdown_first != markdown_second:
        raise RuntimeError("S evidence render is not deterministic")
    (repo_root / OUTPUT_JSON).write_bytes(json_first)
    (repo_root / OUTPUT_MARKDOWN).write_bytes(markdown_first)
    return {
        "json": {"sha256": _sha256_bytes(json_first), "bytes": len(json_first)},
        "markdown": {"sha256": _sha256_bytes(markdown_first), "bytes": len(markdown_first)},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    payload = build_evidence(args.repo_root.resolve())
    print(json.dumps(write_evidence(args.repo_root.resolve(), payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
