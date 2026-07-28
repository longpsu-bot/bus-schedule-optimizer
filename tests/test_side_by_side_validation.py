from __future__ import annotations

import inspect
import json
from copy import deepcopy
from dataclasses import fields, replace
from datetime import UTC, date, datetime
from enum import StrEnum

import pytest
from route_corpus_support import (
    imported_workbook_from_fixture,
    load_corpus_fixture,
    normalization_options_from_fixture,
)

import bus_schedule_engine
import bus_schedule_engine.side_by_side_validation as side_by_side
from bus_schedule_engine import (
    ComparisonDispositionV1,
    ComparisonRuleV1,
    ComparisonStatusV1,
    SideBySideValidationReportV1,
    SolverChoice,
    build_side_by_side_validation_report_v1,
    run_side_by_side_validation_v1,
    side_by_side_report_to_dict,
)
from bus_schedule_engine.contracts_v1 import (
    DemandConfidence,
    GenerationResultStatus,
    NormalizationOptions,
    OperatingDayType,
)
from bus_schedule_engine.contracts_v1.terminal_occupancy import (
    TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED,
    TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED,
    TERMINAL_2_OCCUPANCY_CAPACITY_EXCEEDED,
    TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED,
    TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,
)
from bus_schedule_engine.importer import ImportedWorkbook
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    RouteType,
    ScenarioParameters,
    Trip,
    VolumeType,
)
from bus_schedule_engine.optimization_service import analyze_and_optimize_schedule_v1


def _small_fixed_resource_fixture(
    *,
    combined_demand: bool = False,
) -> tuple[ImportedWorkbook, NormalizationOptions]:
    parameters = ScenarioParameters(
        route_id="M5A1-SYNTHETIC",
        route_name="Milestone 5A1 accepted solution",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=20,
        total_daily_trips=8,
        terminal_1_name="Terminal One",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=7 * 3600 + 30 * 60,
        terminal_2_name="Terminal Two",
        terminal_2_first_departure=6 * 3600 + 5 * 60,
        terminal_2_last_departure=7 * 3600 + 35 * 60,
        vehicle_capacity_passengers=100,
        target_load_factor=0.85,
        maximum_load_factor=0.90,
        time_block_minutes=60,
        minimum_layover_minutes=5,
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=f"B-{direction.value}-{index + 1:02d}",
            departure_terminal=parameters.terminal_for_direction(direction),
            direction=direction,
            departure_seconds=departure_minutes * 60,
            arrival_seconds=(departure_minutes + 20) * 60,
        )
        for direction, departures in (
            (Direction.TERMINAL_1_TO_2, (360, 375, 420, 450)),
            (Direction.TERMINAL_2_TO_1, (365, 395, 425, 455)),
        )
        for index, departure_minutes in enumerate(departures)
    ]
    directions = (
        (Direction.COMBINED,)
        if combined_demand
        else (Direction.TERMINAL_1_TO_2, Direction.TERMINAL_2_TO_1)
    )
    demand = [
        DemandRecord(
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 7),
            observation_days=1,
            block_start_seconds=block_start * 60,
            block_end_seconds=(block_start + 60) * 60,
            direction=direction,
            passenger_volume=(340 if combined_demand else 170),
            volume_type=VolumeType.AVERAGE_DAY,
        )
        for direction in directions
        for block_start in (360, 420)
    ]
    imported = ImportedWorkbook(
        parameters_a=replace(parameters),
        trips_a=[
            replace(trip, scenario="A", trip_id=trip.trip_id.replace("B-", "A-")) for trip in trips
        ],
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )
    options = NormalizationOptions(
        source_id="m5a1-synthetic",
        imported_at=datetime(2026, 7, 27, 8, 0, tzinfo=UTC),
        operating_day_type_a=OperatingDayType.WEEKDAY,
        operating_day_type_b=OperatingDayType.WEEKDAY,
        available_fleet_limit_a=4,
        available_fleet_limit_b=4,
        demand_confidence=DemandConfidence.HIGH,
    )
    return imported, options


def _with_occupancy_limits(
    imported: ImportedWorkbook,
    *,
    terminal_1: int | None,
    terminal_2: int | None,
) -> ImportedWorkbook:
    return replace(
        imported,
        parameters_b=replace(
            imported.parameters_b,
            terminal_1_max_occupancy_vehicles=terminal_1,
            terminal_2_max_occupancy_vehicles=terminal_2,
        ),
    )


@pytest.fixture(scope="module")
def accepted_report() -> SideBySideValidationReportV1:
    imported, options = _small_fixed_resource_fixture()
    return run_side_by_side_validation_v1(imported, options)


@pytest.fixture(scope="module")
def occupancy_reports() -> dict[str, SideBySideValidationReportV1]:
    configurations = {
        "neither": (None, None),
        "both_pass": (10, 10),
        "terminal_1_pass": (10, None),
        "terminal_2_pass": (None, 10),
        "terminal_1_fail": (1, None),
        "terminal_2_fail": (None, 1),
        "both_fail": (1, 1),
    }
    reports: dict[str, SideBySideValidationReportV1] = {}
    for name, (terminal_1, terminal_2) in configurations.items():
        imported, options = _small_fixed_resource_fixture()
        reports[name] = run_side_by_side_validation_v1(
            _with_occupancy_limits(
                imported,
                terminal_1=terminal_1,
                terminal_2=terminal_2,
            ),
            options,
        )
    return reports


@pytest.fixture(scope="module")
def alpha_report() -> SideBySideValidationReportV1:
    fixture = load_corpus_fixture("corpus_alpha_80.json")
    return run_side_by_side_validation_v1(
        imported_workbook_from_fixture(fixture),
        normalization_options_from_fixture(fixture),
    )


@pytest.fixture(scope="module")
def beta_report() -> SideBySideValidationReportV1:
    fixture = load_corpus_fixture("corpus_beta_46.json")
    return run_side_by_side_validation_v1(
        imported_workbook_from_fixture(fixture),
        normalization_options_from_fixture(fixture),
    )


def _comparison(
    report: SideBySideValidationReportV1,
    fact_code: str,
):
    return next(record for record in report.comparisons if record.fact_code == fact_code)


def _rebuild_report(
    report: SideBySideValidationReportV1,
    *,
    legacy=None,
    unified=None,
) -> SideBySideValidationReportV1:
    return side_by_side._report(
        legacy or report.legacy_snapshot,
        unified or report.unified_snapshot,
    )


def test_required_baseline_api_imports_and_signature() -> None:
    assert (
        bus_schedule_engine.build_side_by_side_validation_report_v1
        is build_side_by_side_validation_report_v1
    )
    assert bus_schedule_engine.run_side_by_side_validation_v1 is run_side_by_side_validation_v1
    assert bus_schedule_engine.side_by_side_report_to_dict is side_by_side_report_to_dict
    signature = inspect.signature(run_side_by_side_validation_v1)
    assert list(signature.parameters) == [
        "imported",
        "normalization_options",
        "solver_choice",
        "evaluation_policy",
        "decision_policy",
        "repeatability_evidence",
        "heuristic_config",
        "solver_policy",
    ]
    assert signature.parameters["solver_choice"].default == SolverChoice.HEURISTIC


def test_pure_builder_matches_runner_without_invoking_either_execution_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _small_fixed_resource_fixture()
    legacy_bundle = side_by_side.run_analysis(deepcopy(imported))
    unified_result = analyze_and_optimize_schedule_v1(deepcopy(imported), options)
    expected = run_side_by_side_validation_v1(imported, options)

    def forbidden(*args, **kwargs):
        raise AssertionError("pure report building must not run an analysis path")

    monkeypatch.setattr(side_by_side, "run_analysis", forbidden)
    monkeypatch.setattr(side_by_side, "analyze_and_optimize_schedule_v1", forbidden)

    report = build_side_by_side_validation_report_v1(
        legacy_bundle,
        unified_result,
    )

    assert report == expected
    assert report.legacy_snapshot.terminal_occupancy_status == (
        expected.legacy_snapshot.terminal_occupancy_status
    )
    assert report.unified_snapshot.terminal_occupancy_issue_codes == (
        expected.unified_snapshot.terminal_occupancy_issue_codes
    )
    assert report.blocking_discrepancy_codes == expected.blocking_discrepancy_codes
    assert report.expert_review_required_codes == expected.expert_review_required_codes
    assert report.informational_codes == expected.informational_codes


def test_models_are_frozen_slotted_and_enums_are_strings() -> None:
    model_types = (
        side_by_side.TimetableTripSnapshotV1,
        side_by_side.TimetableSnapshotV1,
        side_by_side.LegacyPathSnapshotV1,
        side_by_side.UnifiedPathSnapshotV1,
        side_by_side.FactComparisonRecordV1,
        side_by_side.SideBySideValidationReportV1,
    )
    assert all(model.__dataclass_params__.frozen for model in model_types)
    assert all("__slots__" in model.__dict__ for model in model_types)
    assert issubclass(ComparisonRuleV1, StrEnum)
    assert tuple(item.value for item in ComparisonRuleV1) == (
        "MUST_MATCH",
        "REVIEW_IF_DIFFERENT",
        "NOT_COMPARABLE",
    )


def test_original_imported_workbook_is_unchanged() -> None:
    imported, options = _small_fixed_resource_fixture()
    before = deepcopy(imported)

    run_side_by_side_validation_v1(imported, options)

    assert imported == before


def test_legacy_and_unified_paths_receive_separate_isolated_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _small_fixed_resource_fixture()
    received: list[ImportedWorkbook] = []
    real_legacy = side_by_side.run_analysis
    real_unified = side_by_side.analyze_and_optimize_schedule_v1

    def legacy_spy(value):
        received.append(value)
        return real_legacy(value)

    def unified_spy(value, normalization_options, **kwargs):
        received.append(value)
        return real_unified(value, normalization_options, **kwargs)

    monkeypatch.setattr(side_by_side, "run_analysis", legacy_spy)
    monkeypatch.setattr(side_by_side, "analyze_and_optimize_schedule_v1", unified_spy)

    run_side_by_side_validation_v1(imported, options)

    assert len(received) == 2
    assert received[0] is not imported
    assert received[1] is not imported
    assert received[0] is not received[1]
    assert received[0].trips_b is not received[1].trips_b
    assert received[0].trips_b[0] is not received[1].trips_b[0]


def test_adapter_invokes_no_chart_xlsx_or_ui_artifact_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bus_schedule_engine import comparison_exporter, diagram, excel_exporter, ui_utils

    imported, options = _small_fixed_resource_fixture()

    def forbidden(*args, **kwargs):
        raise AssertionError("artifact code must not be invoked")

    for module, name in (
        (diagram, "build_comparison_diagram"),
        (diagram, "build_departure_detail_diagram"),
        (diagram, "diagram_png_bytes"),
        (excel_exporter, "export_results"),
        (comparison_exporter, "export_bc_comparison"),
        (ui_utils, "run_and_build_artifacts"),
    ):
        monkeypatch.setattr(module, name, forbidden)

    run_side_by_side_validation_v1(imported, options)


def test_adapter_writes_no_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pathlib import Path

    imported, options = _small_fixed_resource_fixture()

    def forbidden(*args, **kwargs):
        raise AssertionError("side-by-side adapter must not write files")

    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)

    run_side_by_side_validation_v1(imported, options)


def test_repeated_reports_and_ordering_are_deterministic() -> None:
    imported, options = _small_fixed_resource_fixture()

    first = run_side_by_side_validation_v1(imported, options)
    second = run_side_by_side_validation_v1(imported, options)

    assert first == second
    first_order = tuple(
        (record.category.value, record.fact_code, record.reason_code)
        for record in first.comparisons
    )
    second_order = tuple(
        (record.category.value, record.fact_code, record.reason_code)
        for record in second.comparisons
    )
    assert first_order == second_order
    assert len({record.fact_code for record in first.comparisons}) == len(first.comparisons)


def test_serialization_is_deterministic_json_compatible(
    accepted_report: SideBySideValidationReportV1,
) -> None:
    first = side_by_side_report_to_dict(accepted_report)
    second = side_by_side_report_to_dict(accepted_report)

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["legacy_snapshot"]["path_identifier"] == "LEGACY_MVP"
    assert first["unified_snapshot"]["path_identifier"] == "UNIFIED_CONTRACT_V1"
    assert "solution_fingerprint" in first["unified_snapshot"]


@pytest.mark.parametrize(
    "fact_code",
    (
        "SCENARIO_B_ROUTE_ID",
        "SCENARIO_B_TOTAL_TRIP_COUNT",
        "SCENARIO_B_DIRECTIONAL_TRIP_COUNTS",
        "SCENARIO_B_FIRST_DEPARTURES",
        "SCENARIO_B_LAST_DEPARTURES",
        "SCENARIO_B_SOURCE_TRIP_IDS",
        "SCENARIO_B_TRIP_RUNTIMES",
    ),
)
def test_scenario_b_source_facts_match(
    accepted_report: SideBySideValidationReportV1,
    fact_code: str,
) -> None:
    record = _comparison(accepted_report, fact_code)
    assert record.comparison_rule == ComparisonRuleV1.MUST_MATCH
    assert record.comparison_status == ComparisonStatusV1.MATCH
    assert record.disposition == ComparisonDispositionV1.INFORMATIONAL


@pytest.mark.parametrize(
    ("fact_code", "mutator"),
    (
        (
            "SCENARIO_B_TOTAL_TRIP_COUNT",
            lambda timetable: replace(timetable, trip_count=timetable.trip_count + 1),
        ),
        (
            "SCENARIO_B_FIRST_DEPARTURES",
            lambda timetable: replace(
                timetable,
                first_departures_by_terminal=(
                    (
                        timetable.first_departures_by_terminal[0][0],
                        timetable.first_departures_by_terminal[0][1] + 60,
                    ),
                    timetable.first_departures_by_terminal[1],
                ),
            ),
        ),
        (
            "SCENARIO_B_TRIP_RUNTIMES",
            lambda timetable: replace(
                timetable,
                trips=(
                    replace(
                        timetable.trips[0],
                        runtime_seconds=timetable.trips[0].runtime_seconds + 60,
                    ),
                    *timetable.trips[1:],
                ),
            ),
        ),
    ),
)
def test_deliberate_b_source_mismatch_blocks_cutover(
    accepted_report: SideBySideValidationReportV1,
    fact_code: str,
    mutator,
) -> None:
    unified = accepted_report.unified_snapshot
    changed = replace(unified, scenario_b=mutator(unified.scenario_b))
    report = _rebuild_report(accepted_report, unified=changed)
    record = _comparison(report, fact_code)

    assert record.comparison_status == ComparisonStatusV1.DIFFERENT
    assert record.disposition == ComparisonDispositionV1.BLOCKS_CUTOVER
    assert record.reason_code in report.blocking_discrepancy_codes
    assert report.has_blocking_discrepancies is True
    assert report.requires_expert_review is True


def test_validation_issue_differences_require_review(
    accepted_report: SideBySideValidationReportV1,
) -> None:
    unified = replace(
        accepted_report.unified_snapshot,
        validation_issue_codes=("SYNTHETIC_DIFFERENCE",),
    )
    report = _rebuild_report(accepted_report, unified=unified)
    record = _comparison(report, "SCENARIO_B_VALIDATION_ISSUE_CODES")

    assert record.disposition == ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED
    assert record.reason_code in report.expert_review_required_codes


def test_legacy_weighted_score_is_not_compared_to_unified_vector(
    accepted_report: SideBySideValidationReportV1,
) -> None:
    weighted = _comparison(accepted_report, "LEGACY_WEIGHTED_SCORE")
    vector = _comparison(accepted_report, "UNIFIED_OBJECTIVE_VECTOR")

    assert weighted.comparison_rule == ComparisonRuleV1.NOT_COMPARABLE
    assert weighted.unified_value is None
    assert vector.comparison_rule == ComparisonRuleV1.NOT_COMPARABLE
    assert vector.legacy_value is None


def test_combined_demand_is_not_fabricated_into_directional_demand() -> None:
    imported, options = _small_fixed_resource_fixture(combined_demand=True)
    report = run_side_by_side_validation_v1(imported, options)

    assert {block.direction for block in report.legacy_snapshot.demand_authority.blocks} == {
        "combined"
    }
    assert {block.direction for block in report.unified_snapshot.demand_authority.blocks} == {
        "combined"
    }
    assert report.unified_snapshot.demand_authority.directional_generation_supported is False


def test_demand_grain_difference_is_explicit(
    accepted_report: SideBySideValidationReportV1,
) -> None:
    unified = accepted_report.unified_snapshot
    authority = unified.demand_authority
    changed_block = replace(
        authority.blocks[0],
        block_end_seconds=authority.blocks[0].block_end_seconds - 60,
    )
    changed_authority = replace(
        authority,
        blocks=(changed_block, *authority.blocks[1:]),
    )
    report = _rebuild_report(
        accepted_report,
        unified=replace(unified, demand_authority=changed_authority),
    )

    grain = _comparison(report, "DEMAND_BLOCK_GRAIN")
    values = _comparison(report, "DEMAND_BLOCK_VALUES")
    assert grain.reason_code == "DEMAND_BLOCK_GRAIN_DIFFERS"
    assert grain.disposition == ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED
    assert values.comparison_rule == ComparisonRuleV1.NOT_COMPARABLE


def test_missing_unified_accepted_c_never_substitutes_b(
    alpha_report: SideBySideValidationReportV1,
) -> None:
    unified = alpha_report.unified_snapshot
    assert unified.scenario_b is not None
    assert unified.scenario_c is None
    assert unified.solution_fingerprint is None
    assert unified.b_to_c_trace == ()


def test_rejected_or_raw_candidate_is_not_exposed_as_unified_c(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _small_fixed_resource_fixture()
    real_result = analyze_and_optimize_schedule_v1(imported, options)
    assert real_result.recommended_outcome is not None
    rejected = replace(
        real_result.recommended_outcome,
        result_status=GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR,
    )
    rejected_result = replace(
        real_result,
        heuristic_outcome=rejected,
        recommended_outcome=rejected,
    )
    monkeypatch.setattr(
        side_by_side,
        "analyze_and_optimize_schedule_v1",
        lambda *args, **kwargs: rejected_result,
    )

    report = run_side_by_side_validation_v1(imported, options)

    assert report.unified_snapshot.heuristic_outcome_status == (
        GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR.value
    )
    assert report.unified_snapshot.scenario_c is None
    assert report.unified_snapshot.solution_fingerprint is None


def test_legacy_only_c_has_explicit_review_code(
    alpha_report: SideBySideValidationReportV1,
) -> None:
    record = _comparison(alpha_report, "SCENARIO_C_EXISTENCE")
    assert alpha_report.legacy_snapshot.scenario_c is not None
    assert record.reason_code == "LEGACY_C_WITHOUT_UNIFIED_AUTHORITY"
    assert record.disposition == ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED


def test_unified_only_c_has_explicit_review_code(
    accepted_report: SideBySideValidationReportV1,
) -> None:
    legacy = replace(
        accepted_report.legacy_snapshot,
        scenario_c=None,
        scenario_c_authority=None,
        c_to_b_trace=(),
        scenario_c_generation_status=None,
        scenario_c_minimum_required_fleet=None,
        scenario_c_shifted_trip_count=None,
        scenario_c_total_absolute_shift_seconds=None,
        scenario_c_maximum_absolute_shift_seconds=None,
        scenario_c_headway_regimes=(),
    )
    report = _rebuild_report(accepted_report, legacy=legacy)
    record = _comparison(report, "SCENARIO_C_EXISTENCE")

    assert record.reason_code == "UNIFIED_ACCEPTED_C_WITHOUT_LEGACY_C"
    assert record.disposition == ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED


@pytest.mark.parametrize(
    "fact_code",
    (
        "SCENARIO_C_SOURCE_MAPPING",
        "SCENARIO_C_PER_SOURCE_DEPARTURE_TIMES",
        "SCENARIO_C_PER_SOURCE_RUNTIMES",
    ),
)
def test_both_c_paths_reconcile_by_source_trip_id(
    accepted_report: SideBySideValidationReportV1,
    fact_code: str,
) -> None:
    assert accepted_report.legacy_snapshot.scenario_c_authority == "LEGACY_DIAGNOSTIC_ONLY"
    assert accepted_report.unified_snapshot.scenario_c_authority == (
        "CONTRACT_V1_INDEPENDENTLY_VALIDATED"
    )
    record = _comparison(accepted_report, fact_code)
    assert record.comparison_status == ComparisonStatusV1.MATCH


@pytest.mark.parametrize(
    ("fact_code", "attribute"),
    (
        ("SCENARIO_C_PER_SOURCE_DEPARTURE_TIMES", "departure_time_seconds"),
        ("SCENARIO_C_PER_SOURCE_RUNTIMES", "runtime_seconds"),
    ),
)
def test_different_c_trip_fact_requires_review(
    accepted_report: SideBySideValidationReportV1,
    fact_code: str,
    attribute: str,
) -> None:
    unified = accepted_report.unified_snapshot
    assert unified.scenario_c is not None
    first = unified.scenario_c.trips[0]
    changed_trip = replace(first, **{attribute: getattr(first, attribute) + 60})
    changed_timetable = replace(
        unified.scenario_c,
        trips=(changed_trip, *unified.scenario_c.trips[1:]),
    )
    report = _rebuild_report(
        accepted_report,
        unified=replace(unified, scenario_c=changed_timetable),
    )
    record = _comparison(report, fact_code)

    assert record.comparison_status == ComparisonStatusV1.DIFFERENT
    assert record.disposition == ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED


def test_minimum_fleet_difference_requires_review(
    accepted_report: SideBySideValidationReportV1,
) -> None:
    unified = replace(
        accepted_report.unified_snapshot,
        minimum_required_fleet=accepted_report.unified_snapshot.minimum_required_fleet + 1,
    )
    report = _rebuild_report(accepted_report, unified=unified)
    record = _comparison(report, "SCENARIO_B_MINIMUM_REQUIRED_FLEET")
    assert record.disposition == ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED


def test_initial_positioning_remains_unified_only(
    accepted_report: SideBySideValidationReportV1,
) -> None:
    for fact_code in (
        "UNIFIED_INITIAL_FLEET_TERMINAL_1",
        "UNIFIED_INITIAL_FLEET_TERMINAL_2",
    ):
        record = _comparison(accepted_report, fact_code)
        assert record.legacy_value is None
        assert record.comparison_status == ComparisonStatusV1.UNIFIED_ONLY
        assert record.disposition == ComparisonDispositionV1.INFORMATIONAL


def test_missing_terminal_occupancy_limits_remain_not_evaluated(
    occupancy_reports: dict[str, SideBySideValidationReportV1],
) -> None:
    unified = occupancy_reports["neither"].unified_snapshot
    assert unified.terminal_occupancy_limits == (
        ("terminal_1", None),
        ("terminal_2", None),
    )
    assert unified.terminal_occupancy_terminal_statuses == (
        ("terminal_1", "NOT_EVALUATED"),
        ("terminal_2", "NOT_EVALUATED"),
    )
    assert unified.terminal_occupancy_status == "NOT_EVALUATED"
    assert unified.terminal_occupancy_issue_codes == (TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,)
    assert unified.terminal_occupancy_limits != (
        ("terminal_1", unified.recommended_initial_fleet_terminal_1),
        ("terminal_2", unified.recommended_initial_fleet_terminal_2),
    )


def test_both_terminal_occupancy_limits_must_pass_for_aggregate_pass(
    occupancy_reports: dict[str, SideBySideValidationReportV1],
) -> None:
    unified = occupancy_reports["both_pass"].unified_snapshot
    assert unified.terminal_occupancy_limits == (
        ("terminal_1", 10),
        ("terminal_2", 10),
    )
    assert unified.terminal_occupancy_terminal_statuses == (
        ("terminal_1", "PASS"),
        ("terminal_2", "PASS"),
    )
    assert unified.terminal_occupancy_status == "PASS"
    assert unified.terminal_occupancy_issue_codes == ()


@pytest.mark.parametrize(
    ("report_name", "failed_terminal", "exceeded_code"),
    (
        (
            "terminal_1_fail",
            "terminal_1",
            TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED,
        ),
        (
            "terminal_2_fail",
            "terminal_2",
            TERMINAL_2_OCCUPANCY_CAPACITY_EXCEEDED,
        ),
        (
            "both_fail",
            "terminal_1",
            TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED,
        ),
        (
            "both_fail",
            "terminal_2",
            TERMINAL_2_OCCUPANCY_CAPACITY_EXCEEDED,
        ),
    ),
)
def test_terminal_occupancy_overflow_produces_terminal_and_aggregate_fail(
    occupancy_reports: dict[str, SideBySideValidationReportV1],
    report_name: str,
    failed_terminal: str,
    exceeded_code: str,
) -> None:
    unified = occupancy_reports[report_name].unified_snapshot
    statuses = dict(unified.terminal_occupancy_terminal_statuses)
    assert statuses[failed_terminal] == "FAIL"
    assert unified.terminal_occupancy_status == "FAIL"
    assert exceeded_code in unified.terminal_occupancy_issue_codes


@pytest.mark.parametrize(
    (
        "report_name",
        "passing_terminal",
        "missing_terminal",
        "not_evaluated_code",
    ),
    (
        (
            "terminal_1_pass",
            "terminal_1",
            "terminal_2",
            TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED,
        ),
        (
            "terminal_2_pass",
            "terminal_2",
            "terminal_1",
            TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED,
        ),
    ),
)
def test_partial_terminal_occupancy_is_explicit_and_retains_limitation(
    occupancy_reports: dict[str, SideBySideValidationReportV1],
    report_name: str,
    passing_terminal: str,
    missing_terminal: str,
    not_evaluated_code: str,
) -> None:
    unified = occupancy_reports[report_name].unified_snapshot
    statuses = dict(unified.terminal_occupancy_terminal_statuses)
    assert statuses[passing_terminal] == "PASS"
    assert statuses[missing_terminal] == "NOT_EVALUATED"
    assert unified.terminal_occupancy_status == "PARTIALLY_EVALUATED"
    assert not_evaluated_code in unified.terminal_occupancy_issue_codes


@pytest.mark.parametrize(
    ("report_name", "failed_terminal", "missing_terminal"),
    (
        ("terminal_1_fail", "terminal_1", "terminal_2"),
        ("terminal_2_fail", "terminal_2", "terminal_1"),
    ),
)
def test_partial_terminal_overflow_is_fail_not_partial(
    occupancy_reports: dict[str, SideBySideValidationReportV1],
    report_name: str,
    failed_terminal: str,
    missing_terminal: str,
) -> None:
    unified = occupancy_reports[report_name].unified_snapshot
    statuses = dict(unified.terminal_occupancy_terminal_statuses)
    assert statuses[failed_terminal] == "FAIL"
    assert statuses[missing_terminal] == "NOT_EVALUATED"
    assert unified.terminal_occupancy_status == "FAIL"


def test_no_partial_occupancy_configuration_can_report_pass(
    occupancy_reports: dict[str, SideBySideValidationReportV1],
) -> None:
    partial_names = (
        "terminal_1_pass",
        "terminal_2_pass",
        "terminal_1_fail",
        "terminal_2_fail",
    )
    assert all(
        occupancy_reports[name].unified_snapshot.terminal_occupancy_status != "PASS"
        for name in partial_names
    )


def test_occupancy_comparison_evidence_is_explicit_and_deterministic(
    occupancy_reports: dict[str, SideBySideValidationReportV1],
) -> None:
    report = occupancy_reports["terminal_1_pass"]
    imported, options = _small_fixed_resource_fixture()
    repeated = run_side_by_side_validation_v1(
        _with_occupancy_limits(imported, terminal_1=10, terminal_2=None),
        options,
    )
    cross_path = _comparison(report, "SCENARIO_B_TERMINAL_OCCUPANCY_STATUS")
    by_terminal = _comparison(report, "UNIFIED_TERMINAL_OCCUPANCY_BY_TERMINAL")
    issue_codes = _comparison(report, "UNIFIED_TERMINAL_OCCUPANCY_ISSUE_CODES")

    assert cross_path.comparison_rule == ComparisonRuleV1.REVIEW_IF_DIFFERENT
    assert cross_path.disposition == ComparisonDispositionV1.EXPERT_REVIEW_REQUIRED
    for record in (by_terminal, issue_codes):
        assert record.comparison_rule == ComparisonRuleV1.NOT_COMPARABLE
        assert record.comparison_status == ComparisonStatusV1.UNIFIED_ONLY
        assert record.disposition == ComparisonDispositionV1.INFORMATIONAL
    assert by_terminal.unified_value == (
        ("terminal_1", "PASS"),
        ("terminal_2", "NOT_EVALUATED"),
    )
    assert issue_codes.unified_value == (TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED,)
    assert report == repeated
    assert by_terminal == _comparison(repeated, "UNIFIED_TERMINAL_OCCUPANCY_BY_TERMINAL")
    assert issue_codes == _comparison(repeated, "UNIFIED_TERMINAL_OCCUPANCY_ISSUE_CODES")


def test_per_terminal_occupancy_fields_serialize_deterministically(
    occupancy_reports: dict[str, SideBySideValidationReportV1],
) -> None:
    report = occupancy_reports["terminal_2_pass"]
    first = side_by_side_report_to_dict(report)
    second = side_by_side_report_to_dict(report)
    unified = first["unified_snapshot"]

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert unified["terminal_occupancy_terminal_statuses"] == [
        ["terminal_1", "NOT_EVALUATED"],
        ["terminal_2", "PASS"],
    ]
    assert unified["terminal_occupancy_issue_codes"] == [
        TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED
    ]


def test_alpha_natural_policy_remains_solver_free_and_has_no_unified_c(
    alpha_report: SideBySideValidationReportV1,
) -> None:
    unified = alpha_report.unified_snapshot
    assert unified.demand_confidence == DemandConfidence.LOW.value
    assert unified.adjustment_decision == "INSUFFICIENT_DATA"
    assert unified.solver_attempted is False
    assert unified.scenario_c is None
    assert unified.comparison_objective_names is None
    assert unified.comparison_recommended_solver is None


def test_beta_preserves_gap_and_has_no_solver_vector_or_recommendation(
    beta_report: SideBySideValidationReportV1,
) -> None:
    unified = beta_report.unified_snapshot
    gaps = unified.demand_authority.explicit_temporal_gaps
    assert gaps is not None
    assert any(
        direction == "outbound" and start == 17 * 3600 and end == 18 * 3600
        for _code, direction, start, end in gaps
    )
    assert unified.adjustment_decision == "INSUFFICIENT_DATA"
    assert unified.solver_attempted is False
    assert unified.comparison_objective_names is None
    assert unified.comparison_heuristic_vector is None
    assert unified.comparison_ortools_vector is None
    assert unified.comparison_recommended_solver is None


def test_synthetic_fixture_produces_independently_accepted_unified_c(
    accepted_report: SideBySideValidationReportV1,
) -> None:
    unified = accepted_report.unified_snapshot
    assert unified.solver_attempted is True
    assert unified.heuristic_outcome_status == GenerationResultStatus.SOLUTION_ACCEPTED.value
    assert unified.scenario_c is not None
    assert unified.solution_fingerprint is not None
    assert len(unified.solution_fingerprint) == 64
    assert len(unified.b_to_c_trace) == unified.scenario_b.trip_count
    assert {source for source, _trip in unified.b_to_c_trace} == {
        trip.trip_id for trip in unified.scenario_b.trips
    }
    assert _comparison(accepted_report, "SCENARIO_C_EXISTENCE").comparison_status == (
        ComparisonStatusV1.MATCH
    )


def test_report_has_no_automatic_approval_property(
    accepted_report: SideBySideValidationReportV1,
) -> None:
    names = {field.name for field in fields(SideBySideValidationReportV1)}
    assert "automatically_approved" not in names
    assert "cutover_authorized" not in names
    assert "readiness_score" not in names
    assert accepted_report.has_blocking_discrepancies is False
    assert accepted_report.requires_expert_review is True


@pytest.mark.parametrize(
    (
        "blocking_codes",
        "review_codes",
        "has_blocking",
        "requires_review",
    ),
    (
        ((), ("REVIEW_ONLY",), False, True),
        (("BLOCKING_ONLY",), (), True, True),
        ((), (), False, False),
    ),
)
def test_blocking_and_expert_review_properties_remain_distinct(
    accepted_report: SideBySideValidationReportV1,
    blocking_codes: tuple[str, ...],
    review_codes: tuple[str, ...],
    has_blocking: bool,
    requires_review: bool,
) -> None:
    report = replace(
        accepted_report,
        blocking_discrepancy_codes=blocking_codes,
        expert_review_required_codes=review_codes,
    )
    assert report.blocking_discrepancy_codes == blocking_codes
    assert report.expert_review_required_codes == review_codes
    assert report.has_blocking_discrepancies is has_blocking
    assert report.requires_expert_review is requires_review
