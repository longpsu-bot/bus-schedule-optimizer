from __future__ import annotations

import json
from pathlib import Path

from scripts.run_pr62_l_domain_priority_selector import (
    _candidate_audit_record,
    _canonical_json_bytes,
    _extreme_tail_audit,
    _human_final_complexity_concern,
    _markdown,
    _nearby_alternatives,
    _policy_health_classification,
)


def _record(
    fingerprint: str,
    *,
    mismatch: float,
    sustained: int,
    fleet: int,
    average_wait: float,
    inbound_tail: int = 20,
    inbound_max_wait: float = 14.0,
) -> dict[str, object]:
    return {
        "fingerprint": fingerprint,
        "mismatch": mismatch,
        "average_wait_minutes": average_wait,
        "directional_maximum_bucket_wait_minutes": {
            "outbound": 12.0,
            "inbound": inbound_max_wait,
        },
        "fleet_required": fleet,
        "actual_service_regime_count": 10,
        "sustained_headway_level_count": sustained,
        "effective_palette_count": 4,
        "single_gap_regime_count": 0,
        "total_excess_terminal_wait": 100,
        "max_excess_terminal_wait": 20,
        "tail_headways": {"outbound": 20, "inbound": inbound_tail},
        "access_safe": inbound_max_wait <= 15.0,
    }


def test_policy_health_flags_authoritative_rhythm_difference_without_scalar_weight() -> None:
    selected = _record("A", mismatch=0.010, sustained=8, fleet=18, average_wait=6.0)
    simpler = _record("B", mismatch=0.011, sustained=5, fleet=17, average_wait=5.9)

    classification = _policy_health_classification(
        selection_classification="UNIQUE_DOMAIN_PRIORITY_SELECTION",
        selected=selected,
        access_safe=(selected, simpler),
    )

    assert classification == "DOMAIN_HIERARCHY_DEMAND_FIRST_COMPLEXITY_CONCERN"


def test_policy_health_reports_access_guardrail_empty_without_relaxation() -> None:
    classification = _policy_health_classification(
        selection_classification="ACCESS_GUARDRAIL_TOO_RESTRICTIVE",
        selected=None,
        access_safe=(),
    )

    assert classification == "DOMAIN_HIERARCHY_ACCESS_GUARDRAIL_TOO_RESTRICTIVE"


def test_nearby_alternatives_cover_named_review_roles_without_duplicate_rows() -> None:
    selected = _record("A", mismatch=0.010, sustained=8, fleet=18, average_wait=6.0)
    simple = _record("B", mismatch=0.012, sustained=4, fleet=17, average_wait=5.9)
    next_best = _record("C", mismatch=0.011, sustained=6, fleet=16, average_wait=6.1)

    rows = _nearby_alternatives((selected, simple, next_best), selected_fingerprint="A")

    assert len(rows) == 3
    assert rows[0]["fingerprint"] == "A"
    assert set(rows[0]["roles"]) == {"SELECTED"}
    assert "NEXT_BEST_MISMATCH" in rows[2]["roles"]
    assert not any("score" in key.lower() for row in rows for key in row)


def test_extreme_tail_audit_uses_directional_access_reason_not_headway_policy() -> None:
    tail_30 = _record(
        "T30",
        mismatch=0.01,
        sustained=5,
        fleet=12,
        average_wait=9.5,
        inbound_tail=30,
        inbound_max_wait=16.0,
    )

    audit = _extreme_tail_audit(
        (tail_30,),
        scenario_b_inbound_maximum_wait_minutes=15.0,
    )

    assert audit["30"][0]["excluded_by_access_guardrail"] is True
    assert audit["30"][0]["reason"] == "INBOUND_MAX_ACCESS_REGRESSION"
    assert audit["45"] == []
    assert audit["policy_is_headway_threshold"] is False


def test_l_canonical_json_is_byte_identical() -> None:
    payload = {"b": [2, 1], "a": {"value": 1}}

    assert _canonical_json_bytes(payload) == _canonical_json_bytes(payload)


def test_l_markdown_renderer_has_clean_line_endings() -> None:
    payload = {
        "profile": "domain_priority_operational_selector_v1",
        "routes": {},
        "READY_FOR_POST_HIJKL_RECERTIFICATION": False,
        "production_guards": {},
    }

    rendered = _markdown(payload)

    assert rendered.startswith("# PR62-L")
    assert "\r" not in rendered
    assert rendered.endswith("\n")


def test_candidate_audit_does_not_duplicate_full_directional_diagnostics() -> None:
    record = _record("A", mismatch=0.01, sustained=5, fleet=15, average_wait=6.0)
    record["directions"] = {"outbound": {"bucket_service_shares": [0.1] * 68}}
    record["hard_feasible"] = True
    record["hard_feasibility_reasons"] = []
    record["delta_mismatch_vs_best_access_safe"] = 0.0
    record["maximum_directional_p90_bucket_wait_minutes"] = 10.0
    record["single_gap_regime_count"] = 0
    record["total_excess_terminal_wait"] = 100
    record["max_excess_terminal_wait"] = 20

    compact = _candidate_audit_record(record)

    assert "directions" not in compact
    assert compact["directional_maximum_bucket_wait_minutes"] == {
        "outbound": 12.0,
        "inbound": 14.0,
    }


def test_human_final_complexity_uses_primary_sustained_vocabulary_first() -> None:
    assert _human_final_complexity_concern(
        selected_sustained=8,
        selected_regimes=14,
        selected_effective=6,
        human_sustained=5,
        human_regimes=17,
        human_effective=5,
    )


def test_committed_l_evidence_locks_stage_counts_tails_and_guards() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "docs/engine/evidence/PR62_L_DOMAIN_PRIORITY_SELECTOR.json"
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path.stat().st_size < 1_000_000
    assert payload["routes"]["6"]["stage_counts"] == {
        "I_Pareto": 47,
        "hard_feasible": 47,
        "access_safe": 41,
        "best_demand_fit": 1,
        "best_rhythm": 1,
        "best_fleet_efficiency": 1,
        "selected": 1,
    }
    assert payload["routes"]["10"]["stage_counts"] == {
        "I_Pareto": 11,
        "hard_feasible": 11,
        "access_safe": 7,
        "best_demand_fit": 1,
        "best_rhythm": 1,
        "best_fleet_efficiency": 1,
        "selected": 1,
    }
    audit = payload["routes"]["10"]["inbound_extreme_tail_audit"]
    assert all(audit[str(tail)] for tail in (30, 45, 48, 54))
    assert all(
        item["reason"] == "INBOUND_MAX_ACCESS_REGRESSION"
        for tail in (30, 45, 48, 54)
        for item in audit[str(tail)]
    )
    assert payload["READY_FOR_POST_HIJKL_RECERTIFICATION"] is False
    assert set(payload["production_guards"].values()) == {"NO"}
