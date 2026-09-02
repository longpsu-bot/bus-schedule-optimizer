from __future__ import annotations

from types import SimpleNamespace

import pytest

import bus_schedule_engine.contracts_v1.operational_selection_policy_v2 as policy_v2
from bus_schedule_engine.contracts_v1.operational_selection_policy import (
    OperationalSelectionCandidateV1,
)
from bus_schedule_engine.contracts_v1.operational_selection_policy_v2 import (
    OperationalSelectionCandidateV2,
    build_operational_selection_candidate_v2,
    directional_trip_equivalent_error_v2,
    select_operational_candidates_v2,
    select_operational_timetable_v2,
)


def _candidate(
    fingerprint: str,
    *,
    sse: float,
    te: float,
    rhythm: tuple[int, int, int, int] = (8, 12, 6, 0),
    fleet: tuple[int, int, int] = (12, 100, 10),
    hard_feasible: bool = True,
    hard_reasons: tuple[str, ...] = (),
    outbound_max_wait: float = 10.0,
    inbound_max_wait: float = 11.0,
) -> OperationalSelectionCandidateV2:
    v1 = OperationalSelectionCandidateV1(
        fingerprint=fingerprint,
        hard_feasible=hard_feasible,
        hard_feasibility_reasons=hard_reasons,
        observed_demand_mismatch=sse,
        outbound_maximum_bucket_expected_wait_minutes=outbound_max_wait,
        inbound_maximum_bucket_expected_wait_minutes=inbound_max_wait,
        total_directional_sustained_headway_level_count=rhythm[0],
        actual_service_regime_count=rhythm[1],
        total_directional_effective_palette_count=rhythm[2],
        total_single_gap_regime_count=rhythm[3],
        fleet_required=fleet[0],
        total_excess_terminal_wait=fleet[1],
        max_excess_terminal_wait=fleet[2],
        diagnostics={},
        hard_feasibility_metrics={},
    )
    return OperationalSelectionCandidateV2(
        v1_candidate=v1,
        outbound_trip_equivalent_error=te / 2,
        inbound_trip_equivalent_error=te / 2,
        pair_trip_equivalent_error=te,
        diagnostics={},
    )


def test_simpler_candidate_inside_one_trip_te_band_beats_common_anchor() -> None:
    result = select_operational_candidates_v2(
        route_id="test",
        candidates=(
            _candidate("A", sse=1.0, te=10.0, rhythm=(8, 12, 6, 0)),
            _candidate("B", sse=2.0, te=10.7, rhythm=(6, 10, 5, 0)),
        ),
        scenario_b_directional_maximum_wait_minutes={"outbound": 10.0, "inbound": 11.0},
    )

    assert result.common_anchor_fingerprint == "A"
    assert result.selected_pair_fingerprint == "B"
    assert result.selected_stage == "RHYTHM_SIMPLICITY"
    assert result.classification == "ONE_TRIP_MATERIALITY_SELECTS_SIMPLER_ALTERNATIVE"


def test_directional_te_uses_exact_production_counts_and_shares() -> None:
    metrics = SimpleNamespace(
        bucket_service_counts=(4, 6),
        bucket_demand_shares=(0.5, 0.5),
        bucket_service_shares=(0.4, 0.6),
    )

    assert directional_trip_equivalent_error_v2(metrics, total_trips=10) == pytest.approx(1.0)


def test_candidate_projection_sums_directional_te_without_averaging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    v1 = _candidate("A", sse=1.0, te=2.0).v1_candidate
    monkeypatch.setattr(policy_v2, "build_operational_selection_candidate_v1", lambda **_: v1)
    outbound = SimpleNamespace(
        metrics=SimpleNamespace(
            bucket_service_counts=(5, 5),
            bucket_demand_shares=(0.625, 0.375),
            bucket_service_shares=(0.5, 0.5),
        ),
        state=SimpleNamespace(total_trips=10),
    )
    inbound = SimpleNamespace(
        metrics=SimpleNamespace(
            bucket_service_counts=(5, 5),
            bucket_demand_shares=(0.575, 0.425),
            bucket_service_shares=(0.5, 0.5),
        ),
        state=SimpleNamespace(total_trips=10),
    )

    result = build_operational_selection_candidate_v2(
        context=object(), candidate=SimpleNamespace(outbound=outbound, inbound=inbound)
    )

    assert result.outbound_trip_equivalent_error == pytest.approx(1.25)
    assert result.inbound_trip_equivalent_error == pytest.approx(0.75)
    assert result.pair_trip_equivalent_error == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("counts", "demand", "service", "total_trips"),
    (
        ((), (), (), 0),
        ((4, 6), (1.0,), (0.4, 0.6), 10),
        ((-1, 11), (0.5, 0.5), (-0.1, 1.1), 10),
        ((4.5, 5.5), (0.5, 0.5), (0.45, 0.55), 10),
        ((4, 5), (0.5, 0.5), (0.4, 0.6), 10),
        ((4, 6), (0.4, 0.4), (0.4, 0.6), 10),
        ((4, 6), (0.5, 0.5), (0.5, 0.5), 10),
        ((4, 6), (float("nan"), float("nan")), (0.4, 0.6), 10),
        ((4, 6), (0.5, 0.5), (float("inf"), float("-inf")), 10),
    ),
)
def test_directional_te_rejects_invalid_production_vectors(
    counts: tuple[float, ...],
    demand: tuple[float, ...],
    service: tuple[float, ...],
    total_trips: int,
) -> None:
    metrics = SimpleNamespace(
        bucket_service_counts=counts,
        bucket_demand_shares=demand,
        bucket_service_shares=service,
    )

    with pytest.raises(ValueError):
        directional_trip_equivalent_error_v2(metrics, total_trips=total_trips)


def _select(*candidates: OperationalSelectionCandidateV2):
    return select_operational_candidates_v2(
        route_id="test",
        candidates=candidates,
        scenario_b_directional_maximum_wait_minutes={"outbound": 10.0, "inbound": 11.0},
    )


def test_unique_sse_and_te_bests_establish_common_anchor() -> None:
    result = _select(_candidate("A", sse=1.0, te=10.0), _candidate("B", sse=2.0, te=10.5))

    assert result.sse_best_count == 1
    assert result.te_best_count == 1
    assert result.common_anchor_fingerprint == "A"
    assert result.common_anchor_sse == pytest.approx(1.0)
    assert result.common_anchor_te == pytest.approx(10.0)
    assert result.top_anchor_concordant is True


def test_conflicting_unique_sse_and_te_bests_fail_closed() -> None:
    result = _select(_candidate("A", sse=1.0, te=11.0), _candidate("B", sse=2.0, te=10.0))

    assert result.classification == "DEMAND_FIT_ANCHOR_CONFLICT"
    assert result.selected_pair_fingerprint is None
    assert result.materiality_set_count == 0


@pytest.mark.parametrize(
    "candidates",
    (
        (_candidate("A", sse=1.0, te=10.0), _candidate("B", sse=1.0 + 0.5e-12, te=10.5)),
        (_candidate("A", sse=1.0, te=10.0), _candidate("B", sse=2.0, te=10.0 + 0.5e-12)),
    ),
)
def test_non_unique_sse_or_te_best_fails_closed_without_fingerprint(
    candidates: tuple[OperationalSelectionCandidateV2, ...],
) -> None:
    result = _select(*candidates)

    assert result.classification == "DEMAND_FIT_ANCHOR_NOT_UNIQUE"
    assert result.selected_pair_fingerprint is None


def test_one_trip_band_boundary_uses_numerical_epsilon_exactly() -> None:
    epsilon = 1e-12
    result = _select(
        _candidate("A", sse=1.0, te=10.0),
        _candidate("B", sse=2.0, te=10.7),
        _candidate("C", sse=3.0, te=11.0),
        _candidate("D", sse=4.0, te=11.0 + 2 * epsilon),
        _candidate("E", sse=5.0, te=11.1),
    )

    materiality_trace = next(
        item for item in result.stage_trace if item.stage == "ONE_TRIP_TE_MATERIALITY_ENVELOPE"
    )
    assert materiality_trace.retained_fingerprints == ("A", "B", "C")
    assert {
        item.fingerprint
        for item in result.rejected_candidates
        if item.stage == materiality_trace.stage
    } == {
        "D",
        "E",
    }


def test_simpler_rhythm_outside_band_cannot_displace_anchor() -> None:
    result = _select(
        _candidate("A", sse=1.0, te=10.0, rhythm=(8, 12, 6, 0)),
        _candidate("B", sse=2.0, te=11.2, rhythm=(3, 5, 3, 0)),
    )

    assert result.selected_pair_fingerprint == "A"
    rejection = next(item for item in result.rejected_candidates if item.fingerprint == "B")
    assert rejection.stage == "ONE_TRIP_TE_MATERIALITY_ENVELOPE"
    assert rejection.relevant_metric_values["materiality_band_trips"] == 1.0


def test_lower_rank_sse_te_disagreement_does_not_override_rhythm() -> None:
    result = _select(
        _candidate("A", sse=1.0, te=10.0, rhythm=(8, 12, 6, 0)),
        _candidate("B", sse=2.0, te=10.8, rhythm=(7, 10, 5, 0)),
        _candidate("C", sse=3.0, te=10.7, rhythm=(6, 10, 5, 0)),
    )

    assert result.selected_pair_fingerprint == "C"


def test_fleet_required_is_first_efficiency_component_after_exact_rhythm_tie() -> None:
    result = _select(
        _candidate("A", sse=1.0, te=10.0, fleet=(12, 2000, 70)),
        _candidate("B", sse=2.0, te=10.7, fleet=(11, 2500, 80)),
    )

    assert result.selected_pair_fingerprint == "B"
    assert result.selected_stage == "FLEET_EFFICIENCY"


def test_hard_infeasible_candidate_never_enters_access_or_anchor() -> None:
    result = _select(
        _candidate("A", sse=2.0, te=10.0),
        _candidate(
            "B",
            sse=1.0,
            te=9.0,
            rhythm=(1, 1, 1, 0),
            hard_feasible=False,
            hard_reasons=("MINIMUM_LAYOVER_VIOLATION",),
        ),
    )

    assert result.hard_feasible_count == 1
    assert result.passenger_access_safe_count == 1
    assert result.common_anchor_fingerprint == "A"
    assert result.selected_pair_fingerprint == "A"
    assert result.rejected_candidates[0].stage == "HARD_OPERATIONAL_FEASIBILITY"


def test_access_regression_is_excluded_before_anchor_calculation() -> None:
    result = _select(
        _candidate("A", sse=2.0, te=10.0),
        _candidate("B", sse=1.0, te=9.0, inbound_max_wait=11.0 + 2e-12),
    )

    assert result.passenger_access_safe_count == 1
    assert result.common_anchor_fingerprint == "A"
    assert result.selected_pair_fingerprint == "A"
    rejection = next(item for item in result.rejected_candidates if item.fingerprint == "B")
    assert rejection.stage == "SCENARIO_B_MAX_ACCESS_NON_REGRESSION"


def test_empty_hard_feasible_and_access_safe_sets_fail_closed() -> None:
    no_feasible = _select(
        _candidate(
            "A",
            sse=1.0,
            te=10.0,
            hard_feasible=False,
            hard_reasons=("FLEET_CEILING_EXCEEDED",),
        )
    )
    no_access = _select(_candidate("A", sse=1.0, te=10.0, outbound_max_wait=10.1))

    assert no_feasible.classification == "NO_HARD_FEASIBLE_CANDIDATE"
    assert no_feasible.selected_pair_fingerprint is None
    assert no_access.classification == "ACCESS_GUARDRAIL_TOO_RESTRICTIVE"
    assert no_access.selected_pair_fingerprint is None


def test_fingerprint_is_only_final_deterministic_tiebreak() -> None:
    result = _select(
        _candidate("Z", sse=1.0, te=10.0),
        _candidate("A", sse=2.0, te=10.7),
    )

    assert result.selected_pair_fingerprint == "A"
    assert result.classification == "METRICALLY_EQUIVALENT_DETERMINISTIC_TIEBREAK"
    assert result.selected_stage == "FINAL_DETERMINISTIC_TIEBREAK"
    assert result.pair_fingerprint_is_quality_objective is False


def test_contract_package_exports_v1_and_explicit_v2_names() -> None:
    from bus_schedule_engine import contracts_v1

    assert (
        contracts_v1.OPERATIONAL_SELECTION_PROFILE_V1 == "domain_priority_operational_selector_v1"
    )
    assert (
        contracts_v1.OPERATIONAL_SELECTION_PROFILE_V2
        == "one_trip_te_materiality_operational_selector_v2"
    )
    assert contracts_v1.TE_MATERIALITY_BAND_TRIPS_V2 == 1.0
    assert contracts_v1.PRIORITY_ORDER_V2 == (
        "HARD_OPERATIONAL_FEASIBILITY",
        "SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
        "COMMON_SSE_TE_DEMAND_FIT_ANCHOR",
        "ONE_TRIP_TE_MATERIALITY_ENVELOPE",
        "RHYTHM_SIMPLICITY",
        "FLEET_EFFICIENCY",
    )
    assert (
        contracts_v1.OperationalSelectionPolicyV1 is not contracts_v1.OperationalSelectionPolicyV2
    )
    assert callable(contracts_v1.build_operational_selection_candidate_v2)
    assert callable(contracts_v1.select_operational_candidates_v2)
    assert callable(contracts_v1.select_operational_timetable_v2)


def test_timetable_selector_projects_frontier_once_and_uses_directional_scenario_b_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _candidate("A", sse=1.0, te=10.0)
    projected: list[object] = []

    def project(*, context: object, candidate: object) -> OperationalSelectionCandidateV2:
        projected.append(candidate)
        return snapshot

    monkeypatch.setattr(policy_v2, "build_operational_selection_candidate_v2", project)
    from bus_schedule_engine import service_plan_coordinator as coordinator

    monkeypatch.setattr(
        coordinator,
        "expected_passenger_wait_metrics_v1",
        lambda departures, _buckets: (0.0, 10.0 if departures == (1,) else 11.0, 0.0, ()),
    )
    raw_candidate = object()
    context = SimpleNamespace(
        route_id="test",
        scenario_b_departures={"outbound": (1,), "inbound": (2,)},
        demand_buckets={"outbound": (), "inbound": ()},
    )

    result = select_operational_timetable_v2(context=context, candidates=(raw_candidate,))

    assert projected == [raw_candidate]
    assert result.selected_pair_fingerprint == "A"
