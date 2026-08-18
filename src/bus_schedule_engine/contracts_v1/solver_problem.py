from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, replace
from enum import Enum
from typing import Any

from bus_schedule_engine.models import ProtectedServiceFloorEnforcementAuthorityV1

from .evaluation import ScenarioBEvaluationBundleV1, ScenarioBEvaluationPolicyV1
from .evaluation_fingerprints import evaluation_fingerprint
from .evaluation_serialization import (
    block_supply_plan_to_contract_dict,
    demand_analysis_block_to_contract_dict,
    demand_resolution_to_contract_dict,
)
from .heuristic_context import (
    HEURISTIC_TURNAROUND_BRIDGE_MODE as HEURISTIC_TURNAROUND_BRIDGE_MODE,
)
from .models import (
    DemandAllocationAuthorityModeV1,
    NormalizedInputBundleV1,
    ScenarioBInput,
    ScenarioCOptimizationModeV1,
)
from .public_api import evaluate_scenario_b_v1
from .serialization import canonical_sha256
from .solver_models import (
    BoundaryConvention,
    BoundedInitialFleetV1,
    DirectionRedistributionAuthorizationV1,
    DirectionTripLockMode,
    FleetConstraintMode,
    InitialFleetPositioningMode,
    InitialFleetValuesV1,
    OperatingParameterLockV1,
    ScheduleGenerationContextV1,
    ScheduleProblemV1,
    SolverPolicyV1,
)
from .terminal_occupancy import TERMINAL_OCCUPANCY_EVENT_ORDER

PROBLEM_FINGERPRINT_PROFILE = "contract_v1_h4_problem"
EMPTY_ADAPTER_CONTEXT_FINGERPRINT_PROFILE = "contract_v1_h4_empty_adapter_context"
NUMERIC_RECONCILIATION_TOLERANCE_MINUTES = 1e-9
ANALYTICAL_BLOCK_MEMBERSHIP_CONVENTION = "half_open"
RUNTIME_LOCK_MODE = "fixed_by_source_trip"
TURNAROUND_APPLICATION_MODE = "arrival_terminal_specific"


class ScheduleProblemError(ValueError):
    """Raised when a canonical Schedule Problem cannot be proven valid."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        codes: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code or (codes[0] if codes else None)
        self.codes = codes or ((code,) if code is not None else ())


def jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def empty_adapter_context_fingerprint() -> str:
    return canonical_sha256({"fingerprint_profile": (EMPTY_ADAPTER_CONTEXT_FINGERPRINT_PROFILE)})


def _scenario_source_identity(scenario) -> dict[str, str]:
    return {
        "source_type": scenario.source_metadata.source_type.value,
        "source_id": scenario.source_metadata.source_id,
    }


def build_operating_parameter_locks_v1(
    scenario_b: ScenarioBInput,
    source_b_fingerprint: str,
    *,
    direction_trip_lock_mode: DirectionTripLockMode,
    fleet_constraint_mode: FleetConstraintMode,
    initial_fleet_positioning_mode: InitialFleetPositioningMode,
    adapter_operating_lock_values: Mapping[str, object] | None = None,
) -> tuple[OperatingParameterLockV1, ...]:
    values: dict[str, object] = {
        "route_id": scenario_b.route_id,
        "route_name": scenario_b.route_name,
        "route_type": scenario_b.route_type.value,
        "terminal_1_name": scenario_b.terminal_1_name,
        "terminal_2_name": scenario_b.terminal_2_name,
        "trip_runtime_minutes": scenario_b.trip_runtime_minutes,
        "runtime_lock_mode": RUNTIME_LOCK_MODE,
        "exact_trip_runtime_minutes_by_source_b_trip_id": {
            trip.trip_id: trip.runtime_minutes
            for trip in sorted(
                scenario_b.exact_timetable,
                key=lambda item: item.trip_id,
            )
        },
        "turnaround_minutes": {
            "terminal_1": scenario_b.turnaround_minutes.terminal_1,
            "terminal_2": scenario_b.turnaround_minutes.terminal_2,
        },
        "turnaround_application_mode": TURNAROUND_APPLICATION_MODE,
        "vehicle_capacity": scenario_b.vehicle_capacity,
        "total_daily_trips": scenario_b.total_daily_trips,
        "trips_by_direction": {
            "outbound": scenario_b.trips_by_direction.outbound,
            "inbound": scenario_b.trips_by_direction.inbound,
        },
        "first_departures": {
            "terminal_1": scenario_b.first_departures.terminal_1,
            "terminal_2": scenario_b.first_departures.terminal_2,
        },
        "last_departures": {
            "terminal_1": scenario_b.last_departures.terminal_1,
            "terminal_2": scenario_b.last_departures.terminal_2,
        },
        "available_fleet_limit": scenario_b.available_fleet_limit,
        "approved_active_fleet": scenario_b.approved_active_fleet,
        "fleet_constraint_mode": fleet_constraint_mode.value,
        "initial_fleet_positioning_mode": (initial_fleet_positioning_mode.value),
        "direction_trip_lock_mode": direction_trip_lock_mode.value,
        "operating_day_type": scenario_b.operating_day_type.value,
    }
    if scenario_b.terminal_occupancy_limits is not None:
        limits = scenario_b.terminal_occupancy_limits
        values["terminal_occupancy_limits"] = {
            "terminal_1": limits.terminal_1,
            "terminal_2": limits.terminal_2,
        }
        values["terminal_occupancy_event_order"] = TERMINAL_OCCUPANCY_EVENT_ORDER
    for field, value in (adapter_operating_lock_values or {}).items():
        if field in values:
            raise ScheduleProblemError(
                f"Adapter lock duplicates canonical lock {field}",
                code="PROBLEM_LOCK_DUPLICATE_FIELD",
            )
        values[field] = value
    return tuple(
        OperatingParameterLockV1(
            field=field,
            value=value,
            source_fingerprint=source_b_fingerprint,
        )
        for field, value in sorted(values.items())
    )


def _lock_payload(lock: OperatingParameterLockV1) -> dict[str, object]:
    return {
        "field": lock.field,
        "value": jsonable(lock.value),
        "locked": lock.locked,
        "source_fingerprint": lock.source_fingerprint,
        "authorized_exception": lock.authorized_exception,
    }


def problem_fingerprint_payload(
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
    requirements = sorted(
        problem.block_requirements,
        key=lambda item: (
            item.direction.value,
            item.block_start,
            item.block_end,
            item.block_id,
        ),
    )
    authorization = problem.direction_redistribution_authorization
    fixed = problem.fixed_initial_fleet
    bounded = problem.bounded_initial_fleet
    payload = {
        "fingerprint_profile": PROBLEM_FINGERPRINT_PROFILE,
        "contract_version": problem.contract_version,
        "source_a_fingerprint": problem.source_a_fingerprint,
        "source_b_fingerprint": problem.source_b_fingerprint,
        "observed_demand_fingerprint": (problem.observed_demand_fingerprint),
        "scenario_a_source_identity": (
            _scenario_source_identity(problem.scenario_a)
            if problem.scenario_a is not None
            else None
        ),
        "scenario_b_source_identity": _scenario_source_identity(problem.scenario_b),
        "evaluation_fingerprint": problem.evaluation_fingerprint,
        "demand_response_mode": (
            problem.demand_response_mode.value if problem.demand_response_mode is not None else None
        ),
        "demand_resolution": (
            demand_resolution_to_contract_dict(problem.demand_resolution)
            if problem.demand_resolution is not None
            else None
        ),
        "analysis_blocks": [demand_analysis_block_to_contract_dict(item) for item in blocks],
        "operating_parameter_locks": [
            _lock_payload(item)
            for item in sorted(
                problem.operating_parameter_locks,
                key=lambda item: item.field,
            )
        ],
        "direction_trip_lock_mode": problem.direction_trip_lock_mode.value,
        "direction_redistribution_authorization": (
            {
                "enabled": authorization.enabled,
                "authorized_by": authorization.authorized_by,
                "directional_demand_confidence": (
                    authorization.directional_demand_confidence.value
                ),
            }
            if authorization is not None
            else None
        ),
        "fleet_constraint_mode": problem.fleet_constraint_mode.value,
        "initial_fleet_positioning_mode": (problem.initial_fleet_positioning_mode.value),
        "fixed_initial_fleet": (
            {
                "terminal_1": fixed.terminal_1,
                "terminal_2": fixed.terminal_2,
            }
            if fixed is not None
            else None
        ),
        "bounded_initial_fleet": (
            {
                "terminal_1": asdict(bounded.terminal_1),
                "terminal_2": asdict(bounded.terminal_2),
            }
            if bounded is not None
            else None
        ),
        "planning_load_factor_ceiling": (problem.planning_load_factor_ceiling),
        "critical_load_factor_ceiling": (problem.critical_load_factor_ceiling),
        "block_requirements": [block_supply_plan_to_contract_dict(item) for item in requirements],
        "boundary_convention": problem.boundary_convention.value,
        "solver_adapter": problem.solver_adapter,
        "adapter_context_fingerprint": (problem.adapter_context_fingerprint),
        "solver_policy": jsonable(asdict(problem.solver_policy)),
    }
    if problem.optimization_mode != ScenarioCOptimizationModeV1.LEGACY_A_BOUND:
        payload["scenario_c_optimization_mode"] = problem.optimization_mode.value
        payload["demand_allocation_authority_mode"] = (
            problem.demand_allocation_authority_mode.value
            if problem.demand_allocation_authority_mode is not None
            else None
        )
    return payload


def calculate_problem_fingerprint(problem: ScheduleProblemV1) -> str:
    return canonical_sha256(problem_fingerprint_payload(problem))


def derive_problem_id(problem_fingerprint: str) -> str:
    return f"PROBLEM-{problem_fingerprint[:16].upper()}"


def _raise_problem_issues(issues) -> None:
    codes = tuple(issue.code for issue in issues)
    raise ScheduleProblemError(
        "Canonical Schedule Problem validation failed: " + ", ".join(codes),
        codes=codes,
    )


def build_schedule_problem_v1(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    *,
    solver_adapter: str,
    adapter_context_fingerprint: str,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    solver_policy: SolverPolicyV1 | None = None,
    direction_trip_lock_mode: DirectionTripLockMode = (DirectionTripLockMode.FIXED_BY_DIRECTION),
    direction_redistribution_authorization: (DirectionRedistributionAuthorizationV1 | None) = None,
    fleet_constraint_mode: FleetConstraintMode = (FleetConstraintMode.AVAILABLE_UPPER_BOUND),
    initial_fleet_positioning_mode: InitialFleetPositioningMode = (
        InitialFleetPositioningMode.SOLVER_DETERMINED
    ),
    fixed_initial_fleet: InitialFleetValuesV1 | None = None,
    bounded_initial_fleet: BoundedInitialFleetV1 | None = None,
    boundary_convention: BoundaryConvention = BoundaryConvention.HALF_OPEN,
    adapter_operating_lock_values: Mapping[str, object] | None = None,
    demand_allocation_authority_mode: DemandAllocationAuthorityModeV1 | None = None,
) -> ScheduleProblemV1:
    effective_policy = evaluation_policy or ScenarioBEvaluationPolicyV1()
    authoritative_evaluation = evaluate_scenario_b_v1(
        normalized_inputs,
        effective_policy,
    )
    authoritative_evaluation_fingerprint = evaluation_fingerprint(
        normalized_inputs,
        authoritative_evaluation,
        effective_policy,
    )
    supplied_evaluation_fingerprint = evaluation_fingerprint(
        normalized_inputs,
        b_evaluation,
        effective_policy,
    )
    if supplied_evaluation_fingerprint != authoritative_evaluation_fingerprint:
        code = "B_EVALUATION_PROVENANCE_MISMATCH"
        raise ScheduleProblemError(
            f"{code}: supplied Scenario B evaluation does not match "
            "the authoritative current evaluation",
            code=code,
        )

    resolution = authoritative_evaluation.demand_resolution
    problem = ScheduleProblemV1(
        problem_id="",
        problem_fingerprint="",
        evaluation_fingerprint=authoritative_evaluation_fingerprint,
        source_a_fingerprint=normalized_inputs.scenario_a_fingerprint,
        source_b_fingerprint=normalized_inputs.scenario_b_fingerprint,
        observed_demand_fingerprint=(normalized_inputs.observed_demand_fingerprint),
        solver_adapter=solver_adapter,
        adapter_context_fingerprint=adapter_context_fingerprint,
        scenario_a=normalized_inputs.scenario_a,
        scenario_b=normalized_inputs.scenario_b,
        demand_response_mode=(
            normalized_inputs.observed_demand.demand_response_mode
            if normalized_inputs.observed_demand is not None
            else None
        ),
        demand_resolution=(resolution.contract if resolution is not None else None),
        analysis_blocks=(tuple(resolution.blocks) if resolution is not None else ()),
        operating_parameter_locks=build_operating_parameter_locks_v1(
            normalized_inputs.scenario_b,
            normalized_inputs.scenario_b_fingerprint,
            direction_trip_lock_mode=direction_trip_lock_mode,
            fleet_constraint_mode=fleet_constraint_mode,
            initial_fleet_positioning_mode=(initial_fleet_positioning_mode),
            adapter_operating_lock_values=adapter_operating_lock_values,
        ),
        direction_trip_lock_mode=direction_trip_lock_mode,
        direction_redistribution_authorization=(direction_redistribution_authorization),
        fleet_constraint_mode=fleet_constraint_mode,
        initial_fleet_positioning_mode=initial_fleet_positioning_mode,
        fixed_initial_fleet=fixed_initial_fleet,
        bounded_initial_fleet=bounded_initial_fleet,
        planning_load_factor_ceiling=(effective_policy.planning_load_factor_ceiling),
        critical_load_factor_ceiling=(effective_policy.critical_load_factor_ceiling),
        block_requirements=tuple(authoritative_evaluation.b_block_supply),
        boundary_convention=boundary_convention,
        solver_policy=solver_policy or SolverPolicyV1(),
        optimization_mode=normalized_inputs.optimization_mode,
        demand_allocation_authority_mode=demand_allocation_authority_mode,
    )
    fingerprint = calculate_problem_fingerprint(problem)
    problem = replace(
        problem,
        problem_fingerprint=fingerprint,
        problem_id=derive_problem_id(fingerprint),
    )
    from .problem_validation import validate_schedule_problem_v1

    validation = validate_schedule_problem_v1(problem)
    if not validation.passed:
        _raise_problem_issues(validation.issues)
    return problem


def build_schedule_generation_context_v1(
    problem: ScheduleProblemV1,
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None,
) -> ScheduleGenerationContextV1:
    effective_policy = evaluation_policy or ScenarioBEvaluationPolicyV1()
    authoritative_evaluation = evaluate_scenario_b_v1(
        normalized_inputs,
        effective_policy,
    )
    if evaluation_fingerprint(
        normalized_inputs,
        b_evaluation,
        effective_policy,
    ) != evaluation_fingerprint(
        normalized_inputs,
        authoritative_evaluation,
        effective_policy,
    ):
        raise ScheduleProblemError(
            "PROBLEM_EVALUATION_FINGERPRINT_MISMATCH: supplied evaluation "
            "does not match current generation-context authority.",
            code="PROBLEM_EVALUATION_FINGERPRINT_MISMATCH",
        )
    context = ScheduleGenerationContextV1(
        problem=problem,
        normalized_inputs=normalized_inputs,
        b_evaluation=authoritative_evaluation,
        evaluation_policy=effective_policy,
        protected_service_floor_enforcement_authority=(
            protected_service_floor_enforcement_authority
            if protected_service_floor_enforcement_authority is not None
            and protected_service_floor_enforcement_authority.has_enforceable_regimes
            else None
        ),
    )
    from .problem_validation import validate_schedule_generation_context_v1

    validation = validate_schedule_generation_context_v1(context)
    if not validation.passed:
        _raise_problem_issues(validation.issues)
    return context
