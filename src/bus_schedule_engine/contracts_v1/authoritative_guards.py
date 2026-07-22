from __future__ import annotations

from dataclasses import replace

from .demand_resolution import (
    DemandBlockPolicyV1,
    DemandResolutionError,
    DemandResolutionResultV1,
    InterpolationMethod,
    build_demand_analysis_blocks_v1 as _build_demand_analysis_blocks_v1,
)
from .evaluation import (
    BDisposition,
    DimensionStatus,
    EvaluationIssueSeverity,
    ScenarioBEvaluationBundleV1,
    ScenarioBEvaluationPolicyV1,
    evaluate_scenario_b_v1 as _evaluate_scenario_b_v1,
)
from .models import (
    ContractDirection,
    DemandObservation,
    DemandResolutionType,
    NormalizedInputBundleV1,
    ObservedDemandInput,
)


def _validate_source_observations(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1,
) -> None:
    source_types = {
        observation.source_resolution_type for observation in demand.observations
    }
    if len(source_types) > 1:
        raise DemandResolutionError(
            "Mixed source resolutions require conservative pre-normalization "
            "into a separately identified comparison dataset"
        )
    if policy.interpolation_method != InterpolationMethod.NONE:
        raise DemandResolutionError(
            "PR-02 authoritative implementation supports interpolation_method=none only"
        )
    if source_types == {DemandResolutionType.REGULAR_INTERVAL}:
        resolution_values = {
            observation.source_resolution_minutes
            for observation in demand.observations
        }
        if None in resolution_values or len(resolution_values) != 1:
            raise DemandResolutionError(
                "Regular-interval demand requires one explicit common source resolution"
            )

    by_direction: dict[ContractDirection, list[DemandObservation]] = {}
    for observation in demand.observations:
        if observation.source_resolution_type == DemandResolutionType.DAILY_TOTAL:
            continue
        by_direction.setdefault(observation.direction, []).append(observation)

    for direction, observations in by_direction.items():
        ordered = sorted(
            observations,
            key=lambda item: (
                item.interval_start,
                item.interval_end,
                item.observation_id,
            ),
        )
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current.interval_start < previous.interval_end:
                raise DemandResolutionError(
                    "Overlapping demand observations are not authoritative within "
                    f"direction {direction.value}: {previous.observation_id}, "
                    f"{current.observation_id}"
                )


def build_demand_analysis_blocks_v1(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1 | None = None,
) -> DemandResolutionResultV1:
    effective_policy = policy or DemandBlockPolicyV1()
    _validate_source_observations(demand, effective_policy)
    return _build_demand_analysis_blocks_v1(demand, effective_policy)


def evaluate_scenario_b_v1(
    bundle: NormalizedInputBundleV1,
    policy: ScenarioBEvaluationPolicyV1 | None = None,
) -> ScenarioBEvaluationBundleV1:
    effective_policy = policy or ScenarioBEvaluationPolicyV1()
    if bundle.observed_demand is not None:
        _validate_source_observations(
            bundle.observed_demand,
            effective_policy.demand_blocks,
        )

    result = _evaluate_scenario_b_v1(bundle, effective_policy)
    demand_dimension = result.evaluation.demand_suitability
    has_error = any(
        issue.severity
        in {
            EvaluationIssueSeverity.BLOCKING,
            EvaluationIssueSeverity.ERROR,
        }
        for issue in demand_dimension.issues
    )
    if not has_error or demand_dimension.status == DimensionStatus.FAIL:
        return result

    corrected_dimension = replace(
        demand_dimension,
        status=DimensionStatus.FAIL,
        explanation=(
            demand_dimension.explanation
            + " A proven no-service or critical condition takes precedence over "
            "other insufficient-data blocks."
        ),
    )
    disposition = result.evaluation.disposition
    if result.fleet_assessment.feasible:
        disposition = BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE
    corrected_evaluation = replace(
        result.evaluation,
        demand_suitability=corrected_dimension,
        disposition=disposition,
    )
    return replace(result, evaluation=corrected_evaluation)
