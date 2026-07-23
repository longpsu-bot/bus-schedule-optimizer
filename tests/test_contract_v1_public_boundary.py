from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from bus_schedule_engine.contracts_v1 import (
    BDisposition,
    BlockSupplyStatus,
    DemandBlockPolicyV1,
    DemandConfidence,
    DemandResolutionError,
    DimensionStatus,
    InterpolationMethod,
    NormalizationOptions,
    OperatingDayType,
    build_demand_analysis_blocks_v1,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
)
from bus_schedule_engine.importer import ImportedWorkbook
from bus_schedule_engine.models import DemandRecord, Direction, VolumeType


def _record(
    start_hour: int,
    end_hour: int,
    passengers: float,
    *,
    direction: Direction = Direction.COMBINED,
) -> DemandRecord:
    return DemandRecord(
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 10),
        observation_days=10,
        block_start_seconds=start_hour * 3600,
        block_end_seconds=end_hour * 3600,
        direction=direction,
        passenger_volume=passengers,
        volume_type=VolumeType.AVERAGE_DAY,
    )


def _bundle(
    parameters,
    trips,
    demand,
    *,
    confidence: DemandConfidence = DemandConfidence.HIGH,
):
    imported = ImportedWorkbook(
        parameters_a=parameters,
        trips_a=[replace(trip, scenario="A") for trip in trips],
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )
    return normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="pr02-public-boundary",
            imported_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
            operating_day_type_a=OperatingDayType.WEEKDAY,
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_a=4,
            available_fleet_limit_b=4,
            demand_confidence=confidence,
        ),
    )


def test_public_boundary_rejects_overlapping_same_direction_demand(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [
            _record(6, 8, 40, direction=Direction.TERMINAL_1_TO_2),
            _record(7, 9, 40, direction=Direction.TERMINAL_1_TO_2),
        ],
    )

    with pytest.raises(
        DemandResolutionError,
        match="OVERLAPPING_DEMAND_OBSERVATIONS",
    ) as raised:
        build_demand_analysis_blocks_v1(bundle.observed_demand)

    assert raised.value.code == "OVERLAPPING_DEMAND_OBSERVATIONS"


def test_public_boundary_rejects_overlapping_combined_and_directional_grain(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [
            _record(6, 8, 40),
            _record(7, 9, 40, direction=Direction.TERMINAL_1_TO_2),
        ],
    )

    with pytest.raises(
        DemandResolutionError,
        match="MIXED_DIRECTION_GRAIN_OVERLAP",
    ) as raised:
        build_demand_analysis_blocks_v1(bundle.observed_demand)

    assert raised.value.code == "MIXED_DIRECTION_GRAIN_OVERLAP"


def test_public_boundary_rejects_unimplemented_interpolation(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(6, 7, 20)],
    )

    with pytest.raises(DemandResolutionError, match="interpolation_method=none"):
        build_demand_analysis_blocks_v1(
            bundle.observed_demand,
            DemandBlockPolicyV1(interpolation_method=InterpolationMethod.STEP),
        )


def test_blocking_demand_failure_is_not_erased_by_insufficient_blocks(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(5, 6, 50), _record(6, 7, 50)],
        confidence=DemandConfidence.LOW,
    )

    result = evaluate_scenario_b_v1(bundle)

    assert result.b_block_supply[0].status == BlockSupplyStatus.NO_SERVICE_WITH_DEMAND
    assert result.b_block_supply[1].status == BlockSupplyStatus.INSUFFICIENT_DATA
    assert result.evaluation.demand_suitability.status == DimensionStatus.FAIL
    assert result.evaluation.disposition == BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE
