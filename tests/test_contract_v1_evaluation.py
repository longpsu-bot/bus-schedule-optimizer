from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from bus_schedule_engine.contracts_v1 import (
    BDisposition,
    BlockBoundaryReason,
    BlockMode,
    BlockSupplyStatus,
    DemandBlockPolicyV1,
    DemandConfidence,
    DemandResolutionError,
    DimensionStatus,
    NormalizationOptions,
    OperatingDayType,
    ScenarioBEvaluationPolicyV1,
    block_supply_plan_to_contract_dict,
    build_demand_analysis_blocks_v1,
    demand_analysis_block_to_contract_dict,
    demand_resolution_to_contract_dict,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
    schedule_evaluation_to_contract_dict,
)
from bus_schedule_engine.importer import ImportedWorkbook
from bus_schedule_engine.models import DemandRecord, Direction, Trip, VolumeType

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "v1"


def _schema_errors(payload: dict[str, object], schema_name: str) -> list[str]:
    schema = json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(payload)]


def _record(
    start_hour: int,
    end_hour: int,
    passengers: float,
    *,
    direction: Direction = Direction.COMBINED,
    volume_type: VolumeType = VolumeType.AVERAGE_DAY,
    observation_days: int = 10,
) -> DemandRecord:
    return DemandRecord(
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 10),
        observation_days=observation_days,
        block_start_seconds=start_hour * 3600,
        block_end_seconds=end_hour * 3600,
        direction=direction,
        passenger_volume=passengers,
        volume_type=volume_type,
    )


def _bundle(
    parameters,
    trips: list[Trip],
    demand: list[DemandRecord],
    *,
    fleet_limit: int = 4,
    confidence: DemandConfidence = DemandConfidence.HIGH,
):
    trips_a = [replace(item, scenario="A") for item in trips]
    imported = ImportedWorkbook(
        parameters_a=parameters,
        trips_a=trips_a,
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )
    return normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="pr02-fixture",
            imported_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
            operating_day_type_a=OperatingDayType.WEEKDAY,
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_a=fleet_limit,
            available_fleet_limit_b=fleet_limit,
            demand_confidence=confidence,
        ),
    )


def test_native_resolution_normalizes_multiday_totals_and_matches_schemas(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [
            _record(
                6,
                7,
                100,
                volume_type=VolumeType.TOTAL_OBSERVATION_PERIOD,
            ),
            _record(
                7,
                8,
                200,
                volume_type=VolumeType.TOTAL_OBSERVATION_PERIOD,
            ),
        ],
    )

    resolution = build_demand_analysis_blocks_v1(bundle.observed_demand)

    assert [item.observed_passengers for item in resolution.blocks] == [10, 20]
    assert [item.demand_rate_per_hour for item in resolution.blocks] == [10, 20]
    assert resolution.blocks[0].source_interval_ids == ("D-0001",)
    assert _schema_errors(
        demand_resolution_to_contract_dict(resolution.contract),
        "demand_resolution.schema.json",
    ) == []
    assert _schema_errors(
        demand_analysis_block_to_contract_dict(resolution.blocks[0]),
        "demand_analysis_block.schema.json",
    ) == []


def test_adaptive_blocks_merge_small_changes_and_keep_sustained_boundary(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [
            _record(6, 7, 10),
            _record(7, 8, 11),
            _record(8, 9, 30),
            _record(9, 10, 31),
        ],
    )
    policy = DemandBlockPolicyV1(
        block_mode=BlockMode.ADAPTIVE,
        maximum_block_duration=180,
        material_change_ratio=0.50,
        minimum_sustained_intervals=2,
    )

    resolution = build_demand_analysis_blocks_v1(bundle.observed_demand, policy)

    assert [item.source_interval_ids for item in resolution.blocks] == [
        ("D-0001", "D-0002"),
        ("D-0003", "D-0004"),
    ]
    assert resolution.blocks[1].block_boundary_reason == BlockBoundaryReason.SUSTAINED_CHANGE


def test_manual_boundary_cannot_split_source_interval(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(6, 8, 40)],
    )

    with pytest.raises(DemandResolutionError, match="may not split source intervals"):
        build_demand_analysis_blocks_v1(
            bundle.observed_demand,
            DemandBlockPolicyV1(
                block_mode=BlockMode.MANUAL,
                manual_boundaries=(6 * 3600, 7 * 3600, 8 * 3600),
                maximum_block_duration=120,
            ),
        )


def test_combined_demand_remains_combined(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(6, 7, 100)],
    )

    resolution = build_demand_analysis_blocks_v1(bundle.observed_demand)

    assert len(resolution.blocks) == 1
    assert resolution.blocks[0].direction.value == "combined"


def test_exact_85_percent_is_within_planning_ceiling(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    trips = make_valid_trips(parameters)
    bundle = _bundle(parameters, trips, [_record(6, 7, 170)])

    result = evaluate_scenario_b_v1(bundle)
    plan = result.b_block_supply[0]

    assert plan.b_trip_count == 2
    assert plan.load_factor == pytest.approx(0.85)
    assert plan.status == BlockSupplyStatus.WITHIN_PLANNING_CEILING
    assert (
        result.evaluation.disposition
        == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE
    )


def test_above_85_is_warning_and_demand_unsuitable(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(parameters, make_valid_trips(parameters), [_record(6, 7, 171)])

    result = evaluate_scenario_b_v1(bundle)

    assert result.b_block_supply[0].status == BlockSupplyStatus.WARNING_ABOVE_85
    assert result.evaluation.demand_suitability.status == DimensionStatus.WARNING
    assert (
        result.evaluation.disposition
        == BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE
    )


def test_low_load_is_review_only_not_donor_or_reduction_signal(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(parameters, make_valid_trips(parameters), [_record(6, 7, 10)])

    result = evaluate_scenario_b_v1(bundle)
    plan = result.b_block_supply[0]

    assert plan.status == BlockSupplyStatus.LOW_LOAD_REVIEW_ONLY
    assert plan.status != BlockSupplyStatus.ELIGIBLE_DONOR_PERIOD
    assert "not a trip-reduction instruction" in plan.allocation_reason
    assert (
        result.evaluation.disposition
        == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE
    )


def test_low_confidence_demand_is_insufficient_for_authoritative_disposition(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(6, 7, 171)],
        confidence=DemandConfidence.LOW,
    )

    result = evaluate_scenario_b_v1(bundle)

    assert result.b_block_supply[0].status == BlockSupplyStatus.INSUFFICIENT_DATA
    assert result.evaluation.disposition == BDisposition.INSUFFICIENT_DATA


def test_no_service_with_demand_is_preserved_even_in_adaptive_mode(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(6, 7, 50), _record(7, 8, 50)],
    )
    policy = ScenarioBEvaluationPolicyV1(
        demand_blocks=DemandBlockPolicyV1(
            block_mode=BlockMode.ADAPTIVE,
            maximum_block_duration=120,
            material_change_ratio=0.20,
        )
    )

    result = evaluate_scenario_b_v1(bundle, policy)

    assert len(result.demand_resolution.blocks) == 2
    assert result.b_block_supply[1].status == BlockSupplyStatus.NO_SERVICE_WITH_DEMAND
    assert result.evaluation.demand_suitability.status == DimensionStatus.FAIL


def test_submitted_b_fleet_infeasibility_does_not_claim_parameter_infeasibility(
    make_parameters,
) -> None:
    parameters = make_parameters(
        trip_runtime_minutes=60,
        minimum_layover_minutes=5,
        vehicle_capacity_passengers=60,
    )
    definitions = [
        ("B-01", parameters.terminal_1_name, Direction.TERMINAL_1_TO_2, 6 * 3600),
        ("B-02", parameters.terminal_2_name, Direction.TERMINAL_2_TO_1, 6 * 3600 + 10 * 60),
        ("B-03", parameters.terminal_1_name, Direction.TERMINAL_1_TO_2, 7 * 3600),
        ("B-04", parameters.terminal_2_name, Direction.TERMINAL_2_TO_1, 7 * 3600 + 10 * 60),
    ]
    trips = [
        Trip(
            scenario="B",
            trip_id=trip_id,
            departure_terminal=terminal,
            direction=direction,
            departure_seconds=departure,
            arrival_seconds=departure + 60 * 60,
        )
        for trip_id, terminal, direction, departure in definitions
    ]
    bundle = _bundle(parameters, trips, [_record(6, 7, 20)], fleet_limit=2)

    result = evaluate_scenario_b_v1(bundle)

    assert result.fleet_assessment.minimum_required_fleet == 3
    assert not result.fleet_assessment.feasible
    assert (
        result.evaluation.disposition
        == BDisposition.TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION
    )
    assert result.evaluation.disposition != BDisposition.PARAMETERS_INFEASIBLE


def test_evaluation_and_supply_serialization_match_contract_schemas(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(parameters, make_valid_trips(parameters), [_record(6, 7, 171)])

    result = evaluate_scenario_b_v1(bundle)

    assert _schema_errors(
        schedule_evaluation_to_contract_dict(result.evaluation),
        "schedule_evaluation_result.schema.json",
    ) == []
    assert _schema_errors(
        block_supply_plan_to_contract_dict(result.b_block_supply[0]),
        "block_supply_plan.schema.json",
    ) == []


def test_no_demand_returns_insufficient_data_without_fabricated_blocks(
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
            source_id="pr02-b-only",
            imported_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_b=4,
        ),
    )

    result = evaluate_scenario_b_v1(bundle)

    assert result.demand_resolution is None
    assert result.b_block_supply == ()
    assert result.evaluation.disposition == BDisposition.INSUFFICIENT_DATA
