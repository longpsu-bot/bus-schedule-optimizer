from __future__ import annotations

from dataclasses import asdict

from .regime_headway_policy import SCENARIO_C_BALANCED_REGIME_POLICY_PROFILE
from .serialization import canonical_sha256
from .solver_models import (
    RawCandidateTripV1,
    RawHeadwayRegimeV1,
    ScheduleGenerationOutcomeV1,
    ScheduleSolutionV1,
)
from .solver_problem import jsonable
from .two_stage_models import SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE

CANDIDATE_FINGERPRINT_PROFILE = "contract_v1_h1_candidate"
SOLUTION_FINGERPRINT_PROFILE = "contract_v1_h1_solution"
OUTCOME_FINGERPRINT_PROFILE = "contract_v1_h1_outcome"
_SCENARIO_C_BALANCED_REGIME_ADAPTERS = frozenset(
    {
        "legacy_heuristic_v1",
        "ortools_cp_sat_quality_v1",
    }
)
_SCENARIO_C_UNIFORM_V3_ADAPTERS = frozenset({"ortools_cp_sat_two_stage_uniform_v1"})


def _scenario_c_regime_policy_profile(solver_adapter: str) -> str | None:
    if solver_adapter in _SCENARIO_C_BALANCED_REGIME_ADAPTERS:
        return SCENARIO_C_BALANCED_REGIME_POLICY_PROFILE
    if solver_adapter in _SCENARIO_C_UNIFORM_V3_ADAPTERS:
        return SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE
    return None


def candidate_fingerprint(
    *,
    problem_fingerprint: str,
    solver_adapter: str,
    exact_timetable: tuple[RawCandidateTripV1, ...],
    headway_regimes: tuple[RawHeadwayRegimeV1, ...],
    allocation_plan_fingerprint: str | None = None,
    optimization_mode: object | None = None,
    demand_allocation_authority_mode: object | None = None,
    final_tail_policy_fingerprint: str | None = None,
) -> str:
    payload: dict[str, object] = {
        "fingerprint_profile": CANDIDATE_FINGERPRINT_PROFILE,
        "problem_fingerprint": problem_fingerprint,
        "solver_adapter": solver_adapter,
        "exact_timetable": jsonable([asdict(item) for item in exact_timetable]),
        "headway_regimes": jsonable([asdict(item) for item in headway_regimes]),
    }
    regime_policy_profile = _scenario_c_regime_policy_profile(solver_adapter)
    if regime_policy_profile is not None:
        payload["scenario_c_regime_policy_profile"] = regime_policy_profile
    if allocation_plan_fingerprint is not None:
        payload["allocation_plan_fingerprint"] = allocation_plan_fingerprint
        payload["scenario_c_optimization_mode"] = jsonable(optimization_mode)
        payload["demand_allocation_authority_mode"] = jsonable(demand_allocation_authority_mode)
        payload["final_tail_policy_fingerprint"] = final_tail_policy_fingerprint
    return canonical_sha256(payload)


def solution_fingerprint_payload(
    solution: ScheduleSolutionV1,
    *,
    problem_fingerprint: str,
) -> dict[str, object]:
    payload = jsonable(asdict(solution))
    payload.pop("solution_fingerprint", None)
    payload.pop("solve_duration_seconds", None)
    for field in (
        "allocation_plan_fingerprint",
        "optimization_mode",
        "demand_allocation_authority_mode",
        "uniform_regime_policy_profile",
        "final_tail_policy_fingerprint",
    ):
        if payload.get(field) is None:
            payload.pop(field, None)
    if payload.get("protected_service_floor_enforcement_fingerprint") is None:
        payload.pop("protected_service_floor_enforcement_fingerprint", None)
    if payload.get("protected_service_floor_validation_fingerprint") is None:
        payload.pop("protected_service_floor_validation_fingerprint", None)
    result: dict[str, object] = {
        "fingerprint_profile": SOLUTION_FINGERPRINT_PROFILE,
        "problem_fingerprint": problem_fingerprint,
        "solution": payload,
    }
    regime_policy_profile = _scenario_c_regime_policy_profile(solution.solver_adapter)
    if regime_policy_profile is not None:
        result["scenario_c_regime_policy_profile"] = regime_policy_profile
    return result


def outcome_fingerprint_payload(
    outcome: ScheduleGenerationOutcomeV1,
    *,
    problem_fingerprint: str,
) -> dict[str, object]:
    payload = jsonable(asdict(outcome))
    payload.pop("outcome_fingerprint", None)
    payload.pop("solve_duration_seconds", None)
    if payload.get("protected_service_floor_enforcement_fingerprint") is None:
        payload.pop("protected_service_floor_enforcement_fingerprint", None)
    if payload.get("protected_service_floor_validation_fingerprint") is None:
        payload.pop("protected_service_floor_validation_fingerprint", None)
    solution = payload.get("solution")
    if isinstance(solution, dict):
        solution.pop("solve_duration_seconds", None)
        for field in (
            "allocation_plan_fingerprint",
            "optimization_mode",
            "demand_allocation_authority_mode",
            "uniform_regime_policy_profile",
            "final_tail_policy_fingerprint",
        ):
            if solution.get(field) is None:
                solution.pop(field, None)
        if solution.get("protected_service_floor_enforcement_fingerprint") is None:
            solution.pop("protected_service_floor_enforcement_fingerprint", None)
        if solution.get("protected_service_floor_validation_fingerprint") is None:
            solution.pop("protected_service_floor_validation_fingerprint", None)
    diagnostic = payload.get("diagnostic_candidate")
    if isinstance(diagnostic, dict):
        if diagnostic.get("protected_service_floor_enforcement_fingerprint") is None:
            diagnostic.pop("protected_service_floor_enforcement_fingerprint", None)
        if diagnostic.get("protected_service_floor_validation_fingerprint") is None:
            diagnostic.pop("protected_service_floor_validation_fingerprint", None)
    result: dict[str, object] = {
        "fingerprint_profile": OUTCOME_FINGERPRINT_PROFILE,
        "problem_fingerprint": problem_fingerprint,
        "outcome": payload,
    }
    regime_policy_profile = _scenario_c_regime_policy_profile(outcome.solver_adapter)
    if regime_policy_profile is not None:
        result["scenario_c_regime_policy_profile"] = regime_policy_profile
    return result
