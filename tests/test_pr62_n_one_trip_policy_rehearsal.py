from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import scripts.run_pr62_n_one_trip_policy_rehearsal as pr62_n

ANCHOR_6 = "ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b"
ANCHOR_10 = "bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c"
SELECTED_10 = "e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24"


def _candidate(
    fingerprint: str,
    *,
    sse: float,
    te: float,
    rhythm: tuple[int, int, int, int] = (8, 12, 6, 0),
    fleet: tuple[int, int, int] = (12, 100, 10),
    feasible: bool = True,
    access_safe: bool = True,
) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "observed_demand_mismatch": sse,
        "pair_trip_equivalent_error": te,
        "rhythm_simplicity_tuple": list(rhythm),
        "fleet_efficiency_tuple": list(fleet),
        "fleet_required": fleet[0],
        "total_excess_terminal_wait": fleet[1],
        "max_excess_terminal_wait": fleet[2],
        "average_wait_minutes": 6.0,
        "directional_maximum_bucket_wait_minutes": {"outbound": 10.0, "inbound": 11.0},
        "tail_headways": {"outbound": 15, "inbound": 15},
        "hard_operational_feasible": feasible,
        "scenario_b_directional_max_access_safe": access_safe,
    }


def test_common_sse_and_te_best_establishes_anchor() -> None:
    result = pr62_n.rehearse_route(
        [_candidate("A", sse=1.0, te=10.0), _candidate("B", sse=2.0, te=11.0)]
    )

    assert result["top_anchor_concordant"] is True
    assert result["common_demand_fit_anchor"]["fingerprint"] == "A"


def test_conflicting_metric_bests_stop_before_materiality_selection() -> None:
    result = pr62_n.rehearse_route(
        [_candidate("A", sse=1.0, te=11.0), _candidate("B", sse=2.0, te=10.0)]
    )

    assert result["classification"] == "DEMAND_FIT_ANCHOR_CONFLICT"
    assert result["selected"] is None
    assert result["materiality_set"] == []


def test_one_trip_band_uses_epsilon_at_exact_boundary() -> None:
    result = pr62_n.rehearse_route(
        [
            _candidate("A", sse=1.0, te=10.0),
            _candidate("B", sse=2.0, te=10.7),
            _candidate("C", sse=3.0, te=11.0),
            _candidate("D", sse=4.0, te=11.0000001),
        ]
    )

    assert [row["fingerprint"] for row in result["materiality_set"]] == ["A", "B", "C"]


def test_rhythm_selects_simpler_candidate_inside_band() -> None:
    result = pr62_n.rehearse_route(
        [
            _candidate("A", sse=1.0, te=10.0, rhythm=(8, 12, 6, 0)),
            _candidate("B", sse=2.0, te=10.7, rhythm=(6, 10, 5, 0)),
        ]
    )

    assert result["selected"]["fingerprint"] == "B"
    assert result["classification"] == "ONE_TRIP_BAND_SELECTS_SIMPLER_ALTERNATIVE"


def test_better_rhythm_outside_band_cannot_displace_anchor() -> None:
    result = pr62_n.rehearse_route(
        [
            _candidate("A", sse=1.0, te=10.0, rhythm=(8, 12, 6, 0)),
            _candidate("B", sse=2.0, te=11.2, rhythm=(3, 5, 3, 0)),
        ]
    )

    assert result["selected"]["fingerprint"] == "A"


def test_fleet_efficiency_breaks_exact_rhythm_tie() -> None:
    result = pr62_n.rehearse_route(
        [
            _candidate("A", sse=1.0, te=10.0, fleet=(12, 100, 10)),
            _candidate("B", sse=2.0, te=10.7, fleet=(11, 200, 20)),
        ]
    )

    assert result["selected"]["fingerprint"] == "B"


def test_infeasible_candidate_is_excluded_before_materiality() -> None:
    result = pr62_n.rehearse_route(
        [
            _candidate("A", sse=1.0, te=10.0),
            _candidate("B", sse=0.5, te=9.5, rhythm=(1, 1, 1, 0), feasible=False),
        ]
    )

    assert result["selected"]["fingerprint"] == "A"
    assert result["stage_counts"]["hard_operational_feasible"] == 1


def test_access_unsafe_candidate_is_excluded_before_materiality() -> None:
    result = pr62_n.rehearse_route(
        [
            _candidate("A", sse=1.0, te=10.0),
            _candidate("B", sse=0.5, te=9.5, rhythm=(1, 1, 1, 0), access_safe=False),
        ]
    )

    assert result["selected"]["fingerprint"] == "A"
    assert result["stage_counts"]["directional_access_safe"] == 1


def test_lower_rank_sse_disagreement_does_not_override_rhythm_inside_band() -> None:
    result = pr62_n.rehearse_route(
        [
            _candidate("A", sse=1.0, te=10.0, rhythm=(8, 12, 6, 0)),
            _candidate("B", sse=2.0, te=10.8, rhythm=(7, 10, 5, 0)),
            _candidate("C", sse=3.0, te=10.7, rhythm=(6, 10, 5, 0)),
        ]
    )

    assert result["in_band_pairwise_rank_disagreement_count"] == 1
    assert result["selected"]["fingerprint"] == "C"
    assert result["in_band_selection_deterministic"] is True


def test_negative_delta_te_fails_closed_as_inconsistent_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = [_candidate("A", sse=1.0, te=10.0), _candidate("B", sse=2.0, te=9.0)]
    monkeypatch.setattr(pr62_n, "_metric_best", lambda rows, metric: rows[0])

    result = pr62_n.rehearse_route(candidates)

    assert result["classification"] == "N_EVIDENCE_INCONCLUSIVE"
    assert result["selected"] is None


def test_identical_metrics_use_fingerprint_only_as_deterministic_identity() -> None:
    result = pr62_n.rehearse_route(
        [_candidate("B", sse=1.0, te=10.0), _candidate("A", sse=1.0, te=10.0)]
    )

    assert result["selected"]["fingerprint"] == "A"
    assert result["classification"] == "ONE_TRIP_BAND_METRICALLY_EQUIVALENT_TIE"
    assert result["selection_detail_classification"] == (
        "METRICALLY_EQUIVALENT_DETERMINISTIC_TIEBREAK"
    )


def test_committed_evidence_rehearsal_locks_both_routes() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    payload = pr62_n.build_evidence(repo_root)

    assert payload["routes"]["6"]["selected"]["fingerprint"] == ANCHOR_6
    assert payload["routes"]["6"]["classification"] == "ONE_TRIP_BAND_SELECTS_ANCHOR"
    assert payload["routes"]["10"]["selected"]["fingerprint"] == SELECTED_10
    assert payload["routes"]["10"]["classification"] == (
        "ONE_TRIP_BAND_SELECTS_SIMPLER_ALTERNATIVE"
    )
    assert payload["routes"]["10"]["common_demand_fit_anchor"]["fingerprint"] == ANCHOR_10


def test_committed_evidence_records_policy_decision_and_guards() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    payload = pr62_n.build_evidence(repo_root)

    assert payload["cross_route_classification"] == "ONE_TRIP_POLICY_REHEARSAL_SUPPORTED"
    assert payload["READY_FOR_ONE_TRIP_POLICY_FREEZE"] is True
    assert payload["READY_FOR_FINAL_XLSX_RECERTIFICATION"] is False
    assert payload["routes"]["6"]["policy_health"] == (
        "REHEARSAL_POLICY_COHERENT_BUT_COMPLEX_ANCHOR_RETAINED"
    )
    assert payload["routes"]["10"]["policy_health"] == ("REHEARSAL_POLICY_COHERENT_SIMPLICITY_GAIN")
    assert payload["production_guards"]["one_trip_threshold_used_in_rehearsal"] is True
    assert payload["production_guards"]["one_trip_threshold_added_to_production_selector"] is False


def test_route_10_tradeoff_and_access_exclusion_are_explicit() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    route = pr62_n.build_evidence(repo_root)["routes"]["10"]

    assert route["selected_vs_anchor_tradeoff"]["delta_TE"] == pytest.approx(0.7122514457735889)
    assert route["selected_vs_anchor_tradeoff"]["delta_SSE"] > 0
    assert route["selected_vs_anchor_tradeoff"]["average_wait_delta_seconds_per_passenger"] > 0
    assert route["selected_vs_anchor_tradeoff"]["fleet_required_delta"] == -1
    assert route["access_exclusions"]["classification"] == "ACCESS_EXCLUDED_BEFORE_MATERIALITY"


def test_route_6_human_final_is_context_only_and_not_in_band() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    route = pr62_n.build_evidence(repo_root)["routes"]["6"]

    assert route["human_final_context"]["classification"] == "POST_SEARCH_EXPERT_BENCHMARK"
    assert route["human_final_context"]["selection_eligible"] is False
    assert all(row["fingerprint"] != "HUMAN_FINAL" for row in route["materiality_set"])


def test_prior_l_m_and_m1_artifacts_are_hash_locked() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    expected = {
        "docs/engine/evidence/PR62_L_DOMAIN_PRIORITY_SELECTOR.json": (
            450425,
            "91925a47e27abdcf524c73b38c33cd446559b887a32f6708f624eacc3e62b843",
        ),
        "docs/engine/evidence/PR62_L_DOMAIN_PRIORITY_SELECTOR.md": (
            4623,
            "a1106de9c6d0f33d56de8eb8c71433edbaed4ba5e86ec79d1c6fece597e013f0",
        ),
        "docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.json": (
            525934,
            "f9c5438c3d4b0b871b8fc1ec24a9dcd3a392efd76e85e7ab9ec385532c98c0c9",
        ),
        "docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.md": (
            5828,
            "b580540645bd3c941d2e14425b67f2c2773bc684a9e28836407df21f8030a309",
        ),
        "docs/engine/evidence/PR62_M1_RANK_CONCORDANCE_CLARIFICATION.json": (
            99878,
            "fcb77df73cc5bdf39738a7e81300456870938cab489144fbe2f59a414fbffcda",
        ),
        "docs/engine/evidence/PR62_M1_RANK_CONCORDANCE_CLARIFICATION.md": (
            6815,
            "ba9e989643a96dbee2079e104913355ca8b8184892ee4ca9599b9c3f89024cbf",
        ),
    }

    for relative_path, (size, digest) in expected.items():
        path = repo_root / relative_path
        assert path.stat().st_size == size
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_canonical_renderers_are_byte_identical() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    first = pr62_n.build_evidence(repo_root)
    second = pr62_n.build_evidence(repo_root)

    assert pr62_n._canonical_json_bytes(first) == pr62_n._canonical_json_bytes(second)
    assert pr62_n._markdown(first) == pr62_n._markdown(second)
    assert "\r" not in pr62_n._markdown(first)
