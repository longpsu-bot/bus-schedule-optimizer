from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from bus_schedule_engine.contracts_v1.demand_regimes import (
    DailyDemandObservationV1,
    DemandRegimeDetectorConfigV1,
    RegimeModelSelectionStatusV1,
    demand_regime_model_selection_to_dict_v1,
    select_demand_regime_model_v1,
)
from bus_schedule_engine.contracts_v1.models import ContractDirection
from bus_schedule_engine.contracts_v1.multi_period_demand import (
    DemandDirectionGrainV1,
    DemandProfileAggregationMethodV1,
    DemandProfileV1,
    DerivedDemandObservationV1,
)


def _case(
    days: tuple[tuple[float, ...], ...],
    *,
    bucket_minutes: int = 60,
) -> tuple[DemandProfileV1, tuple[DailyDemandObservationV1, ...]]:
    bucket_count = len(days[0])
    assert all(len(item) == bucket_count for item in days)
    starts = tuple((5 * 60 + index * bucket_minutes) * 60 for index in range(bucket_count))
    aggregate = tuple(sum(day[index] for day in days) / len(days) for index in range(bucket_count))
    profile = DemandProfileV1(
        profile_id="daily-test-profile",
        included_period_ids=("daily-test-period",),
        aggregation_method=DemandProfileAggregationMethodV1.SINGLE_PERIOD,
        period_weight_method="observation_days",
        total_observation_days=len(days),
        direction_grain=DemandDirectionGrainV1.COMBINED,
        derived_observations=tuple(
            DerivedDemandObservationV1(
                direction=ContractDirection.COMBINED,
                interval_start=start,
                interval_end=start + bucket_minutes * 60,
                average_daily_passengers=value,
            )
            for start, value in zip(starts, aggregate, strict=True)
        ),
        source_period_fingerprints=(("daily-test-period", "abc"),),
        limitations=(),
        profile_fingerprint="daily-profile-fingerprint",
    )
    observations = tuple(
        DailyDemandObservationV1(
            observation_date=date(2026, 1, 1) + timedelta(days=day_index),
            direction=ContractDirection.COMBINED,
            interval_start=start,
            interval_end=start + bucket_minutes * 60,
            passenger_demand=value,
        )
        for day_index, day in enumerate(days)
        for start, value in zip(starts, day, strict=True)
    )
    return profile, observations


def _selection(
    days: tuple[tuple[float, ...], ...],
    *,
    target_min_regime_minutes: int = 60,
    complexity_penalty: float = 0.05,
):
    profile, observations = _case(days)
    result = select_demand_regime_model_v1(
        profile,
        observations,
        DemandRegimeDetectorConfigV1(
            target_min_regime_minutes=target_min_regime_minutes,
            complexity_penalty=complexity_penalty,
        ),
    )
    assert result.status == RegimeModelSelectionStatusV1.SUCCESS
    return result.selections[0]


def test_stable_three_regime_signal_selects_three_with_stable_boundaries() -> None:
    days = tuple(
        tuple(value + (day_index % 3 - 1) for value in (30, 30, 30, 150, 150, 150, 40, 40, 40))
        for day_index in range(12)
    )

    selection = _selection(days)

    assert selection.selected_regime_count == 3
    assert selection.final_boundaries == (8 * 3600, 11 * 3600)
    final_stability = [item for item in selection.boundary_stability if item.is_final_boundary]
    assert [item.exact_boundary_frequency for item in final_stability] == [1.0, 1.0]


def test_flat_repeated_demand_selects_one_despite_larger_frontier() -> None:
    days = tuple(tuple([100.0 + day_index] * 10) for day_index in range(10))

    selection = _selection(days)

    assert selection.natural_max_regimes == 10
    assert selection.selected_regime_count == 1
    assert all(item.within_one_se for item in selection.model_scores)


def test_one_se_rule_rejects_nonpersistent_local_overfit() -> None:
    spike_positions = (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    days = tuple(
        tuple(135.0 if index == spike else 100.0 for index in range(12))
        for spike in spike_positions
    )

    selection = _selection(days)

    assert selection.candidate_frontier.candidates[-1].fit_error < (
        selection.candidate_frontier.candidates[0].fit_error
    )
    assert selection.selected_regime_count == 1
    assert selection.best_validation_regime_count >= 1


def test_persistent_fine_structure_can_select_more_than_six_regimes() -> None:
    signal = tuple(
        value
        for plateau in range(8)
        for value in ((20.0, 20.0) if plateau % 2 == 0 else (200.0, 200.0))
    )

    selection = _selection(tuple(signal for _ in range(10)), target_min_regime_minutes=120)

    assert selection.natural_max_regimes == 8
    assert selection.best_validation_regime_count == 8
    assert selection.selected_regime_count == 8


def test_identical_repeated_days_have_zero_se_without_division_errors() -> None:
    signal = (20.0, 20.0, 100.0, 100.0, 30.0, 30.0)

    selection = _selection(tuple(signal for _ in range(7)))

    assert selection.selected_regime_count == 3
    assert all(
        item.validation_standard_error == pytest.approx(0.0) for item in selection.model_scores
    )


def test_missing_daily_bucket_excludes_day_and_never_imputes_zero() -> None:
    days = tuple((20.0, 20.0, 100.0, 100.0) for _ in range(8))
    profile, observations = _case(days)
    missing_date = date(2026, 1, 3)
    observations = tuple(
        item
        for item in observations
        if not (item.observation_date == missing_date and item.interval_start == 6 * 3600)
    )

    result = select_demand_regime_model_v1(profile, observations)
    selection = result.selections[0]

    assert result.status == RegimeModelSelectionStatusV1.SUCCESS
    assert selection.total_observed_days == 8
    assert selection.eligible_validation_days == 7
    assert len(selection.excluded_days) == 1
    assert selection.excluded_days[0].reason_code == "DAILY_DEMAND_COVERAGE_INCOMPLETE"
    assert selection.excluded_days[0].missing_intervals == ((6 * 3600, 7 * 3600),)


def test_insufficient_repeated_observations_returns_structured_status_and_frontier() -> None:
    profile, observations = _case(tuple((20.0, 20.0, 100.0, 100.0) for _ in range(6)))

    result = select_demand_regime_model_v1(profile, observations)
    selection = result.selections[0]

    assert result.status == (RegimeModelSelectionStatusV1.INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS)
    assert selection.selected_regime_count is None
    assert selection.final_plan is None
    assert len(selection.candidate_frontier.candidates) == 2
    assert selection.failure_code == "INSUFFICIENT_REPEATED_DEMAND_OBSERVATIONS"


def test_complete_model_selection_is_byte_identical_across_100_runs() -> None:
    days = tuple(
        tuple(value + (day_index % 3 - 1) for value in (30, 30, 150, 150, 40, 40))
        for day_index in range(9)
    )
    profile, observations = _case(days)

    serialized = {
        json.dumps(
            demand_regime_model_selection_to_dict_v1(
                select_demand_regime_model_v1(profile, observations)
            ),
            sort_keys=True,
            separators=(",", ":"),
        )
        for _ in range(100)
    }

    assert len(serialized) == 1


def test_complexity_penalty_has_no_authority_when_cv_is_available() -> None:
    days = tuple(
        tuple(value + (day_index % 3 - 1) for value in (30, 30, 150, 150, 40, 40))
        for day_index in range(9)
    )

    low_penalty = _selection(days, complexity_penalty=0.001)
    high_penalty = _selection(days, complexity_penalty=0.5)

    assert (
        low_penalty.legacy_penalty_selected_regime_count
        != high_penalty.legacy_penalty_selected_regime_count
    )
    assert low_penalty.selected_regime_count == high_penalty.selected_regime_count
    assert low_penalty.final_boundaries == high_penalty.final_boundaries
