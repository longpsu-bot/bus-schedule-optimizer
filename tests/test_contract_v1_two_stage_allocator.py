from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from bus_schedule_engine.contracts_v1 import (
    ContractDirection,
    DemandAllocationAuthorityModeV1,
    DemandConfidence,
    FinalAcceptanceStateV1,
    GenerationResultStatus,
    NativeSolverStatus,
    NormalizationOptions,
    OperatingDayType,
    ScenarioBEvaluationPolicyV1,
    ScenarioCOptimizationModeV1,
    ServiceBoundarySemanticsV1,
    SolverPolicyV1,
    Stage1AllocationResultV1,
    Stage2ConstraintFamilyV1,
    Stage2InfeasibilityDiagnosticV1,
    Stage2TimetableResultV1,
    TripAllocationSolveStatusV1,
    UniformIntegerRegimePolicyV3,
    allocate_trips_stage_1_v1,
    build_schedule_generation_context_v1,
    build_schedule_problem_v1,
    build_two_stage_demand_authority_v1,
    build_two_stage_uniform_request_v1,
    calculate_positive_demand_service_gap_minutes_v1,
    calculate_two_stage_quality_vector_v1,
    evaluate_scenario_b_v1,
    finalize_allocation_plan,
    finalize_stage_2_infeasibility_diagnostic,
    find_representable_uniform_regime_v1,
    normalize_imported_workbook_v1,
    run_two_stage_scenario_c_v1,
    schedule_problem_to_contract_dict,
    schedule_solution_to_contract_dict,
    solve_exact_timetable_stage_2_v1,
    two_stage_result_to_contract_dict_v1,
    validate_and_build_solution_v1,
)
from bus_schedule_engine.contracts_v1 import two_stage_solver as two_stage_solver_module
from bus_schedule_engine.importer import ImportedWorkbook
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    RouteType,
    ScenarioParameters,
    Trip,
    VolumeType,
)

_ADAPTER_ID = "ortools_cp_sat_two_stage_uniform_v1"


def _record(direction: Direction, start: int, end: int, passengers: float) -> DemandRecord:
    return DemandRecord(
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 7),
        observation_days=7,
        block_start_seconds=start * 60,
        block_end_seconds=end * 60,
        direction=direction,
        passenger_volume=passengers,
        volume_type=VolumeType.AVERAGE_DAY,
    )


def _stage1_request(
    *,
    outbound: tuple[int, ...] = (360, 380, 400, 420),
    inbound: tuple[int, ...] = (365, 385, 405, 425),
    demand: tuple[DemandRecord, ...] | None = None,
):
    parameters = ScenarioParameters(
        route_id="SYNTHETIC-STAGE-1",
        route_name="Synthetic Stage 1",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=1,
        total_daily_trips=len(outbound) + len(inbound),
        terminal_1_name="T1",
        terminal_1_first_departure=outbound[0] * 60,
        terminal_1_last_departure=outbound[-1] * 60,
        terminal_2_name="T2",
        terminal_2_first_departure=inbound[0] * 60,
        terminal_2_last_departure=inbound[-1] * 60,
        vehicle_capacity_passengers=60,
        target_load_factor=0.85,
        maximum_load_factor=0.9,
        time_block_minutes=30,
        minimum_layover_minutes=5,
        available_fleet_limit=len(outbound) + len(inbound),
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=f"B-OUT-{index:03d}",
            departure_terminal="T1",
            direction=Direction.TERMINAL_1_TO_2,
            departure_seconds=minute * 60,
            arrival_seconds=(minute + 1) * 60,
        )
        for index, minute in enumerate(outbound, start=1)
    ] + [
        Trip(
            scenario="B",
            trip_id=f"B-IN-{index:03d}",
            departure_terminal="T2",
            direction=Direction.TERMINAL_2_TO_1,
            departure_seconds=minute * 60,
            arrival_seconds=(minute + 1) * 60,
        )
        for index, minute in enumerate(inbound, start=1)
    ]
    effective_demand = demand or (
        _record(Direction.TERMINAL_1_TO_2, 360, 391, 80),
        _record(Direction.TERMINAL_1_TO_2, 391, 421, 70),
        _record(Direction.TERMINAL_2_TO_1, 365, 396, 75),
        _record(Direction.TERMINAL_2_TO_1, 396, 426, 65),
    )
    normalized = normalize_imported_workbook_v1(
        ImportedWorkbook(
            parameters_a=None,
            trips_a=[],
            parameters_b=parameters,
            trips_b=trips,
            demand=list(effective_demand),
            configuration={},
        ),
        NormalizationOptions(
            source_id="synthetic-stage-1",
            imported_at=datetime(2026, 8, 18, 8, 0, tzinfo=UTC),
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_b=len(outbound) + len(inbound),
            terminal_1_max_occupancy_vehicles_b=len(outbound) + len(inbound),
            terminal_2_max_occupancy_vehicles_b=len(outbound) + len(inbound),
            demand_confidence=DemandConfidence.HIGH,
            optimization_mode=ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE,
        ),
    )
    evaluation_policy = ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(normalized, evaluation_policy)
    authority = build_two_stage_demand_authority_v1(normalized, evaluation)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        solver_adapter=_ADAPTER_ID,
        adapter_context_fingerprint=authority.authority_fingerprint,
        evaluation_policy=evaluation_policy,
        solver_policy=SolverPolicyV1(time_limit_seconds=2.0),
        demand_allocation_authority_mode=authority.authority_mode,
    )
    return problem, authority, normalized, evaluation, evaluation_policy


def test_exact_uniform_representability_and_bounded_boundary_repair() -> None:
    exact = find_representable_uniform_regime_v1(
        (360, 370, 380),
        permitted_start_window=(360, 360),
        permitted_end_window=(380, 380),
        minimum_headway_minutes=2,
        maximum_headway_minutes=30,
        absolute_max_shift_per_trip_minutes=30,
        preferred_start_minute=360,
        preferred_end_minute=380,
    )
    repaired = find_representable_uniform_regime_v1(
        (360, 367, 374, 380),
        permitted_start_window=(360, 360),
        permitted_end_window=(378, 382),
        minimum_headway_minutes=2,
        maximum_headway_minutes=30,
        absolute_max_shift_per_trip_minutes=30,
        preferred_start_minute=360,
        preferred_end_minute=380,
    )

    assert exact is not None and exact.departure_minutes == (360, 370, 380)
    assert repaired is not None and repaired.departure_minutes == (360, 367, 374, 381)


def test_alternate_trip_count_can_repair_a_non_divisible_span_without_balanced_rounding() -> None:
    four_trips = find_representable_uniform_regime_v1(
        (360, 367, 374, 380),
        permitted_start_window=(360, 360),
        permitted_end_window=(380, 380),
        minimum_headway_minutes=2,
        maximum_headway_minutes=30,
        absolute_max_shift_per_trip_minutes=30,
        preferred_start_minute=360,
        preferred_end_minute=380,
    )
    three_trips = find_representable_uniform_regime_v1(
        (360, 370, 380),
        permitted_start_window=(360, 360),
        permitted_end_window=(380, 380),
        minimum_headway_minutes=2,
        maximum_headway_minutes=30,
        absolute_max_shift_per_trip_minutes=30,
        preferred_start_minute=360,
        preferred_end_minute=380,
    )

    assert four_trips is None
    assert three_trips is not None
    assert three_trips.uniform_headway_minutes == 10


def test_no_representable_progression_returns_explicit_none() -> None:
    assert (
        find_representable_uniform_regime_v1(
            (360, 370, 380),
            permitted_start_window=(360, 360),
            permitted_end_window=(381, 381),
            minimum_headway_minutes=2,
            maximum_headway_minutes=30,
            absolute_max_shift_per_trip_minutes=30,
            preferred_start_minute=360,
            preferred_end_minute=381,
        )
        is None
    )


def test_stage_1_fixes_daily_and_directional_totals_and_emits_only_exact_regimes() -> None:
    problem, authority, *_ = _stage1_request()
    result = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=2),
        time_limit_seconds=2.0,
    )

    assert result.plans
    plan = result.plans[0]
    assert plan.total_trips == 8
    assert dict(plan.trips_by_direction) == {
        ContractDirection.OUTBOUND: 4,
        ContractDirection.INBOUND: 4,
    }
    for regime in plan.proposed_regimes:
        if regime.measurable:
            assert regime.uniform_headway_minutes is not None
            assert regime.planned_end_minute - regime.planned_start_minute == (
                (regime.trip_count - 1) * regime.uniform_headway_minutes
            )
    assert any(len(regime.covered_demand_block_ids) > 1 for regime in plan.proposed_regimes)
    assert plan.necessary_feasibility.passed
    assert plan.necessary_feasibility.diagnostic_fingerprint
    assert plan.necessary_feasibility.fleet_lower_bound is not None
    assert plan.necessary_feasibility.fleet_lower_bound <= problem.scenario_b.available_fleet_limit
    b_no_service = c_no_service = 0
    b_critical = c_critical = 0
    b_planning = c_planning = 0
    for block in plan.allocation_blocks:
        b_no_service += int(block.observed_passengers > 0 and block.source_b_trip_count == 0)
        c_no_service += int(block.observed_passengers > 0 and block.trip_count == 0)
        b_critical += max(0, block.required_trips_90 - block.source_b_trip_count)
        c_critical += max(0, block.required_trips_90 - block.trip_count)
        b_planning += max(0, block.required_trips_85 - block.source_b_trip_count)
        c_planning += max(0, block.required_trips_85 - block.trip_count)
    assert all(
        c_value <= b_value
        for c_value, b_value in zip(
            (c_no_service, c_critical, c_planning),
            (b_no_service, b_critical, b_planning),
            strict=True,
        )
    )


def test_combined_demand_allocates_total_service_without_changing_direction_counts() -> None:
    problem, authority, *_ = _stage1_request(
        demand=(
            _record(Direction.COMBINED, 360, 396, 170),
            _record(Direction.COMBINED, 396, 426, 130),
        )
    )
    assert authority.authority_mode == (
        DemandAllocationAuthorityModeV1.COMBINED_FIXED_DIRECTION_COUNTS
    )
    result = allocate_trips_stage_1_v1(
        problem,
        authority,
        time_limit_seconds=2.0,
    )

    assert result.plans
    plan = result.plans[0]
    assert dict(plan.trips_by_direction) == {
        ContractDirection.OUTBOUND: 4,
        ContractDirection.INBOUND: 4,
    }
    assert all(block.direction == ContractDirection.COMBINED for block in plan.allocation_blocks)
    assert all(len(block.directional_trip_counts) == 2 for block in plan.allocation_blocks)
    assert any(
        "does not claim directional passenger inference" in item for item in result.limitations
    )
    stage_2 = solve_exact_timetable_stage_2_v1(
        problem,
        plan,
        policy=UniformIntegerRegimePolicyV3(),
        time_limit_seconds=2.0,
    )
    assert stage_2.candidate is not None
    combined_gap = calculate_positive_demand_service_gap_minutes_v1(
        problem.analysis_blocks,
        tuple(
            (trip.direction, trip.c_departure_time // 60)
            for trip in stage_2.candidate.exact_timetable
        ),
    )
    assert combined_gap < max(block.duration_minutes for block in problem.analysis_blocks)


def test_combined_passenger_gap_uses_one_alternating_service_stream() -> None:
    combined_problem, *_ = _stage1_request(
        outbound=(425, 460),
        inbound=(440, 475),
        demand=(_record(Direction.COMBINED, 420, 480, 130),),
    )
    directional_problem, *_ = _stage1_request(
        outbound=(425, 460),
        inbound=(440, 475),
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 420, 480, 65),
            _record(Direction.TERMINAL_2_TO_1, 420, 480, 65),
        ),
    )
    alternating = (
        (ContractDirection.OUTBOUND, 425),
        (ContractDirection.INBOUND, 440),
        (ContractDirection.OUTBOUND, 460),
        (ContractDirection.INBOUND, 475),
    )

    assert (
        calculate_positive_demand_service_gap_minutes_v1(
            combined_problem.analysis_blocks,
            alternating,
        )
        == 20
    )
    assert (
        calculate_positive_demand_service_gap_minutes_v1(
            directional_problem.analysis_blocks,
            alternating,
        )
        == 35
    )


def test_combined_passenger_metrics_ignore_direction_split_with_same_service_sequence() -> None:
    problem, _, normalized, evaluation, evaluation_policy = _stage1_request(
        outbound=(425, 460),
        inbound=(440, 475),
        demand=(_record(Direction.COMBINED, 420, 480, 130),),
    )
    minutes = (425, 440, 460, 475)
    first_split = tuple(
        (direction, minute)
        for direction, minute in zip(
            (
                ContractDirection.OUTBOUND,
                ContractDirection.INBOUND,
                ContractDirection.OUTBOUND,
                ContractDirection.INBOUND,
            ),
            minutes,
            strict=True,
        )
    )
    second_split = tuple(
        (direction, minute)
        for direction, minute in zip(
            (
                ContractDirection.OUTBOUND,
                ContractDirection.OUTBOUND,
                ContractDirection.OUTBOUND,
                ContractDirection.OUTBOUND,
            ),
            minutes,
            strict=True,
        )
    )

    assert calculate_positive_demand_service_gap_minutes_v1(
        problem.analysis_blocks,
        first_split,
    ) == calculate_positive_demand_service_gap_minutes_v1(
        problem.analysis_blocks,
        second_split,
    )

    context = build_schedule_generation_context_v1(
        problem,
        normalized,
        evaluation,
        evaluation_policy,
    )
    combined_only_solution = SimpleNamespace(
        c_exact_timetable=tuple(
            SimpleNamespace(
                direction=direction,
                c_departure_time=minute * 60,
                headway_regime_id="SYNTHETIC-COMBINED",
            )
            for direction, minute in second_split
        ),
        shifted_trip_count=0,
        total_shift_minutes=0,
        maximum_shift_minutes=0,
    )
    vector = calculate_two_stage_quality_vector_v1(
        context,
        solution=combined_only_solution,
    )
    assert vector[0] == 0
    assert vector[4] == 20


def test_stage_1_rejects_non_positive_budget() -> None:
    problem, authority, *_ = _stage1_request()
    with pytest.raises(ValueError, match="finite and positive"):
        allocate_trips_stage_1_v1(problem, authority, time_limit_seconds=0)


def test_stage_1_prunes_plan_when_safe_fleet_lower_bound_exceeds_limit() -> None:
    problem, authority, *_ = _stage1_request()
    long_runtime_scenario = replace(
        problem.scenario_b,
        available_fleet_limit=1,
        exact_timetable=tuple(
            replace(
                trip,
                runtime_minutes=100,
                arrival_time=trip.departure_time + 100 * 60,
            )
            for trip in problem.scenario_b.exact_timetable
        ),
    )
    constrained_problem = replace(problem, scenario_b=long_runtime_scenario)

    result = allocate_trips_stage_1_v1(
        constrained_problem,
        authority,
        policy=UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=1),
        time_limit_seconds=2.0,
    )

    assert not result.plans
    assert result.necessary_feasibility_pruned_count >= 1
    diagnostic = result.pruned_necessary_feasibility[0]
    assert not diagnostic.passed
    assert Stage2ConstraintFamilyV1.FLEET in diagnostic.constraint_families
    assert diagnostic.fleet_lower_bound is not None
    assert diagnostic.fleet_lower_bound > constrained_problem.scenario_b.available_fleet_limit


def test_stage_2_uses_fixed_allocation_exact_uniformity_and_b_anchored_minutes() -> None:
    problem, authority, *_ = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=1)
    stage_1 = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=policy,
        time_limit_seconds=2.0,
    )
    assert stage_1.plans
    stage_2 = solve_exact_timetable_stage_2_v1(
        problem,
        stage_1.plans[0],
        policy=policy,
        time_limit_seconds=2.0,
    )

    assert stage_2.candidate is not None
    candidate = stage_2.candidate
    assert len(candidate.exact_timetable) == problem.scenario_b.total_daily_trips
    source = {trip.trip_id: trip for trip in problem.scenario_b.exact_timetable}
    assert {trip.source_b_trip_id for trip in candidate.exact_timetable} == set(source)
    assert all(trip.c_departure_time % 60 == 0 for trip in candidate.exact_timetable)
    assert all(
        abs(trip.c_departure_time - source[trip.source_b_trip_id].departure_time)
        <= policy.absolute_max_shift_per_trip_minutes * 60
        for trip in candidate.exact_timetable
    )
    assert all(
        trip.arrival_time
        == trip.c_departure_time + source[trip.source_b_trip_id].runtime_minutes * 60
        for trip in candidate.exact_timetable
    )
    assert all(
        not regime.actual_headway_sequence or len(set(regime.actual_headway_sequence)) == 1
        for regime in candidate.headway_regimes
    )


def test_stage_2_infeasible_result_has_versioned_family_diagnostic() -> None:
    problem, authority, *_ = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=1)
    stage_1 = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=policy,
        time_limit_seconds=2.0,
    )
    assert stage_1.plans
    constrained_problem = replace(
        problem,
        scenario_b=replace(problem.scenario_b, available_fleet_limit=1),
    )

    stage_2 = solve_exact_timetable_stage_2_v1(
        constrained_problem,
        stage_1.plans[0],
        policy=policy,
        time_limit_seconds=2.0,
    )

    assert stage_2.solver_status == NativeSolverStatus.INFEASIBLE
    assert stage_2.candidate is None
    diagnostic = stage_2.infeasibility_diagnostic
    assert diagnostic is not None
    assert diagnostic.diagnostic_profile == ("scenario_c_stage_2_infeasibility_diagnostic_v1")
    assert diagnostic.diagnostic_fingerprint
    assert Stage2ConstraintFamilyV1.FLEET in diagnostic.constraint_families
    assert Stage2ConstraintFamilyV1.REGIME_TRANSITION_JUMP in diagnostic.constraint_families
    assert "not claimed to be a mathematically minimal unsat core" in diagnostic.explanation


def test_stage_2_candidate_passes_existing_runtime_fleet_turnaround_and_occupancy_validator() -> (
    None
):
    problem, authority, normalized, evaluation, evaluation_policy = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=1)
    stage_1 = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=policy,
        time_limit_seconds=2.0,
    )
    stage_2 = solve_exact_timetable_stage_2_v1(
        problem,
        stage_1.plans[0],
        policy=policy,
        time_limit_seconds=2.0,
    )
    assert stage_2.candidate is not None

    context = build_schedule_generation_context_v1(
        problem,
        normalized,
        evaluation,
        evaluation_policy,
    )
    validation = validate_and_build_solution_v1(
        context,
        stage_2.candidate,
        allocation_plan=stage_1.plans[0],
        uniform_regime_policy=policy,
    )

    assert validation.passed, validation.rejection_codes
    assert validation.solution is not None
    assert validation.solution.minimum_required_fleet <= problem.scenario_b.available_fleet_limit
    assert problem.scenario_b.terminal_occupancy_limits is not None
    assert any("Physical terminal occupancy" in item for item in validation.solution.explanations)


def test_two_stage_adapter_shares_one_finite_budget_and_bounds_allocation_retries() -> None:
    _, _, normalized, evaluation, evaluation_policy = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=2)
    context, solver = build_two_stage_uniform_request_v1(
        normalized,
        evaluation,
        evaluation_policy=evaluation_policy,
        solver_policy=SolverPolicyV1(time_limit_seconds=2.0),
        uniform_regime_policy=policy,
    )

    result = run_two_stage_scenario_c_v1(context, solver)

    assert result.native_solver_status in {
        NativeSolverStatus.OPTIMAL,
        NativeSolverStatus.FEASIBLE,
    }
    assert result.final_acceptance_state != FinalAcceptanceStateV1.NO_FINAL_C_WITHIN_SOLVE_BUDGET
    assert result.diagnostics.total_budget_seconds == 2.0
    assert result.diagnostics.solve_duration_stage_1 <= 0.7 + 0.1
    assert result.diagnostics.stage_2_allocation_attempt_count <= 2
    assert result.diagnostics.maximum_stage_2_departure_domain_width_minutes <= (
        policy.absolute_max_shift_per_trip_minutes * 2
    )
    assert result.diagnostics.full_service_window_domain_count == 0
    assert (
        result.diagnostics.solve_duration_stage_1 + result.diagnostics.solve_duration_stage_2 <= 2.1
    )
    assert result.result_fingerprint
    assert result.allocation_plan is not None
    assert result.candidate_outcome is not None
    assert result.candidate_outcome.solution is not None

    artifact = two_stage_result_to_contract_dict_v1(result)
    allocation = artifact["stage_1_allocation"]
    accepted = artifact["accepted_candidate"]
    assert isinstance(allocation, dict)
    assert isinstance(accepted, dict)
    assert allocation["allocation_by_demand_interval"]
    assert allocation["necessary_feasibility"]["passed"] is True
    assert allocation["necessary_feasibility"]["fleet_lower_bound"] is not None
    assert accepted["final_service_regimes"]
    assert all(
        trip["c_departure_time"].endswith(":00")
        for trip in accepted["exact_timetable_and_b_to_c_shifts"]
    )
    assert artifact["final_service_tail_metrics"]
    assert artifact["solve_diagnostics"]["total_budget_seconds"] == 2.0
    assert artifact["solve_diagnostics"]["full_service_window_domain_count"] == 0
    assert artifact["solve_diagnostics"]["stage_2_infeasibility_diagnostics"] == []


def test_bounded_stage_2_infeasibility_is_unknown_without_losing_plan_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, normalized, evaluation, evaluation_policy = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=2)
    context, solver = build_two_stage_uniform_request_v1(
        normalized,
        evaluation,
        evaluation_policy=evaluation_policy,
        solver_policy=SolverPolicyV1(time_limit_seconds=5.0),
        uniform_regime_policy=policy,
    )
    seed_stage_1 = allocate_trips_stage_1_v1(
        context.problem,
        solver.demand_authority,
        policy=policy,
        time_limit_seconds=2.0,
    )
    assert seed_stage_1.plans
    first_plan = seed_stage_1.plans[0]
    second_plan = finalize_allocation_plan(replace(first_plan, rank=2, allocation_fingerprint=""))
    bounded_stage_1 = Stage1AllocationResultV1(
        solve_status=TripAllocationSolveStatusV1.FEASIBLE,
        plans=(first_plan, second_plan),
        candidate_count=12,
        admissible_allocation_count=2,
        necessary_feasibility_pruned_count=8,
        pruned_necessary_feasibility=(),
        solve_duration_seconds=0.01,
        budget_exhausted=False,
        explanations=("Stage 1 returned the configured bounded top-N plan set.",),
        limitations=("Additional authorized Stage 1 allocations may exist.",),
    )
    attempts: list[Stage2TimetableResultV1] = []

    def prove_fixed_plan_infeasible(
        problem,
        plan,
        **_kwargs,
    ) -> Stage2TimetableResultV1:
        diagnostic = finalize_stage_2_infeasibility_diagnostic(
            Stage2InfeasibilityDiagnosticV1(
                allocation_plan_fingerprint=plan.allocation_fingerprint,
                native_solver_status=NativeSolverStatus.INFEASIBLE,
                constraint_families=(Stage2ConstraintFamilyV1.FLEET,),
                explanation=(
                    "Stage 2 proved this allocation plan infeasible under the encoded constraints."
                ),
            )
        )
        attempt = Stage2TimetableResultV1(
            solver_status=NativeSolverStatus.INFEASIBLE,
            candidate=None,
            allocation_plan=plan,
            solve_duration_seconds=0.01,
            variable_count=1,
            constraint_count=1,
            maximum_departure_domain_width_minutes=1,
            full_service_window_domain_count=0,
            infeasibility_diagnostic=diagnostic,
            explanations=(diagnostic.explanation,),
            limitations=(),
        )
        attempts.append(attempt)
        return attempt

    monkeypatch.setattr(
        two_stage_solver_module,
        "solve_exact_timetable_stage_2_v1",
        prove_fixed_plan_infeasible,
    )
    monkeypatch.setattr(
        two_stage_solver_module,
        "allocate_trips_stage_1_v1",
        lambda *_args, **_kwargs: bounded_stage_1,
    )

    result = run_two_stage_scenario_c_v1(context, solver)

    assert len(attempts) == policy.maximum_stage_1_alternative_plans
    assert all(item.solver_status == NativeSolverStatus.INFEASIBLE for item in attempts)
    assert result.native_solver_status == NativeSolverStatus.UNKNOWN
    assert result.final_acceptance_state == FinalAcceptanceStateV1.NO_FINAL_C_WITHIN_SOLVE_BUDGET
    assert result.candidate_outcome is not None
    assert result.candidate_outcome.result_status == (
        GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT
    )
    assert result.candidate_outcome.result_status != (
        GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS
    )
    assert not result.diagnostics.budget_exhausted
    assert len(result.diagnostics.stage_2_infeasibility_diagnostics) == len(attempts)
    assert all(
        item.native_solver_status == NativeSolverStatus.INFEASIBLE
        for item in result.diagnostics.stage_2_infeasibility_diagnostics
    )
    assert any(
        "All bounded Stage 2 allocation plans attempted in this run were proven infeasible." in item
        for item in result.explanations
    )
    assert any("bounded-plan exhaustion is not a timeout" in item for item in result.explanations)
    assert any(
        "This does not prove that no feasible Scenario C exists under the locked Scenario B "
        "parameters." in item
        for item in (*result.explanations, *result.limitations)
    )

    artifact = two_stage_result_to_contract_dict_v1(result)
    assert artifact["native_solver_status"] == "UNKNOWN"
    assert artifact["final_acceptance_state"] == "NO_FINAL_C_WITHIN_SOLVE_BUDGET"
    serialized_diagnostics = artifact["solve_diagnostics"]["stage_2_infeasibility_diagnostics"]
    assert len(serialized_diagnostics) == len(attempts)
    assert all(item["native_solver_status"] == "INFEASIBLE" for item in serialized_diagnostics)


def test_exhaustive_stage_1_infeasibility_remains_aggregate_infeasible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, normalized, evaluation, evaluation_policy = _stage1_request()
    context, solver = build_two_stage_uniform_request_v1(
        normalized,
        evaluation,
        evaluation_policy=evaluation_policy,
        solver_policy=SolverPolicyV1(time_limit_seconds=2.0),
    )

    def prove_complete_stage_1_model_infeasible(*_args, **_kwargs) -> Stage1AllocationResultV1:
        return Stage1AllocationResultV1(
            solve_status=TripAllocationSolveStatusV1.INFEASIBLE,
            plans=(),
            candidate_count=0,
            admissible_allocation_count=0,
            necessary_feasibility_pruned_count=0,
            pruned_necessary_feasibility=(),
            solve_duration_seconds=0.01,
            budget_exhausted=False,
            explanations=(
                "Stage 1 CP-SAT proved the complete encoded allocation model infeasible.",
            ),
            limitations=(),
        )

    monkeypatch.setattr(
        two_stage_solver_module,
        "allocate_trips_stage_1_v1",
        prove_complete_stage_1_model_infeasible,
    )

    result = run_two_stage_scenario_c_v1(context, solver)

    assert result.native_solver_status == NativeSolverStatus.INFEASIBLE
    assert result.final_acceptance_state == FinalAcceptanceStateV1.NO_FINAL_C_WITHIN_SOLVE_BUDGET
    assert result.candidate_outcome is not None
    assert result.candidate_outcome.result_status == (
        GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS
    )
    assert result.diagnostics.stage_2_allocation_attempt_count == 0


def test_budget_timeout_is_truthfully_unknown_not_infeasible() -> None:
    _, _, normalized, evaluation, evaluation_policy = _stage1_request()
    context, solver = build_two_stage_uniform_request_v1(
        normalized,
        evaluation,
        evaluation_policy=evaluation_policy,
        solver_policy=SolverPolicyV1(time_limit_seconds=0.000001),
    )

    result = run_two_stage_scenario_c_v1(context, solver)
    detailed = solver.last_detailed_run

    assert detailed is not None
    assert detailed.solver_run.solver_status == NativeSolverStatus.UNKNOWN
    assert not detailed.stage_1_result.plans
    assert detailed.diagnostics.stage_2_allocation_attempt_count == 0
    assert result.native_solver_status == NativeSolverStatus.UNKNOWN
    assert result.final_acceptance_state == FinalAcceptanceStateV1.NO_FINAL_C_WITHIN_SOLVE_BUDGET
    assert not any("bounded-plan exhaustion" in item for item in result.explanations)


def test_v3_thresholds_bind_problem_solution_and_artifact_identities() -> None:
    _, _, normalized, evaluation, evaluation_policy = _stage1_request()
    first_context, first_solver = build_two_stage_uniform_request_v1(
        normalized,
        evaluation,
        evaluation_policy=evaluation_policy,
        solver_policy=SolverPolicyV1(time_limit_seconds=2.0),
        uniform_regime_policy=UniformIntegerRegimePolicyV3(
            absolute_max_shift_per_trip_minutes=30,
        ),
    )
    second_context, _ = build_two_stage_uniform_request_v1(
        normalized,
        evaluation,
        evaluation_policy=evaluation_policy,
        solver_policy=SolverPolicyV1(time_limit_seconds=2.0),
        uniform_regime_policy=UniformIntegerRegimePolicyV3(
            absolute_max_shift_per_trip_minutes=29,
        ),
    )
    assert first_context.problem.problem_fingerprint != second_context.problem.problem_fingerprint
    problem_payload = schedule_problem_to_contract_dict(first_context.problem)
    assert problem_payload["scenario_c_optimization_mode"] == ("B_ANCHORED_TWO_STAGE_REBALANCE_V1")
    assert problem_payload["demand_allocation_authority_mode"] == (
        "DIRECTIONAL_DEMAND_FIXED_DIRECTION_COUNTS"
    )

    result = run_two_stage_scenario_c_v1(first_context, first_solver)
    assert result.candidate_outcome is not None
    assert result.candidate_outcome.solution is not None
    solution_payload = schedule_solution_to_contract_dict(result.candidate_outcome.solution)
    assert solution_payload["allocation_plan_fingerprint"] == (
        result.allocation_plan.allocation_fingerprint
    )
    assert solution_payload["uniform_regime_policy_profile"] == (
        "scenario_c_uniform_integer_regime_policy_v3"
    )


def test_selected_multi_period_profile_fingerprint_binds_v3_problem_identity() -> None:
    _, _, normalized, evaluation, evaluation_policy = _stage1_request()
    first_context, first_solver = build_two_stage_uniform_request_v1(
        normalized,
        evaluation,
        evaluation_policy=evaluation_policy,
        solver_policy=SolverPolicyV1(time_limit_seconds=2.0),
        demand_profile_fingerprint="a" * 64,
    )
    second_context, second_solver = build_two_stage_uniform_request_v1(
        normalized,
        evaluation,
        evaluation_policy=evaluation_policy,
        solver_policy=SolverPolicyV1(time_limit_seconds=2.0),
        demand_profile_fingerprint="b" * 64,
    )

    assert first_solver.demand_authority.demand_profile_fingerprint == "a" * 64
    assert second_solver.demand_authority.demand_profile_fingerprint == "b" * 64
    assert first_context.problem.problem_fingerprint != second_context.problem.problem_fingerprint


def test_final_tail_is_uniform_spread_and_locked_to_last_departure() -> None:
    problem, authority, *_ = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=1)
    stage_1 = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=policy,
        time_limit_seconds=2.0,
    )
    stage_2 = solve_exact_timetable_stage_2_v1(
        problem,
        stage_1.plans[0],
        policy=policy,
        time_limit_seconds=2.0,
    )
    assert stage_2.candidate is not None
    by_regime = {item.regime_id: item for item in stage_2.candidate.headway_regimes}
    for regime in stage_1.plans[0].proposed_regimes:
        if not regime.is_final_service_tail:
            continue
        actual = by_regime[regime.regime_id]
        locked_last = max(
            trip.departure_time
            for trip in problem.scenario_b.exact_timetable
            if trip.direction == regime.direction
        )
        assert actual.end_time == locked_last
        assert (actual.end_time - actual.start_time) // 60 >= 55
        assert len(set(actual.actual_headway_sequence)) <= 1


def test_final_service_sentinel_allows_locked_last_at_half_open_boundary() -> None:
    boundary = 18 * 60
    problem, authority, *_ = _stage1_request(
        outbound=(17 * 60, 17 * 60 + 30, boundary),
        inbound=(17 * 60, 17 * 60 + 30, boundary),
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 17 * 60, boundary, 80),
            _record(Direction.TERMINAL_2_TO_1, 17 * 60, boundary, 80),
        ),
    )
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=1)

    stage_1 = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=policy,
        time_limit_seconds=2.0,
    )

    assert stage_1.plans
    plan = stage_1.plans[0]
    assert {
        (item.direction, item.departure_minute, item.boundary_semantics)
        for item in plan.final_service_sentinels
    } == {
        (
            ContractDirection.OUTBOUND,
            boundary,
            ServiceBoundarySemanticsV1.FINAL_SERVICE_SENTINEL,
        ),
        (
            ContractDirection.INBOUND,
            boundary,
            ServiceBoundarySemanticsV1.FINAL_SERVICE_SENTINEL,
        ),
    }
    assert all(block.trip_count == 2 for block in plan.allocation_blocks)

    stage_2 = solve_exact_timetable_stage_2_v1(
        problem,
        plan,
        policy=policy,
        time_limit_seconds=2.0,
    )

    assert stage_2.candidate is not None
    candidate = stage_2.candidate
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        departures = sorted(
            trip.c_departure_time // 60
            for trip in candidate.exact_timetable
            if trip.direction == direction
        )
        assert departures == [17 * 60, 17 * 60 + 30, boundary]
        assert boundary not in range(17 * 60, boundary)
    for block in plan.allocation_blocks:
        actual_members = tuple(
            trip
            for trip in candidate.exact_timetable
            if block.start_minute * 60 <= trip.c_departure_time < block.end_minute * 60
            and (block.direction == ContractDirection.COMBINED or trip.direction == block.direction)
        )
        assert len(actual_members) == block.trip_count
        assert all(trip.c_departure_time != boundary * 60 for trip in actual_members)
    for regime in candidate.headway_regimes:
        assert regime.actual_headway_sequence == (30.0, 30.0)


def test_non_final_demand_boundaries_remain_half_open_with_final_sentinel() -> None:
    boundary = 18 * 60
    middle = 17 * 60 + 30
    problem, authority, *_ = _stage1_request(
        outbound=(17 * 60, middle, boundary),
        inbound=(17 * 60, middle, boundary),
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 17 * 60, middle, 40),
            _record(Direction.TERMINAL_1_TO_2, middle, boundary, 40),
            _record(Direction.TERMINAL_2_TO_1, 17 * 60, middle, 40),
            _record(Direction.TERMINAL_2_TO_1, middle, boundary, 40),
        ),
    )
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=2)
    stage_1 = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=policy,
        time_limit_seconds=2.0,
    )
    assert stage_1.plans
    stage_2 = solve_exact_timetable_stage_2_v1(
        problem,
        stage_1.plans[0],
        policy=policy,
        time_limit_seconds=2.0,
    )
    assert stage_2.candidate is not None

    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        blocks = sorted(
            (block for block in stage_1.plans[0].allocation_blocks if block.direction == direction),
            key=lambda item: item.start_minute,
        )
        departures = tuple(
            trip.c_departure_time // 60
            for trip in stage_2.candidate.exact_timetable
            if trip.direction == direction
        )
        assert (
            sum(blocks[0].start_minute <= item < blocks[0].end_minute for item in departures) == 1
        )
        assert (
            sum(blocks[1].start_minute <= item < blocks[1].end_minute for item in departures) == 1
        )
        assert middle not in range(blocks[0].start_minute, blocks[0].end_minute)
        assert middle in range(blocks[1].start_minute, blocks[1].end_minute)
        assert boundary not in range(blocks[1].start_minute, blocks[1].end_minute)


def test_non_minute_or_bunched_v3_tail_candidate_is_rejected() -> None:
    problem, authority, normalized, evaluation, evaluation_policy = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=1)
    stage_1 = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=policy,
        time_limit_seconds=2.0,
    )
    stage_2 = solve_exact_timetable_stage_2_v1(
        problem,
        stage_1.plans[0],
        policy=policy,
        time_limit_seconds=2.0,
    )
    assert stage_2.candidate is not None
    tail_ids = {
        regime.regime_id
        for regime in stage_1.plans[0].proposed_regimes
        if regime.is_final_service_tail
    }
    members = [
        trip for trip in stage_2.candidate.exact_timetable if trip.headway_regime_id in tail_ids
    ]
    target = sorted(members, key=lambda item: item.c_departure_time)[0]
    changed_trip = replace(
        target,
        c_departure_time=target.c_departure_time + 30,
        arrival_time=target.arrival_time + 30,
    )
    changed = replace(
        stage_2.candidate,
        exact_timetable=tuple(
            changed_trip if trip.c_trip_id == target.c_trip_id else trip
            for trip in stage_2.candidate.exact_timetable
        ),
    )
    context = build_schedule_generation_context_v1(
        problem,
        normalized,
        evaluation,
        evaluation_policy,
    )

    validation = validate_and_build_solution_v1(
        context,
        changed,
        allocation_plan=stage_1.plans[0],
        uniform_regime_policy=policy,
    )

    assert not validation.passed
    assert "V3_DEPARTURE_NOT_WHOLE_MINUTE" in validation.rejection_codes

    bunched_trip = replace(
        target,
        c_departure_time=target.c_departure_time + 10 * 60,
        arrival_time=target.arrival_time + 10 * 60,
    )
    bunched = replace(
        stage_2.candidate,
        exact_timetable=tuple(
            bunched_trip if trip.c_trip_id == target.c_trip_id else trip
            for trip in stage_2.candidate.exact_timetable
        ),
    )
    bunched_validation = validate_and_build_solution_v1(
        context,
        bunched,
        allocation_plan=stage_1.plans[0],
        uniform_regime_policy=policy,
    )
    assert "V3_WITHIN_REGIME_HEADWAY_NOT_EXACTLY_UNIFORM" in (bunched_validation.rejection_codes)
    assert "V3_FINAL_TAIL_AVOIDABLE_COMPRESSION" in bunched_validation.rejection_codes


def _solved_plan_with_tail_count(problem, authority, policy, tail_count):
    stage_1 = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=policy,
        time_limit_seconds=3.0,
    )
    for plan in stage_1.plans:
        if any(
            regime.is_final_service_tail and regime.trip_count != tail_count
            for regime in plan.proposed_regimes
        ):
            continue
        stage_2 = solve_exact_timetable_stage_2_v1(
            problem,
            plan,
            policy=policy,
            time_limit_seconds=2.0,
        )
        if stage_2.candidate is not None:
            return plan, stage_2.candidate
    pytest.fail("expected one bounded Stage 1 alternative to be Stage 2 feasible")


def test_tail_headway_can_be_longer_for_low_demand_and_shorter_for_strong_late_demand() -> None:
    outbound = (300, 315, 330, 345, 360, 390, 420)
    inbound = (305, 320, 335, 350, 365, 395, 425)
    (
        low_problem,
        low_authority,
        low_normalized,
        low_evaluation,
        low_evaluation_policy,
    ) = _stage1_request(
        outbound=outbound,
        inbound=inbound,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 300, 361, 204),
            _record(Direction.TERMINAL_1_TO_2, 361, 421, 20),
            _record(Direction.TERMINAL_2_TO_1, 305, 366, 204),
            _record(Direction.TERMINAL_2_TO_1, 366, 426, 20),
        ),
    )
    strong_problem, strong_authority, *_ = _stage1_request(
        outbound=outbound,
        inbound=inbound,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 300, 361, 153),
            _record(Direction.TERMINAL_1_TO_2, 361, 421, 204),
            _record(Direction.TERMINAL_2_TO_1, 305, 366, 153),
            _record(Direction.TERMINAL_2_TO_1, 366, 426, 204),
        ),
    )
    policy = UniformIntegerRegimePolicyV3(
        maximum_stage_1_alternative_plans=12,
        maximum_transition_jump_minutes=30,
    )
    low_plan, low_candidate = _solved_plan_with_tail_count(
        low_problem,
        low_authority,
        policy,
        3,
    )
    strong_plan, strong_candidate = _solved_plan_with_tail_count(
        strong_problem,
        strong_authority,
        policy,
        4,
    )

    def headways(plan, candidate, direction):
        raw = {item.regime_id: item for item in candidate.headway_regimes}
        regimes = sorted(
            (item for item in plan.proposed_regimes if item.direction == direction),
            key=lambda item: item.planned_start_minute,
        )
        return tuple(
            raw[item.regime_id].actual_headway_sequence[0]
            for item in regimes
            if raw[item.regime_id].actual_headway_sequence
        )

    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        low = headways(low_plan, low_candidate, direction)
        strong = headways(strong_plan, strong_candidate, direction)
        assert len(low) >= 2
        assert low[-1] > low[-2]
        assert strong[-1] < low[-1]
    low_context = build_schedule_generation_context_v1(
        low_problem,
        low_normalized,
        low_evaluation,
        low_evaluation_policy,
    )
    low_validation = validate_and_build_solution_v1(
        low_context,
        low_candidate,
        allocation_plan=low_plan,
        uniform_regime_policy=policy,
    )
    assert low_validation.passed, low_validation.rejection_codes


def test_protected_floors_are_not_stage_1_donors_or_stage_2_tail_overrides() -> None:
    from test_protected_service_floor_ortools_constraints import _authority as _protected_authority

    problem, demand_authority, *_ = _stage1_request()
    protected = _protected_authority(
        problem.scenario_b,
        outbound_indices=(0, 1),
        inbound_indices=(0, 1),
    )
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=2)
    stage_1 = allocate_trips_stage_1_v1(
        problem,
        demand_authority,
        policy=policy,
        protected_service_floor_enforcement_authority=protected,
        time_limit_seconds=2.0,
    )

    assert stage_1.plans
    assert all(
        block.trip_count >= block.protected_minimum_trip_count
        for block in stage_1.plans[0].allocation_blocks
    )
    stage_2 = solve_exact_timetable_stage_2_v1(
        problem,
        stage_1.plans[0],
        policy=policy,
        protected_service_floor_enforcement_authority=protected,
        time_limit_seconds=2.0,
    )
    assert stage_2.candidate is not None
    candidate_by_source = {
        trip.source_b_trip_id: trip for trip in stage_2.candidate.exact_timetable
    }
    for regime in protected.protected_regimes:
        departures = tuple(
            candidate_by_source[source_id].c_departure_time
            for source_id in regime.ordered_b_trip_ids
        )
        assert departures[0] == regime.protected_window_start
        assert departures[-1] == regime.protected_window_end
        assert all(
            later - earlier <= regime.maximum_future_c_headway_minutes * 60
            for earlier, later in zip(departures, departures[1:], strict=False)
        )
