"""Representability-aware Stage 1 authority for production V3 global regularity.

V1 made timetable-wide regularity explicit, but real MST6 review showed that Stage 1 could
still spend its bounded solve budget producing passenger-optimal allocation vectors that could
not be mapped back to Scenario B within the hard +/-30 minute trip-shift domain or coarsened
under the 16-regime cap.

V2 keeps every V1 hard operating rule and adds cheap necessary structure before regime build:

* passenger-proportional targets become a bounded allocation envelope rather than a strict
  lexicographic optimum;
* cumulative departure counts at every analytical boundary must lie inside the envelope that
  one-to-one B-anchored trips can reach under the configured maximum shift;
* per-direction service-rate change points are bounded by the regime cap and minimized before
  residual passenger-target error;
* Scenario B block counts are supplied only as CP-SAT hints, never as constraints.

The policy remains explicitly installed only for the production V3 runner and is fully
reversible for test isolation.
"""

from __future__ import annotations

from dataclasses import replace

from . import two_stage_allocator as allocator
from . import two_stage_models as models
from . import two_stage_solver as stage2
from . import v3_global_regularity as v1
from .models import ContractDirection
from .serialization import canonical_sha256

GLOBAL_REGULARITY_POLICY_PROFILE_V2 = "scenario_c_global_regularity_policy_v2"
PASSENGER_TARGET_ENVELOPE_TRIPS_V2 = 1
B_SHIFT_CUMULATIVE_ENVELOPE_V2 = True
PER_DIRECTION_CHANGE_POINT_CAP_V2 = True

_INSTALLED = False
_V1_BUILD_ALLOCATION_MODEL = None
_V1_POLICY_FINGERPRINT_PROPERTY = None
_V1_ADAPTER_CONTEXT_FINGERPRINT = None


def _policy_fingerprint_payload() -> dict[str, object]:
    return {
        "profile": GLOBAL_REGULARITY_POLICY_PROFILE_V2,
        "passenger_target_envelope_trips": PASSENGER_TARGET_ENVELOPE_TRIPS_V2,
        "b_shift_cumulative_envelope": B_SHIFT_CUMULATIVE_ENVELOPE_V2,
        "per_direction_change_point_cap": PER_DIRECTION_CHANGE_POINT_CAP_V2,
        "objective_order": (
            "NO_SERVICE",
            "CRITICAL_SHORTAGE",
            "PLANNING_SHORTAGE",
            "PER_DIRECTION_SERVICE_CHANGE_POINTS",
            "B_CONTINUITY",
            "PASSENGER_TARGET_ERROR",
        ),
    }


def _v2_policy_fingerprint(self) -> str:
    assert _V1_POLICY_FINGERPRINT_PROPERTY is not None
    base_getter = _V1_POLICY_FINGERPRINT_PROPERTY.fget
    assert base_getter is not None
    return canonical_sha256(
        {
            "v1_policy_fingerprint": base_getter(self),
            "representability_aware_stage_1": _policy_fingerprint_payload(),
        }
    )


def _v2_adapter_context_fingerprint(demand_authority, policy, protected_fingerprint):
    assert _V1_ADAPTER_CONTEXT_FINGERPRINT is not None
    base = _V1_ADAPTER_CONTEXT_FINGERPRINT(
        demand_authority,
        policy,
        protected_fingerprint,
    )
    return canonical_sha256(
        {
            "v1_adapter_context_fingerprint": base,
            "representability_aware_stage_1": _policy_fingerprint_payload(),
        }
    )


def _protected_floor_for_stream(bundle, direction, block_id: str) -> int:
    if direction == ContractDirection.COMBINED:
        return sum(
            bundle.protected_minimum_by_direction_and_block.get((candidate, block_id), 0)
            for candidate in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
        )
    return bundle.protected_minimum_by_direction_and_block.get((direction, block_id), 0)


def _final_tail_floor_for_stream(bundle, policy, direction, row, rows) -> int:
    last_block = max(rows, key=lambda item: (item.end_time, item.block_id))
    if row.block_id != last_block.block_id:
        return 0
    sentinel_directions = {item.direction for item in bundle.final_service_sentinels}
    minimum = policy.final_service_tail.final_service_tail_minimum_trip_count
    if direction == ContractDirection.COMBINED:
        return sum(
            max(0, minimum - int(candidate in sentinel_directions))
            for candidate in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
        )
    return max(0, minimum - int(direction in sentinel_directions))


def _add_passenger_target_envelopes(problem, bundle, policy) -> None:
    requirements = {item.block_id: item for item in problem.block_requirements}
    total_trips = problem.scenario_b.total_daily_trips
    for direction, rows, analytical_total in v1._demand_target_streams(problem, bundle):
        observed_total = sum(float(row.observed_passengers) for row in rows)
        targets = (
            v1._largest_remainder_targets(rows, analytical_total)
            if observed_total > 0
            else v1._fallback_source_targets(problem, direction, rows)
        )
        for row in rows:
            aggregate = v1._aggregate_count_var(
                bundle.model,
                bundle.count_by_direction_and_block,
                direction,
                row,
                total_trips,
            )
            target = targets[row.block_id]
            planning_floor = requirements[row.block_id].required_trips_85
            protected_floor = _protected_floor_for_stream(bundle, direction, row.block_id)
            final_tail_floor = _final_tail_floor_for_stream(
                bundle,
                policy,
                direction,
                row,
                rows,
            )
            lower = max(0, target - PASSENGER_TARGET_ENVELOPE_TRIPS_V2)
            upper = max(
                target + PASSENGER_TARGET_ENVELOPE_TRIPS_V2,
                planning_floor,
                protected_floor,
                final_tail_floor,
            )
            bundle.model.add(aggregate >= lower)
            bundle.model.add(aggregate <= upper)


def _source_minutes(problem, direction: ContractDirection) -> tuple[int, ...]:
    return tuple(
        trip.departure_time // 60
        for trip in allocator._ordered_directional_trips(problem)[direction]
    )


def _add_b_shift_cumulative_envelopes(problem, bundle, policy) -> None:
    """Add necessary cumulative-count conditions implied by one-to-one B +/- shift mapping."""
    shift = policy.absolute_max_shift_per_trip_minutes
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        blocks = sorted(
            (
                block
                for block in bundle.blocks
                if block.direction in {direction, ContractDirection.COMBINED}
            ),
            key=lambda item: (item.start_time, item.end_time, item.block_id),
        )
        if not blocks:
            continue
        source_minutes = _source_minutes(problem, direction)
        cumulative = []
        for block in blocks:
            cumulative.append(bundle.count_by_direction_and_block[(direction, block.block_id)])
            boundary = block.end_time // 60
            lower = sum(minute < boundary - shift for minute in source_minutes)
            upper = sum(minute < boundary + shift for minute in source_minutes)
            prefix = sum(cumulative)
            bundle.model.add(prefix >= lower)
            bundle.model.add(prefix <= upper)


def _service_change_terms(problem, bundle, policy):
    """Return per-direction service-rate change booleans and impose the regime-count proxy cap."""
    del problem
    changes = []
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        blocks = sorted(
            (
                block
                for block in bundle.blocks
                if block.direction in {direction, ContractDirection.COMBINED}
            ),
            key=lambda item: (item.start_time, item.end_time, item.block_id),
        )
        directional_changes = []
        for index, (left_block, right_block) in enumerate(
            zip(blocks, blocks[1:], strict=False),
            start=1,
        ):
            left = bundle.count_by_direction_and_block[(direction, left_block.block_id)]
            right = bundle.count_by_direction_and_block[(direction, right_block.block_id)]
            changed = bundle.model.new_bool_var(
                f"stage1_v2_rate_change_{direction.value}_{index:04d}"
            )
            rate_delta = left * right_block.duration_minutes - right * left_block.duration_minutes
            bundle.model.add(rate_delta != 0).only_enforce_if(changed)
            bundle.model.add(rate_delta == 0).only_enforce_if(changed.negated())
            directional_changes.append(changed)
            changes.append(changed)
        maximum_changes = max(0, policy.maximum_headway_regimes_per_direction - 1)
        if directional_changes:
            bundle.model.add(sum(directional_changes) <= maximum_changes)
    bound = len(changes)
    term = allocator._bounded_sum(
        bundle.model,
        changes,
        upper_bound=bound,
        name="stage1_v2_directional_service_change_points",
    )
    return term, bound


def _add_b_hints(problem, bundle) -> None:
    blocks_by_id = {item.block_id: item for item in bundle.blocks}
    for (direction, block_id), variable in bundle.count_by_direction_and_block.items():
        source_count = allocator._source_count(problem, blocks_by_id[block_id], direction)
        bundle.model.add_hint(variable, source_count)


def _representability_aware_build_model(problem, authority, policy, protected_authority):
    assert _V1_BUILD_ALLOCATION_MODEL is not None
    bundle = _V1_BUILD_ALLOCATION_MODEL(problem, authority, policy, protected_authority)
    _add_passenger_target_envelopes(problem, bundle, policy)
    _add_b_shift_cumulative_envelopes(problem, bundle, policy)
    _add_b_hints(problem, bundle)
    change_term, change_bound = _service_change_terms(problem, bundle, policy)

    # V1 objective terms are:
    # 0 no-service, 1 critical shortage, 2 planning shortage,
    # 3 passenger target error, 4 aggregate change points, 5 B continuity.
    old_terms = bundle.objective_terms
    old_bounds = bundle.objective_term_bounds
    if len(old_terms) != 6 or len(old_bounds) != 6:
        raise allocator.Stage1AllocationError(
            allocator.STAGE_1_PROBLEM_AUTHORITY_MISMATCH,
            "V2 representability-aware Stage 1 requires the V1 six-term objective contract",
        )
    terms = (
        old_terms[0],
        old_terms[1],
        old_terms[2],
        change_term,
        old_terms[5],
        old_terms[3],
    )
    bounds = (
        old_bounds[0],
        old_bounds[1],
        old_bounds[2],
        change_bound,
        old_bounds[5],
        old_bounds[3],
    )
    weights = allocator._lexicographic_weights(bounds)
    theoretical_maximum = sum(bound * weight for bound, weight in zip(bounds, weights, strict=True))
    if theoretical_maximum > 2**63 - 1:
        raise allocator.Stage1AllocationError(
            allocator.STAGE_1_PROBLEM_AUTHORITY_MISMATCH,
            "V2 representability-aware Stage 1 objective exceeds signed-int64 authority",
        )
    bundle.model.minimize(sum(term * weight for term, weight in zip(terms, weights, strict=True)))
    return replace(bundle, objective_terms=terms, objective_term_bounds=bounds)


def install_global_regularity_v2() -> None:
    """Install V1 global regularity plus representability-aware Stage 1."""
    global _INSTALLED
    global _V1_ADAPTER_CONTEXT_FINGERPRINT
    global _V1_BUILD_ALLOCATION_MODEL
    global _V1_POLICY_FINGERPRINT_PROPERTY
    if _INSTALLED:
        return
    v1.install_global_regularity_v1()
    _V1_BUILD_ALLOCATION_MODEL = allocator._build_allocation_model
    _V1_POLICY_FINGERPRINT_PROPERTY = models.UniformIntegerRegimePolicyV3.policy_fingerprint
    _V1_ADAPTER_CONTEXT_FINGERPRINT = stage2._adapter_context_fingerprint

    allocator._build_allocation_model = _representability_aware_build_model
    models.UniformIntegerRegimePolicyV3.policy_fingerprint = property(_v2_policy_fingerprint)
    stage2._adapter_context_fingerprint = _v2_adapter_context_fingerprint
    _INSTALLED = True


def uninstall_global_regularity_v2() -> None:
    """Restore V1 hooks, then restore the baseline through V1's uninstaller."""
    global _INSTALLED
    global _V1_ADAPTER_CONTEXT_FINGERPRINT
    global _V1_BUILD_ALLOCATION_MODEL
    global _V1_POLICY_FINGERPRINT_PROPERTY
    if not _INSTALLED:
        return
    assert _V1_BUILD_ALLOCATION_MODEL is not None
    assert _V1_POLICY_FINGERPRINT_PROPERTY is not None
    assert _V1_ADAPTER_CONTEXT_FINGERPRINT is not None
    allocator._build_allocation_model = _V1_BUILD_ALLOCATION_MODEL
    models.UniformIntegerRegimePolicyV3.policy_fingerprint = _V1_POLICY_FINGERPRINT_PROPERTY
    stage2._adapter_context_fingerprint = _V1_ADAPTER_CONTEXT_FINGERPRINT
    _INSTALLED = False
    v1.uninstall_global_regularity_v1()
    _V1_BUILD_ALLOCATION_MODEL = None
    _V1_POLICY_FINGERPRINT_PROPERTY = None
    _V1_ADAPTER_CONTEXT_FINGERPRINT = None


__all__ = [
    "B_SHIFT_CUMULATIVE_ENVELOPE_V2",
    "GLOBAL_REGULARITY_POLICY_PROFILE_V2",
    "PASSENGER_TARGET_ENVELOPE_TRIPS_V2",
    "PER_DIRECTION_CHANGE_POINT_CAP_V2",
    "install_global_regularity_v2",
    "uninstall_global_regularity_v2",
]
