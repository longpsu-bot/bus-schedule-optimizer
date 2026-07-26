"""OR-Tools CP-SAT fixed-resource service-quality optimization for Contract V1."""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import ClassVar

import ortools
from ortools.sat.python import cp_model

from .evaluation import ScenarioBEvaluationBundleV1, ScenarioBEvaluationPolicyV1
from .models import ContractDirection, NormalizedInputBundleV1
from .ortools_solver import (
    _adapter_capability_issues,
    _bounded_sum_var,
    _build_demand_cp_sat_model,
    _demand_problem_authority_issues,
    _demand_request_authority_issues,
    _DemandCpSatModelBundle,
    _DemandObjectiveStage,
    _map_cp_sat_status,
    _ordered_directional_trips,
    _previous_headways,
    _regularity_status,
    _solver_controls,
)
from .service_quality_metrics import (
    SERVICE_QUALITY_OBJECTIVE_NAMES_V1 as _QUALITY_OBJECTIVE_NAMES,
)
from .service_quality_metrics import (
    _derive_sustained_service_regimes,
    _QualityModelError,
    _regime_for_departure,
    _scaled_directional_demand,
    _SustainedServiceRegime,
)
from .service_quality_metrics import (
    recompute_service_quality_objective_vector_v1 as _recompute_service_quality_objective_vector_v1,
)
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
    empty_adapter_context_fingerprint,
)

ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY = (
    "ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY"
)
_QUALITY_BOUNDARY_REASON = "SUSTAINED_DIRECTIONAL_SERVICE_RATE"
_SINGLETON_TARGET_HEADWAY_MINUTES = 1.0


@dataclass(frozen=True, slots=True)
class _QualityCpSatModelBundle:
    demand: _DemandCpSatModelBundle
    regimes: tuple[_SustainedServiceRegime, ...]
    stages: tuple[_DemandObjectiveStage, ...]


def _quality_problem_authority_issues(problem: ScheduleProblemV1) -> tuple[str, ...]:
    demand_issues = list(_demand_problem_authority_issues(problem))
    if demand_issues and demand_issues[0].endswith("REQUIRES_DIRECTIONAL_AUTHORITY"):
        demand_issues = demand_issues[1:]
    issues = demand_issues
    for check in (_scaled_directional_demand, _derive_sustained_service_regimes):
        try:
            check(problem)
        except _QualityModelError as exc:
            issues.append(exc.code)
    deduplicated = tuple(dict.fromkeys(issues))
    if not deduplicated:
        return ()
    return (ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY, *deduplicated)


def _equivalent_and(
    model: cp_model.CpModel,
    values: list[cp_model.IntVar],
    *,
    name: str,
) -> cp_model.IntVar:
    result = model.new_bool_var(name)
    for value in values:
        model.add(result <= value)
    model.add(result >= sum(values) - len(values) + 1)
    return result


def _equivalent_or(
    model: cp_model.CpModel,
    values: list[cp_model.IntVar],
    *,
    name: str,
) -> cp_model.IntVar:
    result = model.new_bool_var(name)
    for value in values:
        model.add(result >= value)
    model.add(result <= sum(values))
    return result


def _conditional_value(
    model: cp_model.CpModel,
    expression,
    active: cp_model.IntVar,
    *,
    upper_bound: int,
    name: str,
) -> cp_model.IntVar:
    result = model.new_int_var(0, upper_bound, name)
    model.add(result == expression).only_enforce_if(active)
    model.add(result == 0).only_enforce_if(active.negated())
    return result


def _max_or_zero(
    model: cp_model.CpModel,
    values: list[cp_model.IntVar],
    *,
    upper_bound: int,
    name: str,
) -> cp_model.IntVar:
    result = model.new_int_var(0, upper_bound, name)
    if values:
        model.add_max_equality(result, values)
    else:
        model.add(result == 0)
    return result


def _first_or_last_member(
    model: cp_model.CpModel,
    member: cp_model.IntVar,
    excluded_members: list[cp_model.IntVar],
    *,
    name: str,
) -> cp_model.IntVar:
    result = model.new_bool_var(name)
    model.add(result <= member)
    for excluded in excluded_members:
        model.add(result + excluded <= 1)
    model.add(result >= member - sum(excluded_members))
    return result


def _build_quality_cp_sat_model(problem: ScheduleProblemV1) -> _QualityCpSatModelBundle:
    demand = _build_demand_cp_sat_model(problem)
    model = demand.hard.model
    directional = _ordered_directional_trips(problem)
    requirements = {item.block_id: item for item in problem.block_requirements}
    regimes = _derive_sustained_service_regimes(problem)
    scaled_demand = _scaled_directional_demand(problem)

    headway_by_direction: dict[ContractDirection, list[cp_model.IntVar]] = {}
    active_positive_headways: list[cp_model.IntVar] = []
    maximum_directional_span = 0
    for direction, trips in directional.items():
        span = (
            trips[-1].departure_time // 60 - trips[0].departure_time // 60 if len(trips) > 1 else 0
        )
        maximum_directional_span = max(maximum_directional_span, span)
        headways: list[cp_model.IntVar] = []
        positive_blocks = tuple(
            block
            for block in problem.analysis_blocks
            if block.direction == direction and requirements[block.block_id].passenger_demand > 0
        )
        for index, (earlier, later) in enumerate(
            zip(trips, trips[1:], strict=False),
            start=1,
        ):
            earlier_departure = demand.hard.departure_by_source_id[earlier.trip_id]
            later_departure = demand.hard.departure_by_source_id[later.trip_id]
            headway = model.new_int_var(
                1,
                span,
                f"quality_headway_{direction.value}_{index:04d}",
            )
            model.add(headway == later_departure - earlier_departure)
            headways.append(headway)

            overlap_values: list[cp_model.IntVar] = []
            for block in positive_blocks:
                start = block.start_time // 60
                end = block.end_time // 60
                earlier_before_end = model.new_bool_var(
                    f"quality_earlier_before_end_{index:04d}_{block.block_id}"
                )
                later_after_start = model.new_bool_var(
                    f"quality_later_after_start_{index:04d}_{block.block_id}"
                )
                model.add(earlier_departure <= end - 1).only_enforce_if(earlier_before_end)
                model.add(earlier_departure >= end).only_enforce_if(earlier_before_end.negated())
                model.add(later_departure >= start + 1).only_enforce_if(later_after_start)
                model.add(later_departure <= start).only_enforce_if(later_after_start.negated())
                overlap_values.append(
                    _equivalent_and(
                        model,
                        [earlier_before_end, later_after_start],
                        name=f"quality_overlap_{index:04d}_{block.block_id}",
                    )
                )
            if overlap_values:
                overlaps_positive_demand = _equivalent_or(
                    model,
                    overlap_values,
                    name=f"quality_positive_overlap_{direction.value}_{index:04d}",
                )
                active_positive_headways.append(
                    _conditional_value(
                        model,
                        headway,
                        overlaps_positive_demand,
                        upper_bound=span,
                        name=f"quality_active_positive_headway_{direction.value}_{index:04d}",
                    )
                )
        headway_by_direction[direction] = headways

    maximum_positive_headway = _max_or_zero(
        model,
        active_positive_headways,
        upper_bound=maximum_directional_span,
        name=_QUALITY_OBJECTIVE_NAMES[5],
    )

    block_max_gap_values: list[cp_model.IntVar] = []
    total_positive_block_duration = 0
    for block in sorted(
        problem.analysis_blocks,
        key=lambda item: (
            item.direction.value,
            item.start_time,
            item.end_time,
            item.block_id,
        ),
    ):
        if requirements[block.block_id].passenger_demand <= 0:
            continue
        trips = directional[block.direction]
        members = [
            demand.membership_by_source_and_block[(trip.trip_id, block.block_id)] for trip in trips
        ]
        duration = (block.end_time - block.start_time) // 60
        total_positive_block_duration += duration
        gap_values: list[cp_model.IntVar] = []
        for index, trip in enumerate(trips):
            departure = demand.hard.departure_by_source_id[trip.trip_id]
            first_member = _first_or_last_member(
                model,
                members[index],
                members[:index],
                name=f"quality_first_member_{trip.trip_id}_{block.block_id}",
            )
            last_member = _first_or_last_member(
                model,
                members[index],
                members[index + 1 :],
                name=f"quality_last_member_{trip.trip_id}_{block.block_id}",
            )
            gap_values.append(
                _conditional_value(
                    model,
                    departure - block.start_time // 60,
                    first_member,
                    upper_bound=duration,
                    name=f"quality_start_gap_{trip.trip_id}_{block.block_id}",
                )
            )
            gap_values.append(
                _conditional_value(
                    model,
                    block.end_time // 60 - departure,
                    last_member,
                    upper_bound=duration,
                    name=f"quality_end_gap_{trip.trip_id}_{block.block_id}",
                )
            )
        for index, (earlier_member, later_member) in enumerate(
            zip(members, members[1:], strict=False),
            start=1,
        ):
            internal = _equivalent_and(
                model,
                [earlier_member, later_member],
                name=f"quality_internal_pair_{index:04d}_{block.block_id}",
            )
            gap_values.append(
                _conditional_value(
                    model,
                    headway_by_direction[block.direction][index - 1],
                    internal,
                    upper_bound=duration,
                    name=f"quality_internal_gap_{index:04d}_{block.block_id}",
                )
            )
        has_service = model.new_bool_var(f"quality_has_service_{block.block_id}")
        block_count = demand.block_trip_count_by_id[block.block_id]
        model.add(block_count >= 1).only_enforce_if(has_service)
        model.add(block_count == 0).only_enforce_if(has_service.negated())
        full_duration = model.new_int_var(
            0,
            duration,
            f"quality_no_service_full_gap_{block.block_id}",
        )
        model.add(full_duration == 0).only_enforce_if(has_service)
        model.add(full_duration == duration).only_enforce_if(has_service.negated())
        gap_values.append(full_duration)
        block_max_gap_values.append(
            _max_or_zero(
                model,
                gap_values,
                upper_bound=duration,
                name=f"quality_block_max_gap_{block.block_id}",
            )
        )
    total_positive_block_max_gap = _bounded_sum_var(
        model,
        block_max_gap_values,
        upper_bound=total_positive_block_duration,
        name=_QUALITY_OBJECTIVE_NAMES[6],
    )

    alignment_values: list[cp_model.IntVar] = []
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        total_weight = scaled_demand.total_by_direction[direction]
        trip_count = (
            problem.scenario_b.trips_by_direction.outbound
            if direction == ContractDirection.OUTBOUND
            else problem.scenario_b.trips_by_direction.inbound
        )
        if total_weight == 0:
            continue
        per_block_bound = trip_count * total_weight
        for block in problem.analysis_blocks:
            if block.direction != direction:
                continue
            error = model.new_int_var(
                0,
                per_block_bound,
                f"quality_alignment_error_{block.block_id}",
            )
            model.add_abs_equality(
                error,
                demand.block_trip_count_by_id[block.block_id] * total_weight
                - trip_count * scaled_demand.weight_by_block_id[block.block_id],
            )
            alignment_values.append(error)
    alignment_error = _bounded_sum_var(
        model,
        alignment_values,
        upper_bound=scaled_demand.total_alignment_upper_bound,
        name=_QUALITY_OBJECTIVE_NAMES[7],
    )

    regime_membership: dict[tuple[str, str], cp_model.IntVar] = {}
    for trip in problem.scenario_b.exact_timetable:
        for regime in regimes:
            if regime.direction != trip.direction:
                continue
            value = model.new_bool_var(f"quality_regime_member_{trip.trip_id}_{regime.regime_id}")
            model.add(
                value
                == sum(
                    demand.membership_by_source_and_block[(trip.trip_id, block_id)]
                    for block_id in regime.block_ids
                )
            )
            regime_membership[(trip.trip_id, regime.regime_id)] = value

    within_changes: list[cp_model.IntVar] = []
    transition_jumps: list[cp_model.IntVar] = []
    for direction, trips in directional.items():
        span = (
            trips[-1].departure_time // 60 - trips[0].departure_time // 60 if len(trips) > 1 else 0
        )
        directional_regimes = tuple(item for item in regimes if item.direction == direction)
        for index in range(1, len(trips) - 1):
            change = model.new_int_var(
                0,
                span,
                f"quality_headway_change_{direction.value}_{index:04d}",
            )
            model.add_abs_equality(
                change,
                headway_by_direction[direction][index] - headway_by_direction[direction][index - 1],
            )
            same_values = [
                _equivalent_and(
                    model,
                    [
                        regime_membership[(trips[index - 1].trip_id, regime.regime_id)],
                        regime_membership[(trips[index].trip_id, regime.regime_id)],
                        regime_membership[(trips[index + 1].trip_id, regime.regime_id)],
                    ],
                    name=(f"quality_triple_same_{direction.value}_{index:04d}_{regime.regime_id}"),
                )
                for regime in directional_regimes
            ]
            all_same = _equivalent_or(
                model,
                same_values,
                name=f"quality_triple_within_{direction.value}_{index:04d}",
            )
            within_changes.append(
                _conditional_value(
                    model,
                    change,
                    all_same,
                    upper_bound=span,
                    name=f"quality_within_change_{direction.value}_{index:04d}",
                )
            )
            transition_jumps.append(
                _conditional_value(
                    model,
                    change,
                    all_same.negated(),
                    upper_bound=span,
                    name=f"quality_transition_jump_{direction.value}_{index:04d}",
                )
            )

    maximum_within_change = _max_or_zero(
        model,
        within_changes,
        upper_bound=maximum_directional_span,
        name=_QUALITY_OBJECTIVE_NAMES[8],
    )
    total_within_change = _bounded_sum_var(
        model,
        within_changes,
        upper_bound=sum(
            max(0, len(trips) - 2)
            * (
                trips[-1].departure_time // 60 - trips[0].departure_time // 60
                if len(trips) > 1
                else 0
            )
            for trips in directional.values()
        ),
        name=_QUALITY_OBJECTIVE_NAMES[9],
    )
    maximum_transition_jump = _max_or_zero(
        model,
        transition_jumps,
        upper_bound=maximum_directional_span,
        name=_QUALITY_OBJECTIVE_NAMES[10],
    )
    total_transition_jump = _bounded_sum_var(
        model,
        transition_jumps,
        upper_bound=sum(
            max(0, len(trips) - 2)
            * (
                trips[-1].departure_time // 60 - trips[0].departure_time // 60
                if len(trips) > 1
                else 0
            )
            for trips in directional.values()
        ),
        name=_QUALITY_OBJECTIVE_NAMES[11],
    )

    quality_values = (
        maximum_positive_headway,
        total_positive_block_max_gap,
        alignment_error,
        maximum_within_change,
        total_within_change,
        maximum_transition_jump,
        total_transition_jump,
    )
    stage_values = (
        *(stage.value for stage in demand.stages[:5]),
        *quality_values,
        *(stage.value for stage in demand.stages[5:]),
    )
    return _QualityCpSatModelBundle(
        demand=demand,
        regimes=regimes,
        stages=tuple(
            _DemandObjectiveStage(name=name, value=value)
            for name, value in zip(_QUALITY_OBJECTIVE_NAMES, stage_values, strict=True)
        ),
    )


def _quality_solver_limitations(problem: ScheduleProblemV1) -> tuple[str, ...]:
    time_limit, worker_count, random_seed = _solver_controls(problem)
    configured_time_limit = "none" if time_limit is None else f"{time_limit:g} seconds"
    return (
        f"OR-Tools version {ortools.__version__}; total staged-solve time limit: "
        f"{configured_time_limit}; worker count: {worker_count}; random seed: {random_seed}.",
        "Milestone 4A2 optimizes fixed-resource demand protection, positive-demand "
        "service gaps, proportional directional-demand alignment, and sustained-regime "
        "headway regularity before B-preservation shift tie-breaks.",
        "Variable trip counts, directional trip-count redistribution, fleet minimization, "
        "heuristic comparison, application solver selection, UI, charts, and XLSX are "
        "not optimized or integrated by this adapter.",
        "Sustained service regimes are derived from authoritative directional demand blocks "
        "and exact planning service-rate equality; they are not directly passenger-supplied.",
    )


def _model_invalid_result(
    problem: ScheduleProblemV1,
    adapter_id: str,
    started: float,
    issues: tuple[str, ...],
) -> SolverRunResultV1:
    return SolverRunResultV1(
        execution_status=SolverExecutionStatus.COMPLETED,
        solver_status=NativeSolverStatus.MODEL_INVALID,
        solver_adapter=adapter_id,
        solve_duration_seconds=max(0.0, time.perf_counter() - started),
        candidate=None,
        explanations=tuple(
            f"{issue}: service-quality adapter rejected the problem." for issue in issues
        ),
        limitations=(
            *_quality_solver_limitations(problem),
            "MODEL_INVALID identifies an adapter capability, precision, integer-safety, "
            "or integration defect; it is not timetable or fleet infeasibility.",
        ),
    )


def _build_quality_candidate(
    problem: ScheduleProblemV1,
    bundle: _QualityCpSatModelBundle,
    solver: cp_model.CpSolver,
    *,
    status: NativeSolverStatus,
    duration: float,
    attempted: tuple[str, ...],
    proven: tuple[tuple[str, int], ...],
    adapter_id: str,
) -> RawScheduleCandidateV1:
    directional = _ordered_directional_trips(problem)
    source_order = tuple(
        sorted(
            problem.scenario_b.exact_timetable,
            key=lambda item: (item.departure_time, item.trip_id),
        )
    )
    c_id_by_source_id = {
        trip.trip_id: f"C-ORTOOLS-{index:04d}" for index, trip in enumerate(source_order, start=1)
    }
    solved_minutes = {
        trip.trip_id: solver.value(bundle.demand.hard.departure_by_source_id[trip.trip_id])
        for trip in source_order
    }
    b_minutes = {trip.trip_id: trip.departure_time // 60 for trip in source_order}
    previous_b: dict[str, float | None] = {}
    previous_c: dict[str, float | None] = {}
    for trips in directional.values():
        previous_b.update(_previous_headways(trips, b_minutes))
        previous_c.update(_previous_headways(trips, solved_minutes))

    regime_by_source_id = {
        trip.trip_id: _regime_for_departure(
            problem,
            bundle.regimes,
            trip.direction,
            solved_minutes[trip.trip_id] * 60,
        )
        for trip in source_order
    }
    exact_timetable = tuple(
        sorted(
            (
                RawCandidateTripV1(
                    c_trip_id=c_id_by_source_id[trip.trip_id],
                    source_b_trip_id=trip.trip_id,
                    direction=trip.direction,
                    departure_terminal=trip.departure_terminal,
                    b_departure_time=trip.departure_time,
                    c_departure_time=solved_minutes[trip.trip_id] * 60,
                    arrival_time=(solved_minutes[trip.trip_id] + trip.runtime_minutes) * 60,
                    runtime_minutes=trip.runtime_minutes,
                    shift_minutes=float(solved_minutes[trip.trip_id] - b_minutes[trip.trip_id]),
                    previous_b_headway=previous_b[trip.trip_id],
                    previous_c_headway=previous_c[trip.trip_id],
                    headway_regime_id=regime_by_source_id[trip.trip_id].regime_id,
                    change_reason=(
                        "OR-Tools lexicographic fixed-resource service-quality optimization."
                    ),
                )
                for trip in source_order
            ),
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
    )

    raw_regimes: list[RawHeadwayRegimeV1] = []
    extra_limitations: list[str] = []
    for regime in bundle.regimes:
        members = tuple(
            sorted(
                (trip for trip in exact_timetable if trip.headway_regime_id == regime.regime_id),
                key=lambda item: (item.c_departure_time, item.c_trip_id),
            )
        )
        if not members:
            continue
        headways = tuple(
            float((later.c_departure_time - earlier.c_departure_time) // 60)
            for earlier, later in zip(members, members[1:], strict=False)
        )
        if len(members) == 1:
            target = _SINGLETON_TARGET_HEADWAY_MINUTES
            extra_limitations.append(
                f"{regime.regime_id} contains one solved trip, so headway is not "
                f"measurable and the {_SINGLETON_TARGET_HEADWAY_MINUTES:g}-minute "
                "positive placeholder target is used."
            )
        elif regime.required_trips_85 > 0:
            target = regime.duration_minutes / regime.required_trips_85
        else:
            target = _SINGLETON_TARGET_HEADWAY_MINUTES
            extra_limitations.append(
                f"{regime.regime_id} has a zero planning service rate; its descriptive "
                f"target uses the positive {_SINGLETON_TARGET_HEADWAY_MINUTES:g}-minute "
                "placeholder."
            )
        raw_regimes.append(
            RawHeadwayRegimeV1(
                regime_id=regime.regime_id,
                direction=regime.direction,
                start_time=members[0].c_departure_time,
                end_time=members[-1].c_departure_time,
                trip_count=len(members),
                target_headway=target,
                actual_headway_sequence=headways,
                boundary_reason=_QUALITY_BOUNDARY_REASON,
                legacy_regularity_status=_regularity_status(headways),
            )
        )
    regimes = tuple(raw_regimes)
    provisional = RawScheduleCandidateV1(
        solver_status=status,
        solver_adapter=adapter_id,
        solve_duration_seconds=duration,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=problem.problem_fingerprint,
            solver_adapter=adapter_id,
            exact_timetable=exact_timetable,
            headway_regimes=regimes,
        ),
        exact_timetable=exact_timetable,
        headway_regimes=regimes,
        explanation="Service-quality explanation pending independent recomputation.",
        limitations=(*_quality_solver_limitations(problem), *extra_limitations),
    )
    vector = _recompute_service_quality_objective_vector_v1(problem, provisional)
    for name, proven_value in proven:
        recomputed = vector[_QUALITY_OBJECTIVE_NAMES.index(name)]
        if recomputed != proven_value:
            raise ValueError(
                f"Independently recomputed {name}={recomputed} does not match "
                f"solver-proven value {proven_value}"
            )
    proven_by_name = dict(proven)
    stage_values = ", ".join(
        f"{name}={value}" + (" (proven)" if name in proven_by_name else " (candidate; unproven)")
        for name, value in zip(_QUALITY_OBJECTIVE_NAMES, vector, strict=True)
    )
    unproven = tuple(name for name in _QUALITY_OBJECTIVE_NAMES if name not in proven_by_name)
    explanation = (
        f"CP-SAT service-quality staged solve returned {status.value}. "
        f"Objective stages attempted: {', '.join(attempted) if attempted else 'none'}. "
        "Objective stages proven optimal: "
        f"{', '.join(f'{name}={value}' for name, value in proven) if proven else 'none'}. "
        f"Independently recomputed candidate vector: ({', '.join(map(str, vector))}). "
        f"Stage values: {stage_values}. "
        f"Unproven current/later stages: {', '.join(unproven) if unproven else 'none'}. "
        "Variable trip counts and fleet minimization were not optimized."
    )
    return replace(provisional, explanation=explanation)


def _quality_non_candidate_result(
    problem: ScheduleProblemV1,
    *,
    adapter_id: str,
    status: NativeSolverStatus,
    duration: float,
    attempted: tuple[str, ...],
    proven: tuple[tuple[str, int], ...],
    detail: str,
) -> SolverRunResultV1:
    return SolverRunResultV1(
        execution_status=SolverExecutionStatus.COMPLETED,
        solver_status=status,
        solver_adapter=adapter_id,
        solve_duration_seconds=duration,
        candidate=None,
        explanations=(
            f"{detail} Objective stages attempted: "
            f"{', '.join(attempted) if attempted else 'none'}. "
            "Objective stages proven optimal: "
            f"{', '.join(f'{name}={value}' for name, value in proven) if proven else 'none'}.",
        ),
        limitations=_quality_solver_limitations(problem),
    )


@dataclass(frozen=True, slots=True)
class OrToolsCpSatServiceQualitySolver:
    adapter_id: ClassVar[str] = "ortools_cp_sat_quality_v1"

    def solve(self, problem: ScheduleProblemV1) -> SolverRunResultV1:
        started = time.perf_counter()
        issues = (
            *_adapter_capability_issues(problem, self.adapter_id),
            *_quality_problem_authority_issues(problem),
        )
        issues = tuple(dict.fromkeys(issues))
        if issues:
            return _model_invalid_result(problem, self.adapter_id, started, issues)
        try:
            bundle = _build_quality_cp_sat_model(problem)
            model_error = bundle.demand.hard.model.validate()
            if model_error:
                return _model_invalid_result(
                    problem,
                    self.adapter_id,
                    started,
                    ("ORTOOLS_CP_SAT_MODEL_VALIDATION_FAILED",),
                )

            time_limit, worker_count, random_seed = _solver_controls(problem)
            attempted: list[str] = []
            proven: list[tuple[str, int]] = []
            latest_solver: cp_model.CpSolver | None = None
            for stage in bundle.stages:
                elapsed = max(0.0, time.perf_counter() - started)
                remaining = None if time_limit is None else max(0.0, time_limit - elapsed)
                if remaining is not None and remaining <= 0:
                    duration = max(0.0, time.perf_counter() - started)
                    if latest_solver is None:
                        return _quality_non_candidate_result(
                            problem,
                            adapter_id=self.adapter_id,
                            status=NativeSolverStatus.UNKNOWN,
                            duration=duration,
                            attempted=tuple(attempted),
                            proven=tuple(proven),
                            detail="The adapter time budget expired before the first stage.",
                        )
                    candidate = _build_quality_candidate(
                        problem,
                        bundle,
                        latest_solver,
                        status=NativeSolverStatus.FEASIBLE,
                        duration=duration,
                        attempted=tuple(attempted),
                        proven=tuple(proven),
                        adapter_id=self.adapter_id,
                    )
                    return SolverRunResultV1(
                        execution_status=SolverExecutionStatus.COMPLETED,
                        solver_status=NativeSolverStatus.FEASIBLE,
                        solver_adapter=self.adapter_id,
                        solve_duration_seconds=duration,
                        candidate=candidate,
                        explanations=(candidate.explanation,),
                        limitations=candidate.limitations,
                    )

                attempted.append(stage.name)
                bundle.demand.hard.model.minimize(stage.value)
                solver = cp_model.CpSolver()
                if remaining is not None:
                    solver.parameters.max_time_in_seconds = remaining
                solver.parameters.num_search_workers = worker_count
                solver.parameters.random_seed = random_seed
                native_status = _map_cp_sat_status(solver.solve(bundle.demand.hard.model))
                duration = max(0.0, time.perf_counter() - started)

                if native_status == NativeSolverStatus.OPTIMAL:
                    stage_value = int(solver.value(stage.value))
                    proven.append((stage.name, stage_value))
                    bundle.demand.hard.model.add(stage.value == stage_value)
                    latest_solver = solver
                    continue
                if native_status == NativeSolverStatus.FEASIBLE:
                    candidate = _build_quality_candidate(
                        problem,
                        bundle,
                        solver,
                        status=NativeSolverStatus.FEASIBLE,
                        duration=duration,
                        attempted=tuple(attempted),
                        proven=tuple(proven),
                        adapter_id=self.adapter_id,
                    )
                    return SolverRunResultV1(
                        execution_status=SolverExecutionStatus.COMPLETED,
                        solver_status=NativeSolverStatus.FEASIBLE,
                        solver_adapter=self.adapter_id,
                        solve_duration_seconds=duration,
                        candidate=candidate,
                        explanations=(candidate.explanation,),
                        limitations=candidate.limitations,
                    )
                if native_status == NativeSolverStatus.UNKNOWN and latest_solver is not None:
                    candidate = _build_quality_candidate(
                        problem,
                        bundle,
                        latest_solver,
                        status=NativeSolverStatus.FEASIBLE,
                        duration=duration,
                        attempted=tuple(attempted),
                        proven=tuple(proven),
                        adapter_id=self.adapter_id,
                    )
                    return SolverRunResultV1(
                        execution_status=SolverExecutionStatus.COMPLETED,
                        solver_status=NativeSolverStatus.FEASIBLE,
                        solver_adapter=self.adapter_id,
                        solve_duration_seconds=duration,
                        candidate=candidate,
                        explanations=(candidate.explanation,),
                        limitations=candidate.limitations,
                    )
                return _quality_non_candidate_result(
                    problem,
                    adapter_id=self.adapter_id,
                    status=native_status,
                    duration=duration,
                    attempted=tuple(attempted),
                    proven=tuple(proven),
                    detail={
                        NativeSolverStatus.UNKNOWN: (
                            "CP-SAT returned UNKNOWN before finding a candidate."
                        ),
                        NativeSolverStatus.INFEASIBLE: (
                            "CP-SAT proved the encoded fixed-resource quality model infeasible."
                        ),
                        NativeSolverStatus.MODEL_INVALID: (
                            "CP-SAT reported that the encoded quality model is invalid."
                        ),
                    }[native_status],
                )

            duration = max(0.0, time.perf_counter() - started)
            if latest_solver is None:
                return _quality_non_candidate_result(
                    problem,
                    adapter_id=self.adapter_id,
                    status=NativeSolverStatus.UNKNOWN,
                    duration=duration,
                    attempted=tuple(attempted),
                    proven=tuple(proven),
                    detail="No service-quality stage produced a candidate.",
                )
            candidate = _build_quality_candidate(
                problem,
                bundle,
                latest_solver,
                status=NativeSolverStatus.OPTIMAL,
                duration=duration,
                attempted=tuple(attempted),
                proven=tuple(proven),
                adapter_id=self.adapter_id,
            )
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.OPTIMAL,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=duration,
                candidate=candidate,
                explanations=(candidate.explanation,),
                limitations=candidate.limitations,
            )
        except Exception:
            return _model_invalid_result(
                problem,
                self.adapter_id,
                started,
                ("ORTOOLS_QUALITY_ADAPTER_FAILURE",),
            )


def build_ortools_service_quality_request_v1(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    *,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    solver_policy: SolverPolicyV1 | None = None,
) -> tuple[
    ScheduleGenerationContextV1,
    OrToolsCpSatServiceQualitySolver,
]:
    request_issues = _demand_request_authority_issues(normalized_inputs, b_evaluation)
    if request_issues:
        raise ScheduleProblemError(
            f"{ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY}: "
            + ", ".join(request_issues),
            code=ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY,
            codes=(
                ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY,
                *request_issues,
            ),
        )
    problem = build_schedule_problem_v1(
        normalized_inputs,
        b_evaluation,
        solver_adapter=OrToolsCpSatServiceQualitySolver.adapter_id,
        adapter_context_fingerprint=empty_adapter_context_fingerprint(),
        evaluation_policy=evaluation_policy,
        solver_policy=solver_policy,
        direction_trip_lock_mode=DirectionTripLockMode.FIXED_BY_DIRECTION,
        fleet_constraint_mode=FleetConstraintMode.AVAILABLE_UPPER_BOUND,
        initial_fleet_positioning_mode=InitialFleetPositioningMode.SOLVER_DETERMINED,
        boundary_convention=BoundaryConvention.HALF_OPEN,
    )
    problem_issues = _quality_problem_authority_issues(problem)
    if problem_issues:
        raise ScheduleProblemError(
            f"{ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY}: "
            + ", ".join(problem_issues[1:]),
            code=ORTOOLS_SERVICE_QUALITY_REQUIRES_DIRECTIONAL_AUTHORITY,
            codes=problem_issues,
        )
    generation_context = build_schedule_generation_context_v1(
        problem,
        normalized_inputs,
        b_evaluation,
        evaluation_policy,
    )
    return generation_context, OrToolsCpSatServiceQualitySolver()


__all__ = [
    "OrToolsCpSatServiceQualitySolver",
    "build_ortools_service_quality_request_v1",
]
