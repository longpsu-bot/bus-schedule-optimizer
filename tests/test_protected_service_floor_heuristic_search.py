from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest
from test_contract_v1_solver import _fixture, _normalized

import bus_schedule_engine.contracts_v1.heuristic_solver as heuristic_solver_module
from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.c_generator import (
    HEURISTIC_PROTECTED_FLOOR_AUTHORITY_MISMATCH,
    PROTECTED_FLOOR_BOUNDARY,
    PROTECTED_FLOOR_DIRECTION_PLANS_EVALUATED,
    PROTECTED_FLOOR_DIRECTION_PLANS_FILTERED,
    PROTECTED_FLOOR_DONOR_WINDOW,
    PROTECTED_FLOOR_INTERNAL_HEADWAY,
    PROTECTED_FLOOR_NO_IMPROVING_COMPLIANT_CANDIDATE,
    PROTECTED_FLOOR_SOURCE_AUTHORITY,
    PROTECTED_FLOOR_TRIP_COUNT,
    HeuristicProtectedFloorAuthorityError,
    HeuristicProtectedFloorRegimeV1,
    HeuristicProtectedFloorSearchProjectionV1,
    _fallback_plans,
    _filter_protected_direction_plans,
    _observed_plan,
    _protected_floor_plan_rejection_reasons,
    build_heuristic_protected_floor_search_projection_v1,
    generate_scenario_c,
    validate_heuristic_protected_floor_search_projection_v1,
)
from bus_schedule_engine.contracts_v1.heuristic_context import heuristic_context_fingerprint
from bus_schedule_engine.contracts_v1.models import ContractDirection
from bus_schedule_engine.contracts_v1.public_api import evaluate_scenario_b_v1
from bus_schedule_engine.contracts_v1.serialization import canonical_sha256, scenario_fingerprint
from bus_schedule_engine.contracts_v1.solver_adapter import (
    build_heuristic_schedule_request_v1,
)
from bus_schedule_engine.contracts_v1.solver_fingerprints import candidate_fingerprint
from bus_schedule_engine.contracts_v1.solver_models import (
    GenerationResultStatus,
    NativeSolverStatus,
    SolverExecutionStatus,
    SolverRunResultV1,
)
from bus_schedule_engine.contracts_v1.solver_orchestration import run_schedule_solver_v1
from bus_schedule_engine.contracts_v1.solver_validation import validate_and_build_solution_v1
from bus_schedule_engine.models import (
    Direction,
    ProtectedServiceFloorEnforcementAuthorityV1,
    ProtectedServiceFloorEnforcementRegimeV1,
    Trip,
    TripRidershipDirectionV1,
)
from bus_schedule_engine.protected_service_floor_codes import (
    PROTECTED_DONOR_REMOVAL,
)
from bus_schedule_engine.protected_service_floor_enforcement import (
    PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
    _authority_fingerprint_payload,
)

_BASELINE_CONTEXT_FINGERPRINT = "7aa27b368bc257b7dad796a23947cbb83f8cb6c12ee4ea7fca81d338b41898da"
_BASELINE_PROBLEM_FINGERPRINT = "530de10b8568f7b3afb470dcce33c78e68f9bc4605a20309cf72acbc82e69bb7"
_BASELINE_CANDIDATE_FINGERPRINT = "d4560a94347dc8134eebb816d376f8295ab3adb5a0613e796e3e8bef5a34c233"
_BASELINE_SOLUTION_FINGERPRINT = "3cc4535cbe53241b58a7d3c424dac686ff1ecfa490c1bfb71aff51a5de161af9"
_BASELINE_OUTCOME_FINGERPRINT = "2b046d2d1f4003dff7abd6d91d065b9a2241752407513c4851344dbfa57d1626"


def _authority(
    scenario,
    *,
    enforceable: bool = True,
    tolerance_minutes: int = 60,
    assessment_fingerprint: str = "a" * 64,
) -> ProtectedServiceFloorEnforcementAuthorityV1:
    regimes: tuple[ProtectedServiceFloorEnforcementRegimeV1, ...] = ()
    if enforceable:
        members = tuple(
            trip
            for trip in scenario.exact_timetable
            if trip.direction == ContractDirection.OUTBOUND
        )[:3]
        regimes = (
            ProtectedServiceFloorEnforcementRegimeV1(
                regime_id="OUTBOUND-R01",
                direction=TripRidershipDirectionV1.OUTBOUND,
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
            ),
        )
    fields = {
        "scenario_b_fingerprint": scenario_fingerprint(scenario),
        "assessment_fingerprint": assessment_fingerprint,
        "policy_fingerprint": "b" * 64,
        "regime_derivation_fingerprint": "c" * 64,
        "trip_ridership_input_fingerprint": "d" * 64 if enforceable else None,
        "trip_ridership_analysis_fingerprint": "e" * 64 if enforceable else None,
        "target_load_factor": 0.85,
        "maximum_load_factor": 0.90,
        "protected_regimes": regimes,
    }
    return ProtectedServiceFloorEnforcementAuthorityV1(
        **fields,
        enforcement_profile=PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
        enforcement_fingerprint=canonical_sha256(_authority_fingerprint_payload(**fields)),
    )


def _request(
    authority: ProtectedServiceFloorEnforcementAuthorityV1 | str | None = None,
):
    parameters, trips, demand, fleet_limit = _fixture()
    normalized = _normalized(parameters, trips, demand, fleet_limit)
    if authority == "enforceable":
        authority = _authority(normalized.scenario_b)
    elif authority == "strict":
        authority = _authority(normalized.scenario_b, tolerance_minutes=0)
    elif authority == "empty":
        authority = _authority(normalized.scenario_b, enforceable=False)
    evaluation = evaluate_scenario_b_v1(normalized)
    context, adapter = build_heuristic_schedule_request_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        demand,
        ScenarioCConfig(),
        protected_service_floor_enforcement_authority=authority,
    )
    return context, adapter, parameters, trips, demand, fleet_limit, normalized


def _legacy_source(
    direction: Direction,
    minute_offsets: tuple[int, ...] = (0, 30, 60, 90, 120, 150, 180),
) -> list[Trip]:
    base = 6 * 3600 + (5 * 60 if direction == Direction.TERMINAL_2_TO_1 else 0)
    return [
        Trip(
            scenario="B",
            trip_id=f"{direction.value}-{index:02d}",
            departure_terminal="T1" if direction == Direction.TERMINAL_1_TO_2 else "T2",
            direction=direction,
            departure_seconds=base + offset * 60,
            arrival_seconds=base + offset * 60 + 30 * 60,
        )
        for index, offset in enumerate(minute_offsets, start=1)
    ]


def _projected_regime(
    source: list[Trip],
    start_index: int = 1,
    end_index: int = 3,
    *,
    tolerance_minutes: int = 0,
    maximum_headway_minutes: int = 30,
    minimum_trip_count: int | None = None,
    regime_id: str = "R1",
) -> HeuristicProtectedFloorRegimeV1:
    members = source[start_index : end_index + 1]
    return HeuristicProtectedFloorRegimeV1(
        regime_id=regime_id,
        direction=source[0].direction,
        ordered_b_trip_ids=tuple(trip.trip_id for trip in members),
        maximum_future_c_headway_minutes=maximum_headway_minutes,
        minimum_future_c_trip_count=(minimum_trip_count or len(members)),
        protected_window_start=members[0].departure_seconds,
        protected_window_end=members[-1].departure_seconds,
        future_boundary_tolerance_minutes=tolerance_minutes,
        donor_removal_prohibited=True,
    )


def _plan(source: list[Trip], minute_offsets: tuple[float, ...] | None = None):
    times = (
        [source[0].departure_seconds + round(offset * 60) for offset in minute_offsets]
        if minute_offsets is not None
        else [trip.departure_seconds for trip in source]
    )
    baseline = _observed_plan(
        source[0].direction,
        [trip.departure_seconds for trip in source],
        ScenarioCConfig(),
    )
    return replace(baseline, times=tuple(times))


def _historical_context_fingerprint(context) -> str:
    return heuristic_context_fingerprint(
        legacy_parameters=context.legacy_parameters,
        legacy_trips_b=context.legacy_trips_b,
        legacy_demand=context.legacy_demand,
        heuristic_config=context.heuristic_config,
        turnaround_bridge_mode=context.turnaround_bridge_mode,
        turnaround_bridge_value_minutes=context.turnaround_bridge_value_minutes,
        source_b_fingerprint=context.source_b_fingerprint,
        observed_demand_fingerprint=context.observed_demand_fingerprint,
    )


def test_no_authority_preserves_merged_6a2b_fingerprints() -> None:
    context, adapter, *_ = _request()
    run = adapter.solve(context.problem)
    outcome = run_schedule_solver_v1(context, adapter)

    assert adapter.compatibility_context.context_fingerprint == _BASELINE_CONTEXT_FINGERPRINT
    assert context.problem.problem_fingerprint == _BASELINE_PROBLEM_FINGERPRINT
    assert run.candidate is not None
    assert run.candidate.candidate_fingerprint == _BASELINE_CANDIDATE_FINGERPRINT
    assert outcome.solution is not None
    assert outcome.solution.solution_fingerprint == _BASELINE_SOLUTION_FINGERPRINT
    assert outcome.outcome_fingerprint == _BASELINE_OUTCOME_FINGERPRINT


def test_valid_empty_authority_preserves_historical_identity_and_behavior() -> None:
    baseline_context, baseline_adapter, *_ = _request()
    empty_context, empty_adapter, *_ = _request("empty")
    baseline_run = baseline_adapter.solve(baseline_context.problem)
    empty_run = empty_adapter.solve(empty_context.problem)
    baseline_outcome = run_schedule_solver_v1(baseline_context, baseline_adapter)
    empty_outcome = run_schedule_solver_v1(empty_context, empty_adapter)

    assert empty_context.protected_service_floor_enforcement_authority is None
    assert empty_adapter.compatibility_context.context_fingerprint == (
        baseline_adapter.compatibility_context.context_fingerprint
    )
    assert empty_context.problem.problem_fingerprint == baseline_context.problem.problem_fingerprint
    assert empty_run.solver_status == baseline_run.solver_status
    assert empty_run.candidate is not None and baseline_run.candidate is not None
    assert empty_run.candidate.candidate_fingerprint == baseline_run.candidate.candidate_fingerprint
    assert empty_outcome.outcome_fingerprint == baseline_outcome.outcome_fingerprint


def test_enforceable_authority_changes_context_deterministically_and_is_exactly_attached() -> None:
    first_context, first_adapter, *_ = _request("enforceable")
    second_context, second_adapter, *_ = _request("enforceable")
    baseline_context, baseline_adapter, *_ = _request()
    authority = first_adapter.protected_service_floor_enforcement_authority

    assert authority is not None
    assert first_context.protected_service_floor_enforcement_authority is authority
    assert first_adapter.compatibility_context.protected_service_floor_enforcement_fingerprint == (
        authority.enforcement_fingerprint
    )
    assert first_adapter.compatibility_context.context_fingerprint != (
        baseline_adapter.compatibility_context.context_fingerprint
    )
    assert first_context.problem.problem_fingerprint != baseline_context.problem.problem_fingerprint
    assert first_adapter.compatibility_context.context_fingerprint == (
        second_adapter.compatibility_context.context_fingerprint
    )
    assert first_context.problem.problem_fingerprint == second_context.problem.problem_fingerprint


def test_changing_valid_enforcement_fingerprint_changes_context_fingerprint() -> None:
    _, _, parameters, trips, demand, fleet_limit, normalized = _request()
    first = _authority(normalized.scenario_b, assessment_fingerprint="a" * 64)
    second = _authority(normalized.scenario_b, assessment_fingerprint="f" * 64)
    evaluation = evaluate_scenario_b_v1(normalized)
    first_context, first_adapter = build_heuristic_schedule_request_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        demand,
        ScenarioCConfig(),
        protected_service_floor_enforcement_authority=first,
    )
    second_context, second_adapter = build_heuristic_schedule_request_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        demand,
        ScenarioCConfig(),
        protected_service_floor_enforcement_authority=second,
    )

    assert first.enforcement_fingerprint != second.enforcement_fingerprint
    assert first_adapter.compatibility_context.context_fingerprint != (
        second_adapter.compatibility_context.context_fingerprint
    )
    assert first_context.problem.problem_fingerprint != second_context.problem.problem_fingerprint


def test_tampered_authority_returns_model_invalid_before_generator(monkeypatch) -> None:
    context, adapter, *_ = _request("enforceable")
    authority = adapter.protected_service_floor_enforcement_authority
    assert authority is not None
    tampered_adapter = replace(
        adapter,
        protected_service_floor_enforcement_authority=replace(
            authority,
            enforcement_fingerprint="0" * 64,
        ),
    )

    def unexpected(*args, **kwargs):  # pragma: no cover - invocation fails the test
        raise AssertionError("generator must not execute")

    monkeypatch.setattr(heuristic_solver_module, "generate_scenario_c", unexpected)
    run = tampered_adapter.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert run.candidate is None
    assert any(HEURISTIC_PROTECTED_FLOOR_AUTHORITY_MISMATCH in item for item in run.explanations)


def test_context_fingerprint_without_authority_binding_returns_model_invalid(monkeypatch) -> None:
    context, adapter, *_ = _request("enforceable")
    compatibility = adapter.compatibility_context
    unbound = replace(
        compatibility,
        context_fingerprint=_historical_context_fingerprint(compatibility),
        protected_service_floor_enforcement_fingerprint=None,
    )
    unbound_adapter = replace(adapter, compatibility_context=unbound)

    def unexpected(*args, **kwargs):  # pragma: no cover - invocation fails the test
        raise AssertionError("generator must not execute")

    monkeypatch.setattr(heuristic_solver_module, "generate_scenario_c", unexpected)
    run = unbound_adapter.solve(context.problem)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert any(HEURISTIC_PROTECTED_FLOOR_AUTHORITY_MISMATCH in item for item in run.explanations)


def test_exact_protected_direction_plan_and_declared_tolerance_pass() -> None:
    source = _legacy_source(Direction.TERMINAL_1_TO_2)
    exact = _plan(source)
    within_tolerance = _plan(source, (0, 31, 60, 90, 120, 150, 180))
    regime = _projected_regime(source, tolerance_minutes=1)

    assert _protected_floor_plan_rejection_reasons(exact, source, (regime,)) == ()
    assert (
        _protected_floor_plan_rejection_reasons(
            within_tolerance,
            source,
            (regime,),
        )
        == ()
    )


def test_donor_window_and_replacement_departure_cannot_cure_protected_source_removal() -> None:
    source = _legacy_source(Direction.TERMINAL_1_TO_2)
    regime = _projected_regime(source)
    moved = _plan(source, (30, 0, 60, 90, 120, 150, 180))

    reasons = _protected_floor_plan_rejection_reasons(moved, source, (regime,))

    assert PROTECTED_FLOOR_DONOR_WINDOW in reasons
    assert PROTECTED_FLOOR_BOUNDARY in reasons


@pytest.mark.parametrize(
    "offsets",
    (
        (0, 32, 60, 90, 120, 150, 180),
        (0, 30, 60, 88, 120, 150, 180),
    ),
)
def test_protected_start_or_end_outside_tolerance_is_filtered(offsets) -> None:
    source = _legacy_source(Direction.TERMINAL_1_TO_2)
    regime = _projected_regime(source, tolerance_minutes=1)

    reasons = _protected_floor_plan_rejection_reasons(
        _plan(source, offsets),
        source,
        (regime,),
    )

    assert PROTECTED_FLOOR_BOUNDARY in reasons


def test_internal_headway_equal_below_and_above_floor() -> None:
    source = _legacy_source(Direction.TERMINAL_1_TO_2)
    exact_regime = _projected_regime(source)
    tolerant_regime = _projected_regime(source, tolerance_minutes=2)

    assert _protected_floor_plan_rejection_reasons(_plan(source), source, (exact_regime,)) == ()
    assert (
        _protected_floor_plan_rejection_reasons(
            _plan(source, (0, 30, 59, 88, 120, 150, 180)),
            source,
            (tolerant_regime,),
        )
        == ()
    )
    assert PROTECTED_FLOOR_INTERNAL_HEADWAY in _protected_floor_plan_rejection_reasons(
        _plan(source, (0, 30, 61, 90, 120, 150, 180)),
        source,
        (exact_regime,),
    )


def test_non_minute_gap_is_explicitly_filtered_and_source_order_defect_is_invalid() -> None:
    source = _legacy_source(Direction.TERMINAL_1_TO_2)
    regime = _projected_regime(source)

    reasons = _protected_floor_plan_rejection_reasons(
        _plan(source, (0, 30, 60.5, 90, 120, 150, 180)),
        source,
        (regime,),
    )
    assert PROTECTED_FLOOR_SOURCE_AUTHORITY in reasons
    with pytest.raises(HeuristicProtectedFloorAuthorityError):
        _protected_floor_plan_rejection_reasons(
            _plan(source, (0, 30, 95, 90, 120, 150, 180)),
            source,
            (regime,),
        )


def test_directions_and_adjacent_regimes_are_filtered_independently() -> None:
    outbound = _legacy_source(Direction.TERMINAL_1_TO_2)
    inbound = _legacy_source(Direction.TERMINAL_2_TO_1)
    outbound_first = _projected_regime(outbound, 0, 2, regime_id="OUT-1")
    outbound_second = _projected_regime(outbound, 3, 5, regime_id="OUT-2")
    inbound_regime = _projected_regime(inbound, 1, 3, regime_id="IN-1")
    changed_outbound = _plan(outbound, (0, 30, 60, 90, 121, 150, 180))

    assert (
        _protected_floor_plan_rejection_reasons(changed_outbound, outbound, (outbound_first,)) == ()
    )
    assert PROTECTED_FLOOR_INTERNAL_HEADWAY in _protected_floor_plan_rejection_reasons(
        changed_outbound,
        outbound,
        (outbound_second,),
    )
    assert _protected_floor_plan_rejection_reasons(_plan(inbound), inbound, (inbound_regime,)) == ()


def test_projection_rejects_double_counted_or_missing_protected_source() -> None:
    source = _legacy_source(Direction.TERMINAL_1_TO_2)
    first = _projected_regime(source, 0, 2, regime_id="R1")
    overlap = _projected_regime(source, 2, 4, regime_id="R2")
    missing = replace(first, ordered_b_trip_ids=("missing", *first.ordered_b_trip_ids[1:]))

    with pytest.raises(HeuristicProtectedFloorAuthorityError):
        validate_heuristic_protected_floor_search_projection_v1(
            HeuristicProtectedFloorSearchProjectionV1("f" * 64, (first, overlap)),
            source,
        )
    with pytest.raises(HeuristicProtectedFloorAuthorityError):
        validate_heuristic_protected_floor_search_projection_v1(
            HeuristicProtectedFloorSearchProjectionV1("f" * 64, (missing,)),
            source,
        )


def test_trip_count_floor_defect_is_not_silently_accepted() -> None:
    source = _legacy_source(Direction.TERMINAL_1_TO_2)
    malformed = _projected_regime(source, minimum_trip_count=4)
    projection = HeuristicProtectedFloorSearchProjectionV1("f" * 64, (malformed,))

    assert PROTECTED_FLOOR_TRIP_COUNT in _protected_floor_plan_rejection_reasons(
        _plan(source), source, (malformed,)
    )
    with pytest.raises(HeuristicProtectedFloorAuthorityError):
        validate_heuristic_protected_floor_search_projection_v1(projection, source)


def test_direction_plan_filter_selects_only_compliant_plans_and_counts_reasons() -> None:
    source = _legacy_source(Direction.TERMINAL_1_TO_2)
    regime = _projected_regime(source)
    violating = _plan(source, (0, 30, 61, 90, 120, 150, 180))
    compliant = _plan(source)
    counts: Counter[str] = Counter()

    filtered = _filter_protected_direction_plans(
        [violating, compliant],
        source,
        (regime,),
        counts,
    )

    assert filtered == [compliant]
    assert counts == Counter(
        {
            PROTECTED_FLOOR_DIRECTION_PLANS_EVALUATED: 2,
            PROTECTED_FLOOR_DIRECTION_PLANS_FILTERED: 1,
            PROTECTED_FLOOR_INTERNAL_HEADWAY: 1,
        }
    )


def test_all_violating_plans_leave_no_compliant_plan_with_deterministic_counts() -> None:
    source = _legacy_source(Direction.TERMINAL_1_TO_2)
    regime = _projected_regime(source)
    plans = [
        _plan(source, (0, 30, 61, 90, 120, 150, 180)),
        _plan(source, (0, 30, 62, 90, 120, 150, 180)),
    ]
    first_counts: Counter[str] = Counter()
    second_counts: Counter[str] = Counter()

    assert _filter_protected_direction_plans(plans, source, (regime,), first_counts) == []
    assert _filter_protected_direction_plans(plans, source, (regime,), second_counts) == []
    assert first_counts == second_counts


def test_exact_b_fallback_passes_every_projected_regime() -> None:
    outbound = _legacy_source(Direction.TERMINAL_1_TO_2)
    inbound = _legacy_source(Direction.TERMINAL_2_TO_1)
    source_by_direction = {
        Direction.TERMINAL_1_TO_2: outbound,
        Direction.TERMINAL_2_TO_1: inbound,
    }
    regimes = (
        _projected_regime(outbound, 1, 3, regime_id="OUT"),
        _projected_regime(inbound, 1, 3, regime_id="IN"),
    )
    fallback = _fallback_plans(source_by_direction, ScenarioCConfig())

    for direction, regime in zip(source_by_direction, regimes, strict=True):
        assert (
            _protected_floor_plan_rejection_reasons(
                fallback[direction],
                source_by_direction[direction],
                (regime,),
            )
            == ()
        )


def test_generator_diagnostics_are_deterministic_and_conditionally_present() -> None:
    context, adapter, parameters, trips, demand, fleet_limit, _ = _request("enforceable")
    authority = adapter.protected_service_floor_enforcement_authority
    assert authority is not None
    projection = build_heuristic_protected_floor_search_projection_v1(authority)

    first = generate_scenario_c(
        parameters,
        trips,
        demand,
        fleet_limit,
        ScenarioCConfig(),
        projection,
    )
    second = generate_scenario_c(
        parameters,
        trips,
        demand,
        fleet_limit,
        ScenarioCConfig(),
        projection,
    )
    baseline = generate_scenario_c(
        parameters,
        trips,
        demand,
        fleet_limit,
        ScenarioCConfig(),
    )
    first_counts = dict(first.optimization_log.rejection_reason_counts)
    baseline_counts = dict(baseline.optimization_log.rejection_reason_counts)

    assert first.optimization_log.rejection_reason_counts == (
        second.optimization_log.rejection_reason_counts
    )
    assert first_counts[PROTECTED_FLOOR_DIRECTION_PLANS_EVALUATED] > 0
    assert first_counts[PROTECTED_FLOOR_DIRECTION_PLANS_FILTERED] >= 0
    assert PROTECTED_FLOOR_NO_IMPROVING_COMPLIANT_CANDIDATE in first_counts
    assert PROTECTED_FLOOR_DIRECTION_PLANS_EVALUATED not in baseline_counts
    assert context.problem.adapter_context_fingerprint == (
        adapter.compatibility_context.context_fingerprint
    )


def test_bounded_protected_search_exhaustion_is_unknown_not_global_infeasibility() -> None:
    context, adapter, *_ = _request("strict")
    run = adapter.solve(context.problem)
    outcome = run_schedule_solver_v1(context, adapter)

    assert run.solver_status == NativeSolverStatus.UNKNOWN
    assert run.candidate is None
    assert outcome.result_status == GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT
    assert outcome.result_status != GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS
    assert any("does not prove global infeasibility" in item for item in run.limitations)


def test_compliant_native_candidate_still_passes_common_independent_validator() -> None:
    context, adapter, *_ = _request("enforceable")
    run = adapter.solve(context.problem)

    assert run.candidate is not None
    validation = validate_and_build_solution_v1(context, run.candidate)
    outcome = run_schedule_solver_v1(context, adapter)

    assert validation.passed
    assert validation.protected_service_floor_validation is not None
    assert validation.protected_service_floor_validation.passed
    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.protected_service_floor_enforcement_fingerprint == (
        adapter.protected_service_floor_enforcement_authority.enforcement_fingerprint
    )
    assert outcome.solution is not None
    assert outcome.solution.protected_service_floor_validation_fingerprint == (
        outcome.protected_service_floor_validation_fingerprint
    )


class _StaticNativeClaimSolver:
    adapter_id = "legacy_heuristic_v1"

    def __init__(self, run: SolverRunResultV1) -> None:
        self.run = run

    def solve(self, problem):
        return self.run


def test_tampered_post_search_candidate_is_rejected_despite_native_feasible_claim() -> None:
    context, adapter, *_ = _request("enforceable")
    run = adapter.solve(context.problem)
    assert run.candidate is not None
    authority = adapter.protected_service_floor_enforcement_authority
    assert authority is not None
    protected_regime = authority.protected_regimes[0]
    first_source = protected_regime.ordered_b_trip_ids[0]
    tampered_departure = (
        protected_regime.protected_window_start
        - (protected_regime.future_boundary_tolerance_minutes + 1) * 60
    )
    changed_rows = tuple(
        replace(
            trip,
            c_departure_time=tampered_departure,
            arrival_time=trip.arrival_time + tampered_departure - trip.c_departure_time,
            shift_minutes=(tampered_departure - trip.b_departure_time) / 60,
        )
        if trip.source_b_trip_id == first_source
        else trip
        for trip in run.candidate.exact_timetable
    )
    tampered = replace(
        run.candidate,
        exact_timetable=changed_rows,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=context.problem.problem_fingerprint,
            solver_adapter=run.candidate.solver_adapter,
            exact_timetable=changed_rows,
            headway_regimes=run.candidate.headway_regimes,
        ),
    )
    native_claim = replace(run, candidate=tampered)

    validation = validate_and_build_solution_v1(context, tampered)
    outcome = run_schedule_solver_v1(context, _StaticNativeClaimSolver(native_claim))

    assert not validation.passed
    assert PROTECTED_DONOR_REMOVAL in validation.rejection_codes
    assert outcome.result_status == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.FEASIBLE
    assert outcome.solution is None
