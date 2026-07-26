from __future__ import annotations

import inspect
import itertools
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import ortools
import pytest
from ortools.sat.python import cp_model

import bus_schedule_engine.contracts_v1.ortools_solver as ortools_solver_module
import bus_schedule_engine.contracts_v1.solver_orchestration as solver_orchestration_module
import bus_schedule_engine.optimization_service as optimization_service
from bus_schedule_engine.contracts_v1 import (
    BoundaryConvention,
    CandidateValidationStatus,
    ContractDirection,
    DemandConfidence,
    DirectionTripLockMode,
    FleetConstraintMode,
    GenerationResultStatus,
    InitialFleetPositioningMode,
    NativeSolverStatus,
    NormalizationOptions,
    OperatingDayType,
    OrToolsCpSatScheduleSolver,
    ScenarioBEvaluationPolicyV1,
    SolverPolicyV1,
    TurnaroundMinutes,
    assess_scenario_b_fleet_v1,
    build_ortools_schedule_request_v1,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
    run_schedule_solver_v1,
    validate_and_build_solution_v1,
)
from bus_schedule_engine.contracts_v1.solver_fingerprints import candidate_fingerprint
from bus_schedule_engine.contracts_v1.solver_problem import (
    empty_adapter_context_fingerprint,
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
from bus_schedule_engine.optimization_service import SolverChoice


def _request(
    *,
    outbound_minutes: tuple[int, ...],
    inbound_minutes: tuple[int, ...],
    outbound_runtimes: tuple[int, ...] | None = None,
    inbound_runtimes: tuple[int, ...] | None = None,
    turnaround: tuple[int, int] = (5, 5),
    fleet_limit: int = 2,
    second_offset: int = 0,
    with_demand: bool = True,
    solver_policy: SolverPolicyV1 | None = None,
    route_id: str = "ORTOOLS-TINY",
):
    outbound_runtimes = outbound_runtimes or (30,) * len(outbound_minutes)
    inbound_runtimes = inbound_runtimes or (30,) * len(inbound_minutes)
    all_runtimes = (*outbound_runtimes, *inbound_runtimes)
    parameters = ScenarioParameters(
        route_id=route_id,
        route_name="OR-Tools fixed-resource proof fixture",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=all_runtimes[0],
        allowed_trip_runtime_minutes=(min(all_runtimes), max(all_runtimes)),
        total_daily_trips=len(outbound_minutes) + len(inbound_minutes),
        terminal_1_name="Terminal One",
        terminal_1_first_departure=outbound_minutes[0] * 60 + second_offset,
        terminal_1_last_departure=outbound_minutes[-1] * 60 + second_offset,
        terminal_2_name="Terminal Two",
        terminal_2_first_departure=inbound_minutes[0] * 60 + second_offset,
        terminal_2_last_departure=inbound_minutes[-1] * 60 + second_offset,
        vehicle_capacity_passengers=60,
        minimum_layover_minutes=min(turnaround),
    )
    definitions = (
        (
            Direction.TERMINAL_1_TO_2,
            outbound_minutes,
            outbound_runtimes,
            "O",
        ),
        (
            Direction.TERMINAL_2_TO_1,
            inbound_minutes,
            inbound_runtimes,
            "I",
        ),
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=f"B-{label}-{index:02d}",
            departure_terminal=parameters.terminal_for_direction(direction),
            direction=direction,
            departure_seconds=departure * 60 + second_offset,
            arrival_seconds=(departure + runtime) * 60 + second_offset,
        )
        for direction, departures, runtimes, label in definitions
        for index, (departure, runtime) in enumerate(
            zip(departures, runtimes, strict=True),
            start=1,
        )
    ]
    demand: list[DemandRecord] = []
    if with_demand:
        for direction, departures, _, _ in definitions:
            start = departures[0] * 60
            coverage_end = departures[-1] * 60 + 60
            while start < coverage_end:
                end = min(start + 3600, coverage_end)
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
        parameters_a=replace(parameters),
        trips_a=[replace(trip, scenario="A") for trip in trips],
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )
    normalized = normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id=f"{route_id.lower()}-fixture",
            imported_at=datetime(2026, 7, 26, 9, 0, tzinfo=UTC),
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
    from bus_schedule_engine.contracts_v1 import scenario_fingerprint

    normalized = replace(
        normalized,
        scenario_b=scenario_b,
        scenario_b_fingerprint=scenario_fingerprint(scenario_b),
    )
    policy = ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(normalized, policy)
    context, solver = build_ortools_schedule_request_v1(
        normalized,
        evaluation,
        evaluation_policy=policy,
        solver_policy=solver_policy,
    )
    return context, solver, imported


def _one_vehicle_request(**kwargs):
    return _request(
        outbound_minutes=(360,),
        inbound_minutes=(395,),
        fleet_limit=1,
        route_id="ORTOOLS-ONE-VEHICLE",
        **kwargs,
    )


def _two_vehicle_request(*, fleet_limit: int = 2, **kwargs):
    return _request(
        outbound_minutes=(360,),
        inbound_minutes=(365,),
        fleet_limit=fleet_limit,
        route_id=f"ORTOOLS-TWO-VEHICLES-{fleet_limit}",
        **kwargs,
    )


def _unequal_turnaround_request(**kwargs):
    return _request(
        outbound_minutes=(360, 445),
        inbound_minutes=(395, 480),
        turnaround=(20, 5),
        fleet_limit=1,
        route_id="ORTOOLS-UNEQUAL-TURNAROUND",
        **kwargs,
    )


def _source_runtime_request(**kwargs):
    return _request(
        outbound_minutes=(360, 455),
        inbound_minutes=(395, 485),
        outbound_runtimes=(30, 25),
        inbound_runtimes=(40, 35),
        turnaround=(20, 5),
        fleet_limit=1,
        route_id="ORTOOLS-SOURCE-RUNTIMES",
        **kwargs,
    )


def _six_trip_respace_request(*, fleet_limit: int = 2, **kwargs):
    return _request(
        outbound_minutes=(360, 361, 420),
        inbound_minutes=(365, 366, 425),
        outbound_runtimes=(20, 20, 20),
        inbound_runtimes=(20, 20, 20),
        turnaround=(5, 5),
        fleet_limit=fleet_limit,
        route_id=f"ORTOOLS-SIX-TRIP-{fleet_limit}",
        **kwargs,
    )


def _eight_trip_respace_request(*, fleet_limit: int = 2, **kwargs):
    return _request(
        outbound_minutes=(360, 361, 362, 379),
        inbound_minutes=(361, 362, 363, 378),
        outbound_runtimes=(1, 1, 1, 1),
        inbound_runtimes=(1, 1, 1, 1),
        turnaround=(5, 5),
        fleet_limit=fleet_limit,
        route_id=f"ORTOOLS-EIGHT-TRIP-{fleet_limit}",
        **kwargs,
    )


def _refingerprint(context, candidate):
    return replace(
        candidate,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=context.problem.problem_fingerprint,
            solver_adapter=candidate.solver_adapter,
            exact_timetable=candidate.exact_timetable,
            headway_regimes=candidate.headway_regimes,
        ),
    )


def _enumeration_exists(context) -> bool:
    scenario = context.problem.scenario_b
    by_direction = {
        direction: tuple(
            sorted(
                (trip for trip in scenario.exact_timetable if trip.direction == direction),
                key=lambda item: (item.departure_time, item.trip_id),
            )
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    }

    def legal_sequences(trips):
        first = trips[0].departure_time // 60
        last = trips[-1].departure_time // 60
        middle_count = len(trips) - 2
        if middle_count <= 0:
            return ((first, last) if len(trips) == 2 else (first,),)
        return tuple(
            (first, *middle, last)
            for middle in itertools.combinations(range(first + 1, last), middle_count)
        )

    outbound_sequences = legal_sequences(by_direction[ContractDirection.OUTBOUND])
    inbound_sequences = legal_sequences(by_direction[ContractDirection.INBOUND])
    for outbound, inbound in itertools.product(outbound_sequences, inbound_sequences):
        solved = {
            trip.trip_id: minute
            for direction, sequence in (
                (ContractDirection.OUTBOUND, outbound),
                (ContractDirection.INBOUND, inbound),
            )
            for trip, minute in zip(by_direction[direction], sequence, strict=True)
        }
        exact = tuple(
            replace(
                trip,
                departure_time=solved[trip.trip_id] * 60,
                arrival_time=(solved[trip.trip_id] + trip.runtime_minutes) * 60,
            )
            for trip in scenario.exact_timetable
        )
        if assess_scenario_b_fleet_v1(replace(scenario, exact_timetable=exact)).feasible:
            return True
    return False


def test_ortools_imports_and_installed_version_matches_the_pin() -> None:
    assert ortools.__version__ == "9.15.6755"
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert '"ortools==9.15.6755"' in pyproject.read_text(encoding="utf-8")


def test_adapter_implements_the_existing_schedule_solver_shape() -> None:
    solver = OrToolsCpSatScheduleSolver()
    signature = inspect.signature(solver.solve)

    assert callable(solver.solve)
    assert tuple(signature.parameters) == ("problem",)


def test_adapter_id_is_exact() -> None:
    assert OrToolsCpSatScheduleSolver.adapter_id == "ortools_cp_sat_v1"


def test_request_builder_creates_the_canonical_context_and_empty_adapter_fingerprint() -> None:
    context, solver, _ = _one_vehicle_request()

    assert solver.adapter_id == context.problem.solver_adapter
    assert context.problem.adapter_context_fingerprint == empty_adapter_context_fingerprint()
    assert context.problem.direction_trip_lock_mode == DirectionTripLockMode.FIXED_BY_DIRECTION
    assert context.problem.fleet_constraint_mode == FleetConstraintMode.AVAILABLE_UPPER_BOUND
    assert (
        context.problem.initial_fleet_positioning_mode
        == InitialFleetPositioningMode.SOLVER_DETERMINED
    )
    assert context.problem.boundary_convention == BoundaryConvention.HALF_OPEN
    assert context.problem.direction_redistribution_authorization is None
    assert context.problem.fixed_initial_fleet is None
    assert context.problem.bounded_initial_fleet is None


def test_public_adapter_and_builder_signatures_are_stable() -> None:
    assert str(inspect.signature(OrToolsCpSatScheduleSolver.solve)) == (
        "(self, problem: 'ScheduleProblemV1') -> 'SolverRunResultV1'"
    )
    assert tuple(inspect.signature(build_ortools_schedule_request_v1).parameters) == (
        "normalized_inputs",
        "b_evaluation",
        "evaluation_policy",
        "solver_policy",
    )


def test_one_vehicle_operates_one_feasible_alternating_chain() -> None:
    context, solver, _ = _one_vehicle_request()

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solver_status == NativeSolverStatus.OPTIMAL
    assert outcome.solution is not None
    assert outcome.solution.minimum_required_fleet == 1


def test_two_vehicles_are_unavoidable_in_the_fixed_tiny_timetable() -> None:
    context, solver, _ = _two_vehicle_request()

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.solution is not None
    assert outcome.solution.minimum_required_fleet == 2


def test_early_departures_require_an_initial_split_at_both_terminals() -> None:
    context, solver, _ = _two_vehicle_request()

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.solution is not None
    assert outcome.solution.recommended_initial_fleet_terminal_1 == 1
    assert outcome.solution.recommended_initial_fleet_terminal_2 == 1


def test_ready_at_the_exact_departure_minute_is_usable() -> None:
    context, solver, _ = _one_vehicle_request()

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.solution is not None
    assignments = sorted(outcome.solution.fleet_assignment, key=lambda item: item.departure_time)
    assert assignments[0].ready_time == assignments[1].departure_time
    assert assignments[0].vehicle_id == assignments[1].vehicle_id


def test_unequal_turnarounds_are_applied_at_the_correct_arrival_terminals() -> None:
    context, solver, _ = _unequal_turnaround_request()

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.solution is not None
    for assignment in outcome.solution.fleet_assignment:
        expected = 20 if assignment.arrival_terminal.value == "terminal_1" else 5
        assert assignment.ready_time == assignment.arrival_time + expected * 60


def test_problem_feasible_exactly_at_available_fleet_limit_is_accepted() -> None:
    context, solver, _ = _two_vehicle_request(fleet_limit=2)

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solution is not None
    assert outcome.solution.minimum_required_fleet == outcome.solution.available_fleet_limit == 2


def test_same_problem_below_minimum_fleet_is_infeasible() -> None:
    context, solver, _ = _two_vehicle_request(fleet_limit=1)

    run = solver.solve(context.problem)
    outcome = run_schedule_solver_v1(context, solver)

    assert run.solver_status == NativeSolverStatus.INFEASIBLE
    assert run.candidate is None
    assert outcome.result_status == GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS


def test_first_and_last_departures_remain_locked() -> None:
    context, solver, _ = _six_trip_respace_request()

    run = solver.solve(context.problem)

    assert run.candidate is not None
    for direction, first, last in (
        (ContractDirection.OUTBOUND, 360 * 60, 420 * 60),
        (ContractDirection.INBOUND, 365 * 60, 425 * 60),
    ):
        rows = sorted(
            (trip for trip in run.candidate.exact_timetable if trip.direction == direction),
            key=lambda item: item.c_departure_time,
        )
        assert rows[0].c_departure_time == first
        assert rows[-1].c_departure_time == last


def test_source_specific_runtimes_remain_exact() -> None:
    context, solver, _ = _source_runtime_request()

    run = solver.solve(context.problem)

    assert run.candidate is not None
    source = {trip.trip_id: trip for trip in context.problem.scenario_b.exact_timetable}
    for trip in run.candidate.exact_timetable:
        assert trip.runtime_minutes == source[trip.source_b_trip_id].runtime_minutes
        assert trip.arrival_time == trip.c_departure_time + trip.runtime_minutes * 60


def test_total_and_directional_trip_counts_remain_unchanged() -> None:
    context, solver, _ = _six_trip_respace_request()

    run = solver.solve(context.problem)

    assert run.candidate is not None
    assert len(run.candidate.exact_timetable) == 6
    assert (
        sum(trip.direction == ContractDirection.OUTBOUND for trip in run.candidate.exact_timetable)
        == 3
    )
    assert (
        sum(trip.direction == ContractDirection.INBOUND for trip in run.candidate.exact_timetable)
        == 3
    )


def test_source_trip_order_is_preserved_within_each_direction() -> None:
    context, solver, _ = _six_trip_respace_request()

    run = solver.solve(context.problem)

    assert run.candidate is not None
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        source_ids = [
            trip.trip_id
            for trip in sorted(
                (
                    trip
                    for trip in context.problem.scenario_b.exact_timetable
                    if trip.direction == direction
                ),
                key=lambda item: (item.departure_time, item.trip_id),
            )
        ]
        candidate_ids = [
            trip.source_b_trip_id
            for trip in sorted(
                (trip for trip in run.candidate.exact_timetable if trip.direction == direction),
                key=lambda item: item.c_departure_time,
            )
        ]
        assert candidate_ids == source_ids


def test_infeasible_b_is_respaced_into_a_feasible_c_when_locks_permit() -> None:
    context, solver, _ = _six_trip_respace_request()
    assert context.b_evaluation.fleet_assessment.minimum_required_fleet > 2

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.solution is not None
    assert outcome.solution.minimum_required_fleet == 2
    assert any(trip.shift_minutes != 0 for trip in outcome.solution.c_exact_timetable)


def test_real_cp_sat_candidate_becomes_accepted_only_after_independent_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, solver, _ = _six_trip_respace_request()
    calls = 0
    real_validator = solver_orchestration_module.validate_and_build_solution_v1

    def recording_candidate_validation(generation_context, candidate):
        nonlocal calls
        calls += 1
        return real_validator(generation_context, candidate)

    monkeypatch.setattr(
        solver_orchestration_module,
        "validate_and_build_solution_v1",
        recording_candidate_validation,
    )
    outcome = run_schedule_solver_v1(context, solver)

    assert calls == 1
    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solution is not None


def test_deliberately_corrupted_cp_sat_candidate_is_rejected() -> None:
    context, solver, _ = _source_runtime_request()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    first = run.candidate.exact_timetable[0]
    corrupted = _refingerprint(
        context,
        replace(
            run.candidate,
            exact_timetable=(
                replace(
                    first,
                    runtime_minutes=first.runtime_minutes + 1,
                    arrival_time=first.arrival_time + 60,
                ),
                *run.candidate.exact_timetable[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(context, corrupted)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "SOURCE_RUNTIME_LOCK_VIOLATION" in validation.rejection_codes

    class CorruptingSolver:
        adapter_id = solver.adapter_id

        def solve(self, problem):
            return replace(run, candidate=corrupted)

    outcome = run_schedule_solver_v1(context, CorruptingSolver())
    assert outcome.result_status == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is not None


def test_accepted_fleet_and_terminal_stock_evidence_reconcile() -> None:
    context, solver, _ = _two_vehicle_request()

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.solution is not None
    solution = outcome.solution
    assert solution.minimum_required_fleet == (
        solution.recommended_initial_fleet_terminal_1
        + solution.recommended_initial_fleet_terminal_2
    )
    assert all(
        event.stock_before >= 0 and event.stock_after >= 0
        for event in (
            *solution.vehicle_stock_profile_terminal_1,
            *solution.vehicle_stock_profile_terminal_2,
        )
    )


def test_ready_before_departure_ordering_is_visible_in_validated_stock_profile() -> None:
    context, solver, _ = _one_vehicle_request()

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.solution is not None
    events = outcome.solution.vehicle_stock_profile_terminal_2
    equal_time = [
        event
        for event in events
        if event.event_time == context.problem.scenario_b.first_departures.terminal_2
    ]
    assert [event.event_type for event in equal_time] == ["VEHICLE_READY", "DEPARTURE"]


@pytest.mark.parametrize(
    ("cp_status", "native_status"),
    (
        (cp_model.OPTIMAL, NativeSolverStatus.OPTIMAL),
        (cp_model.FEASIBLE, NativeSolverStatus.FEASIBLE),
        (cp_model.INFEASIBLE, NativeSolverStatus.INFEASIBLE),
        (cp_model.MODEL_INVALID, NativeSolverStatus.MODEL_INVALID),
        (cp_model.UNKNOWN, NativeSolverStatus.UNKNOWN),
    ),
)
def test_native_status_mapping_is_exact(cp_status, native_status) -> None:
    assert ortools_solver_module._map_cp_sat_status(cp_status) == native_status


@pytest.mark.parametrize(
    "cp_status",
    (cp_model.UNKNOWN, cp_model.INFEASIBLE, cp_model.MODEL_INVALID),
)
def test_non_candidate_native_statuses_contain_no_candidate(
    monkeypatch: pytest.MonkeyPatch,
    cp_status,
) -> None:
    context, solver, _ = _one_vehicle_request()
    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda self, model: cp_status)

    run = solver.solve(context.problem)

    assert run.solver_status == ortools_solver_module._map_cp_sat_status(cp_status)
    assert run.candidate is None


def test_non_minute_source_departures_return_model_invalid() -> None:
    context, solver, _ = _one_vehicle_request(second_offset=1, with_demand=False)

    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert run.candidate is None
    assert any("ORTOOLS_NON_MINUTE_ALIGNED_DEPARTURE" in item for item in run.explanations)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("direction_trip_lock_mode", DirectionTripLockMode.TOTAL_ONLY),
        ("fleet_constraint_mode", FleetConstraintMode.EXACT_SCHEDULED_FLEET),
        ("initial_fleet_positioning_mode", InitialFleetPositioningMode.FIXED),
        (
            "boundary_convention",
            BoundaryConvention.HALF_OPEN_WITH_FINAL_SENTINEL,
        ),
    ),
)
def test_unsupported_problem_modes_return_model_invalid(field, value) -> None:
    context, solver, _ = _one_vehicle_request()
    unsupported = replace(context.problem, **{field: value})

    run = solver.solve(unsupported)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert run.candidate is None


def test_model_has_no_optimization_objective() -> None:
    context, _, _ = _six_trip_respace_request()

    bundle = ortools_solver_module._build_cp_sat_model(context.problem)

    assert not bundle.model.proto.objective.vars


def test_model_has_no_vehicle_trip_minute_grid() -> None:
    context, _, _ = _six_trip_respace_request()

    bundle = ortools_solver_module._build_cp_sat_model(context.problem)
    variable_names = [variable.name for variable in bundle.model.proto.variables]

    assert len(variable_names) == 26
    assert not any("vehicle_" in name or "_minute_" in name for name in variable_names)
    assert not any(
        token in name
        for name in variable_names
        for token in ("demand", "headway", "load_factor", "shift", "objective")
    )


def test_ortools_adapter_never_imports_or_calls_the_heuristic_generator() -> None:
    source = Path(ortools_solver_module.__file__).read_text(encoding="utf-8")

    assert "generate_scenario_c" not in source
    assert "heuristic_solver" not in source
    assert "c_generator" not in source


def test_optimization_service_does_not_use_the_feasibility_only_adapter() -> None:
    source = Path(optimization_service.__file__).read_text(encoding="utf-8")

    assert "build_ortools_schedule_request_v1" not in source
    assert "OrToolsCpSatScheduleSolver" not in source
    for solver_choice in (SolverChoice.OR_TOOLS, SolverChoice.BOTH):
        optimization_service._validate_solver_choice(solver_choice)


def test_supplied_solver_controls_are_applied_and_disclosed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, solver, _ = _one_vehicle_request(
        solver_policy=SolverPolicyV1(
            time_limit_seconds=2.5,
            worker_count=3,
            random_seed=7,
        )
    )
    captured = {}

    def recording_solve(cp_solver, model):
        captured["time_limit"] = cp_solver.parameters.max_time_in_seconds
        captured["workers"] = cp_solver.parameters.num_search_workers
        captured["seed"] = cp_solver.parameters.random_seed
        return cp_model.UNKNOWN

    monkeypatch.setattr(cp_model.CpSolver, "solve", recording_solve)
    run = solver.solve(context.problem)

    assert captured == {"time_limit": 2.5, "workers": 3, "seed": 7}
    assert any("2.5 seconds" in item for item in run.limitations)
    assert any("worker count: 3" in item for item in run.limitations)
    assert any("random seed: 7" in item for item in run.limitations)
    assert any(f"OR-Tools version {ortools.__version__}" in item for item in run.limitations)


def test_omitted_solver_controls_use_deterministic_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, solver, _ = _one_vehicle_request()
    captured = {}

    def recording_solve(cp_solver, model):
        captured["workers"] = cp_solver.parameters.num_search_workers
        captured["seed"] = cp_solver.parameters.random_seed
        return cp_model.UNKNOWN

    monkeypatch.setattr(cp_model.CpSolver, "solve", recording_solve)
    solver.solve(context.problem)

    assert captured == {"workers": 1, "seed": 0}


def test_model_counts_are_exact_for_representative_tiny_fixtures() -> None:
    one_context, _, _ = _one_vehicle_request()
    six_context, _, _ = _six_trip_respace_request()

    one_proto = ortools_solver_module._build_cp_sat_model(one_context.problem).model.proto
    six_proto = ortools_solver_module._build_cp_sat_model(six_context.problem).model.proto

    assert (len(one_proto.variables), len(one_proto.constraints)) == (6, 11)
    assert (len(six_proto.variables), len(six_proto.constraints)) == (26, 51)


@pytest.mark.parametrize(
    ("request_factory", "fleet_limit"),
    (
        (_six_trip_respace_request, 2),
        (_eight_trip_respace_request, 2),
        (_six_trip_respace_request, 1),
        (_eight_trip_respace_request, 1),
    ),
)
def test_exhaustive_enumeration_agrees_with_cp_sat_existence(
    request_factory,
    fleet_limit: int,
) -> None:
    context, solver, _ = request_factory(fleet_limit=fleet_limit)

    enumeration_exists = _enumeration_exists(context)
    run = solver.solve(context.problem)
    cp_sat_exists = run.solver_status in {
        NativeSolverStatus.OPTIMAL,
        NativeSolverStatus.FEASIBLE,
    }

    assert cp_sat_exists == enumeration_exists


def test_repeated_single_worker_seed_zero_solves_are_deterministic() -> None:
    context, solver, _ = _six_trip_respace_request()

    first = solver.solve(context.problem)
    second = solver.solve(context.problem)

    assert first.candidate is not None
    assert second.candidate is not None
    assert first.candidate.exact_timetable == second.candidate.exact_timetable
    assert first.candidate.candidate_fingerprint == second.candidate.candidate_fingerprint


def test_candidate_and_regime_ids_are_deterministic() -> None:
    context, solver, _ = _six_trip_respace_request()

    run = solver.solve(context.problem)

    assert run.candidate is not None
    assert {trip.c_trip_id for trip in run.candidate.exact_timetable} == {
        f"C-ORTOOLS-{index:04d}" for index in range(1, 7)
    }
    assert {regime.regime_id for regime in run.candidate.headway_regimes} == {
        "ORTOOLS-OUTBOUND-FEASIBILITY",
        "ORTOOLS-INBOUND-FEASIBILITY",
    }


def test_feasibility_only_explanation_never_claims_best_timetable() -> None:
    context, solver, _ = _one_vehicle_request()

    run = solver.solve(context.problem)
    feasibility_model = ortools_solver_module._build_cp_sat_model(context.problem).model

    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert run.candidate is not None
    assert "no service-quality objective was optimized" in run.candidate.explanation
    assert "best timetable" not in run.candidate.explanation.lower()
    assert not feasibility_model.proto.objective.vars


def test_headway_regimes_cover_each_direction_and_report_exact_sequences() -> None:
    context, solver, _ = _six_trip_respace_request()

    run = solver.solve(context.problem)

    assert run.candidate is not None
    for regime in run.candidate.headway_regimes:
        members = sorted(
            (trip for trip in run.candidate.exact_timetable if trip.direction == regime.direction),
            key=lambda item: item.c_departure_time,
        )
        expected = tuple(
            (later.c_departure_time - earlier.c_departure_time) / 60
            for earlier, later in zip(members, members[1:], strict=False)
        )
        assert regime.trip_count == len(members)
        assert regime.start_time == members[0].c_departure_time
        assert regime.end_time == members[-1].c_departure_time
        assert regime.actual_headway_sequence == expected
        assert regime.target_headway > 0
        assert regime.boundary_reason == "FULL_DIRECTION_TECHNICAL_FEASIBILITY"
