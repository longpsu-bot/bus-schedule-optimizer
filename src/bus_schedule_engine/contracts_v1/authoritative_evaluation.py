"""Neutral owner of the authoritative public Scenario B evaluation semantics."""

from __future__ import annotations

from dataclasses import replace

from .demand_coverage import demand_source_defects_v1
from .demand_resolution import (
    DemandBlockPolicyV1,
    DemandResolutionError,
    InterpolationMethod,
)
from .evaluation import (
    BDisposition,
    DimensionStatus,
    EvaluationIssueSeverity,
    ScenarioBEvaluationBundleV1,
    ScenarioBEvaluationPolicyV1,
)
from .evaluation import evaluate_scenario_b_v1 as _evaluate_scenario_b_v1
from .models import DemandResolutionType, NormalizedInputBundleV1, ObservedDemandInput


def validate_authoritative_demand_source_v1(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1,
) -> None:
    """Apply the public Contract V1 demand-source guards."""
    if policy.interpolation_method != InterpolationMethod.NONE:
        raise DemandResolutionError(
            "PR-02 authoritative evaluation supports interpolation_method=none only"
        )

    regular_resolutions = {
        observation.source_resolution_minutes
        for observation in demand.observations
        if observation.source_resolution_type == DemandResolutionType.REGULAR_INTERVAL
    }
    if regular_resolutions and (None in regular_resolutions or len(regular_resolutions) != 1):
        raise DemandResolutionError(
            "Regular-interval demand requires one explicit common source resolution"
        )

    defects = demand_source_defects_v1(demand.observations)
    if defects:
        first = defects[0]
        raise DemandResolutionError(first.message, code=first.code)


def evaluate_authoritative_scenario_b_v1(
    bundle: NormalizedInputBundleV1,
    policy: ScenarioBEvaluationPolicyV1,
) -> ScenarioBEvaluationBundleV1:
    """Evaluate B with the same guards and correction used by the public API."""
    if bundle.observed_demand is not None:
        validate_authoritative_demand_source_v1(
            bundle.observed_demand,
            policy.demand_blocks,
        )

    result = _evaluate_scenario_b_v1(bundle, policy)
    demand_dimension = result.evaluation.demand_suitability
    has_blocking_demand_issue = any(
        issue.severity
        in {
            EvaluationIssueSeverity.BLOCKING,
            EvaluationIssueSeverity.ERROR,
        }
        for issue in demand_dimension.issues
    )
    if not (
        has_blocking_demand_issue and demand_dimension.status == DimensionStatus.INSUFFICIENT_DATA
    ):
        return result

    corrected_dimension = replace(demand_dimension, status=DimensionStatus.FAIL)
    disposition = (
        BDisposition.TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION
        if not result.fleet_assessment.feasible
        else BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE
    )
    corrected_evaluation = replace(
        result.evaluation,
        demand_suitability=corrected_dimension,
        disposition=disposition,
    )
    return replace(result, evaluation=corrected_evaluation)


__all__ = [
    "evaluate_authoritative_scenario_b_v1",
    "validate_authoritative_demand_source_v1",
]
