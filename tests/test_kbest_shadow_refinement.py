"""Hard authority gates and the uncapped, unchanged aggregate selector."""

from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import pytest

import bus_schedule_engine.kbest_shadow_refinement as shadow
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
)
from bus_schedule_engine.contracts_v1.kbest_dag_frontier import (
    KBestDagCandidateV1,
    KBestDagFrontierV1,
    KBestDagGraphStatisticsV1,
    KBestDagTelemetryV1,
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


def _path_raw(headways, gaps=None):
    counts = (*((3,) * (len(headways) - 1)), 2)
    gaps = gaps or headways[:-1]
    starts = [0]
    for h, n, gap in zip(headways, counts, gaps, strict=False):
        starts.append(starts[-1] + (n - 1) * h + gap)
    end = starts[-1] + headways[-1]
    bounds = (*starts, end + 1)
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
        state.route_id, state.direction, 0, (end + 1) * 60, 0, end * 60, "test"
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
