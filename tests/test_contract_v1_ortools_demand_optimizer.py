from __future__ import annotations

import inspect
import itertools
import math
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ortools.sat.python import cp_model
from test_contract_v1_ortools_solver import _request

import bus_schedule_engine.contracts_v1.ortools_solver as ortools_solver_module
import bus_schedule_engine.optimization_service as optimization_service
from bus_schedule_engine.contracts_v1 import (
    CandidateValidationStatus,
    ContractDirection,
    DemandConfidence,
    GenerationResultStatus,
    NativeSolverStatus,
    NormalizationOptions,
    OperatingDayType,
    OrToolsCpSatDemandOptimizationSolver,
    OrToolsCpSatScheduleSolver,
    ScenarioBEvaluationPolicyV1,
    ScheduleProblemError,
    SolverPolicyV1,
    TurnaroundMinutes,
    assess_scenario_b_fleet_v1,
    build_ortools_demand_optimization_request_v1,
    build_ortools_schedule_request_v1,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
    run_schedule_solver_v1,
    scenario_fingerprint,
    validate_and_build_solution_v1,
)
from bus_schedule_engine.contracts_v1.ortools_solver import (
    ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY,
    _build_cp_sat_model,
    _build_demand_cp_sat_model,
    _recompute_demand_objective_vector_v1,
)
from bus_schedule_engine.contracts_v1.solver_fingerprints import candidate_fingerprint
from bus_schedule_engine.models import DemandRecord, Direction, VolumeType
from bus_schedule_engine.optimization_service import SolverChoice

_OBJECTIVE_NAMES = (
    "no_service_block_count",
    "critical_block_count",
    "total_critical_shortage_trips",
    "planning_warning_block_count",
    "total_planning_shortage_trips",
    "shifted_trip_count",
    "total_shift_minutes",
    "maximum_shift_minutes",
)


def _record(
    direction: Direction,
    start_minute: int,
    end_minute: int,
    passengers: float,
) -> DemandRecord:
    return DemandRecord(
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 7),
        observation_days=1,
        block_start_seconds=start_minute * 60,
        block_end_seconds=end_minute * 60,
        direction=direction,
        passenger_volume=passengers,
        volume_type=VolumeType.AVERAGE_DAY,
    )


def _normalize_imported(imported, *, route_id: str, fleet_limit: int, turnaround=(5, 5)):
    normalized = normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id=f"{route_id.lower()}-demand-fixture",
            imported_at=datetime(2026, 7, 26, 10, 0, tzinfo=UTC),
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
    return replace(
        normalized,
        scenario_b=scenario_b,
        scenario_b_fingerprint=scenario_fingerprint(scenario_b),
    )


def _demand_request(
    *,
    outbound_minutes: tuple[int, ...],
    inbound_minutes: tuple[int, ...],
    demand: tuple[DemandRecord, ...],
    outbound_runtimes: tuple[int, ...] | None = None,
    inbound_runtimes: tuple[int, ...] | None = None,
    turnaround: tuple[int, int] = (5, 5),
    fleet_limit: int = 4,
    solver_policy: SolverPolicyV1 | None = None,
    route_id: str = "ORTOOLS-DEMAND",
):
    _, _, imported = _request(
        outbound_minutes=outbound_minutes,
        inbound_minutes=inbound_minutes,
        outbound_runtimes=outbound_runtimes,
        inbound_runtimes=inbound_runtimes,
        turnaround=turnaround,
        fleet_limit=fleet_limit,
        with_demand=False,
        route_id=route_id,
    )
    imported = replace(imported, demand=list(demand))
    normalized = _normalize_imported(
        imported,
        route_id=route_id,
        fleet_limit=fleet_limit,
        turnaround=turnaround,
    )
    policy = ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(normalized, policy)
    context, solver = build_ortools_demand_optimization_request_v1(
        normalized,
        evaluation,
        evaluation_policy=policy,
        solver_policy=solver_policy,
    )
    return context, solver, normalized, evaluation


def _no_service_fixture(*, solver_policy: SolverPolicyV1 | None = None):
    return _demand_request(
        outbound_minutes=(360, 370, 420),
        inbound_minutes=(365,),
        outbound_runtimes=(1, 1, 1),
        inbound_runtimes=(1,),
        fleet_limit=4,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 380, 1),
            _record(Direction.TERMINAL_1_TO_2, 380, 400, 1),
            _record(Direction.TERMINAL_1_TO_2, 400, 421, 1),
            _record(Direction.TERMINAL_2_TO_1, 365, 366, 0),
        ),
        solver_policy=solver_policy,
        route_id="ORTOOLS-DEMAND-NO-SERVICE",
    )


def _shortage_fixture():
    return _demand_request(
        outbound_minutes=(360, 370, 380, 420),
        inbound_minutes=(365,),
        outbound_runtimes=(1, 1, 1, 1),
        inbound_runtimes=(1,),
        fleet_limit=5,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 380, 110),
            _record(Direction.TERMINAL_1_TO_2, 380, 400, 53),
            _record(Direction.TERMINAL_1_TO_2, 400, 421, 1),
            _record(Direction.TERMINAL_2_TO_1, 365, 366, 0),
        ),
        route_id="ORTOOLS-DEMAND-SHORTAGE",
    )


def _preservation_fixture():
    return _demand_request(
        outbound_minutes=(360, 380, 420),
        inbound_minutes=(365, 395, 425),
        outbound_runtimes=(1, 1, 1),
        inbound_runtimes=(1, 1, 1),
        fleet_limit=6,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 390, 0),
            _record(Direction.TERMINAL_1_TO_2, 390, 421, 0),
            _record(Direction.TERMINAL_2_TO_1, 365, 400, 0),
            _record(Direction.TERMINAL_2_TO_1, 400, 426, 0),
        ),
        route_id="ORTOOLS-DEMAND-PRESERVATION",
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


def _candidate_block_counts(context, candidate) -> dict[str, int]:
    counts = {block.block_id: 0 for block in context.problem.analysis_blocks}
    for trip in candidate.exact_timetable:
        memberships = [
            block.block_id
            for block in context.problem.analysis_blocks
            if block.direction == trip.direction
            and block.start_time <= trip.c_departure_time < block.end_time
        ]
        assert len(memberships) == 1
        counts[memberships[0]] += 1
    return counts


def _independent_vector_for_minutes(problem, solved: dict[str, int]) -> tuple[int, ...]:
    requirements = {item.block_id: item for item in problem.block_requirements}
    counts = {item.block_id: 0 for item in problem.analysis_blocks}
    shifts: list[int] = []
    for trip in problem.scenario_b.exact_timetable:
        departure_seconds = solved[trip.trip_id] * 60
        memberships = [
            block.block_id
            for block in problem.analysis_blocks
            if block.direction == trip.direction
            and block.start_time <= departure_seconds < block.end_time
        ]
        if len(memberships) != 1:
            raise ValueError("not an exact half-open membership")
        counts[memberships[0]] += 1
        shifts.append(abs(solved[trip.trip_id] - trip.departure_time // 60))
    return (
        sum(
            requirements[block_id].passenger_demand > 0 and count == 0
            for block_id, count in counts.items()
        ),
        sum(
            requirements[block_id].required_trips_90 > 0
            and count < requirements[block_id].required_trips_90
            for block_id, count in counts.items()
        ),
        sum(
            max(0, requirements[block_id].required_trips_90 - count)
            for block_id, count in counts.items()
        ),
        sum(
            requirements[block_id].required_trips_85 > 0
            and count < requirements[block_id].required_trips_85
            for block_id, count in counts.items()
        ),
        sum(
            max(0, requirements[block_id].required_trips_85 - count)
            for block_id, count in counts.items()
        ),
        sum(shift > 0 for shift in shifts),
        sum(shifts),
        max(shifts, default=0),
    )


def _enumerated_optimum(problem) -> tuple[int, ...]:
    directional = {
        direction: tuple(
            sorted(
                (
                    trip
                    for trip in problem.scenario_b.exact_timetable
                    if trip.direction == direction
                ),
                key=lambda item: (item.departure_time, item.trip_id),
            )
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    }

    def sequences(trips):
        first = trips[0].departure_time // 60
        last = trips[-1].departure_time // 60
        middle_count = len(trips) - 2
        if middle_count <= 0:
            return ((first,),) if len(trips) == 1 else ((first, last),)
        return tuple(
            (first, *middle, last)
            for middle in itertools.combinations(range(first + 1, last), middle_count)
        )

    vectors: list[tuple[int, ...]] = []
    for outbound, inbound in itertools.product(
        sequences(directional[ContractDirection.OUTBOUND]),
        sequences(directional[ContractDirection.INBOUND]),
    ):
        solved = {
            trip.trip_id: minute
            for direction, sequence in (
                (ContractDirection.OUTBOUND, outbound),
                (ContractDirection.INBOUND, inbound),
            )
            for trip, minute in zip(directional[direction], sequence, strict=True)
        }
        exact = tuple(
            replace(
                trip,
                departure_time=solved[trip.trip_id] * 60,
                arrival_time=(solved[trip.trip_id] + trip.runtime_minutes) * 60,
            )
            for trip in problem.scenario_b.exact_timetable
        )
        if not assess_scenario_b_fleet_v1(
            replace(problem.scenario_b, exact_timetable=exact)
        ).feasible:
            continue
        try:
            vectors.append(_independent_vector_for_minutes(problem, solved))
        except ValueError:
            continue
    assert vectors
    return min(vectors)


def test_full_directional_demand_permits_request_construction() -> None:
    context, solver, _, evaluation = _no_service_fixture()

    assert evaluation.demand_resolution is not None
    assert evaluation.demand_resolution.coverage_assessment is not None
    assert evaluation.demand_resolution.coverage_assessment.directional_c_generation_supported
    assert context.problem.solver_adapter == solver.adapter_id


@pytest.mark.parametrize(
    "records",
    [
        (_record(Direction.COMBINED, 360, 421, 10),),
        (_record(Direction.TERMINAL_1_TO_2, 360, 421, 10),),
        (
            _record(Direction.TERMINAL_1_TO_2, 360, 390, 10),
            _record(Direction.COMBINED, 390, 421, 10),
        ),
    ],
    ids=["combined-only", "incomplete-directional", "mixed-grain"],
)
def test_unsupported_demand_authority_is_rejected_before_optimization(records) -> None:
    _, _, imported = _request(
        outbound_minutes=(360, 420),
        inbound_minutes=(365, 415),
        with_demand=False,
        fleet_limit=4,
        route_id="ORTOOLS-DEMAND-AUTHORITY-REJECT",
    )
    normalized = _normalize_imported(
        replace(imported, demand=list(records)),
        route_id="ORTOOLS-DEMAND-AUTHORITY-REJECT",
        fleet_limit=4,
    )
    evaluation = evaluate_scenario_b_v1(normalized)

    with pytest.raises(ScheduleProblemError) as caught:
        build_ortools_demand_optimization_request_v1(normalized, evaluation)

    assert caught.value.code == ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY


def test_non_minute_block_boundaries_are_rejected_by_builder_gate() -> None:
    _, _, normalized, evaluation = _no_service_fixture()
    assert evaluation.demand_resolution is not None
    first = evaluation.demand_resolution.blocks[0]
    modified_block = replace(first, end_time=first.end_time + 1)
    modified_resolution = replace(
        evaluation.demand_resolution,
        blocks=(modified_block, *evaluation.demand_resolution.blocks[1:]),
    )
    modified = replace(evaluation, demand_resolution=modified_resolution)

    with pytest.raises(ScheduleProblemError) as caught:
        build_ortools_demand_optimization_request_v1(normalized, modified)

    assert caught.value.code == ORTOOLS_DEMAND_OPTIMIZATION_REQUIRES_DIRECTIONAL_AUTHORITY


def test_direct_unsupported_problem_solve_returns_model_invalid() -> None:
    context, solver, _, _ = _no_service_fixture()
    unsupported = replace(context.problem, observed_demand_fingerprint=None)

    run = solver.solve(unsupported)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert run.candidate is None


def test_public_adapter_and_builder_signatures_are_exact() -> None:
    assert OrToolsCpSatDemandOptimizationSolver.adapter_id == "ortools_cp_sat_demand_v1"
    assert tuple(inspect.signature(OrToolsCpSatDemandOptimizationSolver().solve).parameters) == (
        "problem",
    )
    assert tuple(inspect.signature(build_ortools_demand_optimization_request_v1).parameters) == (
        "normalized_inputs",
        "b_evaluation",
        "evaluation_policy",
        "solver_policy",
    )


@pytest.mark.parametrize(
    "fixture",
    [_no_service_fixture, _shortage_fixture, _preservation_fixture],
)
def test_optimized_candidate_preserves_fixed_counts_and_source_order(fixture) -> None:
    context, solver, *_ = fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    candidate = run.candidate

    assert len(candidate.exact_timetable) == context.problem.scenario_b.total_daily_trips
    for direction, expected in (
        (ContractDirection.OUTBOUND, context.problem.scenario_b.trips_by_direction.outbound),
        (ContractDirection.INBOUND, context.problem.scenario_b.trips_by_direction.inbound),
    ):
        source = sorted(
            (
                trip
                for trip in context.problem.scenario_b.exact_timetable
                if trip.direction == direction
            ),
            key=lambda item: (item.departure_time, item.trip_id),
        )
        solved = sorted(
            (trip for trip in candidate.exact_timetable if trip.direction == direction),
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
        assert len(solved) == expected
        assert [item.source_b_trip_id for item in solved] == [item.trip_id for item in source]


def test_endpoint_locks_and_exact_source_runtimes_are_preserved() -> None:
    context, solver, *_ = _no_service_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    source = {trip.trip_id: trip for trip in context.problem.scenario_b.exact_timetable}

    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        source_rows = sorted(
            (trip for trip in source.values() if trip.direction == direction),
            key=lambda item: item.departure_time,
        )
        solved_rows = sorted(
            (trip for trip in run.candidate.exact_timetable if trip.direction == direction),
            key=lambda item: item.c_departure_time,
        )
        assert solved_rows[0].c_departure_time == source_rows[0].departure_time
        assert solved_rows[-1].c_departure_time == source_rows[-1].departure_time
    for trip in run.candidate.exact_timetable:
        assert trip.runtime_minutes == source[trip.source_b_trip_id].runtime_minutes
        assert trip.arrival_time == trip.c_departure_time + trip.runtime_minutes * 60


@pytest.mark.parametrize("turnaround", [(20, 5), (5, 20)])
def test_terminal_specific_turnaround_and_fleet_upper_bound_remain_hard(turnaround) -> None:
    inbound_minute = 395 if turnaround == (20, 5) else 410
    context, solver, *_ = _demand_request(
        outbound_minutes=(360, 445),
        inbound_minutes=(inbound_minute,),
        outbound_runtimes=(30, 30),
        inbound_runtimes=(30,),
        turnaround=turnaround,
        fleet_limit=1,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 446, 0),
            _record(
                Direction.TERMINAL_2_TO_1,
                inbound_minute,
                inbound_minute + 1,
                0,
            ),
        ),
        route_id=f"ORTOOLS-DEMAND-TURN-{turnaround[0]}-{turnaround[1]}",
    )
    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solution is not None
    assert outcome.solution.minimum_required_fleet <= 1
    assert outcome.solution.fleet_margin >= 0


def test_same_minute_readiness_remains_usable() -> None:
    context, solver, *_ = _demand_request(
        outbound_minutes=(360, 430),
        inbound_minutes=(395,),
        outbound_runtimes=(30, 30),
        inbound_runtimes=(30,),
        turnaround=(5, 5),
        fleet_limit=1,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 431, 0),
            _record(Direction.TERMINAL_2_TO_1, 365, 396, 0),
        ),
        route_id="ORTOOLS-DEMAND-SAME-MINUTE",
    )

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solution is not None
    assert outcome.solution.minimum_required_fleet == 1


def test_every_trip_has_exactly_one_half_open_membership_and_counts_reconcile() -> None:
    context, solver, *_ = _no_service_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None

    counts = _candidate_block_counts(context, run.candidate)

    assert sum(counts.values()) == context.problem.scenario_b.total_daily_trips
    assert all(isinstance(value, int) and value >= 0 for value in counts.values())


def test_departure_on_boundary_belongs_to_later_block() -> None:
    context, solver, *_ = _no_service_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    outbound = sorted(
        (
            trip
            for trip in run.candidate.exact_timetable
            if trip.direction == ContractDirection.OUTBOUND
        ),
        key=lambda item: item.c_departure_time,
    )

    assert outbound[1].c_departure_time == 380 * 60
    memberships = [
        block
        for block in context.problem.analysis_blocks
        if block.direction == ContractDirection.OUTBOUND
        and block.start_time <= outbound[1].c_departure_time < block.end_time
    ]
    assert len(memberships) == 1
    assert memberships[0].start_time == 380 * 60


def test_no_service_block_count_is_minimized_first() -> None:
    context, solver, *_ = _no_service_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None

    vector = _recompute_demand_objective_vector_v1(context.problem, run.candidate)

    assert vector[0] == 0
    assert vector == _enumerated_optimum(context.problem)


@pytest.mark.parametrize(
    ("higher", "lower"),
    list(zip(_OBJECTIVE_NAMES, _OBJECTIVE_NAMES[1:], strict=False)),
)
def test_objective_stages_are_in_exact_lexicographic_order(higher, lower) -> None:
    context, *_ = _shortage_fixture()
    bundle = _build_demand_cp_sat_model(context.problem)
    names = tuple(stage.name for stage in bundle.stages)

    assert names.index(higher) < names.index(lower)


def test_demand_objectives_precede_all_shift_tie_breaks() -> None:
    context, *_ = _shortage_fixture()
    names = tuple(stage.name for stage in _build_demand_cp_sat_model(context.problem).stages)

    assert names[:5] == _OBJECTIVE_NAMES[:5]
    assert names[5:] == _OBJECTIVE_NAMES[5:]


@pytest.mark.parametrize(
    "forbidden",
    [
        "low_load_penalty",
        "oversupply_penalty",
        "distance_to_85",
        "abs_load_factor",
        "weighted_objective",
    ],
)
def test_no_prohibited_symmetric_or_oversupply_objective_exists(forbidden) -> None:
    source = Path(ortools_solver_module.__file__).read_text(encoding="utf-8").lower()

    assert forbidden not in source


def test_zero_demand_does_not_remove_service_to_raise_load_factor() -> None:
    context, solver, *_ = _preservation_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None

    vector = _recompute_demand_objective_vector_v1(context.problem, run.candidate)

    assert vector == (0, 0, 0, 0, 0, 0, 0, 0)
    assert all(trip.shift_minutes == 0 for trip in run.candidate.exact_timetable)


@pytest.mark.parametrize(
    "fixture",
    [_no_service_fixture, _shortage_fixture, _preservation_fixture],
    ids=["no-service", "shortage", "preservation"],
)
def test_exhaustive_enumeration_oracle_agrees_with_cp_sat(fixture) -> None:
    context, solver, *_ = fixture()
    run = solver.solve(context.problem)
    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert run.candidate is not None

    actual = _recompute_demand_objective_vector_v1(context.problem, run.candidate)

    assert actual == _enumerated_optimum(context.problem)


def test_real_optimized_candidate_passes_independent_validation() -> None:
    context, solver, *_ = _no_service_fixture()

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solution is not None
    assert outcome.solution.fleet_feasibility_status == "FLEET_FEASIBLE"
    assert (
        outcome.solution.recommended_initial_fleet_terminal_1
        + outcome.solution.recommended_initial_fleet_terminal_2
        == outcome.solution.minimum_required_fleet
    )


def test_corrupted_optimized_candidate_is_rejected() -> None:
    context, solver, *_ = _no_service_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    first = run.candidate.exact_timetable[0]
    corrupted = replace(
        run.candidate,
        exact_timetable=(
            replace(first, arrival_time=first.arrival_time - 60),
            *run.candidate.exact_timetable[1:],
        ),
    )
    corrupted = _refingerprint(context, corrupted)

    validation = validate_and_build_solution_v1(context, corrupted)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert validation.solution is None


def test_reported_stage_values_equal_independent_recomputation() -> None:
    context, solver, *_ = _shortage_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    vector = _recompute_demand_objective_vector_v1(context.problem, run.candidate)

    for name, value in zip(_OBJECTIVE_NAMES, vector, strict=True):
        assert f"{name}={value} (proven)" in run.candidate.explanation


def test_candidate_explanation_discloses_4a1_limitations() -> None:
    context, solver, *_ = _no_service_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None

    assert "Headway and service-gap quality were not optimized" in run.candidate.explanation
    assert any("sustained-demand" in item for item in run.candidate.limitations)


def test_complete_staged_solve_returns_optimal() -> None:
    context, solver, *_ = _no_service_fixture()

    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert run.candidate is not None
    assert run.candidate.explanation.count("(proven)") == 8


def test_controlled_feasible_stage_stops_later_optimization_honestly(monkeypatch) -> None:
    context, solver, *_ = _no_service_fixture()
    original = cp_model.CpSolver.solve
    calls = 0

    def controlled(self, model):
        nonlocal calls
        calls += 1
        status = original(self, model)
        return cp_model.FEASIBLE if calls == 3 else status

    monkeypatch.setattr(cp_model.CpSolver, "solve", controlled)
    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.FEASIBLE
    assert run.candidate is not None
    assert calls == 3
    assert "no_service_block_count=0 (proven)" in run.candidate.explanation
    assert "total_critical_shortage_trips=" in run.candidate.explanation
    assert "total_critical_shortage_trips=0 (proven)" not in run.candidate.explanation
    assert (
        "planning_warning_block_count"
        not in run.candidate.explanation.split("Objective stages attempted:")[1].split(".")[0]
    )


def test_first_stage_unknown_returns_no_candidate(monkeypatch) -> None:
    context, solver, *_ = _no_service_fixture()
    monkeypatch.setattr(
        cp_model.CpSolver,
        "solve",
        lambda self, model: cp_model.UNKNOWN,
    )

    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.UNKNOWN
    assert run.candidate is None


def test_later_stage_timeout_retains_earlier_candidate_as_feasible(monkeypatch) -> None:
    context, solver, *_ = _no_service_fixture()
    original = cp_model.CpSolver.solve
    calls = 0

    def controlled(self, model):
        nonlocal calls
        calls += 1
        if calls == 2:
            return cp_model.UNKNOWN
        return original(self, model)

    monkeypatch.setattr(cp_model.CpSolver, "solve", controlled)
    run = solver.solve(context.problem)

    assert calls == 2
    assert run.solver_status == NativeSolverStatus.FEASIBLE
    assert run.candidate is not None
    assert "no_service_block_count=0 (proven)" in run.candidate.explanation
    assert "critical_block_count=0 (proven)" not in run.candidate.explanation


@pytest.mark.parametrize(
    ("native", "expected"),
    [
        (cp_model.INFEASIBLE, NativeSolverStatus.INFEASIBLE),
        (cp_model.MODEL_INVALID, NativeSolverStatus.MODEL_INVALID),
    ],
)
def test_native_failure_statuses_remain_exact(monkeypatch, native, expected) -> None:
    context, solver, *_ = _no_service_fixture()
    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda self, model: native)

    run = solver.solve(context.problem)

    assert run.solver_status == expected
    assert run.candidate is None


def test_total_time_limit_is_applied_as_remaining_adapter_budget(monkeypatch) -> None:
    context, solver, *_ = _no_service_fixture(
        solver_policy=SolverPolicyV1(
            time_limit_seconds=60,
            worker_count=1,
            random_seed=0,
        )
    )
    observed: list[float] = []
    original = cp_model.CpSolver.solve

    def capture(self, model):
        observed.append(self.parameters.max_time_in_seconds)
        return original(self, model)

    monkeypatch.setattr(cp_model.CpSolver, "solve", capture)
    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert len(observed) == 8
    assert all(0 < value <= 60 for value in observed)
    assert all(later <= earlier for earlier, later in zip(observed, observed[1:], strict=False))


def test_feasibility_adapter_model_remains_objective_free() -> None:
    context, _, _ = _request(
        outbound_minutes=(360, 390),
        inbound_minutes=(365, 395),
        fleet_limit=4,
    )
    model = _build_cp_sat_model(context.problem).model

    assert not model.proto.objective.vars


def test_existing_feasibility_builder_and_adapter_remain_available() -> None:
    context, solver, _ = _request(
        outbound_minutes=(360, 390),
        inbound_minutes=(365, 395),
        fleet_limit=4,
    )

    assert isinstance(solver, OrToolsCpSatScheduleSolver)
    assert solver.adapter_id == "ortools_cp_sat_v1"
    assert build_ortools_schedule_request_v1
    assert solver.solve(context.problem).candidate is not None


def test_feasibility_fingerprint_remains_deterministic() -> None:
    context, solver, _ = _request(
        outbound_minutes=(360, 390),
        inbound_minutes=(365, 395),
        fleet_limit=4,
    )

    first = solver.solve(context.problem)
    second = solver.solve(context.problem)

    assert first.candidate is not None and second.candidate is not None
    assert first.candidate.candidate_fingerprint == second.candidate.candidate_fingerprint


def test_demand_optimizer_is_deterministic_with_default_controls() -> None:
    context, solver, *_ = _no_service_fixture()

    runs = [solver.solve(context.problem) for _ in range(3)]

    assert {run.solver_status for run in runs} == {NativeSolverStatus.OPTIMAL}
    assert all(run.candidate is not None for run in runs)
    candidates = [run.candidate for run in runs if run.candidate is not None]
    assert len({candidate.candidate_fingerprint for candidate in candidates}) == 1
    assert len({candidate.exact_timetable for candidate in candidates}) == 1
    assert (
        len(
            {
                _recompute_demand_objective_vector_v1(context.problem, candidate)
                for candidate in candidates
            }
        )
        == 1
    )


@pytest.mark.parametrize(
    "forbidden",
    [
        "headway_objective",
        "service_gap_objective",
        "sustained_demand_share",
        "fleet_minimization_objective",
        "HeuristicScheduleSolverAdapter",
    ],
)
def test_prohibited_future_objectives_and_heuristic_import_are_absent(forbidden) -> None:
    source = Path(ortools_solver_module.__file__).read_text(encoding="utf-8")

    assert forbidden not in source


def test_optimization_service_remains_unchanged_and_solver_choices_unavailable() -> None:
    service_path = Path(optimization_service.__file__)
    source = service_path.read_text(encoding="utf-8")

    assert "OrToolsCpSatDemandOptimizationSolver" not in source
    with pytest.raises(NotImplementedError):
        optimization_service._validate_solver_choice(SolverChoice.OR_TOOLS)
    with pytest.raises(NotImplementedError):
        optimization_service._validate_solver_choice(SolverChoice.BOTH)


def test_model_uses_exact_membership_and_eight_unweighted_stages() -> None:
    context, *_ = _no_service_fixture()
    bundle = _build_demand_cp_sat_model(context.problem)
    proto = bundle.hard.model.proto

    assert len(bundle.membership_by_source_and_block) > 0
    assert len(bundle.block_trip_count_by_id) == len(context.problem.analysis_blocks)
    assert tuple(stage.name for stage in bundle.stages) == _OBJECTIVE_NAMES
    assert not proto.objective.vars
    assert len(proto.variables) > len(context.problem.scenario_b.exact_timetable)
    assert len(proto.constraints) > len(context.problem.scenario_b.exact_timetable)


def test_all_demand_values_and_requirements_are_finite_and_nonnegative() -> None:
    context, *_ = _shortage_fixture()

    for requirement in context.problem.block_requirements:
        assert math.isfinite(requirement.passenger_demand)
        assert requirement.passenger_demand >= 0
        assert requirement.required_trips_90 >= 0
        assert requirement.required_trips_85 >= 0
