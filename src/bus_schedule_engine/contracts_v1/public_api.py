"""Authoritative public guards for PR-02 demand resolution and B evaluation."""

from __future__ import annotations

from dataclasses import replace

from .demand_coverage import demand_source_defects_v1
from .demand_resolution import (
    DemandBlockPolicyV1,
    DemandResolutionContractV1,
    DemandResolutionError,
    DemandResolutionResultV1,
    InterpolationMethod,
)
from .demand_resolution import (
    build_demand_analysis_blocks_v1 as _build_demand_analysis_blocks_v1,
)
from .demand_resolution import (
    detect_demand_resolution_v1 as _detect_demand_resolution_v1,
)
from .evaluation import (
    BDisposition,
    DimensionStatus,
    EvaluationIssueSeverity,
    ScenarioBEvaluationBundleV1,
    ScenarioBEvaluationPolicyV1,
)
from .evaluation import (
    evaluate_scenario_b_v1 as _evaluate_scenario_b_v1,
)
from .models import (
    DemandResolutionType,
    NormalizedInputBundleV1,
    ObservedDemandInput,
)


def _validate_authoritative_demand_source(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1,
) -> None:
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


def detect_demand_resolution_v1(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1 | None = None,
) -> DemandResolutionContractV1:
    effective_policy = policy or DemandBlockPolicyV1()
    _validate_authoritative_demand_source(demand, effective_policy)
    return _detect_demand_resolution_v1(demand, effective_policy)


def build_demand_analysis_blocks_v1(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1 | None = None,
) -> DemandResolutionResultV1:
    effective_policy = policy or DemandBlockPolicyV1()
    _validate_authoritative_demand_source(demand, effective_policy)
    return _build_demand_analysis_blocks_v1(demand, effective_policy)


def evaluate_scenario_b_v1(
    bundle: NormalizedInputBundleV1,
    policy: ScenarioBEvaluationPolicyV1 | None = None,
) -> ScenarioBEvaluationBundleV1:
    effective_policy = policy or ScenarioBEvaluationPolicyV1()
    if bundle.observed_demand is not None:
        _validate_authoritative_demand_source(
            bundle.observed_demand,
            effective_policy.demand_blocks,
        )

    result = _evaluate_scenario_b_v1(bundle, effective_policy)
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
