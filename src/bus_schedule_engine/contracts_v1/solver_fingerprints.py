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

CANDIDATE_FINGERPRINT_PROFILE = "contract_v1_h1_candidate"
SOLUTION_FINGERPRINT_PROFILE = "contract_v1_h1_solution"
OUTCOME_FINGERPRINT_PROFILE = "contract_v1_h1_outcome"
_SCENARIO_C_BALANCED_REGIME_ADAPTERS = frozenset(
    {
        "legacy_heuristic_v1",
        "ortools_cp_sat_quality_v1",
    }
)


def _scenario_c_regime_policy_profile(solver_adapter: str) -> str | None:
    if solver_adapter in _SCENARIO_C_BALANCED_REGIME_ADAPTERS:
        return SCENARIO_C_BALANCED_REGIME_POLICY_PROFILE
    return None


def candidate_fingerprint(
    *,
    problem_fingerprint: str,
    solver_adapter: str,
    exact_timetable: tuple[RawCandidateTripV1, ...],
    headway_regimes: tuple[RawHeadwayRegimeV1, ...],
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
    return canonical_sha256(payload)


def solution_fingerprint_payload(
    solution: ScheduleSolutionV1,
    *,
    problem_fingerprint: str,
) -> dict[str, object]:
    payload = jsonable(asdict(solution))
    payload.pop("solution_fingerprint", None)
    payload.pop("solve_duration_seconds", None)
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
