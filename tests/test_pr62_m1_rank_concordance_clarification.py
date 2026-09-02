from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import scripts.run_pr62_m1_rank_concordance_clarification as pr62_m1


def _candidate(
    fingerprint: str,
    *,
    sse: float,
    te: float,
    rhythm: tuple[int, int, int, int],
    fleet: tuple[int, int, int] = (10, 20, 5),
    wait: float = 6.0,
) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "observed_demand_mismatch": sse,
        "pair_trip_equivalent_error": te,
        "rhythm_simplicity_tuple": list(rhythm),
        "fleet_efficiency_tuple": list(fleet),
        "fleet_required": fleet[0],
        "average_wait_minutes": wait,
        "directional_maximum_bucket_wait_minutes": {"outbound": 10.0, "inbound": 11.0},
    }


def test_same_best_does_not_hide_lower_rank_disagreement() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=10.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=2.0, te=12.0, rhythm=(4, 5, 5, 0)),
        _candidate("C", sse=3.0, te=11.0, rhythm=(5, 4, 5, 0)),
    )

    result = pr62_m1._analyze_candidates(candidates, selected_fingerprint="A")

    assert result["same_best_candidate"] is True
    assert result["pairwise_disagreement_count"] == 1
    assert result["full_rank_concordant"] is False


def test_different_metric_bests_classify_as_top_conflict() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=11.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=2.0, te=10.0, rhythm=(4, 5, 5, 0)),
    )

    result = pr62_m1._analyze_candidates(candidates, selected_fingerprint="A")

    assert result["classification"] == "TOP_DEMAND_FIT_METRIC_CONFLICT"


def test_first_simpler_witness_can_be_concordant_with_lower_rank_noise() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=10.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=2.0, te=11.0, rhythm=(4, 5, 5, 0)),
        _candidate("C", sse=4.0, te=13.0, rhythm=(5, 4, 5, 0)),
        _candidate("D", sse=3.0, te=14.0, rhythm=(5, 3, 5, 0)),
    )

    result = pr62_m1._analyze_candidates(candidates, selected_fingerprint="A")

    assert result["first_simpler_comparison"]["same_candidate"] is True
    assert result["first_TE_simpler_witness"]["fingerprint"] == "B"
    assert result["first_SSE_simpler_witness"]["fingerprint"] == "B"


def test_first_simpler_metric_conflict_has_specific_classification() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=10.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=2.0, te=12.0, rhythm=(4, 5, 5, 0)),
        _candidate("C", sse=3.0, te=11.0, rhythm=(3, 5, 5, 0)),
    )

    result = pr62_m1._analyze_candidates(candidates, selected_fingerprint="A")

    assert result["first_TE_simpler_witness"]["fingerprint"] == "C"
    assert result["first_SSE_simpler_witness"]["fingerprint"] == "B"
    assert result["classification"] == "TOP_CONCORDANT_FIRST_SIMPLICITY_CONFLICT"


def test_later_breakpoint_path_variation_has_specific_classification() -> None:
    candidates = (
        _candidate("A", sse=0.0, te=0.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=1.0, te=1.0, rhythm=(4, 5, 5, 0)),
        _candidate("C", sse=2.0, te=3.0, rhythm=(3, 5, 5, 0)),
        _candidate("D", sse=3.0, te=2.0, rhythm=(2, 5, 5, 0)),
    )

    result = pr62_m1._analyze_candidates(candidates, selected_fingerprint="A")

    assert result["first_simpler_comparison"]["same_candidate"] is True
    assert result["path_comparison"]["exact_sequence_identical"] is False
    assert result["classification"] == "TOP_AND_FIRST_SIMPLICITY_CONCORDANT_PATH_VARIATION"


def test_disagreement_relevance_uses_actual_role_membership() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=1.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=2.0, te=3.0, rhythm=(5, 5, 5, 0)),
        _candidate("C", sse=3.0, te=2.0, rhythm=(5, 5, 5, 0)),
    )

    non_relevant = pr62_m1._pairwise_disagreements(candidates, roles_by_fingerprint={})
    relevant = pr62_m1._pairwise_disagreements(
        candidates, roles_by_fingerprint={"B": {"TE_BREAKPOINT_PREFERRED"}}
    )

    assert non_relevant[0]["relevance_tags"] == ["NON_DECISION_RELEVANT"]
    assert "DECISION_RELEVANT" in relevant[0]["relevance_tags"]
    assert "INVOLVES_TE_BREAKPOINT_PREFERRED" in relevant[0]["relevance_tags"]


def test_one_te_envelope_reports_disagreement_without_changing_review_preference() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=10.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=3.0, te=10.7, rhythm=(4, 5, 5, 0)),
        _candidate("C", sse=2.0, te=10.9, rhythm=(3, 5, 5, 0)),
    )

    result = pr62_m1._analyze_candidates(candidates, selected_fingerprint="A")
    envelope = result["one_TE_envelope_audit"]

    assert [row["fingerprint"] for row in envelope["candidates"]] == ["A", "B", "C"]
    assert envelope["pairwise_disagreement_count"] == 1
    assert envelope["review_preferred_fingerprint"] == "C"
    assert envelope["rank_disagreement_changes_review_preferred_candidate"] is False


def test_committed_m_artifacts_are_immutable_inputs() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    expected = {
        "docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.json": (
            525934,
            "f9c5438c3d4b0b871b8fc1ec24a9dcd3a392efd76e85e7ab9ec385532c98c0c9",
        ),
        "docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.md": (
            5828,
            "b580540645bd3c941d2e14425b67f2c2773bc684a9e28836407df21f8030a309",
        ),
    }

    for relative_path, (size, digest) in expected.items():
        path = repo_root / relative_path
        assert path.stat().st_size == size
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_canonical_renderers_are_byte_identical() -> None:
    payload = {"b": [2, 1], "a": {"value": 1}}

    assert pr62_m1._canonical_json_bytes(payload) == pr62_m1._canonical_json_bytes(payload)
    assert pr62_m1._markdown(payload) == pr62_m1._markdown(payload)
    assert "\r" not in pr62_m1._markdown(payload)


def test_epsilon_ties_do_not_count_as_disagreements() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=2.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=1.0 + pr62_m1.NUMERICAL_EPSILON / 2, te=1.0, rhythm=(4, 5, 5, 0)),
    )

    assert pr62_m1._pairwise_disagreements(candidates, roles_by_fingerprint={}) == []


def test_metric_path_uses_exact_deltas_and_review_order() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=10.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=1.5, te=11.0, rhythm=(4, 5, 5, 0)),
        _candidate("C", sse=2.0, te=12.0, rhythm=(3, 5, 5, 0)),
    )

    path = pr62_m1._metric_breakpoint_path(
        candidates, metric_key="observed_demand_mismatch", delta_key="delta_SSE"
    )

    assert [row["delta_SSE"] for row in path] == pytest.approx([0.0, 0.5, 1.0])
    assert [row["preferred_fingerprint"] for row in path] == ["A", "B", "C"]


def test_minimum_sustained_palette_role_uses_the_exact_l_rhythm_tuple_order() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=10.0, rhythm=(9, 9, 5, 0)),
        _candidate("B", sse=2.0, te=11.0, rhythm=(8, 12, 5, 0)),
        _candidate("C", sse=3.0, te=12.0, rhythm=(8, 11, 6, 0)),
    )

    result = pr62_m1._analyze_candidates(candidates, selected_fingerprint="A")

    assert "MINIMUM_SUSTAINED_PALETTE" in result["decision_roles"]["C"]
    assert "MINIMUM_SUSTAINED_PALETTE" not in result["decision_roles"]["B"]


def test_te_materiality_fact_can_survive_first_simpler_metric_conflict() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=10.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=3.0, te=10.7, rhythm=(4, 5, 5, 0)),
        _candidate("C", sse=2.0, te=11.1, rhythm=(3, 5, 5, 0)),
    )
    result = pr62_m1._analyze_candidates(candidates, selected_fingerprint="A")

    route_10 = pr62_m1._route_interpretation("10", result)

    assert result["first_simpler_comparison"]["same_candidate"] is False
    assert route_10["sub_one_trip_simplicity_result_robust"] is True


def test_te_path_proves_at_least_one_te_even_when_sse_first_witness_differs() -> None:
    candidates = (
        _candidate("A", sse=1.0, te=10.0, rhythm=(5, 5, 5, 0)),
        _candidate("B", sse=3.0, te=11.2, rhythm=(4, 5, 5, 0)),
        _candidate("C", sse=2.0, te=11.5, rhythm=(3, 5, 5, 0)),
    )
    result = pr62_m1._analyze_candidates(candidates, selected_fingerprint="A")

    route_6 = pr62_m1._route_interpretation("6", result)

    assert result["first_simpler_comparison"]["same_candidate"] is False
    assert route_6["at_least_one_TE_conclusion_structurally_meaningful"] is True


def test_committed_m_evidence_recomputes_expected_concordance_findings() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    payload = pr62_m1.build_evidence(repo_root)

    assert payload["routes"]["6"]["pairwise_disagreement_count"] == 61
    assert payload["routes"]["10"]["pairwise_disagreement_count"] == 2
    assert payload["routes"]["6"]["TE_path_exactly_reproduces_M"] is True
    assert payload["routes"]["10"]["TE_path_exactly_reproduces_M"] is True
    assert payload["routes"]["6"]["first_simpler_comparison"] == {
        "TE_fingerprint": "ae3c74d827222635551a604db5dfcc138d439813d4fcff2d3a85d4102b2a17fa",
        "SSE_fingerprint": "1efac6b6aaa18c159d794434bdfbce0c2dbe0a9db961442a0987a5a03700c402",
        "same_candidate": False,
    }
    assert payload["routes"]["10"]["first_simpler_comparison"] == {
        "TE_fingerprint": "e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24",
        "SSE_fingerprint": "9ed9d164b35e14bb8a86145fc62823ea334313f15f7c746d43e2756171e0fcd0",
        "same_candidate": False,
    }
    assert (
        payload["routes"]["10"]["interpretation"]["sub_one_trip_simplicity_result_robust"] is True
    )
    assert (
        payload["cross_route_classification"] == "MATERIALITY_PATH_VARIATION_REQUIRES_POLICY_REVIEW"
    )
