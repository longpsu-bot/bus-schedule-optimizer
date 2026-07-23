from __future__ import annotations

import time

from bus_schedule_engine.c_generator import generate_scenario_c
from bus_schedule_engine.models import GeneratedScenario, ScenarioCStatus

from .solver_fingerprints import candidate_fingerprint
from .solver_models import (
    NativeSolverStatus,
    RawCandidateTripV1,
    RawHeadwayRegimeV1,
    RawScheduleCandidateV1,
    ScheduleProblemV1,
    SolverExecutionStatus,
    SolverRunResultV1,
)
from .solver_problem import (
    HEURISTIC_TURNAROUND_BRIDGE_MODE,
    contract_direction,
    departure_terminal,
)

_ACCEPTED_HEURISTIC_STATUSES = {
    ScenarioCStatus.SUITABLE_REGULAR,
    ScenarioCStatus.DEMAND_IMPROVED_NOT_REGULAR,
    ScenarioCStatus.REGULAR_STILL_UNDERSUPPLIED,
}


def _raw_candidate_from_generated(
    generated: GeneratedScenario,
    problem: ScheduleProblemV1,
    solve_duration_seconds: float,
    adapter_id: str,
) -> RawScheduleCandidateV1:
    traces = {trace.c_trip_id: trace for trace in generated.trip_traces}
    source_b = {trip.trip_id: trip for trip in problem.normalized_inputs.scenario_b.exact_timetable}
    trips: list[RawCandidateTripV1] = []
    for trip in sorted(
        generated.trips,
        key=lambda item: (item.departure_seconds, item.trip_id),
    ):
        trace = traces.get(trip.trip_id)
        source_id = (
            trace.source_b_trip_id if trace is not None else trip.source_b_trip_id or trip.trip_id
        )
        source = source_b.get(source_id)
        if source is None:
            raise ValueError(f"Heuristic candidate trip {trip.trip_id} has unknown source B trip")
        direction = contract_direction(trip.direction)
        generated_arrival = trip.resolved_arrival_seconds(
            problem.normalized_inputs.scenario_b.trip_runtime_minutes
        )
        arrival = trip.departure_seconds + source.runtime_minutes * 60
        if generated_arrival != arrival:
            raise ValueError(
                f"Heuristic candidate trip {trip.trip_id} changed its source B runtime"
            )
        trips.append(
            RawCandidateTripV1(
                c_trip_id=trip.trip_id,
                source_b_trip_id=source_id,
                direction=direction,
                departure_terminal=departure_terminal(direction),
                b_departure_time=source.departure_time,
                c_departure_time=trip.departure_seconds,
                arrival_time=arrival,
                runtime_minutes=source.runtime_minutes,
                shift_minutes=(trip.departure_seconds - source.departure_time) / 60,
                previous_b_headway=(trace.original_previous_headway if trace is not None else None),
                previous_c_headway=(trace.new_previous_headway if trace is not None else None),
                headway_regime_id=(
                    trace.headway_regime_id if trace is not None else "REGIME_UNSPECIFIED"
                ),
                change_reason=(trace.change_reason if trace is not None else generated.reason),
            )
        )
    raw_trips = tuple(trips)
    regimes: list[RawHeadwayRegimeV1] = []
    for regime in generated.headway_regimes:
        members = sorted(
            (trip for trip in raw_trips if trip.headway_regime_id == regime.regime_id),
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
        if not members:
            continue
        actual_headways = tuple(
            (right.c_departure_time - left.c_departure_time) / 60
            for left, right in zip(members, members[1:], strict=False)
        )
        regimes.append(
            RawHeadwayRegimeV1(
                regime_id=regime.regime_id,
                direction=contract_direction(regime.direction),
                start_time=members[0].c_departure_time,
                end_time=members[-1].c_departure_time,
                trip_count=len(members),
                target_headway=regime.target_headway_minutes,
                actual_headway_sequence=actual_headways,
                boundary_reason=regime.boundary_reason.value,
                legacy_regularity_status=regime.headway_status,
            )
        )
    raw_regimes = tuple(regimes)
    return RawScheduleCandidateV1(
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter=adapter_id,
        solve_duration_seconds=solve_duration_seconds,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=problem.problem_fingerprint,
            solver_adapter=adapter_id,
            exact_timetable=raw_trips,
            headway_regimes=raw_regimes,
        ),
        exact_timetable=raw_trips,
        headway_regimes=raw_regimes,
        explanation=generated.reason,
        limitations=(
            "The legacy heuristic adapter finds candidates but does not prove "
            "optimality or global infeasibility.",
            f"The heuristic searched with {HEURISTIC_TURNAROUND_BRIDGE_MODE} "
            f"using scalar {problem.legacy_parameters.effective_layover_minutes} minutes; "
            "authoritative validation uses the exact arrival-terminal values "
            f"{problem.normalized_inputs.scenario_b.turnaround_minutes.terminal_1}/"
            f"{problem.normalized_inputs.scenario_b.turnaround_minutes.terminal_2}.",
        ),
    )


class HeuristicScheduleSolverAdapter:
    adapter_id = "legacy_heuristic_v1"

    def solve(self, problem: ScheduleProblemV1) -> SolverRunResultV1:
        started = time.perf_counter()
        try:
            generated = generate_scenario_c(
                problem.legacy_parameters,
                list(problem.legacy_trips_b),
                list(problem.legacy_demand),
                problem.normalized_inputs.scenario_b.available_fleet_limit,
                problem.heuristic_config,
            )
            duration = max(0.0, time.perf_counter() - started)
            if generated.generation_status in _ACCEPTED_HEURISTIC_STATUSES:
                candidate = _raw_candidate_from_generated(
                    generated,
                    problem,
                    duration,
                    self.adapter_id,
                )
                return SolverRunResultV1(
                    execution_status=SolverExecutionStatus.COMPLETED,
                    solver_status=NativeSolverStatus.FEASIBLE,
                    solver_adapter=self.adapter_id,
                    solve_duration_seconds=duration,
                    candidate=candidate,
                    explanations=(generated.reason,),
                    limitations=candidate.limitations,
                )
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.UNKNOWN,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=duration,
                candidate=None,
                explanations=(generated.reason,),
                limitations=(
                    "The heuristic search ended without an accepted candidate; "
                    "this is not proof that B's locked parameters are infeasible.",
                    f"Search used {HEURISTIC_TURNAROUND_BRIDGE_MODE} with scalar "
                    f"{problem.legacy_parameters.effective_layover_minutes} minutes and may "
                    "miss candidates that rely on the shorter terminal turnaround.",
                ),
            )
        except Exception as exc:
            duration = max(0.0, time.perf_counter() - started)
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.MODEL_INVALID,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=duration,
                candidate=None,
                explanations=(f"Heuristic adapter failed: {exc}",),
                limitations=(
                    "MODEL_INVALID identifies an adapter or compatibility defect, "
                    "not route or timetable infeasibility.",
                ),
            )
