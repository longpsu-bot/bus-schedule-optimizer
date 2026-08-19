from dataclasses import replace
from datetime import date

import pytest

from bus_schedule_engine.contracts_v1 import (
    ContractDirection,
    DemandObservationPeriodV1,
    DemandPeriodObservationV1,
    DemandProfileAggregationMethodV1,
    DemandProfileConfigV1,
    MultiPeriodDemandError,
    MultiPeriodDemandInputV1,
    VolumeClassification,
    derive_demand_profile_v1,
)


def _observation(
    start: int,
    passengers: float,
    *,
    direction: ContractDirection = ContractDirection.OUTBOUND,
    volume: VolumeClassification = VolumeClassification.AVERAGE_DAY,
) -> DemandPeriodObservationV1:
    return DemandPeriodObservationV1(
        interval_start=start,
        interval_end=start + 1800,
        direction=direction,
        passenger_volume=passengers,
        volume_classification=volume,
        source_time_basis="actual_departure_time",
        source_dataset_id="placeholder",
    )


def _period(
    period_id: str,
    days: int,
    values: tuple[float, float] = (10.0, 20.0),
    *,
    status: str = "READY",
    volume: VolumeClassification = VolumeClassification.AVERAGE_DAY,
    direction: ContractDirection = ContractDirection.OUTBOUND,
) -> DemandObservationPeriodV1:
    dataset = f"dataset-{period_id}"
    observations = tuple(
        replace(
            _observation(6 * 3600 + index * 1800, value, direction=direction, volume=volume),
            source_dataset_id=dataset,
        )
        for index, value in enumerate(values)
    )
    return DemandObservationPeriodV1(
        period_id=period_id,
        period_start=date(2026, 3 if period_id == "p1" else 4, 1),
        period_end=date(2026, 3 if period_id == "p1" else 4, days),
        observation_days=days,
        observations=observations,
        source_dataset_id=dataset,
        period_role="CURRENT_TIMETABLE_EVIDENCE",
        status=status,
    )


def _profile(
    profile_id: str = "stable",
    periods: tuple[str, ...] = ("p1", "p2"),
    method: DemandProfileAggregationMethodV1 = (DemandProfileAggregationMethodV1.DAY_WEIGHTED_MEAN),
) -> DemandProfileConfigV1:
    return DemandProfileConfigV1(
        profile_id=profile_id,
        included_period_ids=periods,
        aggregation_method=method,
        period_weight="observation_days",
        authority_role="PRIMARY",
        status="READY",
        description="test profile",
    )


def _input(*, periods=None, profiles=None) -> MultiPeriodDemandInputV1:
    effective_profiles = profiles or (_profile(),)
    return MultiPeriodDemandInputV1(
        demand_dataset_id="multi",
        periods=periods or (_period("p1", 10), _period("p2", 20, (40.0, 50.0))),
        profiles=effective_profiles,
        default_profile_id=effective_profiles[0].profile_id,
    )


def test_repeated_blocks_across_periods_are_valid_and_day_weighted() -> None:
    result = derive_demand_profile_v1(_input(), "stable")

    assert result.profile.total_observation_days == 30
    assert [item.average_daily_passengers for item in result.profile.derived_observations] == [
        30.0,
        40.0,
    ]
    assert all(fingerprint for _, fingerprint in result.profile.source_period_fingerprints)


def test_single_period_exactly_reproduces_average_day_values() -> None:
    demand_input = _input(
        profiles=(
            _profile(
                "current",
                ("p2",),
                DemandProfileAggregationMethodV1.SINGLE_PERIOD,
            ),
        )
    )

    result = derive_demand_profile_v1(demand_input, "current")

    assert [item.average_daily_passengers for item in result.profile.derived_observations] == [
        40.0,
        50.0,
    ]


def test_total_period_volume_is_normalized_before_combination() -> None:
    periods = (
        _period(
            "p1",
            10,
            (100.0, 200.0),
            volume=VolumeClassification.TOTAL_OBSERVATION_PERIOD,
        ),
        _period("p2", 20, (40.0, 50.0)),
    )

    result = derive_demand_profile_v1(_input(periods=periods), "stable")

    assert [item.average_daily_passengers for item in result.profile.derived_observations] == [
        30.0,
        40.0,
    ]


@pytest.mark.parametrize(
    ("demand_input", "code"),
    [
        (
            _input(periods=(_period("p1", 10), _period("p1", 10))),
            "DUPLICATE_PERIOD_ID",
        ),
        (
            _input(profiles=(_profile(periods=("p1", "missing")),)),
            "PROFILE_REFERENCES_UNKNOWN_PERIOD",
        ),
        (
            _input(periods=(_period("p1", 10, status="DRAFT"), _period("p2", 20))),
            "PERIOD_NOT_READY",
        ),
    ],
)
def test_fail_closed_period_and_profile_validation(demand_input, code: str) -> None:
    with pytest.raises(MultiPeriodDemandError) as exc_info:
        derive_demand_profile_v1(demand_input, "stable")

    assert exc_info.value.code == code


def test_overlap_inside_one_period_is_rejected() -> None:
    period = _period("p1", 10)
    overlapping = replace(
        period,
        observations=(
            period.observations[0],
            replace(period.observations[1], interval_start=6 * 3600 + 900),
        ),
    )
    demand_input = _input(
        periods=(overlapping,),
        profiles=(
            _profile(
                periods=("p1",),
                method=DemandProfileAggregationMethodV1.SINGLE_PERIOD,
            ),
        ),
    )

    with pytest.raises(MultiPeriodDemandError) as exc_info:
        derive_demand_profile_v1(demand_input, "stable")

    assert exc_info.value.code == "OVERLAPPING_DEMAND_INTERVALS"


def test_mixed_direction_grain_fails_closed() -> None:
    demand_input = _input(
        periods=(
            _period("p1", 10),
            _period("p2", 20, direction=ContractDirection.COMBINED),
        )
    )

    with pytest.raises(MultiPeriodDemandError) as exc_info:
        derive_demand_profile_v1(demand_input, "stable")

    assert exc_info.value.code == "MIXED_INCOMPATIBLE_DIRECTION_GRAINS"


def test_profile_fingerprint_changes_with_values_days_and_config() -> None:
    baseline = derive_demand_profile_v1(_input(), "stable").profile.profile_fingerprint
    changed_value = derive_demand_profile_v1(
        _input(periods=(_period("p1", 10, (11.0, 20.0)), _period("p2", 20, (40, 50)))),
        "stable",
    ).profile.profile_fingerprint
    changed_days = derive_demand_profile_v1(
        _input(periods=(_period("p1", 11), _period("p2", 20, (40, 50)))),
        "stable",
    ).profile.profile_fingerprint
    changed_config = derive_demand_profile_v1(
        _input(profiles=(replace(_profile(), description="changed"),)),
        "stable",
    ).profile.profile_fingerprint

    assert len({baseline, changed_value, changed_days, changed_config}) == 4


@pytest.mark.parametrize("days", [31.5, 0, -1, True, float("nan"), float("inf")])
def test_contract_rejects_non_integral_or_non_finite_observation_days(days: object) -> None:
    period = replace(_period("p1", 10), observation_days=days)

    with pytest.raises(MultiPeriodDemandError) as exc_info:
        derive_demand_profile_v1(
            _input(
                periods=(period,),
                profiles=(
                    _profile(
                        periods=("p1",),
                        method=DemandProfileAggregationMethodV1.SINGLE_PERIOD,
                    ),
                ),
            ),
            "stable",
        )

    assert exc_info.value.code == "OBSERVATION_DAYS_INVALID"


@pytest.mark.parametrize(
    "passengers",
    [-1, True, float("nan"), float("inf"), -float("inf")],
)
def test_contract_rejects_invalid_passenger_volume(passengers: object) -> None:
    period = _period("p1", 10)
    invalid = replace(
        period,
        observations=(
            replace(period.observations[0], passenger_volume=passengers),
            period.observations[1],
        ),
    )

    with pytest.raises(MultiPeriodDemandError) as exc_info:
        derive_demand_profile_v1(
            _input(
                periods=(invalid,),
                profiles=(
                    _profile(
                        periods=("p1",),
                        method=DemandProfileAggregationMethodV1.SINGLE_PERIOD,
                    ),
                ),
            ),
            "stable",
        )

    assert exc_info.value.code == "PASSENGER_VOLUME_INVALID"


@pytest.mark.parametrize("threshold", [True, float("nan"), float("inf"), -0.1, 1.1])
def test_shape_distance_threshold_must_be_finite_and_bounded(threshold: object) -> None:
    with pytest.raises(MultiPeriodDemandError) as exc_info:
        derive_demand_profile_v1(
            _input(),
            "stable",
            shape_distance_threshold=threshold,
        )

    assert exc_info.value.code == "SHAPE_DISTANCE_THRESHOLD_INVALID"


def test_zero_daily_passenger_shape_is_deterministic_and_finite() -> None:
    periods = (_period("p1", 10, (0.0, 0.0)), _period("p2", 20, (0.0, 0.0)))

    result = derive_demand_profile_v1(_input(periods=periods), "stable")

    for diagnostic in result.period_diagnostics:
        assert diagnostic.average_daily_passengers == 0
        assert diagnostic.peak_share == 0
        assert diagnostic.maximum_shape_distance == 0
        assert [share for _, _, share in diagnostic.normalized_block_shares] == [0, 0]
