from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from bus_schedule_engine.contracts_v1 import (
    BDisposition,
    BlockMode,
    BlockSupplyStatus,
    DemandBlockPolicyV1,
    DemandConfidence,
    DemandResolutionError,
    DemandResolutionType,
    DimensionStatus,
    NormalizationOptions,
    OperatingDayType,
    ScenarioBEvaluationPolicyV1,
    build_demand_analysis_blocks_v1,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
    observed_demand_fingerprint,
)
from bus_schedule_engine.contracts_v1.demand_coverage import (
    COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE,
    COMBINED_DEMAND_UNSUPPORTED_FOR_DIRECTIONAL_C,
    DEMAND_DEPARTURE_NOT_COVERED,
    DEMAND_DIRECTION_STREAM_MISSING,
    DEMAND_SERVICE_WINDOW_NOT_COVERED,
    DEMAND_TEMPORAL_COVERAGE_GAP,
    MIXED_DIRECTION_GRAIN_PARTIAL_SUPPORT,
    DemandCoverageModeV1,
)
from bus_schedule_engine.contracts_v1.evaluation_fingerprints import (
    evaluation_fingerprint,
)
from bus_schedule_engine.importer import ImportedWorkbook
from bus_schedule_engine.models import DemandRecord, Direction, Trip, VolumeType


def _record(
    start_minute: int,
    end_minute: int,
    passengers: float,
    *,
    direction: Direction = Direction.COMBINED,
) -> DemandRecord:
    return DemandRecord(
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 10),
        observation_days=10,
        block_start_seconds=start_minute * 60,
        block_end_seconds=end_minute * 60,
        direction=direction,
        passenger_volume=passengers,
        volume_type=VolumeType.AVERAGE_DAY,
    )


def _bundle(
    parameters,
    trips: list[Trip],
    demand: list[DemandRecord],
    *,
    confidence: DemandConfidence = DemandConfidence.HIGH,
):
    imported = ImportedWorkbook(
        parameters_a=parameters,
        trips_a=[replace(item, scenario="A") for item in trips],
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )
    return normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="v1-h3-demand-coverage",
            imported_at=datetime(2026, 7, 23, 14, 0, tzinfo=UTC),
            operating_day_type_a=OperatingDayType.WEEKDAY,
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_a=4,
            available_fleet_limit_b=4,
            demand_confidence=confidence,
        ),
    )


def _coverage(result):
    assert result.demand_resolution is not None
    assessment = result.demand_resolution.coverage_assessment
    assert assessment is not None
    return assessment


def test_case_01_internal_gap_is_reported(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 420, 20), _record(480, 540, 30)],
    )

    result = evaluate_scenario_b_v1(bundle)
    assessment = _coverage(result)

    assert DEMAND_TEMPORAL_COVERAGE_GAP in assessment.evaluation_issue_codes
    assert any(
        item.code == DEMAND_TEMPORAL_COVERAGE_GAP
        and item.start_time == 420 * 60
        and item.end_time == 480 * 60
        for item in assessment.uncovered_segments
    )


def test_case_02_gap_does_not_create_zero_passenger_block(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 420, 20), _record(480, 540, 30)],
    )

    resolution = build_demand_analysis_blocks_v1(bundle.observed_demand)

    assert len(resolution.blocks) == 2
    assert [item.observed_passengers for item in resolution.blocks] == [20, 30]
    assert not any(
        item.start_time == 420 * 60 and item.end_time == 480 * 60 for item in resolution.blocks
    )


def test_case_03_leading_gap_blocks_whole_b_suitability(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(370, 480, 10)],
    )

    result = evaluate_scenario_b_v1(bundle)
    assessment = _coverage(result)

    assert DEMAND_SERVICE_WINDOW_NOT_COVERED in assessment.evaluation_issue_codes
    assert not assessment.whole_b_suitability_supported
    assert result.evaluation.disposition == BDisposition.INSUFFICIENT_DATA


def test_case_04_trailing_gap_blocks_whole_b_suitability(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 420, 10)],
    )

    result = evaluate_scenario_b_v1(bundle)
    assessment = _coverage(result)

    assert DEMAND_SERVICE_WINDOW_NOT_COVERED in assessment.evaluation_issue_codes
    assert not assessment.whole_b_suitability_supported
    assert result.evaluation.disposition == BDisposition.INSUFFICIENT_DATA


def test_case_05_final_departure_on_half_open_end_is_uncovered(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 420, 10)],
    )

    assessment = _coverage(evaluate_scenario_b_v1(bundle))

    assert DEMAND_DEPARTURE_NOT_COVERED in assessment.evaluation_issue_codes
    assert any(
        item.trip_id == "T3" and item.departure_time == 420 * 60
        for item in assessment.uncovered_departures
    )


def test_case_06_uncovered_departure_evidence_is_complete_and_deterministic(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 420, 10)],
    )

    assessment = _coverage(evaluate_scenario_b_v1(bundle))
    evidence = [
        item for item in assessment.evidence if item.startswith(DEMAND_DEPARTURE_NOT_COVERED)
    ]

    assert evidence
    assert all(
        "scenario=" in item
        and "direction=" in item
        and "trip_id=" in item
        and "departure_time=" in item
        for item in evidence
    )
    assert [
        (
            item.scenario.value,
            item.direction.value,
            item.trip_id,
            item.departure_time,
        )
        for item in assessment.uncovered_departures
    ] == [
        ("A", "outbound", "T3", 420 * 60),
        ("B", "outbound", "T3", 420 * 60),
        ("A", "inbound", "T4", 430 * 60),
        ("B", "inbound", "T4", 430 * 60),
    ]


def test_case_07_missing_inbound_stream_is_insufficient(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [
            _record(
                350,
                425,
                10,
                direction=Direction.TERMINAL_1_TO_2,
            )
        ],
    )

    result = evaluate_scenario_b_v1(bundle)
    assessment = _coverage(result)

    assert DEMAND_DIRECTION_STREAM_MISSING in assessment.evaluation_issue_codes
    assert not assessment.whole_b_suitability_supported
    assert result.evaluation.disposition == BDisposition.INSUFFICIENT_DATA


def test_case_08_full_directional_coverage_preserves_supported_behavior(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [
            _record(
                350,
                425,
                10,
                direction=Direction.TERMINAL_1_TO_2,
            ),
            _record(
                365,
                435,
                10,
                direction=Direction.TERMINAL_2_TO_1,
            ),
        ],
    )

    result = evaluate_scenario_b_v1(bundle)
    assessment = _coverage(result)

    assert assessment.whole_b_suitability_supported
    assert assessment.directional_c_generation_supported
    assert result.evaluation.disposition == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE


def test_case_09_directional_streams_may_use_different_boundaries(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [
            _record(
                345,
                423,
                10,
                direction=Direction.TERMINAL_1_TO_2,
            ),
            _record(
                367,
                437,
                10,
                direction=Direction.TERMINAL_2_TO_1,
            ),
        ],
    )

    assessment = _coverage(evaluate_scenario_b_v1(bundle))

    assert assessment.directional_c_generation_supported
    assert {
        (item.stream.value, item.start_time, item.end_time) for item in assessment.source_segments
    } == {
        ("outbound", 345 * 60, 423 * 60),
        ("inbound", 367 * 60, 437 * 60),
    }


def test_case_10_combined_only_can_support_aggregate_b_suitability(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(350, 440, 100)],
    )

    result = evaluate_scenario_b_v1(bundle)
    assessment = _coverage(result)

    assert assessment.mode == DemandCoverageModeV1.COMBINED_ONLY
    assert assessment.whole_b_suitability_supported
    assert not assessment.directional_c_generation_supported
    assert result.evaluation.disposition == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE


def test_case_11_combined_only_carries_directional_support_limitation(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(350, 440, 10)],
    )

    result = evaluate_scenario_b_v1(bundle)
    assessment = _coverage(result)

    assert COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE in assessment.evaluation_issue_codes
    assert COMBINED_DEMAND_UNSUPPORTED_FOR_DIRECTIONAL_C in assessment.generation_issue_codes
    assert any(
        COMBINED_DEMAND_DIRECTIONAL_SUPPORT_UNAVAILABLE in item
        for item in result.evaluation.limitations
    )


def test_case_13_combined_demand_is_never_reused_as_two_directional_blocks(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(350, 440, 100)],
    )

    result = evaluate_scenario_b_v1(bundle)

    assert len(result.demand_resolution.blocks) == 1
    assert result.demand_resolution.blocks[0].direction.value == "combined"
    assert len(result.b_block_supply) == 1
    assert result.b_block_supply[0].b_trip_count == 4


def test_case_16_non_overlapping_mixed_grain_preserves_blocks_but_is_partial(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [
            _record(300, 360, 0),
            _record(
                360,
                440,
                10,
                direction=Direction.TERMINAL_1_TO_2,
            ),
        ],
    )

    result = evaluate_scenario_b_v1(bundle)
    assessment = _coverage(result)

    assert len(result.demand_resolution.blocks) == 2
    assert {item.direction.value for item in result.demand_resolution.blocks} == {
        "combined",
        "outbound",
    }
    assert MIXED_DIRECTION_GRAIN_PARTIAL_SUPPORT in assessment.evaluation_issue_codes
    assert not assessment.whole_b_suitability_supported
    assert not assessment.directional_c_generation_supported
    assert result.evaluation.disposition == BDisposition.INSUFFICIENT_DATA


def test_case_17_adaptive_mode_never_merges_across_gap(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 420, 10), _record(480, 540, 0)],
    )

    resolution = build_demand_analysis_blocks_v1(
        bundle.observed_demand,
        DemandBlockPolicyV1(
            block_mode=BlockMode.ADAPTIVE,
            maximum_block_duration=180,
        ),
    )

    assert len(resolution.blocks) == 2
    assert [item.source_interval_ids for item in resolution.blocks] == [
        ("D-0001",),
        ("D-0002",),
    ]


def test_case_18_manual_mode_rejects_block_spanning_gap(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 420, 10), _record(480, 540, 10)],
    )

    with pytest.raises(DemandResolutionError, match="unexplained demand gap"):
        build_demand_analysis_blocks_v1(
            bundle.observed_demand,
            DemandBlockPolicyV1(
                block_mode=BlockMode.MANUAL,
                manual_boundaries=(360 * 60, 540 * 60),
                maximum_block_duration=180,
            ),
        )


def test_case_19_no_service_finding_survives_gap(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [
            _record(300, 360, 50),
            _record(360, 420, 10),
            _record(480, 540, 10),
        ],
    )

    result = evaluate_scenario_b_v1(bundle)

    assert BlockSupplyStatus.NO_SERVICE_WITH_DEMAND in {
        item.status for item in result.b_block_supply
    }
    assert result.evaluation.demand_suitability.status == DimensionStatus.FAIL
    assert result.evaluation.disposition == BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE


def test_case_20_critical_finding_survives_gap(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 420, 181), _record(480, 540, 0)],
    )

    result = evaluate_scenario_b_v1(bundle)

    assert result.b_block_supply[0].status == BlockSupplyStatus.CRITICAL_ABOVE_90
    assert result.evaluation.demand_suitability.status == DimensionStatus.FAIL
    assert result.evaluation.disposition == BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE


def test_case_21_warning_finding_survives_gap(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 420, 171), _record(480, 540, 0)],
    )

    result = evaluate_scenario_b_v1(bundle)

    assert result.b_block_supply[0].status == BlockSupplyStatus.WARNING_ABOVE_85
    assert result.evaluation.demand_suitability.status == DimensionStatus.WARNING
    assert result.evaluation.disposition == BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE


def test_case_22_passing_observed_blocks_plus_gap_are_not_suitable(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters(vehicle_capacity_passengers=100)
    bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 420, 10), _record(480, 540, 0)],
    )

    result = evaluate_scenario_b_v1(bundle)

    assert result.b_block_supply[0].status == BlockSupplyStatus.LOW_LOAD_REVIEW_ONLY
    assert result.evaluation.demand_suitability.status == DimensionStatus.INSUFFICIENT_DATA
    assert result.evaluation.disposition == BDisposition.INSUFFICIENT_DATA


def test_case_28_coverage_change_alters_evaluation_fingerprint(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    trips = make_valid_trips(parameters)
    full_bundle = _bundle(
        parameters,
        trips,
        [_record(360, 420, 5), _record(420, 440, 5)],
    )
    gap_bundle = _bundle(
        parameters,
        trips,
        [_record(360, 420, 5), _record(480, 500, 5)],
    )
    policy = ScenarioBEvaluationPolicyV1()
    full = evaluate_scenario_b_v1(full_bundle, policy)
    gap = evaluate_scenario_b_v1(gap_bundle, policy)

    assert evaluation_fingerprint(full_bundle, full, policy) != evaluation_fingerprint(
        gap_bundle, gap, policy
    )


def test_case_29_daily_total_only_remains_intraday_insufficient(
    make_parameters,
    make_valid_trips,
) -> None:
    parameters = make_parameters()
    regular_bundle = _bundle(
        parameters,
        make_valid_trips(parameters),
        [_record(360, 440, 100)],
    )
    observed = regular_bundle.observed_demand
    assert observed is not None
    daily_observation = replace(
        observed.observations[0],
        interval_start=0,
        interval_end=23 * 3600 + 59 * 60,
        source_resolution_type=DemandResolutionType.DAILY_TOTAL,
        source_resolution_minutes=None,
    )
    daily_demand = replace(observed, observations=(daily_observation,))
    daily_bundle = replace(
        regular_bundle,
        observed_demand=daily_demand,
        observed_demand_fingerprint=observed_demand_fingerprint(daily_demand),
    )

    result = evaluate_scenario_b_v1(daily_bundle)
    assessment = _coverage(result)

    assert assessment.mode == DemandCoverageModeV1.DAILY_TOTAL_ONLY
    assert result.demand_resolution.blocks == ()
    assert result.evaluation.disposition == BDisposition.INSUFFICIENT_DATA
