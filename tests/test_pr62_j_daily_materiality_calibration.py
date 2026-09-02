from __future__ import annotations

import importlib
import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from bus_schedule_engine.contracts_v1.demand_regimes import DailyDemandObservationV1
from bus_schedule_engine.contracts_v1.models import ContractDirection


def _runner():
    return importlib.import_module("scripts.run_pr62_j_daily_materiality_calibration")


def _dated(values: tuple[float, ...]) -> dict[date, float]:
    first = date(2026, 3, 1)
    return {first + timedelta(days=index): value for index, value in enumerate(values)}


def test_paired_one_se_uses_sample_sd_and_same_date_differences() -> None:
    runner = _runner()
    reference = _dated((10.0, 20.0, 30.0))
    candidate = _dated((8.0, 20.0, 32.0))

    summary = runner._paired_one_se(candidate, reference, expected_dates=tuple(reference))

    assert summary["mean_delta"] == pytest.approx(0.0)
    assert summary["sample_standard_deviation"] == pytest.approx(2.0)
    assert summary["standard_error"] == pytest.approx(2.0 / math.sqrt(3))
    assert summary["paired_date_count"] == 3
    assert summary["passes_one_se"] is True


def test_paired_one_se_known_positive_mean_fails() -> None:
    runner = _runner()
    reference = _dated((10.0, 20.0, 30.0))
    candidate = _dated((11.0, 22.0, 33.0))

    summary = runner._paired_one_se(candidate, reference, expected_dates=tuple(reference))

    assert summary["mean_delta"] == pytest.approx(2.0)
    assert summary["sample_standard_deviation"] == pytest.approx(1.0)
    assert summary["standard_error"] == pytest.approx(1.0 / math.sqrt(3))
    assert summary["passes_one_se"] is False


@pytest.mark.parametrize(
    ("delta", "expected_pass"),
    ((0.5, False), (1e-13, False), (0.0, True)),
)
def test_zero_variance_has_zero_se_and_only_nonpositive_mean_passes(
    delta: float,
    expected_pass: bool,
) -> None:
    runner = _runner()
    reference = _dated((10.0, 20.0, 30.0))
    candidate = {key: value + delta for key, value in reference.items()}

    summary = runner._paired_one_se(candidate, reference, expected_dates=tuple(reference))

    assert summary["sample_standard_deviation"] == 0.0
    assert summary["standard_error"] == 0.0
    assert summary["passes_one_se"] is expected_pass


def test_paired_one_se_fails_closed_when_candidate_dates_do_not_match_authority() -> None:
    runner = _runner()
    reference = _dated((10.0, 20.0, 30.0))
    candidate = dict(reference)
    candidate.pop(max(candidate))

    with pytest.raises(ValueError, match="paired date set"):
        runner._paired_one_se(candidate, reference, expected_dates=tuple(reference))


def test_joint_passenger_envelope_requires_both_metric_tests() -> None:
    runner = _runner()
    candidates = (
        {"fingerprint": "both", "wait_one_se": True, "mismatch_one_se": True},
        {"fingerprint": "wait-only", "wait_one_se": True, "mismatch_one_se": False},
        {"fingerprint": "mismatch-only", "wait_one_se": False, "mismatch_one_se": True},
    )

    assert runner._passenger_equivalent_fingerprints(candidates) == ("both",)


def test_secondary_pareto_removes_candidate_dominated_without_weights() -> None:
    runner = _runner()
    candidates = (
        {
            "fingerprint": "a",
            "secondary_metrics": {
                "maximum_bucket_expected_wait_minutes": 20.0,
                "sustained_headway_level_count": 5,
                "service_regime_count": 8,
                "fleet_required": 12,
                "total_excess_terminal_wait": 100,
            },
        },
        {
            "fingerprint": "b",
            "secondary_metrics": {
                "maximum_bucket_expected_wait_minutes": 19.0,
                "sustained_headway_level_count": 5,
                "service_regime_count": 8,
                "fleet_required": 12,
                "total_excess_terminal_wait": 100,
            },
        },
    )

    assert runner._secondary_operating_frontier_fingerprints(candidates) == ("b",)


def test_secondary_pareto_keeps_multiple_access_palette_tradeoffs() -> None:
    runner = _runner()
    candidates = (
        {
            "fingerprint": "a",
            "secondary_metrics": {
                "maximum_bucket_expected_wait_minutes": 15.0,
                "sustained_headway_level_count": 6,
                "service_regime_count": 8,
                "fleet_required": 12,
                "total_excess_terminal_wait": 100,
            },
        },
        {
            "fingerprint": "b",
            "secondary_metrics": {
                "maximum_bucket_expected_wait_minutes": 20.0,
                "sustained_headway_level_count": 5,
                "service_regime_count": 8,
                "fleet_required": 12,
                "total_excess_terminal_wait": 100,
            },
        },
    )

    assert runner._secondary_operating_frontier_fingerprints(candidates) == ("a", "b")


def test_metric_reference_uses_minimum_mean_then_fingerprint() -> None:
    runner = _runner()
    candidates = (
        {"fingerprint": "b", "daily_wait": _dated((4.0, 6.0))},
        {"fingerprint": "a", "daily_wait": _dated((5.0, 5.0))},
        {"fingerprint": "worse", "daily_wait": _dated((6.0, 6.0))},
    )

    assert runner._metric_reference_fingerprint(candidates, "daily_wait") == "a"


def test_daily_direction_metrics_reuse_exact_wait_and_production_mismatch() -> None:
    runner = _runner()
    observed_date = date(2026, 3, 1)
    observations = (
        DailyDemandObservationV1(
            observation_date=observed_date,
            direction=ContractDirection.OUTBOUND,
            interval_start=0,
            interval_end=600,
            passenger_demand=1.0,
        ),
        DailyDemandObservationV1(
            observation_date=observed_date,
            direction=ContractDirection.OUTBOUND,
            interval_start=600,
            interval_end=1800,
            passenger_demand=3.0,
        ),
    )

    metrics = runner._daily_direction_metrics((0, 600, 1200), observations)

    assert metrics["expected_wait_minutes"] == pytest.approx(5.0)
    assert metrics["active_demand_mass"] == pytest.approx(2.5)
    assert metrics["observed_demand_mismatch"] == pytest.approx(1.0 / 72.0)


@pytest.mark.parametrize(
    ("passenger_size", "secondary_size", "expected"),
    (
        (0, 0, "NO_JOINT_ONE_SE_PASSENGER_EQUIVALENT_SET"),
        (1, 1, "UNIQUE_PASSENGER_EQUIVALENT_CANDIDATE"),
        (2, 1, "UNIQUE_MATERIALITY_OPERATING_CANDIDATE"),
        (2, 2, "MULTIPLE_MATERIALITY_EQUIVALENT_TRADEOFFS"),
    ),
)
def test_route_classification_obeys_non_arbitrary_selection_rules(
    passenger_size: int,
    secondary_size: int,
    expected: str,
) -> None:
    runner = _runner()

    assert runner._route_classification(passenger_size, secondary_size) == expected


@pytest.mark.parametrize(
    ("route_classes", "expected"),
    (
        (
            (
                "UNIQUE_PASSENGER_EQUIVALENT_CANDIDATE",
                "UNIQUE_MATERIALITY_OPERATING_CANDIDATE",
            ),
            "MATERIALITY_RULE_SUPPORTED_FOR_PRODUCTION",
        ),
        (
            (
                "UNIQUE_PASSENGER_EQUIVALENT_CANDIDATE",
                "MULTIPLE_MATERIALITY_EQUIVALENT_TRADEOFFS",
            ),
            "MATERIALITY_RULE_NEEDS_DOMAIN_TIEBREAK",
        ),
        (
            (
                "UNIQUE_PASSENGER_EQUIVALENT_CANDIDATE",
                "NO_JOINT_ONE_SE_PASSENGER_EQUIVALENT_SET",
            ),
            "MATERIALITY_RULE_NOT_SUPPORTED",
        ),
    ),
)
def test_cross_route_classification_requires_coherent_pilot_behavior(
    route_classes: tuple[str, str],
    expected: str,
) -> None:
    runner = _runner()

    assert runner._cross_route_classification(route_classes) == expected


def test_production_statement_render_is_independent_of_mapping_insertion_order() -> None:
    runner = _runner()
    forward = {
        "Coordinator search changed": "NO",
        "10-D Pareto changed": "NO",
        "Compiler changed": "NO",
    }
    reversed_order = dict(reversed(tuple(forward.items())))

    assert runner._production_change_lines(forward) == runner._production_change_lines(
        reversed_order
    )


def test_empty_fingerprint_set_renders_explicitly_without_trailing_space() -> None:
    runner = _runner()

    assert runner._fingerprint_set_line("PASSENGER_EQUIVALENT_SET", ()) == (
        "PASSENGER_EQUIVALENT_SET: `none`"
    )


def test_evidence_markdown_renderer_has_clean_line_endings() -> None:
    runner = _runner()
    repo_root = Path(__file__).resolve().parents[1]
    payload = json.loads((repo_root / runner.OUTPUT_JSON).read_text(encoding="utf-8"))

    rendered = runner._markdown(payload)

    assert not rendered.endswith("\n")
    assert all(line.rstrip() == line for line in rendered.splitlines())
