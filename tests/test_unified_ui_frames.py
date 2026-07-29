from __future__ import annotations

import json

import pytest
from presentation_support import (
    build_corpus_result_and_report,
    build_result_and_report,
    rejected_result_and_report,
)

from bus_schedule_engine.optimization_service import SolverChoice
from bus_schedule_engine.unified_presentation import build_unified_presentation_v1
from bus_schedule_engine.unified_ui_frames import (
    DISPLAY_DERIVED,
    DISPLAY_DERIVED_FIELDS,
    accepted_c_summary_v1,
    demand_block_rows_v1,
    demand_gap_rows_v1,
    demand_summary_v1,
    expert_review_discrepancy_rows_v1,
    headway_regime_rows_v1,
    outcome_rows_v1,
    technical_dimension_rows_v1,
    technical_summary_v1,
)


@pytest.fixture(scope="module")
def accepted_pair():
    return build_result_and_report()


@pytest.fixture(scope="module")
def accepted_presentation(accepted_pair):
    return build_unified_presentation_v1(*accepted_pair)


@pytest.fixture(scope="module")
def alpha_presentation():
    return build_unified_presentation_v1(*build_corpus_result_and_report("corpus_alpha_80.json"))


@pytest.fixture(scope="module")
def beta_presentation():
    return build_unified_presentation_v1(*build_corpus_result_and_report("corpus_beta_46.json"))


def test_technical_dimensions_preserve_status_confidence_and_order(
    accepted_presentation,
) -> None:
    rows = technical_dimension_rows_v1(accepted_presentation)
    expected_names = (
        "input_validity",
        "parameter_consistency",
        "technical_feasibility",
        "fleet_feasibility",
        "headway_quality",
    )
    expected = {
        dimension.dimension_name: dimension
        for dimension in accepted_presentation.dimensions
        if dimension.dimension_name in expected_names
    }

    assert tuple(dict.fromkeys(row["Nhóm đánh giá"] for row in rows)) == (
        "Tính hợp lệ đầu vào",
        "Tính nhất quán tham số",
        "Khả thi kỹ thuật",
        "Khả thi đội xe",
        "Chất lượng giãn cách",
    )
    for row in rows:
        dimension = next(
            item
            for item in expected.values()
            if item.status == row["Trạng thái"]
            and item.confidence == row["Độ tin cậy"]
            and item.explanation == row["Giải thích"]
        )
        assert json.loads(row["Bằng chứng"]) == list(dimension.evidence)


def test_issue_rows_preserve_code_severity_message_explanation_and_evidence(
    accepted_presentation,
) -> None:
    rows = technical_dimension_rows_v1(accepted_presentation)
    returned_issues = {
        (code, severity, message, dimension.explanation, dimension.evidence)
        for dimension in accepted_presentation.dimensions
        if dimension.dimension_name
        in {
            "input_validity",
            "parameter_consistency",
            "technical_feasibility",
            "fleet_feasibility",
            "headway_quality",
        }
        for code, severity, message in zip(
            dimension.issue_codes,
            dimension.issue_severities,
            dimension.issue_messages,
            strict=True,
        )
    }
    projected_issues = {
        (
            row["Mã"],
            row["Mức độ"],
            row["Nội dung"],
            row["Giải thích"],
            tuple(json.loads(row["Bằng chứng"])),
        )
        for row in rows
        if row["Mã"] is not None
    }

    assert projected_issues == returned_issues


def test_technical_summary_uses_returned_statuses_and_derived_issue_count(
    accepted_presentation,
) -> None:
    summary = technical_summary_v1(accepted_presentation)
    by_name = {
        dimension.dimension_name: dimension for dimension in accepted_presentation.dimensions
    }

    assert summary["technical_feasibility_status"] == by_name["technical_feasibility"].status
    assert summary["fleet_feasibility_status"] == by_name["fleet_feasibility"].status
    assert summary["headway_quality_status"] == by_name["headway_quality"].status
    assert summary["total_issue_count"] == sum(
        len(by_name[name].issue_codes)
        for name in (
            "input_validity",
            "parameter_consistency",
            "technical_feasibility",
            "fleet_feasibility",
            "headway_quality",
        )
    )


def test_block_rows_preserve_exact_contract_keys_and_deterministic_order(
    accepted_presentation,
) -> None:
    rows = demand_block_rows_v1(accepted_presentation)
    blocks = accepted_presentation.blocks

    assert len(rows) == len(blocks)
    assert [row["Mã block"] for row in rows] == [block.block_id for block in blocks]
    assert [row["Nhu cầu hành khách"] for row in rows] == [
        block.passenger_demand for block in blocks
    ]
    assert [row["Chuyến B"] for row in rows] == [block.b_trip_count for block in blocks]
    assert [row["Hệ số tải B"] for row in rows] == [block.b_load_factor for block in blocks]
    assert len({(row["Mã block"], row["Khung thời gian"], row["Chiều"]) for row in rows}) == (
        len(rows)
    )


def test_combined_demand_remains_combined_without_directional_fabrication() -> None:
    presentation = build_unified_presentation_v1(*build_result_and_report(combined_demand=True))
    rows = demand_block_rows_v1(presentation)

    assert {block.direction for block in presentation.blocks} == {"combined"}
    assert {row["Chiều"] for row in rows} == {"Tổng hợp hai chiều"}
    assert all("Terminal One →" not in row["Chiều"] for row in rows)


def test_c_values_appear_only_for_accepted_c(
    accepted_presentation,
    alpha_presentation,
) -> None:
    accepted_rows = demand_block_rows_v1(accepted_presentation)
    alpha_rows = demand_block_rows_v1(alpha_presentation)

    assert accepted_presentation.outcome.accepted_c_exists is True
    assert all(row["Chuyến C được chấp nhận"] is not None for row in accepted_rows)
    assert all(row["Hệ số tải C"] is not None for row in accepted_rows)
    assert alpha_presentation.outcome.accepted_c_exists is False
    assert all(row["Chuyến C được chấp nhận"] is None for row in alpha_rows)
    assert all(row["Hệ số tải C"] is None for row in alpha_rows)
    assert all(row["Trạng thái C"] is None for row in alpha_rows)
    assert any(row["Chuyến B"] is not None for row in alpha_rows)


def test_demand_summary_maxima_and_gap_count_are_returned_only_where_authoritative(
    accepted_presentation,
    beta_presentation,
) -> None:
    accepted = demand_summary_v1(accepted_presentation)
    beta = demand_summary_v1(beta_presentation)

    assert accepted["maximum_b_load_factor"] == max(
        block.b_load_factor
        for block in accepted_presentation.blocks
        if block.b_load_factor is not None
    )
    assert accepted["maximum_c_load_factor"] == max(
        block.c_load_factor
        for block in accepted_presentation.blocks
        if block.c_load_factor is not None
    )
    assert beta["demand_gap_count"] == 1
    assert beta["maximum_c_load_factor"] is None


def test_beta_exact_outbound_1700_1800_gap_is_visible(beta_presentation) -> None:
    rows = demand_gap_rows_v1(beta_presentation)

    assert rows == (
        {
            "Mã khoảng trống": beta_presentation.demand_gaps[0].code,
            "Chiều": (f"{beta_presentation.terminal_1_name} → {beta_presentation.terminal_2_name}"),
            "Khung thời gian": "17:00–18:00",
        },
    )


def test_accepted_c_summary_and_headway_rows_preserve_returned_facts(
    accepted_presentation,
) -> None:
    summary = accepted_c_summary_v1(accepted_presentation)
    rows = headway_regime_rows_v1(accepted_presentation)
    scenario_b = accepted_presentation.scenario("B")
    scenario_c = accepted_presentation.scenario("C")

    assert summary is not None
    assert summary["b_trip_count"] == len(scenario_b.trips)
    assert summary["accepted_c_trip_count"] == len(scenario_c.trips)
    assert summary["accepted_solution_fingerprint"] == (
        accepted_presentation.accepted_solution_fingerprint
    )
    assert summary["headway_regime_count"] == len(accepted_presentation.headway_regimes)
    assert len(rows) == len(accepted_presentation.headway_regimes)
    for row, regime in zip(rows, accepted_presentation.headway_regimes, strict=True):
        assert row["Mã chế độ"] == regime.regime_id
        assert row["Số chuyến"] == regime.trip_count
        assert json.loads(row["Chuỗi giãn cách thực tế"]) == list(regime.actual_headway_sequence)
        assert json.loads(row["Giãn cách ngoại lệ"]) == list(regime.exceptional_headways)


def test_no_accepted_c_never_returns_summary_or_headway_rows(alpha_presentation) -> None:
    assert accepted_c_summary_v1(alpha_presentation) is None
    assert headway_regime_rows_v1(alpha_presentation) == ()
    assert alpha_presentation.scenario("B") is not None
    assert alpha_presentation.scenario("C") is None


def test_rejected_candidate_exposes_only_validator_codes() -> None:
    presentation = build_unified_presentation_v1(*rejected_result_and_report())
    rows = outcome_rows_v1(presentation)
    serialized = json.dumps(rows, ensure_ascii=False, sort_keys=True)

    assert "SYNTHETIC_DOMAIN_REJECTION" in serialized
    assert "rejected-diagnostic-candidate" not in serialized
    assert accepted_c_summary_v1(presentation) is None
    assert headway_regime_rows_v1(presentation) == ()


def test_solver_vectors_are_preserved_without_weighted_total() -> None:
    presentation = build_unified_presentation_v1(
        *build_result_and_report(solver_choice=SolverChoice.BOTH)
    )
    rows = outcome_rows_v1(presentation)
    by_label = {row["Nội dung"]: row["Giá trị"] for row in rows}

    assert json.loads(by_label["Tên mục tiêu so sánh"]) == list(
        presentation.outcome.comparison_objective_names
    )
    assert json.loads(by_label["Vector heuristic"]) == list(
        presentation.outcome.heuristic_objective_vector
    )
    assert json.loads(by_label["Vector OR-Tools"]) == list(
        presentation.outcome.ortools_objective_vector
    )
    assert all("weighted" not in label.lower() for label in by_label)
    assert all("điểm" not in label.lower() for label in by_label)


def test_alpha_legacy_only_c_remains_expert_review_evidence(
    alpha_presentation,
) -> None:
    rows = expert_review_discrepancy_rows_v1(alpha_presentation)

    assert any(row["Mã rà soát"] == "LEGACY_C_WITHOUT_UNIFIED_AUTHORITY" for row in rows)
    assert alpha_presentation.scenario("C") is None


def test_display_derived_fields_are_explicitly_documented() -> None:
    assert DISPLAY_DERIVED == "DISPLAY_DERIVED"
    assert {
        "total_issue_count",
        "demand_gap_count",
        "maximum_b_load_factor",
        "maximum_c_load_factor",
        "shifted_c_trip_count",
        "headway_regime_count",
        "exceptional_headway_count",
    }.issubset(DISPLAY_DERIVED_FIELDS)
