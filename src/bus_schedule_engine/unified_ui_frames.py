"""Pure Streamlit-ready projections from one unified presentation bundle.

``DISPLAY_DERIVED`` fields are limited to deterministic sorting, counts, maxima,
and formatting over facts already returned in ``UnifiedPresentationBundleV1``.
No validation, demand allocation, load-factor calculation, fleet assignment,
solver comparison, headway analysis, or Scenario C generation occurs here.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from .unified_presentation import (
    DISPLAY_DERIVED,
    UnifiedPresentationBundleV1,
)

DISPLAY_DERIVED_FIELDS = frozenset(
    {
        "total_issue_count",
        "demand_gap_count",
        "maximum_b_load_factor",
        "maximum_c_load_factor",
        "b_trip_count",
        "accepted_c_trip_count",
        "shifted_c_trip_count",
        "b_warning_block_count",
        "b_critical_block_count",
        "c_warning_block_count",
        "c_critical_block_count",
        "headway_regime_count",
        "exceptional_headway_count",
    }
)

_TECHNICAL_DIMENSION_ORDER = (
    "input_validity",
    "parameter_consistency",
    "technical_feasibility",
    "fleet_feasibility",
    "headway_quality",
)
_DIMENSION_LABELS = {
    "input_validity": "Tính hợp lệ đầu vào",
    "parameter_consistency": "Tính nhất quán tham số",
    "technical_feasibility": "Khả thi kỹ thuật",
    "demand_suitability": "Mức phù hợp nhu cầu",
    "fleet_feasibility": "Khả thi đội xe",
    "headway_quality": "Chất lượng giãn cách",
}
_DIRECTION_ORDER = {"outbound": 0, "inbound": 1, "combined": 2}


def _require_presentation(
    presentation: UnifiedPresentationBundleV1,
) -> UnifiedPresentationBundleV1:
    if not isinstance(presentation, UnifiedPresentationBundleV1):
        raise TypeError("presentation must be a UnifiedPresentationBundleV1")
    return presentation


def _json_text(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _service_time(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours:02d}:{minutes:02d}"


def direction_label_v1(
    presentation: UnifiedPresentationBundleV1,
    direction: str,
) -> str:
    """Format a returned raw direction without changing its underlying grain."""
    _require_presentation(presentation)
    if direction == "outbound":
        return f"{presentation.terminal_1_name} → {presentation.terminal_2_name}"
    if direction == "inbound":
        return f"{presentation.terminal_2_name} → {presentation.terminal_1_name}"
    if direction == "combined":
        return "Tổng hợp hai chiều"
    return direction


def _dimension_by_name(
    presentation: UnifiedPresentationBundleV1,
    name: str,
):
    return next(
        (dimension for dimension in presentation.dimensions if dimension.dimension_name == name),
        None,
    )


def technical_summary_v1(
    presentation: UnifiedPresentationBundleV1,
) -> dict[str, object]:
    """Return statuses plus the ``DISPLAY_DERIVED`` total issue count."""
    _require_presentation(presentation)
    technical = _dimension_by_name(presentation, "technical_feasibility")
    fleet = _dimension_by_name(presentation, "fleet_feasibility")
    headway = _dimension_by_name(presentation, "headway_quality")
    selected = tuple(
        dimension
        for name in _TECHNICAL_DIMENSION_ORDER
        if (dimension := _dimension_by_name(presentation, name)) is not None
    )
    return {
        "technical_feasibility_status": technical.status if technical is not None else None,
        "technical_confidence": technical.confidence if technical is not None else None,
        "fleet_feasibility_status": fleet.status if fleet is not None else None,
        "headway_quality_status": headway.status if headway is not None else None,
        "total_issue_count": sum(len(dimension.issue_codes) for dimension in selected),
    }


def technical_dimension_rows_v1(
    presentation: UnifiedPresentationBundleV1,
) -> tuple[dict[str, object], ...]:
    """Preserve returned statuses and issue order for the five technical dimensions."""
    _require_presentation(presentation)
    rows: list[dict[str, object]] = []
    for name in _TECHNICAL_DIMENSION_ORDER:
        dimension = _dimension_by_name(presentation, name)
        if dimension is None:
            continue
        evidence = _json_text(dimension.evidence)
        issues = tuple(
            zip(
                dimension.issue_codes,
                dimension.issue_severities,
                dimension.issue_messages,
                strict=True,
            )
        )
        if not issues:
            rows.append(
                {
                    "Nhóm đánh giá": _DIMENSION_LABELS[name],
                    "Trạng thái": dimension.status,
                    "Độ tin cậy": dimension.confidence,
                    "Mức độ": None,
                    "Mã": None,
                    "Nội dung": None,
                    "Giải thích": dimension.explanation,
                    "Bằng chứng": evidence,
                }
            )
            continue
        rows.extend(
            {
                "Nhóm đánh giá": _DIMENSION_LABELS[name],
                "Trạng thái": dimension.status,
                "Độ tin cậy": dimension.confidence,
                "Mức độ": severity,
                "Mã": code,
                "Nội dung": message,
                "Giải thích": dimension.explanation,
                "Bằng chứng": evidence,
            }
            for code, severity, message in issues
        )
    return tuple(rows)


def _maximum(values: Iterable[float | None]) -> float | None:
    present = tuple(value for value in values if value is not None)
    return max(present) if present else None


def demand_summary_v1(
    presentation: UnifiedPresentationBundleV1,
) -> dict[str, object]:
    """Return demand authority plus allowed ``DISPLAY_DERIVED`` counts and maxima."""
    _require_presentation(presentation)
    dimension = _dimension_by_name(presentation, "demand_suitability")
    accepted_c = presentation.outcome.accepted_c_exists
    return {
        "demand_suitability_status": dimension.status if dimension is not None else None,
        "demand_confidence": dimension.confidence if dimension is not None else None,
        "demand_gap_count": len(presentation.demand_gaps),
        "maximum_b_load_factor": _maximum(block.b_load_factor for block in presentation.blocks),
        "maximum_c_load_factor": (
            _maximum(block.c_load_factor for block in presentation.blocks) if accepted_c else None
        ),
    }


def demand_block_rows_v1(
    presentation: UnifiedPresentationBundleV1,
) -> tuple[dict[str, object], ...]:
    """Project exact Contract block rows without aggregation or directional inference."""
    _require_presentation(presentation)
    blocks = tuple(
        sorted(
            presentation.blocks,
            key=lambda block: (
                _DIRECTION_ORDER.get(block.direction, 99),
                block.block_start_seconds,
                block.block_end_seconds,
                block.block_id,
            ),
        )
    )
    include_a = any(block.a_trip_count is not None for block in blocks)
    accepted_c = presentation.outcome.accepted_c_exists
    rows: list[dict[str, object]] = []
    for block in blocks:
        row: dict[str, object] = {
            "Mã block": block.block_id,
            "Khung thời gian": (
                f"{_service_time(block.block_start_seconds)}–"
                f"{_service_time(block.block_end_seconds)}"
            ),
            "Chiều": direction_label_v1(presentation, block.direction),
            "Nhu cầu hành khách": block.passenger_demand,
            "Độ tin cậy": block.confidence,
            "Sức chứa xe": block.vehicle_capacity,
        }
        if include_a:
            row["Chuyến A (thông tin)"] = block.a_trip_count
        row.update(
            {
                "Chuyến B": block.b_trip_count,
                "Chuyến C được chấp nhận": (block.c_actual_trip_count if accepted_c else None),
                "Chuyến cần ở 85%": block.required_trips_85,
                "Chuyến cần ở 90%": block.required_trips_90,
                "Hệ số tải B": block.b_load_factor,
                "Hệ số tải C": block.c_load_factor if accepted_c else None,
                "Thiếu chuyến B": block.b_shortage,
                "Thiếu chuyến C": block.c_shortage if accepted_c else None,
                "Trạng thái B": block.b_status,
                "Trạng thái C": block.c_status if accepted_c else None,
                "Căn cứ phân bổ": block.allocation_reason,
            }
        )
        rows.append(row)
    return tuple(rows)


def demand_gap_rows_v1(
    presentation: UnifiedPresentationBundleV1,
) -> tuple[dict[str, object], ...]:
    """Format exact returned demand gaps without filling or reallocating them."""
    _require_presentation(presentation)
    gaps = sorted(
        presentation.demand_gaps,
        key=lambda gap: (
            _DIRECTION_ORDER.get(gap.direction, 99),
            gap.start_time_seconds,
            gap.end_time_seconds,
            gap.code,
        ),
    )
    return tuple(
        {
            "Mã khoảng trống": gap.code,
            "Chiều": direction_label_v1(presentation, gap.direction),
            "Khung thời gian": (
                f"{_service_time(gap.start_time_seconds)}–{_service_time(gap.end_time_seconds)}"
            ),
        }
        for gap in gaps
    )


def outcome_rows_v1(
    presentation: UnifiedPresentationBundleV1,
) -> tuple[dict[str, object], ...]:
    """Preserve unified outcome and solver vectors without a weighted total."""
    _require_presentation(presentation)
    outcome = presentation.outcome
    facts = (
        ("Định đoạt phương án B", outcome.b_disposition),
        ("Quyết định điều chỉnh", outcome.adjustment_decision),
        ("Hành động được chọn", outcome.selected_action),
        ("Lựa chọn solver", outcome.solver_choice),
        ("Đã thử solver", outcome.solver_attempted),
        ("Trạng thái heuristic", outcome.heuristic_result_status),
        ("Trạng thái OR-Tools", outcome.ortools_result_status),
        ("Trạng thái native heuristic", outcome.heuristic_native_solver_status),
        ("Trạng thái native OR-Tools", outcome.ortools_native_solver_status),
        ("Mã từ chối của validator", _json_text(outcome.validator_rejection_codes)),
        ("Tên mục tiêu so sánh", _json_text(outcome.comparison_objective_names)),
        ("Vector heuristic", _json_text(outcome.heuristic_objective_vector)),
        ("Vector OR-Tools", _json_text(outcome.ortools_objective_vector)),
        ("Solver được khuyến nghị", outcome.recommended_solver),
        ("Căn cứ so sánh", outcome.comparison_reason),
        ("Có C được chấp nhận", outcome.accepted_c_exists),
        ("Thẩm quyền C", outcome.accepted_c_authority),
    )
    return tuple({"Nội dung": label, "Giá trị": value} for label, value in facts)


def accepted_c_summary_v1(
    presentation: UnifiedPresentationBundleV1,
) -> dict[str, object] | None:
    """Return accepted-C facts and explicitly documented ``DISPLAY_DERIVED`` metrics."""
    _require_presentation(presentation)
    if not presentation.outcome.accepted_c_exists:
        return None
    scenario_b = presentation.scenario("B")
    scenario_c = presentation.scenario("C")
    initial_fleet = presentation.initial_fleet
    if scenario_b is None or scenario_c is None or initial_fleet is None:
        return None
    return {
        "b_trip_count": len(scenario_b.trips),
        "accepted_c_trip_count": len(scenario_c.trips),
        "shifted_c_trip_count": sum(
            trip.shift_minutes is not None and trip.shift_minutes != 0 for trip in scenario_c.trips
        ),
        "minimum_required_fleet": initial_fleet.minimum_required_fleet,
        "available_fleet_limit": initial_fleet.available_fleet_limit,
        "fleet_margin": initial_fleet.fleet_margin,
        "terminal_1_vehicle_count": initial_fleet.terminal_1_vehicle_count,
        "terminal_2_vehicle_count": initial_fleet.terminal_2_vehicle_count,
        "maximum_b_load_factor": _maximum(block.b_load_factor for block in presentation.blocks),
        "maximum_c_load_factor": _maximum(block.c_load_factor for block in presentation.blocks),
        "b_warning_block_count": sum(
            block.b_status == "WARNING_ABOVE_85" for block in presentation.blocks
        ),
        "b_critical_block_count": sum(
            block.b_status == "CRITICAL_ABOVE_90" for block in presentation.blocks
        ),
        "c_warning_block_count": sum(
            block.c_status == "WARNING_ABOVE_85" for block in presentation.blocks
        ),
        "c_critical_block_count": sum(
            block.c_status == "CRITICAL_ABOVE_90" for block in presentation.blocks
        ),
        "headway_regime_count": len(presentation.headway_regimes),
        "exceptional_headway_count": sum(
            len(regime.exceptional_headways) for regime in presentation.headway_regimes
        ),
        "accepted_solution_fingerprint": presentation.accepted_solution_fingerprint,
    }


def headway_regime_rows_v1(
    presentation: UnifiedPresentationBundleV1,
) -> tuple[dict[str, object], ...]:
    """Format exact returned headway-regime facts without recomputing headways."""
    _require_presentation(presentation)
    regimes = sorted(
        presentation.headway_regimes,
        key=lambda regime: (
            _DIRECTION_ORDER.get(regime.direction, 99),
            regime.start_time_seconds,
            regime.end_time_seconds,
            regime.regime_id,
        ),
    )
    return tuple(
        {
            "Mã chế độ": regime.regime_id,
            "Chiều": direction_label_v1(presentation, regime.direction),
            "Khung thời gian": (
                f"{_service_time(regime.start_time_seconds)}–"
                f"{_service_time(regime.end_time_seconds)}"
            ),
            "Block được bao phủ": _json_text(regime.covered_analysis_blocks),
            "Số chuyến": regime.trip_count,
            "Tần suất mục tiêu": regime.target_service_rate,
            "Giãn cách mục tiêu": regime.target_headway,
            "Chuỗi giãn cách thực tế": _json_text(regime.actual_headway_sequence),
            "Giãn cách chuyển tiếp": _json_text(regime.transition_headways),
            "Giãn cách ngoại lệ": _json_text(regime.exceptional_headways),
            "Căn cứ ranh giới": regime.boundary_reason,
            "Trạng thái đều đặn": regime.regularity_status,
        }
        for regime in regimes
    )


def expert_review_discrepancy_rows_v1(
    presentation: UnifiedPresentationBundleV1,
) -> tuple[dict[str, object], ...]:
    """Return discrepancy evidence corresponding to every expert-review code."""
    _require_presentation(presentation)
    codes = set(presentation.expert_review_required_codes)
    return tuple(
        {
            "Mã rà soát": item.reason_code,
            "Mã sự kiện": item.fact_code,
            "Nhóm": item.category,
            "Quy tắc": item.comparison_rule,
            "Trạng thái": item.comparison_status,
            "Giá trị legacy": _json_text(item.legacy_value),
            "Giá trị unified": _json_text(item.unified_value),
            "Giải thích": item.explanation,
        }
        for item in presentation.discrepancies
        if item.reason_code in codes or item.fact_code in codes
    )


__all__ = [
    "DISPLAY_DERIVED",
    "DISPLAY_DERIVED_FIELDS",
    "accepted_c_summary_v1",
    "demand_block_rows_v1",
    "demand_gap_rows_v1",
    "demand_summary_v1",
    "direction_label_v1",
    "expert_review_discrepancy_rows_v1",
    "headway_regime_rows_v1",
    "outcome_rows_v1",
    "technical_dimension_rows_v1",
    "technical_summary_v1",
]
