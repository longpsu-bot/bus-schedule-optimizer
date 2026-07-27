from __future__ import annotations

import inspect
from dataclasses import replace
from datetime import UTC, date, datetime

import pandas as pd
import pytest
from ortools.sat.python import cp_model

from bus_schedule_engine.contracts_v1 import (
    DemandConfidence,
    NormalizationError,
    NormalizationOptions,
    NormalizedInputBundleV1,
    OperatingDayType,
    ScenarioBEvaluationPolicyV1,
    ScenarioBInput,
    ServiceAdjustmentDecisionPolicyV1,
    ServiceAdjustmentDecisionV1,
    SolverPolicyV1,
    TerminalOccupancyLimitsV1,
    build_ortools_schedule_request_v1,
    build_service_adjustment_evaluation_context_v1,
    evaluate_scenario_b_v1,
    evaluate_service_adjustment_need_v1,
    normalize_imported_workbook_v1,
    run_schedule_solver_v1,
    scenario_fingerprint,
    scenario_to_contract_dict,
    validate_and_build_solution_v1,
)
from bus_schedule_engine.contracts_v1.evaluation import assess_scenario_b_fleet_v1
from bus_schedule_engine.contracts_v1.models import (
    ContractDirection,
    DepartureTerminal,
    ExactTimetableTrip,
    InputSourceType,
    SourceMetadata,
    TerminalDepartureTimes,
    TripsByDirection,
    TurnaroundMinutes,
)
from bus_schedule_engine.contracts_v1.ortools_quality_solver import (
    _build_quality_cp_sat_model,
)
from bus_schedule_engine.contracts_v1.ortools_solver import (
    _build_cp_sat_model,
    _build_demand_cp_sat_model,
)
from bus_schedule_engine.contracts_v1.serialization import canonical_sha256
from bus_schedule_engine.contracts_v1.service_quality_metrics import (
    SERVICE_QUALITY_OBJECTIVE_NAMES_V1,
)
from bus_schedule_engine.contracts_v1.solver_fingerprints import candidate_fingerprint
from bus_schedule_engine.contracts_v1.solver_models import NativeSolverStatus
from bus_schedule_engine.contracts_v1.terminal_occupancy import (
    TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED,
    TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED,
    TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED,
    TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,
    TERMINAL_OCCUPANCY_EVENT_ORDER,
    assess_terminal_occupancy_v1,
)
from bus_schedule_engine.importer import ImportedWorkbook, InputDataError, _parameters
from bus_schedule_engine.models import (
    DemandRecord,
    Direction,
    RouteType,
    ScenarioParameters,
    Trip,
    VolumeType,
)


def _scenario(
    *,
    outbound_minutes: tuple[int, ...] = (360, 390),
    inbound_minutes: tuple[int, ...] = (365, 395),
    outbound_runtimes: tuple[int, ...] | None = None,
    inbound_runtimes: tuple[int, ...] | None = None,
    limits: TerminalOccupancyLimitsV1 | None = None,
    fleet_limit: int = 7,
    turnaround: int = 5,
    route_id: str = "TERMINAL-OCCUPANCY",
) -> ScenarioBInput:
    outbound_runtimes = outbound_runtimes or (10,) * len(outbound_minutes)
    inbound_runtimes = inbound_runtimes or (10,) * len(inbound_minutes)
    exact = tuple(
        sorted(
            (
                *(
                    ExactTimetableTrip(
                        trip_id=f"B-O-{index:02d}",
                        direction=ContractDirection.OUTBOUND,
                        departure_terminal=DepartureTerminal.TERMINAL_1,
                        departure_time=departure * 60,
                        runtime_minutes=runtime,
                        arrival_time=(departure + runtime) * 60,
                    )
                    for index, (departure, runtime) in enumerate(
                        zip(outbound_minutes, outbound_runtimes, strict=True),
                        start=1,
                    )
                ),
                *(
                    ExactTimetableTrip(
                        trip_id=f"B-I-{index:02d}",
                        direction=ContractDirection.INBOUND,
                        departure_terminal=DepartureTerminal.TERMINAL_2,
                        departure_time=departure * 60,
                        runtime_minutes=runtime,
                        arrival_time=(departure + runtime) * 60,
                    )
                    for index, (departure, runtime) in enumerate(
                        zip(inbound_minutes, inbound_runtimes, strict=True),
                        start=1,
                    )
                ),
            ),
            key=lambda trip: (trip.departure_time, trip.trip_id),
        )
    )
    return ScenarioBInput(
        route_id=route_id,
        route_name="Terminal occupancy fixture",
        route_type=RouteType.INTRA_PROVINCIAL,
        terminal_1_name="Terminal One",
        terminal_2_name="Terminal Two",
        trip_runtime_minutes=10,
        turnaround_minutes=TurnaroundMinutes(turnaround, turnaround),
        total_daily_trips=len(exact),
        trips_by_direction=TripsByDirection(
            outbound=len(outbound_minutes),
            inbound=len(inbound_minutes),
        ),
        first_departures=TerminalDepartureTimes(
            terminal_1=outbound_minutes[0] * 60,
            terminal_2=inbound_minutes[0] * 60,
        ),
        last_departures=TerminalDepartureTimes(
            terminal_1=outbound_minutes[-1] * 60,
            terminal_2=inbound_minutes[-1] * 60,
        ),
        vehicle_capacity=60,
        available_fleet_limit=fleet_limit,
        operating_day_type=OperatingDayType.WEEKDAY,
        exact_timetable=exact,
        source_metadata=SourceMetadata(
            source_type=InputSourceType.MANUAL,
            source_id=route_id.lower(),
            imported_at=datetime(2026, 7, 27, 9, 0, tzinfo=UTC),
        ),
        terminal_occupancy_limits=limits,
    )


def _bundle(scenario: ScenarioBInput) -> NormalizedInputBundleV1:
    return NormalizedInputBundleV1(
        scenario_a=None,
        scenario_b=scenario,
        observed_demand=None,
        scenario_a_fingerprint=None,
        scenario_b_fingerprint=scenario_fingerprint(scenario),
        observed_demand_fingerprint=None,
    )


def _legacy_imported(
    *,
    outbound_minutes: tuple[int, ...],
    inbound_minutes: tuple[int, ...],
    outbound_runtimes: tuple[int, ...] | None = None,
    inbound_runtimes: tuple[int, ...] | None = None,
    fleet_limit: int = 7,
    terminal_1_limit: int | None = None,
    terminal_2_limit: int | None = None,
    with_demand: bool = True,
) -> ImportedWorkbook:
    outbound_runtimes = outbound_runtimes or (10,) * len(outbound_minutes)
    inbound_runtimes = inbound_runtimes or (10,) * len(inbound_minutes)
    parameters = ScenarioParameters(
        route_id="TERMINAL-OCCUPANCY",
        route_name="Terminal occupancy fixture",
        route_type=RouteType.INTRA_PROVINCIAL,
        trip_runtime_minutes=10,
        allowed_trip_runtime_minutes=(10,),
        total_daily_trips=len(outbound_minutes) + len(inbound_minutes),
        terminal_1_name="Terminal One",
        terminal_1_first_departure=outbound_minutes[0] * 60,
        terminal_1_last_departure=outbound_minutes[-1] * 60,
        terminal_2_name="Terminal Two",
        terminal_2_first_departure=inbound_minutes[0] * 60,
        terminal_2_last_departure=inbound_minutes[-1] * 60,
        vehicle_capacity_passengers=60,
        minimum_layover_minutes=5,
        available_fleet_limit=fleet_limit,
        operating_day_type="weekday",
        terminal_1_max_occupancy_vehicles=terminal_1_limit,
        terminal_2_max_occupancy_vehicles=terminal_2_limit,
    )
    definitions = (
        (Direction.TERMINAL_1_TO_2, outbound_minutes, outbound_runtimes, "O"),
        (Direction.TERMINAL_2_TO_1, inbound_minutes, inbound_runtimes, "I"),
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=f"B-{label}-{index:02d}",
            departure_terminal=parameters.terminal_for_direction(direction),
            direction=direction,
            departure_seconds=departure * 60,
            arrival_seconds=(departure + runtime) * 60,
        )
        for direction, departures, runtimes, label in definitions
        for index, (departure, runtime) in enumerate(
            zip(departures, runtimes, strict=True),
            start=1,
        )
    ]
    demand = []
    if with_demand:
        for direction, departures, _, _ in definitions:
            demand.append(
                DemandRecord(
                    period_start=date(2026, 7, 1),
                    period_end=date(2026, 7, 1),
                    observation_days=1,
                    block_start_seconds=departures[0] * 60,
                    block_end_seconds=(departures[-1] + 1) * 60,
                    direction=direction,
                    passenger_volume=0,
                    volume_type=VolumeType.AVERAGE_DAY,
                )
            )
    return ImportedWorkbook(
        parameters_a=replace(parameters),
        trips_a=[replace(trip, scenario="A") for trip in trips],
        parameters_b=parameters,
        trips_b=trips,
        demand=demand,
        configuration={},
    )


def _normalized(
    *,
    outbound_minutes: tuple[int, ...],
    inbound_minutes: tuple[int, ...],
    outbound_runtimes: tuple[int, ...] | None = None,
    inbound_runtimes: tuple[int, ...] | None = None,
    fleet_limit: int = 7,
    terminal_1_limit: int | None = None,
    terminal_2_limit: int | None = None,
    override_1: int | None = None,
    override_2: int | None = None,
) -> NormalizedInputBundleV1:
    return normalize_imported_workbook_v1(
        _legacy_imported(
            outbound_minutes=outbound_minutes,
            inbound_minutes=inbound_minutes,
            outbound_runtimes=outbound_runtimes,
            inbound_runtimes=inbound_runtimes,
            fleet_limit=fleet_limit,
            terminal_1_limit=terminal_1_limit,
            terminal_2_limit=terminal_2_limit,
        ),
        NormalizationOptions(
            source_id="terminal-occupancy-fixture",
            imported_at=datetime(2026, 7, 27, 9, 0, tzinfo=UTC),
            terminal_1_max_occupancy_vehicles_b=override_1,
            terminal_2_max_occupancy_vehicles_b=override_2,
            demand_confidence=DemandConfidence.HIGH,
        ),
    )


def _request(
    *,
    outbound_minutes: tuple[int, ...],
    inbound_minutes: tuple[int, ...],
    outbound_runtimes: tuple[int, ...] | None = None,
    inbound_runtimes: tuple[int, ...] | None = None,
    terminal_1_limit: int | None = None,
    terminal_2_limit: int | None = None,
):
    normalized = _normalized(
        outbound_minutes=outbound_minutes,
        inbound_minutes=inbound_minutes,
        outbound_runtimes=outbound_runtimes,
        inbound_runtimes=inbound_runtimes,
        terminal_1_limit=terminal_1_limit,
        terminal_2_limit=terminal_2_limit,
    )
    policy = ScenarioBEvaluationPolicyV1()
    evaluation = evaluate_scenario_b_v1(normalized, policy)
    context, solver = build_ortools_schedule_request_v1(
        normalized,
        evaluation,
        evaluation_policy=policy,
        solver_policy=SolverPolicyV1(time_limit_seconds=10, worker_count=1, random_seed=0),
    )
    return normalized, evaluation, context, solver


def _same_minute_scenario(
    limits: TerminalOccupancyLimitsV1 | None,
) -> ScenarioBInput:
    return _scenario(
        outbound_minutes=(0, 20),
        inbound_minutes=(9, 10),
        outbound_runtimes=(10, 10),
        inbound_runtimes=(10, 10),
        limits=limits,
        fleet_limit=7,
        route_id="SAME-MINUTE",
    )


def test_no_limits_omits_property_and_preserves_legacy_payload_fingerprint() -> None:
    scenario = _scenario()
    payload = scenario_to_contract_dict(scenario)
    assert "terminal_occupancy_limits" not in payload
    legacy_fingerprint = canonical_sha256(
        {key: value for key, value in payload.items() if key != "source_metadata"}
    )
    assert scenario_fingerprint(scenario) == legacy_fingerprint


@pytest.mark.parametrize(
    ("terminal_1", "terminal_2"),
    [(2, None), (None, 3), (2, 3)],
)
def test_one_or_both_terminal_limits_are_serialized_and_fingerprinted(
    terminal_1: int | None,
    terminal_2: int | None,
) -> None:
    limits = TerminalOccupancyLimitsV1(terminal_1, terminal_2)
    scenario = _scenario(limits=limits)
    assert scenario_to_contract_dict(scenario)["terminal_occupancy_limits"] == {
        field: value
        for field, value in (("terminal_1", terminal_1), ("terminal_2", terminal_2))
        if value is not None
    }
    assert scenario_fingerprint(scenario) != scenario_fingerprint(
        _scenario(limits=TerminalOccupancyLimitsV1(9, terminal_2))
    )


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "2"])
def test_invalid_terminal_limits_are_rejected(value: object) -> None:
    with pytest.raises(ValueError):
        TerminalOccupancyLimitsV1(terminal_1=value)  # type: ignore[arg-type]


def test_empty_terminal_limits_object_is_rejected() -> None:
    with pytest.raises(ValueError):
        TerminalOccupancyLimitsV1()


def _workbook_parameter_frame(**extra: object) -> pd.DataFrame:
    values: dict[str, object] = {
        "route_id": "R-1",
        "route_name": "Route",
        "route_type": "intra_provincial",
        "trip_runtime_minutes": 10,
        "total_daily_trips": 2,
        "terminal_1_name": "T1",
        "terminal_1_first_departure": "06:00",
        "terminal_1_last_departure": "06:00",
        "terminal_2_name": "T2",
        "terminal_2_first_departure": "06:10",
        "terminal_2_last_departure": "06:10",
        "vehicle_capacity_passengers": 60,
        **extra,
    }
    return pd.DataFrame(values.items(), columns=["key", "value"])


def test_optional_workbook_keys_import_and_normalization_override_wins() -> None:
    parameters = _parameters(
        _workbook_parameter_frame(
            terminal_1_max_occupancy_vehicles=2,
            terminal_2_max_occupancy_vehicles=3,
        ),
        "B",
    )
    assert parameters.terminal_1_max_occupancy_vehicles == 2
    assert parameters.terminal_2_max_occupancy_vehicles == 3

    normalized = _normalized(
        outbound_minutes=(360, 390),
        inbound_minutes=(365, 395),
        terminal_1_limit=2,
        terminal_2_limit=3,
        override_1=5,
    )
    assert normalized.scenario_b.terminal_occupancy_limits == TerminalOccupancyLimitsV1(5, 3)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, float("inf"), "2"])
def test_invalid_workbook_occupancy_values_are_rejected(value: object) -> None:
    with pytest.raises(InputDataError):
        _parameters(
            _workbook_parameter_frame(terminal_1_max_occupancy_vehicles=value),
            "B",
        )


def test_invalid_normalization_override_is_rejected() -> None:
    with pytest.raises(NormalizationError):
        normalize_imported_workbook_v1(
            _legacy_imported(
                outbound_minutes=(360, 390),
                inbound_minutes=(365, 395),
            ),
            NormalizationOptions(
                source_id="invalid-limit",
                imported_at=datetime(2026, 7, 27, tzinfo=UTC),
                terminal_1_max_occupancy_vehicles_b=True,  # type: ignore[arg-type]
            ),
        )


def test_capacity_is_never_inferred_from_fleet_or_timetable() -> None:
    normalized = _normalized(
        outbound_minutes=(0, 20),
        inbound_minutes=(9, 10),
        fleet_limit=7,
    )
    assert normalized.scenario_b.available_fleet_limit == 7
    assert normalized.scenario_b.terminal_occupancy_limits is None


def test_physical_profile_counts_initial_arrival_waiting_ready_and_departure() -> None:
    scenario = _scenario(
        outbound_minutes=(0, 30),
        inbound_minutes=(0, 40),
        limits=TerminalOccupancyLimitsV1(2, 2),
        turnaround=5,
    )
    fleet = assess_scenario_b_fleet_v1(scenario)
    assessment = assess_terminal_occupancy_v1(
        scenario,
        initial_terminal_1=fleet.recommended_initial_fleet_terminal_1,
        initial_terminal_2=fleet.recommended_initial_fleet_terminal_2,
    )
    terminal_1 = assessment.terminal_1
    assert terminal_1.initial_physical_occupancy == 1
    arrival = next(event for event in terminal_1.events if event.arrival_trip_ids)
    ready = next(
        event
        for event in fleet.terminal_1_events
        if event.event_type == "READY" and event.trip_id in arrival.arrival_trip_ids
    )
    assert ready.event_time > arrival.event_time
    assert arrival.occupancy_after_arrivals == 1
    later_departure = next(
        event
        for event in terminal_1.events
        if event.departure_trip_ids and event.event_time > arrival.event_time
    )
    assert later_departure.occupancy_after_departures == 0
    assert terminal_1.maximum_occupancy == 1
    assert terminal_1.remaining_capacity_margin == 1


def test_terminals_are_independent_and_one_may_remain_unevaluated() -> None:
    scenario = _scenario(limits=TerminalOccupancyLimitsV1(terminal_1=1))
    fleet = assess_scenario_b_fleet_v1(scenario)
    assessment = assess_terminal_occupancy_v1(
        scenario,
        initial_terminal_1=fleet.recommended_initial_fleet_terminal_1,
        initial_terminal_2=fleet.recommended_initial_fleet_terminal_2,
    )
    assert assessment.terminal_1.capacity == 1
    assert assessment.terminal_2.capacity is None
    assert assessment.limitations == (TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED,)


def test_missing_limits_produce_only_the_route_level_limitation() -> None:
    scenario = _scenario()
    fleet = assess_scenario_b_fleet_v1(scenario)
    assessment = assess_terminal_occupancy_v1(
        scenario,
        initial_terminal_1=fleet.recommended_initial_fleet_terminal_1,
        initial_terminal_2=fleet.recommended_initial_fleet_terminal_2,
    )
    assert assessment.limitations == (TERMINAL_OCCUPANCY_CAPACITY_NOT_EVALUATED,)


def test_exact_capacity_is_accepted_and_one_vehicle_overflow_is_rejected() -> None:
    exact = _scenario(limits=TerminalOccupancyLimitsV1(1, 1))
    exact_fleet = assess_scenario_b_fleet_v1(exact)
    exact_assessment = assess_terminal_occupancy_v1(
        exact,
        initial_terminal_1=exact_fleet.recommended_initial_fleet_terminal_1,
        initial_terminal_2=exact_fleet.recommended_initial_fleet_terminal_2,
    )
    assert exact_assessment.terminal_1.limit_binding
    assert not exact_assessment.terminal_1.limit_exceeded

    overflow = _same_minute_scenario(TerminalOccupancyLimitsV1(terminal_1=2))
    overflow_fleet = assess_scenario_b_fleet_v1(overflow)
    overflow_assessment = assess_terminal_occupancy_v1(
        overflow,
        initial_terminal_1=overflow_fleet.recommended_initial_fleet_terminal_1,
        initial_terminal_2=overflow_fleet.recommended_initial_fleet_terminal_2,
    )
    assert overflow_assessment.terminal_1.maximum_occupancy == 3
    assert overflow_assessment.terminal_1.remaining_capacity_margin == -1
    assert overflow_assessment.issue_codes == (TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED,)


def test_same_minute_arrival_is_counted_before_departure() -> None:
    scenario = _same_minute_scenario(TerminalOccupancyLimitsV1(terminal_1=2))
    fleet = assess_scenario_b_fleet_v1(scenario)
    assessment = assess_terminal_occupancy_v1(
        scenario,
        initial_terminal_1=fleet.recommended_initial_fleet_terminal_1,
        initial_terminal_2=fleet.recommended_initial_fleet_terminal_2,
    )
    event = next(event for event in assessment.terminal_1.events if event.event_time == 20 * 60)
    assert assessment.event_order == TERMINAL_OCCUPANCY_EVENT_ORDER
    assert event.arrival_trip_ids == ("B-I-02",)
    assert event.departure_trip_ids == ("B-O-02",)
    assert event.occupancy_before_arrivals == 2
    assert event.occupancy_after_arrivals == 3
    assert event.occupancy_after_departures == 2


def test_final_arrivals_after_last_departure_are_evaluated_without_boundary_resets() -> None:
    scenario = _scenario(
        outbound_minutes=(0, 20),
        inbound_minutes=(0, 40),
        limits=TerminalOccupancyLimitsV1(2, 2),
    )
    fleet = assess_scenario_b_fleet_v1(scenario)
    assessment = assess_terminal_occupancy_v1(
        scenario,
        initial_terminal_1=fleet.recommended_initial_fleet_terminal_1,
        initial_terminal_2=fleet.recommended_initial_fleet_terminal_2,
    )
    assert assessment.terminal_1.events[-1].event_time == 50 * 60
    assert assessment.terminal_1.events[-1].arrival_trip_ids == ("B-I-02",)


def test_scenario_b_separates_fleet_and_occupancy_feasibility_with_full_evidence() -> None:
    scenario = _same_minute_scenario(TerminalOccupancyLimitsV1(terminal_1=2))
    result = evaluate_scenario_b_v1(_bundle(scenario))
    assert result.evaluation.fleet_feasibility.status.value == "PASS"
    assert result.evaluation.technical_feasibility.status.value == "FAIL"
    issue = next(
        issue
        for issue in result.evaluation.technical_feasibility.issues
        if issue.code == TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED
    )
    evidence = "|".join(issue.references)
    for expected in (
        "configured_capacity=2",
        "maximum_physical_occupancy=3",
        "violating_event_time=1200",
        "arrival_trip_ids=B-I-02",
        "departure_trip_ids=B-O-02",
        "occupancy_before_arrivals=2",
        "occupancy_after_arrivals=3",
        "occupancy_after_departures=2",
    ):
        assert expected in evidence
    assert TERMINAL_2_OCCUPANCY_CAPACITY_NOT_EVALUATED in result.evaluation.limitations


def test_terminal_2_violation_uses_its_independent_exact_issue_code() -> None:
    scenario = _scenario(
        outbound_minutes=(9, 10),
        inbound_minutes=(0, 20),
        limits=TerminalOccupancyLimitsV1(terminal_2=2),
        route_id="TERMINAL-2-SAME-MINUTE",
    )
    result = evaluate_scenario_b_v1(_bundle(scenario))
    issue_codes = {issue.code for issue in result.evaluation.technical_feasibility.issues}
    assert issue_codes == {"TERMINAL_2_OCCUPANCY_CAPACITY_EXCEEDED"}
    assert TERMINAL_1_OCCUPANCY_CAPACITY_NOT_EVALUATED in result.evaluation.limitations


def test_adjustment_evaluator_requires_technical_adjustment_for_occupancy_failure() -> None:
    bundle = _bundle(_same_minute_scenario(TerminalOccupancyLimitsV1(terminal_1=2)))
    evaluation_policy = ScenarioBEvaluationPolicyV1()
    context = build_service_adjustment_evaluation_context_v1(
        bundle,
        evaluation_policy,
        ServiceAdjustmentDecisionPolicyV1(),
    )
    assessment = evaluate_service_adjustment_need_v1(context)
    assert assessment.primary_decision == ServiceAdjustmentDecisionV1.TECHNICAL_ADJUSTMENT_REQUIRED
    assert TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED in assessment.reason_codes


def test_seven_fleet_two_spaces_can_be_feasible_in_shared_cp_sat_model() -> None:
    _, _, context, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(0, 30),
        terminal_1_limit=2,
    )
    bundle = _build_cp_sat_model(context.problem)
    solver = cp_model.CpSolver()
    assert solver.solve(bundle.model) in {cp_model.OPTIMAL, cp_model.FEASIBLE}
    assert solver.value(bundle.initial_terminal_1) <= 2


def test_capacity_plus_fixed_endpoints_can_be_proven_infeasible() -> None:
    _, _, context, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(9, 10),
        outbound_runtimes=(10, 10),
        inbound_runtimes=(10, 10),
        terminal_1_limit=2,
    )
    bundle = _build_cp_sat_model(context.problem)
    solver = cp_model.CpSolver()
    assert solver.solve(bundle.model) == cp_model.INFEASIBLE


def test_cp_sat_enforces_initial_terminal_occupancy_upper_bound() -> None:
    _, _, context, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(100, 110),
        terminal_1_limit=1,
    )
    bundle = _build_cp_sat_model(context.problem)
    solver = cp_model.CpSolver()
    assert solver.solve(bundle.model) == cp_model.INFEASIBLE


def test_unspecified_terminal_adds_no_cp_sat_capacity_constraint() -> None:
    _, _, context, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(0, 30),
        terminal_1_limit=2,
    )
    bundle = _build_cp_sat_model(context.problem)
    variable_names = [variable.name for variable in bundle.model.proto.variables]
    assert any(name.startswith("occupancy_terminal_1_") for name in variable_names)
    assert not any(name.startswith("occupancy_terminal_2_") for name in variable_names)


def test_all_three_ortools_models_inherit_shared_occupancy_constraints() -> None:
    _, _, context, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(0, 30),
        terminal_1_limit=2,
    )
    hard = _build_cp_sat_model(context.problem)
    demand = _build_demand_cp_sat_model(context.problem)
    quality = _build_quality_cp_sat_model(context.problem)
    assert hard.terminal_occupancy_arrival_event_count == 2
    assert demand.hard.terminal_occupancy_arrival_event_count == 2
    assert quality.demand.hard.terminal_occupancy_arrival_event_count == 2


def test_eighty_trip_event_model_has_documented_quadratic_counts_and_no_minute_grid() -> None:
    _, _, context, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(0, 30),
        terminal_1_limit=2,
        terminal_2_limit=2,
    )
    large = _scenario(
        outbound_minutes=tuple(range(0, 400, 10)),
        inbound_minutes=tuple(range(5, 405, 10)),
        limits=TerminalOccupancyLimitsV1(40, 40),
        fleet_limit=80,
        route_id="EIGHTY-TRIP",
    )
    model = _build_cp_sat_model(replace(context.problem, scenario_b=large))
    assert model.terminal_occupancy_arrival_event_count == 80
    assert model.terminal_occupancy_binary_variable_count == 6_320
    assert model.terminal_occupancy_constraint_count == 12_722
    source = inspect.getsource(_build_cp_sat_model) + inspect.getsource(_build_demand_cp_sat_model)
    assert "operating_minutes" not in source
    assert "minute_grid" not in source


def test_accepted_candidate_explains_independently_reconstructed_occupancy() -> None:
    _, _, context, solver = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(0, 30),
        terminal_1_limit=2,
        terminal_2_limit=2,
    )
    outcome = run_schedule_solver_v1(context, solver)
    assert outcome.solution is not None
    explanation = " ".join(outcome.solution.explanations)
    assert TERMINAL_OCCUPANCY_EVENT_ORDER in explanation
    assert "terminal_1 maximum_occupancy=" in explanation
    assert "remaining_margin=" in explanation
    assert "binding=" in explanation


@pytest.mark.parametrize(
    "native_status",
    [NativeSolverStatus.OPTIMAL, NativeSolverStatus.FEASIBLE],
)
def test_native_overflow_candidate_is_still_rejected_by_independent_validator(
    native_status: NativeSolverStatus,
) -> None:
    _, _, unlimited_context, unlimited_solver = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(9, 10),
        outbound_runtimes=(10, 10),
        inbound_runtimes=(10, 10),
    )
    raw = unlimited_solver.solve(unlimited_context.problem)
    assert raw.candidate is not None
    _, _, limited_context, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(9, 10),
        outbound_runtimes=(10, 10),
        inbound_runtimes=(10, 10),
        terminal_1_limit=2,
    )
    candidate = replace(
        raw.candidate,
        solver_status=native_status,
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=limited_context.problem.problem_fingerprint,
            solver_adapter=raw.candidate.solver_adapter,
            exact_timetable=raw.candidate.exact_timetable,
            headway_regimes=raw.candidate.headway_regimes,
        ),
    )
    validation = validate_and_build_solution_v1(limited_context, candidate)
    assert not validation.passed
    assert TERMINAL_1_OCCUPANCY_CAPACITY_EXCEEDED in validation.rejection_codes
    assert validation.solution is None


def test_capacity_locks_and_problem_fingerprint_are_canonical_and_deterministic() -> None:
    _, _, first, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(0, 30),
        terminal_1_limit=2,
    )
    _, _, repeated, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(0, 30),
        terminal_1_limit=2,
    )
    _, _, changed, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(0, 30),
        terminal_1_limit=3,
    )
    locks = {lock.field: lock.value for lock in first.problem.operating_parameter_locks}
    assert locks["terminal_occupancy_limits"] == {
        "terminal_1": 2,
        "terminal_2": None,
    }
    assert locks["terminal_occupancy_event_order"] == TERMINAL_OCCUPANCY_EVENT_ORDER
    assert first.problem.problem_fingerprint == repeated.problem.problem_fingerprint
    assert first.problem.problem_fingerprint != changed.problem.problem_fingerprint
    assert not any(
        "authorization" in field or "capability" in field
        for field in locks
        if field.startswith("terminal_occupancy")
    )


def test_unsupplied_capacity_fabricates_no_operating_lock() -> None:
    _, _, context, _ = _request(
        outbound_minutes=(0, 20),
        inbound_minutes=(0, 30),
    )
    lock_fields = {lock.field for lock in context.problem.operating_parameter_locks}
    assert "terminal_occupancy_limits" not in lock_fields
    assert "terminal_occupancy_event_order" not in lock_fields


def test_no_sixteenth_objective_is_added() -> None:
    assert len(SERVICE_QUALITY_OBJECTIVE_NAMES_V1) == 15
