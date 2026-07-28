"""Test-only characterization constructors for Milestone 5A2B."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

from route_corpus_support import (
    imported_workbook_from_fixture,
    load_corpus_fixture,
    normalization_options_from_fixture,
)

import bus_schedule_engine.side_by_side_validation as side_by_side
from bus_schedule_engine.contracts_v1 import (
    DemandConfidence,
    GenerationResultStatus,
    NormalizationOptions,
    OperatingDayType,
    RejectedCandidateDiagnosticV1,
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
from bus_schedule_engine.optimization_service import (
    BusScheduleOptimizationResult,
    SolverChoice,
    analyze_and_optimize_schedule_v1,
)
from bus_schedule_engine.side_by_side_validation import (
    SideBySideValidationReportV1,
    run_side_by_side_validation_v1,
)


def small_fixed_resource_fixture(
    *,
    combined_demand: bool = False,
    terminal_1_occupancy: int | None = None,
    terminal_2_occupancy: int | None = None,
) -> tuple[ImportedWorkbook, NormalizationOptions]:
    parameters = ScenarioParameters(
        route_id="M5A2B-SYNTHETIC",
        route_name="Milestone 5A2B accepted solution",
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
        terminal_1_max_occupancy_vehicles=terminal_1_occupancy,
        terminal_2_max_occupancy_vehicles=terminal_2_occupancy,
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
        source_id="m5a2b-synthetic",
        imported_at=datetime(2026, 7, 28, 8, 0, tzinfo=UTC),
        operating_day_type_a=OperatingDayType.WEEKDAY,
        operating_day_type_b=OperatingDayType.WEEKDAY,
        available_fleet_limit_a=4,
        available_fleet_limit_b=4,
        demand_confidence=DemandConfidence.HIGH,
    )
    return imported, options


def build_result_and_report(
    *,
    solver_choice: SolverChoice = SolverChoice.HEURISTIC,
    combined_demand: bool = False,
    terminal_1_occupancy: int | None = None,
    terminal_2_occupancy: int | None = None,
) -> tuple[BusScheduleOptimizationResult, SideBySideValidationReportV1]:
    imported, options = small_fixed_resource_fixture(
        combined_demand=combined_demand,
        terminal_1_occupancy=terminal_1_occupancy,
        terminal_2_occupancy=terminal_2_occupancy,
    )
    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=solver_choice,
    )
    report = run_side_by_side_validation_v1(
        imported,
        options,
        solver_choice=solver_choice,
    )
    return result, report


def build_corpus_result_and_report(
    filename: str,
) -> tuple[BusScheduleOptimizationResult, SideBySideValidationReportV1]:
    fixture = load_corpus_fixture(filename)
    imported = imported_workbook_from_fixture(fixture)
    options = normalization_options_from_fixture(fixture)
    return (
        analyze_and_optimize_schedule_v1(imported, options),
        run_side_by_side_validation_v1(imported, options),
    )


def rejected_result_and_report() -> tuple[
    BusScheduleOptimizationResult,
    SideBySideValidationReportV1,
]:
    result, accepted_report = build_result_and_report()
    outcome = result.recommended_outcome
    assert outcome is not None
    rejected = replace(
        outcome,
        result_status=GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR,
        diagnostic_candidate=RejectedCandidateDiagnosticV1(
            candidate_fingerprint="rejected-diagnostic-candidate",
            rejection_codes=("SYNTHETIC_DOMAIN_REJECTION",),
            summary="Synthetic rejection retained for presentation characterization.",
        ),
    )
    rejected_result = replace(
        result,
        heuristic_outcome=rejected,
        recommended_outcome=rejected,
    )
    unified = side_by_side._build_unified_snapshot(rejected_result)
    rejected_report = side_by_side._report(
        accepted_report.legacy_snapshot,
        unified,
    )
    return rejected_result, rejected_report
