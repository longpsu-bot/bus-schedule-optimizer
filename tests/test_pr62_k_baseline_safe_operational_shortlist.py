from __future__ import annotations

import importlib
from datetime import date, timedelta

import pytest

from bus_schedule_engine.contracts_v1.demand_regimes import DailyDemandObservationV1
from bus_schedule_engine.contracts_v1.models import ContractDirection


def _runner():
    return importlib.import_module("scripts.run_pr62_k_baseline_safe_operational_shortlist")


def _passenger_metrics(*, wait: float = 5.0, mismatch: float = 0.1, maximum: float = 10.0):
    return {
        "mean_daily_wait_minutes": wait,
        "mean_daily_mismatch": mismatch,
        "maximum_bucket_expected_wait_minutes": maximum,
    }


def _candidate(
    fingerprint: str,
    *,
    sustained: int,
    regimes: int,
    fleet: int,
    excess: int,
    maximum: float,
    selection_eligible: bool = True,
):
    return {
        "fingerprint": fingerprint,
        "selection_eligible": selection_eligible,
        "baseline_safe_passenger_service": True,
        "secondary_metrics": {
            "sustained_headway_level_count": sustained,
            "service_regime_count": regimes,
            "fleet_required": fleet,
            "total_excess_terminal_wait": excess,
            "maximum_bucket_expected_wait_minutes": maximum,
        },
    }


def test_exact_scenario_b_daily_evaluation_uses_authoritative_departures() -> None:
    runner = _runner()
    observed_date = date(2026, 3, 1)
    observations = tuple(
        DailyDemandObservationV1(
            observation_date=observed_date,
            direction=direction,
            interval_start=start,
            interval_end=end,
            passenger_demand=demand,
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
        for start, end, demand in ((0, 600, 1.0), (600, 1800, 3.0))
    )
    index = runner.pr62_j._observation_index(
        type("DailyRoute", (), {"daily_observations": observations})()
    )

    daily = runner._daily_pair_metrics_with_mass(
        outbound_departures=(0, 600, 1200),
        inbound_departures=(0, 600, 1200),
        observation_index=index,
        eligible_dates=(observed_date,),
    )

    assert daily[observed_date]["expected_wait_minutes"] == pytest.approx(5.0)
    assert daily[observed_date]["observed_demand_mismatch"] == pytest.approx(1.0 / 36.0)
    assert daily[observed_date]["active_passenger_mass"] == pytest.approx(5.0)


def test_strict_three_metric_baseline_safe_passes() -> None:
    runner = _runner()

    result = runner._baseline_safety(
        _passenger_metrics(wait=4.9, mismatch=0.09, maximum=9.9),
        _passenger_metrics(),
    )

    assert result == {
        "wait_non_regression": True,
        "mismatch_non_regression": True,
        "maximum_bucket_wait_non_regression": True,
        "baseline_safe_passenger_service": True,
    }


@pytest.mark.parametrize(
    ("regression", "failed_gate"),
    (
        ({"wait": 5.000001}, "wait_non_regression"),
        ({"mismatch": 0.100001}, "mismatch_non_regression"),
        ({"maximum": 10.000001}, "maximum_bucket_wait_non_regression"),
    ),
)
def test_baseline_safe_fails_when_any_passenger_metric_regresses(
    regression: dict[str, float], failed_gate: str
) -> None:
    runner = _runner()

    result = runner._baseline_safety(_passenger_metrics(**regression), _passenger_metrics())

    assert result[failed_gate] is False
    assert result["baseline_safe_passenger_service"] is False


def test_numerical_equality_passes_all_three_baseline_gates() -> None:
    runner = _runner()
    epsilon = runner.NUMERICAL_EPSILON

    result = runner._baseline_safety(
        _passenger_metrics(
            wait=5.0 + epsilon,
            mismatch=0.1 + epsilon,
            maximum=10.0 + epsilon,
        ),
        _passenger_metrics(),
    )

    assert result["baseline_safe_passenger_service"] is True


def test_operational_secondary_pareto_removes_dominated_candidate() -> None:
    runner = _runner()
    candidates = (
        _candidate("dominated", sustained=5, regimes=8, fleet=12, excess=100, maximum=20.0),
        _candidate("frontier", sustained=5, regimes=8, fleet=12, excess=100, maximum=19.0),
    )

    assert runner._operational_frontier_fingerprints(candidates) == ("frontier",)


def test_multiple_operational_tradeoffs_remain_unresolved() -> None:
    runner = _runner()
    candidates = (
        _candidate("simpler", sustained=4, regimes=7, fleet=12, excess=100, maximum=20.0),
        _candidate("access", sustained=5, regimes=7, fleet=12, excess=100, maximum=15.0),
    )

    frontier = runner._operational_frontier_fingerprints(candidates)

    assert frontier == ("access", "simpler")
    assert runner._route_classification(len(candidates), len(frontier)) == (
        "MULTIPLE_BASELINE_SAFE_OPERATING_TRADEOFFS"
    )


def test_human_final_benchmark_never_enters_selectable_engine_set() -> None:
    runner = _runner()
    candidates = (
        _candidate("engine", sustained=5, regimes=8, fleet=12, excess=100, maximum=19.0),
        _candidate(
            "HUMAN_FINAL",
            sustained=4,
            regimes=7,
            fleet=11,
            excess=90,
            maximum=18.0,
            selection_eligible=False,
        ),
    )

    assert runner._baseline_safe_engine_fingerprints(candidates) == ("engine",)


def test_daily_robustness_and_passenger_hours_use_each_dates_mass() -> None:
    runner = _runner()
    first = date(2026, 3, 1)
    second = first + timedelta(days=1)
    baseline = {
        first: {
            "expected_wait_minutes": 10.0,
            "observed_demand_mismatch": 0.2,
            "active_passenger_mass": 100.0,
        },
        second: {
            "expected_wait_minutes": 10.0,
            "observed_demand_mismatch": 0.2,
            "active_passenger_mass": 10.0,
        },
    }
    candidate = {
        first: {
            "expected_wait_minutes": 8.0,
            "observed_demand_mismatch": 0.1,
            "active_passenger_mass": 100.0,
        },
        second: {
            "expected_wait_minutes": 11.0,
            "observed_demand_mismatch": 0.2,
            "active_passenger_mass": 10.0,
        },
    }

    summary = runner._daily_comparison(candidate, baseline, expected_dates=(first, second))

    assert summary["wait_candidate_better_percentage"] == 50.0
    assert summary["wait_equal_percentage"] == 0.0
    assert summary["wait_candidate_worse_percentage"] == 50.0
    assert summary["mismatch_candidate_better_percentage"] == 50.0
    assert summary["mismatch_equal_percentage"] == 50.0
    assert summary["mismatch_candidate_worse_percentage"] == 0.0
    assert summary["passenger_wait_minutes_saved_per_average_day"] == pytest.approx(95.0)
    assert summary["passenger_wait_hours_saved_per_average_day"] == pytest.approx(95.0 / 60.0)


@pytest.mark.parametrize(
    ("routes", "expected"),
    (
        (
            {
                "6": {"I_pareto_size": 47, "BASELINE_SAFE_SET_size": 0, "BASELINE_SAFE_OPERATIONAL_FRONTIER_size": 0},
                "10": {"I_pareto_size": 11, "BASELINE_SAFE_SET_size": 2, "BASELINE_SAFE_OPERATIONAL_FRONTIER_size": 1},
            },
            "BASELINE_SAFE_POLICY_TOO_RESTRICTIVE",
        ),
        (
            {
                "6": {"I_pareto_size": 47, "BASELINE_SAFE_SET_size": 5, "BASELINE_SAFE_OPERATIONAL_FRONTIER_size": 2},
                "10": {"I_pareto_size": 11, "BASELINE_SAFE_SET_size": 2, "BASELINE_SAFE_OPERATIONAL_FRONTIER_size": 1},
            },
            "BASELINE_SAFE_POLICY_PROMISING",
        ),
        (
            {
                "6": {"I_pareto_size": 47, "BASELINE_SAFE_SET_size": 47, "BASELINE_SAFE_OPERATIONAL_FRONTIER_size": 47},
                "10": {"I_pareto_size": 11, "BASELINE_SAFE_SET_size": 11, "BASELINE_SAFE_OPERATIONAL_FRONTIER_size": 11},
            },
            "BASELINE_SAFE_POLICY_INCONCLUSIVE",
        ),
    ),
)
def test_cross_route_policy_classification(
    routes: dict[str, dict[str, int]], expected: str
) -> None:
    runner = _runner()

    assert runner._cross_route_classification(routes) == expected


def test_daily_vector_fingerprint_is_independent_of_mapping_order() -> None:
    runner = _runner()
    first = date(2026, 3, 1)
    second = first + timedelta(days=1)
    forward = {first: 1.0, second: 2.0}
    reverse = dict(reversed(tuple(forward.items())))

    assert runner._daily_vector_fingerprint(forward) == runner._daily_vector_fingerprint(reverse)


def test_headway_run_end_index_is_derived_from_start_and_gap_count() -> None:
    runner = _runner()
    run = runner.pr62_i.exact_headway_runs((0, 600, 1200))[0]

    assert runner._headway_run_record(run) == {
        "headway_minutes": 10,
        "gap_count": 2,
        "start_departure_index": 0,
        "end_departure_index": 2,
    }
