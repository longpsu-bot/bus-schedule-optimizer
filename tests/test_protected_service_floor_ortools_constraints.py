from __future__ import annotations

from dataclasses import replace

import pytest
from ortools.sat.python import cp_model
from test_contract_v1_ortools_quality_optimizer import (
    _OBJECTIVE_NAMES,
    _quality_request,
    _record,
    _regularity_fixture,
    _two_regime_fixture,
)

import bus_schedule_engine.contracts_v1.ortools_quality_solver as quality_module
from bus_schedule_engine.contracts_v1 import (
    CandidateValidationStatus,
    ContractDirection,
    GenerationResultStatus,
    NativeSolverStatus,
    build_ortools_service_quality_request_v1,
    run_schedule_solver_v1,
    validate_and_build_solution_v1,
)
from bus_schedule_engine.contracts_v1.exact_demand_authority import _ExactDemandAuthority
from bus_schedule_engine.contracts_v1.ortools_protected_floor import (
    ORTOOLS_PROTECTED_FLOOR_PROJECTION_INVALID,
    OrToolsProtectedFloorProjectionError,
    build_ortools_protected_floor_projection_v1,
)
from bus_schedule_engine.contracts_v1.ortools_quality_solver import (
    ORTOOLS_PROTECTED_FLOOR_AUTHORITY_MISMATCH,
    ORTOOLS_QUALITY_ADAPTER_CONTEXT_PROFILE,
    _add_protected_floor_constraints,
    _build_quality_cp_sat_model,
    _ortools_quality_adapter_context_fingerprint,
    _recompute_service_quality_objective_vector_with_authority_v1,
)
from bus_schedule_engine.contracts_v1.ortools_solver import (
    _build_demand_cp_sat_model,
    _ordered_directional_trips,
)
from bus_schedule_engine.contracts_v1.serialization import canonical_sha256, scenario_fingerprint
from bus_schedule_engine.models import (
    Direction,
    ProtectedServiceFloorEnforcementAuthorityV1,
    ProtectedServiceFloorEnforcementRegimeV1,
    TripRidershipDirectionV1,
)
from bus_schedule_engine.protected_service_floor_codes import (
    PROTECTED_INTERNAL_HEADWAY_ABOVE_FLOOR,
    PROTECTED_WINDOW_END_VIOLATION,
)
from bus_schedule_engine.protected_service_floor_enforcement import (
    PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
    _authority_fingerprint_payload,
)

_BASELINE_EXACT_DEMAND_FINGERPRINT = (
    "b5aca6282b8fb8b1e4cf8f4d4157249f38619774fc1f533dcec5eb8c5e15ae61"
)
_BASELINE_ADAPTER_CONTEXT_FINGERPRINT = _BASELINE_EXACT_DEMAND_FINGERPRINT
_BASELINE_PROBLEM_FINGERPRINT = "ba382c469cd73bfa18cc84c7a4aa5fa49cd8e22e48fccb575de82d4d4aea7b4e"
_BASELINE_CANDIDATE_FINGERPRINT = "d347313be93ea66f4e995ea69a10a77ceeca167cfbfc1df547a6b75d66f8a416"
_BASELINE_SOLUTION_FINGERPRINT = "491448e770b86e6ecf2196de9a5fe71a2af248c3a2b5e7b827678bad1d593a7b"
_BASELINE_OUTCOME_FINGERPRINT = "56312802f8f7f451ca37ad4c82f1fae6b4138349603ecabf13d10db1710f4da0"
_BASELINE_VECTOR = (0, 0, 0, 0, 0, 4, 6, 4, 0, 0, 2, 2, 4, 9, 3)
_BASELINE_TIMETABLE = (
    ("B-O-01", 21600),
    ("B-I-01", 21720),
    ("B-I-02", 21780),
    ("B-O-02", 21840),
    ("B-O-03", 22080),
    ("B-O-04", 22200),
    ("B-O-05", 22320),
    ("B-O-06", 22440),
)


def _authority_fields(authority: ProtectedServiceFloorEnforcementAuthorityV1) -> dict:
    return {
        "scenario_b_fingerprint": authority.scenario_b_fingerprint,
        "assessment_fingerprint": authority.assessment_fingerprint,
        "policy_fingerprint": authority.policy_fingerprint,
        "regime_derivation_fingerprint": authority.regime_derivation_fingerprint,
        "trip_ridership_input_fingerprint": authority.trip_ridership_input_fingerprint,
        "trip_ridership_analysis_fingerprint": authority.trip_ridership_analysis_fingerprint,
        "target_load_factor": authority.target_load_factor,
        "maximum_load_factor": authority.maximum_load_factor,
        "protected_regimes": authority.protected_regimes,
    }


def _with_regimes(
    authority: ProtectedServiceFloorEnforcementAuthorityV1,
    regimes: tuple[ProtectedServiceFloorEnforcementRegimeV1, ...],
) -> ProtectedServiceFloorEnforcementAuthorityV1:
    fields = _authority_fields(authority)
    fields["protected_regimes"] = regimes
    return ProtectedServiceFloorEnforcementAuthorityV1(
        **fields,
        enforcement_profile=PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
        enforcement_fingerprint=canonical_sha256(_authority_fingerprint_payload(**fields)),
    )


def _authority(
    scenario,
    *,
    outbound_indices: tuple[int, ...] = (1, 2, 3),
    inbound_indices: tuple[int, ...] | None = None,
    tolerance_minutes: int = 0,
    empty: bool = False,
    assessment_fingerprint: str = "a" * 64,
) -> ProtectedServiceFloorEnforcementAuthorityV1:
    regimes: list[ProtectedServiceFloorEnforcementRegimeV1] = []
    for direction, indices, regime_id in (
        (ContractDirection.OUTBOUND, outbound_indices, "OUTBOUND-R01"),
        (ContractDirection.INBOUND, inbound_indices, "INBOUND-R01"),
    ):
        if empty or indices is None:
            continue
        directional = tuple(
            sorted(
                (trip for trip in scenario.exact_timetable if trip.direction == direction),
                key=lambda trip: (trip.departure_time, trip.trip_id),
            )
        )
        members = tuple(directional[index] for index in indices)
        regimes.append(
            ProtectedServiceFloorEnforcementRegimeV1(
                regime_id=regime_id,
                direction=TripRidershipDirectionV1(direction.value),
                ordered_b_trip_ids=tuple(trip.trip_id for trip in members),
                maximum_future_c_headway_minutes=max(
                    later.departure_time - earlier.departure_time
                    for earlier, later in zip(members, members[1:], strict=False)
                )
                // 60,
                minimum_future_c_trip_count=len(members),
                protected_window_start=members[0].departure_time,
                protected_window_end=members[-1].departure_time,
                future_boundary_tolerance_minutes=tolerance_minutes,
                donor_removal_prohibited=True,
            )
        )
    fields = {
        "scenario_b_fingerprint": scenario_fingerprint(scenario),
        "assessment_fingerprint": assessment_fingerprint,
        "policy_fingerprint": "b" * 64,
        "regime_derivation_fingerprint": "c" * 64,
        "trip_ridership_input_fingerprint": "d" * 64 if regimes else None,
        "trip_ridership_analysis_fingerprint": "e" * 64 if regimes else None,
        "target_load_factor": 0.85,
        "maximum_load_factor": 0.90,
        "protected_regimes": tuple(regimes),
    }
    return ProtectedServiceFloorEnforcementAuthorityV1(
        **fields,
        enforcement_profile=PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
        enforcement_fingerprint=canonical_sha256(_authority_fingerprint_payload(**fields)),
    )


def _request(authority=None):
    _, _, normalized, evaluation = _two_regime_fixture()
    context, solver = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        protected_service_floor_enforcement_authority=authority,
    )
    return context, solver, normalized, evaluation


def _protected_request(*, tolerance_minutes: int = 0, indices=(1, 2, 3)):
    _, _, normalized, evaluation = _two_regime_fixture()
    authority = _authority(
        normalized.scenario_b,
        outbound_indices=indices,
        tolerance_minutes=tolerance_minutes,
    )
    context, solver = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        protected_service_floor_enforcement_authority=authority,
    )
    return context, solver, authority


def _hard_model_status(context, solver, authority, departures: dict[str, int]):
    projection = build_ortools_protected_floor_projection_v1(
        authority,
        context.problem.scenario_b,
    )
    demand = _build_demand_cp_sat_model(context.problem)
    _add_protected_floor_constraints(
        demand,
        _ordered_directional_trips(context.problem),
        projection,
    )
    for source_id, minute in departures.items():
        demand.hard.model.add(demand.hard.departure_by_source_id[source_id] == minute)
    native = cp_model.CpSolver().solve(demand.hard.model)
    return native, projection


def _assert_pre_solve_mismatch(outcome) -> None:
    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID
    assert outcome.solver_status == NativeSolverStatus.MODEL_INVALID
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is None
    assert any(ORTOOLS_PROTECTED_FLOOR_AUTHORITY_MISMATCH in item for item in outcome.explanations)
    wording = " ".join((*outcome.explanations, *outcome.limitations)).lower()
    for forbidden in (
        "route infeasibility",
        "timetable infeasibility",
        "fleet infeasibility",
        "policy infeasibility",
        "global infeasibility",
    ):
        assert forbidden not in wording


def test_no_authority_preserves_v2_quality_identity_and_objectives() -> None:
    first_context, first_solver, *_ = _request()
    second_context, second_solver, *_ = _request()
    first_run = first_solver.solve(first_context.problem)
    second_run = second_solver.solve(second_context.problem)
    first_outcome = run_schedule_solver_v1(first_context, first_solver)
    second_outcome = run_schedule_solver_v1(second_context, second_solver)

    assert first_solver.exact_demand_authority.authority_fingerprint == (
        _BASELINE_EXACT_DEMAND_FINGERPRINT
    )
    assert first_context.problem.adapter_context_fingerprint == _BASELINE_ADAPTER_CONTEXT_FINGERPRINT
    assert first_context.problem.problem_fingerprint == _BASELINE_PROBLEM_FINGERPRINT
    assert first_run.solver_status == NativeSolverStatus.OPTIMAL
    assert first_run.candidate is not None and second_run.candidate is not None
    assert first_run.candidate.candidate_fingerprint == second_run.candidate.candidate_fingerprint
    assert (
        tuple(
            (trip.source_b_trip_id, trip.c_departure_time)
            for trip in first_run.candidate.exact_timetable
        )
        == _BASELINE_TIMETABLE
    )
    assert (
        _recompute_service_quality_objective_vector_with_authority_v1(
            first_context.problem,
            first_run.candidate,
            first_solver.exact_demand_authority,
        )
        == _BASELINE_VECTOR
    )
    assert first_outcome.solution is not None and second_outcome.solution is not None
    assert first_outcome.solution.solution_fingerprint == second_outcome.solution.solution_fingerprint
    assert first_outcome.outcome_fingerprint == second_outcome.outcome_fingerprint

def test_valid_empty_authority_preserves_v2_identity_and_model_behavior() -> None:
    baseline_context, baseline_solver, normalized, _ = _request()
    empty = _authority(normalized.scenario_b, empty=True)
    empty_context, empty_solver, *_ = _request(empty)
    baseline = run_schedule_solver_v1(baseline_context, baseline_solver)
    outcome = run_schedule_solver_v1(empty_context, empty_solver)

    assert empty_context.protected_service_floor_enforcement_authority is None
    assert empty_solver.protected_service_floor_enforcement_authority is empty
    assert empty_solver.protected_service_floor_enforcement_fingerprint is None
    assert (
        empty_context.problem.adapter_context_fingerprint == _BASELINE_ADAPTER_CONTEXT_FINGERPRINT
    )
    assert empty_context.problem.problem_fingerprint == _BASELINE_PROBLEM_FINGERPRINT
    assert outcome.solution is not None and baseline.solution is not None
    assert outcome.solution.solution_fingerprint == baseline.solution.solution_fingerprint
    assert outcome.outcome_fingerprint == baseline.outcome_fingerprint
    assert outcome.solution.c_exact_timetable == baseline.solution.c_exact_timetable

def test_enforceable_authority_composes_context_deterministically_and_is_shared() -> None:
    first_context, first_solver, authority = _protected_request()
    second_context, second_solver, second_authority = _protected_request()

    expected = _ortools_quality_adapter_context_fingerprint(
        first_solver.exact_demand_authority.authority_fingerprint,
        authority.enforcement_fingerprint,
    )
    assert ORTOOLS_QUALITY_ADAPTER_CONTEXT_PROFILE
    assert first_context.protected_service_floor_enforcement_authority is authority
    assert first_solver.protected_service_floor_enforcement_authority is authority
    assert first_solver.protected_service_floor_enforcement_fingerprint == (
        authority.enforcement_fingerprint
    )
    assert first_context.problem.adapter_context_fingerprint == expected
    assert first_context.problem.problem_fingerprint != _BASELINE_PROBLEM_FINGERPRINT
    assert second_authority == authority
    assert second_solver.protected_service_floor_enforcement_fingerprint == (
        authority.enforcement_fingerprint
    )
    assert second_context.problem.adapter_context_fingerprint == expected
    assert second_context.problem.problem_fingerprint == first_context.problem.problem_fingerprint


def test_each_composite_component_changes_the_context_fingerprint() -> None:
    context, solver, authority = _protected_request()
    exact = solver.exact_demand_authority.authority_fingerprint
    original = context.problem.adapter_context_fingerprint

    assert _ortools_quality_adapter_context_fingerprint(exact, "f" * 64) != original
    assert _ortools_quality_adapter_context_fingerprint(
        "0" * 64, authority.enforcement_fingerprint
    ) != (original)


@pytest.mark.parametrize(
    "tamper",
    (
        "different-context-authority",
        "context-authority-solver-none",
        "solver-authority-context-none",
        "context-empty-solver-enforceable",
        "context-enforceable-solver-empty",
        "stale-context-authority",
        "stale-solver-authority",
        "combined-context",
        "exact-demand",
    ),
)
def test_authority_defects_fail_before_solver_or_model_build(monkeypatch, tamper: str) -> None:
    context, solver, authority = _protected_request()
    empty = _authority(context.problem.scenario_b, empty=True)
    other = _authority(
        context.problem.scenario_b,
        assessment_fingerprint="f" * 64,
    )
    if tamper == "different-context-authority":
        context = replace(context, protected_service_floor_enforcement_authority=other)
    elif tamper == "context-authority-solver-none":
        solver = replace(solver, protected_service_floor_enforcement_authority=None)
    elif tamper == "solver-authority-context-none":
        context = replace(context, protected_service_floor_enforcement_authority=None)
    elif tamper == "context-empty-solver-enforceable":
        context = replace(context, protected_service_floor_enforcement_authority=empty)
    elif tamper == "context-enforceable-solver-empty":
        solver = replace(solver, protected_service_floor_enforcement_authority=empty)
    elif tamper == "stale-context-authority":
        stale = replace(authority, scenario_b_fingerprint="0" * 64)
        context = replace(context, protected_service_floor_enforcement_authority=stale)
    elif tamper == "stale-solver-authority":
        solver = replace(
            solver,
            protected_service_floor_enforcement_authority=replace(
                authority,
                scenario_b_fingerprint="0" * 64,
            ),
        )
    elif tamper == "combined-context":
        context = replace(
            context,
            problem=replace(context.problem, adapter_context_fingerprint="0" * 64),
        )
    elif tamper == "exact-demand":
        solver = replace(
            solver,
            exact_demand_authority=replace(
                solver.exact_demand_authority,
                authority_fingerprint="0" * 64,
            ),
        )

    solve_calls = 0
    model_calls = 0

    def forbidden_solve(self, problem):
        nonlocal solve_calls
        solve_calls += 1
        raise AssertionError("solver must not execute")

    def forbidden_model(*args, **kwargs):
        nonlocal model_calls
        model_calls += 1
        raise AssertionError("model must not build")

    monkeypatch.setattr(type(solver), "solve", forbidden_solve)
    monkeypatch.setattr(quality_module, "_build_quality_cp_sat_model", forbidden_model)
    outcome = run_schedule_solver_v1(context, solver)

    _assert_pre_solve_mismatch(outcome)
    assert solve_calls == 0
    assert model_calls == 0


def test_no_floor_and_equivalent_empty_bindings_continue_normally() -> None:
    context, solver, normalized, _ = _request()
    empty = _authority(normalized.scenario_b, empty=True)
    empty_context = replace(context, protected_service_floor_enforcement_authority=empty)
    empty_solver = replace(solver, protected_service_floor_enforcement_authority=empty)

    assert run_schedule_solver_v1(context, solver).result_status == (
        GenerationResultStatus.SOLUTION_ACCEPTED
    )
    assert run_schedule_solver_v1(empty_context, empty_solver).result_status == (
        GenerationResultStatus.SOLUTION_ACCEPTED
    )


def test_projection_is_deterministic_bound_and_exact_b_feasible() -> None:
    context, _, authority = _protected_request()
    first = build_ortools_protected_floor_projection_v1(authority, context.problem.scenario_b)
    second = build_ortools_protected_floor_projection_v1(authority, context.problem.scenario_b)

    assert first == second
    assert first.enforcement_fingerprint == authority.enforcement_fingerprint
    assert first.scenario_b_fingerprint == scenario_fingerprint(context.problem.scenario_b)
    assert first.regimes[0].source_indices == (1, 2, 3)
    assert first.internal_pair_constraint_count == 2


@pytest.mark.parametrize(
    "mutation",
    (
        "missing-source",
        "overlap",
        "wrong-direction",
        "wrong-order",
        "stale-boundary",
        "invalid-count",
        "invalid-headway",
    ),
)
def test_projection_defects_are_model_invalid(mutation: str) -> None:
    context, _, authority = _protected_request()
    regime = authority.protected_regimes[0]
    if mutation == "missing-source":
        regimes = (replace(regime, ordered_b_trip_ids=("MISSING", *regime.ordered_b_trip_ids[1:])),)
    elif mutation == "overlap":
        regimes = (regime, replace(regime, regime_id="OUTBOUND-R02"))
    elif mutation == "wrong-direction":
        regimes = (replace(regime, direction=TripRidershipDirectionV1.INBOUND),)
    elif mutation == "wrong-order":
        regimes = (replace(regime, ordered_b_trip_ids=tuple(reversed(regime.ordered_b_trip_ids))),)
    elif mutation == "stale-boundary":
        regimes = (replace(regime, protected_window_start=regime.protected_window_start + 60),)
    elif mutation == "invalid-count":
        regimes = (replace(regime, minimum_future_c_trip_count=99),)
    else:
        regimes = (replace(regime, maximum_future_c_headway_minutes=0),)
    malformed = _with_regimes(authority, regimes)

    with pytest.raises(OrToolsProtectedFloorProjectionError) as caught:
        build_ortools_protected_floor_projection_v1(malformed, context.problem.scenario_b)
    assert ORTOOLS_PROTECTED_FLOOR_PROJECTION_INVALID in str(caught.value)


def test_adjacent_regimes_remain_separate_and_cannot_overlap_source_slices() -> None:
    _, _, normalized, _ = _two_regime_fixture()
    first = _authority(normalized.scenario_b, outbound_indices=(0, 1))
    second_regime = _authority(
        normalized.scenario_b,
        outbound_indices=(2, 3),
    ).protected_regimes[0]
    authority = _with_regimes(
        first,
        (first.protected_regimes[0], replace(second_regime, regime_id="OUTBOUND-R02")),
    )
    projection = build_ortools_protected_floor_projection_v1(authority, normalized.scenario_b)

    assert tuple(regime.regime_id for regime in projection.regimes) == (
        "OUTBOUND-R01",
        "OUTBOUND-R02",
    )
    assert projection.internal_pair_constraint_count == 2


def test_unprotected_source_between_members_is_retained_in_full_slice() -> None:
    _, _, normalized, _ = _two_regime_fixture()
    authority = _authority(normalized.scenario_b, outbound_indices=(1, 3))
    projection = build_ortools_protected_floor_projection_v1(authority, normalized.scenario_b)
    regime = projection.regimes[0]

    assert regime.source_indices == (1, 3)
    assert regime.last_source_index - regime.first_source_index + 1 == 3
    assert projection.source_member_count == 2
    assert projection.internal_pair_constraint_count == 2


@pytest.mark.parametrize(
    ("tolerance", "departures", "expected_feasible"),
    (
        (0, {"B-O-02": 361, "B-O-03": 365, "B-O-04": 368}, True),
        (1, {"B-O-02": 362, "B-O-03": 365, "B-O-04": 367}, True),
        (1, {"B-O-02": 363, "B-O-03": 365, "B-O-04": 368}, False),
        (0, {"B-O-02": 361, "B-O-03": 365, "B-O-04": 368}, True),
        (0, {"B-O-02": 361, "B-O-03": 364, "B-O-04": 368}, True),
        (0, {"B-O-02": 361, "B-O-03": 362, "B-O-04": 368}, False),
    ),
    ids=(
        "exact-boundaries",
        "boundaries-within-tolerance",
        "boundary-outside-tolerance",
        "headway-equal-maximum",
        "headway-below-maximum",
        "headway-above-maximum",
    ),
)
def test_native_boundary_and_full_slice_headway_constraints(
    tolerance: int,
    departures: dict[str, int],
    expected_feasible: bool,
) -> None:
    context, solver, authority = _protected_request(tolerance_minutes=tolerance)
    status, projection = _hard_model_status(context, solver, authority, departures)

    assert (status in (cp_model.OPTIMAL, cp_model.FEASIBLE)) is expected_feasible
    assert projection.internal_pair_constraint_count == 2


def test_donor_interval_is_source_specific_and_replacement_cannot_cure_removal() -> None:
    context, solver, authority = _protected_request(
        tolerance_minutes=1,
        indices=(1, 3),
    )
    status, projection = _hard_model_status(
        context,
        solver,
        authority,
        {
            "B-O-02": 361,
            "B-O-03": 368,
            "B-O-04": 370,
        },
    )

    assert projection.donor_constraint_count == 2
    assert status == cp_model.INFEASIBLE


def test_transition_gaps_outside_protected_slice_are_not_constrained() -> None:
    context, _, normalized, evaluation = _quality_request(
        outbound_minutes=(360, 390, 400, 410, 440),
        inbound_minutes=(365,),
        outbound_runtimes=(1, 1, 1, 1, 1),
        inbound_runtimes=(1,),
        fleet_limit=6,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 360, 441, 10),
            _record(Direction.TERMINAL_2_TO_1, 365, 366, 0),
        ),
        route_id="ORTOOLS-PROTECTED-TRANSITIONS",
    )
    authority = _authority(normalized.scenario_b, outbound_indices=(1, 2, 3))
    context, solver = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        protected_service_floor_enforcement_authority=authority,
    )
    status, projection = _hard_model_status(context, solver, authority, {})

    assert projection.regimes[0].maximum_future_c_headway_minutes == 10
    assert projection.internal_pair_constraint_count == 2
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)


def test_directional_regimes_are_isolated_and_structural_count_adds_no_trips() -> None:
    _, _, normalized, evaluation = _two_regime_fixture()
    authority = _authority(
        normalized.scenario_b,
        outbound_indices=(1, 2, 3),
        inbound_indices=(0, 1),
    )
    context, solver = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        protected_service_floor_enforcement_authority=authority,
    )
    projection = build_ortools_protected_floor_projection_v1(authority, normalized.scenario_b)
    bundle = _build_quality_cp_sat_model(
        context.problem,
        solver.exact_demand_authority,
        projection,
    )

    assert tuple(regime.direction for regime in projection.regimes) == (
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
    )
    assert len(bundle.demand.hard.departure_by_source_id) == (
        context.problem.scenario_b.total_daily_trips
    )
    assert bundle.protected_regime_count == 2
    assert bundle.protected_source_member_count == 5


def test_normal_protected_run_passes_common_validation_and_carries_fingerprints() -> None:
    context, solver, authority = _protected_request(indices=(3, 4, 5))
    run = solver.solve(context.problem)
    outcome = run_schedule_solver_v1(context, solver)

    assert run.candidate is not None
    validation = validate_and_build_solution_v1(context, run.candidate)
    assert validation.passed
    assert validation.protected_service_floor_validation is not None
    assert validation.protected_service_floor_validation.passed
    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.solution is not None
    assert outcome.protected_service_floor_enforcement_fingerprint == (
        authority.enforcement_fingerprint
    )
    assert outcome.solution.protected_service_floor_enforcement_fingerprint == (
        authority.enforcement_fingerprint
    )
    assert any("common independent 6A2B validation remains" in item for item in run.limitations)


def test_common_validator_remains_final_when_native_candidate_is_tampered() -> None:
    context, solver, _ = _protected_request(indices=(3, 4, 5))
    run = solver.solve(context.problem)
    assert run.candidate is not None
    protected_last = next(
        trip for trip in run.candidate.exact_timetable if trip.source_b_trip_id == "B-O-06"
    )
    tampered = replace(
        run.candidate,
        exact_timetable=tuple(
            replace(trip, c_departure_time=trip.c_departure_time + 60)
            if trip is protected_last
            else trip
            for trip in run.candidate.exact_timetable
        ),
    )
    validation = validate_and_build_solution_v1(context, tampered)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert validation.solution is None
    assert validation.protected_service_floor_validation is not None
    assert not validation.protected_service_floor_validation.passed
    assert PROTECTED_WINDOW_END_VIOLATION in (
        validation.protected_service_floor_validation.rejection_codes
    )


def test_unknown_keeps_no_proof_semantics_under_protection(monkeypatch) -> None:
    context, solver, _ = _protected_request(indices=(3, 4, 5))
    monkeypatch.setattr(
        quality_module, "_map_cp_sat_status", lambda status: NativeSolverStatus.UNKNOWN
    )
    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.UNKNOWN
    assert run.candidate is None
    wording = " ".join((*run.explanations, *run.limitations)).lower()
    assert "proved" not in wording or "proven optimal: none" in wording
    assert "no compliant timetable exists" not in wording


def test_protected_infeasible_explanation_is_scoped_to_complete_encoded_model() -> None:
    _, _, normalized, evaluation = _regularity_fixture()
    authority = _authority(normalized.scenario_b, outbound_indices=(0, 1, 2))
    context, solver = build_ortools_service_quality_request_v1(
        normalized,
        evaluation,
        protected_service_floor_enforcement_authority=authority,
    )
    run = solver.solve(context.problem)
    wording = " ".join(run.explanations)

    assert run.solver_status == NativeSolverStatus.INFEASIBLE
    assert "complete encoded fixed-resource service-quality model" in wording
    assert "current Scenario B operating locks" in wording
    assert "exact bound protected-floor authority" in wording
    assert "policy alone" not in wording
    assert "expanded-fleet" not in wording


def test_objective_order_controls_and_no_floor_model_structure_are_preserved() -> None:
    baseline_context, baseline_solver, *_ = _request()
    protected_context, protected_solver, authority = _protected_request()
    projection = build_ortools_protected_floor_projection_v1(
        authority,
        protected_context.problem.scenario_b,
    )
    baseline = _build_quality_cp_sat_model(
        baseline_context.problem,
        baseline_solver.exact_demand_authority,
    )
    protected = _build_quality_cp_sat_model(
        protected_context.problem,
        protected_solver.exact_demand_authority,
        projection,
    )

    assert tuple(stage.name for stage in baseline.stages) == _OBJECTIVE_NAMES
    assert tuple(stage.name for stage in protected.stages) == _OBJECTIVE_NAMES
    assert baseline.protected_enforcement_fingerprint is None
    assert baseline.protected_regime_count == 0
    assert protected.protected_enforcement_fingerprint == authority.enforcement_fingerprint
    assert protected_context.problem.solver_policy == baseline_context.problem.solver_policy


def test_direct_solver_rejects_invalid_projection_authority_as_model_invalid() -> None:
    context, solver, authority = _protected_request()
    solver = replace(
        solver,
        protected_service_floor_enforcement_authority=replace(
            authority,
            scenario_b_fingerprint="0" * 64,
        ),
    )
    run = solver.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert run.candidate is None
    assert any(ORTOOLS_PROTECTED_FLOOR_PROJECTION_INVALID in item for item in run.explanations)


def test_exact_demand_authority_remains_independently_self_bound() -> None:
    context, solver, _ = _protected_request()
    changed = _ExactDemandAuthority(
        blocks=solver.exact_demand_authority.blocks,
        authority_fingerprint="0" * 64,
    )
    run = replace(solver, exact_demand_authority=changed).solve(context.problem)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert run.candidate is None


def test_full_slice_native_rejection_matches_common_headway_semantics() -> None:
    context, solver, authority = _protected_request()
    status, _ = _hard_model_status(
        context,
        solver,
        authority,
        {"B-O-02": 361, "B-O-03": 362, "B-O-04": 368},
    )
    assert status == cp_model.INFEASIBLE
    assert PROTECTED_INTERNAL_HEADWAY_ABOVE_FLOOR
