from __future__ import annotations

from types import SimpleNamespace

import pytest

from bus_schedule_engine.contracts_v1.service_plan_state import (
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
)
from bus_schedule_engine.local_rhythm_refinement import (
    LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING,
    LOCAL_RHYTHM_FAMILY_PLAN_MAPPING_INVALID,
    LocalRhythmFamilyPlanMappingError,
    LocalRhythmRefinementPolicyV1,
    compile_local_states_v1,
    detect_local_rhythm_families_v1,
    enumerate_local_rhythm_states_v1,
    evaluate_directional_cross_product_v1,
    map_actual_family_to_planning_indices_v1,
    pair_rhythm_tuple_v1,
    retain_strict_directional_canonicalizations_v1,
    search_route_service_plans_with_local_rhythm_refinement_v1,
    strict_pair_rhythm_progress_v1,
)


def _actual(headway: int, *, trips: int = 4, regime_id: str | None = None):
    return SimpleNamespace(
        service_regime_id=regime_id or f"R-{headway}",
        uniform_headway_minutes=headway,
        trip_count=trips,
    )


def _state() -> ServicePlanStateV1:
    return ServicePlanStateV1(
        route_id="10",
        direction="outbound",
        fixed_first_departure=5 * 3600,
        fixed_last_departure=21 * 3600,
        service_regimes=(
            ServiceRegimeDecisionV1(5 * 3600, 9 * 3600, 13),
            ServiceRegimeDecisionV1(9 * 3600, 13 * 3600, 14),
            ServiceRegimeDecisionV1(13 * 3600, 17 * 3600, 12),
            ServiceRegimeDecisionV1(17 * 3600, 22 * 3600, 12),
        ),
        seed_id="seed",
    )


def _compilation(service_ids: tuple[str, ...]):
    return SimpleNamespace(
        demand_regime_slices=tuple(
            SimpleNamespace(demand_regime_id=f"opaque::{index}", service_regime_id=service_id)
            for index, service_id in enumerate(service_ids)
        )
    )


def test_detects_one_contiguous_family_and_weighted_representative_20() -> None:
    families = detect_local_rhythm_families_v1(
        [
            _actual(19, regime_id="A"),
            _actual(21, regime_id="B"),
            _actual(20, regime_id="C"),
            _actual(19, regime_id="D"),
        ]
    )

    assert len(families) == 1
    assert families[0].headways == (19, 21, 20, 19)
    assert families[0].canonical_representative == 20
    assert families[0].micro_rhythm_boundary_count == 3


def test_non_contiguous_near_equal_headways_are_not_clustered() -> None:
    assert detect_local_rhythm_families_v1([_actual(19), _actual(14), _actual(20)]) == ()


def test_two_trip_regime_breaks_a_sustained_family() -> None:
    assert detect_local_rhythm_families_v1([_actual(19), _actual(20, trips=2), _actual(19)]) == ()


def test_weighted_representative_chooses_19_for_19_heavy_family() -> None:
    family = detect_local_rhythm_families_v1(
        [_actual(19, trips=31), _actual(20, trips=6), _actual(19, trips=8)]
    )[0]

    assert family.internal_gap_counts == (30, 5, 7)
    assert family.canonical_representative == 19


def test_actual_family_maps_by_slice_order_without_plan_id_parsing() -> None:
    family = detect_local_rhythm_families_v1(
        [_actual(19, regime_id="S-A"), _actual(20, regime_id="S-B")]
    )[0]

    indices = map_actual_family_to_planning_indices_v1(
        state=_state(), compilation=_compilation(("OTHER", "S-A", "S-B", "TAIL")), family=family
    )

    assert indices == (1, 2)


def test_non_contiguous_planning_mapping_fails_closed() -> None:
    family = detect_local_rhythm_families_v1(
        [_actual(19, regime_id="S-A"), _actual(20, regime_id="S-B")]
    )[0]

    with pytest.raises(
        LocalRhythmFamilyPlanMappingError, match=LOCAL_RHYTHM_FAMILY_PLAN_MAPPING_INVALID
    ):
        map_actual_family_to_planning_indices_v1(
            state=_state(), compilation=_compilation(("S-A", "OTHER", "S-B", "TAIL")), family=family
        )


def test_radius_three_edge_family_domain_has_at_most_49_combinations() -> None:
    generated = enumerate_local_rhythm_states_v1(
        source=_state(), planning_indices=(0, 1), planning_grid_seconds=60
    )

    assert generated.statistics.structural_local_combinations == 49
    assert len(generated.states) <= 49


def test_radius_three_middle_family_domain_is_one_side_at_a_time() -> None:
    generated = enumerate_local_rhythm_states_v1(
        source=_state(), planning_indices=(1, 2), planning_grid_seconds=60
    )

    assert generated.statistics.structural_local_combinations == 97
    assert len(generated.states) <= 97


def test_generated_states_preserve_total_trips_and_fixed_endpoints() -> None:
    source = _state()
    generated = enumerate_local_rhythm_states_v1(
        source=source, planning_indices=(1, 2), planning_grid_seconds=60
    )

    assert generated.states
    assert {item.total_trips for item in generated.states} == {source.total_trips}
    assert {item.fixed_first_departure for item in generated.states} == {
        source.fixed_first_departure
    }
    assert {item.fixed_last_departure for item in generated.states} == {source.fixed_last_departure}


def test_generated_state_boundaries_remain_on_whole_minute_grid() -> None:
    generated = enumerate_local_rhythm_states_v1(
        source=_state(), planning_indices=(1, 2), planning_grid_seconds=120
    )

    assert generated.states
    assert all(boundary % 60 == 0 for state in generated.states for boundary in state.boundaries)
    assert all(
        (boundary - 5 * 3600) % 120 == 0
        for state in generated.states
        for boundary in state.boundaries
    )


def test_equal_or_worse_micro_boundary_candidate_is_rejected() -> None:
    source = SimpleNamespace(
        compile_variant=SimpleNamespace(
            compilation=SimpleNamespace(service_regimes=(_actual(19), _actual(20)))
        )
    )
    equal = SimpleNamespace(
        compile_variant=SimpleNamespace(
            compilation=SimpleNamespace(service_regimes=(_actual(19), _actual(20)))
        )
    )
    better = SimpleNamespace(
        compile_variant=SimpleNamespace(
            compilation=SimpleNamespace(service_regimes=(_actual(19), _actual(19)))
        )
    )

    assert retain_strict_directional_canonicalizations_v1(source, (equal, better)) == (better,)


def test_equal_or_worse_pair_rhythm_cannot_recurse() -> None:
    source = SimpleNamespace(
        metrics=SimpleNamespace(
            total_directional_sustained_headway_level_count=4,
            actual_service_regime_count=8,
            total_directional_effective_palette_count=4,
            total_single_gap_regime_count=0,
        )
    )
    equal = SimpleNamespace(metrics=source.metrics)
    worse = SimpleNamespace(
        metrics=SimpleNamespace(
            total_directional_sustained_headway_level_count=5,
            actual_service_regime_count=6,
            total_directional_effective_palette_count=3,
            total_single_gap_regime_count=0,
        )
    )

    assert pair_rhythm_tuple_v1(source) == (4, 8, 4, 0)
    assert strict_pair_rhythm_progress_v1(source, equal) is False
    assert strict_pair_rhythm_progress_v1(source, worse) is False


def test_rhythm_progress_is_independent_of_fleet_tuple() -> None:
    source = SimpleNamespace(
        metrics=SimpleNamespace(
            total_directional_sustained_headway_level_count=4,
            actual_service_regime_count=8,
            total_directional_effective_palette_count=4,
            total_single_gap_regime_count=0,
            fleet_required=10,
        )
    )
    better_rhythm_worse_fleet = SimpleNamespace(
        metrics=SimpleNamespace(
            total_directional_sustained_headway_level_count=3,
            actual_service_regime_count=20,
            total_directional_effective_palette_count=20,
            total_single_gap_regime_count=20,
            fleet_required=12,
        )
    )

    assert strict_pair_rhythm_progress_v1(source, better_rhythm_worse_fleet) is True


def _pair_metrics(levels: int):
    return SimpleNamespace(
        total_directional_sustained_headway_level_count=levels,
        actual_service_regime_count=6,
        total_directional_effective_palette_count=levels,
        total_single_gap_regime_count=0,
        pareto_vector=(levels,) * 10,
    )


def test_complete_cross_product_includes_both_refined_directions(monkeypatch) -> None:
    import bus_schedule_engine.local_rhythm_refinement as refinement

    source = SimpleNamespace(pair_fingerprint="source", metrics=_pair_metrics(4))
    outbound = (SimpleNamespace(name="ob-original"), SimpleNamespace(name="ob-refined"))
    inbound = (SimpleNamespace(name="ib-original"), SimpleNamespace(name="ib-refined"))
    calls: list[tuple[str, str]] = []

    def evaluate(ob, ib, *, context):
        calls.append((ob.name, ib.name))
        levels = 2 if "refined" in ob.name and "refined" in ib.name else 3
        return SimpleNamespace(
            pair_fingerprint=f"{ob.name}/{ib.name}", metrics=_pair_metrics(levels)
        ), ()

    monkeypatch.setattr(refinement, "evaluate_operating_pair_v1", evaluate)
    monkeypatch.setattr(
        refinement,
        "update_operating_pair_pareto_v1",
        lambda frontier, candidate, *, limit=None: (*frontier, candidate),
    )

    result = evaluate_directional_cross_product_v1(
        source_pair=source,
        outbound_options=outbound,
        inbound_options=inbound,
        context=SimpleNamespace(),
        frontier=(source,),
        pair_frontier_limit=512,
        already_generated=set(),
    )

    assert calls == [
        ("ob-original", "ib-original"),
        ("ob-original", "ib-refined"),
        ("ob-refined", "ib-original"),
        ("ob-refined", "ib-refined"),
    ]
    assert "ob-refined/ib-refined" in result.generated_pair_fingerprints
    assert result.pair_cross_products_evaluated == 4


def test_every_cross_product_pair_uses_existing_pareto_updater(monkeypatch) -> None:
    import bus_schedule_engine.local_rhythm_refinement as refinement

    source = SimpleNamespace(pair_fingerprint="source", metrics=_pair_metrics(4))
    updater_calls: list[str] = []

    monkeypatch.setattr(
        refinement,
        "evaluate_operating_pair_v1",
        lambda ob, ib, *, context: (
            SimpleNamespace(pair_fingerprint=f"{ob}/{ib}", metrics=_pair_metrics(3)),
            (),
        ),
    )

    def update(frontier, candidate, *, limit=None):
        updater_calls.append(candidate.pair_fingerprint)
        return (*frontier, candidate)

    monkeypatch.setattr(refinement, "update_operating_pair_pareto_v1", update)

    result = evaluate_directional_cross_product_v1(
        source_pair=source,
        outbound_options=("O",),
        inbound_options=("I",),
        context=SimpleNamespace(),
        frontier=(source,),
        pair_frontier_limit=512,
        already_generated=set(),
    )

    assert updater_calls == ["O/I"]
    assert result.pareto_admitted_generated_pairs == 1


def test_duplicate_pair_descendants_are_suppressed_before_admission(monkeypatch) -> None:
    import bus_schedule_engine.local_rhythm_refinement as refinement

    source = SimpleNamespace(pair_fingerprint="source", metrics=_pair_metrics(4))
    monkeypatch.setattr(
        refinement,
        "evaluate_operating_pair_v1",
        lambda ob, ib, *, context: (
            SimpleNamespace(pair_fingerprint="duplicate", metrics=_pair_metrics(3)),
            (),
        ),
    )
    result = evaluate_directional_cross_product_v1(
        source_pair=source,
        outbound_options=("O1", "O2"),
        inbound_options=("I",),
        context=SimpleNamespace(),
        frontier=(source,),
        pair_frontier_limit=512,
        already_generated=set(),
    )

    assert result.generated_pair_fingerprints == ("duplicate",)
    assert result.duplicate_pair_rejects == 1


def test_compiler_cap_binding_is_an_explicit_blocker(monkeypatch) -> None:
    import bus_schedule_engine.local_rhythm_refinement as refinement

    monkeypatch.setattr(
        refinement,
        "compile_service_plan_frontier_v1",
        lambda *args, **kwargs: SimpleNamespace(variants=(), variants_limit_pruned=1, failure=None),
    )
    source_directional = SimpleNamespace(
        state=_state(), compile_variant=SimpleNamespace(compilation=SimpleNamespace())
    )

    result = compile_local_states_v1(
        source_directional=source_directional,
        states=(_state(),),
        context=SimpleNamespace(endpoint_authority={"outbound": SimpleNamespace()}),
    )

    assert result.compiler_cap_binding_count == 1
    assert result.classification == LOCAL_RHYTHM_COMPILE_FRONTIER_CAP_BINDING


def test_integrated_entry_calls_global_coordinator_once_and_processes_source_once(
    monkeypatch,
) -> None:
    import bus_schedule_engine.local_rhythm_refinement as refinement

    source = SimpleNamespace(
        pair_fingerprint="source",
        metrics=_pair_metrics(4),
        outbound=SimpleNamespace(),
        inbound=SimpleNamespace(),
    )
    coordinator_calls = 0
    processor_calls: list[str] = []

    def search(**kwargs):
        nonlocal coordinator_calls
        coordinator_calls += 1
        return SimpleNamespace(
            pareto_frontier=(source,), search_budget=SimpleNamespace(max_pair_frontier=512)
        )

    selection = SimpleNamespace(
        phase_robust_materiality_fingerprints=("source",),
        selected_pair_fingerprint="source",
        common_anchor_fingerprint="anchor",
        continuous_preservation_bound=1.0,
        classification="SELECTED",
    )
    monkeypatch.setattr(refinement, "search_route_service_plans_v1", search)
    monkeypatch.setattr(refinement, "select_operational_timetable_v3", lambda **kwargs: selection)

    def process(**kwargs):
        processor_calls.append(kwargs["source_pair"].pair_fingerprint)
        return refinement.SourcePairRefinementV1.empty(kwargs["frontier"])

    monkeypatch.setattr(refinement, "refine_source_pair_v1", process)

    result = search_route_service_plans_with_local_rhythm_refinement_v1(
        context=SimpleNamespace(route_id="10"),
        seeds=(),
        refinement_policy=LocalRhythmRefinementPolicyV1(),
    )

    assert coordinator_calls == 1
    assert processor_calls == ["source"]
    assert result.processed_source_pair_fingerprints == ("source",)
    assert result.statistics.refinement_iterations == 1


def test_same_rhythm_result_terminates_without_cycle(monkeypatch) -> None:
    import bus_schedule_engine.local_rhythm_refinement as refinement

    source = SimpleNamespace(
        pair_fingerprint="source",
        metrics=_pair_metrics(4),
        outbound=SimpleNamespace(),
        inbound=SimpleNamespace(),
    )
    selection = SimpleNamespace(
        phase_robust_materiality_fingerprints=("source",),
        selected_pair_fingerprint="source",
        common_anchor_fingerprint="anchor",
        continuous_preservation_bound=1.0,
        classification="SELECTED",
    )
    monkeypatch.setattr(
        refinement,
        "search_route_service_plans_v1",
        lambda **kwargs: SimpleNamespace(
            pareto_frontier=(source,), search_budget=SimpleNamespace(max_pair_frontier=512)
        ),
    )
    monkeypatch.setattr(refinement, "select_operational_timetable_v3", lambda **kwargs: selection)
    monkeypatch.setattr(
        refinement,
        "refine_source_pair_v1",
        lambda **kwargs: refinement.SourcePairRefinementV1.empty(kwargs["frontier"]),
    )

    result = search_route_service_plans_with_local_rhythm_refinement_v1(
        context=SimpleNamespace(route_id="10"), seeds=()
    )

    assert result.statistics.processed_source_count == 1
    assert result.statistics.refinement_iterations == 1


def test_v3_source_remains_exact_start_bytes() -> None:
    import hashlib
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    path = repo_root / "src/bus_schedule_engine/contracts_v1/operational_selection_policy_v3.py"

    assert (
        hashlib.sha256(path.read_bytes()).hexdigest()
        == "b36390de2737cf344a26621f7de03f399eac34d730d895ef162f4913bf4eb4d3"
    )
