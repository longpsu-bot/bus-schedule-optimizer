"""Unified application service for Contract V1 bus-schedule optimization."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from .c_config import ScenarioCConfig
from .contracts_v1 import (
    GenerationResultStatus,
    NormalizationOptions,
    NormalizedInputBundleV1,
    RepeatabilityEvidenceV1,
    ScenarioBEvaluationBundleV1,
    ScenarioBEvaluationPolicyV1,
    ScheduleGenerationOutcomeV1,
    ServiceAdjustmentAssessmentV1,
    ServiceAdjustmentDecisionPolicyV1,
    ServiceAdjustmentDecisionV1,
    ServiceAdjustmentEvaluationContextV1,
    SolverPolicyV1,
    build_heuristic_schedule_request_v1,
    build_ortools_service_quality_request_v1,
    build_service_adjustment_evaluation_context_v1,
    evaluate_scenario_b_v1,
    evaluate_service_adjustment_need_v1,
    normalize_imported_workbook_v1,
    run_schedule_solver_v1,
)
from .importer import ImportedWorkbook
from .models import ProtectedServiceFloorEnforcementAuthorityV1
from .optimization_comparison import (
    SolverComparisonV1,
    compare_solver_outcomes_v1,
    comparison_proof_limitations_v1,
)

DEFAULT_OR_TOOLS_TOTAL_TIME_LIMIT_SECONDS = 120.0


class OptimizationAction(StrEnum):
    NO_CHANGE = "NO_CHANGE"
    FIXED_RESOURCE_REDISTRIBUTION = "FIXED_RESOURCE_REDISTRIBUTION"
    FIXED_RESOURCE_RESPACE = "FIXED_RESOURCE_RESPACE"
    TRIP_INCREASE_RECOMMENDED = "TRIP_INCREASE_RECOMMENDED"
    TRIP_REDUCTION_RECOMMENDED = "TRIP_REDUCTION_RECOMMENDED"
    TECHNICAL_CORRECTION_REQUIRED = "TECHNICAL_CORRECTION_REQUIRED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class SolverChoice(StrEnum):
    HEURISTIC = "HEURISTIC"
    OR_TOOLS = "OR_TOOLS"
    BOTH = "BOTH"


class OptimizationExecutionStageV1(StrEnum):
    """Stable application-visible stages for unexpected execution failures."""

    NORMALIZATION = "NORMALIZATION"
    EVALUATION = "EVALUATION"
    HEURISTIC_SOLVER = "HEURISTIC_SOLVER"
    OR_TOOLS_SOLVER = "OR_TOOLS_SOLVER"
    SOLVER_COMPARISON = "SOLVER_COMPARISON"
    PRESENTATION = "PRESENTATION"
    ARTIFACTS = "ARTIFACTS"


class OptimizationExecutionErrorV1(RuntimeError):
    """Wrap an unexpected exception without changing completed outcome semantics."""

    def __init__(self, stage: OptimizationExecutionStageV1, exc: Exception) -> None:
        self.stage = stage
        self.original_exception_type = exc.__class__.__name__
        message = " ".join(str(exc).split()) or self.original_exception_type
        super().__init__(f"{stage.value}: {message}")


@dataclass(frozen=True, slots=True)
class BusScheduleOptimizationResult:
    normalized_inputs: NormalizedInputBundleV1
    b_evaluation: ScenarioBEvaluationBundleV1
    adjustment_context: ServiceAdjustmentEvaluationContextV1
    adjustment_assessment: ServiceAdjustmentAssessmentV1
    selected_action: OptimizationAction
    solver_choice: SolverChoice
    solver_attempted: bool
    heuristic_outcome: ScheduleGenerationOutcomeV1 | None
    ortools_outcome: ScheduleGenerationOutcomeV1 | None
    comparison: SolverComparisonV1 | None
    recommended_outcome: ScheduleGenerationOutcomeV1 | None
    explanations: tuple[str, ...]
    limitations: tuple[str, ...]
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None
    protected_service_floor_enforcement_failure_code: str | None = None


_ACTION_BY_DECISION = {
    ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA: OptimizationAction.INSUFFICIENT_DATA,
    ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED: (
        OptimizationAction.TECHNICAL_CORRECTION_REQUIRED
    ),
    ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS: (
        OptimizationAction.TRIP_INCREASE_RECOMMENDED
    ),
    ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS: (
        OptimizationAction.FIXED_RESOURCE_REDISTRIBUTION
    ),
    ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS: (OptimizationAction.TRIP_REDUCTION_RECOMMENDED),
    ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES: (
        OptimizationAction.FIXED_RESOURCE_RESPACE
    ),
    ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE: OptimizationAction.NO_CHANGE,
}

_FIXED_RESOURCE_ACTIONS = {
    OptimizationAction.FIXED_RESOURCE_REDISTRIBUTION,
    OptimizationAction.FIXED_RESOURCE_RESPACE,
}

_DIRECTIONAL_SOLVING_UNAVAILABLE = (
    "Authoritative directional solving is unavailable because H3 demand coverage "
    "does not fully support both directional streams."
)
_PROTECTED_AUTHORITY_FAILURE_LIMITATION = (
    "Protected-service-floor enforcement authority is invalid. Scenario B evaluation remains "
    "available, but Scenario C generation was blocked to prevent an unprotected fallback."
)


def select_optimization_action(
    assessment: ServiceAdjustmentAssessmentV1,
) -> OptimizationAction:
    """Map the canonical adjustment decision without considering solver availability."""
    return _ACTION_BY_DECISION[assessment.primary_decision]


def _validate_solver_choice(solver_choice: SolverChoice) -> None:
    if not isinstance(solver_choice, SolverChoice):
        raise TypeError("solver_choice must be a SolverChoice")


def _effective_ortools_solver_policy(
    solver_policy: SolverPolicyV1 | None,
) -> SolverPolicyV1:
    """Apply the ordinary-runtime OR budget without changing low-level Contract defaults."""
    if solver_policy is None:
        return SolverPolicyV1(
            time_limit_seconds=DEFAULT_OR_TOOLS_TOTAL_TIME_LIMIT_SECONDS,
        )
    if solver_policy.time_limit_seconds is not None:
        return solver_policy
    return replace(
        solver_policy,
        time_limit_seconds=DEFAULT_OR_TOOLS_TOTAL_TIME_LIMIT_SECONDS,
    )


def _both_solver_budget_limitation(ortools_policy: SolverPolicyV1) -> str:
    return (
        "BOTH may consume approximately two solver budgets when an explicit policy also bounds "
        "the heuristic; with the ordinary default, the heuristic keeps its existing bounded "
        f"search and OR-Tools receives one total staged budget of {ortools_policy.time_limit_seconds:g} "
        "seconds, plus application overhead."
    )


def _default_decision_policy(
    evaluation_policy: ScenarioBEvaluationPolicyV1,
) -> ServiceAdjustmentDecisionPolicyV1:
    return ServiceAdjustmentDecisionPolicyV1(
        planning_load_factor_ceiling=evaluation_policy.planning_load_factor_ceiling,
        critical_load_factor_ceiling=evaluation_policy.critical_load_factor_ceiling,
        low_load_review_threshold=evaluation_policy.low_load_review_threshold,
        minimum_authoritative_demand_confidence=(
            evaluation_policy.minimum_authoritative_demand_confidence
        ),
    )


def _directional_generation_supported(
    evaluation: ScenarioBEvaluationBundleV1,
) -> bool:
    resolution = evaluation.demand_resolution
    return bool(
        resolution is not None
        and resolution.coverage_assessment is not None
        and resolution.coverage_assessment.directional_c_generation_supported
    )


def _deduplicate(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _accepted_outcome(
    outcome: ScheduleGenerationOutcomeV1,
) -> ScheduleGenerationOutcomeV1 | None:
    if (
        outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
        and outcome.solution is not None
    ):
        return outcome
    return None


def _run_stage(stage: OptimizationExecutionStageV1, operation):
    try:
        return operation()
    except OptimizationExecutionErrorV1:
        raise
    except Exception as exc:
        raise OptimizationExecutionErrorV1(stage, exc) from exc


def _result(
    *,
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    adjustment_context: ServiceAdjustmentEvaluationContextV1,
    adjustment_assessment: ServiceAdjustmentAssessmentV1,
    selected_action: OptimizationAction,
    solver_choice: SolverChoice,
    solver_attempted: bool,
    heuristic_outcome: ScheduleGenerationOutcomeV1 | None,
    ortools_outcome: ScheduleGenerationOutcomeV1 | None,
    comparison: SolverComparisonV1 | None,
    recommended_outcome: ScheduleGenerationOutcomeV1 | None,
    extra_limitations: tuple[str, ...] = (),
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None,
    protected_service_floor_enforcement_failure_code: str | None = None,
) -> BusScheduleOptimizationResult:
    heuristic_explanations = heuristic_outcome.explanations if heuristic_outcome is not None else ()
    ortools_explanations = ortools_outcome.explanations if ortools_outcome is not None else ()
    comparison_explanations = (comparison.explanation,) if comparison is not None else ()
    heuristic_limitations = heuristic_outcome.limitations if heuristic_outcome is not None else ()
    ortools_limitations = ortools_outcome.limitations if ortools_outcome is not None else ()
    return BusScheduleOptimizationResult(
        normalized_inputs=normalized_inputs,
        b_evaluation=b_evaluation,
        adjustment_context=adjustment_context,
        adjustment_assessment=adjustment_assessment,
        selected_action=selected_action,
        solver_choice=solver_choice,
        solver_attempted=solver_attempted,
        heuristic_outcome=heuristic_outcome,
        ortools_outcome=ortools_outcome,
        comparison=comparison,
        recommended_outcome=recommended_outcome,
        explanations=_deduplicate(
            (
                adjustment_assessment.explanation,
                *heuristic_explanations,
                *ortools_explanations,
                *comparison_explanations,
            )
        ),
        limitations=_deduplicate(
            (
                *adjustment_assessment.limitations,
                *heuristic_limitations,
                *ortools_limitations,
                *extra_limitations,
            )
        ),
        protected_service_floor_enforcement_authority=(
            protected_service_floor_enforcement_authority
        ),
        protected_service_floor_enforcement_failure_code=(
            protected_service_floor_enforcement_failure_code
        ),
    )


def analyze_and_optimize_schedule_v1(
    imported: ImportedWorkbook,
    normalization_options: NormalizationOptions,
    *,
    solver_choice: SolverChoice = SolverChoice.HEURISTIC,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    decision_policy: ServiceAdjustmentDecisionPolicyV1 | None = None,
    repeatability_evidence: RepeatabilityEvidenceV1 | None = None,
    heuristic_config: ScenarioCConfig | None = None,
    solver_policy: SolverPolicyV1 | None = None,
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None,
    protected_service_floor_enforcement_failure_code: str | None = None,
) -> BusScheduleOptimizationResult:
    """Normalize, assess, and conditionally run the selected canonical solver boundary."""
    _validate_solver_choice(solver_choice)
    normalized_inputs = _run_stage(
        OptimizationExecutionStageV1.NORMALIZATION,
        lambda: normalize_imported_workbook_v1(imported, normalization_options),
    )
    return _analyze_normalized_and_optimize_schedule_v1(
        imported,
        normalized_inputs,
        solver_choice=solver_choice,
        evaluation_policy=evaluation_policy,
        decision_policy=decision_policy,
        repeatability_evidence=repeatability_evidence,
        heuristic_config=heuristic_config,
        solver_policy=solver_policy,
        protected_service_floor_enforcement_authority=(
            protected_service_floor_enforcement_authority
        ),
        protected_service_floor_enforcement_failure_code=(
            protected_service_floor_enforcement_failure_code
        ),
    )


def _analyze_normalized_and_optimize_schedule_v1(
    imported: ImportedWorkbook,
    normalized_inputs: NormalizedInputBundleV1,
    *,
    solver_choice: SolverChoice = SolverChoice.HEURISTIC,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    decision_policy: ServiceAdjustmentDecisionPolicyV1 | None = None,
    repeatability_evidence: RepeatabilityEvidenceV1 | None = None,
    heuristic_config: ScenarioCConfig | None = None,
    solver_policy: SolverPolicyV1 | None = None,
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None,
    protected_service_floor_enforcement_failure_code: str | None = None,
) -> BusScheduleOptimizationResult:
    """Assess and optimize an already normalized, verified Contract V1 bundle."""
    _validate_solver_choice(solver_choice)
    effective_evaluation_policy = evaluation_policy or ScenarioBEvaluationPolicyV1()

    def evaluate():
        b_evaluation = evaluate_scenario_b_v1(
            normalized_inputs,
            effective_evaluation_policy,
        )
        effective_decision_policy = decision_policy or _default_decision_policy(
            effective_evaluation_policy
        )
        adjustment_context = build_service_adjustment_evaluation_context_v1(
            normalized_inputs,
            effective_evaluation_policy,
            effective_decision_policy,
            repeatability_evidence,
            b_evaluation,
        )
        adjustment_assessment = evaluate_service_adjustment_need_v1(adjustment_context)
        selected_action = select_optimization_action(adjustment_assessment)
        return b_evaluation, adjustment_context, adjustment_assessment, selected_action

    (
        b_evaluation,
        adjustment_context,
        adjustment_assessment,
        selected_action,
    ) = _run_stage(
        OptimizationExecutionStageV1.EVALUATION,
        evaluate,
    )

    result_arguments = {
        "normalized_inputs": normalized_inputs,
        "b_evaluation": b_evaluation,
        "adjustment_context": adjustment_context,
        "adjustment_assessment": adjustment_assessment,
        "selected_action": selected_action,
        "solver_choice": solver_choice,
        "protected_service_floor_enforcement_authority": (
            protected_service_floor_enforcement_authority
        ),
        "protected_service_floor_enforcement_failure_code": (
            protected_service_floor_enforcement_failure_code
        ),
    }
    if protected_service_floor_enforcement_failure_code is not None:
        return _result(
            **result_arguments,
            solver_attempted=False,
            heuristic_outcome=None,
            ortools_outcome=None,
            comparison=None,
            recommended_outcome=None,
            extra_limitations=(
                f"{protected_service_floor_enforcement_failure_code}: "
                f"{_PROTECTED_AUTHORITY_FAILURE_LIMITATION}",
            ),
        )
    if selected_action not in _FIXED_RESOURCE_ACTIONS:
        return _result(
            **result_arguments,
            solver_attempted=False,
            heuristic_outcome=None,
            ortools_outcome=None,
            comparison=None,
            recommended_outcome=None,
        )

    if not _directional_generation_supported(b_evaluation):
        return _result(
            **result_arguments,
            solver_attempted=False,
            heuristic_outcome=None,
            ortools_outcome=None,
            comparison=None,
            recommended_outcome=None,
            extra_limitations=(_DIRECTIONAL_SOLVING_UNAVAILABLE,),
        )

    attached_enforcement_authority = (
        protected_service_floor_enforcement_authority
        if protected_service_floor_enforcement_authority is not None
        and protected_service_floor_enforcement_authority.has_enforceable_regimes
        else None
    )
    enforcement_request_arguments = (
        {"protected_service_floor_enforcement_authority": (attached_enforcement_authority)}
        if attached_enforcement_authority is not None
        else {}
    )

    if solver_choice == SolverChoice.HEURISTIC:

        def run_heuristic():
            effective_heuristic_config = heuristic_config or ScenarioCConfig.from_mapping(
                imported.configuration
            )
            heuristic_context, heuristic_solver = build_heuristic_schedule_request_v1(
                normalized_inputs,
                b_evaluation,
                imported.parameters_b,
                imported.trips_b,
                imported.demand,
                effective_heuristic_config,
                evaluation_policy=effective_evaluation_policy,
                solver_policy=solver_policy,
                **enforcement_request_arguments,
            )
            return run_schedule_solver_v1(
                heuristic_context,
                heuristic_solver,
            )

        heuristic_outcome = _run_stage(
            OptimizationExecutionStageV1.HEURISTIC_SOLVER,
            run_heuristic,
        )
        return _result(
            **result_arguments,
            solver_attempted=True,
            heuristic_outcome=heuristic_outcome,
            ortools_outcome=None,
            comparison=None,
            recommended_outcome=_accepted_outcome(heuristic_outcome),
        )

    effective_ortools_policy = _effective_ortools_solver_policy(solver_policy)

    if solver_choice == SolverChoice.OR_TOOLS:

        def run_ortools():
            ortools_context, ortools_solver = build_ortools_service_quality_request_v1(
                normalized_inputs,
                b_evaluation,
                evaluation_policy=effective_evaluation_policy,
                solver_policy=effective_ortools_policy,
                **enforcement_request_arguments,
            )
            return run_schedule_solver_v1(
                ortools_context,
                ortools_solver,
            )

        ortools_outcome = _run_stage(
            OptimizationExecutionStageV1.OR_TOOLS_SOLVER,
            run_ortools,
        )
        return _result(
            **result_arguments,
            solver_attempted=True,
            heuristic_outcome=None,
            ortools_outcome=ortools_outcome,
            comparison=None,
            recommended_outcome=_accepted_outcome(ortools_outcome),
        )

    heuristic_context, heuristic_solver = _run_stage(
        OptimizationExecutionStageV1.HEURISTIC_SOLVER,
        lambda: build_heuristic_schedule_request_v1(
            normalized_inputs,
            b_evaluation,
            imported.parameters_b,
            imported.trips_b,
            imported.demand,
            heuristic_config or ScenarioCConfig.from_mapping(imported.configuration),
            evaluation_policy=effective_evaluation_policy,
            solver_policy=solver_policy,
            **enforcement_request_arguments,
        ),
    )
    ortools_context, ortools_solver = _run_stage(
        OptimizationExecutionStageV1.OR_TOOLS_SOLVER,
        lambda: build_ortools_service_quality_request_v1(
            normalized_inputs,
            b_evaluation,
            evaluation_policy=effective_evaluation_policy,
            solver_policy=effective_ortools_policy,
            **enforcement_request_arguments,
        ),
    )
    heuristic_outcome = _run_stage(
        OptimizationExecutionStageV1.HEURISTIC_SOLVER,
        lambda: run_schedule_solver_v1(
            heuristic_context,
            heuristic_solver,
        ),
    )
    ortools_outcome = _run_stage(
        OptimizationExecutionStageV1.OR_TOOLS_SOLVER,
        lambda: run_schedule_solver_v1(
            ortools_context,
            ortools_solver,
        ),
    )
    exact_demand_authority = getattr(
        ortools_solver,
        "exact_demand_authority",
        None,
    )

    def compare():
        return (
            compare_solver_outcomes_v1(
                ortools_context.problem,
                heuristic_outcome,
                ortools_outcome,
                exact_demand_authority=exact_demand_authority,
            )
            if exact_demand_authority is not None
            else compare_solver_outcomes_v1(
                ortools_context.problem,
                heuristic_outcome,
                ortools_outcome,
            )
        )

    comparison = _run_stage(
        OptimizationExecutionStageV1.SOLVER_COMPARISON,
        compare,
    )
    recommended_outcome = {
        SolverChoice.HEURISTIC: heuristic_outcome,
        SolverChoice.OR_TOOLS: ortools_outcome,
        None: None,
    }[comparison.recommended_solver]
    return _result(
        **result_arguments,
        solver_attempted=True,
        heuristic_outcome=heuristic_outcome,
        ortools_outcome=ortools_outcome,
        comparison=comparison,
        recommended_outcome=recommended_outcome,
        extra_limitations=(
            _both_solver_budget_limitation(effective_ortools_policy),
            *comparison_proof_limitations_v1(comparison, ortools_outcome),
        ),
    )


__all__ = [
    "DEFAULT_OR_TOOLS_TOTAL_TIME_LIMIT_SECONDS",
    "BusScheduleOptimizationResult",
    "OptimizationAction",
    "OptimizationExecutionErrorV1",
    "OptimizationExecutionStageV1",
    "SolverComparisonV1",
    "SolverChoice",
    "analyze_and_optimize_schedule_v1",
    "select_optimization_action",
]
