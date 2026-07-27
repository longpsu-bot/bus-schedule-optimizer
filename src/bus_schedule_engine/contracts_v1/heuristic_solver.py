from __future__ import annotations

import time
from dataclasses import dataclass
from typing import ClassVar

from bus_schedule_engine.c_generator import generate_scenario_c
from bus_schedule_engine.models import GeneratedScenario, ScenarioCStatus

from .heuristic_context import (
    HEURISTIC_TURNAROUND_BRIDGE_MODE,
    HeuristicCompatibilityContextV1,
    contract_direction,
    departure_terminal,
    heuristic_context_mismatch_codes,
)
from .regime_headway_policy import _authoritative_candidate_payload
from .solver_fingerprints import candidate_fingerprint
from .solver_models import (
    NativeSolverStatus,
    RawCandidateTripV1,
    RawScheduleCandidateV1,
    ScheduleProblemV1,
    SolverExecutionStatus,
    SolverRunResultV1,
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
    context: HeuristicCompatibilityContextV1,
) -> RawScheduleCandidateV1:
    traces = {trace.c_trip_id: trace for trace in generated.trip_traces}
    source_b = {trip.trip_id: trip for trip in problem.scenario_b.exact_timetable}
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
        generated_arrival = trip.resolved_arrival_seconds(problem.scenario_b.trip_runtime_minutes)
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
                headway_regime_id="REGIME_PENDING_AUTHORITY",
                change_reason=(trace.change_reason if trace is not None else generated.reason),
            )
        )
    raw_trips, raw_regimes, _ = _authoritative_candidate_payload(
        problem,
        tuple(trips),
    )
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
            f"using scalar "
            f"{context.turnaround_bridge_value_minutes} minutes; "
            "authoritative validation uses the exact arrival-terminal values "
            f"{problem.scenario_b.turnaround_minutes.terminal_1}/"
            f"{problem.scenario_b.turnaround_minutes.terminal_2}.",
        ),
    )


@dataclass(frozen=True, slots=True)
class HeuristicScheduleSolverAdapter:
    compatibility_context: HeuristicCompatibilityContextV1
    adapter_id: ClassVar[str] = "legacy_heuristic_v1"

    def solve(self, problem: ScheduleProblemV1) -> SolverRunResultV1:
        started = time.perf_counter()
        mismatch_codes = list(
            heuristic_context_mismatch_codes(
                problem,
                self.compatibility_context,
            )
        )
        if problem.solver_adapter != self.adapter_id:
            mismatch_codes.append("PROBLEM_ADAPTER_CONTEXT_MISMATCH")
        if mismatch_codes:
            duration = max(0.0, time.perf_counter() - started)
            codes = tuple(sorted(set(mismatch_codes)))
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.MODEL_INVALID,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=duration,
                candidate=None,
                explanations=tuple(
                    f"{code}: heuristic compatibility context rejected." for code in codes
                ),
                limitations=(
                    "MODEL_INVALID identifies an adapter-context or integration "
                    "defect, not route, demand, timetable, fleet, or parameter "
                    "infeasibility.",
                ),
            )
        try:
            context = self.compatibility_context
            generated = generate_scenario_c(
                context.legacy_parameters,
                list(context.legacy_trips_b),
                list(context.legacy_demand),
                problem.scenario_b.available_fleet_limit,
                context.heuristic_config,
            )
            duration = max(0.0, time.perf_counter() - started)
            if generated.generation_status in _ACCEPTED_HEURISTIC_STATUSES:
                candidate = _raw_candidate_from_generated(
                    generated,
                    problem,
                    duration,
                    self.adapter_id,
                    context,
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
                    f"{context.turnaround_bridge_value_minutes} minutes and may "
                    "miss candidates that rely on the shorter terminal turnaround.",
                ),
            )
        except Exception:
            duration = max(0.0, time.perf_counter() - started)
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.MODEL_INVALID,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=duration,
                candidate=None,
                explanations=(
                    "HEURISTIC_ADAPTER_FAILURE: Heuristic adapter failed "
                    "before returning a valid result.",
                ),
                limitations=(
                    "MODEL_INVALID identifies an adapter or compatibility defect, "
                    "not route or timetable infeasibility.",
                ),
            )
