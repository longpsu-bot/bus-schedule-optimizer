from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import bus_schedule_engine.service_plan_coordinator as coordinator
from bus_schedule_engine.contracts_v1.clean_boundary_compiler import (
    OperationalEndpointAuthorityV1,
)
from bus_schedule_engine.contracts_v1.clean_compile_frontier import (
    compile_service_plan_frontier_v1,
)
from bus_schedule_engine.contracts_v1.closed_loop_service_protection import (
    ACTIVE_TRANSLATED_PROTECTED_WINDOWS,
    INVALID_TRANSLATED_PROTECTION_AUTHORITY,
    PROTECTED_INTERNAL_HEADWAY_ABOVE_MAXIMUM,
    PROTECTED_TRIP_COUNT_BELOW_MINIMUM,
    VALID_NO_ENFORCEABLE_WINDOW,
    ClosedLoopProtectedServiceWindowV1,
    build_closed_loop_service_protection_authority_v1,
    translate_protected_service_floor_authority_v1,
    validate_closed_loop_service_protection_v1,
)
from bus_schedule_engine.contracts_v1.service_plan_state import (
    ServicePlanMoveV1,
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
    merge_adjacent_neighbors_v1,
    move_one_trip_left_to_right_neighbors_v1,
    move_one_trip_right_to_left_neighbors_v1,
    service_plan_fingerprint_v1,
    shift_boundary_left_neighbors_v1,
    shift_boundary_right_neighbors_v1,
    split_regime_neighbors_v1,
    tail_absorb_one_neighbors_v1,
    tail_release_one_neighbors_v1,
    validate_service_plan_state_v1,
)
from bus_schedule_engine.models import (
    ProtectedServiceFloorEnforcementAuthorityV1,
    ProtectedServiceFloorEnforcementRegimeV1,
    TripRidershipDirectionV1,
)
from bus_schedule_engine.protected_service_floor_enforcement import (
    PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
)
from bus_schedule_engine.service_plan_coordinator import (
    CLEAN_BOUNDARY_UNCOMPILABLE,
    DEFAULT_COORDINATOR_SEARCH_BUDGET_V1,
    DEMAND_OVERSERVED_INTERVAL,
    DEMAND_RESPONSE_DIRECTION_MISMATCH,
    DEMAND_UNDERSERVED_INTERVAL,
    FLEET_LIMIT_EXCEEDED,
    LARGEST_SERVICE_FREQUENCY_JUMP,
    REDUNDANT_SERVICE_BOUNDARY,
    SEARCH_BUDGET_EXHAUSTED,
    TAIL_OVER_SERVICE,
    TAIL_UNDER_SERVICE,
    CoordinatorSearchBudgetV1,
    DemandBucketEvidenceV1,
    DemandResponseRegimeEvidenceV1,
    DirectionalCompilationCandidateV1,
    FeedbackEvidenceV1,
    OperatingPairCandidateV1,
    OperatingPairMetricsV1,
    RouteCoordinatorContextV1,
    dominates_operating_pair_v1,
    evaluate_actual_service_v1,
    evaluate_operating_pair_v1,
    expected_passenger_wait_metrics_v1,
    generate_targeted_neighbors_v1,
    load_route_coordinator_inputs_v1,
    route_result_payload_v1,
    search_route_service_plans_v1,
    update_operating_pair_pareto_v1,
    verify_frozen_prior_artifacts_v1,
)


def _state(
    direction: str = "outbound",
    *,
    first_count: int = 4,
    second_count: int = 4,
    fixed_last: int = 3540,
    seed: str = "TEST",
) -> ServicePlanStateV1:
    return ServicePlanStateV1(
        route_id="X",
        direction=direction,
        fixed_first_departure=0,
        fixed_last_departure=fixed_last,
        service_regimes=(
            ServiceRegimeDecisionV1(0, 1800, first_count),
            ServiceRegimeDecisionV1(1800, 3600, second_count),
        ),
        seed_id=seed,
    )


def _authority(
    direction: str = "outbound", *, fixed_last: int = 3540
) -> OperationalEndpointAuthorityV1:
    return OperationalEndpointAuthorityV1(
        route_id="X",
        direction=direction,
        analysis_window_start=0,
        analysis_window_end=3600,
        fixed_first_departure=0,
        fixed_last_departure=fixed_last,
        authority_source="test",
    )


def test_bounded_open_queue_reintroduction_ignores_stale_same_priority_entry() -> None:
    queue = coordinator._BoundedOpenQueue(limit=2)
    state_a = _state(seed="A")
    state_b = dataclasses.replace(state_a, seed_id="B")
    state_c = dataclasses.replace(state_a, seed_id="C")
    old_priority = (2, "old")
    new_priority = (1, "new")

    assert queue.push(state_a, old_priority) == (True, False, None)
    assert queue.push(state_b, new_priority) == (True, False, None)
    assert queue.pop() == (state_b, new_priority)
    assert not queue

    assert queue.push(state_c, old_priority) == (True, False, None)
    assert queue.pop() == (state_c, old_priority)
    assert not queue
    assert queue.pop() is None


def test_bounded_open_queue_rejects_active_equal_or_worse_duplicate() -> None:
    queue = coordinator._BoundedOpenQueue(limit=2)
    state = _state(seed="ACTIVE")
    duplicate = dataclasses.replace(state, seed_id="DUPLICATE")

    assert queue.push(state, (1,)) == (True, False, None)
    active_before = dict(queue.active)
    ticket_before = queue._next_ticket

    assert queue.push(duplicate, (1,)) == (False, False, None)
    assert queue.push(duplicate, (2,)) == (False, False, None)
    assert queue.active == active_before
    assert queue._next_ticket == ticket_before
    assert queue.pop() == (state, (1,))


def test_bounded_open_queue_better_replacement_returns_current_state() -> None:
    queue = coordinator._BoundedOpenQueue(limit=2)
    old = _state(seed="OLD")
    replacement = dataclasses.replace(old, seed_id="REPLACEMENT")

    assert queue.push(old, (2,)) == (True, False, None)
    old_ticket = queue.active[service_plan_fingerprint_v1(old)][1]
    assert queue.push(replacement, (1,)) == (True, False, None)
    new_ticket = queue.active[service_plan_fingerprint_v1(old)][1]

    assert new_ticket > old_ticket
    assert queue.pop() == (replacement, (1,))
    assert not queue
    assert queue.pop() is None


def test_bounded_open_queue_capacity_evicts_semantic_worst_and_ignores_stale() -> None:
    queue = coordinator._BoundedOpenQueue(limit=2)
    best = _state(first_count=3, second_count=5, seed="BEST")
    worst = _state(first_count=5, second_count=3, seed="WORST")
    middle = _state(first_count=6, second_count=2, seed="MIDDLE")
    worst_fingerprint = service_plan_fingerprint_v1(worst)

    assert queue.push(best, (1,)) == (True, False, None)
    assert queue.push(worst, (3,)) == (True, False, None)
    assert len(queue.active) == 2
    assert queue.push(middle, (2,)) == (True, True, worst_fingerprint)
    assert len(queue.active) == 2
    assert worst_fingerprint not in queue.active

    assert queue.pop() == (best, (1,))
    assert queue.pop() == (middle, (2,))
    assert not queue
    assert queue.pop() is None


def test_bounded_open_queue_pop_order_is_priority_then_fingerprint() -> None:
    queue = coordinator._BoundedOpenQueue(limit=4)
    states = (
        _state(first_count=3, second_count=5, seed="ONE"),
        _state(first_count=5, second_count=3, seed="TWO"),
        _state(first_count=6, second_count=2, seed="THREE"),
    )
    priorities = ((2,), (1,), (1,))
    for state, priority in zip(states, priorities, strict=True):
        assert queue.push(state, priority)[0]

    expected = sorted(
        zip(priorities, states, strict=True),
        key=lambda item: (item[0], service_plan_fingerprint_v1(item[1])),
    )
    actual = []
    while queue:
        state, priority = queue.pop()
        actual.append((priority, state))

    assert actual == expected
    assert queue.heap == []


def _context(
    *,
    fleet_ceiling: int = 20,
    runtime_minutes: int = 1,
    seed_prior: float = 30.0,
    protection=None,
) -> RouteCoordinatorContextV1:
    buckets = (
        DemandBucketEvidenceV1("outbound", 0, 1800, 10.0),
        DemandBucketEvidenceV1("outbound", 1800, 3600, 10.0),
    )
    inbound = tuple(
        DemandBucketEvidenceV1("inbound", item.start, item.end, item.observed_demand)
        for item in buckets
    )
    return RouteCoordinatorContextV1(
        route_id="X",
        route_name="Synthetic",
        endpoint_authority={"outbound": _authority(), "inbound": _authority("inbound")},
        demand_buckets={"outbound": buckets, "inbound": inbound},
        scenario_b_departures={
            "outbound": (0, 900, 1800, 2700, 3540),
            "inbound": (0, 900, 1800, 2700, 3540),
        },
        seed_headway_prior_minutes={"outbound": seed_prior, "inbound": seed_prior},
        planning_grid_seconds=900,
        runtime_minutes=runtime_minutes,
        minimum_layover_minutes=1,
        fleet_ceiling=fleet_ceiling,
        immutable_demand_sha256="immutable",
        service_protection_authority=protection,
    )


def _protection_authority():
    return build_closed_loop_service_protection_authority_v1(
        source_authority_profile="synthetic_verified_6a2b",
        source_authority_fingerprint="a" * 64,
        windows=(
            ClosedLoopProtectedServiceWindowV1(
                source_regime_id="PEAK-OUTBOUND-1",
                direction="outbound",
                protected_window_start=0,
                protected_window_end=1200,
                boundary_tolerance_minutes=0,
                maximum_headway_minutes=15,
                minimum_trip_count=3,
            ),
        ),
    )


def _all_neighbor_groups(state: ServicePlanStateV1):
    kwargs = {"floor_headway_minutes": 30.0}
    return (
        merge_adjacent_neighbors_v1(state, **kwargs),
        split_regime_neighbors_v1(state, planning_grid_seconds=900, **kwargs),
        shift_boundary_left_neighbors_v1(state, planning_grid_seconds=900, **kwargs),
        shift_boundary_right_neighbors_v1(state, planning_grid_seconds=900, **kwargs),
        move_one_trip_left_to_right_neighbors_v1(state, **kwargs),
        move_one_trip_right_to_left_neighbors_v1(state, **kwargs),
        tail_absorb_one_neighbors_v1(state, **kwargs),
        tail_release_one_neighbors_v1(state, **kwargs),
    )


def _compile(state: ServicePlanStateV1, limit: int = 8):
    return compile_service_plan_frontier_v1(
        state,
        endpoint_authority=_authority(state.direction, fixed_last=state.fixed_last_departure),
        compile_frontier_limit=limit,
    )


def _run_scripted_pair_feedback_search(monkeypatch, pair_feedback_script):
    seeds = (
        _state("outbound", first_count=2, second_count=2),
        _state("inbound", first_count=2, second_count=2),
    )
    neighbor_calls = []
    pair_call_index = 0

    def compiler(state, **_kwargs):
        return SimpleNamespace(variants=_compile(state, limit=2).variants, failure=None)

    def without_direction_feedback(candidate, **kwargs):
        metrics, _ = evaluate_actual_service_v1(candidate, **kwargs)
        return metrics, ()

    def scripted_pair_feedback(_outbound, _inbound, *, context):
        nonlocal pair_call_index
        del context
        feedback = pair_feedback_script[pair_call_index]
        pair_call_index += 1
        return None, feedback

    def recording_neighbors(state, *, feedback, **kwargs):
        neighbors = generate_targeted_neighbors_v1(state, feedback=feedback, **kwargs)
        neighbor_calls.append(
            (
                service_plan_fingerprint_v1(state),
                tuple(item.code for item in feedback),
                tuple(item.magnitude for item in feedback),
                len(neighbors),
            )
        )
        return neighbors

    monkeypatch.setattr(coordinator, "evaluate_actual_service_v1", without_direction_feedback)
    monkeypatch.setattr(coordinator, "evaluate_operating_pair_v1", scripted_pair_feedback)
    monkeypatch.setattr(coordinator, "generate_targeted_neighbors_v1", recording_neighbors)
    result = search_route_service_plans_v1(
        context=_context(),
        seeds=seeds,
        budget=CoordinatorSearchBudgetV1(2, 512, 2, 8, 8),
        compiler=compiler,
    )
    assert pair_call_index == len(pair_feedback_script) == 4
    return result, neighbor_calls, seeds


def _pair(pair_id: str, values: tuple[float | int, ...]) -> OperatingPairCandidateV1:
    metrics = OperatingPairMetricsV1(*values, max_excess_terminal_wait=0)
    return OperatingPairCandidateV1(
        pair_fingerprint=pair_id,
        outbound=None,  # type: ignore[arg-type]
        inbound=None,  # type: ignore[arg-type]
        metrics=metrics,
        fleet_ceiling=99,
        minimum_connection_layover_minutes=None,
        feedback=(),
        history=(),
    )


def _variant_with_departures(departures: tuple[int, ...], direction: str = "outbound"):
    base = _compile(_state(direction), limit=1).variants[0]
    return dataclasses.replace(
        base,
        compilation_fingerprint=f"synthetic-{direction}-{departures}",
        compilation=dataclasses.replace(base.compilation, exact_departures=departures),
    )


def _response_evidence(
    rates: tuple[float, ...],
    *,
    direction: str = "outbound",
    boundaries: tuple[int, ...] = (0, 1200, 2400, 3600),
) -> tuple[DemandResponseRegimeEvidenceV1, ...]:
    return tuple(
        DemandResponseRegimeEvidenceV1(
            regime_id=f"D-{direction}-{index}",
            direction=direction,
            start=start,
            end=end,
            integrated_demand_mass=rate * (end - start) / 3600,
            demand_rate_per_hour=rate,
        )
        for index, (start, end, rate) in enumerate(
            zip(boundaries[:-1], boundaries[1:], rates, strict=True)
        )
    )


def _directional_record(
    state: ServicePlanStateV1,
    variant,
    *,
    state_fingerprint: str | None = None,
) -> DirectionalCompilationCandidateV1:
    metrics, feedback = evaluate_actual_service_v1(
        variant,
        demand_buckets=_context().demand_buckets[state.direction],
        scenario_b_departures=_context().scenario_b_departures[state.direction],
    )
    return DirectionalCompilationCandidateV1(
        state=state,
        state_fingerprint=state_fingerprint or service_plan_fingerprint_v1(state),
        compile_variant=variant,
        metrics=metrics,
        feedback=feedback,
        history=(),
    )


def test_baseline_seed_prior_is_not_global_hard_validity_or_tail_protection() -> None:
    parent = ServicePlanStateV1(
        route_id="X",
        direction="outbound",
        fixed_first_departure=0,
        fixed_last_departure=5340,
        service_regimes=(
            ServiceRegimeDecisionV1(0, 1800, 5),
            ServiceRegimeDecisionV1(1800, 5400, 3),
        ),
        seed_id="BASELINE-PRIOR-15",
    )
    relaxed = tail_release_one_neighbors_v1(parent, floor_headway_minutes=None)
    assert [item.state.trip_count_vector for item in relaxed] == [(6, 2)]
    assert tail_release_one_neighbors_v1(parent, floor_headway_minutes=15.0) == ()
    tail_flexible = relaxed[0].state

    assert (
        validate_service_plan_state_v1(
            tail_flexible,
            authoritative_total_trips=8,
            planning_grid_seconds=900,
            floor_headway_minutes=None,
        )
        == ()
    )
    assert "MINIMUM_SERVICE_FLOOR" in validate_service_plan_state_v1(
        tail_flexible,
        authoritative_total_trips=8,
        planning_grid_seconds=900,
        floor_headway_minutes=15.0,
    )

    endpoint = OperationalEndpointAuthorityV1(
        route_id="X",
        direction="outbound",
        analysis_window_start=0,
        analysis_window_end=5400,
        fixed_first_departure=0,
        fixed_last_departure=5340,
        authority_source="test",
    )
    frontier = compile_service_plan_frontier_v1(
        tail_flexible,
        endpoint_authority=endpoint,
        compile_frontier_limit=8,
    )
    assert frontier.variants
    candidate = frontier.variants[0].compilation
    assert candidate.service_regimes[-1].uniform_headway_minutes > 15
    assert candidate.exact_departures[0] == tail_flexible.fixed_first_departure
    assert candidate.exact_departures[-1] == tail_flexible.fixed_last_departure
    assert len(candidate.exact_departures) == tail_flexible.total_trips
    assert all(
        later > earlier and (later - earlier) % 60 == 0
        for service in candidate.service_regimes
        for earlier, later in zip(service.departures, service.departures[1:], strict=False)
    )
    protection = validate_closed_loop_service_protection_v1(
        authority=None,
        direction="outbound",
        exact_departures=candidate.exact_departures,
    )
    assert protection.passed
    assert protection.authority_status == VALID_NO_ENFORCEABLE_WINDOW


def test_protected_peak_rejects_exact_candidate_before_fleet_while_tail_stays_free(
    monkeypatch,
) -> None:
    outbound_state = _state("outbound", first_count=2, second_count=2)
    inbound_state = _state("inbound", first_count=3, second_count=2)
    weak = next(
        item
        for item in _compile(outbound_state, limit=8).variants
        if item.compilation.exact_departures == (0, 1200, 2400, 3540)
    )
    inbound = _compile(inbound_state, limit=8).variants[0]
    assert weak.compilation.service_regimes[-1].uniform_headway_minutes > 15

    def compiler(state, **_kwargs):
        return SimpleNamespace(
            variants=(weak,) if state.direction == "outbound" else (inbound,),
            failure=None,
        )

    fleet_calls = 0
    scored_directions: list[str] = []
    real_evaluate = coordinator.evaluate_actual_service_v1

    def unexpected_fleet(**_kwargs):
        nonlocal fleet_calls
        fleet_calls += 1
        raise AssertionError("protected rejection must occur before fleet validation")

    def recording_evaluate(candidate, **kwargs):
        scored_directions.append(candidate.compilation.direction)
        return real_evaluate(candidate, **kwargs)

    monkeypatch.setattr(coordinator, "validate_fleet_combination_v1", unexpected_fleet)
    monkeypatch.setattr(coordinator, "evaluate_actual_service_v1", recording_evaluate)
    result = search_route_service_plans_v1(
        context=_context(seed_prior=15.0, protection=_protection_authority()),
        seeds=(outbound_state, inbound_state),
        budget=CoordinatorSearchBudgetV1(2, 16, 1, 4, 4),
        compiler=compiler,
    )

    assert fleet_calls == 0
    assert "outbound" not in scored_directions
    assert result.statistics.protected_compile_variants_rejected == 1
    assert {item.source_regime_id for item in result.protection_violations} == {"PEAK-OUTBOUND-1"}
    assert {item.violated_rule for item in result.protection_violations} >= {
        PROTECTED_TRIP_COUNT_BELOW_MINIMUM,
        PROTECTED_INTERNAL_HEADWAY_ABOVE_MAXIMUM,
    }


def test_exact_candidate_satisfying_protected_peak_reaches_fleet_validation() -> None:
    outbound_state = _state("outbound", first_count=3, second_count=2)
    inbound_state = _state("inbound", first_count=3, second_count=2)
    outbound = next(
        item
        for item in _compile(outbound_state, limit=8).variants
        if item.compilation.exact_departures == (0, 600, 1200, 1800, 3540)
    )
    inbound = _compile(inbound_state, limit=8).variants[0]
    assert outbound.compilation.service_regimes[-1].uniform_headway_minutes > 15

    def compiler(state, **_kwargs):
        return SimpleNamespace(
            variants=(outbound,) if state.direction == "outbound" else (inbound,),
            failure=None,
        )

    result = search_route_service_plans_v1(
        context=_context(seed_prior=15.0, protection=_protection_authority()),
        seeds=(outbound_state, inbound_state),
        budget=CoordinatorSearchBudgetV1(2, 16, 1, 4, 4),
        compiler=compiler,
    )

    assert result.statistics.protected_compile_variants_rejected == 0
    assert result.statistics.fleet_validations_run == 1
    assert result.pareto_frontier
    assert result.protection_violations == ()


def test_invalid_translated_authority_fails_closed_before_compile_or_fleet(
    monkeypatch,
) -> None:
    valid = _protection_authority()
    invalid = dataclasses.replace(
        valid,
        windows=(dataclasses.replace(valid.windows[0], maximum_headway_minutes=16),),
    )
    compile_calls = 0
    fleet_calls = 0

    def unexpected_compile(*_args, **_kwargs):
        nonlocal compile_calls
        compile_calls += 1
        raise AssertionError("invalid authority must stop before unprotected compilation")

    def unexpected_fleet(**_kwargs):
        nonlocal fleet_calls
        fleet_calls += 1
        raise AssertionError("invalid authority must stop before fleet validation")

    monkeypatch.setattr(coordinator, "validate_fleet_combination_v1", unexpected_fleet)
    context = _context(seed_prior=15.0, protection=invalid)
    result = search_route_service_plans_v1(
        context=context,
        seeds=(_state("outbound"), _state("inbound")),
        compiler=unexpected_compile,
    )
    payload = route_result_payload_v1(
        context=context,
        result=result,
        prior_artifact_verification={},
    )

    assert result.status == INVALID_TRANSLATED_PROTECTION_AUTHORITY
    assert result.feedback_code_counts == {INVALID_TRANSLATED_PROTECTION_AUTHORITY: 1}
    assert result.evaluated_state_fingerprints == ()
    assert result.statistics.states_evaluated == 0
    assert result.statistics.fleet_validations_run == 0
    assert FLEET_LIMIT_EXCEEDED not in result.feedback_code_counts
    assert compile_calls == fleet_calls == 0
    assert payload["protected_service_authority"]["status"] == (
        INVALID_TRANSLATED_PROTECTION_AUTHORITY
    )
    assert payload["protected_service_authority"]["validation_errors"]
    assert payload["seed_headway_prior_minutes"] == {"inbound": 15.0, "outbound": 15.0}


def test_protected_authority_translation_is_deterministic_and_fact_sensitive() -> None:
    regime = ProtectedServiceFloorEnforcementRegimeV1(
        regime_id="PEAK-OUTBOUND-1",
        direction=TripRidershipDirectionV1.OUTBOUND,
        ordered_b_trip_ids=("O01", "O02", "O03"),
        maximum_future_c_headway_minutes=15,
        minimum_future_c_trip_count=3,
        protected_window_start=0,
        protected_window_end=1800,
        future_boundary_tolerance_minutes=2,
        donor_removal_prohibited=True,
    )
    source = ProtectedServiceFloorEnforcementAuthorityV1(
        scenario_b_fingerprint="1" * 64,
        assessment_fingerprint="2" * 64,
        policy_fingerprint="3" * 64,
        regime_derivation_fingerprint="4" * 64,
        trip_ridership_input_fingerprint="5" * 64,
        trip_ridership_analysis_fingerprint="6" * 64,
        target_load_factor=0.85,
        maximum_load_factor=0.9,
        protected_regimes=(regime,),
        enforcement_profile=PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
        enforcement_fingerprint="7" * 64,
    )

    first = translate_protected_service_floor_authority_v1(source)
    second = translate_protected_service_floor_authority_v1(source)
    changed = translate_protected_service_floor_authority_v1(
        dataclasses.replace(
            source,
            protected_regimes=(dataclasses.replace(regime, maximum_future_c_headway_minutes=16),),
        )
    )

    assert first.status == ACTIVE_TRANSLATED_PROTECTED_WINDOWS
    assert first.windows == second.windows
    assert first.translation_fingerprint == second.translation_fingerprint
    assert changed.translation_fingerprint != first.translation_fingerprint
    assert not hasattr(first.windows[0], "ordered_b_trip_ids")


def test_no_protected_authority_is_explicit_and_does_not_promote_seed_prior() -> None:
    result = search_route_service_plans_v1(
        context=_context(seed_prior=15.0),
        seeds=(_state(),),
        budget=CoordinatorSearchBudgetV1(1, 8, 1, 2, 2),
    )
    payload = route_result_payload_v1(
        context=_context(seed_prior=15.0),
        result=result,
        prior_artifact_verification={},
    )

    authority = payload["protected_service_authority"]
    assert authority["status"] == VALID_NO_ENFORCEABLE_WINDOW
    assert authority["authority_supplied"] is False
    assert authority["windows"] == []
    assert payload["seed_headway_prior_minutes"] == {"inbound": 15.0, "outbound": 15.0}


def test_fingerprint_cache_prevents_repeated_state_evaluation() -> None:
    state = _state()
    duplicate = dataclasses.replace(state, seed_id="DUPLICATE")
    calls: list[str] = []

    def compiler(value, **_kwargs):
        calls.append(service_plan_fingerprint_v1(value))
        return SimpleNamespace(variants=(), failure=None)

    result = search_route_service_plans_v1(
        context=_context(),
        seeds=(state, duplicate),
        budget=CoordinatorSearchBudgetV1(
            max_service_plan_evaluations=1,
            max_open_states=8,
            max_compile_frontier_per_state=2,
            max_directional_compilations=4,
            max_pair_frontier=4,
        ),
        compiler=compiler,
    )
    assert len(calls) == len(set(calls)) == 1
    assert result.statistics.duplicate_states_skipped >= 1


def test_merge_adjacent_neighbor() -> None:
    state = _state()
    neighbors = merge_adjacent_neighbors_v1(state, floor_headway_minutes=30.0)
    assert len(neighbors) == 1
    assert neighbors[0].move == ServicePlanMoveV1.MERGE_ADJACENT
    assert neighbors[0].state.trip_count_vector == (8,)


def test_split_regime_enumerates_integer_alternatives() -> None:
    state = ServicePlanStateV1(
        "X",
        "outbound",
        0,
        3540,
        (ServiceRegimeDecisionV1(0, 3600, 8),),
        "TEST",
    )
    neighbors = split_regime_neighbors_v1(
        state,
        planning_grid_seconds=900,
        floor_headway_minutes=30.0,
    )
    vectors = {item.state.trip_count_vector for item in neighbors}
    assert (2, 6) in vectors
    assert (4, 4) in vectors
    assert (6, 2) in vectors


def test_boundary_shift_left_and_right_one_bucket() -> None:
    state = _state()
    left = shift_boundary_left_neighbors_v1(
        state, planning_grid_seconds=900, floor_headway_minutes=30.0
    )
    right = shift_boundary_right_neighbors_v1(
        state, planning_grid_seconds=900, floor_headway_minutes=30.0
    )
    assert {item.state.boundaries for item in left} == {(900,)}
    assert {item.state.boundaries for item in right} == {(2700,)}


def test_one_trip_movement_both_directions() -> None:
    state = _state()
    left_to_right = move_one_trip_left_to_right_neighbors_v1(state, floor_headway_minutes=30.0)
    right_to_left = move_one_trip_right_to_left_neighbors_v1(state, floor_headway_minutes=30.0)
    assert left_to_right[0].state.trip_count_vector == (3, 5)
    assert right_to_left[0].state.trip_count_vector == (5, 3)


def test_every_neighborhood_move_preserves_fixed_total() -> None:
    state = _state(first_count=5, second_count=5)
    neighbors = [item for group in _all_neighbor_groups(state) for item in group]
    assert neighbors
    assert {item.state.total_trips for item in neighbors} == {state.total_trips}


def test_immutable_demand_evidence_is_frozen_and_unchanged() -> None:
    bucket = DemandBucketEvidenceV1("outbound", 0, 1800, 10.0)
    before = dataclasses.asdict(bucket)
    with pytest.raises(dataclasses.FrozenInstanceError):
        bucket.observed_demand = 12.0  # type: ignore[misc]
    assert dataclasses.asdict(bucket) == before


def test_compile_frontier_preserves_multiple_clean_variants() -> None:
    state = _state(first_count=2, second_count=2)
    frontier = _compile(state)
    assert len(frontier.variants) >= 2
    assert len({item.compilation_fingerprint for item in frontier.variants}) == len(
        frontier.variants
    )


def test_compile_local_dominance_does_not_eliminate_distinct_exact_phase() -> None:
    frontier = _compile(_state(first_count=2, second_count=3), limit=5)
    assert len(frontier.variants) == 5
    local_vectors = [
        (
            item.headway_quantization,
            item.actual_service_regime_count,
            item.phase_edge_quality_minutes,
        )
        for item in frontier.variants
    ]
    better = local_vectors[0]
    worse = local_vectors[-1]
    assert all(left <= right for left, right in zip(better, worse, strict=True))
    assert any(left < right for left, right in zip(better, worse, strict=True))
    assert (
        frontier.variants[0].compilation.exact_departures
        != frontier.variants[-1].compilation.exact_departures
    )
    assert frontier.variants_dominance_pruned == 0


def test_directional_dominance_does_not_eliminate_distinct_exact_phase() -> None:
    state = _state(first_count=2, second_count=2)
    variants = _compile(state, limit=2).variants
    better = _directional_record(state, variants[0])
    worse = dataclasses.replace(
        _directional_record(state, variants[1]),
        metrics=dataclasses.replace(
            better.metrics,
            observed_demand_mismatch=better.metrics.observed_demand_mismatch + 1.0,
            actual_service_regime_count=better.metrics.actual_service_regime_count + 1,
            max_frequency_jump=better.metrics.max_frequency_jump + 1.0,
            total_frequency_variation=better.metrics.total_frequency_variation + 1.0,
            moved_trips_vs_b=better.metrics.moved_trips_vs_b + 1,
        ),
        compile_variant=dataclasses.replace(
            variants[1],
            headway_quantization=better.compile_variant.headway_quantization + 1.0,
            phase_edge_quality_minutes=(better.compile_variant.phase_edge_quality_minutes + 1),
        ),
    )
    a = coordinator._directional_vector(better)
    b = coordinator._directional_vector(worse)
    assert all(left <= right for left, right in zip(a, b, strict=True))
    assert any(left < right for left, right in zip(a, b, strict=True))
    assert (
        better.compile_variant.compilation.exact_departures
        != worse.compile_variant.compilation.exact_departures
    )

    retained = coordinator._retain_directional_archive((worse, better), limit=2)
    assert [item.compile_variant.compilation_fingerprint for item in retained] == [
        better.compile_variant.compilation_fingerprint,
        worse.compile_variant.compilation_fingerprint,
    ]


def test_phase_distinct_directional_candidate_reaches_exact_fleet_validation(
    monkeypatch,
) -> None:
    outbound_state = _state("outbound", first_count=2, second_count=2)
    inbound_state = _state("inbound", first_count=2, second_count=2)
    outbound_frontier = _compile(outbound_state, limit=8)
    inbound_frontier = _compile(inbound_state, limit=8)
    locally_preferred = outbound_frontier.variants[0]
    phase_distinct = outbound_frontier.variants[1]
    opposite = inbound_frontier.variants[0]
    assert locally_preferred.headway_quantization < phase_distinct.headway_quantization

    def compiler(state, **_kwargs):
        variants = (
            (locally_preferred, phase_distinct) if state.direction == "outbound" else (opposite,)
        )
        return SimpleNamespace(variants=variants, failure=None)

    exact_validations: dict[tuple[int, ...], tuple[str, int | None]] = {}
    exact_validator = coordinator.validate_fleet_combination_v1

    def recording_validator(**kwargs):
        validation = exact_validator(**kwargs)
        exact_validations[kwargs["outbound"].exact_departures] = (
            validation.status,
            validation.fleet_requirement,
        )
        return validation

    monkeypatch.setattr(coordinator, "validate_fleet_combination_v1", recording_validator)
    result = search_route_service_plans_v1(
        context=_context(fleet_ceiling=3, runtime_minutes=15),
        seeds=(outbound_state, inbound_state),
        budget=CoordinatorSearchBudgetV1(2, 16, 2, 2, 8),
        compiler=compiler,
    )

    assert exact_validations[locally_preferred.compilation.exact_departures] == (
        "FLEET_INFEASIBLE",
        4,
    )
    assert exact_validations[phase_distinct.compilation.exact_departures] == (
        "FLEET_FEASIBLE",
        3,
    )
    assert result.pareto_frontier
    assert {
        item.outbound.compile_variant.compilation_fingerprint for item in result.pareto_frontier
    } == {phase_distinct.compilation_fingerprint}


def test_fleet_validation_happens_after_both_direction_compilations(monkeypatch) -> None:
    events: list[str] = []
    real_validate = coordinator.validate_fleet_combination_v1

    def compiler(state, **kwargs):
        events.append(f"compile:{state.direction}")
        return compile_service_plan_frontier_v1(state, **kwargs)

    def validator(**kwargs):
        events.append("fleet")
        return real_validate(**kwargs)

    monkeypatch.setattr(coordinator, "validate_fleet_combination_v1", validator)
    search_route_service_plans_v1(
        context=_context(),
        seeds=(
            _state("outbound", first_count=2, second_count=2),
            _state("inbound", first_count=2, second_count=2),
        ),
        budget=CoordinatorSearchBudgetV1(2, 16, 2, 8, 8),
        compiler=compiler,
    )
    assert "fleet" in events
    assert events.index("fleet") > events.index("compile:outbound")
    assert events.index("fleet") > events.index("compile:inbound")


def test_compiled_actual_frequency_jump_drives_feedback() -> None:
    frontier = _compile(_state(first_count=2, second_count=2))
    metrics, feedback = evaluate_actual_service_v1(
        frontier.variants[0],
        demand_buckets=_context().demand_buckets["outbound"],
        scenario_b_departures=_context().scenario_b_departures["outbound"],
    )
    assert metrics.max_frequency_jump > 0
    assert LARGEST_SERVICE_FREQUENCY_JUMP in {item.code for item in feedback}


def test_redundant_compiled_boundary_causes_merge_proposal() -> None:
    state = _state(first_count=3, second_count=3, fixed_last=3000)
    frontier = _compile(state)
    _, feedback = evaluate_actual_service_v1(
        frontier.variants[0],
        demand_buckets=_context().demand_buckets["outbound"],
        scenario_b_departures=(0, 600, 1200, 1800, 2400, 3000),
    )
    assert REDUNDANT_SERVICE_BOUNDARY in {item.code for item in feedback}
    neighbors = generate_targeted_neighbors_v1(
        state,
        feedback=feedback,
        planning_grid_seconds=900,
        floor_headway_minutes=30.0,
    )
    assert any(item.move == ServicePlanMoveV1.MERGE_ADJACENT for item in neighbors)


def test_large_service_shock_generates_smoothing_moves() -> None:
    feedback = (FeedbackEvidenceV1(LARGEST_SERVICE_FREQUENCY_JUMP, "outbound", 1800, 0),)
    neighbors = generate_targeted_neighbors_v1(
        _state(first_count=5, second_count=5),
        feedback=feedback,
        planning_grid_seconds=900,
        floor_headway_minutes=30.0,
    )
    moves = {item.move for item in neighbors if item.priority == 0}
    assert ServicePlanMoveV1.SPLIT_REGIME in moves
    assert ServicePlanMoveV1.MOVE_ONE_TRIP_LEFT_TO_RIGHT in moves
    assert ServicePlanMoveV1.SHIFT_BOUNDARY_LEFT in moves


def test_fleet_exceeded_feedback_generates_targeted_neighbors() -> None:
    feedback = (FeedbackEvidenceV1(FLEET_LIMIT_EXCEEDED, "pair", magnitude=1),)
    neighbors = generate_targeted_neighbors_v1(
        _state(first_count=5, second_count=5),
        feedback=feedback,
        planning_grid_seconds=900,
        floor_headway_minutes=30.0,
    )
    moves = {item.move for item in neighbors if item.priority == 0}
    assert ServicePlanMoveV1.SHIFT_BOUNDARY_LEFT in moves
    assert ServicePlanMoveV1.MOVE_ONE_TRIP_RIGHT_TO_LEFT in moves


def test_repeated_fleet_feedback_expands_each_semantic_parent_once(monkeypatch) -> None:
    feedback_script = tuple(
        (FeedbackEvidenceV1(FLEET_LIMIT_EXCEEDED, "pair", magnitude=magnitude),)
        for magnitude in (1, 2, 1, 2)
    )
    result, neighbor_calls, seeds = _run_scripted_pair_feedback_search(monkeypatch, feedback_script)
    fleet_calls = [call for call in neighbor_calls if call[1] == (FLEET_LIMIT_EXCEEDED,)]
    parent_fingerprints = {service_plan_fingerprint_v1(state) for state in seeds}

    assert result.statistics.fleet_validations_run == 4
    assert result.feedback_code_counts[FLEET_LIMIT_EXCEEDED] == 4
    assert result.statistics.fleet_feedback_expansion_requests == 8
    assert result.statistics.fleet_feedback_expansions_executed == 2
    assert result.statistics.fleet_feedback_expansions_skipped == 6
    assert len(fleet_calls) == 2
    assert {call[0] for call in fleet_calls} == parent_fingerprints
    assert {call[2] for call in fleet_calls} == {(1,)}
    assert result.statistics.states_generated == 2 + sum(call[3] for call in neighbor_calls)


def test_nonfleet_and_mixed_feedback_are_not_suppressed_by_fleet_cache(monkeypatch) -> None:
    localized = FeedbackEvidenceV1(
        DEMAND_UNDERSERVED_INTERVAL,
        "outbound",
        interval_start=0,
        interval_end=1800,
    )
    feedback_script = (
        (FeedbackEvidenceV1(FLEET_LIMIT_EXCEEDED, "pair", magnitude=1),),
        (localized,),
        (FeedbackEvidenceV1(FLEET_LIMIT_EXCEEDED, "pair", magnitude=9), localized),
        (FeedbackEvidenceV1(FLEET_LIMIT_EXCEEDED, "pair", magnitude=2),),
    )
    result, neighbor_calls, _ = _run_scripted_pair_feedback_search(monkeypatch, feedback_script)
    fleet_calls = [call for call in neighbor_calls if call[1] == (FLEET_LIMIT_EXCEEDED,)]
    localized_calls = [call for call in neighbor_calls if call[1] == (DEMAND_UNDERSERVED_INTERVAL,)]
    mixed_calls = [
        call
        for call in neighbor_calls
        if call[1] == (FLEET_LIMIT_EXCEEDED, DEMAND_UNDERSERVED_INTERVAL)
    ]

    assert len(fleet_calls) == len(localized_calls) == len(mixed_calls) == 2
    assert all(call[3] > 0 for call in (*localized_calls, *mixed_calls))
    assert result.statistics.fleet_feedback_expansion_requests == 4
    assert result.statistics.fleet_feedback_expansions_executed == 2
    assert result.statistics.fleet_feedback_expansions_skipped == 2
    assert result.feedback_code_counts[FLEET_LIMIT_EXCEEDED] == 3
    assert result.feedback_code_counts[DEMAND_UNDERSERVED_INTERVAL] == 2
    assert result.feedback_code_counts[FLEET_LIMIT_EXCEEDED] > (
        result.statistics.fleet_feedback_expansions_executed
    )


def test_fleet_feedback_control_is_deterministic(monkeypatch) -> None:
    feedback_script = tuple(
        (FeedbackEvidenceV1(FLEET_LIMIT_EXCEEDED, "pair", magnitude=magnitude),)
        for magnitude in (1, 2, 1, 2)
    )
    first, first_calls, _ = _run_scripted_pair_feedback_search(monkeypatch, feedback_script)
    second, second_calls, _ = _run_scripted_pair_feedback_search(monkeypatch, feedback_script)

    assert first.status == second.status
    assert dataclasses.asdict(first.statistics) == dataclasses.asdict(second.statistics)
    assert first.evaluated_state_fingerprints == second.evaluated_state_fingerprints
    assert tuple(item.pair_fingerprint for item in first.pareto_frontier) == tuple(
        item.pair_fingerprint for item in second.pareto_frontier
    )
    assert first.feedback_code_counts == second.feedback_code_counts
    assert first_calls == second_calls


def test_tail_over_service_generates_release_proposal() -> None:
    neighbors = generate_targeted_neighbors_v1(
        _state(first_count=5, second_count=5),
        feedback=(FeedbackEvidenceV1(TAIL_OVER_SERVICE, "outbound"),),
        planning_grid_seconds=900,
        floor_headway_minutes=30.0,
    )
    assert any(
        item.move == ServicePlanMoveV1.TAIL_RELEASE_ONE and item.priority == 0 for item in neighbors
    )


def test_dominated_candidate_is_removed_from_pareto() -> None:
    better = _pair("better", (1.0, 5.0, 2, 0.1, 0.2, 1, 3, 4))
    worse = _pair("worse", (2.0, 6.0, 3, 0.2, 0.3, 2, 4, 5))
    assert dominates_operating_pair_v1(better, worse)
    assert update_operating_pair_pareto_v1((worse,), better) == (better,)


def test_nondominated_tradeoff_candidates_survive() -> None:
    demand_best = _pair("demand", (1.0, 5.0, 3, 0.2, 0.3, 2, 4, 5))
    fleet_best = _pair("fleet", (2.0, 6.0, 2, 0.1, 0.2, 1, 3, 4))
    frontier = update_operating_pair_pareto_v1((demand_best,), fleet_best)
    assert {item.pair_fingerprint for item in frontier} == {"demand", "fleet"}


def test_search_budget_stops_deterministically() -> None:
    result = search_route_service_plans_v1(
        context=_context(),
        seeds=(
            _state("outbound", first_count=2, second_count=2),
            _state("inbound", first_count=2, second_count=2),
        ),
        budget=CoordinatorSearchBudgetV1(1, 16, 2, 8, 8),
    )
    assert result.statistics.states_evaluated == 1
    assert result.statistics.budget_exhausted is True
    assert result.status == SEARCH_BUDGET_EXHAUSTED


def test_budget_exhaustion_returns_useful_frontier() -> None:
    result = search_route_service_plans_v1(
        context=_context(),
        seeds=(
            _state("outbound", first_count=2, second_count=2),
            _state("inbound", first_count=2, second_count=2),
        ),
        budget=CoordinatorSearchBudgetV1(2, 16, 2, 8, 8),
    )
    assert result.status == SEARCH_BUDGET_EXHAUSTED
    assert result.pareto_frontier


def test_compile_archive_and_pair_retention_are_deterministic_and_bounded() -> None:
    signatures = []
    budget = CoordinatorSearchBudgetV1(2, 16, 4, 4, 4)
    seeds = (
        _state("outbound", first_count=2, second_count=2),
        _state("inbound", first_count=2, second_count=2),
    )
    archive_source = _compile(seeds[0], limit=8).variants[:6]
    archive_records = tuple(
        _directional_record(
            seeds[0],
            variant,
            state_fingerprint=("STATE-0" if index < 3 else f"STATE-{index - 2}"),
        )
        for index, variant in enumerate(archive_source)
    )
    assert len(_compile(seeds[0], limit=1).variants) == 1
    for _ in range(20):
        compile_frontier = _compile(seeds[0], limit=budget.max_compile_frontier_per_state)
        archive = coordinator._retain_directional_archive(
            archive_records,
            limit=budget.max_directional_compilations,
        )
        result = search_route_service_plans_v1(context=_context(), seeds=seeds, budget=budget)
        assert len(compile_frontier.variants) <= budget.max_compile_frontier_per_state
        assert len(archive) <= budget.max_directional_compilations
        assert len({item.state_fingerprint for item in archive}) == 4
        assert len(result.pareto_frontier) <= budget.max_pair_frontier
        assert result.statistics.states_evaluated <= budget.max_service_plan_evaluations
        signatures.append(
            (
                tuple(item.compilation_fingerprint for item in compile_frontier.variants),
                tuple(item.compile_variant.compilation_fingerprint for item in archive),
                tuple(item.pair_fingerprint for item in result.pareto_frontier),
                dataclasses.asdict(result.statistics),
                result.evaluated_state_fingerprints,
            )
        )
    assert len(set(repr(item) for item in signatures)) == 1


def test_prior_v1_v2_v3_artifacts_remain_byte_identical() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (repo_root / "config" / "service_plan_coordinator_frozen_prior_v1.json").read_text(
            encoding="utf-8"
        )
    )["sha256"]
    if any(not (repo_root / relative).is_file() for relative in manifest):
        pytest.skip("optional local pilot artifacts are unavailable")
    result = verify_frozen_prior_artifacts_v1(repo_root)
    assert result["unchanged"] is True
    assert len(result["sha256"]) >= 20


def test_compile_failure_feedback_keeps_search_finite() -> None:
    def compiler(_state, **_kwargs):
        return SimpleNamespace(variants=(), failure=None)

    result = search_route_service_plans_v1(
        context=_context(),
        seeds=(_state(),),
        budget=CoordinatorSearchBudgetV1(3, 8, 2, 4, 4),
        compiler=compiler,
    )
    assert result.statistics.states_evaluated <= 3
    assert CLEAN_BOUNDARY_UNCOMPILABLE in result.feedback_code_counts


def test_exact_expected_wait_integral_for_uniform_bucket() -> None:
    wait, maximum, per_bucket, mass = expected_passenger_wait_metrics_v1(
        (0, 600, 1200),
        (DemandBucketEvidenceV1("outbound", 0, 1200, 20.0),),
    )
    assert wait == pytest.approx(5.0)
    assert maximum == pytest.approx(5.0)
    assert per_bucket == pytest.approx((5.0,))
    assert mass == pytest.approx(20.0)


def test_same_bucket_counts_can_have_different_exact_wait_and_pareto_quality() -> None:
    buckets = (
        DemandBucketEvidenceV1("outbound", 0, 1800, 10.0),
        DemandBucketEvidenceV1("outbound", 1800, 3600, 10.0),
    )
    regular = _variant_with_departures((0, 600, 1200, 1800, 2400, 3000, 3600))
    uneven = _variant_with_departures((0, 300, 1500, 1800, 2100, 3300, 3600))
    regular_metrics, _ = evaluate_actual_service_v1(
        regular, demand_buckets=buckets, scenario_b_departures=regular.compilation.exact_departures
    )
    uneven_metrics, _ = evaluate_actual_service_v1(
        uneven, demand_buckets=buckets, scenario_b_departures=regular.compilation.exact_departures
    )
    assert regular_metrics.bucket_service_counts == uneven_metrics.bucket_service_counts
    assert regular_metrics.observed_demand_mismatch == pytest.approx(
        uneven_metrics.observed_demand_mismatch
    )
    assert regular_metrics.demand_weighted_expected_passenger_wait_minutes < (
        uneven_metrics.demand_weighted_expected_passenger_wait_minutes
    )

    lower_wait = _pair("lower", (1.0, 5.0, 2, 0.1, 0.2, 1, 3, 4))
    higher_wait = _pair("higher", (1.0, 7.5, 2, 0.1, 0.2, 1, 3, 4))
    assert dominates_operating_pair_v1(lower_wait, higher_wait)


def test_pair_expected_wait_is_weighted_by_directional_active_demand_mass() -> None:
    outbound_state = _state("outbound")
    inbound_state = _state("inbound")
    outbound = _directional_record(outbound_state, _compile(outbound_state, limit=1).variants[0])
    inbound = _directional_record(inbound_state, _compile(inbound_state, limit=1).variants[0])
    outbound = dataclasses.replace(
        outbound,
        metrics=dataclasses.replace(
            outbound.metrics,
            demand_weighted_expected_passenger_wait_minutes=4.0,
            active_demand_mass=10.0,
        ),
    )
    inbound = dataclasses.replace(
        inbound,
        metrics=dataclasses.replace(
            inbound.metrics,
            demand_weighted_expected_passenger_wait_minutes=10.0,
            active_demand_mass=30.0,
        ),
    )
    pair, feedback = evaluate_operating_pair_v1(outbound, inbound, context=_context())
    assert feedback == ()
    assert pair is not None
    assert pair.metrics.demand_weighted_expected_passenger_wait_minutes == pytest.approx(8.5)
    assert pair.metrics.demand_weighted_expected_passenger_wait_minutes != pytest.approx(7.0)


@pytest.mark.parametrize(
    ("departures", "expected_feedback_count", "expected_boundary"),
    [
        ((0, 600, 1200, 1500, 1800, 2100, 2400, 3000, 3600), 0, None),
        ((0, 600, 1200, 1800, 2400, 3000, 3600), 1, 1200),
        ((0, 300, 600, 900, 1200, 1800, 2400, 2700, 3000, 3300, 3600), 1, 1200),
    ],
)
def test_response_direction_feedback_is_localized_and_not_validity(
    departures: tuple[int, ...], expected_feedback_count: int, expected_boundary: int | None
) -> None:
    variant = _variant_with_departures(departures)
    metrics, feedback = evaluate_actual_service_v1(
        variant,
        demand_buckets=(DemandBucketEvidenceV1("outbound", 0, 3600, 30.0),),
        scenario_b_departures=departures,
        demand_response_regimes=_response_evidence((10.0, 40.0, 10.0)),
    )
    response_feedback = tuple(
        item for item in feedback if item.code == DEMAND_RESPONSE_DIRECTION_MISMATCH
    )
    assert len(response_feedback) == expected_feedback_count
    assert metrics.demand_response_transition_count == 2
    if response_feedback:
        item = response_feedback[0]
        assert item.boundary_time == expected_boundary
        assert item.left_demand_regime_id is not None
        assert item.right_demand_regime_id is not None
        assert item.delta_log_demand is not None
        assert item.delta_log_service is not None
        assert item.expected_demand_direction in {"UP", "DOWN"}
        assert item.observed_service_direction in {"UP", "DOWN", "FLAT"}
        assert item.sqrt_expected_delta_log_service is not None
        assert item.sqrt_response_residual is not None


def test_small_correctly_directed_response_is_not_a_mismatch() -> None:
    departures = (0, 600, 1200, 1600, 2000, 2400, 3000, 3600)
    metrics, feedback = evaluate_actual_service_v1(
        _variant_with_departures(departures),
        demand_buckets=(DemandBucketEvidenceV1("outbound", 0, 3600, 30.0),),
        scenario_b_departures=departures,
        demand_response_regimes=_response_evidence((10.0, 40.0, 10.0)),
    )
    assert DEMAND_RESPONSE_DIRECTION_MISMATCH not in {item.code for item in feedback}
    assert metrics.sqrt_seed_response_deviation is not None
    assert metrics.sqrt_seed_response_deviation > 0


def test_response_feedback_selects_one_deterministic_largest_severity() -> None:
    departures = tuple(range(0, 3601, 300))
    regimes = _response_evidence((10.0, 40.0, 20.0, 80.0), boundaries=(0, 900, 1800, 2700, 3600))
    selected = []
    for _ in range(10):
        _, feedback = evaluate_actual_service_v1(
            _variant_with_departures(departures),
            demand_buckets=(DemandBucketEvidenceV1("outbound", 0, 3600, 30.0),),
            scenario_b_departures=departures,
            demand_response_regimes=regimes,
        )
        response = [item for item in feedback if item.code == DEMAND_RESPONSE_DIRECTION_MISMATCH]
        assert len(response) == 1
        selected.append((response[0].boundary_time, response[0].left_demand_regime_id))
    assert set(selected) == {(900, "D-outbound-0")}


def _multi_regime_state() -> ServicePlanStateV1:
    return ServicePlanStateV1(
        route_id="X",
        direction="outbound",
        fixed_first_departure=0,
        fixed_last_departure=3540,
        service_regimes=tuple(
            ServiceRegimeDecisionV1(start, start + 900, 4) for start in (0, 900, 1800, 2700)
        ),
        seed_id="MULTI",
    )


def test_redundant_boundary_generates_only_the_diagnosed_merge() -> None:
    neighbors = generate_targeted_neighbors_v1(
        _multi_regime_state(),
        feedback=(FeedbackEvidenceV1(REDUNDANT_SERVICE_BOUNDARY, "outbound", boundary_time=1800),),
        planning_grid_seconds=300,
        floor_headway_minutes=None,
    )
    merges = [item for item in neighbors if item.move == ServicePlanMoveV1.MERGE_ADJACENT]
    assert {item.affected_index for item in merges} == {1}
    assert {item.move for item in neighbors} == {ServicePlanMoveV1.MERGE_ADJACENT}


def test_demand_interval_neighbors_do_not_touch_distant_regimes() -> None:
    neighbors = generate_targeted_neighbors_v1(
        _multi_regime_state(),
        feedback=(
            FeedbackEvidenceV1(
                DEMAND_UNDERSERVED_INTERVAL,
                "outbound",
                interval_start=900,
                interval_end=1800,
            ),
        ),
        planning_grid_seconds=300,
        floor_headway_minutes=None,
    )
    assert neighbors
    assert all(item.affected_index in {0, 1} for item in neighbors)
    assert not any(item.affected_index >= 2 for item in neighbors)


@pytest.mark.parametrize(
    ("boundary", "expected_split_indices", "expected_pair_indices"),
    [(1200, {1}, {0, 1}), (1800, {1, 2}, {1})],
)
def test_response_boundary_neighbors_stay_local(
    boundary: int, expected_split_indices: set[int], expected_pair_indices: set[int]
) -> None:
    neighbors = generate_targeted_neighbors_v1(
        _multi_regime_state(),
        feedback=(
            FeedbackEvidenceV1(
                DEMAND_RESPONSE_DIRECTION_MISMATCH,
                "outbound",
                boundary_time=boundary,
                interval_start=boundary - 300,
                interval_end=boundary + 300,
            ),
        ),
        planning_grid_seconds=300,
        floor_headway_minutes=None,
    )
    split_indices = {
        item.affected_index for item in neighbors if item.move == ServicePlanMoveV1.SPLIT_REGIME
    }
    pair_indices = {
        item.affected_index
        for item in neighbors
        if item.move
        in {
            ServicePlanMoveV1.SHIFT_BOUNDARY_LEFT,
            ServicePlanMoveV1.SHIFT_BOUNDARY_RIGHT,
            ServicePlanMoveV1.MOVE_ONE_TRIP_LEFT_TO_RIGHT,
            ServicePlanMoveV1.MOVE_ONE_TRIP_RIGHT_TO_LEFT,
        }
    }
    assert split_indices == expected_split_indices
    assert pair_indices == expected_pair_indices


@pytest.mark.parametrize(
    ("demand", "expected"),
    [((51.0, 49.0), False), ((80.0, 20.0), True)],
)
def test_demand_feedback_requires_one_trip_transfer_materiality(
    demand: tuple[float, float], expected: bool
) -> None:
    departures = (0, 900, 1800, 3540)
    buckets = (
        DemandBucketEvidenceV1("outbound", 0, 1800, demand[0]),
        DemandBucketEvidenceV1("outbound", 1800, 3600, demand[1]),
    )
    _, feedback = evaluate_actual_service_v1(
        _variant_with_departures(departures),
        demand_buckets=buckets,
        scenario_b_departures=departures,
    )
    codes = {item.code for item in feedback}
    assert (DEMAND_UNDERSERVED_INTERVAL in codes) is expected
    assert (DEMAND_OVERSERVED_INTERVAL in codes) is expected


@pytest.mark.parametrize(
    ("tail_share", "expected"),
    [(0.68, False), (0.80, True)],
)
def test_tail_feedback_requires_one_trip_materiality(tail_share: float, expected: bool) -> None:
    state = _state(first_count=2, second_count=4)
    variant = _compile(state, limit=1).variants[0]
    tail_start = variant.compilation.service_regimes[-1].first_departure
    buckets = (
        DemandBucketEvidenceV1("outbound", 0, tail_start, 1 - tail_share),
        DemandBucketEvidenceV1("outbound", tail_start, 3600, tail_share),
    )
    _, feedback = evaluate_actual_service_v1(
        variant,
        demand_buckets=buckets,
        scenario_b_departures=variant.compilation.exact_departures,
    )
    assert (TAIL_UNDER_SERVICE in {item.code for item in feedback}) is expected


def test_response_quality_anchor_survives_when_archive_has_capacity() -> None:
    state = _state(first_count=2, second_count=2)
    variants = _compile(state, limit=3).variants
    assert len(variants) == 3
    records = [_directional_record(state, variant) for variant in variants]
    flat = dataclasses.replace(
        records[0],
        metrics=dataclasses.replace(
            records[0].metrics,
            demand_weighted_expected_passenger_wait_minutes=1.0,
            sqrt_seed_response_deviation=1.0,
        ),
    )
    response = dataclasses.replace(
        records[1],
        metrics=dataclasses.replace(
            records[1].metrics,
            observed_demand_mismatch=records[0].metrics.observed_demand_mismatch + 10,
            demand_weighted_expected_passenger_wait_minutes=2.0,
            sqrt_seed_response_deviation=0.1,
        ),
    )
    distractor = dataclasses.replace(
        records[2],
        metrics=dataclasses.replace(
            records[2].metrics,
            observed_demand_mismatch=records[0].metrics.observed_demand_mismatch + 20,
            demand_weighted_expected_passenger_wait_minutes=3.0,
            sqrt_seed_response_deviation=2.0,
        ),
    )
    retained = coordinator._retain_directional_archive((distractor, response, flat), limit=2)
    assert {item.compile_variant.compilation_fingerprint for item in retained} == {
        flat.compile_variant.compilation_fingerprint,
        response.compile_variant.compilation_fingerprint,
    }


def test_exact_wait_anchor_survives_when_archive_has_capacity() -> None:
    state = _state(first_count=2, second_count=2)
    variants = _compile(state, limit=3).variants
    records = [_directional_record(state, variant) for variant in variants]
    local = dataclasses.replace(
        records[0],
        metrics=dataclasses.replace(
            records[0].metrics,
            demand_weighted_expected_passenger_wait_minutes=3.0,
            sqrt_seed_response_deviation=0.1,
        ),
    )
    wait = dataclasses.replace(
        records[1],
        metrics=dataclasses.replace(
            records[1].metrics,
            observed_demand_mismatch=records[0].metrics.observed_demand_mismatch + 10,
            demand_weighted_expected_passenger_wait_minutes=1.0,
            sqrt_seed_response_deviation=1.0,
        ),
    )
    distractor = dataclasses.replace(
        records[2],
        metrics=dataclasses.replace(
            records[2].metrics,
            observed_demand_mismatch=records[0].metrics.observed_demand_mismatch + 20,
            demand_weighted_expected_passenger_wait_minutes=4.0,
            sqrt_seed_response_deviation=2.0,
        ),
    )
    retained = coordinator._retain_directional_archive((distractor, wait, local), limit=2)
    assert {item.compile_variant.compilation_fingerprint for item in retained} == {
        local.compile_variant.compilation_fingerprint,
        wait.compile_variant.compilation_fingerprint,
    }


def test_default_search_budgets_are_unchanged() -> None:
    assert dataclasses.asdict(DEFAULT_COORDINATOR_SEARCH_BUDGET_V1) == {
        "max_service_plan_evaluations": 24,
        "max_open_states": 512,
        "max_compile_frontier_per_state": 4,
        "max_directional_compilations": 24,
        "max_pair_frontier": 512,
    }


@pytest.mark.parametrize(
    ("route_id", "workbook_name"),
    [
        ("6", "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx"),
        ("10", "Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx"),
    ],
)
def test_local_pilot_context_loads_canonical_response_evidence_and_compiles_smoke(
    route_id: str, workbook_name: str
) -> None:
    workspace = Path(__file__).resolve().parents[1]
    artifact_root = workspace
    demand_path = (
        artifact_root
        / "outputs"
        / "demand_regime_model_selection"
        / f"route_{route_id}_demand_regimes.json"
    )
    if not demand_path.is_file():
        artifact_root = workspace / "bus-schedule-optimizer-main-run"
        demand_path = (
            artifact_root
            / "outputs"
            / "demand_regime_model_selection"
            / f"route_{route_id}_demand_regimes.json"
        )
    workbook = workspace / workbook_name
    if not demand_path.is_file() or not workbook.is_file():
        pytest.skip("optional frozen pilot artifacts or route workbook are unavailable")
    context, seeds = load_route_coordinator_inputs_v1(
        repo_root=artifact_root, route_id=route_id, workbook_path=workbook
    )
    assert context.demand_response_regimes is not None
    assert set(context.demand_response_regimes) == {"outbound", "inbound"}
    for direction in ("outbound", "inbound"):
        regimes = context.demand_response_regimes[direction]
        assert regimes
        assert {item.direction for item in regimes} == {direction}
        seed = next(item for item in seeds if item.direction == direction)
        frontier = compile_service_plan_frontier_v1(
            seed,
            endpoint_authority=context.endpoint_authority[direction],
            compile_frontier_limit=1,
        )
        assert frontier.variants
        metrics, _ = evaluate_actual_service_v1(
            frontier.variants[0],
            demand_buckets=context.demand_buckets[direction],
            scenario_b_departures=context.scenario_b_departures[direction],
            demand_response_regimes=regimes,
        )
        assert metrics.active_demand_mass > 0
        assert metrics.demand_response_transition_count == len(regimes) - 1
