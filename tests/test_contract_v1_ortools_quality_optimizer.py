from __future__ import annotations

import inspect
import itertools
import math
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from ortools.sat.python import cp_model
from test_contract_v1_ortools_demand_optimizer import (
    _demand_request,
    _record,
)
from test_contract_v1_ortools_solver import _request

import bus_schedule_engine.contracts_v1.ortools_quality_solver as quality_module
import bus_schedule_engine.contracts_v1.ortools_solver as ortools_solver_module
import bus_schedule_engine.optimization_service as optimization_service
from bus_schedule_engine.contracts_v1 import (
    BoundaryConvention,
    CandidateValidationStatus,
    ContractDirection,
    DirectionTripLockMode,
    FleetConstraintMode,
    GenerationResultStatus,
    InitialFleetPositioningMode,
    NativeSolverStatus,
    OrToolsCpSatDemandOptimizationSolver,
    OrToolsCpSatScheduleSolver,
    OrToolsCpSatServiceQualitySolver,
    ScheduleProblemError,
    SolverPolicyV1,
    assess_scenario_b_fleet_v1,
    build_ortools_service_quality_request_v1,
    run_schedule_solver_v1,
    validate_and_build_solution_v1,
)
from bus_schedule_engine.contracts_v1.ortools_quality_solver import (
    ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY,
    _build_quality_cp_sat_model,
    _derive_sustained_service_regimes,
    _recompute_service_quality_objective_vector_v1,
)
from bus_schedule_engine.contracts_v1.service_quality_metrics import (
    _recompute_service_quality_objective_vector_with_authority_v1,
)
from bus_schedule_engine.contracts_v1.solver_fingerprints import candidate_fingerprint
from bus_schedule_engine.models import Direction
from bus_schedule_engine.optimization_service import SolverChoice

_OBJECTIVE_NAMES = (
    "no_service_block_count",
    "critical_block_count",
    "total_critical_shortage_trips",
    "planning_warning_block_count",
    "total_planning_shortage_trips",
    "maximum_positive_demand_headway_minutes",
    "total_positive_demand_block_max_gap_minutes",
    "directional_demand_alignment_error",
    "maximum_within_regime_headway_change_minutes",
    "total_within_regime_headway_change_minutes",
    "maximum_regime_transition_headway_jump_minutes",
    "total_regime_transition_headway_jump_minutes",
    "shifted_trip_count",
    "total_shift_minutes",
    "maximum_shift_minutes",
)


def _quality_request(**kwargs):
    _, _, normalized, evaluation = _demand_request(**kwargs)
    context, solver = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        solver_policy=kwargs.get("solver_policy"),
    )
    return context, solver, normalized, evaluation


def _cross_block_fixture(*, solver_policy: SolverPolicyV1 | None = None):
    return _quality_request(
        outbound_minutes=(360, 370, 400),
        inbound_minutes=(365,),
        outbound_runtimes=(1, 1, 1),
        inbound_runtimes=(1,),
        fleet_limit=4,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 380, 20),
            _record(Direction.TERMINAL_1_TO_2, 380, 401, 20),
            _record(Direction.TERMINAL_2_TO_1, 365, 366, 0),
        ),
        solver_policy=solver_policy,
        route_id="ORTOOLS-QUALITY-CROSS-BLOCK",
    )


def _alignment_fixture():
    return _quality_request(
        outbound_minutes=(360, 365, 375, 400),
        inbound_minutes=(362,),
        outbound_runtimes=(1, 1, 1, 1),
        inbound_runtimes=(1,),
        fleet_limit=5,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 370, 10),
            _record(Direction.TERMINAL_1_TO_2, 370, 401, 30),
            _record(Direction.TERMINAL_2_TO_1, 362, 363, 0),
        ),
        route_id="ORTOOLS-QUALITY-ALIGNMENT",
    )


def _regularity_fixture():
    return _quality_request(
        outbound_minutes=(360, 361, 370, 371),
        inbound_minutes=(362,),
        outbound_runtimes=(1, 1, 1, 1),
        inbound_runtimes=(1,),
        fleet_limit=5,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 366, 10),
            _record(Direction.TERMINAL_1_TO_2, 366, 372, 10),
            _record(Direction.TERMINAL_2_TO_1, 362, 363, 0),
        ),
        route_id="ORTOOLS-QUALITY-REGULARITY",
    )


def _two_regime_fixture():
    return _quality_request(
        outbound_minutes=(360, 361, 365, 368, 371, 374),
        inbound_minutes=(362, 363),
        outbound_runtimes=(1, 1, 1, 1, 1, 1),
        inbound_runtimes=(1, 1),
        fleet_limit=8,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 368, 80),
            _record(Direction.TERMINAL_1_TO_2, 368, 375, 200),
            _record(Direction.TERMINAL_2_TO_1, 362, 364, 0),
        ),
        route_id="ORTOOLS-QUALITY-TWO-REGIME",
    )


def _zero_demand_fixture():
    return _quality_request(
        outbound_minutes=(360, 370, 380),
        inbound_minutes=(365, 375, 385),
        outbound_runtimes=(1, 1, 1),
        inbound_runtimes=(1, 1, 1),
        fleet_limit=6,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 370, 0),
            _record(Direction.TERMINAL_1_TO_2, 370, 381, 0),
            _record(Direction.TERMINAL_2_TO_1, 365, 375, 0),
            _record(Direction.TERMINAL_2_TO_1, 375, 386, 0),
        ),
        route_id="ORTOOLS-QUALITY-ZERO-DEMAND",
    )


def _no_service_positive_block_fixture():
    return _quality_request(
        outbound_minutes=(360, 390),
        inbound_minutes=(365,),
        outbound_runtimes=(1, 1),
        inbound_runtimes=(1,),
        fleet_limit=3,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 370, 10),
            _record(Direction.TERMINAL_1_TO_2, 370, 380, 10),
            _record(Direction.TERMINAL_1_TO_2, 380, 391, 10),
            _record(Direction.TERMINAL_2_TO_1, 365, 366, 0),
        ),
        route_id="ORTOOLS-QUALITY-NO-SERVICE-GAP",
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


def _independent_regimes(problem):
    requirements = {item.block_id: item for item in problem.block_requirements}
    block_to_regime: dict[str, str] = {}
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        blocks = sorted(
            (block for block in problem.analysis_blocks if block.direction == direction),
            key=lambda item: (item.start_time, item.end_time, item.block_id),
        )
        regime_index = 0
        previous = None
        for block in blocks:
            if previous is None:
                regime_index += 1
            else:
                previous_requirement = requirements[previous.block_id]
                requirement = requirements[block.block_id]
                equal_rate = (
                    previous_requirement.required_trips_85 * requirement.duration_minutes
                    == requirement.required_trips_85 * previous_requirement.duration_minutes
                )
                if previous.end_time != block.start_time or not equal_rate:
                    regime_index += 1
            block_to_regime[block.block_id] = f"INDEPENDENT-{direction.value}-{regime_index:04d}"
            previous = block
    return block_to_regime


def _independent_vector_for_minutes(problem, solved: dict[str, int]) -> tuple[int, ...]:
    requirements = {item.block_id: item for item in problem.block_requirements}
    blocks = {item.block_id: item for item in problem.analysis_blocks}
    counts = {block_id: 0 for block_id in blocks}
    block_by_trip: dict[str, str] = {}
    shifts: list[int] = []
    directional: dict[ContractDirection, list[tuple[str, int]]] = {
        ContractDirection.OUTBOUND: [],
        ContractDirection.INBOUND: [],
    }
    for source in problem.scenario_b.exact_timetable:
        departure = solved[source.trip_id] * 60
        memberships = [
            block_id
            for block_id, block in blocks.items()
            if block.direction == source.direction
            and block.start_time <= departure < block.end_time
        ]
        if len(memberships) != 1:
            raise ValueError("invalid block membership")
        block_id = memberships[0]
        block_by_trip[source.trip_id] = block_id
        counts[block_id] += 1
        shifts.append(abs(solved[source.trip_id] - source.departure_time // 60))
        directional[source.direction].append((source.trip_id, solved[source.trip_id]))
    for rows in directional.values():
        rows.sort(key=lambda item: (item[1], item[0]))

    exact_demand = {
        block_id: Fraction(Decimal(str(requirement.passenger_demand)))
        for block_id, requirement in requirements.items()
    }
    common_denominator = math.lcm(*(value.denominator for value in exact_demand.values()))
    raw_weights = {
        block_id: value.numerator * (common_denominator // value.denominator)
        for block_id, value in exact_demand.items()
    }
    reduction_gcd = math.gcd(*raw_weights.values()) or 1
    weights = {block_id: value // reduction_gcd for block_id, value in raw_weights.items()}

    max_positive_gap = 0
    for direction, rows in directional.items():
        positive_blocks = [
            block
            for block in blocks.values()
            if block.direction == direction and requirements[block.block_id].passenger_demand > 0
        ]
        for (_, earlier), (_, later) in zip(rows, rows[1:], strict=False):
            if any(
                earlier * 60 < block.end_time and later * 60 > block.start_time
                for block in positive_blocks
            ):
                max_positive_gap = max(max_positive_gap, later - earlier)

    total_block_gap = 0
    for block_id, block in blocks.items():
        if requirements[block_id].passenger_demand <= 0:
            continue
        members = [
            minute
            for _, minute in directional[block.direction]
            if block.start_time <= minute * 60 < block.end_time
        ]
        if not members:
            total_block_gap += (block.end_time - block.start_time) // 60
        else:
            gaps = [
                members[0] - block.start_time // 60,
                *(later - earlier for earlier, later in zip(members, members[1:], strict=False)),
                block.end_time // 60 - members[-1],
            ]
            total_block_gap += max(gaps)

    alignment = 0
    for direction, rows in directional.items():
        directional_blocks = [block for block in blocks.values() if block.direction == direction]
        total_weight = sum(weights[block.block_id] for block in directional_blocks)
        if total_weight:
            alignment += sum(
                abs(counts[block.block_id] * total_weight - len(rows) * weights[block.block_id])
                for block in directional_blocks
            )

    block_to_regime = _independent_regimes(problem)
    internal_sequences: dict[str, list[int]] = {}
    for rows in directional.values():
        for earlier, later in zip(rows, rows[1:], strict=False):
            earlier_regime = block_to_regime[block_by_trip[earlier[0]]]
            later_regime = block_to_regime[block_by_trip[later[0]]]
            if earlier_regime == later_regime:
                internal_sequences.setdefault(earlier_regime, []).append(later[1] - earlier[1])
    if any(
        sequence and max(sequence) - min(sequence) > 1 for sequence in internal_sequences.values()
    ):
        raise ValueError("non-balanced within-regime headway")

    within: list[int] = []
    transition: list[int] = []
    for rows in directional.values():
        for previous, current, following in zip(rows, rows[1:], rows[2:], strict=False):
            change = abs((following[1] - current[1]) - (current[1] - previous[1]))
            regime_ids = {
                block_to_regime[block_by_trip[previous[0]]],
                block_to_regime[block_by_trip[current[0]]],
                block_to_regime[block_by_trip[following[0]]],
            }
            (within if len(regime_ids) == 1 else transition).append(change)

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
        max_positive_gap,
        total_block_gap,
        alignment,
        max(within, default=0),
        sum(within),
        max(transition, default=0),
        sum(transition),
        sum(value > 0 for value in shifts),
        sum(shifts),
        max(shifts, default=0),
    )


def _enumerated_optimum(problem) -> tuple[int, ...] | None:
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
        return (
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
    return min(vectors) if vectors else None


def test_authoritative_directional_demand_permits_construction() -> None:
    context, solver, *_ = _cross_block_fixture()

    assert solver.adapter_id == "ortools_cp_sat_quality_v1"
    assert context.problem.solver_adapter == solver.adapter_id
    assert context.problem.direction_trip_lock_mode == DirectionTripLockMode.FIXED_BY_DIRECTION
    assert context.problem.fleet_constraint_mode == FleetConstraintMode.AVAILABLE_UPPER_BOUND
    assert (
        context.problem.initial_fleet_positioning_mode
        == InitialFleetPositioningMode.SOLVER_DETERMINED
    )
    assert context.problem.boundary_convention == BoundaryConvention.HALF_OPEN


@pytest.mark.parametrize(
    "demand",
    [
        (_record(Direction.COMBINED, 360, 401, 10),),
        (_record(Direction.TERMINAL_1_TO_2, 360, 401, 10),),
        (
            _record(Direction.TERMINAL_1_TO_2, 360, 380, 10),
            _record(Direction.COMBINED, 380, 401, 10),
        ),
    ],
    ids=["combined-only", "incomplete-directional", "mixed-grain"],
)
def test_unsupported_demand_authority_is_rejected(demand) -> None:
    _, _, imported = _request(
        outbound_minutes=(360, 400),
        inbound_minutes=(365, 395),
        with_demand=False,
        fleet_limit=4,
        route_id="ORTOOLS-QUALITY-AUTHORITY-REJECT",
    )
    from test_contract_v1_ortools_demand_optimizer import _normalize_imported

    normalized = _normalize_imported(
        replace(imported, demand=list(demand)),
        route_id="ORTOOLS-QUALITY-AUTHORITY-REJECT",
        fleet_limit=4,
    )
    from bus_schedule_engine.contracts_v1 import evaluate_scenario_b_v1

    evaluation = evaluate_scenario_b_v1(normalized)
    with pytest.raises(ScheduleProblemError) as caught:
        build_ortools_service_quality_request_v1(normalized, evaluation)
    assert caught.value.code == ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY


def test_demand_precision_beyond_six_decimals_is_exactly_supported() -> None:
    context, solver, *_ = _quality_request(
        outbound_minutes=(360, 380),
        inbound_minutes=(365,),
        fleet_limit=3,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 381, 0.1234567),
            _record(Direction.TERMINAL_2_TO_1, 365, 366, 0),
        ),
        route_id="ORTOOLS-QUALITY-PRECISION",
    )

    assert context.problem.adapter_context_fingerprint == (
        solver.exact_demand_authority.authority_fingerprint
    )
    assert Fraction(1_234_567, 10_000_000) in {
        block.fraction for block in solver.exact_demand_authority.blocks
    }


def test_exact_threshold_discrepancy_is_reported_instead_of_silently_changed() -> None:
    with pytest.raises(ScheduleProblemError) as caught:
        _quality_request(
            outbound_minutes=(360, 370, 380),
            inbound_minutes=(365,),
            fleet_limit=4,
            demand=(
                _record(Direction.TERMINAL_1_TO_2, 360, 381, 1e18),
                _record(Direction.TERMINAL_2_TO_1, 365, 366, 0),
            ),
            route_id="ORTOOLS-QUALITY-UNSAFE-INTEGER",
        )

    assert "EXACT_DEMAND_SERVICE_THRESHOLD_MISMATCH" in caught.value.codes


def test_direct_unsupported_problem_solve_returns_model_invalid() -> None:
    context, solver, *_ = _cross_block_fixture()
    unsupported = replace(context.problem, observed_demand_fingerprint=None)

    run = solver.solve(unsupported)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert run.candidate is None


def test_public_adapter_and_builder_signatures_are_exact() -> None:
    assert OrToolsCpSatServiceQualitySolver.adapter_id == "ortools_cp_sat_quality_v1"
    assert str(inspect.signature(OrToolsCpSatServiceQualitySolver.solve)) == (
        "(self, problem: 'ScheduleProblemV1') -> 'SolverRunResultV1'"
    )
    assert tuple(inspect.signature(build_ortools_service_quality_request_v1).parameters) == (
        "normalized_inputs",
        "b_evaluation",
        "evaluation_policy",
        "solver_policy",
        "protected_service_floor_enforcement_authority",
    )


def test_fixed_total_directional_counts_source_order_and_endpoints() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None

    assert len(run.candidate.exact_timetable) == context.problem.scenario_b.total_daily_trips
    for direction, expected in (
        (ContractDirection.OUTBOUND, 6),
        (ContractDirection.INBOUND, 2),
    ):
        source = sorted(
            (
                trip
                for trip in context.problem.scenario_b.exact_timetable
                if trip.direction == direction
            ),
            key=lambda item: (item.departure_time, item.trip_id),
        )
        candidate = sorted(
            (trip for trip in run.candidate.exact_timetable if trip.direction == direction),
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
        assert len(candidate) == expected
        assert [item.source_b_trip_id for item in candidate] == [item.trip_id for item in source]
        assert candidate[0].c_departure_time == source[0].departure_time
        assert candidate[-1].c_departure_time == source[-1].departure_time


def test_source_runtime_turnaround_and_fleet_limit_remain_hard() -> None:
    context, solver, *_ = _quality_request(
        outbound_minutes=(360, 445),
        inbound_minutes=(395, 475),
        outbound_runtimes=(30, 25),
        inbound_runtimes=(30, 30),
        turnaround=(20, 5),
        fleet_limit=1,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 446, 0),
            _record(Direction.TERMINAL_2_TO_1, 395, 476, 0),
        ),
        route_id="ORTOOLS-QUALITY-HARD-RUNTIME",
    )
    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solution is not None
    assert outcome.solution.minimum_required_fleet <= 1
    source = {trip.trip_id: trip for trip in context.problem.scenario_b.exact_timetable}
    for assignment in outcome.solution.fleet_assignment:
        candidate = next(
            trip
            for trip in outcome.solution.c_exact_timetable
            if trip.c_trip_id == assignment.c_trip_id
        )
        runtime = source[candidate.source_b_trip_id].runtime_minutes
        assert assignment.arrival_time == assignment.departure_time + runtime * 60
        turnaround = 20 if assignment.arrival_terminal.value == "terminal_1" else 5
        assert assignment.ready_time == assignment.arrival_time + turnaround * 60


def test_same_minute_readiness_remains_usable() -> None:
    context, solver, *_ = _quality_request(
        outbound_minutes=(360, 430),
        inbound_minutes=(395, 465),
        outbound_runtimes=(30, 30),
        inbound_runtimes=(30, 30),
        turnaround=(5, 5),
        fleet_limit=1,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 431, 0),
            _record(Direction.TERMINAL_2_TO_1, 365, 466, 0),
        ),
        route_id="ORTOOLS-QUALITY-SAME-MINUTE",
    )

    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.solution is not None
    assert outcome.solution.minimum_required_fleet == 1


def test_every_trip_has_exactly_one_block_and_emitted_regime() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    regime_ids = {regime.regime_id for regime in run.candidate.headway_regimes}

    for trip in run.candidate.exact_timetable:
        memberships = [
            block
            for block in context.problem.analysis_blocks
            if block.direction == trip.direction
            and block.start_time <= trip.c_departure_time < block.end_time
        ]
        assert len(memberships) == 1
        assert trip.headway_regime_id in regime_ids
    assert all(
        any(trip.headway_regime_id == regime.regime_id for trip in run.candidate.exact_timetable)
        for regime in run.candidate.headway_regimes
    )


def test_cross_block_headway_is_one_complete_actual_gap() -> None:
    context, solver, *_ = _cross_block_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    vector = _recompute_service_quality_objective_vector_v1(
        context.problem,
        run.candidate,
    )
    outbound = sorted(
        (
            trip
            for trip in run.candidate.exact_timetable
            if trip.direction == ContractDirection.OUTBOUND
        ),
        key=lambda item: item.c_departure_time,
    )

    assert vector[5] == max(
        (later.c_departure_time - earlier.c_departure_time) // 60
        for earlier, later in zip(outbound, outbound[1:], strict=False)
    )


def test_no_service_positive_block_contributes_full_duration() -> None:
    context, solver, *_ = _no_service_positive_block_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    vector = _recompute_service_quality_objective_vector_v1(
        context.problem,
        run.candidate,
    )

    assert vector[0] == 1
    assert vector[6] >= 10


def test_boundary_departures_use_half_open_membership() -> None:
    context, solver, *_ = _quality_request(
        outbound_minutes=(360, 370),
        inbound_minutes=(365,),
        outbound_runtimes=(1, 1),
        inbound_runtimes=(1,),
        fleet_limit=3,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 370, 10),
            _record(Direction.TERMINAL_1_TO_2, 370, 371, 10),
            _record(Direction.TERMINAL_2_TO_1, 365, 366, 0),
        ),
        route_id="ORTOOLS-QUALITY-HALF-OPEN-BOUNDARY",
    )
    run = solver.solve(context.problem)
    assert run.candidate is not None
    boundary = next(
        block.start_time
        for block in context.problem.analysis_blocks
        if block.direction == ContractDirection.OUTBOUND and block.start_time == 370 * 60
    )
    boundary_trip = next(
        trip for trip in run.candidate.exact_timetable if trip.c_departure_time == boundary
    )
    memberships = [
        block
        for block in context.problem.analysis_blocks
        if block.direction == boundary_trip.direction
        and block.start_time <= boundary_trip.c_departure_time < block.end_time
    ]

    assert len(memberships) == 1
    assert memberships[0].start_time == boundary


def test_gap_stages_precede_alignment_and_all_regularization() -> None:
    context, *_ = _cross_block_fixture()
    names = tuple(stage.name for stage in _build_quality_cp_sat_model(context.problem).stages)

    assert names == _OBJECTIVE_NAMES
    assert names.index("maximum_positive_demand_headway_minutes") < names.index(
        "total_positive_demand_block_max_gap_minutes"
    )
    assert names.index("total_positive_demand_block_max_gap_minutes") < names.index(
        "directional_demand_alignment_error"
    )


def test_proportional_directional_demand_alignment_is_exact() -> None:
    context, solver, *_ = _alignment_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    vector = _recompute_service_quality_objective_vector_v1(
        context.problem,
        run.candidate,
    )

    assert vector[7] == 0
    enumerated = _enumerated_optimum(context.problem)
    assert enumerated is not None
    assert vector[:8] == enumerated[:8]


def test_zero_demand_direction_contributes_zero_alignment_error() -> None:
    context, solver, *_ = _zero_demand_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None

    assert (
        _recompute_service_quality_objective_vector_v1(
            context.problem,
            run.candidate,
        )[7]
        == 0
    )


@pytest.mark.parametrize(
    "forbidden",
    (
        "low_load_penalty",
        "oversupply_penalty",
        "distance_to_85",
        "abs_load_factor",
        "weighted_objective",
        "composite_score",
    ),
)
def test_no_low_load_oversupply_symmetric_or_weighted_objective(forbidden) -> None:
    source = Path(quality_module.__file__).read_text(encoding="utf-8").lower()
    assert forbidden not in source


def test_equal_rate_adjacent_blocks_merge_and_raw_boundary_does_not_reset() -> None:
    context, *_ = _regularity_fixture()
    regimes = _derive_sustained_service_regimes(context.problem)
    outbound = [regime for regime in regimes if regime.direction == ContractDirection.OUTBOUND]

    assert len(outbound) == 1
    assert len(outbound[0].block_ids) == 2


def test_different_planning_rates_create_distinct_regimes() -> None:
    context, *_ = _two_regime_fixture()
    regimes = _derive_sustained_service_regimes(context.problem)
    outbound = [regime for regime in regimes if regime.direction == ContractDirection.OUTBOUND]

    assert len(outbound) == 2
    assert outbound[0].regime_id == "ORTOOLS-QUALITY-OUTBOUND-0001"
    assert outbound[1].regime_id == "ORTOOLS-QUALITY-OUTBOUND-0002"


def test_different_regimes_may_use_different_headway_levels() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    outbound = [
        regime
        for regime in run.candidate.headway_regimes
        if regime.direction == ContractDirection.OUTBOUND
    ]

    assert len(outbound) == 2
    measurable = [
        regime.actual_headway_sequence for regime in outbound if regime.actual_headway_sequence
    ]
    assert len(measurable) == 2
    assert sum(measurable[0]) / len(measurable[0]) != (sum(measurable[1]) / len(measurable[1]))


def test_candidate_regime_sequences_exactly_match_departures() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None

    for regime in run.candidate.headway_regimes:
        members = sorted(
            (
                trip
                for trip in run.candidate.exact_timetable
                if trip.headway_regime_id == regime.regime_id
            ),
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
        assert regime.start_time == members[0].c_departure_time
        assert regime.end_time == members[-1].c_departure_time
        assert regime.trip_count == len(members)
        assert regime.actual_headway_sequence == tuple(
            (later.c_departure_time - earlier.c_departure_time) / 60
            for earlier, later in zip(members, members[1:], strict=False)
        )
        if len(members) >= 2:
            assert regime.target_headway == regime.actual_headway_sequence[0]
            assert regime.legacy_regularity_status == "UNIFORM"
        else:
            assert regime.target_headway == 0
            assert regime.legacy_regularity_status == "SINGLE_TRIP_HEADWAY_NOT_MEASURABLE"
        assert regime.boundary_reason == "MATERIAL_FREQUENCY_CHANGE"


def test_balanced_rounding_is_feasible_under_v2_adjacent_minute_constraint() -> None:
    context, solver, *_ = _regularity_fixture()
    run = solver.solve(context.problem)
    enumerated = _enumerated_optimum(context.problem)

    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert run.candidate is not None
    assert enumerated is not None
    outbound = [
        regime
        for regime in run.candidate.headway_regimes
        if regime.direction == ContractDirection.OUTBOUND
    ]
    assert outbound
    assert all(
        not regime.actual_headway_sequence
        or max(regime.actual_headway_sequence) - min(regime.actual_headway_sequence) <= 1
        for regime in outbound
    )


def test_within_maximum_precedes_total_and_transitions_follow() -> None:
    context, *_ = _regularity_fixture()
    names = tuple(stage.name for stage in _build_quality_cp_sat_model(context.problem).stages)

    assert names.index("maximum_within_regime_headway_change_minutes") < names.index(
        "total_within_regime_headway_change_minutes"
    )
    assert names.index("total_within_regime_headway_change_minutes") < names.index(
        "maximum_regime_transition_headway_jump_minutes"
    )
    assert names.index("maximum_regime_transition_headway_jump_minutes") < names.index(
        "total_regime_transition_headway_jump_minutes"
    )


def test_transition_smoothing_does_not_collapse_legitimate_regimes() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None

    assert (
        len(
            [
                regime
                for regime in run.candidate.headway_regimes
                if regime.direction == ContractDirection.OUTBOUND
            ]
        )
        == 2
    )
    assert _recompute_service_quality_objective_vector_with_authority_v1(
        context.problem,
        run.candidate,
        solver.exact_demand_authority,
    ) == _enumerated_optimum(context.problem)


def test_all_quality_stages_precede_shift_tie_breaks() -> None:
    context, *_ = _two_regime_fixture()
    names = tuple(stage.name for stage in _build_quality_cp_sat_model(context.problem).stages)

    assert names[12:] == (
        "shifted_trip_count",
        "total_shift_minutes",
        "maximum_shift_minutes",
    )


def test_real_candidate_passes_independent_validation_and_fleet_reconciles() -> None:
    context, solver, *_ = _two_regime_fixture()
    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
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


def test_corrupted_candidate_is_rejected() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    first = run.candidate.exact_timetable[0]
    corrupted = _refingerprint(
        context,
        replace(
            run.candidate,
            exact_timetable=(
                replace(first, arrival_time=first.arrival_time - 60),
                *run.candidate.exact_timetable[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(context, corrupted)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert validation.solution is None


def test_reported_vector_equals_independent_recomputation() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    vector = _recompute_service_quality_objective_vector_with_authority_v1(
        context.problem,
        run.candidate,
        solver.exact_demand_authority,
    )

    for name, value in zip(_OBJECTIVE_NAMES, vector, strict=True):
        assert f"{name}={value} (proven)" in run.candidate.explanation


def test_independent_recomputation_mismatch_is_sanitized_as_model_invalid(
    monkeypatch,
) -> None:
    context, solver, *_ = _cross_block_fixture()
    real_recompute = quality_module._recompute_service_quality_objective_vector_with_authority_v1

    def mismatching(problem, candidate, authority):
        vector = real_recompute(problem, candidate, authority)
        return (vector[0] + 1, *vector[1:])

    monkeypatch.setattr(
        quality_module,
        "_recompute_service_quality_objective_vector_with_authority_v1",
        mismatching,
    )

    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert run.candidate is None
    assert any("ORTOOLS_QUALITY_ADAPTER_FAILURE" in item for item in run.explanations)


def test_candidate_explanation_discloses_stages_controls_and_non_objectives() -> None:
    context, solver, *_ = _cross_block_fixture(
        solver_policy=SolverPolicyV1(
            time_limit_seconds=60,
            worker_count=1,
            random_seed=0,
        )
    )

    run = solver.solve(context.problem)

    assert run.candidate is not None
    assert "Objective stages attempted:" in run.candidate.explanation
    assert "Objective stages proven optimal:" in run.candidate.explanation
    assert "Unproven current/later stages: none" in run.candidate.explanation
    assert "Variable trip counts and fleet minimization were not optimized" in (
        run.candidate.explanation
    )
    assert any("worker count: 1" in item for item in run.candidate.limitations)
    assert any("random seed: 0" in item for item in run.candidate.limitations)


def test_complete_staged_solve_returns_optimal() -> None:
    context, solver, *_ = _cross_block_fixture()
    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert run.candidate is not None
    assert run.candidate.explanation.count("(proven)") == 15


def test_controlled_feasible_stage_stops_honestly(monkeypatch) -> None:
    context, solver, *_ = _cross_block_fixture()
    original = cp_model.CpSolver.solve
    calls = 0

    def controlled(self, model):
        nonlocal calls
        calls += 1
        status = original(self, model)
        return cp_model.FEASIBLE if calls == 7 else status

    monkeypatch.setattr(cp_model.CpSolver, "solve", controlled)
    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.FEASIBLE
    assert run.candidate is not None
    assert calls == 7
    assert "maximum_positive_demand_headway_minutes=" in run.candidate.explanation
    assert "total_positive_demand_block_max_gap_minutes=" in run.candidate.explanation
    assert "total_positive_demand_block_max_gap_minutes=0 (proven)" not in (
        run.candidate.explanation
    )
    assert "Unproven current/later stages:" in run.candidate.explanation


def test_first_stage_unknown_returns_no_candidate(monkeypatch) -> None:
    context, solver, *_ = _cross_block_fixture()
    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda self, model: cp_model.UNKNOWN)

    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.UNKNOWN
    assert run.candidate is None


def test_later_unknown_retains_earlier_candidate_as_feasible(monkeypatch) -> None:
    context, solver, *_ = _cross_block_fixture()
    original = cp_model.CpSolver.solve
    calls = 0

    def controlled(self, model):
        nonlocal calls
        calls += 1
        return cp_model.UNKNOWN if calls == 3 else original(self, model)

    monkeypatch.setattr(cp_model.CpSolver, "solve", controlled)
    run = solver.solve(context.problem)

    assert calls == 3
    assert run.solver_status == NativeSolverStatus.FEASIBLE
    assert run.candidate is not None
    assert "no_service_block_count=0 (proven)" in run.candidate.explanation
    assert "total_critical_shortage_trips=0 (proven)" not in run.candidate.explanation


def test_total_time_budget_decreases_across_stages(monkeypatch) -> None:
    context, solver, *_ = _cross_block_fixture(
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
    assert len(observed) == 15
    assert all(0 < value <= 60 for value in observed)
    assert all(later <= earlier for earlier, later in zip(observed, observed[1:], strict=False))


@pytest.mark.parametrize(
    ("cp_status", "native_status"),
    (
        (cp_model.INFEASIBLE, NativeSolverStatus.INFEASIBLE),
        (cp_model.MODEL_INVALID, NativeSolverStatus.MODEL_INVALID),
    ),
)
def test_native_infeasible_and_model_invalid_remain_exact(
    monkeypatch,
    cp_status,
    native_status,
) -> None:
    context, solver, *_ = _cross_block_fixture()
    monkeypatch.setattr(cp_model.CpSolver, "solve", lambda self, model: cp_status)

    run = solver.solve(context.problem)

    assert run.solver_status == native_status
    assert run.candidate is None


@pytest.mark.parametrize(
    "fixture",
    (
        _cross_block_fixture,
        _alignment_fixture,
        _regularity_fixture,
        _two_regime_fixture,
    ),
    ids=(
        "cross-block-gap",
        "proportional-alignment",
        "within-regime-balance",
        "two-service-regimes",
    ),
)
def test_four_tiny_exhaustive_oracles_agree_on_demand_priority_prefix(fixture) -> None:
    context, solver, *_ = fixture()
    run = solver.solve(context.problem)
    enumerated = _enumerated_optimum(context.problem)

    assert enumerated is not None
    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert run.candidate is not None

    cp_vector = _recompute_service_quality_objective_vector_with_authority_v1(
        context.problem,
        run.candidate,
        solver.exact_demand_authority,
    )
    independent_vector = _independent_vector_for_minutes(
        context.problem,
        {
            trip.source_b_trip_id: trip.c_departure_time // 60
            for trip in run.candidate.exact_timetable
        },
    )

    # The first eight objectives are independent of final Scenario C regime regrouping.
    # V2 regime regularity and transition semantics are covered by dedicated canonical-policy tests.
    assert cp_vector[:8] == independent_vector[:8] == enumerated[:8]


def test_repeated_default_solves_are_deterministic() -> None:
    context, solver, *_ = _two_regime_fixture()
    first = solver.solve(context.problem)
    second = solver.solve(context.problem)
    assert first.candidate is not None and second.candidate is not None

    assert first.candidate.exact_timetable == second.candidate.exact_timetable
    assert first.candidate.headway_regimes == second.candidate.headway_regimes
    assert first.candidate.candidate_fingerprint == second.candidate.candidate_fingerprint
    assert _recompute_service_quality_objective_vector_v1(
        context.problem,
        first.candidate,
    ) == _recompute_service_quality_objective_vector_v1(
        context.problem,
        second.candidate,
    )


def test_existing_feasibility_and_demand_adapters_remain_unchanged() -> None:
    assert OrToolsCpSatScheduleSolver.adapter_id == "ortools_cp_sat_v1"
    assert OrToolsCpSatDemandOptimizationSolver.adapter_id == "ortools_cp_sat_demand_v1"
    assert tuple(inspect.signature(OrToolsCpSatScheduleSolver.solve).parameters) == (
        "self",
        "problem",
    )
    assert tuple(inspect.signature(OrToolsCpSatDemandOptimizationSolver.solve).parameters) == (
        "self",
        "problem",
    )
    assert ortools_solver_module._DEMAND_OBJECTIVE_NAMES == (
        "no_service_block_count",
        "critical_block_count",
        "total_critical_shortage_trips",
        "planning_warning_block_count",
        "total_planning_shortage_trips",
        "shifted_trip_count",
        "total_shift_minutes",
        "maximum_shift_minutes",
    )


def test_feasibility_adapter_remains_objective_free() -> None:
    context, _, _ = _request(
        outbound_minutes=(360, 390),
        inbound_minutes=(365, 395),
        fleet_limit=4,
    )
    assert not ortools_solver_module._build_cp_sat_model(context.problem).model.proto.objective.vars


def test_quality_model_has_fifteen_unweighted_stages() -> None:
    context, *_ = _two_regime_fixture()
    bundle = _build_quality_cp_sat_model(context.problem)

    assert tuple(stage.name for stage in bundle.stages) == _OBJECTIVE_NAMES
    assert not bundle.demand.hard.model.proto.objective.vars


def test_no_variable_trip_count_fleet_minimization_or_heuristic_import() -> None:
    source = Path(quality_module.__file__).read_text(encoding="utf-8")

    assert "HeuristicScheduleSolverAdapter" not in source
    assert "generate_scenario_c" not in source
    assert "fleet_minimization_objective" not in source
    assert "variable_trip_count_objective" not in source


def test_no_ui_chart_xlsx_schema_or_phase_b_integration() -> None:
    source = Path(quality_module.__file__).read_text(encoding="utf-8")

    assert "streamlit" not in source.lower()
    assert "plotly" not in source.lower()
    assert "openpyxl" not in source.lower()
    assert "jsonschema" not in source.lower()
    assert "adjustment_routing" not in source
    assert "AuthorizationProfile" not in source
    assert "OrchestrationEnvelope" not in source


def test_optimization_service_integrates_only_the_canonical_quality_builder() -> None:
    source = Path(optimization_service.__file__).read_text(encoding="utf-8")

    assert "OrToolsCpSatServiceQualitySolver" not in source
    assert "build_ortools_service_quality_request_v1" in source
    optimization_service._validate_solver_choice(SolverChoice.OR_TOOLS)
    optimization_service._validate_solver_choice(SolverChoice.BOTH)
