from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from bus_schedule_engine.contracts_v1 import (
    DemandAllocationAuthorityModeV1,
    DemandConfidence,
    NormalizationError,
    NormalizationOptions,
    OperatingDayType,
    ScenarioCOptimizationModeV1,
    build_two_stage_demand_authority_v1,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
)
from bus_schedule_engine.contracts_v1.evaluation_fingerprints import evaluation_fingerprint
from bus_schedule_engine.importer import ImportedWorkbook
from bus_schedule_engine.models import DemandRecord, Direction, VolumeType


def _record(
    direction: Direction,
    start_minute: int,
    end_minute: int,
    passengers: float,
) -> DemandRecord:
    return DemandRecord(
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 7),
        observation_days=7,
        block_start_seconds=start_minute * 60,
        block_end_seconds=end_minute * 60,
        direction=direction,
        passenger_volume=passengers,
        volume_type=VolumeType.AVERAGE_DAY,
    )


def _imported(parameters, trips, demand, *, with_a: bool = False) -> ImportedWorkbook:
    return ImportedWorkbook(
        parameters_a=parameters if with_a else None,
        trips_a=[replace(item, scenario="A") for item in trips] if with_a else [],
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )


def _options(mode: ScenarioCOptimizationModeV1) -> NormalizationOptions:
    return NormalizationOptions(
        source_id="synthetic-two-stage-authority",
        imported_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
        operating_day_type_a=OperatingDayType.WEEKDAY,
        operating_day_type_b=OperatingDayType.WEEKDAY,
        available_fleet_limit_a=4,
        available_fleet_limit_b=4,
        demand_confidence=DemandConfidence.HIGH,
        optimization_mode=mode,
    )


def test_b_plus_demand_without_a_is_accepted_only_in_explicit_b_anchored_mode(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    trips = make_valid_trips(parameters)
    demand = [
        _record(Direction.TERMINAL_1_TO_2, 360, 421, 80),
        _record(Direction.TERMINAL_2_TO_1, 370, 431, 70),
    ]
    imported = _imported(parameters, trips, demand)

    with pytest.raises(NormalizationError, match="DEMAND_WITHOUT_SCENARIO_A"):
        normalize_imported_workbook_v1(
            imported,
            _options(ScenarioCOptimizationModeV1.LEGACY_A_BOUND),
        )

    normalized = normalize_imported_workbook_v1(
        imported,
        _options(ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE),
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    authority = build_two_stage_demand_authority_v1(normalized, evaluation)

    assert normalized.scenario_a is None
    assert authority.authority_mode == (
        DemandAllocationAuthorityModeV1.DIRECTIONAL_FIXED_DIRECTION_COUNTS
    )
    assert authority.supports_directional_passenger_inference is True


def test_combined_mode_preserves_direction_counts_without_directional_inference(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    trips = make_valid_trips(parameters)
    normalized = normalize_imported_workbook_v1(
        _imported(
            parameters,
            trips,
            [_record(Direction.COMBINED, 360, 431, 150)],
        ),
        _options(ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE),
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    authority = build_two_stage_demand_authority_v1(normalized, evaluation)

    assert authority.authority_mode == (
        DemandAllocationAuthorityModeV1.COMBINED_FIXED_DIRECTION_COUNTS
    )
    assert authority.supports_directional_passenger_inference is False
    assert any(
        "does not claim directional passenger inference" in item for item in authority.limitations
    )


def test_new_optimization_mode_is_fingerprinted_without_changing_source_identities(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    trips = make_valid_trips(parameters)
    demand = [
        _record(Direction.TERMINAL_1_TO_2, 360, 421, 80),
        _record(Direction.TERMINAL_2_TO_1, 370, 431, 70),
    ]
    imported = _imported(parameters, trips, demand, with_a=True)
    legacy = normalize_imported_workbook_v1(
        imported,
        _options(ScenarioCOptimizationModeV1.LEGACY_A_BOUND),
    )
    anchored = normalize_imported_workbook_v1(
        imported,
        _options(ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE),
    )
    legacy_evaluation = evaluate_scenario_b_v1(legacy)
    anchored_evaluation = evaluate_scenario_b_v1(anchored)

    assert legacy.scenario_a_fingerprint == anchored.scenario_a_fingerprint
    assert legacy.scenario_b_fingerprint == anchored.scenario_b_fingerprint
    assert legacy.observed_demand_fingerprint == anchored.observed_demand_fingerprint
    assert evaluation_fingerprint(legacy, legacy_evaluation, _evaluation_policy()) != (
        evaluation_fingerprint(anchored, anchored_evaluation, _evaluation_policy())
    )


def _evaluation_policy():
    from bus_schedule_engine.contracts_v1 import ScenarioBEvaluationPolicyV1

    return ScenarioBEvaluationPolicyV1()
