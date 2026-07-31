"""Public additive facade for the Contract V1 solver boundary; no runtime cutover."""

from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.models import (
    DemandRecord,
    ProtectedServiceFloorEnforcementAuthorityV1,
    ScenarioParameters,
    Trip,
)

from .evaluation import (
    ScenarioBEvaluationBundleV1,
    ScenarioBEvaluationPolicyV1,
)
from .heuristic_context import (
    HeuristicCompatibilityContextError,
    HeuristicCompatibilityContextV1,
    build_heuristic_compatibility_context_v1,
)
from .heuristic_solver import HeuristicScheduleSolverAdapter
from .models import NormalizedInputBundleV1
from .solver_models import ScheduleGenerationContextV1, SolverPolicyV1
from .solver_orchestration import run_schedule_solver_v1
from .solver_problem import (
    ScheduleProblemError,
    build_schedule_generation_context_v1,
    build_schedule_problem_v1,
)
from .solver_validation import validate_and_build_solution_v1


def build_heuristic_schedule_request_v1(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    legacy_parameters: ScenarioParameters,
    legacy_trips_b: list[Trip] | tuple[Trip, ...],
    legacy_demand: list[DemandRecord] | tuple[DemandRecord, ...],
    heuristic_config: ScenarioCConfig,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    solver_policy: SolverPolicyV1 | None = None,
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None,
) -> tuple[ScheduleGenerationContextV1, HeuristicScheduleSolverAdapter]:
    if solver_policy is not None and any(
        value is not None
        for value in (
            solver_policy.time_limit_seconds,
            solver_policy.worker_count,
            solver_policy.random_seed,
        )
    ):
        raise ScheduleProblemError(
            "The legacy heuristic adapter does not implement generic solver resource controls.",
            code="PROBLEM_POLICY_INVALID",
        )
    try:
        compatibility_context = build_heuristic_compatibility_context_v1(
            normalized_inputs,
            legacy_parameters,
            legacy_trips_b,
            legacy_demand,
            heuristic_config,
        )
    except HeuristicCompatibilityContextError as exc:
        raise ScheduleProblemError(
            str(exc),
            code=exc.code,
        ) from exc
    problem = build_schedule_problem_v1(
        normalized_inputs,
        b_evaluation,
        solver_adapter=HeuristicScheduleSolverAdapter.adapter_id,
        adapter_context_fingerprint=(compatibility_context.context_fingerprint),
        evaluation_policy=evaluation_policy,
        solver_policy=solver_policy,
        adapter_operating_lock_values={
            "heuristic_turnaround_bridge_mode": (compatibility_context.turnaround_bridge_mode),
            "heuristic_turnaround_bridge_value_minutes": (
                compatibility_context.turnaround_bridge_value_minutes
            ),
        },
    )
    generation_context = build_schedule_generation_context_v1(
        problem,
        normalized_inputs,
        b_evaluation,
        evaluation_policy,
        protected_service_floor_enforcement_authority,
    )
    return (
        generation_context,
        HeuristicScheduleSolverAdapter(compatibility_context),
    )


__all__ = [
    "HeuristicCompatibilityContextV1",
    "HeuristicScheduleSolverAdapter",
    "ScheduleProblemError",
    "build_heuristic_compatibility_context_v1",
    "build_heuristic_schedule_request_v1",
    "build_schedule_generation_context_v1",
    "build_schedule_problem_v1",
    "run_schedule_solver_v1",
    "validate_and_build_solution_v1",
]
