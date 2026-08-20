from __future__ import annotations

from test_contract_v1_two_stage_allocator import _stage1_request

from bus_schedule_engine.contracts_v1 import (
    ContractDirection,
    UniformIntegerRegimePolicyV3,
    allocate_trips_stage_1_v1,
)
from bus_schedule_engine.contracts_v1 import v3_global_regularity_v2 as global_policy_v2


def _stage1_with_v2(problem, authority, policy):
    global_policy_v2.install_global_regularity_v2()
    try:
        return allocate_trips_stage_1_v1(
            problem,
            authority,
            policy=policy,
            time_limit_seconds=4.0,
        )
    finally:
        global_policy_v2.uninstall_global_regularity_v2()


def test_stage1_v2_allocation_respects_cumulative_b_shift_envelope() -> None:
    problem, authority, *_ = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=1)
    result = _stage1_with_v2(problem, authority, policy)
    assert result.plans
    plan = result.plans[0]

    source_by_direction = {
        direction: tuple(
            trip.departure_time // 60
            for trip in sorted(
                (
                    item
                    for item in problem.scenario_b.exact_timetable
                    if item.direction == direction
                ),
                key=lambda item: (item.departure_time, item.trip_id),
            )
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    }
    shift = policy.absolute_max_shift_per_trip_minutes
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        cumulative = 0
        rows = []
        for block in plan.allocation_blocks:
            counts = dict(block.directional_trip_counts)
            if direction in counts:
                rows.append((block, counts[direction]))
        for block, count in sorted(
            rows,
            key=lambda item: (item[0].start_minute, item[0].end_minute, item[0].block_id),
        ):
            cumulative += count
            boundary = block.end_minute
            lower = sum(minute < boundary - shift for minute in source_by_direction[direction])
            upper = sum(minute < boundary + shift for minute in source_by_direction[direction])
            assert lower <= cumulative <= upper


def test_stage1_v2_keeps_directional_regime_count_below_hard_cap() -> None:
    problem, authority, *_ = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(
        maximum_headway_regimes_per_direction=16,
        maximum_stage_1_alternative_plans=1,
    )
    result = _stage1_with_v2(problem, authority, policy)
    assert result.plans
    plan = result.plans[0]
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        regime_count = sum(item.direction == direction for item in plan.proposed_regimes)
        assert regime_count <= policy.maximum_headway_regimes_per_direction


def test_v2_policy_fingerprint_is_versioned_and_reversible() -> None:
    baseline = UniformIntegerRegimePolicyV3().policy_fingerprint
    global_policy_v2.install_global_regularity_v2()
    try:
        installed = UniformIntegerRegimePolicyV3().policy_fingerprint
        assert installed != baseline
    finally:
        global_policy_v2.uninstall_global_regularity_v2()
    assert UniformIntegerRegimePolicyV3().policy_fingerprint == baseline
