from __future__ import annotations

from types import SimpleNamespace

import pytest

from bus_schedule_engine.contracts_v1.clean_boundary_compiler import (
    CleanBoundaryCompilationStatusV1,
    CleanBoundaryCompilationV1,
    CompiledDemandRegimeSliceV1,
    CompiledServiceRegimeV1,
    OperationalEndpointAuthorityV1,
)
from bus_schedule_engine.contracts_v1.clean_compile_frontier import CleanCompileVariantV1
from bus_schedule_engine.contracts_v1.closed_loop_service_protection import (
    ClosedLoopProtectedServiceWindowV1,
    build_closed_loop_service_protection_authority_v1,
    validate_closed_loop_service_protection_v1,
)
from bus_schedule_engine.contracts_v1.service_plan_state import (
    ServicePlanMoveV1,
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
)
from bus_schedule_engine.service_plan_coordinator import (
    TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION,
    CoordinatorSearchBudgetV1,
    DemandBucketEvidenceV1,
    FeedbackEvidenceV1,
    OperatingPairCandidateV1,
    OperatingPairMetricsV1,
    RouteCoordinatorContextV1,
    assess_tail_ordering_v1,
    dominates_operating_pair_v1,
    generate_targeted_neighbors_v1,
    rhythm_simplicity_metrics_v1,
    search_route_service_plans_v1,
)


def _compilation(
    headways: tuple[int, ...],
    *,
    trip_counts: tuple[int, ...] | None = None,
    slice_groups: tuple[tuple[tuple[int, int], ...], ...] | None = None,
    fixed_first: int = 0,
    fixed_last: int | None = None,
) -> CleanBoundaryCompilationV1:
    counts = trip_counts or tuple(3 for _ in headways)
    groups = slice_groups or tuple(
        ((index * 3600, (index + 1) * 3600),) for index in range(len(headways))
    )
    window_end = max(end for group in groups for _, end in group)
    active_last = window_end if fixed_last is None else fixed_last
    services = []
    slices = []
    exact = []
    for index, (headway, trip_count, group) in enumerate(
        zip(headways, counts, groups, strict=True), start=1
    ):
        service_id = f"SERVICE-OUTBOUND-{index:02d}"
        support_start = group[0][0]
        departures = tuple(support_start + gap * headway * 60 for gap in range(trip_count))
        services.append(
            CompiledServiceRegimeV1(
                service_regime_id=service_id,
                direction="outbound",
                demand_regime_ids=tuple(
                    f"PLAN-OUTBOUND-{index:02d}-{part:02d}" for part in range(1, len(group) + 1)
                ),
                uniform_headway_minutes=headway,
                first_departure=departures[0],
                last_departure=departures[-1],
                trip_count=trip_count,
                departures=departures,
            )
        )
        exact.extend(departures)
        for part, (start, end) in enumerate(group, start=1):
            slices.append(
                CompiledDemandRegimeSliceV1(
                    demand_regime_id=f"PLAN-OUTBOUND-{index:02d}-{part:02d}",
                    demand_regime_start=start,
                    demand_regime_end=end,
                    authoritative_trip_count=trip_count,
                    service_regime_id=service_id,
                    uniform_headway_minutes=headway,
                    first_departure=departures[0],
                    last_departure=departures[-1],
                    departures=departures,
                    headway_quantization_error=0.0,
                    phase_imbalance_minutes=0,
                )
            )
    authority = OperationalEndpointAuthorityV1(
        route_id="X",
        direction="outbound",
        analysis_window_start=0,
        analysis_window_end=window_end + 60,
        fixed_first_departure=fixed_first,
        fixed_last_departure=active_last,
        authority_source="synthetic PR62-H test",
    )
    return CleanBoundaryCompilationV1(
        compiler_profile="synthetic",
        route_id="X",
        direction="outbound",
        candidate_id="H-TEST",
        status=CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES,
        endpoint_authority=authority,
        demand_regime_slices=tuple(slices),
        service_regimes=tuple(services),
        exact_departures=tuple(sorted(set(exact))),
        boundary_diagnostics=(),
        total_headway_quantization_error=0.0,
        total_phase_imbalance_minutes=0,
        failure=None,
    )


def _demand(rates: tuple[float, ...]) -> tuple[DemandBucketEvidenceV1, ...]:
    return tuple(
        DemandBucketEvidenceV1("outbound", index * 3600, (index + 1) * 3600, rate)
        for index, rate in enumerate(rates)
    )


@pytest.mark.parametrize(
    ("headways", "classification", "margin"),
    [
        ((8, 10, 15), "TAIL_IS_SLOWEST", 5),
        ((8, 15, 15), "TAIL_IS_SLOWEST", 0),
    ],
)
def test_tail_slowest_and_equal_max_pass(
    headways: tuple[int, ...], classification: str, margin: int
) -> None:
    assessment = assess_tail_ordering_v1(_compilation(headways), _demand((100, 100, 100)))

    assert assessment.classification == classification
    assert assessment.eligible
    assert assessment.tail_slowest_margin_minutes == margin


@pytest.mark.parametrize(
    ("rates", "classification", "eligible"),
    [
        ((100, 200, 50), TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION, False),
        ((50, 200, 100), "TAIL_SHORTER_DEMAND_JUSTIFIED", True),
        ((100, 200, 100), TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION, False),
    ],
)
def test_tail_inversion_uses_strict_immutable_demand_only(
    rates: tuple[float, ...], classification: str, eligible: bool
) -> None:
    assessment = assess_tail_ordering_v1(_compilation((16, 10, 15)), _demand(rates))

    assert assessment.max_non_tail_headway_minutes == 16
    assert assessment.tail_slowest_margin_minutes == -1
    assert assessment.classification == classification
    assert assessment.eligible is eligible
    assert tuple(item.headway_minutes for item in assessment.offending_regimes) == (16,)


def test_all_tail_offenders_must_be_justified() -> None:
    assessment = assess_tail_ordering_v1(_compilation((18, 16, 10, 15)), _demand((40, 90, 200, 80)))

    assert tuple(item.headway_minutes for item in assessment.offending_regimes) == (18, 16)
    assert not assessment.demand_justified
    assert not assessment.eligible


def test_single_regime_has_no_tail_ordering_conflict() -> None:
    assessment = assess_tail_ordering_v1(_compilation((10,)), _demand((100,)))

    assert assessment.classification == "SINGLE_REGIME_NO_TAIL_ORDERING_CONFLICT"
    assert assessment.eligible


@pytest.mark.parametrize(
    ("maximum_headway", "expected"),
    [
        (15, "TAIL_SHORTER_PROTECTION_JUSTIFIED"),
        (20, TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION),
    ],
)
def test_protection_exception_requires_binding_maximum_headway_authority(
    maximum_headway: int, expected: str
) -> None:
    compilation = _compilation((16, 15))
    tail = compilation.service_regimes[-1]
    authority = build_closed_loop_service_protection_authority_v1(
        source_authority_profile="synthetic",
        source_authority_fingerprint="a" * 64,
        windows=(
            ClosedLoopProtectedServiceWindowV1(
                source_regime_id="TAIL-PROTECTION",
                direction="outbound",
                protected_window_start=tail.departures[0],
                protected_window_end=tail.departures[-1],
                boundary_tolerance_minutes=0,
                maximum_headway_minutes=maximum_headway,
                minimum_trip_count=3,
            ),
        ),
    )
    validation = validate_closed_loop_service_protection_v1(
        authority=authority,
        direction="outbound",
        exact_departures=compilation.exact_departures,
    )
    assessment = assess_tail_ordering_v1(
        compilation,
        _demand((100, 50)),
        protection_authority=authority,
        protection_validation=validation,
    )

    assert validation.passed
    assert assessment.classification == expected
    assert assessment.eligible is (maximum_headway == 15)
    assert bool(assessment.protection_witnesses) is (maximum_headway == 15)


def test_merged_slice_support_is_exact_union_clipped_to_active_span() -> None:
    compilation = _compilation(
        (10, 15),
        slice_groups=(((0, 1800), (1800, 3600)), ((3600, 7200),)),
        fixed_first=600,
        fixed_last=6600,
    )
    assessment = assess_tail_ordering_v1(
        compilation,
        (
            DemandBucketEvidenceV1("outbound", 0, 3600, 100),
            DemandBucketEvidenceV1("outbound", 3600, 7200, 50),
        ),
    )

    assert assessment.eligible
    assert assessment.tail_demand_rate_per_hour == pytest.approx(50)
    assert len(compilation.service_regimes) == 2


def test_tail_repair_family_is_strictly_bounded() -> None:
    state = ServicePlanStateV1(
        route_id="X",
        direction="outbound",
        fixed_first_departure=0,
        fixed_last_departure=10740,
        service_regimes=(
            ServiceRegimeDecisionV1(0, 3600, 4),
            ServiceRegimeDecisionV1(3600, 7200, 4),
            ServiceRegimeDecisionV1(7200, 10800, 4),
        ),
        seed_id="H",
    )
    neighbors = generate_targeted_neighbors_v1(
        state,
        feedback=(FeedbackEvidenceV1(TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION, "outbound"),),
        planning_grid_seconds=300,
        floor_headway_minutes=None,
    )

    assert {item.move for item in neighbors} <= {
        ServicePlanMoveV1.TAIL_RELEASE_ONE,
        ServicePlanMoveV1.SHIFT_BOUNDARY_LEFT,
    }
    assert {item.affected_index for item in neighbors} == {1}
    assert all(item.state.total_trips == state.total_trips for item in neighbors)
    for item in neighbors:
        if item.move == ServicePlanMoveV1.SHIFT_BOUNDARY_LEFT:
            assert item.state.boundaries[-1] == state.boundaries[-1] - 300
            assert abs(item.state.trip_count_vector[-2] - state.trip_count_vector[-2]) <= 1


def test_tail_invalid_compilation_is_rejected_before_fleet_pairing() -> None:
    compilation = _compilation((16, 15), fixed_last=7140)
    variant = CleanCompileVariantV1(
        compilation_fingerprint="tail-invalid",
        frontier_rank=1,
        headway_quantization=0.0,
        actual_service_regime_count=2,
        phase_edge_quality_minutes=0,
        compilation=compilation,
    )
    state = ServicePlanStateV1(
        route_id="X",
        direction="outbound",
        fixed_first_departure=0,
        fixed_last_departure=7140,
        service_regimes=(
            ServiceRegimeDecisionV1(0, 3600, 3),
            ServiceRegimeDecisionV1(3600, 7200, 3),
        ),
        seed_id="H-INVALID",
    )
    context = RouteCoordinatorContextV1(
        route_id="X",
        route_name="Synthetic",
        endpoint_authority={"outbound": compilation.endpoint_authority},
        demand_buckets={"outbound": _demand((100, 50))},
        scenario_b_departures={"outbound": compilation.exact_departures},
        seed_headway_prior_minutes={"outbound": 15.0},
        planning_grid_seconds=300,
        runtime_minutes=1,
        minimum_layover_minutes=1,
        fleet_ceiling=20,
        immutable_demand_sha256="immutable",
    )
    result = search_route_service_plans_v1(
        context=context,
        seeds=(state,),
        budget=CoordinatorSearchBudgetV1(1, 32, 1, 4, 8),
        compiler=lambda *_args, **_kwargs: SimpleNamespace(variants=(variant,), failure=None),
    )

    assert result.statistics.tail_ordering_compilations_rejected == 1
    assert result.statistics.fleet_validations_run == 0
    assert not result.pareto_frontier
    assert result.feedback_code_counts[TAIL_NOT_SLOWEST_WITHOUT_DEMAND_JUSTIFICATION] == 1


def test_rhythm_exact_palette_and_repeated_levels() -> None:
    metrics = rhythm_simplicity_metrics_v1(_compilation((16, 10, 14, 10, 15, 8, 14, 15)))

    assert metrics.sustained_headway_levels == (8, 10, 14, 15, 16)
    assert metrics.sustained_headway_level_count == 5
    assert metrics.effective_headway_palette == (8, 10, 15)
    assert metrics.effective_headway_palette_count == 3


def test_single_gap_regime_is_residual_not_sustained() -> None:
    metrics = rhythm_simplicity_metrics_v1(_compilation((8, 14, 15), trip_counts=(3, 2, 3)))

    assert metrics.sustained_headway_levels == (8, 15)
    assert metrics.sustained_headway_level_count == 2
    assert metrics.single_gap_regime_count == 1
    assert metrics.single_gap_headway_levels == (14,)


def test_effective_palette_gap_weights_and_tie_break_are_deterministic() -> None:
    metrics = rhythm_simplicity_metrics_v1(
        _compilation((9, 10, 14, 15, 16), trip_counts=(3, 4, 3, 4, 3))
    )

    assert metrics.effective_headway_palette == (10, 15)


def _pair(pair_id: str, wait: float, palette: int) -> OperatingPairCandidateV1:
    return OperatingPairCandidateV1(
        pair_fingerprint=pair_id,
        outbound=None,  # type: ignore[arg-type]
        inbound=None,  # type: ignore[arg-type]
        metrics=OperatingPairMetricsV1(
            observed_demand_mismatch=1.0,
            demand_weighted_expected_passenger_wait_minutes=wait,
            actual_service_regime_count=4,
            max_frequency_jump=1.0,
            total_frequency_variation=1.0,
            moved_trips_vs_b=1,
            fleet_required=4,
            total_excess_terminal_wait=1,
            max_excess_terminal_wait=1,
            total_directional_sustained_headway_level_count=palette,
        ),
        fleet_ceiling=4,
        minimum_connection_layover_minutes=5,
        feedback=(),
        history=(),
    )


def test_new_palette_dimension_dominates_only_when_other_metrics_are_no_worse() -> None:
    assert dominates_operating_pair_v1(_pair("simple", 5.0, 4), _pair("complex", 5.0, 6))
    assert not dominates_operating_pair_v1(_pair("simple-slow", 6.0, 4), _pair("fast", 5.0, 6))
    assert not dominates_operating_pair_v1(_pair("fast", 5.0, 6), _pair("simple-slow", 6.0, 4))
