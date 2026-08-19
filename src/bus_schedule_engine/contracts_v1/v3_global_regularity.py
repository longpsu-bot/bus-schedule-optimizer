"""Production V3 global-regularity policy installation.

This module promotes the real-route bounded-phase findings into the production V3 path and
adds timetable-wide regularity authority.  The installer is explicit and idempotent so tests
can install/uninstall it without mutating unrelated solver behavior.

Policy order:

1. preserve the existing no-service / critical / planning shortage priorities;
2. allocate remaining fixed trips toward continuous passenger demand rather than treating the
   85-percent planning floor as a symmetric target;
3. minimize service-level change points and change magnitude;
4. preserve Scenario B continuity;
5. coarsen adjacent representable regimes to a fixed point (16 remains a cap, not a target);
6. allow bounded +/-1 statistical 30-minute phase movement with zero full-horizon drift;
7. do not allow Scenario C regime-transition jumps to exceed Scenario B's observed maximum;
8. when final-tail demand is not rising, the final-tail headway may not be shorter than the
   preceding measurable regime.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from fractions import Fraction

from . import solver_validation
from . import two_stage_allocator as allocator
from . import two_stage_models as models
from . import two_stage_solver as stage2
from .models import ContractDirection, DemandAllocationAuthorityModeV1
from .serialization import canonical_sha256

GLOBAL_REGULARITY_POLICY_PROFILE_V1 = "scenario_c_global_regularity_policy_v1"
BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1 = 1
CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1 = 1
GLOBAL_TRANSITION_NOT_WORSE_THAN_B_V1 = True
DECLINING_TAIL_NON_DENSIFICATION_V1 = True

_ORIGINAL_BUILD_ALLOCATION_MODEL = allocator._build_allocation_model
_ORIGINAL_REPRESENTABLE_REGIMES = allocator._representable_regimes
_ORIGINAL_REPRESENTATION_CANDIDATES = allocator._representation_candidates_for_group
_ORIGINAL_EXACT_MEMBERSHIP = allocator._exact_membership_representation
_ORIGINAL_NECESSARY_FEASIBILITY = allocator.evaluate_stage_1_necessary_feasibility_v1
_ORIGINAL_STAGE2_BLOCK_MEMBERSHIP = stage2._add_exact_block_membership_constraints
_ORIGINAL_BUILD_STAGE2_MODEL = stage2._build_stage_2_model
_ORIGINAL_TWO_STAGE_CANDIDATE_ERRORS = solver_validation._two_stage_candidate_errors
_ORIGINAL_ADAPTER_CONTEXT_FINGERPRINT = stage2._adapter_context_fingerprint
_ORIGINAL_POLICY_FINGERPRINT_PROPERTY = models.UniformIntegerRegimePolicyV3.policy_fingerprint
_INSTALLED = False


def _policy_fingerprint_payload() -> dict[str, object]:
    return {
        "profile": GLOBAL_REGULARITY_POLICY_PROFILE_V1,
        "block_phase_max_deviation_trips": BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1,
        "cumulative_phase_max_deviation_trips": CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1,
        "transition_not_worse_than_scenario_b": GLOBAL_TRANSITION_NOT_WORSE_THAN_B_V1,
        "declining_tail_non_densification": DECLINING_TAIL_NON_DENSIFICATION_V1,
        "regime_count_semantics": "HARD_MAXIMUM_WITH_REPRESENTABLE_FIXED_POINT_COARSENING",
        "stage_1_surplus_allocation": "PASSENGER_PROPORTIONAL_LARGEST_REMAINDER",
    }


def _global_policy_fingerprint(self) -> str:
    base_getter = _ORIGINAL_POLICY_FINGERPRINT_PROPERTY.fget
    assert base_getter is not None
    return canonical_sha256(
        {
            "base_policy_fingerprint": base_getter(self),
            "global_regularity": _policy_fingerprint_payload(),
        }
    )


def _global_adapter_context_fingerprint(demand_authority, policy, protected_fingerprint):
    base = _ORIGINAL_ADAPTER_CONTEXT_FINGERPRINT(
        demand_authority,
        policy,
        protected_fingerprint,
    )
    return canonical_sha256(
        {
            "base_adapter_context_fingerprint": base,
            "global_regularity": _policy_fingerprint_payload(),
        }
    )


def _largest_remainder_targets(rows, total: int) -> dict[str, int]:
    """Return deterministic integer trip targets proportional to observed passengers."""
    if total < 0:
        raise ValueError("analytical trip total cannot be negative")
    ordered = tuple(sorted(rows, key=lambda item: (item.start_time, item.end_time, item.block_id)))
    if not ordered:
        return {}
    weights = {row.block_id: Fraction(str(max(0.0, float(row.observed_passengers)))) for row in ordered}
    weight_sum = sum(weights.values(), Fraction(0, 1))
    if weight_sum == 0:
        return {row.block_id: 0 for row in ordered}
    quotas = {row.block_id: Fraction(total, 1) * weights[row.block_id] / weight_sum for row in ordered}
    targets = {block_id: quota.numerator // quota.denominator for block_id, quota in quotas.items()}
    remaining = total - sum(targets.values())
    ranking = sorted(
        ordered,
        key=lambda row: (
            -(quotas[row.block_id] - targets[row.block_id]),
            row.start_time,
            row.end_time,
            row.block_id,
        ),
    )
    for row in ranking[:remaining]:
        targets[row.block_id] += 1
    return targets


def _aggregate_count_var(model, counts, direction, block, total_trips: int):
    if direction == ContractDirection.COMBINED:
        values = [
            counts[(candidate, block.block_id)]
            for candidate in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
        ]
        return allocator._bounded_sum(
            model,
            values,
            upper_bound=total_trips,
            name=f"stage1_global_aggregate_{block.block_id}",
        )
    return counts[(direction, block.block_id)]


def _demand_target_streams(problem, bundle):
    blocks = bundle.blocks
    sentinel_directions = {item.direction for item in bundle.final_service_sentinels}
    if problem.demand_allocation_authority_mode == DemandAllocationAuthorityModeV1.COMBINED_FIXED_DIRECTION_COUNTS:
        analytical_total = sum(
            allocator._direction_total(problem, direction) - int(direction in sentinel_directions)
            for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
        )
        return ((ContractDirection.COMBINED, blocks, analytical_total),)
    return tuple(
        (
            direction,
            tuple(block for block in blocks if block.direction == direction),
            allocator._direction_total(problem, direction) - int(direction in sentinel_directions),
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    )


def _fallback_source_targets(problem, direction, rows) -> dict[str, int]:
    if direction == ContractDirection.COMBINED:
        return {
            row.block_id: sum(
                allocator._source_count(problem, row, candidate)
                for candidate in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
            )
            for row in rows
        }
    return {row.block_id: allocator._source_count(problem, row, direction) for row in rows}


def _global_build_allocation_model(problem, authority, policy, protected_authority):
    """Replace the symmetric planning-floor target with demand fit and smoothness."""
    bundle = _ORIGINAL_BUILD_ALLOCATION_MODEL(problem, authority, policy, protected_authority)
    model = bundle.model
    total_trips = problem.scenario_b.total_daily_trips
    demand_errors = []
    change_points = []
    service_change_magnitudes = []

    for direction, rows, analytical_total in _demand_target_streams(problem, bundle):
        observed_total = sum(float(row.observed_passengers) for row in rows)
        if observed_total > 0:
            targets = _largest_remainder_targets(rows, analytical_total)
        else:
            targets = _fallback_source_targets(problem, direction, rows)
        aggregates = []
        for row in sorted(rows, key=lambda item: (item.start_time, item.end_time, item.block_id)):
            aggregate = _aggregate_count_var(
                model,
                bundle.count_by_direction_and_block,
                direction,
                row,
                total_trips,
            )
            aggregates.append((row, aggregate))
            target = targets[row.block_id]
            error = model.new_int_var(
                0,
                max(total_trips, target),
                f"stage1_demand_target_error_{direction.value}_{row.block_id}",
            )
            model.add_abs_equality(error, aggregate - target)
            demand_errors.append(error)

        for index, ((left_block, left), (right_block, right)) in enumerate(
            zip(aggregates, aggregates[1:], strict=False),
            start=1,
        ):
            # Compare service rates, not raw counts, so non-30-minute blocks remain coherent.
            left_duration = left_block.duration_minutes
            right_duration = right_block.duration_minutes
            rate_delta_bound = total_trips * max(left_duration, right_duration)
            magnitude = model.new_int_var(
                0,
                rate_delta_bound,
                f"stage1_service_rate_change_{direction.value}_{index:04d}",
            )
            rate_delta = left * right_duration - right * left_duration
            model.add_abs_equality(magnitude, rate_delta)
            service_change_magnitudes.append(magnitude)
            changed = model.new_bool_var(f"stage1_change_point_{direction.value}_{index:04d}")
            model.add(rate_delta != 0).only_enforce_if(changed)
            model.add(rate_delta == 0).only_enforce_if(changed.negated())
            change_points.append(changed)

    demand_bound = len(demand_errors) * total_trips
    change_point_bound = len(change_points)
    change_magnitude_bound = sum(
        total_trips * max(left.duration_minutes, right.duration_minutes)
        for _, rows, _ in _demand_target_streams(problem, bundle)
        for left, right in zip(
            sorted(rows, key=lambda item: (item.start_time, item.end_time, item.block_id)),
            sorted(rows, key=lambda item: (item.start_time, item.end_time, item.block_id))[1:],
            strict=False,
        )
    )
    old_terms = bundle.objective_terms
    old_bounds = bundle.objective_term_bounds
    terms = (
        old_terms[0],
        old_terms[1],
        old_terms[2],
        allocator._bounded_sum(
            model,
            demand_errors,
            upper_bound=demand_bound,
            name="stage1_passenger_proportional_demand_error",
        ),
        allocator._bounded_sum(
            model,
            change_points,
            upper_bound=change_point_bound,
            name="stage1_service_change_point_count",
        ),
        allocator._bounded_sum(
            model,
            service_change_magnitudes,
            upper_bound=change_magnitude_bound,
            name="stage1_total_service_rate_change",
        ),
        old_terms[4],
    )
    bounds = (
        old_bounds[0],
        old_bounds[1],
        old_bounds[2],
        demand_bound,
        change_point_bound,
        change_magnitude_bound,
        old_bounds[4],
    )
    model.Proto().ClearField("objective")
    weights = allocator._lexicographic_weights(bounds)
    model.minimize(sum(term * weight for term, weight in zip(terms, weights, strict=True)))
    return replace(bundle, objective_terms=terms, objective_term_bounds=bounds)


def _phase_membership_ok(representation, group, allocation) -> bool:
    ordered_blocks = tuple(sorted(group.blocks, key=lambda item: (item.start_time, item.end_time)))
    cumulative_actual = 0
    cumulative_target = 0
    for block in ordered_blocks:
        target = allocation[(group.direction, block.block_id)]
        actual = sum(
            block.start_time // 60 <= minute < block.end_time // 60
            for minute in representation.departure_minutes
        )
        if abs(actual - target) > BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1:
            return False
        if block.observed_passengers > 0 and target > 0 and actual == 0:
            return False
        cumulative_actual += actual
        cumulative_target += target
        if abs(cumulative_actual - cumulative_target) > CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1:
            return False
    sentinel_count = int(group.has_final_service_sentinel)
    return cumulative_actual == cumulative_target and group.trip_count == cumulative_target + sentinel_count


def _bounded_phase_membership_representation(candidates, group, allocation):
    return next(
        (representation for representation in candidates if _phase_membership_ok(representation, group, allocation)),
        None,
    )


def _singleton_aware_representation_candidates(
    problem,
    group,
    policy,
    projection,
    *,
    absolute_max_shift_per_trip_minutes=None,
    enforce_final_tail=True,
    enforce_protected_floor=True,
):
    if group.trip_count != 1:
        return _ORIGINAL_REPRESENTATION_CANDIDATES(
            problem,
            group,
            policy,
            projection,
            absolute_max_shift_per_trip_minutes=absolute_max_shift_per_trip_minutes,
            enforce_final_tail=enforce_final_tail,
            enforce_protected_floor=enforce_protected_floor,
        )
    directional = allocator._ordered_directional_trips(problem)[group.direction]
    sources = directional[group.source_start_index : group.source_end_index + 1]
    if len(sources) != 1:
        return (), (0, -1), (0, -1)
    source = sources[0]
    source_minute = source.departure_time // 60
    first_service = directional[0].departure_time // 60
    last_service = directional[-1].departure_time // 60
    block_start = min(block.start_time // 60 for block in group.blocks)
    block_end = max(block.end_time // 60 for block in group.blocks)
    upper_membership = block_end if group.has_final_service_sentinel else block_end - 1
    shift_limit = (
        policy.absolute_max_shift_per_trip_minutes
        if absolute_max_shift_per_trip_minutes is None
        else absolute_max_shift_per_trip_minutes
    )
    lower = max(first_service, block_start, source_minute - shift_limit)
    upper = min(last_service, upper_membership, source_minute + shift_limit)
    if group.source_start_index == 0:
        lower = max(lower, first_service)
        upper = min(upper, first_service)
    if group.source_end_index == len(directional) - 1:
        lower = max(lower, last_service)
        upper = min(upper, last_service)
    if lower > upper:
        return (), (lower, upper), (lower, upper)
    candidates = tuple(
        allocator.UniformRegimeRepresentationV1(
            start_minute=minute,
            end_minute=minute,
            uniform_headway_minutes=None,
            departure_minutes=(minute,),
        )
        for minute in sorted(range(lower, upper + 1), key=lambda item: (abs(item - source_minute), item))
    )
    return candidates, (lower, upper), (lower, upper)


def _planned_departures(regime) -> tuple[int, ...]:
    if regime.trip_count == 1:
        return (regime.planned_start_minute,)
    if regime.uniform_headway_minutes is None:
        return ()
    return tuple(
        regime.planned_start_minute + index * regime.uniform_headway_minutes
        for index in range(regime.trip_count)
    )


def _bounded_phase_plan_ok(allocation_blocks, regimes) -> bool:
    rows_by_direction = defaultdict(list)
    represented_by_regime = {regime.regime_id: _planned_departures(regime) for regime in regimes}
    for block in allocation_blocks:
        for direction, expected in block.directional_trip_counts:
            actual = sum(
                block.start_minute <= minute < block.end_minute
                for regime in regimes
                if regime.direction == direction
                for minute in represented_by_regime.get(regime.regime_id, ())
            )
            if abs(actual - expected) > BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1:
                return False
            if block.observed_passengers > 0 and expected > 0 and actual == 0:
                return False
            rows_by_direction[direction].append((block, expected, actual))
    for rows in rows_by_direction.values():
        cumulative_actual = cumulative_target = 0
        for block, expected, actual in sorted(
            rows,
            key=lambda item: (item[0].start_minute, item[0].end_minute, item[0].block_id),
        ):
            del block
            cumulative_actual += actual
            cumulative_target += expected
            if abs(cumulative_actual - cumulative_target) > CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1:
                return False
        if cumulative_actual != cumulative_target:
            return False
    return True


def _bounded_phase_necessary_feasibility(
    problem,
    allocation,
    allocation_blocks,
    regimes,
    final_service_sentinels,
    policy,
):
    result = _ORIGINAL_NECESSARY_FEASIBILITY(
        problem,
        allocation,
        allocation_blocks,
        regimes,
        final_service_sentinels,
        policy,
    )
    families = set(result.constraint_families)
    if models.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP in families and _bounded_phase_plan_ok(
        allocation_blocks,
        regimes,
    ):
        families.remove(models.Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP)
    if families == set(result.constraint_families):
        return result
    passed = not families
    explanation = (
        "Stage 1 plan passed bounded block-phase, B-anchor, final-tail, and safe fleet checks."
        if passed
        else "Stage 1 plan failed necessary Stage 2 checks for: "
        + ", ".join(item.value for item in sorted(families, key=lambda item: item.value))
        + "."
    )
    corrected = replace(
        result,
        passed=passed,
        constraint_families=tuple(sorted(families, key=lambda item: item.value)),
        explanation=explanation,
        diagnostic_fingerprint="",
    )
    return allocator.finalize_stage_1_necessary_feasibility(corrected)


def _group_from_regime(regime, blocks_by_id, cursor: int):
    return allocator._RegimeGroup(
        direction=regime.direction,
        blocks=tuple(blocks_by_id[item] for item in regime.covered_demand_block_ids),
        trip_count=regime.trip_count,
        source_start_index=cursor,
        source_end_index=cursor + regime.trip_count - 1,
        is_final_service_tail=regime.is_final_service_tail,
        has_final_service_sentinel=(
            regime.boundary_semantics == models.ServiceBoundarySemanticsV1.FINAL_SERVICE_SENTINEL
        ),
    )


def _tail_span_from_probe(probe) -> int:
    representation = probe.representation
    if representation is None:
        return 0
    return representation.end_minute - representation.start_minute


def _proposed_regime(problem, direction, index, group, probe, policy, projection):
    representation = probe.representation
    assert representation is not None
    maximum = (
        policy.final_service_tail.final_service_tail_maximum_headway_minutes
        if group.is_final_service_tail
        else max(1, representation.end_minute - representation.start_minute)
    )
    maximum = allocator._protected_maximum_headway(
        projection,
        direction,
        group.source_start_index,
        group.source_end_index,
        maximum,
    )
    return models.ProposedServiceRegimeV1(
        regime_id=f"V3-{direction.value.upper()}-{index:04d}",
        direction=direction,
        covered_demand_block_ids=tuple(block.block_id for block in group.blocks),
        trip_count=group.trip_count,
        permitted_start_window=probe.start_window,
        permitted_end_window=probe.end_window,
        planned_start_minute=representation.start_minute,
        planned_end_minute=representation.end_minute,
        minimum_headway_minutes=policy.minimum_operational_headway_minutes,
        maximum_headway_minutes=max(policy.minimum_operational_headway_minutes, maximum),
        uniform_headway_minutes=representation.uniform_headway_minutes,
        boundary_reason=(
            "FINAL_SERVICE_TAIL_ANCHORED_TO_LOCKED_LAST_DEPARTURE"
            if group.is_final_service_tail
            else "GLOBAL_REGULARITY_FIXED_POINT_COARSENING"
        ),
        is_final_service_tail=group.is_final_service_tail,
        boundary_semantics=(
            models.ServiceBoundarySemanticsV1.FINAL_SERVICE_SENTINEL
            if group.has_final_service_sentinel
            else models.ServiceBoundarySemanticsV1.HALF_OPEN_DEMAND_MEMBERSHIP
        ),
    )


def _global_representable_regimes(
    problem,
    allocation,
    blocks,
    policy,
    projection,
    final_service_sentinels,
    candidate_fingerprint,
):
    outcome = _ORIGINAL_REPRESENTABLE_REGIMES(
        problem,
        allocation,
        blocks,
        policy,
        projection,
        final_service_sentinels,
        candidate_fingerprint,
    )
    if outcome.regimes is None:
        return outcome
    blocks_by_id = {block.block_id: block for block in blocks}
    requirements = {item.block_id: item.required_trips_85 for item in problem.block_requirements}
    output = []
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        original = sorted(
            (item for item in outcome.regimes if item.direction == direction),
            key=lambda item: (item.planned_start_minute, item.planned_end_minute, item.regime_id),
        )
        groups = []
        cursor = 0
        for regime in original:
            group = _group_from_regime(regime, blocks_by_id, cursor)
            groups.append(group)
            cursor += regime.trip_count
        allocated = {
            block.block_id: allocation[(direction, block.block_id)]
            for block in blocks
            if block.direction in {direction, ContractDirection.COMBINED}
        }
        tail_target = policy.final_service_tail.final_service_tail_window_minutes
        while len(groups) >= 2:
            options = []
            for pair_index in range(len(groups) - 1):
                left, right = groups[pair_index : pair_index + 2]
                if not allocator._groups_are_contiguous(left, right):
                    continue
                if right.is_final_service_tail:
                    current_tail_probe = allocator._representation_for_group(
                        problem,
                        right,
                        policy,
                        projection,
                        allocation,
                    )
                    if _tail_span_from_probe(current_tail_probe) >= max(
                        0,
                        tail_target - policy.maximum_regime_boundary_adjustment_minutes,
                    ):
                        continue
                merged = allocator._merge_groups(left, right)
                probe = allocator._representation_for_group(
                    problem,
                    merged,
                    policy,
                    projection,
                    allocation,
                )
                if probe.representation is None:
                    continue
                options.append(
                    (
                        allocator._merge_score(
                            problem,
                            left,
                            right,
                            merged,
                            probe.representation,
                            requirements,
                            allocated,
                        ),
                        pair_index,
                        merged,
                    )
                )
            if not options:
                break
            _, pair_index, merged = min(options, key=lambda item: item[0])
            groups[pair_index : pair_index + 2] = [merged]

        probes = [
            allocator._representation_for_group(problem, group, policy, projection, allocation)
            for group in groups
        ]
        if any(probe.representation is None for probe in probes):
            return outcome
        output.extend(
            _proposed_regime(problem, direction, index, group, probe, policy, projection)
            for index, (group, probe) in enumerate(zip(groups, probes, strict=True), start=1)
        )
    return allocator._RegimeBuildOutcome(regimes=tuple(output), diagnostic=None)


def _add_bounded_phase_block_membership_constraints(model, problem, plan, departure_by_source_id):
    directional = stage2._ordered_directional_trips(problem)
    by_direction_and_block = {}
    count_by_direction_and_block = {}
    target_by_direction_and_block = {}
    blocks_by_direction = defaultdict(list)
    for allocation_block in plan.allocation_blocks:
        targets = dict(allocation_block.directional_trip_counts)
        for direction, target in targets.items():
            memberships = []
            for source in directional[direction]:
                departure = departure_by_source_id[source.trip_id]
                at_or_after = stage2._reified_less_than_or_equal(
                    model,
                    allocation_block.start_minute,
                    departure,
                    name=f"v3_phase_after_{source.trip_id}_{allocation_block.block_id}",
                )
                before_end = stage2._reified_less_than_or_equal(
                    model,
                    departure,
                    allocation_block.end_minute - 1,
                    name=f"v3_phase_before_{source.trip_id}_{allocation_block.block_id}",
                )
                member = model.new_bool_var(
                    f"v3_phase_member_{source.trip_id}_{allocation_block.block_id}"
                )
                model.add(member <= at_or_after)
                model.add(member <= before_end)
                model.add(member >= at_or_after + before_end - 1)
                memberships.append(member)
            count = model.new_int_var(
                0,
                len(directional[direction]),
                f"v3_phase_count_{direction.value}_{allocation_block.block_id}",
            )
            model.add(count == sum(memberships))
            lower = max(0, target - BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1)
            upper = min(len(directional[direction]), target + BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1)
            if allocation_block.observed_passengers > 0 and target > 0:
                lower = max(lower, 1)
            model.add(count >= lower)
            model.add(count <= upper)
            key = (direction, allocation_block.block_id)
            by_direction_and_block[key] = tuple(memberships)
            count_by_direction_and_block[key] = count
            target_by_direction_and_block[key] = target
            blocks_by_direction[direction].append(allocation_block)

    for direction, direction_blocks in blocks_by_direction.items():
        ordered = sorted(
            direction_blocks,
            key=lambda item: (item.start_minute, item.end_minute, item.block_id),
        )
        cumulative_counts = []
        cumulative_target = 0
        for block in ordered:
            key = (direction, block.block_id)
            cumulative_counts.append(count_by_direction_and_block[key])
            cumulative_target += target_by_direction_and_block[key]
            prefix = sum(cumulative_counts)
            model.add(prefix - cumulative_target <= CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1)
            model.add(cumulative_target - prefix <= CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1)
        if ordered:
            model.add(sum(cumulative_counts) == cumulative_target)
    return by_direction_and_block


def _scenario_b_max_headway_change(problem) -> int:
    maximum = 0
    has_comparable = False
    directional = stage2._ordered_directional_trips(problem)
    for trips in directional.values():
        minutes = [trip.departure_time // 60 for trip in trips]
        headways = [later - earlier for earlier, later in zip(minutes, minutes[1:], strict=False)]
        for earlier, later in zip(headways, headways[1:], strict=False):
            has_comparable = True
            maximum = max(maximum, abs(later - earlier))
    return maximum if has_comparable else 10**9


def _regime_passenger_rate(problem, regime) -> float:
    blocks = {item.block_id: item for item in problem.analysis_blocks}
    covered = [blocks[item] for item in regime.covered_demand_block_ids if item in blocks]
    duration = sum(item.duration_minutes for item in covered)
    if duration <= 0:
        return 0.0
    return sum(float(item.observed_passengers) for item in covered) * 60.0 / duration


def _tail_demand_not_rising(problem, earlier, tail) -> bool:
    return _regime_passenger_rate(problem, tail) <= _regime_passenger_rate(problem, earlier) + 1e-9


def _global_build_stage2_model(problem, plan, policy, protected_projection):
    bundle = _ORIGINAL_BUILD_STAGE2_MODEL(problem, plan, policy, protected_projection)
    model = bundle.model
    effective_transition_cap = min(
        policy.maximum_transition_jump_minutes,
        _scenario_b_max_headway_change(problem),
    )
    directional_regimes = stage2._directional_regimes(plan)
    for direction, regimes in directional_regimes.items():
        for index, (earlier, later) in enumerate(zip(regimes, regimes[1:], strict=False), start=1):
            earlier_ids = bundle.source_ids_by_regime_id[earlier.regime_id]
            later_ids = bundle.source_ids_by_regime_id[later.regime_id]
            transition = (
                bundle.departure_by_source_id[later_ids[0]]
                - bundle.departure_by_source_id[earlier_ids[-1]]
            )
            for suffix, regime in (("before", earlier), ("after", later)):
                regime_headway = bundle.headway_by_regime_id.get(regime.regime_id)
                if regime_headway is None or effective_transition_cap >= 10**9:
                    continue
                jump = model.new_int_var(
                    0,
                    max(1, problem.scenario_b.total_daily_trips * 60),
                    f"v3_global_transition_{direction.value}_{index:04d}_{suffix}",
                )
                model.add_abs_equality(jump, transition - regime_headway)
                model.add(jump <= effective_transition_cap)
            if (
                later.is_final_service_tail
                and _tail_demand_not_rising(problem, earlier, later)
                and earlier.regime_id in bundle.headway_by_regime_id
                and later.regime_id in bundle.headway_by_regime_id
            ):
                model.add(
                    bundle.headway_by_regime_id[later.regime_id]
                    >= bundle.headway_by_regime_id[earlier.regime_id]
                )
    proto = model.Proto()
    return replace(
        bundle,
        variable_count=len(proto.variables),
        constraint_count=len(proto.constraints),
    )


def _candidate_bounded_phase_ok(candidate, allocation_plan) -> bool:
    if allocation_plan is None:
        return False
    rows_by_direction = defaultdict(list)
    for block in allocation_plan.allocation_blocks:
        for direction, expected in block.directional_trip_counts:
            actual = sum(
                trip.direction == direction
                and block.start_minute * 60 <= trip.c_departure_time < block.end_minute * 60
                for trip in candidate.exact_timetable
            )
            if abs(actual - expected) > BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1:
                return False
            if block.observed_passengers > 0 and expected > 0 and actual == 0:
                return False
            rows_by_direction[direction].append((block, expected, actual))
    for rows in rows_by_direction.values():
        cumulative_actual = cumulative_target = 0
        for block, expected, actual in sorted(
            rows,
            key=lambda item: (item[0].start_minute, item[0].end_minute, item[0].block_id),
        ):
            del block
            cumulative_actual += actual
            cumulative_target += expected
            if abs(cumulative_actual - cumulative_target) > CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1:
                return False
        if cumulative_actual != cumulative_target:
            return False
    return True


def _candidate_global_regularity_errors(problem, candidate, allocation_plan, policy):
    errors = _ORIGINAL_TWO_STAGE_CANDIDATE_ERRORS(problem, candidate, allocation_plan, policy)
    exact_code = "V3_STAGE_1_BLOCK_ALLOCATION_NOT_REPRODUCED"
    if exact_code in errors and _candidate_bounded_phase_ok(candidate, allocation_plan):
        errors = [item for item in errors if item != exact_code]

    if allocation_plan is None:
        return errors
    raw_by_id = {item.regime_id: item for item in candidate.headway_regimes}
    members_by_id = defaultdict(list)
    for trip in candidate.exact_timetable:
        members_by_id[trip.headway_regime_id].append(trip)
    effective_transition_cap = min(
        policy.maximum_transition_jump_minutes,
        _scenario_b_max_headway_change(problem),
    )
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        regimes = sorted(
            (item for item in allocation_plan.proposed_regimes if item.direction == direction),
            key=lambda item: (item.planned_start_minute, item.planned_end_minute, item.regime_id),
        )
        for earlier, later in zip(regimes, regimes[1:], strict=False):
            earlier_members = sorted(members_by_id[earlier.regime_id], key=lambda item: item.c_departure_time)
            later_members = sorted(members_by_id[later.regime_id], key=lambda item: item.c_departure_time)
            if not earlier_members or not later_members:
                continue
            transition = (
                later_members[0].c_departure_time - earlier_members[-1].c_departure_time
            ) // 60
            adjacent = [raw_by_id[item.regime_id] for item in (earlier, later) if item.regime_id in raw_by_id]
            if any(
                raw.actual_headway_sequence
                and abs(transition - raw.actual_headway_sequence[0]) > effective_transition_cap
                for raw in adjacent
            ):
                errors.append("V3_GLOBAL_TRANSITION_JUMP_WORSE_THAN_SCENARIO_B")
            earlier_raw = raw_by_id.get(earlier.regime_id)
            later_raw = raw_by_id.get(later.regime_id)
            if (
                later.is_final_service_tail
                and _tail_demand_not_rising(problem, earlier, later)
                and earlier_raw is not None
                and later_raw is not None
                and earlier_raw.actual_headway_sequence
                and later_raw.actual_headway_sequence
                and later_raw.actual_headway_sequence[0] < earlier_raw.actual_headway_sequence[0]
            ):
                errors.append("V3_FINAL_TAIL_HEADWAY_SHORTER_WHILE_DEMAND_NOT_RISING")
    return list(dict.fromkeys(errors))


def install_global_regularity_v1() -> None:
    """Install the production V3 regularity policy once for this process."""
    global _INSTALLED
    if _INSTALLED:
        return
    models.UniformIntegerRegimePolicyV3.policy_fingerprint = property(_global_policy_fingerprint)
    stage2._adapter_context_fingerprint = _global_adapter_context_fingerprint
    allocator._build_allocation_model = _global_build_allocation_model
    allocator._representation_candidates_for_group = _singleton_aware_representation_candidates
    allocator._exact_membership_representation = _bounded_phase_membership_representation
    allocator._representable_regimes = _global_representable_regimes
    allocator.evaluate_stage_1_necessary_feasibility_v1 = _bounded_phase_necessary_feasibility
    stage2._add_exact_block_membership_constraints = _add_bounded_phase_block_membership_constraints
    stage2._build_stage_2_model = _global_build_stage2_model
    solver_validation._two_stage_candidate_errors = _candidate_global_regularity_errors
    _INSTALLED = True


def uninstall_global_regularity_v1() -> None:
    """Restore merged baseline functions; intended for isolated regression tests."""
    global _INSTALLED
    if not _INSTALLED:
        return
    models.UniformIntegerRegimePolicyV3.policy_fingerprint = _ORIGINAL_POLICY_FINGERPRINT_PROPERTY
    stage2._adapter_context_fingerprint = _ORIGINAL_ADAPTER_CONTEXT_FINGERPRINT
    allocator._build_allocation_model = _ORIGINAL_BUILD_ALLOCATION_MODEL
    allocator._representation_candidates_for_group = _ORIGINAL_REPRESENTATION_CANDIDATES
    allocator._exact_membership_representation = _ORIGINAL_EXACT_MEMBERSHIP
    allocator._representable_regimes = _ORIGINAL_REPRESENTABLE_REGIMES
    allocator.evaluate_stage_1_necessary_feasibility_v1 = _ORIGINAL_NECESSARY_FEASIBILITY
    stage2._add_exact_block_membership_constraints = _ORIGINAL_STAGE2_BLOCK_MEMBERSHIP
    stage2._build_stage_2_model = _ORIGINAL_BUILD_STAGE2_MODEL
    solver_validation._two_stage_candidate_errors = _ORIGINAL_TWO_STAGE_CANDIDATE_ERRORS
    _INSTALLED = False


__all__ = [
    "BLOCK_PHASE_MAX_DEVIATION_TRIPS_V1",
    "CUMULATIVE_PHASE_MAX_DEVIATION_TRIPS_V1",
    "DECLINING_TAIL_NON_DENSIFICATION_V1",
    "GLOBAL_REGULARITY_POLICY_PROFILE_V1",
    "GLOBAL_TRANSITION_NOT_WORSE_THAN_B_V1",
    "install_global_regularity_v1",
    "uninstall_global_regularity_v1",
]
