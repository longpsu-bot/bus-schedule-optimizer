"""OR-Tools CP-SAT hard-feasibility adapter for Contract V1 schedules."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import ClassVar

import ortools
from ortools.sat.python import cp_model

from .evaluation import ScenarioBEvaluationBundleV1, ScenarioBEvaluationPolicyV1
from .models import (
    ContractDirection,
    DepartureTerminal,
    ExactTimetableTrip,
    NormalizedInputBundleV1,
)
from .problem_validation import validate_schedule_problem_v1
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
    build_schedule_generation_context_v1,
    build_schedule_problem_v1,
    empty_adapter_context_fingerprint,
)

_FEASIBILITY_BOUNDARY_REASON = "FULL_DIRECTION_TECHNICAL_FEASIBILITY"
_SINGLETON_TARGET_HEADWAY_MINUTES = 1.0
_REGIME_IDS = {
    ContractDirection.OUTBOUND: "ORTOOLS-OUTBOUND-FEASIBILITY",
    ContractDirection.INBOUND: "ORTOOLS-INBOUND-FEASIBILITY",
}


@dataclass(frozen=True, slots=True)
class _CpSatModelBundle:
    model: cp_model.CpModel
    departure_by_source_id: dict[str, cp_model.IntVar]
    initial_terminal_1: cp_model.IntVar
    initial_terminal_2: cp_model.IntVar


def _ordered_directional_trips(
    problem: ScheduleProblemV1,
) -> dict[ContractDirection, tuple[ExactTimetableTrip, ...]]:
    return {
        direction: tuple(
            sorted(
                (
                    trip
                    for trip in problem.scenario_b.exact_timetable
                    if trip.direction == direction
                ),
                key=lambda item: (item.departure_time, item.trip_id),
            )
        )
        for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND)
    }


def _adapter_capability_issues(problem: ScheduleProblemV1, adapter_id: str) -> tuple[str, ...]:
    issues = [item.code for item in validate_schedule_problem_v1(problem).issues]
    scenario = problem.scenario_b
    if problem.solver_adapter != adapter_id:
        issues.append("PROBLEM_ADAPTER_CONTEXT_MISMATCH")
    if problem.direction_trip_lock_mode != DirectionTripLockMode.FIXED_BY_DIRECTION:
        issues.append("ORTOOLS_UNSUPPORTED_DIRECTION_TRIP_LOCK_MODE")
    if problem.fleet_constraint_mode != FleetConstraintMode.AVAILABLE_UPPER_BOUND:
        issues.append("ORTOOLS_UNSUPPORTED_FLEET_CONSTRAINT_MODE")
    if problem.initial_fleet_positioning_mode != InitialFleetPositioningMode.SOLVER_DETERMINED:
        issues.append("ORTOOLS_UNSUPPORTED_INITIAL_FLEET_POSITIONING_MODE")
    if problem.boundary_convention != BoundaryConvention.HALF_OPEN:
        issues.append("ORTOOLS_UNSUPPORTED_BOUNDARY_CONVENTION")
    if problem.direction_redistribution_authorization is not None:
        issues.append("ORTOOLS_UNSUPPORTED_DIRECTION_REDISTRIBUTION")
    if problem.fixed_initial_fleet is not None or problem.bounded_initial_fleet is not None:
        issues.append("ORTOOLS_UNSUPPORTED_INITIAL_FLEET_VALUES")
    if (
        not scenario.terminal_1_name.strip()
        or not scenario.terminal_2_name.strip()
        or scenario.terminal_1_name == scenario.terminal_2_name
    ):
        issues.append("ORTOOLS_INVALID_TWO_TERMINAL_SHAPE")

    source_ids = [trip.trip_id for trip in scenario.exact_timetable]
    if len(source_ids) != len(set(source_ids)):
        issues.append("ORTOOLS_INVALID_SOURCE_MAPPING")
    directional = _ordered_directional_trips(problem)
    if (
        len(scenario.exact_timetable) != scenario.total_daily_trips
        or len(directional[ContractDirection.OUTBOUND]) != scenario.trips_by_direction.outbound
        or len(directional[ContractDirection.INBOUND]) != scenario.trips_by_direction.inbound
        or scenario.total_daily_trips
        != scenario.trips_by_direction.outbound + scenario.trips_by_direction.inbound
    ):
        issues.append("ORTOOLS_INVALID_SOURCE_MAPPING")

    expected_terminal = {
        ContractDirection.OUTBOUND: DepartureTerminal.TERMINAL_1,
        ContractDirection.INBOUND: DepartureTerminal.TERMINAL_2,
    }
    for direction, trips in directional.items():
        if not trips or any(
            trip.departure_terminal != expected_terminal[direction]
            or trip.runtime_minutes <= 0
            or trip.arrival_time != trip.departure_time + trip.runtime_minutes * 60
            for trip in trips
        ):
            issues.append("ORTOOLS_INVALID_SOURCE_MAPPING")

    departure_values = [
        *(trip.departure_time for trip in scenario.exact_timetable),
        scenario.first_departures.terminal_1,
        scenario.first_departures.terminal_2,
        scenario.last_departures.terminal_1,
        scenario.last_departures.terminal_2,
    ]
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value % 60 != 0
        for value in departure_values
    ):
        issues.append("ORTOOLS_NON_MINUTE_ALIGNED_DEPARTURE")
    return tuple(dict.fromkeys(issues))


def _directional_window_minutes(
    problem: ScheduleProblemV1,
    direction: ContractDirection,
) -> tuple[int, int]:
    scenario = problem.scenario_b
    if direction == ContractDirection.OUTBOUND:
        return (
            scenario.first_departures.terminal_1 // 60,
            scenario.last_departures.terminal_1 // 60,
        )
    return (
        scenario.first_departures.terminal_2 // 60,
        scenario.last_departures.terminal_2 // 60,
    )


def _build_cp_sat_model(problem: ScheduleProblemV1) -> _CpSatModelBundle:
    model = cp_model.CpModel()
    directional = _ordered_directional_trips(problem)
    departure_by_source_id: dict[str, cp_model.IntVar] = {}
    for direction, trips in directional.items():
        first_minute, last_minute = _directional_window_minutes(problem, direction)
        variables: list[cp_model.IntVar] = []
        for index, trip in enumerate(trips, start=1):
            variable = model.new_int_var(
                first_minute,
                last_minute,
                f"departure_{direction.value}_{index:04d}_{trip.trip_id}",
            )
            variables.append(variable)
            departure_by_source_id[trip.trip_id] = variable
            model.add_hint(variable, trip.departure_time // 60)
        model.add(variables[0] == first_minute)
        model.add(variables[-1] == last_minute)
        for earlier, later in zip(variables, variables[1:], strict=False):
            model.add(later >= earlier + 1)

    fleet_limit = problem.scenario_b.available_fleet_limit
    initial_terminal_1 = model.new_int_var(0, fleet_limit, "initial_terminal_1")
    initial_terminal_2 = model.new_int_var(0, fleet_limit, "initial_terminal_2")
    model.add(initial_terminal_1 + initial_terminal_2 <= fleet_limit)

    outbound = directional[ContractDirection.OUTBOUND]
    inbound = directional[ContractDirection.INBOUND]
    turnaround_terminal_1 = problem.scenario_b.turnaround_minutes.terminal_1
    turnaround_terminal_2 = problem.scenario_b.turnaround_minutes.terminal_2

    for outbound_index, outbound_trip in enumerate(outbound, start=1):
        outbound_departure = departure_by_source_id[outbound_trip.trip_id]
        ready_indicators: list[cp_model.IntVar] = []
        for inbound_index, inbound_trip in enumerate(inbound, start=1):
            indicator = model.new_bool_var(
                "ready_terminal_1_"
                f"{inbound_index:04d}_{inbound_trip.trip_id}_"
                f"by_{outbound_index:04d}_{outbound_trip.trip_id}"
            )
            ready_indicators.append(indicator)
            ready_time = (
                departure_by_source_id[inbound_trip.trip_id]
                + inbound_trip.runtime_minutes
                + turnaround_terminal_1
            )
            model.add(ready_time <= outbound_departure).only_enforce_if(indicator)
            model.add(ready_time >= outbound_departure + 1).only_enforce_if(indicator.negated())
        model.add(initial_terminal_1 + sum(ready_indicators) >= outbound_index)

    for inbound_index, inbound_trip in enumerate(inbound, start=1):
        inbound_departure = departure_by_source_id[inbound_trip.trip_id]
        ready_indicators = []
        for outbound_index, outbound_trip in enumerate(outbound, start=1):
            indicator = model.new_bool_var(
                "ready_terminal_2_"
                f"{outbound_index:04d}_{outbound_trip.trip_id}_"
                f"by_{inbound_index:04d}_{inbound_trip.trip_id}"
            )
            ready_indicators.append(indicator)
            ready_time = (
                departure_by_source_id[outbound_trip.trip_id]
                + outbound_trip.runtime_minutes
                + turnaround_terminal_2
            )
            model.add(ready_time <= inbound_departure).only_enforce_if(indicator)
            model.add(ready_time >= inbound_departure + 1).only_enforce_if(indicator.negated())
        model.add(initial_terminal_2 + sum(ready_indicators) >= inbound_index)

    return _CpSatModelBundle(
        model=model,
        departure_by_source_id=departure_by_source_id,
        initial_terminal_1=initial_terminal_1,
        initial_terminal_2=initial_terminal_2,
    )


def _map_cp_sat_status(status: cp_model.CpSolverStatus) -> NativeSolverStatus:
    return {
        cp_model.OPTIMAL: NativeSolverStatus.OPTIMAL,
        cp_model.FEASIBLE: NativeSolverStatus.FEASIBLE,
        cp_model.INFEASIBLE: NativeSolverStatus.INFEASIBLE,
        cp_model.MODEL_INVALID: NativeSolverStatus.MODEL_INVALID,
        cp_model.UNKNOWN: NativeSolverStatus.UNKNOWN,
    }[status]


def _solver_controls(problem: ScheduleProblemV1) -> tuple[float | None, int, int]:
    policy = problem.solver_policy
    return (
        policy.time_limit_seconds,
        policy.worker_count if policy.worker_count is not None else 1,
        policy.random_seed if policy.random_seed is not None else 0,
    )


def _solver_limitations(problem: ScheduleProblemV1) -> tuple[str, ...]:
    time_limit, worker_count, random_seed = _solver_controls(problem)
    configured_time_limit = "none" if time_limit is None else f"{time_limit:g} seconds"
    return (
        f"OR-Tools version {ortools.__version__}; configured time limit: "
        f"{configured_time_limit}; worker count: {worker_count}; random seed: {random_seed}.",
        "The CP-SAT model is feasibility-only; it does not optimize demand, headway, "
        "service quality, trip shifts, or fleet size.",
        "Raw headway regimes describe the solved timetable for Contract V1 reconciliation; "
        "they are not demand-derived or headway-optimized.",
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
        explanations=tuple(f"{issue}: OR-Tools adapter rejected the problem." for issue in issues),
        limitations=(
            *_solver_limitations(problem),
            "MODEL_INVALID identifies an adapter capability or integration defect, "
            "not route, timetable, fleet, or locked-parameter infeasibility.",
        ),
    )


def _previous_headways(
    rows: tuple[ExactTimetableTrip, ...],
    departure_by_source_id: dict[str, int],
) -> dict[str, float | None]:
    output: dict[str, float | None] = {}
    previous: int | None = None
    for trip in rows:
        departure = departure_by_source_id[trip.trip_id]
        output[trip.trip_id] = None if previous is None else float(departure - previous)
        previous = departure
    return output


def _regularity_status(headways: tuple[float, ...]) -> str:
    if not headways or max(headways) == min(headways):
        return "REGULAR"
    if max(headways) - min(headways) <= 1:
        return "BALANCED_ROUNDING"
    return "EXCEPTIONAL"


def _build_raw_candidate(
    problem: ScheduleProblemV1,
    bundle: _CpSatModelBundle,
    solver: cp_model.CpSolver,
    status: NativeSolverStatus,
    solve_duration_seconds: float,
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
        trip.trip_id: solver.value(bundle.departure_by_source_id[trip.trip_id])
        for trip in source_order
    }
    b_minutes = {trip.trip_id: trip.departure_time // 60 for trip in source_order}
    previous_b: dict[str, float | None] = {}
    previous_c: dict[str, float | None] = {}
    for trips in directional.values():
        previous_b.update(_previous_headways(trips, b_minutes))
        previous_c.update(_previous_headways(trips, solved_minutes))

    raw_rows = [
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
            headway_regime_id=_REGIME_IDS[trip.direction],
            change_reason="OR-Tools fixed-resource technical-feasibility solve.",
        )
        for trip in source_order
    ]
    exact_timetable = tuple(
        sorted(raw_rows, key=lambda item: (item.c_departure_time, item.c_trip_id))
    )

    regimes: list[RawHeadwayRegimeV1] = []
    singleton_direction = False
    for direction in (ContractDirection.OUTBOUND, ContractDirection.INBOUND):
        members = tuple(
            sorted(
                (trip for trip in exact_timetable if trip.direction == direction),
                key=lambda item: (item.c_departure_time, item.c_trip_id),
            )
        )
        headways = tuple(
            float((later.c_departure_time - earlier.c_departure_time) // 60)
            for earlier, later in zip(members, members[1:], strict=False)
        )
        singleton_direction = singleton_direction or len(members) == 1
        target = sum(headways) / len(headways) if headways else _SINGLETON_TARGET_HEADWAY_MINUTES
        regimes.append(
            RawHeadwayRegimeV1(
                regime_id=_REGIME_IDS[direction],
                direction=direction,
                start_time=members[0].c_departure_time,
                end_time=members[-1].c_departure_time,
                trip_count=len(members),
                target_headway=target,
                actual_headway_sequence=headways,
                boundary_reason=_FEASIBILITY_BOUNDARY_REASON,
                legacy_regularity_status=_regularity_status(headways),
            )
        )
    raw_regimes = tuple(regimes)
    explanation = (
        "CP-SAT proved technical feasibility for the encoded fixed-resource model; "
        "no service-quality objective was optimized."
        if status == NativeSolverStatus.OPTIMAL
        else "CP-SAT found a technical-feasibility candidate for the encoded fixed-resource "
        "model; no service-quality objective was optimized."
    )
    limitations = _solver_limitations(problem)
    if singleton_direction:
        limitations += (
            "A one-trip direction has no measurable headway; its descriptive regime uses "
            f"the positive {_SINGLETON_TARGET_HEADWAY_MINUTES:g}-minute placeholder target.",
        )
    return RawScheduleCandidateV1(
        solver_status=status,
        solver_adapter=adapter_id,
        solve_duration_seconds=solve_duration_seconds,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=problem.problem_fingerprint,
            solver_adapter=adapter_id,
            exact_timetable=exact_timetable,
            headway_regimes=raw_regimes,
        ),
        exact_timetable=exact_timetable,
        headway_regimes=raw_regimes,
        explanation=explanation,
        limitations=limitations,
    )


@dataclass(frozen=True, slots=True)
class OrToolsCpSatScheduleSolver:
    adapter_id: ClassVar[str] = "ortools_cp_sat_v1"

    def solve(self, problem: ScheduleProblemV1) -> SolverRunResultV1:
        started = time.perf_counter()
        issues = _adapter_capability_issues(problem, self.adapter_id)
        if issues:
            return _model_invalid_result(problem, self.adapter_id, started, issues)
        try:
            bundle = _build_cp_sat_model(problem)
            model_error = bundle.model.validate()
            if model_error:
                return _model_invalid_result(
                    problem,
                    self.adapter_id,
                    started,
                    ("ORTOOLS_CP_SAT_MODEL_VALIDATION_FAILED",),
                )
            solver = cp_model.CpSolver()
            time_limit, worker_count, random_seed = _solver_controls(problem)
            if time_limit is not None:
                solver.parameters.max_time_in_seconds = time_limit
            solver.parameters.num_search_workers = worker_count
            solver.parameters.random_seed = random_seed
            native_status = _map_cp_sat_status(solver.solve(bundle.model))
            duration = max(0.0, time.perf_counter() - started)
            candidate = (
                _build_raw_candidate(
                    problem,
                    bundle,
                    solver,
                    native_status,
                    duration,
                    self.adapter_id,
                )
                if native_status in {NativeSolverStatus.OPTIMAL, NativeSolverStatus.FEASIBLE}
                else None
            )
            explanation = (
                candidate.explanation
                if candidate is not None
                else {
                    NativeSolverStatus.INFEASIBLE: (
                        "CP-SAT proved the encoded fixed-resource model infeasible."
                    ),
                    NativeSolverStatus.MODEL_INVALID: (
                        "CP-SAT reported that the encoded model is invalid."
                    ),
                    NativeSolverStatus.UNKNOWN: (
                        "CP-SAT returned UNKNOWN; no feasibility or infeasibility proof "
                        "is available."
                    ),
                }[native_status]
            )
            limitations = (
                candidate.limitations if candidate is not None else _solver_limitations(problem)
            )
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=native_status,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=duration,
                candidate=candidate,
                explanations=(explanation,),
                limitations=limitations,
            )
        except Exception:
            return _model_invalid_result(
                problem,
                self.adapter_id,
                started,
                ("ORTOOLS_ADAPTER_FAILURE",),
            )


def build_ortools_schedule_request_v1(
    normalized_inputs: NormalizedInputBundleV1,
    b_evaluation: ScenarioBEvaluationBundleV1,
    *,
    evaluation_policy: ScenarioBEvaluationPolicyV1 | None = None,
    solver_policy: SolverPolicyV1 | None = None,
) -> tuple[ScheduleGenerationContextV1, OrToolsCpSatScheduleSolver]:
    problem = build_schedule_problem_v1(
        normalized_inputs,
        b_evaluation,
        solver_adapter=OrToolsCpSatScheduleSolver.adapter_id,
        adapter_context_fingerprint=empty_adapter_context_fingerprint(),
        evaluation_policy=evaluation_policy,
        solver_policy=solver_policy,
        direction_trip_lock_mode=DirectionTripLockMode.FIXED_BY_DIRECTION,
        fleet_constraint_mode=FleetConstraintMode.AVAILABLE_UPPER_BOUND,
        initial_fleet_positioning_mode=InitialFleetPositioningMode.SOLVER_DETERMINED,
        boundary_convention=BoundaryConvention.HALF_OPEN,
    )
    generation_context = build_schedule_generation_context_v1(
        problem,
        normalized_inputs,
        b_evaluation,
        evaluation_policy,
    )
    return generation_context, OrToolsCpSatScheduleSolver()


__all__ = [
    "OrToolsCpSatScheduleSolver",
    "build_ortools_schedule_request_v1",
]
