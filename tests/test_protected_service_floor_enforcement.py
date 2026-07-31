from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta

import pytest
from presentation_support import small_fixed_resource_fixture

import bus_schedule_engine.application_pipeline as application_pipeline
from bus_schedule_engine.application_pipeline import (
    UnifiedApplicationStatusV1,
    run_unified_application_pipeline_v1,
)
from bus_schedule_engine.contracts_v1.adapters import (
    NormalizationOptions,
    normalize_imported_workbook_v1,
)
from bus_schedule_engine.contracts_v1.models import (
    ContractDirection,
    DemandConfidence,
    DepartureTerminal,
    ExactTimetableTrip,
    InputSourceType,
    OperatingDayType,
    ScenarioBInput,
    SourceMetadata,
    TerminalDepartureTimes,
    TripsByDirection,
    TurnaroundMinutes,
)
from bus_schedule_engine.contracts_v1.public_api import evaluate_scenario_b_v1
from bus_schedule_engine.contracts_v1.serialization import canonical_sha256, scenario_fingerprint
from bus_schedule_engine.contracts_v1.solver_fingerprints import candidate_fingerprint
from bus_schedule_engine.contracts_v1.solver_models import (
    GenerationResultStatus,
    NativeSolverStatus,
    RawCandidateTripV1,
    RawScheduleCandidateV1,
    SolverExecutionStatus,
    SolverRunResultV1,
)
from bus_schedule_engine.contracts_v1.solver_orchestration import run_schedule_solver_v1
from bus_schedule_engine.contracts_v1.solver_problem import (
    build_schedule_generation_context_v1,
    build_schedule_problem_v1,
    empty_adapter_context_fingerprint,
)
from bus_schedule_engine.contracts_v1.solver_validation import validate_and_build_solution_v1
from bus_schedule_engine.importer import ImportedWorkbook
from bus_schedule_engine.models import (
    Direction,
    ProtectedServiceFloorEnforcementAuthorityV1,
    ProtectedServiceFloorEnforcementRegimeV1,
    RouteType,
    ScenarioParameters,
    Trip,
    TripRidershipDatasetMetadataV1,
    TripRidershipDirectionV1,
    TripRidershipObservationV1,
)
from bus_schedule_engine.optimization_service import (
    SolverChoice,
    analyze_and_optimize_schedule_v1,
)
from bus_schedule_engine.protected_service_floor import (
    assess_protected_service_floors_v1,
    protected_service_floor_policy_from_workbook_v1,
)
from bus_schedule_engine.protected_service_floor_codes import (
    PROTECTED_DONOR_REMOVAL,
    PROTECTED_HEADWAY_NOT_MEASURABLE_OR_INVALID,
    PROTECTED_INTERNAL_HEADWAY_ABOVE_FLOOR,
    PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_MISMATCH,
    PROTECTED_SOURCE_ORDER_VIOLATION,
    PROTECTED_SOURCE_TRIP_MISSING_OR_DUPLICATED,
    PROTECTED_TRIP_COUNT_BELOW_FLOOR,
    PROTECTED_WINDOW_END_VIOLATION,
    PROTECTED_WINDOW_START_VIOLATION,
)
from bus_schedule_engine.protected_service_floor_enforcement import (
    PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
    ProtectedServiceFloorEnforcementAuthorityError,
    _authority_fingerprint_payload,
    build_protected_service_floor_enforcement_authority_v1,
    validate_candidate_against_protected_service_floors_v1,
)
from bus_schedule_engine.trip_ridership import analyze_trip_ridership_v1

BASE = 6 * 3600


def _scenario(
    outbound_minutes: tuple[int, ...] = (0, 15, 30),
    inbound_minutes: tuple[int, ...] = (),
) -> ScenarioBInput:
    exact: list[ExactTimetableTrip] = []
    for direction, prefix, terminal, offsets in (
        (
            ContractDirection.OUTBOUND,
            "O",
            DepartureTerminal.TERMINAL_1,
            outbound_minutes,
        ),
        (
            ContractDirection.INBOUND,
            "I",
            DepartureTerminal.TERMINAL_2,
            inbound_minutes,
        ),
    ):
        for index, minutes in enumerate(offsets, start=1):
            departure = BASE + minutes * 60
            exact.append(
                ExactTimetableTrip(
                    trip_id=f"{prefix}{index:02d}",
                    direction=direction,
                    departure_terminal=terminal,
                    departure_time=departure,
                    runtime_minutes=30,
                    arrival_time=departure + 30 * 60,
                )
            )
    return ScenarioBInput(
        route_id="M6A2B",
        route_name="Protected enforcement fixture",
        route_type=RouteType.INTRA_PROVINCIAL,
        terminal_1_name="T1",
        terminal_2_name="T2",
        trip_runtime_minutes=30,
        turnaround_minutes=TurnaroundMinutes(terminal_1=5, terminal_2=5),
        total_daily_trips=len(exact),
        trips_by_direction=TripsByDirection(
            outbound=len(outbound_minutes),
            inbound=len(inbound_minutes),
        ),
        first_departures=TerminalDepartureTimes(
            terminal_1=BASE + (outbound_minutes[0] if outbound_minutes else 0) * 60,
            terminal_2=BASE + (inbound_minutes[0] if inbound_minutes else 0) * 60,
        ),
        last_departures=TerminalDepartureTimes(
            terminal_1=BASE + (outbound_minutes[-1] if outbound_minutes else 0) * 60,
            terminal_2=BASE + (inbound_minutes[-1] if inbound_minutes else 0) * 60,
        ),
        vehicle_capacity=100,
        available_fleet_limit=20,
        approved_active_fleet=10,
        operating_day_type=OperatingDayType.WEEKDAY,
        exact_timetable=tuple(exact),
        source_metadata=SourceMetadata(
            source_type=InputSourceType.XLSX,
            source_id="m6a2b-fixture",
            imported_at=datetime(2026, 7, 31, tzinfo=UTC),
        ),
    )


def _imported(
    scenario: ScenarioBInput,
    *,
    configuration: dict[str, object] | None = None,
) -> ImportedWorkbook:
    parameters = ScenarioParameters(
        route_id=scenario.route_id,
        route_name=scenario.route_name,
        route_type=scenario.route_type,
        trip_runtime_minutes=30,
        total_daily_trips=scenario.total_daily_trips,
        terminal_1_name="T1",
        terminal_1_first_departure=scenario.first_departures.terminal_1,
        terminal_1_last_departure=scenario.last_departures.terminal_1,
        terminal_2_name="T2",
        terminal_2_first_departure=scenario.first_departures.terminal_2,
        terminal_2_last_departure=scenario.last_departures.terminal_2,
        vehicle_capacity_passengers=100,
        target_load_factor=0.85,
        maximum_load_factor=0.90,
        minimum_layover_minutes=5,
        allowed_trip_runtime_minutes=(30,),
        available_fleet_limit=20,
        approved_active_fleet=10,
        operating_day_type="weekday",
    )
    trips = [
        Trip(
            scenario="B",
            trip_id=trip.trip_id,
            departure_terminal="T1" if trip.direction == ContractDirection.OUTBOUND else "T2",
            direction=(
                Direction.TERMINAL_1_TO_2
                if trip.direction == ContractDirection.OUTBOUND
                else Direction.TERMINAL_2_TO_1
            ),
            departure_seconds=trip.departure_time,
            arrival_seconds=trip.resolved_arrival_time,
        )
        for trip in scenario.exact_timetable
    ]
    observations = tuple(
        TripRidershipObservationV1(
            observation_id=f"{trip.trip_id}-D{day_index}",
            service_date=date(2026, 7, 1) + timedelta(days=day_index),
            source_trip_id=None,
            scheduled_trip_id=trip.trip_id,
            direction=TripRidershipDirectionV1(trip.direction.value),
            scheduled_departure_seconds=trip.departure_time,
            actual_departure_seconds=None,
            passenger_count=90,
            vehicle_id=None,
            notes=None,
        )
        for trip in scenario.exact_timetable
        for day_index in range(3)
    )
    return ImportedWorkbook(
        parameters_a=None,
        trips_a=[],
        parameters_b=parameters,
        trips_b=trips,
        demand=[],
        configuration=configuration or {},
        trip_ridership_metadata=TripRidershipDatasetMetadataV1(
            dataset_id="M6A2B-RIDERSHIP",
            source_type="manual_count",
            confidence="medium",
            observed_schedule_scenario="B",
            operating_day_type="weekday",
            match_tolerance_minutes=5,
        ),
        trip_ridership_observations=observations,
    )


def _authority(
    scenario: ScenarioBInput | None = None,
    *,
    configuration: dict[str, object] | None = None,
):
    scenario = scenario or _scenario()
    imported = _imported(scenario, configuration=configuration)
    analysis = analyze_trip_ridership_v1(imported, scenario)
    assessment = assess_protected_service_floors_v1(
        imported,
        scenario,
        analysis,
        protected_service_floor_policy_from_workbook_v1(imported),
    )
    authority = build_protected_service_floor_enforcement_authority_v1(
        imported,
        scenario,
        analysis,
        assessment,
    )
    return imported, scenario, analysis, assessment, authority


def _candidate(
    scenario: ScenarioBInput,
    *,
    departures: dict[str, int] | None = None,
    omitted: tuple[str, ...] = (),
    extras: tuple[tuple[str, str, ContractDirection, int], ...] = (),
    adapter: str = "heuristic_contract_v1",
) -> RawScheduleCandidateV1:
    departures = departures or {}
    rows: list[RawCandidateTripV1] = []
    for source in scenario.exact_timetable:
        if source.trip_id in omitted:
            continue
        departure = departures.get(source.trip_id, source.departure_time)
        rows.append(
            RawCandidateTripV1(
                c_trip_id=f"C-{source.trip_id}",
                source_b_trip_id=source.trip_id,
                direction=source.direction,
                departure_terminal=source.departure_terminal,
                b_departure_time=source.departure_time,
                c_departure_time=departure,
                arrival_time=departure + source.runtime_minutes * 60,
                runtime_minutes=source.runtime_minutes,
                shift_minutes=(departure - source.departure_time) / 60,
                previous_b_headway=None,
                previous_c_headway=None,
                headway_regime_id="R",
                change_reason="fixture",
            )
        )
    for c_trip_id, source_b_trip_id, direction, departure in extras:
        rows.append(
            RawCandidateTripV1(
                c_trip_id=c_trip_id,
                source_b_trip_id=source_b_trip_id,
                direction=direction,
                departure_terminal=(
                    DepartureTerminal.TERMINAL_1
                    if direction == ContractDirection.OUTBOUND
                    else DepartureTerminal.TERMINAL_2
                ),
                b_departure_time=departure,
                c_departure_time=departure,
                arrival_time=departure + 30 * 60,
                runtime_minutes=30,
                shift_minutes=0,
                previous_b_headway=None,
                previous_c_headway=None,
                headway_regime_id="R",
                change_reason="fixture-extra",
            )
        )
    return RawScheduleCandidateV1(
        solver_status=NativeSolverStatus.FEASIBLE,
        solver_adapter=adapter,
        solve_duration_seconds=0,
        candidate_fingerprint="a" * 64,
        exact_timetable=tuple(rows),
        headway_regimes=(),
        explanation="fixture",
        limitations=(),
    )


def _validate(authority, scenario, candidate):
    return validate_candidate_against_protected_service_floors_v1(
        authority,
        scenario,
        candidate,
    )


def test_current_assessment_produces_deterministic_frozen_authority() -> None:
    imported, scenario, analysis, assessment, first = _authority()
    second = build_protected_service_floor_enforcement_authority_v1(
        imported, scenario, analysis, assessment
    )

    assert first == second
    assert first.has_enforceable_regimes
    assert len(first.enforcement_fingerprint) == 64
    assert ProtectedServiceFloorEnforcementAuthorityV1.__dataclass_params__.frozen is True
    assert "__slots__" in ProtectedServiceFloorEnforcementAuthorityV1.__dict__
    with pytest.raises(FrozenInstanceError):
        first.enforcement_fingerprint = "0" * 64


@pytest.mark.parametrize("stale_part", ["policy", "load", "trip_input", "analysis", "scenario"])
def test_stale_authority_inputs_fail_closed(stale_part: str) -> None:
    imported, scenario, analysis, assessment, _ = _authority()
    if stale_part == "policy":
        imported = replace(
            imported,
            configuration={"protected_service_floor_minimum_departures_per_regime": 4},
        )
    elif stale_part == "load":
        imported = replace(
            imported,
            parameters_b=replace(imported.parameters_b, target_load_factor=0.80),
        )
    elif stale_part == "trip_input":
        imported = replace(
            imported,
            trip_ridership_observations=imported.trip_ridership_observations[:-1],
        )
    elif stale_part == "analysis":
        analysis = replace(analysis, analysis_fingerprint="0" * 64)
    else:
        scenario = replace(scenario, route_name="stale Scenario B")

    with pytest.raises(ProtectedServiceFloorEnforcementAuthorityError):
        build_protected_service_floor_enforcement_authority_v1(
            imported, scenario, analysis, assessment
        )


def test_exact_window_count_and_headway_pass_for_both_adapter_labels() -> None:
    _, scenario, _, _, authority = _authority()
    for adapter in ("heuristic_contract_v1", "ortools_cp_sat_quality_v1"):
        result = _validate(authority, scenario, _candidate(scenario, adapter=adapter))
        assert result.passed
        assert result.rejection_codes == ()


def test_balanced_internal_headways_at_the_floor_pass() -> None:
    scenario = _scenario(outbound_minutes=(0, 14, 29))
    _, _, _, _, authority = _authority(
        scenario,
        configuration={"protected_service_floor_minimum_regime_duration_minutes": 20},
    )
    result = _validate(authority, scenario, _candidate(scenario))
    assert result.passed


def test_boundary_tolerance_applies_only_to_window_edges() -> None:
    _, scenario, _, _, authority = _authority(
        configuration={
            "protected_service_floor_future_service_window_boundary_tolerance_minutes": 1
        }
    )
    result = _validate(
        authority,
        scenario,
        _candidate(
            scenario,
            departures={"O01": BASE + 60, "O03": BASE + 29 * 60},
        ),
    )
    assert result.passed


def test_additional_same_direction_trip_is_allowed_and_opposite_direction_is_ignored() -> None:
    _, scenario, _, _, authority = _authority()
    result = _validate(
        authority,
        scenario,
        _candidate(
            scenario,
            extras=(
                ("C-EXTRA-O", "UNPROTECTED-O", ContractDirection.OUTBOUND, BASE + 7 * 60),
                ("C-EXTRA-I", "UNPROTECTED-I", ContractDirection.INBOUND, BASE + 7 * 60),
            ),
        ),
    )
    assert result.passed


def test_moved_protected_source_is_donor_removal_even_with_aggregate_replacement() -> None:
    _, scenario, _, _, authority = _authority()
    result = _validate(
        authority,
        scenario,
        _candidate(
            scenario,
            departures={"O02": BASE + 60 * 60},
            extras=(("C-REPLACEMENT", "UNPROTECTED", ContractDirection.OUTBOUND, BASE + 15 * 60),),
        ),
    )
    assert PROTECTED_DONOR_REMOVAL in result.rejection_codes


def test_protected_source_crossing_is_rejected() -> None:
    _, scenario, _, _, authority = _authority()
    result = _validate(
        authority,
        scenario,
        _candidate(
            scenario,
            departures={"O01": BASE + 15 * 60, "O02": BASE},
        ),
    )
    assert PROTECTED_SOURCE_ORDER_VIOLATION in result.rejection_codes


@pytest.mark.parametrize(
    ("departures", "expected"),
    [
        ({"O01": BASE + 60}, PROTECTED_WINDOW_START_VIOLATION),
        ({"O03": BASE + 29 * 60}, PROTECTED_WINDOW_END_VIOLATION),
    ],
)
def test_protected_window_boundaries_are_exact_by_default(departures, expected) -> None:
    _, scenario, _, _, authority = _authority()
    result = _validate(authority, scenario, _candidate(scenario, departures=departures))
    assert expected in result.rejection_codes


def test_trip_count_and_internal_headway_failures_are_independent() -> None:
    _, scenario, _, _, authority = _authority()
    result = _validate(
        authority,
        scenario,
        _candidate(scenario, departures={"O02": BASE + 60 * 60}),
    )
    assert PROTECTED_TRIP_COUNT_BELOW_FLOOR in result.rejection_codes
    assert PROTECTED_INTERNAL_HEADWAY_ABOVE_FLOOR in result.rejection_codes


def test_non_positive_and_non_whole_minute_internal_headways_are_rejected() -> None:
    _, scenario, _, _, authority = _authority()
    for departure in (BASE, BASE + 15 * 60 + 30):
        result = _validate(
            authority,
            scenario,
            _candidate(
                scenario,
                extras=(("C-INVALID", "UNPROTECTED", ContractDirection.OUTBOUND, departure),),
            ),
        )
        assert PROTECTED_HEADWAY_NOT_MEASURABLE_OR_INVALID in result.rejection_codes


def test_missing_mapping_and_multiple_failures_use_stable_order() -> None:
    _, scenario, _, _, authority = _authority()
    candidate = _candidate(scenario, omitted=("O01", "O02"))
    first = _validate(authority, scenario, candidate)
    second = _validate(authority, scenario, candidate)

    assert first == second
    assert first.rejection_codes == (
        PROTECTED_SOURCE_TRIP_MISSING_OR_DUPLICATED,
        PROTECTED_WINDOW_START_VIOLATION,
        PROTECTED_TRIP_COUNT_BELOW_FLOOR,
        PROTECTED_HEADWAY_NOT_MEASURABLE_OR_INVALID,
    )


def test_duplicated_protected_source_mapping_is_rejected() -> None:
    _, scenario, _, _, authority = _authority()
    result = _validate(
        authority,
        scenario,
        _candidate(
            scenario,
            extras=(("C-DUPLICATE", "O02", ContractDirection.OUTBOUND, BASE + 15 * 60),),
        ),
    )
    assert PROTECTED_SOURCE_TRIP_MISSING_OR_DUPLICATED in result.rejection_codes


def test_authority_mismatch_is_an_explicit_candidate_rejection() -> None:
    _, scenario, _, _, authority = _authority()
    tampered = replace(authority, enforcement_fingerprint="0" * 64)
    result = _validate(tampered, scenario, _candidate(scenario))
    assert result.rejection_codes == (PROTECTED_SERVICE_FLOOR_ENFORCEMENT_AUTHORITY_MISMATCH,)


def test_direction_floors_are_isolated() -> None:
    scenario = _scenario(inbound_minutes=(0, 15, 30))
    _, _, _, _, authority = _authority(scenario)
    result = _validate(
        authority,
        scenario,
        _candidate(scenario, departures={"I02": BASE + 60 * 60}),
    )
    assert not result.passed
    assert PROTECTED_DONOR_REMOVAL in result.rejection_codes
    outbound = next(
        regime
        for regime in authority.protected_regimes
        if regime.direction == TripRidershipDirectionV1.OUTBOUND
    )
    assert outbound.ordered_b_trip_ids == ("O01", "O02", "O03")


def test_adjacent_protected_regimes_are_validated_independently() -> None:
    scenario = _scenario(outbound_minutes=(0, 10, 20, 30, 40, 50))
    regimes = (
        ProtectedServiceFloorEnforcementRegimeV1(
            regime_id="OUT-01",
            direction=TripRidershipDirectionV1.OUTBOUND,
            ordered_b_trip_ids=("O01", "O02", "O03"),
            maximum_future_c_headway_minutes=10,
            minimum_future_c_trip_count=3,
            protected_window_start=BASE,
            protected_window_end=BASE + 20 * 60,
            future_boundary_tolerance_minutes=0,
            donor_removal_prohibited=True,
        ),
        ProtectedServiceFloorEnforcementRegimeV1(
            regime_id="OUT-02",
            direction=TripRidershipDirectionV1.OUTBOUND,
            ordered_b_trip_ids=("O04", "O05", "O06"),
            maximum_future_c_headway_minutes=10,
            minimum_future_c_trip_count=3,
            protected_window_start=BASE + 30 * 60,
            protected_window_end=BASE + 50 * 60,
            future_boundary_tolerance_minutes=0,
            donor_removal_prohibited=True,
        ),
    )
    payload = {
        "scenario_b_fingerprint": scenario_fingerprint(scenario),
        "assessment_fingerprint": "1" * 64,
        "policy_fingerprint": "2" * 64,
        "regime_derivation_fingerprint": "3" * 64,
        "trip_ridership_input_fingerprint": "4" * 64,
        "trip_ridership_analysis_fingerprint": "5" * 64,
        "target_load_factor": 0.85,
        "maximum_load_factor": 0.90,
        "protected_regimes": regimes,
    }
    authority = ProtectedServiceFloorEnforcementAuthorityV1(
        **payload,
        enforcement_profile=PROTECTED_SERVICE_FLOOR_ENFORCEMENT_PROFILE,
        enforcement_fingerprint=canonical_sha256(_authority_fingerprint_payload(**payload)),
    )
    candidate = _candidate(
        scenario,
        departures={"O05": BASE + 45 * 60},
    )

    result = _validate(authority, scenario, candidate)

    assert result.rejection_codes == (PROTECTED_INTERNAL_HEADWAY_ABOVE_FLOOR,)


@pytest.mark.parametrize("adapter", ["heuristic_contract_v1", "ortools_cp_sat_quality_v1"])
def test_common_contract_validator_rejects_same_floor_violation_for_every_adapter(
    adapter: str,
) -> None:
    source_scenario = _scenario(inbound_minutes=(0, 15, 30))
    imported = _imported(source_scenario)
    normalized = normalize_imported_workbook_v1(
        imported,
        NormalizationOptions(
            source_id="m6a2b-fixture",
            imported_at=datetime(2026, 7, 31, tzinfo=UTC),
            operating_day_type_b=OperatingDayType.WEEKDAY,
            available_fleet_limit_b=20,
            demand_confidence=DemandConfidence.UNKNOWN,
        ),
    )
    scenario = normalized.scenario_b
    analysis = analyze_trip_ridership_v1(imported, scenario)
    assessment = assess_protected_service_floors_v1(
        imported,
        scenario,
        analysis,
        protected_service_floor_policy_from_workbook_v1(imported),
    )
    authority = build_protected_service_floor_enforcement_authority_v1(
        imported, scenario, analysis, assessment
    )
    evaluation = evaluate_scenario_b_v1(normalized)
    problem = build_schedule_problem_v1(
        normalized,
        evaluation,
        solver_adapter=adapter,
        adapter_context_fingerprint=empty_adapter_context_fingerprint(),
    )
    context = build_schedule_generation_context_v1(
        problem,
        normalized,
        evaluation,
        protected_service_floor_enforcement_authority=authority,
    )
    candidate = _candidate(
        scenario,
        departures={"O02": BASE + 60 * 60},
        adapter=adapter,
    )
    candidate = replace(
        candidate,
        explanation="The native solver claims the protected floor passed.",
        candidate_fingerprint=candidate_fingerprint(
            problem_fingerprint=problem.problem_fingerprint,
            solver_adapter=adapter,
            exact_timetable=candidate.exact_timetable,
            headway_regimes=candidate.headway_regimes,
        ),
    )

    result = validate_and_build_solution_v1(context, candidate)

    assert not result.passed
    assert PROTECTED_DONOR_REMOVAL in result.rejection_codes
    assert PROTECTED_TRIP_COUNT_BELOW_FLOOR in result.rejection_codes
    assert result.protected_service_floor_validation is not None

    class NativeClaimingSolver:
        adapter_id = adapter

        def solve(self, _problem):
            return SolverRunResultV1(
                execution_status=SolverExecutionStatus.COMPLETED,
                solver_status=NativeSolverStatus.FEASIBLE,
                solver_adapter=adapter,
                solve_duration_seconds=0,
                candidate=candidate,
                explanations=("Native solver claimed the protected floor passed.",),
                limitations=(),
            )

    outcome = run_schedule_solver_v1(context, NativeClaimingSolver())
    assert outcome.result_status == GenerationResultStatus.CANDIDATE_REJECTED_BY_DOMAIN_VALIDATOR
    assert outcome.diagnostic_candidate is not None
    assert PROTECTED_DONOR_REMOVAL in outcome.diagnostic_candidate.rejection_codes
    assert any("does not prove" in item for item in outcome.limitations)


def test_ordinary_pipeline_normalizes_once_and_reuses_the_same_scenario_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _imported(_scenario(inbound_minutes=(0, 15, 30)))
    calls = {"normalize": 0, "trip": 0, "assessment": 0, "optimization": 0}
    observed: dict[str, object] = {}
    real_normalize = application_pipeline.normalize_imported_workbook_v1
    real_trip = application_pipeline.analyze_trip_ridership_v1
    real_assessment = application_pipeline.assess_protected_service_floors_v1
    real_optimization = application_pipeline.analyze_and_optimize_schedule_v1

    def normalization_spy(*args, **kwargs):
        calls["normalize"] += 1
        bundle = real_normalize(*args, **kwargs)
        observed["bundle"] = bundle
        return bundle

    def trip_spy(workbook, scenario_b):
        calls["trip"] += 1
        assert scenario_b is observed["bundle"].scenario_b
        return real_trip(workbook, scenario_b)

    def assessment_spy(workbook, scenario_b, analysis, policy):
        calls["assessment"] += 1
        assert scenario_b is observed["bundle"].scenario_b
        return real_assessment(workbook, scenario_b, analysis, policy)

    def optimization_spy(*args, **kwargs):
        calls["optimization"] += 1
        assert kwargs["_normalized_inputs"] is observed["bundle"]
        return real_optimization(*args, **kwargs)

    monkeypatch.setattr(application_pipeline, "normalize_imported_workbook_v1", normalization_spy)
    monkeypatch.setattr(application_pipeline, "analyze_trip_ridership_v1", trip_spy)
    monkeypatch.setattr(application_pipeline, "assess_protected_service_floors_v1", assessment_spy)
    monkeypatch.setattr(application_pipeline, "analyze_and_optimize_schedule_v1", optimization_spy)

    run = run_unified_application_pipeline_v1(
        imported,
        source_id="m6a2b-fixture",
        imported_at=datetime(2026, 7, 31, tzinfo=UTC),
    )

    assert run.status == UnifiedApplicationStatusV1.COMPLETE
    assert calls == {"normalize": 1, "trip": 1, "assessment": 1, "optimization": 1}
    assert run.unified_result.normalized_inputs is observed["bundle"]


def test_trip_analysis_failure_blocks_scenario_c_without_hiding_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = _imported(_scenario(inbound_minutes=(0, 15, 30)))

    def fail_trip_analysis(*_args, **_kwargs):
        raise RuntimeError("raw trip rows must remain private")

    monkeypatch.setattr(
        application_pipeline,
        "analyze_trip_ridership_v1",
        fail_trip_analysis,
    )
    run = run_unified_application_pipeline_v1(
        imported,
        source_id="m6a2b-fixture",
        imported_at=datetime(2026, 7, 31, tzinfo=UTC),
    )

    assert run.status == UnifiedApplicationStatusV1.COMPLETE
    assert run.unified_result is not None
    assert run.unified_result.b_evaluation is not None
    assert run.unified_result.solver_attempted is False
    assert run.unified_result.recommended_outcome is None
    assert run.protected_service_floor_enforcement_failure is not None
    assert "raw trip rows" not in (
        run.protected_service_floor_enforcement_failure.sanitized_message
    )


@pytest.mark.parametrize("solver_choice", tuple(SolverChoice))
def test_no_protected_regimes_preserve_solver_behavior_and_fingerprints(
    solver_choice: SolverChoice,
) -> None:
    imported, options = small_fixed_resource_fixture()
    normalized = normalize_imported_workbook_v1(imported, options)
    assessment = assess_protected_service_floors_v1(
        imported,
        normalized.scenario_b,
        None,
        protected_service_floor_policy_from_workbook_v1(imported),
    )
    authority = build_protected_service_floor_enforcement_authority_v1(
        imported,
        normalized.scenario_b,
        None,
        assessment,
    )
    assert not authority.has_enforceable_regimes

    baseline = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=solver_choice,
    )
    enforced = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=solver_choice,
        protected_service_floor_enforcement_authority=authority,
        _normalized_inputs=normalized,
    )

    assert baseline.selected_action == enforced.selected_action
    assert baseline.solver_attempted == enforced.solver_attempted
    for baseline_outcome, enforced_outcome in (
        (baseline.heuristic_outcome, enforced.heuristic_outcome),
        (baseline.ortools_outcome, enforced.ortools_outcome),
    ):
        assert (baseline_outcome is None) == (enforced_outcome is None)
        if baseline_outcome is None or enforced_outcome is None:
            continue
        assert baseline_outcome.outcome_fingerprint == enforced_outcome.outcome_fingerprint
        assert baseline_outcome.result_status == enforced_outcome.result_status
        assert baseline_outcome.protected_service_floor_enforcement_fingerprint is None
        assert enforced_outcome.protected_service_floor_enforcement_fingerprint is None
        if baseline_outcome.solution is not None:
            assert enforced_outcome.solution is not None
            assert baseline_outcome.solution.solution_fingerprint == (
                enforced_outcome.solution.solution_fingerprint
            )


@pytest.mark.parametrize("solver_choice", tuple(SolverChoice))
def test_accepted_solver_outcomes_bind_enforcement_and_validation_fingerprints(
    solver_choice: SolverChoice,
) -> None:
    imported, options = small_fixed_resource_fixture()
    normalized = normalize_imported_workbook_v1(imported, options)
    observations = tuple(
        TripRidershipObservationV1(
            observation_id=f"{trip.trip_id}-D{day_index}",
            service_date=date(2026, 7, 1) + timedelta(days=day_index),
            source_trip_id=None,
            scheduled_trip_id=trip.trip_id,
            direction=TripRidershipDirectionV1(trip.direction.value),
            scheduled_departure_seconds=trip.departure_time,
            actual_departure_seconds=None,
            passenger_count=90,
            vehicle_id=None,
            notes=None,
        )
        for trip in normalized.scenario_b.exact_timetable
        for day_index in range(3)
    )
    imported = replace(
        imported,
        trip_ridership_metadata=TripRidershipDatasetMetadataV1(
            dataset_id="M6A2B-ACCEPTED",
            source_type="manual_count",
            confidence="high",
            observed_schedule_scenario="B",
            operating_day_type="weekday",
            match_tolerance_minutes=5,
        ),
        trip_ridership_observations=observations,
    )
    analysis = analyze_trip_ridership_v1(imported, normalized.scenario_b)
    assessment = assess_protected_service_floors_v1(
        imported,
        normalized.scenario_b,
        analysis,
        protected_service_floor_policy_from_workbook_v1(imported),
    )
    authority = build_protected_service_floor_enforcement_authority_v1(
        imported,
        normalized.scenario_b,
        analysis,
        assessment,
    )
    assert authority.has_enforceable_regimes

    result = analyze_and_optimize_schedule_v1(
        imported,
        options,
        solver_choice=solver_choice,
        protected_service_floor_enforcement_authority=authority,
        _normalized_inputs=normalized,
    )

    outcomes = tuple(
        outcome
        for outcome in (result.heuristic_outcome, result.ortools_outcome)
        if outcome is not None
    )
    assert outcomes
    for outcome in outcomes:
        assert outcome.result_status == GenerationResultStatus.SOLUTION_ACCEPTED
        assert outcome.solution is not None
        assert outcome.protected_service_floor_enforcement_fingerprint == (
            authority.enforcement_fingerprint
        )
        assert outcome.protected_service_floor_validation_fingerprint is not None
        assert outcome.solution.protected_service_floor_enforcement_fingerprint == (
            authority.enforcement_fingerprint
        )
        assert outcome.solution.protected_service_floor_validation_fingerprint == (
            outcome.protected_service_floor_validation_fingerprint
        )
