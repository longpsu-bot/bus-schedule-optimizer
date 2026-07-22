from __future__ import annotations

import math
import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

import plotly
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from .block_supply import (
    BlockSupplyComparison,
    SupplyPresentationStatus,
    aggregate_block_supply,
    build_block_supply_comparison,
)
from .models import (
    AnalysisBundle,
    BlockEvaluation,
    Direction,
    HeadwayType,
    ScenarioCStatus,
    ScenarioResult,
    Trip,
)
from .time_utils import format_hhmm

DAY_SECONDS = 24 * 60 * 60
DEMAND_LANE = "Nhu cầu và mức cung ứng theo block"
SCENARIO_COLORS = {
    "A": "#2563EB",
    "B": "#F59E0B",
    "C": "#059669",
    "C1": "#059669",
    "C2": "#7C3AED",
    "C3": "#DB2777",
}
DEMAND_DIRECTION_COLORS = {
    Direction.COMBINED: "#2563EB",
    Direction.TERMINAL_1_TO_2: "#2563EB",
    Direction.TERMINAL_2_TO_1: "#93C5FD",
}
SUPPLY_STATUS_STYLES = {
    "no_service": ("Không có chuyến", "#991B1B", "dash"),
    "critical": ("Tải >90%", "#DC2626", "solid"),
    "warning": ("Tải 85–90%", "#F59E0B", "solid"),
    "surplus": ("Dư chuyến tại target", "#60A5FA", "dot"),
}


def _configure_kaleido_for_unicode_paths() -> None:
    """Use an ASCII temp path because Kaleido 0.2.1 cannot open Unicode package paths."""
    source = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
    target = Path(tempfile.gettempdir()) / "bus_schedule_plotly.min.js"
    if not target.exists() or target.stat().st_size != source.stat().st_size:
        shutil.copyfile(source, target)
    pio.kaleido.scope.plotlyjs = str(target)


def diagram_png_bytes(figure: go.Figure) -> bytes:
    _configure_kaleido_for_unicode_paths()
    return figure.to_image(format="png", width=1600, height=1100, scale=1.5)


def _recommended_scenario(bundle: AnalysisBundle) -> str | None:
    candidates = [
        result
        for result in bundle.scenarios
        if result.name.startswith("C")
        and result.score is not None
        and (result.name != "C" or result.generation_status == ScenarioCStatus.SUITABLE_REGULAR)
    ]
    if not candidates:
        return None
    return max(
        candidates, key=lambda result: (result.score, -result.evaluation.blocks_over_target)
    ).name


def _scenario_lane_prefix(scenario: str, recommended: bool = False) -> str:
    if scenario == "A":
        return "A hiện tại"
    if scenario == "B":
        return "B — Biểu đồ giờ đề xuất"
    star = "★ " if recommended else ""
    if scenario == "C":
        return f"{star}C — Tái phân bổ ổn định theo nhu cầu"
    return f"{star}{scenario} khuyến nghị"


def _lane_for_direction(
    result: ScenarioResult, direction: Direction, recommended_scenario: str | None
) -> str:
    prefix = _scenario_lane_prefix(result.name, result.name == recommended_scenario)
    return f"{prefix} · {_direction_label(result, direction)}"


def _lane(result: ScenarioResult, trip: Trip, recommended_scenario: str | None = None) -> str:
    prefix = _scenario_lane_prefix(result.name, result.name == recommended_scenario)
    return f"{prefix} · {_direction_label(result, trip.direction)}"


def _lanes(bundle: AnalysisBundle, recommended_scenario: str | None) -> list[str]:
    lanes = []
    for result in bundle.scenarios:
        prefix = _scenario_lane_prefix(result.name, result.name == recommended_scenario)
        lanes.extend(
            [
                f"{prefix} · {_direction_label(result, Direction.TERMINAL_1_TO_2)}",
                f"{prefix} · {_direction_label(result, Direction.TERMINAL_2_TO_1)}",
            ]
        )
    return lanes


def _service_day_origin(bundle: AnalysisBundle) -> int:
    """Choose the first point after the largest idle gap on the 24-hour clock."""
    points = sorted(
        {
            trip.departure_seconds % DAY_SECONDS
            for result in bundle.scenarios
            for trip in result.trips
        }
    )
    if not points:
        points = sorted(
            {
                block.block_start_seconds % DAY_SECONDS
                for result in bundle.scenarios
                for block in result.evaluation.blocks
            }
        )
    if len(points) <= 1:
        return points[0] if points else 0
    gaps = [
        ((points[(index + 1) % len(points)] - point) % DAY_SECONDS, index)
        for index, point in enumerate(points)
    ]
    _, gap_index = max(gaps)
    return points[(gap_index + 1) % len(points)]


def _block_service_day_origin(rows: list[BlockSupplyComparison]) -> int:
    """Choose a chronological category origin from block boundaries, not trip times."""
    points = sorted({row.block_start_seconds % DAY_SECONDS for row in rows})
    if len(points) <= 1:
        return points[0] if points else 0
    gaps = [
        ((points[(index + 1) % len(points)] - point) % DAY_SECONDS, index)
        for index, point in enumerate(points)
    ]
    _, gap_index = max(gaps)
    return points[(gap_index + 1) % len(points)]


def _project_seconds(seconds: int | float, origin: int) -> float:
    """Project a clock value onto a continuous service-day axis."""
    value = float(seconds)
    if value >= DAY_SECONDS:
        projected = value
        while projected < origin:
            projected += DAY_SECONDS
        return projected
    projected = value % DAY_SECONDS
    if projected < origin:
        projected += DAY_SECONDS
    return projected


def _project_interval(start_seconds: int, end_seconds: int, origin: int) -> tuple[float, float]:
    start = _project_seconds(start_seconds, origin)
    duration = end_seconds - start_seconds
    while duration <= 0:
        duration += DAY_SECONDS
    return start, start + duration


def _clock_hhmm(seconds: int | float | None) -> str:
    if seconds is None:
        return "—"
    return format_hhmm(float(seconds) % DAY_SECONDS)


def _direction_label(result: ScenarioResult, direction: Direction) -> str:
    if direction == Direction.TERMINAL_1_TO_2:
        return f"{result.parameters.terminal_1_name} → {result.parameters.terminal_2_name}"
    if direction == Direction.TERMINAL_2_TO_1:
        return f"{result.parameters.terminal_2_name} → {result.parameters.terminal_1_name}"
    return "Tổng hợp hai chiều"


def _matching_block(result: ScenarioResult, trip: Trip, origin: int) -> BlockEvaluation | None:
    departure = _project_seconds(trip.departure_seconds, origin)
    return next(
        (
            block
            for block in result.evaluation.blocks
            if _project_interval(block.block_start_seconds, block.block_end_seconds, origin)[0]
            <= departure
            < _project_interval(block.block_start_seconds, block.block_end_seconds, origin)[1]
            and block.direction in {trip.direction, Direction.COMBINED}
        ),
        None,
    )


def _unique_blocks(
    blocks: Iterable[BlockEvaluation], origin: int
) -> list[tuple[float, float, BlockEvaluation]]:
    by_interval: dict[tuple[float, float], BlockEvaluation] = {}
    for block in blocks:
        start, end = _project_interval(block.block_start_seconds, block.block_end_seconds, origin)
        key = (start, end)
        current = by_interval.get(key)
        if current is None or block.demand > current.demand:
            by_interval[key] = block
    return [(start, end, by_interval[(start, end)]) for start, end in sorted(by_interval)]


def _format_number(value: float | int | None, suffix: str = "") -> str:
    if value is None:
        return "—"
    formatted = f"{value:,.1f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"{formatted}{suffix}"


def _format_percent_vi(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1%}".replace(".", ",")


def _trip_gap_label(value: int) -> str:
    if value < 0:
        return f"thiếu {abs(value)} chuyến"
    if value > 0:
        return f"dư {value} chuyến"
    return "đủ chuyến"


def _add_demand_traces(
    figure: go.Figure,
    blocks: list[tuple[float, float, BlockEvaluation]],
) -> None:
    direction_order = (
        Direction.COMBINED,
        Direction.TERMINAL_1_TO_2,
        Direction.TERMINAL_2_TO_1,
    )
    available_directions = {block.direction for _, _, block in blocks}
    for direction in direction_order:
        if direction not in available_directions:
            continue
        direction_label = _direction_label_for_demand(direction)
        demand_label = (
            "Nhu cầu tổng hợp hai chiều — ước tính"
            if direction == Direction.COMBINED
            else f"Nhu cầu {direction_label}"
        )
        selected = [item for item in blocks if item[2].direction == direction]
        customdata = [
            [
                _clock_hhmm(block.block_start_seconds),
                _clock_hhmm(block.block_end_seconds),
                direction_label,
                _format_number(block.demand),
                block.data_note or "Dữ liệu theo chiều",
            ]
            for _, _, block in selected
        ]
        figure.add_trace(
            go.Bar(
                x=[(start + end) / 120 for start, end, _ in selected],
                y=[block.demand for _, _, block in selected],
                width=[(end - start) / 60 for start, end, _ in selected],
                name=demand_label,
                legendgroup="demand",
                marker={
                    "color": DEMAND_DIRECTION_COLORS[direction],
                    "line": {"color": "#FFFFFF", "width": 0.8},
                },
                opacity=0.88,
                meta={"trace_type": "demand", "direction": direction.value, "panel": 1},
                customdata=customdata,
                hovertemplate=(
                    "Block: %{customdata[0]}–%{customdata[1]}<br>"
                    "Phạm vi: %{customdata[2]}<br>"
                    "Nhu cầu: %{customdata[3]} hành khách<br>"
                    "%{customdata[4]}<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )

    totals: dict[tuple[float, float], float] = {}
    for start, end, block in blocks:
        totals[(start, end)] = totals.get((start, end), 0) + block.demand
    if totals:
        (peak_start, peak_end), peak_demand = max(totals.items(), key=lambda item: item[1])
        figure.add_annotation(
            x=(peak_start + peak_end) / 120,
            y=peak_demand,
            text=(
                f"Cao nhất: {peak_demand:.0f} khách"
                f"<br>{_clock_hhmm(peak_start)}–{_clock_hhmm(peak_end)}"
            ),
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-38,
            bgcolor="rgba(255,255,255,0.88)",
            bordercolor="#CBD5E1",
            borderwidth=1,
            row=1,
            col=1,
        )


def _direction_label_for_demand(direction: Direction) -> str:
    if direction == Direction.COMBINED:
        return "Tổng hợp hai chiều — ước tính"
    if direction == Direction.TERMINAL_1_TO_2:
        return "Bến 1 → Bến 2"
    return "Bến 2 → Bến 1"


def _resolve_supply_direction(
    rows: list[BlockSupplyComparison], requested: Direction | str
) -> Direction:
    direction = Direction(requested)
    if direction == Direction.COMBINED:
        return direction
    if any(row.direction == direction for row in rows):
        return direction
    return Direction.COMBINED


def _rows_by_interval(
    rows: list[BlockSupplyComparison],
) -> dict[tuple[int, int], list[BlockSupplyComparison]]:
    grouped: dict[tuple[int, int], list[BlockSupplyComparison]] = {}
    for row in rows:
        grouped.setdefault((row.block_start_seconds, row.block_end_seconds), []).append(row)
    return grouped


def _block_category(row: BlockSupplyComparison) -> str:
    return f"{_clock_hhmm(row.block_start_seconds)}–{_clock_hhmm(row.block_end_seconds)}"


def _trip_counts_by_interval(
    rows: list[BlockSupplyComparison],
    result: ScenarioResult,
    origin: int,
) -> dict[tuple[int, int], int]:
    counts: dict[tuple[int, int], int] = {}
    for row in rows:
        start, end = _project_interval(row.block_start_seconds, row.block_end_seconds, origin)
        counts[(row.block_start_seconds, row.block_end_seconds)] = sum(
            start <= _project_seconds(trip.departure_seconds, origin) < end
            and (row.direction == Direction.COMBINED or trip.direction == row.direction)
            for trip in result.trips
        )
    return counts


def _hover_customdata(
    row: BlockSupplyComparison,
    interval_rows: list[BlockSupplyComparison],
    result_b: ScenarioResult,
    a_trip_count: int | None = None,
) -> list[object]:
    demand_by_direction = {
        direction: sum(
            item.passenger_demand for item in interval_rows if item.direction == direction
        )
        for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    }
    has_directional = any(item.direction != Direction.COMBINED for item in interval_rows)
    total_demand = (
        sum(item.passenger_demand for item in interval_rows if item.direction != Direction.COMBINED)
        if has_directional
        else sum(item.passenger_demand for item in interval_rows)
    )
    return [
        _clock_hhmm(row.block_start_seconds),
        _clock_hhmm(row.block_end_seconds),
        (
            _format_number(demand_by_direction[Direction.TERMINAL_1_TO_2])
            if has_directional
            else "—"
        ),
        (
            _format_number(demand_by_direction[Direction.TERMINAL_2_TO_1])
            if has_directional
            else "—"
        ),
        _format_number(total_demand),
        row.vehicle_capacity,
        row.b_trip_count,
        row.c_trip_count,
        row.required_trips_85,
        row.minimum_trips_90,
        _format_number(row.b_nominal_capacity),
        _format_number(row.c_nominal_capacity),
        _format_percent_vi(row.b_load_factor),
        _format_percent_vi(row.c_load_factor),
        _trip_gap_label(row.b_trip_gap_to_85),
        _trip_gap_label(row.c_trip_gap_to_85),
        row.b_status.value,
        row.c_status.value,
        row.demand_confidence,
        _direction_label(result_b, row.direction),
        _format_number(row.passenger_demand),
        a_trip_count if a_trip_count is not None else "—",
    ]


_SUPPLY_HOVER_PREFIX = (
    "Khung giờ: %{customdata[0]}–%{customdata[1]}<br>"
    "Phạm vi: %{customdata[19]}<br>"
    "Nhu cầu phạm vi đang xem: %{customdata[20]} hành khách<br>"
    "Nhu cầu chiều 1: %{customdata[2]} hành khách<br>"
    "Nhu cầu chiều 2: %{customdata[3]} hành khách<br>"
    "Tổng nhu cầu: %{customdata[4]} hành khách<br>"
    "Sức chứa phương tiện: %{customdata[5]} hành khách<br>"
)
_SUPPLY_HOVER_SUFFIX = (
    "B — số chuyến: %{customdata[6]}<br>"
    "C — số chuyến: %{customdata[7]}<br>"
    "Số chuyến cần tại 85%: %{customdata[8]}<br>"
    "Số chuyến tối thiểu tại 90%: %{customdata[9]}<br>"
    "B — sức cung danh nghĩa: %{customdata[10]}<br>"
    "C — sức cung danh nghĩa: %{customdata[11]}<br>"
    "B — load factor: %{customdata[12]} · %{customdata[14]}<br>"
    "C — load factor: %{customdata[13]} · %{customdata[15]}<br>"
    "Trạng thái B: %{customdata[16]}<br>"
    "Trạng thái C: %{customdata[17]}<br>"
    "Tin cậy nhu cầu: %{customdata[18]}<extra></extra>"
)
SUPPLY_HOVER_TEMPLATE = (
    _SUPPLY_HOVER_PREFIX
    + "A — số chuyến hiện tại: %{customdata[21]}<br>"
    + _SUPPLY_HOVER_SUFFIX
)
SUPPLY_HOVER_TEMPLATE_NO_A = _SUPPLY_HOVER_PREFIX + _SUPPLY_HOVER_SUFFIX


def _demand_trace_rows(
    base_rows: list[BlockSupplyComparison], direction: Direction
) -> list[tuple[Direction, list[BlockSupplyComparison]]]:
    if direction != Direction.COMBINED:
        return [(direction, [row for row in base_rows if row.direction == direction])]
    combined = [row for row in base_rows if row.direction == Direction.COMBINED]
    if combined:
        return [(Direction.COMBINED, combined)]
    return [
        (
            item_direction,
            [row for row in base_rows if row.direction == item_direction],
        )
        for item_direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
        if any(row.direction == item_direction for row in base_rows)
    ]


def _add_quantitative_demand_traces(
    figure: go.Figure,
    base_rows: list[BlockSupplyComparison],
    supply_rows: list[BlockSupplyComparison],
    result_b: ScenarioResult,
    origin: int,
    direction: Direction,
    result_a: ScenarioResult | None = None,
) -> None:
    supply_by_interval = {
        (row.block_start_seconds, row.block_end_seconds): row for row in supply_rows
    }
    base_by_interval = _rows_by_interval(base_rows)
    interval_order = {
        (row.block_start_seconds, row.block_end_seconds): index
        for index, row in enumerate(supply_rows)
    }
    a_counts = (
        _trip_counts_by_interval(supply_rows, result_a, origin)
        if result_a is not None and result_a.trips
        else None
    )
    for demand_direction, selected in _demand_trace_rows(base_rows, direction):
        if not selected:
            continue
        label = (
            "Nhu cầu tổng hợp hai chiều — ước tính"
            if demand_direction == Direction.COMBINED
            else f"Nhu cầu {_direction_label(result_b, demand_direction)}"
        )
        x_values: list[str] = []
        y_values: list[float] = []
        customdata: list[list[object]] = []
        for row in sorted(
            selected,
            key=lambda item: interval_order[
                (item.block_start_seconds, item.block_end_seconds)
            ],
        ):
            supply = supply_by_interval[(row.block_start_seconds, row.block_end_seconds)]
            interval_rows = base_by_interval[(row.block_start_seconds, row.block_end_seconds)]
            key = (row.block_start_seconds, row.block_end_seconds)
            x_values.append(_block_category(row))
            y_values.append(row.passenger_demand)
            customdata.append(
                _hover_customdata(
                    supply,
                    interval_rows,
                    result_b,
                    None if a_counts is None else a_counts[key],
                )
            )
        figure.add_trace(
            go.Bar(
                x=x_values,
                y=y_values,
                name=label,
                legendgroup="demand",
                marker={
                    "color": DEMAND_DIRECTION_COLORS[demand_direction],
                    "line": {"color": "#FFFFFF", "width": 0.8},
                },
                opacity=0.68,
                meta={
                    "trace_type": "demand",
                    "direction": demand_direction.value,
                    "panel": 1,
                    "supply_view": direction.value,
                },
                customdata=customdata,
                hovertemplate=(
                    SUPPLY_HOVER_TEMPLATE if a_counts is not None else SUPPLY_HOVER_TEMPLATE_NO_A
                ),
            ),
            row=1,
            col=1,
            secondary_y=False,
        )

    if supply_rows:
        peak = max(supply_rows, key=lambda item: item.passenger_demand)
        figure.add_annotation(
            x=_block_category(peak),
            y=peak.passenger_demand,
            text=(
                f"Cao nhất: {peak.passenger_demand:.0f} khách"
                f"<br>{_clock_hhmm(peak.block_start_seconds)}–"
                f"{_clock_hhmm(peak.block_end_seconds)}"
            ),
            showarrow=True,
            arrowhead=2,
            ax=0,
            ay=-38,
            bgcolor="rgba(255,255,255,0.90)",
            bordercolor="#CBD5E1",
            borderwidth=1,
            row=1,
            col=1,
        )


def _line_values(
    rows: list[BlockSupplyComparison],
    value_name: str,
    base_by_interval: dict[tuple[int, int], list[BlockSupplyComparison]],
    result_b: ScenarioResult,
    a_counts: dict[tuple[int, int], int] | None = None,
) -> tuple[list[str], list[int], list[list[object]]]:
    x_values: list[str] = []
    y_values: list[int] = []
    customdata: list[list[object]] = []
    for row in rows:
        key = (row.block_start_seconds, row.block_end_seconds)
        value = int(a_counts[key] if value_name == "a_trip_count" else getattr(row, value_name))
        hover = _hover_customdata(
            row,
            base_by_interval[key],
            result_b,
            None if a_counts is None else a_counts[key],
        )
        x_values.append(_block_category(row))
        y_values.append(value)
        customdata.append(hover)
    return x_values, y_values, customdata


def _add_supply_lines(
    figure: go.Figure,
    base_rows: list[BlockSupplyComparison],
    supply_rows: list[BlockSupplyComparison],
    result_b: ScenarioResult,
    origin: int,
    direction: Direction,
    result_a: ScenarioResult | None = None,
) -> None:
    base_by_interval = _rows_by_interval(base_rows)
    a_counts = (
        _trip_counts_by_interval(supply_rows, result_a, origin)
        if result_a is not None and result_a.trips
        else None
    )
    specifications = [
        (
            "minimum_trips_90",
            "Số chuyến tối thiểu tại LF 90%",
            "#94A3B8",
            "dot",
            "triangle-up-open",
            2.2,
            50,
        ),
        (
            "required_trips_85",
            "Số chuyến cần thiết tại LF 85%",
            "#334155",
            "dash",
            "square-open",
            2.0,
            40,
        ),
    ]
    if a_counts is not None:
        specifications.append(
            (
                "a_trip_count",
                "A — Số chuyến hiện tại",
                SCENARIO_COLORS["A"],
                "dot",
                "x",
                2.1,
                10,
            )
        )
    specifications.extend(
        [
            (
                "c_trip_count",
                "C — Số chuyến tái phân bổ",
                SCENARIO_COLORS["C"],
                "solid",
                "diamond",
                3.2,
                30,
            ),
            (
                "b_trip_count",
                "B — Số chuyến thực tế",
                SCENARIO_COLORS["B"],
                "dash",
                "circle-open",
                1.9,
                20,
            ),
        ]
    )
    for metric, label, color, dash, marker_symbol, width, legendrank in specifications:
        x_values, y_values, customdata = _line_values(
            supply_rows, metric, base_by_interval, result_b, a_counts
        )
        figure.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines+markers",
                name=label,
                legendgroup=f"supply-{metric}",
                legendrank=legendrank,
                line={"color": color, "width": width, "dash": dash, "shape": "linear"},
                marker={
                    "symbol": marker_symbol,
                    "size": 8,
                    "color": color,
                    "line": {"color": color, "width": 1.2},
                },
                connectgaps=False,
                meta={
                    "trace_type": "supply_line",
                    "metric": metric,
                    "panel": 1,
                    "supply_view": direction.value,
                },
                customdata=customdata,
                hovertemplate=(
                    SUPPLY_HOVER_TEMPLATE if a_counts is not None else SUPPLY_HOVER_TEMPLATE_NO_A
                ),
            ),
            row=1,
            col=1,
            secondary_y=True,
        )


def _add_supply_warning_annotations(
    figure: go.Figure,
    rows: list[BlockSupplyComparison],
) -> None:
    material = [
        row
        for row in rows
        if row.b_status
        in {
            SupplyPresentationStatus.CRITICAL,
            SupplyPresentationStatus.NO_SERVICE_WITH_DEMAND,
        }
    ]
    material.sort(key=lambda row: (row.b_trip_gap_to_85, row.block_start_seconds))
    for row in material[:3]:
        b_shortage = max(0, -row.b_trip_gap_to_85)
        c_shortage = max(0, -row.c_trip_gap_to_85)
        c_text = "C đạt mục tiêu" if c_shortage == 0 else f"C còn thiếu {c_shortage} chuyến"
        figure.add_annotation(
            x=_block_category(row),
            y=max(
                row.b_trip_count,
                row.c_trip_count,
                row.required_trips_85,
                row.minimum_trips_90,
            )
            + 0.35,
            xref="x",
            yref="y2",
            text=f"B thiếu {b_shortage} chuyến<br>{c_text}",
            showarrow=False,
            bgcolor="rgba(255,255,255,0.92)",
            bordercolor="#F59E0B",
            borderwidth=1,
            font={"size": 10, "color": "#7C2D12"},
        )


def _add_trip_traces(
    figure: go.Figure,
    bundle: AnalysisBundle,
    origin: int,
    recommended_scenario: str | None,
    *,
    row: int = 1,
) -> None:
    symbols = {
        Direction.TERMINAL_1_TO_2: "triangle-right",
        Direction.TERMINAL_2_TO_1: "triangle-left",
    }
    for result in bundle.scenarios:
        vehicle_by_trip = {
            assignment.trip_id: assignment.vehicle_id for assignment in result.fleet.assignments
        }
        trace_by_trip = {trace.c_trip_id: trace for trace in result.trip_traces}
        regime_by_id = {regime.regime_id: regime for regime in result.headway_regimes}
        for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
            selected = sorted(
                (trip for trip in result.trips if trip.direction == direction),
                key=lambda trip: (_project_seconds(trip.departure_seconds, origin), trip.trip_id),
            )
            if not selected:
                continue
            projected = [_project_seconds(trip.departure_seconds, origin) for trip in selected]
            customdata = []
            for index, trip in enumerate(selected):
                block = _matching_block(result, trip, origin)
                headway = None if index == 0 else (projected[index] - projected[index - 1]) / 60
                position = (
                    "Chuyến đầu"
                    if index == 0
                    else "Chuyến cuối"
                    if index == len(selected) - 1
                    else ""
                )
                capacity = trip.vehicle_capacity_override or result.parameters.capacity
                trace = trace_by_trip.get(trip.trip_id)
                regime = regime_by_id.get(trace.headway_regime_id) if trace else None
                customdata.append(
                    [
                        result.name,
                        trip.trip_id,
                        trip.departure_terminal,
                        _direction_label(result, trip.direction),
                        _clock_hhmm(trip.departure_seconds),
                        _clock_hhmm(
                            trip.resolved_arrival_seconds(
                                result.parameters.default_trip_runtime_minutes
                            )
                        ),
                        _format_number(headway, " phút"),
                        trip.vehicle_id or vehicle_by_trip.get(trip.trip_id) or "—",
                        capacity,
                        _format_number(None if block is None else block.demand),
                        _format_number(
                            None
                            if block is None or block.load_factor is None
                            else block.load_factor * 100,
                            "%",
                        ),
                        position,
                        trace.source_b_trip_id if trace else "—",
                        _clock_hhmm(trace.b_departure_seconds) if trace else "—",
                        _format_number(trace.shift_minutes, " phút") if trace else "—",
                        trace.headway_regime_id if trace else "—",
                        trace.headway_type.value if trace else "—",
                        _format_number(regime.target_headway_minutes if regime else None, " phút"),
                        trace.new_demand_interval if trace else "—",
                        trace.change_reason if trace else "—",
                    ]
                )
            marker_symbols = []
            marker_line_colors = []
            for trip in selected:
                trace = trace_by_trip.get(trip.trip_id)
                if trace and trace.shift_minutes != 0:
                    marker_symbols.append("diamond")
                else:
                    marker_symbols.append(symbols[direction])
                if trace and trace.headway_type == HeadwayType.EXCEPTIONAL:
                    marker_line_colors.append("#DC2626")
                elif trace and trace.headway_type == HeadwayType.TRANSITION:
                    marker_line_colors.append("#7C3AED")
                else:
                    marker_line_colors.append("#FFFFFF")
            figure.add_trace(
                go.Scatter(
                    x=[value / 60 for value in projected],
                    y=[_lane(result, trip, recommended_scenario) for trip in selected],
                    mode="markers",
                    name=f"{result.name}{' ★' if result.name == recommended_scenario else ''}",
                    legendgroup=result.name,
                    showlegend=direction == Direction.TERMINAL_1_TO_2,
                    marker={
                        "size": [
                            14 if index in {0, len(selected) - 1} else 10
                            for index in range(len(selected))
                        ],
                        "symbol": marker_symbols,
                        "color": SCENARIO_COLORS.get(result.name, "#334155"),
                        "line": {"color": marker_line_colors, "width": 1.8},
                    },
                    meta={
                        "trace_type": "trip",
                        "scenario": result.name,
                        "direction": direction.value,
                    },
                    customdata=customdata,
                    hovertemplate=(
                        "Phương án: %{customdata[0]}<br>"
                        "Chuyến: %{customdata[1]} %{customdata[11]}<br>"
                        "Bến xuất phát: %{customdata[2]}<br>"
                        "Chiều: %{customdata[3]}<br>"
                        "Giờ xuất bến: %{customdata[4]}<br>"
                        "Giờ đến: %{customdata[5]}<br>"
                        "Headway với chuyến trước: %{customdata[6]}<br>"
                        "Xe: %{customdata[7]}<br>"
                        "Sức chứa xe: %{customdata[8]}<br>"
                        "Nhu cầu block: %{customdata[9]}<br>"
                        "Load factor: %{customdata[10]}<br>"
                        "Chuyến nguồn B: %{customdata[12]}<br>"
                        "Giờ B / C: %{customdata[13]} / %{customdata[4]}<br>"
                        "Dịch chuyển: %{customdata[14]}<br>"
                        "Regime: %{customdata[15]} · %{customdata[16]}<br>"
                        "Headway mục tiêu: %{customdata[17]}<br>"
                        "Khung nhu cầu: %{customdata[18]}<br>"
                        "Lý do: %{customdata[19]}<extra></extra>"
                    ),
                ),
                row=row,
                col=1,
            )


def _supply_status(result: ScenarioResult, block: BlockEvaluation) -> str | None:
    if block.demand > 0 and block.trips == 0:
        return "no_service"
    if block.load_factor is None:
        return None
    if block.load_factor > result.parameters.maximum_load_factor:
        return "critical"
    if block.load_factor > result.parameters.target_load_factor:
        return "warning"
    if block.trip_gap_to_target > 0:
        return "surplus"
    return None


def _status_lanes(
    result: ScenarioResult,
    block: BlockEvaluation,
    recommended_scenario: str | None,
) -> list[str]:
    if block.direction == Direction.COMBINED:
        return [
            _lane_for_direction(result, Direction.TERMINAL_1_TO_2, recommended_scenario),
            _lane_for_direction(result, Direction.TERMINAL_2_TO_1, recommended_scenario),
        ]
    return [_lane_for_direction(result, block.direction, recommended_scenario)]


def _add_supply_status_traces(
    figure: go.Figure,
    bundle: AnalysisBundle,
    origin: int,
    recommended_scenario: str | None,
    *,
    row: int = 1,
) -> None:
    grouped: dict[str, dict[str, list]] = {
        status: {"x": [], "y": [], "customdata": []} for status in SUPPLY_STATUS_STYLES
    }
    for result in bundle.scenarios:
        for block in result.evaluation.blocks:
            status = _supply_status(result, block)
            if status is None:
                continue
            start, end = _project_interval(
                block.block_start_seconds, block.block_end_seconds, origin
            )
            load_factor = _format_number(
                None if block.load_factor is None else block.load_factor * 100, "%"
            )
            direction_note = _direction_label_for_demand(block.direction)
            if block.direction == Direction.COMBINED:
                direction_note += " — không kết luận riêng chiều"
            status_label = SUPPLY_STATUS_STYLES[status][0]
            customdata = [
                result.name,
                _clock_hhmm(block.block_start_seconds),
                _clock_hhmm(block.block_end_seconds),
                direction_note,
                status_label,
                _format_number(block.demand),
                block.trips,
                block.required_trips,
                block.trip_gap_to_target,
                _format_number(block.nominal_capacity),
                _format_number(block.target_capacity),
                load_factor,
            ]
            for lane in _status_lanes(result, block, recommended_scenario):
                grouped[status]["x"].extend([start / 60, end / 60, None])
                grouped[status]["y"].extend([lane, lane, None])
                grouped[status]["customdata"].extend([customdata, customdata, customdata])

    for status, (label, color, dash) in SUPPLY_STATUS_STYLES.items():
        values = grouped[status]
        if not values["x"]:
            continue
        figure.add_trace(
            go.Scatter(
                x=values["x"],
                y=values["y"],
                mode="lines",
                name=label,
                legendgroup="supply-status",
                line={"color": color, "width": 16, "dash": dash},
                opacity=0.23 if status != "no_service" else 0.34,
                connectgaps=False,
                meta={"trace_type": "supply_status", "status": status, "panel": 2},
                customdata=values["customdata"],
                hovertemplate=(
                    "Phương án: %{customdata[0]}<br>"
                    "Block: %{customdata[1]}–%{customdata[2]}<br>"
                    "Phạm vi: %{customdata[3]}<br>"
                    "Trạng thái cung ứng: %{customdata[4]}<br>"
                    "Nhu cầu: %{customdata[5]}<br>"
                    "Số chuyến / cần tại 85%: %{customdata[6]} / %{customdata[7]}<br>"
                    "Chênh lệch chuyến: %{customdata[8]:+d}<br>"
                    "Sức chứa danh nghĩa: %{customdata[9]}<br>"
                    "Sức chứa tại 85%: %{customdata[10]}<br>"
                    "Load factor: %{customdata[11]}<extra></extra>"
                ),
            ),
            row=row,
            col=1,
        )


def _add_time_guides(
    figure: go.Figure, source_blocks: list[tuple[float, float, BlockEvaluation]]
) -> None:
    boundaries = sorted({value for start, end, _ in source_blocks for value in (start, end)})
    for boundary in boundaries:
        figure.add_vline(
            x=boundary / 60,
            line={"color": "#CBD5E1", "width": 0.7, "dash": "dot"},
            layer="below",
            row=1,
            col=1,
        )
    if source_blocks:
        final_start, final_end, _ = max(source_blocks, key=lambda item: item[1])
        figure.add_annotation(
            x=(final_start + final_end) / 120,
            y=1.0,
            xref="x",
            yref="paper",
            text="Block dịch vụ cuối",
            showarrow=False,
            yanchor="bottom",
            font={"color": "#475569", "size": 11},
        )


def _add_c_regime_boundaries(
    figure: go.Figure,
    bundle: AnalysisBundle,
    origin: int,
    *,
    row: int = 1,
) -> None:
    result = bundle.get("C")
    if result is None:
        return
    for direction in (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1):
        regimes = sorted(
            (regime for regime in result.headway_regimes if regime.direction == direction),
            key=lambda regime: regime.start_seconds,
        )
        for previous, current in zip(regimes, regimes[1:], strict=False):
            if abs(current.target_headway_minutes - previous.target_headway_minutes) < 0.01:
                continue
            projected = _project_seconds(current.start_seconds, origin) / 60
            figure.add_vline(
                x=projected,
                line={"color": "#0F766E", "width": 1.4, "dash": "dash"},
                layer="above",
                row=row,
                col=1,
            )
            figure.add_annotation(
                x=projected,
                y=_lane_for_direction(result, direction, _recommended_scenario(bundle)),
                text=f"{current.regime_id}: {current.target_headway_minutes:.1f}′",
                showarrow=False,
                xanchor="left",
                yshift=11,
                font={"size": 9, "color": "#0F766E"},
                row=row,
                col=1,
            )


def _shortage_count(result: ScenarioResult) -> int:
    return sum(
        block.demand > 0
        and (
            block.trips == 0
            or (
                block.load_factor is not None
                and block.load_factor > result.parameters.target_load_factor
            )
        )
        for block in result.evaluation.blocks
    )


def _recommendation_summary(bundle: AnalysisBundle, recommended_scenario: str | None) -> str:
    if recommended_scenario is None:
        return ""
    recommended = bundle.get(recommended_scenario)
    if recommended is None:
        return ""
    summary = (
        f"★ {recommended.name} ưu tiên: {_shortage_count(recommended)} block thiếu/quá tải"
        f" · {len(recommended.trips)} chuyến · {recommended.fleet.minimum_vehicles} xe"
    )
    alternatives = [
        result
        for result in bundle.scenarios
        if result.name.startswith("C") and result.name != recommended.name
    ]
    if alternatives:
        alternative = max(
            alternatives,
            key=lambda result: result.score if result.score is not None else float("-inf"),
        )
        summary += f"; {alternative.name}: {_shortage_count(alternative)} block thiếu/quá tải"
    return summary


def build_comparison_diagram(
    bundle: AnalysisBundle,
    supply_direction: Direction | str = Direction.COMBINED,
) -> go.Figure:
    recommended_scenario = _recommended_scenario(bundle)
    base_supply_rows = build_block_supply_comparison(bundle)
    effective_direction = _resolve_supply_direction(base_supply_rows, supply_direction)
    origin = _block_service_day_origin(base_supply_rows)
    supply_rows = sorted(
        aggregate_block_supply(base_supply_rows, effective_direction),
        key=lambda row: _project_interval(
            row.block_start_seconds, row.block_end_seconds, origin
        )[0],
    )
    figure = make_subplots(
        rows=1,
        cols=1,
        specs=[[{"secondary_y": True}]],
    )
    result_b = bundle.get("B")
    result_a = bundle.get("A")
    if base_supply_rows and supply_rows and result_b is not None:
        _add_quantitative_demand_traces(
            figure,
            base_supply_rows,
            supply_rows,
            result_b,
            origin,
            effective_direction,
            result_a,
        )
        _add_supply_lines(
            figure,
            base_supply_rows,
            supply_rows,
            result_b,
            origin,
            effective_direction,
            result_a,
        )
        _add_supply_warning_annotations(figure, supply_rows)
    else:
        figure.add_annotation(
            text="Cần kết quả B và C để dựng biểu đồ cung ứng theo block.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )

    block_categories = [_block_category(row) for row in supply_rows]
    recommendation_summary = _recommendation_summary(bundle, recommended_scenario)
    title_text = "Nhu cầu và số chuyến xuất bến theo block"
    if recommendation_summary:
        title_text += f"<br><sup>{recommendation_summary}</sup>"
    figure.update_layout(
        title={
            "text": title_text,
            "x": 0.01,
            "xanchor": "left",
        },
        template="plotly_white",
        height=720,
        margin={"l": 90, "r": 115, "t": 125, "b": 165},
        hovermode="closest",
        dragmode="pan",
        barmode="stack",
        bargap=0.18,
        legend={
            "orientation": "h",
            "y": -0.23,
            "x": 0,
            "groupclick": "togglegroup",
            "traceorder": "grouped",
        },
        xaxis={
            "title": "Khung phân tích nhu cầu",
            "type": "category",
            "categoryorder": "array",
            "categoryarray": block_categories,
            "tickangle": -35,
            "showgrid": True,
            "gridcolor": "#F1F5F9",
            "fixedrange": False,
        },
        yaxis={
            "title": "Hành khách / block",
            "type": "linear",
            "rangemode": "tozero",
            "showgrid": True,
            "gridcolor": "#E2E8F0",
            "fixedrange": False,
        },
        yaxis2={
            "title": "Chuyến xuất bến / block",
            "type": "linear",
            "rangemode": "tozero",
            "side": "right",
            "showgrid": False,
            "fixedrange": False,
        },
        meta={
            "time_axis": "x_categories",
            "panels": ["demand_supply"],
            "overview_chart": "excel_style_combination",
            "scenario_a_visible": bool(result_a is not None and result_a.trips),
            "supply_view": effective_direction.value,
            "directional_demand_confirmed": any(
                row.direction != Direction.COMBINED for row in base_supply_rows
            ),
            "recommended_scenario": recommended_scenario,
            "service_day_origin_seconds": origin,
            "c_timetable_fingerprint": (
                bundle.get("C").timetable_fingerprint if bundle.get("C") else ""
            ),
        },
    )
    return figure


def build_departure_detail_diagram(bundle: AnalysisBundle) -> go.Figure:
    """Build the continuous-time diagnostic view with one marker per departure."""
    recommended_scenario = _recommended_scenario(bundle)
    lanes = _lanes(bundle, recommended_scenario)
    origin = _service_day_origin(bundle)
    source = bundle.get("B") or bundle.scenarios[0]
    source_blocks = sorted(
        (
            (*_project_interval(block.block_start_seconds, block.block_end_seconds, origin), block)
            for block in source.evaluation.blocks
        ),
        key=lambda item: (item[0], item[1], item[2].direction.value),
    )
    time_regions = _unique_blocks(source.evaluation.blocks, origin)
    figure = make_subplots(rows=1, cols=1)
    _add_supply_status_traces(
        figure,
        bundle,
        origin,
        recommended_scenario,
        row=1,
    )
    _add_trip_traces(
        figure,
        bundle,
        origin,
        recommended_scenario,
        row=1,
    )
    _add_time_guides(figure, time_regions)
    _add_c_regime_boundaries(figure, bundle, origin, row=1)

    timeline_values = [
        value for start, end, _ in source_blocks for value in (start / 60, end / 60)
    ] + [
        _project_seconds(trip.departure_seconds, origin) / 60
        for result in bundle.scenarios
        for trip in result.trips
    ]
    minimum = math.floor(min(timeline_values, default=360) / 60) * 60
    maximum = math.ceil(max(timeline_values, default=1080) / 60) * 60
    if maximum <= minimum:
        maximum = minimum + 60
    ticks = list(range(minimum, maximum + 1, 60))
    figure.update_layout(
        title={
            "text": "Chi tiết giờ xuất bến",
            "x": 0.01,
            "xanchor": "left",
        },
        template="plotly_white",
        height=max(620, 72 * len(lanes) + 220),
        margin={"l": 215, "r": 70, "t": 90, "b": 135},
        hovermode="closest",
        dragmode="zoom",
        legend={
            "orientation": "h",
            "y": -0.16,
            "x": 0,
            "groupclick": "togglegroup",
            "traceorder": "grouped",
        },
        xaxis={
            "title": "Thời gian trong ngày",
            "type": "linear",
            "tickmode": "array",
            "tickvals": ticks,
            "ticktext": [_clock_hhmm(tick * 60) for tick in ticks],
            "range": [minimum - 10, maximum + 10],
            "showgrid": True,
            "gridcolor": "#E2E8F0",
            "fixedrange": False,
        },
        yaxis={
            "title": "Phương án và bến xuất phát",
            "type": "category",
            "categoryorder": "array",
            "categoryarray": lanes,
            "autorange": "reversed",
            "showgrid": True,
            "gridcolor": "#F1F5F9",
            "fixedrange": False,
        },
        meta={
            "time_axis": "x",
            "lane_axis": "y",
            "panels": ["schedule_supply"],
            "detail_chart": "exact_departures",
            "recommended_scenario": recommended_scenario,
            "service_day_origin_seconds": origin,
            "c_timetable_fingerprint": (
                bundle.get("C").timetable_fingerprint if bundle.get("C") else ""
            ),
        },
    )
    return figure


def export_diagram(
    figure: go.Figure, output_dir: str | Path, stem: str = "Bus_Schedule_Comparison"
) -> tuple[Path, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    html_path = directory / f"{stem}.html"
    png_path = directory / f"{stem}.png"
    figure.write_html(html_path, include_plotlyjs=True, full_html=True)
    png_path.write_bytes(diagram_png_bytes(figure))
    return png_path, html_path
