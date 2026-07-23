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
    DepartureTerminal,
    GenerationResultStatus,
    HeuristicScheduleSolverAdapter,
    NativeSolverStatus,
    NormalizationOptions,
    OperatingDayType,
    RawCandidateTripV1,
    RawHeadwayRegimeV1,
    RawScheduleCandidateV1,
    ScenarioBEvaluationPolicyV1,
    ScheduleProblemError,
    SolverExecutionStatus,
    SolverRunResultV1,
    TurnaroundMinutes,
    build_schedule_problem_v1,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
    run_schedule_solver_v1,
    scenario_fingerprint,
    schedule_outcome_to_contract_dict,
    schedule_solution_to_contract_dict,
    validate_and_build_solution_v1,
)
from bus_schedule_engine.contracts_v1.fleet_assignment import assign_contract_v1_fleet
from bus_schedule_engine.contracts_v1.solver_fingerprints import candidate_fingerprint
from bus_schedule_engine.contracts_v1.solver_problem import (
    HEURISTIC_TURNAROUND_BRIDGE_MODE,
    RUNTIME_LOCK_MODE,
    TURNAROUND_APPLICATION_MODE,
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

    volumes = [10] * 7 if low_demand else [150, 150, 30, 30, 150, 150, 0]
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


def _contract_problem(
    parameters: ScenarioParameters,
    trips: list[Trip],
    *,
    fleet_limit: int,
    turnaround: tuple[int, int],
):
    demand = []
    for direction in (
        Direction.TERMINAL_1_TO_2,
        Direction.TERMINAL_2_TO_1,
    ):
        start = min(trip.departure_seconds for trip in trips if trip.direction == direction)
        coverage_end = (
            max(trip.departure_seconds for trip in trips if trip.direction == direction) + 60
        )
        while start < coverage_end:
            end = min(start + 60 * 60, coverage_end)
            demand.append(
                DemandRecord(
                    period_start=date(2026, 7, 1),
                    period_end=date(2026, 7, 7),
                    observation_days=1,
                    block_start_seconds=start,
                    block_end_seconds=end,
                    direction=direction,
                    passenger_volume=0,
                    volume_type=VolumeType.AVERAGE_DAY,
                )
            )
            start = end
    imported = ImportedWorkbook(
        parameters_a=parameters,
        trips_a=[replace(trip, scenario="A") for trip in trips],
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )
    normalized = normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="solver-v1-h2-fixture",
            imported_at=datetime(2026, 7, 23, 8, 0, tzinfo=UTC),
            operating_day_type_a=OperatingDayType.WEEKDAY,
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_a=fleet_limit,
            available_fleet_limit_b=fleet_limit,
            demand_confidence=DemandConfidence.HIGH,
        ),
    )
    scenario_b = replace(
        normalized.scenario_b,
        turnaround_minutes=TurnaroundMinutes(
            terminal_1=turnaround[0],
            terminal_2=turnaround[1],
        ),
    )
    normalized = replace(
        normalized,
        scenario_b=scenario_b,
        scenario_b_fingerprint=scenario_fingerprint(scenario_b),
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    return build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        demand,
        ScenarioCConfig(),
    )


def _turnaround_problem(
    *,
    turnaround: tuple[int, int] = (5, 20),
    fleet_limit: int = 2,
):
    parameters = ScenarioParameters(
        route_id="TURNAROUND-V1-H2",
        route_name="Runtime and turnaround authority",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=30,
        total_daily_trips=4,
        terminal_1_name="Terminal 1",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=7 * 3600,
        terminal_2_name="Terminal 2",
        terminal_2_first_departure=6 * 3600 + 15 * 60,
        terminal_2_last_departure=7 * 3600 + 15 * 60,
        vehicle_capacity_passengers=60,
        minimum_layover_minutes=5,
    )
    definitions = (
        ("B-O-1", Direction.TERMINAL_1_TO_2, 6 * 3600),
        ("B-I-1", Direction.TERMINAL_2_TO_1, 6 * 3600 + 15 * 60),
        ("B-O-2", Direction.TERMINAL_1_TO_2, 7 * 3600),
        ("B-I-2", Direction.TERMINAL_2_TO_1, 7 * 3600 + 15 * 60),
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=trip_id,
            departure_terminal=parameters.terminal_for_direction(direction),
            direction=direction,
            departure_seconds=departure,
            arrival_seconds=departure + 30 * 60,
        )
        for trip_id, direction, departure in definitions
    ]
    return (
        _contract_problem(
            parameters,
            trips,
            fleet_limit=fleet_limit,
            turnaround=turnaround,
        ),
        parameters,
        trips,
    )


def _runtime_problem(
    *,
    first_runtime: int = 55,
    fleet_limit: int = 8,
):
    parameters = ScenarioParameters(
        route_id="RUNTIME-V1-H2",
        route_name="Exact source runtime authority",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=60,
        allowed_trip_runtime_minutes=(55, 65),
        total_daily_trips=4,
        terminal_1_name="Terminal 1",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=9 * 3600,
        terminal_2_name="Terminal 2",
        terminal_2_first_departure=6 * 3600 + 10 * 60,
        terminal_2_last_departure=9 * 3600 + 10 * 60,
        vehicle_capacity_passengers=60,
        minimum_layover_minutes=5,
    )
    definitions = (
        ("B-O-1", Direction.TERMINAL_1_TO_2, 6 * 3600, first_runtime),
        ("B-I-1", Direction.TERMINAL_2_TO_1, 6 * 3600 + 10 * 60, 65),
        ("B-O-2", Direction.TERMINAL_1_TO_2, 9 * 3600, 65),
        ("B-I-2", Direction.TERMINAL_2_TO_1, 9 * 3600 + 10 * 60, 55),
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=trip_id,
            departure_terminal=parameters.terminal_for_direction(direction),
            direction=direction,
            departure_seconds=departure,
            arrival_seconds=departure + runtime * 60,
        )
        for trip_id, direction, departure, runtime in definitions
    ]
    return (
        _contract_problem(
            parameters,
            trips,
            fleet_limit=fleet_limit,
            turnaround=(5, 5),
        ),
        parameters,
        trips,
    )


def _two_trip_turnaround_problem(
    *,
    inbound_departure: int,
    fleet_limit: int,
):
    parameters = ScenarioParameters(
        route_id="TURNAROUND-CHAIN-V1-H2",
        route_name="Arrival-terminal turnaround chain",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=30,
        total_daily_trips=2,
        terminal_1_name="Terminal 1",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=6 * 3600,
        terminal_2_name="Terminal 2",
        terminal_2_first_departure=inbound_departure,
        terminal_2_last_departure=inbound_departure,
        vehicle_capacity_passengers=60,
        minimum_layover_minutes=5,
    )
    trips = [
        Trip(
            scenario="B",
            trip_id="B-O-1",
            departure_terminal=parameters.terminal_1_name,
            direction=Direction.TERMINAL_1_TO_2,
            departure_seconds=6 * 3600,
            arrival_seconds=6 * 3600 + 30 * 60,
        ),
        Trip(
            scenario="B",
            trip_id="B-I-1",
            departure_terminal=parameters.terminal_2_name,
            direction=Direction.TERMINAL_2_TO_1,
            departure_seconds=inbound_departure,
            arrival_seconds=inbound_departure + 30 * 60,
        ),
    ]
    return _contract_problem(
        parameters,
        trips,
        fleet_limit=fleet_limit,
        turnaround=(5, 20),
    )


def _baseline_candidate(problem) -> RawScheduleCandidateV1:
    source_rows = sorted(
        problem.normalized_inputs.scenario_b.exact_timetable,
        key=lambda item: (item.departure_time, item.trip_id),
    )
    c_id_by_source = {
        trip.trip_id: f"C-{index:04d}" for index, trip in enumerate(source_rows, start=1)
    }
    previous_b = _previous_headways(
        [(trip.direction, trip.departure_time, trip.trip_id) for trip in source_rows]
    )
    raw_trips = tuple(
        RawCandidateTripV1(
            c_trip_id=c_id_by_source[trip.trip_id],
            source_b_trip_id=trip.trip_id,
            direction=trip.direction,
            departure_terminal=trip.departure_terminal,
            b_departure_time=trip.departure_time,
            c_departure_time=trip.departure_time,
            arrival_time=trip.departure_time + trip.runtime_minutes * 60,
            runtime_minutes=trip.runtime_minutes,
            shift_minutes=0,
            previous_b_headway=previous_b[trip.trip_id],
            previous_c_headway=previous_b[trip.trip_id],
            headway_regime_id=f"REGIME-{trip.direction.value}",
            change_reason="V1-H2 authority fixture",
        )
        for trip in source_rows
    )
    regimes: list[RawHeadwayRegimeV1] = []
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        members = [trip for trip in raw_trips if trip.direction == direction]
        gaps = tuple(
            (right.c_departure_time - left.c_departure_time) / 60
            for left, right in zip(members, members[1:], strict=False)
        )
        regimes.append(
            RawHeadwayRegimeV1(
                regime_id=f"REGIME-{direction.value}",
                direction=direction,
                start_time=members[0].c_departure_time,
                end_time=members[-1].c_departure_time,
                trip_count=len(members),
                target_headway=(sum(gaps) / len(gaps) if gaps else 60),
                actual_headway_sequence=gaps,
                boundary_reason="FIRST_SERVICE_CONSTRAINT",
                legacy_regularity_status="REGULAR",
            )
        )
    raw_regimes = tuple(regimes)
    adapter_id = "legacy_heuristic_v1"
    return RawScheduleCandidateV1(
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter=adapter_id,
        solve_duration_seconds=0,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=problem.problem_fingerprint,
            solver_adapter=adapter_id,
            exact_timetable=raw_trips,
            headway_regimes=raw_regimes,
        ),
        exact_timetable=raw_trips,
        headway_regimes=raw_regimes,
        explanation="V1-H2 exact authority candidate",
        limitations=(),
    )


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


def test_problem_binds_scenario_default_and_exact_source_runtime_mapping() -> None:
    problem, _, _ = _runtime_problem(first_runtime=55)
    changed_problem, _, _ = _runtime_problem(first_runtime=56)

    assert problem.normalized_inputs.scenario_b.trip_runtime_minutes == 60
    assert problem.legacy_parameters.default_trip_runtime_minutes == 65
    assert {
        trip.runtime_minutes for trip in problem.normalized_inputs.scenario_b.exact_timetable
    } == {55, 65}
    assert changed_problem.normalized_inputs.scenario_b.trip_runtime_minutes == 60
    assert problem.problem_fingerprint != changed_problem.problem_fingerprint


def test_fleet_assessment_uses_each_exact_runtime_not_scenario_or_fallback() -> None:
    problem, _, _ = _runtime_problem()
    scenario = problem.normalized_inputs.scenario_b
    fleet = problem.b_evaluation.fleet_assessment
    ready_by_trip = {
        event.trip_id: event.event_time
        for event in (*fleet.terminal_1_events, *fleet.terminal_2_events)
        if event.event_type == "READY"
    }
    source_by_id = {trip.trip_id: trip for trip in scenario.exact_timetable}

    assert ready_by_trip["B-O-1"] == (source_by_id["B-O-1"].departure_time + 55 * 60 + 5 * 60)
    assert ready_by_trip["B-I-1"] == (source_by_id["B-I-1"].departure_time + 65 * 60 + 5 * 60)
    assert ready_by_trip["B-O-1"] != (
        source_by_id["B-O-1"].departure_time + scenario.trip_runtime_minutes * 60 + 5 * 60
    )
    assert ready_by_trip["B-O-1"] != (
        source_by_id["B-O-1"].departure_time
        + problem.legacy_parameters.default_trip_runtime_minutes * 60
        + 5 * 60
    )


def test_problem_accepts_5_20_and_derives_conservative_heuristic_bridge() -> None:
    problem, parameters, _ = _turnaround_problem()

    assert parameters.effective_layover_minutes == 5
    assert problem.normalized_inputs.scenario_b.turnaround_minutes == TurnaroundMinutes(
        terminal_1=5,
        terminal_2=20,
    )
    assert problem.legacy_parameters.effective_layover_minutes == 20
    assert problem.legacy_parameters is not parameters


def test_problem_fingerprint_changes_for_each_terminal_turnaround() -> None:
    baseline, _, _ = _turnaround_problem(turnaround=(5, 20))
    terminal_1_changed, _, _ = _turnaround_problem(turnaround=(6, 20))
    terminal_2_changed, _, _ = _turnaround_problem(turnaround=(5, 21))

    assert baseline.problem_fingerprint != terminal_1_changed.problem_fingerprint
    assert baseline.problem_fingerprint != terminal_2_changed.problem_fingerprint
    assert terminal_1_changed.problem_fingerprint != terminal_2_changed.problem_fingerprint


def test_asymmetric_bridge_exhaustion_is_unknown_and_disclosed() -> None:
    problem, _, _ = _turnaround_problem()

    run = HeuristicScheduleSolverAdapter().solve(problem)

    assert run.candidate is None
    assert run.solver_status == NativeSolverStatus.UNKNOWN
    assert any(HEURISTIC_TURNAROUND_BRIDGE_MODE in item for item in run.limitations)
    assert any("scalar 20 minutes" in item for item in run.limitations)


def test_exact_5_20_validation_accepts_candidate_stricter_bridge_misses() -> None:
    problem, parameters, legacy_trips = _turnaround_problem()
    candidate = _baseline_candidate(problem)
    validation = validate_and_build_solution_v1(problem, candidate)
    conservative_legacy = assign_fleet(
        legacy_trips,
        replace(parameters, minimum_layover_minutes=20),
    )

    assert conservative_legacy.minimum_vehicles == 3
    assert validation.status == CandidateValidationStatus.ACCEPTED
    assert validation.solution is not None
    solution = validation.solution
    assert solution.minimum_required_fleet == 2
    assert len({item.vehicle_id for item in solution.fleet_assignment}) == 2
    assert solution.minimum_required_fleet == (
        solution.recommended_initial_fleet_terminal_1
        + solution.recommended_initial_fleet_terminal_2
    )
    for assignment in solution.fleet_assignment:
        expected_turnaround = (
            5 if assignment.arrival_terminal == DepartureTerminal.TERMINAL_1 else 20
        )
        assert assignment.ready_time == assignment.arrival_time + expected_turnaround * 60


def test_ready_at_same_timestamp_is_available_before_departure() -> None:
    problem = _two_trip_turnaround_problem(
        inbound_departure=6 * 3600 + 50 * 60,
        fleet_limit=1,
    )
    candidate = _baseline_candidate(problem)
    assignment = assign_contract_v1_fleet(
        candidate.exact_timetable,
        problem.normalized_inputs.scenario_b.exact_timetable,
        problem.normalized_inputs.scenario_b.turnaround_minutes,
        problem.normalized_inputs.scenario_b.available_fleet_limit,
    )
    validation = validate_and_build_solution_v1(problem, candidate)

    assert assignment.vehicle_count == 1
    assert assignment.assignments[0].ready_time == assignment.assignments[1].departure_time
    assert assignment.assignments[0].vehicle_id == assignment.assignments[1].vehicle_id
    assert validation.status == CandidateValidationStatus.ACCEPTED


def test_candidate_requiring_shorter_terminal_2_turnaround_is_rejected() -> None:
    problem = _two_trip_turnaround_problem(
        inbound_departure=6 * 3600 + 49 * 60,
        fleet_limit=1,
    )
    candidate = _baseline_candidate(problem)

    validation = validate_and_build_solution_v1(problem, candidate)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "AVAILABLE_FLEET_LIMIT_EXCEEDED" in validation.rejection_codes
    assert validation.fleet_assessment is not None
    assert validation.fleet_assessment.minimum_required_fleet == 2


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


def test_case_12_and_23_combined_unsuitable_b_returns_sanitized_no_run() -> None:
    parameters, trips, _, fleet_limit = _fixture()
    combined_demand = [
        DemandRecord(
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 7),
            observation_days=1,
            block_start_seconds=(6 + index) * 3600,
            block_end_seconds=(7 + index) * 3600,
            direction=Direction.COMBINED,
            passenger_volume=300 if index == 0 else 0,
            volume_type=VolumeType.AVERAGE_DAY,
        )
        for index in range(7)
    ]
    normalized = _normalized(
        parameters,
        trips,
        combined_demand,
        fleet_limit,
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        combined_demand,
        ScenarioCConfig(),
    )

    outcome = run_schedule_solver_v1(problem, _BombSolver())

    assert (
        evaluation.evaluation.disposition == BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE
    )
    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_INSUFFICIENT_DATA
    assert outcome.execution_status == SolverExecutionStatus.NOT_RUN
    assert outcome.solver_status is None
    assert outcome.solver_adapter is None
    assert outcome.solve_duration_seconds == 0
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is None
    assert any(
        "COMBINED_DEMAND_UNSUPPORTED_FOR_DIRECTIONAL_C" in item for item in outcome.limitations
    )


def test_case_24_technically_infeasible_b_with_incomplete_coverage_does_not_run() -> None:
    parameters, trips, _, _ = _fixture()
    normalized = _normalized(parameters, trips, [], 1)
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

    assert (
        evaluation.evaluation.disposition
        == BDisposition.TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION
    )
    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_INSUFFICIENT_DATA
    assert outcome.execution_status == SolverExecutionStatus.NOT_RUN


def test_case_25_fixed_parameter_infeasibility_precedes_demand_coverage() -> None:
    parameters, trips, _, fleet_limit = _fixture()
    normalized = _normalized(parameters, trips, [], fleet_limit)
    evaluation = evaluate_scenario_b_v1(normalized)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        [],
        ScenarioCConfig(),
    )
    proven = replace(
        problem,
        b_evaluation=replace(
            problem.b_evaluation,
            evaluation=replace(
                problem.b_evaluation.evaluation,
                disposition=BDisposition.PARAMETERS_INFEASIBLE,
            ),
        ),
    )

    outcome = run_schedule_solver_v1(proven, _BombSolver())

    assert outcome.result_status == GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS
    assert outcome.execution_status == SolverExecutionStatus.NOT_RUN
    assert outcome.solution is None


def test_case_26_direct_candidate_validation_rejects_missing_c_authority() -> None:
    full_problem, parameters, trips, _, fleet_limit = _problem()
    candidate = _candidate(full_problem)
    normalized = _normalized(parameters, trips, [], fleet_limit)
    evaluation = evaluate_scenario_b_v1(normalized)
    incomplete_problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        [],
        ScenarioCConfig(),
    )
    bypass_candidate = _refingerprint(incomplete_problem, candidate)

    validation = validate_and_build_solution_v1(
        incomplete_problem,
        bypass_candidate,
    )

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "DEMAND_COVERAGE_INCOMPLETE_FOR_AUTHORITATIVE_C" in validation.rejection_codes
    assert validation.solution is None


def test_case_28_coverage_change_alters_problem_fingerprint() -> None:
    full_problem, parameters, trips, demand, fleet_limit = _problem()
    gapped_demand = [item for item in demand if item.block_start_seconds < 12 * 3600]
    gapped_normalized = _normalized(
        parameters,
        trips,
        gapped_demand,
        fleet_limit,
    )
    gapped_evaluation = evaluate_scenario_b_v1(gapped_normalized)
    gapped_problem = build_schedule_problem_v1(
        gapped_normalized,
        gapped_evaluation,
        parameters,
        trips,
        gapped_demand,
        ScenarioCConfig(),
    )

    assert full_problem.problem_fingerprint != gapped_problem.problem_fingerprint
    assert full_problem.b_evaluation.demand_resolution.coverage_assessment.directional_c_generation_supported
    assert not (
        gapped_problem.b_evaluation.demand_resolution.coverage_assessment.directional_c_generation_supported
    )


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

    assert problem.b_evaluation.demand_resolution.coverage_assessment.directional_c_generation_supported
    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.FEASIBLE
    assert outcome.solution is not None
    assert len(outcome.solution.solution_fingerprint) == 64
    assert tuple(trips) == baseline
    assert timetable_fingerprint(trips) == baseline_fingerprint
    assert problem.normalized_inputs.scenario_b == scenario_b_before
    assert problem.legacy_parameters.effective_layover_minutes == (
        parameters.effective_layover_minutes
    )
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


def test_candidate_arrival_inconsistent_with_locked_source_runtime_is_rejected() -> None:
    problem, _, _ = _runtime_problem()
    candidate = _baseline_candidate(problem)
    first = candidate.exact_timetable[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=(
                replace(first, arrival_time=first.arrival_time + 60),
                *candidate.exact_timetable[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "CANDIDATE_ARRIVAL_RUNTIME_MISMATCH" in validation.rejection_codes
    assert "SOURCE_RUNTIME_LOCK_VIOLATION" not in validation.rejection_codes
    assert "CANDIDATE_FINGERPRINT_MISMATCH" not in validation.rejection_codes


def test_accepted_arrivals_and_ready_times_use_source_runtime_and_arrival_terminal() -> None:
    problem, _, _ = _runtime_problem()
    candidate = _baseline_candidate(problem)

    validation = validate_and_build_solution_v1(problem, candidate)

    assert validation.solution is not None
    source_by_id = {
        trip.trip_id: trip for trip in problem.normalized_inputs.scenario_b.exact_timetable
    }
    candidate_by_id = {trip.c_trip_id: trip for trip in candidate.exact_timetable}
    for assignment in validation.solution.fleet_assignment:
        raw = candidate_by_id[assignment.c_trip_id]
        source = source_by_id[raw.source_b_trip_id]
        assert assignment.arrival_time == raw.c_departure_time + source.runtime_minutes * 60
        assert assignment.ready_time == assignment.arrival_time + 5 * 60
    locks = {lock.field: lock.value for lock in validation.solution.operating_parameter_locks}
    assert locks["trip_runtime_minutes"] == 60
    assert locks["exact_trip_runtime_minutes_by_source_b_trip_id"] == {
        trip_id: source_by_id[trip_id].runtime_minutes for trip_id in sorted(source_by_id)
    }
    assert locks["turnaround_minutes"] == {"terminal_1": 5, "terminal_2": 5}
    assert locks["turnaround_application_mode"] == TURNAROUND_APPLICATION_MODE


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


def test_solution_fingerprint_changes_with_authoritative_arrival_ready_evidence() -> None:
    first_problem, _, _ = _runtime_problem(first_runtime=55)
    second_problem, _, _ = _runtime_problem(first_runtime=56)
    first_validation = validate_and_build_solution_v1(
        first_problem,
        _baseline_candidate(first_problem),
    )
    second_validation = validate_and_build_solution_v1(
        second_problem,
        _baseline_candidate(second_problem),
    )

    assert first_validation.solution is not None
    assert second_validation.solution is not None
    first_assignment = next(
        item for item in first_validation.solution.fleet_assignment if item.c_trip_id == "C-0001"
    )
    second_assignment = next(
        item for item in second_validation.solution.fleet_assignment if item.c_trip_id == "C-0001"
    )
    assert first_assignment.arrival_time != second_assignment.arrival_time
    assert first_assignment.ready_time != second_assignment.ready_time
    assert (
        first_validation.solution.solution_fingerprint
        != second_validation.solution.solution_fingerprint
    )


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
        "trip_runtime_minutes",
        "fleet_constraint_mode",
        "initial_fleet_positioning_mode",
        "direction_trip_lock_mode",
        "runtime_lock_mode",
        "exact_trip_runtime_minutes_by_source_b_trip_id",
        "turnaround_minutes",
        "turnaround_application_mode",
        "heuristic_turnaround_bridge_mode",
        "heuristic_turnaround_bridge_value_minutes",
    } <= lock_fields
    locks = {lock.field: lock.value for lock in solution.operating_parameter_locks}
    assert locks["runtime_lock_mode"] == RUNTIME_LOCK_MODE
    assert locks["turnaround_application_mode"] == TURNAROUND_APPLICATION_MODE
    assert locks["heuristic_turnaround_bridge_mode"] == (HEURISTIC_TURNAROUND_BRIDGE_MODE)
    assert list(locks["exact_trip_runtime_minutes_by_source_b_trip_id"]) == sorted(
        locks["exact_trip_runtime_minutes_by_source_b_trip_id"]
    )
    assert all(
        lock.source_fingerprint == problem.normalized_inputs.scenario_b_fingerprint
        for lock in solution.operating_parameter_locks
    )
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
