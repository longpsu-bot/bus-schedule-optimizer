from __future__ import annotations

import inspect
import math
from dataclasses import replace
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

import pytest
from ortools.sat.python import cp_model
from test_contract_v1_ortools_demand_optimizer import _demand_request, _record
from test_contract_v1_ortools_quality_optimizer import (
    _regularity_fixture,
    _two_regime_fixture,
)

from bus_schedule_engine.contracts_v1 import (
    CandidateValidationStatus,
    ContractDirection,
    NativeSolverStatus,
    ScenarioBEvaluationPolicyV1,
    SolverPolicyV1,
    build_ortools_service_quality_request_v1,
    evaluate_scenario_b_v1,
    run_schedule_solver_v1,
    validate_and_build_solution_v1,
)
from bus_schedule_engine.contracts_v1.demand_resolution import (
    BlockMode,
    DemandBlockPolicyV1,
)
from bus_schedule_engine.contracts_v1.exact_demand_authority import (
    _build_exact_demand_authority,
    _canonical_authority_fingerprint,
    _ExactBlockDemand,
    _ExactDemandAuthority,
    _ExactDemandAuthorityError,
    _scale_exact_demand_authority,
    _source_daily_fraction,
)
from bus_schedule_engine.contracts_v1.models import VolumeClassification
from bus_schedule_engine.contracts_v1.ortools_quality_solver import (
    ORTOOLS_QUALITY_EXACT_DEMAND_CONTEXT_MISMATCH,
    _build_quality_cp_sat_model,
)
from bus_schedule_engine.contracts_v1.regime_headway_policy import (
    _authoritative_candidate_payload,
)
from bus_schedule_engine.contracts_v1.service_quality_metrics import (
    _recompute_service_quality_objective_vector_with_authority_v1,
)
from bus_schedule_engine.contracts_v1.solver_fingerprints import candidate_fingerprint
from bus_schedule_engine.contracts_v1.solver_models import (
    RawCandidateTripV1,
    RawScheduleCandidateV1,
)
from bus_schedule_engine.models import DemandRecord, Direction, VolumeType
from bus_schedule_engine.optimization_comparison import compare_solver_outcomes_v1
from bus_schedule_engine.optimization_service import SolverChoice

ROOT = Path(__file__).resolve().parents[1]


def _total_record(
    direction: Direction,
    start_minute: int,
    end_minute: int,
    passengers: float,
    *,
    observation_days: int = 15,
) -> DemandRecord:
    return DemandRecord(
        period_start=date(2026, 7, 1),
        period_end=date(2026, 7, 1) + timedelta(days=observation_days - 1),
        observation_days=observation_days,
        block_start_seconds=start_minute * 60,
        block_end_seconds=end_minute * 60,
        direction=direction,
        passenger_volume=passengers,
        volume_type=VolumeType.TOTAL_OBSERVATION_PERIOD,
    )


def _exact_fixture(
    *,
    outbound: float = 146,
    inbound: float = 264,
    observation_days: int = 15,
):
    _, _, normalized, evaluation = _demand_request(
        outbound_minutes=(360, 370, 380),
        inbound_minutes=(365, 375),
        fleet_limit=5,
        demand=(
            _total_record(
                Direction.TERMINAL_1_TO_2,
                360,
                381,
                outbound,
                observation_days=observation_days,
            ),
            _total_record(
                Direction.TERMINAL_2_TO_1,
                365,
                376,
                inbound,
                observation_days=observation_days,
            ),
        ),
        route_id=f"EXACT-{outbound}-{inbound}-{observation_days}",
    )
    policy = ScenarioBEvaluationPolicyV1()
    context, solver = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        evaluation_policy=policy,
    )
    return context, solver, normalized, evaluation, policy


def _single_regime_fixture(
    outbound_minutes: tuple[int, ...],
    *,
    inbound_minutes: tuple[int, ...] = (365,),
    fleet_limit: int = 12,
    turnaround: tuple[int, int] = (5, 5),
    solver_policy: SolverPolicyV1 | None = None,
):
    end = max((*outbound_minutes, *inbound_minutes)) + 1
    _, _, normalized, evaluation = _demand_request(
        outbound_minutes=outbound_minutes,
        inbound_minutes=inbound_minutes,
        fleet_limit=fleet_limit,
        turnaround=turnaround,
        solver_policy=solver_policy,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, min(outbound_minutes), end, 20),
            _record(Direction.TERMINAL_2_TO_1, min(inbound_minutes), end, 10),
        ),
        route_id=f"UNIFORM-{'-'.join(map(str, outbound_minutes))}",
    )
    context, solver = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        solver_policy=solver_policy,
    )
    return context, solver


def _raw_candidate_for_seconds(
    problem,
    *,
    outbound_seconds: tuple[int, ...],
    inbound_seconds: tuple[int, ...] | None = None,
) -> tuple[RawScheduleCandidateV1, object]:
    sequences = {
        ContractDirection.OUTBOUND: outbound_seconds,
        ContractDirection.INBOUND: inbound_seconds,
    }
    trips: list[RawCandidateTripV1] = []
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        sources = sorted(
            (trip for trip in problem.scenario_b.exact_timetable if trip.direction == direction),
            key=lambda item: (item.departure_time, item.trip_id),
        )
        values = sequences[direction]
        if values is None:
            values = tuple(source.departure_time for source in sources)
        assert len(sources) == len(values)
        for index, (source, departure) in enumerate(
            zip(sources, values, strict=True),
            start=1,
        ):
            trips.append(
                RawCandidateTripV1(
                    c_trip_id=f"C-{direction.value}-{index:04d}",
                    source_b_trip_id=source.trip_id,
                    direction=source.direction,
                    departure_terminal=source.departure_terminal,
                    b_departure_time=source.departure_time,
                    c_departure_time=departure,
                    arrival_time=departure + source.runtime_minutes * 60,
                    runtime_minutes=source.runtime_minutes,
                    shift_minutes=(departure - source.departure_time) / 60,
                    previous_b_headway=None,
                    previous_c_headway=None,
                    headway_regime_id="REGIME_PENDING_AUTHORITY",
                    change_reason="Focused exact uniformity fixture.",
                )
            )
    labeled, regimes, policy = _authoritative_candidate_payload(
        problem,
        tuple(trips),
    )
    provisional = RawScheduleCandidateV1(
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter=problem.solver_adapter,
        solve_duration_seconds=0.0,
        candidate_fingerprint="",
        exact_timetable=labeled,
        headway_regimes=regimes,
        explanation="Focused exact uniformity fixture.",
        limitations=(),
    )
    return (
        replace(
            provisional,
            candidate_fingerprint=candidate_fingerprint(
                problem_fingerprint=problem.problem_fingerprint,
                solver_adapter=problem.solver_adapter,
                exact_timetable=labeled,
                headway_regimes=regimes,
            ),
        ),
        policy,
    )


def _refingerprint(problem, candidate):
    return replace(
        candidate,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=problem.problem_fingerprint,
            solver_adapter=candidate.solver_adapter,
            exact_timetable=candidate.exact_timetable,
            headway_regimes=candidate.headway_regimes,
        ),
    )


def test_exact_total_period_values_remain_reduced_fractions() -> None:
    _, solver, *_ = _exact_fixture()
    fractions = {block.fraction for block in solver.exact_demand_authority.blocks}
    assert Fraction(146, 15) in fractions
    assert Fraction(264, 15) == Fraction(88, 5)
    assert Fraction(88, 5) in fractions


@pytest.mark.parametrize(
    ("value", "classification", "days", "expected"),
    (
        (7, VolumeClassification.AVERAGE_DAY, 15, Fraction(7, 1)),
        (1.25, VolumeClassification.AVERAGE_DAY, 15, Fraction(5, 4)),
        (0, VolumeClassification.AVERAGE_DAY, 15, Fraction(0, 1)),
        (146, VolumeClassification.TOTAL_OBSERVATION_PERIOD, 15, Fraction(146, 15)),
        (264, VolumeClassification.TOTAL_OBSERVATION_PERIOD, 15, Fraction(88, 5)),
    ),
)
def test_source_conversion_is_exact(
    value,
    classification,
    days,
    expected,
) -> None:
    assert _source_daily_fraction(value, classification, days) == expected


def test_negative_exact_demand_fails_closed() -> None:
    with pytest.raises(_ExactDemandAuthorityError) as caught:
        _source_daily_fraction(
            -1,
            VolumeClassification.AVERAGE_DAY,
            1,
        )
    assert caught.value.code == "EXACT_DEMAND_NEGATIVE"


def test_native_block_maps_one_source_and_every_block_has_authority() -> None:
    _, solver, _, evaluation, _ = _exact_fixture()
    assert evaluation.demand_resolution is not None
    assert all(len(block.source_interval_ids) == 1 for block in evaluation.demand_resolution.blocks)
    assert {block.block_id for block in solver.exact_demand_authority.blocks} == {
        block.block_id for block in evaluation.demand_resolution.blocks
    }


@pytest.mark.parametrize("mode", (BlockMode.ADAPTIVE, BlockMode.MANUAL))
def test_sum_blocks_aggregate_source_fractions_exactly(mode: BlockMode) -> None:
    _, _, normalized, _ = _demand_request(
        outbound_minutes=(360, 370, 379),
        inbound_minutes=(360, 370, 379),
        fleet_limit=6,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 370, 10),
            _record(Direction.TERMINAL_1_TO_2, 370, 380, 20),
            _record(Direction.TERMINAL_2_TO_1, 360, 370, 30),
            _record(Direction.TERMINAL_2_TO_1, 370, 380, 40),
        ),
        route_id=f"EXACT-{mode.value}-SUM",
    )
    block_policy = DemandBlockPolicyV1(
        block_mode=mode,
        manual_boundaries=((360 * 60, 380 * 60) if mode == BlockMode.MANUAL else ()),
        material_change_ratio=10,
    )
    policy = ScenarioBEvaluationPolicyV1(demand_blocks=block_policy)
    evaluation = evaluate_scenario_b_v1(normalized, policy)
    authority = _build_exact_demand_authority(
        normalized,
        evaluation,
        evaluation_policy=policy,
    )
    assert {block.fraction for block in authority.blocks} == {
        Fraction(30, 1),
        Fraction(70, 1),
    }


def test_missing_unknown_and_duplicate_source_mappings_fail_closed() -> None:
    _, _, normalized, evaluation, policy = _exact_fixture()
    assert evaluation.demand_resolution is not None
    blocks = evaluation.demand_resolution.blocks
    unknown = replace(
        blocks[0],
        source_interval_ids=("UNKNOWN-SOURCE",),
    )
    unknown_evaluation = replace(
        evaluation,
        demand_resolution=replace(
            evaluation.demand_resolution,
            blocks=(unknown, *blocks[1:]),
        ),
    )
    with pytest.raises(_ExactDemandAuthorityError) as caught:
        _build_exact_demand_authority(
            normalized,
            unknown_evaluation,
            evaluation_policy=policy,
        )
    assert caught.value.code == "EXACT_DEMAND_UNKNOWN_SOURCE_OBSERVATION"

    duplicated = replace(
        blocks[1],
        source_interval_ids=blocks[0].source_interval_ids,
    )
    duplicate_evaluation = replace(
        evaluation,
        demand_resolution=replace(
            evaluation.demand_resolution,
            blocks=(blocks[0], duplicated),
        ),
    )
    with pytest.raises(_ExactDemandAuthorityError) as caught:
        _build_exact_demand_authority(
            normalized,
            duplicate_evaluation,
            evaluation_policy=policy,
        )
    assert caught.value.code == "EXACT_DEMAND_SOURCE_ASSIGNED_INCONSISTENTLY"


def test_authority_fingerprint_is_deterministic_order_independent_and_sensitive() -> None:
    _, solver, normalized, evaluation, policy = _exact_fixture()
    first = solver.exact_demand_authority
    second = _build_exact_demand_authority(
        normalized,
        evaluation,
        evaluation_policy=policy,
    )
    assert first.authority_fingerprint == second.authority_fingerprint
    reversed_rows = tuple(reversed(first.blocks))
    assert _canonical_authority_fingerprint(reversed_rows) == first.authority_fingerprint
    changed_rows = (
        replace(first.blocks[0], numerator=first.blocks[0].numerator + 1),
        *first.blocks[1:],
    )
    assert _canonical_authority_fingerprint(changed_rows) != first.authority_fingerprint


def test_observation_day_change_changes_authority_fingerprint() -> None:
    _, first, *_ = _exact_fixture(observation_days=15)
    _, second, *_ = _exact_fixture(observation_days=14)
    assert (
        first.exact_demand_authority.authority_fingerprint
        != second.exact_demand_authority.authority_fingerprint
    )


def test_problem_context_binds_exact_authority_and_mismatch_is_model_invalid() -> None:
    context, solver, *_ = _exact_fixture()
    assert (
        context.problem.adapter_context_fingerprint
        == solver.exact_demand_authority.authority_fingerprint
    )
    mismatch = replace(
        context.problem,
        adapter_context_fingerprint="0" * 64,
    )
    run = solver.solve(mismatch)
    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert any(
        ORTOOLS_QUALITY_EXACT_DEMAND_CONTEXT_MISMATCH in explanation
        for explanation in run.explanations
    )


def test_global_lcm_and_gcd_reduction_share_one_two_direction_scale() -> None:
    context, solver, *_ = _exact_fixture()
    scaled = _scale_exact_demand_authority(
        solver.exact_demand_authority,
        context.problem,
    )
    assert scaled.common_denominator == 15
    assert scaled.reduction_gcd == 2
    assert set(scaled.weight_by_block_id.values()) == {73, 132}
    assert set(scaled.total_by_direction) == {
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
    }


def test_mixed_denominators_scale_without_rounding_or_truncation() -> None:
    context, solver, *_ = _exact_fixture(outbound=146, inbound=55)
    scaled = _scale_exact_demand_authority(
        solver.exact_demand_authority,
        context.problem,
    )
    exact = solver.exact_demand_authority.fraction_by_block_id()
    weighted = scaled.weight_by_block_id
    ids = tuple(exact)
    assert Fraction(weighted[ids[0]], weighted[ids[1]]) == exact[ids[0]] / exact[ids[1]]


def test_unsafe_lcm_and_cross_products_fail_closed() -> None:
    context, solver, *_ = _exact_fixture()
    ids = tuple(block.block_id for block in solver.exact_demand_authority.blocks)
    assert math.gcd(3_037_000_499, 3_037_000_503) == 1
    unsafe_lcm = _ExactDemandAuthority(
        blocks=(
            _ExactBlockDemand(ids[0], 1, 3_037_000_499),
            _ExactBlockDemand(ids[1], 1, 3_037_000_503),
        ),
        authority_fingerprint="0" * 64,
    )
    with pytest.raises(_ExactDemandAuthorityError) as caught:
        _scale_exact_demand_authority(unsafe_lcm, context.problem)
    assert caught.value.code == "ORTOOLS_QUALITY_DEMAND_INTEGER_UNSAFE"

    safe_limit = (1 << 62) - 1
    unsafe_cross_product = _ExactDemandAuthority(
        blocks=(
            _ExactBlockDemand(ids[0], safe_limit // 2 + 1, 1),
            _ExactBlockDemand(ids[1], 1, 1),
        ),
        authority_fingerprint="0" * 64,
    )
    with pytest.raises(_ExactDemandAuthorityError) as caught:
        _scale_exact_demand_authority(
            unsafe_cross_product,
            context.problem,
        )
    assert caught.value.code == "ORTOOLS_QUALITY_DEMAND_INTEGER_UNSAFE"


@pytest.mark.parametrize(
    ("minutes", "expected_status", "expected_sequence"),
    (
        ((360, 372, 384, 396), "UNIFORM", (12, 12, 12)),
        ((360, 372, 385, 397), "INVALID_NON_UNIFORM", (12, 13, 12)),
        ((360, 382, 405, 427, 450), "INVALID_NON_UNIFORM", (22, 23, 22, 23)),
        ((360,), "SINGLE_TRIP_HEADWAY_NOT_MEASURABLE", ()),
        ((360, 372), "UNIFORM", (12,)),
    ),
)
def test_regime_uniformity_edge_cases(
    minutes,
    expected_status,
    expected_sequence,
) -> None:
    context, _ = _single_regime_fixture(tuple(minutes))
    candidate, policy = _raw_candidate_for_seconds(
        context.problem,
        outbound_seconds=tuple(value * 60 for value in minutes),
    )
    outbound = next(
        analysis
        for analysis in policy.analyses
        if analysis.regime.direction == ContractDirection.OUTBOUND
    )
    assert outbound.status == expected_status
    assert outbound.internal_headways == expected_sequence
    if expected_status == "INVALID_NON_UNIFORM":
        assert "WITHIN_REGIME_HEADWAY_NOT_UNIFORM" in policy.error_codes
    else:
        assert "WITHIN_REGIME_HEADWAY_NOT_UNIFORM" not in policy.error_codes
    assert candidate.headway_regimes


def test_two_regimes_use_independent_headways_and_transition_is_excluded() -> None:
    context, solver, *_ = _two_regime_fixture()
    outcome = run_schedule_solver_v1(context, solver)
    assert outcome.solution is not None
    outbound = [
        regime
        for regime in outcome.solution.c_headway_regimes
        if regime.direction == ContractDirection.OUTBOUND
    ]
    assert len(outbound) == 2
    assert {regime.target_headway for regime in outbound} == {2.0, 4.0}
    assert all(len(set(regime.actual_headway_sequence)) <= 1 for regime in outbound)
    assert outbound[0].transition_headways == outbound[1].transition_headways
    transition = outbound[0].transition_headways[0]
    assert transition not in outbound[1].actual_headway_sequence


def test_candidate_labels_cannot_bypass_authoritative_validation() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    first = run.candidate.exact_timetable[0]
    corrupted = replace(
        run.candidate,
        exact_timetable=(
            replace(first, headway_regime_id="FAKE-REGIME"),
            *run.candidate.exact_timetable[1:],
        ),
    )
    validation = validate_and_build_solution_v1(
        context,
        _refingerprint(context.problem, corrupted),
    )
    assert validation.status == CandidateValidationStatus.REJECTED
    assert "HEADWAY_REGIME_AUTHORITY_MISMATCH" in validation.rejection_codes


@pytest.mark.parametrize(
    ("seconds", "code"),
    (
        ((360 * 60, 360 * 60), "NON_POSITIVE_ADJACENT_HEADWAY"),
        ((360 * 60, 372 * 60 + 30), "NON_WHOLE_MINUTE_ADJACENT_HEADWAY"),
    ),
)
def test_non_positive_and_non_whole_minute_headways_fail(
    seconds,
    code,
) -> None:
    context, _ = _single_regime_fixture((360, 372))
    _, policy = _raw_candidate_for_seconds(
        context.problem,
        outbound_seconds=seconds,
    )
    assert code in policy.error_codes


def test_accepted_solution_has_zero_within_stages_and_active_transition_stages() -> None:
    context, solver, *_ = _two_regime_fixture()
    outcome = run_schedule_solver_v1(context, solver)
    assert outcome.solution is not None
    vector = _recompute_service_quality_objective_vector_with_authority_v1(
        context.problem,
        outcome.solution,
        solver.exact_demand_authority,
    )
    assert vector[8:10] == (0, 0)
    assert vector[10] > 0
    assert vector[11] > 0


def test_divisible_span_solves_and_non_divisible_span_is_infeasible() -> None:
    divisible_context, divisible_solver = _single_regime_fixture((360, 370, 380, 390, 448))
    divisible = divisible_solver.solve(divisible_context.problem)
    assert divisible.solver_status == NativeSolverStatus.OPTIMAL
    assert divisible.candidate is not None
    outbound = next(
        regime
        for regime in divisible.candidate.headway_regimes
        if regime.direction == ContractDirection.OUTBOUND
    )
    assert outbound.actual_headway_sequence == (22.0, 22.0, 22.0, 22.0)

    impossible_context, impossible_solver, *_ = _regularity_fixture()
    impossible = impossible_solver.solve(impossible_context.problem)
    assert impossible.solver_status == NativeSolverStatus.INFEASIBLE
    assert impossible.candidate is None


def test_unknown_remains_unknown_without_uniformity_relaxation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, solver = _single_regime_fixture((360, 372, 384))
    monkeypatch.setattr(
        cp_model.CpSolver,
        "solve",
        lambda self, model: cp_model.UNKNOWN,
    )
    run = solver.solve(context.problem)
    assert run.solver_status == NativeSolverStatus.UNKNOWN
    assert run.candidate is None


def test_valid_multiple_regime_allocation_can_restore_feasibility() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert run.candidate is not None
    assert (
        len(
            {
                regime.target_headway
                for regime in run.candidate.headway_regimes
                if regime.direction == ContractDirection.OUTBOUND
            }
        )
        > 1
    )


def test_cp_sat_candidate_passes_independent_uniformity_validation() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    validation = validate_and_build_solution_v1(context, run.candidate)
    assert validation.status == CandidateValidationStatus.ACCEPTED
    assert validation.solution is not None


def test_corrupted_non_uniform_quality_candidate_is_rejected() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    outbound = [
        trip
        for trip in run.candidate.exact_timetable
        if trip.direction == ContractDirection.OUTBOUND
    ]
    changed_id = outbound[-2].c_trip_id
    changed = tuple(
        replace(
            trip,
            c_departure_time=trip.c_departure_time + 60,
            arrival_time=trip.arrival_time + 60,
        )
        if trip.c_trip_id == changed_id
        else trip
        for trip in run.candidate.exact_timetable
    )
    corrupted = _refingerprint(
        context.problem,
        replace(run.candidate, exact_timetable=changed),
    )
    validation = validate_and_build_solution_v1(context, corrupted)
    assert validation.status == CandidateValidationStatus.REJECTED
    assert "WITHIN_REGIME_HEADWAY_NOT_UNIFORM" in validation.rejection_codes


def test_raw_candidate_solution_and_solver_proof_use_same_exact_vector() -> None:
    context, solver, *_ = _two_regime_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    validation = validate_and_build_solution_v1(context, run.candidate)
    assert validation.solution is not None
    candidate_vector = _recompute_service_quality_objective_vector_with_authority_v1(
        context.problem,
        run.candidate,
        solver.exact_demand_authority,
    )
    solution_vector = _recompute_service_quality_objective_vector_with_authority_v1(
        context.problem,
        validation.solution,
        solver.exact_demand_authority,
    )
    assert candidate_vector == solution_vector
    assert all(
        f"{name}={value}" in run.candidate.explanation
        for name, value in zip(
            (
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
            ),
            candidate_vector,
            strict=True,
        )
    )


def test_comparison_excludes_non_uniform_accepted_looking_outcome() -> None:
    context, solver, *_ = _two_regime_fixture()
    accepted = run_schedule_solver_v1(context, solver)
    assert accepted.solution is not None
    trips = list(accepted.solution.c_exact_timetable)
    outbound_indexes = [
        index for index, trip in enumerate(trips) if trip.direction == ContractDirection.OUTBOUND
    ]
    changed_index = outbound_indexes[-2]
    trips[changed_index] = replace(
        trips[changed_index],
        c_departure_time=trips[changed_index].c_departure_time + 60,
    )
    fake_non_uniform = replace(
        accepted,
        solution=replace(
            accepted.solution,
            solver_adapter="legacy_heuristic_v1",
            c_exact_timetable=tuple(trips),
        ),
        solver_adapter="legacy_heuristic_v1",
        solver_status=NativeSolverStatus.FEASIBLE,
    )
    comparison = compare_solver_outcomes_v1(
        context.problem,
        fake_non_uniform,
        accepted,
        exact_demand_authority=solver.exact_demand_authority,
    )
    assert comparison.heuristic_vector is None
    assert comparison.ortools_vector is not None
    assert comparison.recommended_solver == SolverChoice.OR_TOOLS
    assert comparison.reason_code == "ONLY_ORTOOLS_ACCEPTED"


def test_source_inspection_proves_solver_decision_variables_and_no_fixed_grid() -> None:
    source = inspect.getsource(_build_quality_cp_sat_model)
    assert "new_int_var" in source
    assert "quality_regime_headway_" in source
    assert "only_enforce_if(same_regime_pair)" in source
    assert "later_departure - earlier_departure" in source
    assert " % " not in source
    assert "modulo" not in source.lower()
    assert "target_headway" not in source
    assert "regime_headway_by_id[regime.regime_id]" in source


def test_no_production_literal_fixes_a_route_or_direction_headway() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src" / "bus_schedule_engine").rglob("*.py")
    )
    prohibited = (
        "target_headway_minutes = 22",
        "target_headway_minutes=22",
        "departure % ",
        "AddModuloEquality",
        "add_modulo_equality",
    )
    assert not any(token in production for token in prohibited)
