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
    ContractDirection,
    DemandConfidence,
    GenerationResultStatus,
    HeuristicScheduleSolverAdapter,
    NativeSolverStatus,
    NormalizationOptions,
    OperatingDayType,
    RawScheduleCandidateV1,
    ScenarioBEvaluationPolicyV1,
    ScheduleProblemError,
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
from bus_schedule_engine.contracts_v1.solver_fingerprints import candidate_fingerprint
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
    fleet_limit_override: int | None = None,
):
    parameters, trips, demand, fleet_limit = _fixture(low_demand=low_demand)
    effective_fleet_limit = fleet_limit if fleet_limit_override is None else fleet_limit_override
    normalized = _normalized(parameters, trips, demand, effective_fleet_limit)
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
    return problem, parameters, trips, demand, effective_fleet_limit


def _candidate(problem):
    run = HeuristicScheduleSolverAdapter().solve(problem)
    assert run.candidate is not None
    return run.candidate


def _refingerprint(problem, candidate: RawScheduleCandidateV1) -> RawScheduleCandidateV1:
    return replace(
        candidate,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=problem.problem_fingerprint,
            solver_adapter=candidate.solver_adapter,
            exact_timetable=candidate.exact_timetable,
            headway_regimes=candidate.headway_regimes,
        ),
    )


def _previous_headways(rows) -> dict[str, float | None]:
    by_direction = {}
    for direction, departure, trip_id in rows:
        by_direction.setdefault(direction, []).append((departure, trip_id))
    output: dict[str, float | None] = {}
    for directional_rows in by_direction.values():
        previous = None
        for departure, trip_id in sorted(
            directional_rows,
            key=lambda item: (item[0], item[1]),
        ):
            output[trip_id] = None if previous is None else (departure - previous) / 60
            previous = departure
    return output


def _reconcile_raw_claims(
    problem,
    candidate: RawScheduleCandidateV1,
) -> RawScheduleCandidateV1:
    b_by_id = {trip.trip_id: trip for trip in problem.normalized_inputs.scenario_b.exact_timetable}
    previous_b = _previous_headways(
        [
            (trip.direction, trip.departure_time, trip.trip_id)
            for trip in problem.normalized_inputs.scenario_b.exact_timetable
        ]
    )
    previous_c = _previous_headways(
        [
            (trip.direction, trip.c_departure_time, trip.c_trip_id)
            for trip in candidate.exact_timetable
        ]
    )
    trips = tuple(
        replace(
            trip,
            shift_minutes=(trip.c_departure_time - b_by_id[trip.source_b_trip_id].departure_time)
            / 60,
            previous_b_headway=previous_b[trip.source_b_trip_id],
            previous_c_headway=previous_c[trip.c_trip_id],
        )
        for trip in candidate.exact_timetable
    )
    regimes = []
    for regime in candidate.headway_regimes:
        members = sorted(
            (trip for trip in trips if trip.headway_regime_id == regime.regime_id),
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
        regimes.append(
            replace(
                regime,
                start_time=members[0].c_departure_time,
                end_time=members[-1].c_departure_time,
                trip_count=len(members),
                actual_headway_sequence=tuple(
                    (right.c_departure_time - left.c_departure_time) / 60
                    for left, right in zip(members, members[1:], strict=False)
                ),
            )
        )
    return _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=trips,
            headway_regimes=tuple(regimes),
        ),
    )


def _zero_headway_candidate(problem) -> tuple[RawScheduleCandidateV1, str, str]:
    candidate = _candidate(problem)
    regime = next(
        item
        for item in candidate.headway_regimes
        if sum(trip.headway_regime_id == item.regime_id for trip in candidate.exact_timetable) >= 2
    )
    members = sorted(
        (trip for trip in candidate.exact_timetable if trip.headway_regime_id == regime.regime_id),
        key=lambda item: (item.c_departure_time, item.c_trip_id),
    )
    earlier, later = members[:2]
    changed = tuple(
        (
            replace(
                trip,
                c_departure_time=earlier.c_departure_time,
                arrival_time=(earlier.c_departure_time + trip.runtime_minutes * 60),
            )
            if trip.c_trip_id == later.c_trip_id
            else trip
        )
        for trip in candidate.exact_timetable
    )
    reconciled = _reconcile_raw_claims(
        problem,
        replace(candidate, exact_timetable=changed),
    )
    return reconciled, earlier.c_trip_id, later.c_trip_id


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


class _RaisingSolver:
    adapter_id = "raising_test_adapter"

    def solve(self, problem):
        raise RuntimeError("secret workbook value at C:\\private\\operator\\source.xlsx")


def test_problem_reconciles_normalized_and_legacy_inputs() -> None:
    problem, _, trips, _, _ = _problem()

    assert len(problem.legacy_trips_b) == 26
    assert problem.normalized_inputs.scenario_b.total_daily_trips == 26
    assert problem.b_evaluation == evaluate_scenario_b_v1(
        problem.normalized_inputs,
        problem.evaluation_policy,
    )
    assert len(problem.problem_fingerprint) == 64
    assert timetable_fingerprint(list(problem.legacy_trips_b)) == timetable_fingerprint(trips)


def test_problem_rejects_low_demand_evaluation_for_high_demand_bundle() -> None:
    high_problem, parameters, trips, demand, _ = _problem()
    low_parameters, low_trips, low_demand, fleet_limit = _fixture(low_demand=True)
    low_normalized = _normalized(
        low_parameters,
        low_trips,
        low_demand,
        fleet_limit,
    )
    low_evaluation = evaluate_scenario_b_v1(low_normalized)
    assert (
        low_evaluation.evaluation.disposition
        == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE
    )

    with pytest.raises(ScheduleProblemError) as raised:
        build_schedule_problem_v1(
            high_problem.normalized_inputs,
            low_evaluation,
            parameters,
            trips,
            demand,
            ScenarioCConfig(),
        )

    assert raised.value.code == "B_EVALUATION_PROVENANCE_MISMATCH"


def test_problem_rejects_evaluation_from_different_policy() -> None:
    problem, parameters, trips, demand, _ = _problem()
    different_policy = replace(
        problem.evaluation_policy,
        planning_load_factor_ceiling=0.50,
    )

    with pytest.raises(ScheduleProblemError) as raised:
        build_schedule_problem_v1(
            problem.normalized_inputs,
            problem.b_evaluation,
            parameters,
            trips,
            demand,
            ScenarioCConfig(),
            different_policy,
        )

    assert raised.value.code == "B_EVALUATION_PROVENANCE_MISMATCH"


def test_problem_rejects_altered_block_evidence_with_same_disposition() -> None:
    problem, parameters, trips, demand, _ = _problem()
    first = problem.b_evaluation.b_block_supply[0]
    altered = replace(
        problem.b_evaluation,
        b_block_supply=(
            replace(first, shortage=first.shortage + 1),
            *problem.b_evaluation.b_block_supply[1:],
        ),
    )
    assert altered.evaluation.disposition == problem.b_evaluation.evaluation.disposition

    with pytest.raises(ScheduleProblemError) as raised:
        build_schedule_problem_v1(
            problem.normalized_inputs,
            altered,
            parameters,
            trips,
            demand,
            ScenarioCConfig(),
            problem.evaluation_policy,
        )

    assert raised.value.code == "B_EVALUATION_PROVENANCE_MISMATCH"


def test_problem_rejects_altered_fleet_evidence_with_same_disposition() -> None:
    problem, parameters, trips, demand, _ = _problem()
    altered = replace(
        problem.b_evaluation,
        fleet_assessment=replace(
            problem.b_evaluation.fleet_assessment,
            minimum_required_fleet=(
                problem.b_evaluation.fleet_assessment.minimum_required_fleet + 1
            ),
        ),
    )
    assert altered.evaluation.disposition == problem.b_evaluation.evaluation.disposition

    with pytest.raises(ScheduleProblemError) as raised:
        build_schedule_problem_v1(
            problem.normalized_inputs,
            altered,
            parameters,
            trips,
            demand,
            ScenarioCConfig(),
            problem.evaluation_policy,
        )

    assert raised.value.code == "B_EVALUATION_PROVENANCE_MISMATCH"


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
    scenario_b_before = problem.normalized_inputs.scenario_b

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
    assert problem.normalized_inputs.scenario_b == scenario_b_before
    direct_times = {trip.source_b_trip_id: trip.departure_seconds for trip in direct.trips}
    adapter_times = {
        trip.source_b_trip_id: trip.c_departure_time for trip in outcome.solution.c_exact_timetable
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
    assert outcome.result_status == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is not None


def test_shift_claim_is_rejected_even_with_valid_candidate_fingerprint() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    target = next(item for item in candidate.exact_timetable if item.shift_minutes == -4)
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=tuple(
                replace(item, shift_minutes=0) if item.c_trip_id == target.c_trip_id else item
                for item in candidate.exact_timetable
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "SHIFT_MINUTES_MISMATCH" in validation.rejection_codes
    assert "CANDIDATE_FINGERPRINT_MISMATCH" not in validation.rejection_codes


def test_previous_b_headway_claim_is_independently_checked() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    target = next(item for item in candidate.exact_timetable if item.previous_b_headway is not None)
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=tuple(
                replace(
                    item,
                    previous_b_headway=item.previous_b_headway + 1,
                )
                if item.c_trip_id == target.c_trip_id
                else item
                for item in candidate.exact_timetable
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "PREVIOUS_B_HEADWAY_MISMATCH" in validation.rejection_codes


def test_previous_c_headway_claim_is_independently_checked() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    target = next(item for item in candidate.exact_timetable if item.previous_c_headway is not None)
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=tuple(
                replace(
                    item,
                    previous_c_headway=item.previous_c_headway + 1,
                )
                if item.c_trip_id == target.c_trip_id
                else item
                for item in candidate.exact_timetable
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "PREVIOUS_C_HEADWAY_MISMATCH" in validation.rejection_codes


def test_duplicate_headway_regime_ids_are_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                *candidate.headway_regimes,
                replace(candidate.headway_regimes[0]),
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "DUPLICATE_HEADWAY_REGIME_ID" in validation.rejection_codes


def test_unknown_headway_regime_reference_is_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.exact_timetable[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=(
                replace(first, headway_regime_id="UNKNOWN-REGIME"),
                *candidate.exact_timetable[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "UNKNOWN_HEADWAY_REGIME_REFERENCE" in validation.rejection_codes


def test_orphan_headway_regime_is_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    orphan = replace(
        candidate.headway_regimes[0],
        regime_id="ORPHAN-REGIME",
    )
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(*candidate.headway_regimes, orphan),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "ORPHAN_HEADWAY_REGIME" in validation.rejection_codes


def test_headway_regime_direction_mismatch_is_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.headway_regimes[0]
    opposite = (
        ContractDirection.INBOUND
        if first.direction == ContractDirection.OUTBOUND
        else ContractDirection.OUTBOUND
    )
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                replace(first, direction=opposite),
                *candidate.headway_regimes[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_DIRECTION_MISMATCH" in validation.rejection_codes


def test_fabricated_headway_regime_trip_count_is_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.headway_regimes[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                replace(first, trip_count=105),
                *candidate.headway_regimes[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_TRIP_COUNT_MISMATCH" in validation.rejection_codes


def test_fabricated_headway_sequence_is_rejected_with_valid_fingerprint() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.headway_regimes[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                replace(first, actual_headway_sequence=(999,)),
                *candidate.headway_regimes[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_SEQUENCE_MISMATCH" in validation.rejection_codes
    assert "CANDIDATE_FINGERPRINT_MISMATCH" not in validation.rejection_codes


def test_headway_regime_member_endpoints_are_independently_checked() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.headway_regimes[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                replace(
                    first,
                    start_time=first.start_time + 60,
                    end_time=first.end_time - 60,
                ),
                *candidate.headway_regimes[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_START_MISMATCH" in validation.rejection_codes
    assert "HEADWAY_REGIME_END_MISMATCH" in validation.rejection_codes


def test_non_positive_headway_regime_target_is_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.headway_regimes[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                replace(first, target_headway=0),
                *candidate.headway_regimes[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "INVALID_HEADWAY_REGIME_TARGET" in validation.rejection_codes


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


def test_same_b_and_status_under_different_evaluations_change_outcome_identity() -> None:
    parameters, trips, demand, fleet_limit = _fixture(low_demand=True)
    changed_demand = [replace(item, passenger_volume=item.passenger_volume + 1) for item in demand]
    first_normalized = _normalized(parameters, trips, demand, fleet_limit)
    second_normalized = _normalized(
        parameters,
        trips,
        changed_demand,
        fleet_limit,
    )
    first_evaluation = evaluate_scenario_b_v1(first_normalized)
    second_evaluation = evaluate_scenario_b_v1(second_normalized)
    first_problem = build_schedule_problem_v1(
        first_normalized,
        first_evaluation,
        parameters,
        trips,
        demand,
        ScenarioCConfig(),
    )
    second_problem = build_schedule_problem_v1(
        second_normalized,
        second_evaluation,
        parameters,
        trips,
        changed_demand,
        ScenarioCConfig(),
    )

    first = run_schedule_solver_v1(first_problem, _BombSolver())
    second = run_schedule_solver_v1(second_problem, _BombSolver())

    assert first_problem.normalized_inputs.scenario_b_fingerprint == (
        second_problem.normalized_inputs.scenario_b_fingerprint
    )
    assert first.result_status == second.result_status
    assert first.outcome_fingerprint != second.outcome_fingerprint


def test_same_b_and_status_under_different_solver_config_change_outcome_identity() -> None:
    first_problem, *_ = _problem(low_demand=True)
    second_problem, *_ = _problem(
        low_demand=True,
        config=replace(
            ScenarioCConfig(),
            configuration_version="scenario_c_regimes_v1_identity_variant",
        ),
    )

    first = run_schedule_solver_v1(first_problem, _BombSolver())
    second = run_schedule_solver_v1(second_problem, _BombSolver())

    assert first_problem.normalized_inputs.scenario_b_fingerprint == (
        second_problem.normalized_inputs.scenario_b_fingerprint
    )
    assert first.result_status == second.result_status
    assert first.outcome_fingerprint != second.outcome_fingerprint


def test_accepted_solution_fingerprint_changes_with_bound_problem_identity() -> None:
    first_problem, *_ = _problem()
    second_problem, *_ = _problem(
        config=replace(
            ScenarioCConfig(),
            configuration_version="scenario_c_regimes_v1_identity_variant",
        ),
    )

    first = run_schedule_solver_v1(
        first_problem,
        HeuristicScheduleSolverAdapter(),
    )
    second = run_schedule_solver_v1(
        second_problem,
        HeuristicScheduleSolverAdapter(),
    )

    assert first.solution is not None
    assert second.solution is not None
    assert [
        (item.source_b_trip_id, item.c_departure_time) for item in first.solution.c_exact_timetable
    ] == [
        (item.source_b_trip_id, item.c_departure_time) for item in second.solution.c_exact_timetable
    ]
    assert first.solution.solution_fingerprint != second.solution.solution_fingerprint


def test_solver_exception_returns_sanitized_model_invalid_envelope() -> None:
    problem, *_ = _problem()

    outcome = run_schedule_solver_v1(problem, _RaisingSolver())

    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.MODEL_INVALID
    assert outcome.solver_adapter == "raising_test_adapter"
    assert outcome.solve_duration_seconds >= 0
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is None
    assert any("SOLVER_ADAPTER_EXCEPTION" in item for item in outcome.explanations)
    serialized_explanations = " ".join(outcome.explanations)
    assert "secret workbook value" not in serialized_explanations
    assert "source.xlsx" not in serialized_explanations


def test_accepted_solution_and_outcome_match_json_schemas() -> None:
    problem, *_ = _problem()
    outcome = run_schedule_solver_v1(problem, HeuristicScheduleSolverAdapter())
    assert outcome.solution is not None

    solution_payload = schedule_solution_to_contract_dict(outcome.solution)
    outcome_payload = schedule_outcome_to_contract_dict(outcome)

    assert _schema_errors(solution_payload, "schedule_solution.schema.json") == []
    assert (
        _schema_errors(
            outcome_payload,
            "schedule_generation_outcome.schema.json",
        )
        == []
    )


def test_candidate_fingerprint_tampering_is_rejected() -> None:
    problem, *_ = _problem()
    run = HeuristicScheduleSolverAdapter().solve(problem)
    assert run.candidate is not None
    tampered = replace(run.candidate, candidate_fingerprint="0" * 64)

    validation = validate_and_build_solution_v1(problem, tampered)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "CANDIDATE_FINGERPRINT_MISMATCH" in validation.rejection_codes


def test_outcome_fingerprint_ignores_solve_duration() -> None:
    problem, *_ = _problem()
    run = HeuristicScheduleSolverAdapter().solve(problem)
    assert run.candidate is not None
    first = run_schedule_solver_v1(problem, _StaticSolver(run))
    delayed_candidate = replace(
        run.candidate,
        solve_duration_seconds=run.candidate.solve_duration_seconds + 9,
    )
    delayed_run = replace(
        run,
        solve_duration_seconds=run.solve_duration_seconds + 9,
        candidate=delayed_candidate,
    )
    second = run_schedule_solver_v1(problem, _StaticSolver(delayed_run))

    assert first.outcome_fingerprint == second.outcome_fingerprint
    assert first.solution is not None
    assert second.solution is not None
    assert first.solution.solution_fingerprint == second.solution.solution_fingerprint


def test_corrected_schema_allows_zero_regime_headways() -> None:
    regime_schema = SCHEMAS["schedule_solution.schema.json"]["$defs"]["regime"]

    assert regime_schema["properties"]["actual_headway_sequence"]["items"] == {
        "type": "integer",
        "minimum": 0,
    }
    assert regime_schema["properties"]["transition_headways"]["items"] == {
        "type": "integer",
        "minimum": 0,
    }
    assert regime_schema["properties"]["exceptional_headways"]["items"] == {
        "type": "integer",
        "minimum": 0,
    }


def test_zero_headway_is_derived_preserved_exceptional_and_schema_valid() -> None:
    problem, *_ = _problem(fleet_limit_override=20)
    candidate, earlier_id, later_id = _zero_headway_candidate(problem)
    base_run = HeuristicScheduleSolverAdapter().solve(problem)
    outcome = run_schedule_solver_v1(
        problem,
        _StaticSolver(replace(base_run, candidate=candidate)),
    )

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solution is not None
    solution = outcome.solution
    later = next(item for item in solution.c_exact_timetable if item.c_trip_id == later_id)
    assert later.previous_c_headway == 0
    zero_regime = next(
        item for item in solution.c_headway_regimes if 0 in item.actual_headway_sequence
    )
    assert zero_regime.regularity_status == "EXCEPTIONAL"
    assert zero_regime.exceptional_headways == zero_regime.actual_headway_sequence
    assert 0 in zero_regime.exceptional_headways

    assignment_by_trip = {item.c_trip_id: item for item in solution.fleet_assignment}
    assert assignment_by_trip[earlier_id].departure_time == (
        assignment_by_trip[later_id].departure_time
    )
    assert assignment_by_trip[earlier_id].vehicle_id != (assignment_by_trip[later_id].vehicle_id)
    assert solution.minimum_required_fleet <= solution.available_fleet_limit
    assert all(
        event.stock_before >= 0 and event.stock_after >= 0
        for event in (
            *solution.vehicle_stock_profile_terminal_1,
            *solution.vehicle_stock_profile_terminal_2,
        )
    )

    payload = schedule_solution_to_contract_dict(solution)
    serialized_regime = next(
        item for item in payload["c_headway_regimes"] if 0 in item["actual_headway_sequence"]
    )
    assert serialized_regime["actual_headway_sequence"] == list(zero_regime.actual_headway_sequence)
    assert 0 in serialized_regime["actual_headway_sequence"]
    assert _schema_errors(payload, "schedule_solution.schema.json") == []
    assert (
        _schema_errors(
            schedule_outcome_to_contract_dict(outcome),
            "schedule_generation_outcome.schema.json",
        )
        == []
    )


def test_zero_previous_headway_claimed_as_one_is_rejected() -> None:
    problem, *_ = _problem(fleet_limit_override=20)
    candidate, _, later_id = _zero_headway_candidate(problem)
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=tuple(
                replace(item, previous_c_headway=1) if item.c_trip_id == later_id else item
                for item in candidate.exact_timetable
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "PREVIOUS_C_HEADWAY_MISMATCH" in validation.rejection_codes


def test_zero_regime_gap_claimed_as_one_is_rejected() -> None:
    problem, *_ = _problem(fleet_limit_override=20)
    candidate, *_ = _zero_headway_candidate(problem)
    regime_index = next(
        index
        for index, regime in enumerate(candidate.headway_regimes)
        if 0 in regime.actual_headway_sequence
    )
    regime = candidate.headway_regimes[regime_index]
    claimed = tuple(1 if item == 0 else item for item in regime.actual_headway_sequence)
    regimes = list(candidate.headway_regimes)
    regimes[regime_index] = replace(
        regime,
        actual_headway_sequence=claimed,
    )
    tampered = _refingerprint(
        problem,
        replace(candidate, headway_regimes=tuple(regimes)),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_SEQUENCE_MISMATCH" in validation.rejection_codes
    assert "CANDIDATE_FINGERPRINT_MISMATCH" not in validation.rejection_codes


def test_zero_headway_with_insufficient_fleet_fails_existing_fleet_rules() -> None:
    sufficient_problem, *_ = _problem(fleet_limit_override=20)
    candidate, *_ = _zero_headway_candidate(sufficient_problem)
    insufficient_problem, *_ = _problem(fleet_limit_override=1)
    candidate_for_insufficient_problem = _refingerprint(
        insufficient_problem,
        candidate,
    )

    validation = validate_and_build_solution_v1(
        insufficient_problem,
        candidate_for_insufficient_problem,
    )

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "AVAILABLE_FLEET_LIMIT_EXCEEDED" in validation.rejection_codes
    assert "HEADWAY_REGIME_SEQUENCE_MISMATCH" not in validation.rejection_codes
    assert "PREVIOUS_C_HEADWAY_MISMATCH" not in validation.rejection_codes


def test_invalid_execution_state_is_completed_model_invalid_not_not_run() -> None:
    problem, *_ = _problem()
    invalid_run = SolverRunResultV1(
        execution_status=SolverExecutionStatus.NOT_RUN,
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter="invalid_test_adapter",
        solve_duration_seconds=0.1,
        candidate=None,
        explanations=("invalid",),
        limitations=(),
    )

    outcome = run_schedule_solver_v1(problem, _StaticSolver(invalid_run))

    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.MODEL_INVALID
    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID


def test_solution_reports_modes_locks_and_actual_maximum_vehicle_use() -> None:
    problem, *_ = _problem()
    outcome = run_schedule_solver_v1(problem, HeuristicScheduleSolverAdapter())
    assert outcome.solution is not None
    solution = outcome.solution
    lock_fields = {lock.field for lock in solution.operating_parameter_locks}
    assert {
        "fleet_constraint_mode",
        "initial_fleet_positioning_mode",
        "direction_trip_lock_mode",
    } <= lock_fields
    events = []
    for assignment in solution.fleet_assignment:
        events.append((assignment.departure_time, 1))
        events.append((assignment.ready_time, -1))
    active = 0
    maximum = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        maximum = max(maximum, active)
    assert solution.maximum_simultaneous_vehicle_use == maximum
    assert maximum <= solution.minimum_required_fleet
