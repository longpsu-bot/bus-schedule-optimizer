"""Hard gates, family realization, exact pair decisions, and source-once shadow worklists."""

from dataclasses import FrozenInstanceError, fields, make_dataclass, replace
from fractions import Fraction
from types import SimpleNamespace

import pytest

import bus_schedule_engine.kbest_shadow_refinement as shadow
import bus_schedule_engine.local_rhythm_refinement as local
import bus_schedule_engine.service_plan_coordinator as coordinator
from bus_schedule_engine.contracts_v1 import operational_selection_policy_v3 as selection_v3
from bus_schedule_engine.contracts_v1.clean_boundary_compiler import (
    CleanBoundaryCompilationStatusV1,
    OperationalEndpointAuthorityV1,
    _PhaseCandidate,
)
from bus_schedule_engine.contracts_v1.clean_compile_frontier import (
    CleanCompileVariantV1,
    _compilation_from_path,
    _FrontierPath,
    _regimes_from_state,
    clean_compilation_fingerprint_v1,
)
from bus_schedule_engine.contracts_v1.closed_loop_service_protection import (
    ClosedLoopProtectedServiceWindowV1,
    build_closed_loop_service_protection_authority_v1,
    validate_closed_loop_service_protection_authority_v1,
)
from bus_schedule_engine.contracts_v1.kbest_dag_frontier import (
    KBestDagCandidateV1,
    KBestDagFrontierV1,
    KBestDagGraphStatisticsV1,
    KBestDagTelemetryV1,
    compile_service_plan_family_kbest_v1,
    service_plan_matches_endpoint_contract_v1,
)
from bus_schedule_engine.contracts_v1.service_plan_state import (
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
    service_plan_fingerprint_v1,
)
from bus_schedule_engine.service_plan_coordinator import (
    DemandBucketEvidenceV1,
    DirectionalCompilationCandidateV1,
    evaluate_actual_service_v1,
)


def _raw(a=9, b=12, c=100):
    """Eight real trips, with adjacent gaps owned by the left-hand rhythm."""
    return _path_raw((a, b, c))


def _path_raw(headways, gaps=None, counts=None, tail_padding=1):
    counts = counts or (*((3,) * (len(headways) - 1)), 2)
    gaps = gaps or headways[:-1]
    starts = [0]
    for h, n, gap in zip(headways, counts, gaps, strict=False):
        starts.append(starts[-1] + (n - 1) * h + gap)
    end = starts[-1] + headways[-1]
    bounds = (*starts, end + tail_padding)
    state = ServicePlanStateV1(
        route_id="eligibility-test",
        direction="outbound",
        fixed_first_departure=0,
        fixed_last_departure=end * 60,
        service_regimes=tuple(
            ServiceRegimeDecisionV1(left * 60, right * 60, count)
            for left, right, count in zip(bounds, bounds[1:], counts, strict=False)
        ),
        seed_id="shadow-test",
    )
    authority = OperationalEndpointAuthorityV1(
        state.route_id, state.direction, 0, (end + tail_padding) * 60, 0, end * 60, "test"
    )
    phases = []
    for start, stop, h, n in zip(bounds, bounds[1:], headways, counts, strict=False):
        deps = tuple(start + i * h for i in range(n))
        phases.append(
            _PhaseCandidate(
                start,
                h,
                deps[-1],
                deps,
                Fraction(abs(h * n - (stop - start)), stop - start),
                abs((stop - 1 - deps[-1]) - (deps[0] - start)),
            )
        )
    path = _FrontierPath(
        tuple(phases),
        sum((p.quantization_error for p in phases), Fraction()),
        1 + sum(a != b for a, b in zip(headways, headways[1:], strict=False)),
        sum(p.phase_imbalance_minutes for p in phases),
    )
    fp = service_plan_fingerprint_v1(state)
    compilation = _compilation_from_path(
        state=state,
        state_fingerprint=fp,
        authority=authority,
        regimes=_regimes_from_state(state),
        path=path,
        rank=1,
    )
    return KBestDagCandidateV1(
        state,
        fp,
        compilation,
        clean_compilation_fingerprint_v1(compilation),
        path.objective,
        path.quantization.numerator,
        (path.quantization.numerator, *path.objective[1:], path.headways, path.departures),
        (0,) * len(headways),
        path.headways,
        path.departures,
    )


def _context(raw, protection=None):
    authority = raw.compilation.endpoint_authority
    return SimpleNamespace(
        endpoint_authority={"outbound": authority},
        service_protection_authority=protection,
        demand_buckets={
            "outbound": (
                DemandBucketEvidenceV1("outbound", 0, authority.analysis_window_end, 10.0),
            )
        },
        scenario_b_departures={"outbound": raw.compilation.exact_departures},
        demand_response_regimes=None,
    )


def _directional(raw, context):
    variant = CleanCompileVariantV1(
        raw.compilation_fingerprint,
        1,
        float(raw.compiler_objective[0]),
        raw.compiler_objective[1],
        raw.compiler_objective[2],
        raw.compilation,
    )
    metrics, feedback = evaluate_actual_service_v1(
        variant,
        demand_buckets=context.demand_buckets["outbound"],
        scenario_b_departures=context.scenario_b_departures["outbound"],
    )
    return DirectionalCompilationCandidateV1(
        raw.state, raw.state_fingerprint, variant, metrics, feedback, ("source",)
    )


def _evaluate(raws, *, source_raw=None, context=None):
    source_raw = source_raw or _raw(10, 11, 100)
    context = context or _context(source_raw)
    return shadow.evaluate_kbest_dag_hard_eligibility_v1(
        source_directional=_directional(source_raw, context), candidates=raws, context=context
    )


def _forbidden(*args, **kwargs):
    raise AssertionError("downstream authority reached by an ineligible candidate")


@pytest.mark.parametrize("broken", ["structure", "status", "endpoint", "trip_total"])
def test_eligibility_structural_endpoint_and_trip_fail_closed_before_protection(
    monkeypatch, broken
):
    raw = _raw()
    source = _raw(10, 11, 100)
    if broken == "structure":
        raw = replace(raw, compilation=replace(raw.compilation, exact_departures=(0,)))
    elif broken == "status":
        raw = replace(
            raw,
            compilation=replace(
                raw.compilation, status=CleanBoundaryCompilationStatusV1.CLEAN_BOUNDARY_UNCOMPILABLE
            ),
        )
    elif broken == "endpoint":
        # Internally valid compilation, inconsistent with the external endpoint authority.
        raw = _raw(9, 12, 101)
    else:
        # Candidate remains structurally valid; the source's authoritative total differs.
        source = replace(
            source,
            state=replace(
                source.state,
                service_regimes=(
                    replace(source.state.service_regimes[0], trip_count=4),
                    *source.state.service_regimes[1:],
                ),
            ),
        )
    monkeypatch.setattr(shadow, "validate_closed_loop_service_protection_v1", _forbidden)
    monkeypatch.setattr(shadow, "evaluate_actual_service_v1", _forbidden)
    monkeypatch.setattr(shadow, "retain_strict_directional_canonicalizations_v1", _forbidden)
    result = _evaluate((raw,), source_raw=source)
    assert result.structural_rejects == 1
    assert result.protection_rejects == result.tail_rejects == result.strict_progress_rejects == 0
    assert result.eligible_fingerprints == result.candidates == ()


def _protection():
    return build_closed_loop_service_protection_authority_v1(
        source_authority_profile="test",
        source_authority_fingerprint="a" * 64,
        windows=(ClosedLoopProtectedServiceWindowV1("early", "outbound", 0, 18 * 60, 0, 10, 3),),
    )


def test_protection_failure_never_evaluates_metrics_or_progress(monkeypatch):
    raw = _raw(10, 11, 100)
    monkeypatch.setattr(shadow, "evaluate_actual_service_v1", _forbidden)
    monkeypatch.setattr(shadow, "retain_strict_directional_canonicalizations_v1", _forbidden)
    result = _evaluate((raw,), context=_context(raw, _protection()))
    assert result.protection_rejects == 1
    assert result.structural_rejects == result.tail_rejects == 0
    assert result.eligible_fingerprints == ()


def test_tail_failure_never_reaches_progress(monkeypatch):
    monkeypatch.setattr(shadow, "retain_strict_directional_canonicalizations_v1", _forbidden)
    result = _evaluate((_raw(25, 26, 10),))
    assert result.tail_rejects == 1
    assert result.structural_rejects == result.protection_rejects == 0
    assert result.eligible_fingerprints == ()


def test_eligibility_retains_real_metrics_and_separates_strict_progress():
    raw, source = _raw(), _raw(10, 11, 100)
    context = _context(source)
    result = _evaluate((source, raw), context=context)
    assert result.eligible_fingerprints == (
        source.compilation_fingerprint,
        raw.compilation_fingerprint,
    )
    assert result.strict_progress_rejects == 1
    assert result.structural_rejects == result.protection_rejects == result.tail_rejects == 0
    assert len(result.candidates) == 1
    retained = result.candidates[0]
    independently_evaluated = _directional(raw, context)
    assert retained.metrics == independently_evaluated.metrics
    assert retained.feedback == independently_evaluated.feedback
    assert retained.compile_variant.headway_quantization == float(Fraction(99, 101))
    assert retained.compile_variant.actual_service_regime_count == 3
    assert retained.compile_variant.phase_edge_quality_minutes == 19
    assert retained.metrics.tail_ordering.eligible


def test_eligibility_aggregate_reject_counts_are_separate():
    good = _raw()
    bad_structure = replace(good, compilation=replace(good.compilation, exact_departures=()))
    # The tail failure preserves the same first three protected trips.
    bad_tail = _raw(9, 39, 19)
    result = _evaluate(
        (bad_structure, _raw(10, 11, 100), bad_tail, good), context=_context(good, _protection())
    )
    assert result.structural_rejects == 1
    assert result.protection_rejects == 1
    assert result.tail_rejects == 1
    assert result.eligible_fingerprints == (good.compilation_fingerprint,)


def _family(raws, source, context, index=0):
    raws = tuple(raws)
    return shadow.KBestDagFamilyShadowV1(
        family_index=index,
        frontier=KBestDagFrontierV1(
            raws,
            tuple(raw.compilation_fingerprint for raw in raws),
            len(raws),
            True,
            KBestDagGraphStatisticsV1(0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            KBestDagTelemetryV1(0, 0, 0, 0, 0),
        ),
        eligibility=shadow.evaluate_kbest_dag_hard_eligibility_v1(
            source_directional=source,
            candidates=raws,
            context=context,
        ),
    )


def _large_pool(count):
    source_raw = _raw(1000, 1001, 23997)
    context = _context(source_raw)
    source = _directional(source_raw, context)
    # Sorted quality gets worse down this vector; the distant extreme is last.
    raws = (source_raw, *(_raw(a, 1000, 27000 - 3 * a) for a in range(399, 400 - count, -1)))
    assert len({raw.compilation_fingerprint for raw in raws}) == count
    return source, context, raws


@pytest.mark.parametrize("count", [31, 32, 33])
def test_diversity_boundary_retains_every_eligible_identity_when_capacity_allows(count):
    source, context, raws = _large_pool(count)
    family = _family(raws, source, context)
    result = shadow.retain_kbest_dag_directional_frontier_v1(
        source_directional=source,
        family_results=(family,),
        context=context,
        limit=32,
    )
    assert result.raw_candidates_before_cross_family_dedupe == count
    assert result.eligible_candidates_before_cross_family_dedupe == count
    assert result.aggregate_eligible_count_after_dedupe == count
    assert result.retained_count == min(count, 32)
    assert result.pre_diversity_truncation_count == 0
    if count <= 32:
        assert set(result.retained_fingerprints) == {r.compilation_fingerprint for r in raws}
    assert result.retained_fingerprints[0] == source.compile_variant.compilation_fingerprint


def test_aggregate_300_unique_inspects_high_tail_with_real_selector():
    source, context, raws = _large_pool(300)
    families = (_family(raws[:150], source, context), _family(raws[150:], source, context, 1))
    assert sum(len(f.eligibility.eligible_candidates) for f in families) == 300
    assert sum(f.eligibility.strict_progress_rejects for f in families) == 1
    assert sum(len(f.eligibility.candidates) for f in families) == 299
    result = shadow.retain_kbest_dag_directional_frontier_v1(
        source_directional=source,
        family_results=families,
        context=context,
        limit=32,
    )
    assert result.family_count == 2
    assert result.raw_candidates_before_cross_family_dedupe == 300
    assert result.eligible_candidates_before_cross_family_dedupe == 300
    assert result.aggregate_eligible_count_after_dedupe == 300
    assert result.source_added
    assert result.pre_diversity_truncation_count == 0
    assert result.retained_count == 32
    # The source is the exact quality anchor; index 299 is the unique farthest
    # exact-departure vector, picked second by the real headway-shape max-min pass.
    assert raws[-1].departure_vector == (0, 101, 202, 303, 1303, 2303, 3303, 30000)
    assert result.retained_fingerprints[:2] == (
        raws[0].compilation_fingerprint,
        raws[-1].compilation_fingerprint,
    )
    assert result.selector_seconds >= 0.0
    repeat = shadow.retain_kbest_dag_directional_frontier_v1(
        source_directional=source,
        family_results=tuple(reversed(families)),
        context=context,
        limit=32,
    )
    assert repeat.retained_fingerprints == result.retained_fingerprints
    print(
        f"300 aggregate: seconds={result.selector_seconds:.6f}; farthest={raws[-1].compilation_fingerprint}"
    )


def test_diversity_headway_shapes_then_exact_departure_max_min():
    source_raw = _path_raw((10, 11, 10, 11, 100))
    context = _context(source_raw)
    source = _directional(source_raw, context)
    shape = (7, 12, 7, 12, 112)
    base = _path_raw(shape)
    left = _path_raw(shape, gaps=(12, 7, 7, 12))
    right = _path_raw(shape, gaps=(7, 7, 12, 12))
    family = _family((right, base, left), source, context)
    result = shadow.retain_kbest_dag_directional_frontier_v1(
        source_directional=source,
        family_results=(family,),
        context=context,
        limit=3,
    )
    # Source is quality anchor. Base is best representative of the new shape.
    # With both shapes represented, right (distance 15 to base) beats left at
    # equal distance via its smaller exact quantization objective.
    assert result.retained_fingerprints == (
        source_raw.compilation_fingerprint,
        base.compilation_fingerprint,
        right.compilation_fingerprint,
    )


def test_ineligible_best_quality_candidate_cannot_occupy_a_slot(monkeypatch):
    source, context, raws = _large_pool(33)
    invalid = replace(
        raws[-1],
        compilation=replace(raws[-1].compilation, exact_departures=()),
        compiler_objective=(Fraction(-1), 0, 0),
    )
    family = _family((invalid, *raws), source, context)
    assert family.eligibility.structural_rejects == 1
    assert len(family.eligibility.eligible_candidates) == 33
    result = shadow.retain_kbest_dag_directional_frontier_v1(
        source_directional=source,
        family_results=(family,),
        context=context,
        limit=32,
    )
    assert result.raw_candidates_before_cross_family_dedupe == 34
    assert result.eligible_candidates_before_cross_family_dedupe == 33
    assert all(c.compile_variant.compilation.exact_departures for c in result.candidates)
    assert result.retained_fingerprints[0] == source.compile_variant.compilation_fingerprint


def test_aggregate_revalidates_source_before_diversity(monkeypatch):
    source_raw = _raw(10, 11, 100)
    context = _context(source_raw, _protection())
    source = _directional(source_raw, context)
    family = _family((_raw(),), source, context)
    result = shadow.retain_kbest_dag_directional_frontier_v1(
        source_directional=source,
        family_results=(family,),
        context=context,
        limit=32,
    )
    assert not result.source_added
    assert result.source_rejection == "protection"
    assert result.retained_fingerprints == (_raw().compilation_fingerprint,)


def test_aggregate_dedupe_uses_exact_objective_not_family_integer_scale():
    source, context, raws = _large_pool(3)
    worse = replace(raws[1], compiler_objective=(Fraction(2), 3, 400), exact_scaled_quantization=1)
    better = replace(raws[1], exact_scaled_quantization=10**9)
    families = (_family((worse, raws[2]), source, context), _family((better,), source, context, 1))
    result = shadow.retain_kbest_dag_directional_frontier_v1(
        source_directional=source,
        family_results=families,
        context=context,
        limit=32,
    )
    assert result.raw_candidates_before_cross_family_dedupe == 3
    assert result.aggregate_eligible_count_after_dedupe == 3
    retained = next(
        c
        for c in result.candidates
        if c.compile_variant.compilation_fingerprint == better.compilation_fingerprint
    )
    assert retained.compile_variant.headway_quantization == float(better.compiler_objective[0])
    repeat = shadow.retain_kbest_dag_directional_frontier_v1(
        source_directional=source,
        family_results=tuple(reversed(families)),
        context=context,
        limit=32,
    )
    assert repeat.candidates == result.candidates


def test_aggregate_equal_semantic_duplicate_provenance_is_family_order_independent():
    source, context, raws = _large_pool(2)
    source_raw, target = raws
    rank_two = replace(
        target,
        compilation=replace(
            target.compilation,
            candidate_id=target.compilation.candidate_id.replace("C001", "C002"),
        ),
    )
    rank_one_family = _family((target,), source, context)
    rank_two_family = _family((source_raw, rank_two), source, context, 1)
    assert rank_one_family.eligibility.candidates[0].compile_variant.frontier_rank == 1
    assert rank_two_family.eligibility.candidates[0].compile_variant.frontier_rank == 2

    forward = shadow.retain_kbest_dag_directional_frontier_v1(
        source_directional=source,
        family_results=(rank_one_family, rank_two_family),
        context=context,
        limit=32,
    )
    reverse = shadow.retain_kbest_dag_directional_frontier_v1(
        source_directional=source,
        family_results=(rank_two_family, rank_one_family),
        context=context,
        limit=32,
    )

    assert forward.retained_fingerprints == reverse.retained_fingerprints
    assert forward.candidates == reverse.candidates
    retained = next(
        candidate
        for candidate in forward.candidates
        if candidate.compile_variant.compilation_fingerprint == target.compilation_fingerprint
    )
    assert retained.compile_variant.frontier_rank == 1
    assert retained.compile_variant.compilation.candidate_id.endswith("C001")


def test_family_realization_covers_every_actual_family_and_maps_merged_planning_slices(monkeypatch):
    raw = _path_raw((10, 10, 11, 30, 31, 100))
    context = _context(raw)
    context.planning_grid_seconds = 60
    source = _directional(raw, context)
    calls = []

    def compile_family(**kwargs):
        calls.append(kwargs)
        return compile_service_plan_family_kbest_v1(**kwargs)

    monkeypatch.setattr(
        shadow, "compile_service_plan_family_kbest_v1", compile_family, raising=False
    )
    result = shadow.realize_kbest_dag_families_v1(source_directional=source, context=context)

    assert len(result) == len(calls) == 2
    assert tuple(item.family.headways for item in result) == ((10, 11), (30, 31))
    assert tuple(item.planning_indices for item in result) == ((0, 1, 2), (3, 4))
    assert tuple(item.dag_call_count for item in result) == (1, 1)
    for item, call in zip(result, calls, strict=True):
        assert call["raw_limit"] == 256
        assert len(call["states"]) > 1
        assert (
            tuple(service_plan_fingerprint_v1(state) for state in call["states"])
            == item.valid_state_fingerprints
        )
        assert item.valid_state_fingerprints == tuple(sorted(item.valid_state_fingerprints))
        assert item.shadow.frontier.graph_statistics.state_count == len(call["states"])
        assert len(item.graph_hash) == len(item.raw_hash) == len(item.eligible_hash) == 64

    repeated = shadow.realize_kbest_dag_families_v1(source_directional=source, context=context)
    assert [
        (item.state_manifest_hash, item.graph_hash, item.raw_hash, item.eligible_hash)
        for item in result
    ] == [
        (item.state_manifest_hash, item.graph_hash, item.raw_hash, item.eligible_hash)
        for item in repeated
    ]


def test_family_radius_three_varies_only_one_external_side_per_state(monkeypatch):
    raw = _path_raw((20, 10, 11, 100), counts=(6, 3, 3, 2))
    context = _context(raw)
    context.planning_grid_seconds = 60
    source = _directional(raw, context)
    calls = []

    def compile_family(**kwargs):
        calls.append(kwargs)
        return compile_service_plan_family_kbest_v1(**kwargs)

    monkeypatch.setattr(
        shadow, "compile_service_plan_family_kbest_v1", compile_family, raising=False
    )
    result = shadow.realize_kbest_dag_families_v1(source_directional=source, context=context)

    assert len(result) == len(calls) == 1
    assert result[0].planning_indices == (1, 2)
    assert result[0].generation.statistics.structural_local_combinations == 97
    states = calls[0]["states"]
    # Source boundaries 120/183 minutes and merged trip counts 6/6/2.
    left_steps = {(state.service_regimes[0].end // 60) - 120 for state in states}
    right_steps = {(state.service_regimes[1].end // 60) - 183 for state in states}
    assert left_steps == right_steps == {-3, -2, -1, 0, 1, 2, 3}
    assert {state.service_regimes[1].trip_count - 6 for state in states} >= {-3, 3}
    for state in states:
        first, middle, last = state.service_regimes
        assert (first.end == 120 * 60 and first.trip_count == 6) or (
            middle.end == 183 * 60 and last.trip_count == 2
        )


@pytest.mark.parametrize("keep_valid", [True, False])
def test_family_endpoint_invalid_generated_states_removed_before_dag(monkeypatch, keep_valid):
    raw = _raw(10, 11, 100)
    context = _context(raw)
    context.planning_grid_seconds = 60
    source = _directional(raw, context)
    generated = local.enumerate_local_rhythm_states_v1(
        source=source.state, planning_indices=(0, 1), planning_grid_seconds=60
    )
    valid = generated.states[0]
    invalid = replace(
        valid,
        service_regimes=(
            replace(valid.service_regimes[0], end=valid.fixed_last_departure + 60),
            replace(
                valid.service_regimes[1],
                start=valid.fixed_last_departure + 60,
                end=valid.fixed_last_departure + 120,
            ),
        ),
    )
    assert not service_plan_matches_endpoint_contract_v1(
        invalid, context.endpoint_authority["outbound"]
    )
    states = (invalid, valid) if keep_valid else (invalid,)
    monkeypatch.setattr(
        shadow,
        "enumerate_local_rhythm_states_v1",
        lambda **kwargs: replace(generated, states=states),
        raising=False,
    )
    calls = []

    def compile_family(**kwargs):
        calls.append(kwargs)
        assert kwargs["states"] == (valid,)
        return compile_service_plan_family_kbest_v1(**kwargs)

    monkeypatch.setattr(
        shadow, "compile_service_plan_family_kbest_v1", compile_family, raising=False
    )
    result = shadow.realize_kbest_dag_families_v1(source_directional=source, context=context)

    assert len(result) == 1  # Even an entirely rejected family stays in the manifest.
    record = result[0]
    assert record.endpoint_rejected_state_fingerprints == (service_plan_fingerprint_v1(invalid),)
    assert record.dag_call_count == len(calls) == int(keep_valid)
    assert (record.shadow is not None) == keep_valid


def test_family_mapping_rejection_is_recorded_without_dag_call(monkeypatch):
    raw = _raw(10, 11, 100)
    context = _context(raw)
    context.planning_grid_seconds = 60
    source = _directional(raw, context)
    broken = replace(source.compile_variant.compilation, demand_regime_slices=())
    source = replace(source, compile_variant=replace(source.compile_variant, compilation=broken))
    monkeypatch.setattr(shadow, "compile_service_plan_family_kbest_v1", _forbidden, raising=False)
    result = shadow.realize_kbest_dag_families_v1(source_directional=source, context=context)
    assert len(result) == 1
    assert result[0].classification == local.LOCAL_RHYTHM_FAMILY_PLAN_MAPPING_INVALID
    assert result[0].dag_call_count == 0
    assert result[0].planning_indices == ()


def test_family_real_radius_generated_endpoint_invalid_states_never_enter_dag(monkeypatch):
    raw = _path_raw((10, 11, 1), tail_padding=5)
    context = _context(raw)
    context.planning_grid_seconds = 60
    calls = []

    def compile_family(**kwargs):
        calls.append(kwargs)
        # Radius +2 and +3 would put fixed last 64 before the last regime starts.
        assert len(kwargs["states"]) == 20
        assert all(state.service_regimes[-1].start <= 64 * 60 for state in kwargs["states"])
        return compile_service_plan_family_kbest_v1(**kwargs)

    monkeypatch.setattr(shadow, "compile_service_plan_family_kbest_v1", compile_family)
    records = shadow.realize_kbest_dag_families_v1(
        source_directional=_directional(raw, context), context=context
    )
    assert len(records) == len(calls) == 1
    record = records[0]
    assert len(record.generated_state_fingerprints) == 28
    assert len(record.endpoint_rejected_state_fingerprints) == 8
    assert len(record.valid_state_fingerprints) == 20


def _pair_model(fingerprint, rhythm=(4, 8, 4, 0), mismatch=10):
    metrics = coordinator.OperatingPairMetricsV1(
        observed_demand_mismatch=mismatch,
        demand_weighted_expected_passenger_wait_minutes=10,
        actual_service_regime_count=rhythm[1],
        max_frequency_jump=1,
        total_frequency_variation=1,
        moved_trips_vs_b=0,
        fleet_required=2,
        total_excess_terminal_wait=0,
        max_excess_terminal_wait=0,
        total_directional_sustained_headway_level_count=rhythm[0],
        total_directional_effective_palette_count=rhythm[2],
        total_single_gap_regime_count=rhythm[3],
    )
    return SimpleNamespace(pair_fingerprint=fingerprint, metrics=metrics)


def _option(fingerprint):
    return SimpleNamespace(compile_variant=SimpleNamespace(compilation_fingerprint=fingerprint))


def test_pair_cross_product_is_complete_sorted_and_bounded_by_retained_32(monkeypatch):
    source = _pair_model("source")
    outbound = tuple(_option(f"O{i:02}") for i in reversed(range(32)))
    inbound = tuple(_option(f"I{i:02}") for i in reversed(range(32)))
    calls = []

    def evaluate(ob, ib, *, context):
        key = (
            ob.compile_variant.compilation_fingerprint,
            ib.compile_variant.compilation_fingerprint,
        )
        calls.append(key)
        return _pair_model("/".join(key), (3, 7, 3, 0)), ()

    monkeypatch.setattr(shadow, "evaluate_operating_pair_v1", evaluate, raising=False)
    result = shadow.evaluate_kbest_dag_pairs_v1(
        source_pair=source,
        outbound_options=outbound,
        inbound_options=inbound,
        context=SimpleNamespace(),
        frontier=(source,),
        pair_frontier_limit=5,
        already_generated=set(),
    )
    assert len(calls) == len(result.decisions) == 32 * 32
    assert calls == [(f"O{i:02}", f"I{j:02}") for i in range(32) for j in range(32)]
    assert tuple(pair.pair_fingerprint for pair in result.frontier) == (
        "O00/I00",
        "O00/I01",
        "O00/I02",
        "O00/I03",
        "O00/I04",
    )
    assert len(result.admitted_descendants) == 5


def test_pair_fleet_duplicate_equal_worse_and_strict_decisions_precede_pareto(monkeypatch):
    source = _pair_model("source")
    outcomes = {
        "0-fleet": None,
        "1-duplicate": _pair_model("seen", (3, 7, 3, 0)),
        "2-equal": _pair_model("equal"),
        "3-worse": _pair_model("worse", (5, 1, 1, 0)),
        "4-better": _pair_model("better", (3, 20, 20, 20)),
        "5-dominated": _pair_model("dominated", (3, 20, 20, 20), mismatch=11),
    }
    seen = {"seen"}
    pareto_calls = []

    def update(frontier, pair, *, limit):
        pareto_calls.append(pair.pair_fingerprint)
        assert limit == 9
        return coordinator.update_operating_pair_pareto_v1(frontier, pair, limit=limit)

    monkeypatch.setattr(
        shadow,
        "evaluate_operating_pair_v1",
        lambda ob, ib, *, context: (outcomes[ob.compile_variant.compilation_fingerprint], ()),
        raising=False,
    )
    monkeypatch.setattr(shadow, "update_operating_pair_pareto_v1", update, raising=False)
    result = shadow.evaluate_kbest_dag_pairs_v1(
        source_pair=source,
        outbound_options=tuple(_option(key) for key in reversed(outcomes)),
        inbound_options=(_option("I"),),
        context=SimpleNamespace(),
        frontier=(source,),
        pair_frontier_limit=9,
        already_generated=seen,
    )
    assert [item.decision for item in result.decisions] == [
        "FLEET_REJECTED",
        "DUPLICATE_PAIR",
        "NON_STRICT_RHYTHM",
        "NON_STRICT_RHYTHM",
        "PARETO_ADMITTED",
        "PARETO_REJECTED",
    ]
    assert pareto_calls == ["better", "dominated"]
    assert result.generated_pair_fingerprints == ("equal", "worse", "better", "dominated")
    assert seen == {"seen", "equal", "worse", "better", "dominated"}
    assert len(result.admitted_descendants) == 1
    parent = result.admitted_descendants[0]
    assert (parent.parent_fingerprint, parent.child_fingerprint) == ("source", "better")
    assert parent.parent_rhythm == (4, 8, 4, 0)
    assert parent.child_rhythm == (3, 20, 20, 20)
    for item in result.decisions:
        assert (item.pareto_before_hash != item.pareto_after_hash) == (
            item.decision == "PARETO_ADMITTED"
        )


def _real_pair_context(raw=None):
    raw = raw or _raw(10, 11, 100)
    context = _context(raw)
    context.route_id = raw.state.route_id
    context.planning_grid_seconds = 60
    context.runtime_minutes = 30
    context.minimum_layover_minutes = 5
    context.fleet_ceiling = 100
    outbound = _directional(raw, context)
    inbound_authority = replace(raw.compilation.endpoint_authority, direction="inbound")
    inbound_compilation = replace(
        raw.compilation, direction="inbound", endpoint_authority=inbound_authority
    )
    inbound = replace(
        outbound,
        state=replace(outbound.state, direction="inbound"),
        compile_variant=replace(
            outbound.compile_variant,
            compilation=inbound_compilation,
            compilation_fingerprint=clean_compilation_fingerprint_v1(inbound_compilation),
        ),
    )
    inbound = replace(inbound, state_fingerprint=service_plan_fingerprint_v1(inbound.state))
    context.endpoint_authority["inbound"] = inbound_authority
    context.demand_buckets["inbound"] = tuple(
        replace(bucket, direction="inbound") for bucket in context.demand_buckets["outbound"]
    )
    context.scenario_b_departures["inbound"] = inbound_compilation.exact_departures
    inbound_metrics, inbound_feedback = coordinator.evaluate_actual_service_v1(
        inbound.compile_variant,
        demand_buckets=context.demand_buckets["inbound"],
        scenario_b_departures=context.scenario_b_departures["inbound"],
    )
    inbound = replace(inbound, metrics=inbound_metrics, feedback=inbound_feedback)
    pair, feedback = coordinator.evaluate_operating_pair_v1(outbound, inbound, context=context)
    assert pair is not None and not feedback
    return pair, context


def test_pair_exact_fleet_rejection_cannot_reach_pareto(monkeypatch):
    source, context = _real_pair_context()
    assert source.metrics.fleet_required > 1
    context.fleet_ceiling = 1
    monkeypatch.setattr(shadow, "update_operating_pair_pareto_v1", _forbidden, raising=False)
    result = shadow.evaluate_kbest_dag_pairs_v1(
        source_pair=source,
        outbound_options=(source.outbound,),
        inbound_options=(source.inbound,),
        context=context,
        frontier=(source,),
        pair_frontier_limit=32,
        already_generated=set(),
    )
    assert len(result.decisions) == 1
    assert result.decisions[0].decision == "FLEET_REJECTED"
    assert result.decisions[0].pair_fingerprint is None
    assert result.generated_pair_fingerprints == result.admitted_descendants == ()
    assert result.frontier == (source,)


def test_source_pair_crosses_only_aggregate_retained_candidates(monkeypatch):
    source, context = _real_pair_context()
    calls = []

    def evaluate(ob, ib, *, context):
        calls.append(
            (ob.compile_variant.compilation_fingerprint, ib.compile_variant.compilation_fingerprint)
        )
        return coordinator.evaluate_operating_pair_v1(ob, ib, context=context)

    monkeypatch.setattr(shadow, "evaluate_operating_pair_v1", evaluate)
    result = shadow.refine_kbest_dag_source_pair_v1(
        source_pair=source,
        context=context,
        frontier=(source,),
        pair_frontier_limit=32,
        directional_frontier_limit=2,
        already_generated=set(),
    )
    retained = dict(result.directional_retentions)
    assert len(result.families) == 2
    assert sum(item.dag_call_count for item in result.families) == 2
    assert tuple(len(retained[direction].candidates) for direction in ("outbound", "inbound")) == (
        2,
        2,
    )
    assert calls == [
        (ob, ib)
        for ob in sorted(retained["outbound"].retained_fingerprints)
        for ib in sorted(retained["inbound"].retained_fingerprints)
    ]
    assert len(result.pair_evaluation.decisions) == 4
    assert all(len(value) == 64 for _, value in result.retained_hashes)
    assert all(
        item.child_rhythm < item.parent_rhythm
        for item in result.pair_evaluation.admitted_descendants
    )


def test_source_retention_counts_detected_families_even_when_no_states_reach_dag(monkeypatch):
    source, context = _real_pair_context()

    def empty_generation(**kwargs):
        return replace(local.enumerate_local_rhythm_states_v1(**kwargs), states=())

    monkeypatch.setattr(shadow, "enumerate_local_rhythm_states_v1", empty_generation)
    monkeypatch.setattr(shadow, "compile_service_plan_family_kbest_v1", _forbidden)
    result = shadow.refine_kbest_dag_source_pair_v1(
        source_pair=source,
        context=context,
        frontier=(source,),
        pair_frontier_limit=32,
        directional_frontier_limit=32,
        already_generated=set(),
    )
    assert len(result.families) == 2
    assert tuple(record.dag_call_count for record in result.families) == (0, 0)
    assert tuple(retention.family_count for _, retention in result.directional_retentions) == (1, 1)
    assert tuple(
        retention.raw_candidates_before_cross_family_dedupe
        for _, retention in result.directional_retentions
    ) == (0, 0)


def _completed(frontier, budget):
    return coordinator.RouteCoordinatorResultV1(
        route_id="eligibility-test",
        status="SEARCH_COMPLETE",
        search_budget=budget,
        statistics=coordinator.CoordinatorSearchStatisticsV1(),
        seed_states=(),
        pareto_frontier=tuple(frontier),
        feedback_code_counts={},
        revision_examples={},
        evaluated_state_fingerprints=(),
        protection_violations=(),
        protection_authority_validation=validate_closed_loop_service_protection_authority_v1(None),
    )


def test_completed_global_result_path_never_invokes_coordinator(monkeypatch):
    source, context = _real_pair_context()
    budget = coordinator.CoordinatorSearchBudgetV1(max_pair_frontier=4)
    completed = _completed((source,), budget)
    monkeypatch.setattr(
        coordinator,
        "search_route_service_plans_v1",
        lambda **kwargs: pytest.fail("global coordinator called from shadow path"),
    )
    monkeypatch.setattr(
        local,
        "search_route_service_plans_v1",
        lambda **kwargs: pytest.fail("legacy global coordinator called from shadow path"),
    )
    result = shadow.run_kbest_dag_shadow_from_completed_result_v1(
        base_coordinator_result=completed,
        context=context,
        coordinator_budget=budget,
        directional_frontier_limit=32,
    )
    assert result.base_coordinator_result is completed
    assert result.statistics.global_coordinator_executions == 0
    assert result.statistics.processed_source_count >= 1
    assert result.statistics.dag_graphs_built == sum(
        family.dag_call_count
        for source_result in result.source_refinements
        for family in source_result.families
    )
    assert len(result.processed_source_pair_fingerprints) == len(
        set(result.processed_source_pair_fingerprints)
    )
    assert len(result.selection_history) == result.statistics.processed_source_count + 1
    assert result.selection_history[-1] == result.final_v3_selection


def test_source_worklist_sorts_once_and_only_continues_material_strict_descendants(monkeypatch):
    a, z, orphan = (_pair_model(fp) for fp in ("a", "z", "orphan"))
    b = _pair_model("b", (3, 6, 3, 0))
    c = _pair_model("c", (2, 4, 2, 0))
    equal = _pair_model("equal")
    nonmaterial = _pair_model("nonmaterial", (3, 6, 3, 0))
    budget = coordinator.CoordinatorSearchBudgetV1(max_pair_frontier=9)
    completed = _completed((z, a, orphan), budget)
    process_calls, selection_calls = [], []

    def select(*, context, candidates):
        selection_calls.append(tuple(item.pair_fingerprint for item in candidates))
        material = (
            ("z", "a", "a")
            if len(selection_calls) == 1
            else ("z", "orphan", "equal", "c", "b", "a", "b")
        )
        return SimpleNamespace(
            phase_robust_materiality_fingerprints=material,
            selected_pair_fingerprint=material[-1],
            common_anchor_fingerprint="anchor",
            continuous_preservation_bound=1.0,
            classification="SELECTED",
        )

    def refine(
        *,
        source_pair,
        context,
        frontier,
        pair_frontier_limit,
        directional_frontier_limit,
        already_generated,
    ):
        assert pair_frontier_limit == 9 and directional_frontier_limit == 32
        fp = source_pair.pair_fingerprint
        process_calls.append(fp)
        if fp == "a":
            # Remove the other queued base source to prove its original object is preserved.
            frontier = (b, equal, nonmaterial, orphan)
            children = (b, equal, nonmaterial)
        elif fp == "b":
            frontier = (*frontier, c)
            children = (c,)
        else:
            children = ()
        parents = tuple(
            shadow.KBestDagDescendantV1(
                fp,
                child.pair_fingerprint,
                local.pair_rhythm_tuple_v1(source_pair),
                local.pair_rhythm_tuple_v1(child),
            )
            for child in children
        )
        pairs = shadow.KBestDagPairEvaluationV1(
            tuple(frontier), (), tuple(child.pair_fingerprint for child in children), parents
        )
        return shadow.KBestDagSourceRefinementV1(
            source_pair_fingerprint=fp, frontier=tuple(frontier), pair_evaluation=pairs
        )

    monkeypatch.setattr(shadow, "select_operational_timetable_v3", select, raising=False)
    monkeypatch.setattr(shadow, "refine_kbest_dag_source_pair_v1", refine, raising=False)
    result = shadow.run_kbest_dag_shadow_from_completed_result_v1(
        base_coordinator_result=completed,
        context=SimpleNamespace(),
        coordinator_budget=budget,
        directional_frontier_limit=32,
    )
    assert process_calls == ["a", "b", "c", "z"]
    assert result.processed_source_pair_fingerprints == ("a", "b", "c", "z")
    assert len(selection_calls) == 5
    assert [
        (item.parent_fingerprint, item.child_fingerprint) for item in result.continuation_history
    ] == [("a", "b"), ("b", "c")]
    assert all(item.child_rhythm < item.parent_rhythm for item in result.continuation_history)
    assert result.statistics.source_materiality_pair_count == 2
    assert result.statistics.processed_source_count == result.statistics.refinement_iterations == 4


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_completed_source_runner_rejects_invalid_retention_limit_before_selection(
    monkeypatch, limit
):
    monkeypatch.setattr(shadow, "select_operational_timetable_v3", _forbidden, raising=False)
    with pytest.raises(ValueError, match="positive integer"):
        shadow.run_kbest_dag_shadow_from_completed_result_v1(
            base_coordinator_result=_completed((), coordinator.CoordinatorSearchBudgetV1()),
            context=SimpleNamespace(),
            coordinator_budget=coordinator.CoordinatorSearchBudgetV1(),
            directional_frontier_limit=limit,
        )


def test_completed_source_runner_accepts_no_seeds():
    with pytest.raises(TypeError, match="seeds"):
        shadow.run_kbest_dag_shadow_from_completed_result_v1(
            base_coordinator_result=_completed((), coordinator.CoordinatorSearchBudgetV1()),
            context=SimpleNamespace(),
            coordinator_budget=coordinator.CoordinatorSearchBudgetV1(),
            seeds=(),
        )


def _cache_family(source_pair, context, cache, **kwargs):
    return shadow.realize_kbest_dag_families_v1(
        source_directional=source_pair.outbound,
        source_pair_fingerprint=source_pair.pair_fingerprint,
        context=context,
        semantic_cache=cache,
        **kwargs,
    )


def test_cache_reuses_only_frozen_raw_and_hard_eligible_family_semantics(monkeypatch):
    source, context = _real_pair_context()
    cache = {}
    first = _cache_family(source, context, cache)
    assert len(cache) == 1
    key, value = next(iter(cache.items()))
    assert isinstance(key, shadow.KBestDagSemanticCacheKeyV1)
    assert {field.name for field in fields(value)} == {
        "frontier",
        "eligible_candidates",
        "structural_rejects",
        "protection_rejects",
        "tail_rejects",
    }
    assert value.eligible_candidates == first[0].shadow.eligibility.eligible_candidates
    assert not hasattr(value, "candidates")  # Strict progress is recomputed outside the cache.
    with pytest.raises(FrozenInstanceError):
        value.tail_rejects = 1
    with pytest.raises(FrozenInstanceError):
        key.source_pair_fingerprint = "different"
    monkeypatch.setattr(shadow, "compile_service_plan_family_kbest_v1", _forbidden)
    monkeypatch.setattr(shadow, "_hard_eligible_candidate_v1", _forbidden)
    second = _cache_family(source, context, cache)
    assert first[0].dag_call_count == 1 and second[0].dag_call_count == 0
    assert second[0].cache_hit is True
    assert second[0].cache_key == key
    assert first[0].shadow.eligibility == second[0].shadow.eligibility
    assert first[0].shadow.eligibility is not second[0].shadow.eligibility
    assert first[0].raw_hash == second[0].raw_hash
    assert first[0].eligible_hash == second[0].eligible_hash


@pytest.mark.parametrize(
    "change",
    [
        "source_pair",
        "source_state",
        "direction",
        "family",
        "state_manifest",
        "endpoint",
        "protection",
        "demand",
        "demand_sha",
        "demand_response",
        "scenario_b",
        "implementation",
    ],
)
def test_cache_key_invalidates_every_semantic_authority(monkeypatch, change):
    source, context = _real_pair_context()
    cache = {}
    baseline = _cache_family(source, context, cache, implementation_authority_hash="a" * 64)
    key = baseline[0].cache_key
    assert key.raw_limit == 256
    assert key.source_pair_fingerprint == source.pair_fingerprint
    assert key.direction == "outbound"
    assert key.implementation_authority_hash == "a" * 64
    assert tuple(fp for fp, _ in key.sorted_state_manifest) == baseline[0].valid_state_fingerprints
    kwargs = {"implementation_authority_hash": "a" * 64}
    direction = "outbound"
    if change == "source_pair":
        source = replace(source, pair_fingerprint="new-source-pair")
    elif change == "source_state":
        source = replace(
            source,
            outbound=replace(
                source.outbound,
                state=replace(source.outbound.state, seed_id="new-source-provenance"),
            ),
        )
    elif change == "direction":
        direction = "inbound"
    elif change == "family":
        original = shadow.detect_local_rhythm_families_v1
        monkeypatch.setattr(
            shadow,
            "detect_local_rhythm_families_v1",
            lambda regimes: tuple(
                replace(family, canonical_representative=family.canonical_representative + 1)
                for family in original(regimes)
            ),
        )
    elif change == "state_manifest":
        original = shadow.enumerate_local_rhythm_states_v1

        def generate(**kwargs):
            result = original(**kwargs)
            return replace(
                result,
                states=tuple(
                    replace(state, seed_id="new-state-provenance") for state in result.states
                ),
            )

        monkeypatch.setattr(shadow, "enumerate_local_rhythm_states_v1", generate)
    elif change == "endpoint":
        context.endpoint_authority[direction] = replace(
            context.endpoint_authority[direction], authority_source="new-authority"
        )
    elif change == "protection":
        context.service_protection_authority = _protection()
    elif change == "demand":
        context.demand_buckets[direction] = tuple(
            replace(bucket, observed_demand=11.0) for bucket in context.demand_buckets[direction]
        )
    elif change == "demand_sha":
        context.immutable_demand_sha256 = "b" * 64
    elif change == "demand_response":
        context.demand_response_regimes = {"outbound": (), "inbound": ()}
    elif change == "scenario_b":
        context.scenario_b_departures[direction] = (0, *context.scenario_b_departures[direction])
    else:
        kwargs["implementation_authority_hash"] = "b" * 64
    changed = shadow.realize_kbest_dag_families_v1(
        source_directional=getattr(source, direction),
        source_pair_fingerprint=source.pair_fingerprint,
        context=context,
        semantic_cache=cache,
        **kwargs,
    )
    assert changed[0].cache_key != key
    assert changed[0].cache_hit is False
    assert changed[0].dag_call_count == 1
    assert len(cache) == 2


def test_cache_key_is_stable_under_generated_state_permutation(monkeypatch):
    source, context = _real_pair_context()
    cache = {}
    first = _cache_family(source, context, cache)
    original = shadow.enumerate_local_rhythm_states_v1

    def generate(**kwargs):
        result = original(**kwargs)
        return replace(result, states=tuple(reversed(result.states)))

    monkeypatch.setattr(shadow, "enumerate_local_rhythm_states_v1", generate)
    monkeypatch.setattr(shadow, "compile_service_plan_family_kbest_v1", _forbidden)
    second = _cache_family(source, context, cache)
    assert second[0].cache_key == first[0].cache_key
    assert second[0].cache_hit is True
    assert len(cache) == 1


@pytest.mark.parametrize("forbidden", ["cap", "retained", "pair", "pareto", "worklist", "v3"])
def test_cache_rejects_values_containing_run_state(monkeypatch, forbidden):
    source, context = _real_pair_context()
    cache = {}
    _cache_family(source, context, cache)
    key, value = next(iter(cache.items()))
    cache[key] = {"family": value, forbidden: ()}
    monkeypatch.setattr(shadow, "compile_service_plan_family_kbest_v1", _forbidden)
    with pytest.raises(ValueError, match="raw/eligible"):
        _cache_family(source, context, cache)


@pytest.mark.parametrize("forbidden", ["cap", "retained", "pair", "pareto", "worklist", "v3"])
def test_cache_rejects_frozen_run_state_nested_in_eligible_semantics(monkeypatch, forbidden):
    source, context = _real_pair_context()
    cache = {}
    _cache_family(source, context, cache)
    key, value = next(iter(cache.items()))
    payload_type = make_dataclass("RunState", [(forbidden, tuple)], frozen=True, slots=True)
    poisoned = replace(value.eligible_candidates[0], metrics=payload_type(()))
    cache[key] = replace(value, eligible_candidates=(poisoned,))
    monkeypatch.setattr(shadow, "compile_service_plan_family_kbest_v1", _forbidden)
    with pytest.raises(ValueError, match="raw/eligible"):
        _cache_family(source, context, cache)


def test_cap_specific_sensitivity_descendant_runs_its_own_worklist_and_dag(monkeypatch):
    source, context = _real_pair_context(_path_raw((20, 10, 11, 100), counts=(6, 3, 3, 2)))
    families = shadow.realize_kbest_dag_families_v1(
        source_directional=source.outbound, context=context
    )
    options = {
        cap: shadow.retain_kbest_dag_directional_frontier_v1(
            source_directional=source.outbound,
            family_results=tuple(f.shadow for f in families),
            context=context,
            limit=cap,
        ).retained_fingerprints
        for cap in (16, 32, 64)
    }
    cap64_only_option = min(set(options[64]) - set(options[32]) - set(options[16]))
    child = replace(
        source,
        pair_fingerprint="cap64-child",
        metrics=replace(source.metrics, total_directional_sustained_headway_level_count=0),
    )
    budget = coordinator.CoordinatorSearchBudgetV1(max_pair_frontier=9)
    completed = _completed((source,), budget)
    evaluations, compiler_calls, selections = [], [], []
    original_compile = shadow.compile_service_plan_family_kbest_v1

    def compile_family(**kwargs):
        compiler_calls.append(
            tuple(service_plan_fingerprint_v1(state) for state in kwargs["states"])
        )
        return original_compile(**kwargs)

    def evaluate(
        *,
        source_pair,
        outbound_options,
        inbound_options,
        context,
        frontier,
        pair_frontier_limit,
        already_generated,
    ):
        assert pair_frontier_limit == 9
        evaluations.append((source_pair.pair_fingerprint, already_generated))
        children = ()
        if source_pair.pair_fingerprint == source.pair_fingerprint and cap64_only_option in {
            option.compile_variant.compilation_fingerprint for option in outbound_options
        }:
            frontier = (*frontier, child)
            children = (
                shadow.KBestDagDescendantV1(
                    source.pair_fingerprint,
                    child.pair_fingerprint,
                    local.pair_rhythm_tuple_v1(source),
                    local.pair_rhythm_tuple_v1(child),
                ),
            )
        return shadow.KBestDagPairEvaluationV1(
            tuple(frontier), (), tuple(item.child_fingerprint for item in children), children
        )

    def select(*, context, candidates):
        result = SimpleNamespace(
            phase_robust_materiality_fingerprints=tuple(
                item.pair_fingerprint for item in candidates
            ),
            selected_pair_fingerprint=source.pair_fingerprint,
        )
        selections.append(result)
        return result

    monkeypatch.setattr(shadow, "compile_service_plan_family_kbest_v1", compile_family)
    monkeypatch.setattr(shadow, "evaluate_kbest_dag_pairs_v1", evaluate)
    monkeypatch.setattr(shadow, "select_operational_timetable_v3", select)
    result = shadow.run_kbest_dag_cap_sensitivity_v1(
        base_coordinator_result=completed, context=context, coordinator_budget=budget
    )
    runs = (result.cap16, result.cap32, result.cap64)
    assert [run.processed_source_pair_fingerprints for run in runs] == [
        (source.pair_fingerprint,),
        (source.pair_fingerprint,),
        (source.pair_fingerprint, "cap64-child"),
    ]
    assert [fp for fp, _ in evaluations] == [source.pair_fingerprint] * 3 + ["cap64-child"]
    assert len({id(generated) for _, generated in evaluations}) == 3
    assert evaluations[-1][1] is evaluations[-2][1]
    assert (
        len(compiler_calls) == 2 * len(families) * 2
    )  # Base source, plus the new descendant in both directions.
    assert sum(f.dag_call_count for f in result.cap64.source_refinements[-1].families) == 2 * len(
        families
    )
    for attribute in (
        "processed_source_pair_fingerprints",
        "pareto_history_hashes",
        "selection_history",
        "source_refinements",
        "augmented_pareto_frontier",
    ):
        assert len({id(getattr(run, attribute)) for run in runs}) == 3
    retained = [run.source_refinements[0].directional_retentions[0][1] for run in runs]
    assert [item.retained_count for item in retained] == [16, 32, 64]
    assert len({id(item.candidates) for item in retained}) == 3
    assert len({id(run.base_v3_selection) for run in runs}) == 3
    assert result.cap32.source_refinements[0].families[0].cache_hit is True


def test_sensitivity_fresh_repeat_discards_shared_cache(monkeypatch):
    source, context = _real_pair_context()
    budget = coordinator.CoordinatorSearchBudgetV1(max_pair_frontier=4)
    completed = _completed((source,), budget)
    cache = {}
    first = shadow.run_kbest_dag_cap_sensitivity_v1(
        base_coordinator_result=completed,
        context=context,
        coordinator_budget=budget,
        semantic_cache=cache,
    )
    assert cache
    cache.clear()
    cache["invalid-unused-cache"] = {"cap": 32}
    repeated = shadow.run_kbest_dag_cap_sensitivity_v1(
        base_coordinator_result=completed,
        context=context,
        coordinator_budget=budget,
        semantic_cache=cache,
        fresh_repeat=True,
    )
    assert cache == {"invalid-unused-cache": {"cap": 32}}
    for left, right in zip(
        (first.cap16, first.cap32, first.cap64),
        (repeated.cap16, repeated.cap32, repeated.cap64),
        strict=True,
    ):
        assert left.processed_source_pair_fingerprints == right.processed_source_pair_fingerprints
        assert left.pareto_history_hashes == right.pareto_history_hashes
        assert left.final_v3_selection == right.final_v3_selection
    assert repeated.cap16.source_refinements[0].families[0].cache_hit is False
    assert repeated.cap16.statistics.dag_graphs_built > 0


def _binding_candidate(fingerprint, *, sse, te, continuous, rhythm, wait):
    """Hand-chosen 10-D tradeoffs; V3 inputs are projected independently of Pareto metrics."""
    pair = _pair_model(fingerprint, rhythm=rhythm, mismatch=sse)
    pair.metrics = replace(pair.metrics, demand_weighted_expected_passenger_wait_minutes=wait)
    pair.selection_snapshot = SimpleNamespace(
        fingerprint=fingerprint,
        hard_feasible=True,
        hard_feasibility_reasons=(),
        hard_feasibility_metrics={},
        observed_demand_mismatch=sse,
        outbound_maximum_bucket_expected_wait_minutes=0.0,
        inbound_maximum_bucket_expected_wait_minutes=0.0,
        pair_trip_equivalent_error=te,
        outbound_continuous_exposure_equivalent=continuous / 2,
        inbound_continuous_exposure_equivalent=continuous / 2,
        pair_continuous_exposure_equivalent=continuous,
        total_directional_sustained_headway_level_count=rhythm[0],
        actual_service_regime_count=rhythm[1],
        total_directional_effective_palette_count=rhythm[2],
        total_single_gap_regime_count=rhythm[3],
        fleet_required=2,
        total_excess_terminal_wait=0,
        max_excess_terminal_wait=0,
        diagnostics={},
    )
    return pair


def _binding_context(monkeypatch):
    # Use unchanged timetable selection and V3, supplying the explicit metric fixture at projection.
    monkeypatch.setattr(
        selection_v3,
        "build_operational_selection_candidate_v3",
        lambda *, context, candidate: candidate.selection_snapshot,
    )
    return _real_pair_context()[1]


def _binding_run(candidates, context):
    return SimpleNamespace(
        augmented_pareto_frontier=tuple(candidates),
        final_v3_selection=selection_v3.select_operational_timetable_v3(
            context=context, candidates=candidates
        ),
    )


def test_binding_normalized_union_can_select_a_cap32_present_candidate(monkeypatch):
    context = _binding_context(monkeypatch)
    a = _binding_candidate("A", sse=1.0, te=10.0, continuous=20.0, rhythm=(2, 2, 2, 0), wait=9)
    b = _binding_candidate("B", sse=2.0, te=12.0, continuous=22.0, rhythm=(1, 2, 2, 0), wait=8)
    x = _binding_candidate("X", sse=3.0, te=11.0, continuous=24.0, rhythm=(3, 2, 2, 0), wait=7)
    cap32 = _binding_run((b, a), context)
    cap64 = _binding_run((x, b, a), context)
    assert cap32.final_v3_selection.selected_pair_fingerprint == "A"
    assert cap32.final_v3_selection.continuous_preservation_bound == 0.0
    update_calls, selection_calls = [], []

    def update(frontier, candidate, *, limit):
        update_calls.append((candidate.pair_fingerprint, limit))
        return coordinator.update_operating_pair_pareto_v1(frontier, candidate, limit=limit)

    def select(*, context, candidates):
        assert update_calls == [("A", None), ("B", None), ("X", None)]
        selection_calls.append(tuple(item.pair_fingerprint for item in candidates))
        return selection_v3.select_operational_timetable_v3(context=context, candidates=candidates)

    monkeypatch.setattr(shadow, "update_operating_pair_pareto_v1", update)
    monkeypatch.setattr(shadow, "select_operational_timetable_v3", select)
    result = shadow.adjudicate_kbest_dag_cap_binding_v1(cap32=cap32, cap64=cap64, context=context)
    assert selection_calls == [("A", "B", "X")]
    assert result.normalized_union_selection.selected_pair_fingerprint == "B"
    assert result.normalized_union_selection.continuous_preservation_bound == 4.0
    assert result.binding is True
    assert result.classification == "U6_DIRECTIONAL_FRONTIER_32_CAP_BINDING"
    assert result.normalized_union_winner_cap32_present is True
    assert result.normalized_union_winner_cap64_only is False
    assert tuple(item.pair_fingerprint for item in result.normalized_union_frontier) == (
        "A",
        "B",
        "X",
    )


@pytest.mark.parametrize(
    ("x_rhythm", "winner", "binding"), [((1, 2, 2, 0), "X", True), ((3, 2, 2, 0), "A", False)]
)
def test_binding_cap64_exclusive_winner_and_same_winner(monkeypatch, x_rhythm, winner, binding):
    context = _binding_context(monkeypatch)
    a = _binding_candidate("A", sse=1.0, te=10.0, continuous=20.0, rhythm=(2, 2, 2, 0), wait=9)
    x = _binding_candidate("X", sse=3.0, te=11.0, continuous=24.0, rhythm=x_rhythm, wait=7)
    result = shadow.adjudicate_kbest_dag_cap_binding_v1(
        cap32=_binding_run((a,), context), cap64=_binding_run((x, a), context), context=context
    )
    assert result.normalized_union_selection.selected_pair_fingerprint == winner
    assert result.binding is binding
    assert result.normalized_union_winner_cap32_present is (winner == "A")
    assert result.normalized_union_winner_cap64_only is (winner == "X")


def test_normalized_union_removes_cross_cap_dominated_calibration_candidate_before_v3(monkeypatch):
    context = _binding_context(monkeypatch)
    a = _binding_candidate("A", sse=1.0, te=10.0, continuous=20.0, rhythm=(2, 2, 2, 0), wait=9)
    b = _binding_candidate("B", sse=2.0, te=12.0, continuous=22.0, rhythm=(1, 2, 2, 0), wait=8)
    d = _binding_candidate("D", sse=4.0, te=11.0, continuous=100.0, rhythm=(4, 2, 2, 0), wait=10)
    cap32, cap64 = _binding_run((a, b), context), _binding_run((d,), context)
    calls = []

    def select(*, context, candidates):
        calls.append(tuple(item.pair_fingerprint for item in candidates))
        assert calls[-1] == ("A", "B"), "V3 must never see the dominated calibration candidate"
        return selection_v3.select_operational_timetable_v3(context=context, candidates=candidates)

    monkeypatch.setattr(shadow, "select_operational_timetable_v3", select)
    result = shadow.adjudicate_kbest_dag_cap_binding_v1(cap32=cap32, cap64=cap64, context=context)
    assert calls == [("A", "B")]
    assert result.normalized_union_selection.selected_pair_fingerprint == "A"
    assert result.normalized_union_selection.continuous_preservation_bound == 0.0
    assert result.binding is False


def test_sensitivity_binding_ignores_cap16_diagnostic_universe(monkeypatch):
    context = _binding_context(monkeypatch)
    a = _binding_candidate("A", sse=1.0, te=10.0, continuous=20.0, rhythm=(2, 2, 2, 0), wait=9)
    b = _binding_candidate("B", sse=2.0, te=12.0, continuous=22.0, rhythm=(1, 2, 2, 0), wait=8)
    x = _binding_candidate("X", sse=3.0, te=11.0, continuous=24.0, rhythm=(3, 2, 2, 0), wait=7)
    runs = {
        16: _binding_run((a, b, x), context),
        32: _binding_run((a, b), context),
        64: _binding_run((a, b), context),
    }
    calls = []
    budget = coordinator.CoordinatorSearchBudgetV1()
    completed = _completed((), budget)

    def run(**kwargs):
        assert kwargs["base_coordinator_result"] is completed
        cap = kwargs["directional_frontier_limit"]
        calls.append(cap)
        return runs[cap]

    monkeypatch.setattr(shadow, "run_kbest_dag_shadow_from_completed_result_v1", run)
    result = shadow.run_kbest_dag_cap_sensitivity_v1(
        base_coordinator_result=completed, context=context, coordinator_budget=budget
    )
    assert calls == [16, 32, 64]
    assert result.cap16.final_v3_selection.selected_pair_fingerprint == "B"
    assert result.cap_binding.normalized_union_selection.selected_pair_fingerprint == "A"
    assert result.cap_binding.binding is False


def test_binding_compares_no_selection_outcomes_and_empty_union(monkeypatch):
    context = _binding_context(monkeypatch)
    empty = _binding_run((), context)
    result = shadow.adjudicate_kbest_dag_cap_binding_v1(cap32=empty, cap64=empty, context=context)
    assert result.normalized_union_frontier == ()
    assert result.normalized_union_selection.selected_pair_fingerprint is None
    assert result.binding is False
    assert result.normalized_union_winner_cap32_present is False
    assert result.normalized_union_winner_cap64_only is False
