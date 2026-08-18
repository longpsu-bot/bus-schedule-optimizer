from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .evaluation_fingerprints import evaluation_fingerprint
from .evaluation_serialization import (
    block_supply_plan_to_contract_dict,
    demand_analysis_block_to_contract_dict,
)
from .models import DemandResolutionType, ScenarioCOptimizationModeV1
from .public_api import evaluate_scenario_b_v1
from .serialization import observed_demand_fingerprint, scenario_fingerprint
from .solver_models import (
    BoundaryConvention,
    DirectionTripLockMode,
    FleetConstraintMode,
    InitialFleetPositioningMode,
    ScheduleGenerationContextV1,
    ScheduleProblemV1,
)
from .solver_problem import (
    HEURISTIC_TURNAROUND_BRIDGE_MODE,
    RUNTIME_LOCK_MODE,
    TURNAROUND_APPLICATION_MODE,
    build_operating_parameter_locks_v1,
    calculate_problem_fingerprint,
    derive_problem_id,
)
from .validation import validate_scenario_input

_FINGERPRINT_PATTERN = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class ScheduleProblemValidationIssueV1:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ScheduleProblemValidationResultV1:
    issues: tuple[ScheduleProblemValidationIssueV1, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


def _issue(
    issues: list[ScheduleProblemValidationIssueV1],
    code: str,
    message: str,
) -> None:
    if code not in {item.code for item in issues}:
        issues.append(ScheduleProblemValidationIssueV1(code=code, message=message))


def _valid_fingerprint(value: str) -> bool:
    return bool(_FINGERPRINT_PATTERN.fullmatch(value))


def _validate_scenarios(
    problem: ScheduleProblemV1,
    issues: list[ScheduleProblemValidationIssueV1],
) -> None:
    if (problem.scenario_a is None) != (problem.source_a_fingerprint is None):
        _issue(
            issues,
            "PROBLEM_SCENARIO_A_NULLABILITY_MISMATCH",
            "Scenario A and its fingerprint must be null together.",
        )
    if problem.scenario_a is not None:
        if (
            problem.source_a_fingerprint is None
            or scenario_fingerprint(problem.scenario_a) != problem.source_a_fingerprint
        ):
            _issue(
                issues,
                "PROBLEM_SCENARIO_A_FINGERPRINT_MISMATCH",
                "Scenario A does not match its declared fingerprint.",
            )
        if not validate_scenario_input(problem.scenario_a).passed:
            _issue(
                issues,
                "PROBLEM_SCENARIO_A_FINGERPRINT_MISMATCH",
                "Scenario A is not a valid normalized Contract V1 scenario.",
            )
    if scenario_fingerprint(problem.scenario_b) != problem.source_b_fingerprint:
        _issue(
            issues,
            "PROBLEM_SCENARIO_B_FINGERPRINT_MISMATCH",
            "Scenario B does not match its declared fingerprint.",
        )
    if not validate_scenario_input(problem.scenario_b).passed:
        _issue(
            issues,
            "PROBLEM_SCENARIO_B_FINGERPRINT_MISMATCH",
            "Scenario B is not a valid normalized Contract V1 scenario.",
        )
    if problem.scenario_a is not None:
        route_fields = (
            "route_id",
            "route_name",
            "route_type",
            "terminal_1_name",
            "terminal_2_name",
        )
        if any(
            getattr(problem.scenario_a, field) != getattr(problem.scenario_b, field)
            for field in route_fields
        ):
            _issue(
                issues,
                "PROBLEM_SCENARIO_A_FINGERPRINT_MISMATCH",
                "Scenario A and B route identity does not reconcile.",
            )


def _validate_demand(
    problem: ScheduleProblemV1,
    issues: list[ScheduleProblemValidationIssueV1],
) -> None:
    no_demand = problem.observed_demand_fingerprint is None
    if no_demand:
        if (
            problem.demand_response_mode is not None
            or problem.demand_resolution is not None
            or problem.analysis_blocks
            or problem.block_requirements
        ):
            _issue(
                issues,
                "PROBLEM_DEMAND_NULLABILITY_MISMATCH",
                "No-demand problems must use null demand fields and empty arrays.",
            )
        return
    if (
        not _valid_fingerprint(problem.observed_demand_fingerprint)
        or problem.demand_response_mode is None
        or problem.demand_resolution is None
    ):
        _issue(
            issues,
            "PROBLEM_DEMAND_NULLABILITY_MISMATCH",
            "Demand identity, response mode, and resolution must be present together.",
        )
        return
    is_daily_total = (
        problem.demand_resolution.source_resolution_type == DemandResolutionType.DAILY_TOTAL
    )
    if is_daily_total:
        if problem.analysis_blocks or problem.block_requirements:
            _issue(
                issues,
                "PROBLEM_DEMAND_NULLABILITY_MISMATCH",
                "Daily-total demand cannot contain intraday blocks or requirements.",
            )
    elif not problem.analysis_blocks or not problem.block_requirements:
        _issue(
            issues,
            "PROBLEM_BLOCK_RECONCILIATION_MISMATCH",
            "Intraday demand requires analysis blocks and B requirements.",
        )

    block_ids = [item.block_id for item in problem.analysis_blocks]
    if len(set(block_ids)) != len(block_ids):
        _issue(
            issues,
            "PROBLEM_DUPLICATE_BLOCK_ID",
            "Analysis block IDs must be unique.",
        )
    requirement_ids = [item.block_id for item in problem.block_requirements]
    if len(set(requirement_ids)) != len(requirement_ids) or set(block_ids) != set(requirement_ids):
        _issue(
            issues,
            "PROBLEM_BLOCK_RECONCILIATION_MISMATCH",
            "Block requirements must reconcile one-to-one with analysis blocks.",
        )
        return
    requirement_by_id = {item.block_id: item for item in problem.block_requirements}
    for block in problem.analysis_blocks:
        requirement = requirement_by_id[block.block_id]
        if (
            requirement.scenario.value != "B"
            or requirement.direction != block.direction
            or requirement.block_start != block.start_time
            or requirement.block_end != block.end_time
            or requirement.duration_minutes != block.duration_minutes
            or requirement.passenger_demand != block.observed_passengers
            or requirement.demand_rate_per_hour != block.demand_rate_per_hour
            or requirement.confidence != block.confidence
        ):
            _issue(
                issues,
                "PROBLEM_BLOCK_RECONCILIATION_MISMATCH",
                f"Requirement {block.block_id} does not match its analysis block.",
            )


def _expected_core_lock_values(problem: ScheduleProblemV1) -> dict[str, object]:
    locks = build_operating_parameter_locks_v1(
        problem.scenario_b,
        problem.source_b_fingerprint,
        direction_trip_lock_mode=problem.direction_trip_lock_mode,
        fleet_constraint_mode=problem.fleet_constraint_mode,
        initial_fleet_positioning_mode=(problem.initial_fleet_positioning_mode),
    )
    return {item.field: item.value for item in locks}


def _validate_locks(
    problem: ScheduleProblemV1,
    issues: list[ScheduleProblemValidationIssueV1],
) -> None:
    lock_fields = [item.field for item in problem.operating_parameter_locks]
    if len(set(lock_fields)) != len(lock_fields):
        _issue(
            issues,
            "PROBLEM_LOCK_DUPLICATE_FIELD",
            "Operating lock field names must be unique.",
        )
    lock_by_field = {item.field: item for item in problem.operating_parameter_locks}
    expected = _expected_core_lock_values(problem)
    if not set(expected).issubset(lock_by_field):
        _issue(
            issues,
            "PROBLEM_LOCK_SET_INCOMPLETE",
            "The canonical operating lock set is incomplete.",
        )
    for field, expected_value in expected.items():
        lock = lock_by_field.get(field)
        if lock is None:
            continue
        if not lock.locked or lock.authorized_exception is not None:
            _issue(
                issues,
                "PROBLEM_LOCK_SET_INCOMPLETE",
                f"Mandatory lock {field} is not unconditionally locked.",
            )
        if lock.source_fingerprint != problem.source_b_fingerprint:
            _issue(
                issues,
                "PROBLEM_LOCK_SOURCE_MISMATCH",
                f"Lock {field} does not bind the canonical Scenario B source.",
            )
        if lock.value != expected_value:
            _issue(
                issues,
                "PROBLEM_LOCK_VALUE_MISMATCH",
                f"Lock {field} does not match canonical Scenario B.",
            )
    for lock in problem.operating_parameter_locks:
        if lock.source_fingerprint != problem.source_b_fingerprint:
            _issue(
                issues,
                "PROBLEM_LOCK_SOURCE_MISMATCH",
                f"Lock {lock.field} does not bind the canonical Scenario B source.",
            )
    if problem.solver_adapter == "legacy_heuristic_v1":
        required_bridge = {
            "heuristic_turnaround_bridge_mode": (HEURISTIC_TURNAROUND_BRIDGE_MODE),
            "heuristic_turnaround_bridge_value_minutes": max(
                problem.scenario_b.turnaround_minutes.terminal_1,
                problem.scenario_b.turnaround_minutes.terminal_2,
            ),
        }
        if not set(required_bridge).issubset(lock_by_field):
            _issue(
                issues,
                "PROBLEM_LOCK_SET_INCOMPLETE",
                "The heuristic H2 turnaround bridge locks are missing.",
            )
        for field, value in required_bridge.items():
            lock = lock_by_field.get(field)
            if lock is not None and (
                not lock.locked or lock.value != value or lock.authorized_exception is not None
            ):
                _issue(
                    issues,
                    "PROBLEM_LOCK_VALUE_MISMATCH",
                    f"Heuristic bridge lock {field} is invalid.",
                )
    runtime_lock = lock_by_field.get("runtime_lock_mode")
    turnaround_lock = lock_by_field.get("turnaround_application_mode")
    if runtime_lock is not None and runtime_lock.value != RUNTIME_LOCK_MODE:
        _issue(
            issues,
            "PROBLEM_LOCK_VALUE_MISMATCH",
            "The runtime lock mode is not fixed by source trip.",
        )
    if turnaround_lock is not None and turnaround_lock.value != TURNAROUND_APPLICATION_MODE:
        _issue(
            issues,
            "PROBLEM_LOCK_VALUE_MISMATCH",
            "The turnaround mode is not arrival-terminal-specific.",
        )


def _validate_modes_and_policy(
    problem: ScheduleProblemV1,
    issues: list[ScheduleProblemValidationIssueV1],
) -> None:
    if (
        problem.direction_trip_lock_mode != DirectionTripLockMode.FIXED_BY_DIRECTION
        or problem.fleet_constraint_mode != FleetConstraintMode.AVAILABLE_UPPER_BOUND
        or problem.initial_fleet_positioning_mode != InitialFleetPositioningMode.SOLVER_DETERMINED
        or problem.boundary_convention != BoundaryConvention.HALF_OPEN
        or problem.direction_redistribution_authorization is not None
        or problem.fixed_initial_fleet is not None
        or problem.bounded_initial_fleet is not None
    ):
        _issue(
            issues,
            "UNSUPPORTED_PROBLEM_MODE",
            "The current Contract V1 runtime supports only fixed directions, "
            "available-fleet upper bounds, solver-determined positioning, and "
            "half-open analytical boundaries.",
        )
    if problem.optimization_mode == ScenarioCOptimizationModeV1.LEGACY_A_BOUND:
        if problem.demand_allocation_authority_mode is not None:
            _issue(
                issues,
                "UNSUPPORTED_PROBLEM_MODE",
                "Legacy A-bound problems cannot claim a V3 allocation authority mode.",
            )
    elif problem.demand_allocation_authority_mode is None:
        _issue(
            issues,
            "PROBLEM_DEMAND_ALLOCATION_AUTHORITY_MISSING",
            "B-anchored two-stage problems require explicit directional or combined authority.",
        )
    policy = problem.solver_policy
    policy_invalid = not policy.require_independent_validation
    if policy.time_limit_seconds is not None:
        policy_invalid = policy_invalid or (
            isinstance(policy.time_limit_seconds, bool)
            or not isinstance(policy.time_limit_seconds, (int, float))
            or not math.isfinite(float(policy.time_limit_seconds))
            or policy.time_limit_seconds <= 0
        )
    if policy.worker_count is not None:
        policy_invalid = policy_invalid or (
            isinstance(policy.worker_count, bool)
            or not isinstance(policy.worker_count, int)
            or policy.worker_count < 1
        )
    if policy.random_seed is not None:
        policy_invalid = policy_invalid or (
            isinstance(policy.random_seed, bool)
            or not isinstance(policy.random_seed, int)
            or policy.random_seed < 0
        )
    if (
        not math.isfinite(problem.planning_load_factor_ceiling)
        or not math.isfinite(problem.critical_load_factor_ceiling)
        or problem.planning_load_factor_ceiling <= 0
        or problem.critical_load_factor_ceiling <= 0
        or problem.planning_load_factor_ceiling > problem.critical_load_factor_ceiling
    ):
        policy_invalid = True
    if policy_invalid:
        _issue(
            issues,
            "PROBLEM_POLICY_INVALID",
            "Generic solver policy or load-factor ceilings are invalid.",
        )


def validate_schedule_problem_v1(
    problem: ScheduleProblemV1,
) -> ScheduleProblemValidationResultV1:
    issues: list[ScheduleProblemValidationIssueV1] = []
    if (
        not problem.solver_adapter.strip()
        or not _valid_fingerprint(problem.adapter_context_fingerprint)
        or not _valid_fingerprint(problem.evaluation_fingerprint)
        or not _valid_fingerprint(problem.source_b_fingerprint)
    ):
        _issue(
            issues,
            "PROBLEM_POLICY_INVALID",
            "Adapter identity and required fingerprints must be present.",
        )
    _validate_scenarios(problem, issues)
    _validate_demand(problem, issues)
    _validate_locks(problem, issues)
    _validate_modes_and_policy(problem, issues)

    expected_fingerprint = calculate_problem_fingerprint(problem)
    if problem.problem_fingerprint != expected_fingerprint:
        _issue(
            issues,
            "PROBLEM_FINGERPRINT_MISMATCH",
            "The problem fingerprint does not match canonical problem facts.",
        )
    if problem.problem_id != derive_problem_id(problem.problem_fingerprint):
        _issue(
            issues,
            "PROBLEM_ID_FINGERPRINT_MISMATCH",
            "The problem ID is not derived from the problem fingerprint.",
        )
    return ScheduleProblemValidationResultV1(tuple(issues))


def validate_schedule_generation_context_v1(
    context: ScheduleGenerationContextV1,
) -> ScheduleProblemValidationResultV1:
    problem = context.problem
    issues = list(validate_schedule_problem_v1(problem).issues)
    normalized = context.normalized_inputs
    if (
        problem.scenario_a != normalized.scenario_a
        or problem.source_a_fingerprint != normalized.scenario_a_fingerprint
    ):
        _issue(
            issues,
            "PROBLEM_SCENARIO_A_FINGERPRINT_MISMATCH",
            "Generation context Scenario A does not match the problem.",
        )
    if problem.optimization_mode != normalized.optimization_mode:
        _issue(
            issues,
            "PROBLEM_OPTIMIZATION_MODE_MISMATCH",
            "Generation context optimization mode does not match the problem.",
        )
    if (
        problem.scenario_b != normalized.scenario_b
        or problem.source_b_fingerprint != normalized.scenario_b_fingerprint
    ):
        _issue(
            issues,
            "PROBLEM_SCENARIO_B_FINGERPRINT_MISMATCH",
            "Generation context Scenario B does not match the problem.",
        )
    observed = normalized.observed_demand
    expected_demand_fingerprint = (
        observed_demand_fingerprint(observed) if observed is not None else None
    )
    if (
        normalized.observed_demand_fingerprint != expected_demand_fingerprint
        or problem.observed_demand_fingerprint != expected_demand_fingerprint
    ):
        _issue(
            issues,
            "PROBLEM_DEMAND_FINGERPRINT_MISMATCH",
            "Generation context demand does not match the problem.",
        )
    expected_mode = observed.demand_response_mode if observed is not None else None
    if problem.demand_response_mode != expected_mode:
        _issue(
            issues,
            "PROBLEM_DEMAND_NULLABILITY_MISMATCH",
            "Generation context demand response mode does not match.",
        )

    try:
        authoritative = evaluate_scenario_b_v1(
            normalized,
            context.evaluation_policy,
        )
    except Exception:
        _issue(
            issues,
            "PROBLEM_EVALUATION_FINGERPRINT_MISMATCH",
            "Generation context cannot produce a valid authoritative evaluation.",
        )
        return ScheduleProblemValidationResultV1(tuple(issues))
    authoritative_fingerprint = evaluation_fingerprint(
        normalized,
        authoritative,
        context.evaluation_policy,
    )
    supplied_fingerprint = evaluation_fingerprint(
        normalized,
        context.b_evaluation,
        context.evaluation_policy,
    )
    if (
        problem.evaluation_fingerprint != authoritative_fingerprint
        or supplied_fingerprint != authoritative_fingerprint
    ):
        _issue(
            issues,
            "PROBLEM_EVALUATION_FINGERPRINT_MISMATCH",
            "Generation context evaluation does not match current authority.",
        )
    resolution = authoritative.demand_resolution
    expected_resolution = resolution.contract if resolution is not None else None
    if problem.demand_resolution != expected_resolution:
        _issue(
            issues,
            "PROBLEM_BLOCK_RECONCILIATION_MISMATCH",
            "Problem demand resolution does not match authoritative evaluation.",
        )
    expected_blocks = tuple(resolution.blocks) if resolution is not None else ()
    if [demand_analysis_block_to_contract_dict(item) for item in problem.analysis_blocks] != [
        demand_analysis_block_to_contract_dict(item) for item in expected_blocks
    ]:
        _issue(
            issues,
            "PROBLEM_BLOCK_RECONCILIATION_MISMATCH",
            "Problem analysis blocks do not match authoritative evaluation.",
        )
    if [block_supply_plan_to_contract_dict(item) for item in problem.block_requirements] != [
        block_supply_plan_to_contract_dict(item) for item in authoritative.b_block_supply
    ]:
        _issue(
            issues,
            "PROBLEM_BLOCK_RECONCILIATION_MISMATCH",
            "Problem block requirements do not match authoritative evaluation.",
        )
    if (
        problem.planning_load_factor_ceiling
        != context.evaluation_policy.planning_load_factor_ceiling
        or problem.critical_load_factor_ceiling
        != context.evaluation_policy.critical_load_factor_ceiling
    ):
        _issue(
            issues,
            "PROBLEM_EVALUATION_FINGERPRINT_MISMATCH",
            "Problem ceilings do not match the authoritative evaluation policy.",
        )
    enforcement_authority = context.protected_service_floor_enforcement_authority
    if enforcement_authority is not None:
        from bus_schedule_engine.protected_service_floor_codes import (
            PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_MISMATCH,
        )
        from bus_schedule_engine.protected_service_floor_enforcement import (
            protected_service_floor_enforcement_authority_is_valid_v1,
        )

        if not protected_service_floor_enforcement_authority_is_valid_v1(
            enforcement_authority,
            normalized.scenario_b,
        ):
            _issue(
                issues,
                PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_MISMATCH,
                "Protected-service-floor authority does not match the generation context.",
            )
    return ScheduleProblemValidationResultV1(tuple(issues))
