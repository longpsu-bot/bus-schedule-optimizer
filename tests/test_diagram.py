from __future__ import annotations

from dataclasses import replace

import pytest

from bus_schedule_engine.diagram import (
    SUPPLY_HOVER_TEMPLATE,
    build_comparison_diagram,
    build_departure_detail_diagram,
    export_diagram,
)
from bus_schedule_engine.models import (
    AnalysisBundle,
    BlockEvaluation,
    Direction,
    EvaluationStatus,
    FleetResult,
    GenerationReport,
    HeadwayStats,
    RouteType,
    ScenarioCStatus,
    ScenarioEvaluation,
    ScenarioParameters,
    ScenarioResult,
    Trip,
    ValidationReport,
)


def _parameters(first: int = 6 * 3600, last: int = 8 * 3600) -> ScenarioParameters:
    return ScenarioParameters(
        route_id="T-AXIS",
        route_name="Tuyến kiểm tra trục",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=30,
        total_daily_trips=4,
        terminal_1_name="Bến Đông",
        terminal_1_first_departure=first,
        terminal_1_last_departure=last,
        terminal_2_name="Bến Tây",
        terminal_2_first_departure=first,
        terminal_2_last_departure=last,
        vehicle_capacity_passengers=60,
        target_load_factor=0.85,
        maximum_load_factor=0.90,
        time_block_minutes=60,
        minimum_layover_minutes=5,
    )


def _block(
    scenario: str,
    start: int,
    end: int,
    trips: int,
    *,
    demand: float = 100,
    direction: Direction = Direction.COMBINED,
) -> BlockEvaluation:
    headway = HeadwayStats(
        count=max(0, trips - 1),
        mean_minutes=5 if trips > 1 else None,
        minimum_minutes=5 if trips > 1 else None,
        maximum_minutes=5 if trips > 1 else None,
        standard_deviation_minutes=0 if trips > 1 else None,
        coefficient_of_variation=0 if trips > 1 else None,
    )
    nominal_capacity = trips * 60
    required = 2 if demand > 0 else 0
    return BlockEvaluation(
        scenario=scenario,
        block_start_seconds=start,
        block_end_seconds=end,
        direction=direction,
        trips=trips,
        nominal_capacity=nominal_capacity,
        target_capacity=nominal_capacity * 0.85,
        maximum_recommended_capacity=nominal_capacity * 0.90,
        demand=demand,
        load_factor=None if trips == 0 else demand / nominal_capacity,
        required_trips=required,
        trip_gap_to_target=trips - required,
        status=(
            EvaluationStatus.NO_SERVICE_WITH_DEMAND
            if trips == 0 and demand > 0
            else EvaluationStatus.SUITABLE
        ),
        headway=headway,
        data_note="Nhu cầu tổng hợp hai chiều — ước tính",
    )


def _trip(
    scenario: str,
    trip_id: str,
    terminal: str,
    direction: Direction,
    departure: int,
) -> Trip:
    return Trip(
        scenario=scenario,
        trip_id=trip_id,
        departure_terminal=terminal,
        direction=direction,
        departure_seconds=departure,
        arrival_seconds=departure + 30 * 60,
        vehicle_id=f"XE-{trip_id}",
    )


def _result(name: str, trips: list[Trip], blocks: list[BlockEvaluation]) -> ScenarioResult:
    parameters = _parameters(
        first=min(trip.departure_seconds for trip in trips),
        last=max(trip.departure_seconds for trip in trips),
    )
    headway = blocks[0].headway
    evaluation = ScenarioEvaluation(
        scenario=name,
        blocks=blocks,
        overall_status=EvaluationStatus.SUITABLE,
        technical_status=EvaluationStatus.SUITABLE,
        demand_status=EvaluationStatus.SUITABLE,
        maximum_load_factor=max(
            (block.load_factor for block in blocks if block.load_factor is not None),
            default=None,
        ),
        blocks_over_target=0,
        blocks_over_maximum=0,
        headway=headway,
        early_coverage_gap_minutes=0,
        late_coverage_gap_minutes=0,
    )
    return ScenarioResult(
        name=name,
        parameters=parameters,
        trips=trips,
        validation=ValidationReport(),
        evaluation=evaluation,
        fleet=FleetResult(minimum_vehicles=0, assignments=[], vehicle_summaries=[]),
        score=100,
        generation_status=(ScenarioCStatus.SUITABLE_REGULAR if name == "C" else None),
    )


def _standard_bundle() -> AnalysisBundle:
    east = "Bến Đông"
    west = "Bến Tây"
    b_trips = [
        _trip("B", "B1", east, Direction.TERMINAL_1_TO_2, 6 * 3600 + 20 * 60),
        _trip("B", "B2", west, Direction.TERMINAL_2_TO_1, 7 * 3600 + 20 * 60),
    ]
    c_trips = [
        _trip("C", "C1", west, Direction.TERMINAL_2_TO_1, 6 * 3600 + 25 * 60),
        _trip("C", "C2", east, Direction.TERMINAL_1_TO_2, 7 * 3600 + 10 * 60),
    ]
    b_blocks = [
        _block("B", 6 * 3600, 7 * 3600, 1, demand=80),
        _block("B", 7 * 3600, 8 * 3600, 1, demand=140),
    ]
    c_blocks = [
        _block("C", 6 * 3600, 7 * 3600, 1, demand=80),
        _block("C", 7 * 3600, 8 * 3600, 1, demand=140),
    ]
    return AnalysisBundle(
        scenarios=[_result("B", b_trips, b_blocks), _result("C", c_trips, c_blocks)],
        generation=GenerationReport(feasible=True),
        limitations=[],
    )


def _traces(figure, trace_type: str):
    return [
        trace for trace in figure.data if trace.meta and trace.meta["trace_type"] == trace_type
    ]


def test_overview_is_excel_style_combo_with_chronological_block_categories() -> None:
    figure = build_comparison_diagram(_standard_bundle())
    demand = _traces(figure, "demand")
    supply = _traces(figure, "supply_line")

    assert figure.layout.meta["overview_chart"] == "excel_style_combination"
    assert figure.layout.xaxis.type == "category"
    assert list(figure.layout.xaxis.categoryarray) == ["06:00–07:00", "07:00–08:00"]
    assert figure.layout.yaxis.title.text == "Hành khách / block"
    assert figure.layout.yaxis2.title.text == "Chuyến xuất bến / block"
    assert all(trace.type == "bar" and trace.yaxis == "y" for trace in demand)
    assert all(trace.type == "scatter" and trace.yaxis == "y2" for trace in supply)
    assert all(trace.mode == "lines+markers" for trace in supply)
    assert all(trace.line.shape == "linear" for trace in supply)
    assert {trace.meta["metric"] for trace in supply} == {
        "b_trip_count",
        "c_trip_count",
        "required_trips_85",
        "minimum_trips_90",
    }
    assert not _traces(figure, "trip")


def test_overview_hover_contains_required_block_context() -> None:
    figure = build_comparison_diagram(_standard_bundle())
    demand = _traces(figure, "demand")[0]

    assert len(demand.customdata[0]) == 22
    assert "A — số chuyến hiện tại" not in demand.hovertemplate
    for label in (
        "Tổng nhu cầu",
        "Sức chứa phương tiện",
        "B — số chuyến",
        "C — số chuyến",
        "Số chuyến cần tại 85%",
        "Số chuyến tối thiểu tại 90%",
        "Trạng thái B",
        "Trạng thái C",
        "Tin cậy nhu cầu",
    ):
        assert label in SUPPLY_HOVER_TEMPLATE


def test_scenario_a_line_is_added_and_extends_grid_when_current_data_exists() -> None:
    bundle = _standard_bundle()
    east = "Bến Đông"
    west = "Bến Tây"
    a_trips = [
        _trip("A", "A1", east, Direction.TERMINAL_1_TO_2, 5 * 3600 + 30 * 60),
        _trip("A", "A2", west, Direction.TERMINAL_2_TO_1, 6 * 3600 + 30 * 60),
        _trip("A", "A3", east, Direction.TERMINAL_1_TO_2, 7 * 3600 + 30 * 60),
    ]
    bundle.scenarios.insert(
        0,
        _result(
            "A",
            a_trips,
            [
                _block("A", 5 * 3600, 6 * 3600, 1, demand=0),
                _block("A", 6 * 3600, 7 * 3600, 1, demand=0),
                _block("A", 7 * 3600, 8 * 3600, 1, demand=0),
            ],
        ),
    )

    figure = build_comparison_diagram(bundle)
    a_line = next(
        trace
        for trace in _traces(figure, "supply_line")
        if trace.meta["metric"] == "a_trip_count"
    )

    assert figure.layout.meta["scenario_a_visible"] is True
    assert figure.layout.xaxis.categoryarray[0] == "05:00–06:00"
    assert a_line.name == "A — Số chuyến hiện tại"
    assert sum(a_line.y) == len(a_trips)
    assert "A — số chuyến hiện tại" in a_line.hovertemplate


def test_scenario_a_line_is_not_created_when_a_has_no_departures() -> None:
    bundle = _standard_bundle()
    empty_a = _result(
        "A",
        [_trip("A", "A1", "Bến Đông", Direction.TERMINAL_1_TO_2, 6 * 3600)],
        [_block("A", 6 * 3600, 7 * 3600, 1)],
    )
    empty_a.trips = []
    bundle.scenarios.insert(0, empty_a)

    figure = build_comparison_diagram(bundle)

    assert figure.layout.meta["scenario_a_visible"] is False
    assert not any(
        trace.meta["metric"] == "a_trip_count" for trace in _traces(figure, "supply_line")
    )
    assert all("A — số chuyến hiện tại" not in trace.hovertemplate for trace in figure.data)


def test_exact_departures_are_available_only_in_separate_detail_figure() -> None:
    bundle = _standard_bundle()
    overview = build_comparison_diagram(bundle)
    detail = build_departure_detail_diagram(bundle)
    trip_traces = _traces(detail, "trip")

    assert not _traces(overview, "trip")
    assert detail.layout.meta["detail_chart"] == "exact_departures"
    assert detail.layout.xaxis.type == "linear"
    assert detail.layout.yaxis.type == "category"
    assert sum(len(trace.x) for trace in trip_traces) == 4
    assert all(isinstance(value, (int, float)) for trace in trip_traces for value in trace.x)
    assert all(isinstance(value, str) for trace in trip_traces for value in trace.y)


@pytest.mark.parametrize(
    ("expected_status", "load_factor", "trips", "trip_gap"),
    [
        ("no_service", None, 0, -2),
        ("critical", 0.95, 1, -1),
        ("warning", 0.88, 1, -1),
        ("surplus", 0.50, 3, 1),
    ],
)
def test_detail_supply_status_is_drawn_only_in_its_scenario_lane(
    expected_status: str, load_factor: float | None, trips: int, trip_gap: int
) -> None:
    bundle = _standard_bundle()
    bundle.scenarios = [bundle.get("B")]
    block = bundle.scenarios[0].evaluation.blocks[0]
    bundle.scenarios[0].evaluation.blocks = [
        replace(
            block,
            direction=Direction.TERMINAL_1_TO_2,
            load_factor=load_factor,
            trips=trips,
            trip_gap_to_target=trip_gap,
        )
    ]
    figure = build_departure_detail_diagram(bundle)
    status_trace = next(
        trace
        for trace in _traces(figure, "supply_status")
        if trace.meta["status"] == expected_status
    )

    assert all(
        lane == "B — Biểu đồ giờ đề xuất · Bến Đông → Bến Tây"
        for lane in status_trace.y
        if lane is not None
    )


def test_cross_midnight_departures_remain_left_to_right_in_detail() -> None:
    east = "Bến Đông"
    trips = [
        _trip("B", "N1", east, Direction.TERMINAL_1_TO_2, 23 * 3600 + 30 * 60),
        _trip("B", "N2", east, Direction.TERMINAL_1_TO_2, 10 * 60),
        _trip("B", "N3", east, Direction.TERMINAL_1_TO_2, 45 * 60),
    ]
    blocks = [_block("B", 23 * 3600, 3600, 3)]
    bundle = AnalysisBundle(
        scenarios=[_result("B", trips, blocks)],
        generation=GenerationReport(feasible=True),
        limitations=[],
    )
    trace = _traces(build_departure_detail_diagram(bundle), "trip")[0]

    assert list(trace.x) == [1410, 1450, 1485]
    assert [row[4] for row in trace.customdata] == ["23:30", "00:10", "00:45"]


def test_png_and_html_exports_preserve_combo_chart_identity(tmp_path) -> None:
    figure = build_comparison_diagram(_standard_bundle())
    png_path, html_path = export_diagram(figure, tmp_path, stem="combo-check")

    assert png_path.read_bytes().startswith(b"\x89PNG")
    html = html_path.read_text(encoding="utf-8")
    assert '"overview_chart":"excel_style_combination"' in html
    assert '"panels":["demand_supply"]' in html
    assert '"trace_type":"trip"' not in html
