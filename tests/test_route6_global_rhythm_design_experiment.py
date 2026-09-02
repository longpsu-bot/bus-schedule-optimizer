from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from bus_schedule_engine.clean_boundary_pilot import build_minimum_fleet_plan_v1
from bus_schedule_engine.service_plan_coordinator import DemandBucketEvidenceV1


def _load_module():
    scripts = Path(__file__).parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    path = scripts / "route6_global_rhythm_design_experiment.py"
    spec = importlib.util.spec_from_file_location("route6_global_rhythm_design_experiment", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


experiment = _load_module()


def _synthetic_buckets() -> tuple[DemandBucketEvidenceV1, ...]:
    return tuple(
        DemandBucketEvidenceV1("outbound", start * 60, (start + 30) * 60, 1.0)
        for start in range(0, 990, 30)
    )


def test_exact_arithmetic_enumeration_discovers_clean_oracles() -> None:
    sequences = experiment.enumerate_exact_clean_sequences_up_to_three_regimes()
    histograms = []
    for sequence in sequences:
        histogram = {}
        for regime in sequence:
            histogram[regime.headway_minutes] = (
                histogram.get(regime.headway_minutes, 0) + regime.gap_count
            )
        histograms.append(histogram)
        assert all(regime.gap_count >= 2 for regime in sequence)
        assert sum(regime.gap_count for regime in sequence) == 77
        assert sum(regime.headway_minutes * regime.gap_count for regime in sequence) == 965
    assert {10: 38, 15: 39} in histograms
    assert {8: 25, 10: 3, 15: 49} in histograms


def test_bounded_dp_is_deterministic_and_preserves_exact_endpoints() -> None:
    settings = experiment.SearchSettings("TEST", 4, 8, 8)
    first, _, first_oracles = experiment.run_directional_dp(
        direction="outbound",
        demand_buckets=_synthetic_buckets(),
        settings=settings,
        fixed_first_departure=0,
        total_gaps=12,
        operating_span_minutes=150,
    )
    second, _, second_oracles = experiment.run_directional_dp(
        direction="outbound",
        demand_buckets=_synthetic_buckets(),
        settings=settings,
        fixed_first_departure=0,
        total_gaps=12,
        operating_span_minutes=150,
    )
    assert first_oracles == second_oracles
    assert [item.fingerprint for item in first] == [item.fingerprint for item in second]
    assert all(regime.gap_count >= 2 for item in first for regime in item.regimes)
    assert all(item.departure_offsets_minutes[-1] == 150 for item in first)
    assert all(len(item.departure_offsets_minutes) == 13 for item in first)


def test_exact_expected_wait_matches_analytic_result() -> None:
    bucket = DemandBucketEvidenceV1("outbound", 0, 30 * 60, 30.0)
    result = experiment.expected_passenger_wait_metrics((0, 10 * 60, 30 * 60), (bucket,))
    assert result["demand_weighted_expected_passenger_wait_minutes"] == pytest.approx(500 / 60)
    assert result["maximum_bucket_expected_wait_minutes"] == pytest.approx(500 / 60)


def test_exact_wait_distinguishes_equal_bucket_counts_with_different_timing() -> None:
    bucket = DemandBucketEvidenceV1("outbound", 0, 30 * 60, 30.0)
    early = (0, 5 * 60, 30 * 60)
    balanced = (0, 15 * 60, 30 * 60)
    assert experiment._bucket_counts(early, (bucket,)) == experiment._bucket_counts(
        balanced, (bucket,)
    )
    early_wait = experiment.expected_passenger_wait_metrics(early, (bucket,))[
        "demand_weighted_expected_passenger_wait_minutes"
    ]
    balanced_wait = experiment.expected_passenger_wait_metrics(balanced, (bucket,))[
        "demand_weighted_expected_passenger_wait_minutes"
    ]
    assert early_wait != balanced_wait


def test_fleet_validation_consumes_completed_exact_candidates() -> None:
    label = experiment._initial_label()
    label = experiment._new_label(label, headway_minutes=10, gap_count=2)
    departures = tuple(offset * 60 for offset in label.departure_offsets_minutes)
    assert len(departures) == 3
    plan = build_minimum_fleet_plan_v1(
        route_id="synthetic",
        outbound_candidate_id="out",
        inbound_candidate_id="in",
        outbound_departures=departures,
        inbound_departures=departures,
        runtime_minutes=1,
        minimum_layover_minutes=1,
    )
    assert len(plan.assignments) == 6


def test_equal_operational_vectors_are_not_dominance() -> None:
    vector = (1.0,) * len(experiment.PAIR_OBJECTIVES)
    assert not experiment._dominates(vector, vector)
