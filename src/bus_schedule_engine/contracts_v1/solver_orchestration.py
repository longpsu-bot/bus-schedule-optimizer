from __future__ import annotations

import time
from dataclasses import replace

from .demand_coverage import (
    DEMAND_COVERAGE_INCOMPLETE_FOR_C_GENERATION,
    assess_demand_coverage_v1,
)
from .evaluation import BDisposition
from .serialization import canonical_sha256
from .solver_fingerprints import outcome_fingerprint_payload
from .solver_models import (
    GenerationResultStatus,
    NativeSolverStatus,
    RejectedCandidateDiagnosticV1,
    ScheduleGenerationOutcomeV1,
    ScheduleProblemV1,
    ScheduleSolver,
    SolverExecutionStatus,
)
from .solver_validation import validate_and_build_solution_v1


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


def _not_run_outcome(
    problem: ScheduleProblemV1,
    result_status: GenerationResultStatus,
    explanation: str,
    limitations: tuple[str, ...] = (),
) -> ScheduleGenerationOutcomeV1:
    return _finalize_outcome(
        problem,
        ScheduleGenerationOutcomeV1(
            result_status=result_status,
            execution_status=SolverExecutionStatus.NOT_RUN,
            solver_status=None,
            solver_adapter=None,
            solve_duration_seconds=0.0,
            outcome_fingerprint="",
            source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,
            solution=None,
            diagnostic_candidate=None,
            explanations=(explanation,),
            limitations=limitations,
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
            source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,
            solution=None,
            diagnostic_candidate=None,
            explanations=explanations,
            limitations=limitations,
        ),
    )


def run_schedule_solver_v1(
    problem: ScheduleProblemV1,
    solver: ScheduleSolver,
) -> ScheduleGenerationOutcomeV1:
    disposition = problem.b_evaluation.evaluation.disposition
    if disposition == BDisposition.PARAMETERS_INFEASIBLE:
        return _not_run_outcome(
            problem,
            GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS,
            "B's locked parameters were proven infeasible before solver invocation.",
        )
    if disposition == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE:
        return _not_run_outcome(
            problem,
            GenerationResultStatus.C_NOT_REQUIRED_B_SUITABLE,
            "Scenario B is feasible and demand-suitable; no duplicate C is generated.",
        )
    coverage = assess_demand_coverage_v1(
        problem.normalized_inputs,
        minimum_confidence=(problem.evaluation_policy.minimum_authoritative_demand_confidence),
    )
    if not coverage.directional_c_generation_supported:
        return _not_run_outcome(
            problem,
            GenerationResultStatus.C_NOT_GENERATED_INSUFFICIENT_DATA,
            (
                f"{DEMAND_COVERAGE_INCOMPLETE_FOR_C_GENERATION}: "
                "Demand evidence is insufficient for authoritative directional C generation."
            ),
            limitations=coverage.limitations,
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
    if run.solver_status == NativeSolverStatus.MODEL_INVALID:
        return _completed_without_solution(
            problem,
            result_status=GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID,
            solver_status=run.solver_status,
            solver_adapter=run.solver_adapter,
            solve_duration_seconds=run.solve_duration_seconds,
            explanations=("Solver adapter reported an invalid model or adapter result.",),
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

    validation = validate_and_build_solution_v1(problem, run.candidate)
    if not validation.passed or validation.solution is None:
        diagnostic = RejectedCandidateDiagnosticV1(
            candidate_fingerprint=run.candidate.candidate_fingerprint,
            rejection_codes=validation.rejection_codes,
            summary=validation.summary,
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
                source_b_fingerprint=(problem.normalized_inputs.scenario_b_fingerprint),
                solution=None,
                diagnostic_candidate=diagnostic,
                explanations=run.explanations,
                limitations=run.limitations,
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
            source_b_fingerprint=problem.normalized_inputs.scenario_b_fingerprint,
            solution=validation.solution,
            diagnostic_candidate=None,
            explanations=run.explanations,
            limitations=run.limitations,
        ),
    )
