"""Phase-aware source slicing for production V3 global regularity.

Global regularity V2 made Stage 1 count paths B-shift-aware, but regime construction still
partitioned Scenario B source trips at the exact cumulative Stage 1 block counts. That was
stricter than the already-authoritative bounded-phase policy: actual block membership may move
by one trip and cumulative phase may move by one trip before returning to zero at the end of
the analytical horizon.

V3 carries that same bounded phase into source-slice construction. It chooses deterministic
per-block realized counts near Scenario B while preserving +/-1 block deviation, +/-1
cumulative deviation, positive-demand service, and zero final drift. Regime-local membership
no longer requires an artificial zero drift at every regime boundary. The cheap necessary
feasibility check uses a bounded CP-SAT projection of the Stage 2 departure domains, exact
uniform regimes, and bounded-phase membership, rather than one fixed Stage 1 planned witness.
It rejects only when that joint subset is proven infeasible. The full operational model remains
Stage 2 authority.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from ortools.sat.python import cp_model

from . import two_stage_allocator as allocator
from . import two_stage_models as models
from . import two_stage_solver as stage2
from . import v3_global_regularity as v1
from . import v3_global_regularity_v2 as v2
from .models import ContractDirection
from .serialization import canonical_sha256

GLOBAL_REGULARITY_POLICY_PROFILE_V3 = "scenario_c_global_regularity_policy_v3"
PHASE_AWARE_SOURCE_SLICING_V3 = True
REGIME_LOCAL_ZERO_DRIFT_REQUIRED_V3 = False
NECESSARY_MEMBERSHIP_USES_DEPARTURE_DOMAINS_V3 = True
NECESSARY_MEMBERSHIP_REQUIRES_UNIFORM_PHASE_REACHABILITY_V3 = True
NECESSARY_UNIFORM_PHASE_SOLVE_LIMIT_SECONDS_V3 = 1.0

_INSTALLED = False
_V2_INITIAL_GROUPS = None
_V2_EXACT_MEMBERSHIP = None
_V2_NECESSARY_FEASIBILITY = None
_V2_POLICY_FINGERPRINT_PROPERTY = None
_V2_ADAPTER_CONTEXT_FINGERPRINT = None


def _policy_fingerprint_payload() -> dict[str, object]:
    return {
        "profile": GLOBAL_REGULARITY_POLICY_PROFILE_V3,
        "phase_aware_source_slicing": PHASE_AWARE_SOURCE_SLICING_V3,
        "block_phase_max_deviation_trips": v1.BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1,
        "cumulative_phase_max_deviation_trips": v1.CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1,
        "regime_local_zero_drift_required": REGIME_LOCAL_ZERO_DRIFT_REQUIRED_V3,
        "full_direction_zero_drift_required": True,
        "necessary_membership_uses_departure_domains": (
            NECESSARY_MEMBERSHIP_USES_DEPARTURE_DOMAINS_V3
        ),
        "necessary_membership_requires_uniform_phase_reachability": (
            NECESSARY_MEMBERSHIP_REQUIRES_UNIFORM_PHASE_REACHABILITY_V3
        ),
        "source_slice_selection": "MINIMIZE_B_BLOCK_COUNT_DEVIATION_THEN_PHASE_MOVEMENT",
    }


def _v3_policy_fingerprint(self) -> str:
    assert _V2_POLICY_FINGERPRINT_PROPERTY is not None
    base_getter = _V2_POLICY_FINGERPRINT_PROPERTY.fget
    assert base_getter is not None
    return canonical_sha256(
        {
            "v2_policy_fingerprint": base_getter(self),
            "phase_aware_source_slicing": _policy_fingerprint_payload(),
        }
    )


def _v3_adapter_context_fingerprint(demand_authority, policy, protected_fingerprint):
    assert _V2_ADAPTER_CONTEXT_FINGERPRINT is not None
    base = _V2_ADAPTER_CONTEXT_FINGERPRINT(
        demand_authority,
        policy,
        protected_fingerprint,
    )
    return canonical_sha256(
        {
            "v2_adapter_context_fingerprint": base,
            "phase_aware_source_slicing": _policy_fingerprint_payload(),
        }
    )


def _realized_block_counts(problem, direction, blocks, allocation) -> tuple[int, ...]:
    """Choose a deterministic full-direction bounded-phase realization close to Scenario B."""
    ordered = tuple(
        sorted(blocks, key=lambda item: (item.start_time, item.end_time, item.block_id))
    )
    if not ordered:
        return ()
    targets = tuple(allocation[(direction, block.block_id)] for block in ordered)
    source_counts = tuple(allocator._source_count(problem, block, direction) for block in ordered)

    # state: cumulative phase delta -> (score tuple, realized counts)
    states: dict[int, tuple[tuple[int, int, tuple[int, ...]], tuple[int, ...]]] = {
        0: ((0, 0, ()), ())
    }
    for block, target, source_count in zip(ordered, targets, source_counts, strict=True):
        next_states: dict[int, tuple[tuple[int, int, tuple[int, ...]], tuple[int, ...]]] = {}
        lower = max(0, target - v1.BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1)
        upper = target + v1.BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1
        if block.observed_passengers > 0 and target > 0:
            lower = max(lower, 1)
        for previous_delta, (previous_score, previous_counts) in states.items():
            for actual in range(lower, upper + 1):
                delta = previous_delta + actual - target
                if abs(delta) > v1.CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1:
                    continue
                counts = (*previous_counts, actual)
                score = (
                    previous_score[0] + abs(actual - source_count),
                    previous_score[1] + abs(actual - target),
                    counts,
                )
                incumbent = next_states.get(delta)
                if incumbent is None or score < incumbent[0]:
                    next_states[delta] = (score, counts)
        states = next_states
        if not states:
            return targets
    final = states.get(0)
    return final[1] if final is not None else targets


def _phase_aware_initial_groups(problem, allocation, blocks, final_service_sentinels):
    output: dict[ContractDirection, list[allocator._RegimeGroup]] = {}
    sentinel_by_direction = {item.direction: item for item in final_service_sentinels}
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        compatible = tuple(
            block for block in blocks if block.direction in {direction, ContractDirection.COMBINED}
        )
        ordered = tuple(
            sorted(compatible, key=lambda item: (item.start_time, item.end_time, item.block_id))
        )
        realized = _realized_block_counts(problem, direction, ordered, allocation)
        nonzero = tuple(
            (block, count) for block, count in zip(ordered, realized, strict=True) if count > 0
        )
        cursor = 0
        groups: list[allocator._RegimeGroup] = []
        for index, (block, count) in enumerate(nonzero):
            groups.append(
                allocator._RegimeGroup(
                    direction=direction,
                    blocks=(block,),
                    trip_count=count,
                    source_start_index=cursor,
                    source_end_index=cursor + count - 1,
                    is_final_service_tail=index == len(nonzero) - 1,
                    has_final_service_sentinel=False,
                )
            )
            cursor += count
        sentinel = sentinel_by_direction.get(direction)
        if sentinel is not None:
            if groups:
                last = groups[-1]
                groups[-1] = replace(
                    last,
                    trip_count=last.trip_count + 1,
                    source_end_index=last.source_end_index + 1,
                    is_final_service_tail=True,
                    has_final_service_sentinel=True,
                )
            elif ordered:
                groups.append(
                    allocator._RegimeGroup(
                        direction=direction,
                        blocks=(ordered[-1],),
                        trip_count=1,
                        source_start_index=0,
                        source_end_index=0,
                        is_final_service_tail=True,
                        has_final_service_sentinel=True,
                    )
                )
            cursor += 1
        if cursor != allocator._direction_total(problem, direction):
            # This should be unreachable because realized counts have zero final drift.
            assert _V2_INITIAL_GROUPS is not None
            return _V2_INITIAL_GROUPS(problem, allocation, blocks, final_service_sentinels)
        output[direction] = groups
    return output


def _regime_local_phase_ok(representation, group, allocation) -> bool:
    """Check block phase locally; full cumulative authority is enforced after all regimes exist."""
    for block in sorted(
        group.blocks, key=lambda item: (item.start_time, item.end_time, item.block_id)
    ):
        target = allocation[(group.direction, block.block_id)]
        actual = sum(
            block.start_time // 60 <= minute < block.end_time // 60
            for minute in representation.departure_minutes
        )
        if abs(actual - target) > v1.BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1:
            return False
        if block.observed_passengers > 0 and target > 0 and actual == 0:
            return False
    return len(representation.departure_minutes) == group.trip_count


def _phase_aware_membership_representation(candidates, group, allocation):
    return next(
        (
            representation
            for representation in candidates
            if _regime_local_phase_ok(representation, group, allocation)
        ),
        None,
    )


def _uniform_phase_membership_reachability(
    problem,
    allocation_blocks,
    regimes,
    final_service_sentinels,
    policy,
) -> bool | None:
    """Prove or find joint uniform-regime and bounded-phase domain reachability.

    ``False`` is a safe necessary-feasibility rejection because this model is a strict subset
    of Stage 2 hard constraints. ``None`` means the bounded diagnostic solve was inconclusive
    and must never reject a candidate.
    """
    domains, domain_failures = allocator._necessary_departure_domains(
        problem,
        regimes,
        final_service_sentinels,
        policy,
    )
    if domain_failures or len(domains) != problem.scenario_b.total_daily_trips:
        return False
    source_ids_by_regime = allocator._source_ids_by_regime(problem, regimes)
    if not source_ids_by_regime:
        return False

    model = cp_model.CpModel()
    departures = {
        trip.trip_id: model.new_int_var(
            domains[trip.trip_id][0],
            domains[trip.trip_id][1],
            f"v3_necessary_departure_{trip.trip_id}",
        )
        for trip in problem.scenario_b.exact_timetable
    }
    directional = allocator._ordered_directional_trips(problem)
    for trips in directional.values():
        model.add(departures[trips[0].trip_id] == trips[0].departure_time // 60)
        model.add(departures[trips[-1].trip_id] == trips[-1].departure_time // 60)
        for earlier, later in zip(trips, trips[1:], strict=False):
            model.add(
                departures[later.trip_id] - departures[earlier.trip_id]
                >= policy.minimum_operational_headway_minutes
            )

    for regime in regimes:
        source_ids = source_ids_by_regime[regime.regime_id]
        first = departures[source_ids[0]]
        last = departures[source_ids[-1]]
        model.add(first >= regime.permitted_start_window[0])
        model.add(first <= regime.permitted_start_window[1])
        model.add(last >= regime.permitted_end_window[0])
        model.add(last <= regime.permitted_end_window[1])
        if regime.trip_count >= 2:
            headway = model.new_int_var(
                regime.minimum_headway_minutes,
                regime.maximum_headway_minutes,
                f"v3_necessary_uniform_headway_{regime.regime_id}",
            )
            for earlier_id, later_id in zip(source_ids, source_ids[1:], strict=False):
                model.add(departures[later_id] - departures[earlier_id] == headway)

    v1._add_bounded_phase_block_membership_constraints(
        model,
        problem,
        SimpleNamespace(allocation_blocks=allocation_blocks),
        departures,
    )
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = NECESSARY_UNIFORM_PHASE_SOLVE_LIMIT_SECONDS_V3
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(model)
    if status == cp_model.INFEASIBLE:
        return False
    if status in {cp_model.OPTIMAL, cp_model.FEASIBLE}:
        return True
    return None


def _phase_aware_necessary_feasibility(
    problem,
    allocation,
    allocation_blocks,
    regimes,
    final_service_sentinels,
    policy,
):
    """Keep every V2 necessary failure except a false fixed-witness membership rejection."""
    assert _V2_NECESSARY_FEASIBILITY is not None
    result = _V2_NECESSARY_FEASIBILITY(
        problem,
        allocation,
        allocation_blocks,
        regimes,
        final_service_sentinels,
        policy,
    )
    membership = models.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP
    if result.passed or membership not in result.constraint_families:
        return result
    reachability = _uniform_phase_membership_reachability(
        problem,
        allocation_blocks,
        regimes,
        final_service_sentinels,
        policy,
    )
    if reachability is False:
        families = tuple(
            sorted(
                {
                    *result.constraint_families,
                    models.Stage2ConstraintFamilyV1.UNIFORM_HEADWAY,
                },
                key=lambda item: item.value,
            )
        )
        return allocator.finalize_stage_1_necessary_feasibility(
            replace(
                result,
                passed=False,
                constraint_families=families,
                explanation=(
                    "Stage 1 plan cannot jointly satisfy exact uniform headways, B-anchored "
                    "departure domains, and bounded full-direction phase membership."
                ),
                diagnostic_fingerprint="",
            )
        )

    remaining = tuple(item for item in result.constraint_families if item != membership)
    passed = not remaining
    explanation = (
        "Stage 1 plan passed joint uniform-regime and bounded-phase domain reachability; full "
        "operational feasibility remains Stage 2 CP-SAT authority."
        if passed
        else "Stage 1 planned witness was phase-inexact but joint uniform-regime and bounded-"
        "phase domain reachability was not disproven; remaining necessary failures: "
        + ", ".join(item.value for item in remaining)
        + "."
    )
    return allocator.finalize_stage_1_necessary_feasibility(
        models.Stage1NecessaryFeasibilityResultV1(
            allocation_candidate_fingerprint=result.allocation_candidate_fingerprint,
            passed=passed,
            constraint_families=remaining,
            fleet_lower_bound=result.fleet_lower_bound,
            explanation=explanation,
            diagnostic_fingerprint="",
        )
    )


def install_global_regularity_v3() -> None:
    """Install V2 plus bounded-phase-aware source slicing and necessary feasibility."""
    global _INSTALLED
    global _V2_ADAPTER_CONTEXT_FINGERPRINT
    global _V2_EXACT_MEMBERSHIP
    global _V2_INITIAL_GROUPS
    global _V2_NECESSARY_FEASIBILITY
    global _V2_POLICY_FINGERPRINT_PROPERTY
    if _INSTALLED:
        return
    v2.install_global_regularity_v2()
    _V2_INITIAL_GROUPS = allocator._initial_groups
    _V2_EXACT_MEMBERSHIP = allocator._exact_membership_representation
    _V2_NECESSARY_FEASIBILITY = allocator.evaluate_stage_1_necessary_feasibility_v1
    _V2_POLICY_FINGERPRINT_PROPERTY = models.UniformIntegerRegimePolicyV3.policy_fingerprint
    _V2_ADAPTER_CONTEXT_FINGERPRINT = stage2._adapter_context_fingerprint

    allocator._initial_groups = _phase_aware_initial_groups
    allocator._exact_membership_representation = _phase_aware_membership_representation
    allocator.evaluate_stage_1_necessary_feasibility_v1 = _phase_aware_necessary_feasibility
    models.UniformIntegerRegimePolicyV3.policy_fingerprint = property(_v3_policy_fingerprint)
    stage2._adapter_context_fingerprint = _v3_adapter_context_fingerprint
    _INSTALLED = True


def uninstall_global_regularity_v3() -> None:
    """Restore V2 hooks, then restore baseline through V2's uninstaller."""
    global _INSTALLED
    global _V2_ADAPTER_CONTEXT_FINGERPRINT
    global _V2_EXACT_MEMBERSHIP
    global _V2_INITIAL_GROUPS
    global _V2_NECESSARY_FEASIBILITY
    global _V2_POLICY_FINGERPRINT_PROPERTY
    if not _INSTALLED:
        return
    assert _V2_INITIAL_GROUPS is not None
    assert _V2_EXACT_MEMBERSHIP is not None
    assert _V2_NECESSARY_FEASIBILITY is not None
    assert _V2_POLICY_FINGERPRINT_PROPERTY is not None
    assert _V2_ADAPTER_CONTEXT_FINGERPRINT is not None
    allocator._initial_groups = _V2_INITIAL_GROUPS
    allocator._exact_membership_representation = _V2_EXACT_MEMBERSHIP
    allocator.evaluate_stage_1_necessary_feasibility_v1 = _V2_NECESSARY_FEASIBILITY
    models.UniformIntegerRegimePolicyV3.policy_fingerprint = _V2_POLICY_FINGERPRINT_PROPERTY
    stage2._adapter_context_fingerprint = _V2_ADAPTER_CONTEXT_FINGERPRINT
    _INSTALLED = False
    v2.uninstall_global_regularity_v2()
    _V2_INITIAL_GROUPS = None
    _V2_EXACT_MEMBERSHIP = None
    _V2_NECESSARY_FEASIBILITY = None
    _V2_POLICY_FINGERPRINT_PROPERTY = None
    _V2_ADAPTER_CONTEXT_FINGERPRINT = None


__all__ = [
    "GLOBAL_REGULARITY_POLICY_PROFILE_V3",
    "NECESSARY_MEMBERSHIP_REQUIRES_UNIFORM_PHASE_REACHABILITY_V3",
    "NECESSARY_MEMBERSHIP_USES_DEPARTURE_DOMAINS_V3",
    "NECESSARY_UNIFORM_PHASE_SOLVE_LIMIT_SECONDS_V3",
    "PHASE_AWARE_SOURCE_SLICING_V3",
    "REGIME_LOCAL_ZERO_DRIFT_REQUIRED_V3",
    "install_global_regularity_v3",
    "uninstall_global_regularity_v3",
]
