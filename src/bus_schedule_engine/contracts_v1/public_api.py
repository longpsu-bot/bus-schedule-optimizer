"""Authoritative public guards for PR-02 demand resolution and B evaluation."""

from __future__ import annotations

from .adjustment_context import (
    RepeatabilityEvidenceV1,
    ServiceAdjustmentDecisionPolicyV1,
    ServiceAdjustmentEvaluationContextV1,
    _build_service_adjustment_evaluation_context_core_v1,
)
from .adjustment_routing import (
    AdjustmentCapabilityRoutingPolicyV1,
    AdjustmentCapabilityRoutingV1,
    AdjustmentCapabilityV1,
    FixedResourceAuthorizationProfileV1,
)
from .adjustment_routing import (
    build_adjustment_capability_routing_policy_v1 as _build_adjustment_capability_routing_policy_v1,
)
from .adjustment_routing import (
    build_current_fixed_resource_authorization_profile_v1 as _build_current_fixed_resource_authorization_profile_v1,
)
from .adjustment_routing import (
    route_adjustment_capability_v1 as _route_adjustment_capability_v1,
)
from .authoritative_evaluation import (
    evaluate_authoritative_scenario_b_v1,
    validate_authoritative_demand_source_v1,
)
from .demand_resolution import (
    DemandBlockPolicyV1,
    DemandResolutionContractV1,
    DemandResolutionResultV1,
)
from .demand_resolution import (
    build_demand_analysis_blocks_v1 as _build_demand_analysis_blocks_v1,
)
from .demand_resolution import (
    detect_demand_resolution_v1 as _detect_demand_resolution_v1,
)
from .evaluation import (
    ScenarioBEvaluationBundleV1,
    ScenarioBEvaluationPolicyV1,
)
from .models import (
    NormalizedInputBundleV1,
    ObservedDemandInput,
)
from .service_adjustment import (
    HEURISTIC_ADAPTER_ID,
    ServiceAdjustmentAssessmentV1,
    ServiceAdjustmentPolicyV1,
)
from .service_adjustment import (
    evaluate_service_adjustment_need_v1 as _evaluate_service_adjustment_need_v1,
)
from .solver_models import ScheduleGenerationContextV1
from .validation import (
    ContractValidationError,
    ensure_valid_bundle,
)


def _validate_authoritative_demand_source(
    demand: ObservedDemandInput,
    policy: DemandBlockPolicyV1,
) -> None:
    validate_authoritative_demand_source_v1(demand, policy)


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
    return evaluate_authoritative_scenario_b_v1(bundle, effective_policy)


def project_service_adjustment_decision_policy_v1(
    legacy_policy: ServiceAdjustmentPolicyV1,
) -> ServiceAdjustmentDecisionPolicyV1:
    """Project only quantitative authority from the temporary legacy policy."""
    return ServiceAdjustmentDecisionPolicyV1(
        planning_load_factor_ceiling=legacy_policy.planning_load_factor_ceiling,
        critical_load_factor_ceiling=legacy_policy.critical_load_factor_ceiling,
        low_load_review_threshold=legacy_policy.low_load_review_threshold,
        minimum_authoritative_demand_confidence=(
            legacy_policy.minimum_authoritative_demand_confidence
        ),
        headway_rounding_tolerance_minutes=(legacy_policy.headway_rounding_tolerance_minutes),
        required_regular_headway_rate=legacy_policy.required_regular_headway_rate,
        minimum_sustained_change_intervals=(legacy_policy.minimum_sustained_change_intervals),
        minimum_material_headway_change_minutes=(
            legacy_policy.minimum_material_headway_change_minutes
        ),
        minimum_material_service_rate_change_ratio=(
            legacy_policy.minimum_material_service_rate_change_ratio
        ),
        maximum_headway_regimes_per_direction=(legacy_policy.maximum_headway_regimes_per_direction),
        minimum_valid_observed_days_for_reduction=(
            legacy_policy.minimum_valid_observed_days_for_reduction
        ),
        minimum_surplus_consistency_rate=(legacy_policy.minimum_surplus_consistency_rate),
        minimum_residual_surplus_trips_for_reduction=(
            legacy_policy.minimum_residual_surplus_trips_for_reduction
        ),
        minimum_service_trips_per_direction=(legacy_policy.minimum_service_trips_per_direction),
        maximum_joint_donor_search_states=(legacy_policy.maximum_joint_donor_search_states),
        maximum_joint_reduction_search_states=(legacy_policy.maximum_joint_reduction_search_states),
    )


def build_service_adjustment_evaluation_context_v1(
    bundle: NormalizedInputBundleV1,
    evaluation_policy: ScenarioBEvaluationPolicyV1,
    decision_policy: ServiceAdjustmentDecisionPolicyV1,
    repeatability_evidence: RepeatabilityEvidenceV1 | None = None,
    b_evaluation_cache: ScenarioBEvaluationBundleV1 | None = None,
) -> ServiceAdjustmentEvaluationContextV1:
    """Build the canonical pre-problem quantitative authority."""
    ensure_valid_bundle(bundle)
    authoritative = evaluate_authoritative_scenario_b_v1(
        bundle,
        evaluation_policy,
    )
    return _build_service_adjustment_evaluation_context_core_v1(
        bundle,
        evaluation_policy,
        decision_policy,
        authoritative,
        repeatability_evidence,
        b_evaluation_cache,
    )


def evaluate_service_adjustment_need_v1(
    context: ServiceAdjustmentEvaluationContextV1,
) -> ServiceAdjustmentAssessmentV1:
    """Return the canonical problem-free quantitative assessment."""
    return _evaluate_service_adjustment_need_v1(context)


def build_current_fixed_resource_authorization_profile_v1() -> FixedResourceAuthorizationProfileV1:
    """Return the exact currently supported fixed-resource lock profile."""
    return _build_current_fixed_resource_authorization_profile_v1()


def build_adjustment_capability_routing_policy_v1(
    configured_capabilities: tuple[AdjustmentCapabilityV1, ...] = (
        AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION,
        AdjustmentCapabilityV1.FIXED_RESOURCE_DEPARTURE_RESPACE,
    ),
    *,
    solver_adapter_id: str = HEURISTIC_ADAPTER_ID,
    available_adapter_ids: tuple[str, ...] = (HEURISTIC_ADAPTER_ID,),
    fixed_resource_profile: FixedResourceAuthorizationProfileV1 | None = None,
) -> AdjustmentCapabilityRoutingPolicyV1:
    """Build an immutable closed capability-routing policy."""
    return _build_adjustment_capability_routing_policy_v1(
        configured_capabilities,
        solver_adapter_id=solver_adapter_id,
        available_adapter_ids=available_adapter_ids,
        fixed_resource_profile=fixed_resource_profile,
    )


def route_adjustment_capability_v1(
    assessment: ServiceAdjustmentAssessmentV1,
    authoritative_context: ServiceAdjustmentEvaluationContextV1,
    routing_policy: AdjustmentCapabilityRoutingPolicyV1,
) -> AdjustmentCapabilityRoutingV1:
    """Route a validated canonical assessment without constructing a problem."""
    return _route_adjustment_capability_v1(
        assessment,
        authoritative_context,
        routing_policy,
    )


def _effective_legacy_service_adjustment_policy_v1(
    requested: ServiceAdjustmentPolicyV1 | None,
    evaluation_policy: ScenarioBEvaluationPolicyV1,
) -> ServiceAdjustmentPolicyV1:
    if requested is not None:
        return requested
    return ServiceAdjustmentPolicyV1(
        planning_load_factor_ceiling=evaluation_policy.planning_load_factor_ceiling,
        critical_load_factor_ceiling=evaluation_policy.critical_load_factor_ceiling,
        low_load_review_threshold=evaluation_policy.low_load_review_threshold,
        minimum_authoritative_demand_confidence=(
            evaluation_policy.minimum_authoritative_demand_confidence
        ),
    )


def evaluate_service_adjustment_need_from_generation_context_v1(
    context: ScheduleGenerationContextV1,
    policy: ServiceAdjustmentPolicyV1 | None = None,
    repeatability_evidence: RepeatabilityEvidenceV1 | None = None,
) -> ServiceAdjustmentAssessmentV1:
    """Transitional compatibility path from the old H4 generation context."""
    from .problem_validation import validate_schedule_generation_context_v1

    validation = validate_schedule_generation_context_v1(context)
    if not validation.passed:
        raise ContractValidationError(validation.issues)
    effective_legacy_policy = _effective_legacy_service_adjustment_policy_v1(
        policy,
        context.evaluation_policy,
    )
    decision_policy = project_service_adjustment_decision_policy_v1(effective_legacy_policy)
    evaluation_context = build_service_adjustment_evaluation_context_v1(
        context.normalized_inputs,
        context.evaluation_policy,
        decision_policy,
        repeatability_evidence,
        context.b_evaluation,
    )
    return evaluate_service_adjustment_need_v1(evaluation_context)
