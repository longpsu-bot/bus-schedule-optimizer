from __future__ import annotations

import re
import time
from dataclasses import replace

from bus_schedule_engine.c_generator import (
    HEURISTIC_PROTECTED_FLOOR_AUTHORITY_MISMATCH,
)
from bus_schedule_engine.protected_service_floor_codes import (
    PROTECTED_FLOOR_REJECTION_CODE_ORDER,
)
from bus_schedule_engine.protected_service_floor_enforcement import (
    protected_service_floor_enforcement_authority_is_valid_v1,
)

from .heuristic_context import heuristic_context_mismatch_codes
from .problem_validation import validate_schedule_generation_context_v1
from .serialization import canonical_sha256
from .solver_fingerprints import outcome_fingerprint_payload
from .solver_models import (
    GenerationResultStatus,
    NativeSolverStatus,
    RejectedCandidateDiagnosticV1,
    ScheduleGenerationContextV1,
    ScheduleGenerationOutcomeV1,
    ScheduleProblemV1,
    ScheduleSolver,
    SolverExecutionStatus,
)
from .solver_validation import validate_and_build_solution_v1

_HEADWAY_REGIME_NOT_REPRESENTABLE = "HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1"
_WITHIN_REGIME_HEADWAY_NOT_UNIFORM = "WITHIN_REGIME_HEADWAY_NOT_UNIFORM"
_ENFORCEMENT_FINGERPRINT_PATTERN = re.compile(r"[0-9a-f]{64}")


def _valid_optional_enforcement_fingerprint(value: object) -> bool:
    return value is None or (
        isinstance(value, str) and _ENFORCEMENT_FINGERPRINT_PATTERN.fullmatch(value) is not None
    )


def _is_heuristic_schedule_solver(solver: ScheduleSolver) -> bool:
    from .heuristic_solver import HeuristicScheduleSolverAdapter

    return isinstance(solver, HeuristicScheduleSolverAdapter)


def _heuristic_protected_floor_authority_binding_mismatch(
    context: ScheduleGenerationContextV1,
    solver: ScheduleSolver,
) -> bool:
    if not _is_heuristic_schedule_solver(solver):
        return False

    authority = context.protected_service_floor_enforcement_authority
    if authority is not None and not protected_service_floor_enforcement_authority_is_valid_v1(
        authority,
        context.problem.scenario_b,
    ):
        return True
    native_search_authority = solver.protected_service_floor_enforcement_authority
    if (
        native_search_authority is not None
        and not protected_service_floor_enforcement_authority_is_valid_v1(
            native_search_authority,
            context.problem.scenario_b,
        )
    ):
        return True
    expected_fingerprint = (
        authority.enforcement_fingerprint
        if authority is not None and authority.has_enforceable_regimes
        else None
    )
    native_search_fingerprint = solver.protected_service_floor_enforcement_fingerprint
    compatibility_fingerprint = (
        solver.compatibility_context.protected_service_floor_enforcement_fingerprint
    )
    if not all(
        _valid_optional_enforcement_fingerprint(value)
        for value in (
            expected_fingerprint,
            native_search_fingerprint,
            compatibility_fingerprint,
        )
    ):
        return True
    if not (expected_fingerprint == native_search_fingerprint == compatibility_fingerprint):
        return True
    return "PROBLEM_ADAPTER_CONTEXT_MISMATCH" in heuristic_context_mismatch_codes(
        context.problem,
        solver.compatibility_context,
    )


def _validation_rejection_limitations(
    rejection_codes: tuple[str, ...],
) -> tuple[str, ...]:
    limitations: list[str] = []
    if _HEADWAY_REGIME_NOT_REPRESENTABLE in rejection_codes:
        limitations.append(
            "HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1: an authoritative "
            "zero-trip, one-trip, or invalid non-uniform regime cannot be represented "
            "faithfully in accepted Contract V1 output; no solution was built."
        )
    if _WITHIN_REGIME_HEADWAY_NOT_UNIFORM in rejection_codes:
        limitations.append(
            "WITHIN_REGIME_HEADWAY_NOT_UNIFORM: solved adjacent departures within "
            "at least one authoritative regime do not share one exact headway."
        )
    if any(code in rejection_codes for code in PROTECTED_FLOOR_REJECTION_CODE_ORDER):
        limitations.append(
            "Protected-service-floor acceptance enforcement rejected this solver-produced "
            "candidate. Milestone 6A2B does not prove that no compliant candidate exists."
        )
    return tuple(limitations)


def _finalize_outcome(
    problem: ScheduleProblemV1,
    outcome: ScheduleGenerationOutcomeV1,
) -> ScheduleGenerationOutcomeV1:
    return replace(
        outcome,
        outcome_fingerprint=canonical_sha256(
            outcome_fingerprint_payload(
                outcome,
                problem_fingerprint=problem.problem_fingerprint,
            )
        ),
    )


def _completed_without_solution(
    problem: ScheduleProblemV1,
    *,
    result_status: GenerationResultStatus,
    solver_status: NativeSolverStatus,
    solver_adapter: str,
    solve_duration_seconds: float,
    explanations: tuple[str, ...],
    limitations: tuple[str, ...],
) -> ScheduleGenerationOutcomeV1:
    return _finalize_outcome(
        problem,
        ScheduleGenerationOutcomeV1(
            result_status=result_status,
            execution_status=SolverExecutionStatus.COMPLETED,
            solver_status=solver_status,
            solver_adapter=solver_adapter,
            solve_duration_seconds=solve_duration_seconds,
            outcome_fingerprint="",
            source_b_fingerprint=problem.source_b_fingerprint,
            solution=None,
            diagnostic_candidate=None,
            explanations=explanations,
            limitations=limitations,
        ),
    )


def run_schedule_solver_v1(
    context: ScheduleGenerationContextV1,
    solver: ScheduleSolver,
) -> ScheduleGenerationOutcomeV1:
    problem = context.problem
    context_validation = validate_schedule_generation_context_v1(context)
    is_heuristic_solver = _is_heuristic_schedule_solver(solver)
    heuristic_authority_mismatch = _heuristic_protected_floor_authority_binding_mismatch(
        context,
        solver,
    )
    if not context_validation.passed:
        explanations = tuple(
            f"{issue.code}: generation context rejected." for issue in context_validation.issues
        )
        if heuristic_authority_mismatch:
            explanations = (
                *explanations,
                f"{HEURISTIC_PROTECTED_FLOOR_AUTHORITY_MISMATCH}: generation-context "
                "authority does not match the heuristic native-search binding.",
            )
        return _completed_without_solution(
            problem,
            result_status=(GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID),
            solver_status=NativeSolverStatus.MODEL_INVALID,
            solver_adapter=solver.adapter_id,
            solve_duration_seconds=0.0,
            explanations=explanations,
            limitations=(
                "MODEL_INVALID identifies a problem/context integration defect, "
                "not route, demand, timetable, fleet, or parameter infeasibility.",
            ),
        )
    if solver.adapter_id != problem.solver_adapter:
        return _completed_without_solution(
            problem,
            result_status=(GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID),
            solver_status=NativeSolverStatus.MODEL_INVALID,
            solver_adapter=solver.adapter_id,
            solve_duration_seconds=0.0,
            explanations=(
                "PROBLEM_ADAPTER_CONTEXT_MISMATCH: solver adapter does not "
                "match the canonical problem.",
            ),
            limitations=(
                "MODEL_INVALID identifies an adapter-context or integration "
                "defect, not route, demand, timetable, fleet, or parameter "
                "infeasibility.",
            ),
        )
    if heuristic_authority_mismatch:
        return _completed_without_solution(
            problem,
            result_status=GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,
            solver_status=NativeSolverStatus.MODEL_INVALID,
            solver_adapter=solver.adapter_id,
            solve_duration_seconds=0.0,
            explanations=(
                f"{HEURISTIC_PROTECTED_FLOOR_AUTHORITY_MISMATCH}: generation-context "
                "authority does not match the heuristic native-search binding.",
            ),
            limitations=(
                "MODEL_INVALID identifies a protected-floor authority binding or "
                "integration defect; it supplies no domain-feasibility classification.",
            ),
        )
    validation_context = (
        replace(
            context,
            protected_service_floor_enforcement_authority=None,
        )
        if context.protected_service_floor_enforcement_authority is not None
        and not context.protected_service_floor_enforcement_authority.has_enforceable_regimes
        and is_heuristic_solver
        else context
    )

    started = time.perf_counter()
    try:
        run = solver.solve(problem)
    except Exception:
        elapsed = max(0.0, time.perf_counter() - started)
        return _completed_without_solution(
            problem,
            result_status=GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,
            solver_status=NativeSolverStatus.MODEL_INVALID,
            solver_adapter=solver.adapter_id,
            solve_duration_seconds=elapsed,
            explanations=(
                "SOLVER_ADAPTER_EXCEPTION: Solver adapter raised an exception "
                "before returning a valid result.",
            ),
            limitations=(
                "MODEL_INVALID identifies an adapter or implementation defect, "
                "not route, timetable, fleet, or parameter infeasibility.",
            ),
        )
    if run.execution_status != SolverExecutionStatus.COMPLETED:
        return _completed_without_solution(
            problem,
            result_status=GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,
            solver_status=NativeSolverStatus.MODEL_INVALID,
            solver_adapter=run.solver_adapter,
            solve_duration_seconds=run.solve_duration_seconds,
            explanations=("Solver adapter returned an invalid execution-state combination.",),
            limitations=run.limitations,
        )
    if run.solver_adapter != problem.solver_adapter:
        return _completed_without_solution(
            problem,
            result_status=(GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID),
            solver_status=NativeSolverStatus.MODEL_INVALID,
            solver_adapter=run.solver_adapter,
            solve_duration_seconds=run.solve_duration_seconds,
            explanations=(
                "PROBLEM_ADAPTER_CONTEXT_MISMATCH: solver result adapter does "
                "not match the canonical problem.",
            ),
            limitations=run.limitations,
        )
    if run.solver_status == NativeSolverStatus.MODEL_INVALID:
        return _completed_without_solution(
            problem,
            result_status=GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,
            solver_status=run.solver_status,
            solver_adapter=run.solver_adapter,
            solve_duration_seconds=run.solve_duration_seconds,
            explanations=run.explanations
            or ("Solver adapter reported an invalid model or adapter result.",),
            limitations=run.limitations,
        )
    if run.solver_status == NativeSolverStatus.INFEASIBLE:
        return _completed_without_solution(
            problem,
            result_status=GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS,
            solver_status=run.solver_status,
            solver_adapter=run.solver_adapter,
            solve_duration_seconds=run.solve_duration_seconds,
            explanations=run.explanations,
            limitations=run.limitations,
        )
    if run.solver_status == NativeSolverStatus.UNKNOWN:
        return _completed_without_solution(
            problem,
            result_status=GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT,
            solver_status=run.solver_status,
            solver_adapter=run.solver_adapter,
            solve_duration_seconds=run.solve_duration_seconds,
            explanations=run.explanations,
            limitations=run.limitations,
        )
    if (
        run.candidate is None
        or run.candidate.solver_status != run.solver_status
        or run.candidate.solver_adapter != run.solver_adapter
    ):
        return _completed_without_solution(
            problem,
            result_status=GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,
            solver_status=NativeSolverStatus.MODEL_INVALID,
            solver_adapter=run.solver_adapter,
            solve_duration_seconds=run.solve_duration_seconds,
            explanations=("Solver status and candidate payload are inconsistent.",),
            limitations=run.limitations,
        )

    validation = validate_and_build_solution_v1(validation_context, run.candidate)
    if not validation.passed or validation.solution is None:
        diagnostic = RejectedCandidateDiagnosticV1(
            candidate_fingerprint=run.candidate.candidate_fingerprint,
            rejection_codes=validation.rejection_codes,
            summary=validation.summary,
            protected_service_floor_enforcement_fingerprint=(
                validation.protected_service_floor_validation.enforcement_fingerprint
                if validation.protected_service_floor_validation is not None
                else None
            ),
            protected_service_floor_validation_fingerprint=(
                validation.protected_service_floor_validation.validation_fingerprint
                if validation.protected_service_floor_validation is not None
                else None
            ),
        )
        return _finalize_outcome(
            problem,
            ScheduleGenerationOutcomeV1(
                result_status=(GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR),
                execution_status=run.execution_status,
                solver_status=run.solver_status,
                solver_adapter=run.solver_adapter,
                solve_duration_seconds=run.solve_duration_seconds,
                outcome_fingerprint="",
                source_b_fingerprint=problem.source_b_fingerprint,
                solution=None,
                diagnostic_candidate=diagnostic,
                explanations=run.explanations,
                limitations=tuple(
                    dict.fromkeys(
                        (
                            *run.limitations,
                            *_validation_rejection_limitations(validation.rejection_codes),
                        )
                    )
                ),
                protected_service_floor_enforcement_fingerprint=(
                    validation.protected_service_floor_validation.enforcement_fingerprint
                    if validation.protected_service_floor_validation is not None
                    else None
                ),
                protected_service_floor_validation_fingerprint=(
                    validation.protected_service_floor_validation.validation_fingerprint
                    if validation.protected_service_floor_validation is not None
                    else None
                ),
            ),
        )
    return _finalize_outcome(
        problem,
        ScheduleGenerationOutcomeV1(
            result_status=GenerationResultStatus.SOLUTION_ACCEPTED,
            execution_status=run.execution_status,
            solver_status=run.solver_status,
            solver_adapter=run.solver_adapter,
            solve_duration_seconds=run.solve_duration_seconds,
            outcome_fingerprint="",
            source_b_fingerprint=problem.source_b_fingerprint,
            solution=validation.solution,
            diagnostic_candidate=None,
            explanations=run.explanations,
            limitations=run.limitations,
            protected_service_floor_enforcement_fingerprint=(
                validation.protected_service_floor_validation.enforcement_fingerprint
                if validation.protected_service_floor_validation is not None
                else None
            ),
            protected_service_floor_validation_fingerprint=(
                validation.protected_service_floor_validation.validation_fingerprint
                if validation.protected_service_floor_validation is not None
                else None
            ),
        ),
    )
