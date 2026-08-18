from __future__ import annotations

import ast
import inspect
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import bus_schedule_engine.optimization_service as optimization_service
from bus_schedule_engine import (
    BusScheduleOptimizationResult,
    OptimizationAction,
    OptimizationExecutionErrorV1,
    OptimizationExecutionStageV1,
    SolverChoice,
    analyze_and_optimize_schedule_v1,
    select_optimization_action,
)
from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.contracts_v1 import (
    BDisposition,
    ContractDirection,
    ContractValidationError,
    DemandConfidence,
    GenerationResultStatus,
    HeuristicScheduleSolverAdapter,
    NativeSolverStatus,
    NormalizationOptions,
    OperatingDayType,
    RepeatabilityDayEvidenceV1,
    RepeatabilityEvidenceV1,
    ScenarioBEvaluationPolicyV1,
    ScheduleGenerationOutcomeV1,
    ServiceAdjustmentDecisionPolicyV1,
    ServiceAdjustmentDecisionV1,
    SolverExecutionStatus,
    build_service_adjustment_evaluation_context_v1,
    evaluate_scenario_b_v1,
    evaluate_service_adjustment_need_v1,
    normalize_imported_workbook_v1,
    solver_orchestration,
)
from bus_schedule_engine.contracts_v1 import (
    build_heuristic_schedule_request_v1 as canonical_heuristic_request,
)
from bus_schedule_engine.contracts_v1 import (
    run_schedule_solver_v1 as canonical_solver_runner,
)
from bus_schedule_engine.excel_exporter import create_input_template
from bus_schedule_engine.importer import ImportedWorkbook, import_workbook
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    RouteType,
    ScenarioParameters,
    Trip,
    VolumeType,
)
from bus_schedule_engine.service import run_analysis

EXPECTED_ACTIONS = {
    ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA: OptimizationAction.INSUFFICIENT_DATA,
    ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED: (
        OptimizationAction.TECHNICAL_CORRECTION_REQUIRED
    ),
    ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS: (
        OptimizationAction.TRIP_INCREASE_RECOMMENDED
    ),
    ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS: (
        OptimizationAction.FIXED_RESOURCE_REDISTRIBUTION
    ),
    ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS: (OptimizationAction.TRIP_REDUCTION_RECOMMENDED),
    ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES: (
        OptimizationAction.FIXED_RESOURCE_RESPACE
    ),
    ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE: OptimizationAction.NO_CHANGE,
}

NO_SOLVER_DECISIONS = (
    ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE,
    ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS,
    ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS,
    ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED,
    ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA,
)


def test_execution_stage_model_includes_application_boundaries() -> None:
    assert tuple(stage.value for stage in OptimizationExecutionStageV1) == (
        "NORMALIZATION",
        "EVALUATION",
        "HEURISTIC_SOLVER",
        "OR_TOOLS_SOLVER",
        "SOLVER_COMPARISON",
        "PRESENTATION",
        "ARTIFACTS",
    )


def _fixture(
    *,
    demand_mode: str = "directional",
    incomplete_directional: bool = False,
) -> tuple[ImportedWorkbook, NormalizationOptions]:
    parameters = ScenarioParameters(
        route_id="OPT-SERVICE-01",
        route_name="Unified optimization service fixture",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=30,
        total_daily_trips=26,
        terminal_1_name="Terminal East",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=12 * 3600,
        terminal_2_name="Terminal West",
        terminal_2_first_departure=6 * 3600 + 15 * 60,
        terminal_2_last_departure=12 * 3600 + 15 * 60,
        vehicle_capacity_passengers=60,
        target_load_factor=0.85,
        maximum_load_factor=0.90,
        time_block_minutes=60,
        minimum_layover_minutes=5,
    )
    trips: list[Trip] = []
    for direction, offset in (
        (Direction.TERMINAL_1_TO_2, 0),
        (Direction.TERMINAL_2_TO_1, 15),
    ):
        for index in range(13):
            departure = (360 + offset + index * 30) * 60
            trips.append(
                Trip(
                    scenario="B",
                    trip_id=f"B-{direction.value}-{index + 1:02d}",
                    departure_terminal=parameters.terminal_for_direction(direction),
                    direction=direction,
                    departure_seconds=departure,
                    arrival_seconds=departure + 30 * 60,
                )
            )

    volumes = (150, 150, 30, 30, 150, 150, 0)
    if demand_mode == "combined":
        demand_directions = (Direction.COMBINED,)
    elif demand_mode == "none":
        demand_directions = ()
    else:
        demand_directions = (
            Direction.TERMINAL_1_TO_2,
            Direction.TERMINAL_2_TO_1,
        )
    demand = [
        DemandRecord(
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 7),
            observation_days=1,
            block_start_seconds=(6 + index) * 3600,
            block_end_seconds=(7 + index) * 3600,
            direction=direction,
            passenger_volume=volume * (2 if direction == Direction.COMBINED else 1),
            volume_type=VolumeType.AVERAGE_DAY,
        )
        for direction in demand_directions
        for index, volume in enumerate(volumes)
        if not (incomplete_directional and direction == Direction.TERMINAL_2_TO_1 and index >= 5)
    ]
    imported = ImportedWorkbook(
        parameters_a=replace(parameters),
        trips_a=[replace(trip, scenario="A") for trip in trips],
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )
    options = NormalizationOptions(
        source_id="optimization-service-fixture",
        imported_at=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
        operating_day_type_a=OperatingDayType.WEEKDAY,
        operating_day_type_b=OperatingDayType.WEEKDAY,
        available_fleet_limit_a=4,
        available_fleet_limit_b=4,
        demand_confidence=DemandConfidence.HIGH,
    )
    return imported, options


def _small_fixed_resource_fixture(
    *,
    irregular_timetable: bool,
    demand_profile: tuple[int, int],
) -> tuple[ImportedWorkbook, NormalizationOptions]:
    parameters = ScenarioParameters(
        route_id="OPT-SERVICE-SMALL",
        route_name="Canonical fixed-resource service fixture",
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
    outbound_times = (360, 375, 420, 450) if irregular_timetable else (360, 390, 420, 450)
    inbound_times = (365, 395, 425, 455)
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
            (Direction.TERMINAL_1_TO_2, outbound_times),
            (Direction.TERMINAL_2_TO_1, inbound_times),
        )
        for index, departure_minutes in enumerate(departures)
    ]
    demand = [
        DemandRecord(
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 7),
            observation_days=1,
            block_start_seconds=block_start * 60,
            block_end_seconds=(block_start + 60) * 60,
            direction=direction,
            passenger_volume=passenger_volume,
            volume_type=VolumeType.AVERAGE_DAY,
        )
        for direction in (
            Direction.TERMINAL_1_TO_2,
            Direction.TERMINAL_2_TO_1,
        )
        for block_start, passenger_volume in zip(
            (360, 420),
            demand_profile,
            strict=True,
        )
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
        source_id="canonical-fixed-resource-fixture",
        imported_at=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
        operating_day_type_a=OperatingDayType.WEEKDAY,
        operating_day_type_b=OperatingDayType.WEEKDAY,
        available_fleet_limit_a=4,
        available_fleet_limit_b=4,
        demand_confidence=DemandConfidence.HIGH,
    )
    return imported, options


def _canonical_assessment(
    imported: ImportedWorkbook,
    options: NormalizationOptions,
):
    normalized = normalize_imported_workbook_v1(imported, options)
    evaluation_policy = ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(normalized, evaluation_policy)
    decision_policy = ServiceAdjustmentDecisionPolicyV1(
        planning_load_factor_ceiling=evaluation_policy.planning_load_factor_ceiling,
        critical_load_factor_ceiling=evaluation_policy.critical_load_factor_ceiling,
        low_load_review_threshold=evaluation_policy.low_load_review_threshold,
        minimum_authoritative_demand_confidence=(
            evaluation_policy.minimum_authoritative_demand_confidence
        ),
    )
    context = build_service_adjustment_evaluation_context_v1(
        normalized,
        evaluation_policy,
        decision_policy,
        b_evaluation_cache=evaluation,
    )
    return evaluate_service_adjustment_need_v1(context)


def _force_decision(
    monkeypatch: pytest.MonkeyPatch,
    assessment,
    decision: ServiceAdjustmentDecisionV1,
) -> None:
    forced = replace(assessment, primary_decision=decision)
    monkeypatch.setattr(
        optimization_service,
        "evaluate_service_adjustment_need_v1",
        lambda context: forced,
    )


def _unknown_outcome() -> ScheduleGenerationOutcomeV1:
    return ScheduleGenerationOutcomeV1(
        result_status=GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT,
        execution_status=SolverExecutionStatus.COMPLETED,
        solver_status=NativeSolverStatus.UNKNOWN,
        solver_adapter="legacy_heuristic_v1",
        solve_duration_seconds=0.25,
        outcome_fingerprint="f" * 64,
        source_b_fingerprint="b" * 64,
        solution=None,
        diagnostic_candidate=None,
        explanations=("Heuristic search returned UNKNOWN.",),
        limitations=("No global infeasibility proof is available.",),
    )


def _repeatability() -> RepeatabilityEvidenceV1:
    return RepeatabilityEvidenceV1(
        days=tuple(
            RepeatabilityDayEvidenceV1(
                day_reference=f"2026-07-{index:02d}",
                fully_supported=True,
                current_daily_trips=26,
                required_daily_trips=25,
                shortage_block_count=0,
                no_service_with_demand_block_count=0,
                critical_block_count=0,
                authoritative_evidence_fingerprint=f"repeatability-{index}",
            )
            for index in range(1, 4)
        ),
        configured_minimum_valid_day_count=3,
        configured_minimum_surplus_consistency_rate=0.80,
        representative_day_type_or_provenance="weekday APC sample",
    )


@pytest.mark.parametrize(
    ("decision", "expected_action"),
    tuple(EXPECTED_ACTIONS.items()),
)
def test_every_adjustment_decision_maps_to_the_required_action(
    decision,
    expected_action,
) -> None:
    imported, options = _fixture()
    assessment = replace(
        _canonical_assessment(imported, options),
        primary_decision=decision,
    )
    before = deepcopy(assessment)

    assert select_optimization_action(assessment) == expected_action
    assert assessment == before


def test_action_selector_reads_only_the_canonical_decision() -> None:
    class DecisionOnly:
        primary_decision = ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS

        def __getattr__(self, name):  # pragma: no cover - access is the failure
            raise AssertionError(f"Unexpected assessment access: {name}")

    assert (
        select_optimization_action(DecisionOnly())
        == OptimizationAction.FIXED_RESOURCE_REDISTRIBUTION
    )


@pytest.mark.parametrize("decision", NO_SOLVER_DECISIONS)
def test_no_solver_actions_construct_no_problem_and_invoke_no_solver(
    monkeypatch: pytest.MonkeyPatch,
    decision: ServiceAdjustmentDecisionV1,
) -> None:
    imported, options = _fixture()
    _force_decision(monkeypatch, _canonical_assessment(imported, options), decision)
    calls = {"build": 0, "run": 0}

    def forbidden_build(*args, **kwargs):
        calls["build"] += 1
        raise AssertionError("No-solver action must not construct a heuristic request")

    def forbidden_run(*args, **kwargs):
        calls["run"] += 1
        raise AssertionError("No-solver action must not invoke the solver boundary")

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        forbidden_build,
    )
    monkeypatch.setattr(
        optimization_service,
        "run_schedule_solver_v1",
        forbidden_run,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert calls == {"build": 0, "run": 0}
    assert result.selected_action == EXPECTED_ACTIONS[decision]
    assert result.solver_attempted is False
    assert result.heuristic_outcome is None
    assert result.ortools_outcome is None
    assert result.comparison is None
    assert result.recommended_outcome is None
    assert result.explanations == (result.adjustment_assessment.explanation,)
    assert result.limitations == result.adjustment_assessment.limitations


def test_canonical_insufficient_data_decision_stops_before_problem_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture(demand_mode="none")

    def forbidden(*args, **kwargs):
        raise AssertionError("The service must own the insufficient-data business gate")

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        forbidden,
    )
    monkeypatch.setattr(
        optimization_service,
        "run_schedule_solver_v1",
        forbidden,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert result.b_evaluation.evaluation.disposition == BDisposition.INSUFFICIENT_DATA
    assert (
        result.adjustment_assessment.primary_decision
        == ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA
    )
    assert result.selected_action == OptimizationAction.INSUFFICIENT_DATA
    assert result.solver_attempted is False
    assert result.heuristic_outcome is None
    assert result.recommended_outcome is None


def test_canonical_regular_demand_suitable_timetable_stops_at_no_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _small_fixed_resource_fixture(
        irregular_timetable=False,
        demand_profile=(170, 170),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("A no-change service decision must not invoke the solver")

    monkeypatch.setattr(optimization_service, "run_schedule_solver_v1", forbidden)

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert (
        result.b_evaluation.evaluation.disposition
        == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE
    )
    assert (
        result.adjustment_assessment.primary_decision
        == ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE
    )
    assert result.selected_action == OptimizationAction.NO_CHANGE
    assert result.solver_attempted is False
    assert result.heuristic_outcome is None


@pytest.mark.parametrize(
    "decision",
    (
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES,
    ),
)
def test_fixed_resource_actions_use_the_same_canonical_composition_boundary(
    monkeypatch: pytest.MonkeyPatch,
    decision: ServiceAdjustmentDecisionV1,
) -> None:
    imported, options = _fixture()
    _force_decision(monkeypatch, _canonical_assessment(imported, options), decision)
    calls: list[tuple[str, object]] = []
    generation_context = object()
    heuristic_solver = object()
    outcome = _unknown_outcome()

    def record_build(*args, **kwargs):
        calls.append(("build", (args, kwargs)))
        return generation_context, heuristic_solver

    def record_run(context, solver):
        calls.append(("run", (context, solver)))
        return outcome

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        record_build,
    )
    monkeypatch.setattr(
        optimization_service,
        "run_schedule_solver_v1",
        record_run,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert [item[0] for item in calls] == ["build", "run"]
    build_args, build_kwargs = calls[0][1]
    assert build_args[:5] == (
        result.normalized_inputs,
        result.b_evaluation,
        imported.parameters_b,
        imported.trips_b,
        imported.demand,
    )
    assert isinstance(build_args[5], ScenarioCConfig)
    assert build_kwargs["evaluation_policy"] == result.adjustment_context.b_evaluation_policy
    assert calls[1][1] == (generation_context, heuristic_solver)
    assert result.solver_attempted is True
    assert result.heuristic_outcome is outcome
    assert result.recommended_outcome is None


def test_canonical_respace_path_executes_and_accepts_an_independently_validated_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _small_fixed_resource_fixture(
        irregular_timetable=True,
        demand_profile=(170, 170),
    )
    solver_calls = 0
    validation_calls = 0
    real_solve = HeuristicScheduleSolverAdapter.solve
    real_validator = solver_orchestration.validate_and_build_solution_v1

    def recording_solve(self, problem):
        nonlocal solver_calls
        solver_calls += 1
        return real_solve(self, problem)

    def recording_validator(context, candidate):
        nonlocal validation_calls
        validation_calls += 1
        return real_validator(context, candidate)

    monkeypatch.setattr(HeuristicScheduleSolverAdapter, "solve", recording_solve)
    monkeypatch.setattr(
        solver_orchestration,
        "validate_and_build_solution_v1",
        recording_validator,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert (
        result.b_evaluation.evaluation.disposition
        == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE
    )
    assert (
        result.adjustment_assessment.primary_decision
        == ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES
    )
    assert result.selected_action == OptimizationAction.FIXED_RESOURCE_RESPACE
    assert solver_calls == 1
    assert validation_calls == 1
    assert result.solver_attempted is True
    assert result.recommended_outcome is result.heuristic_outcome
    assert result.ortools_outcome is None
    assert result.comparison is None
    assert result.heuristic_outcome is not None
    assert (
        result.heuristic_outcome.result_status != GenerationResultStatus.C_NOT_REQUIRED_B_SUITABLE
    )
    assert result.heuristic_outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert result.heuristic_outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert result.heuristic_outcome.solver_status == NativeSolverStatus.FEASIBLE
    assert result.heuristic_outcome.solution is not None


def test_canonical_redistribute_trips_path_invokes_the_real_solver() -> None:
    imported, options = _small_fixed_resource_fixture(
        irregular_timetable=False,
        demand_profile=(255, 85),
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert (
        result.b_evaluation.evaluation.disposition
        == BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE
    )
    assert (
        result.adjustment_assessment.primary_decision
        == ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS
    )
    assert result.selected_action == OptimizationAction.FIXED_RESOURCE_REDISTRIBUTION
    assert result.solver_attempted is True
    assert result.recommended_outcome is None
    assert result.ortools_outcome is None
    assert result.comparison is None
    assert result.heuristic_outcome is not None
    assert result.heuristic_outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert result.heuristic_outcome.solver_status == NativeSolverStatus.UNKNOWN
    assert (
        result.heuristic_outcome.result_status
        == GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT
    )
    assert result.heuristic_outcome.solution is None


def test_balanced_heuristic_candidate_is_accepted_by_independent_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    )
    validation_calls = 0
    real_validator = solver_orchestration.validate_and_build_solution_v1

    def recording_validator(context, candidate):
        nonlocal validation_calls
        validation_calls += 1
        return real_validator(context, candidate)

    monkeypatch.setattr(
        solver_orchestration,
        "validate_and_build_solution_v1",
        recording_validator,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert validation_calls == 1
    assert result.solver_attempted is True
    assert result.heuristic_outcome is not None
    assert result.recommended_outcome is result.heuristic_outcome
    assert result.heuristic_outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert result.heuristic_outcome.solution is not None
    assert result.heuristic_outcome.diagnostic_candidate is None


def test_heuristic_unknown_remains_unknown_without_an_accepted_solution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    )

    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        heuristic_config=ScenarioCConfig(
            preferred_max_shift_per_trip_minutes=0,
            absolute_max_shift_per_trip_minutes=0,
        ),
    )

    assert result.solver_attempted is True
    assert result.recommended_outcome is None
    assert result.heuristic_outcome is not None
    assert result.heuristic_outcome.solver_status == NativeSolverStatus.UNKNOWN
    assert (
        result.heuristic_outcome.result_status
        == GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT
    )
    assert result.heuristic_outcome.solution is None


def test_corrupted_candidate_is_rejected_by_the_independent_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    )

    def corrupting_request(*args, **kwargs):
        context, solver = canonical_heuristic_request(*args, **kwargs)

        class CorruptingSolver:
            adapter_id = solver.adapter_id

            def solve(self, problem):
                run = solver.solve(problem)
                assert run.candidate is not None
                first = run.candidate.exact_timetable[0]
                corrupted = replace(
                    run.candidate,
                    exact_timetable=(
                        replace(
                            first,
                            runtime_minutes=first.runtime_minutes + 1,
                            arrival_time=first.arrival_time + 60,
                        ),
                        *run.candidate.exact_timetable[1:],
                    ),
                )
                return replace(run, candidate=corrupted)

        return context, CorruptingSolver()

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        corrupting_request,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert result.solver_attempted is True
    assert result.recommended_outcome is None
    assert result.heuristic_outcome is not None
    assert (
        result.heuristic_outcome.result_status
        == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    )
    assert result.heuristic_outcome.solution is None
    assert result.heuristic_outcome.diagnostic_candidate is not None
    assert "SOURCE_RUNTIME_LOCK_VIOLATION" in (
        result.heuristic_outcome.diagnostic_candidate.rejection_codes
    )


@pytest.mark.parametrize(
    ("demand_mode", "incomplete_directional"),
    (("combined", False), ("directional", True)),
)
def test_non_authoritative_directional_coverage_never_constructs_a_problem(
    monkeypatch: pytest.MonkeyPatch,
    demand_mode: str,
    incomplete_directional: bool,
) -> None:
    imported, options = _fixture(
        demand_mode=demand_mode,
        incomplete_directional=incomplete_directional,
    )
    demand_before = deepcopy(imported.demand)
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Incomplete H3 coverage must not construct a problem")

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        forbidden,
    )
    monkeypatch.setattr(
        optimization_service,
        "run_schedule_solver_v1",
        forbidden,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert result.selected_action == OptimizationAction.FIXED_RESOURCE_REDISTRIBUTION
    assert result.solver_attempted is False
    assert result.heuristic_outcome is None
    assert result.recommended_outcome is None
    assert any("directional solving is unavailable" in item for item in result.limitations)
    assert imported.demand == demand_before
    if demand_mode == "combined":
        assert {
            item.direction for item in result.normalized_inputs.observed_demand.observations
        } == {ContractDirection.COMBINED}


def test_full_directional_coverage_permits_the_supported_heuristic_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    )
    run_calls = 0

    def record_run(context, solver):
        nonlocal run_calls
        run_calls += 1
        return _unknown_outcome()

    monkeypatch.setattr(optimization_service, "run_schedule_solver_v1", record_run)

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert (
        result.b_evaluation.demand_resolution.coverage_assessment.directional_c_generation_supported
    )
    assert run_calls == 1
    assert result.solver_attempted is True


def test_default_decision_policy_reconciles_with_custom_evaluation_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    evaluation_policy = ScenarioBEvaluationPolicyV1(
        planning_load_factor_ceiling=0.81,
        critical_load_factor_ceiling=0.93,
        low_load_review_threshold=0.24,
        minimum_authoritative_demand_confidence=DemandConfidence.HIGH,
    )
    captured = {}
    real_builder = build_service_adjustment_evaluation_context_v1

    def recording_builder(
        bundle,
        supplied_evaluation_policy,
        decision_policy,
        repeatability_evidence=None,
        b_evaluation_cache=None,
    ):
        captured["decision_policy"] = decision_policy
        return real_builder(
            bundle,
            supplied_evaluation_policy,
            decision_policy,
            repeatability_evidence,
            b_evaluation_cache,
        )

    monkeypatch.setattr(
        optimization_service,
        "build_service_adjustment_evaluation_context_v1",
        recording_builder,
    )

    analyze_and_optimize_schedule_v1(
        imported,
        options,
        evaluation_policy=evaluation_policy,
    )

    decision_policy = captured["decision_policy"]
    assert decision_policy.planning_load_factor_ceiling == 0.81
    assert decision_policy.critical_load_factor_ceiling == 0.93
    assert decision_policy.low_load_review_threshold == 0.24
    assert decision_policy.minimum_authoritative_demand_confidence == DemandConfidence.HIGH
    assert decision_policy.headway_rounding_tolerance_minutes == 1


def test_supplied_mismatched_decision_policy_fails_before_assessment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    assessment_called = False

    def forbidden_assessment(context):
        nonlocal assessment_called
        assessment_called = True
        raise AssertionError("Mismatched policy must fail before assessment")

    monkeypatch.setattr(
        optimization_service,
        "evaluate_service_adjustment_need_v1",
        forbidden_assessment,
    )

    with pytest.raises(OptimizationExecutionErrorV1) as captured:
        analyze_and_optimize_schedule_v1(
            imported,
            options,
            evaluation_policy=ScenarioBEvaluationPolicyV1(planning_load_factor_ceiling=0.80),
            decision_policy=ServiceAdjustmentDecisionPolicyV1(planning_load_factor_ceiling=0.85),
        )

    assert captured.value.stage == OptimizationExecutionStageV1.EVALUATION
    assert isinstance(captured.value.__cause__, ContractValidationError)
    assert "ADJUSTMENT_DECISION_POLICY_EVALUATION_AUTHORITY_MISMATCH" in str(
        captured.value.__cause__
    )
    assert assessment_called is False


def test_repeatability_evidence_reaches_the_canonical_context_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    repeatability = _repeatability()
    captured = {}
    real_builder = build_service_adjustment_evaluation_context_v1

    def recording_builder(
        bundle,
        evaluation_policy,
        decision_policy,
        repeatability_evidence=None,
        b_evaluation_cache=None,
    ):
        captured["repeatability"] = repeatability_evidence
        return real_builder(
            bundle,
            evaluation_policy,
            decision_policy,
            repeatability_evidence,
            b_evaluation_cache,
        )

    monkeypatch.setattr(
        optimization_service,
        "build_service_adjustment_evaluation_context_v1",
        recording_builder,
    )

    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        repeatability_evidence=repeatability,
    )

    assert captured["repeatability"] is repeatability
    assert result.adjustment_context.repeatability_evidence is repeatability
    assert result.adjustment_assessment.repeatability_evidence is repeatability


def test_normalization_receives_the_exact_supplied_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    captured = {}
    real_normalizer = normalize_imported_workbook_v1

    def recording_normalizer(supplied_imported, supplied_options):
        captured["imported"] = supplied_imported
        captured["options"] = supplied_options
        return real_normalizer(supplied_imported, supplied_options)

    monkeypatch.setattr(
        optimization_service,
        "normalize_imported_workbook_v1",
        recording_normalizer,
    )

    analyze_and_optimize_schedule_v1(imported, options)

    assert captured == {"imported": imported, "options": options}
    assert captured["imported"] is imported
    assert captured["options"] is options


def test_xlsx_importer_output_runs_through_the_unified_service(
    tmp_path: Path,
) -> None:
    workbook_path = create_input_template(tmp_path / "canonical-input.xlsx")
    imported = import_workbook(workbook_path)
    options = NormalizationOptions(
        source_id="xlsx-importer-unified-service",
        imported_at=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
        operating_day_type_a=OperatingDayType.WEEKDAY,
        operating_day_type_b=OperatingDayType.WEEKDAY,
        available_fleet_limit_a=4,
        available_fleet_limit_b=4,
        demand_confidence=DemandConfidence.HIGH,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert result.normalized_inputs.scenario_b.route_id == imported.parameters_b.route_id
    assert len(result.normalized_inputs.scenario_b.exact_timetable) == len(imported.trips_b)
    assert (
        result.adjustment_assessment.primary_decision
        == ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS
    )
    assert result.selected_action == OptimizationAction.TRIP_INCREASE_RECOMMENDED
    assert result.solver_attempted is False
    assert result.heuristic_outcome is None


def test_imported_workbook_and_scenario_b_exact_timetable_remain_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    imported_before = deepcopy(imported)
    normalized_before = normalize_imported_workbook_v1(imported, options)
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert imported == imported_before
    assert result.normalized_inputs == normalized_before
    assert (
        result.normalized_inputs.scenario_b.exact_timetable
        == normalized_before.scenario_b.exact_timetable
    )
    assert result.b_evaluation == evaluate_scenario_b_v1(normalized_before)


def test_repeated_no_solver_calls_are_exactly_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE,
    )

    first = analyze_and_optimize_schedule_v1(imported, options)
    second = analyze_and_optimize_schedule_v1(imported, options)

    assert first == second


def test_legacy_weighted_comparator_and_runtime_are_never_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE,
    )
    import bus_schedule_engine.comparator as comparator
    import bus_schedule_engine.service as legacy_service

    def forbidden(*args, **kwargs):
        raise AssertionError("Unified service must not enter the legacy runtime")

    monkeypatch.setattr(comparator, "score_scenario", forbidden)
    monkeypatch.setattr(legacy_service, "run_analysis", forbidden)

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert result.selected_action == OptimizationAction.NO_CHANGE


def test_unified_module_has_no_direct_generator_or_cancelled_phase_b_dependency() -> None:
    source_path = Path(optimization_service.__file__)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "adjustment_routing" not in source
    assert "AuthorizationProfile" not in source
    assert "OrchestrationEnvelope" not in source
    assert not any(
        module.endswith(("service", "comparator", "c_generator")) for module in imported_modules
    )
    assert {"run_analysis", "score_scenario", "generate_scenario_c"}.isdisjoint(called_names)


@pytest.mark.parametrize("solver_choice", tuple(SolverChoice))
def test_every_declared_solver_choice_is_accepted_by_validation(
    solver_choice: SolverChoice,
) -> None:
    optimization_service._validate_solver_choice(solver_choice)


def test_invalid_solver_choice_type_fails_before_normalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()

    def forbidden_normalization(*args, **kwargs):
        raise AssertionError("Invalid solver choice must fail immediately")

    monkeypatch.setattr(
        optimization_service,
        "normalize_imported_workbook_v1",
        forbidden_normalization,
    )

    with pytest.raises(TypeError, match="solver_choice must be a SolverChoice"):
        analyze_and_optimize_schedule_v1(
            imported,
            options,
            solver_choice="HEURISTIC",  # type: ignore[arg-type]
        )


def test_public_wrapper_always_normalizes_and_delegates_its_derived_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    observed: dict[str, object] = {}
    real_normalize = optimization_service.normalize_imported_workbook_v1
    real_internal = optimization_service._analyze_normalized_and_optimize_schedule_v1

    def normalization_spy(workbook, supplied_options):
        bundle = real_normalize(workbook, supplied_options)
        observed["normalized"] = bundle
        return bundle

    def internal_spy(workbook, normalized_inputs, **kwargs):
        observed["internal"] = normalized_inputs
        return real_internal(workbook, normalized_inputs, **kwargs)

    monkeypatch.setattr(
        optimization_service,
        "normalize_imported_workbook_v1",
        normalization_spy,
    )
    monkeypatch.setattr(
        optimization_service,
        "_analyze_normalized_and_optimize_schedule_v1",
        internal_spy,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert observed["internal"] is observed["normalized"]
    assert result.normalized_inputs is observed["normalized"]


def test_public_wrapper_rejects_injected_normalized_bundle_from_another_workbook() -> None:
    imported, options = _fixture()
    foreign_imported = replace(
        imported,
        parameters_b=replace(imported.parameters_b, route_name="Foreign normalized authority"),
    )
    foreign_bundle = normalize_imported_workbook_v1(foreign_imported, options)

    assert (
        "_normalized_inputs" not in inspect.signature(analyze_and_optimize_schedule_v1).parameters
    )
    with pytest.raises(TypeError, match="unexpected keyword argument '_normalized_inputs'"):
        analyze_and_optimize_schedule_v1(
            imported,
            options,
            _normalized_inputs=foreign_bundle,  # type: ignore[call-arg]
        )


def test_public_result_is_frozen_slotted_and_exports_are_available() -> None:
    assert BusScheduleOptimizationResult.__dataclass_params__.frozen is True
    assert "__slots__" in BusScheduleOptimizationResult.__dict__
    assert set(OptimizationAction) == set(EXPECTED_ACTIONS.values())
    assert set(SolverChoice) == {
        SolverChoice.HEURISTIC,
        SolverChoice.OR_TOOLS,
        SolverChoice.BOTH,
    }
    assert callable(analyze_and_optimize_schedule_v1)
    assert callable(select_optimization_action)


def test_representative_legacy_run_analysis_result_is_exactly_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, _ = _fixture()
    before = run_analysis(deepcopy(imported))

    def forbidden_new_service(*args, **kwargs):
        raise AssertionError("Legacy run_analysis must not call the unified service")

    monkeypatch.setattr(
        optimization_service,
        "analyze_and_optimize_schedule_v1",
        forbidden_new_service,
    )
    after = run_analysis(deepcopy(imported))

    assert after == before


def test_solver_attempted_is_true_only_after_canonical_runner_is_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    assessment = _canonical_assessment(imported, options)
    outcome = _unknown_outcome()
    _force_decision(
        monkeypatch,
        assessment,
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    )
    calls = 0

    def recording_runner(context, solver):
        nonlocal calls
        calls += 1
        return outcome

    monkeypatch.setattr(
        optimization_service,
        "run_schedule_solver_v1",
        recording_runner,
    )

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert calls == 1
    assert result.solver_attempted is True
    assert result.heuristic_outcome is outcome
    assert canonical_solver_runner is not recording_runner


def test_unexpected_normalization_exception_is_staged_with_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    original = RuntimeError("normalizer unavailable")

    def fail(*args, **kwargs):
        raise original

    monkeypatch.setattr(
        optimization_service,
        "normalize_imported_workbook_v1",
        fail,
    )
    with pytest.raises(OptimizationExecutionErrorV1) as captured:
        analyze_and_optimize_schedule_v1(imported, options)

    assert captured.value.stage == OptimizationExecutionStageV1.NORMALIZATION
    assert captured.value.__cause__ is original


def test_contract_validation_error_during_normalization_is_staged_with_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    issue_error = ContractValidationError(())

    def fail(*args, **kwargs):
        raise issue_error

    monkeypatch.setattr(
        optimization_service,
        "normalize_imported_workbook_v1",
        fail,
    )
    with pytest.raises(OptimizationExecutionErrorV1) as captured:
        analyze_and_optimize_schedule_v1(imported, options)

    assert captured.value.stage == OptimizationExecutionStageV1.NORMALIZATION
    assert captured.value.__cause__ is issue_error


def test_contract_validation_error_during_evaluation_is_staged_with_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()
    issue_error = ContractValidationError(())

    def fail(*args, **kwargs):
        raise issue_error

    monkeypatch.setattr(
        optimization_service,
        "build_service_adjustment_evaluation_context_v1",
        fail,
    )
    with pytest.raises(OptimizationExecutionErrorV1) as captured:
        analyze_and_optimize_schedule_v1(imported, options)

    assert captured.value.stage == OptimizationExecutionStageV1.EVALUATION
    assert captured.value.__cause__ is issue_error


def test_unexpected_evaluation_exception_is_staged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _fixture()

    def fail(*args, **kwargs):
        raise RuntimeError("evaluation unavailable")

    monkeypatch.setattr(optimization_service, "evaluate_scenario_b_v1", fail)
    with pytest.raises(OptimizationExecutionErrorV1) as captured:
        analyze_and_optimize_schedule_v1(imported, options)

    assert captured.value.stage == OptimizationExecutionStageV1.EVALUATION
    assert isinstance(captured.value.__cause__, RuntimeError)


@pytest.mark.parametrize(
    ("solver_choice", "expected_stage"),
    (
        (SolverChoice.HEURISTIC, OptimizationExecutionStageV1.HEURISTIC_SOLVER),
        (SolverChoice.OR_TOOLS, OptimizationExecutionStageV1.OR_TOOLS_SOLVER),
    ),
)
def test_unexpected_solver_exception_is_staged(
    monkeypatch: pytest.MonkeyPatch,
    solver_choice: SolverChoice,
    expected_stage: OptimizationExecutionStageV1,
) -> None:
    imported, options = _small_fixed_resource_fixture(
        irregular_timetable=False,
        demand_profile=(255, 85),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("solver unavailable")

    monkeypatch.setattr(optimization_service, "run_schedule_solver_v1", fail)
    with pytest.raises(OptimizationExecutionErrorV1) as captured:
        analyze_and_optimize_schedule_v1(
            imported,
            options,
            solver_choice=solver_choice,
        )

    assert captured.value.stage == expected_stage
    assert isinstance(captured.value.__cause__, RuntimeError)


def test_unexpected_both_comparison_exception_is_staged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _small_fixed_resource_fixture(
        irregular_timetable=False,
        demand_profile=(255, 85),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("comparison unavailable")

    monkeypatch.setattr(optimization_service, "compare_solver_outcomes_v1", fail)
    with pytest.raises(OptimizationExecutionErrorV1) as captured:
        analyze_and_optimize_schedule_v1(
            imported,
            options,
            solver_choice=SolverChoice.BOTH,
        )

    assert captured.value.stage == OptimizationExecutionStageV1.SOLVER_COMPARISON
    assert isinstance(captured.value.__cause__, RuntimeError)
