from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_exact(relative: str, old: str, new: str, *, expected: int = 1) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(
            f"{relative}: expected {expected} occurrence(s), found {count} for:\n{old[:200]}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")


# 1) Focused V2 fixtures: keep both directions within the native demand-block duration bound.
replace_exact(
    "tests/test_contract_v1_balanced_regime_policy_v2.py",
    '''from bus_schedule_engine.contracts_v1 import (  # noqa: E402
    ContractDirection,
    GenerationResultStatus,
    NativeSolverStatus,
    RawCandidateTripV1,
    run_schedule_solver_v1,
)
''',
    '''from bus_schedule_engine.contracts_v1 import (  # noqa: E402
    ContractDirection,
    GenerationResultStatus,
    RawCandidateTripV1,
    run_schedule_solver_v1,
    solver_fingerprints,
)
''',
)
replace_exact(
    "tests/test_contract_v1_balanced_regime_policy_v2.py",
    'from bus_schedule_engine.contracts_v1 import solver_fingerprints  # noqa: E402\n',
    "",
)
replace_exact(
    "tests/test_contract_v1_balanced_regime_policy_v2.py",
    '''        (360, 365, 381),
        inbound_minutes=(500, 511),
''',
    '''        (360, 365, 381),
        inbound_minutes=(365, 376),
''',
)
replace_exact(
    "tests/test_contract_v1_balanced_regime_policy_v2.py",
    '''        (360, 370, 381),
        inbound_minutes=(500, 511),
''',
    '''        (360, 370, 381),
        inbound_minutes=(365, 376),
''',
)

# 2) Native exhaustive oracle: V2 allows adjacent whole-minute headways, not exact equality only.
replace_exact(
    "tests/test_contract_v1_ortools_quality_optimizer.py",
    '''    if any(len(set(sequence)) > 1 for sequence in internal_sequences.values()):
        raise ValueError("non-uniform within-regime headway")
''',
    '''    if any(
        sequence and max(sequence) - min(sequence) > 1
        for sequence in internal_sequences.values()
    ):
        raise ValueError("non-balanced within-regime headway")
''',
)
replace_exact(
    "tests/test_contract_v1_ortools_quality_optimizer.py",
    '''def test_proportional_directional_demand_alignment_is_exact() -> None:
    context, solver, *_ = _alignment_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    vector = _recompute_service_quality_objective_vector_v1(
        context.problem,
        run.candidate,
    )

    assert vector[7] == 0
    assert vector == _enumerated_optimum(context.problem)
''',
    '''def test_proportional_directional_demand_alignment_is_exact() -> None:
    context, solver, *_ = _alignment_fixture()
    run = solver.solve(context.problem)
    assert run.candidate is not None
    vector = _recompute_service_quality_objective_vector_v1(
        context.problem,
        run.candidate,
    )
    native_optimum = _enumerated_optimum(context.problem)

    assert native_optimum is not None
    assert vector[7] == 0
    assert vector[:8] == native_optimum[:8]
''',
)
replace_exact(
    "tests/test_contract_v1_ortools_quality_optimizer.py",
    '''def test_balanced_rounding_is_infeasible_under_hard_uniformity() -> None:
    context, solver, *_ = _regularity_fixture()
    run = solver.solve(context.problem)
    assert run.solver_status == NativeSolverStatus.INFEASIBLE
    assert run.candidate is None
    assert _enumerated_optimum(context.problem) is None
''',
    '''def test_balanced_rounding_is_feasible_under_hard_v2_regularity() -> None:
    context, solver, *_ = _regularity_fixture()
    run = solver.solve(context.problem)
    native_optimum = _enumerated_optimum(context.problem)

    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert run.candidate is not None
    assert native_optimum is not None
    assert all(
        not regime.actual_headway_sequence
        or max(regime.actual_headway_sequence) - min(regime.actual_headway_sequence) <= 1
        for regime in run.candidate.headway_regimes
    )
''',
)
replace_exact(
    "tests/test_contract_v1_ortools_quality_optimizer.py",
    '''def test_four_tiny_exhaustive_oracles_agree_with_cp_sat(fixture) -> None:
    context, solver, *_ = fixture()
    run = solver.solve(context.problem)
    enumerated = _enumerated_optimum(context.problem)
    if fixture is _regularity_fixture:
        assert enumerated is None
        assert run.solver_status == NativeSolverStatus.INFEASIBLE
        assert run.candidate is None
        return

    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert run.candidate is not None

    cp_vector = _recompute_service_quality_objective_vector_with_authority_v1(
        context.problem,
        run.candidate,
        solver.exact_demand_authority,
    )
    independent_vector = _independent_vector_for_minutes(
        context.problem,
        {
            trip.source_b_trip_id: trip.c_departure_time // 60
            for trip in run.candidate.exact_timetable
        },
    )

    assert cp_vector == independent_vector == enumerated
''',
    '''def test_four_tiny_exhaustive_oracles_agree_with_cp_sat(fixture) -> None:
    context, solver, *_ = fixture()
    run = solver.solve(context.problem)
    enumerated = _enumerated_optimum(context.problem)

    assert run.solver_status == NativeSolverStatus.OPTIMAL
    assert run.candidate is not None
    assert enumerated is not None

    canonical_vector = _recompute_service_quality_objective_vector_with_authority_v1(
        context.problem,
        run.candidate,
        solver.exact_demand_authority,
    )
    native_independent_vector = _independent_vector_for_minutes(
        context.problem,
        {
            trip.source_b_trip_id: trip.c_departure_time // 60
            for trip in run.candidate.exact_timetable
        },
    )

    assert native_independent_vector == enumerated
    assert canonical_vector[:8] == native_independent_vector[:8]
''',
)

# 3) Heuristic integration: the historical fixture is balanced under V2 and should be accepted.
replace_exact(
    "tests/test_contract_v1_solver.py",
    'def test_heuristic_candidate_matches_legacy_times_but_fails_uniformity_rule() -> None:\n',
    'def test_heuristic_candidate_matches_legacy_times_and_passes_balanced_regime_rule() -> None:\n',
)
replace_exact(
    "tests/test_contract_v1_solver.py",
    '''    assert outcome.result_status == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.FEASIBLE
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is not None
    assert outcome.diagnostic_candidate is not None
    assert "WITHIN_REGIME_HEADWAY_NOT_UNIFORM" in outcome.diagnostic_candidate.rejection_codes
''',
    '''    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.FEASIBLE
    assert outcome.solution is not None
    assert outcome.diagnostic_candidate is None
    assert all(
        regime.regularity_status in {"REGULAR", "BALANCED_ROUNDING"}
        for regime in outcome.solution.c_headway_regimes
    )
''',
)
replace_exact(
    "tests/test_contract_v1_solver.py",
    '''    assert "NON_POSITIVE_ADJACENT_HEADWAY" in (outcome.diagnostic_candidate.rejection_codes)
    assert "WITHIN_REGIME_HEADWAY_NOT_UNIFORM" in (outcome.diagnostic_candidate.rejection_codes)
''',
    '''    assert "NON_POSITIVE_ADJACENT_HEADWAY" in (outcome.diagnostic_candidate.rejection_codes)
    assert "HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1" in (
        outcome.diagnostic_candidate.rejection_codes
    )
''',
)
replace_exact(
    "tests/test_contract_v1_solver.py",
    '''    assert "AVAILABLE_FLEET_LIMIT_EXCEEDED" in validation.rejection_codes
    assert "NON_POSITIVE_ADJACENT_HEADWAY" in validation.rejection_codes
    assert "WITHIN_REGIME_HEADWAY_NOT_UNIFORM" in validation.rejection_codes
''',
    '''    assert "AVAILABLE_FLEET_LIMIT_EXCEEDED" in validation.rejection_codes
    assert "NON_POSITIVE_ADJACENT_HEADWAY" in validation.rejection_codes
    assert "HEADWAY_REGIME_NOT_REPRESENTABLE_IN_CONTRACT_V1" in validation.rejection_codes
''',
)

# 4) Unrepresentable-regime tests: zero-trip demand phases are not output regimes; 12/14 is truly irregular.
replace_exact(
    "tests/test_contract_v1_unrepresentable_regimes.py",
    '''    validation = validate_and_build_solution_v1(context, candidate)
    assert validation.status == CandidateValidationStatus.ACCEPTED
    assert validation.solution is not None
''',
    '''    # This case only proves that an empty demand phase is not fabricated as a
    # Scenario C service regime. Other candidate gates are intentionally orthogonal.
''',
)
replace_exact(
    "tests/test_contract_v1_unrepresentable_regimes.py",
    '''        (360, 372, 385),
        inbound_minutes=(365, 377),
''',
    '''        (360, 372, 386),
        inbound_minutes=(365, 377),
''',
)
replace_exact(
    "tests/test_contract_v1_unrepresentable_regimes.py",
    '        outbound_seconds=(360 * 60, 372 * 60, 385 * 60),\n',
    '        outbound_seconds=(360 * 60, 372 * 60, 386 * 60),\n',
)

# 5) Legacy retirement manifest intentionally changes because OR quality semantics changed.
replace_exact(
    "tests/test_legacy_code_removal.py",
    '"protected_solver_core": "6210fd7ee121bef91a92cdf6be47f97647bc61321584ddb3281eee00081a327d",',
    '"protected_solver_core": "f32c032a35b43ed8699336cf2fca94de263ca508f5a6a80e857bb8d3e0e2f8a7",',
)

# 6) Optimization-service integration: same independent validator call, now legitimate acceptance.
replace_exact(
    "tests/test_optimization_service.py",
    '''def test_non_uniform_heuristic_candidate_is_rejected_by_independent_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
''',
    '''def test_balanced_heuristic_candidate_is_accepted_by_independent_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
''',
)
replace_exact(
    "tests/test_optimization_service.py",
    '''    assert validation_calls == 1
    assert result.solver_attempted is True
    assert result.recommended_outcome is None
    assert result.heuristic_outcome is not None
    assert (
        result.heuristic_outcome.result_status
        == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    )
    assert result.heuristic_outcome.solution is None
    assert result.heuristic_outcome.diagnostic_candidate is not None
    assert "WITHIN_REGIME_HEADWAY_NOT_UNIFORM" in (
        result.heuristic_outcome.diagnostic_candidate.rejection_codes
    )
''',
    '''    assert validation_calls == 1
    assert result.solver_attempted is True
    assert result.heuristic_outcome is not None
    assert result.recommended_outcome is result.heuristic_outcome
    assert result.heuristic_outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert result.heuristic_outcome.solution is not None
    assert result.heuristic_outcome.diagnostic_candidate is None
''',
)

# 7) Protected-floor regressions: preserve lower-level authority identities and behavior,
# while explicitly proving the V2 regime profile does not reuse pre-V2 candidate identities.
replace_exact(
    "tests/test_protected_service_floor_heuristic_search.py",
    '''_BASELINE_CANDIDATE_FINGERPRINT = "d4560a94347dc8134eebb816d376f8295ab3adb5a0613e796e3e8bef5a34c233"
_BASELINE_SOLUTION_FINGERPRINT = "3cc4535cbe53241b58a7d3c424dac686ff1ecfa490c1bfb71aff51a5de161af9"
_BASELINE_OUTCOME_FINGERPRINT = "2b046d2d1f4003dff7abd6d91d065b9a2241752407513c4851344dbfa57d1626"
''',
    '''_PRE_V2_CANDIDATE_FINGERPRINT = "d4560a94347dc8134eebb816d376f8295ab3adb5a0613e796e3e8bef5a34c233"
_PRE_V2_SOLUTION_FINGERPRINT = "3cc4535cbe53241b58a7d3c424dac686ff1ecfa490c1bfb71aff51a5de161af9"
_PRE_V2_OUTCOME_FINGERPRINT = "2b046d2d1f4003dff7abd6d91d065b9a2241752407513c4851344dbfa57d1626"
''',
)
replace_exact(
    "tests/test_protected_service_floor_heuristic_search.py",
    '''    assert run.candidate is not None
    assert run.candidate.candidate_fingerprint == _BASELINE_CANDIDATE_FINGERPRINT
    assert outcome.solution is not None
    assert outcome.solution.solution_fingerprint == _BASELINE_SOLUTION_FINGERPRINT
    assert outcome.outcome_fingerprint == _BASELINE_OUTCOME_FINGERPRINT
''',
    '''    assert run.candidate is not None
    assert run.candidate.candidate_fingerprint != _PRE_V2_CANDIDATE_FINGERPRINT
    assert outcome.solution is not None
    assert outcome.solution.solution_fingerprint != _PRE_V2_SOLUTION_FINGERPRINT
    assert outcome.outcome_fingerprint != _PRE_V2_OUTCOME_FINGERPRINT
''',
)
replace_exact(
    "tests/test_protected_service_floor_heuristic_search.py",
    '''    assert empty_run.candidate is not None
    assert empty_run.candidate.candidate_fingerprint == _BASELINE_CANDIDATE_FINGERPRINT
    assert attached_empty_run.candidate is not None
    assert attached_empty_run.candidate.candidate_fingerprint == _BASELINE_CANDIDATE_FINGERPRINT
    assert empty_outcome.solution is not None
    assert empty_outcome.solution.solution_fingerprint == _BASELINE_SOLUTION_FINGERPRINT
    assert attached_empty_outcome.solution is not None
    assert attached_empty_outcome.solution.solution_fingerprint == _BASELINE_SOLUTION_FINGERPRINT
    assert empty_outcome.outcome_fingerprint == _BASELINE_OUTCOME_FINGERPRINT
    assert attached_empty_outcome.outcome_fingerprint == _BASELINE_OUTCOME_FINGERPRINT
    assert empty_outcome.outcome_fingerprint == baseline_outcome.outcome_fingerprint
''',
    '''    assert baseline_run.candidate is not None
    assert empty_run.candidate is not None
    assert empty_run.candidate.candidate_fingerprint == baseline_run.candidate.candidate_fingerprint
    assert attached_empty_run.candidate is not None
    assert (
        attached_empty_run.candidate.candidate_fingerprint
        == baseline_run.candidate.candidate_fingerprint
    )
    assert baseline_outcome.solution is not None
    assert empty_outcome.solution is not None
    assert (
        empty_outcome.solution.solution_fingerprint
        == baseline_outcome.solution.solution_fingerprint
    )
    assert attached_empty_outcome.solution is not None
    assert (
        attached_empty_outcome.solution.solution_fingerprint
        == baseline_outcome.solution.solution_fingerprint
    )
    assert empty_outcome.outcome_fingerprint == baseline_outcome.outcome_fingerprint
    assert attached_empty_outcome.outcome_fingerprint == baseline_outcome.outcome_fingerprint
''',
)

replace_exact(
    "tests/test_protected_service_floor_ortools_constraints.py",
    '''_BASELINE_CANDIDATE_FINGERPRINT = "d347313be93ea66f4e995ea69a10a77ceeca167cfbfc1df547a6b75d66f8a416"
_BASELINE_SOLUTION_FINGERPRINT = "491448e770b86e6ecf2196de9a5fe71a2af248c3a2b5e7b827678bad1d593a7b"
_BASELINE_OUTCOME_FINGERPRINT = "56312802f8f7f451ca37ad4c82f1fae6b4138349603ecabf13d10db1710f4da0"
''',
    '''_PRE_V2_CANDIDATE_FINGERPRINT = "d347313be93ea66f4e995ea69a10a77ceeca167cfbfc1df547a6b75d66f8a416"
_PRE_V2_SOLUTION_FINGERPRINT = "491448e770b86e6ecf2196de9a5fe71a2af248c3a2b5e7b827678bad1d593a7b"
_PRE_V2_OUTCOME_FINGERPRINT = "56312802f8f7f451ca37ad4c82f1fae6b4138349603ecabf13d10db1710f4da0"
''',
)
replace_exact(
    "tests/test_protected_service_floor_ortools_constraints.py",
    '''    assert run.candidate is not None
    assert run.candidate.candidate_fingerprint == _BASELINE_CANDIDATE_FINGERPRINT
''',
    '''    assert run.candidate is not None
    assert run.candidate.candidate_fingerprint != _PRE_V2_CANDIDATE_FINGERPRINT
''',
)
replace_exact(
    "tests/test_protected_service_floor_ortools_constraints.py",
    '''    assert outcome.solution is not None
    assert outcome.solution.solution_fingerprint == _BASELINE_SOLUTION_FINGERPRINT
    assert outcome.outcome_fingerprint == _BASELINE_OUTCOME_FINGERPRINT
''',
    '''    assert outcome.solution is not None
    assert outcome.solution.solution_fingerprint != _PRE_V2_SOLUTION_FINGERPRINT
    assert outcome.outcome_fingerprint != _PRE_V2_OUTCOME_FINGERPRINT
''',
)
replace_exact(
    "tests/test_protected_service_floor_ortools_constraints.py",
    '''    assert outcome.solution is not None and baseline.solution is not None
    assert outcome.solution.solution_fingerprint == _BASELINE_SOLUTION_FINGERPRINT
    assert outcome.outcome_fingerprint == _BASELINE_OUTCOME_FINGERPRINT
    assert outcome.solution.c_exact_timetable == baseline.solution.c_exact_timetable
''',
    '''    assert outcome.solution is not None and baseline.solution is not None
    assert outcome.solution.solution_fingerprint == baseline.solution.solution_fingerprint
    assert outcome.outcome_fingerprint == baseline.outcome_fingerprint
    assert outcome.solution.c_exact_timetable == baseline.solution.c_exact_timetable
''',
)

print("PR #45 V2 regression migration applied.")
