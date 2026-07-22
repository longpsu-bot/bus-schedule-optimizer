from __future__ import annotations

from datetime import date

import pytest

from bus_schedule_engine.block_supply import (
    SupplyPresentationStatus,
    aggregate_block_supply,
    build_block_supply_comparison,
)
from bus_schedule_engine.demand import evaluate_scenario
from bus_schedule_engine.diagram import (
    build_comparison_diagram,
    build_departure_detail_diagram,
)
from bus_schedule_engine.models import (
    AnalysisBundle,
    DemandRecord,
    Direction,
    FleetResult,
    GenerationReport,
    RouteType,
    ScenarioCStatus,
    ScenarioParameters,
    ScenarioResult,
    Trip,
    ValidationReport,
    VolumeType,
)


def _parameters() -> ScenarioParameters:
    return ScenarioParameters(
        route_id="T-SUPPLY",
        route_name="Tuyến kiểm tra cung ứng",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=30,
        total_daily_trips=8,
        terminal_1_name="Bến Đông",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=8 * 3600,
        terminal_2_name="Bến Tây",
        terminal_2_first_departure=6 * 3600,
        terminal_2_last_departure=8 * 3600,
        vehicle_capacity_passengers=100,
        target_load_factor=0.85,
        maximum_load_factor=0.90,
        time_block_minutes=60,
        minimum_layover_minutes=5,
    )


def _demand() -> list[DemandRecord]:
    values = (
        (6 * 3600, 7 * 3600, Direction.TERMINAL_1_TO_2, 88),
        (6 * 3600, 7 * 3600, Direction.TERMINAL_2_TO_1, 91),
        (7 * 3600, 8 * 3600, Direction.TERMINAL_1_TO_2, 20),
        (7 * 3600, 8 * 3600, Direction.TERMINAL_2_TO_1, 20),
    )
    return [
        DemandRecord(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 1),
            observation_days=1,
            block_start_seconds=start,
            block_end_seconds=end,
            direction=direction,
            passenger_volume=passengers,
            volume_type=VolumeType.AVERAGE_DAY,
        )
        for start, end, direction, passengers in values
    ]


def _trip(scenario: str, sequence: int, direction: Direction, departure: int) -> Trip:
    parameters = _parameters()
    terminal = (
        parameters.terminal_1_name
        if direction == Direction.TERMINAL_1_TO_2
        else parameters.terminal_2_name
    )
    return Trip(
        scenario=scenario,
        trip_id=f"{scenario}-{sequence:02d}",
        departure_terminal=terminal,
        direction=direction,
        departure_seconds=departure,
        arrival_seconds=departure + parameters.trip_runtime_minutes * 60,
    )


def _result(
    name: str, trips: list[Trip], demand: list[DemandRecord] | None = None
) -> ScenarioResult:
    parameters = _parameters()
    evaluation = evaluate_scenario(
        name,
        trips,
        _demand() if demand is None else demand,
        parameters,
        ValidationReport(),
    )
    return ScenarioResult(
        name=name,
        parameters=parameters,
        trips=trips,
        validation=ValidationReport(),
        evaluation=evaluation,
        fleet=FleetResult(minimum_vehicles=2, assignments=[], vehicle_summaries=[]),
        score=90,
        active_vehicle_count=2,
        generation_status=ScenarioCStatus.SUITABLE_REGULAR if name == "C" else None,
    )


def _bundle() -> AnalysisBundle:
    b_trips = [
        _trip("B", 1, Direction.TERMINAL_1_TO_2, 6 * 3600 + 10 * 60),
        _trip("B", 2, Direction.TERMINAL_2_TO_1, 6 * 3600 + 15 * 60),
        _trip("B", 3, Direction.TERMINAL_1_TO_2, 7 * 3600),
        _trip("B", 4, Direction.TERMINAL_1_TO_2, 7 * 3600 + 30 * 60),
        _trip("B", 5, Direction.TERMINAL_2_TO_1, 7 * 3600 + 5 * 60),
        _trip("B", 6, Direction.TERMINAL_2_TO_1, 7 * 3600 + 35 * 60),
    ]
    c_trips = [
        _trip("C", 1, Direction.TERMINAL_1_TO_2, 6 * 3600 + 10 * 60),
        _trip("C", 2, Direction.TERMINAL_1_TO_2, 6 * 3600 + 40 * 60),
        _trip("C", 3, Direction.TERMINAL_2_TO_1, 6 * 3600 + 15 * 60),
        _trip("C", 4, Direction.TERMINAL_2_TO_1, 6 * 3600 + 45 * 60),
        _trip("C", 5, Direction.TERMINAL_1_TO_2, 7 * 3600),
        _trip("C", 6, Direction.TERMINAL_2_TO_1, 7 * 3600 + 5 * 60),
    ]
    return AnalysisBundle(
        scenarios=[_result("B", b_trips), _result("C", c_trips)],
        generation=GenerationReport(feasible=True),
        limitations=[],
    )


def test_supply_rows_reuse_authoritative_counts_requirements_and_statuses() -> None:
    rows = build_block_supply_comparison(_bundle())
    first_d1 = next(
        row
        for row in rows
        if row.block_start_seconds == 6 * 3600 and row.direction == Direction.TERMINAL_1_TO_2
    )
    first_d2 = next(
        row
        for row in rows
        if row.block_start_seconds == 6 * 3600 and row.direction == Direction.TERMINAL_2_TO_1
    )

    assert first_d1.b_trip_count == 1
    assert first_d1.c_trip_count == 2
    assert first_d1.required_trips_85 == 2
    assert first_d1.minimum_trips_90 == 1
    assert first_d1.b_status == SupplyPresentationStatus.WARNING
    assert first_d1.c_status == SupplyPresentationStatus.TARGET_MET

    assert first_d2.required_trips_85 == 2
    assert first_d2.minimum_trips_90 == 2
    assert first_d2.b_status == SupplyPresentationStatus.CRITICAL
    assert first_d2.c_status == SupplyPresentationStatus.TARGET_MET


def test_departure_on_shared_boundary_is_counted_exactly_once() -> None:
    rows = build_block_supply_comparison(_bundle())
    d1_rows = sorted(
        (row for row in rows if row.direction == Direction.TERMINAL_1_TO_2),
        key=lambda row: row.block_start_seconds,
    )
    assert [row.b_trip_count for row in d1_rows] == [1, 2]
    assert sum(row.b_trip_count for row in d1_rows) == 3


def test_final_boundary_departure_moves_to_one_extended_canonical_block() -> None:
    bundle = _bundle()
    bundle.scenarios[0] = _result(
        "B",
        bundle.get("B").trips
        + [_trip("B", 7, Direction.TERMINAL_1_TO_2, 8 * 3600)],
    )
    bundle.scenarios[1] = _result(
        "C",
        bundle.get("C").trips
        + [_trip("C", 7, Direction.TERMINAL_1_TO_2, 8 * 3600)],
    )

    rows = build_block_supply_comparison(bundle)
    combined = aggregate_block_supply(rows, Direction.COMBINED)
    final = next(row for row in combined if row.block_start_seconds == 8 * 3600)

    assert final.b_trip_count == 1
    assert final.c_trip_count == 1
    assert sum(row.b_trip_count for row in combined) == len(bundle.get("B").trips)
    assert sum(row.c_trip_count for row in combined) == len(bundle.get("C").trips)


def test_overlapping_source_intervals_are_regrouped_without_changing_total_demand() -> None:
    overlapping = [
        record
        for record in _demand()
        if record.direction == Direction.TERMINAL_1_TO_2
    ] + [
        DemandRecord(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 1),
            observation_days=1,
            block_start_seconds=start,
            block_end_seconds=end,
            direction=Direction.TERMINAL_2_TO_1,
            passenger_volume=passengers,
            volume_type=VolumeType.AVERAGE_DAY,
        )
        for start, end, passengers in (
            (6 * 3600 + 15 * 60, 7 * 3600 + 15 * 60, 91),
            (6 * 3600 + 45 * 60, 7 * 3600 + 45 * 60, 20),
        )
    ]
    source = _bundle()
    bundle = AnalysisBundle(
        scenarios=[
            _result("B", source.get("B").trips, overlapping),
            _result("C", source.get("C").trips, overlapping),
        ],
        generation=GenerationReport(feasible=True),
        limitations=[],
    )

    rows = build_block_supply_comparison(bundle)
    combined = aggregate_block_supply(rows, Direction.COMBINED)

    assert {row.block_end_seconds - row.block_start_seconds for row in rows} == {3600}
    assert sum(row.passenger_demand for row in rows) == pytest.approx(
        sum(record.average_daily_demand for record in overlapping)
    )
    assert sum(row.b_trip_count for row in combined) == len(bundle.get("B").trips)
    assert sum(row.c_trip_count for row in combined) == len(bundle.get("C").trips)


def test_combined_view_reconciles_both_directions() -> None:
    rows = build_block_supply_comparison(_bundle())
    combined = aggregate_block_supply(rows, Direction.COMBINED)
    first = combined[0]
    directional_first = [
        row for row in rows if row.block_start_seconds == first.block_start_seconds
    ]
    assert first.passenger_demand == sum(row.passenger_demand for row in directional_first)
    assert first.b_trip_count == sum(row.b_trip_count for row in directional_first)
    assert first.c_trip_count == sum(row.c_trip_count for row in directional_first)
    assert first.required_trips_85 == sum(row.required_trips_85 for row in directional_first)
    assert first.minimum_trips_90 == sum(row.minimum_trips_90 for row in directional_first)


def test_demand_with_no_departure_uses_authoritative_no_service_status() -> None:
    bundle = _bundle()
    result_b = bundle.get("B")
    shifted = [trip for trip in result_b.trips if trip.trip_id != "B-02"]
    shifted.append(_trip("B", 7, Direction.TERMINAL_2_TO_1, 7 * 3600 + 50 * 60))
    bundle.scenarios[0] = _result("B", shifted)

    first_d2 = next(
        row
        for row in build_block_supply_comparison(bundle)
        if row.block_start_seconds == 6 * 3600 and row.direction == Direction.TERMINAL_2_TO_1
    )
    assert first_d2.b_trip_count == 0
    assert first_d2.b_status == SupplyPresentationStatus.NO_SERVICE_WITH_DEMAND


def test_combo_chart_uses_columns_lines_separate_axes_and_reconciles_timetable() -> None:
    bundle = _bundle()
    figure = build_comparison_diagram(bundle)
    demand_traces = [
        trace for trace in figure.data if trace.meta and trace.meta["trace_type"] == "demand"
    ]
    supply_lines = {
        trace.meta["metric"]: trace
        for trace in figure.data
        if trace.meta and trace.meta["trace_type"] == "supply_line"
    }

    assert figure.layout.yaxis.title.text == "Hành khách / block"
    assert figure.layout.yaxis2.title.text == "Chuyến xuất bến / block"
    assert all(trace.yaxis == "y" for trace in demand_traces)
    assert all(trace.yaxis == "y2" for trace in supply_lines.values())
    assert all(trace.type == "bar" for trace in demand_traces)
    assert all(trace.type == "scatter" for trace in supply_lines.values())
    assert all(trace.mode == "lines+markers" for trace in supply_lines.values())
    assert all(trace.line.shape == "linear" for trace in supply_lines.values())
    first_bar = demand_traces[0]
    assert list(supply_lines["b_trip_count"].x) == list(first_bar.x)

    assert sum(supply_lines["b_trip_count"].y) == len(bundle.get("B").trips)
    assert sum(supply_lines["c_trip_count"].y) == len(bundle.get("C").trips)
    assert not any(
        trace.meta and trace.meta["trace_type"] == "trip" for trace in figure.data
    )

    detail = build_departure_detail_diagram(bundle)
    detail_trips = [
        trace for trace in detail.data if trace.meta and trace.meta["trace_type"] == "trip"
    ]
    assert sum(len(trace.x) for trace in detail_trips) == (
        len(bundle.get("B").trips) + len(bundle.get("C").trips)
    )


def test_directional_chart_uses_directional_demand_and_departures() -> None:
    bundle = _bundle()
    figure = build_comparison_diagram(bundle, Direction.TERMINAL_1_TO_2)
    demand_traces = [
        trace for trace in figure.data if trace.meta and trace.meta["trace_type"] == "demand"
    ]
    b_line = next(
        trace
        for trace in figure.data
        if trace.meta
        and trace.meta["trace_type"] == "supply_line"
        and trace.meta["metric"] == "b_trip_count"
    )
    expected = aggregate_block_supply(
        build_block_supply_comparison(bundle), Direction.TERMINAL_1_TO_2
    )

    assert figure.layout.meta["supply_view"] == Direction.TERMINAL_1_TO_2.value
    assert {trace.meta["direction"] for trace in demand_traces} == {Direction.TERMINAL_1_TO_2.value}
    assert list(b_line.y) == [row.b_trip_count for row in expected]


def test_combined_demand_is_labeled_as_estimated_not_confirmed_directional() -> None:
    combined_demand = [
        DemandRecord(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 1),
            observation_days=1,
            block_start_seconds=6 * 3600,
            block_end_seconds=7 * 3600,
            direction=Direction.COMBINED,
            passenger_volume=179,
            volume_type=VolumeType.AVERAGE_DAY,
        )
    ]
    b_trips = [
        _trip("B", 1, Direction.TERMINAL_1_TO_2, 6 * 3600 + 10 * 60),
        _trip("B", 2, Direction.TERMINAL_2_TO_1, 6 * 3600 + 20 * 60),
    ]
    c_trips = [
        _trip("C", 1, Direction.TERMINAL_1_TO_2, 6 * 3600 + 15 * 60),
        _trip("C", 2, Direction.TERMINAL_2_TO_1, 6 * 3600 + 25 * 60),
    ]
    bundle = AnalysisBundle(
        scenarios=[
            _result("B", b_trips, combined_demand),
            _result("C", c_trips, combined_demand),
        ],
        generation=GenerationReport(feasible=True),
        limitations=[],
    )
    figure = build_comparison_diagram(bundle, Direction.TERMINAL_1_TO_2)
    demand = next(
        trace for trace in figure.data if trace.meta and trace.meta["trace_type"] == "demand"
    )

    assert figure.layout.meta["supply_view"] == Direction.COMBINED.value
    assert figure.layout.meta["directional_demand_confirmed"] is False
    assert demand.name == "Nhu cầu tổng hợp hai chiều — ước tính"
