from __future__ import annotations

from types import SimpleNamespace

import pytest

from bus_schedule_engine.contracts_v1 import (
    ContractDirection,
    UniformIntegerRegimePolicyV3,
    allocate_trips_stage_1_v1,
    solve_exact_timetable_stage_2_v1,
)
from bus_schedule_engine.contracts_v1 import v3_global_regularity as global_policy
from bus_schedule_engine.models import Direction
from test_contract_v1_two_stage_allocator import (
    _dense_half_hour_stage1_request,
    _record,
    _stage1_request,
)


@pytest.fixture()
def installed_global_policy():
    global_policy.install_global_regularity_v1()
    try:
        yield
    finally:
        global_policy.uninstall_global_regularity_v1()


def _first_feasible_candidate(problem, authority, policy):
    stage_1 = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=policy,
        time_limit_seconds=4.0,
    )
    assert stage_1.plans
    for plan in stage_1.plans:
        stage_2 = solve_exact_timetable_stage_2_v1(
            problem,
            plan,
            policy=policy,
            time_limit_seconds=3.0,
        )
        if stage_2.candidate is not None:
            return plan, stage_2.candidate
    pytest.fail("expected one globally regular Stage 2 candidate")


def test_largest_remainder_targets_follow_passenger_volume() -> None:
    rows = (
        SimpleNamespace(block_id="low-1", start_time=0, end_time=1800, observed_passengers=10),
        SimpleNamespace(block_id="peak", start_time=1800, end_time=3600, observed_passengers=80),
        SimpleNamespace(block_id="low-2", start_time=3600, end_time=5400, observed_passengers=10),
    )

    targets = global_policy._largest_remainder_targets(rows, 10)

    assert targets == {"low-1": 1, "peak": 8, "low-2": 1}


def test_surplus_fixed_trips_follow_demand_after_service_floors(
    installed_global_policy,
) -> None:
    outbound = (300, 315, 330, 345, 360, 375, 390, 405)
    inbound = (305, 320, 335, 350, 365, 380, 395, 410)
    problem, authority, *_ = _stage1_request(
        outbound=outbound,
        inbound=inbound,
        demand=(
            _record(Direction.TERMINAL_1_TO_2, 300, 340, 15),
            _record(Direction.TERMINAL_1_TO_2, 340, 380, 255),
            _record(Direction.TERMINAL_1_TO_2, 380, 420, 5),
            _record(Direction.TERMINAL_2_TO_1, 305, 345, 15),
            _record(Direction.TERMINAL_2_TO_1, 345, 385, 255),
            _record(Direction.TERMINAL_2_TO_1, 385, 425, 5),
        ),
    )
    result = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=1),
        time_limit_seconds=4.0,
    )

    assert result.plans
    plan = result.plans[0]
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        rows = sorted(
            (block for block in plan.allocation_blocks if block.direction == direction),
            key=lambda item: item.start_minute,
        )
        assert len(rows) == 3
        assert rows[1].observed_passengers > rows[2].observed_passengers
        assert rows[1].trip_count > rows[2].trip_count


def test_sixteen_regimes_is_a_cap_not_a_coarsening_target(installed_global_policy) -> None:
    problem, authority, *_ = _dense_half_hour_stage1_request(block_count=18)
    policy = UniformIntegerRegimePolicyV3(
        maximum_headway_regimes_per_direction=16,
        maximum_stage_1_alternative_plans=1,
    )
    result = allocate_trips_stage_1_v1(
        problem,
        authority,
        policy=policy,
        time_limit_seconds=5.0,
    )

    assert result.plans
    plan = result.plans[0]
    counts = {
        direction: sum(regime.direction == direction for regime in plan.proposed_regimes)
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    }
    assert all(value < policy.maximum_headway_regimes_per_direction for value in counts.values())
    assert any(
        len(regime.covered_demand_block_ids) >= 3
        for regime in plan.proposed_regimes
        if not regime.is_final_service_tail
    )


def test_declining_tail_cannot_be_denser_than_previous_regime(installed_global_policy) -> None:
    problem, authority, *_ = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(
        maximum_stage_1_alternative_plans=4,
        maximum_transition_jump_minutes=30,
    )
    plan, candidate = _first_feasible_candidate(problem, authority, policy)
    raw = {item.regime_id: item for item in candidate.headway_regimes}

    checked = 0
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        regimes = sorted(
            (item for item in plan.proposed_regimes if item.direction == direction),
            key=lambda item: item.planned_start_minute,
        )
        assert regimes[-1].is_final_service_tail
        if len(regimes) < 2:
            continue
        earlier, tail = regimes[-2:]
        earlier_raw = raw[earlier.regime_id]
        tail_raw = raw[tail.regime_id]
        if earlier_raw.actual_headway_sequence and tail_raw.actual_headway_sequence:
            if global_policy._tail_demand_not_rising(problem, earlier, tail):
                assert tail_raw.actual_headway_sequence[0] >= earlier_raw.actual_headway_sequence[0]
                checked += 1
    assert checked >= 1


def test_global_transition_jump_is_not_worse_than_scenario_b(installed_global_policy) -> None:
    problem, authority, *_ = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(
        maximum_stage_1_alternative_plans=4,
        maximum_transition_jump_minutes=30,
    )
    plan, candidate = _first_feasible_candidate(problem, authority, policy)
    raw = {item.regime_id: item for item in candidate.headway_regimes}
    cap = global_policy._scenario_b_max_headway_change(problem)

    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        regimes = sorted(
            (item for item in plan.proposed_regimes if item.direction == direction),
            key=lambda item: item.planned_start_minute,
        )
        members_by_id = {
            regime.regime_id: sorted(
                (
                    trip
                    for trip in candidate.exact_timetable
                    if trip.headway_regime_id == regime.regime_id
                ),
                key=lambda item: item.c_departure_time,
            )
            for regime in regimes
        }
        for earlier, later in zip(regimes, regimes[1:], strict=False):
            transition = (
                members_by_id[later.regime_id][0].c_departure_time
                - members_by_id[earlier.regime_id][-1].c_departure_time
            ) // 60
            for regime in (earlier, later):
                sequence = raw[regime.regime_id].actual_headway_sequence
                if sequence:
                    assert abs(transition - sequence[0]) <= cap


def test_bounded_phase_acceptance_allows_one_trip_boundary_movement() -> None:
    blocks = (
        SimpleNamespace(
            block_id="A",
            start_minute=300,
            end_minute=330,
            observed_passengers=20.0,
            directional_trip_counts=((ContractDirection.OUTBOUND, 2),),
        ),
        SimpleNamespace(
            block_id="B",
            start_minute=330,
            end_minute=360,
            observed_passengers=20.0,
            directional_trip_counts=((ContractDirection.OUTBOUND, 2),),
        ),
    )
    candidate = SimpleNamespace(
        exact_timetable=(
            SimpleNamespace(direction=ContractDirection.OUTBOUND, c_departure_time=310 * 60),
            SimpleNamespace(direction=ContractDirection.OUTBOUND, c_departure_time=330 * 60),
            SimpleNamespace(direction=ContractDirection.OUTBOUND, c_departure_time=340 * 60),
            SimpleNamespace(direction=ContractDirection.OUTBOUND, c_departure_time=350 * 60),
        )
    )
    plan = SimpleNamespace(allocation_blocks=blocks)

    assert global_policy._candidate_bounded_phase_ok(candidate, plan)


def test_policy_fingerprint_binds_global_regularity_semantics(installed_global_policy) -> None:
    policy = UniformIntegerRegimePolicyV3()
    base_getter = global_policy._ORIGINAL_POLICY_FINGERPRINT_PROPERTY.fget
    assert base_getter is not None

    assert len(policy.policy_fingerprint) == 64
    assert policy.policy_fingerprint != base_getter(policy)
