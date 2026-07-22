from __future__ import annotations

from datetime import date

import pytest

from bus_schedule_engine.demand import (
    classify_load_factor,
    evaluate_scenario,
    headway_statistics,
    required_trips,
)
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    EvaluationStatus,
    Trip,
    ValidationReport,
    VolumeType,
)


def test_required_trips_400_passengers_capacity_60_target_85() -> None:
    assert required_trips(400, 60, 0.85) == 8


@pytest.mark.parametrize("load_factor", [0.0, 0.5, 0.85])
def test_load_factor_at_or_below_target_is_suitable(load_factor: float) -> None:
    assert (
        classify_load_factor(load_factor, 0.85, 0.90, has_demand=True, trips=1)
        == EvaluationStatus.SUITABLE
    )


def test_load_factor_between_target_and_maximum_is_warning() -> None:
    assert (
        classify_load_factor(0.88, 0.85, 0.90, has_demand=True, trips=1) == EvaluationStatus.MONITOR
    )


def test_load_factor_over_maximum_is_unsuitable() -> None:
    assert (
        classify_load_factor(0.91, 0.85, 0.90, has_demand=True, trips=1)
        == EvaluationStatus.UNSUITABLE
    )


def test_no_service_with_demand_is_not_zero_load_factor(make_parameters) -> None:
    parameters = make_parameters(total_daily_trips=0)
    record = DemandRecord(
        date(2026, 7, 1),
        date(2026, 7, 1),
        1,
        6 * 3600,
        7 * 3600,
        Direction.COMBINED,
        40,
        VolumeType.AVERAGE_DAY,
    )
    evaluation = evaluate_scenario("B", [], [record], parameters, ValidationReport())
    block = evaluation.blocks[0]
    assert block.load_factor is None
    assert block.status == EvaluationStatus.NO_SERVICE_WITH_DEMAND


def test_total_15_days_is_normalized_before_evaluation() -> None:
    record = DemandRecord(
        date(2026, 7, 1),
        date(2026, 7, 15),
        15,
        6 * 3600,
        7 * 3600,
        Direction.COMBINED,
        6000,
        VolumeType.TOTAL_OBSERVATION_PERIOD,
    )
    assert record.average_daily_demand == 400


def test_twelve_trips_in_sixty_minutes_have_five_minute_headway() -> None:
    stats = headway_statistics([index * 5 * 60 for index in range(12)])
    assert stats.mean_minutes == 5
    assert stats.minimum_minutes == 5
    assert stats.maximum_minutes == 5
    assert stats.standard_deviation_minutes == 0


def test_combined_demand_does_not_create_directional_conclusion(
    make_parameters, make_valid_trips
) -> None:
    parameters = make_parameters()
    record = DemandRecord(
        date(2026, 7, 1),
        date(2026, 7, 1),
        1,
        6 * 3600,
        8 * 3600,
        Direction.COMBINED,
        100,
        VolumeType.AVERAGE_DAY,
    )
    evaluation = evaluate_scenario(
        "B", make_valid_trips(parameters), [record], parameters, ValidationReport()
    )
    assert evaluation.blocks[0].direction == Direction.COMBINED
    assert "không kết luận" in evaluation.limitations[0].lower()


def test_block_headway_includes_gap_crossing_demand_boundary(make_parameters) -> None:
    parameters = make_parameters(
        total_daily_trips=3,
        terminal_1_first_departure=6 * 3600 + 50 * 60,
        terminal_1_last_departure=7 * 3600 + 10 * 60,
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=f"B-{index}",
            departure_terminal=parameters.terminal_1_name,
            direction=Direction.TERMINAL_1_TO_2,
            departure_seconds=departure,
        )
        for index, departure in enumerate([6 * 3600 + 50 * 60, 7 * 3600, 7 * 3600 + 10 * 60], 1)
    ]
    record = DemandRecord(
        date(2026, 7, 1),
        date(2026, 7, 1),
        1,
        7 * 3600,
        8 * 3600,
        Direction.TERMINAL_1_TO_2,
        100,
        VolumeType.AVERAGE_DAY,
    )
    evaluation = evaluate_scenario("B", trips, [record], parameters, ValidationReport())
    assert evaluation.blocks[0].headway.mean_minutes == 10
    assert evaluation.blocks[0].headway.minimum_minutes == 10
    assert evaluation.blocks[0].headway.maximum_minutes == 10
