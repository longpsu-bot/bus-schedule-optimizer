from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import run_pr62_g0_route6_layover_sensitivity as g0

from bus_schedule_engine.service_plan_coordinator import RouteCoordinatorContextV1


def _context() -> RouteCoordinatorContextV1:
    return RouteCoordinatorContextV1(
        route_id="6",
        route_name="Route 6",
        endpoint_authority={},
        demand_buckets={},
        scenario_b_departures={},
        seed_headway_prior_minutes={},
        planning_grid_seconds=60,
        runtime_minutes=70,
        minimum_layover_minutes=5,
        fleet_ceiling=20,
        immutable_demand_sha256="frozen",
    )


def test_sensitivity_context_is_immutable_10_minute_override() -> None:
    baseline = _context()
    sensitivity = dataclasses.replace(baseline, minimum_layover_minutes=10)
    assert baseline.minimum_layover_minutes == 5
    assert sensitivity.minimum_layover_minutes == 10
    assert sensitivity is not baseline


@pytest.mark.parametrize(
    ("static_fleet", "connections", "reoptimized", "expected"),
    [
        (20, True, True, "BASELINE_TIMETABLE_ROBUST_AT_10"),
        (21, True, True, "ROBUST_AFTER_REOPTIMIZATION"),
        (21, True, False, "NOT_ROBUST_WITHIN_CURRENT_SEARCH"),
    ],
)
def test_robustness_classification(
    static_fleet: int, connections: bool, reoptimized: bool, expected: str
) -> None:
    assert (
        g0.robustness_classification(
            static_fleet_required=static_fleet,
            static_connections_valid=connections,
            reoptimized_feasible=reoptimized,
        )
        == expected
    )


def _pair(outbound: tuple[int, ...], inbound: tuple[int, ...]) -> SimpleNamespace:
    def record(direction: str, values: tuple[int, ...]) -> SimpleNamespace:
        compilation = SimpleNamespace(exact_departures=values)
        return SimpleNamespace(compile_variant=SimpleNamespace(compilation=compilation))

    return SimpleNamespace(
        outbound=record("outbound", outbound), inbound=record("inbound", inbound)
    )


def test_ordered_departure_shift_comparison() -> None:
    baseline = _pair((0, 600, 1200), (0, 600, 1200))
    sensitivity = _pair((0, 660, 1200), (0, 480, 1200))
    result = g0.departure_shift_comparison(baseline, sensitivity)
    assert result["changed_count"] == 2
    assert result["total_absolute_shift_minutes"] == 3
    assert result["mean_absolute_shift_minutes"] == pytest.approx(1.5)
    assert result["median_absolute_shift_minutes"] == pytest.approx(1.5)
    assert result["maximum_absolute_shift_minutes"] == 2
    assert result["largest_10"][0]["direction"] == "inbound"
    assert result["largest_10"][0]["sequence"] == 2


def test_render_is_deterministic() -> None:
    evidence_path = Path(__file__).resolve().parents[1] / g0.OUTPUT_JSON
    if not evidence_path.is_file():
        pytest.skip("G0 evidence has not been generated")
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert g0.render_artifacts(payload) == g0.render_artifacts(payload)


def test_generated_evidence_guards_and_case_b_identity() -> None:
    evidence_path = Path(__file__).resolve().parents[1] / g0.OUTPUT_JSON
    if not evidence_path.is_file():
        pytest.skip("G0 evidence has not been generated")
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    authority = payload["baseline_authority"]
    assert authority["minimum_layover_minutes"] == 5
    assert (
        payload["case_b_static_revalidation_10_min"]["fleet_plan"]["minimum_layover_minutes"] == 10
    )
    assert (
        payload["case_b_static_revalidation_10_min"]["departures_tuple_identical_to_case_a"] is True
    )
    assert (
        payload["case_b_static_revalidation_10_min"]["passenger_facing_metrics_identical_to_case_a"]
        is True
    )
    for direction in g0.DIRECTIONS:
        a = payload["case_a_baseline_5_min"]["selected_pair"]["directions"][direction]
        c = payload["case_c_reoptimized_10_min"]["selected_pair"]["directions"][direction]
        assert a["trip_total"] == c["trip_total"] == authority["trip_totals"][direction]
        assert a["first_departure"] == c["first_departure"]
        assert a["last_departure"] == c["last_departure"]
    assert payload["case_c_reoptimized_10_min"]["determinism"]["passed"] is True
