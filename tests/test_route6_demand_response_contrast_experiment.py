from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_module():
    scripts = Path(__file__).parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    path = scripts / "route6_demand_response_contrast_experiment.py"
    spec = importlib.util.spec_from_file_location(
        "route6_demand_response_contrast_experiment", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


experiment = _load_module()


def _regime(regime_id: str, start: int, end: int, demand_rate: float) -> dict[str, object]:
    duration_minutes = (end - start) / 60
    return {
        "regime_id": regime_id,
        "direction": "outbound",
        "canonical_start": experiment._hhmm(start),
        "canonical_end": experiment._hhmm(end),
        "active_start": experiment._hhmm(start),
        "active_end": experiment._hhmm(end),
        "active_start_seconds": start,
        "active_end_seconds": end,
        "active_duration_minutes": duration_minutes,
        "integrated_immutable_demand_mass": demand_rate * duration_minutes / 60,
        "demand_rate_per_hour": demand_rate,
    }


def test_exact_service_frequency_projection_for_sustained_ten_minute_headway() -> None:
    departures = tuple(range(0, 3601, 10 * 60))
    assert experiment.effective_service_frequency_per_hour(
        departures, window_start=0, window_end=3600
    ) == pytest.approx(6.0)


def test_mixed_exact_interval_projection_is_time_weighted() -> None:
    assert experiment.effective_service_frequency_per_hour(
        (0, 10 * 60, 30 * 60), window_start=0, window_end=20 * 60
    ) == pytest.approx(4.5)


def test_demand_overlap_integration_is_proportional_and_deterministic() -> None:
    buckets = (
        {"start": 0, "end": 30 * 60, "observed_demand": 30.0},
        {"start": 30 * 60, "end": 60 * 60, "observed_demand": 60.0},
    )
    first = experiment.integrate_demand_mass(buckets, window_start=15 * 60, window_end=45 * 60)
    second = experiment.integrate_demand_mass(buckets, window_start=15 * 60, window_end=45 * 60)
    assert first == pytest.approx(45.0)
    assert first == second


def test_service_differentiation_arithmetic() -> None:
    assert pytest.approx(1.875) == (60 / 8) / (60 / 15)
    assert pytest.approx(1.2) == (60 / 10) / (60 / 12)
    assert pytest.approx(13 / 12) == (60 / 12) / (60 / 13)


def test_demand_alignment_distinguishes_equal_raw_frequency_ranges() -> None:
    regimes = (_regime("LOW", 0, 1200, 10), _regime("HIGH", 1200, 2400, 40))
    aligned = experiment.analyze_direction((0, 1200, 1800, 2400), regimes)
    misaligned = experiment.analyze_direction((0, 600, 1200, 2400), regimes)
    assert aligned["service_differentiation"]["max_min_service_frequency_ratio"] == pytest.approx(
        misaligned["service_differentiation"]["max_min_service_frequency_ratio"]
    )
    assert (
        aligned["demand_service_rank_correlation"] > misaligned["demand_service_rank_correlation"]
    )
    assert (
        aligned["demand_response_direction_accuracy"]
        > misaligned["demand_response_direction_accuracy"]
    )


def test_flat_service_has_zero_elasticity_and_contrast_amplitude() -> None:
    regimes = (_regime("LOW", 0, 1800, 10), _regime("HIGH", 1800, 3600, 90))
    result = experiment.analyze_direction(tuple(range(0, 3601, 600)), regimes)
    assert result["service_demand_response_regression"]["gamma"] == pytest.approx(0.0)
    assert result["actual_service_contrast_amplitude"] == pytest.approx(0.0)
    assert result["contrast_amplitude_ratio_to_sqrt_reference"] == pytest.approx(0.0)


def _sqrt_response_analysis() -> dict[str, object]:
    regimes = (
        _regime("D1", 0, 3600, 1),
        _regime("D2", 3600, 7200, 4),
        _regime("D3", 7200, 10800, 9),
        _regime("D4", 10800, 14400, 16),
    )
    departures = (
        0,
        3600,
        5400,
        7200,
        8400,
        9600,
        10800,
        11700,
        12600,
        13500,
        14400,
    )
    return experiment.analyze_direction(departures, regimes)


def test_log_log_elasticity_recovers_sqrt_relationship() -> None:
    result = _sqrt_response_analysis()
    assert result["service_demand_response_regression"]["gamma"] == pytest.approx(0.5)


def test_sqrt_relationship_has_near_zero_response_residual() -> None:
    result = _sqrt_response_analysis()
    assert result["sqrt_seed_response_deviation"] == pytest.approx(0.0, abs=1e-12)
    assert all(
        row["sqrt_response_residual"] == pytest.approx(0.0, abs=1e-12)
        for row in result["adjacent_demand_contrasts"]
    )


def test_repeated_analysis_is_byte_deterministic() -> None:
    first = _sqrt_response_analysis()
    second = _sqrt_response_analysis()
    assert first == second
    assert first["analysis_fingerprint"] == second["analysis_fingerprint"]
    assert experiment._canonical_json(first) == experiment._canonical_json(second)


def test_external_ai_keeps_external_benchmark_lineage() -> None:
    lineage = experiment.reference_lineage("EXTERNAL_AI")
    assert lineage == {
        "lineage": "EXTERNAL_BENCHMARK",
        "project_engine_lineage": False,
    }
