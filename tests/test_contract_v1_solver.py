from __future__ import annotations

import json
from dataclasses import fields, replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

import bus_schedule_engine.contracts_v1.solver_orchestration as solver_orchestration_module
from bus_schedule_engine.c_config import ScenarioCConfig
from bus_schedule_engine.c_generator import generate_scenario_c
from bus_schedule_engine.contracts_v1 import (
    BDisposition,
    BoundaryConvention,
    CandidateValidationStatus,
    ContractDirection,
    DemandConfidence,
    DemandResolutionType,
    DepartureTerminal,
    DirectionTripLockMode,
    FleetConstraintMode,
    GenerationResultStatus,
    InitialFleetPositioningMode,
    InputSourceType,
    NativeSolverStatus,
    NormalizationOptions,
    OperatingDayType,
    RawCandidateTripV1,
    RawScheduleCandidateV1,
    ScenarioBEvaluationPolicyV1,
    ScheduleProblemError,
    ScheduleProblemV1,
    SolverExecutionStatus,
    SolverPolicyV1,
    SolverRunResultV1,
    TurnaroundMinutes,
    build_heuristic_schedule_request_v1,
    evaluate_scenario_b_v1,
    normalize_imported_workbook_v1,
    observed_demand_fingerprint,
    run_schedule_solver_v1,
    scenario_fingerprint,
    schedule_outcome_to_contract_dict,
    schedule_problem_to_contract_dict,
    schedule_solution_to_contract_dict,
    validate_and_build_solution_v1,
    validate_schedule_problem_v1,
)
from bus_schedule_engine.contracts_v1 import (
    HeuristicScheduleSolverAdapter as _HeuristicScheduleSolverAdapter,
)
from bus_schedule_engine.contracts_v1 import (
    build_schedule_problem_v1 as build_canonical_schedule_problem_v1,
)
from bus_schedule_engine.contracts_v1.fleet_assignment import assign_contract_v1_fleet
from bus_schedule_engine.contracts_v1.regime_headway_policy import (
    _authoritative_candidate_payload,
)
from bus_schedule_engine.contracts_v1.solver_fingerprints import candidate_fingerprint
from bus_schedule_engine.contracts_v1.solver_problem import (
    HEURISTIC_TURNAROUND_BRIDGE_MODE,
    RUNTIME_LOCK_MODE,
    TURNAROUND_APPLICATION_MODE,
    empty_adapter_context_fingerprint,
)
from bus_schedule_engine.fingerprint import timetable_fingerprint
from bus_schedule_engine.fleet import assign_fleet
from bus_schedule_engine.importer import ImportedWorkbook
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    RouteType,
    ScenarioParameters,
    Trip,
    VolumeType,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts" / "v1"
SCHEMAS = {
    path.name: json.loads(path.read_text(encoding="utf-8"))
    for path in SCHEMA_DIR.glob("*.schema.json")
}
REGISTRY = Registry().with_resources(
    (schema["$id"], Resource.from_contents(schema)) for schema in SCHEMAS.values()
)
_HEURISTIC_ADAPTERS: dict[str, _HeuristicScheduleSolverAdapter] = {}


def build_schedule_problem_v1(
    normalized,
    evaluation,
    parameters,
    trips,
    demand,
    config,
    policy=None,
):
    context, adapter = build_heuristic_schedule_request_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        demand,
        config,
        policy,
    )
    _HEURISTIC_ADAPTERS[context.problem_fingerprint] = adapter
    return context


def _heuristic_adapter(context) -> _HeuristicScheduleSolverAdapter:
    return _HEURISTIC_ADAPTERS[context.problem_fingerprint]


def _heuristic_context(context):
    return _heuristic_adapter(context).compatibility_context


class HeuristicScheduleSolverAdapter:
    """Compatibility proxy for the pre-H4 adversarial suite."""

    adapter_id = _HeuristicScheduleSolverAdapter.adapter_id

    def solve(self, problem):
        context = problem if hasattr(problem, "problem") else None
        canonical_problem = context.problem if context is not None else problem
        if context is not None:
            adapter = _heuristic_adapter(context)
        else:
            adapter = _HEURISTIC_ADAPTERS[canonical_problem.problem_fingerprint]
        return adapter.solve(canonical_problem)


def _schema_errors(instance: dict[str, object], schema_name: str) -> list[str]:
    validator = Draft202012Validator(
        SCHEMAS[schema_name],
        registry=REGISTRY,
        format_checker=FormatChecker(),
    )
    return [error.message for error in validator.iter_errors(instance)]


def _fixture(
    *,
    low_demand: bool = False,
) -> tuple[ScenarioParameters, list[Trip], list[DemandRecord], int]:
    parameters = ScenarioParameters(
        route_id="SOLVER-01",
        route_name="Tuyến kiểm thử solver boundary",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=30,
        total_daily_trips=26,
        terminal_1_name="Bến Đông",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=12 * 3600,
        terminal_2_name="Bến Tây",
        terminal_2_first_departure=6 * 3600 + 15 * 60,
        terminal_2_last_departure=12 * 3600 + 15 * 60,
        vehicle_capacity_passengers=60,
        target_load_factor=0.85,
        maximum_load_factor=0.90,
        time_block_minutes=60,
        minimum_layover_minutes=5,
    )
    trips: list[Trip] = []
    for direction, offset in (
        (Direction.TERMINAL_1_TO_2, 0),
        (Direction.TERMINAL_2_TO_1, 15),
    ):
        for index in range(13):
            departure = (360 + offset + index * 30) * 60
            trips.append(
                Trip(
                    scenario="B",
                    trip_id=f"B-{direction.value}-{index + 1:02d}",
                    departure_terminal=parameters.terminal_for_direction(direction),
                    direction=direction,
                    departure_seconds=departure,
                    arrival_seconds=departure + 30 * 60,
                )
            )

    volumes = [10] * 7 if low_demand else [150, 150, 30, 30, 150, 150, 150]
    demand = [
        DemandRecord(
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 7),
            observation_days=1,
            block_start_seconds=(6 + index) * 3600,
            block_end_seconds=(7 + index) * 3600,
            direction=direction,
            passenger_volume=volume,
            volume_type=VolumeType.AVERAGE_DAY,
        )
        for direction in (
            Direction.TERMINAL_1_TO_2,
            Direction.TERMINAL_2_TO_1,
        )
        for index, volume in enumerate(volumes)
    ]
    active_fleet = assign_fleet(trips, parameters).minimum_vehicles
    return parameters, trips, demand, active_fleet


def _normalized(
    parameters: ScenarioParameters,
    trips: list[Trip],
    demand: list[DemandRecord],
    fleet_limit: int,
):
    imported = ImportedWorkbook(
        parameters_a=parameters,
        trips_a=[replace(trip, scenario="A") for trip in trips],
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )
    return normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="solver-v1-fixture",
            imported_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
            operating_day_type_a=OperatingDayType.WEEKDAY,
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_a=fleet_limit,
            available_fleet_limit_b=fleet_limit,
            demand_confidence=DemandConfidence.HIGH,
        ),
    )


def _problem(
    *,
    low_demand: bool = False,
    config: ScenarioCConfig | None = None,
    fleet_limit_override: int | None = None,
):
    parameters, trips, demand, fleet_limit = _fixture(low_demand=low_demand)
    effective_fleet_limit = fleet_limit if fleet_limit_override is None else fleet_limit_override
    normalized = _normalized(parameters, trips, demand, effective_fleet_limit)
    policy = ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(normalized, policy)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        demand,
        config or ScenarioCConfig(),
        policy,
    )
    return problem, parameters, trips, demand, effective_fleet_limit


def _b_only_problem():
    parameters, trips, _, fleet_limit = _fixture()
    normalized = _normalized(parameters, trips, [], fleet_limit)
    normalized = replace(
        normalized,
        scenario_a=None,
        scenario_a_fingerprint=None,
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    context = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        [],
        ScenarioCConfig(),
    )
    return context, parameters, trips, fleet_limit


def _daily_total_problem():
    parameters, trips, demand, fleet_limit = _fixture()
    daily_rows = [
        replace(
            demand[0],
            direction=direction,
        )
        for direction in (
            Direction.TERMINAL_1_TO_2,
            Direction.TERMINAL_2_TO_1,
        )
    ]
    normalized = _normalized(parameters, trips, daily_rows, fleet_limit)
    assert normalized.observed_demand is not None
    observed = replace(
        normalized.observed_demand,
        observations=tuple(
            replace(
                item,
                source_resolution_type=DemandResolutionType.DAILY_TOTAL,
                source_resolution_minutes=None,
            )
            for item in normalized.observed_demand.observations
        ),
    )
    normalized = replace(
        normalized,
        observed_demand=observed,
        observed_demand_fingerprint=observed_demand_fingerprint(observed),
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    context = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        daily_rows,
        ScenarioCConfig(),
    )
    return context


def _generic_problem(
    normalized,
    evaluation,
    *,
    solver_policy: SolverPolicyV1 | None = None,
):
    return build_canonical_schedule_problem_v1(
        normalized,
        evaluation,
        solver_adapter="contract_v1_test_adapter",
        adapter_context_fingerprint=empty_adapter_context_fingerprint(),
        solver_policy=solver_policy,
    )


def _candidate(problem):
    run = HeuristicScheduleSolverAdapter().solve(problem)
    assert run.candidate is not None
    return run.candidate


def _contract_problem(
    parameters: ScenarioParameters,
    trips: list[Trip],
    *,
    fleet_limit: int,
    turnaround: tuple[int, int],
):
    demand = []
    for direction in (
        Direction.TERMINAL_1_TO_2,
        Direction.TERMINAL_2_TO_1,
    ):
        start = min(trip.departure_seconds for trip in trips if trip.direction == direction)
        coverage_end = (
            max(trip.departure_seconds for trip in trips if trip.direction == direction) + 60
        )
        while start < coverage_end:
            end = min(start + 60 * 60, coverage_end)
            demand.append(
                DemandRecord(
                    period_start=date(2026, 7, 1),
                    period_end=date(2026, 7, 7),
                    observation_days=1,
                    block_start_seconds=start,
                    block_end_seconds=end,
                    direction=direction,
                    passenger_volume=0,
                    volume_type=VolumeType.AVERAGE_DAY,
                )
            )
            start = end
    imported = ImportedWorkbook(
        parameters_a=parameters,
        trips_a=[replace(trip, scenario="A") for trip in trips],
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )
    normalized = normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="solver-v1-h2-fixture",
            imported_at=datetime(2026, 7, 23, 8, 0, tzinfo=UTC),
            operating_day_type_a=OperatingDayType.WEEKDAY,
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_a=fleet_limit,
            available_fleet_limit_b=fleet_limit,
            demand_confidence=DemandConfidence.HIGH,
        ),
    )
    scenario_b = replace(
        normalized.scenario_b,
        turnaround_minutes=TurnaroundMinutes(
            terminal_1=turnaround[0],
            terminal_2=turnaround[1],
        ),
    )
    normalized = replace(
        normalized,
        scenario_b=scenario_b,
        scenario_b_fingerprint=scenario_fingerprint(scenario_b),
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    return build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        demand,
        ScenarioCConfig(),
    )


def _turnaround_problem(
    *,
    turnaround: tuple[int, int] = (5, 20),
    fleet_limit: int = 2,
):
    parameters = ScenarioParameters(
        route_id="TURNAROUND-V1-H2",
        route_name="Runtime and turnaround authority",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=30,
        total_daily_trips=4,
        terminal_1_name="Terminal 1",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=7 * 3600,
        terminal_2_name="Terminal 2",
        terminal_2_first_departure=6 * 3600 + 15 * 60,
        terminal_2_last_departure=7 * 3600 + 15 * 60,
        vehicle_capacity_passengers=60,
        minimum_layover_minutes=5,
    )
    definitions = (
        ("B-O-1", Direction.TERMINAL_1_TO_2, 6 * 3600),
        ("B-I-1", Direction.TERMINAL_2_TO_1, 6 * 3600 + 15 * 60),
        ("B-O-2", Direction.TERMINAL_1_TO_2, 7 * 3600),
        ("B-I-2", Direction.TERMINAL_2_TO_1, 7 * 3600 + 15 * 60),
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=trip_id,
            departure_terminal=parameters.terminal_for_direction(direction),
            direction=direction,
            departure_seconds=departure,
            arrival_seconds=departure + 30 * 60,
        )
        for trip_id, direction, departure in definitions
    ]
    return (
        _contract_problem(
            parameters,
            trips,
            fleet_limit=fleet_limit,
            turnaround=turnaround,
        ),
        parameters,
        trips,
    )


def _runtime_problem(
    *,
    first_runtime: int = 55,
    fleet_limit: int = 8,
):
    parameters = ScenarioParameters(
        route_id="RUNTIME-V1-H2",
        route_name="Exact source runtime authority",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=60,
        allowed_trip_runtime_minutes=(55, 65),
        total_daily_trips=4,
        terminal_1_name="Terminal 1",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=9 * 3600,
        terminal_2_name="Terminal 2",
        terminal_2_first_departure=6 * 3600 + 10 * 60,
        terminal_2_last_departure=9 * 3600 + 10 * 60,
        vehicle_capacity_passengers=60,
        minimum_layover_minutes=5,
    )
    definitions = (
        ("B-O-1", Direction.TERMINAL_1_TO_2, 6 * 3600, first_runtime),
        ("B-I-1", Direction.TERMINAL_2_TO_1, 6 * 3600 + 10 * 60, 65),
        ("B-O-2", Direction.TERMINAL_1_TO_2, 9 * 3600, 65),
        ("B-I-2", Direction.TERMINAL_2_TO_1, 9 * 3600 + 10 * 60, 55),
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=trip_id,
            departure_terminal=parameters.terminal_for_direction(direction),
            direction=direction,
            departure_seconds=departure,
            arrival_seconds=departure + runtime * 60,
        )
        for trip_id, direction, departure, runtime in definitions
    ]
    return (
        _contract_problem(
            parameters,
            trips,
            fleet_limit=fleet_limit,
            turnaround=(5, 5),
        ),
        parameters,
        trips,
    )


def _two_trip_turnaround_problem(
    *,
    inbound_departure: int,
    fleet_limit: int,
):
    parameters = ScenarioParameters(
        route_id="TURNAROUND-CHAIN-V1-H2",
        route_name="Arrival-terminal turnaround chain",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=30,
        total_daily_trips=4,
        terminal_1_name="Terminal 1",
        terminal_1_first_departure=6 * 3600,
        terminal_1_last_departure=inbound_departure + 35 * 60,
        terminal_2_name="Terminal 2",
        terminal_2_first_departure=inbound_departure,
        terminal_2_last_departure=inbound_departure + 85 * 60,
        vehicle_capacity_passengers=60,
        minimum_layover_minutes=5,
    )
    trips = [
        Trip(
            scenario="B",
            trip_id="B-O-1",
            departure_terminal=parameters.terminal_1_name,
            direction=Direction.TERMINAL_1_TO_2,
            departure_seconds=6 * 3600,
            arrival_seconds=6 * 3600 + 30 * 60,
        ),
        Trip(
            scenario="B",
            trip_id="B-I-1",
            departure_terminal=parameters.terminal_2_name,
            direction=Direction.TERMINAL_2_TO_1,
            departure_seconds=inbound_departure,
            arrival_seconds=inbound_departure + 30 * 60,
        ),
        Trip(
            scenario="B",
            trip_id="B-O-2",
            departure_terminal=parameters.terminal_1_name,
            direction=Direction.TERMINAL_1_TO_2,
            departure_seconds=inbound_departure + 35 * 60,
            arrival_seconds=inbound_departure + 65 * 60,
        ),
        Trip(
            scenario="B",
            trip_id="B-I-2",
            departure_terminal=parameters.terminal_2_name,
            direction=Direction.TERMINAL_2_TO_1,
            departure_seconds=inbound_departure + 85 * 60,
            arrival_seconds=inbound_departure + 115 * 60,
        ),
    ]
    return _contract_problem(
        parameters,
        trips,
        fleet_limit=fleet_limit,
        turnaround=(5, 20),
    )


def _baseline_candidate(problem) -> RawScheduleCandidateV1:
    source_rows = sorted(
        problem.normalized_inputs.scenario_b.exact_timetable,
        key=lambda item: (item.departure_time, item.trip_id),
    )
    c_id_by_source = {
        trip.trip_id: f"C-{index:04d}" for index, trip in enumerate(source_rows, start=1)
    }
    previous_b = _previous_headways(
        [(trip.direction, trip.departure_time, trip.trip_id) for trip in source_rows]
    )
    raw_trips = tuple(
        RawCandidateTripV1(
            c_trip_id=c_id_by_source[trip.trip_id],
            source_b_trip_id=trip.trip_id,
            direction=trip.direction,
            departure_terminal=trip.departure_terminal,
            b_departure_time=trip.departure_time,
            c_departure_time=trip.departure_time,
            arrival_time=trip.departure_time + trip.runtime_minutes * 60,
            runtime_minutes=trip.runtime_minutes,
            shift_minutes=0,
            previous_b_headway=previous_b[trip.trip_id],
            previous_c_headway=previous_b[trip.trip_id],
            headway_regime_id="REGIME_PENDING_AUTHORITY",
            change_reason="V1-H2 authority fixture",
        )
        for trip in source_rows
    )
    raw_trips, raw_regimes, _ = _authoritative_candidate_payload(
        problem.problem,
        raw_trips,
    )
    adapter_id = "legacy_heuristic_v1"
    return RawScheduleCandidateV1(
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter=adapter_id,
        solve_duration_seconds=0,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=problem.problem_fingerprint,
            solver_adapter=adapter_id,
            exact_timetable=raw_trips,
            headway_regimes=raw_regimes,
        ),
        exact_timetable=raw_trips,
        headway_regimes=raw_regimes,
        explanation="V1-H2 exact authority candidate",
        limitations=(),
    )


def _refingerprint(problem, candidate: RawScheduleCandidateV1) -> RawScheduleCandidateV1:
    return replace(
        candidate,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=problem.problem_fingerprint,
            solver_adapter=candidate.solver_adapter,
            exact_timetable=candidate.exact_timetable,
            headway_regimes=candidate.headway_regimes,
        ),
    )


def _previous_headways(rows) -> dict[str, float | None]:
    by_direction = {}
    for direction, departure, trip_id in rows:
        by_direction.setdefault(direction, []).append((departure, trip_id))
    output: dict[str, float | None] = {}
    for directional_rows in by_direction.values():
        previous = None
        for departure, trip_id in sorted(
            directional_rows,
            key=lambda item: (item[0], item[1]),
        ):
            output[trip_id] = None if previous is None else (departure - previous) / 60
            previous = departure
    return output


def _reconcile_raw_claims(
    problem,
    candidate: RawScheduleCandidateV1,
) -> RawScheduleCandidateV1:
    b_by_id = {trip.trip_id: trip for trip in problem.normalized_inputs.scenario_b.exact_timetable}
    previous_b = _previous_headways(
        [
            (trip.direction, trip.departure_time, trip.trip_id)
            for trip in problem.normalized_inputs.scenario_b.exact_timetable
        ]
    )
    previous_c = _previous_headways(
        [
            (trip.direction, trip.c_departure_time, trip.c_trip_id)
            for trip in candidate.exact_timetable
        ]
    )
    trips = tuple(
        replace(
            trip,
            shift_minutes=(trip.c_departure_time - b_by_id[trip.source_b_trip_id].departure_time)
            / 60,
            previous_b_headway=previous_b[trip.source_b_trip_id],
            previous_c_headway=previous_c[trip.c_trip_id],
        )
        for trip in candidate.exact_timetable
    )
    regimes = []
    for regime in candidate.headway_regimes:
        members = sorted(
            (trip for trip in trips if trip.headway_regime_id == regime.regime_id),
            key=lambda item: (item.c_departure_time, item.c_trip_id),
        )
        regimes.append(
            replace(
                regime,
                start_time=members[0].c_departure_time,
                end_time=members[-1].c_departure_time,
                trip_count=len(members),
                actual_headway_sequence=tuple(
                    (right.c_departure_time - left.c_departure_time) / 60
                    for left, right in zip(members, members[1:], strict=False)
                ),
            )
        )
    return _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=trips,
            headway_regimes=tuple(regimes),
        ),
    )


def _zero_headway_candidate(problem) -> tuple[RawScheduleCandidateV1, str, str]:
    candidate = _candidate(problem)
    regime = next(
        item
        for item in candidate.headway_regimes
        if sum(trip.headway_regime_id == item.regime_id for trip in candidate.exact_timetable) >= 2
    )
    members = sorted(
        (trip for trip in candidate.exact_timetable if trip.headway_regime_id == regime.regime_id),
        key=lambda item: (item.c_departure_time, item.c_trip_id),
    )
    earlier, later = members[:2]
    changed = tuple(
        (
            replace(
                trip,
                c_departure_time=earlier.c_departure_time,
                arrival_time=(earlier.c_departure_time + trip.runtime_minutes * 60),
            )
            if trip.c_trip_id == later.c_trip_id
            else trip
        )
        for trip in candidate.exact_timetable
    )
    reconciled = _reconcile_raw_claims(
        problem,
        replace(candidate, exact_timetable=changed),
    )
    return reconciled, earlier.c_trip_id, later.c_trip_id


class _BombSolver:
    adapter_id = "must_not_run"

    def solve(self, problem):  # pragma: no cover - failure makes test explicit
        raise AssertionError("solver must not be invoked")


class _StaticSolver:
    adapter_id = "static_test_adapter"

    def __init__(self, run: SolverRunResultV1):
        self._run = run
        self.adapter_id = run.solver_adapter
        self.call_count = 0

    def solve(self, problem):
        self.call_count += 1
        return self._run


def _completed_run_for_candidate(candidate: RawScheduleCandidateV1) -> SolverRunResultV1:
    return SolverRunResultV1(
        execution_status=SolverExecutionStatus.COMPLETED,
        solver_status=candidate.solver_status,
        solver_adapter=candidate.solver_adapter,
        solve_duration_seconds=candidate.solve_duration_seconds,
        candidate=candidate,
        explanations=("Static accepted-candidate contract fixture.",),
        limitations=candidate.limitations,
    )


class _RaisingSolver:
    adapter_id = _HeuristicScheduleSolverAdapter.adapter_id

    def solve(self, problem):
        raise RuntimeError("secret workbook value at C:\\private\\operator\\source.xlsx")


def test_problem_reconciles_normalized_and_legacy_inputs() -> None:
    problem, _, trips, _, _ = _problem()

    assert len(_heuristic_context(problem).legacy_trips_b) == 26
    assert problem.normalized_inputs.scenario_b.total_daily_trips == 26
    assert problem.b_evaluation == evaluate_scenario_b_v1(
        problem.normalized_inputs,
        problem.evaluation_policy,
    )
    assert len(problem.problem_fingerprint) == 64
    assert timetable_fingerprint(
        list(_heuristic_context(problem).legacy_trips_b)
    ) == timetable_fingerprint(
        sorted(trips, key=lambda item: (item.departure_seconds, item.trip_id))
    )


def test_problem_binds_scenario_default_and_exact_source_runtime_mapping() -> None:
    problem, _, _ = _runtime_problem(first_runtime=55)
    changed_problem, _, _ = _runtime_problem(first_runtime=56)

    assert problem.normalized_inputs.scenario_b.trip_runtime_minutes == 60
    assert _heuristic_context(problem).legacy_parameters.default_trip_runtime_minutes == 65
    assert {
        trip.runtime_minutes for trip in problem.normalized_inputs.scenario_b.exact_timetable
    } == {55, 65}
    assert changed_problem.normalized_inputs.scenario_b.trip_runtime_minutes == 60
    assert problem.problem_fingerprint != changed_problem.problem_fingerprint


def test_fleet_assessment_uses_each_exact_runtime_not_scenario_or_fallback() -> None:
    problem, _, _ = _runtime_problem()
    scenario = problem.normalized_inputs.scenario_b
    fleet = problem.b_evaluation.fleet_assessment
    ready_by_trip = {
        event.trip_id: event.event_time
        for event in (*fleet.terminal_1_events, *fleet.terminal_2_events)
        if event.event_type == "READY"
    }
    source_by_id = {trip.trip_id: trip for trip in scenario.exact_timetable}

    assert ready_by_trip["B-O-1"] == (source_by_id["B-O-1"].departure_time + 55 * 60 + 5 * 60)
    assert ready_by_trip["B-I-1"] == (source_by_id["B-I-1"].departure_time + 65 * 60 + 5 * 60)
    assert ready_by_trip["B-O-1"] != (
        source_by_id["B-O-1"].departure_time + scenario.trip_runtime_minutes * 60 + 5 * 60
    )
    assert ready_by_trip["B-O-1"] != (
        source_by_id["B-O-1"].departure_time
        + _heuristic_context(problem).legacy_parameters.default_trip_runtime_minutes * 60
        + 5 * 60
    )


def test_problem_accepts_5_20_and_derives_conservative_heuristic_bridge() -> None:
    problem, parameters, _ = _turnaround_problem()

    assert parameters.effective_layover_minutes == 5
    assert problem.normalized_inputs.scenario_b.turnaround_minutes == TurnaroundMinutes(
        terminal_1=5,
        terminal_2=20,
    )
    assert _heuristic_context(problem).legacy_parameters.effective_layover_minutes == 20
    assert _heuristic_context(problem).legacy_parameters is not parameters


def test_problem_fingerprint_changes_for_each_terminal_turnaround() -> None:
    baseline, _, _ = _turnaround_problem(turnaround=(5, 20))
    terminal_1_changed, _, _ = _turnaround_problem(turnaround=(6, 20))
    terminal_2_changed, _, _ = _turnaround_problem(turnaround=(5, 21))

    assert baseline.problem_fingerprint != terminal_1_changed.problem_fingerprint
    assert baseline.problem_fingerprint != terminal_2_changed.problem_fingerprint
    assert terminal_1_changed.problem_fingerprint != terminal_2_changed.problem_fingerprint


def test_asymmetric_bridge_exhaustion_is_unknown_and_disclosed() -> None:
    problem, _, _ = _turnaround_problem()

    run = HeuristicScheduleSolverAdapter().solve(problem)

    assert run.candidate is None
    assert run.solver_status == NativeSolverStatus.UNKNOWN
    assert any(HEURISTIC_TURNAROUND_BRIDGE_MODE in item for item in run.limitations)
    assert any("scalar 20 minutes" in item for item in run.limitations)


def test_exact_5_20_validation_accepts_candidate_stricter_bridge_misses() -> None:
    problem, parameters, legacy_trips = _turnaround_problem()
    candidate = _baseline_candidate(problem)
    validation = validate_and_build_solution_v1(problem, candidate)
    conservative_legacy = assign_fleet(
        legacy_trips,
        replace(parameters, minimum_layover_minutes=20),
    )

    assert conservative_legacy.minimum_vehicles == 3
    assert validation.status == CandidateValidationStatus.ACCEPTED
    assert validation.solution is not None
    solution = validation.solution
    assert solution.minimum_required_fleet == 2
    assert len({item.vehicle_id for item in solution.fleet_assignment}) == 2
    assert solution.minimum_required_fleet == (
        solution.recommended_initial_fleet_terminal_1
        + solution.recommended_initial_fleet_terminal_2
    )
    for assignment in solution.fleet_assignment:
        expected_turnaround = (
            5 if assignment.arrival_terminal == DepartureTerminal.TERMINAL_1 else 20
        )
        assert assignment.ready_time == assignment.arrival_time + expected_turnaround * 60


def test_ready_at_same_timestamp_is_available_before_departure() -> None:
    problem = _two_trip_turnaround_problem(
        inbound_departure=6 * 3600 + 50 * 60,
        fleet_limit=1,
    )
    candidate = _baseline_candidate(problem)
    assignment = assign_contract_v1_fleet(
        candidate.exact_timetable,
        problem.normalized_inputs.scenario_b.exact_timetable,
        problem.normalized_inputs.scenario_b.turnaround_minutes,
        problem.normalized_inputs.scenario_b.available_fleet_limit,
    )
    validation = validate_and_build_solution_v1(problem, candidate)

    assert assignment.vehicle_count == 1
    assert assignment.assignments[0].ready_time == assignment.assignments[1].departure_time
    assert assignment.assignments[0].vehicle_id == assignment.assignments[1].vehicle_id
    assert validation.status == CandidateValidationStatus.ACCEPTED


def test_candidate_requiring_shorter_terminal_2_turnaround_is_rejected() -> None:
    problem = _two_trip_turnaround_problem(
        inbound_departure=6 * 3600 + 49 * 60,
        fleet_limit=1,
    )
    candidate = _baseline_candidate(problem)

    validation = validate_and_build_solution_v1(problem, candidate)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "AVAILABLE_FLEET_LIMIT_EXCEEDED" in validation.rejection_codes
    assert validation.fleet_assessment is not None
    assert validation.fleet_assessment.minimum_required_fleet == 2


def test_problem_rejects_low_demand_evaluation_for_high_demand_bundle() -> None:
    high_problem, parameters, trips, demand, _ = _problem()
    low_parameters, low_trips, low_demand, fleet_limit = _fixture(low_demand=True)
    low_normalized = _normalized(
        low_parameters,
        low_trips,
        low_demand,
        fleet_limit,
    )
    low_evaluation = evaluate_scenario_b_v1(low_normalized)
    assert (
        low_evaluation.evaluation.disposition
        == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE
    )

    with pytest.raises(ScheduleProblemError) as raised:
        build_schedule_problem_v1(
            high_problem.normalized_inputs,
            low_evaluation,
            parameters,
            trips,
            demand,
            ScenarioCConfig(),
        )

    assert raised.value.code == "B_EVALUATION_PROVENANCE_MISMATCH"


def test_problem_rejects_evaluation_from_different_policy() -> None:
    problem, parameters, trips, demand, _ = _problem()
    different_policy = replace(
        problem.evaluation_policy,
        planning_load_factor_ceiling=0.50,
    )

    with pytest.raises(ScheduleProblemError) as raised:
        build_schedule_problem_v1(
            problem.normalized_inputs,
            problem.b_evaluation,
            parameters,
            trips,
            demand,
            ScenarioCConfig(),
            different_policy,
        )

    assert raised.value.code == "B_EVALUATION_PROVENANCE_MISMATCH"


def test_problem_rejects_altered_block_evidence_with_same_disposition() -> None:
    problem, parameters, trips, demand, _ = _problem()
    first = problem.b_evaluation.b_block_supply[0]
    altered = replace(
        problem.b_evaluation,
        b_block_supply=(
            replace(first, shortage=first.shortage + 1),
            *problem.b_evaluation.b_block_supply[1:],
        ),
    )
    assert altered.evaluation.disposition == problem.b_evaluation.evaluation.disposition

    with pytest.raises(ScheduleProblemError) as raised:
        build_schedule_problem_v1(
            problem.normalized_inputs,
            altered,
            parameters,
            trips,
            demand,
            ScenarioCConfig(),
            problem.evaluation_policy,
        )

    assert raised.value.code == "B_EVALUATION_PROVENANCE_MISMATCH"


def test_problem_rejects_altered_fleet_evidence_with_same_disposition() -> None:
    problem, parameters, trips, demand, _ = _problem()
    altered = replace(
        problem.b_evaluation,
        fleet_assessment=replace(
            problem.b_evaluation.fleet_assessment,
            minimum_required_fleet=(
                problem.b_evaluation.fleet_assessment.minimum_required_fleet + 1
            ),
        ),
    )
    assert altered.evaluation.disposition == problem.b_evaluation.evaluation.disposition

    with pytest.raises(ScheduleProblemError) as raised:
        build_schedule_problem_v1(
            problem.normalized_inputs,
            altered,
            parameters,
            trips,
            demand,
            ScenarioCConfig(),
            problem.evaluation_policy,
        )

    assert raised.value.code == "B_EVALUATION_PROVENANCE_MISMATCH"


def test_problem_rejects_legacy_parameter_drift() -> None:
    problem, parameters, trips, demand, _ = _problem()

    with pytest.raises(ScheduleProblemError, match="vehicle_capacity"):
        build_schedule_problem_v1(
            problem.normalized_inputs,
            problem.b_evaluation,
            replace(parameters, vehicle_capacity_passengers=61),
            trips,
            demand,
            ScenarioCConfig(),
            problem.evaluation_policy,
        )


def test_runner_executes_valid_problem_when_b_is_demand_suitable() -> None:
    problem, *_ = _problem(low_demand=True)
    assert (
        problem.b_evaluation.evaluation.disposition
        == BDisposition.TECHNICALLY_FEASIBLE_AND_DEMAND_SUITABLE
    )
    solver = _StaticSolver(
        SolverRunResultV1(
            execution_status=SolverExecutionStatus.COMPLETED,
            solver_status=NativeSolverStatus.UNKNOWN,
            solver_adapter=problem.problem.solver_adapter,
            solve_duration_seconds=0.01,
            candidate=None,
            explanations=("Execution-focused runner invoked the solver.",),
            limitations=(),
        )
    )

    outcome = run_schedule_solver_v1(problem, solver)

    assert solver.call_count == 1
    assert outcome.result_status == GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.UNKNOWN
    assert outcome.solution is None


def test_runner_module_contains_no_upstream_business_no_run_gates() -> None:
    source = Path(solver_orchestration_module.__file__).read_text(encoding="utf-8")

    assert "BDisposition" not in source
    assert "assess_demand_coverage_v1" not in source
    assert "SolverExecutionStatus.NOT_RUN" not in source
    assert "C_NOT_REQUIRED_B_SUITABLE" not in source


def test_runner_executes_valid_problem_without_demand_business_authority() -> None:
    parameters, trips, _, fleet_limit = _fixture()
    imported = ImportedWorkbook(
        parameters_a=None,
        trips_a=[],
        parameters_b=parameters,
        trips_b=trips,
        demand=[],
        configuration={},
    )
    normalized = normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="solver-no-demand",
            imported_at=datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_b=fleet_limit,
        ),
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        [],
        ScenarioCConfig(),
    )
    solver = _StaticSolver(
        SolverRunResultV1(
            execution_status=SolverExecutionStatus.COMPLETED,
            solver_status=NativeSolverStatus.UNKNOWN,
            solver_adapter=problem.problem.solver_adapter,
            solve_duration_seconds=0.01,
            candidate=None,
            explanations=("Execution-focused runner invoked the solver.",),
            limitations=(),
        )
    )

    outcome = run_schedule_solver_v1(problem, solver)

    assert solver.call_count == 1
    assert outcome.result_status == GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.UNKNOWN
    assert outcome.solution is None


def test_runner_does_not_apply_combined_demand_business_gate() -> None:
    parameters, trips, _, fleet_limit = _fixture()
    combined_demand = [
        DemandRecord(
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 7),
            observation_days=1,
            block_start_seconds=(6 + index) * 3600,
            block_end_seconds=(7 + index) * 3600,
            direction=Direction.COMBINED,
            passenger_volume=300 if index == 0 else 0,
            volume_type=VolumeType.AVERAGE_DAY,
        )
        for index in range(7)
    ]
    normalized = _normalized(
        parameters,
        trips,
        combined_demand,
        fleet_limit,
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        combined_demand,
        ScenarioCConfig(),
    )
    solver = _StaticSolver(
        SolverRunResultV1(
            execution_status=SolverExecutionStatus.COMPLETED,
            solver_status=NativeSolverStatus.UNKNOWN,
            solver_adapter=problem.problem.solver_adapter,
            solve_duration_seconds=0.01,
            candidate=None,
            explanations=("Execution-focused runner invoked the solver.",),
            limitations=(),
        )
    )

    outcome = run_schedule_solver_v1(problem, solver)

    assert (
        evaluation.evaluation.disposition == BDisposition.TECHNICALLY_FEASIBLE_BUT_DEMAND_UNSUITABLE
    )
    assert solver.call_count == 1
    assert outcome.result_status == GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.UNKNOWN
    assert outcome.solver_adapter == problem.problem.solver_adapter
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is None


def test_runner_maps_native_infeasible_without_a_disposition_business_gate() -> None:
    parameters, trips, _, _ = _fixture()
    normalized = _normalized(parameters, trips, [], 1)
    evaluation = evaluate_scenario_b_v1(normalized)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        [],
        ScenarioCConfig(),
    )
    solver = _StaticSolver(
        SolverRunResultV1(
            execution_status=SolverExecutionStatus.COMPLETED,
            solver_status=NativeSolverStatus.INFEASIBLE,
            solver_adapter=problem.problem.solver_adapter,
            solve_duration_seconds=0.01,
            candidate=None,
            explanations=("Solver proved the encoded problem infeasible.",),
            limitations=(),
        )
    )

    outcome = run_schedule_solver_v1(problem, solver)

    assert (
        evaluation.evaluation.disposition
        == BDisposition.TECHNICALLY_INFEASIBLE_BUT_PARAMETERS_MAY_ALLOW_REDISTRIBUTION
    )
    assert solver.call_count == 1
    assert outcome.result_status == GenerationResultStatus.NO_FEASIBLE_C_WITH_B_PARAMETERS
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.INFEASIBLE


def test_case_25_unbound_fixed_parameter_proof_is_model_invalid() -> None:
    parameters, trips, _, fleet_limit = _fixture()
    normalized = _normalized(parameters, trips, [], fleet_limit)
    evaluation = evaluate_scenario_b_v1(normalized)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        [],
        ScenarioCConfig(),
    )
    proven = replace(
        problem,
        b_evaluation=replace(
            problem.b_evaluation,
            evaluation=replace(
                problem.b_evaluation.evaluation,
                disposition=BDisposition.PARAMETERS_INFEASIBLE,
            ),
        ),
    )

    outcome = run_schedule_solver_v1(proven, _BombSolver())

    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.MODEL_INVALID
    assert any("PROBLEM_EVALUATION_FINGERPRINT_MISMATCH" in item for item in outcome.explanations)
    assert outcome.solution is None


def test_case_26_direct_candidate_validation_rejects_missing_c_authority() -> None:
    full_problem, parameters, trips, _, fleet_limit = _problem()
    candidate = _candidate(full_problem)
    normalized = _normalized(parameters, trips, [], fleet_limit)
    evaluation = evaluate_scenario_b_v1(normalized)
    incomplete_problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        [],
        ScenarioCConfig(),
    )
    bypass_candidate = _refingerprint(incomplete_problem, candidate)

    validation = validate_and_build_solution_v1(
        incomplete_problem,
        bypass_candidate,
    )

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "DEMAND_COVERAGE_INCOMPLETE_FOR_AUTHORITATIVE_C" in validation.rejection_codes
    assert validation.solution is None


def test_case_28_coverage_change_alters_problem_fingerprint() -> None:
    full_problem, parameters, trips, demand, fleet_limit = _problem()
    gapped_demand = [item for item in demand if item.block_start_seconds < 12 * 3600]
    gapped_normalized = _normalized(
        parameters,
        trips,
        gapped_demand,
        fleet_limit,
    )
    gapped_evaluation = evaluate_scenario_b_v1(gapped_normalized)
    gapped_problem = build_schedule_problem_v1(
        gapped_normalized,
        gapped_evaluation,
        parameters,
        trips,
        gapped_demand,
        ScenarioCConfig(),
    )

    assert full_problem.problem_fingerprint != gapped_problem.problem_fingerprint
    assert full_problem.b_evaluation.demand_resolution.coverage_assessment.directional_c_generation_supported
    assert not (
        gapped_problem.b_evaluation.demand_resolution.coverage_assessment.directional_c_generation_supported
    )


def test_heuristic_candidate_matches_legacy_times_and_balanced_regime_is_accepted() -> None:
    parameters, trips, demand, fleet_limit = _fixture()
    demand = [
        (replace(item, passenger_volume=0) if item.block_start_seconds == 12 * 3600 else item)
        for item in demand
    ]
    normalized = _normalized(parameters, trips, demand, fleet_limit)
    policy = ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(normalized, policy)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        parameters,
        trips,
        demand,
        ScenarioCConfig(),
        policy,
    )
    baseline = tuple(trips)
    baseline_fingerprint = timetable_fingerprint(trips)
    scenario_b_before = problem.normalized_inputs.scenario_b

    direct = generate_scenario_c(
        parameters,
        trips,
        demand,
        fleet_limit,
        _heuristic_context(problem).heuristic_config,
    )
    solver = HeuristicScheduleSolverAdapter()
    run = solver.solve(problem)
    outcome = run_schedule_solver_v1(problem, solver)

    assert problem.b_evaluation.demand_resolution.coverage_assessment.directional_c_generation_supported
    assert run.candidate is not None
    assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.FEASIBLE
    assert outcome.solution is not None
    assert outcome.diagnostic_candidate is None
    assert all(
        regime.regularity_status in {"REGULAR", "BALANCED_ROUNDING"}
        for regime in outcome.solution.c_headway_regimes
    )
    assert tuple(trips) == baseline
    assert timetable_fingerprint(trips) == baseline_fingerprint
    assert problem.normalized_inputs.scenario_b == scenario_b_before
    assert _heuristic_context(problem).legacy_parameters.effective_layover_minutes == (
        parameters.effective_layover_minutes
    )
    direct_times = {trip.source_b_trip_id: trip.departure_seconds for trip in direct.trips}
    adapter_times = {
        trip.source_b_trip_id: trip.c_departure_time for trip in run.candidate.exact_timetable
    }
    assert adapter_times == direct_times


def test_heuristic_exhaustion_is_unknown_not_infeasible() -> None:
    config = ScenarioCConfig(
        preferred_max_shift_per_trip_minutes=0,
        absolute_max_shift_per_trip_minutes=0,
    )
    problem, *_ = _problem(config=config)
    solver = HeuristicScheduleSolverAdapter()

    run = solver.solve(problem)
    outcome = run_schedule_solver_v1(problem, solver)

    assert run.solver_status == NativeSolverStatus.UNKNOWN
    assert run.candidate is None
    assert outcome.result_status == GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT
    assert outcome.solver_status == NativeSolverStatus.UNKNOWN
    assert outcome.solution is None


def test_tampered_runtime_is_rejected_as_diagnostic_only() -> None:
    problem, *_ = _problem()
    run = HeuristicScheduleSolverAdapter().solve(problem)
    assert run.candidate is not None
    first = run.candidate.exact_timetable[0]
    tampered_trip = replace(
        first,
        runtime_minutes=first.runtime_minutes + 1,
        arrival_time=first.arrival_time + 60,
    )
    tampered = replace(
        run.candidate,
        exact_timetable=(tampered_trip, *run.candidate.exact_timetable[1:]),
    )

    validation = validate_and_build_solution_v1(problem, tampered)
    outcome = run_schedule_solver_v1(
        problem,
        _StaticSolver(replace(run, candidate=tampered)),
    )

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "SOURCE_RUNTIME_LOCK_VIOLATION" in validation.rejection_codes
    assert outcome.result_status == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is not None


def test_candidate_arrival_inconsistent_with_locked_source_runtime_is_rejected() -> None:
    problem, _, _ = _runtime_problem()
    candidate = _baseline_candidate(problem)
    first = candidate.exact_timetable[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=(
                replace(first, arrival_time=first.arrival_time + 60),
                *candidate.exact_timetable[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "CANDIDATE_ARRIVAL_RUNTIME_MISMATCH" in validation.rejection_codes
    assert "SOURCE_RUNTIME_LOCK_VIOLATION" not in validation.rejection_codes
    assert "CANDIDATE_FINGERPRINT_MISMATCH" not in validation.rejection_codes


def test_accepted_arrivals_and_ready_times_use_source_runtime_and_arrival_terminal() -> None:
    problem, _, _ = _runtime_problem()
    candidate = _baseline_candidate(problem)

    validation = validate_and_build_solution_v1(problem, candidate)

    assert validation.solution is not None
    source_by_id = {
        trip.trip_id: trip for trip in problem.normalized_inputs.scenario_b.exact_timetable
    }
    candidate_by_id = {trip.c_trip_id: trip for trip in candidate.exact_timetable}
    for assignment in validation.solution.fleet_assignment:
        raw = candidate_by_id[assignment.c_trip_id]
        source = source_by_id[raw.source_b_trip_id]
        assert assignment.arrival_time == raw.c_departure_time + source.runtime_minutes * 60
        assert assignment.ready_time == assignment.arrival_time + 5 * 60
    locks = {lock.field: lock.value for lock in validation.solution.operating_parameter_locks}
    assert locks["trip_runtime_minutes"] == 60
    assert locks["exact_trip_runtime_minutes_by_source_b_trip_id"] == {
        trip_id: source_by_id[trip_id].runtime_minutes for trip_id in sorted(source_by_id)
    }
    assert locks["turnaround_minutes"] == {"terminal_1": 5, "terminal_2": 5}
    assert locks["turnaround_application_mode"] == TURNAROUND_APPLICATION_MODE


def test_shift_claim_is_rejected_even_with_valid_candidate_fingerprint() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    target = next(item for item in candidate.exact_timetable if item.shift_minutes == -4)
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=tuple(
                replace(item, shift_minutes=0) if item.c_trip_id == target.c_trip_id else item
                for item in candidate.exact_timetable
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "SHIFT_MINUTES_MISMATCH" in validation.rejection_codes
    assert "CANDIDATE_FINGERPRINT_MISMATCH" not in validation.rejection_codes


def test_previous_b_headway_claim_is_independently_checked() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    target = next(item for item in candidate.exact_timetable if item.previous_b_headway is not None)
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=tuple(
                replace(
                    item,
                    previous_b_headway=item.previous_b_headway + 1,
                )
                if item.c_trip_id == target.c_trip_id
                else item
                for item in candidate.exact_timetable
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "PREVIOUS_B_HEADWAY_MISMATCH" in validation.rejection_codes


def test_previous_c_headway_claim_is_independently_checked() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    target = next(item for item in candidate.exact_timetable if item.previous_c_headway is not None)
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=tuple(
                replace(
                    item,
                    previous_c_headway=item.previous_c_headway + 1,
                )
                if item.c_trip_id == target.c_trip_id
                else item
                for item in candidate.exact_timetable
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "PREVIOUS_C_HEADWAY_MISMATCH" in validation.rejection_codes


def test_duplicate_headway_regime_ids_are_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                *candidate.headway_regimes,
                replace(candidate.headway_regimes[0]),
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "DUPLICATE_HEADWAY_REGIME_ID" in validation.rejection_codes


def test_unknown_headway_regime_reference_is_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.exact_timetable[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=(
                replace(first, headway_regime_id="UNKNOWN-REGIME"),
                *candidate.exact_timetable[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_AUTHORITY_MISMATCH" in validation.rejection_codes


def test_extra_headway_regime_is_rejected_as_unknown_authority_reference() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    orphan = replace(
        candidate.headway_regimes[0],
        regime_id="ORPHAN-REGIME",
    )
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(*candidate.headway_regimes, orphan),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "UNKNOWN_HEADWAY_REGIME_REFERENCE" in validation.rejection_codes


def test_headway_regime_direction_mismatch_is_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.headway_regimes[0]
    opposite = (
        ContractDirection.INBOUND
        if first.direction == ContractDirection.OUTBOUND
        else ContractDirection.OUTBOUND
    )
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                replace(first, direction=opposite),
                *candidate.headway_regimes[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_DIRECTION_MISMATCH" in validation.rejection_codes


def test_fabricated_headway_regime_trip_count_is_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.headway_regimes[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                replace(first, trip_count=105),
                *candidate.headway_regimes[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_TRIP_COUNT_MISMATCH" in validation.rejection_codes


def test_fabricated_headway_sequence_is_rejected_with_valid_fingerprint() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.headway_regimes[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                replace(first, actual_headway_sequence=(999,)),
                *candidate.headway_regimes[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_SEQUENCE_MISMATCH" in validation.rejection_codes
    assert "CANDIDATE_FINGERPRINT_MISMATCH" not in validation.rejection_codes


def test_headway_regime_member_endpoints_are_independently_checked() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.headway_regimes[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                replace(
                    first,
                    start_time=first.start_time + 60,
                    end_time=first.end_time - 60,
                ),
                *candidate.headway_regimes[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_START_MISMATCH" in validation.rejection_codes
    assert "HEADWAY_REGIME_END_MISMATCH" in validation.rejection_codes


def test_non_positive_headway_regime_target_is_rejected() -> None:
    problem, *_ = _problem()
    candidate = _candidate(problem)
    first = candidate.headway_regimes[0]
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            headway_regimes=(
                replace(first, target_headway=0),
                *candidate.headway_regimes[1:],
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "INVALID_HEADWAY_REGIME_TARGET" in validation.rejection_codes


def test_solution_and_outcome_fingerprints_ignore_solve_duration() -> None:
    problem, *_ = _problem()
    first_candidate = _baseline_candidate(problem)
    second_candidate: RawScheduleCandidateV1 = replace(
        first_candidate,
        solve_duration_seconds=first_candidate.solve_duration_seconds + 9,
    )
    first_validation = validate_and_build_solution_v1(problem, first_candidate)
    second_validation = validate_and_build_solution_v1(problem, second_candidate)
    assert first_validation.solution is not None
    assert second_validation.solution is not None

    assert (
        first_validation.solution.solution_fingerprint
        == second_validation.solution.solution_fingerprint
    )


def test_same_b_and_status_under_different_evaluations_change_outcome_identity() -> None:
    parameters, trips, demand, fleet_limit = _fixture(low_demand=True)
    changed_demand = [replace(item, passenger_volume=item.passenger_volume + 1) for item in demand]
    first_normalized = _normalized(parameters, trips, demand, fleet_limit)
    second_normalized = _normalized(
        parameters,
        trips,
        changed_demand,
        fleet_limit,
    )
    first_evaluation = evaluate_scenario_b_v1(first_normalized)
    second_evaluation = evaluate_scenario_b_v1(second_normalized)
    first_problem = build_schedule_problem_v1(
        first_normalized,
        first_evaluation,
        parameters,
        trips,
        demand,
        ScenarioCConfig(),
    )
    second_problem = build_schedule_problem_v1(
        second_normalized,
        second_evaluation,
        parameters,
        trips,
        changed_demand,
        ScenarioCConfig(),
    )

    first = run_schedule_solver_v1(first_problem, _BombSolver())
    second = run_schedule_solver_v1(second_problem, _BombSolver())

    assert first_problem.normalized_inputs.scenario_b_fingerprint == (
        second_problem.normalized_inputs.scenario_b_fingerprint
    )
    assert first.result_status == second.result_status
    assert first.outcome_fingerprint != second.outcome_fingerprint


def test_same_b_and_status_under_different_solver_config_change_outcome_identity() -> None:
    first_problem, *_ = _problem(low_demand=True)
    second_problem, *_ = _problem(
        low_demand=True,
        config=replace(
            ScenarioCConfig(),
            configuration_version="scenario_c_regimes_v1_identity_variant",
        ),
    )

    first = run_schedule_solver_v1(first_problem, _BombSolver())
    second = run_schedule_solver_v1(second_problem, _BombSolver())

    assert first_problem.normalized_inputs.scenario_b_fingerprint == (
        second_problem.normalized_inputs.scenario_b_fingerprint
    )
    assert first.result_status == second.result_status
    assert first.outcome_fingerprint != second.outcome_fingerprint


def test_accepted_solution_fingerprint_changes_with_bound_problem_identity() -> None:
    first_problem, *_ = _problem()
    second_problem, *_ = _problem(
        config=replace(
            ScenarioCConfig(),
            configuration_version="scenario_c_regimes_v1_identity_variant",
        ),
    )

    first = run_schedule_solver_v1(
        first_problem,
        _StaticSolver(_completed_run_for_candidate(_baseline_candidate(first_problem))),
    )
    second = run_schedule_solver_v1(
        second_problem,
        _StaticSolver(_completed_run_for_candidate(_baseline_candidate(second_problem))),
    )

    assert first.solution is not None
    assert second.solution is not None
    assert [
        (item.source_b_trip_id, item.c_departure_time) for item in first.solution.c_exact_timetable
    ] == [
        (item.source_b_trip_id, item.c_departure_time) for item in second.solution.c_exact_timetable
    ]
    assert first.solution.solution_fingerprint != second.solution.solution_fingerprint


def test_solution_fingerprint_changes_with_authoritative_arrival_ready_evidence() -> None:
    first_problem, _, _ = _runtime_problem(first_runtime=55)
    second_problem, _, _ = _runtime_problem(first_runtime=56)
    first_validation = validate_and_build_solution_v1(
        first_problem,
        _baseline_candidate(first_problem),
    )
    second_validation = validate_and_build_solution_v1(
        second_problem,
        _baseline_candidate(second_problem),
    )

    assert first_validation.solution is not None
    assert second_validation.solution is not None
    first_assignment = next(
        item for item in first_validation.solution.fleet_assignment if item.c_trip_id == "C-0001"
    )
    second_assignment = next(
        item for item in second_validation.solution.fleet_assignment if item.c_trip_id == "C-0001"
    )
    assert first_assignment.arrival_time != second_assignment.arrival_time
    assert first_assignment.ready_time != second_assignment.ready_time
    assert (
        first_validation.solution.solution_fingerprint
        != second_validation.solution.solution_fingerprint
    )


def test_solver_exception_returns_sanitized_model_invalid_envelope() -> None:
    problem, *_ = _problem()

    outcome = run_schedule_solver_v1(problem, _RaisingSolver())

    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.MODEL_INVALID
    assert outcome.solver_adapter == _HeuristicScheduleSolverAdapter.adapter_id
    assert outcome.solve_duration_seconds >= 0
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is None
    assert any("SOLVER_ADAPTER_EXCEPTION" in item for item in outcome.explanations)
    serialized_explanations = " ".join(outcome.explanations)
    assert "secret workbook value" not in serialized_explanations
    assert "source.xlsx" not in serialized_explanations


def test_accepted_solution_and_outcome_match_json_schemas() -> None:
    problem, *_ = _problem()
    outcome = run_schedule_solver_v1(
        problem,
        _StaticSolver(_completed_run_for_candidate(_baseline_candidate(problem))),
    )
    assert outcome.solution is not None

    solution_payload = schedule_solution_to_contract_dict(outcome.solution)
    outcome_payload = schedule_outcome_to_contract_dict(outcome)

    assert _schema_errors(solution_payload, "schedule_solution.schema.json") == []
    assert (
        _schema_errors(
            outcome_payload,
            "schedule_generation_outcome.schema.json",
        )
        == []
    )


def test_candidate_fingerprint_tampering_is_rejected() -> None:
    problem, *_ = _problem()
    run = HeuristicScheduleSolverAdapter().solve(problem)
    assert run.candidate is not None
    tampered = replace(run.candidate, candidate_fingerprint="0" * 64)

    validation = validate_and_build_solution_v1(problem, tampered)

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "CANDIDATE_FINGERPRINT_MISMATCH" in validation.rejection_codes


def test_outcome_fingerprint_ignores_solve_duration() -> None:
    problem, *_ = _problem()
    candidate = _baseline_candidate(problem)
    run = _completed_run_for_candidate(candidate)
    first = run_schedule_solver_v1(problem, _StaticSolver(run))
    delayed_candidate = replace(
        candidate,
        solve_duration_seconds=candidate.solve_duration_seconds + 9,
    )
    delayed_run = replace(
        run,
        solve_duration_seconds=run.solve_duration_seconds + 9,
        candidate=delayed_candidate,
    )
    second = run_schedule_solver_v1(problem, _StaticSolver(delayed_run))

    assert first.outcome_fingerprint == second.outcome_fingerprint
    assert first.solution is not None
    assert second.solution is not None
    assert first.solution.solution_fingerprint == second.solution.solution_fingerprint


def test_corrected_schema_allows_zero_regime_headways() -> None:
    regime_schema = SCHEMAS["schedule_solution.schema.json"]["$defs"]["regime"]

    assert regime_schema["properties"]["actual_headway_sequence"]["items"] == {
        "type": "integer",
        "minimum": 0,
    }
    assert regime_schema["properties"]["transition_headways"]["items"] == {
        "type": "integer",
        "minimum": 0,
    }
    assert regime_schema["properties"]["exceptional_headways"]["items"] == {
        "type": "integer",
        "minimum": 0,
    }


def test_zero_headway_is_rejected_by_uniform_regime_policy() -> None:
    problem, *_ = _problem(fleet_limit_override=20)
    candidate, *_ = _zero_headway_candidate(problem)
    outcome = run_schedule_solver_v1(
        problem,
        _StaticSolver(_completed_run_for_candidate(candidate)),
    )

    assert outcome.result_status == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    assert outcome.solution is None
    assert outcome.diagnostic_candidate is not None
    assert "NON_POSITIVE_ADJACENT_HEADWAY" in (outcome.diagnostic_candidate.rejection_codes)
    assert "NON_POSITIVE_ADJACENT_HEADWAY" in (outcome.diagnostic_candidate.rejection_codes)
    assert (
        _schema_errors(
            schedule_outcome_to_contract_dict(outcome),
            "schedule_generation_outcome.schema.json",
        )
        == []
    )


def test_zero_previous_headway_claimed_as_one_is_rejected() -> None:
    problem, *_ = _problem(fleet_limit_override=20)
    candidate, _, later_id = _zero_headway_candidate(problem)
    tampered = _refingerprint(
        problem,
        replace(
            candidate,
            exact_timetable=tuple(
                replace(item, previous_c_headway=1) if item.c_trip_id == later_id else item
                for item in candidate.exact_timetable
            ),
        ),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "PREVIOUS_C_HEADWAY_MISMATCH" in validation.rejection_codes


def test_zero_regime_gap_claimed_as_one_is_rejected() -> None:
    problem, *_ = _problem(fleet_limit_override=20)
    candidate, *_ = _zero_headway_candidate(problem)
    regime_index = next(
        index
        for index, regime in enumerate(candidate.headway_regimes)
        if 0 in regime.actual_headway_sequence
    )
    regime = candidate.headway_regimes[regime_index]
    claimed = tuple(1 if item == 0 else item for item in regime.actual_headway_sequence)
    regimes = list(candidate.headway_regimes)
    regimes[regime_index] = replace(
        regime,
        actual_headway_sequence=claimed,
    )
    tampered = _refingerprint(
        problem,
        replace(candidate, headway_regimes=tuple(regimes)),
    )

    validation = validate_and_build_solution_v1(problem, tampered)

    assert "HEADWAY_REGIME_SEQUENCE_MISMATCH" in validation.rejection_codes
    assert "CANDIDATE_FINGERPRINT_MISMATCH" not in validation.rejection_codes


def test_zero_headway_with_insufficient_fleet_fails_existing_fleet_rules() -> None:
    sufficient_problem, *_ = _problem(fleet_limit_override=20)
    candidate, *_ = _zero_headway_candidate(sufficient_problem)
    insufficient_problem, *_ = _problem(fleet_limit_override=1)
    candidate_for_insufficient_problem = _refingerprint(
        insufficient_problem,
        candidate,
    )

    validation = validate_and_build_solution_v1(
        insufficient_problem,
        candidate_for_insufficient_problem,
    )

    assert validation.status == CandidateValidationStatus.REJECTED
    assert "AVAILABLE_FLEET_LIMIT_EXCEEDED" in validation.rejection_codes
    assert "NON_POSITIVE_ADJACENT_HEADWAY" in validation.rejection_codes
    assert "NON_POSITIVE_ADJACENT_HEADWAY" in validation.rejection_codes
    assert "PREVIOUS_C_HEADWAY_MISMATCH" not in validation.rejection_codes


def test_invalid_execution_state_is_completed_model_invalid_not_not_run() -> None:
    problem, *_ = _problem()
    invalid_run = SolverRunResultV1(
        execution_status=SolverExecutionStatus.NOT_RUN,
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter="invalid_test_adapter",
        solve_duration_seconds=0.1,
        candidate=None,
        explanations=("invalid",),
        limitations=(),
    )

    outcome = run_schedule_solver_v1(problem, _StaticSolver(invalid_run))

    assert outcome.execution_status == SolverExecutionStatus.COMPLETED
    assert outcome.solver_status == NativeSolverStatus.MODEL_INVALID
    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID


def test_solution_reports_modes_locks_and_actual_maximum_vehicle_use() -> None:
    problem, *_ = _problem()
    outcome = run_schedule_solver_v1(
        problem,
        _StaticSolver(_completed_run_for_candidate(_baseline_candidate(problem))),
    )
    assert outcome.solution is not None
    solution = outcome.solution
    lock_fields = {lock.field for lock in solution.operating_parameter_locks}
    assert {
        "trip_runtime_minutes",
        "fleet_constraint_mode",
        "initial_fleet_positioning_mode",
        "direction_trip_lock_mode",
        "runtime_lock_mode",
        "exact_trip_runtime_minutes_by_source_b_trip_id",
        "turnaround_minutes",
        "turnaround_application_mode",
        "heuristic_turnaround_bridge_mode",
        "heuristic_turnaround_bridge_value_minutes",
    } <= lock_fields
    locks = {lock.field: lock.value for lock in solution.operating_parameter_locks}
    assert locks["runtime_lock_mode"] == RUNTIME_LOCK_MODE
    assert locks["turnaround_application_mode"] == TURNAROUND_APPLICATION_MODE
    assert locks["heuristic_turnaround_bridge_mode"] == (HEURISTIC_TURNAROUND_BRIDGE_MODE)
    assert list(locks["exact_trip_runtime_minutes_by_source_b_trip_id"]) == sorted(
        locks["exact_trip_runtime_minutes_by_source_b_trip_id"]
    )
    assert all(
        lock.source_fingerprint == problem.normalized_inputs.scenario_b_fingerprint
        for lock in solution.operating_parameter_locks
    )
    events = []
    for assignment in solution.fleet_assignment:
        events.append((assignment.departure_time, 1))
        events.append((assignment.ready_time, -1))
    active = 0
    maximum = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        maximum = max(maximum, active)
    assert solution.maximum_simultaneous_vehicle_use == maximum
    assert maximum <= solution.minimum_required_fleet


def test_h4_typed_problem_contains_only_canonical_fields() -> None:
    field_names = {item.name for item in fields(ScheduleProblemV1)}

    assert {
        "problem_id",
        "problem_fingerprint",
        "evaluation_fingerprint",
        "scenario_a",
        "scenario_b",
        "adapter_context_fingerprint",
        "operating_parameter_locks",
        "solver_policy",
    } <= field_names
    assert {
        "normalized_inputs",
        "b_evaluation",
        "evaluation_policy",
        "legacy_parameters",
        "legacy_trips_b",
        "legacy_demand",
        "heuristic_config",
    }.isdisjoint(field_names)


def test_h4_solver_receives_only_canonical_problem() -> None:
    context, *_ = _problem()

    class _CapturingSolver:
        def __init__(self, adapter_id: str) -> None:
            self.adapter_id = adapter_id
            self.received = None

        def solve(self, problem):
            self.received = problem
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.UNKNOWN,
                solver_adapter=self.adapter_id,
                solve_duration_seconds=0,
                candidate=None,
                explanations=("No candidate.",),
                limitations=(),
            )

    solver = _CapturingSolver(context.problem.solver_adapter)
    run_schedule_solver_v1(context, solver)

    assert solver.received is context.problem
    assert isinstance(solver.received, ScheduleProblemV1)


def test_h4_full_directional_problem_serializes_and_validates_schema() -> None:
    context, *_ = _problem()

    payload = schedule_problem_to_contract_dict(context.problem)

    assert payload["problem_id"] == ("PROBLEM-" + context.problem.problem_fingerprint[:16].upper())
    assert len(payload["analysis_blocks"]) == len(context.problem.analysis_blocks)
    assert {item["direction"] for item in payload["analysis_blocks"]} == {
        "outbound",
        "inbound",
    }
    assert _schema_errors(payload, "schedule_problem.schema.json") == []


def test_h4_b_only_no_demand_problem_uses_nulls_and_empty_arrays() -> None:
    context, *_ = _b_only_problem()
    payload = schedule_problem_to_contract_dict(context.problem)

    assert payload["scenario_a"] is None
    assert payload["source_a_fingerprint"] is None
    assert payload["observed_demand_fingerprint"] is None
    assert payload["demand_response_mode"] is None
    assert payload["demand_resolution"] is None
    assert payload["analysis_blocks"] == []
    assert payload["block_requirements"] == []
    assert _schema_errors(payload, "schedule_problem.schema.json") == []


def test_h4_daily_total_demand_has_resolution_without_intraday_blocks() -> None:
    context = _daily_total_problem()
    payload = schedule_problem_to_contract_dict(context.problem)

    assert payload["observed_demand_fingerprint"] is not None
    assert payload["demand_response_mode"] == "static"
    assert payload["demand_resolution"]["source_resolution_type"] == ("daily_total")
    assert payload["analysis_blocks"] == []
    assert payload["block_requirements"] == []
    solver = _StaticSolver(
        SolverRunResultV1(
            execution_status=SolverExecutionStatus.COMPLETED,
            solver_status=NativeSolverStatus.UNKNOWN,
            solver_adapter=context.problem.solver_adapter,
            solve_duration_seconds=0.01,
            candidate=None,
            explanations=("Execution-focused runner invoked the solver.",),
            limitations=(),
        )
    )

    outcome = run_schedule_solver_v1(context, solver)

    assert solver.call_count == 1
    assert outcome.result_status == GenerationResultStatus.C_NOT_FOUND_WITHIN_SOLVE_LIMIT
    assert outcome.execution_status == SolverExecutionStatus.COMPLETED


def test_h4_scenario_a_object_and_fingerprint_are_nullable_together() -> None:
    context, *_ = _problem()
    missing_fingerprint = replace(
        context.problem,
        source_a_fingerprint=None,
    )
    missing_object = replace(
        context.problem,
        scenario_a=None,
    )

    assert "PROBLEM_SCENARIO_A_NULLABILITY_MISMATCH" in {
        item.code for item in validate_schedule_problem_v1(missing_fingerprint).issues
    }
    assert "PROBLEM_SCENARIO_A_NULLABILITY_MISMATCH" in {
        item.code for item in validate_schedule_problem_v1(missing_object).issues
    }


@pytest.mark.parametrize(
    "mutation",
    [
        lambda problem: replace(
            problem,
            observed_demand_fingerprint=None,
        ),
        lambda problem: replace(problem, demand_response_mode=None),
        lambda problem: replace(problem, demand_resolution=None),
        lambda problem: replace(problem, analysis_blocks=()),
        lambda problem: replace(problem, block_requirements=()),
    ],
)
def test_h4_demand_identity_resolution_and_blocks_must_reconcile(
    mutation,
) -> None:
    context, *_ = _problem()

    codes = {item.code for item in validate_schedule_problem_v1(mutation(context.problem)).issues}

    assert {
        "PROBLEM_DEMAND_NULLABILITY_MISMATCH",
        "PROBLEM_BLOCK_RECONCILIATION_MISMATCH",
    } & codes


def test_h4_nested_scenario_tampering_is_rejected() -> None:
    context, *_ = _problem()
    first_b = context.problem.scenario_b.exact_timetable[0]
    tampered_b = replace(
        context.problem.scenario_b,
        exact_timetable=(
            replace(first_b, runtime_minutes=first_b.runtime_minutes + 1),
            *context.problem.scenario_b.exact_timetable[1:],
        ),
    )
    assert "PROBLEM_SCENARIO_B_FINGERPRINT_MISMATCH" in {
        item.code
        for item in validate_schedule_problem_v1(
            replace(context.problem, scenario_b=tampered_b)
        ).issues
    }

    assert context.problem.scenario_a is not None
    tampered_a = replace(
        context.problem.scenario_a,
        route_name=context.problem.scenario_a.route_name + " changed",
    )
    assert "PROBLEM_SCENARIO_A_FINGERPRINT_MISMATCH" in {
        item.code
        for item in validate_schedule_problem_v1(
            replace(context.problem, scenario_a=tampered_a)
        ).issues
    }


def test_h4_evaluation_problem_fingerprint_and_problem_id_tampering_fail() -> None:
    context, *_ = _problem()
    cases = (
        (
            replace(context.problem, evaluation_fingerprint="0" * 64),
            "PROBLEM_FINGERPRINT_MISMATCH",
        ),
        (
            replace(context.problem, problem_fingerprint="0" * 64),
            "PROBLEM_FINGERPRINT_MISMATCH",
        ),
        (
            replace(context.problem, problem_id="PROBLEM-" + "0" * 16),
            "PROBLEM_ID_FINGERPRINT_MISMATCH",
        ),
    )
    for problem, expected_code in cases:
        assert expected_code in {item.code for item in validate_schedule_problem_v1(problem).issues}
    assert context.problem.problem_id == (
        "PROBLEM-" + context.problem.problem_fingerprint[:16].upper()
    )


def test_h4_duplicate_and_mismatched_block_ids_are_rejected() -> None:
    context, *_ = _problem()
    blocks = context.problem.analysis_blocks
    requirements = context.problem.block_requirements
    duplicate = replace(
        context.problem,
        analysis_blocks=(
            blocks[0],
            replace(blocks[1], block_id=blocks[0].block_id),
            *blocks[2:],
        ),
    )
    assert "PROBLEM_DUPLICATE_BLOCK_ID" in {
        item.code for item in validate_schedule_problem_v1(duplicate).issues
    }

    for changed_requirements in (
        requirements[:-1],
        (*requirements, replace(requirements[0], block_id="EXTRA-BLOCK")),
        (
            replace(
                requirements[0],
                block_id="MISMATCHED-BLOCK",
            ),
            *requirements[1:],
        ),
    ):
        changed = replace(
            context.problem,
            block_requirements=tuple(changed_requirements),
        )
        assert "PROBLEM_BLOCK_RECONCILIATION_MISMATCH" in {
            item.code for item in validate_schedule_problem_v1(changed).issues
        }


def test_h4_operating_locks_are_complete_unique_locked_and_source_bound() -> None:
    context, *_ = _problem()
    locks = context.problem.operating_parameter_locks
    cases = (
        (
            replace(context.problem, operating_parameter_locks=locks[1:]),
            "PROBLEM_LOCK_SET_INCOMPLETE",
        ),
        (
            replace(
                context.problem,
                operating_parameter_locks=(*locks, locks[0]),
            ),
            "PROBLEM_LOCK_DUPLICATE_FIELD",
        ),
        (
            replace(
                context.problem,
                operating_parameter_locks=(
                    replace(locks[0], locked=False),
                    *locks[1:],
                ),
            ),
            "PROBLEM_LOCK_SET_INCOMPLETE",
        ),
        (
            replace(
                context.problem,
                operating_parameter_locks=(
                    replace(locks[0], source_fingerprint="0" * 64),
                    *locks[1:],
                ),
            ),
            "PROBLEM_LOCK_SOURCE_MISMATCH",
        ),
        (
            replace(
                context.problem,
                operating_parameter_locks=(
                    replace(locks[0], value="tampered"),
                    *locks[1:],
                ),
            ),
            "PROBLEM_LOCK_VALUE_MISMATCH",
        ),
    )
    for problem, expected_code in cases:
        assert expected_code in {item.code for item in validate_schedule_problem_v1(problem).issues}


def test_h4_accepted_solution_reuses_exact_problem_lock_tuple() -> None:
    context, *_ = _problem()

    outcome = run_schedule_solver_v1(
        context,
        _StaticSolver(_completed_run_for_candidate(_baseline_candidate(context))),
    )

    assert outcome.solution is not None
    assert outcome.solution.operating_parameter_locks is context.problem.operating_parameter_locks


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("direction_trip_lock_mode", DirectionTripLockMode.TOTAL_ONLY),
        ("fleet_constraint_mode", FleetConstraintMode.EXACT_SCHEDULED_FLEET),
        (
            "initial_fleet_positioning_mode",
            InitialFleetPositioningMode.FIXED,
        ),
        (
            "boundary_convention",
            BoundaryConvention.HALF_OPEN_WITH_FINAL_SENTINEL,
        ),
    ],
)
def test_h4_unsupported_problem_modes_fail_closed(field, value) -> None:
    context, *_ = _problem()
    changed = replace(context.problem, **{field: value})

    assert "UNSUPPORTED_PROBLEM_MODE" in {
        item.code for item in validate_schedule_problem_v1(changed).issues
    }


def test_h4_problem_serialization_never_contains_legacy_context() -> None:
    context, *_ = _problem()

    payload = schedule_problem_to_contract_dict(context.problem)
    serialized = json.dumps(payload, sort_keys=True)

    assert "legacy_parameters" not in payload
    assert "legacy_trips_b" not in payload
    assert "legacy_demand" not in payload
    assert "heuristic_config" not in payload
    assert "preferred_max_shift_per_trip_minutes" not in serialized


def test_h4_scenario_c_config_changes_context_and_problem_identity() -> None:
    first, *_ = _problem()
    second, *_ = _problem(
        config=replace(
            ScenarioCConfig(),
            preferred_max_shift_per_trip_minutes=14,
        )
    )

    assert (
        _heuristic_context(first).context_fingerprint
        != _heuristic_context(second).context_fingerprint
    )
    assert first.problem_fingerprint != second.problem_fingerprint


def test_h4_bridge_value_changes_context_and_problem_identity() -> None:
    first, *_ = _turnaround_problem(turnaround=(5, 20))
    second, *_ = _turnaround_problem(turnaround=(5, 21))

    assert (
        _heuristic_context(first).context_fingerprint
        != _heuristic_context(second).context_fingerprint
    )
    assert first.problem_fingerprint != second.problem_fingerprint


def test_h4_legacy_demand_row_changes_context_fingerprint() -> None:
    parameters, trips, demand, fleet_limit = _fixture()
    changed_demand = [
        replace(demand[0], passenger_volume=demand[0].passenger_volume + 1),
        *demand[1:],
    ]
    first_normalized = _normalized(parameters, trips, demand, fleet_limit)
    second_normalized = _normalized(
        parameters,
        trips,
        changed_demand,
        fleet_limit,
    )
    first = build_schedule_problem_v1(
        first_normalized,
        evaluate_scenario_b_v1(first_normalized),
        parameters,
        trips,
        demand,
        ScenarioCConfig(),
    )
    second = build_schedule_problem_v1(
        second_normalized,
        evaluate_scenario_b_v1(second_normalized),
        parameters,
        trips,
        changed_demand,
        ScenarioCConfig(),
    )

    assert (
        _heuristic_context(first).context_fingerprint
        != _heuristic_context(second).context_fingerprint
    )


def test_h4_adapter_rejects_context_from_another_b_problem() -> None:
    first, *_ = _problem()
    second, *_ = _runtime_problem()

    run = _heuristic_adapter(first).solve(second.problem)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert run.candidate is None
    assert any("HEURISTIC_CONTEXT_SOURCE_MISMATCH" in item for item in run.explanations)


def test_h4_adapter_rejects_demand_context_mismatch() -> None:
    high_demand, *_ = _problem()
    low_demand, *_ = _problem(low_demand=True)

    run = _heuristic_adapter(high_demand).solve(low_demand.problem)

    assert run.solver_status == NativeSolverStatus.MODEL_INVALID
    assert run.candidate is None
    assert any("HEURISTIC_CONTEXT_DEMAND_MISMATCH" in item for item in run.explanations)


def test_h4_orchestration_rejects_wrong_adapter_without_invocation() -> None:
    context, *_ = _problem()

    outcome = run_schedule_solver_v1(context, _BombSolver())

    assert outcome.result_status == GenerationResultStatus.C_NOT_GENERATED_MODEL_INVALID
    assert outcome.solver_status == NativeSolverStatus.MODEL_INVALID
    assert any("PROBLEM_ADAPTER_CONTEXT_MISMATCH" in item for item in outcome.explanations)


def test_h4_identical_inputs_have_deterministic_context_and_problem_ids() -> None:
    first, *_ = _problem()
    second, *_ = _problem()

    assert (
        _heuristic_context(first).context_fingerprint
        == _heuristic_context(second).context_fingerprint
    )
    assert first.problem_fingerprint == second.problem_fingerprint
    assert first.problem.problem_id == second.problem.problem_id


def test_h4_generic_solver_policy_changes_problem_fingerprint() -> None:
    parameters, trips, demand, fleet_limit = _fixture()
    normalized = _normalized(parameters, trips, demand, fleet_limit)
    evaluation = evaluate_scenario_b_v1(normalized)
    first = _generic_problem(normalized, evaluation)
    second = _generic_problem(
        normalized,
        evaluation,
        solver_policy=SolverPolicyV1(random_seed=7),
    )

    assert first.problem_fingerprint != second.problem_fingerprint


def test_h4_import_timestamps_and_notes_do_not_change_problem_identity() -> None:
    parameters, trips, demand, fleet_limit = _fixture()
    normalized = _normalized(parameters, trips, demand, fleet_limit)
    assert normalized.scenario_a is not None
    assert normalized.observed_demand is not None
    changed_a = replace(
        normalized.scenario_a,
        source_metadata=replace(
            normalized.scenario_a.source_metadata,
            imported_at=datetime(2030, 1, 1, tzinfo=UTC),
            notes="Changed A note",
        ),
    )
    changed_b = replace(
        normalized.scenario_b,
        source_metadata=replace(
            normalized.scenario_b.source_metadata,
            imported_at=datetime(2030, 1, 2, tzinfo=UTC),
            notes="Changed B note",
        ),
    )
    changed_demand = replace(
        normalized.observed_demand,
        source_metadata=replace(
            normalized.observed_demand.source_metadata,
            imported_at=datetime(2030, 1, 3, tzinfo=UTC),
            notes="Changed demand note",
        ),
    )
    changed = replace(
        normalized,
        scenario_a=changed_a,
        scenario_b=changed_b,
        observed_demand=changed_demand,
    )
    first = _generic_problem(normalized, evaluate_scenario_b_v1(normalized))
    second = _generic_problem(changed, evaluate_scenario_b_v1(changed))

    assert first.problem_fingerprint == second.problem_fingerprint


def test_h4_stable_source_id_and_type_change_problem_identity() -> None:
    parameters, trips, demand, fleet_limit = _fixture()
    normalized = _normalized(parameters, trips, demand, fleet_limit)
    changed_b = replace(
        normalized.scenario_b,
        source_metadata=replace(
            normalized.scenario_b.source_metadata,
            source_type=InputSourceType.API,
            source_id="changed-stable-source",
        ),
    )
    changed = replace(normalized, scenario_b=changed_b)
    first = _generic_problem(normalized, evaluate_scenario_b_v1(normalized))
    second = _generic_problem(changed, evaluate_scenario_b_v1(changed))

    assert first.source_b_fingerprint == second.source_b_fingerprint
    assert first.problem_fingerprint != second.problem_fingerprint
