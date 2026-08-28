from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

import scripts.run_pr62_r_demand_fit_metric_validity as r

REPO_ROOT = Path(__file__).resolve().parents[1]


def _bucket(start: int, end: int, demand: float) -> dict[str, float | int]:
    return {"start": start, "end": end, "observed_demand": demand}


def test_exposure_mass_splits_interval_across_bucket_edge() -> None:
    metrics = r.bucket_exposure_metrics(
        [7 * 3600 + 50 * 60, 8 * 3600 + 10 * 60],
        [
            _bucket(7 * 3600 + 30 * 60, 8 * 3600, 1.0),
            _bucket(8 * 3600, 8 * 3600 + 30 * 60, 1.0),
        ],
    )

    assert [row["exposure_mass"] for row in metrics["buckets"]] == pytest.approx([0.5, 0.5])
    assert metrics["total_exposure_mass"] == pytest.approx(1.0)


def test_point_count_edge_jump_moves_one_whole_trip_but_exposure_is_smooth() -> None:
    buckets = [_bucket(27000, 28800, 3.0), _bucket(28800, 30600, 1.0)]
    before = [27000, 28740, 30600]
    after = [27000, 28800, 30600]

    point_before = r.production_point_metrics(before, buckets)
    point_after = r.production_point_metrics(after, buckets)
    exposure_before = r.bucket_exposure_metrics(before, buckets)
    exposure_after = r.bucket_exposure_metrics(after, buckets)

    assert point_before["bucket_service_counts"] == [2, 0]
    assert point_after["bucket_service_counts"] == [1, 1]
    assert point_before["bucket_service_counts"][0] - point_after["bucket_service_counts"][0] == 1
    assert abs(exposure_after["equivalent"] - exposure_before["equivalent"]) < abs(
        point_after["te"] - point_before["te"]
    )


def test_service_and_bucket_exposure_conserve_n_minus_one_units() -> None:
    departures = [0, 600, 1800, 3600]
    buckets = [_bucket(0, 1800, 1.0), _bucket(1800, 3600, 1.0)]

    continuous = r.continuous_exposure_metrics(departures, buckets)
    bucket = r.bucket_exposure_metrics(departures, buckets)

    assert continuous["service_exposure_integral"] == pytest.approx(3.0)
    assert bucket["total_exposure_mass"] == pytest.approx(3.0)


def test_demand_density_integral_reproduces_observed_mass() -> None:
    metrics = r.continuous_exposure_metrics(
        [0, 1800, 3600],
        [_bucket(0, 1800, 7.5), _bucket(1800, 3600, 2.5)],
    )

    assert metrics["demand_integral"] == pytest.approx(10.0)
    assert metrics["total_demand"] == pytest.approx(10.0)


def test_continuous_tv_is_zero_for_proportional_piecewise_densities() -> None:
    metrics = r.continuous_exposure_metrics(
        [0, 1800, 3600],
        [_bucket(0, 1800, 1.0), _bucket(1800, 3600, 1.0)],
    )

    assert metrics["tv"] == pytest.approx(0.0, abs=1e-12)
    assert metrics["equivalent"] == pytest.approx(0.0, abs=1e-12)
    assert metrics["continuous_l2"] == pytest.approx(0.0, abs=1e-12)


def test_continuous_tv_integrates_exact_union_of_breakpoints() -> None:
    metrics = r.continuous_exposure_metrics(
        [0, 1200, 3600],
        [_bucket(0, 1800, 1.0), _bucket(1800, 3600, 1.0)],
    )

    assert metrics["breakpoints"] == [0, 1200, 1800, 3600]
    assert metrics["tv"] == pytest.approx(1.0 / 6.0)


def test_rank_reversal_classifies_bucket_edge_aliasing() -> None:
    decision = r.classify_p_vs_q(
        p_production_te=1.0,
        q_production_te=2.0,
        p_bucket_equivalent=1.5,
        q_bucket_equivalent=1.5,
        p_continuous_equivalent=1.6,
        q_continuous_equivalent=1.4,
        production_vs_bucket_rank_disagreements=1,
        production_vs_continuous_rank_disagreements=1,
    )

    assert decision["POINT_COUNT_PREFERS_P"] is True
    assert decision["BUCKET_EXPOSURE_EQUIVALENT_TIE"] is True
    assert decision["CONTINUOUS_EXPOSURE_PREFERS_Q"] is True
    assert decision["root_classification"] == "BUCKET_EDGE_ALIASING_CONFIRMED"


def test_no_false_aliasing_when_all_metrics_prefer_p() -> None:
    decision = r.classify_p_vs_q(
        p_production_te=1.0,
        q_production_te=2.0,
        p_bucket_equivalent=1.0,
        q_bucket_equivalent=2.0,
        p_continuous_equivalent=1.0,
        q_continuous_equivalent=2.0,
        production_vs_bucket_rank_disagreements=0,
        production_vs_continuous_rank_disagreements=0,
    )

    assert decision["POINT_COUNT_PREFERS_P"] is True
    assert decision["BUCKET_EXPOSURE_PREFERS_Q"] is False
    assert decision["CONTINUOUS_EXPOSURE_PREFERS_Q"] is False
    assert decision["root_classification"] != "BUCKET_EDGE_ALIASING_CONFIRMED"


@pytest.mark.parametrize(
    "buckets",
    [
        [_bucket(0, 100, 1.0), _bucket(101, 200, 1.0)],
        [_bucket(0, 101, 1.0), _bucket(100, 200, 1.0)],
    ],
)
def test_malformed_demand_support_fails_closed(
    buckets: list[dict[str, float | int]],
) -> None:
    with pytest.raises(ValueError, match="demand support"):
        r.continuous_exposure_metrics([0, 100, 200], buckets)


def test_metrics_reject_nonfinite_or_unordered_inputs() -> None:
    with pytest.raises(ValueError):
        r.continuous_exposure_metrics([0, 100, 100], [_bucket(0, 100, 1.0), _bucket(100, 200, 1.0)])
    with pytest.raises(ValueError):
        r.continuous_exposure_metrics(
            [0, 100, 200],
            [_bucket(0, 100, math.inf), _bucket(100, 200, 1.0)],
        )


def test_departure_edge_audit_reports_half_open_membership_and_crossing() -> None:
    audit = r.departure_edge_crossing_audit(
        [0, 1740, 3600],
        [0, 1800, 3600],
        [_bucket(0, 1800, 1.0), _bucket(1800, 3601, 1.0)],
    )

    assert audit["total_departures_changed"] == 1
    assert audit["bucket_changing_departures"] == 1
    assert audit["total_bucket_boundary_crossings"] == 1
    assert audit["changed_departures"][0] == {
        "sequence": 2,
        "P_time_seconds": 1740,
        "Q_time_seconds": 1800,
        "signed_shift_minutes": 1.0,
        "absolute_shift_minutes": 1.0,
        "P_bucket_index": 0,
        "Q_bucket_index": 1,
        "bucket_membership_changed": True,
        "crossed_bucket_boundaries_seconds": [1800],
    }
    assert audit["absolute_shift_minutes"] == {"sum": 1.0, "median": 1.0, "max": 1.0}
    assert audit["bucket_changing_shift_distribution_minutes"] == [{"shift": 1.0, "count": 1}]


def test_immutable_lock_lookup_normalizes_windows_path_separators() -> None:
    record = {"sha256": "abc", "unchanged": True}
    locks = {"docs/engine/evidence/example.json": record}

    assert r.immutable_lock_record(locks, Path(r"docs\engine\evidence\example.json")) == record


def test_preserved_reports_must_be_byte_identical_and_match_expected_fingerprints(
    tmp_path: Path,
) -> None:
    report = {
        "pareto_frontier": [
            {
                "pair_fingerprint": "candidate-a",
                "outbound": {"compile_variant": {"exact_departures": [0, 60]}},
                "inbound": {"compile_variant": {"exact_departures": [30, 90]}},
            }
        ]
    }
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    encoded = r.canonical_json_bytes(report)
    first.write_bytes(encoded)
    second.write_bytes(encoded)

    loaded, provenance = r.load_preserved_frontier_reports(
        first, second, expected_fingerprints=["candidate-a"]
    )

    assert loaded[0]["pair_fingerprint"] == "candidate-a"
    assert provenance["reports_byte_identical"] is True
    assert provenance["fingerprints_match_PR62_I"] is True

    second.write_bytes(encoded + b"\n")
    with pytest.raises(RuntimeError, match="byte-identical"):
        r.load_preserved_frontier_reports(first, second, expected_fingerprints=["candidate-a"])


def test_preserved_report_fingerprint_mismatch_fails_closed(tmp_path: Path) -> None:
    report = {"pareto_frontier": [{"pair_fingerprint": "candidate-a"}]}
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    encoded = r.canonical_json_bytes(report)
    first.write_bytes(encoded)
    second.write_bytes(encoded)

    with pytest.raises(RuntimeError, match="PR62-I"):
        r.load_preserved_frontier_reports(first, second, expected_fingerprints=["candidate-b"])


def test_committed_r_evidence_is_complete_deterministic_and_review_only() -> None:
    payload = json.loads((REPO_ROOT / r.OUTPUT_JSON).read_text(encoding="utf-8"))

    assert payload["milestone"] == "PR62-R"
    assert payload["Q_commit_SHA"] == "e2425e5c77cdfd9832aff8cb4cda218424b2c323"
    assert payload["READY_FOR_PR62_COMPLETION_REVIEW"] is False
    assert payload["READY_FOR_FINAL_PILOT_USE"] is False
    assert payload["metric_authority"]["production_point_metrics_changed"] is False
    assert payload["metric_authority"]["continuous_metrics_added_to_production"] is False
    assert payload["coordinator_replay"]["calls_by_route"] == {"10": 1, "6": 2}
    assert payload["coordinator_replay"]["fingerprints_validated_before_use"] is True
    assert payload["replay_provenance"]["route_6"] == {
        "attempts": 2,
        "recovery_replay_authorized": True,
        "first_attempt_search_completed": True,
        "first_attempt_postprocessing_lost": True,
        "failure_stage": "WINDOWS_PATH_NORMALIZATION_POSTPROCESSING",
        "recovery_scope": "ROUTE_6_ONLY_COMPLETE_ACCESS_SAFE_AUDIT",
        "recovery_replay_fingerprints_match_PR62_I": True,
        "same_frozen_inputs_code_seed_and_budget": True,
    }
    assert payload["replay_provenance"]["route_10"]["recovery_replay_authorized"] is False
    assert payload["replay_provenance"]["route_10"]["recovery_replay_executed"] is False
    assert payload["replay_provenance"]["route_10"]["preserved_report_count"] == 2
    assert payload["replay_provenance"]["route_10"]["reports_byte_identical"] is True
    assert payload["routes"]["10"]["production_candidate_count"] == 7
    assert payload["routes"]["6"]["production_candidate_count"] == 41
    assert len(payload["routes"]["10"]["ranking_table"]) == 7
    assert len(payload["routes"]["6"]["ranking_table"]) == 41
    assert payload["route10_P_vs_Q"]["P_fingerprint"] == r.ROUTE10_P_PAIR
    assert payload["route10_P_vs_Q"]["Q_fingerprint"] == r.ROUTE10_Q_PAIR
    assert payload["candidate_universe"]["Q_canonical"]["authority"] == (
        "Q_CANONICAL_EXTERNAL_REVIEW_CANDIDATE"
    )
    assert r.ROUTE10_Q_PAIR not in payload["routes"]["10"]["production_fingerprints"]
    assert payload["production_guards"] == r.EXPECTED_PRODUCTION_GUARDS
    assert (REPO_ROOT / r.OUTPUT_JSON).read_bytes() == r.canonical_json_bytes(payload)
    assert (REPO_ROOT / r.OUTPUT_MARKDOWN).read_bytes() == r.render_markdown(payload).encode(
        "utf-8"
    )
    assert (REPO_ROOT / r.OUTPUT_JSON).stat().st_size < 1_000_000


def test_all_production_candidate_metrics_are_finite_and_ranked() -> None:
    payload = json.loads((REPO_ROOT / r.OUTPUT_JSON).read_text(encoding="utf-8"))
    metric_keys = (
        "production_SSE",
        "production_TE",
        "bucket_exposure_SSE",
        "bucket_exposure_equivalent",
        "continuous_exposure_equivalent",
    )

    for route_id in ("6", "10"):
        route = payload["routes"][route_id]
        for row in route["ranking_table"]:
            assert all(math.isfinite(row[key]) for key in metric_keys)
            assert all(row["ranks"][key] >= 1 for key in metric_keys)
        assert set(route["best_sets"]) == set(metric_keys)
        assert set(route["top_5"]) == set(metric_keys)
        assert set(route["pairwise_rank_disagreement_counts"]) == {
            "production_TE_vs_bucket_exposure_equivalent",
            "production_TE_vs_continuous_exposure_equivalent",
            "production_SSE_vs_bucket_exposure_SSE",
        }


def test_route_locks_and_evidence_authorities_remain_immutable() -> None:
    payload = json.loads((REPO_ROOT / r.OUTPUT_JSON).read_text(encoding="utf-8"))
    for relative, expected in r.IMMUTABLE_FILE_LOCKS.items():
        actual = r.sha256_file(REPO_ROOT / relative)
        assert actual == expected
        assert payload["immutable_file_locks"][relative]["sha256"] == expected
        assert payload["immutable_file_locks"][relative]["unchanged"] is True


def test_route10_tradeoff_and_edge_audits_are_signed_and_complete() -> None:
    payload = json.loads((REPO_ROOT / r.OUTPUT_JSON).read_text(encoding="utf-8"))
    tradeoff = payload["route10_P_vs_Q"]
    required_deltas = {
        "production_SSE",
        "production_TE",
        "bucket_exposure_SSE",
        "bucket_exposure_equivalent",
        "continuous_exposure_TV",
        "continuous_exposure_equivalent",
        "continuous_L2",
    }

    assert set(tradeoff["Q_minus_P"]["pair"]) == required_deltas
    assert set(tradeoff["Q_minus_P"]["outbound"]) == required_deltas
    assert set(tradeoff["Q_minus_P"]["inbound"]) == required_deltas
    assert payload["route10_anchor_vs_Q"]["Q_minus_anchor"].keys() == {
        "production_TE",
        "bucket_exposure_equivalent",
        "continuous_exposure_equivalent",
    }
    assert payload["bucket_edge_contribution_audit"]["directions"].keys() == {
        "outbound",
        "inbound",
    }
    anchor_bucket_audit = payload["bucket_edge_contribution_audit"]["anchor_vs_Q"]
    anchor_contribution_delta = sum(
        row["Q_minus_anchor_production_TE_contribution"]
        for direction in ("outbound", "inbound")
        for row in anchor_bucket_audit["directions"][direction]["buckets"]
    )
    assert anchor_contribution_delta == pytest.approx(
        payload["route10_anchor_vs_Q"]["Q_minus_anchor"]["production_TE"]
    )
    assert payload["departure_edge_crossing_audit"]["directions"].keys() == {
        "outbound",
        "inbound",
    }
    assert payload["root_classification"] in {
        "BUCKET_EDGE_ALIASING_CONFIRMED",
        "BUCKET_EDGE_ALIASING_MATERIAL_BUT_NOT_DECISIVE",
        "DEMAND_FIT_LOSS_PERSISTS_UNDER_CONTINUOUS_EXPOSURE",
        "MIXED_DEMAND_FIT_METRIC_EVIDENCE",
        "R_EVIDENCE_INCONCLUSIVE",
    }


def test_route6_control_and_anchor_stability_have_exact_states() -> None:
    payload = json.loads((REPO_ROOT / r.OUTPUT_JSON).read_text(encoding="utf-8"))

    assert payload["anchor_validity"]["classification"] in {
        "ANCHOR_STABLE_ACROSS_DEMAND_FIT_SEMANTICS",
        "ANCHOR_SEMANTICS_SENSITIVE",
    }
    assert payload["route6_control"]["classification"] in {
        "ROUTE6_CONTROL_TOP_STABLE",
        "ROUTE6_CONTROL_TOP_SEMANTICS_SENSITIVE",
    }
    assert payload["next_milestone_recommendation"].startswith("PR62-S_")
