"""Transparent comparison of independently validated optimization outcomes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .contracts_v1 import (
    SERVICE_QUALITY_OBJECTIVE_NAMES_V1,
    GenerationResultStatus,
    NativeSolverStatus,
    ScheduleGenerationOutcomeV1,
    ScheduleProblemV1,
    ScheduleSolutionV1,
    recompute_service_quality_objective_vector_v1,
)
from .contracts_v1.exact_demand_authority import _ExactDemandAuthority
from .contracts_v1.regime_headway_policy import (
    SCENARIO_C_REPRESENTABLE_REGIME_STATUSES,
    _analyze_regime_headways,
    _headway_regime_representability_error_codes,
    _RegimeHeadwayPolicyError,
)
from .contracts_v1.service_quality_metrics import (
    _recompute_service_quality_objective_vector_with_authority_v1,
)

if TYPE_CHECKING:
    from .optimization_service import SolverChoice


@dataclass(frozen=True, slots=True)
class SolverComparisonV1:
    objective_names: tuple[str, ...]
    heuristic_vector: tuple[int, ...] | None
    ortools_vector: tuple[int, ...] | None
    recommended_solver: SolverChoice | None
    reason_code: str
    explanation: str


def _verify_outcome_source(
    problem: ScheduleProblemV1,
    outcome: ScheduleGenerationOutcomeV1,
    *,
    label: str,
) -> None:
    if outcome.source_b_fingerprint != problem.source_b_fingerprint:
        raise ValueError(
            "SOURCE_B_FINGERPRINT_MISMATCH: "
            f"{label} outcome does not bind the common comparison problem"
        )
    if (
        outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
        and outcome.solution is not None
        and outcome.solution.source_b_fingerprint != problem.source_b_fingerprint
    ):
        raise ValueError(
            "SOURCE_B_FINGERPRINT_MISMATCH: "
            f"{label} accepted solution does not bind the common comparison problem"
        )


def _eligible_solution(
    outcome: ScheduleGenerationOutcomeV1,
) -> ScheduleSolutionV1 | None:
    if (
        outcome.result_status != GenerationResultStatus.SOLUTION_ACCEPTED
        or outcome.solution is None
    ):
        return None
    return outcome.solution


def _numeric_equal(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-9)


def _canonical_solution_regimes_are_current(
    problem: ScheduleProblemV1,
    solution: ScheduleSolutionV1,
) -> bool:
    if problem.solver_adapter not in {
        "legacy_heuristic_v1",
        "ortools_cp_sat_quality_v1",
    }:
        return True
    try:
        policy = _analyze_regime_headways(
            problem,
            solution.c_exact_timetable,
            enforce_candidate_labels=True,
        )
    except _RegimeHeadwayPolicyError:
        return False
    if policy.error_codes or _headway_regime_representability_error_codes(policy):
        return False

    canonical = {
        analysis.regime.regime_id: analysis
        for analysis in policy.analyses
        if analysis.status in SCENARIO_C_REPRESENTABLE_REGIME_STATUSES
    }
    emitted = {regime.regime_id: regime for regime in solution.c_headway_regimes}
    if len(emitted) != len(solution.c_headway_regimes) or set(emitted) != set(canonical):
        return False
    trip_by_id = {trip.c_trip_id: trip for trip in solution.c_exact_timetable}
    for regime_id, analysis in canonical.items():
        regime = emitted[regime_id]
        if not analysis.trip_ids or analysis.target_headway is None:
            return False
        members = tuple(trip_by_id[trip_id] for trip_id in analysis.trip_ids)
        expected_transitions = tuple(
            value
            for value in (
                analysis.transition_headway_before,
                analysis.transition_headway_after,
            )
            if value is not None
        )
        if (
            regime.direction != analysis.regime.direction
            or regime.start_time != members[0].c_departure_time
            or regime.end_time != members[-1].c_departure_time
            or regime.trip_count != len(members)
            or regime.actual_headway_sequence != analysis.internal_headways
            or regime.transition_headways != expected_transitions
            or not _numeric_equal(regime.target_headway, analysis.target_headway)
        ):
            return False
    return True


def _eligible_vector(
    problem: ScheduleProblemV1,
    solution: ScheduleSolutionV1 | None,
    exact_demand_authority: _ExactDemandAuthority | None,
) -> tuple[int, ...] | None:
    if solution is None or not _canonical_solution_regimes_are_current(problem, solution):
        return None
    try:
        return (
            recompute_service_quality_objective_vector_v1(problem, solution)
            if exact_demand_authority is None
            else _recompute_service_quality_objective_vector_with_authority_v1(
                problem,
                solution,
                exact_demand_authority,
            )
        )
    except (TypeError, ValueError):
        return None


def _first_difference(
    heuristic_vector: tuple[int, ...] | None,
    ortools_vector: tuple[int, ...] | None,
) -> str:
    if heuristic_vector is None or ortools_vector is None or heuristic_vector == ortools_vector:
        return "none"
    for name, heuristic_value, ortools_value in zip(
        SERVICE_QUALITY_OBJECTIVE_NAMES_V1,
        heuristic_vector,
        ortools_vector,
        strict=True,
    ):
        if heuristic_value != ortools_value:
            return f"{name}: heuristic={heuristic_value}, OR-Tools={ortools_value}"
    raise AssertionError("Differing objective vectors have no differing objective")


def _comparison_explanation(
    *,
    heuristic_vector: tuple[int, ...] | None,
    ortools_vector: tuple[int, ...] | None,
    recommended_solver: SolverChoice | None,
    reason_code: str,
    ortools_optimality_proven: bool,
) -> str:
    selected = recommended_solver.value if recommended_solver is not None else "none"
    first_difference = _first_difference(heuristic_vector, ortools_vector)
    proof_text = "yes" if ortools_optimality_proven else "no"
    qualification = ""
    if (
        recommended_solver is not None
        and recommended_solver.value == "OR_TOOLS"
        and reason_code == "ORTOOLS_VECTOR_BETTER"
        and not ortools_optimality_proven
    ):
        qualification = (
            " The OR-Tools candidate vector is lexicographically better, "
            "but global optimality was not proven."
        )
    return (
        f"Canonical objectives: {SERVICE_QUALITY_OBJECTIVE_NAMES_V1}. "
        f"Heuristic vector: {heuristic_vector if heuristic_vector is not None else 'not eligible'}. "
        f"OR-Tools vector: {ortools_vector if ortools_vector is not None else 'not eligible'}. "
        f"First differing objective: {first_difference}. "
        f"Selected solver: {selected}. Reason code: {reason_code}. "
        f"OR-Tools optimality proven for an eligible accepted solution: {proof_text}."
        f"{qualification}"
    )


def compare_solver_outcomes_v1(
    problem: ScheduleProblemV1,
    heuristic_outcome: ScheduleGenerationOutcomeV1,
    ortools_outcome: ScheduleGenerationOutcomeV1,
    *,
    exact_demand_authority: _ExactDemandAuthority | None = None,
) -> SolverComparisonV1:
    """Compare eligible accepted solutions under one canonical quality problem."""

    from .optimization_service import SolverChoice

    if len(SERVICE_QUALITY_OBJECTIVE_NAMES_V1) != 15:
        raise ValueError("SERVICE_QUALITY_OBJECTIVE_NAMES_V1 must contain exactly 15 stages")
    _verify_outcome_source(problem, heuristic_outcome, label="heuristic")
    _verify_outcome_source(problem, ortools_outcome, label="OR-Tools")

    heuristic_solution = _eligible_solution(heuristic_outcome)
    ortools_solution = _eligible_solution(ortools_outcome)
    heuristic_vector = _eligible_vector(
        problem,
        heuristic_solution,
        exact_demand_authority,
    )
    ortools_vector = _eligible_vector(
        problem,
        ortools_solution,
        exact_demand_authority,
    )
    ortools_optimality_proven = bool(
        ortools_vector is not None and ortools_outcome.solver_status == NativeSolverStatus.OPTIMAL
    )

    if heuristic_vector is None and ortools_vector is None:
        recommended_solver = None
        reason_code = "NO_ACCEPTED_SOLUTION"
    elif ortools_vector is None:
        recommended_solver = SolverChoice.HEURISTIC
        reason_code = "ONLY_HEURISTIC_ACCEPTED"
    elif heuristic_vector is None:
        recommended_solver = SolverChoice.OR_TOOLS
        reason_code = "ONLY_ORTOOLS_ACCEPTED"
    elif heuristic_vector < ortools_vector:
        recommended_solver = SolverChoice.HEURISTIC
        reason_code = "HEURISTIC_VECTOR_BETTER"
    elif ortools_vector < heuristic_vector:
        recommended_solver = SolverChoice.OR_TOOLS
        reason_code = "ORTOOLS_VECTOR_BETTER"
    elif (
        ortools_outcome.solver_status == NativeSolverStatus.OPTIMAL
        and heuristic_outcome.solver_status != NativeSolverStatus.OPTIMAL
    ):
        recommended_solver = SolverChoice.OR_TOOLS
        reason_code = "EQUAL_VECTOR_ORTOOLS_PROVEN_OPTIMAL"
    else:
        recommended_solver = SolverChoice.HEURISTIC
        reason_code = "EQUAL_VECTOR_HEURISTIC_CONTINUITY"

    return SolverComparisonV1(
        objective_names=SERVICE_QUALITY_OBJECTIVE_NAMES_V1,
        heuristic_vector=heuristic_vector,
        ortools_vector=ortools_vector,
        recommended_solver=recommended_solver,
        reason_code=reason_code,
        explanation=_comparison_explanation(
            heuristic_vector=heuristic_vector,
            ortools_vector=ortools_vector,
            recommended_solver=recommended_solver,
            reason_code=reason_code,
            ortools_optimality_proven=ortools_optimality_proven,
        ),
    )


def comparison_proof_limitations_v1(
    comparison: SolverComparisonV1,
    ortools_outcome: ScheduleGenerationOutcomeV1,
) -> tuple[str, ...]:
    if (
        comparison.ortools_vector is None
        or ortools_outcome.solver_status != NativeSolverStatus.FEASIBLE
    ):
        return ()
    if comparison.reason_code == "ORTOOLS_VECTOR_BETTER":
        return (
            "The independently validated OR-Tools FEASIBLE solution is recommended "
            "because its actual objective vector is lexicographically better, but "
            "global optimality was not proven.",
        )
    return (
        "The independently validated OR-Tools FEASIBLE solution is comparison-eligible, "
        "but global optimality was not proven.",
    )


__all__ = ["SolverComparisonV1"]
