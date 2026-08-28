"""Freeze and certify the PR62-T phase-robust materiality selector V3."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from bus_schedule_engine.contracts_v1.operational_selection_policy import (
    NUMERICAL_EPSILON,
    OperationalSelectionCandidateV1,
)
from bus_schedule_engine.contracts_v1.operational_selection_policy_v2 import (
    OperationalSelectionCandidateV2,
)
from bus_schedule_engine.contracts_v1.operational_selection_policy_v3 import (
    LEGACY_TE_CALIBRATION_BAND_TRIPS_V3,
    OPERATIONAL_SELECTION_PROFILE_V3,
    PRIMARY_MATERIALITY_METRIC_V3,
    PRIORITY_ORDER_V3,
    OperationalSelectionCandidateV3,
    select_operational_candidates_v3,
)

SOURCE_COMMIT = "b45a7317de9f8142da8d5976280b1503964ee054"
S_JSON = Path("docs/engine/evidence/PR62_S_PHASE_ROBUST_MATERIALITY_POLICY_EXPERIMENT.json")
S_MARKDOWN = Path("docs/engine/evidence/PR62_S_PHASE_ROBUST_MATERIALITY_POLICY_EXPERIMENT.md")
OUTPUT_JSON = Path("docs/engine/evidence/PR62_T_PHASE_ROBUST_MATERIALITY_POLICY_FREEZE.json")
OUTPUT_MARKDOWN = Path("docs/engine/evidence/PR62_T_PHASE_ROBUST_MATERIALITY_POLICY_FREEZE.md")

ROUTE6_ANCHOR = "ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b"
ROUTE10_ANCHOR = "bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c"
ROUTE10_CONTINUOUS_INTERIM = "6dbd9d2cac0931e85b1b50283b7011c610488226c863ce0192ff6bdf22bd3f16"
ROUTE10_BUCKET_INTERIM = "c8eeb70f59bbf027e8444148533e639e0a7123b5225e7fec25a242475a678dd7"
ROUTE10_Q = "12e9541a84a90d3a8c58a749b140173668e721b951399dab90b0066792c6e4a5"

IMMUTABLE_AUTHORITY_LOCKS = {
    S_JSON.as_posix(): "e54ab2a5d366c3d76613a93e73fae0a722cd642f64dbc1f077618d51c6472c2a",
    S_MARKDOWN.as_posix(): "bcfa140683be12a1441e149c9ad3155b4d9985f93a187d4930d17003b1e7b22f",
    "src/bus_schedule_engine/contracts_v1/operational_selection_policy.py": (
        "5f10bf7130c20898a3e537fc8f7b73e990335f92ccb7913c41e50a308809e415"
    ),
    "src/bus_schedule_engine/contracts_v1/operational_selection_policy_v2.py": (
        "79a63d38dfde00f42af1f5a56cb67adb3280c3941b45cdb1f67fb65c67ea3181"
    ),
    "src/bus_schedule_engine/service_plan_coordinator.py": (
        "99da83840f30d5ff7781b1525ec5202074641f1c01203ad46ddc42200a24bfc0"
    ),
    "src/bus_schedule_engine/contracts_v1/clean_boundary_compiler.py": (
        "e36950284e7d2bea1f7ff15dc1bb016d360b8b3dd6ff3ce0299cfcbdb3952490"
    ),
    "src/bus_schedule_engine/contracts_v1/fleet_assignment.py": (
        "ea222b7f3c4d46eb908b6a1df4b6f450128dff418f7a8e466192eab8b965f093"
    ),
    "outputs/final_pilot/Route_6_Final_Pilot_Timetable.xlsx": (
        "13454026722f996d8b06e5305b3b6ab2d57ea6126734f4deeb23c3e7dbafd02c"
    ),
    "outputs/final_pilot/Route_10_Final_Pilot_Timetable.xlsx": (
        "d84dd2e873d3ba30275463a5eff67277a22467839af0f0125e69160a891fc3db"
    ),
}

PRODUCTION_GUARDS = {
    "V1_selector_changed": "NO",
    "V2_selector_changed": "NO",
    "Active_production_selector_changed": "NO",
    "Coordinator_changed": "NO",
    "Search_changed": "NO",
    "Search_budget_changed": "NO",
    "Queue_changed": "NO",
    "Pareto_changed": "NO",
    "Compiler_changed": "NO",
    "Protection_changed": "NO",
    "Tail_changed": "NO",
    "Access_changed": "NO",
    "Fleet_validator_changed": "NO",
    "Rhythm_tuple_changed": "NO",
    "Micro_rhythm_hard_constraint_added": "NO",
    "Settlement_or_residual_added": "NO",
    "Canonical_Route_6_XLSX_changed": "NO",
    "Canonical_Route_10_XLSX_changed": "NO",
    "XLSX_regenerated": "NO",
    "Private_workbook_opened": "NO",
    "Private_workbook_committed": "NO",
    "V3_selector_added": "YES",
    "Continuous_exposure_metric_promoted_to_V3_materiality": "YES",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def verify_file_locks(
    repo_root: Path, expected_locks: Mapping[str, str]
) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for relative, expected in expected_locks.items():
        path = repo_root / relative
        data = path.read_bytes()
        actual = _sha256_bytes(data)
        if actual != expected:
            raise RuntimeError(
                f"authority lock mismatch for {relative}: expected {expected}, got {actual}"
            )
        records[relative] = {
            "bytes": len(data),
            "sha256": actual,
            "unchanged": True,
        }
    return records


def _direction_max_wait(record: Mapping[str, Any], direction: str) -> float:
    return float(
        record.get("operations", {})
        .get("directions", {})
        .get(direction, {})
        .get("maximum_bucket_wait_minutes", 0.0)
    )


def _candidate_from_s_record(record: Mapping[str, Any]) -> OperationalSelectionCandidateV3:
    rhythm = tuple(int(value) for value in record["rhythm_tuple"])
    fleet = tuple(int(value) for value in record["fleet_tuple"])
    v1 = OperationalSelectionCandidateV1(
        fingerprint=str(record["fingerprint"]),
        hard_feasible=True,
        hard_feasibility_reasons=(),
        observed_demand_mismatch=float(record["production_SSE"]),
        outbound_maximum_bucket_expected_wait_minutes=_direction_max_wait(record, "outbound"),
        inbound_maximum_bucket_expected_wait_minutes=_direction_max_wait(record, "inbound"),
        total_directional_sustained_headway_level_count=rhythm[0],
        actual_service_regime_count=rhythm[1],
        total_directional_effective_palette_count=rhythm[2],
        total_single_gap_regime_count=rhythm[3],
        fleet_required=fleet[0],
        total_excess_terminal_wait=fleet[1],
        max_excess_terminal_wait=fleet[2],
        diagnostics={
            "authority": record["authority"],
            "micro_rhythm_boundary_count": record["micro_rhythm_boundary_count"],
            "source": "COMMITTED_PR62_S_ACCESS_SAFE_CANDIDATE_RECORD",
        },
        hard_feasibility_metrics={"committed_S_hard_feasible": True},
    )
    te = float(record["production_TE"])
    v2 = OperationalSelectionCandidateV2(
        v1_candidate=v1,
        outbound_trip_equivalent_error=te / 2.0,
        inbound_trip_equivalent_error=te / 2.0,
        pair_trip_equivalent_error=te,
        diagnostics={"source": "COMMITTED_PR62_S_PRODUCTION_TE"},
    )
    continuous = float(record["continuous_exposure_equivalent"])
    return OperationalSelectionCandidateV3(
        v2_candidate=v2,
        outbound_continuous_exposure_equivalent=continuous / 2.0,
        inbound_continuous_exposure_equivalent=continuous / 2.0,
        pair_continuous_exposure_equivalent=continuous,
        diagnostics={
            "source": "COMMITTED_PR62_S_CONTINUOUS_EXPOSURE_EQUIVALENT",
            "authority": record["authority"],
        },
    )


def _access_authority(records: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    return {
        direction: max(_direction_max_wait(record, direction) for record in records)
        for direction in ("outbound", "inbound")
    }


def _selection_result(
    route_id: str, records: Sequence[Mapping[str, Any]]
) -> tuple[Any, dict[str, float]]:
    access = _access_authority(records)
    result = select_operational_candidates_v3(
        route_id=route_id,
        candidates=tuple(_candidate_from_s_record(record) for record in records),
        scenario_b_directional_maximum_wait_minutes=access,
    )
    return result, access


def _result_payload(
    result: Any, records: Sequence[Mapping[str, Any]], access: Mapping[str, float]
) -> dict[str, Any]:
    payload = asdict(result)
    anchor_te = result.common_anchor_te
    anchor_continuous = result.anchor_continuous_exposure_equivalent
    payload["scenario_b_access_safe_universe_reconstruction"] = {
        "authority": "COMMITTED_PR62_S_ACCESS_SAFE_CANDIDATE_UNIVERSE",
        "directional_maxima_used_to_preserve_prefiltered_universe": dict(access),
    }
    payload["candidate_metric_audit"] = [
        {
            "fingerprint": record["fingerprint"],
            "authority": record["authority"],
            "production_SSE": record["production_SSE"],
            "production_TE": record["production_TE"],
            "production_TE_delta_from_anchor": (
                float(record["production_TE"]) - float(anchor_te) if anchor_te is not None else None
            ),
            "continuous_exposure_equivalent": record["continuous_exposure_equivalent"],
            "continuous_exposure_delta_from_anchor": (
                float(record["continuous_exposure_equivalent"]) - float(anchor_continuous)
                if anchor_continuous is not None
                else None
            ),
            "rhythm_tuple": record["rhythm_tuple"],
            "fleet_tuple": record["fleet_tuple"],
            "micro_rhythm_boundary_count": record["micro_rhythm_boundary_count"],
            "inside_legacy_te_calibration_set": record["fingerprint"]
            in result.legacy_calibration_fingerprints,
            "inside_continuous_materiality_set": record["fingerprint"]
            in result.phase_robust_materiality_fingerprints,
        }
        for record in sorted(records, key=lambda row: row["fingerprint"])
    ]
    return payload


def _corroborating_metric_path(
    *,
    calibration_records: Sequence[Mapping[str, Any]],
    selection_records: Sequence[Mapping[str, Any]],
    anchor_fingerprint: str,
    metric: str,
) -> dict[str, Any]:
    anchor = next(
        record for record in calibration_records if record["fingerprint"] == anchor_fingerprint
    )
    calibration = tuple(
        record
        for record in calibration_records
        if float(record["production_TE"]) - float(anchor["production_TE"])
        <= LEGACY_TE_CALIBRATION_BAND_TRIPS_V3 + NUMERICAL_EPSILON
    )
    if not any(record["fingerprint"] == anchor_fingerprint for record in calibration):
        raise RuntimeError("bucket corroboration calibration omitted its anchor")
    bound = max(float(record[metric]) - float(anchor[metric]) for record in calibration)
    deltas = {
        str(record["fingerprint"]): float(record[metric]) - float(anchor[metric])
        for record in selection_records
    }
    if any(delta < -NUMERICAL_EPSILON for delta in deltas.values()):
        raise RuntimeError("bucket corroboration has a phase-robust reference conflict")
    admitted = tuple(
        record
        for record in selection_records
        if deltas[str(record["fingerprint"])] <= bound + NUMERICAL_EPSILON
    )
    selected = min(
        admitted,
        key=lambda record: (
            tuple(record["rhythm_tuple"]),
            tuple(record["fleet_tuple"]),
            record["fingerprint"],
        ),
    )
    return {
        "metric": metric,
        "legacy_calibration_count": len(calibration),
        "legacy_calibration_fingerprints": sorted(record["fingerprint"] for record in calibration),
        "preservation_bound": bound,
        "materiality_count": len(admitted),
        "materiality_fingerprints": sorted(record["fingerprint"] for record in admitted),
        "selected": selected["fingerprint"],
        "selected_rhythm_tuple": selected["rhythm_tuple"],
        "selected_fleet_tuple": selected["fleet_tuple"],
    }


def _assert_exact_route_locks(
    route6: Any, route10: Any, augmented: Any, bucket: Mapping[str, Any]
) -> None:
    exact = (
        (route6.common_anchor_fingerprint, ROUTE6_ANCHOR, "Route 6 anchor"),
        (route6.legacy_calibration_set_count, 5, "Route 6 calibration count"),
        (route6.continuous_preservation_bound, 1.2760765031007502, "Route 6 bound"),
        (route6.phase_robust_materiality_set_count, 6, "Route 6 materiality count"),
        (route6.selected_pair_fingerprint, ROUTE6_ANCHOR, "Route 6 selected"),
        (route10.common_anchor_fingerprint, ROUTE10_ANCHOR, "Route 10 anchor"),
        (route10.legacy_calibration_set_count, 2, "Route 10 calibration count"),
        (route10.continuous_preservation_bound, 1.9858806668778222, "Route 10 bound"),
        (route10.phase_robust_materiality_set_count, 6, "Route 10 materiality count"),
        (route10.selected_pair_fingerprint, ROUTE10_CONTINUOUS_INTERIM, "Route 10 selected"),
        (augmented.legacy_calibration_set_count, 2, "Route 10 Q calibration count"),
        (augmented.continuous_preservation_bound, 1.9858806668778222, "Route 10 Q bound"),
        (augmented.phase_robust_materiality_set_count, 7, "Route 10 Q materiality count"),
        (augmented.selected_pair_fingerprint, ROUTE10_Q, "Route 10 Q selected"),
        (bucket["route_10_production_only"]["selected"], ROUTE10_BUCKET_INTERIM, "bucket interim"),
        (bucket["route_10_q_augmented"]["selected"], ROUTE10_Q, "bucket Q selected"),
    )
    for actual, expected, label in exact:
        if actual != expected:
            raise RuntimeError(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def build_evidence(repo_root: Path) -> dict[str, Any]:
    locks = verify_file_locks(repo_root, IMMUTABLE_AUTHORITY_LOCKS)
    s_payload = json.loads((repo_root / S_JSON).read_text(encoding="utf-8"))
    route6_records = tuple(s_payload["routes"]["6"]["candidates"])
    route10_augmented_records = tuple(s_payload["routes"]["10"]["candidates"])
    route10_production_records = tuple(
        record
        for record in route10_augmented_records
        if record["authority"] != "Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE"
    )
    q_record = next(
        record for record in route10_augmented_records if record["fingerprint"] == ROUTE10_Q
    )
    if q_record["authority"] != "Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE":
        raise RuntimeError("Q authority was relabeled in committed S evidence")

    route6, route6_access = _selection_result("6", route6_records)
    route10, route10_access = _selection_result("10", route10_production_records)
    augmented, augmented_access = _selection_result("10", route10_augmented_records)
    bucket = {
        "role": "REVIEW_ONLY_CORROBORATION_NOT_V3_SELECTION",
        "route_6": _corroborating_metric_path(
            calibration_records=route6_records,
            selection_records=route6_records,
            anchor_fingerprint=ROUTE6_ANCHOR,
            metric="bucket_exposure_equivalent",
        ),
        "route_10_production_only": _corroborating_metric_path(
            calibration_records=route10_production_records,
            selection_records=route10_production_records,
            anchor_fingerprint=ROUTE10_ANCHOR,
            metric="bucket_exposure_equivalent",
        ),
        "route_10_q_augmented": _corroborating_metric_path(
            calibration_records=route10_production_records,
            selection_records=route10_augmented_records,
            anchor_fingerprint=ROUTE10_ANCHOR,
            metric="bucket_exposure_equivalent",
        ),
    }
    _assert_exact_route_locks(route6, route10, augmented, bucket)
    q_audit = next(
        row
        for row in _result_payload(augmented, route10_augmented_records, augmented_access)[
            "candidate_metric_audit"
        ]
        if row["fingerprint"] == ROUTE10_Q
    )

    return {
        "milestone": "PR62-T",
        "source_commit": SOURCE_COMMIT,
        "S_authority_hashes": {
            "json": locks[S_JSON.as_posix()],
            "markdown": locks[S_MARKDOWN.as_posix()],
        },
        "v3_profile": OPERATIONAL_SELECTION_PROFILE_V3,
        "priority_order": list(PRIORITY_ORDER_V3),
        "primary_materiality_metric": PRIMARY_MATERIALITY_METRIC_V3,
        "metric_definition": {
            "directional_departures": "FINITE_STRICTLY_INCREASING_EXACT_TIMES",
            "demand_support": "FINITE_ORDERED_CONTIGUOUS_NON_OVERLAPPING_POSITIVE_WIDTH_NON_NEGATIVE_DEMAND",
            "demand_density": "NORMALIZED_OBSERVED_DEMAND_MASS_DIVIDED_BY_BUCKET_WIDTH",
            "service_density": "ONE_DIVIDED_BY_HEADWAY_AND_N_MINUS_ONE_ON_EACH_INTERDEPARTURE_INTERVAL",
            "integration": "EXACT_UNION_OF_DEMAND_BOUNDARIES_DEPARTURES_AND_DOMAIN_ENDPOINTS",
            "directional_tv": "0.5_TIMES_INTEGRAL_ABSOLUTE_SERVICE_MINUS_DEMAND_DENSITY",
            "directional_equivalent": "DIRECTIONAL_TRIP_COUNT_TIMES_DIRECTIONAL_TV",
            "pair_equivalent": "OUTBOUND_PLUS_INBOUND_EQUIVALENT",
            "numerical_epsilon": NUMERICAL_EPSILON,
            "discretization": False,
            "point_counting": False,
            "minute_rounding": False,
            "bucket_boundary_reassignment": False,
        },
        "calibration_semantics": {
            "legacy_te_calibration_band_trips": LEGACY_TE_CALIBRATION_BAND_TRIPS_V3,
            "role": "CALIBRATION_QUANTUM_ONLY_NOT_FINAL_V3_ELIGIBILITY_GATE",
            "route_local_bound": "MAX_CONTINUOUS_DELTA_OF_LEGACY_TE_CALIBRATION_SET",
            "final_materiality": "ALL_ACCESS_SAFE_CANDIDATES_WITH_CONTINUOUS_DELTA_AT_MOST_ROUTE_LOCAL_BOUND_PLUS_EPSILON",
        },
        "no_universal_continuous_materiality_band": True,
        "route_results": {
            "6_current_production": _result_payload(route6, route6_records, route6_access),
            "10_current_production": _result_payload(
                route10, route10_production_records, route10_access
            ),
            "10_q_augmented_review": _result_payload(
                augmented, route10_augmented_records, augmented_access
            ),
        },
        "route_10_q_required_snapshot": {
            **q_audit,
            "actual_service_regime_count": q_record["operations"]["actual_service_regime_count"],
            "headways": {
                direction: q_record["operations"]["directions"][direction][
                    "service_regime_headways"
                ]
                for direction in ("outbound", "inbound")
            },
        },
        "bucket_exposure_corroboration": bucket,
        "intermediate_winner_comparison": {
            "continuous_production_only_winner": route10.selected_pair_fingerprint,
            "bucket_production_only_winner": bucket["route_10_production_only"]["selected"],
            "intermediate_winners_identical": (
                route10.selected_pair_fingerprint == bucket["route_10_production_only"]["selected"]
            ),
            "q_augmented_winners_converge_on_q": (
                augmented.selected_pair_fingerprint == ROUTE10_Q
                and bucket["route_10_q_augmented"]["selected"] == ROUTE10_Q
            ),
        },
        "q_production_boundary": {
            "fingerprint": ROUTE10_Q,
            "authority": q_record["authority"],
            "generated_by_current_production_search": False,
            "current_production_frontier_count": len(route10_production_records),
            "q_augmented_review_universe_count": len(route10_augmented_records),
        },
        "input_provenance": {
            "authority": "COMMITTED_PR62_S_CANDIDATE_RECORDS",
            "coordinator_replays_executed_by_T": 0,
            "production_searches_executed_by_T": 0,
            "private_workbook_opened_by_T": False,
        },
        "immutable_file_locks": locks,
        "production_guards": dict(PRODUCTION_GUARDS),
        "classification": "PHASE_ROBUST_MATERIALITY_POLICY_V3_FROZEN",
        "next_milestone": "PR62-U_LOCAL_RHYTHM_CANONICALIZATION_SEARCH_INTEGRATION",
        "readiness": {
            "READY_FOR_LOCAL_RHYTHM_SEARCH_INTEGRATION": True,
            "READY_FOR_FINAL_PILOT_USE": False,
            "READY_FOR_PR62_COMPLETION_REVIEW": False,
        },
        "READY_FOR_LOCAL_RHYTHM_SEARCH_INTEGRATION": True,
        "READY_FOR_FINAL_PILOT_USE": False,
        "READY_FOR_PR62_COMPLETION_REVIEW": False,
        "readiness_reason": (
            "V3 policy is frozen, but Q is not generated by the current live search candidate "
            "universe and canonical XLSX files remain P/V2 products."
        ),
        "deterministic_render": True,
    }


def _fmt(value: Any) -> str:
    return f"{value:.16g}" if isinstance(value, float) else str(value)


def render_markdown(payload: Mapping[str, Any]) -> str:
    route6 = payload["route_results"]["6_current_production"]
    route10 = payload["route_results"]["10_current_production"]
    augmented = payload["route_results"]["10_q_augmented_review"]
    bucket = payload["bucket_exposure_corroboration"]
    guards = payload["production_guards"]
    lines = [
        "# PR62-T — Phase-robust materiality policy V3 freeze",
        "",
        f"Classification: **{payload['classification']}**.",
        "",
        "## Frozen semantics",
        "",
        f"- Profile: `{payload['v3_profile']}`.",
        f"- Primary metric: `{payload['primary_materiality_metric']}`.",
        "- SSE and production point-TE establish one unique common anchor.",
        "- The old +1.0 point-TE rule creates only the legacy semantic calibration set.",
        "- Its maximum continuous-exposure delta defines the smallest route-local preservation envelope.",
        "- Final admitted candidates are selected only by the frozen rhythm tuple, fleet tuple, then fingerprint on an exact tie.",
        "- No universal continuous threshold, percentile, weighted score, or micro-rhythm hard gate was introduced.",
        "",
        "## Exact results",
        "",
        "| Universe | Calibration | Continuous bound | Materiality | Selected | Classification |",
        "|---|---:|---:|---:|---|---|",
        f"| Route 6 production | {route6['legacy_calibration_set_count']} | {_fmt(route6['continuous_preservation_bound'])} | {route6['phase_robust_materiality_set_count']} | `{route6['selected_pair_fingerprint']}` | `{route6['classification']}` |",
        f"| Route 10 production | {route10['legacy_calibration_set_count']} | {_fmt(route10['continuous_preservation_bound'])} | {route10['phase_robust_materiality_set_count']} | `{route10['selected_pair_fingerprint']}` | `{route10['classification']}` |",
        f"| Route 10 Q-augmented review | {augmented['legacy_calibration_set_count']} | {_fmt(augmented['continuous_preservation_bound'])} | {augmented['phase_robust_materiality_set_count']} | `{augmented['selected_pair_fingerprint']}` | `{augmented['classification']}` |",
        "",
        "Q remains `Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE`; V3 alone does not make the live production search generate Q.",
        "",
        "## Bucket-exposure corroboration",
        "",
        f"- Route 6 bound `{_fmt(bucket['route_6']['preservation_bound'])}` selects the anchor.",
        f"- Route 10 production-only bound `{_fmt(bucket['route_10_production_only']['preservation_bound'])}` selects `{bucket['route_10_production_only']['selected']}`, which differs from the primary continuous interim winner.",
        f"- Route 10 Q-augmented review selects Q `{bucket['route_10_q_augmented']['selected']}`. Both phase-robust definitions converge on Q once Q exists in the universe.",
        "",
        "## Production boundary and readiness",
        "",
        "- Coordinator/search replays executed by T: `0`.",
        "- V1 and V2 selectors, coordinator, search, compiler, validators, and canonical XLSX files remain locked.",
        f"- Next milestone: `{payload['next_milestone']}`.",
        "- `READY_FOR_LOCAL_RHYTHM_SEARCH_INTEGRATION = true`.",
        "- `READY_FOR_FINAL_PILOT_USE = false`.",
        "- `READY_FOR_PR62_COMPLETION_REVIEW = false`.",
        "",
        "## Production guards",
        "",
    ]
    lines.extend(f"- `{key} = {value}`" for key, value in guards.items())
    lines.append("")
    return "\n".join(lines)


def write_evidence(repo_root: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    json_first = canonical_json_bytes(payload)
    json_second = canonical_json_bytes(payload)
    markdown_first = render_markdown(payload).encode("utf-8")
    markdown_second = render_markdown(payload).encode("utf-8")
    if json_first != json_second or markdown_first != markdown_second:
        raise RuntimeError("T evidence render is not deterministic")
    json_path = repo_root / OUTPUT_JSON
    markdown_path = repo_root / OUTPUT_MARKDOWN
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_bytes(json_first)
    markdown_path.write_bytes(markdown_first)
    return {
        "json": {"bytes": len(json_first), "sha256": _sha256_bytes(json_first)},
        "markdown": {
            "bytes": len(markdown_first),
            "sha256": _sha256_bytes(markdown_first),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    payload = build_evidence(repo_root)
    print(json.dumps(write_evidence(repo_root, payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
