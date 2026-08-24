from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from bus_schedule_engine.clean_boundary_pilot import (
    build_product_headway_rows_v1,
    frozen_upstream_fingerprints_v1,
    run_clean_boundary_pilot_v1,
)
from bus_schedule_engine.contracts_v1.clean_boundary_compiler import (
    BoundaryOwnershipV1,
    CleanBoundaryCompilationStatusV1,
    DemandRegimeAllocationV1,
    OperationalEndpointAuthorityV1,
    clean_boundary_compilation_to_dict_v1,
    compile_clean_boundary_timetable_v1,
    scan_serialized_headway_outliers_v1,
    validate_clean_boundary_compilation_v1,
)

_REPO_ROOT = Path(__file__).parents[1]


def _require_optional_files(*paths: Path) -> None:
    missing = [path for path in paths if not path.is_file()]
    if missing:
        pytest.skip("optional local pilot inputs are unavailable")


def _regime(regime_id: str, start: int, end: int, count: int) -> DemandRegimeAllocationV1:
    return DemandRegimeAllocationV1(
        regime_id=regime_id,
        start_time=start * 60,
        end_time=end * 60,
        allocated_trip_count=count,
        nominal_headway=(end - start) / count,
    )


def _compile(
    regimes: tuple[DemandRegimeAllocationV1, ...],
    *,
    first: int,
    last: int,
):
    return compile_clean_boundary_timetable_v1(
        route_id="fixture",
        direction="outbound",
        candidate_id="C3_BALANCED",
        regimes=regimes,
        endpoint_authority=OperationalEndpointAuthorityV1(
            route_id="fixture",
            direction="outbound",
            analysis_window_start=regimes[0].start_time,
            analysis_window_end=regimes[-1].end_time,
            fixed_first_departure=first * 60,
            fixed_last_departure=last * 60,
            authority_source="fixture::THAM_SO_B",
        ),
    )


def test_fixed_first_departure_is_a_hard_constraint() -> None:
    result = _compile(
        (_regime("D1", 0, 30, 3), _regime("D2", 30, 60, 3)),
        first=4,
        last=50,
    )
    assert result.status == CleanBoundaryCompilationStatusV1.COMPILED_CLEAN_BOUNDARIES
    assert result.exact_departures[0] == 4 * 60


def test_fixed_last_departure_is_a_hard_constraint() -> None:
    result = _compile(
        (_regime("D1", 0, 30, 3), _regime("D2", 30, 60, 3)),
        first=4,
        last=50,
    )
    assert result.exact_departures[-1] == 50 * 60


def test_analysis_window_does_not_move_or_fill_operational_endpoints() -> None:
    result = _compile(
        (_regime("D1", 0, 30, 3), _regime("D2", 30, 60, 3)),
        first=4,
        last=50,
    )
    authority = result.endpoint_authority
    assert authority.analysis_window_end == 60 * 60
    assert authority.fixed_last_departure == 50 * 60
    assert max(result.exact_departures) == 50 * 60
    assert not any(
        departure > authority.fixed_last_departure for departure in result.exact_departures
    )


def test_clean_boundary_can_be_owned_by_left_rhythm() -> None:
    result = _compile(
        (_regime("D1", 0, 24, 3), _regime("D2", 24, 54, 3)),
        first=0,
        last=44,
    )
    boundary = result.boundary_diagnostics[0]
    assert boundary.gap_minutes == boundary.left_service_headway == 8
    assert boundary.right_service_headway == 10
    assert boundary.ownership == BoundaryOwnershipV1.LEFT


def test_clean_boundary_can_be_owned_by_right_rhythm() -> None:
    result = _compile(
        (_regime("D1", 0, 30, 3), _regime("D2", 30, 60, 3)),
        first=4,
        last=50,
    )
    boundary = result.boundary_diagnostics[0]
    assert boundary.left_service_headway == 8
    assert boundary.gap_minutes == boundary.right_service_headway == 10
    assert boundary.ownership == BoundaryOwnershipV1.RIGHT


def test_boundary_gap_outside_adjacent_headways_is_rejected() -> None:
    regimes = (_regime("D1", 0, 24, 3), _regime("D2", 24, 54, 3))
    result = _compile(regimes, first=0, last=44)
    forged_boundary = replace(result.boundary_diagnostics[0], gap_minutes=9, valid=True)
    forged = replace(result, boundary_diagnostics=(forged_boundary,))
    with pytest.raises(ValueError, match="differs from both adjacent headways"):
        validate_clean_boundary_compilation_v1(forged, regimes)


def test_equal_continuous_headways_merge_service_regimes() -> None:
    result = _compile(
        (_regime("D1", 0, 30, 3), _regime("D2", 30, 60, 3)),
        first=0,
        last=50,
    )
    assert len(result.service_regimes) == 1
    service = result.service_regimes[0]
    assert service.uniform_headway_minutes == 10
    assert service.demand_regime_ids == ("D1", "D2")
    assert service.trip_count == 6


def test_exact_demand_regime_counts_survive_compilation() -> None:
    regimes = (_regime("D1", 0, 30, 3), _regime("D2", 30, 60, 3))
    result = _compile(regimes, first=4, last=50)
    for regime in regimes:
        assert (
            sum(
                regime.start_time <= departure < regime.end_time
                for departure in result.exact_departures
            )
            == regime.allocated_trip_count
        )


def test_impossible_clean_boundary_returns_structured_failure() -> None:
    result = _compile(
        (_regime("D1", 0, 30, 3), _regime("D2", 30, 60, 3)),
        first=0,
        last=33,
    )
    assert result.status == CleanBoundaryCompilationStatusV1.CLEAN_BOUNDARY_UNCOMPILABLE
    assert result.failure is not None
    assert result.failure.boundary_time == 30 * 60
    assert result.failure.left_trip_count == 3
    assert result.failure.right_trip_count == 3
    assert result.failure.left_feasible_headways
    assert result.failure.right_feasible_headways == (1,)
    assert "g in {hL, hR}" in result.failure.reason


def test_compiled_serialization_has_no_transition_category() -> None:
    result = _compile(
        (_regime("D1", 0, 24, 3), _regime("D2", 24, 54, 3)),
        first=0,
        last=44,
    )
    serialized = json.dumps(clean_boundary_compilation_to_dict_v1(result), sort_keys=True)
    assert "TRANSITION" not in serialized


def test_product_scan_detects_an_isolated_boundary_outlier() -> None:
    result = _compile(
        (_regime("D1", 0, 24, 3), _regime("D2", 24, 54, 3)),
        first=0,
        last=44,
    )
    forged_boundary = replace(result.boundary_diagnostics[0], gap_minutes=9, valid=False)
    forged = replace(result, boundary_diagnostics=(forged_boundary,))
    assert scan_serialized_headway_outliers_v1(forged) == (forged_boundary,)
    assert len(build_product_headway_rows_v1(result)) == len(result.exact_departures)


def test_clean_boundary_compiler_is_deterministic_across_100_runs() -> None:
    regimes = (_regime("D1", 0, 30, 3), _regime("D2", 30, 60, 3))
    baseline = clean_boundary_compilation_to_dict_v1(_compile(regimes, first=4, last=50))
    for _ in range(99):
        assert (
            clean_boundary_compilation_to_dict_v1(_compile(regimes, first=4, last=50)) == baseline
        )


def test_frozen_upstream_fingerprints_match_the_correction_manifest() -> None:
    manifest = json.loads(
        (_REPO_ROOT / "config" / "clean_boundary_frozen_fingerprints_v1.json").read_text(
            encoding="utf-8"
        )
    )
    _require_optional_files(*(_REPO_ROOT / relative for relative in manifest["sha256"]))
    assert frozen_upstream_fingerprints_v1(_REPO_ROOT) == manifest["sha256"]


def test_real_route_pilot_recompiles_12_and_validates_18_combinations(tmp_path: Path) -> None:
    workbooks = {
        "6": _REPO_ROOT.parent / "Engine_Input_MST_6_V3_MultiPeriod_Mar-Jul_2026.xlsx",
        "10": _REPO_ROOT.parent / "Engine_Input_MST_10_V3_MultiPeriod_Mar-Jul_2026.xlsx",
    }
    manifest = json.loads(
        (_REPO_ROOT / "config" / "clean_boundary_frozen_fingerprints_v1.json").read_text(
            encoding="utf-8"
        )
    )
    _require_optional_files(
        *workbooks.values(),
        *(_REPO_ROOT / relative for relative in manifest["sha256"]),
    )
    payload = run_clean_boundary_pilot_v1(
        repo_root=_REPO_ROOT,
        route_workbooks=workbooks,
        output_directory=tmp_path,
    )
    assert sum(len(route["compilations"]) for route in payload["routes"]) == 12
    assert sum(len(route["fleet_matrix"]) for route in payload["routes"]) == 18
    assert all(
        compilation["status"] == "COMPILED_CLEAN_BOUNDARIES"
        for route in payload["routes"]
        for compilation in route["compilations"]
    )
    assert payload["product_headway_outlier_scan"] == {
        "status": "PASS",
        "outlier_count": 0,
    }
    assert payload["frozen_upstream_fingerprints_unchanged"] is True
    selections = {route["route_id"]: route["final_selection"] for route in payload["routes"]}
    assert selections["6"]["outbound_candidate_id"] == "C3_BALANCED"
    assert selections["6"]["inbound_candidate_id"] == "C3_BALANCED"
    assert selections["6"]["fleet_requirement"] == 19
    assert selections["10"]["outbound_candidate_id"] == "C3_BALANCED"
    assert selections["10"]["inbound_candidate_id"] == "C3_BALANCED"
    assert selections["10"]["fleet_requirement"] == 12
