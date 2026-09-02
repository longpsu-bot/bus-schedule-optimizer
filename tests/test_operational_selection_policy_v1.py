from __future__ import annotations

import dataclasses

from bus_schedule_engine.contracts_v1.clean_boundary_compiler import (
    OperationalEndpointAuthorityV1,
)
from bus_schedule_engine.contracts_v1.clean_compile_frontier import (
    compile_service_plan_frontier_v1,
)
from bus_schedule_engine.contracts_v1.operational_selection_policy import (
    OperationalSelectionCandidateV1,
    build_operational_selection_candidate_v1,
    select_operational_candidates_v1,
    select_operational_timetable_v1,
)
from bus_schedule_engine.contracts_v1.service_plan_state import (
    ServicePlanStateV1,
    ServiceRegimeDecisionV1,
    service_plan_fingerprint_v1,
)
from bus_schedule_engine.service_plan_coordinator import (
    DemandBucketEvidenceV1,
    DirectionalCompilationCandidateV1,
    RouteCoordinatorContextV1,
    evaluate_actual_service_v1,
    evaluate_operating_pair_v1,
)


def _candidate(
    fingerprint: str,
    *,
    hard_feasible: bool = True,
    hard_reasons: tuple[str, ...] = (),
    mismatch: float = 0.01,
    outbound_max_wait: float = 10.0,
    inbound_max_wait: float = 10.0,
    sustained_count: int = 5,
    regime_count: int = 10,
    effective_palette_count: int = 4,
    single_gap_count: int = 0,
    fleet: int = 15,
    total_terminal_wait: int = 100,
    max_terminal_wait: int = 20,
) -> OperationalSelectionCandidateV1:
    return OperationalSelectionCandidateV1(
        fingerprint=fingerprint,
        hard_feasible=hard_feasible,
        hard_feasibility_reasons=hard_reasons,
        observed_demand_mismatch=mismatch,
        outbound_maximum_bucket_expected_wait_minutes=outbound_max_wait,
        inbound_maximum_bucket_expected_wait_minutes=inbound_max_wait,
        total_directional_sustained_headway_level_count=sustained_count,
        actual_service_regime_count=regime_count,
        total_directional_effective_palette_count=effective_palette_count,
        total_single_gap_regime_count=single_gap_count,
        fleet_required=fleet,
        total_excess_terminal_wait=total_terminal_wait,
        max_excess_terminal_wait=max_terminal_wait,
        diagnostics={},
        hard_feasibility_metrics={},
    )


def test_hard_feasibility_cannot_be_rescued_by_better_demand_fit() -> None:
    infeasible = _candidate(
        "A",
        hard_feasible=False,
        hard_reasons=("MINIMUM_LAYOVER_VIOLATION",),
        mismatch=0.0,
    )
    feasible = _candidate("B", mismatch=0.1)

    result = select_operational_candidates_v1(
        route_id="6",
        candidates=(infeasible, feasible),
        scenario_b_directional_maximum_wait_minutes={"outbound": 15.0, "inbound": 15.0},
    )

    assert result.hard_feasible_count == 1
    assert result.selected_pair_fingerprint == "B"
    assert result.rejected_candidates[0].stage == "HARD_OPERATIONAL_FEASIBILITY"
    assert result.rejected_candidates[0].reason == "MINIMUM_LAYOVER_VIOLATION"


def test_fleet_ceiling_failure_is_rejected_before_demand_fit() -> None:
    over_ceiling = _candidate(
        "A",
        hard_feasible=False,
        hard_reasons=("FLEET_CEILING_EXCEEDED",),
        mismatch=0.0,
        fleet=21,
    )
    feasible = _candidate("B", mismatch=0.1, fleet=20)

    result = select_operational_candidates_v1(
        route_id="6",
        candidates=(over_ceiling, feasible),
        scenario_b_directional_maximum_wait_minutes={"outbound": 15.0, "inbound": 15.0},
    )

    assert result.selected_pair_fingerprint == "B"
    assert result.rejected_candidates[0].stage == "HARD_OPERATIONAL_FEASIBILITY"


def test_access_guardrail_excludes_best_mismatch_and_accepts_exact_equality() -> None:
    unsafe = _candidate("A", mismatch=0.0, inbound_max_wait=20.0)
    exact = _candidate("B", mismatch=0.1, inbound_max_wait=15.0)

    result = select_operational_candidates_v1(
        route_id="10",
        candidates=(unsafe, exact),
        scenario_b_directional_maximum_wait_minutes={"outbound": 12.0, "inbound": 15.0},
    )

    assert result.passenger_access_safe_count == 1
    assert result.selected_pair_fingerprint == "B"
    assert result.rejected_candidates[0].stage == "SCENARIO_B_MAX_ACCESS_NON_REGRESSION"
    assert result.rejected_candidates[0].reason == "INBOUND_MAX_ACCESS_REGRESSION"


def test_access_guardrail_is_directional_not_pair_maximum() -> None:
    candidate = _candidate("A", outbound_max_wait=13.0, inbound_max_wait=14.0)

    result = select_operational_candidates_v1(
        route_id="10",
        candidates=(candidate,),
        scenario_b_directional_maximum_wait_minutes={"outbound": 12.0, "inbound": 15.0},
    )

    assert result.passenger_access_safe_count == 0
    assert result.selected_pair_fingerprint is None
    assert result.classification == "ACCESS_GUARDRAIL_TOO_RESTRICTIVE"


def test_demand_fit_has_strict_priority_over_rhythm_and_fleet() -> None:
    demand_best = _candidate(
        "A",
        mismatch=0.010,
        sustained_count=8,
        effective_palette_count=8,
        fleet=20,
    )
    simpler = _candidate(
        "B",
        mismatch=0.011,
        sustained_count=3,
        effective_palette_count=3,
        fleet=15,
    )

    result = select_operational_candidates_v1(
        route_id="6",
        candidates=(demand_best, simpler),
        scenario_b_directional_maximum_wait_minutes={"outbound": 15.0, "inbound": 15.0},
    )

    assert result.best_demand_fit_count == 1
    assert result.selected_pair_fingerprint == "A"
    assert result.selected_stage == "OBSERVED_DEMAND_MISMATCH"
    assert any(
        item.fingerprint == "B" and item.stage == "OBSERVED_DEMAND_MISMATCH"
        for item in result.rejected_candidates
    )


def test_demand_fit_retains_numerical_epsilon_equals_without_rounding_band() -> None:
    best = _candidate("B", mismatch=0.01)
    epsilon_equal = _candidate("A", mismatch=0.01 + 0.5e-12)
    outside_epsilon = _candidate("C", mismatch=0.01 + 2e-12)

    result = select_operational_candidates_v1(
        route_id="6",
        candidates=(outside_epsilon, epsilon_equal, best),
        scenario_b_directional_maximum_wait_minutes={"outbound": 15.0, "inbound": 15.0},
    )

    assert result.best_demand_fit_count == 2
    assert result.stage_trace[2].retained_fingerprints == ("A", "B")
    assert any(item.fingerprint == "C" for item in result.rejected_candidates)


def _select_equal_demand_pair(
    left: OperationalSelectionCandidateV1,
    right: OperationalSelectionCandidateV1,
):
    return select_operational_candidates_v1(
        route_id="6",
        candidates=(left, right),
        scenario_b_directional_maximum_wait_minutes={"outbound": 15.0, "inbound": 15.0},
    )


def test_rhythm_prefers_sustained_vocabulary_before_regime_count() -> None:
    more_levels = _candidate("A", sustained_count=7, regime_count=10)
    fewer_levels = _candidate("B", sustained_count=5, regime_count=12)

    result = _select_equal_demand_pair(more_levels, fewer_levels)

    assert result.best_rhythm_count == 1
    assert result.selected_pair_fingerprint == "B"
    assert result.selected_stage == "RHYTHM_SIMPLICITY"


def test_rhythm_uses_regime_count_after_equal_sustained_vocabulary() -> None:
    more_regimes = _candidate("A", sustained_count=5, regime_count=12)
    fewer_regimes = _candidate("B", sustained_count=5, regime_count=10)

    result = _select_equal_demand_pair(more_regimes, fewer_regimes)

    assert result.selected_pair_fingerprint == "B"


def test_rhythm_uses_effective_palette_after_equal_regime_count() -> None:
    larger_palette = _candidate("A", effective_palette_count=5)
    smaller_palette = _candidate("B", effective_palette_count=4)

    result = _select_equal_demand_pair(larger_palette, smaller_palette)

    assert result.selected_pair_fingerprint == "B"


def test_rhythm_uses_single_gap_count_last_without_hard_rejection() -> None:
    one_gap = _candidate("A", single_gap_count=1)
    no_gap = _candidate("B", single_gap_count=0)

    result = _select_equal_demand_pair(one_gap, no_gap)

    assert result.hard_feasible_count == 2
    assert result.selected_pair_fingerprint == "B"


def test_fleet_efficiency_prefers_lower_fleet_after_equal_demand_and_rhythm() -> None:
    more_fleet = _candidate("A", fleet=18)
    less_fleet = _candidate("B", fleet=17)

    result = _select_equal_demand_pair(more_fleet, less_fleet)

    assert result.best_fleet_efficiency_count == 1
    assert result.selected_pair_fingerprint == "B"
    assert result.selected_stage == "FLEET_EFFICIENCY"


def test_fleet_efficiency_uses_total_terminal_wait_after_equal_fleet() -> None:
    more_wait = _candidate("A", fleet=17, total_terminal_wait=3000)
    less_wait = _candidate("B", fleet=17, total_terminal_wait=2500)

    result = _select_equal_demand_pair(more_wait, less_wait)

    assert result.selected_pair_fingerprint == "B"


def test_fleet_efficiency_uses_max_terminal_wait_last() -> None:
    larger_max = _candidate("A", max_terminal_wait=30)
    smaller_max = _candidate("B", max_terminal_wait=20)

    result = _select_equal_demand_pair(larger_max, smaller_max)

    assert result.selected_pair_fingerprint == "B"


def test_fingerprint_is_only_the_final_metrically_equivalent_tiebreak() -> None:
    lexicographically_later = _candidate("B")
    lexicographically_earlier = _candidate("A")

    result = _select_equal_demand_pair(lexicographically_later, lexicographically_earlier)

    assert result.best_fleet_efficiency_count == 2
    assert result.selected_pair_fingerprint == "A"
    assert result.selected_stage == "FINAL_DETERMINISTIC_TIEBREAK"
    assert result.classification == "METRICALLY_EQUIVALENT_DETERMINISTIC_TIEBREAK"
    assert any(
        item.fingerprint == "B" and item.stage == "FINAL_DETERMINISTIC_TIEBREAK"
        for item in result.rejected_candidates
    )
    assert tuple(item.stage for item in result.stage_trace) == (
        "HARD_OPERATIONAL_FEASIBILITY",
        "SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
        "OBSERVED_DEMAND_MISMATCH",
        "RHYTHM_SIMPLICITY",
        "FLEET_EFFICIENCY",
    )


def _real_operating_pair():
    authorities = {
        direction: OperationalEndpointAuthorityV1(
            route_id="X",
            direction=direction,
            analysis_window_start=0,
            analysis_window_end=3600,
            fixed_first_departure=0,
            fixed_last_departure=3540,
            authority_source="test",
        )
        for direction in ("outbound", "inbound")
    }
    states = {
        direction: ServicePlanStateV1(
            route_id="X",
            direction=direction,
            fixed_first_departure=0,
            fixed_last_departure=3540,
            service_regimes=(
                ServiceRegimeDecisionV1(0, 1800, 4),
                ServiceRegimeDecisionV1(1800, 3600, 4),
            ),
            seed_id="TEST",
        )
        for direction in ("outbound", "inbound")
    }
    variants = {
        direction: compile_service_plan_frontier_v1(
            states[direction],
            endpoint_authority=authorities[direction],
            compile_frontier_limit=1,
        ).variants[0]
        for direction in ("outbound", "inbound")
    }
    buckets = {
        direction: (
            DemandBucketEvidenceV1(direction, 0, 1800, 10.0),
            DemandBucketEvidenceV1(direction, 1800, 3600, 10.0),
        )
        for direction in ("outbound", "inbound")
    }
    context = RouteCoordinatorContextV1(
        route_id="X",
        route_name="Synthetic",
        endpoint_authority=authorities,
        demand_buckets=buckets,
        scenario_b_departures={
            direction: variants[direction].compilation.exact_departures
            for direction in ("outbound", "inbound")
        },
        seed_headway_prior_minutes={"outbound": 30.0, "inbound": 30.0},
        planning_grid_seconds=900,
        runtime_minutes=1,
        minimum_layover_minutes=1,
        fleet_ceiling=20,
        immutable_demand_sha256="immutable",
    )
    directions = {}
    for direction in ("outbound", "inbound"):
        metrics, feedback = evaluate_actual_service_v1(
            variants[direction],
            demand_buckets=buckets[direction],
            scenario_b_departures=context.scenario_b_departures[direction],
        )
        directions[direction] = DirectionalCompilationCandidateV1(
            state=states[direction],
            state_fingerprint=service_plan_fingerprint_v1(states[direction]),
            compile_variant=variants[direction],
            metrics=metrics,
            feedback=feedback,
            history=(),
        )
    pair, feedback = evaluate_operating_pair_v1(
        directions["outbound"],
        directions["inbound"],
        context=context,
    )
    assert feedback == ()
    assert pair is not None
    return context, pair


def test_operating_pair_adapter_independently_confirms_all_hard_feasibility() -> None:
    context, pair = _real_operating_pair()

    candidate = build_operational_selection_candidate_v1(context=context, candidate=pair)

    assert candidate.hard_feasible
    assert candidate.hard_feasibility_reasons == ()
    assert all(candidate.hard_feasibility_metrics["checks"].values())
    assert set(candidate.diagnostics) >= {
        "directional_bucket_service_shares",
        "demand_response_direction_accuracy",
        "sqrt_response_deviation",
        "under_over_feedback_presence",
    }


def test_operating_pair_adapter_rejects_stored_minimum_layover_violation() -> None:
    context, pair = _real_operating_pair()
    invalid = dataclasses.replace(pair, minimum_connection_layover_minutes=0)

    candidate = build_operational_selection_candidate_v1(context=context, candidate=invalid)

    assert not candidate.hard_feasible
    assert "MINIMUM_LAYOVER_VIOLATION" in candidate.hard_feasibility_reasons


def test_operating_pair_adapter_rejects_false_minimum_layover_witness() -> None:
    context, pair = _real_operating_pair()
    invalid = dataclasses.replace(pair, minimum_connection_layover_minutes=99)

    candidate = build_operational_selection_candidate_v1(context=context, candidate=invalid)

    assert not candidate.hard_feasible
    assert "MINIMUM_LAYOVER_WITNESS_MISMATCH" in candidate.hard_feasibility_reasons


def test_operating_pair_adapter_rejects_fleet_requirement_above_ceiling() -> None:
    context, pair = _real_operating_pair()
    metrics = dataclasses.replace(
        pair.metrics,
        fleet_required=context.fleet_ceiling + 1,
    )
    invalid = dataclasses.replace(pair, metrics=metrics)

    candidate = build_operational_selection_candidate_v1(context=context, candidate=invalid)

    assert not candidate.hard_feasible
    assert "FLEET_CEILING_EXCEEDED" in candidate.hard_feasibility_reasons


def test_post_search_selector_keeps_frontier_input_immutable() -> None:
    context, pair = _real_operating_pair()
    before = dataclasses.asdict(pair.metrics)

    result = select_operational_timetable_v1(context=context, candidates=(pair,))

    assert result.selected_pair_fingerprint == pair.pair_fingerprint
    assert dataclasses.asdict(pair.metrics) == before


def test_operational_selection_contract_is_public_from_contracts_v1() -> None:
    from bus_schedule_engine.contracts_v1 import OperationalSelectionPolicyV1

    policy = OperationalSelectionPolicyV1()

    assert policy.profile == "domain_priority_operational_selector_v1"
    assert policy.priority_order == (
        "HARD_OPERATIONAL_FEASIBILITY",
        "SCENARIO_B_MAX_ACCESS_NON_REGRESSION",
        "OBSERVED_DEMAND_MISMATCH",
        "RHYTHM_SIMPLICITY",
        "FLEET_EFFICIENCY",
    )
