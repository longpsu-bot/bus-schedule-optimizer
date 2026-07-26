"""Pure Contract V1-D2 Phase B adjustment capability routing."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass, replace
from enum import Enum, StrEnum
from typing import Any

from .adjustment_context import (
    ServiceAdjustmentEvaluationContextV1,
    ensure_valid_service_adjustment_evaluation_context_v1,
)
from .models import CONTRACT_VERSION, ContractDirection
from .serialization import canonical_sha256
from .service_adjustment import (
    HEURISTIC_ADAPTER_ID,
    HeadwayRegularityClassificationV1,
    ServiceAdjustmentAssessmentV1,
    ServiceAdjustmentDecisionV1,
    ServiceAdjustmentPolicyV1,
    ensure_valid_service_adjustment_assessment_v1,
)
from .solver_models import (
    BoundaryConvention,
    DirectionTripLockMode,
    FleetConstraintMode,
    InitialFleetPositioningMode,
)
from .validation import (
    ContractValidationError,
    ContractValidationIssue,
    ContractValidationResult,
    ContractValidationSeverity,
)

FIXED_RESOURCE_PROFILE_FINGERPRINT_PROFILE = "contract_v1_d2b_fixed_resource_authorization_profile"
ROUTING_POLICY_FINGERPRINT_PROFILE = "contract_v1_d2b_adjustment_capability_routing_policy"
ROUTING_FINGERPRINT_PROFILE = "contract_v1_d2b_adjustment_capability_routing"
LEGACY_ASSESSMENT_PROJECTION_FINGERPRINT_PROFILE = (
    "contract_v1_d2b_legacy_service_adjustment_assessment_projection"
)

FIXED_RESOURCE_TRIP_REDISTRIBUTION_ACTION = "fixed_resource_trip_redistribution"
FIXED_RESOURCE_DEPARTURE_RESPACE_ACTION = "fixed_resource_departure_respace"

ADJUSTMENT_CAPABILITY_NOT_AUTHORIZED_INSUFFICIENT_DATA = (
    "ADJUSTMENT_CAPABILITY_NOT_AUTHORIZED_INSUFFICIENT_DATA"
)
TECHNICAL_PARAMETER_CHANGE_REQUIRED = "TECHNICAL_PARAMETER_CHANGE_REQUIRED"
VARIABLE_TRIP_INCREASE_CAPABILITY_REQUIRED = "VARIABLE_TRIP_INCREASE_CAPABILITY_REQUIRED"
VARIABLE_TRIP_REDUCTION_CAPABILITY_REQUIRED = "VARIABLE_TRIP_REDUCTION_CAPABILITY_REQUIRED"
CURRENT_SOLVER_CAN_IMPLEMENT = "CURRENT_SOLVER_CAN_IMPLEMENT"
CURRENT_SOLVER_CAPABILITY_INSUFFICIENT = "CURRENT_SOLVER_CAPABILITY_INSUFFICIENT"
NO_GENERATION_REQUIRED = "NO_GENERATION_REQUIRED"


class AdjustmentCapabilityV1(StrEnum):
    NO_GENERATION_REQUIRED = "NO_GENERATION_REQUIRED"
    FIXED_RESOURCE_TRIP_REDISTRIBUTION = "FIXED_RESOURCE_TRIP_REDISTRIBUTION"
    FIXED_RESOURCE_DEPARTURE_RESPACE = "FIXED_RESOURCE_DEPARTURE_RESPACE"
    VARIABLE_TRIP_INCREASE_REQUIRED = "VARIABLE_TRIP_INCREASE_REQUIRED"
    VARIABLE_TRIP_REDUCTION_REQUIRED = "VARIABLE_TRIP_REDUCTION_REQUIRED"
    TECHNICAL_PARAMETER_CHANGE_REQUIRED = "TECHNICAL_PARAMETER_CHANGE_REQUIRED"
    NOT_AUTHORIZED_INSUFFICIENT_DATA = "NOT_AUTHORIZED_INSUFFICIENT_DATA"


@dataclass(frozen=True, slots=True)
class FixedResourceAuthorizationProfileV1:
    direction_trip_lock_mode: DirectionTripLockMode
    fleet_constraint_mode: FleetConstraintMode
    initial_fleet_positioning_mode: InitialFleetPositioningMode
    boundary_convention: BoundaryConvention
    total_daily_trip_count_locked: bool
    directional_trip_counts_locked: bool
    first_departures_locked: bool
    last_departures_locked: bool
    source_trip_runtime_locked: bool
    arrival_terminal_turnaround_locked: bool
    vehicle_capacity_locked: bool
    available_fleet_limit_locked: bool
    operating_window_locked: bool
    minimum_service_locked: bool
    terminal_stock_must_remain_non_negative: bool
    profile_fingerprint: str

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class FixedResourceCapabilityBindingV1:
    capability: AdjustmentCapabilityV1
    generation_action: str
    solver_adapter_id: str
    adapter_available: bool
    supported_fixed_resource_profile: FixedResourceAuthorizationProfileV1
    supported_direction_trip_lock_mode: DirectionTripLockMode
    supported_fleet_constraint_mode: FleetConstraintMode
    supported_initial_fleet_positioning_mode: InitialFleetPositioningMode
    supported_boundary_convention: BoundaryConvention


@dataclass(frozen=True, slots=True)
class AdjustmentCapabilityRoutingPolicyV1:
    fixed_resource_bindings: tuple[FixedResourceCapabilityBindingV1, ...]
    routing_policy_fingerprint: str

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class AdjustmentCapabilityRoutingV1:
    routing_id: str
    source_evaluation_context_fingerprint: str
    source_assessment_fingerprint: str
    source_adjustment_decision_policy_fingerprint: str
    routing_policy_fingerprint: str
    primary_decision: ServiceAdjustmentDecisionV1
    routed_capability: AdjustmentCapabilityV1
    authorized_generation_action: str | None
    solver_adapter_id: str | None
    problem_construction_authorized: bool
    solver_invocation_authorized: bool
    required_fixed_resource_profile: FixedResourceAuthorizationProfileV1 | None
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]
    routing_fingerprint: str

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


@dataclass(frozen=True, slots=True)
class LegacyServiceAdjustmentAssessmentProjectionV1:
    canonical_assessment: ServiceAdjustmentAssessmentV1
    canonical_assessment_fingerprint: str
    legacy_source_problem_fingerprint: str | None
    legacy_heuristic_authorized: bool
    legacy_authorized_generation_action: str | None
    source_routing_fingerprint: str
    projection_fingerprint: str

    @property
    def contract_version(self) -> str:
        return CONTRACT_VERSION


_FIXED_CAPABILITY_ORDER = {
    AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION: 0,
    AdjustmentCapabilityV1.FIXED_RESOURCE_DEPARTURE_RESPACE: 1,
}
_FIXED_ACTIONS = {
    AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION: (
        FIXED_RESOURCE_TRIP_REDISTRIBUTION_ACTION
    ),
    AdjustmentCapabilityV1.FIXED_RESOURCE_DEPARTURE_RESPACE: (
        FIXED_RESOURCE_DEPARTURE_RESPACE_ACTION
    ),
}
_DECISION_CAPABILITIES = {
    ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA: (
        AdjustmentCapabilityV1.NOT_AUTHORIZED_INSUFFICIENT_DATA
    ),
    ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED: (
        AdjustmentCapabilityV1.TECHNICAL_PARAMETER_CHANGE_REQUIRED
    ),
    ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS: (
        AdjustmentCapabilityV1.VARIABLE_TRIP_INCREASE_REQUIRED
    ),
    ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS: (
        AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION
    ),
    ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS: (
        AdjustmentCapabilityV1.VARIABLE_TRIP_REDUCTION_REQUIRED
    ),
    ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES: (
        AdjustmentCapabilityV1.FIXED_RESOURCE_DEPARTURE_RESPACE
    ),
    ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE: (
        AdjustmentCapabilityV1.NO_GENERATION_REQUIRED
    ),
}
_NON_FIXED_REASONS = {
    ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA: (
        ADJUSTMENT_CAPABILITY_NOT_AUTHORIZED_INSUFFICIENT_DATA
    ),
    ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED: (
        TECHNICAL_PARAMETER_CHANGE_REQUIRED
    ),
    ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS: (VARIABLE_TRIP_INCREASE_CAPABILITY_REQUIRED),
    ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS: (VARIABLE_TRIP_REDUCTION_CAPABILITY_REQUIRED),
    ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE: NO_GENERATION_REQUIRED,
}
_NON_FIXED_LIMITATIONS = {
    ServiceAdjustmentDecisionV1.INSUFFICIENT_DATA: (
        "Insufficient authoritative data does not authorize problem "
        "construction or solver invocation.",
    ),
    ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED: (
        "The current fixed-resource solver does not implement technical parameter changes.",
    ),
    ServiceAdjustmentDecisionV1.INCREASE_TOTAL_TRIPS: (
        "A future variable-trip/resource-planning capability is required.",
    ),
    ServiceAdjustmentDecisionV1.REDUCE_TOTAL_TRIPS: (
        "The proven reduction remains advisory until a variable-trip "
        "reduction capability is approved.",
    ),
    ServiceAdjustmentDecisionV1.KEEP_CURRENT_TIMETABLE: (),
}
_LEGACY_DECISION_CAPABILITIES = {
    ServiceAdjustmentDecisionV1.REDISTRIBUTE_TRIPS: (
        AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION
    ),
    ServiceAdjustmentDecisionV1.REDISTRIBUTE_DEPARTURE_TIMES: (
        AdjustmentCapabilityV1.FIXED_RESOURCE_DEPARTURE_RESPACE
    ),
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _issue(code: str, path: str, message: str) -> ContractValidationIssue:
    return ContractValidationIssue(code=code, path=path, message=message)


def _error_issues(
    validation: ContractValidationResult,
) -> tuple[ContractValidationIssue, ...]:
    return tuple(
        issue for issue in validation.issues if issue.severity == ContractValidationSeverity.ERROR
    )


def _raise_validation(issues: list[ContractValidationIssue]) -> None:
    if issues:
        raise ContractValidationError(tuple(issues))


def fixed_resource_authorization_profile_payload_v1(
    profile: FixedResourceAuthorizationProfileV1,
) -> dict[str, object]:
    return {
        "fingerprint_profile": FIXED_RESOURCE_PROFILE_FINGERPRINT_PROFILE,
        "contract_version": CONTRACT_VERSION,
        "direction_trip_lock_mode": _jsonable(profile.direction_trip_lock_mode),
        "fleet_constraint_mode": _jsonable(profile.fleet_constraint_mode),
        "initial_fleet_positioning_mode": _jsonable(profile.initial_fleet_positioning_mode),
        "boundary_convention": _jsonable(profile.boundary_convention),
        "total_daily_trip_count_locked": profile.total_daily_trip_count_locked,
        "directional_trip_counts_locked": profile.directional_trip_counts_locked,
        "first_departures_locked": profile.first_departures_locked,
        "last_departures_locked": profile.last_departures_locked,
        "source_trip_runtime_locked": profile.source_trip_runtime_locked,
        "arrival_terminal_turnaround_locked": (profile.arrival_terminal_turnaround_locked),
        "vehicle_capacity_locked": profile.vehicle_capacity_locked,
        "available_fleet_limit_locked": profile.available_fleet_limit_locked,
        "operating_window_locked": profile.operating_window_locked,
        "minimum_service_locked": profile.minimum_service_locked,
        "terminal_stock_must_remain_non_negative": (
            profile.terminal_stock_must_remain_non_negative
        ),
    }


def calculate_fixed_resource_authorization_profile_fingerprint_v1(
    profile: FixedResourceAuthorizationProfileV1,
) -> str:
    return canonical_sha256(fixed_resource_authorization_profile_payload_v1(profile))


def validate_fixed_resource_authorization_profile_v1(
    profile: FixedResourceAuthorizationProfileV1,
) -> ContractValidationResult:
    if type(profile) is not FixedResourceAuthorizationProfileV1:
        return ContractValidationResult(
            (
                _issue(
                    "FIXED_RESOURCE_PROFILE_TYPE_INVALID",
                    "profile",
                    "The fixed-resource profile must use the exact typed V1 contract.",
                ),
            )
        )

    issues: list[ContractValidationIssue] = []
    expected_modes = (
        (
            "direction_trip_lock_mode",
            profile.direction_trip_lock_mode,
            DirectionTripLockMode.FIXED_BY_DIRECTION,
            DirectionTripLockMode,
        ),
        (
            "fleet_constraint_mode",
            profile.fleet_constraint_mode,
            FleetConstraintMode.AVAILABLE_UPPER_BOUND,
            FleetConstraintMode,
        ),
        (
            "initial_fleet_positioning_mode",
            profile.initial_fleet_positioning_mode,
            InitialFleetPositioningMode.SOLVER_DETERMINED,
            InitialFleetPositioningMode,
        ),
        (
            "boundary_convention",
            profile.boundary_convention,
            BoundaryConvention.HALF_OPEN,
            BoundaryConvention,
        ),
    )
    for field_name, actual, expected, enum_type in expected_modes:
        if type(actual) is not enum_type or actual != expected:
            issues.append(
                _issue(
                    "FIXED_RESOURCE_PROFILE_MODE_UNSUPPORTED",
                    f"profile.{field_name}",
                    f"{field_name} must be the current supported mode {expected.value}.",
                )
            )

    lock_fields = (
        "total_daily_trip_count_locked",
        "directional_trip_counts_locked",
        "first_departures_locked",
        "last_departures_locked",
        "source_trip_runtime_locked",
        "arrival_terminal_turnaround_locked",
        "vehicle_capacity_locked",
        "available_fleet_limit_locked",
        "operating_window_locked",
        "minimum_service_locked",
        "terminal_stock_must_remain_non_negative",
    )
    for field_name in lock_fields:
        if getattr(profile, field_name) is not True:
            issues.append(
                _issue(
                    "FIXED_RESOURCE_PROFILE_REQUIRED_LOCK_WEAKENED",
                    f"profile.{field_name}",
                    f"{field_name} must be exactly true.",
                )
            )

    expected_fingerprint = calculate_fixed_resource_authorization_profile_fingerprint_v1(profile)
    if profile.profile_fingerprint != expected_fingerprint:
        issues.append(
            _issue(
                "FIXED_RESOURCE_PROFILE_FINGERPRINT_MISMATCH",
                "profile.profile_fingerprint",
                "Profile fingerprint does not bind every mode and required lock.",
            )
        )
    return ContractValidationResult(tuple(issues))


def ensure_valid_fixed_resource_authorization_profile_v1(
    profile: FixedResourceAuthorizationProfileV1,
) -> None:
    validation = validate_fixed_resource_authorization_profile_v1(profile)
    if not validation.passed:
        raise ContractValidationError(_error_issues(validation))


def build_current_fixed_resource_authorization_profile_v1() -> FixedResourceAuthorizationProfileV1:
    profile = FixedResourceAuthorizationProfileV1(
        direction_trip_lock_mode=DirectionTripLockMode.FIXED_BY_DIRECTION,
        fleet_constraint_mode=FleetConstraintMode.AVAILABLE_UPPER_BOUND,
        initial_fleet_positioning_mode=(InitialFleetPositioningMode.SOLVER_DETERMINED),
        boundary_convention=BoundaryConvention.HALF_OPEN,
        total_daily_trip_count_locked=True,
        directional_trip_counts_locked=True,
        first_departures_locked=True,
        last_departures_locked=True,
        source_trip_runtime_locked=True,
        arrival_terminal_turnaround_locked=True,
        vehicle_capacity_locked=True,
        available_fleet_limit_locked=True,
        operating_window_locked=True,
        minimum_service_locked=True,
        terminal_stock_must_remain_non_negative=True,
        profile_fingerprint="",
    )
    return replace(
        profile,
        profile_fingerprint=(
            calculate_fixed_resource_authorization_profile_fingerprint_v1(profile)
        ),
    )


def _binding_payload(
    binding: FixedResourceCapabilityBindingV1,
) -> dict[str, object]:
    profile = binding.supported_fixed_resource_profile
    profile_payload = (
        {
            **fixed_resource_authorization_profile_payload_v1(profile),
            "profile_fingerprint": profile.profile_fingerprint,
        }
        if type(profile) is FixedResourceAuthorizationProfileV1
        else _jsonable(profile)
    )
    return {
        "capability": _jsonable(binding.capability),
        "generation_action": binding.generation_action,
        "solver_adapter_id": binding.solver_adapter_id,
        "adapter_available": binding.adapter_available,
        "supported_fixed_resource_profile": profile_payload,
        "supported_direction_trip_lock_mode": _jsonable(binding.supported_direction_trip_lock_mode),
        "supported_fleet_constraint_mode": _jsonable(binding.supported_fleet_constraint_mode),
        "supported_initial_fleet_positioning_mode": _jsonable(
            binding.supported_initial_fleet_positioning_mode
        ),
        "supported_boundary_convention": _jsonable(binding.supported_boundary_convention),
    }


def adjustment_capability_routing_policy_payload_v1(
    policy: AdjustmentCapabilityRoutingPolicyV1,
) -> dict[str, object]:
    return {
        "fingerprint_profile": ROUTING_POLICY_FINGERPRINT_PROFILE,
        "contract_version": CONTRACT_VERSION,
        "fixed_resource_bindings": [
            _binding_payload(binding) for binding in policy.fixed_resource_bindings
        ],
    }


def calculate_adjustment_capability_routing_policy_fingerprint_v1(
    policy: AdjustmentCapabilityRoutingPolicyV1,
) -> str:
    return canonical_sha256(adjustment_capability_routing_policy_payload_v1(policy))


def _binding_validation_issues(
    binding: FixedResourceCapabilityBindingV1,
    index: int,
) -> list[ContractValidationIssue]:
    prefix = f"routing_policy.fixed_resource_bindings[{index}]"
    if type(binding) is not FixedResourceCapabilityBindingV1:
        return [
            _issue(
                "ROUTING_POLICY_BINDING_TYPE_INVALID",
                prefix,
                "Every fixed-resource binding must use the exact immutable type.",
            )
        ]
    issues: list[ContractValidationIssue] = []
    if (
        type(binding.capability) is not AdjustmentCapabilityV1
        or binding.capability not in _FIXED_ACTIONS
    ):
        issues.append(
            _issue(
                "ROUTING_POLICY_CAPABILITY_UNSUPPORTED",
                f"{prefix}.capability",
                "Only the two fixed-resource capabilities may have solver bindings.",
            )
        )
    else:
        expected_action = _FIXED_ACTIONS[binding.capability]
        if binding.generation_action != expected_action:
            issues.append(
                _issue(
                    "ROUTING_POLICY_CAPABILITY_ACTION_MISMATCH",
                    f"{prefix}.generation_action",
                    "Generation action does not match the bound capability.",
                )
            )
    if not isinstance(binding.generation_action, str) or not binding.generation_action.strip():
        issues.append(
            _issue(
                "ROUTING_POLICY_ACTION_INVALID",
                f"{prefix}.generation_action",
                "Generation action must be a non-empty string.",
            )
        )
    if (
        not isinstance(binding.solver_adapter_id, str)
        or not binding.solver_adapter_id.strip()
        or binding.solver_adapter_id != binding.solver_adapter_id.strip()
    ):
        issues.append(
            _issue(
                "ROUTING_POLICY_ADAPTER_ID_INVALID",
                f"{prefix}.solver_adapter_id",
                "Solver adapter ID must be a non-empty canonical string.",
            )
        )
    if type(binding.adapter_available) is not bool:
        issues.append(
            _issue(
                "ROUTING_POLICY_AVAILABILITY_INVALID",
                f"{prefix}.adapter_available",
                "Adapter availability must be an explicit boolean.",
            )
        )

    profile_validation = validate_fixed_resource_authorization_profile_v1(
        binding.supported_fixed_resource_profile
    )
    issues.extend(_error_issues(profile_validation))
    profile = binding.supported_fixed_resource_profile
    if type(profile) is not FixedResourceAuthorizationProfileV1:
        return issues
    mode_pairs = (
        (
            "supported_direction_trip_lock_mode",
            binding.supported_direction_trip_lock_mode,
            profile.direction_trip_lock_mode,
            DirectionTripLockMode,
        ),
        (
            "supported_fleet_constraint_mode",
            binding.supported_fleet_constraint_mode,
            profile.fleet_constraint_mode,
            FleetConstraintMode,
        ),
        (
            "supported_initial_fleet_positioning_mode",
            binding.supported_initial_fleet_positioning_mode,
            profile.initial_fleet_positioning_mode,
            InitialFleetPositioningMode,
        ),
        (
            "supported_boundary_convention",
            binding.supported_boundary_convention,
            profile.boundary_convention,
            BoundaryConvention,
        ),
    )
    for field_name, actual, expected, enum_type in mode_pairs:
        if type(actual) is not enum_type or actual != expected:
            issues.append(
                _issue(
                    "ROUTING_POLICY_SUPPORTED_MODE_MISMATCH",
                    f"{prefix}.{field_name}",
                    "Supported problem mode does not match the typed profile.",
                )
            )
    return issues


def validate_adjustment_capability_routing_policy_v1(
    policy: AdjustmentCapabilityRoutingPolicyV1,
) -> ContractValidationResult:
    if type(policy) is not AdjustmentCapabilityRoutingPolicyV1:
        return ContractValidationResult(
            (
                _issue(
                    "ROUTING_POLICY_TYPE_INVALID",
                    "routing_policy",
                    "Routing requires the exact immutable routing-policy type.",
                ),
            )
        )
    issues: list[ContractValidationIssue] = []
    if not isinstance(policy.fixed_resource_bindings, tuple):
        issues.append(
            _issue(
                "ROUTING_POLICY_BINDINGS_NOT_IMMUTABLE",
                "routing_policy.fixed_resource_bindings",
                "Capability bindings must be an immutable tuple.",
            )
        )
        bindings: tuple[FixedResourceCapabilityBindingV1, ...] = ()
    else:
        bindings = policy.fixed_resource_bindings
    capabilities = tuple(
        binding.capability
        for binding in bindings
        if type(binding) is FixedResourceCapabilityBindingV1
        and type(binding.capability) is AdjustmentCapabilityV1
    )
    if len(capabilities) != len(bindings):
        issues.append(
            _issue(
                "ROUTING_POLICY_BINDING_TYPE_INVALID",
                "routing_policy.fixed_resource_bindings",
                "Every binding must use FixedResourceCapabilityBindingV1.",
            )
        )
    if len(set(capabilities)) != len(capabilities):
        issues.append(
            _issue(
                "ROUTING_POLICY_DUPLICATE_CAPABILITY_BINDING",
                "routing_policy.fixed_resource_bindings",
                "A fixed-resource capability may be configured only once.",
            )
        )
    if all(capability in _FIXED_CAPABILITY_ORDER for capability in capabilities):
        expected_order = tuple(sorted(capabilities, key=_FIXED_CAPABILITY_ORDER.__getitem__))
        if capabilities != expected_order:
            issues.append(
                _issue(
                    "ROUTING_POLICY_BINDING_ORDER_INVALID",
                    "routing_policy.fixed_resource_bindings",
                    "Capability bindings must use deterministic canonical order.",
                )
            )
    for index, binding in enumerate(bindings):
        issues.extend(_binding_validation_issues(binding, index))

    if all(type(binding) is FixedResourceCapabilityBindingV1 for binding in bindings):
        expected_fingerprint = calculate_adjustment_capability_routing_policy_fingerprint_v1(policy)
        if policy.routing_policy_fingerprint != expected_fingerprint:
            issues.append(
                _issue(
                    "ROUTING_POLICY_FINGERPRINT_MISMATCH",
                    "routing_policy.routing_policy_fingerprint",
                    "Routing-policy fingerprint does not bind all capability settings.",
                )
            )
    return ContractValidationResult(tuple(issues))


def ensure_valid_adjustment_capability_routing_policy_v1(
    policy: AdjustmentCapabilityRoutingPolicyV1,
) -> None:
    validation = validate_adjustment_capability_routing_policy_v1(policy)
    if not validation.passed:
        raise ContractValidationError(_error_issues(validation))


def _validate_available_adapter_ids(
    available_adapter_ids: tuple[str, ...],
) -> None:
    issues: list[ContractValidationIssue] = []
    if not isinstance(available_adapter_ids, tuple):
        issues.append(
            _issue(
                "ROUTING_POLICY_AVAILABLE_ADAPTERS_NOT_IMMUTABLE",
                "available_adapter_ids",
                "Available adapter IDs must be an immutable tuple.",
            )
        )
        _raise_validation(issues)
    adapter_ids_valid = not any(
        not isinstance(adapter_id, str)
        or not adapter_id.strip()
        or adapter_id != adapter_id.strip()
        for adapter_id in available_adapter_ids
    )
    if not adapter_ids_valid:
        issues.append(
            _issue(
                "ROUTING_POLICY_AVAILABLE_ADAPTER_ID_INVALID",
                "available_adapter_ids",
                "Available adapter IDs must be non-empty canonical strings.",
            )
        )
    if adapter_ids_valid and len(set(available_adapter_ids)) != len(available_adapter_ids):
        issues.append(
            _issue(
                "ROUTING_POLICY_DUPLICATE_AVAILABLE_ADAPTER",
                "available_adapter_ids",
                "Available adapter IDs may not contain duplicates.",
            )
        )
    if adapter_ids_valid and available_adapter_ids != tuple(sorted(available_adapter_ids)):
        issues.append(
            _issue(
                "ROUTING_POLICY_AVAILABLE_ADAPTER_ORDER_INVALID",
                "available_adapter_ids",
                "Available adapter IDs must use deterministic lexical order.",
            )
        )
    _raise_validation(issues)


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
    if not isinstance(configured_capabilities, tuple):
        raise ContractValidationError(
            (
                _issue(
                    "ROUTING_POLICY_CAPABILITIES_NOT_IMMUTABLE",
                    "configured_capabilities",
                    "Configured capabilities must be an immutable tuple.",
                ),
            )
        )
    if (
        not isinstance(solver_adapter_id, str)
        or not solver_adapter_id.strip()
        or solver_adapter_id != solver_adapter_id.strip()
    ):
        raise ContractValidationError(
            (
                _issue(
                    "ROUTING_POLICY_ADAPTER_ID_INVALID",
                    "solver_adapter_id",
                    "Solver adapter ID must be a non-empty canonical string.",
                ),
            )
        )
    _validate_available_adapter_ids(available_adapter_ids)
    if any(
        type(capability) is not AdjustmentCapabilityV1 or capability not in _FIXED_ACTIONS
        for capability in configured_capabilities
    ):
        raise ContractValidationError(
            (
                _issue(
                    "ROUTING_POLICY_CAPABILITY_UNSUPPORTED",
                    "configured_capabilities",
                    "Only the two fixed-resource capabilities may be configured.",
                ),
            )
        )
    if len(set(configured_capabilities)) != len(configured_capabilities):
        raise ContractValidationError(
            (
                _issue(
                    "ROUTING_POLICY_DUPLICATE_CAPABILITY_BINDING",
                    "configured_capabilities",
                    "Configured capabilities may not contain duplicates.",
                ),
            )
        )
    profile = (
        fixed_resource_profile
        if fixed_resource_profile is not None
        else build_current_fixed_resource_authorization_profile_v1()
    )
    ensure_valid_fixed_resource_authorization_profile_v1(profile)
    ordered_capabilities = tuple(
        sorted(configured_capabilities, key=_FIXED_CAPABILITY_ORDER.__getitem__)
    )
    bindings = tuple(
        FixedResourceCapabilityBindingV1(
            capability=capability,
            generation_action=_FIXED_ACTIONS[capability],
            solver_adapter_id=solver_adapter_id,
            adapter_available=solver_adapter_id in available_adapter_ids,
            supported_fixed_resource_profile=profile,
            supported_direction_trip_lock_mode=(profile.direction_trip_lock_mode),
            supported_fleet_constraint_mode=profile.fleet_constraint_mode,
            supported_initial_fleet_positioning_mode=(profile.initial_fleet_positioning_mode),
            supported_boundary_convention=profile.boundary_convention,
        )
        for capability in ordered_capabilities
    )
    policy = AdjustmentCapabilityRoutingPolicyV1(
        fixed_resource_bindings=bindings,
        routing_policy_fingerprint="",
    )
    policy = replace(
        policy,
        routing_policy_fingerprint=(
            calculate_adjustment_capability_routing_policy_fingerprint_v1(policy)
        ),
    )
    ensure_valid_adjustment_capability_routing_policy_v1(policy)
    return policy


def project_adjustment_capability_routing_policy_v1(
    legacy_policy: ServiceAdjustmentPolicyV1,
    available_adapter_ids: tuple[str, ...],
) -> AdjustmentCapabilityRoutingPolicyV1:
    """Project only the two legacy routing fields after Phase A assessment."""
    if type(legacy_policy) is not ServiceAdjustmentPolicyV1:
        raise ContractValidationError(
            (
                _issue(
                    "LEGACY_ROUTING_POLICY_TYPE_INVALID",
                    "legacy_policy",
                    "Legacy routing projection requires ServiceAdjustmentPolicyV1.",
                ),
            )
        )
    _validate_available_adapter_ids(available_adapter_ids)
    if (
        not isinstance(legacy_policy.fixed_resource_solver_adapter, str)
        or not legacy_policy.fixed_resource_solver_adapter.strip()
        or legacy_policy.fixed_resource_solver_adapter
        != legacy_policy.fixed_resource_solver_adapter.strip()
    ):
        raise ContractValidationError(
            (
                _issue(
                    "LEGACY_ROUTING_ADAPTER_ID_INVALID",
                    "legacy_policy.fixed_resource_solver_adapter",
                    "Legacy fixed-resource adapter ID must be non-empty.",
                ),
            )
        )
    decisions = legacy_policy.fixed_resource_authorized_decisions
    issues: list[ContractValidationIssue] = []
    if not isinstance(decisions, tuple):
        issues.append(
            _issue(
                "LEGACY_ROUTING_DECISIONS_NOT_IMMUTABLE",
                "legacy_policy.fixed_resource_authorized_decisions",
                "Legacy authorized decisions must be an immutable tuple.",
            )
        )
    else:
        decisions_valid = not any(
            type(decision) is not ServiceAdjustmentDecisionV1
            or decision not in _LEGACY_DECISION_CAPABILITIES
            for decision in decisions
        )
        if not decisions_valid:
            issues.append(
                _issue(
                    "LEGACY_ROUTING_AUTHORIZED_DECISION_UNSUPPORTED",
                    "legacy_policy.fixed_resource_authorized_decisions",
                    "Only fixed-resource redistribution decisions may use the legacy adapter.",
                )
            )
        elif len(set(decisions)) != len(decisions):
            issues.append(
                _issue(
                    "LEGACY_ROUTING_DUPLICATE_AUTHORIZED_DECISION",
                    "legacy_policy.fixed_resource_authorized_decisions",
                    "Legacy authorized decisions may not contain duplicates.",
                )
            )
    _raise_validation(issues)
    capabilities = tuple(_LEGACY_DECISION_CAPABILITIES[decision] for decision in decisions)
    return build_adjustment_capability_routing_policy_v1(
        capabilities,
        solver_adapter_id=legacy_policy.fixed_resource_solver_adapter,
        available_adapter_ids=available_adapter_ids,
    )


def _full_directional_authority(
    context: ServiceAdjustmentEvaluationContextV1,
) -> bool:
    resolution = context.b_evaluation.demand_resolution
    coverage = resolution.coverage_assessment if resolution is not None else None
    return bool(coverage is not None and coverage.directional_c_generation_supported)


def _fixed_resource_evidence_issues(
    assessment: ServiceAdjustmentAssessmentV1,
    context: ServiceAdjustmentEvaluationContextV1,
    capability: AdjustmentCapabilityV1,
) -> list[ContractValidationIssue]:
    issues: list[ContractValidationIssue] = []
    if not _full_directional_authority(context):
        issues.append(
            _issue(
                "ADJUSTMENT_ROUTING_DIRECTIONAL_AUTHORITY_MISSING",
                "authoritative_context.b_evaluation.demand_resolution",
                "Fixed-resource directional routing requires full directional authority.",
            )
        )
    if assessment.technical_evidence.technically_feasible is not True:
        issues.append(
            _issue(
                "ADJUSTMENT_ROUTING_TECHNICAL_FEASIBILITY_MISSING",
                "assessment.technical_evidence",
                "Fixed-resource routing requires technically feasible evidence.",
            )
        )

    if capability == AdjustmentCapabilityV1.FIXED_RESOURCE_TRIP_REDISTRIBUTION:
        shortage_by_direction = {
            direction: sum(
                block.shortage_trips
                for block in assessment.block_evidence
                if block.direction == direction
            )
            for direction in (
                ContractDirection.OUTBOUND,
                ContractDirection.INBOUND,
            )
        }
        total_shortage = sum(shortage_by_direction.values())
        combined_shortage = sum(
            block.shortage_trips
            for block in assessment.block_evidence
            if block.direction == ContractDirection.COMBINED
        )
        if total_shortage <= 0 or assessment.daily_evidence.total_shortage_trips != total_shortage:
            issues.append(
                _issue(
                    "ADJUSTMENT_ROUTING_POSITIVE_SHORTAGE_PROOF_MISSING",
                    "assessment.daily_evidence.total_shortage_trips",
                    "Trip redistribution requires a reconciled positive shortage quantity.",
                )
            )
        if combined_shortage:
            issues.append(
                _issue(
                    "ADJUSTMENT_ROUTING_COMBINED_ONLY_AUTHORITY_FORBIDDEN",
                    "assessment.block_evidence",
                    "Combined-only shortage evidence cannot authorize directional routing.",
                )
            )
        for direction, shortage_quantity in shortage_by_direction.items():
            if shortage_quantity <= 0:
                continue
            matches = tuple(
                proof for proof in assessment.joint_donor_evidence if proof.direction == direction
            )
            if len(matches) != 1:
                issues.append(
                    _issue(
                        "ADJUSTMENT_ROUTING_JOINT_DONOR_PROOF_MISSING",
                        "assessment.joint_donor_evidence",
                        f"Exactly one donor proof is required for {direction.value}.",
                    )
                )
                continue
            proof = matches[0]
            if (
                proof.shortage_quantity != shortage_quantity
                or not proof.search_complete
                or proof.proven_joint_capacity < shortage_quantity
                or proof.proven_joint_capacity != len(proof.selected_jointly_feasible_trip_ids)
                or len(proof.selected_jointly_feasible_trip_ids) < shortage_quantity
                or len(set(proof.selected_jointly_feasible_trip_ids))
                != len(proof.selected_jointly_feasible_trip_ids)
                or not set(proof.selected_jointly_feasible_trip_ids).issubset(
                    proof.candidate_trip_ids
                )
                or proof.issue_codes
            ):
                issues.append(
                    _issue(
                        "ADJUSTMENT_ROUTING_JOINT_DONOR_PROOF_INSUFFICIENT",
                        "assessment.joint_donor_evidence",
                        "Complete joint donor capacity must cover every "
                        f"{direction.value} shortage trip.",
                    )
                )
    elif capability == AdjustmentCapabilityV1.FIXED_RESOURCE_DEPARTURE_RESPACE:
        irregular = tuple(
            regime
            for regime in assessment.headway_evidence
            if regime.regularity_classification
            in {
                HeadwayRegularityClassificationV1.IRREGULAR,
                HeadwayRegularityClassificationV1.EXCEPTIONAL,
            }
        )
        if not irregular:
            issues.append(
                _issue(
                    "ADJUSTMENT_ROUTING_IRREGULAR_HEADWAY_PROOF_MISSING",
                    "assessment.headway_evidence",
                    "Departure re-spacing requires an irregular or exceptional regime.",
                )
            )
        if any(regime.direction == ContractDirection.COMBINED for regime in irregular):
            issues.append(
                _issue(
                    "ADJUSTMENT_ROUTING_COMBINED_ONLY_AUTHORITY_FORBIDDEN",
                    "assessment.headway_evidence",
                    "Combined-only evidence cannot authorize directional re-spacing.",
                )
            )
        diagnostics_valid = all(
            regime.respace_technically_possible is True
            and regime.respace_diagnostic is not None
            and regime.respace_diagnostic.passed is True
            and not regime.respace_diagnostic.issue_codes
            and not regime.respace_diagnostic.scenario_validation_issue_codes
            and not regime.respace_diagnostic.operating_lock_issue_codes
            and not regime.respace_diagnostic.runtime_issue_trip_ids
            and not regime.respace_diagnostic.turnaround_or_location_issue_codes
            and bool(regime.respace_diagnostic.changed_trip_ids)
            and regime.respace_diagnostic.minimum_required_fleet
            <= regime.respace_diagnostic.available_fleet_limit
            and regime.respace_diagnostic.minimum_terminal_stock_terminal_1 >= 0
            and regime.respace_diagnostic.minimum_terminal_stock_terminal_2 >= 0
            and regime.respace_diagnostic.fleet_assignment_vehicle_count
            == regime.respace_diagnostic.minimum_required_fleet
            for regime in irregular
        )
        if not diagnostics_valid:
            issues.append(
                _issue(
                    "ADJUSTMENT_ROUTING_RESPACE_DIAGNOSTIC_PROOF_INSUFFICIENT",
                    "assessment.headway_evidence",
                    "Every irregular regime requires a complete passing re-spacing diagnostic.",
                )
            )
    return issues


def _required_binding(
    policy: AdjustmentCapabilityRoutingPolicyV1,
    capability: AdjustmentCapabilityV1,
) -> FixedResourceCapabilityBindingV1 | None:
    return next(
        (binding for binding in policy.fixed_resource_bindings if binding.capability == capability),
        None,
    )


def _route_payload(
    routing: AdjustmentCapabilityRoutingV1,
) -> dict[str, object]:
    profile = routing.required_fixed_resource_profile
    return {
        "fingerprint_profile": ROUTING_FINGERPRINT_PROFILE,
        "contract_version": CONTRACT_VERSION,
        "source_evaluation_context_fingerprint": (routing.source_evaluation_context_fingerprint),
        "source_assessment_fingerprint": (routing.source_assessment_fingerprint),
        "source_adjustment_decision_policy_fingerprint": (
            routing.source_adjustment_decision_policy_fingerprint
        ),
        "routing_policy_fingerprint": routing.routing_policy_fingerprint,
        "primary_decision": _jsonable(routing.primary_decision),
        "routed_capability": _jsonable(routing.routed_capability),
        "authorized_generation_action": (routing.authorized_generation_action),
        "solver_adapter_id": routing.solver_adapter_id,
        "problem_construction_authorized": (routing.problem_construction_authorized),
        "solver_invocation_authorized": (routing.solver_invocation_authorized),
        "required_fixed_resource_profile": (
            {
                **fixed_resource_authorization_profile_payload_v1(profile),
                "profile_fingerprint": profile.profile_fingerprint,
            }
            if type(profile) is FixedResourceAuthorizationProfileV1
            else None
        ),
        "reason_codes": list(routing.reason_codes),
        "limitations": list(routing.limitations),
    }


def calculate_adjustment_capability_routing_fingerprint_v1(
    routing: AdjustmentCapabilityRoutingV1,
) -> str:
    return canonical_sha256(_route_payload(routing))


def derive_adjustment_capability_routing_id_v1(
    routing_fingerprint: str,
) -> str:
    return f"ROUTING-{routing_fingerprint[:16].upper()}"


def _expected_policy_authorization(
    capability: AdjustmentCapabilityV1,
    profile: FixedResourceAuthorizationProfileV1,
    policy: AdjustmentCapabilityRoutingPolicyV1,
) -> tuple[bool, FixedResourceCapabilityBindingV1 | None]:
    binding = _required_binding(policy, capability)
    authorized = bool(
        binding is not None
        and binding.adapter_available
        and binding.supported_fixed_resource_profile == profile
        and binding.generation_action == _FIXED_ACTIONS[capability]
        and binding.solver_adapter_id.strip()
    )
    return authorized, binding


def validate_adjustment_capability_routing_v1(
    routing: AdjustmentCapabilityRoutingV1,
    authoritative_context: ServiceAdjustmentEvaluationContextV1,
    assessment: ServiceAdjustmentAssessmentV1,
    routing_policy: AdjustmentCapabilityRoutingPolicyV1 | None = None,
) -> ContractValidationResult:
    if type(routing) is not AdjustmentCapabilityRoutingV1:
        return ContractValidationResult(
            (
                _issue(
                    "ADJUSTMENT_ROUTING_TYPE_INVALID",
                    "routing",
                    "Routing validation requires the exact canonical route type.",
                ),
            )
        )
    if type(authoritative_context) is not ServiceAdjustmentEvaluationContextV1:
        return ContractValidationResult(
            (
                _issue(
                    "ADJUSTMENT_ROUTING_CONTEXT_TYPE_INVALID",
                    "authoritative_context",
                    "Route validation requires the exact Phase A context type.",
                ),
            )
        )
    if type(assessment) is not ServiceAdjustmentAssessmentV1:
        return ContractValidationResult(
            (
                _issue(
                    "ADJUSTMENT_ROUTING_ASSESSMENT_TYPE_INVALID",
                    "assessment",
                    "Route validation requires the exact canonical assessment type.",
                ),
            )
        )
    issues: list[ContractValidationIssue] = []
    try:
        ensure_valid_service_adjustment_evaluation_context_v1(authoritative_context)
        ensure_valid_service_adjustment_assessment_v1(
            assessment,
            authoritative_context,
        )
    except ContractValidationError as exc:
        issues.extend(exc.issues)

    if routing_policy is not None:
        policy_validation = validate_adjustment_capability_routing_policy_v1(routing_policy)
        issues.extend(_error_issues(policy_validation))

    identity_pairs = (
        (
            "ADJUSTMENT_ROUTING_CONTEXT_MISMATCH",
            "routing.source_evaluation_context_fingerprint",
            routing.source_evaluation_context_fingerprint,
            authoritative_context.context_fingerprint,
        ),
        (
            "ADJUSTMENT_ROUTING_ASSESSMENT_MISMATCH",
            "routing.source_assessment_fingerprint",
            routing.source_assessment_fingerprint,
            assessment.evaluator_fingerprint,
        ),
        (
            "ADJUSTMENT_ROUTING_DECISION_POLICY_MISMATCH",
            "routing.source_adjustment_decision_policy_fingerprint",
            routing.source_adjustment_decision_policy_fingerprint,
            assessment.adjustment_decision_policy_fingerprint,
        ),
    )
    for code, path, declared, expected in identity_pairs:
        if declared != expected:
            issues.append(
                _issue(
                    code,
                    path,
                    f"Declared {path} does not match its canonical source.",
                )
            )
    if (
        routing_policy is not None
        and routing.routing_policy_fingerprint != routing_policy.routing_policy_fingerprint
    ):
        issues.append(
            _issue(
                "ADJUSTMENT_ROUTING_POLICY_MISMATCH",
                "routing.routing_policy_fingerprint",
                "Route does not bind the supplied routing policy.",
            )
        )
    if (
        type(routing.primary_decision) is not ServiceAdjustmentDecisionV1
        or routing.primary_decision != assessment.primary_decision
    ):
        issues.append(
            _issue(
                "ADJUSTMENT_ROUTING_PRIMARY_DECISION_MISMATCH",
                "routing.primary_decision",
                "Capability routing may not change the canonical primary decision.",
            )
        )
    expected_capability = _DECISION_CAPABILITIES.get(assessment.primary_decision)
    if (
        type(routing.routed_capability) is not AdjustmentCapabilityV1
        or routing.routed_capability != expected_capability
    ):
        issues.append(
            _issue(
                "ADJUSTMENT_ROUTING_CAPABILITY_MISMATCH",
                "routing.routed_capability",
                "Routed capability does not match the closed decision matrix.",
            )
        )

    is_fixed = routing.routed_capability in _FIXED_ACTIONS
    if is_fixed:
        profile_validation = validate_fixed_resource_authorization_profile_v1(
            routing.required_fixed_resource_profile
        )
        issues.extend(_error_issues(profile_validation))
        if type(routing.required_fixed_resource_profile) is (FixedResourceAuthorizationProfileV1):
            expected_profile = build_current_fixed_resource_authorization_profile_v1()
            if routing.required_fixed_resource_profile != expected_profile:
                issues.append(
                    _issue(
                        "ADJUSTMENT_ROUTING_PROFILE_MISMATCH",
                        "routing.required_fixed_resource_profile",
                        "Fixed-resource route does not carry the exact current profile.",
                    )
                )
            issues.extend(
                _fixed_resource_evidence_issues(
                    assessment,
                    authoritative_context,
                    routing.routed_capability,
                )
            )
            policy_authorized = None
            binding = None
            if routing_policy is not None:
                policy_authorized, binding = _expected_policy_authorization(
                    routing.routed_capability,
                    expected_profile,
                    routing_policy,
                )
                if (
                    routing.problem_construction_authorized != policy_authorized
                    or routing.solver_invocation_authorized != policy_authorized
                ):
                    issues.append(
                        _issue(
                            "ADJUSTMENT_ROUTING_AUTHORIZATION_POLICY_MISMATCH",
                            "routing.problem_construction_authorized",
                            "Route authorization does not match current policy "
                            "capability and availability.",
                        )
                    )
            both_authorized = bool(
                routing.problem_construction_authorized and routing.solver_invocation_authorized
            )
            if routing.problem_construction_authorized != routing.solver_invocation_authorized:
                issues.append(
                    _issue(
                        "ADJUSTMENT_ROUTING_AUTHORIZATION_BOOLEAN_MISMATCH",
                        "routing",
                        "Problem and solver authorization must change together.",
                    )
                )
            if both_authorized:
                if (
                    routing.authorized_generation_action
                    != _FIXED_ACTIONS[routing.routed_capability]
                    or not isinstance(routing.solver_adapter_id, str)
                    or not routing.solver_adapter_id.strip()
                    or routing.reason_codes != (CURRENT_SOLVER_CAN_IMPLEMENT,)
                ):
                    issues.append(
                        _issue(
                            "ADJUSTMENT_ROUTING_AUTHORIZED_FIELDS_INVALID",
                            "routing",
                            "Authorized fixed-resource routing fields are inconsistent.",
                        )
                    )
                if binding is not None and (
                    routing.solver_adapter_id != binding.solver_adapter_id
                    or routing.authorized_generation_action != binding.generation_action
                ):
                    issues.append(
                        _issue(
                            "ADJUSTMENT_ROUTING_BINDING_MISMATCH",
                            "routing",
                            "Authorized route does not match its exact capability binding.",
                        )
                    )
            elif (
                routing.authorized_generation_action is not None
                or routing.solver_adapter_id is not None
                or routing.reason_codes != (CURRENT_SOLVER_CAPABILITY_INSUFFICIENT,)
            ):
                issues.append(
                    _issue(
                        "ADJUSTMENT_ROUTING_UNAVAILABLE_FIELDS_INVALID",
                        "routing",
                        "Unavailable fixed-resource routes must retain the capability "
                        "and profile but no action or adapter.",
                    )
                )
    else:
        expected_reason = _NON_FIXED_REASONS.get(assessment.primary_decision)
        if (
            routing.required_fixed_resource_profile is not None
            or routing.authorized_generation_action is not None
            or routing.solver_adapter_id is not None
            or routing.problem_construction_authorized
            or routing.solver_invocation_authorized
            or routing.reason_codes != (expected_reason,)
        ):
            issues.append(
                _issue(
                    "ADJUSTMENT_ROUTING_NON_FIXED_FIELDS_INVALID",
                    "routing",
                    "Non-fixed capabilities must use the exact no-authorization matrix.",
                )
            )

    if not isinstance(routing.reason_codes, tuple) or not isinstance(routing.limitations, tuple):
        issues.append(
            _issue(
                "ADJUSTMENT_ROUTING_COLLECTION_NOT_IMMUTABLE",
                "routing",
                "Route reasons and limitations must be immutable tuples.",
            )
        )
    expected_fingerprint = calculate_adjustment_capability_routing_fingerprint_v1(routing)
    if routing.routing_fingerprint != expected_fingerprint:
        issues.append(
            _issue(
                "ADJUSTMENT_ROUTING_FINGERPRINT_MISMATCH",
                "routing.routing_fingerprint",
                "Route fingerprint does not bind the complete routing payload.",
            )
        )
    if routing.routing_id != derive_adjustment_capability_routing_id_v1(expected_fingerprint):
        issues.append(
            _issue(
                "ADJUSTMENT_ROUTING_ID_MISMATCH",
                "routing.routing_id",
                "Routing ID is not derived from the recomputed route fingerprint.",
            )
        )
    return ContractValidationResult(tuple(issues))


def ensure_valid_adjustment_capability_routing_v1(
    routing: AdjustmentCapabilityRoutingV1,
    authoritative_context: ServiceAdjustmentEvaluationContextV1,
    assessment: ServiceAdjustmentAssessmentV1,
    routing_policy: AdjustmentCapabilityRoutingPolicyV1 | None = None,
) -> None:
    validation = validate_adjustment_capability_routing_v1(
        routing,
        authoritative_context,
        assessment,
        routing_policy,
    )
    if not validation.passed:
        raise ContractValidationError(_error_issues(validation))


def route_adjustment_capability_v1(
    assessment: ServiceAdjustmentAssessmentV1,
    authoritative_context: ServiceAdjustmentEvaluationContextV1,
    routing_policy: AdjustmentCapabilityRoutingPolicyV1,
) -> AdjustmentCapabilityRoutingV1:
    """Route an exact canonical assessment without generating or solving."""
    ensure_valid_service_adjustment_evaluation_context_v1(authoritative_context)
    ensure_valid_service_adjustment_assessment_v1(
        assessment,
        authoritative_context,
    )
    ensure_valid_adjustment_capability_routing_policy_v1(routing_policy)
    if type(assessment.primary_decision) is not ServiceAdjustmentDecisionV1:
        raise ContractValidationError(
            (
                _issue(
                    "ADJUSTMENT_ROUTING_PRIMARY_DECISION_INVALID",
                    "assessment.primary_decision",
                    "Assessment decision must be one of the seven closed V1 values.",
                ),
            )
        )
    capability = _DECISION_CAPABILITIES[assessment.primary_decision]
    required_profile = None
    action = None
    adapter_id = None
    problem_authorized = False
    solver_authorized = False

    if capability in _FIXED_ACTIONS:
        evidence_issues = _fixed_resource_evidence_issues(
            assessment,
            authoritative_context,
            capability,
        )
        _raise_validation(evidence_issues)
        required_profile = build_current_fixed_resource_authorization_profile_v1()
        authorized, binding = _expected_policy_authorization(
            capability,
            required_profile,
            routing_policy,
        )
        if authorized:
            assert binding is not None
            action = binding.generation_action
            adapter_id = binding.solver_adapter_id
            problem_authorized = True
            solver_authorized = True
            reasons = (CURRENT_SOLVER_CAN_IMPLEMENT,)
            limitations = ()
        else:
            reasons = (CURRENT_SOLVER_CAPABILITY_INSUFFICIENT,)
            limitations = (
                "The required fixed-resource capability is not configured "
                "with an available compatible adapter.",
            )
    else:
        reasons = (_NON_FIXED_REASONS[assessment.primary_decision],)
        limitations = _NON_FIXED_LIMITATIONS[assessment.primary_decision]

    routing = AdjustmentCapabilityRoutingV1(
        routing_id="",
        source_evaluation_context_fingerprint=(authoritative_context.context_fingerprint),
        source_assessment_fingerprint=assessment.evaluator_fingerprint,
        source_adjustment_decision_policy_fingerprint=(
            assessment.adjustment_decision_policy_fingerprint
        ),
        routing_policy_fingerprint=(routing_policy.routing_policy_fingerprint),
        primary_decision=assessment.primary_decision,
        routed_capability=capability,
        authorized_generation_action=action,
        solver_adapter_id=adapter_id,
        problem_construction_authorized=problem_authorized,
        solver_invocation_authorized=solver_authorized,
        required_fixed_resource_profile=required_profile,
        reason_codes=reasons,
        limitations=limitations,
        routing_fingerprint="",
    )
    fingerprint = calculate_adjustment_capability_routing_fingerprint_v1(routing)
    routing = replace(
        routing,
        routing_id=derive_adjustment_capability_routing_id_v1(fingerprint),
        routing_fingerprint=fingerprint,
    )
    ensure_valid_adjustment_capability_routing_v1(
        routing,
        authoritative_context,
        assessment,
        routing_policy,
    )
    return routing


def _legacy_projection_payload(
    projection: LegacyServiceAdjustmentAssessmentProjectionV1,
) -> dict[str, object]:
    return {
        "fingerprint_profile": (LEGACY_ASSESSMENT_PROJECTION_FINGERPRINT_PROFILE),
        "contract_version": CONTRACT_VERSION,
        "canonical_assessment": _jsonable(asdict(projection.canonical_assessment)),
        "canonical_assessment_fingerprint": (projection.canonical_assessment_fingerprint),
        "legacy_source_problem_fingerprint": (projection.legacy_source_problem_fingerprint),
        "legacy_heuristic_authorized": (projection.legacy_heuristic_authorized),
        "legacy_authorized_generation_action": (projection.legacy_authorized_generation_action),
        "source_routing_fingerprint": (projection.source_routing_fingerprint),
    }


def calculate_legacy_service_adjustment_assessment_projection_fingerprint_v1(
    projection: LegacyServiceAdjustmentAssessmentProjectionV1,
) -> str:
    return canonical_sha256(_legacy_projection_payload(projection))


def validate_legacy_service_adjustment_assessment_projection_v1(
    projection: LegacyServiceAdjustmentAssessmentProjectionV1,
    assessment: ServiceAdjustmentAssessmentV1,
    context: ServiceAdjustmentEvaluationContextV1,
    routing: AdjustmentCapabilityRoutingV1,
) -> ContractValidationResult:
    if type(projection) is not LegacyServiceAdjustmentAssessmentProjectionV1:
        return ContractValidationResult(
            (
                _issue(
                    "LEGACY_ASSESSMENT_PROJECTION_TYPE_INVALID",
                    "projection",
                    "Legacy projection validation requires the exact projection type.",
                ),
            )
        )
    if (
        type(assessment) is not ServiceAdjustmentAssessmentV1
        or type(context) is not ServiceAdjustmentEvaluationContextV1
        or type(routing) is not AdjustmentCapabilityRoutingV1
    ):
        return ContractValidationResult(
            (
                _issue(
                    "LEGACY_ASSESSMENT_PROJECTION_SOURCE_TYPE_INVALID",
                    "projection",
                    "Projection validation requires exact canonical Phase B sources.",
                ),
            )
        )
    issues: list[ContractValidationIssue] = []
    try:
        ensure_valid_service_adjustment_assessment_v1(assessment, context)
        ensure_valid_adjustment_capability_routing_v1(
            routing,
            context,
            assessment,
        )
    except ContractValidationError as exc:
        issues.extend(exc.issues)
    if (
        projection.canonical_assessment != assessment
        or projection.canonical_assessment_fingerprint != assessment.evaluator_fingerprint
    ):
        issues.append(
            _issue(
                "LEGACY_ASSESSMENT_PROJECTION_ASSESSMENT_MISMATCH",
                "projection.canonical_assessment",
                "Projection does not reference the exact canonical assessment.",
            )
        )
    if projection.source_routing_fingerprint != routing.routing_fingerprint:
        issues.append(
            _issue(
                "LEGACY_ASSESSMENT_PROJECTION_ROUTING_MISMATCH",
                "projection.source_routing_fingerprint",
                "Projection does not reference the exact canonical route.",
            )
        )
    expected_authorized = bool(
        routing.problem_construction_authorized and routing.solver_invocation_authorized
    )
    expected_action = routing.authorized_generation_action if expected_authorized else None
    if projection.legacy_source_problem_fingerprint is not None:
        issues.append(
            _issue(
                "LEGACY_ASSESSMENT_PROJECTION_PROBLEM_FORBIDDEN",
                "projection.legacy_source_problem_fingerprint",
                "Phase B creates no problem and must project a null problem fingerprint.",
            )
        )
    if (
        projection.legacy_heuristic_authorized != expected_authorized
        or projection.legacy_authorized_generation_action != expected_action
    ):
        issues.append(
            _issue(
                "LEGACY_ASSESSMENT_PROJECTION_AUTHORIZATION_MISMATCH",
                "projection",
                "Projected legacy authorization does not match the validated route.",
            )
        )
    expected_fingerprint = calculate_legacy_service_adjustment_assessment_projection_fingerprint_v1(
        projection
    )
    if projection.projection_fingerprint != expected_fingerprint:
        issues.append(
            _issue(
                "LEGACY_ASSESSMENT_PROJECTION_FINGERPRINT_MISMATCH",
                "projection.projection_fingerprint",
                "Projection fingerprint does not bind every projected field.",
            )
        )
    return ContractValidationResult(tuple(issues))


def ensure_valid_legacy_service_adjustment_assessment_projection_v1(
    projection: LegacyServiceAdjustmentAssessmentProjectionV1,
    assessment: ServiceAdjustmentAssessmentV1,
    context: ServiceAdjustmentEvaluationContextV1,
    routing: AdjustmentCapabilityRoutingV1,
) -> None:
    validation = validate_legacy_service_adjustment_assessment_projection_v1(
        projection,
        assessment,
        context,
        routing,
    )
    if not validation.passed:
        raise ContractValidationError(_error_issues(validation))


def build_legacy_service_adjustment_assessment_projection_v1(
    assessment: ServiceAdjustmentAssessmentV1,
    context: ServiceAdjustmentEvaluationContextV1,
    routing: AdjustmentCapabilityRoutingV1,
) -> LegacyServiceAdjustmentAssessmentProjectionV1:
    """Build the separate transitional post-routing legacy projection."""
    ensure_valid_service_adjustment_evaluation_context_v1(context)
    ensure_valid_service_adjustment_assessment_v1(assessment, context)
    ensure_valid_adjustment_capability_routing_v1(
        routing,
        context,
        assessment,
    )
    authorized = bool(
        routing.problem_construction_authorized and routing.solver_invocation_authorized
    )
    projection = LegacyServiceAdjustmentAssessmentProjectionV1(
        canonical_assessment=assessment,
        canonical_assessment_fingerprint=assessment.evaluator_fingerprint,
        legacy_source_problem_fingerprint=None,
        legacy_heuristic_authorized=authorized,
        legacy_authorized_generation_action=(
            routing.authorized_generation_action if authorized else None
        ),
        source_routing_fingerprint=routing.routing_fingerprint,
        projection_fingerprint="",
    )
    projection = replace(
        projection,
        projection_fingerprint=(
            calculate_legacy_service_adjustment_assessment_projection_fingerprint_v1(projection)
        ),
    )
    ensure_valid_legacy_service_adjustment_assessment_projection_v1(
        projection,
        assessment,
        context,
        routing,
    )
    return projection


__all__ = [
    "ADJUSTMENT_CAPABILITY_NOT_AUTHORIZED_INSUFFICIENT_DATA",
    "CURRENT_SOLVER_CAN_IMPLEMENT",
    "CURRENT_SOLVER_CAPABILITY_INSUFFICIENT",
    "FIXED_RESOURCE_DEPARTURE_RESPACE_ACTION",
    "FIXED_RESOURCE_TRIP_REDISTRIBUTION_ACTION",
    "NO_GENERATION_REQUIRED",
    "TECHNICAL_PARAMETER_CHANGE_REQUIRED",
    "VARIABLE_TRIP_INCREASE_CAPABILITY_REQUIRED",
    "VARIABLE_TRIP_REDUCTION_CAPABILITY_REQUIRED",
    "AdjustmentCapabilityRoutingPolicyV1",
    "AdjustmentCapabilityRoutingV1",
    "AdjustmentCapabilityV1",
    "FixedResourceAuthorizationProfileV1",
    "FixedResourceCapabilityBindingV1",
    "LegacyServiceAdjustmentAssessmentProjectionV1",
    "build_adjustment_capability_routing_policy_v1",
    "build_current_fixed_resource_authorization_profile_v1",
    "build_legacy_service_adjustment_assessment_projection_v1",
    "calculate_adjustment_capability_routing_fingerprint_v1",
    "calculate_adjustment_capability_routing_policy_fingerprint_v1",
    "calculate_fixed_resource_authorization_profile_fingerprint_v1",
    "calculate_legacy_service_adjustment_assessment_projection_fingerprint_v1",
    "derive_adjustment_capability_routing_id_v1",
    "ensure_valid_adjustment_capability_routing_policy_v1",
    "ensure_valid_adjustment_capability_routing_v1",
    "ensure_valid_fixed_resource_authorization_profile_v1",
    "ensure_valid_legacy_service_adjustment_assessment_projection_v1",
    "project_adjustment_capability_routing_policy_v1",
    "route_adjustment_capability_v1",
    "validate_adjustment_capability_routing_policy_v1",
    "validate_adjustment_capability_routing_v1",
    "validate_fixed_resource_authorization_profile_v1",
    "validate_legacy_service_adjustment_assessment_projection_v1",
]
