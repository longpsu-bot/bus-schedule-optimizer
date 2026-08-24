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
)
from bus_schedule_engine.service_plan_coordinator import (
    CLEAN_BOUNDARY_UNCOMPILABLE,
    FLEET_LIMIT_EXCEEDED,
    LARGEST_SERVICE_FREQUENCY_JUMP,
    REDUNDANT_SERVICE_BOUNDARY,
    SEARCH_BUDGET_EXHAUSTED,
    TAIL_OVER_SERVICE,
    CoordinatorSearchBudgetV1,
    DemandBucketEvidenceV1,
    DirectionalCompilationCandidateV1,
    FeedbackEvidenceV1,
    OperatingPairCandidateV1,
    OperatingPairMetricsV1,
    RouteCoordinatorContextV1,
    dominates_operating_pair_v1,
    evaluate_actual_service_v1,
    generate_targeted_neighbors_v1,
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


def _context(*, fleet_ceiling: int = 20, runtime_minutes: int = 1) -> RouteCoordinatorContextV1:
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
        service_floor_headway_minutes={"outbound": 30.0, "inbound": 30.0},
        planning_grid_seconds=900,
        runtime_minutes=runtime_minutes,
        minimum_layover_minutes=1,
        fleet_ceiling=fleet_ceiling,
        immutable_demand_sha256="immutable",
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
    better = _pair("better", (1.0, 2, 0.1, 0.2, 1, 3, 4))
    worse = _pair("worse", (2.0, 3, 0.2, 0.3, 2, 4, 5))
    assert dominates_operating_pair_v1(better, worse)
    assert update_operating_pair_pareto_v1((worse,), better) == (better,)


def test_nondominated_tradeoff_candidates_survive() -> None:
    demand_best = _pair("demand", (1.0, 3, 0.2, 0.3, 2, 4, 5))
    fleet_best = _pair("fleet", (2.0, 2, 0.1, 0.2, 1, 3, 4))
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
