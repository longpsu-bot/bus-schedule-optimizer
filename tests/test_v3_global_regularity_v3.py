from __future__ import annotations

from types import SimpleNamespace

from test_contract_v1_two_stage_allocator import _stage1_request

from bus_schedule_engine.contracts_v1 import (
    ContractDirection,
    UniformIntegerRegimePolicyV3,
    allocate_trips_stage_1_v1,
)
from bus_schedule_engine.contracts_v1 import v3_global_regularity_v3 as global_policy_v3


def test_phase_realization_can_carry_one_trip_across_block_boundary_and_return_to_zero() -> None:
    problem, *_ = _stage1_request()
    direction = ContractDirection.OUTBOUND
    blocks = tuple(
        sorted(
            (item for item in problem.analysis_blocks if item.direction == direction),
            key=lambda item: (item.start_time, item.end_time, item.block_id),
        )
    )
    assert len(blocks) == 2
    allocation = {
        (direction, blocks[0].block_id): 3,
        (direction, blocks[1].block_id): 1,
    }

    realized = global_policy_v3._realized_block_counts(problem, direction, blocks, allocation)

    assert realized == (2, 2)
    assert abs(realized[0] - 3) == 1
    assert sum(realized) == 4


def test_regime_local_membership_does_not_force_zero_phase_at_every_regime_boundary() -> None:
    problem, *_ = _stage1_request()
    direction = ContractDirection.OUTBOUND
    block = next(item for item in problem.analysis_blocks if item.direction == direction)
    representation = SimpleNamespace(departure_minutes=(360, 380))
    group = SimpleNamespace(direction=direction, blocks=(block,), trip_count=2)
    allocation = {(direction, block.block_id): 3}

    assert global_policy_v3._regime_local_phase_ok(representation, group, allocation)


def test_stage1_v3_builds_with_full_direction_phase_authority() -> None:
    problem, authority, *_ = _stage1_request()
    policy = UniformIntegerRegimePolicyV3(maximum_stage_1_alternative_plans=1)
    global_policy_v3.install_global_regularity_v3()
    try:
        result = allocate_trips_stage_1_v1(
            problem,
            authority,
            policy=policy,
            time_limit_seconds=4.0,
        )
    finally:
        global_policy_v3.uninstall_global_regularity_v3()

    assert result.plans
    assert result.plans[0].necessary_feasibility.passed


def _necessary_result(*families):
    return global_policy_v3.allocator.finalize_stage_1_necessary_feasibility(
        global_policy_v3.models.Stage1NecessaryFeasibilityResultV1(
            allocation_candidate_fingerprint="candidate",
            passed=False,
            constraint_families=tuple(families),
            fleet_lower_bound=None,
            explanation="fixed Stage 1 witness failed a cheap necessary check",
            diagnostic_fingerprint="",
        )
    )


def test_uniform_phase_reachable_membership_is_deferred_to_stage2(monkeypatch) -> None:
    membership = global_policy_v3.models.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP
    base = _necessary_result(membership)
    monkeypatch.setattr(global_policy_v3, "_V2_NECESSARY_FEASIBILITY", lambda *args: base)
    monkeypatch.setattr(
        global_policy_v3,
        "_uniform_phase_membership_reachability",
        lambda *args: True,
    )

    result = global_policy_v3._phase_aware_necessary_feasibility(
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert result.passed
    assert result.constraint_families == ()
    assert "Stage 2 CP-SAT authority" in result.explanation


def test_uniform_phase_reachable_membership_does_not_clear_other_failures(monkeypatch) -> None:
    membership = global_policy_v3.models.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP
    fleet = global_policy_v3.models.Stage2ConstraintFamilyV1.FLEET
    base = _necessary_result(membership, fleet)
    monkeypatch.setattr(global_policy_v3, "_V2_NECESSARY_FEASIBILITY", lambda *args: base)
    monkeypatch.setattr(
        global_policy_v3,
        "_uniform_phase_membership_reachability",
        lambda *args: True,
    )

    result = global_policy_v3._phase_aware_necessary_feasibility(
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert not result.passed
    assert result.constraint_families == (fleet,)


def test_uniform_phase_infeasibility_remains_a_necessary_rejection(monkeypatch) -> None:
    membership = global_policy_v3.models.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP
    uniform = global_policy_v3.models.Stage2ConstraintFamilyV1.UNIFORM_HEADWAY
    base = _necessary_result(membership)
    monkeypatch.setattr(global_policy_v3, "_V2_NECESSARY_FEASIBILITY", lambda *args: base)
    monkeypatch.setattr(
        global_policy_v3,
        "_uniform_phase_membership_reachability",
        lambda *args: False,
    )

    result = global_policy_v3._phase_aware_necessary_feasibility(
        None,
        None,
        None,
        None,
        None,
        None,
    )

    assert not result.passed
    assert result.constraint_families == (membership, uniform)
    assert "cannot jointly satisfy" in result.explanation


def test_v3_policy_fingerprint_is_versioned_and_reversible() -> None:
    baseline = UniformIntegerRegimePolicyV3().policy_fingerprint
    global_policy_v3.install_global_regularity_v3()
    try:
        installed = UniformIntegerRegimePolicyV3().policy_fingerprint
        assert installed != baseline
    finally:
        global_policy_v3.uninstall_global_regularity_v3()
    assert UniformIntegerRegimePolicyV3().policy_fingerprint == baseline
