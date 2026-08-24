from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bus_schedule_engine.contracts_v1.demand_regimes import (
    BoundaryDecisionV1,
    DemandRegimeDetectionStatusV1,
    DemandRegimeDetectorConfigV1,
    DemandRegimeScopeV1,
    demand_regime_detection_to_dict_v1,
    detect_demand_regimes_v1,
)
from bus_schedule_engine.contracts_v1.models import ContractDirection
from bus_schedule_engine.contracts_v1.multi_period_demand import (
    DemandDirectionGrainV1,
    DemandProfileAggregationMethodV1,
    DemandProfileV1,
    DerivedDemandObservationV1,
)


def _profile(
    values: tuple[float, ...],
    *,
    bucket_minutes: int = 60,
    starts: tuple[int, ...] | None = None,
    direction: ContractDirection = ContractDirection.COMBINED,
) -> DemandProfileV1:
    start_values = starts or tuple(
        (5 * 60 + index * bucket_minutes) * 60 for index in range(len(values))
    )
    return DemandProfileV1(
        profile_id="test-profile",
        included_period_ids=("test-period",),
        aggregation_method=DemandProfileAggregationMethodV1.SINGLE_PERIOD,
        period_weight_method="observation_days",
        total_observation_days=1,
        direction_grain=(
            DemandDirectionGrainV1.COMBINED
            if direction == ContractDirection.COMBINED
            else DemandDirectionGrainV1.DIRECTIONAL
        ),
        derived_observations=tuple(
            DerivedDemandObservationV1(
                direction=direction,
                interval_start=start,
                interval_end=start + bucket_minutes * 60,
                average_daily_passengers=value,
            )
            for start, value in zip(start_values, values, strict=True)
        ),
        source_period_fingerprints=(("test-period", "abc"),),
        limitations=(),
        profile_fingerprint="profile-fingerprint",
    )


def _only_plan(values: tuple[float, ...], **kwargs):
    result = detect_demand_regimes_v1(_profile(values, **kwargs))
    assert result.status == DemandRegimeDetectionStatusV1.SUCCESS
    return result.plans[0]


def test_flat_demand_produces_one_regime() -> None:
    plan = _only_plan((100, 100, 100, 100, 100, 100))

    assert len(plan.regimes) == 1
    assert plan.objective_cost == 0


def test_clear_sustained_morning_peak_is_separated() -> None:
    plan = _only_plan((60, 70, 180, 190, 185, 75, 70))

    assert len(plan.regimes) == 3
    assert [item.bucket_count for item in plan.regimes] == [2, 3, 2]
    assert plan.regimes[1].demand_mean > plan.regimes[0].demand_mean
    assert plan.regimes[1].demand_mean > plan.regimes[2].demand_mean


@pytest.mark.parametrize(
    "values",
    [
        (80, 80, 200, 80, 80),
        (180, 180, 80, 180, 180),
    ],
)
def test_single_bucket_spike_or_dip_is_suppressed(values: tuple[float, ...]) -> None:
    plan = _only_plan(values)

    assert len(plan.regimes) == 1
    middle_boundary_evidence = [
        item for item in plan.boundary_evidence if item.decision == BoundaryDecisionV1.SUPPRESS
    ]
    assert middle_boundary_evidence


def test_two_sustained_plateaus_produce_two_regimes() -> None:
    plan = _only_plan((80, 80, 80, 180, 180, 180))

    assert len(plan.regimes) == 2
    assert plan.regimes[0].bucket_count == plan.regimes[1].bucket_count == 3
    kept = [item for item in plan.boundary_evidence if item.decision == BoundaryDecisionV1.KEEP]
    assert len(kept) == 1
    assert kept[0].segmented_fit_improvement > kept[0].complexity_penalty


def test_all_zero_observed_demand_is_a_valid_simple_plan() -> None:
    plan = _only_plan((0, 0, 0, 0, 0, 0))

    assert len(plan.regimes) == 1
    assert plan.total_demand == 0
    assert plan.regimes[0].normalized_demand_mean == 0
    assert plan.regimes[0].demand_share == 0


def test_missing_bucket_is_not_interpreted_as_observed_zero() -> None:
    starts = (5 * 3600, 6 * 3600, 8 * 3600, 9 * 3600)

    result = detect_demand_regimes_v1(_profile((20, 20, 20, 20), starts=starts))

    assert result.status == DemandRegimeDetectionStatusV1.INSUFFICIENT_DEMAND_COVERAGE
    assert result.failure_code == "INSUFFICIENT_DEMAND_COVERAGE"
    assert result.plans == ()
    assert result.coverage[0].missing_intervals == ((7 * 3600, 8 * 3600),)
    assert result.coverage[0].coverage_ratio == pytest.approx(0.8)


def test_serialized_result_is_identical_across_100_runs() -> None:
    profile = _profile((60, 70, 180, 190, 185, 75, 70))
    serialized = {
        json.dumps(
            demand_regime_detection_to_dict_v1(detect_demand_regimes_v1(profile)),
            sort_keys=True,
            separators=(",", ":"),
        )
        for _ in range(100)
    }

    assert len(serialized) == 1


def test_sustained_plateaus_can_produce_more_than_six_regimes() -> None:
    values = tuple(
        value
        for plateau in range(8)
        for value in ((20.0, 20.0) if plateau % 2 == 0 else (200.0, 200.0))
    )
    profile = _profile(values)
    config = DemandRegimeDetectorConfigV1(
        target_min_regime_minutes=120,
        complexity_penalty=0.001,
    )

    result = detect_demand_regimes_v1(profile, config)
    plan = result.plans[0]

    assert len(plan.regimes) == 8
    assert plan.selected_regime_count == 8
    assert plan.natural_max_regimes == 8


def test_noisy_near_flat_demand_does_not_fill_large_natural_bound() -> None:
    values = (100, 101, 99, 100, 102, 98, 100, 101, 99, 100, 101, 100)
    config = DemandRegimeDetectorConfigV1(target_min_regime_minutes=60)

    plan = detect_demand_regimes_v1(_profile(values), config).plans[0]

    assert plan.natural_max_regimes == len(values)
    assert plan.selected_regime_count == 1


def test_selected_count_never_exceeds_derived_natural_maximum() -> None:
    plan = _only_plan((30, 30, 150, 150, 40, 40, 180, 180, 50, 50))

    assert plan.selected_regime_count <= plan.natural_max_regimes
    assert plan.natural_max_regimes == 5


def test_per_count_diagnostics_use_one_penalty_per_internal_boundary() -> None:
    config = DemandRegimeDetectorConfigV1(
        target_min_regime_minutes=60,
        complexity_penalty=0.125,
    )
    plan = detect_demand_regimes_v1(_profile((20, 20, 200, 200)), config).plans[0]

    for diagnostic in plan.regime_count_objectives:
        assert diagnostic.boundary_penalty_total == pytest.approx(
            0.125 * (diagnostic.regime_count - 1)
        )
        assert diagnostic.total_objective == pytest.approx(
            diagnostic.fit_error + diagnostic.boundary_penalty_total
        )


def test_internal_boundaries_are_on_the_canonical_bucket_grid() -> None:
    profile = _profile((80, 80, 80, 180, 180, 180), bucket_minutes=30)
    plan = detect_demand_regimes_v1(profile).plans[0]
    canonical = {item.interval_start for item in profile.derived_observations}

    assert plan.minimum_regime_bucket_count == 3
    assert all(item.start_time in canonical for item in plan.regimes[1:])


def test_partial_final_bucket_is_covered_without_a_tiny_tail_regime() -> None:
    profile = _profile((80, 80, 80, 80, 80, 200), bucket_minutes=30)
    observations = profile.derived_observations
    partial = DemandProfileV1(
        profile_id=profile.profile_id,
        included_period_ids=profile.included_period_ids,
        aggregation_method=profile.aggregation_method,
        period_weight_method=profile.period_weight_method,
        total_observation_days=profile.total_observation_days,
        direction_grain=profile.direction_grain,
        derived_observations=(
            *observations[:-1],
            DerivedDemandObservationV1(
                direction=observations[-1].direction,
                interval_start=observations[-1].interval_start,
                interval_end=observations[-1].interval_start + 15 * 60,
                average_daily_passengers=observations[-1].average_daily_passengers,
            ),
        ),
        source_period_fingerprints=profile.source_period_fingerprints,
        limitations=profile.limitations,
        profile_fingerprint=profile.profile_fingerprint,
    )

    result = detect_demand_regimes_v1(partial)

    assert result.status == DemandRegimeDetectionStatusV1.SUCCESS
    assert len(result.plans[0].regimes) == 1
    assert result.plans[0].natural_max_regimes == 1
    assert result.plans[0].service_end == observations[-1].interval_start + 15 * 60


def test_combined_demand_creates_shared_route_level_regimes() -> None:
    result = detect_demand_regimes_v1(_profile((80, 80, 180, 180)))

    assert result.scope == DemandRegimeScopeV1.SHARED_ROUTE_LEVEL_REGIMES
    assert [item.direction for item in result.plans] == [ContractDirection.COMBINED]


def test_directional_demand_runs_independently() -> None:
    outbound = _profile(
        (80, 80, 180, 180),
        direction=ContractDirection.OUTBOUND,
    )
    inbound_observations = tuple(
        DerivedDemandObservationV1(
            direction=ContractDirection.INBOUND,
            interval_start=item.interval_start,
            interval_end=item.interval_end,
            average_daily_passengers=value,
        )
        for item, value in zip(
            outbound.derived_observations,
            (180, 180, 80, 80),
            strict=True,
        )
    )
    directional = DemandProfileV1(
        profile_id=outbound.profile_id,
        included_period_ids=outbound.included_period_ids,
        aggregation_method=outbound.aggregation_method,
        period_weight_method=outbound.period_weight_method,
        total_observation_days=outbound.total_observation_days,
        direction_grain=DemandDirectionGrainV1.DIRECTIONAL,
        derived_observations=(*outbound.derived_observations, *inbound_observations),
        source_period_fingerprints=outbound.source_period_fingerprints,
        limitations=outbound.limitations,
        profile_fingerprint=outbound.profile_fingerprint,
    )

    result = detect_demand_regimes_v1(directional)

    assert result.scope == DemandRegimeScopeV1.DIRECTION_SPECIFIC_REGIMES
    assert [item.direction for item in result.plans] == [
        ContractDirection.OUTBOUND,
        ContractDirection.INBOUND,
    ]
    assert all(len(item.regimes) == 2 for item in result.plans)


def test_scenario_b_counts_use_half_open_regimes_and_reconcile_service_window() -> None:
    starts = (7 * 3600, 10 * 3600)
    profile = _profile((20, 200), bucket_minutes=180, starts=starts)
    scenario_b = SimpleNamespace(
        exact_timetable=tuple(
            SimpleNamespace(direction=ContractDirection.OUTBOUND, departure_time=value)
            for value in (
                7 * 3600,
                8 * 3600 + 22 * 60,
                10 * 3600,
                12 * 3600,
                13 * 3600,
            )
        )
    )
    config = DemandRegimeDetectorConfigV1(
        target_min_regime_minutes=90,
        complexity_penalty=0.001,
    )

    plan = detect_demand_regimes_v1(profile, config, scenario_b=scenario_b).plans[0]

    assert [item.current_b_trip_count for item in plan.regimes] == [2, 2]
    assert plan.current_b_regime_trip_count == 4
    assert plan.current_b_service_window_trip_count == 4
    assert plan.current_b_service_window_reconciled is True
    assert plan.current_b_exact_timetable_trip_count == 5
    assert plan.current_b_outside_service_window_trip_count == 1
