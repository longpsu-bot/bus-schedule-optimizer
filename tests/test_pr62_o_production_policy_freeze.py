from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import scripts.run_pr62_o_production_policy_freeze as pr62_o


def test_v1_selector_blob_and_n_evidence_are_immutable() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    v1_bytes = (
        repo_root / "src/bus_schedule_engine/contracts_v1/operational_selection_policy.py"
    ).read_bytes()
    v1_blob = hashlib.sha1(
        f"blob {len(v1_bytes)}\0".encode() + v1_bytes,
        usedforsecurity=False,
    ).hexdigest()

    assert v1_blob == "1fc1097356a3db732f093ebf25dac0810a1791a7"
    assert pr62_o.verify_n_evidence_lock(repo_root) == {
        "json": {
            "bytes": 20224,
            "sha256": "6e15939240963171e80e20b95a4d728df8ec6ccecb3f0b6b192135fb56ad371b",
        },
        "markdown": {
            "bytes": 5927,
            "sha256": "bf4d4b9a9d92f3b640b2c15b3d42ba42ed47e9ad350bf39aadf10d4203f5ce4b",
        },
    }


def test_cross_route_readiness_comes_from_v2_run_results() -> None:
    routes = {
        "6": {
            "pareto_count": 47,
            "selection_result": {
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
        },
        "10": {
            "pareto_count": 11,
            "selection_result": {
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
        },
    }

    decision = pr62_o.production_freeze_decision(routes)

    assert decision == {
        "cross_route_classification": "ONE_TRIP_PRODUCTION_POLICY_FROZEN",
        "READY_FOR_FINAL_XLSX_RECERTIFICATION": True,
        "blockers": [],
    }
    routes["10"]["selection_result"]["selected_pair_fingerprint"] = "unexpected"
    assert (
        pr62_o.production_freeze_decision(routes)["READY_FOR_FINAL_XLSX_RECERTIFICATION"] is False
    )


def test_blocked_route_evidence_renders_without_selection_fallback() -> None:
    route = {
        "route_id": "6",
        "pareto_count": 2,
        "SSE_BEST_SET": ["A"],
        "TE_BEST_SET": ["B"],
        "common_anchor": None,
        "selected": None,
        "selection_result": {
            "hard_feasible_count": 2,
            "passenger_access_safe_count": 2,
            "common_anchor_fingerprint": None,
            "materiality_set_count": 0,
            "selected_pair_fingerprint": None,
            "classification": "DEMAND_FIT_ANCHOR_CONFLICT",
            "stage_trace": [
                {"stage": "HARD_OPERATIONAL_FEASIBILITY"},
                {"stage": "SCENARIO_B_MAX_ACCESS_NON_REGRESSION"},
                {"stage": "COMMON_SSE_TE_DEMAND_FIT_ANCHOR"},
            ],
        },
    }

    rendered = "\n".join(pr62_o._route_markdown(route))

    assert "DEMAND_FIT_ANCHOR_CONFLICT" in rendered
    assert "Selected: `None`" in rendered


def test_committed_o_evidence_locks_production_results_and_tradeoff() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    json_path = repo_root / pr62_o.OUTPUT_JSON
    markdown_path = repo_root / pr62_o.OUTPUT_MARKDOWN
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert json_path.stat().st_size < 500_000
    assert payload["cross_route_classification"] == "ONE_TRIP_PRODUCTION_POLICY_FROZEN"
    assert payload["READY_FOR_FINAL_XLSX_RECERTIFICATION"] is True
    route6 = payload["routes"]["6"]
    route10 = payload["routes"]["10"]
    assert route6["pareto_count"] == 47
    assert route6["selection_result"]["hard_feasible_count"] == 47
    assert route6["selection_result"]["passenger_access_safe_count"] == 41
    assert route6["selection_result"]["materiality_set_count"] == 5
    assert route6["selection_result"]["selected_pair_fingerprint"] == (
        "ad0ebdf717ff9c9e5aa79bbfe2ae36082875b5bb57620d917f9dec695374174b"
    )
    assert route10["pareto_count"] == 11
    assert route10["selection_result"]["hard_feasible_count"] == 11
    assert route10["selection_result"]["passenger_access_safe_count"] == 7
    assert route10["selection_result"]["materiality_set_count"] == 2
    assert route10["selection_result"]["common_anchor_fingerprint"] == (
        "bb35aa0cc7221a887be8328d18de289447ef4070fa147820546efad691fb719c"
    )
    assert route10["selection_result"]["selected_pair_fingerprint"] == (
        "e76426dc2e4420d7f826c939f40d5fb1ea3414744bba3a1a379eb19bc9d4cb24"
    )
    tradeoff = route10["selected_vs_anchor_tradeoff"]
    assert tradeoff["delta_TE"] == pytest.approx(0.7122514457735889)
    assert tradeoff["delta_SSE"] == pytest.approx(0.001359144, abs=1e-9)
    assert tradeoff["average_wait_delta_seconds_per_passenger"] == pytest.approx(2.658655, abs=1e-6)
    assert tradeoff["fleet_required_delta"] == -1
    assert tradeoff["total_excess_terminal_wait_delta"] == -749
    tails = {
        item["tail_headways"]["inbound"] for item in route10["access_exclusions"]["candidates"]
    }
    assert {30, 45, 48, 54}.issubset(tails)
    assert payload["production_guards"]["final_XLSX_regenerated"] is False
    assert payload["production_guards"]["private_workbook_opened"] is False
    assert json_path.read_bytes() == pr62_o._canonical_json_bytes(payload)
    assert markdown_path.read_bytes() == pr62_o._markdown(payload).encode("utf-8")
