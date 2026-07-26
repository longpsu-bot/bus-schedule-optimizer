"""Pre-problem quantitative authority for Contract V1 service adjustment."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from .authoritative_evaluation import evaluate_authoritative_scenario_b_v1
from .evaluation import ScenarioBEvaluationBundleV1, ScenarioBEvaluationPolicyV1
from .evaluation_fingerprints import evaluation_fingerprint
from .models import (
    CONTRACT_VERSION,
    DemandConfidence,
    NormalizedInputBundleV1,
)
from .serialization import (
    canonical_sha256,
    observed_demand_fingerprint,
    scenario_fingerprint,
)
from .validation import (
    ContractValidationError,
    ContractValidationIssue,
    ContractValidationResult,
    ContractValidationSeverity,
    validate_normalized_bundle,
)

ADJUSTMENT_DECISION_POLICY_FINGERPRINT_PROFILE = (
    "contract_v1_d2a_service_adjustment_decision_policy"
)
ADJUSTMENT_EVALUATION_POLICY_FINGERPRINT_PROFILE = "contract_v1_d2a_scenario_b_evaluation_policy"
NORMALIZED_BUNDLE_FINGERPRINT_PROFILE = "contract_v1_d2a_normalized_bundle"
REPEATABILITY_EVIDENCE_FINGERPRINT_PROFILE = "contract_v1_d2a_repeatability_evidence"
ADJUSTMENT_EVALUATION_CONTEXT_FINGERPRINT_PROFILE = (
    "contract_v1_d2a_service_adjustment_evaluation_context"
)


@dataclass(frozen=True, slots=True)
class ServiceAdjustmentDecisionPolicyV1:
    planning_load_factor_ceiling: float = 0.85
    critical_load_factor_ceiling: float = 0.90
    low_load_review_threshold: float = 0.30
    minimum_authoritative_demand_confidence: DemandConfidence = DemandConfidence.MEDIUM
    headway_rounding_tolerance_minutes: int = 1
    required_regular_headway_rate: float = 1.0
    minimum_sustained_change_intervals: int = 2
    minimum_material_headway_change_minutes: int = 5
    minimum_material_service_rate_change_ratio: float = 0.15
    maximum_headway_regimes_per_direction: int = 6
    minimum_valid_observed_days_for_reduction: int = 3
    minimum_surplus_consistency_rate: float = 0.80
    minimum_residual_surplus_trips_for_reduction: int = 1
    minimum_service_trips_per_direction: int = 1
    maximum_joint_donor_search_states: int = 10_000
    maximum_joint_reduction_search_states: int = 10_000

    def __post_init__(self) -> None:
        for name, value in (
            ("planning_load_factor_ceiling", self.planning_load_factor_ceiling),
            ("critical_load_factor_ceiling", self.critical_load_factor_ceiling),
            ("low_load_review_threshold", self.low_load_review_threshold),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0 < float(value) <= 1
            ):
                raise ValueError(f"{name} must be finite and in (0, 1]")
        if self.planning_load_factor_ceiling > self.critical_load_factor_ceiling:
            raise ValueError("planning load-factor ceiling may not exceed the critical ceiling")
        if self.headway_rounding_tolerance_minutes < 0:
            raise ValueError("headway_rounding_tolerance_minutes must be non-negative")
        if not 0 <= self.required_regular_headway_rate <= 1:
            raise ValueError("required_regular_headway_rate must be in [0, 1]")
        if self.minimum_sustained_change_intervals < 1:
            raise ValueError("minimum_sustained_change_intervals must be positive")
        if self.minimum_material_headway_change_minutes < 0:
            raise ValueError("minimum_material_headway_change_minutes must be non-negative")
        if not 0 <= self.minimum_material_service_rate_change_ratio <= 1:
            raise ValueError("minimum material service-rate change must be in [0, 1]")
        if self.maximum_headway_regimes_per_direction < 1:
            raise ValueError("maximum_headway_regimes_per_direction must be positive")
        if self.minimum_valid_observed_days_for_reduction < 1:
            raise ValueError("minimum_valid_observed_days_for_reduction must be positive")
        if not 0 < self.minimum_surplus_consistency_rate <= 1:
            raise ValueError("minimum_surplus_consistency_rate must be in (0, 1]")
        if self.minimum_residual_surplus_trips_for_reduction < 1:
            raise ValueError("minimum_residual_surplus_trips_for_reduction must be positive")
        if self.minimum_service_trips_per_direction < 1:
            raise ValueError("minimum_service_trips_per_direction must be positive")
        if self.maximum_joint_donor_search_states < 1:
            raise ValueError("maximum_joint_donor_search_states must be positive")
        if self.maximum_joint_reduction_search_states < 1:
            raise ValueError("maximum_joint_reduction_search_states must be positive")


@dataclass(frozen=True, slots=True)
class RepeatabilityDayEvidenceV1:
    day_reference: str
    fully_supported: bool
    current_daily_trips: int
    required_daily_trips: int | None
    shortage_block_count: int
    no_service_with_demand_block_count: int
    critical_block_count: int
    authoritative_evidence_fingerprint: str
    warning_block_count: int = 0

    def __post_init__(self) -> None:
        if not self.day_reference.strip():
            raise ValueError("day_reference is required")
        if self.current_daily_trips < 0:
            raise ValueError("current_daily_trips must be non-negative")
        if self.required_daily_trips is not None and self.required_daily_trips < 0:
            raise ValueError("required_daily_trips must be non-negative when present")
        for name, value in (
            ("shortage_block_count", self.shortage_block_count),
            ("no_service_with_demand_block_count", self.no_service_with_demand_block_count),
            ("critical_block_count", self.critical_block_count),
            ("warning_block_count", self.warning_block_count),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.fully_supported and self.required_daily_trips is None:
            raise ValueError("fully supported days require required_daily_trips")
        if not self.authoritative_evidence_fingerprint.strip():
            raise ValueError("authoritative_evidence_fingerprint is required")

    @property
    def daily_surplus_trips(self) -> int:
        if self.required_daily_trips is None:
            return 0
        return max(0, self.current_daily_trips - self.required_daily_trips)

    @property
    def qualifies_as_surplus_day(self) -> bool:
        return bool(
            self.fully_supported
            and self.required_daily_trips is not None
            and self.required_daily_trips < self.current_daily_trips
            and self.shortage_block_count == 0
            and self.no_service_with_demand_block_count == 0
            and self.critical_block_count == 0
        )


@dataclass(frozen=True, slots=True)
class RepeatabilityEvidenceV1:
    days: tuple[RepeatabilityDayEvidenceV1, ...]
    configured_minimum_valid_day_count: int
    configured_minimum_surplus_consistency_rate: float
    representative_day_type_or_provenance: str

    def __post_init__(self) -> None:
        if not isinstance(self.days, tuple):
            raise ValueError("repeatability days must be an immutable tuple")
        if self.configured_minimum_valid_day_count < 1:
            raise ValueError("configured_minimum_valid_day_count must be positive")
        if not 0 < self.configured_minimum_surplus_consistency_rate <= 1:
            raise ValueError("configured minimum surplus consistency must be in (0, 1]")
        if not self.representative_day_type_or_provenance.strip():
            raise ValueError("representative day type or provenance is required")
        day_references = tuple(day.day_reference for day in self.days)
        if len(set(day_references)) != len(day_references):
            raise ValueError("repeatability days may not contain duplicate day references")
        if day_references != tuple(sorted(day_references)):
            raise ValueError("repeatability days must use deterministic day-reference order")

    @property
    def valid_days(self) -> tuple[RepeatabilityDayEvidenceV1, ...]:
        return tuple(
            day for day in self.days if day.fully_supported and day.required_daily_trips is not None
        )

    @property
    def valid_observed_day_count(self) -> int:
        return len(self.valid_days)

    @property
    def surplus_day_count(self) -> int:
        return sum(day.qualifies_as_surplus_day for day in self.valid_days)

    @property
    def surplus_consistency_rate(self) -> float:
        if not self.valid_observed_day_count:
            return 0.0
        return self.surplus_day_count / self.valid_observed_day_count

    @property
    def daily_required_trip_sequence(self) -> tuple[int, ...]:
        return tuple(
            day.required_daily_trips
            for day in self.valid_days
            if day.required_daily_trips is not None
        )

    @property
    def daily_surplus_sequence(self) -> tuple[int, ...]:
        return tuple(
            day.daily_surplus_trips if day.qualifies_as_surplus_day else 0
            for day in self.valid_days
        )


@dataclass(frozen=True, slots=True)
class ServiceAdjustmentEvaluationContextV1:
    normalized_inputs: NormalizedInputBundleV1
    b_evaluation: ScenarioBEvaluationBundleV1
    b_evaluation_policy: ScenarioBEvaluationPolicyV1
    decision_policy: ServiceAdjustmentDecisionPolicyV1
    repeatability_evidence: RepeatabilityEvidenceV1 | None
    normalized_bundle_fingerprint: str
    source_a_fingerprint: str | None
    source_b_fingerprint: str
    observed_demand_fingerprint: str | None
    b_evaluation_policy_fingerprint: str
    authoritative_b_evaluation_fingerprint: str
    adjustment_decision_policy_fingerprint: str
    repeatability_evidence_fingerprint: str | None
    context_fingerprint: str

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def service_adjustment_decision_policy_payload_v1(
    policy: ServiceAdjustmentDecisionPolicyV1,
) -> dict[str, object]:
    return {
        "fingerprint_profile": ADJUSTMENT_DECISION_POLICY_FINGERPRINT_PROFILE,
        "planning_load_factor_ceiling": policy.planning_load_factor_ceiling,
        "critical_load_factor_ceiling": policy.critical_load_factor_ceiling,
        "low_load_review_threshold": policy.low_load_review_threshold,
        "minimum_authoritative_demand_confidence": (
            policy.minimum_authoritative_demand_confidence.value
        ),
        "headway_rounding_tolerance_minutes": policy.headway_rounding_tolerance_minutes,
        "required_regular_headway_rate": policy.required_regular_headway_rate,
        "minimum_sustained_change_intervals": policy.minimum_sustained_change_intervals,
        "minimum_material_headway_change_minutes": (policy.minimum_material_headway_change_minutes),
        "minimum_material_service_rate_change_ratio": (
            policy.minimum_material_service_rate_change_ratio
        ),
        "maximum_headway_regimes_per_direction": (policy.maximum_headway_regimes_per_direction),
        "minimum_valid_observed_days_for_reduction": (
            policy.minimum_valid_observed_days_for_reduction
        ),
        "minimum_surplus_consistency_rate": policy.minimum_surplus_consistency_rate,
        "minimum_residual_surplus_trips_for_reduction": (
            policy.minimum_residual_surplus_trips_for_reduction
        ),
        "minimum_service_trips_per_direction": policy.minimum_service_trips_per_direction,
        "maximum_joint_donor_search_states": policy.maximum_joint_donor_search_states,
        "maximum_joint_reduction_search_states": (policy.maximum_joint_reduction_search_states),
    }


def calculate_service_adjustment_decision_policy_fingerprint_v1(
    policy: ServiceAdjustmentDecisionPolicyV1,
) -> str:
    return canonical_sha256(service_adjustment_decision_policy_payload_v1(policy))


def scenario_b_evaluation_policy_payload_v1(
    policy: ScenarioBEvaluationPolicyV1,
) -> dict[str, object]:
    return {
        "fingerprint_profile": ADJUSTMENT_EVALUATION_POLICY_FINGERPRINT_PROFILE,
        "policy": _jsonable(asdict(policy)),
    }


def calculate_scenario_b_evaluation_policy_fingerprint_v1(
    policy: ScenarioBEvaluationPolicyV1,
) -> str:
    return canonical_sha256(scenario_b_evaluation_policy_payload_v1(policy))


def _source_identity(source: Any | None) -> dict[str, str] | None:
    if source is None:
        return None
    return {
        "source_type": source.source_metadata.source_type.value,
        "source_id": source.source_metadata.source_id,
    }


def normalized_bundle_fingerprint_payload_v1(
    bundle: NormalizedInputBundleV1,
    *,
    source_a_fingerprint: str | None,
    source_b_fingerprint: str,
    observed_demand_fingerprint_value: str | None,
) -> dict[str, object]:
    return {
        "fingerprint_profile": NORMALIZED_BUNDLE_FINGERPRINT_PROFILE,
        "contract_version": bundle.scenario_b.contract_version,
        "source_a_fingerprint": source_a_fingerprint,
        "source_b_fingerprint": source_b_fingerprint,
        "observed_demand_fingerprint": observed_demand_fingerprint_value,
        "scenario_a_source_identity": _source_identity(bundle.scenario_a),
        "scenario_b_source_identity": _source_identity(bundle.scenario_b),
        "observed_demand_source_identity": _source_identity(bundle.observed_demand),
    }


def calculate_normalized_bundle_fingerprint_v1(
    bundle: NormalizedInputBundleV1,
    *,
    source_a_fingerprint: str | None,
    source_b_fingerprint: str,
    observed_demand_fingerprint_value: str | None,
) -> str:
    return canonical_sha256(
        normalized_bundle_fingerprint_payload_v1(
            bundle,
            source_a_fingerprint=source_a_fingerprint,
            source_b_fingerprint=source_b_fingerprint,
            observed_demand_fingerprint_value=observed_demand_fingerprint_value,
        )
    )


def repeatability_evidence_payload_v1(
    evidence: RepeatabilityEvidenceV1,
) -> dict[str, object]:
    return {
        "fingerprint_profile": REPEATABILITY_EVIDENCE_FINGERPRINT_PROFILE,
        "evidence": _jsonable(asdict(evidence)),
    }


def calculate_repeatability_evidence_fingerprint_v1(
    evidence: RepeatabilityEvidenceV1 | None,
) -> str | None:
    if evidence is None:
        return None
    return canonical_sha256(repeatability_evidence_payload_v1(evidence))


def _context_fingerprint_payload(
    *,
    normalized_bundle_fingerprint: str,
    source_a_fingerprint: str | None,
    source_b_fingerprint: str,
    observed_demand_fingerprint_value: str | None,
    b_evaluation_policy_fingerprint: str,
    authoritative_b_evaluation_fingerprint: str,
    adjustment_decision_policy_fingerprint: str,
    repeatability_evidence_fingerprint: str | None,
) -> dict[str, object]:
    return {
        "fingerprint_profile": ADJUSTMENT_EVALUATION_CONTEXT_FINGERPRINT_PROFILE,
        "contract_version": CONTRACT_VERSION,
        "normalized_bundle_fingerprint": normalized_bundle_fingerprint,
        "source_a_fingerprint": source_a_fingerprint,
        "source_b_fingerprint": source_b_fingerprint,
        "observed_demand_fingerprint": observed_demand_fingerprint_value,
        "b_evaluation_policy_fingerprint": b_evaluation_policy_fingerprint,
        "authoritative_b_evaluation_fingerprint": (authoritative_b_evaluation_fingerprint),
        "adjustment_decision_policy_fingerprint": (adjustment_decision_policy_fingerprint),
        "repeatability_evidence_fingerprint": repeatability_evidence_fingerprint,
    }


def _issue(code: str, path: str, message: str) -> ContractValidationIssue:
    return ContractValidationIssue(code=code, path=path, message=message)


def _error_issues(result: ContractValidationResult) -> tuple[ContractValidationIssue, ...]:
    return tuple(
        issue for issue in result.issues if issue.severity == ContractValidationSeverity.ERROR
    )


def _recomputed_source_fingerprints(
    bundle: NormalizedInputBundleV1,
) -> tuple[str | None, str, str | None]:
    return (
        scenario_fingerprint(bundle.scenario_a) if bundle.scenario_a is not None else None,
        scenario_fingerprint(bundle.scenario_b),
        (
            observed_demand_fingerprint(bundle.observed_demand)
            if bundle.observed_demand is not None
            else None
        ),
    )


def _source_fingerprint_issues(
    bundle: NormalizedInputBundleV1,
    source_a: str | None,
    source_b: str,
    observed_demand: str | None,
) -> list[ContractValidationIssue]:
    issues: list[ContractValidationIssue] = []
    if bundle.scenario_a_fingerprint != source_a:
        issues.append(
            _issue(
                "ADJUSTMENT_CONTEXT_SOURCE_A_FINGERPRINT_MISMATCH",
                "normalized_inputs.scenario_a_fingerprint",
                "Stored Scenario A fingerprint does not match normalized Scenario A.",
            )
        )
    if bundle.scenario_b_fingerprint != source_b:
        issues.append(
            _issue(
                "ADJUSTMENT_CONTEXT_SOURCE_B_FINGERPRINT_MISMATCH",
                "normalized_inputs.scenario_b_fingerprint",
                "Stored Scenario B fingerprint does not match normalized Scenario B.",
            )
        )
    if bundle.observed_demand_fingerprint != observed_demand:
        issues.append(
            _issue(
                "ADJUSTMENT_CONTEXT_DEMAND_FINGERPRINT_MISMATCH",
                "normalized_inputs.observed_demand_fingerprint",
                "Stored observed-demand fingerprint does not match normalized demand.",
            )
        )
    return issues


def _decision_policy_authority_issues(
    decision_policy: ServiceAdjustmentDecisionPolicyV1,
    evaluation_policy: ScenarioBEvaluationPolicyV1,
) -> list[ContractValidationIssue]:
    mismatches = []
    if (
        decision_policy.planning_load_factor_ceiling
        != evaluation_policy.planning_load_factor_ceiling
    ):
        mismatches.append("planning_load_factor_ceiling")
    if (
        decision_policy.critical_load_factor_ceiling
        != evaluation_policy.critical_load_factor_ceiling
    ):
        mismatches.append("critical_load_factor_ceiling")
    if (
        decision_policy.minimum_authoritative_demand_confidence
        != evaluation_policy.minimum_authoritative_demand_confidence
    ):
        mismatches.append("minimum_authoritative_demand_confidence")
    if not mismatches:
        return []
    return [
        _issue(
            "ADJUSTMENT_DECISION_POLICY_EVALUATION_AUTHORITY_MISMATCH",
            "decision_policy",
            "Decision policy must match authoritative evaluation policy for: "
            + ", ".join(mismatches),
        )
    ]


def _decision_policy_type_issues(
    decision_policy: object,
) -> list[ContractValidationIssue]:
    if isinstance(decision_policy, ServiceAdjustmentDecisionPolicyV1):
        return []
    return [
        _issue(
            "ADJUSTMENT_CONTEXT_DECISION_POLICY_TYPE_INVALID",
            "decision_policy",
            "Decision policy must be ServiceAdjustmentDecisionPolicyV1.",
        )
    ]


def _raise_if_issues(issues: list[ContractValidationIssue]) -> None:
    if issues:
        raise ContractValidationError(tuple(issues))


def _build_service_adjustment_evaluation_context_core_v1(
    bundle: NormalizedInputBundleV1,
    evaluation_policy: ScenarioBEvaluationPolicyV1,
    decision_policy: ServiceAdjustmentDecisionPolicyV1,
    authoritative_b_evaluation: ScenarioBEvaluationBundleV1,
    repeatability_evidence: RepeatabilityEvidenceV1 | None = None,
    b_evaluation_cache: ScenarioBEvaluationBundleV1 | None = None,
) -> ServiceAdjustmentEvaluationContextV1:
    """Build a context after the public layer has recomputed authoritative B."""
    _raise_if_issues(_decision_policy_type_issues(decision_policy))
    validation = validate_normalized_bundle(bundle)
    _raise_if_issues(list(_error_issues(validation)))
    source_a, source_b, observed_demand = _recomputed_source_fingerprints(bundle)
    issues = _source_fingerprint_issues(
        bundle,
        source_a,
        source_b,
        observed_demand,
    )
    issues.extend(_decision_policy_authority_issues(decision_policy, evaluation_policy))

    authoritative_fingerprint = evaluation_fingerprint(
        bundle,
        authoritative_b_evaluation,
        evaluation_policy,
    )
    if b_evaluation_cache is not None:
        cache_fingerprint = evaluation_fingerprint(
            bundle,
            b_evaluation_cache,
            evaluation_policy,
        )
        if (
            b_evaluation_cache != authoritative_b_evaluation
            or cache_fingerprint != authoritative_fingerprint
        ):
            issues.append(
                _issue(
                    "ADJUSTMENT_CONTEXT_B_EVALUATION_CACHE_MISMATCH",
                    "b_evaluation_cache",
                    "Supplied Scenario B evaluation cache does not match current authority.",
                )
            )
    _raise_if_issues(issues)

    normalized_fingerprint = calculate_normalized_bundle_fingerprint_v1(
        bundle,
        source_a_fingerprint=source_a,
        source_b_fingerprint=source_b,
        observed_demand_fingerprint_value=observed_demand,
    )
    evaluation_policy_fingerprint = calculate_scenario_b_evaluation_policy_fingerprint_v1(
        evaluation_policy
    )
    decision_policy_fingerprint = calculate_service_adjustment_decision_policy_fingerprint_v1(
        decision_policy
    )
    repeatability_fingerprint = calculate_repeatability_evidence_fingerprint_v1(
        repeatability_evidence
    )
    context_fingerprint = canonical_sha256(
        _context_fingerprint_payload(
            normalized_bundle_fingerprint=normalized_fingerprint,
            source_a_fingerprint=source_a,
            source_b_fingerprint=source_b,
            observed_demand_fingerprint_value=observed_demand,
            b_evaluation_policy_fingerprint=evaluation_policy_fingerprint,
            authoritative_b_evaluation_fingerprint=authoritative_fingerprint,
            adjustment_decision_policy_fingerprint=decision_policy_fingerprint,
            repeatability_evidence_fingerprint=repeatability_fingerprint,
        )
    )
    return ServiceAdjustmentEvaluationContextV1(
        normalized_inputs=bundle,
        b_evaluation=authoritative_b_evaluation,
        b_evaluation_policy=evaluation_policy,
        decision_policy=decision_policy,
        repeatability_evidence=repeatability_evidence,
        normalized_bundle_fingerprint=normalized_fingerprint,
        source_a_fingerprint=source_a,
        source_b_fingerprint=source_b,
        observed_demand_fingerprint=observed_demand,
        b_evaluation_policy_fingerprint=evaluation_policy_fingerprint,
        authoritative_b_evaluation_fingerprint=authoritative_fingerprint,
        adjustment_decision_policy_fingerprint=decision_policy_fingerprint,
        repeatability_evidence_fingerprint=repeatability_fingerprint,
        context_fingerprint=context_fingerprint,
    )


def validate_service_adjustment_evaluation_context_v1(
    context: ServiceAdjustmentEvaluationContextV1,
) -> ContractValidationResult:
    """Recompute every authority and identity consumed by the evaluator."""
    if not isinstance(context, ServiceAdjustmentEvaluationContextV1):
        return ContractValidationResult(
            (
                _issue(
                    "ADJUSTMENT_EVALUATION_CONTEXT_TYPE_INVALID",
                    "context",
                    "Canonical evaluation requires ServiceAdjustmentEvaluationContextV1.",
                ),
            )
        )

    policy_type_issues = _decision_policy_type_issues(context.decision_policy)
    if policy_type_issues:
        return ContractValidationResult(tuple(policy_type_issues))

    validation = validate_normalized_bundle(context.normalized_inputs)
    issues = list(_error_issues(validation))
    source_a, source_b, observed_demand = _recomputed_source_fingerprints(context.normalized_inputs)
    issues.extend(
        _source_fingerprint_issues(
            context.normalized_inputs,
            source_a,
            source_b,
            observed_demand,
        )
    )
    issues.extend(
        _decision_policy_authority_issues(
            context.decision_policy,
            context.b_evaluation_policy,
        )
    )

    try:
        authoritative = evaluate_authoritative_scenario_b_v1(
            context.normalized_inputs,
            context.b_evaluation_policy,
        )
    except Exception:
        issues.append(
            _issue(
                "ADJUSTMENT_CONTEXT_AUTHORITATIVE_B_EVALUATION_INVALID",
                "b_evaluation",
                "The context cannot reproduce an authoritative Scenario B evaluation.",
            )
        )
        return ContractValidationResult(tuple(issues))

    authoritative_fingerprint = evaluation_fingerprint(
        context.normalized_inputs,
        authoritative,
        context.b_evaluation_policy,
    )
    supplied_fingerprint = evaluation_fingerprint(
        context.normalized_inputs,
        context.b_evaluation,
        context.b_evaluation_policy,
    )
    if context.b_evaluation != authoritative or supplied_fingerprint != authoritative_fingerprint:
        issues.append(
            _issue(
                "ADJUSTMENT_CONTEXT_AUTHORITATIVE_B_EVALUATION_MISMATCH",
                "b_evaluation",
                "Context Scenario B evaluation does not match current authority.",
            )
        )

    normalized_fingerprint = calculate_normalized_bundle_fingerprint_v1(
        context.normalized_inputs,
        source_a_fingerprint=source_a,
        source_b_fingerprint=source_b,
        observed_demand_fingerprint_value=observed_demand,
    )
    evaluation_policy_fingerprint = calculate_scenario_b_evaluation_policy_fingerprint_v1(
        context.b_evaluation_policy
    )
    decision_policy_fingerprint = calculate_service_adjustment_decision_policy_fingerprint_v1(
        context.decision_policy
    )
    repeatability_fingerprint = calculate_repeatability_evidence_fingerprint_v1(
        context.repeatability_evidence
    )

    declared_pairs = (
        (
            "ADJUSTMENT_CONTEXT_NORMALIZED_BUNDLE_FINGERPRINT_MISMATCH",
            "normalized_bundle_fingerprint",
            context.normalized_bundle_fingerprint,
            normalized_fingerprint,
        ),
        (
            "ADJUSTMENT_CONTEXT_SOURCE_A_IDENTITY_MISMATCH",
            "source_a_fingerprint",
            context.source_a_fingerprint,
            source_a,
        ),
        (
            "ADJUSTMENT_CONTEXT_SOURCE_B_IDENTITY_MISMATCH",
            "source_b_fingerprint",
            context.source_b_fingerprint,
            source_b,
        ),
        (
            "ADJUSTMENT_CONTEXT_DEMAND_IDENTITY_MISMATCH",
            "observed_demand_fingerprint",
            context.observed_demand_fingerprint,
            observed_demand,
        ),
        (
            "ADJUSTMENT_CONTEXT_B_EVALUATION_POLICY_FINGERPRINT_MISMATCH",
            "b_evaluation_policy_fingerprint",
            context.b_evaluation_policy_fingerprint,
            evaluation_policy_fingerprint,
        ),
        (
            "ADJUSTMENT_CONTEXT_AUTHORITATIVE_B_EVALUATION_FINGERPRINT_MISMATCH",
            "authoritative_b_evaluation_fingerprint",
            context.authoritative_b_evaluation_fingerprint,
            authoritative_fingerprint,
        ),
        (
            "ADJUSTMENT_CONTEXT_DECISION_POLICY_FINGERPRINT_MISMATCH",
            "adjustment_decision_policy_fingerprint",
            context.adjustment_decision_policy_fingerprint,
            decision_policy_fingerprint,
        ),
        (
            "ADJUSTMENT_CONTEXT_REPEATABILITY_FINGERPRINT_MISMATCH",
            "repeatability_evidence_fingerprint",
            context.repeatability_evidence_fingerprint,
            repeatability_fingerprint,
        ),
    )
    for code, path, declared, expected in declared_pairs:
        if declared != expected:
            issues.append(
                _issue(
                    code,
                    path,
                    f"Declared {path} does not match recomputed authority.",
                )
            )

    expected_context_fingerprint = canonical_sha256(
        _context_fingerprint_payload(
            normalized_bundle_fingerprint=normalized_fingerprint,
            source_a_fingerprint=source_a,
            source_b_fingerprint=source_b,
            observed_demand_fingerprint_value=observed_demand,
            b_evaluation_policy_fingerprint=evaluation_policy_fingerprint,
            authoritative_b_evaluation_fingerprint=authoritative_fingerprint,
            adjustment_decision_policy_fingerprint=decision_policy_fingerprint,
            repeatability_evidence_fingerprint=repeatability_fingerprint,
        )
    )
    if context.context_fingerprint != expected_context_fingerprint:
        issues.append(
            _issue(
                "ADJUSTMENT_EVALUATION_CONTEXT_FINGERPRINT_MISMATCH",
                "context_fingerprint",
                "Context fingerprint does not match recomputed pre-problem authority.",
            )
        )
    return ContractValidationResult(tuple(issues))


def ensure_valid_service_adjustment_evaluation_context_v1(
    context: ServiceAdjustmentEvaluationContextV1,
) -> None:
    validation = validate_service_adjustment_evaluation_context_v1(context)
    if not validation.passed:
        raise ContractValidationError(_error_issues(validation))


__all__ = [
    "ADJUSTMENT_DECISION_POLICY_FINGERPRINT_PROFILE",
    "ADJUSTMENT_EVALUATION_CONTEXT_FINGERPRINT_PROFILE",
    "ADJUSTMENT_EVALUATION_POLICY_FINGERPRINT_PROFILE",
    "NORMALIZED_BUNDLE_FINGERPRINT_PROFILE",
    "REPEATABILITY_EVIDENCE_FINGERPRINT_PROFILE",
    "RepeatabilityDayEvidenceV1",
    "RepeatabilityEvidenceV1",
    "ServiceAdjustmentDecisionPolicyV1",
    "ServiceAdjustmentEvaluationContextV1",
    "calculate_normalized_bundle_fingerprint_v1",
    "calculate_repeatability_evidence_fingerprint_v1",
    "calculate_scenario_b_evaluation_policy_fingerprint_v1",
    "calculate_service_adjustment_decision_policy_fingerprint_v1",
    "ensure_valid_service_adjustment_evaluation_context_v1",
    "normalized_bundle_fingerprint_payload_v1",
    "repeatability_evidence_payload_v1",
    "scenario_b_evaluation_policy_payload_v1",
    "service_adjustment_decision_policy_payload_v1",
    "validate_service_adjustment_evaluation_context_v1",
]
