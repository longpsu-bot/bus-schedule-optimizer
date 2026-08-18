from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_optimization_service import (  # noqa: E402
    _canonical_assessment,
    _fixture,
    _force_decision,
    _small_fixed_resource_fixture,
    _unknown_outcome,
)

import bus_schedule_engine.optimization_service as optimization_service  # noqa: E402
from bus_schedule_engine.contracts_v1 import (  # noqa: E402
    ScenarioBEvaluationPolicyV1,
    ServiceAdjustmentDecisionV1,
    SolverPolicyV1,
    build_ortools_service_quality_request_v1,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
)
from bus_schedule_engine.optimization_service import (  # noqa: E402
    DEFAULT_OR_TOOLS_TOTAL_TIME_LIMIT_SECONDS,
    SolverChoice,
    _effective_ortools_solver_policy,
    analyze_and_optimize_schedule_v1,
)


def _forced_fixed_resource(monkeypatch: pytest.MonkeyPatch):
    imported, options = _fixture()
    _force_decision(
        monkeypatch,
        _canonical_assessment(imported, options),
        ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS,
    )
    return imported, options


def test_default_ordinary_ortools_policy_is_finite() -> None:
    policy = _effective_ortools_solver_policy(None)

    assert policy.time_limit_seconds == DEFAULT_OR_TOOLS_TOTAL_TIME_LIMIT_SECONDS == 120.0
    assert policy.worker_count is None
    assert policy.random_seed is None
    assert policy.require_independent_validation is True


def test_missing_time_limit_is_filled_without_changing_other_controls() -> None:
    supplied = SolverPolicyV1(
        time_limit_seconds=None,
        worker_count=3,
        random_seed=9,
        require_independent_validation=False,
    )
    effective = _effective_ortools_solver_policy(supplied)

    assert effective is not supplied
    assert effective.time_limit_seconds == 120.0
    assert effective.worker_count == 3
    assert effective.random_seed == 9
    assert effective.require_independent_validation is False


def test_explicit_finite_time_limit_is_preserved_exactly() -> None:
    supplied = SolverPolicyV1(
        time_limit_seconds=7.5,
        worker_count=2,
        random_seed=4,
    )

    assert _effective_ortools_solver_policy(supplied) is supplied


def test_low_level_ortools_request_keeps_contract_none_default() -> None:
    imported, options = _small_fixed_resource_fixture(
        irregular_timetable=True,
        demand_profile=(170, 170),
    )
    normalized = normalize_imported_workbook_v1(imported, options)
    evaluation_policy = ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(normalized, evaluation_policy)
    context, _ = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        evaluation_policy=evaluation_policy,
        solver_policy=None,
    )

    assert context.problem.solver_policy.time_limit_seconds is None


def test_ordinary_ortools_execution_injects_default_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _forced_fixed_resource(monkeypatch)
    captured: list[SolverPolicyV1] = []
    outcome = _unknown_outcome()

    def quality_builder(*args, **kwargs):
        captured.append(kwargs["solver_policy"])
        return object(), object()

    monkeypatch.setattr(
        optimization_service,
        "build_ortools_service_quality_request_v1",
        quality_builder,
    )
    monkeypatch.setattr(
        optimization_service,
        "run_schedule_solver_v1",
        lambda context, solver: outcome,
    )

    analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=SolverChoice.OR_TOOLS,
    )

    assert len(captured) == 1
    assert captured[0].time_limit_seconds == 120.0


def test_both_bounds_only_ortools_when_no_policy_is_supplied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _forced_fixed_resource(monkeypatch)
    captured = {"heuristic": object(), "ortools": object()}
    outcome = _unknown_outcome()

    def heuristic_builder(*args, **kwargs):
        captured["heuristic"] = kwargs["solver_policy"]
        return object(), object()

    def quality_builder(*args, **kwargs):
        captured["ortools"] = kwargs["solver_policy"]
        return object(), object()

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
    monkeypatch.setattr(
        optimization_service,
        "run_schedule_solver_v1",
        lambda context, solver: outcome,
    )
    monkeypatch.setattr(
        optimization_service,
        "compare_solver_outcomes_v1",
        lambda *args, **kwargs: type(
            "Comparison",
            (),
            {
                "explanation": "Synthetic comparison.",
                "recommended_solver": None,
                "ortools_vector": None,
            },
        )(),
    )
    monkeypatch.setattr(
        optimization_service,
        "comparison_proof_limitations_v1",
        lambda *args, **kwargs: (),
    )

    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=SolverChoice.BOTH,
    )

    assert captured["heuristic"] is None
    assert isinstance(captured["ortools"], SolverPolicyV1)
    assert captured["ortools"].time_limit_seconds == 120.0
    assert any("120" in item and "OR-Tools" in item for item in result.limitations)


def test_explicit_finite_budget_reaches_ortools_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported, options = _forced_fixed_resource(monkeypatch)
    supplied = SolverPolicyV1(
        time_limit_seconds=11,
        worker_count=2,
        random_seed=5,
    )
    captured = []
    outcome = _unknown_outcome()

    def quality_builder(*args, **kwargs):
        captured.append(kwargs["solver_policy"])
        return object(), object()

    monkeypatch.setattr(
        optimization_service,
        "build_ortools_service_quality_request_v1",
        quality_builder,
    )
    monkeypatch.setattr(
        optimization_service,
        "run_schedule_solver_v1",
        lambda context, solver: outcome,
    )

    analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=SolverChoice.OR_TOOLS,
        solver_policy=supplied,
    )

    assert captured == [supplied]
