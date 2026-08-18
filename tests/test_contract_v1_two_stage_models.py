from __future__ import annotations

from dataclasses import replace

import pytest

from bus_schedule_engine.contracts_v1 import (
    B_ANCHORED_TWO_STAGE_REBALANCE_V1,
    SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE,
    TRIP_ALLOCATION_PLAN_PROFILE_V1,
    ContractDirection,
    DemandAllocationAuthorityModeV1,
    FinalAcceptanceStateV1,
    FinalServiceTailPolicyV1,
    ProposedServiceRegimeV1,
    ScenarioCOptimizationModeV1,
    TripAllocationBlockV1,
    TripAllocationPlanV1,
    TripAllocationSolveStatusV1,
    UniformIntegerRegimePolicyV3,
    calculate_allocation_fingerprint,
    classify_two_stage_final_acceptance_v1,
    finalize_allocation_plan,
    is_strict_uniform_integer_headway_sequence_v3,
)


def _regime(
    direction: ContractDirection,
    *,
    regime_id: str,
    start: int,
    headway: int,
    trip_count: int,
) -> ProposedServiceRegimeV1:
    end = start + headway * (trip_count - 1)
    return ProposedServiceRegimeV1(
        regime_id=regime_id,
        direction=direction,
        covered_demand_block_ids=(f"{regime_id}-BLOCK",),
        trip_count=trip_count,
        permitted_start_window=(start - 5, start + 5),
        permitted_end_window=(end - 5, end + 5),
        planned_start_minute=start,
        planned_end_minute=end,
        minimum_headway_minutes=2,
        maximum_headway_minutes=30,
        uniform_headway_minutes=headway,
        boundary_reason="MATERIAL_DEMAND_CHANGE",
    )


def _plan() -> TripAllocationPlanV1:
    policy = UniformIntegerRegimePolicyV3()
    blocks = (
        TripAllocationBlockV1(
            block_id="OUT-BLOCK",
            direction=ContractDirection.OUTBOUND,
            start_minute=360,
            end_minute=391,
            trip_count=4,
            observed_passengers=120,
            required_trips_90=3,
            required_trips_85=4,
            source_b_trip_count=4,
            directional_trip_counts=((ContractDirection.OUTBOUND, 4),),
        ),
        TripAllocationBlockV1(
            block_id="IN-BLOCK",
            direction=ContractDirection.INBOUND,
            start_minute=420,
            end_minute=441,
            trip_count=3,
            observed_passengers=80,
            required_trips_90=2,
            required_trips_85=3,
            source_b_trip_count=3,
            directional_trip_counts=((ContractDirection.INBOUND, 3),),
        ),
    )
    plan = TripAllocationPlanV1(
        source_b_fingerprint="b" * 64,
        demand_authority_fingerprint="d" * 64,
        optimization_mode=(ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE),
        demand_authority_mode=(DemandAllocationAuthorityModeV1.DIRECTIONAL_FIXED_DIRECTION_COUNTS),
        allocation_plan_profile=TRIP_ALLOCATION_PLAN_PROFILE_V1,
        uniform_regime_profile=SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE,
        final_tail_policy_fingerprint=policy.policy_fingerprint,
        total_trips=7,
        trips_by_direction=(
            (ContractDirection.OUTBOUND, 4),
            (ContractDirection.INBOUND, 3),
        ),
        allocation_blocks=blocks,
        proposed_regimes=(
            _regime(
                ContractDirection.OUTBOUND,
                regime_id="OUT",
                start=360,
                headway=10,
                trip_count=4,
            ),
            _regime(
                ContractDirection.INBOUND,
                regime_id="IN",
                start=420,
                headway=10,
                trip_count=3,
            ),
        ),
        objective_vector=(0, 0, 0, 0, 0),
        solve_status=TripAllocationSolveStatusV1.OPTIMAL,
        solve_duration_seconds=0.25,
        allocation_fingerprint="",
    )
    return finalize_allocation_plan(plan)


def test_v3_policy_has_explicit_new_profile_and_b_anchored_mode() -> None:
    policy = UniformIntegerRegimePolicyV3()

    assert policy.profile == SCENARIO_C_UNIFORM_INTEGER_REGIME_POLICY_PROFILE
    assert policy.profile == "scenario_c_uniform_integer_regime_policy_v3"
    assert (
        ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE.value
        == B_ANCHORED_TWO_STAGE_REBALANCE_V1
    )
    assert policy.absolute_max_shift_per_trip_minutes == 30
    assert policy.final_service_tail.final_service_tail_window_minutes == 60


def test_measurable_v3_regime_requires_exact_integer_representability() -> None:
    valid = _regime(
        ContractDirection.OUTBOUND,
        regime_id="VALID",
        start=360,
        headway=7,
        trip_count=4,
    )
    assert valid.planned_end_minute == 381

    with pytest.raises(ValueError, match="not exactly representable"):
        ProposedServiceRegimeV1(
            regime_id="INVALID",
            direction=ContractDirection.OUTBOUND,
            covered_demand_block_ids=("BLOCK",),
            trip_count=4,
            permitted_start_window=(360, 360),
            permitted_end_window=(380, 380),
            planned_start_minute=360,
            planned_end_minute=380,
            minimum_headway_minutes=2,
            maximum_headway_minutes=30,
            uniform_headway_minutes=7,
            boundary_reason="SYNTHETIC_UNREPRESENTABLE_SPAN",
        )


def test_allocation_fingerprint_is_duration_independent_and_binds_v3_policy() -> None:
    plan = _plan()
    assert plan.allocation_fingerprint == calculate_allocation_fingerprint(plan)

    duration_changed = replace(plan, solve_duration_seconds=99.0)
    assert calculate_allocation_fingerprint(duration_changed) == plan.allocation_fingerprint

    with pytest.raises(ValueError, match="V3 uniform-regime"):
        replace(plan, uniform_regime_profile="scenario_c_balanced_regime_policy_v2")


def test_final_acceptance_states_are_explicit_and_exhaustive() -> None:
    assert {item.value for item in FinalAcceptanceStateV1} == {
        "FINAL_RECOMMENDED",
        "VALID_CANDIDATE_NOT_FINAL",
        "KEEP_SCENARIO_B",
        "NO_FINAL_C_WITHIN_SOLVE_BUDGET",
    }


@pytest.mark.parametrize("sequence", [(6, 6, 6), (7, 7, 7), (20, 20)])
def test_v3_accepts_only_one_exact_integer_headway(sequence: tuple[int, ...]) -> None:
    assert is_strict_uniform_integer_headway_sequence_v3(sequence)


@pytest.mark.parametrize("sequence", [(6, 7, 6), (10, 11, 10), (20, 21)])
def test_v3_rejects_balanced_or_mixed_headway_sequences(sequence: tuple[int, ...]) -> None:
    assert not is_strict_uniform_integer_headway_sequence_v3(sequence)


def test_final_acceptance_requires_material_improvement_after_independent_validation() -> None:
    baseline = (0, 0, 0, 3, 20, 0, 4, 0, 0, 0)
    assert (
        classify_two_stage_final_acceptance_v1(baseline, baseline)
        == FinalAcceptanceStateV1.KEEP_SCENARIO_B
    )
    assert (
        classify_two_stage_final_acceptance_v1(
            baseline,
            (0, 1, 0, 0, 10, 0, 0, 2, 4, 2),
        )
        == FinalAcceptanceStateV1.VALID_CANDIDATE_NOT_FINAL
    )
    assert (
        classify_two_stage_final_acceptance_v1(
            baseline,
            (0, 0, 0, 2, 20, 0, 4, 1, 1, 1),
        )
        == FinalAcceptanceStateV1.FINAL_RECOMMENDED
    )


def test_one_trip_final_tail_is_explicitly_non_measurable() -> None:
    policy = UniformIntegerRegimePolicyV3(
        final_service_tail=FinalServiceTailPolicyV1(
            final_service_tail_minimum_trip_count=1,
        )
    )
    singleton = ProposedServiceRegimeV1(
        regime_id="FINAL-SINGLETON",
        direction=ContractDirection.OUTBOUND,
        covered_demand_block_ids=("FINAL-BLOCK",),
        trip_count=1,
        permitted_start_window=(420, 420),
        permitted_end_window=(420, 420),
        planned_start_minute=420,
        planned_end_minute=420,
        minimum_headway_minutes=policy.minimum_operational_headway_minutes,
        maximum_headway_minutes=(
            policy.final_service_tail.final_service_tail_maximum_headway_minutes
        ),
        uniform_headway_minutes=None,
        boundary_reason="FINAL_SERVICE_TAIL_ANCHORED_TO_LOCKED_LAST_DEPARTURE",
        is_final_service_tail=True,
    )

    assert not singleton.measurable
    assert singleton.uniform_headway_minutes is None
