"""Stage 2 exact-minute solver and shared-budget V3 adapter."""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import ClassVar

from ortools.sat.python import cp_model

from bus_schedule_engine.models import ProtectedServiceFloorEnforcementAuthorityV1

from .evaluation import ScenarioBEvaluationBundleV1, ScenarioBEvaluationPolicyV1
from .models import (
    ContractDirection,
    NormalizedInputBundleV1,
    ScenarioCOptimizationModeV1,
)
from .ortools_protected_floor import (
    OrToolsProtectedFloorProjectionV1,
    build_ortools_protected_floor_projection_v1,
)
from .ortools_solver import (
    _adapter_capability_issues,
    _build_cp_sat_model,
    _map_cp_sat_status,
    _ordered_directional_trips,
    _previous_headways,
    _reified_less_than_or_equal,
)
from .serialization import canonical_sha256
from .solver_fingerprints import candidate_fingerprint
from .solver_models import (
    BoundaryConvention,
    DirectionTripLockMode,
    FleetConstraintMode,
    InitialFleetPositioningMode,
    NativeSolverStatus,
    RawCandidateTripV1,
    RawHeadwayRegimeV1,
    RawScheduleCandidateV1,
    ScheduleGenerationContextV1,
    ScheduleProblemV1,
    SolverExecutionStatus,
    SolverPolicyV1,
    SolverRunResultV1,
)
from .solver_problem import (
    ScheduleProblemError,
    build_schedule_generation_context_v1,
    build_schedule_problem_v1,
    jsonable,
)
from .two_stage_allocator import allocate_trips_stage_1_v1
from .two_stage_authority import (
    TwoStageDemandAuthorityV1,
    build_two_stage_demand_authority_v1,
)
from .two_stage_models import (
    FinalServiceTailMetricsV1,
    ProposedServiceRegimeV1,
    Stage2ConstraintFamilyV1,
    Stage2InfeasibilityDiagnosticV1,
    Stage2TimetableResultV1,
    TripAllocationPlanV1,
    TripAllocationSolveStatusV1,
    TwoStageNativeRunV1,
    TwoStageSolveDiagnosticsV1,
    UniformIntegerRegimePolicyV3,
    finalize_stage_2_infeasibility_diagnostic,
)

ORTOOLS_TWO_STAGE_UNIFORM_ADAPTER_ID = "ortools_cp_sat_two_stage_uniform_v1"
TWO_STAGE_ADAPTER_CONTEXT_PROFILE_V1 = "scenario_c_two_stage_adapter_context_v1"
TWO_STAGE_ADAPTER_CONTEXT_MISMATCH = "TWO_STAGE_ADAPTER_CONTEXT_MISMATCH"
TWO_STAGE_TOTAL_BUDGET_REQUIRED = "TWO_STAGE_TOTAL_BUDGET_REQUIRED"
_DEFAULT_TOTAL_BUDGET_SECONDS = 120.0
_STAGE_1_BUDGET_SHARE = 0.35
_BOUNDED_STAGE_1_PLANS_EXHAUSTED_WITHOUT_FEASIBLE_C = (
    "BOUNDED_STAGE_1_PLANS_EXHAUSTED_WITHOUT_FEASIBLE_C"
)


@dataclass(frozen=True, slots=True)
class _Stage2Model:
    model: cp_model.CpModel
    departure_by_source_id: dict[str, cp_model.IntVar]
    regime_by_source_id: dict[str, ProposedServiceRegimeV1]
    source_ids_by_regime_id: dict[str, tuple[str, ...]]
    headway_by_regime_id: dict[str, cp_model.IntVar]
    objective_groups: tuple[cp_model.IntVar, ...]
    variable_count: int
    constraint_count: int
    maximum_departure_domain_width_minutes: int
    full_service_window_domain_count: int


def _adapter_context_fingerprint(
    demand_authority: TwoStageDemandAuthorityV1,
    policy: UniformIntegerRegimePolicyV3,
    protected_fingerprint: str | None,
) -> str:
    return canonical_sha256(
        {
            "profile": TWO_STAGE_ADAPTER_CONTEXT_PROFILE_V1,
            "adapter_id": ORTOOLS_TWO_STAGE_UNIFORM_ADAPTER_ID,
            "demand_authority_fingerprint": demand_authority.authority_fingerprint,
            "optimization_mode": ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE.value,
            "demand_authority_mode": demand_authority.authority_mode.value,
            "uniform_regime_policy": jsonable(asdict(policy)),
            "protected_service_floor_enforcement_fingerprint": protected_fingerprint,
        }
    )


def _directional_regimes(
    plan: TripAllocationPlanV1,
) -> dict[ContractDirection, tuple[ProposedServiceRegimeV1, ...]]:
    return {
        direction: tuple(
            sorted(
                (regime for regime in plan.proposed_regimes if regime.direction == direction),
                key=lambda item: (
                    item.planned_start_minute,
                    item.planned_end_minute,
                    item.regime_id,
                ),
            )
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    }


def _source_regime_membership(
    problem: ScheduleProblemV1,
    plan: TripAllocationPlanV1,
) -> tuple[dict[str, ProposedServiceRegimeV1], dict[str, tuple[str, ...]]]:
    directional_trips = _ordered_directional_trips(problem)
    regimes = _directional_regimes(plan)
    regime_by_source: dict[str, ProposedServiceRegimeV1] = {}
    source_ids_by_regime: dict[str, tuple[str, ...]] = {}
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        trips = directional_trips[direction]
        cursor = 0
        for regime in regimes[direction]:
            members = trips[cursor : cursor + regime.trip_count]
            if len(members) != regime.trip_count:
                raise ValueError("Stage 1 regime count exceeds its fixed directional source slice")
            source_ids = tuple(trip.trip_id for trip in members)
            source_ids_by_regime[regime.regime_id] = source_ids
            for source_id in source_ids:
                regime_by_source[source_id] = regime
            cursor += regime.trip_count
        if cursor != len(trips):
            raise ValueError("Stage 1 regimes do not cover the fixed directional source count")
    return regime_by_source, source_ids_by_regime


def _departure_domains(
    problem: ScheduleProblemV1,
    plan: TripAllocationPlanV1,
    policy: UniformIntegerRegimePolicyV3,
) -> dict[str, tuple[int, int]]:
    regime_by_source, source_ids_by_regime = _source_regime_membership(problem, plan)
    blocks = {block.block_id: block for block in problem.analysis_blocks}
    sentinel_by_source_id = {item.source_b_trip_id: item for item in plan.final_service_sentinels}
    directional = _ordered_directional_trips(problem)
    output: dict[str, tuple[int, int]] = {}
    for trips in directional.values():
        service_start = trips[0].departure_time // 60
        service_end = trips[-1].departure_time // 60
        for trip in trips:
            regime = regime_by_source[trip.trip_id]
            covered = tuple(blocks[block_id] for block_id in regime.covered_demand_block_ids)
            regime_start = min(block.start_time // 60 for block in covered)
            regime_end = max(block.end_time // 60 - 1 for block in covered)
            sentinel = sentinel_by_source_id.get(trip.trip_id)
            if sentinel is not None:
                regime_end = max(regime_end, sentinel.departure_minute)
            source_minute = trip.departure_time // 60
            lower = max(
                service_start,
                regime_start,
                source_minute - policy.absolute_max_shift_per_trip_minutes,
            )
            upper = min(
                service_end,
                regime_end,
                source_minute + policy.absolute_max_shift_per_trip_minutes,
            )
            members = source_ids_by_regime[regime.regime_id]
            if trip.trip_id == members[0]:
                lower = max(lower, regime.permitted_start_window[0])
                upper = min(upper, regime.permitted_start_window[1])
            if trip.trip_id == members[-1]:
                lower = max(lower, regime.permitted_end_window[0])
                upper = min(upper, regime.permitted_end_window[1])
            if lower > upper:
                raise ValueError(f"empty B-anchored Stage 2 domain for {trip.trip_id}")
            output[trip.trip_id] = (lower, upper)
    return output


def _add_exact_block_membership_constraints(
    model: cp_model.CpModel,
    problem: ScheduleProblemV1,
    plan: TripAllocationPlanV1,
    departure_by_source_id: dict[str, cp_model.IntVar],
) -> dict[tuple[ContractDirection, str], tuple[cp_model.IntVar, ...]]:
    directional = _ordered_directional_trips(problem)
    by_direction_and_block: dict[tuple[ContractDirection, str], tuple[cp_model.IntVar, ...]] = {}
    for allocation_block in plan.allocation_blocks:
        targets = dict(allocation_block.directional_trip_counts)
        for direction, target in targets.items():
            memberships: list[cp_model.IntVar] = []
            for source in directional[direction]:
                departure = departure_by_source_id[source.trip_id]
                at_or_after = _reified_less_than_or_equal(
                    model,
                    allocation_block.start_minute,
                    departure,
                    name=f"v3_block_after_{source.trip_id}_{allocation_block.block_id}",
                )
                before_end = _reified_less_than_or_equal(
                    model,
                    departure,
                    allocation_block.end_minute - 1,
                    name=f"v3_block_before_{source.trip_id}_{allocation_block.block_id}",
                )
                member = model.new_bool_var(
                    f"v3_block_member_{source.trip_id}_{allocation_block.block_id}"
                )
                model.add(member <= at_or_after)
                model.add(member <= before_end)
                model.add(member >= at_or_after + before_end - 1)
                memberships.append(member)
            model.add(sum(memberships) == target)
            by_direction_and_block[(direction, allocation_block.block_id)] = tuple(memberships)
    return by_direction_and_block


def _positive_demand_service_gap_objective(
    model: cp_model.CpModel,
    problem: ScheduleProblemV1,
    plan: TripAllocationPlanV1,
    departure_by_source_id: dict[str, cp_model.IntVar],
    domains: dict[str, tuple[int, int]],
) -> cp_model.IntVar:
    """Encode gaps on one authority-native stream per positive-demand block."""
    block_gap_values: list[cp_model.IntVar] = []
    maximum_duration = max(
        block.end_minute - block.start_minute for block in plan.allocation_blocks
    )
    total_bound = 0
    for block in plan.allocation_blocks:
        if block.observed_passengers <= 0:
            continue
        duration = block.end_minute - block.start_minute
        total_bound += duration
        block_max = model.new_int_var(
            0,
            duration,
            f"v3_block_max_gap_{block.block_id}",
        )
        compatible_directions = (
            {ContractDirection.OUTBOUND, ContractDirection.INBOUND}
            if block.direction == ContractDirection.COMBINED
            else {block.direction}
        )
        source_ids = tuple(
            source.trip_id
            for source in problem.scenario_b.exact_timetable
            if source.direction in compatible_directions
            and domains[source.trip_id][0] < block.end_minute
            and domains[source.trip_id][1] >= block.start_minute
        )
        distance = model.new_constant(0)
        event_gaps: list[cp_model.IntVar] = []
        for minute in range(block.start_minute, block.end_minute):
            equality_literals: list[cp_model.IntVar] = []
            for source_id in source_ids:
                at_minute = model.new_bool_var(
                    f"v3_at_minute_{block.block_id}_{source_id}_{minute:04d}"
                )
                departure = departure_by_source_id[source_id]
                model.add(departure == minute).only_enforce_if(at_minute)
                model.add(departure != minute).only_enforce_if(at_minute.negated())
                equality_literals.append(at_minute)
            event = model.new_bool_var(f"v3_service_event_{block.block_id}_{minute:04d}")
            if equality_literals:
                model.add_bool_or(equality_literals).only_enforce_if(event)
                model.add_bool_and(
                    tuple(item.negated() for item in equality_literals)
                ).only_enforce_if(event.negated())
            else:
                model.add(event == 0)
            gap = model.new_int_var(
                0,
                duration,
                f"v3_event_gap_{block.block_id}_{minute:04d}",
            )
            model.add(gap == distance).only_enforce_if(event)
            model.add(gap == 0).only_enforce_if(event.negated())
            event_gaps.append(gap)
            next_distance = model.new_int_var(
                0,
                duration,
                f"v3_distance_after_{block.block_id}_{minute:04d}",
            )
            model.add(next_distance == 1).only_enforce_if(event)
            model.add(next_distance == distance + 1).only_enforce_if(event.negated())
            distance = next_distance
        model.add_max_equality(block_max, [*event_gaps, distance])
        block_gap_values.append(block_max)
    maximum = model.new_int_var(0, maximum_duration, "v3_maximum_positive_demand_gap")
    if block_gap_values:
        model.add_max_equality(maximum, block_gap_values)
    else:
        model.add(maximum == 0)
    total = _sum_var(
        model,
        block_gap_values,
        upper_bound=total_bound,
        name="v3_total_positive_demand_block_max_gap",
    )
    objective = model.new_int_var(
        0,
        maximum_duration * (total_bound + 1) + total_bound,
        "v3_passenger_service_continuity_group",
    )
    model.add(objective == maximum * (total_bound + 1) + total)
    return objective


def _add_protected_constraints(
    model: cp_model.CpModel,
    departure_by_source_id: dict[str, cp_model.IntVar],
    projection: OrToolsProtectedFloorProjectionV1 | None,
) -> None:
    if projection is None:
        return
    for regime in projection.regimes:
        departures = tuple(departure_by_source_id[item] for item in regime.ordered_b_trip_ids)
        tolerance = regime.boundary_tolerance_minutes
        if regime.donor_removal_prohibited:
            for departure in departures:
                model.add(departure >= regime.protected_window_start_minutes - tolerance)
                model.add(departure <= regime.protected_window_end_minutes + tolerance)
        model.add(departures[0] >= regime.protected_window_start_minutes - tolerance)
        model.add(departures[0] <= regime.protected_window_start_minutes + tolerance)
        model.add(departures[-1] >= regime.protected_window_end_minutes - tolerance)
        model.add(departures[-1] <= regime.protected_window_end_minutes + tolerance)
        for earlier, later in zip(departures, departures[1:], strict=False):
            model.add(later - earlier <= regime.maximum_future_c_headway_minutes)


def _sum_var(
    model: cp_model.CpModel,
    values: list[cp_model.IntVar],
    *,
    upper_bound: int,
    name: str,
) -> cp_model.IntVar:
    output = model.new_int_var(0, max(0, upper_bound), name)
    model.add(output == sum(values))
    return output


def _build_stage_2_model(
    problem: ScheduleProblemV1,
    plan: TripAllocationPlanV1,
    policy: UniformIntegerRegimePolicyV3,
    protected_projection: OrToolsProtectedFloorProjectionV1 | None,
) -> _Stage2Model:
    domains = _departure_domains(problem, plan, policy)
    hard = _build_cp_sat_model(
        problem,
        departure_domain_by_source_id=domains,
        minimum_headway_minutes=policy.minimum_operational_headway_minutes,
    )
    model = hard.model
    regime_by_source, source_ids_by_regime = _source_regime_membership(problem, plan)
    headway_by_regime: dict[str, cp_model.IntVar] = {}
    for regime in plan.proposed_regimes:
        source_ids = source_ids_by_regime[regime.regime_id]
        first = hard.departure_by_source_id[source_ids[0]]
        last = hard.departure_by_source_id[source_ids[-1]]
        model.add(first >= regime.permitted_start_window[0])
        model.add(first <= regime.permitted_start_window[1])
        model.add(last >= regime.permitted_end_window[0])
        model.add(last <= regime.permitted_end_window[1])
        if regime.trip_count >= 2:
            headway = model.new_int_var(
                regime.minimum_headway_minutes,
                regime.maximum_headway_minutes,
                f"v3_uniform_headway_{regime.regime_id}",
            )
            headway_by_regime[regime.regime_id] = headway
            for earlier_id, later_id in zip(source_ids, source_ids[1:], strict=False):
                model.add(
                    hard.departure_by_source_id[later_id] - hard.departure_by_source_id[earlier_id]
                    == headway
                )
        if regime.is_final_service_tail:
            direction_trips = _ordered_directional_trips(problem)[regime.direction]
            locked_last = direction_trips[-1].departure_time // 60
            model.add(last == locked_last)

    _add_exact_block_membership_constraints(
        model,
        problem,
        plan,
        hard.departure_by_source_id,
    )
    _add_protected_constraints(model, hard.departure_by_source_id, protected_projection)

    service_continuity_group = _positive_demand_service_gap_objective(
        model,
        problem,
        plan,
        hard.departure_by_source_id,
        domains,
    )
    directional_regimes = _directional_regimes(plan)
    transition_values: list[cp_model.IntVar] = []
    tail_preference_values: list[cp_model.IntVar] = []
    directional_span = max(
        trips[-1].departure_time // 60 - trips[0].departure_time // 60
        for trips in _ordered_directional_trips(problem).values()
    )
    for direction, regimes in directional_regimes.items():
        for index, (earlier_regime, later_regime) in enumerate(
            zip(regimes, regimes[1:], strict=False),
            start=1,
        ):
            earlier_ids = source_ids_by_regime[earlier_regime.regime_id]
            later_ids = source_ids_by_regime[later_regime.regime_id]
            transition = (
                hard.departure_by_source_id[later_ids[0]]
                - hard.departure_by_source_id[earlier_ids[-1]]
            )
            for suffix, regime in (("before", earlier_regime), ("after", later_regime)):
                regime_headway = headway_by_regime.get(regime.regime_id)
                if regime_headway is None:
                    continue
                jump = model.new_int_var(
                    0,
                    directional_span,
                    f"v3_transition_jump_{direction.value}_{index:04d}_{suffix}",
                )
                model.add_abs_equality(jump, transition - regime_headway)
                model.add(jump <= policy.maximum_transition_jump_minutes)
                transition_values.append(jump)
            if (
                later_regime.is_final_service_tail
                and policy.final_service_tail.prefer_final_tail_headway_not_shorter_than_previous_regime
                and earlier_regime.regime_id in headway_by_regime
                and later_regime.regime_id in headway_by_regime
            ):
                violation = model.new_int_var(
                    0,
                    directional_span,
                    f"v3_tail_shorter_violation_{direction.value}",
                )
                model.add_max_equality(
                    violation,
                    [
                        0,
                        headway_by_regime[earlier_regime.regime_id]
                        - headway_by_regime[later_regime.regime_id],
                    ],
                )
                tail_preference_values.append(violation)

    shift_values: list[cp_model.IntVar] = []
    shifted_values: list[cp_model.IntVar] = []
    preferred_exceedances: list[cp_model.IntVar] = []
    for source in problem.scenario_b.exact_timetable:
        departure = hard.departure_by_source_id[source.trip_id]
        source_minute = source.departure_time // 60
        shift = model.new_int_var(
            0,
            policy.absolute_max_shift_per_trip_minutes,
            f"v3_shift_{source.trip_id}",
        )
        model.add_abs_equality(shift, departure - source_minute)
        shifted = model.new_bool_var(f"v3_shifted_{source.trip_id}")
        model.add(shift >= 1).only_enforce_if(shifted)
        model.add(shift == 0).only_enforce_if(shifted.negated())
        exceedance = model.new_int_var(
            0,
            max(
                0,
                policy.absolute_max_shift_per_trip_minutes
                - policy.preferred_max_shift_per_trip_minutes,
            ),
            f"v3_preferred_shift_exceedance_{source.trip_id}",
        )
        model.add_max_equality(
            exceedance,
            [0, shift - policy.preferred_max_shift_per_trip_minutes],
        )
        shift_values.append(shift)
        shifted_values.append(shifted)
        preferred_exceedances.append(exceedance)

    transition_sum_bound = directional_span * max(1, len(transition_values))
    transition_sum = _sum_var(
        model,
        transition_values,
        upper_bound=transition_sum_bound,
        name="v3_total_transition_jump",
    )
    transition_max = model.new_int_var(0, directional_span, "v3_maximum_transition_jump")
    if transition_values:
        model.add_max_equality(transition_max, transition_values)
    else:
        model.add(transition_max == 0)
    transition_group = model.new_int_var(
        0,
        directional_span * (transition_sum_bound + 1) + transition_sum_bound,
        "v3_transition_objective_group",
    )
    model.add(transition_group == transition_max * (transition_sum_bound + 1) + transition_sum)
    tail_group = _sum_var(
        model,
        tail_preference_values,
        upper_bound=directional_span * max(1, len(tail_preference_values)),
        name="v3_tail_preference_group",
    )
    trip_count = len(problem.scenario_b.exact_timetable)
    shifted_count = _sum_var(
        model,
        shifted_values,
        upper_bound=trip_count,
        name="v3_shifted_trip_count",
    )
    total_shift = _sum_var(
        model,
        shift_values,
        upper_bound=trip_count * policy.absolute_max_shift_per_trip_minutes,
        name="v3_total_shift",
    )
    preferred_exceedance = _sum_var(
        model,
        preferred_exceedances,
        upper_bound=trip_count * policy.absolute_max_shift_per_trip_minutes,
        name="v3_preferred_shift_exceedance",
    )
    maximum_shift = model.new_int_var(
        0,
        policy.absolute_max_shift_per_trip_minutes,
        "v3_maximum_shift",
    )
    model.add_max_equality(maximum_shift, shift_values)
    total_bound = trip_count * policy.absolute_max_shift_per_trip_minutes
    shifted_and_total_bound = trip_count * (total_bound + 1) + total_bound
    shift_group_bound = (
        (shifted_and_total_bound * (policy.absolute_max_shift_per_trip_minutes + 1))
        + policy.absolute_max_shift_per_trip_minutes
    ) * (total_bound + 1) + total_bound
    shift_group = model.new_int_var(
        0,
        shift_group_bound,
        "v3_b_preservation_group",
    )
    model.add(
        shift_group
        == (
            (shifted_count * (total_bound + 1) + total_shift)
            * (policy.absolute_max_shift_per_trip_minutes + 1)
            + maximum_shift
        )
        * (total_bound + 1)
        + preferred_exceedance
    )
    proto = model.Proto()
    directional_windows = {
        direction: (
            trips[0].departure_time // 60,
            trips[-1].departure_time // 60,
        )
        for direction, trips in _ordered_directional_trips(problem).items()
    }
    return _Stage2Model(
        model=model,
        departure_by_source_id=hard.departure_by_source_id,
        regime_by_source_id=regime_by_source,
        source_ids_by_regime_id=source_ids_by_regime,
        headway_by_regime_id=headway_by_regime,
        objective_groups=(
            service_continuity_group,
            transition_group,
            tail_group,
            shift_group,
        ),
        variable_count=len(proto.variables),
        constraint_count=len(proto.constraints),
        maximum_departure_domain_width_minutes=max(
            upper - lower for lower, upper in domains.values()
        ),
        full_service_window_domain_count=sum(
            domains[source.trip_id] == directional_windows[source.direction]
            for source in problem.scenario_b.exact_timetable
        ),
    )


def _build_candidate(
    problem: ScheduleProblemV1,
    plan: TripAllocationPlanV1,
    policy: UniformIntegerRegimePolicyV3,
    bundle: _Stage2Model,
    solver: cp_model.CpSolver,
    *,
    status: NativeSolverStatus,
    duration: float,
) -> RawScheduleCandidateV1:
    source_order = tuple(
        sorted(
            problem.scenario_b.exact_timetable,
            key=lambda item: (item.departure_time, item.trip_id),
        )
    )
    c_id_by_source = {
        source.trip_id: f"C-V3-{index:04d}" for index, source in enumerate(source_order, start=1)
    }
    solved = {
        source.trip_id: int(solver.value(bundle.departure_by_source_id[source.trip_id]))
        for source in source_order
    }
    b_minutes = {source.trip_id: source.departure_time // 60 for source in source_order}
    directional = _ordered_directional_trips(problem)
    previous_b: dict[str, float | None] = {}
    previous_c: dict[str, float | None] = {}
    for trips in directional.values():
        previous_b.update(_previous_headways(trips, b_minutes))
        previous_c.update(_previous_headways(trips, solved))
    timetable = tuple(
        sorted(
            (
                RawCandidateTripV1(
                    c_trip_id=c_id_by_source[source.trip_id],
                    source_b_trip_id=source.trip_id,
                    direction=source.direction,
                    departure_terminal=source.departure_terminal,
                    b_departure_time=source.departure_time,
                    c_departure_time=solved[source.trip_id] * 60,
                    arrival_time=(solved[source.trip_id] + source.runtime_minutes) * 60,
                    runtime_minutes=source.runtime_minutes,
                    shift_minutes=float(solved[source.trip_id] - b_minutes[source.trip_id]),
                    previous_b_headway=previous_b[source.trip_id],
                    previous_c_headway=previous_c[source.trip_id],
                    headway_regime_id=(bundle.regime_by_source_id[source.trip_id].regime_id),
                    change_reason=("V3 two-stage B-anchored exact uniform-regime optimization."),
                )
                for source in source_order
            ),
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
    )
    trip_by_source = {trip.source_b_trip_id: trip for trip in timetable}
    raw_regimes: list[RawHeadwayRegimeV1] = []
    for regime in plan.proposed_regimes:
        members = tuple(
            sorted(
                (
                    trip_by_source[source_id]
                    for source_id in bundle.source_ids_by_regime_id[regime.regime_id]
                ),
                key=lambda item: (item.c_departure_time, item.c_trip_id),
            )
        )
        sequence = tuple(
            (later.c_departure_time - earlier.c_departure_time) / 60
            for earlier, later in zip(members, members[1:], strict=False)
        )
        raw_regimes.append(
            RawHeadwayRegimeV1(
                regime_id=regime.regime_id,
                direction=regime.direction,
                start_time=members[0].c_departure_time,
                end_time=members[-1].c_departure_time,
                trip_count=len(members),
                target_headway=float(sequence[0] if sequence else 1),
                actual_headway_sequence=sequence,
                boundary_reason=regime.boundary_reason,
                legacy_regularity_status=(
                    "UNIFORM" if sequence else "SINGLE_TRIP_HEADWAY_NOT_MEASURABLE"
                ),
            )
        )
    regimes = tuple(raw_regimes)
    fingerprint = candidate_fingerprint(
        problem_fingerprint=problem.problem_fingerprint,
        solver_adapter=ORTOOLS_TWO_STAGE_UNIFORM_ADAPTER_ID,
        exact_timetable=timetable,
        headway_regimes=regimes,
        allocation_plan_fingerprint=plan.allocation_fingerprint,
        optimization_mode=problem.optimization_mode,
        demand_allocation_authority_mode=problem.demand_allocation_authority_mode,
        final_tail_policy_fingerprint=plan.final_tail_policy_fingerprint,
    )
    return RawScheduleCandidateV1(
        solver_status=status,
        solver_adapter=ORTOOLS_TWO_STAGE_UNIFORM_ADAPTER_ID,
        solve_duration_seconds=duration,
        candidate_fingerprint=fingerprint,
        exact_timetable=timetable,
        headway_regimes=regimes,
        explanation=(
            f"Stage 2 returned {status.value} under fixed Stage 1 allocation "
            f"{plan.allocation_fingerprint}."
        ),
        limitations=(
            "A FEASIBLE native status is a validated candidate only and is not itself a final "
            "Scenario C recommendation.",
        ),
        allocation_plan_fingerprint=plan.allocation_fingerprint,
        optimization_mode=problem.optimization_mode,
        demand_allocation_authority_mode=problem.demand_allocation_authority_mode,
        uniform_regime_policy_profile=policy.profile,
        final_tail_policy_fingerprint=plan.final_tail_policy_fingerprint,
    )


def _stage_2_infeasibility_diagnostic(
    problem: ScheduleProblemV1,
    plan: TripAllocationPlanV1,
    *,
    protected_projection: OrToolsProtectedFloorProjectionV1 | None,
    domain_failure: bool,
    detail: str,
) -> Stage2InfeasibilityDiagnosticV1:
    if domain_failure:
        families = {
            Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP,
            Stage2ConstraintFamilyV1.REGIME_BOUNDARIES,
            Stage2ConstraintFamilyV1.B_SHIFT_BOUND,
            Stage2ConstraintFamilyV1.FIRST_LAST_LOCK,
            Stage2ConstraintFamilyV1.FINAL_SERVICE_TAIL,
        }
    else:
        families = {
            Stage2ConstraintFamilyV1.ALLOCATION_MEMBERSHIP,
            Stage2ConstraintFamilyV1.UNIFORM_HEADWAY,
            Stage2ConstraintFamilyV1.REGIME_BOUNDARIES,
            Stage2ConstraintFamilyV1.MINIMUM_OPERATIONAL_HEADWAY,
            Stage2ConstraintFamilyV1.B_SHIFT_BOUND,
            Stage2ConstraintFamilyV1.FIRST_LAST_LOCK,
            Stage2ConstraintFamilyV1.FINAL_SERVICE_TAIL,
            Stage2ConstraintFamilyV1.REGIME_TRANSITION_JUMP,
            Stage2ConstraintFamilyV1.SOURCE_RUNTIME,
            Stage2ConstraintFamilyV1.TURNAROUND,
            Stage2ConstraintFamilyV1.FLEET,
        }
        if problem.scenario_b.terminal_occupancy_limits is not None:
            families.add(Stage2ConstraintFamilyV1.TERMINAL_OCCUPANCY)
        if protected_projection is not None:
            families.add(Stage2ConstraintFamilyV1.PROTECTED_SERVICE_FLOOR)
    explanation = (
        "Stage 2 proved this allocation plan infeasible under the encoded constraints. "
        f"{detail} The listed deterministic family classification is diagnostic and is not "
        "claimed to be a mathematically minimal unsat core."
    )
    return finalize_stage_2_infeasibility_diagnostic(
        Stage2InfeasibilityDiagnosticV1(
            allocation_plan_fingerprint=plan.allocation_fingerprint,
            native_solver_status=NativeSolverStatus.INFEASIBLE,
            constraint_families=tuple(sorted(families, key=lambda item: item.value)),
            explanation=explanation,
        )
    )


def solve_exact_timetable_stage_2_v1(
    problem: ScheduleProblemV1,
    plan: TripAllocationPlanV1,
    *,
    policy: UniformIntegerRegimePolicyV3,
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None,
    time_limit_seconds: float,
    worker_count: int = 1,
    random_seed: int = 0,
) -> Stage2TimetableResultV1:
    if (
        isinstance(time_limit_seconds, bool)
        or not isinstance(time_limit_seconds, (int, float))
        or not math.isfinite(time_limit_seconds)
        or time_limit_seconds <= 0
    ):
        raise ValueError("Stage 2 time_limit_seconds must be finite and positive")
    started = time.perf_counter()
    projection = (
        build_ortools_protected_floor_projection_v1(
            protected_service_floor_enforcement_authority,
            problem.scenario_b,
        )
        if protected_service_floor_enforcement_authority is not None
        else None
    )
    try:
        bundle = _build_stage_2_model(problem, plan, policy, projection)
    except ValueError as exc:
        diagnostic = _stage_2_infeasibility_diagnostic(
            problem,
            plan,
            protected_projection=projection,
            domain_failure=True,
            detail=f"A deterministic domain probe failed: {exc}",
        )
        return Stage2TimetableResultV1(
            solver_status=NativeSolverStatus.INFEASIBLE,
            candidate=None,
            allocation_plan=plan,
            solve_duration_seconds=max(0.0, time.perf_counter() - started),
            variable_count=0,
            constraint_count=0,
            maximum_departure_domain_width_minutes=0,
            full_service_window_domain_count=0,
            infeasibility_diagnostic=diagnostic,
            explanations=(diagnostic.explanation,),
            limitations=(),
        )
    latest_solver: cp_model.CpSolver | None = None
    proven_groups = 0
    last_status = NativeSolverStatus.UNKNOWN
    for objective in bundle.objective_groups:
        remaining = max(0.0, time_limit_seconds - (time.perf_counter() - started))
        if remaining <= 0:
            break
        bundle.model.minimize(objective)
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = remaining
        solver.parameters.num_search_workers = worker_count
        solver.parameters.random_seed = random_seed
        last_status = _map_cp_sat_status(solver.solve(bundle.model))
        if last_status == NativeSolverStatus.OPTIMAL:
            optimum = int(solver.value(objective))
            bundle.model.add(objective == optimum)
            latest_solver = solver
            proven_groups += 1
            continue
        if last_status == NativeSolverStatus.FEASIBLE:
            latest_solver = solver
        break
    duration = max(0.0, time.perf_counter() - started)
    if latest_solver is None:
        diagnostic = (
            _stage_2_infeasibility_diagnostic(
                problem,
                plan,
                protected_projection=projection,
                domain_failure=False,
                detail=(
                    "The cheap arithmetic-progression, domain, and fleet lower-bound probes "
                    "passed, so infeasibility arises from one or more interactions among the "
                    "remaining encoded families."
                ),
            )
            if last_status == NativeSolverStatus.INFEASIBLE
            else None
        )
        return Stage2TimetableResultV1(
            solver_status=last_status,
            candidate=None,
            allocation_plan=plan,
            solve_duration_seconds=duration,
            variable_count=bundle.variable_count,
            constraint_count=bundle.constraint_count,
            maximum_departure_domain_width_minutes=(bundle.maximum_departure_domain_width_minutes),
            full_service_window_domain_count=bundle.full_service_window_domain_count,
            infeasibility_diagnostic=diagnostic,
            explanations=(
                diagnostic.explanation
                if diagnostic is not None
                else f"Stage 2 returned {last_status.value} without a timetable.",
            ),
            limitations=(),
        )
    final_status = (
        NativeSolverStatus.OPTIMAL
        if proven_groups == len(bundle.objective_groups)
        else NativeSolverStatus.FEASIBLE
    )
    candidate = _build_candidate(
        problem,
        plan,
        policy,
        bundle,
        latest_solver,
        status=final_status,
        duration=duration,
    )
    return Stage2TimetableResultV1(
        solver_status=final_status,
        candidate=candidate,
        allocation_plan=plan,
        solve_duration_seconds=duration,
        variable_count=bundle.variable_count,
        constraint_count=bundle.constraint_count,
        maximum_departure_domain_width_minutes=(bundle.maximum_departure_domain_width_minutes),
        full_service_window_domain_count=bundle.full_service_window_domain_count,
        infeasibility_diagnostic=None,
        explanations=(candidate.explanation,),
        limitations=candidate.limitations,
    )


def _tail_metrics(
    plan: TripAllocationPlanV1,
    candidate: RawScheduleCandidateV1,
) -> tuple[FinalServiceTailMetricsV1, ...]:
    trip_by_regime: dict[str, list[RawCandidateTripV1]] = {}
    for trip in candidate.exact_timetable:
        trip_by_regime.setdefault(trip.headway_regime_id, []).append(trip)
    output: list[FinalServiceTailMetricsV1] = []
    for regime in plan.proposed_regimes:
        if not regime.is_final_service_tail:
            continue
        members = sorted(
            trip_by_regime[regime.regime_id],
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
        span = (members[-1].c_departure_time - members[0].c_departure_time) // 60
        penultimate = (
            (members[-1].c_departure_time - members[-2].c_departure_time) // 60
            if len(members) >= 2
            else None
        )
        output.append(
            FinalServiceTailMetricsV1(
                direction=regime.direction,
                final_tail_start=members[0].c_departure_time,
                final_tail_end=members[-1].c_departure_time,
                final_tail_span_minutes=span,
                final_tail_trip_count=len(members),
                final_tail_uniform_headway_minutes=(penultimate if len(members) >= 2 else None),
                minutes_from_penultimate_trip_to_last_departure=penultimate,
            )
        )
    return tuple(output)


@dataclass(slots=True)
class OrToolsCpSatTwoStageUniformSolver:
    demand_authority: TwoStageDemandAuthorityV1
    policy: UniformIntegerRegimePolicyV3
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None
    last_detailed_run: TwoStageNativeRunV1 | None = None
    adapter_id: ClassVar[str] = ORTOOLS_TWO_STAGE_UNIFORM_ADAPTER_ID

    @property
    def protected_fingerprint(self) -> str | None:
        authority = self.protected_service_floor_enforcement_authority
        return authority.enforcement_fingerprint if authority is not None else None

    def solve_detailed(self, problem: ScheduleProblemV1) -> TwoStageNativeRunV1:
        started = time.perf_counter()
        issues = _adapter_capability_issues(problem, self.adapter_id)
        expected_context = _adapter_context_fingerprint(
            self.demand_authority,
            self.policy,
            self.protected_fingerprint,
        )
        if problem.adapter_context_fingerprint != expected_context:
            issues = (*issues, TWO_STAGE_ADAPTER_CONTEXT_MISMATCH)
        total_budget = problem.solver_policy.time_limit_seconds
        if total_budget is None:
            issues = (*issues, TWO_STAGE_TOTAL_BUDGET_REQUIRED)
            total_budget = 0.0
        if issues:
            run = SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.MODEL_INVALID,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=max(0.0, time.perf_counter() - started),
                candidate=None,
                explanations=tuple(
                    f"{issue}: two-stage adapter rejected the problem." for issue in issues
                ),
                limitations=(),
            )
            empty_stage1 = allocate_empty_stage_1_result()
            detailed = TwoStageNativeRunV1(
                solver_run=run,
                stage_1_result=empty_stage1,
                selected_allocation_plan=None,
                final_tail_metrics=(),
                diagnostics=_diagnostics(empty_stage1, (), total_budget, started),
            )
            self.last_detailed_run = detailed
            return detailed

        stage_1_budget = min(total_budget, max(0.000001, total_budget * _STAGE_1_BUDGET_SHARE))
        stage_1 = allocate_trips_stage_1_v1(
            problem,
            self.demand_authority,
            policy=self.policy,
            protected_service_floor_enforcement_authority=(
                self.protected_service_floor_enforcement_authority
            ),
            time_limit_seconds=stage_1_budget,
            worker_count=(problem.solver_policy.worker_count or 1),
            random_seed=(problem.solver_policy.random_seed or 0),
        )
        attempts: list[Stage2TimetableResultV1] = []
        chosen: Stage2TimetableResultV1 | None = None
        for plan in stage_1.plans:
            remaining = max(0.0, total_budget - (time.perf_counter() - started))
            if remaining <= 0:
                break
            attempt = solve_exact_timetable_stage_2_v1(
                problem,
                plan,
                policy=self.policy,
                protected_service_floor_enforcement_authority=(
                    self.protected_service_floor_enforcement_authority
                ),
                time_limit_seconds=remaining,
                worker_count=(problem.solver_policy.worker_count or 1),
                random_seed=(problem.solver_policy.random_seed or 0),
            )
            attempts.append(attempt)
            if attempt.candidate is not None:
                chosen = attempt
                break
            if attempt.solver_status != NativeSolverStatus.INFEASIBLE:
                break

        total_duration = max(0.0, time.perf_counter() - started)
        if chosen is not None and chosen.candidate is not None:
            solver_status = chosen.solver_status
            candidate = chosen.candidate
            explanations = (*stage_1.explanations, *chosen.explanations)
            limitations = (*stage_1.limitations, *chosen.limitations)
            selected_plan = chosen.allocation_plan
            tails = _tail_metrics(selected_plan, candidate)
        else:
            selected_plan = stage_1.plans[0] if stage_1.plans else None
            candidate = None
            tails = ()
            bounded_stage_2_plans_proven_infeasible = bool(attempts) and all(
                attempt.solver_status == NativeSolverStatus.INFEASIBLE for attempt in attempts
            )
            if not stage_1.plans:
                solver_status = (
                    NativeSolverStatus.INFEASIBLE
                    if stage_1.solve_status
                    in {
                        TripAllocationSolveStatusV1.INFEASIBLE,
                        TripAllocationSolveStatusV1.UNREPRESENTABLE,
                    }
                    else NativeSolverStatus.UNKNOWN
                )
            else:
                # Stage 1 exposes a bounded top-N plan set, not an exhaustive proof that no
                # other authorized allocation exists.  Preserve each fixed-plan INFEASIBLE
                # result below, but do not promote those local proofs to aggregate infeasibility.
                solver_status = NativeSolverStatus.UNKNOWN
            explanations = (
                *stage_1.explanations,
                *(item for attempt in attempts for item in attempt.explanations),
            )
            limitations = stage_1.limitations
            if bounded_stage_2_plans_proven_infeasible:
                explanations = (
                    *explanations,
                    f"{_BOUNDED_STAGE_1_PLANS_EXHAUSTED_WITHOUT_FEASIBLE_C}: All bounded "
                    "Stage 2 allocation plans attempted in this run were proven infeasible.",
                    "This does not prove that no feasible Scenario C exists under the locked "
                    "Scenario B parameters.",
                )
                if total_duration < total_budget:
                    explanations = (
                        *explanations,
                        "The finite total solve budget was not exhausted; bounded-plan "
                        "exhaustion is not a timeout.",
                    )
                limitations = (
                    *limitations,
                    "All bounded Stage 2 allocation plans attempted in this run were proven "
                    "infeasible. This does not prove that no feasible Scenario C exists under "
                    "the locked Scenario B parameters.",
                )
        run = SolverRunResultV1(
            execution_status=SolverExecutionStatus.COMPLETED,
            solver_status=solver_status,
            solver_adapter=self.adapter_id,
            solve_duration_seconds=total_duration,
            candidate=candidate,
            explanations=tuple(explanations),
            limitations=tuple(limitations),
        )
        detailed = TwoStageNativeRunV1(
            solver_run=run,
            stage_1_result=stage_1,
            selected_allocation_plan=selected_plan,
            final_tail_metrics=tails,
            diagnostics=_diagnostics(stage_1, tuple(attempts), total_budget, started),
        )
        self.last_detailed_run = detailed
        return detailed

    def solve(self, problem: ScheduleProblemV1) -> SolverRunResultV1:
        return self.solve_detailed(problem).solver_run


def allocate_empty_stage_1_result():
    from .two_stage_models import Stage1AllocationResultV1

    return Stage1AllocationResultV1(
        solve_status=TripAllocationSolveStatusV1.NOT_FOUND_WITHIN_SOLVE_LIMIT,
        plans=(),
        candidate_count=0,
        admissible_allocation_count=0,
        necessary_feasibility_pruned_count=0,
        pruned_necessary_feasibility=(),
        solve_duration_seconds=0.0,
        budget_exhausted=False,
        explanations=(),
        limitations=(),
    )


def _diagnostics(
    stage_1,
    attempts: tuple[Stage2TimetableResultV1, ...],
    total_budget: float,
    started: float,
) -> TwoStageSolveDiagnosticsV1:
    selected = next((attempt for attempt in attempts if attempt.candidate is not None), None)
    plan = (
        selected.allocation_plan
        if selected is not None
        else (attempts[0].allocation_plan if attempts else None)
    )
    regime_counts = tuple(
        (
            direction,
            sum(regime.direction == direction for regime in plan.proposed_regimes) if plan else 0,
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    )
    total_duration = max(0.0, time.perf_counter() - started)
    return TwoStageSolveDiagnosticsV1(
        stage_1_candidate_count=stage_1.candidate_count,
        stage_1_admissible_allocation_count=stage_1.admissible_allocation_count,
        stage_1_necessary_feasibility_pruned_count=(stage_1.necessary_feasibility_pruned_count),
        stage_2_allocation_attempt_count=len(attempts),
        stage_2_variable_count=sum(item.variable_count for item in attempts),
        stage_2_constraint_count=sum(item.constraint_count for item in attempts),
        maximum_stage_2_departure_domain_width_minutes=max(
            (item.maximum_departure_domain_width_minutes for item in attempts),
            default=0,
        ),
        full_service_window_domain_count=sum(
            item.full_service_window_domain_count for item in attempts
        ),
        regime_count_by_direction=regime_counts,
        solve_duration_stage_1=stage_1.solve_duration_seconds,
        solve_duration_stage_2=sum(item.solve_duration_seconds for item in attempts),
        total_solve_duration=total_duration,
        total_budget_seconds=total_budget,
        budget_exhausted=total_duration >= total_budget if total_budget > 0 else True,
        stage_2_infeasibility_diagnostics=tuple(
            item.infeasibility_diagnostic
            for item in attempts
            if item.infeasibility_diagnostic is not None
        ),
    )


def build_two_stage_uniform_request_v1(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    *,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    solver_policy: SolverPolicyV1 | None = None,
    uniform_regime_policy: UniformIntegerRegimePolicyV3 | None = None,
    protected_service_floor_enforcement_authority: (
        ProtectedServiceFloorEnforcementAuthorityV1 | None
    ) = None,
) -> tuple[ScheduleGenerationContextV1, OrToolsCpSatTwoStageUniformSolver]:
    if normalized_inputs.optimization_mode != (
        ScenarioCOptimizationModeV1.B_ANCHORED_TWO_STAGE_REBALANCE
    ):
        raise ScheduleProblemError(
            "The V3 two-stage request requires explicit B-anchored normalization.",
            code=TWO_STAGE_ADAPTER_CONTEXT_MISMATCH,
        )
    effective_evaluation_policy = evaluation_policy or ScenarioBEvaluationPolicyV1()
    effective_policy = uniform_regime_policy or UniformIntegerRegimePolicyV3()
    effective_solver_policy = solver_policy or SolverPolicyV1(
        time_limit_seconds=_DEFAULT_TOTAL_BUDGET_SECONDS
    )
    if effective_solver_policy.time_limit_seconds is None:
        effective_solver_policy = SolverPolicyV1(
            time_limit_seconds=_DEFAULT_TOTAL_BUDGET_SECONDS,
            worker_count=effective_solver_policy.worker_count,
            random_seed=effective_solver_policy.random_seed,
            require_independent_validation=effective_solver_policy.require_independent_validation,
        )
    demand_authority = build_two_stage_demand_authority_v1(
        normalized_inputs,
        b_evaluation,
    )
    protected_fingerprint = (
        protected_service_floor_enforcement_authority.enforcement_fingerprint
        if protected_service_floor_enforcement_authority is not None
        else None
    )
    adapter_context = _adapter_context_fingerprint(
        demand_authority,
        effective_policy,
        protected_fingerprint,
    )
    adapter_locks = {
        "scenario_c_optimization_mode": normalized_inputs.optimization_mode.value,
        "demand_allocation_authority_mode": demand_authority.authority_mode.value,
        "allocation_plan_profile": effective_policy.allocation_plan_profile,
        "uniform_regime_policy_profile": effective_policy.profile,
        "uniform_regime_policy_fingerprint": effective_policy.policy_fingerprint,
        "final_service_tail_policy": jsonable(asdict(effective_policy.final_service_tail)),
        "preferred_max_shift_per_trip_minutes": (
            effective_policy.preferred_max_shift_per_trip_minutes
        ),
        "absolute_max_shift_per_trip_minutes": (
            effective_policy.absolute_max_shift_per_trip_minutes
        ),
        "minimum_operational_headway_minutes": (
            effective_policy.minimum_operational_headway_minutes
        ),
        "maximum_regime_boundary_adjustment_minutes": (
            effective_policy.maximum_regime_boundary_adjustment_minutes
        ),
    }
    problem = build_schedule_problem_v1(
        normalized_inputs,
        b_evaluation,
        solver_adapter=ORTOOLS_TWO_STAGE_UNIFORM_ADAPTER_ID,
        adapter_context_fingerprint=adapter_context,
        evaluation_policy=effective_evaluation_policy,
        solver_policy=effective_solver_policy,
        direction_trip_lock_mode=DirectionTripLockMode.FIXED_BY_DIRECTION,
        fleet_constraint_mode=FleetConstraintMode.AVAILABLE_UPPER_BOUND,
        initial_fleet_positioning_mode=InitialFleetPositioningMode.SOLVER_DETERMINED,
        boundary_convention=BoundaryConvention.HALF_OPEN,
        adapter_operating_lock_values=adapter_locks,
        demand_allocation_authority_mode=demand_authority.authority_mode,
    )
    context = build_schedule_generation_context_v1(
        problem,
        normalized_inputs,
        b_evaluation,
        effective_evaluation_policy,
        protected_service_floor_enforcement_authority,
    )
    return context, OrToolsCpSatTwoStageUniformSolver(
        demand_authority=demand_authority,
        policy=effective_policy,
        protected_service_floor_enforcement_authority=(
            protected_service_floor_enforcement_authority
        ),
    )


__all__ = [
    "ORTOOLS_TWO_STAGE_UNIFORM_ADAPTER_ID",
    "TWO_STAGE_ADAPTER_CONTEXT_MISMATCH",
    "TWO_STAGE_ADAPTER_CONTEXT_PROFILE_V1",
    "TWO_STAGE_TOTAL_BUDGET_REQUIRED",
    "OrToolsCpSatTwoStageUniformSolver",
    "build_two_stage_uniform_request_v1",
    "solve_exact_timetable_stage_2_v1",
]
