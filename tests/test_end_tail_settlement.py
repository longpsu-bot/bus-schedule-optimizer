from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from bus_schedule_engine.contracts_v1.clean_boundary_compiler import (
    BoundaryOwnershipV1,
    OperationalEndpointAuthorityV1,
)
from bus_schedule_engine.contracts_v1.end_tail_settlement import (
    TAIL_DEBT_CAPACITY_EXCEEDED,
    TAIL_SETTLEMENT_NOT_ELIGIBLE,
    CoreRegimeAllocationEvidenceV2,
    TailAwareAllocationCandidateV2,
    TailAwareAllocationFrontierV2,
    TailAwareAllocationStatusV2,
    TailAwareDemandRegimeV2,
    TailEligibilityEvidenceV2,
    TailEligibilityStatusV2,
    allocate_tail_aware_trips_v2,
    compile_end_tail_settlement_v2,
    effective_service_spans_v1,
    enumerate_feasible_tail_counts_v2,
    evaluate_tail_eligibility_v2,
    select_tail_aware_candidates_v2,
)

MINUTE = 60


def _regimes() -> tuple[TailAwareDemandRegimeV2, ...]:
    return (
        TailAwareDemandRegimeV2("R1", 0, 60 * MINUTE, 0.25, 4),
        TailAwareDemandRegimeV2("R2", 60 * MINUTE, 180 * MINUTE, 0.65, 6),
        TailAwareDemandRegimeV2("R3", 180 * MINUTE, 240 * MINUTE, 0.10, 2),
    )


def _authority() -> OperationalEndpointAuthorityV1:
    return OperationalEndpointAuthorityV1(
        route_id="X",
        direction="outbound",
        analysis_window_start=0,
        analysis_window_end=240 * MINUTE,
        fixed_first_departure=0,
        fixed_last_departure=230 * MINUTE,
        authority_source="test",
    )


def _selected():
    regimes = _regimes()
    authority = _authority()
    frontier = allocate_tail_aware_trips_v2(
        regimes=regimes,
        total_trips=12,
        endpoint_authority=authority,
    )
    selected = select_tail_aware_candidates_v2(
        route_id="X",
        direction="outbound",
        regimes=regimes,
        endpoint_authority=authority,
        frontier=frontier,
    )
    assert selected.c1_demand_fit is not None
    return regimes, authority, frontier, selected.c1_demand_fit.plan


def test_01_low_demand_tail_is_eligible() -> None:
    evidence = evaluate_tail_eligibility_v2(_regimes(), _authority())

    assert evidence.status == TailEligibilityStatusV2.ELIGIBLE
    assert evidence.final_demand_density_index < 1.0
    assert evidence.final_demand_density_index <= evidence.previous_demand_density_index


def test_02_high_demand_final_regime_uses_not_eligible_status() -> None:
    regimes = (*_regimes()[:-1], replace(_regimes()[-1], demand_share=0.40))

    frontier = allocate_tail_aware_trips_v2(
        regimes=regimes,
        total_trips=12,
        endpoint_authority=_authority(),
    )

    assert frontier.status == TailAwareAllocationStatusV2.NOT_ELIGIBLE
    assert frontier.failure_code == TAIL_SETTLEMENT_NOT_ELIGIBLE
    assert frontier.candidates == ()


def test_03_tail_count_is_total_minus_core() -> None:
    _, _, frontier, _ = _selected()

    assert all(
        item.residual_tail_trip_count == 12 - sum(item.core_trip_counts)
        for item in frontier.candidates
    )


def test_04_fixed_last_departure_cannot_move() -> None:
    _, authority, _, plan = _selected()
    assert plan.compilation is not None

    assert plan.compilation.exact_departures[-1] == authority.fixed_last_departure
    assert plan.tail_evidence is not None
    assert plan.tail_evidence.tail_last_departure == authority.fixed_last_departure


def test_05_tail_is_constructed_backward_from_fixed_last() -> None:
    _, _, _, plan = _selected()
    assert plan.compilation is not None
    assert plan.tail_evidence is not None
    tail_slice = plan.compilation.demand_regime_slices[-1]

    expected = tuple(
        plan.tail_evidence.tail_last_departure - offset * plan.tail_evidence.tail_headway * MINUTE
        for offset in range(plan.tail_evidence.tail_trip_count - 1, -1, -1)
    )
    assert tail_slice.departures == expected


def test_06_tail_start_never_precedes_eligible_zone() -> None:
    _, _, _, plan = _selected()
    assert plan.tail_evidence is not None

    assert plan.tail_evidence.tail_start >= plan.tail_evidence.tail_zone_start


def test_07_low_demand_tail_is_not_more_frequent_than_core() -> None:
    _, _, _, plan = _selected()
    assert plan.tail_evidence is not None

    assert plan.tail_evidence.tail_headway >= plan.tail_evidence.previous_core_headway
    assert plan.tail_evidence.low_demand_monotonicity_satisfied


def test_08_tail_does_not_exceed_service_floor_maximum_headway() -> None:
    _, _, frontier, plan = _selected()
    assert plan.tail_evidence is not None

    assert plan.tail_evidence.tail_headway <= frontier.service_floor_headway_minutes
    assert plan.tail_evidence.service_floor_satisfied


def test_09_core_tail_boundary_has_exact_owner() -> None:
    _, _, _, plan = _selected()
    assert plan.compilation is not None
    assert plan.tail_evidence is not None
    boundary = plan.compilation.boundary_diagnostics[-1]

    assert boundary.valid
    assert boundary.gap_minutes in {
        boundary.left_service_headway,
        boundary.right_service_headway,
    }
    assert plan.tail_evidence.clean_boundary_ownership == boundary.ownership.value


def test_10_tail_debt_capacity_is_derived_from_legal_headways() -> None:
    capacity = enumerate_feasible_tail_counts_v2(
        last_core_departure_minute=160,
        previous_core_headway=20,
        tail_zone_start_minute=180,
        fixed_last_departure_minute=240,
        service_floor_headway_minutes=30,
        maximum_tail_trip_count=8,
    )

    assert tuple(capacity) == (3, 4)
    assert capacity[3][0].headway_minutes == 30
    assert capacity[4][1] == BoundaryOwnershipV1.MERGED


def test_11_debt_capacity_overflow_returns_structured_failure() -> None:
    regimes = (
        TailAwareDemandRegimeV2("R1", 0, 180 * MINUTE, 0.8, 9),
        TailAwareDemandRegimeV2("R2", 180 * MINUTE, 300 * MINUTE, 0.2, 1),
    )
    authority = OperationalEndpointAuthorityV1(
        "X",
        "outbound",
        0,
        300 * MINUTE,
        0,
        240 * MINUTE,
        "test",
    )
    span = effective_service_spans_v1(regimes, authority)[0]
    eligibility = TailEligibilityEvidenceV2(
        status=TailEligibilityStatusV2.ELIGIBLE,
        final_regime_id="R2",
        final_demand_share=0.2,
        final_duration_share=0.4,
        final_demand_density_index=0.5,
        previous_regime_id="R1",
        previous_demand_density_index=1.3333333333333333,
        tail_zone_start=180 * MINUTE,
        tail_zone_end=240 * MINUTE,
    )
    evidence = CoreRegimeAllocationEvidenceV2(
        regime_id="R1",
        demand_start=0,
        demand_end=180 * MINUTE,
        effective_start=0,
        effective_end=180 * MINUTE,
        effective_duration_minutes=180,
        demand_share=0.8,
        b_trip_count=9,
        allocated_trip_count=9,
        ideal_trip_count=8,
        minimum_trip_count=9,
        maximum_trip_count=180,
        nominal_operational_headway=20,
        best_integer_headway_proxy=20,
        headway_quantization_error=0,
    )
    allocation = TailAwareAllocationCandidateV2(
        candidate_record_id="OVERFLOW",
        core_trip_counts=(9,),
        core_trip_total=9,
        residual_tail_trip_count=1,
        core_demand_mismatch=0.01,
        full_day_demand_mismatch_after_tail=0.02,
        moved_trips_vs_b=0,
        compile_quality_proxy=0,
        core_regime_evidence=(evidence,),
    )
    frontier = TailAwareAllocationFrontierV2(
        allocator_profile="test",
        status=TailAwareAllocationStatusV2.SUCCESS,
        total_trips=10,
        service_floor_headway_minutes=20,
        service_floor_provenance="test",
        effective_spans=(span, effective_service_spans_v1(regimes, authority)[1]),
        eligibility=eligibility,
        tail_ideal_trip_count=2,
        b_full_day_demand_mismatch=0.02,
        candidates=(allocation,),
        generated_record_count=1,
        bounded_frontier_limit=3,
    )

    plan = compile_end_tail_settlement_v2(
        route_id="X",
        direction="outbound",
        candidate_id="OVERFLOW",
        regimes=regimes,
        endpoint_authority=authority,
        frontier=frontier,
        allocation=allocation,
    )

    assert plan.failure is not None
    assert plan.failure.code == TAIL_DEBT_CAPACITY_EXCEEDED
    assert plan.failure.feasible_tail_trip_counts == (4,)


def test_12_first_edge_uses_effective_span_from_fixed_first() -> None:
    regimes = _regimes()
    authority = replace(_authority(), fixed_first_departure=15 * MINUTE)

    spans = effective_service_spans_v1(regimes, authority)

    assert spans[0].effective_start == 15 * MINUTE
    assert spans[0].effective_duration_minutes == 45
    assert spans[0].demand_duration_minutes == 60


def test_13_no_departure_uses_analysis_extension_after_fixed_last() -> None:
    regimes, authority, _, plan = _selected()
    assert regimes[-1].end_time > authority.fixed_last_departure
    assert plan.compilation is not None

    assert max(plan.compilation.exact_departures) == authority.fixed_last_departure


def test_14_full_trip_total_reconciles_exactly() -> None:
    _, _, frontier, plan = _selected()
    assert plan.compilation is not None

    assert len(plan.compilation.exact_departures) == frontier.total_trips
    assert (
        sum(item.authoritative_trip_count for item in plan.compilation.demand_regime_slices) == 12
    )


def test_15_no_transition_category_or_unowned_gap() -> None:
    _, _, _, plan = _selected()
    assert plan.compilation is not None

    assert all(
        "TRANSITION" not in item.service_regime_id for item in plan.compilation.service_regimes
    )
    assert all(item.valid for item in plan.compilation.boundary_diagnostics)


def test_16_one_hundred_runs_are_deterministic() -> None:
    signatures = []
    for _ in range(100):
        _, _, _, plan = _selected()
        assert plan.compilation is not None
        assert plan.tail_evidence is not None
        signatures.append(
            (
                plan.allocation.core_trip_counts,
                plan.allocation.residual_tail_trip_count,
                plan.compilation.exact_departures,
                plan.tail_evidence.feasible_tail_trip_counts,
            )
        )

    assert len(set(signatures)) == 1


def test_17_frozen_v1_v2_artifact_manifest_matches_bytes() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (repo_root / "config" / "end_tail_frozen_prior_fingerprints_v2.json").read_text(
            encoding="utf-8"
        )
    )["sha256"]
    if any(not (repo_root / relative).is_file() for relative in manifest):
        pytest.skip("optional local pilot artifacts are unavailable")
    for relative, expected in manifest.items():
        actual = hashlib.sha256((repo_root / relative).read_bytes()).hexdigest()
        assert actual == expected
