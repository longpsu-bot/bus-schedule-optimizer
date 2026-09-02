from __future__ import annotations

import importlib
import math
from types import SimpleNamespace

import pytest


def _bucket(start: float, end: float, demand: float) -> dict[str, float]:
    return {"start": start, "end": end, "observed_demand": demand}


def _continuous(departures: list[float], buckets: list[dict[str, float]]) -> dict[str, object]:
    policy_v3 = importlib.import_module(
        "bus_schedule_engine.contracts_v1.operational_selection_policy_v3"
    )
    assert hasattr(policy_v3, "continuous_exposure_metrics_v3")
    return policy_v3.continuous_exposure_metrics_v3(departures, buckets)


def test_profile_exposes_exact_phase_robust_priority_order() -> None:
    """Catch a V3 profile that omits or reorders either calibration stage."""

    policy_v3 = importlib.import_module(
        "bus_schedule_engine.contracts_v1.operational_selection_policy_v3"
    )

    assert policy_v3.OPERATIONAL_SELECTION_PROFILE_V3 == (
        "legacy_calibrated_continuous_exposure_operational_selector_v3"
    )
    assert policy_v3.LEGACY_TE_CALIBRATION_BAND_TRIPS_V3 == 1.0
    assert policy_v3.PRIMARY_MATERIALITY_METRIC_V3 == "continuous_exposure_equivalent"
    assert policy_v3.PRIORITY_ORDER_V3 == (
        "HARD_OPERATIONAL_FEASIBILITY",
        "SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
        "COMMON_SSE_TE_DEMAND_FIT_ANCHOR",
        "LEGACY_ONE_TRIP_TE_SEMANTIC_CALIBRATION",
        "ROUTE_LOCAL_CONTINUOUS_EXPOSURE_MATERIALITY_ENVELOPE",
        "RHYTHM_SIMPLICITY",
        "FLEET_EFFICIENCY",
    )


def test_continuous_exposure_integrates_exact_union_of_breakpoints() -> None:
    """Catch point counting, discretization, or omission of a departure breakpoint."""

    metrics = _continuous(
        [0, 1200, 3600],
        [_bucket(0, 1800, 1.0), _bucket(1800, 3600, 1.0)],
    )

    assert metrics["breakpoints"] == (0.0, 1200.0, 1800.0, 3600.0)
    assert metrics["tv"] == pytest.approx(1.0 / 6.0)
    assert metrics["equivalent"] == pytest.approx(0.5)
    assert metrics["service_exposure_integral"] == pytest.approx(2.0)
    assert metrics["demand_integral"] == pytest.approx(2.0)


def test_continuous_exposure_is_zero_for_matching_piecewise_densities() -> None:
    """Catch use of departure point mass instead of interdeparture exposure density."""

    metrics = _continuous(
        [0, 1800, 3600],
        [_bucket(0, 1800, 1.0), _bucket(1800, 3600, 1.0)],
    )

    assert metrics["tv"] == pytest.approx(0.0, abs=1e-12)
    assert metrics["equivalent"] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize(
    ("departures", "buckets"),
    (
        ([0], [_bucket(0, 100, 1.0)]),
        ([0, 100, 100], [_bucket(0, 100, 1.0), _bucket(100, 200, 1.0)]),
        ([0, float("inf")], [_bucket(0, 100, 1.0)]),
        ([0, 100], []),
        ([0, 100], [_bucket(0, 0, 1.0)]),
        ([0, 100], [_bucket(0, 100, -1.0)]),
        ([0, 100, 200], [_bucket(0, 100, 1.0), _bucket(101, 200, 1.0)]),
        ([0, 100, 200], [_bucket(0, 101, 1.0), _bucket(100, 200, 1.0)]),
        ([-1, 100], [_bucket(0, 100, 1.0)]),
        ([0, 101], [_bucket(0, 100, 1.0)]),
        ([0, 100], [_bucket(0, 100, 0.0)]),
        ([0, 100], [_bucket(0, 100, float("nan"))]),
    ),
)
def test_continuous_exposure_rejects_invalid_exact_inputs(
    departures: list[float], buckets: list[dict[str, float]]
) -> None:
    """Catch permissive inputs that would make the exact metric ambiguous or non-finite."""

    with pytest.raises(ValueError):
        _continuous(departures, buckets)


def _candidate(
    fingerprint: str,
    *,
    sse: float,
    te: float,
    continuous: float,
    rhythm: tuple[int, int, int, int] = (8, 12, 6, 0),
    fleet: tuple[int, int, int] = (12, 100, 10),
    hard_feasible: bool = True,
    hard_reasons: tuple[str, ...] = (),
    outbound_max_wait: float = 10.0,
    inbound_max_wait: float = 11.0,
    micro_rhythm_boundaries: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        fingerprint=fingerprint,
        hard_feasible=hard_feasible,
        hard_feasibility_reasons=hard_reasons,
        hard_feasibility_metrics={},
        observed_demand_mismatch=sse,
        outbound_maximum_bucket_expected_wait_minutes=outbound_max_wait,
        inbound_maximum_bucket_expected_wait_minutes=inbound_max_wait,
        pair_trip_equivalent_error=te,
        outbound_continuous_exposure_equivalent=continuous / 2,
        inbound_continuous_exposure_equivalent=continuous / 2,
        pair_continuous_exposure_equivalent=continuous,
        total_directional_sustained_headway_level_count=rhythm[0],
        actual_service_regime_count=rhythm[1],
        total_directional_effective_palette_count=rhythm[2],
        total_single_gap_regime_count=rhythm[3],
        fleet_required=fleet[0],
        total_excess_terminal_wait=fleet[1],
        max_excess_terminal_wait=fleet[2],
        diagnostics={"micro_rhythm_boundary_count": micro_rhythm_boundaries},
    )


def _select(*candidates: SimpleNamespace):
    policy_v3 = importlib.import_module(
        "bus_schedule_engine.contracts_v1.operational_selection_policy_v3"
    )
    assert hasattr(policy_v3, "select_operational_candidates_v3")
    return policy_v3.select_operational_candidates_v3(
        route_id="test",
        candidates=candidates,
        scenario_b_directional_maximum_wait_minutes={"outbound": 10.0, "inbound": 11.0},
    )


def test_one_trip_te_is_calibration_only_and_translated_candidate_can_win() -> None:
    """Catch reuse of the literal +1 TE gate after it has calibrated the CE envelope."""

    result = _select(
        _candidate("A", sse=1.0, te=10.0, continuous=20.0),
        _candidate("L", sse=2.0, te=11.0, continuous=22.0),
        _candidate(
            "T",
            sse=5.0,
            te=13.0,
            continuous=21.5,
            rhythm=(6, 6, 6, 0),
        ),
    )

    assert result.legacy_calibration_fingerprints == ("A", "L")
    assert result.continuous_preservation_bound == pytest.approx(2.0)
    assert result.phase_robust_materiality_fingerprints == ("A", "L", "T")
    assert result.selected_pair_fingerprint == "T"
    assert result.selected_inside_legacy_te_calibration_set is False
    assert result.classification == "PHASE_ROBUST_MATERIALITY_SELECTS_TRANSLATED_ALTERNATIVE"


def test_route_local_bound_is_maximum_continuous_delta_of_legacy_set() -> None:
    """Catch a percentile, fixed threshold, rounded bound, or minimum-delta mapping."""

    first = _select(
        _candidate("A", sse=1.0, te=10.0, continuous=20.0),
        _candidate("B", sse=2.0, te=10.5, continuous=20.4),
        _candidate("C", sse=3.0, te=11.0, continuous=21.75),
    )
    second = _select(
        _candidate("A", sse=1.0, te=10.0, continuous=20.0),
        _candidate("B", sse=2.0, te=10.5, continuous=20.4),
        _candidate("C", sse=3.0, te=11.0, continuous=23.25),
    )

    assert first.continuous_preservation_bound == pytest.approx(1.75)
    assert second.continuous_preservation_bound == pytest.approx(3.25)


@pytest.mark.parametrize(
    ("candidates", "classification", "sse_count", "te_count"),
    (
        (
            (
                _candidate("A", sse=1.0, te=10.0, continuous=20.0),
                _candidate("B", sse=1.0 + 0.5e-12, te=10.5, continuous=20.5),
            ),
            "DEMAND_FIT_ANCHOR_NOT_UNIQUE",
            2,
            1,
        ),
        (
            (
                _candidate("A", sse=1.0, te=10.0, continuous=20.0),
                _candidate("B", sse=2.0, te=10.0 + 0.5e-12, continuous=20.5),
            ),
            "DEMAND_FIT_ANCHOR_NOT_UNIQUE",
            1,
            2,
        ),
        (
            (
                _candidate("A", sse=1.0, te=11.0, continuous=20.0),
                _candidate("B", sse=2.0, te=10.0, continuous=20.5),
            ),
            "DEMAND_FIT_ANCHOR_CONFLICT",
            1,
            1,
        ),
    ),
)
def test_common_sse_te_anchor_fail_closed_conditions(
    candidates: tuple[SimpleNamespace, ...],
    classification: str,
    sse_count: int,
    te_count: int,
) -> None:
    """Catch ambiguous or conflicting demand-fit anchors entering calibration."""

    result = _select(*candidates)

    assert result.classification == classification
    assert result.sse_best_count == sse_count
    assert result.te_best_count == te_count
    assert result.common_anchor_fingerprint is None
    assert result.selected_pair_fingerprint is None


def test_hard_and_access_filters_run_before_anchor_and_calibration() -> None:
    """Catch infeasible or access-unsafe low-metric candidates contaminating the anchor."""

    result = _select(
        _candidate("A", sse=3.0, te=12.0, continuous=22.0),
        _candidate(
            "H",
            sse=1.0,
            te=10.0,
            continuous=20.0,
            hard_feasible=False,
            hard_reasons=("MINIMUM_LAYOVER_VIOLATION",),
        ),
        _candidate("X", sse=2.0, te=11.0, continuous=21.0, inbound_max_wait=11.1),
    )

    assert result.hard_feasible_count == 2
    assert result.passenger_access_safe_count == 1
    assert result.common_anchor_fingerprint == "A"
    assert result.legacy_calibration_fingerprints == ("A",)


def test_continuous_reference_conflict_fails_closed_without_reanchoring() -> None:
    """Catch silent continuous re-anchoring, clamping, or absolute deltas."""

    result = _select(
        _candidate("A", sse=1.0, te=10.0, continuous=20.0),
        _candidate("B", sse=2.0, te=10.5, continuous=19.0),
    )

    assert result.classification == "PHASE_ROBUST_REFERENCE_CONFLICT"
    assert result.common_anchor_fingerprint == "A"
    assert result.selected_pair_fingerprint is None
    assert result.phase_robust_materiality_set_count == 0


def test_nonfinite_continuous_candidate_fails_closed() -> None:
    """Catch NaN or infinity leaking into bound and membership comparisons."""

    for value in (math.nan, math.inf, -math.inf):
        result = _select(
            _candidate("A", sse=1.0, te=10.0, continuous=20.0),
            _candidate("B", sse=2.0, te=10.5, continuous=value),
        )
        assert result.classification == "INVALID_CONTINUOUS_EXPOSURE_METRIC"
        assert result.selected_pair_fingerprint is None


def test_directional_continuous_values_must_be_finite_and_sum_to_pair() -> None:
    """Catch a finite pair masking invalid or inconsistent directional metrics."""

    invalid_direction = _candidate("B", sse=2.0, te=10.5, continuous=20.5)
    invalid_direction.outbound_continuous_exposure_equivalent = math.inf
    inconsistent_pair = _candidate("C", sse=3.0, te=10.7, continuous=20.7)
    inconsistent_pair.inbound_continuous_exposure_equivalent += 1.0

    for candidate in (invalid_direction, inconsistent_pair):
        result = _select(_candidate("A", sse=1.0, te=10.0, continuous=20.0), candidate)
        assert result.classification == "INVALID_CONTINUOUS_EXPOSURE_METRIC"
        assert result.selected_pair_fingerprint is None


def test_materiality_members_are_not_reranked_by_sse_te_or_continuous_distance() -> None:
    """Catch any demand-fit metric being promoted after CE admission."""

    result = _select(
        _candidate("A", sse=1.0, te=10.0, continuous=20.0, rhythm=(9, 9, 9, 0)),
        _candidate("B", sse=2.0, te=10.2, continuous=20.1, rhythm=(8, 8, 8, 0)),
        _candidate("C", sse=9.0, te=13.0, continuous=21.5, rhythm=(6, 6, 6, 0)),
        _candidate("L", sse=3.0, te=11.0, continuous=22.0, rhythm=(7, 7, 7, 0)),
    )

    assert result.selected_pair_fingerprint == "C"
    assert result.selected_delta_te_from_anchor == pytest.approx(3.0)
    assert result.selected_delta_continuous_from_anchor == pytest.approx(1.5)


def test_frozen_rhythm_then_fleet_then_fingerprint_hierarchy() -> None:
    """Catch fleet/fingerprint promotion or mutation of the four-field rhythm tuple."""

    rhythm = _select(
        _candidate("A", sse=1.0, te=10.0, continuous=20.0, rhythm=(2, 2, 2, 0)),
        _candidate(
            "B",
            sse=2.0,
            te=10.5,
            continuous=20.5,
            rhythm=(1, 9, 9, 9),
            fleet=(99, 99, 99),
        ),
    )
    fleet = _select(
        _candidate("A", sse=1.0, te=10.0, continuous=20.0, fleet=(12, 100, 10)),
        _candidate("B", sse=2.0, te=10.5, continuous=20.5, fleet=(11, 999, 99)),
    )
    tied = _select(
        _candidate("Z", sse=1.0, te=10.0, continuous=20.0),
        _candidate("A", sse=2.0, te=10.5, continuous=20.5),
    )

    assert rhythm.selected_pair_fingerprint == "B"
    assert fleet.selected_pair_fingerprint == "B"
    assert tied.selected_pair_fingerprint == "A"
    assert tied.classification == "METRICALLY_EQUIVALENT_DETERMINISTIC_TIEBREAK"
    assert tied.pair_fingerprint_is_quality_objective is False
    assert next(item for item in rhythm.rejected_candidates if item.fingerprint == "A").stage == (
        "RHYTHM_SIMPLICITY"
    )
    assert next(item for item in fleet.rejected_candidates if item.fingerprint == "A").stage == (
        "FLEET_EFFICIENCY"
    )
    assert next(item for item in tied.rejected_candidates if item.fingerprint == "Z").stage == (
        "FINAL_DETERMINISTIC_TIEBREAK"
    )


def test_micro_rhythm_diagnostic_is_not_a_gate_or_tuple_field() -> None:
    """Catch micro-rhythm boundary count being promoted into production selection."""

    result = _select(
        _candidate("A", sse=1.0, te=10.0, continuous=20.0, micro_rhythm_boundaries=0),
        _candidate(
            "B",
            sse=2.0,
            te=10.5,
            continuous=20.5,
            fleet=(11, 100, 10),
            micro_rhythm_boundaries=99,
        ),
    )

    assert result.selected_pair_fingerprint == "B"


def test_selection_is_deterministic_under_candidate_input_ordering() -> None:
    """Catch order-dependent calibration membership, traces, or winner selection."""

    candidates = (
        _candidate("C", sse=3.0, te=11.0, continuous=22.0),
        _candidate("A", sse=1.0, te=10.0, continuous=20.0),
        _candidate("B", sse=2.0, te=10.5, continuous=21.0),
    )

    forward = _select(*candidates)
    reverse = _select(*reversed(candidates))

    assert forward == reverse
    assert forward.legacy_calibration_fingerprints[0] == "A"
    assert "A" in forward.legacy_calibration_fingerprints


def test_empty_hard_or_access_safe_frontiers_fail_closed() -> None:
    """Catch min() calls or selection attempts on empty filtered universes."""

    no_hard = _select(
        _candidate(
            "A",
            sse=1.0,
            te=10.0,
            continuous=20.0,
            hard_feasible=False,
            hard_reasons=("FLEET_CEILING_EXCEEDED",),
        )
    )
    no_access = _select(_candidate("A", sse=1.0, te=10.0, continuous=20.0, outbound_max_wait=10.1))

    assert no_hard.classification == "NO_HARD_FEASIBLE_CANDIDATE"
    assert no_access.classification == "ACCESS_GUARDRAIL_TOO_RESTRICTIVE"
    assert no_hard.selected_pair_fingerprint is None
    assert no_access.selected_pair_fingerprint is None


def test_candidate_projection_reuses_v2_and_sums_directional_continuous_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch V1/V2 feasibility duplication or pair averaging during V3 projection."""

    policy_v3 = importlib.import_module(
        "bus_schedule_engine.contracts_v1.operational_selection_policy_v3"
    )
    v2_snapshot = SimpleNamespace(fingerprint="A")
    monkeypatch.setattr(
        policy_v3,
        "build_operational_selection_candidate_v2",
        lambda **_: v2_snapshot,
    )
    compilation = SimpleNamespace(exact_departures=(0, 1800, 3600))
    direction = SimpleNamespace(compile_variant=SimpleNamespace(compilation=compilation))
    buckets = (
        SimpleNamespace(start=0, end=1800, observed_demand=1.0),
        SimpleNamespace(start=1800, end=3600, observed_demand=1.0),
    )

    result = policy_v3.build_operational_selection_candidate_v3(
        context=SimpleNamespace(demand_buckets={"outbound": buckets, "inbound": buckets}),
        candidate=SimpleNamespace(outbound=direction, inbound=direction),
    )

    assert result.v2_candidate is v2_snapshot
    assert result.outbound_continuous_exposure_equivalent == pytest.approx(0.0)
    assert result.inbound_continuous_exposure_equivalent == pytest.approx(0.0)
    assert result.pair_continuous_exposure_equivalent == pytest.approx(0.0)


def test_contract_package_exports_explicit_v3_api_without_replacing_v2() -> None:
    """Catch a frozen V3 API that is inaccessible or aliases the active V2 profile."""

    from bus_schedule_engine import contracts_v1

    assert contracts_v1.OPERATIONAL_SELECTION_PROFILE_V2 == (
        "one_trip_te_materiality_operational_selector_v2"
    )
    assert contracts_v1.OPERATIONAL_SELECTION_PROFILE_V3 == (
        "legacy_calibrated_continuous_exposure_operational_selector_v3"
    )
    assert callable(contracts_v1.continuous_exposure_metrics_v3)
    assert callable(contracts_v1.build_operational_selection_candidate_v3)
    assert callable(contracts_v1.select_operational_candidates_v3)
    assert callable(contracts_v1.select_operational_timetable_v3)
