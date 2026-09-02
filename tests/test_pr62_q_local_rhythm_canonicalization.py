from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import scripts.run_pr62_q_local_rhythm_canonicalization as q


def _regime(
    headway: int,
    *,
    trip_count: int = 4,
    regime_id: str | None = None,
    start: int = 0,
) -> dict[str, int | str]:
    return {
        "service_regime_id": regime_id or f"R-{start}-{headway}",
        "first_departure": start,
        "last_departure": start + (trip_count - 1) * headway * 60,
        "trip_count": trip_count,
        "uniform_headway_minutes": headway,
    }


def test_local_family_detector_canonicalizes_contiguous_19_21_20_19() -> None:
    regimes = [
        _regime(19, start=0),
        _regime(21, start=3600),
        _regime(20, start=7200),
        _regime(19, start=10800),
    ]

    families = q.detect_local_rhythm_families(regimes)

    assert len(families) == 1
    assert families[0]["exact_headways"] == [19, 21, 20, 19]
    assert families[0]["canonical_representative"] == 20
    assert families[0]["micro_rhythm_boundary_count"] == 3


def test_weighted_representative_uses_internal_gap_counts() -> None:
    regimes = [
        _regime(19, trip_count=31, start=0),
        _regime(20, trip_count=6, start=36000),
        _regime(19, trip_count=8, start=43200),
    ]

    family = q.detect_local_rhythm_families(regimes)[0]

    assert family["internal_gap_counts"] == [30, 5, 7]
    assert family["canonical_representative"] == 19
    assert family["gap_weighted_absolute_deviation"] == 5


def test_family_detection_is_contiguous_and_excludes_single_gap_regimes() -> None:
    assert q.detect_local_rhythm_families([_regime(19), _regime(14), _regime(20)]) == []
    assert (
        q.detect_local_rhythm_families([_regime(19), _regime(20, trip_count=2), _regime(19)]) == []
    )


def test_range_above_two_is_not_one_family_and_partition_is_deterministic() -> None:
    families = q.detect_local_rhythm_families([_regime(18), _regime(20), _regime(21)])

    assert len(families) == 1
    assert families[0]["exact_headways"] == [18, 20]
    assert families[0]["canonical_representative"] == 19


def test_committed_p_baseline_detects_route10_targets_and_route6_control() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    product = json.loads((repo_root / q.P_PRODUCT_DATA).read_text(encoding="utf-8"))

    route10 = q.detect_product_families(product["routes"]["10"])
    route6 = q.detect_product_families(product["routes"]["6"])

    assert route10["outbound"][0]["exact_headways"] == [19, 21, 20, 19]
    assert route10["outbound"][0]["canonical_representative"] == 20
    assert route10["inbound"][0]["exact_headways"] == [19, 20, 19]
    assert route10["inbound"][0]["canonical_representative"] == 19
    assert route6 == {"outbound": [], "inbound": []}


def test_exact_arithmetic_census_uses_integer_gaps_only() -> None:
    result = q.strict_arithmetic_census(
        service_span_minutes=100,
        gap_count=5,
        ordered_headways=(20,),
    )

    assert result["feasible"] is True
    assert result["compositions"] == [{"gap_counts": [5], "weighted_minutes": 100}]
    assert result["gap_count"] == 5


def test_tail_relief_is_separate_from_strict_canonicalization() -> None:
    result = q.arithmetic_tier_census(
        service_span_minutes=105,
        gap_count=5,
        canonical_headway=20,
        frozen_non_family_headways=(),
        frozen_tail_headway=24,
        permitted_tail_headways=range(20, 31),
    )

    assert result["Q_A"]["feasible"] is False
    assert result["Q_B"]["feasible"] is True
    assert result["Q_B"]["witness"]["tail_headway"] == 25
    assert result["Q_B"]["witness"]["gap_counts"] == [4, 1]


def test_residual_census_reports_evidence_without_semantic_changes() -> None:
    result = q.arithmetic_tier_census(
        service_span_minutes=101,
        gap_count=5,
        canonical_headway=20,
        frozen_non_family_headways=(),
        frozen_tail_headway=None,
        permitted_tail_headways=(),
    )

    assert result["Q_A"]["feasible"] is False
    assert result["Q_B"]["feasible"] is False
    assert result["Q_C"]["residual_required"] is True
    assert result["Q_C"]["residual_gap_minutes"] == 21
    assert result["Q_C"]["production_compiler_changed"] is False
    assert result["Q_C"]["settlement_added"] is False
    assert result["Q_C"]["residual_service_regime_created"] is False


def test_access_and_te_gates_are_non_compensable() -> None:
    assert q.access_gate(14.0, 14.0) is True
    assert q.access_gate(14.0001, 14.0, epsilon=1e-12) is False
    assert q.te_materiality_gate(17.0, 16.0) is True
    assert q.te_materiality_gate(17.0001, 16.0, epsilon=1e-12) is False


def test_production_pareto_relevance_reports_dominance_witnesses() -> None:
    frontier = {"A": (1.0, 2.0), "B": (2.0, 1.0)}

    relevant = q.production_pareto_audit((1.5, 1.5), frontier)
    dominated = q.production_pareto_audit((2.0, 2.0), frontier)

    assert relevant["pareto_relevant"] is True
    assert relevant["dominated_by_current_frontier"] is False
    assert dominated["pareto_relevant"] is False
    assert dominated["dominated_by"] == ["A", "B"]


def test_demand_audit_flags_opposed_exact_frequency_change() -> None:
    family = q.detect_local_rhythm_families(
        [_regime(19, regime_id="A"), _regime(21, regime_id="B", start=3600)]
    )[0]
    evidence = {
        "A": {"integrated_demand_mass": 100.0, "demand_rate_per_hour": 50.0},
        "B": {"integrated_demand_mass": 120.0, "demand_rate_per_hour": 60.0},
    }

    audit = q.demand_justification_audit(family, evidence)

    assert audit[0]["service_frequency_direction"] == "DOWN"
    assert audit[0]["demand_direction"] == "UP"
    assert audit[0]["classification"] == "NOT_DEMAND_RESPONSE_EXPLANATORY"


def test_production_files_and_canonical_workbooks_are_hash_locked() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    expected = {
        "src/bus_schedule_engine/service_plan_coordinator.py": (
            "99da83840f30d5ff7781b1525ec5202074641f1c01203ad46ddc42200a24bfc0"
        ),
        "src/bus_schedule_engine/contracts_v1/clean_boundary_compiler.py": (
            "e36950284e7d2bea1f7ff15dc1bb016d360b8b3dd6ff3ce0299cfcbdb3952490"
        ),
        "src/bus_schedule_engine/contracts_v1/operational_selection_policy.py": (
            "5f10bf7130c20898a3e537fc8f7b73e990335f92ccb7913c41e50a308809e415"
        ),
        "src/bus_schedule_engine/contracts_v1/operational_selection_policy_v2.py": (
            "79a63d38dfde00f42af1f5a56cb67adb3280c3941b45cdb1f67fb65c67ea3181"
        ),
        "src/bus_schedule_engine/clean_boundary_pilot.py": (
            "1b17298d31ed308da058ba213748c23b7a76f8902c3abcef20715d5ca1a99fd9"
        ),
        "outputs/final_pilot/Route_6_Final_Pilot_Timetable.xlsx": (
            "13454026722f996d8b06e5305b3b6ab2d57ea6126734f4deeb23c3e7dbafd02c"
        ),
        "outputs/final_pilot/Route_10_Final_Pilot_Timetable.xlsx": (
            "d84dd2e873d3ba30275463a5eff67277a22467839af0f0125e69160a891fc3db"
        ),
    }

    actual = {
        relative: hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
        for relative in expected
    }

    assert actual == expected


def test_committed_q_evidence_is_deterministic_and_keeps_completion_blocked() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / q.OUTPUT_JSON).read_text(encoding="utf-8"))

    assert payload["milestone"] == "PR62-Q"
    assert payload["READY_FOR_PR62_COMPLETION_REVIEW"] is False
    assert payload["routes"]["10"]["baseline_pair_fingerprint"] == q.ROUTE10_P_PAIR
    assert payload["routes"]["6"]["classification"] == "NO_LOCAL_MICRO_RHYTHM_TARGET"
    assert payload["root_cause_classification"] == "Q_EVIDENCE_INCONCLUSIVE"
    assert payload["blocking_stage"] == "V2_TE_MATERIALITY_BLOCKER"
    assert payload["compiler_backed_census"]["hard_valid_pairs"] == 1
    assert payload["compiler_backed_census"]["access_safe_pairs"] == 1
    assert payload["compiler_backed_census"]["within_one_TE_pairs"] == 0
    assert payload["compiler_backed_census"]["production_pareto_relevant_pairs"] == 1
    assert len(payload["Q_LOCAL_CANONICALIZATION_REVIEW_FRONTIER"]) == 1
    assert payload["production_guards"] == q.EXPECTED_PRODUCTION_GUARDS
    assert (repo_root / q.OUTPUT_JSON).read_bytes() == q.canonical_json_bytes(payload)
    assert (repo_root / q.OUTPUT_MARKDOWN).read_bytes() == q.render_markdown(payload).encode(
        "utf-8"
    )
    assert (repo_root / q.OUTPUT_JSON).stat().st_size < 1_000_000


@pytest.mark.parametrize("direction", ["outbound", "inbound"])
def test_route10_arithmetic_census_reconciles_exact_span_and_gap_count(direction: str) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    payload = q.build_evidence(repo_root, run_compiler_census=False)
    census = payload["routes"]["10"]["directions"][direction]["arithmetic_census"]

    assert census["gap_count"] == 50
    assert census["exact_gap_sum_minutes"] == census["service_span_minutes"]
