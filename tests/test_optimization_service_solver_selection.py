from __future__ import annotations

import ast
import inspect
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_optimization_service import (
    _canonical_assessment,
    _fixture,
    _force_decision,
    _small_fixed_resource_fixture,
    _unknown_outcome,
)

import bus_schedule_engine
import bus_schedule_engine.optimization_comparison as comparison_module
import bus_schedule_engine.optimization_service as optimization_service
from bus_schedule_engine import (
    BusScheduleOptimizationResult,
    SolverChoice,
    SolverComparisonV1,
    analyze_and_optimize_schedule_v1,
)
from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.contracts_v1 import (
    SERVICE_QUALITY_OBJECTIVE_NAMES_V1,
    GenerationResultStatus,
    NativeSolverStatus,
    ScenarioBEvaluationPolicyV1,
    ServiceAdjustmentDecisionV1,
    SolverPolicyV1,
    build_ortools_service_quality_request_v1,
    recompute_service_quality_objective_vector_v1,
)
from bus_schedule_engine.optimization_comparison import compare_solver_outcomes_v1
from bus_schedule_engine.optimization_service import OptimizationAction


@pytest.fixture(scope="module")
def real_solver_case():
    imported, options = _small_fixed_resource_fixture(
        irregular_timetable=True,
        demand_profile=(170, 170),
    )
    heuristic = analyze_and_optimize_schedule_v1(imported, options)
    ortools = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=SolverChoice.OR_TOOLS,
    )
    both = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=SolverChoice.BOTH,
    )
    repeated_both = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=SolverChoice.BOTH,
    )
    quality_context, quality_solver = build_ortools_service_quality_request_v1(
        both.normalized_inputs,
        both.b_evaluation,
        evaluation_policy=both.adjustment_context.b_evaluation_policy,
    )
    raw_quality_run = quality_solver.solve(quality_context.problem)
    return SimpleNamespace(
        imported=imported,
        options=options,
        heuristic=heuristic,
        ortools=ortools,
        both=both,
        repeated_both=repeated_both,
        quality_context=quality_context,
        raw_quality_run=raw_quality_run,
    )


def _forced_fixed_resource(monkeypatch: pytest.MonkeyPatch):
    imported, options = _fixture()
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    )
    return imported, options


def _nonaccepted(outcome, result_status, solver_status):
    return replace(
        outcome,
        result_status=result_status,
        solver_status=solver_status,
        solution=None,
    )


def _mock_comparison(recommended_solver: SolverChoice | None) -> SolverComparisonV1:
    return SolverComparisonV1(
        objective_names=SERVICE_QUALITY_OBJECTIVE_NAMES_V1,
        heuristic_vector=None,
        ortools_vector=None,
        recommended_solver=recommended_solver,
        reason_code="TEST_REASON",
        explanation="Transparent test comparison.",
    )


def test_default_solver_remains_heuristic_and_calls_no_ortools_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _forced_fixed_resource(monkeypatch)
    calls = {"heuristic": 0, "run": 0}
    outcome = _unknown_outcome()

    def heuristic_builder(*args, **kwargs):
        calls["heuristic"] += 1
        return object(), object()

    def forbidden_ortools_builder(*args, **kwargs):
        raise AssertionError("Default HEURISTIC must not construct an OR-Tools request")

    def runner(context, solver):
        calls["run"] += 1
        return outcome

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        heuristic_builder,
    )
    monkeypatch.setattr(
        optimization_service,
        "build_ortools_service_quality_request_v1",
        forbidden_ortools_builder,
    )
    monkeypatch.setattr(optimization_service, "run_schedule_solver_v1", runner)

    result = analyze_and_optimize_schedule_v1(imported, options)

    assert (
        inspect.signature(analyze_and_optimize_schedule_v1).parameters["solver_choice"].default
        == SolverChoice.HEURISTIC
    )
    assert calls == {"heuristic": 1, "run": 1}
    assert result.heuristic_outcome is outcome
    assert result.ortools_outcome is None
    assert result.comparison is None
    assert result.recommended_outcome is None


def test_ortools_calls_only_the_quality_builder_and_never_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _forced_fixed_resource(monkeypatch)
    outcome = replace(
        _unknown_outcome(),
        solver_adapter="ortools_cp_sat_quality_v1",
    )
    context = object()
    solver = object()
    calls: list[str] = []

    def forbidden_heuristic(*args, **kwargs):
        raise AssertionError("OR_TOOLS must not construct or fall back to heuristic")

    def quality_builder(*args, **kwargs):
        calls.append("quality_builder")
        return context, solver

    def runner(supplied_context, supplied_solver):
        calls.append("runner")
        assert (supplied_context, supplied_solver) == (context, solver)
        return outcome

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        forbidden_heuristic,
    )
    monkeypatch.setattr(
        optimization_service,
        "build_ortools_service_quality_request_v1",
        quality_builder,
    )
    monkeypatch.setattr(optimization_service, "run_schedule_solver_v1", runner)

    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=SolverChoice.OR_TOOLS,
        heuristic_config=object(),  # type: ignore[arg-type]
    )

    assert calls == ["quality_builder", "runner"]
    assert result.solver_attempted is True
    assert result.heuristic_outcome is None
    assert result.ortools_outcome is outcome
    assert result.comparison is None
    assert result.recommended_outcome is None


def test_ortools_quality_builder_failure_precedes_solver_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _forced_fixed_resource(monkeypatch)

    def failing_builder(*args, **kwargs):
        raise RuntimeError("quality builder failed")

    def forbidden_runner(*args, **kwargs):
        raise AssertionError("A failed builder must prevent solver invocation")

    monkeypatch.setattr(
        optimization_service,
        "build_ortools_service_quality_request_v1",
        failing_builder,
    )
    monkeypatch.setattr(optimization_service, "run_schedule_solver_v1", forbidden_runner)

    with pytest.raises(RuntimeError, match="quality builder failed"):
        analyze_and_optimize_schedule_v1(
            imported,
            options,
            solver_choice=SolverChoice.OR_TOOLS,
        )


def test_both_builds_both_requests_then_runs_in_stable_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _forced_fixed_resource(monkeypatch)
    evaluation_policy = ScenarioBEvaluationPolicyV1()
    solver_policy = SolverPolicyV1(
        time_limit_seconds=7,
        worker_count=2,
        random_seed=3,
    )
    heuristic_config = ScenarioCConfig(
        preferred_max_shift_per_trip_minutes=15,
        absolute_max_shift_per_trip_minutes=30,
    )
    heuristic_context = SimpleNamespace(problem=object())
    quality_problem = object()
    ortools_context = SimpleNamespace(problem=quality_problem)
    heuristic_solver = object()
    ortools_solver = object()
    heuristic_outcome = _unknown_outcome()
    ortools_outcome = replace(
        _unknown_outcome(),
        solver_adapter="ortools_cp_sat_quality_v1",
        outcome_fingerprint="a" * 64,
    )
    events: list[str] = []

    def heuristic_builder(*args, **kwargs):
        events.append("build_heuristic")
        assert args[5] is heuristic_config
        assert kwargs["evaluation_policy"] is evaluation_policy
        assert kwargs["solver_policy"] is solver_policy
        return heuristic_context, heuristic_solver

    def quality_builder(*args, **kwargs):
        events.append("build_ortools")
        assert len(args) == 2
        assert kwargs["evaluation_policy"] is evaluation_policy
        assert kwargs["solver_policy"] is solver_policy
        assert "heuristic_config" not in kwargs
        return ortools_context, ortools_solver

    def runner(context, solver):
        assert events[:2] == ["build_heuristic", "build_ortools"]
        if solver is heuristic_solver:
            events.append("run_heuristic")
            return heuristic_outcome
        assert solver is ortools_solver
        events.append("run_ortools")
        return ortools_outcome

    comparison = _mock_comparison(SolverChoice.HEURISTIC)

    def compare(problem, supplied_heuristic, supplied_ortools):
        events.append("compare")
        assert problem is quality_problem
        assert supplied_heuristic is heuristic_outcome
        assert supplied_ortools is ortools_outcome
        return comparison

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        heuristic_builder,
    )
    monkeypatch.setattr(
        optimization_service,
        "build_ortools_service_quality_request_v1",
        quality_builder,
    )
    monkeypatch.setattr(optimization_service, "run_schedule_solver_v1", runner)
    monkeypatch.setattr(optimization_service, "compare_solver_outcomes_v1", compare)

    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=SolverChoice.BOTH,
        evaluation_policy=evaluation_policy,
        heuristic_config=heuristic_config,
        solver_policy=solver_policy,
    )

    assert events == [
        "build_heuristic",
        "build_ortools",
        "run_heuristic",
        "run_ortools",
        "compare",
    ]
    assert result.heuristic_outcome is heuristic_outcome
    assert result.ortools_outcome is ortools_outcome
    assert result.comparison is comparison
    assert result.recommended_outcome is heuristic_outcome
    assert any("approximately two solver budgets" in item for item in result.limitations)


@pytest.mark.parametrize("failing_builder", ("heuristic", "ortools"))
def test_both_builder_failure_invokes_neither_solver(
    monkeypatch: pytest.MonkeyPatch,
    failing_builder: str,
) -> None:
    imported, options = _forced_fixed_resource(monkeypatch)
    events: list[str] = []

    def heuristic_builder(*args, **kwargs):
        events.append("build_heuristic")
        if failing_builder == "heuristic":
            raise RuntimeError("builder failed")
        return object(), object()

    def ortools_builder(*args, **kwargs):
        events.append("build_ortools")
        raise RuntimeError("builder failed")

    def forbidden_runner(*args, **kwargs):
        raise AssertionError("BOTH must construct both requests before either solve")

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        heuristic_builder,
    )
    monkeypatch.setattr(
        optimization_service,
        "build_ortools_service_quality_request_v1",
        ortools_builder,
    )
    monkeypatch.setattr(optimization_service, "run_schedule_solver_v1", forbidden_runner)

    with pytest.raises(RuntimeError, match="builder failed"):
        analyze_and_optimize_schedule_v1(
            imported,
            options,
            solver_choice=SolverChoice.BOTH,
        )

    assert events == (
        ["build_heuristic"]
        if failing_builder == "heuristic"
        else ["build_heuristic", "build_ortools"]
    )


@pytest.mark.parametrize("solver_choice", tuple(SolverChoice))
@pytest.mark.parametrize(
    ("demand_mode", "incomplete_directional"),
    (("combined", False), ("directional", True)),
)
def test_directional_authority_gate_prevents_every_builder_and_solver(
    monkeypatch: pytest.MonkeyPatch,
    solver_choice: SolverChoice,
    demand_mode: str,
    incomplete_directional: bool,
) -> None:
    imported, options = _fixture(
        demand_mode=demand_mode,
        incomplete_directional=incomplete_directional,
    )
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("Unsupported directional authority must stop before construction")

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        forbidden,
    )
    monkeypatch.setattr(
        optimization_service,
        "build_ortools_service_quality_request_v1",
        forbidden,
    )
    monkeypatch.setattr(optimization_service, "run_schedule_solver_v1", forbidden)

    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=solver_choice,
    )

    assert result.solver_attempted is False
    assert result.heuristic_outcome is None
    assert result.ortools_outcome is None
    assert result.comparison is None
    assert result.recommended_outcome is None
    assert any("directional solving is unavailable" in item for item in result.limitations)


@pytest.mark.parametrize("solver_choice", tuple(SolverChoice))
def test_no_solver_action_remains_solver_free_for_every_choice(
    monkeypatch: pytest.MonkeyPatch,
    solver_choice: SolverChoice,
) -> None:
    imported, options = _fixture()
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("NO_CHANGE must remain solver-free")

    monkeypatch.setattr(
        optimization_service,
        "build_heuristic_schedule_request_v1",
        forbidden,
    )
    monkeypatch.setattr(
        optimization_service,
        "build_ortools_service_quality_request_v1",
        forbidden,
    )
    monkeypatch.setattr(optimization_service, "run_schedule_solver_v1", forbidden)

    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=solver_choice,
    )

    assert result.selected_action == OptimizationAction.NO_CHANGE
    assert result.solver_attempted is False
    assert result.heuristic_outcome is None
    assert result.ortools_outcome is None
    assert result.comparison is None
    assert result.recommended_outcome is None


def test_service_source_uses_builder_without_direct_solver_or_legacy_comparator() -> None:
    source = Path(optimization_service.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "build_ortools_service_quality_request_v1" in source
    assert "OrToolsCpSatServiceQualitySolver" not in source
    assert "build_ortools_demand_optimization_request_v1" not in source
    assert "build_ortools_schedule_request_v1" not in source
    assert "score_scenario" not in source
    assert "run_analysis" not in source
    assert {"score_scenario", "run_analysis"}.isdisjoint(called_names)


def test_two_accepted_outcomes_use_one_fifteen_stage_authority(real_solver_case) -> None:
    both = real_solver_case.both

    assert both.comparison is not None
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    assert both.heuristic_outcome.solution is not None
    assert both.ortools_outcome.solution is not None
    assert both.comparison.objective_names == SERVICE_QUALITY_OBJECTIVE_NAMES_V1
    assert len(both.comparison.objective_names) == 15
    assert both.comparison.heuristic_vector == recompute_service_quality_objective_vector_v1(
        real_solver_case.quality_context.problem,
        both.heuristic_outcome.solution,
    )
    assert both.comparison.ortools_vector == recompute_service_quality_objective_vector_v1(
        real_solver_case.quality_context.problem,
        both.ortools_outcome.solution,
    )


@pytest.mark.parametrize(
    ("result_status", "solver_status"),
    (
        (
            GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR,
            NativeSolverStatus.FEASIBLE,
        ),
        (
            GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT,
            NativeSolverStatus.UNKNOWN,
        ),
        (
            GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS,
            NativeSolverStatus.INFEASIBLE,
        ),
        (
            GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,
            NativeSolverStatus.MODEL_INVALID,
        ),
    ),
)
def test_nonaccepted_outcomes_have_no_comparison_vector(
    real_solver_case,
    result_status,
    solver_status,
) -> None:
    both = real_solver_case.both
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    heuristic = _nonaccepted(both.heuristic_outcome, result_status, solver_status)
    comparison = compare_solver_outcomes_v1(
        real_solver_case.quality_context.problem,
        heuristic,
        both.ortools_outcome,
    )

    assert comparison.heuristic_vector is None
    assert comparison.ortools_vector is not None
    assert comparison.recommended_solver == SolverChoice.OR_TOOLS
    assert comparison.reason_code == "ONLY_ORTOOLS_ACCEPTED"


def test_only_heuristic_accepted_recommends_heuristic(real_solver_case) -> None:
    both = real_solver_case.both
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    ortools = _nonaccepted(
        both.ortools_outcome,
        GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT,
        NativeSolverStatus.UNKNOWN,
    )

    comparison = compare_solver_outcomes_v1(
        real_solver_case.quality_context.problem,
        both.heuristic_outcome,
        ortools,
    )

    assert comparison.heuristic_vector is not None
    assert comparison.ortools_vector is None
    assert comparison.recommended_solver == SolverChoice.HEURISTIC
    assert comparison.reason_code == "ONLY_HEURISTIC_ACCEPTED"


def test_neither_accepted_produces_no_recommendation(real_solver_case) -> None:
    both = real_solver_case.both
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    heuristic = _nonaccepted(
        both.heuristic_outcome,
        GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT,
        NativeSolverStatus.UNKNOWN,
    )
    ortools = _nonaccepted(
        both.ortools_outcome,
        GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS,
        NativeSolverStatus.INFEASIBLE,
    )

    comparison = compare_solver_outcomes_v1(
        real_solver_case.quality_context.problem,
        heuristic,
        ortools,
    )

    assert comparison.recommended_solver is None
    assert comparison.reason_code == "NO_ACCEPTED_SOLUTION"
    assert comparison.heuristic_vector is None
    assert comparison.ortools_vector is None


@pytest.mark.parametrize(
    ("heuristic_vector", "ortools_vector", "winner", "reason"),
    (
        (
            (0,) * 15,
            (0, 0, 1, *(0 for _ in range(12))),
            SolverChoice.HEURISTIC,
            "HEURISTIC_VECTOR_BETTER",
        ),
        (
            (0, 1, *(0 for _ in range(13))),
            (0,) * 15,
            SolverChoice.OR_TOOLS,
            "ORTOOLS_VECTOR_BETTER",
        ),
    ),
)
def test_lower_vector_wins_lexicographically(
    monkeypatch: pytest.MonkeyPatch,
    real_solver_case,
    heuristic_vector,
    ortools_vector,
    winner,
    reason,
) -> None:
    both = real_solver_case.both
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    assert both.heuristic_outcome.solution is not None
    assert both.ortools_outcome.solution is not None

    def recompute(problem, solution):
        if solution is both.heuristic_outcome.solution:
            return heuristic_vector
        assert solution is both.ortools_outcome.solution
        return ortools_vector

    monkeypatch.setattr(
        comparison_module,
        "recompute_service_quality_objective_vector_v1",
        recompute,
    )
    comparison = compare_solver_outcomes_v1(
        real_solver_case.quality_context.problem,
        both.heuristic_outcome,
        both.ortools_outcome,
    )

    assert comparison.recommended_solver == winner
    assert comparison.reason_code == reason


def test_first_differing_objective_is_disclosed(
    monkeypatch: pytest.MonkeyPatch,
    real_solver_case,
) -> None:
    both = real_solver_case.both
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    assert both.heuristic_outcome.solution is not None
    heuristic_vector = (0, 0, 2, *(0 for _ in range(12)))
    ortools_vector = (0, 0, 1, *(0 for _ in range(12)))

    monkeypatch.setattr(
        comparison_module,
        "recompute_service_quality_objective_vector_v1",
        lambda problem, solution: (
            heuristic_vector if solution is both.heuristic_outcome.solution else ortools_vector
        ),
    )
    comparison = compare_solver_outcomes_v1(
        real_solver_case.quality_context.problem,
        both.heuristic_outcome,
        both.ortools_outcome,
    )

    assert comparison.recommended_solver == SolverChoice.OR_TOOLS
    assert "total_critical_shortage_trips: heuristic=2, OR-Tools=1" in comparison.explanation


def test_equal_vector_ortools_optimal_wins_proof_tie(real_solver_case) -> None:
    comparison = real_solver_case.both.comparison

    assert comparison is not None
    assert comparison.heuristic_vector == comparison.ortools_vector
    assert comparison.recommended_solver == SolverChoice.OR_TOOLS
    assert comparison.reason_code == "EQUAL_VECTOR_ORTOOLS_PROVEN_OPTIMAL"


def test_equal_vector_ortools_feasible_preserves_heuristic_continuity(
    real_solver_case,
) -> None:
    both = real_solver_case.both
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    ortools = replace(
        both.ortools_outcome,
        solver_status=NativeSolverStatus.FEASIBLE,
        solution=replace(
            both.ortools_outcome.solution,
            solver_status=NativeSolverStatus.FEASIBLE,
        ),
    )

    comparison = compare_solver_outcomes_v1(
        real_solver_case.quality_context.problem,
        both.heuristic_outcome,
        ortools,
    )

    assert comparison.heuristic_vector == comparison.ortools_vector
    assert comparison.recommended_solver == SolverChoice.HEURISTIC
    assert comparison.reason_code == "EQUAL_VECTOR_HEURISTIC_CONTINUITY"


def test_better_ortools_feasible_vector_may_win_without_optimality_claim(
    monkeypatch: pytest.MonkeyPatch,
    real_solver_case,
) -> None:
    both = real_solver_case.both
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    ortools = replace(
        both.ortools_outcome,
        solver_status=NativeSolverStatus.FEASIBLE,
        solution=replace(
            both.ortools_outcome.solution,
            solver_status=NativeSolverStatus.FEASIBLE,
        ),
    )
    monkeypatch.setattr(
        comparison_module,
        "recompute_service_quality_objective_vector_v1",
        lambda problem, solution: (
            (1, *(0 for _ in range(14)))
            if solution is both.heuristic_outcome.solution
            else (0,) * 15
        ),
    )

    comparison = compare_solver_outcomes_v1(
        real_solver_case.quality_context.problem,
        both.heuristic_outcome,
        ortools,
    )

    assert comparison.recommended_solver == SolverChoice.OR_TOOLS
    assert comparison.reason_code == "ORTOOLS_VECTOR_BETTER"
    assert "global optimality was not proven" in comparison.explanation


def test_duration_and_fingerprints_never_change_equal_vector_tie(real_solver_case) -> None:
    both = real_solver_case.both
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    changed_heuristic = replace(
        both.heuristic_outcome,
        solve_duration_seconds=9999,
        outcome_fingerprint="1" * 64,
        solution=replace(
            both.heuristic_outcome.solution,
            solve_duration_seconds=8888,
            solution_fingerprint="2" * 64,
        ),
    )
    changed_ortools = replace(
        both.ortools_outcome,
        solve_duration_seconds=0,
        outcome_fingerprint="f" * 64,
        solution=replace(
            both.ortools_outcome.solution,
            solve_duration_seconds=0,
            solution_fingerprint="e" * 64,
        ),
    )

    comparison = compare_solver_outcomes_v1(
        real_solver_case.quality_context.problem,
        changed_heuristic,
        changed_ortools,
    )

    assert comparison.reason_code == "EQUAL_VECTOR_ORTOOLS_PROVEN_OPTIMAL"
    source = Path(comparison_module.__file__).read_text(encoding="utf-8")
    assert "solve_duration_seconds" not in source
    assert "candidate_fingerprint" not in source


def test_source_b_mismatch_fails_closed(real_solver_case) -> None:
    both = real_solver_case.both
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    mismatched = replace(
        both.heuristic_outcome,
        source_b_fingerprint="0" * 64,
    )

    with pytest.raises(ValueError, match="SOURCE_B_FINGERPRINT_MISMATCH"):
        compare_solver_outcomes_v1(
            real_solver_case.quality_context.problem,
            mismatched,
            both.ortools_outcome,
        )


def test_raw_candidate_and_accepted_solution_recompute_identically(real_solver_case) -> None:
    raw_run = real_solver_case.raw_quality_run
    outcome = real_solver_case.ortools.ortools_outcome
    assert raw_run.candidate is not None
    assert outcome is not None
    assert outcome.solution is not None

    raw_vector = recompute_service_quality_objective_vector_v1(
        real_solver_case.quality_context.problem,
        raw_run.candidate,
    )
    solution_vector = recompute_service_quality_objective_vector_v1(
        real_solver_case.quality_context.problem,
        outcome.solution,
    )

    assert raw_vector == solution_vector


def test_real_ortools_and_both_paths_return_validated_outcomes(real_solver_case) -> None:
    ortools = real_solver_case.ortools
    both = real_solver_case.both

    assert ortools.heuristic_outcome is None
    assert ortools.ortools_outcome is not None
    assert ortools.ortools_outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert ortools.ortools_outcome.solution is not None
    assert ortools.recommended_outcome is ortools.ortools_outcome
    assert both.heuristic_outcome is not None
    assert both.ortools_outcome is not None
    assert both.heuristic_outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert both.ortools_outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED


def test_repeated_real_both_runs_are_deterministic(real_solver_case) -> None:
    first = real_solver_case.both
    second = real_solver_case.repeated_both
    assert first.comparison is not None and second.comparison is not None
    assert first.heuristic_outcome is not None and second.heuristic_outcome is not None
    assert first.ortools_outcome is not None and second.ortools_outcome is not None

    assert first.comparison == second.comparison
    assert (
        first.heuristic_outcome.outcome_fingerprint == second.heuristic_outcome.outcome_fingerprint
    )
    assert first.ortools_outcome.outcome_fingerprint == second.ortools_outcome.outcome_fingerprint


def test_result_and_comparison_shapes_are_frozen_slotted_and_exported() -> None:
    assert BusScheduleOptimizationResult.__dataclass_params__.frozen is True
    assert "__slots__" in BusScheduleOptimizationResult.__dict__
    assert [field.name for field in fields(BusScheduleOptimizationResult)][-6:] == [
        "heuristic_outcome",
        "ortools_outcome",
        "comparison",
        "recommended_outcome",
        "explanations",
        "limitations",
    ]
    assert SolverComparisonV1.__dataclass_params__.frozen is True
    assert "__slots__" in SolverComparisonV1.__dict__
    assert [field.name for field in fields(SolverComparisonV1)] == [
        "objective_names",
        "heuristic_vector",
        "ortools_vector",
        "recommended_solver",
        "reason_code",
        "explanation",
    ]
    assert bus_schedule_engine.SolverComparisonV1 is SolverComparisonV1
    assert optimization_service.SolverComparisonV1 is SolverComparisonV1
