from __future__ import annotations

import json
from dataclasses import replace

import pytest
from presentation_support import (
    build_corpus_result_and_report,
    build_result_and_report,
)

import bus_schedule_engine.unified_presentation as unified_presentation
from bus_schedule_engine import diagram
from bus_schedule_engine.unified_diagram import (
    build_unified_demand_supply_figure_v1,
    build_unified_departure_figure_v1,
)
from bus_schedule_engine.unified_presentation import build_unified_presentation_v1


@pytest.fixture(scope="module")
def accepted_presentation():
    return build_unified_presentation_v1(*build_result_and_report())


@pytest.fixture(scope="module")
def alpha_presentation():
    return build_unified_presentation_v1(*build_corpus_result_and_report("corpus_alpha_80.json"))


def _trace(figure, name: str):
    return next(item for item in figure.data if item.name == name)


def _direction_display(presentation, direction: str) -> str:
    if direction == "outbound":
        return f"{presentation.terminal_1_name} → {presentation.terminal_2_name}"
    if direction == "inbound":
        return f"{presentation.terminal_2_name} → {presentation.terminal_1_name}"
    return "Tổng hợp hai chiều"


@pytest.mark.parametrize(
    "builder",
    (
        build_unified_demand_supply_figure_v1,
        build_unified_departure_figure_v1,
    ),
)
def test_chart_metadata_aligns_all_fingerprints_and_review_state(
    builder,
    accepted_presentation,
) -> None:
    figure = builder(accepted_presentation)
    meta = dict(figure.layout.meta)

    assert meta["presentation_mode"] == "VALIDATION_ONLY"
    assert meta["presentation_fingerprint"] == (accepted_presentation.presentation_fingerprint)
    assert meta["source_b_fingerprint"] == accepted_presentation.source_b_fingerprint
    assert meta["accepted_solution_fingerprint"] == (
        accepted_presentation.accepted_solution_fingerprint
    )
    assert meta["accepted_c_exists"] is True
    assert meta["scenario_c_authority"] == "CONTRACT_V1_INDEPENDENTLY_VALIDATED"
    assert meta["cutover_blocked"] == accepted_presentation.cutover_blocked
    assert meta["blocking_discrepancy_codes"] == list(
        accepted_presentation.blocking_discrepancy_codes
    )
    assert meta["expert_review_required_codes"] == list(
        accepted_presentation.expert_review_required_codes
    )
    assert meta["demand_grain"] == "EXACT_CONTRACT_BLOCKS_NO_AGGREGATION"


def test_overview_uses_exact_block_order_and_returned_counts(
    accepted_presentation,
) -> None:
    figure = build_unified_demand_supply_figure_v1(accepted_presentation)
    categories = list(figure.layout.xaxis.categoryarray)
    expected = [
        (
            f"{block.block_start_seconds // 3600:02d}:"
            f"{block.block_start_seconds % 3600 // 60:02d}–"
            f"{block.block_end_seconds // 3600:02d}:"
            f"{block.block_end_seconds % 3600 // 60:02d} · "
            f"{_direction_display(accepted_presentation, block.direction)} · "
            f"{block.block_id}"
        )
        for block in accepted_presentation.blocks
    ]
    assert categories == expected
    demand_trace = _trace(figure, "Nhu cầu hành khách")
    assert [row[1] for row in demand_trace.customdata] == [
        block.direction for block in accepted_presentation.blocks
    ]
    assert [row[5] for row in demand_trace.customdata] == [
        _direction_display(accepted_presentation, block.direction)
        for block in accepted_presentation.blocks
    ]
    assert "Chiều=%{customdata[5]}" in demand_trace.hovertemplate
    assert list(_trace(figure, "Số chuyến B").y) == [
        block.b_trip_count for block in accepted_presentation.blocks
    ]
    assert list(_trace(figure, "Số chuyến C được chấp nhận").y) == [
        block.c_actual_trip_count for block in accepted_presentation.blocks
    ]
    assert list(_trace(figure, "Số chuyến yêu cầu 85%").y) == [
        block.required_trips_85 for block in accepted_presentation.blocks
    ]
    assert list(_trace(figure, "Số chuyến yêu cầu 90%").y) == [
        block.required_trips_90 for block in accepted_presentation.blocks
    ]


def test_overview_does_not_invent_combined_or_c_trace(
    alpha_presentation,
) -> None:
    figure = build_unified_demand_supply_figure_v1(alpha_presentation)
    names = {item.name for item in figure.data}

    assert "Số chuyến B" in names
    assert "Số chuyến C được chấp nhận" not in names
    assert dict(figure.layout.meta)["accepted_solution_fingerprint"] is None
    assert all("combined" not in category for category in figure.layout.xaxis.categoryarray)


def test_combined_demand_chart_stays_combined() -> None:
    presentation = build_unified_presentation_v1(*build_result_and_report(combined_demand=True))
    figure = build_unified_demand_supply_figure_v1(presentation)

    assert {block.direction for block in presentation.blocks} == {"combined"}
    demand_trace = _trace(figure, "Nhu cầu hành khách")
    assert {row[1] for row in demand_trace.customdata} == {"combined"}
    assert {row[5] for row in demand_trace.customdata} == {"Tổng hợp hai chiều"}
    assert all("Tổng hợp hai chiều" in value for value in figure.layout.xaxis.categoryarray)
    assert all(
        all(direction not in value for direction in ("outbound", "inbound", "combined"))
        for value in figure.layout.xaxis.categoryarray
    )


def test_departure_chart_uses_exact_b_and_accepted_c_departures(
    accepted_presentation,
) -> None:
    figure = build_unified_departure_figure_v1(accepted_presentation)
    scenario_b = accepted_presentation.scenario("B")
    scenario_c = accepted_presentation.scenario("C")
    assert scenario_b is not None
    assert scenario_c is not None

    for scenario, label in ((scenario_b, "B"), (scenario_c, "C")):
        for direction in ("outbound", "inbound"):
            display_direction = _direction_display(accepted_presentation, direction)
            trace = _trace(figure, f"{label} · {display_direction}")
            assert list(trace.x) == [
                trip.departure_time_seconds
                for trip in scenario.trips
                if trip.direction == direction
            ]
            assert {row[1] for row in trace.customdata} == {direction}
            assert {row[6] for row in trace.customdata} == {display_direction}
            assert "Chiều=%{customdata[6]}" in trace.hovertemplate


def test_c_departure_hover_preserves_source_shift_regime_and_vehicle(
    accepted_presentation,
) -> None:
    figure = build_unified_departure_figure_v1(accepted_presentation)
    scenario_c = accepted_presentation.scenario("C")
    assert scenario_c is not None
    trace = _trace(
        figure,
        f"C · {_direction_display(accepted_presentation, 'outbound')}",
    )
    outbound = [trip for trip in scenario_c.trips if trip.direction == "outbound"]

    for customdata, trip in zip(trace.customdata, outbound, strict=True):
        assert customdata[1] == trip.direction
        assert customdata[6] == _direction_display(accepted_presentation, trip.direction)
        assert customdata[7] == trip.source_b_trip_id
        assert customdata[9] == trip.shift_minutes
        assert customdata[10] == trip.headway_regime_id
        assert customdata[11] == trip.change_reason
        assert customdata[12] == trip.vehicle_assignment
        assert customdata[2] == trip.departure_terminal
        assert customdata[3] == trip.arrival_terminal
        assert "Nguồn B" in trace.hovertemplate


def test_no_c_lane_and_no_legacy_weighted_score_when_c_absent(
    alpha_presentation,
) -> None:
    figure = build_unified_departure_figure_v1(alpha_presentation)
    assert all(not str(item.name).startswith("C ·") for item in figure.data)
    assert "weighted" not in json.dumps(figure.to_plotly_json()).lower()


def test_midnight_crossing_axis_is_continuous_and_chronological(
    accepted_presentation,
) -> None:
    scenario_b = accepted_presentation.scenario("B")
    assert scenario_b is not None
    outbound_times = iter(
        (23 * 3600 + 50 * 60, 24 * 3600 + 10 * 60, 24 * 3600 + 40 * 60, 25 * 3600 + 10 * 60)
    )
    changed = []
    for trip in scenario_b.trips:
        if trip.direction == "outbound":
            departure = next(outbound_times)
            changed.append(
                replace(
                    trip,
                    departure_time_seconds=departure,
                    arrival_time_seconds=departure + trip.runtime_seconds,
                )
            )
        else:
            changed.append(trip)
    changed_b = replace(scenario_b, trips=tuple(changed))
    scenarios = tuple(
        changed_b if item.scenario_id == "B" else item for item in accepted_presentation.scenarios
    )
    changed_presentation = replace(
        accepted_presentation,
        scenarios=scenarios,
        presentation_fingerprint="",
    )
    presentation = replace(
        changed_presentation,
        presentation_fingerprint=unified_presentation._presentation_fingerprint(
            changed_presentation
        ),
    )
    figure = build_unified_departure_figure_v1(presentation)
    trace = _trace(
        figure,
        f"B · {_direction_display(presentation, 'outbound')}",
    )

    assert list(trace.x) == sorted(trace.x)
    assert max(trace.x) > 24 * 3600
    assert any(str(value).startswith("24:") for value in figure.layout.xaxis.ticktext)
    assert any(str(value).startswith("25:") for value in figure.layout.xaxis.ticktext)


def test_chart_builders_do_not_call_legacy_figure_builders(
    monkeypatch,
    accepted_presentation,
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("legacy figure builder must not be invoked")

    monkeypatch.setattr(diagram, "build_comparison_diagram", forbidden)
    monkeypatch.setattr(diagram, "build_departure_detail_diagram", forbidden)
    build_unified_demand_supply_figure_v1(accepted_presentation)
    build_unified_departure_figure_v1(accepted_presentation)
