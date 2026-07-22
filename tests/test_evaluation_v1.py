from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from bus_schedule_engine.contracts_v1 import (
    DemandConfidence,
    NormalizationOptions,
    OperatingDayType,
    normalize_imported_workbook_v1,
)
from bus_schedule_engine.evaluation_v1 import (
    BlockDemandStatus,
    DemandBlockMode,
    DemandResolutionError,
    DemandResolutionPolicy,
    ScenarioBDisposition,
    build_demand_blocks,
    demand_block_to_dict,
    demand_resolution_to_dict,
    evaluate_scenario_b,
    schedule_evaluation_to_dict,
)
from bus_schedule_engine.importer import ImportedWorkbook
from bus_schedule_engine.models import DemandRecord, Direction, Trip, VolumeType

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "v1"


def _schema_errors(payload: dict[str, object], schema_name: str) -> list[str]:
    schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    return [
        error.message
        for error in Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(payload)
    ]


def _bundle(make_parameters, make_valid_trips, demand: list[DemandRecord]):
    parameters = make_parameters()
    trips_b = make_valid_trips(parameters)
    trips_a = [replace(item, scenario="A") for item in trips_b]
    imported = ImportedWorkbook(
        parameters_a=parameters,
        trips_a=trips_a,
        parameters_b=parameters,
        trips_b=trips_b,
        demand=demand,
        configuration={},
    )
    return normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="evaluation-v1-fixture",
            imported_at=datetime(2026, 7, 22, 8, 0, tzinfo=UTC),
            operating_day_type_a=OperatingDayType.WEEKDAY,
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_a=3,
            available_fleet_limit_b=3,
            demand_confidence=DemandConfidence.MEDIUM,
        ),
    )


def _demand(
    start: int,
    end: int,
    passengers: float,
    direction: Direction = Direction.COMBINED,
) -> DemandRecord:
    return DemandRecord(
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 15),
        observation_days=15,
        block_start_seconds=start,
        block_end_seconds=end,
        direction=direction,
        passenger_volume=passengers,
        volume_type=VolumeType.AVERAGE_DAY,
    )


def test_native_blocks_preserve_source_grain_and_schema(make_parameters, make_valid_trips) -> None:
    bundle = _bundle(
        make_parameters,
        make_valid_trips,
        [_demand(6 * 3600, 7 * 3600, 80), _demand(7 * 3600, 8 * 3600, 20)],
    )
    resolution, blocks = build_demand_blocks(bundle.observed_demand)

    assert len(blocks) == 2
    assert blocks[0].source_interval_ids == ("D-0001",)
    assert blocks[0].observed_passengers == 80
    assert blocks[0].demand_rate_per_hour == 80
    assert _schema_errors(
        demand_resolution_to_dict(resolution),
        "demand_resolution.schema.json",
    ) == []
    assert _schema_errors(
        demand_block_to_dict(blocks[0]),
        "demand_analysis_block.schema.json",
    ) == []


def test_manual_mode_rejects_boundary_that_splits_source_interval(
    make_parameters,
    make_valid_trips,
) -> None:
    bundle = _bundle(
        make_parameters,
        make_valid_trips,
        [_demand(6 * 3600, 7 * 3600, 50)],
    )

    with pytest.raises(DemandResolutionError, match="may not split source intervals"):
        build_demand_blocks(
            bundle.observed_demand,
            DemandResolutionPolicy(
                block_mode=DemandBlockMode.MANUAL,
                manual_boundaries=(6 * 3600 + 30 * 60,),
            ),
        )


def test_adaptive_mode_merges_only_adjacent_similar_source_intervals(
    make_parameters,
    make_valid_trips,
) -> None:
    bundle = _bundle(
        make_parameters,
        make_valid_trips,
        [
            _demand(6 * 3600, 6 * 3600 + 30 * 60, 20),
            _demand(6 * 3600 + 30 * 60, 7 * 3600, 21),
            _demand(7 * 3600, 7 * 3600 + 30 * 60, 60),
        ],
    )
    _, blocks = build_demand_blocks(
        bundle.observed_demand,
        DemandResolutionPolicy(
            block_mode=DemandBlockMode.ADAPTIVE,
            material_change_ratio=0.20,
        ),
    )

    assert len(blocks) == 2
    assert blocks[0].source_interval_ids == ("D-0001", "D-0002")
    assert blocks[0].observed_passengers == 41
    assert blocks[0].duration_minutes == 60


def test_one_sided_load_factor_marks_overload_but_not_low_load_as_failure(
    make_parameters,
    make_valid_trips,
) -> None:
    overloaded = _bundle(
        make_parameters,
        make_valid_trips,
        [_demand(6 * 3600, 7 * 3600, 130)],
    )
    overloaded_result = evaluate_scenario_b(overloaded)

    assert overloaded_result.disposition == ScenarioBDisposition.FEASIBLE_BUT_DEMAND_UNSUITABLE
    assert overloaded_result.block_evaluations[0].status == BlockDemandStatus.CRITICAL_ABOVE_90

    low_load = _bundle(
        make_parameters,
        make_valid_trips,
        [_demand(6 * 3600, 7 * 3600, 10)],
    )
    low_result = evaluate_scenario_b(low_load)

    assert low_result.disposition == ScenarioBDisposition.FEASIBLE_AND_SUITABLE
    assert low_result.block_evaluations[0].status == BlockDemandStatus.LOW_LOAD_REVIEW_ONLY


def test_no_service_with_demand_is_blocking_for_demand_suitability(
    make_parameters,
    make_valid_trips,
) -> None:
    bundle = _bundle(
        make_parameters,
        make_valid_trips,
        [_demand(8 * 3600, 9 * 3600, 25)],
    )
    result = evaluate_scenario_b(bundle)

    assert result.block_evaluations[0].status == BlockDemandStatus.NO_SERVICE_WITH_DEMAND
    assert result.disposition == ScenarioBDisposition.FEASIBLE_BUT_DEMAND_UNSUITABLE


def test_evaluation_payload_matches_contract_schema(make_parameters, make_valid_trips) -> None:
    bundle = _bundle(
        make_parameters,
        make_valid_trips,
        [_demand(6 * 3600, 7 * 3600, 50)],
    )
    result = evaluate_scenario_b(bundle)

    assert _schema_errors(
        schedule_evaluation_to_dict(result),
        "schedule_evaluation_result.schema.json",
    ) == []


def test_missing_observed_demand_returns_insufficient_data(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    trips = make_valid_trips(parameters)
    imported = ImportedWorkbook(
        parameters_a=None,
        trips_a=[],
        parameters_b=parameters,
        trips_b=trips,
        demand=[],
        configuration={},
    )
    bundle = normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="b-only",
            imported_at=datetime(2026, 7, 22, 8, 0, tzinfo=UTC),
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_b=3,
        ),
    )

    result = evaluate_scenario_b(bundle)

    assert result.disposition == ScenarioBDisposition.INSUFFICIENT_DATA
    assert result.block_evaluations == ()
