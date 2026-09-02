from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.run_pr62_m_discrete_demand_fit_materiality as pr62_m
from scripts.run_pr62_m_discrete_demand_fit_materiality import (
    _allocation_move_distance_trips,
    _breakpoint_frontier,
    _directional_allocation_diagnostic,
    _metric_ordering_audit,
    _one_trip_quantum_diagnostic,
    _pair_trip_equivalent_error,
    _route_classification,
)


def _candidate(
    fingerprint: str,
    *,
    mismatch: float,
    trip_equivalent: float,
    rhythm: tuple[int, int, int, int],
    fleet: tuple[int, int, int] = (10, 20, 5),
) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "observed_demand_mismatch": mismatch,
        "pair_trip_equivalent_error": trip_equivalent,
        "rhythm_simplicity_tuple": rhythm,
        "fleet_efficiency_tuple": fleet,
    }


def test_exact_total_variation_is_half_l1_share_distance() -> None:
    diagnostic = _directional_allocation_diagnostic(
        service_counts=(4, 6),
        demand_shares=(0.5, 0.5),
        service_shares=(0.4, 0.6),
    )

    assert diagnostic["directional_allocation_tv"] == pytest.approx(0.1)


def test_one_trip_displacement_has_one_trip_equivalent_error() -> None:
    diagnostic = _directional_allocation_diagnostic(
        service_counts=(4, 6),
        demand_shares=(0.5, 0.5),
        service_shares=(0.4, 0.6),
    )

    assert diagnostic["directional_total_trips"] == 10
    assert diagnostic["directional_trip_equivalent_error"] == pytest.approx(1.0)


def test_multi_bucket_trip_equivalent_error_uses_exact_trip_total() -> None:
    diagnostic = _directional_allocation_diagnostic(
        service_counts=(4, 12, 4),
        demand_shares=(0.25, 0.50, 0.25),
        service_shares=(0.20, 0.60, 0.20),
    )

    assert diagnostic["directional_allocation_tv"] == pytest.approx(0.10)
    assert diagnostic["directional_trip_equivalent_error"] == pytest.approx(2.0)


def test_directional_diagnostic_fails_closed_on_inconsistent_authoritative_metrics() -> None:
    with pytest.raises(ValueError, match="service shares do not match service counts"):
        _directional_allocation_diagnostic(
            service_counts=(4, 6),
            demand_shares=(0.5, 0.5),
            service_shares=(0.5, 0.5),
        )


def test_pair_trip_equivalent_error_sums_directions_without_averaging() -> None:
    assert _pair_trip_equivalent_error(1.25, 0.75) == pytest.approx(2.0)


def test_candidate_allocation_move_distance_is_minimum_bucket_moves() -> None:
    assert _allocation_move_distance_trips((5, 3, 2), (4, 4, 2)) == 1


def test_candidate_allocation_move_distance_requires_equal_directional_totals() -> None:
    with pytest.raises(ValueError, match="equal directional trip totals"):
        _allocation_move_distance_trips((5, 3, 2), (4, 4, 3))


def test_sse_and_tv_ordering_conflict_is_reported_without_substitution() -> None:
    demand = (0.3, 0.3, 0.2, 0.2)
    a = _directional_allocation_diagnostic(
        service_counts=(6, 0, 2, 2),
        demand_shares=demand,
        service_shares=(0.6, 0.0, 0.2, 0.2),
    )
    b = _directional_allocation_diagnostic(
        service_counts=(5, 5, 0, 0),
        demand_shares=demand,
        service_shares=(0.5, 0.5, 0.0, 0.0),
    )
    candidates = (
        _candidate(
            "A",
            mismatch=sum(
                (service - observed) ** 2
                for service, observed in zip((0.6, 0.0, 0.2, 0.2), demand, strict=True)
            ),
            trip_equivalent=float(a["directional_trip_equivalent_error"]),
            rhythm=(8, 12, 6, 0),
        ),
        _candidate(
            "B",
            mismatch=sum(
                (service - observed) ** 2
                for service, observed in zip((0.5, 0.5, 0.0, 0.0), demand, strict=True)
            ),
            trip_equivalent=float(b["directional_trip_equivalent_error"]),
            rhythm=(6, 10, 5, 0),
        ),
    )

    audit = _metric_ordering_audit(candidates)

    assert audit["SSE_BEST"]["fingerprint"] == "B"
    assert audit["TV_BEST"]["fingerprint"] == "A"
    assert audit["same_best_candidate"] is False
    assert audit["pairwise_ranking_disagreement_count"] == 1
    assert audit["production_metric"] == "observed_demand_mismatch"
    assert audit["review_metric_only"] == "pair_trip_equivalent_error"


def test_breakpoint_frontier_uses_exact_observed_deltas_and_review_order() -> None:
    candidates = (
        _candidate("A", mismatch=0.01, trip_equivalent=2.0, rhythm=(8, 12, 6, 0)),
        _candidate("B", mismatch=0.02, trip_equivalent=2.3, rhythm=(6, 10, 5, 0)),
        _candidate("C", mismatch=0.03, trip_equivalent=3.0, rhythm=(4, 8, 4, 0)),
    )

    path = _breakpoint_frontier(candidates)

    assert [row["delta_trip_equivalent"] for row in path] == pytest.approx([0.0, 0.3, 1.0])
    assert [row["preferred_fingerprint"] for row in path] == ["A", "B", "C"]


def test_sub_one_trip_witness_is_diagnostic_only() -> None:
    selected = _candidate("A", mismatch=0.01, trip_equivalent=2.0, rhythm=(8, 12, 6, 0))
    simpler = _candidate("B", mismatch=0.02, trip_equivalent=2.4, rhythm=(6, 10, 5, 0))

    diagnostic = _one_trip_quantum_diagnostic((selected, simpler), selected_fingerprint="A")

    assert diagnostic["sub_one_trip_simpler_exists"] is True
    assert diagnostic["at_or_below_one_trip_simpler_exists"] is True
    assert diagnostic["minimum_delta_to_simpler_candidate"] == pytest.approx(0.4)
    assert diagnostic["production_policy_changed"] is False


def test_metric_conflict_takes_route_classification_precedence() -> None:
    assert (
        _route_classification(metric_ordering_conflict=True, minimum_simpler_delta=0.4)
        == "DEMAND_FIT_METRIC_ORDERING_CONFLICT"
    )


def test_human_final_benchmark_cannot_enter_metric_ranking() -> None:
    candidates = (
        _candidate("A", mismatch=0.01, trip_equivalent=2.0, rhythm=(8, 12, 6, 0)),
        _candidate("B", mismatch=0.02, trip_equivalent=2.4, rhythm=(6, 10, 5, 0)),
    )
    human_final = _candidate(
        "HUMAN_FINAL", mismatch=0.001, trip_equivalent=0.5, rhythm=(3, 5, 3, 0)
    )

    audit = _metric_ordering_audit(candidates, benchmark=human_final)

    assert audit["TV_BEST"]["fingerprint"] == "A"
    assert audit["benchmark"]["fingerprint"] == "HUMAN_FINAL"
    assert audit["benchmark"]["selection_eligible"] is False


def test_m_canonical_json_is_byte_identical() -> None:
    payload = {"b": [2, 1], "a": {"value": 1}}

    assert pr62_m._canonical_json_bytes(payload) == pr62_m._canonical_json_bytes(payload)


def test_m_markdown_renderer_has_clean_line_endings() -> None:
    payload = {
        "profile": "discrete_demand_fit_materiality_v1",
        "routes": {},
        "cross_route_classification": "TRIP_EQUIVALENT_EVIDENCE_INCONCLUSIVE",
        "production_guards": {},
    }

    rendered = pr62_m._markdown(payload)

    assert rendered.startswith("# PR62-M")
    assert "\r" not in rendered
    assert rendered.endswith("\n")


def test_committed_m_evidence_locks_access_safe_counts_and_production_guards() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "docs/engine/evidence/PR62_M_DISCRETE_DEMAND_FIT_MATERIALITY.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.stat().st_size < 1_000_000
    assert payload["routes"]["6"]["stage_counts"]["access_safe"] == 41
    assert payload["routes"]["10"]["stage_counts"]["access_safe"] == 7
    assert payload["human_final_route_6"]["selection_eligible"] is False
    assert payload["human_final_route_6"]["classification"] == "POST_SEARCH_EXPERT_BENCHMARK"
    assert all(
        "allocation_move_distance_vs_HUMAN_FINAL" in candidate
        for candidate in payload["routes"]["6"]["access_safe_candidates"]
    )
    for route_id in ("6", "10"):
        path_above_one = next(
            (
                row["delta_trip_equivalent"]
                for row in payload["routes"][route_id]["trip_equivalent_breakpoint_path"]
                if row["delta_trip_equivalent"] > 1.0 + 1e-12
            ),
            None,
        )
        assert (
            payload["routes"][route_id]["one_trip_quantum_diagnostic"][
                "first_breakpoint_above_one_trip"
            ]
            == path_above_one
        )
    human = payload["human_final_route_6"]
    assert set(human["tail_headways"]) == {"outbound", "inbound"}
    assert set(human["directional_maximum_bucket_wait_minutes"]) == {"outbound", "inbound"}
    assert set(payload["production_guards"].values()) == {"NO"}
