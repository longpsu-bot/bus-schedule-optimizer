from __future__ import annotations

from .evaluation_serialization import (
    block_supply_plan_to_contract_dict,
    demand_analysis_block_to_contract_dict,
    demand_resolution_to_contract_dict,
)
from .models import ScenarioCOptimizationModeV1
from .serialization import scenario_to_contract_dict
from .solver_models import (
    BoundedInitialFleetV1,
    DirectionRedistributionAuthorizationV1,
    InitialFleetValuesV1,
    OperatingParameterLockV1,
    ScheduleProblemV1,
    SolverPolicyV1,
)


def _lock_to_contract_dict(lock: OperatingParameterLockV1) -> dict[str, object]:
    return {
        "field": lock.field,
        "value": lock.value,
        "locked": lock.locked,
        "source_fingerprint": lock.source_fingerprint,
        "authorized_exception": lock.authorized_exception,
    }


def _authorization_to_contract_dict(
    authorization: DirectionRedistributionAuthorizationV1,
) -> dict[str, object]:
    return {
        "enabled": authorization.enabled,
        "authorized_by": authorization.authorized_by,
        "directional_demand_confidence": (authorization.directional_demand_confidence.value),
    }


def _initial_fleet_to_contract_dict(
    values: InitialFleetValuesV1,
) -> dict[str, object]:
    return {
        "terminal_1": values.terminal_1,
        "terminal_2": values.terminal_2,
    }


def _bounded_initial_fleet_to_contract_dict(
    values: BoundedInitialFleetV1,
) -> dict[str, object]:
    return {
        "terminal_1": {
            "minimum": values.terminal_1.minimum,
            "maximum": values.terminal_1.maximum,
        },
        "terminal_2": {
            "minimum": values.terminal_2.minimum,
            "maximum": values.terminal_2.maximum,
        },
    }


def solver_policy_to_contract_dict(policy: SolverPolicyV1) -> dict[str, object]:
    return {
        "time_limit_seconds": policy.time_limit_seconds,
        "worker_count": policy.worker_count,
        "random_seed": policy.random_seed,
        "require_independent_validation": policy.require_independent_validation,
    }


def schedule_problem_to_contract_dict(
    problem: ScheduleProblemV1,
) -> dict[str, object]:
    blocks = sorted(
        problem.analysis_blocks,
        key=lambda item: (
            item.direction.value,
            item.start_time,
            item.end_time,
            item.block_id,
        ),
    )
    locks = sorted(problem.operating_parameter_locks, key=lambda item: item.field)
    requirements = sorted(
        problem.block_requirements,
        key=lambda item: (
            item.direction.value,
            item.block_start,
            item.block_end,
            item.block_id,
        ),
    )
    payload = {
        "contract_version": problem.contract_version,
        "problem_id": problem.problem_id,
        "problem_fingerprint": problem.problem_fingerprint,
        "evaluation_fingerprint": problem.evaluation_fingerprint,
        "source_a_fingerprint": problem.source_a_fingerprint,
        "source_b_fingerprint": problem.source_b_fingerprint,
        "observed_demand_fingerprint": problem.observed_demand_fingerprint,
        "solver_adapter": problem.solver_adapter,
        "adapter_context_fingerprint": problem.adapter_context_fingerprint,
        "scenario_a": (
            scenario_to_contract_dict(problem.scenario_a)
            if problem.scenario_a is not None
            else None
        ),
        "scenario_b": scenario_to_contract_dict(problem.scenario_b),
        "demand_response_mode": (
            problem.demand_response_mode.value if problem.demand_response_mode is not None else None
        ),
        "demand_resolution": (
            demand_resolution_to_contract_dict(problem.demand_resolution)
            if problem.demand_resolution is not None
            else None
        ),
        "analysis_blocks": [demand_analysis_block_to_contract_dict(item) for item in blocks],
        "operating_parameter_locks": [_lock_to_contract_dict(item) for item in locks],
        "direction_trip_lock_mode": problem.direction_trip_lock_mode.value,
        "direction_redistribution_authorization": (
            _authorization_to_contract_dict(problem.direction_redistribution_authorization)
            if problem.direction_redistribution_authorization is not None
            else None
        ),
        "fleet_constraint_mode": problem.fleet_constraint_mode.value,
        "initial_fleet_positioning_mode": (problem.initial_fleet_positioning_mode.value),
        "fixed_initial_fleet": (
            _initial_fleet_to_contract_dict(problem.fixed_initial_fleet)
            if problem.fixed_initial_fleet is not None
            else None
        ),
        "bounded_initial_fleet": (
            _bounded_initial_fleet_to_contract_dict(problem.bounded_initial_fleet)
            if problem.bounded_initial_fleet is not None
            else None
        ),
        "planning_load_factor_ceiling": problem.planning_load_factor_ceiling,
        "critical_load_factor_ceiling": problem.critical_load_factor_ceiling,
        "block_requirements": [block_supply_plan_to_contract_dict(item) for item in requirements],
        "boundary_convention": problem.boundary_convention.value,
        "solver_policy": solver_policy_to_contract_dict(problem.solver_policy),
    }
    if problem.optimization_mode != ScenarioCOptimizationModeV1.LEGACY_A_BOUND:
        payload["scenario_c_optimization_mode"] = problem.optimization_mode.value
        payload["demand_allocation_authority_mode"] = (
            problem.demand_allocation_authority_mode.value
            if problem.demand_allocation_authority_mode is not None
            else None
        )
    return payload
