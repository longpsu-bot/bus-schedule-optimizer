"""Plotly figures for the validation-only unified presentation bundle."""

from __future__ import annotations

import math

import plotly.graph_objects as go

from .unified_presentation import (
    PRESENTATION_MODE_VALIDATION_ONLY,
    PresentationBlockV1,
    PresentationTripV1,
    UnifiedPresentationBundleV1,
    verify_unified_presentation_integrity_v1,
)

_STATUS_COLORS = {
    "WITHIN_PLANNING_CEILING": "#2E8B57",
    "LOW_LOAD_REVIEW_ONLY": "#5B8FF9",
    "ELIGIBLE_DONOR_PERIOD": "#5B8FF9",
    "WARNING_ABOVE_85": "#F5A623",
    "CRITICAL_ABOVE_90": "#D64545",
    "NO_SERVICE_WITH_DEMAND": "#8B0000",
    "INSUFFICIENT_DATA": "#8A8F98",
}
_SCENARIO_COLORS = {"A": "#8A8F98", "B": "#2673DD", "C": "#1A9850"}
_DIRECTION_ORDER = {"outbound": 0, "inbound": 1, "combined": 2}
_DEMAND_DIRECTION_ORDER = ("combined", "outbound", "inbound")
_SCENARIO_ORDER = {"A": 0, "B": 1, "C": 2}


def _service_time(seconds: int | None) -> str:
    if seconds is None:
        return ""
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours:02d}:{minutes:02d}"


def _figure_meta(presentation: UnifiedPresentationBundleV1) -> dict[str, object]:
    return {
        "presentation_mode": presentation.presentation_mode,
        "presentation_fingerprint": presentation.presentation_fingerprint,
        "source_b_fingerprint": presentation.source_b_fingerprint,
        "accepted_solution_fingerprint": presentation.accepted_solution_fingerprint,
        "accepted_c_exists": presentation.outcome.accepted_c_exists,
        "scenario_c_authority": presentation.outcome.accepted_c_authority,
        "cutover_blocked": presentation.cutover_blocked,
        "blocking_discrepancy_codes": list(presentation.blocking_discrepancy_codes),
        "expert_review_required_codes": list(presentation.expert_review_required_codes),
        "demand_grain": "EXACT_CONTRACT_BLOCKS_NO_AGGREGATION",
    }


def _review_annotation(presentation: UnifiedPresentationBundleV1) -> str:
    status = "BỊ CHẶN CUTOVER" if presentation.cutover_blocked else "CHỜ RÀ SOÁT"
    return f"{PRESENTATION_MODE_VALIDATION_ONLY} · {status}"


def _direction_display(
    presentation: UnifiedPresentationBundleV1,
    direction: str,
) -> str:
    if direction == "outbound":
        return f"{presentation.terminal_1_name} → {presentation.terminal_2_name}"
    if direction == "inbound":
        return f"{presentation.terminal_2_name} → {presentation.terminal_1_name}"
    return "Tổng hợp hai chiều"


def _block_category(
    presentation: UnifiedPresentationBundleV1,
    block: object,
) -> str:
    return (
        f"{_service_time(block.block_start_seconds)}–"
        f"{_service_time(block.block_end_seconds)} · "
        f"{_direction_display(presentation, block.direction)} · {block.block_id}"
    )


def _build_unified_demand_supply_figure_v1(
    presentation: UnifiedPresentationBundleV1,
    blocks: tuple[PresentationBlockV1, ...],
    *,
    metadata: dict[str, object] | None = None,
) -> go.Figure:
    categories = [_block_category(presentation, block) for block in blocks]
    figure = go.Figure()
    if blocks:
        figure.add_trace(
            go.Bar(
                name="Nhu cầu hành khách",
                x=categories,
                y=[block.passenger_demand for block in blocks],
                marker_color=[_STATUS_COLORS.get(block.b_status, "#8A8F98") for block in blocks],
                customdata=[
                    [
                        block.block_id,
                        block.direction,
                        block.confidence,
                        block.b_status,
                        block.allocation_reason,
                        _direction_display(presentation, block.direction),
                    ]
                    for block in blocks
                ],
                hovertemplate=(
                    "Block=%{customdata[0]}<br>"
                    "Chiều=%{customdata[5]}<br>"
                    "Nhu cầu=%{y}<br>"
                    "Độ tin cậy=%{customdata[2]}<br>"
                    "Trạng thái B=%{customdata[3]}<br>"
                    "Căn cứ=%{customdata[4]}<extra></extra>"
                ),
                yaxis="y",
            )
        )
        if any(block.a_trip_count is not None for block in blocks):
            figure.add_trace(
                go.Scatter(
                    name="Số chuyến A",
                    x=categories,
                    y=[block.a_trip_count for block in blocks],
                    mode="lines+markers",
                    line={"color": _SCENARIO_COLORS["A"], "dash": "dot"},
                    yaxis="y2",
                    hovertemplate="Số chuyến A=%{y}<extra></extra>",
                )
            )
        figure.add_trace(
            go.Scatter(
                name="Số chuyến B",
                x=categories,
                y=[block.b_trip_count for block in blocks],
                mode="lines+markers",
                line={"color": _SCENARIO_COLORS["B"], "width": 3},
                yaxis="y2",
                hovertemplate="Số chuyến B=%{y}<extra></extra>",
            )
        )
        if presentation.outcome.accepted_c_exists:
            figure.add_trace(
                go.Scatter(
                    name="Số chuyến C được chấp nhận",
                    x=categories,
                    y=[block.c_actual_trip_count for block in blocks],
                    mode="lines+markers",
                    line={"color": _SCENARIO_COLORS["C"], "width": 3},
                    yaxis="y2",
                    hovertemplate="Số chuyến C=%{y}<extra></extra>",
                )
            )
        figure.add_trace(
            go.Scatter(
                name="Số chuyến yêu cầu 85%",
                x=categories,
                y=[block.required_trips_85 for block in blocks],
                mode="lines+markers",
                line={"color": "#7A5195", "dash": "dash"},
                yaxis="y2",
                hovertemplate="Yêu cầu 85%%=%{y}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                name="Số chuyến yêu cầu 90%",
                x=categories,
                y=[block.required_trips_90 for block in blocks],
                mode="lines+markers",
                line={"color": "#EF5675", "dash": "dashdot"},
                yaxis="y2",
                hovertemplate="Yêu cầu 90%%=%{y}<extra></extra>",
            )
        )
    else:
        figure.add_annotation(
            text="Không có block nhu cầu Contract V1 được trả về.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )

    figure.update_layout(
        title="Đối chiếu nhu cầu và số chuyến theo block Contract V1",
        barmode="group",
        xaxis={
            "title": "Block nhu cầu chính xác · chiều · mã block",
            "categoryorder": "array",
            "categoryarray": categories,
        },
        yaxis={"title": "Nhu cầu hành khách"},
        yaxis2={
            "title": "Số chuyến",
            "overlaying": "y",
            "side": "right",
            "rangemode": "tozero",
        },
        legend={"orientation": "h", "y": -0.3},
        margin={"b": 180, "t": 100},
        meta={**_figure_meta(presentation), **(metadata or {})},
        annotations=[
            *figure.layout.annotations,
            {
                "text": _review_annotation(presentation),
                "xref": "paper",
                "yref": "paper",
                "x": 1,
                "y": 1.12,
                "showarrow": False,
                "font": {"color": "#8B0000", "size": 12},
            },
        ],
    )
    return figure


def available_unified_directions_v1(
    presentation: UnifiedPresentationBundleV1,
) -> tuple[str, ...]:
    """Return only exact block directions, in deterministic display order."""
    if not isinstance(presentation, UnifiedPresentationBundleV1):
        raise TypeError("presentation must be a UnifiedPresentationBundleV1")
    verify_unified_presentation_integrity_v1(presentation)
    available = {block.direction for block in presentation.blocks}
    unsupported = sorted(available - set(_DEMAND_DIRECTION_ORDER))
    if unsupported:
        raise ValueError(f"unsupported Contract V1 block directions: {unsupported}")
    return tuple(direction for direction in _DEMAND_DIRECTION_ORDER if direction in available)


def build_unified_demand_supply_figure_v1(
    presentation: UnifiedPresentationBundleV1,
) -> go.Figure:
    """Build an exact-grain demand/supply figure without rerunning business logic."""
    if not isinstance(presentation, UnifiedPresentationBundleV1):
        raise TypeError("presentation must be a UnifiedPresentationBundleV1")
    verify_unified_presentation_integrity_v1(presentation)
    return _build_unified_demand_supply_figure_v1(presentation, presentation.blocks)


def build_unified_demand_supply_figure_for_direction_v1(
    presentation: UnifiedPresentationBundleV1,
    direction: str,
) -> go.Figure:
    """Build one exact returned direction subset without allocation or aggregation."""
    available = available_unified_directions_v1(presentation)
    if not isinstance(direction, str):
        raise TypeError("direction must be a string")
    if direction not in available:
        raise ValueError(f"direction must be one of the exact returned directions: {available}")
    blocks = tuple(block for block in presentation.blocks if block.direction == direction)
    return _build_unified_demand_supply_figure_v1(
        presentation,
        blocks,
        metadata={
            "displayed_direction": direction,
            "displayed_grain": "EXACT_DIRECTION_SUBSET",
        },
    )


def _departure_customdata(
    presentation: UnifiedPresentationBundleV1,
    trip: PresentationTripV1,
) -> list[object]:
    return [
        trip.trip_id,
        trip.direction,
        trip.departure_terminal,
        trip.arrival_terminal,
        _service_time(trip.departure_time_seconds),
        _service_time(trip.arrival_time_seconds),
        _direction_display(presentation, trip.direction),
    ]


def _departure_ticks(
    trips: tuple[PresentationTripV1, ...],
) -> tuple[list[int], list[str]]:
    if not trips:
        return [], []
    minimum = min(trip.departure_time_seconds for trip in trips)
    maximum = max(trip.departure_time_seconds for trip in trips)
    first = math.floor(minimum / 3600) * 3600
    last = math.ceil(maximum / 3600) * 3600
    values = list(range(first, last + 1, 3600))
    return values, [_service_time(value) for value in values]


def build_unified_departure_figure_v1(
    presentation: UnifiedPresentationBundleV1,
) -> go.Figure:
    """Build exact A/B/accepted-C departure lanes on a continuous service axis."""
    if not isinstance(presentation, UnifiedPresentationBundleV1):
        raise TypeError("presentation must be a UnifiedPresentationBundleV1")
    verify_unified_presentation_integrity_v1(presentation)

    figure = go.Figure()
    lane_order: list[str] = []
    all_trips: list[PresentationTripV1] = []
    for scenario in sorted(
        presentation.scenarios,
        key=lambda item: _SCENARIO_ORDER[item.scenario_id],
    ):
        for direction in sorted(
            {trip.direction for trip in scenario.trips},
            key=lambda value: _DIRECTION_ORDER.get(value, 99),
        ):
            trips = tuple(trip for trip in scenario.trips if trip.direction == direction)
            if not trips:
                continue
            lane = f"{scenario.scenario_id} · {_direction_display(presentation, direction)}"
            lane_order.append(lane)
            all_trips.extend(trips)
            if scenario.scenario_id == "C":
                customdata = [
                    [
                        *_departure_customdata(presentation, trip),
                        trip.source_b_trip_id,
                        _service_time(trip.b_departure_time_seconds),
                        trip.shift_minutes,
                        trip.headway_regime_id,
                        trip.change_reason,
                        trip.vehicle_assignment,
                    ]
                    for trip in trips
                ]
                hovertemplate = (
                    "C trip=%{customdata[0]}<br>"
                    "Chiều=%{customdata[6]}<br>"
                    "Bến đi=%{customdata[2]}<br>"
                    "Bến đến=%{customdata[3]}<br>"
                    "Giờ C=%{customdata[4]}<br>"
                    "Giờ đến=%{customdata[5]}<br>"
                    "Nguồn B=%{customdata[7]}<br>"
                    "Giờ B=%{customdata[8]}<br>"
                    "Dịch chuyển (phút)=%{customdata[9]}<br>"
                    "Chế độ=%{customdata[10]}<br>"
                    "Lý do=%{customdata[11]}<br>"
                    "Xe=%{customdata[12]}<extra></extra>"
                )
            else:
                customdata = [_departure_customdata(presentation, trip) for trip in trips]
                hovertemplate = (
                    "Trip=%{customdata[0]}<br>"
                    "Chiều=%{customdata[6]}<br>"
                    "Bến đi=%{customdata[2]}<br>"
                    "Bến đến=%{customdata[3]}<br>"
                    "Giờ đi=%{customdata[4]}<br>"
                    "Giờ đến=%{customdata[5]}<extra></extra>"
                )
            figure.add_trace(
                go.Scatter(
                    name=lane,
                    x=[trip.departure_time_seconds for trip in trips],
                    y=[lane] * len(trips),
                    mode="markers",
                    marker={
                        "size": 11,
                        "color": _SCENARIO_COLORS[scenario.scenario_id],
                        "symbol": "diamond" if scenario.scenario_id == "C" else "circle",
                    },
                    customdata=customdata,
                    hovertemplate=hovertemplate,
                )
            )

    ticks, tick_text = _departure_ticks(tuple(all_trips))
    figure.update_layout(
        title="Giờ xuất bến chính xác theo kịch bản và chiều",
        xaxis={
            "title": "Trục thời gian ngày dịch vụ liên tục",
            "tickmode": "array",
            "tickvals": ticks,
            "ticktext": tick_text,
        },
        yaxis={
            "title": "Kịch bản · chiều",
            "categoryorder": "array",
            "categoryarray": lane_order,
        },
        legend={"orientation": "h", "y": -0.18},
        margin={"l": 140, "b": 110, "t": 100},
        meta=_figure_meta(presentation),
        annotations=[
            {
                "text": _review_annotation(presentation),
                "xref": "paper",
                "yref": "paper",
                "x": 1,
                "y": 1.12,
                "showarrow": False,
                "font": {"color": "#8B0000", "size": 12},
            }
        ],
    )
    return figure


__all__ = [
    "available_unified_directions_v1",
    "build_unified_demand_supply_figure_for_direction_v1",
    "build_unified_demand_supply_figure_v1",
    "build_unified_departure_figure_v1",
]
