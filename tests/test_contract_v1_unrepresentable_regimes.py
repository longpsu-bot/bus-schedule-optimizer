from __future__ import annotations

import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_contract_v1_exact_demand_uniform_headways import (  # noqa: E402
    _raw_candidate_for_seconds,
    _refingerprint,
    _single_regime_fixture,
)
from test_contract_v1_ortools_demand_optimizer import _record  # noqa: E402
from test_contract_v1_ortools_quality_optimizer import (  # noqa: E402
    _quality_request,
    _two_regime_fixture,
)

from bus_schedule_engine.contracts_v1 import (  # noqa: E402
    CandidateValidationStatus,
    ContractDirection,
    GenerationResultStatus,
    NativeSolverStatus,
    RejectedCandidateDiagnosticV1,
    SolverExecutionStatus,
    SolverRunResultV1,
    run_schedule_solver_v1,
    validate_and_build_solution_v1,
)
from bus_schedule_engine.contracts_v1.regime_headway_policy import (  # noqa: E402
    HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1,
    SCENARIO_C_REPRESENTABLE_REGIME_STATUSES,
    _analyze_regime_headways,
)
from bus_schedule_engine.contracts_v1.serialization import canonical_sha256  # noqa: E402
from bus_schedule_engine.contracts_v1.solver_fingerprints import (  # noqa: E402
    solution_fingerprint_payload,
)
from bus_schedule_engine.contracts_v1.solver_validation import (  # noqa: E402
    _solution_headway_regime_integrity_errors,
)
from bus_schedule_engine.models import Direction  # noqa: E402
from bus_schedule_engine.optimization_comparison import (  # noqa: E402
    compare_solver_outcomes_v1,
)
from bus_schedule_engine.optimization_service import SolverChoice  # noqa: E402


class _StaticSolver:
    def __init__(self, run: SolverRunResultV1) -> None:
        self.adapter_id = run.solver_adapter
        self._run = run

    def solve(self, problem):
        return self._run


def _one_trip_case():
    context, _ = _single_regime_fixture((360,), inbound_minutes=(365,))
    candidate, policy = _raw_candidate_for_seconds(
        context.problem,
        outbound_seconds=(360 * 60,),
        inbound_seconds=(365 * 60,),
    )
    return context, candidate, policy


def _zero_trip_phase_case():
    context, *_ = _quality_request(
        outbound_minutes=(360, 390),
        inbound_minutes=(365, 395),
        outbound_runtimes=(1, 1),
        inbound_runtimes=(1, 1),
        fleet_limit=4,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 370, 10),
            _record(Direction.TERMINAL_1_TO_2, 370, 380, 100),
            _record(Direction.TERMINAL_1_TO_2, 380, 391, 200),
            _record(Direction.TERMINAL_2_TO_1, 365, 375, 10),
            _record(Direction.TERMINAL_2_TO_1, 375, 385, 100),
            _record(Direction.TERMINAL_2_TO_1, 385, 396, 200),
        ),
        route_id="ZERO-TRIP-DEMAND-PHASE-NOT-SERVICE-REGIME",
    )
    candidate, policy = _raw_candidate_for_seconds(
        context.problem,
        outbound_seconds=(360 * 60, 390 * 60),
        inbound_seconds=(365 * 60, 395 * 60),
    )
    return context, candidate, policy


@pytest.fixture(scope="module")
def accepted_case():
    context, solver, *_ = _two_regime_fixture()
    outcome = run_schedule_solver_v1(context, solver)
    assert outcome.solution is not None
    return context, solver, outcome


def test_one_trip_regime_is_not_fabricated_and_is_rejected() -> None:
    context, candidate, policy = _one_trip_case()
    analyses = policy.analyses

    assert analyses
    assert {analysis.status for analysis in analyses} == {"SINGLE_TRIP_HEADWAY_NOT_MEASURABLE"}
    assert all(not analysis.headway_measurable for analysis in analyses)
    assert candidate.headway_regimes == ()
    assert all(analysis.target_headway is None for analysis in analyses)
    assert "WITHIN_REGIME_HEADWAY_NOT_UNIFORM" not in policy.error_codes

    validation = validate_and_build_solution_v1(context, candidate)
    assert validation.status == CandidateValidationStatus.REJECTED
    assert validation.rejection_codes == (HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1,)
    assert validation.solution is None


def test_zero_trip_demand_phase_is_not_promoted_to_service_regime() -> None:
    context, candidate, policy = _zero_trip_phase_case()

    assert all(analysis.status != "NO_TRIPS" for analysis in policy.analyses)
    assert all(
        analysis.status in SCENARIO_C_REPRESENTABLE_REGIME_STATUSES
        for analysis in policy.analyses
    )
    assert all(analysis.headway_measurable for analysis in policy.analyses)
    assert all(regime.target_headway > 0 for regime in candidate.headway_regimes)
    assert "WITHIN_REGIME_HEADWAY_NOT_UNIFORM" not in policy.error_codes

    validation = validate_and_build_solution_v1(context, candidate)
    assert validation.status == CandidateValidationStatus.ACCEPTED
    assert validation.solution is not None


def test_invalid_non_uniform_retains_both_distinct_rejection_codes() -> None:
    context, _ = _single_regime_fixture(
        (360, 372, 385),
        inbound_minutes=(365, 377),
    )
    candidate, policy = _raw_candidate_for_seconds(
        context.problem,
        outbound_seconds=(360 * 60, 372 * 60, 385 * 60),
        inbound_seconds=(365 * 60, 377 * 60),
    )
    outbound = next(
        analysis
        for analysis in policy.analyses
        if analysis.regime.direction == ContractDirection.OUTBOUND
    )
    validation = validate_and_build_solution_v1(context, candidate)

    assert outbound.status == "INVALID_NON_UNIFORM"
    assert "WITHIN_REGIME_HEADWAY_NOT_UNIFORM" in validation.rejection_codes
    assert HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1 in validation.rejection_codes
    assert "balanced rounding" in validation.summary


def test_measurable_uniform_regimes_remain_accepted() -> None:
    context, solver = _single_regime_fixture(
        (360, 372),
        inbound_minutes=(365, 377),
    )
    outcome = run_schedule_solver_v1(context, solver)

    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solution is not None
    assert {regime.target_headway for regime in outcome.solution.c_headway_regimes} == {12.0}


def test_two_measurable_regimes_with_different_headways_remain_accepted(
    accepted_case,
) -> None:
    _, _, outcome = accepted_case
    outbound = [
        regime
        for regime in outcome.solution.c_headway_regimes
        if regime.direction == ContractDirection.OUTBOUND
    ]
    assert len(outbound) == 2
    assert {regime.target_headway for regime in outbound} == {2.0, 4.0}


def test_accepted_solution_has_complete_authoritative_referential_integrity(
    accepted_case,
) -> None:
    context, _, outcome = accepted_case
    solution = outcome.solution
    policy = _analyze_regime_headways(
        context.problem,
        solution.c_exact_timetable,
        enforce_candidate_labels=True,
    )
    authority_ids = frozenset(
        analysis.regime.regime_id
        for analysis in policy.analyses
        if analysis.headway_measurable
        and analysis.status in SCENARIO_C_REPRESENTABLE_REGIME_STATUSES
    )
    emitted_counts = Counter(regime.regime_id for regime in solution.c_headway_regimes)
    trip_counts = Counter(trip.headway_regime_id for trip in solution.c_exact_timetable)

    assert frozenset(emitted_counts) == authority_ids
    assert frozenset(trip_counts) == authority_ids
    assert set(emitted_counts.values()) == {1}
    assert all(trip_counts[regime_id] > 0 for regime_id in authority_ids)
    assert (
        _solution_headway_regime_integrity_errors(
            solution.c_exact_timetable,
            solution.c_headway_regimes,
            authoritative_regime_ids=authority_ids,
        )
        == ()
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        (
            lambda solution: (
                solution.c_exact_timetable,
                (*solution.c_headway_regimes, solution.c_headway_regimes[0]),
            ),
            "SOLUTION_HEADWAY_REGIME_REFERENCE_DUPLICATE",
        ),
        (
            lambda solution: (
                solution.c_exact_timetable,
                solution.c_headway_regimes[1:],
            ),
            "SOLUTION_HEADWAY_REGIME_REFERENCE_MISSING",
        ),
        (
            lambda solution: (
                solution.c_exact_timetable,
                (
                    *solution.c_headway_regimes,
                    replace(solution.c_headway_regimes[0], regime_id="ORPHAN-REGIME"),
                ),
            ),
            "SOLUTION_HEADWAY_REGIME_ORPHANED",
        ),
        (
            lambda solution: (
                solution.c_exact_timetable,
                (
                    replace(
                        solution.c_headway_regimes[0],
                        direction=(
                            ContractDirection.INBOUND
                            if solution.c_headway_regimes[0].direction == ContractDirection.OUTBOUND
                            else ContractDirection.OUTBOUND
                        ),
                    ),
                    *solution.c_headway_regimes[1:],
                ),
            ),
            "SOLUTION_HEADWAY_REGIME_DIRECTION_MISMATCH",
        ),
    ),
)
def test_solution_integrity_check_rejects_corrupt_regime_graph(
    accepted_case,
    mutation,
    expected_code,
) -> None:
    _, _, outcome = accepted_case
    solution = outcome.solution
    trips, regimes = mutation(solution)
    authority_ids = frozenset(regime.regime_id for regime in solution.c_headway_regimes)

    errors = _solution_headway_regime_integrity_errors(
        trips,
        regimes,
        authoritative_regime_ids=authority_ids,
    )
    assert expected_code in errors


def test_fake_candidate_regime_id_cannot_bypass_authority(accepted_case) -> None:
    context, solver, _ = accepted_case
    run = solver.solve(context.problem)
    assert run.candidate is not None
    first = run.candidate.exact_timetable[0]
    corrupted = replace(
        run.candidate,
        exact_timetable=(
            replace(first, headway_regime_id="FAKE-AUTHORITY"),
            *run.candidate.exact_timetable[1:],
        ),
    )
    validation = validate_and_build_solution_v1(
        context,
        _refingerprint(context.problem, corrupted),
    )
    assert "HEADWAY_REGIME_AUTHORITY_MISMATCH" in validation.rejection_codes
    assert validation.solution is None


def test_solution_fingerprint_includes_legitimate_regime_content(accepted_case) -> None:
    context, _, outcome = accepted_case
    solution = outcome.solution
    changed = replace(
        solution,
        c_headway_regimes=(
            replace(
                solution.c_headway_regimes[0],
                transition_headways=(
                    *solution.c_headway_regimes[0].transition_headways,
                    999,
                ),
            ),
            *solution.c_headway_regimes[1:],
        ),
    )
    original_fingerprint = canonical_sha256(
        solution_fingerprint_payload(
            solution,
            problem_fingerprint=context.problem.problem_fingerprint,
        )
    )
    changed_fingerprint = canonical_sha256(
        solution_fingerprint_payload(
            changed,
            problem_fingerprint=context.problem.problem_fingerprint,
        )
    )
    assert changed_fingerprint != original_fingerprint


@pytest.mark.parametrize(
    "native_status",
    (NativeSolverStatus.FEASIBLE, NativeSolverStatus.OPTIMAL),
)
def test_native_candidate_is_validator_rejected_without_solution_or_vector(
    native_status,
) -> None:
    context, candidate, _ = _one_trip_case()
    candidate = replace(candidate, solver_status=native_status)
    run = SolverRunResultV1(
        execution_status=SolverExecutionStatus.COMPLETED,
        solver_status=native_status,
        solver_adapter=candidate.solver_adapter,
        solve_duration_seconds=0.0,
        candidate=candidate,
        explanations=("Native solver found a mathematical candidate.",),
        limitations=(),
    )
    outcome = run_schedule_solver_v1(context, _StaticSolver(run))

    assert outcome.result_status == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    assert outcome.solver_status == native_status
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is not None
    assert HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1 in (
        outcome.diagnostic_candidate.rejection_codes
    )
    assert any(
        HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1 in limitation
        for limitation in outcome.limitations
    )


def _rejected_copy(outcome, *, adapter: str):
    return replace(
        outcome,
        result_status=GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR,
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter=adapter,
        solution=None,
        diagnostic_candidate=RejectedCandidateDiagnosticV1(
            candidate_fingerprint="a" * 64,
            rejection_codes=(HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1,),
            summary="Unrepresentable authoritative regime.",
        ),
    )


def test_both_excludes_unrepresentable_candidates_and_preserves_one_accepted_rules(
    accepted_case,
) -> None:
    context, solver, accepted_ortools = accepted_case
    accepted_heuristic = replace(
        accepted_ortools,
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter="legacy_heuristic_v1",
    )
    rejected_heuristic = _rejected_copy(
        accepted_ortools,
        adapter="legacy_heuristic_v1",
    )
    rejected_ortools = _rejected_copy(
        accepted_ortools,
        adapter="ortools_cp_sat_quality_v1",
    )
    authority = solver.exact_demand_authority

    only_ortools = compare_solver_outcomes_v1(
        context.problem,
        rejected_heuristic,
        accepted_ortools,
        exact_demand_authority=authority,
    )
    only_heuristic = compare_solver_outcomes_v1(
        context.problem,
        accepted_heuristic,
        rejected_ortools,
        exact_demand_authority=authority,
    )
    neither = compare_solver_outcomes_v1(
        context.problem,
        rejected_heuristic,
        rejected_ortools,
        exact_demand_authority=authority,
    )

    assert only_ortools.heuristic_vector is None
    assert only_ortools.reason_code == "ONLY_ORTOOLS_ACCEPTED"
    assert only_ortools.recommended_solver == SolverChoice.OR_TOOLS
    assert only_heuristic.ortools_vector is None
    assert only_heuristic.reason_code == "ONLY_HEURISTIC_ACCEPTED"
    assert only_heuristic.recommended_solver == SolverChoice.HEURISTIC
    assert neither.heuristic_vector is None
    assert neither.ortools_vector is None
    assert neither.reason_code == "NO_ACCEPTED_SOLUTION"
    assert neither.recommended_solver is None
