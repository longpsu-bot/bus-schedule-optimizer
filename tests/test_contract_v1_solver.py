from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.c_generator import generate_scenario_c
from bus_schedule_engine.contracts_v1 import (
    BDisposition,
    CandidateValidationStatus,
    DemandConfidence,
    GenerationResultStatus,
    HeuristicScheduleSolverAdapter,
    NativeSolverStatus,
    NormalizationOptions,
    OperatingDayType,
    RawScheduleCandidateV1,
    ScheduleProblemError,
    ScenarioBEvaluationPolicyV1,
    SolverExecutionStatus,
    SolverRunResultV1,
    build_schedule_problem_v1,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
    run_schedule_solver_v1,
    schedule_outcome_to_contract_dict,
    schedule_solution_to_contract_dict,
    validate_and_build_solution_v1,
)
from bus_schedule_engine.fingerprint import timetable_fingerprint
from bus_schedule_engine.fleet import assign_fleet
from bus_schedule_engine.importer import ImportedWorkbook
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    RouteType,
    ScenarioParameters,
    Trip,
    VolumeType,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "v1"
SCHEMAS = {
    path.name: json.loads(path.read_text(encoding="utf-8"))
    for path in SCHEMA_DIR.glob("*.schema.json")
}
REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema)) for schema in SCHEMAS.values()
)


def _schema_errors(instance: dict[str, object], schema_name: str) -> list[str]:
    validator = Draft202012Validator(
        SCHEMAS[schema_name],
        registry=REGISTRY,
        format_checker=FormatChecker(),
    )
    return [error.message for error in validator.iter_errors(instance)]


def _fixture(
    *,
    low_demand: bool = False,
) -> tuple[ScenarioParameters, list[Trip], list[DemandRecord], int]:
    parameters = ScenarioParameters(
        route_id="SOLVER-01",
        route_name="Tuyến kiểm thử solver boundary",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=30,
        total_daily_trips=26,
        terminal_1_name="Bến Đông",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=12 * 3600,
        terminal_2_name="Bến Tây",
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

    volumes = [10] * 6 if low_demand else [150, 150, 30, 30, 150, 150]
    demand = [
        DemandRecord(
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 7),
            observation_days=1,
            block_start_seconds=(6 + index) * 3600,
            block_end_seconds=(7 + index) * 3600,
            direction=direction,
            passenger_volume=volume,
            volume_type=VolumeType.AVERAGE_DAY,
        )
        for direction in (
            Direction.TERMINAL_1_TO_2,
            Direction.TERMINAL_2_TO_1,
        )
        for index, volume in enumerate(volumes)
    ]
    active_fleet = assign_fleet(trips, parameters).minimum_vehicles
    return parameters, trips, demand, active_fleet


def _normalized(
    parameters: ScenarioParameters,
    trips: list[Trip],
    demand: list[DemandRecord],
    fleet_limit: int,
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
            source_id="solver-v1-fixture",
            imported_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
            operating_day_type_a=OperatingDayType.WEEKDAY,
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_a=fleet_limit,
            available_fleet_limit_b=fleet_limit,
            demand_confidence=DemandConfidence.HIGH,
        ),
    )


def _problem(
    *,
    low_demand: bool = False,
    config: ScenarioCConfig | None = None,
):
    parameters, trips, demand, fleet_limit = _fixture(low_demand=low_demand)
    normalized = _normalized(parameters, trips, demand, fleet_limit)
    policy = ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(normalized, policy)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        demand,
        config or ScenarioCConfig(),
        policy,
    )
    return problem, parameters, trips, demand, fleet_limit


class _BombSolver:
    adapter_id = "must_not_run"

    def solve(self, problem):  # pragma: no cover - failure makes test explicit
        raise AssertionError("solver must not be invoked")


class _StaticSolver:
    adapter_id = "static_test_adapter"

    def __init__(self, run: SolverRunResultV1):
        self._run = run

    def solve(self, problem):
        return self._run


def test_problem_reconciles_normalized_and_legacy_inputs() -> None:
    problem, _, trips, _, _ = _problem()

    assert len(problem.legacy_trips_b) == 26
    assert problem.normalized_inputs.scenario_b.total_daily_trips == 26
    assert len(problem.problem_fingerprint) == 64
    assert timetable_fingerprint(list(problem.legacy_trips_b)) == timetable_fingerprint(trips)


def test_problem_rejects_legacy_parameter_drift() -> None:
    problem, parameters, trips, demand, _ = _problem()

    with pytest.raises(ScheduleProblemError, match="vehicle_capacity"):
        build_schedule_problem_v1(
            problem.normalized_inputs,
            problem.b_evaluation,
            replace(parameters, vehicle_capacity_passengers=61),
            trips,
            demand,
            ScenarioCConfig(),
            problem.evaluation_policy,
        )


def test_suitable_b_returns_not_run_without_duplicate_c() -> None:
    problem, *_ = _problem(low_demand=True)
    assert (
        problem.b_evaluation.evaluation.disposition
        == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE
    )

    outcome = run_schedule_solver_v1(problem, _BombSolver())

    assert outcome.result_status == GenerationResultStatus.C_NOT_REQUIRED_B_SUITABLE
    assert outcome.execution_status == SolverExecutionStatus.NOT_RUN
    assert outcome.solver_status is None
    assert outcome.solution is None


def test_insufficient_data_returns_not_run_without_fabricated_c() -> None:
    parameters, trips, _, fleet_limit = _fixture()
    imported = ImportedWorkbook(
        parameters_a=None,
        trips_a=[],
        parameters_b=parameters,
        trips_b=trips,
        demand=[],
        configuration={},
    )
    normalized = normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="solver-no-demand",
            imported_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_b=fleet_limit,
        ),
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        [],
        ScenarioCConfig(),
    )

    outcome = run_schedule_solver_v1(problem, _BombSolver())

    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_INSUFFICIENT_DATA
    assert outcome.execution_status == SolverExecutionStatus.NOT_RUN
    assert outcome.solution is None


def test_heuristic_candidate_crosses_boundary_and_matches_legacy_behavior() -> None:
    problem, parameters, trips, demand, fleet_limit = _problem()
    baseline = tuple(trips)
    baseline_fingerprint = timetable_fingerprint(trips)

    direct = generate_scenario_c(
        parameters,
        trips,
        demand,
        fleet_limit,
        problem.heuristic_config,
    )
    outcome = run_schedule_solver_v1(problem, HeuristicScheduleSolverAdapter())

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.FEASIBLE
    assert outcome.solution is not None
    assert len(outcome.solution.solution_fingerprint) == 64
    assert tuple(trips) == baseline
    assert timetable_fingerprint(trips) == baseline_fingerprint
    direct_times = {
        trip.source_b_trip_id: trip.departure_seconds for trip in direct.trips
    }
    adapter_times = {
        trip.source_b_trip_id: trip.c_departure_time
        for trip in outcome.solution.c_exact_timetable
    }
    assert adapter_times == direct_times
    assert (
        outcome.solution.minimum_required_fleet
        == outcome.solution.recommended_initial_fleet_terminal_1
        + outcome.solution.recommended_initial_fleet_terminal_2
    )
    assert outcome.solution.minimum_required_fleet <= fleet_limit
    assert all(
        event.stock_before >= 0 and event.stock_after >= 0
        for event in (
            *outcome.solution.vehicle_stock_profile_terminal_1,
            *outcome.solution.vehicle_stock_profile_terminal_2,
        )
    )


def test_heuristic_exhaustion_is_unknown_not_infeasible() -> None:
    config = ScenarioCConfig(
        preferred_max_shift_per_trip_minutes=0,
        absolute_max_shift_per_trip_minutes=0,
    )
    problem, *_ = _problem(config=config)
    solver = HeuristicScheduleSolverAdapter()

    run = solver.solve(problem)
    outcome = run_schedule_solver_v1(problem, solver)

    assert run.solver_status == NativeSolverStatus.UNKNOWN
    assert run.candidate is None
    assert outcome.result_status == GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT
    assert outcome.solver_status == NativeSolverStatus.UNKNOWN
    assert outcome.solution is None


def test_tampered_runtime_is_rejected_as_diagnostic_only() -> None:
    problem, *_ = _problem()
    run = HeuristicScheduleSolverAdapter().solve(problem)
    assert run.candidate is not None
    first = run.candidate.exact_timetable[0]
    tampered_trip = replace(
        first,
        runtime_minutes=first.runtime_minutes + 1,
        arrival_time=first.arrival_time + 60,
    )
    tampered = replace(
        run.candidate,
        exact_timetable=(tampered_trip, *run.candidate.exact_timetable[1:]),
    )

    validation = validate_and_build_solution_v1(problem, tampered)
    outcome = run_schedule_solver_v1(
        problem,
        _StaticSolver(replace(run, candidate=tampered)),
    )

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "SOURCE_RUNTIME_LOCK_VIOLATION" in validation.rejection_codes
    assert (
        outcome.result_status
        == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    )
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is not None


def test_solution_and_outcome_fingerprints_ignore_solve_duration() -> None:
    problem, *_ = _problem()
    first_run = HeuristicScheduleSolverAdapter().solve(problem)
    assert first_run.candidate is not None
    second_candidate: RawScheduleCandidateV1 = replace(
        first_run.candidate,
        solve_duration_seconds=first_run.candidate.solve_duration_seconds + 9,
    )
    first_validation = validate_and_build_solution_v1(problem, first_run.candidate)
    second_validation = validate_and_build_solution_v1(problem, second_candidate)
    assert first_validation.solution is not None
    assert second_validation.solution is not None

    assert (
        first_validation.solution.solution_fingerprint
        == second_validation.solution.solution_fingerprint
    )


def test_accepted_solution_and_outcome_match_json_schemas() -> None:
    problem, *_ = _problem()
    outcome = run_schedule_solver_v1(problem, HeuristicScheduleSolverAdapter())
    assert outcome.solution is not None

    solution_payload = schedule_solution_to_contract_dict(outcome.solution)
    outcome_payload = schedule_outcome_to_contract_dict(outcome)

    assert _schema_errors(solution_payload, "schedule_solution.schema.json") == []
    assert _schema_errors(
        outcome_payload,
        "schedule_generation_outcome.schema.json",
    ) == []
